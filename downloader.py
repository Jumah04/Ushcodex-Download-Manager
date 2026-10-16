"""
High-Performance Chunked Multi-Stream Downloader Engine
Part of Ushcodex Download Manager (UDM)
======================================================
Features:
- Seamless URL resolution (Mediafire, Google Drive, direct links)
- Parallel segmented range downloading (16-32 connections)
- True resume: never re-downloads completed chunks
- Chunk integrity and atomic assembly
"""

import os
import sys
import time
import math
import threading
import requests

from url_resolver import resolve_download_url, DEFAULT_UA

BUFFER_SIZE = 128 * 1024  # 128KB read buffer

def human_size(bytes_val):
    if bytes_val is None or bytes_val < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"


class StreamWorker(threading.Thread):
    def __init__(self, worker_id, url, headers, start_b, end_b, part_f, update_cb, stop_event):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.url = url
        self.headers = headers.copy()
        self.start_b = start_b
        self.end_b = end_b
        self.total_chunk_bytes = (end_b - start_b) + 1
        self.part_f = part_f
        self.update_cb = update_cb
        self.stop_event = stop_event
        self.downloaded_bytes = 0
        self.status = "Queued"
        self.success = False

    def run(self):
        existing = 0
        if os.path.exists(self.part_f):
            existing = os.path.getsize(self.part_f)

        self.downloaded_bytes = existing
        self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Resumed" if existing > 0 else "Ready")

        if existing >= self.total_chunk_bytes:
            self.success = True
            self.status = "Done"
            self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Done")
            return

        cur_start = self.start_b + existing
        req_headers = self.headers.copy()
        req_headers["Range"] = f"bytes={cur_start}-{self.end_b}"

        max_retries = 8
        for attempt in range(max_retries):
            if self.stop_event.is_set():
                self.status = "Paused"
                self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Paused")
                return

            try:
                self.status = "Connecting"
                self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, self.status)

                session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=2)
                session.mount("http://", adapter)
                session.mount("https://", adapter)

                with session.get(self.url, headers=req_headers, stream=True, timeout=20) as resp:
                    if resp.status_code not in (200, 206):
                        raise Exception(f"HTTP {resp.status_code}")

                    self.status = "Downloading"
                    self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Downloading")

                    mode = "ab" if existing > 0 else "wb"
                    with open(self.part_f, mode) as f:
                        for chunk in resp.iter_content(chunk_size=BUFFER_SIZE):
                            if self.stop_event.is_set():
                                self.status = "Paused"
                                self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Paused")
                                return
                            if chunk:
                                f.write(chunk)
                                chunk_len = len(chunk)
                                self.downloaded_bytes += chunk_len
                                self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Downloading", chunk_len)

                if self.downloaded_bytes >= self.total_chunk_bytes:
                    self.success = True
                    self.status = "Done"
                    self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Done")
                    return
            except Exception as e:
                self.status = "Reconnecting..."
                self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, self.status)
                time.sleep(1.5)
                if os.path.exists(self.part_f):
                    existing = os.path.getsize(self.part_f)
                    self.downloaded_bytes = existing
                    cur_start = self.start_b + existing
                    req_headers["Range"] = f"bytes={cur_start}-{self.end_b}"

        self.status = "Failed"
        self.update_cb(self.worker_id, self.downloaded_bytes, self.total_chunk_bytes, "Failed")
