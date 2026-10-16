"""
Turbo Multi-Threaded Chunked Downloader (ABU WiFi Throttling Bypass)
====================================================================
Designed to overcome institutional per-connection bandwidth throttling (e.g. MikroTik PCQ,
Layer 7 QoS, single-stream download caps) by splitting files into parallel chunk streams
using HTTP Range requests.

Features:
- Multi-threaded segmented download (16-32 parallel connections)
- Resumable: recovers from dropped connections or campus WiFi interruptions
- Custom User-Agent & headers (bypasses basic Layer 7 QoS tagging)
- Live speed, percentage, ETA, and connection health display
- Interactive prompt if launched with no arguments, or standard CLI
"""

import os
import sys
import time
import math
import argparse
import threading
from urllib.parse import urlparse, unquote
import requests
import warp_manager

DEFAULT_WORKERS = 16
CHUNK_SIZE_BUFFER = 64 * 1024  # 64KB read buffer
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

class DownloadWorker(threading.Thread):
    def __init__(self, url, headers, start_byte, end_byte, part_file, progress_cb, worker_id):
        super().__init__()
        self.url = url
        self.headers = headers.copy()
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.part_file = part_file
        self.progress_cb = progress_cb
        self.worker_id = worker_id
        self.success = False
        self.error_msg = None
        self.downloaded_bytes = 0

    def run(self):
        # Check if already partially downloaded
        existing = 0
        if os.path.exists(self.part_file):
            existing = os.path.getsize(self.part_file)

        current_start = self.start_byte + existing
        if current_start > self.end_byte:
            self.downloaded_bytes = existing
            self.progress_cb(existing)
            self.success = True
            return

        self.downloaded_bytes = existing
        self.progress_cb(existing)

        req_headers = self.headers.copy()
        req_headers["Range"] = f"bytes={current_start}-{self.end_byte}"

        max_retries = 5
        backoff = 2
        for attempt in range(max_retries):
            try:
                with requests.get(self.url, headers=req_headers, stream=True, timeout=25) as resp:
                    if resp.status_code not in (200, 206):
                        raise Exception(f"HTTP Status {resp.status_code}")

                    mode = "ab" if existing > 0 else "wb"
                    with open(self.part_file, mode) as f:
                        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE_BUFFER):
                            if chunk:
                                f.write(chunk)
                                chunk_len = len(chunk)
                                self.downloaded_bytes += chunk_len
                                self.progress_cb(chunk_len)
                self.success = True
                return
            except Exception as e:
                self.error_msg = str(e)
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 10)
                # Recalculate remaining bytes for retry
                if os.path.exists(self.part_file):
                    current_sz = os.path.getsize(self.part_file)
                    new_dl = current_sz - existing
                    existing = current_sz
                    current_start = self.start_byte + existing
                    req_headers["Range"] = f"bytes={current_start}-{self.end_byte}"


def human_size(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"


def get_filename_from_url(url, resp_headers=None):
    if resp_headers and "Content-Disposition" in resp_headers:
        cd = resp_headers["Content-Disposition"]
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"\'; ')
            if filename:
                return filename

    parsed = urlparse(url)
    path = unquote(parsed.path)
    name = os.path.basename(path)
    if not name or "." not in name:
        return "notebooklm_overview_download.mp4"
    return name


def download_file(url, output_path=None, connections=16, custom_headers=None):
    from url_resolver import resolve_download_url
    print(f"\n[+] Resolving direct download stream...")
    final_url, detected_filename, total_length, accept_ranges, err = resolve_download_url(url, custom_headers)

    if err and not final_url:
        print(f"[-] Resolution error: {err}")
        return

    headers = {"User-Agent": DEFAULT_UA}
    if custom_headers:
        headers.update(custom_headers)

    if not output_path:
        output_path = detected_filename

    print(f"[+] Output file : {output_path}")
    print(f"[+] Total size  : {human_size(total_length) if total_length > 0 else 'Unknown'}")
    print(f"[+] Multi-stream: {'Supported (Bypassing Throttle)' if (accept_ranges and total_length > 0) else 'Not supported by server (Single connection)'}")

    # Fallback for servers that do not support Range requests
    if total_length == 0 or not accept_ranges:
        print("[!] Note: Server doesn't support segmented range requests. Downloading via single optimized stream...")
        start_time = time.time()
        with requests.get(final_url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE_BUFFER):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        sys.stdout.write(f"\rDownloaded: {human_size(downloaded)} | Speed: {human_size(speed)}/s")
                        sys.stdout.flush()
        print(f"\n[OK] Download completed: {output_path}")
        return

    # Segmented Multi-Connection Download
    connections = min(connections, 32)
    chunk_size = math.ceil(total_length / connections)
    temp_dir = f"{output_path}.turbo_parts"
    os.makedirs(temp_dir, exist_ok=True)

    progress_lock = threading.Lock()
    downloaded_total = 0

    def progress_callback(bytes_added):
        nonlocal downloaded_total
        with progress_lock:
            downloaded_total += bytes_added

    workers = []
    print(f"[+] Launching {connections} simultaneous streams across throttle queues...")

    for i in range(connections):
        start_byte = i * chunk_size
        end_byte = min((i + 1) * chunk_size - 1, total_length - 1)
        part_file = os.path.join(temp_dir, f"part_{i:03d}.tmp")
        worker = DownloadWorker(final_url, headers, start_byte, end_byte, part_file, progress_callback, i)
        workers.append(worker)

    start_time = time.time()
    for w in workers:
        w.start()

    # Progress tracking loop
    prev_downloaded = 0
    prev_time = start_time

    while any(w.is_alive() for w in workers):
        time.sleep(0.5)
        now = time.time()
        elapsed_delta = now - prev_time

        with progress_lock:
            current_dl = downloaded_total

        # Speed calculation
        if elapsed_delta >= 0.5:
            delta_bytes = current_dl - prev_downloaded
            speed = delta_bytes / elapsed_delta if elapsed_delta > 0 else 0
            prev_downloaded = current_dl
            prev_time = now

            pct = (current_dl / total_length) * 100 if total_length > 0 else 0
            rem_bytes = max(0, total_length - current_dl)
            eta_seconds = int(rem_bytes / speed) if speed > 1024 else 0
            eta_str = f"{eta_seconds // 60:02d}:{eta_seconds % 60:02d}" if speed > 1024 else "--:--"

            bar_width = 25
            filled = int(bar_width * (pct / 100))
            bar = "=" * filled + (">" if filled < bar_width else "") + " " * (bar_width - filled - 1)

            active_workers = sum(1 for w in workers if w.is_alive())
            sys.stdout.write(
                f"\r[{bar[:bar_width]}] {pct:5.1f}% | {human_size(current_dl)}/{human_size(total_length)} "
                f"| {human_size(speed)}/s | ETA: {eta_str} | Streams: {active_workers}/{connections}"
            )
            sys.stdout.flush()

    for w in workers:
        w.join()

    # Verify all succeeded
    failed = [w for w in workers if not w.success]
    if failed:
        print(f"\n[-] Error: {len(failed)} streams encountered errors: {failed[0].error_msg}")
        print("[-] You can re-run the same command; it will automatically resume without restarting!")
        return

    print("\n[+] All chunks successfully downloaded! Assembling final file...")

    # Stitch parts together
    with open(output_path, "wb") as outfile:
        for i in range(connections):
            part_file = os.path.join(temp_dir, f"part_{i:03d}.tmp")
            with open(part_file, "rb") as pf:
                while True:
                    buf = pf.read(1024 * 1024)  # 1MB buffer
                    if not buf:
                        break
                    outfile.write(buf)
            try:
                os.remove(part_file)
            except OSError:
                pass

    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    total_time = time.time() - start_time
    avg_speed = total_length / total_time if total_time > 0 else 0
    print(f"[SUCCESS] Download completed in {total_time:.1f}s (Average: {human_size(avg_speed)}/s)")
    print(f"[SUCCESS] Saved to: {os.path.abspath(output_path)}\n")


def main():
    parser = argparse.ArgumentParser(description="Turbo Multi-Threaded Chunked Downloader (WiFi Throttle Bypass)")
    parser.add_argument("url", nargs="?", help="Direct download URL or video link")
    parser.add_argument("-o", "--output", help="Custom output filename or path")
    parser.add_argument("-c", "--connections", type=int, default=DEFAULT_WORKERS, help="Number of parallel streams (default: 16)")
    parser.add_argument("-H", "--header", action="append", help="Custom header in 'Key: Value' format (e.g. Cookie)")
    parser.add_argument("--warp", action="store_true", help="Auto-connect Cloudflare WARP UDP tunnel to bypass campus throttling")

    args = parser.parse_args()

    if args.warp:
        if not warp_manager.is_warp_installed():
            print("[*] WARP not detected. Installing Cloudflare WARP...")
            warp_manager.install_warp_async()
        else:
            print("[*] Connecting Cloudflare WARP UDP tunnel...")
            warp_manager.connect_warp()

    url = args.url
    if not url:
        print("=" * 65)
        print("  ABU WiFi Throttle Bypass - Turbo Segmented Downloader")
        print("=" * 65)
        print("Paste the download URL below (e.g. from NotebookLM, Drive, or Web)")
        url = input("URL: ").strip()

    if not url:
        print("No URL provided. Exiting.")
        sys.exit(1)

    custom_headers = {}
    if args.header:
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                custom_headers[k.strip()] = v.strip()

    connections = args.connections or DEFAULT_WORKERS
    download_file(url, output_path=args.output, connections=connections, custom_headers=custom_headers)


if __name__ == "__main__":
    main()
