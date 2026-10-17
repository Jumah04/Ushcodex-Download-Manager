"""
Logging System for Ushcodex Download Manager (UDM)
===================================================
Provides persistent file logging to ushcodex_dm.log
and real-time event streaming to the UI.
"""

import os
import sys
import time
import threading

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ushcodex_dm.log")

class UdmLogger:
    def __init__(self, log_path=LOG_FILE):
        self.log_path = log_path
        self.listeners = []
        self._lock = threading.Lock()

    def add_listener(self, callback):
        with self._lock:
            self.listeners.append(callback)

    def log(self, message, level="INFO"):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{ts}] [{level}] {message}"

        # Write to log file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            pass

        # Broadcast to UI listeners
        with self._lock:
            for cb in self.listeners:
                try:
                    cb(formatted)
                except Exception:
                    pass

    def get_recent_logs(self, max_lines=150):
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-max_lines:]]
        except Exception:
            return []

    def clear(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Log cleared by user.\n")
        except Exception:
            pass

logger = UdmLogger()
