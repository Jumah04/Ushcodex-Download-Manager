"""
Persistent Download History Manager for Ushcodex Download Manager
=================================================================
Maintains download records in history.json with full hash verification,
file locations, and instant launch/delete operations.
"""

import os
import json
import time
import hashlib
import threading

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

def compute_file_sha256(filepath, progress_cb=None):
    """Computes SHA-256 hash in 1MB streaming blocks."""
    if not os.path.exists(filepath):
        return None
    sha = hashlib.sha256()
    total_size = os.path.getsize(filepath)
    read_bytes = 0
    with open(filepath, "rb") as f:
        while True:
            buf = f.read(1024 * 1024)
            if not buf:
                break
            sha.update(buf)
            read_bytes += len(buf)
            if progress_cb and total_size > 0:
                progress_cb(read_bytes / total_size)
    return sha.hexdigest()

class HistoryManager:
    def __init__(self, file_path=HISTORY_FILE):
        self.file_path = file_path
        self._lock = threading.Lock()
        self.entries = self._load()

    def _load(self):
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
        except Exception:
            pass

    def add_entry(self, url, filename, filepath, size, speed="--", sha256=None, status="Completed"):
        with self._lock:
            entry = {
                "id": str(int(time.time() * 1000)),
                "date": time.strftime("%Y-%m-%d %H:%M"),
                "filename": filename,
                "filepath": os.path.abspath(filepath),
                "url": url,
                "size": size,
                "speed": speed,
                "sha256": sha256 or "Pending",
                "status": status
            }
            # Prepend newest first
            self.entries.insert(0, entry)
            self._save()
            return entry

    def update_entry(self, entry_id, **kwargs):
        with self._lock:
            for item in self.entries:
                if item["id"] == entry_id:
                    item.update(kwargs)
                    self._save()
                    return item
        return None

    def get_all(self):
        with self._lock:
            return list(self.entries)

    def delete_entry(self, entry_id, delete_disk_file=False):
        with self._lock:
            target = None
            for item in self.entries:
                if item["id"] == entry_id:
                    target = item
                    break
            if target:
                self.entries.remove(target)
                self._save()
                if delete_disk_file and os.path.exists(target["filepath"]):
                    try:
                        os.remove(target["filepath"])
                    except Exception:
                        pass
                return True
        return False

    def clear_all(self):
        with self._lock:
            self.entries = []
            self._save()

history_manager = HistoryManager()
