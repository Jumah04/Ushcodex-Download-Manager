"""
Cloudflare WARP Integration Module for ABU WiFi Turbo Downloader
================================================================
Controls Cloudflare WARP directly from Python:
- Detects if WARP is installed and running
- Automates 1-click silent installation via winget or official MSI
- Auto-registers and connects via warp-cli
- Tunnels all multi-threaded download streams over WireGuard/UDP to bypass campus Layer-7 throttling
"""

import os
import sys
import time
import shutil
import subprocess
import threading

WARP_CLI_PATHS = [
    r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe",
    r"C:\Program Files (x86)\Cloudflare\Cloudflare WARP\warp-cli.exe",
]

def find_warp_cli():
    # Check if in PATH
    which_path = shutil.which("warp-cli")
    if which_path and os.path.exists(which_path):
        return which_path

    # Check known install directories
    for path in WARP_CLI_PATHS:
        if os.path.exists(path):
            return path
    return None

def is_warp_installed():
    return find_warp_cli() is not None

def get_warp_status():
    cli = find_warp_cli()
    if not cli:
        return "Not Installed", "WARP is not installed. Click 'Install WARP' below."

    try:
        # Run warp-cli status with timeout
        res = subprocess.run([cli, "status"], capture_output=True, text=True, timeout=5)
        out = (res.stdout + res.stderr).lower()

        if "connected" in out and "disconnected" not in out:
            return "Connected", "Active: Traffic is tunneled through Cloudflare UDP (Bypassing Throttle)"
        elif "connecting" in out:
            return "Connecting", "Connecting to Cloudflare edge..."
        elif "disconnected" in out:
            return "Disconnected", "Installed but disconnected. Click 'Enable WARP'."
        else:
            return "Ready", f"Status: {res.stdout.strip() or 'Ready'}"
    except Exception as e:
        return "Error", f"Could not check status: {e}"

def connect_warp():
    cli = find_warp_cli()
    if not cli:
        return False, "WARP is not installed."

    try:
        # Ensure registration exists first
        subprocess.run([cli, "registration", "new"], capture_output=True, timeout=10)
    except Exception:
        pass

    try:
        res = subprocess.run([cli, "connect"], capture_output=True, text=True, timeout=10)
        time.sleep(2)
        status, desc = get_warp_status()
        if status == "Connected":
            return True, "Cloudflare WARP successfully connected!"
        return False, f"WARP returned: {res.stdout.strip() or res.stderr.strip() or status}"
    except Exception as e:
        return False, f"Failed to connect: {e}"

def disconnect_warp():
    cli = find_warp_cli()
    if not cli:
        return False, "WARP is not installed."

    try:
        res = subprocess.run([cli, "disconnect"], capture_output=True, text=True, timeout=10)
        time.sleep(1)
        return True, "WARP disconnected. Restored normal Wi-Fi routing."
    except Exception as e:
        return False, f"Failed to disconnect: {e}"

def install_warp_async(progress_cb=None):
    """Installs Cloudflare WARP via winget or direct MSI installer."""
    def worker():
        if progress_cb:
            progress_cb("Starting Cloudflare WARP installation (Click 'Yes' if Windows UAC prompts)...")

        # Try winget first
        try:
            cmd = [
                "winget", "install", "--id", "Cloudflare.Warp",
                "--silent", "--accept-package-agreements", "--accept-source-agreements"
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line_str = line.strip()
                if line_str and progress_cb:
                    progress_cb(f"[winget] {line_str}")
            proc.wait()

            if is_warp_installed():
                if progress_cb:
                    progress_cb("[SUCCESS] Cloudflare WARP installed successfully! Connecting...")
                connect_warp()
                return
        except Exception as e:
            if progress_cb:
                progress_cb(f"[-] winget install note: {e}")

        # Fallback to direct download
        if not is_warp_installed():
            if progress_cb:
                progress_cb("Downloading official Cloudflare WARP installer from Cloudflare CDN...")
            import requests
            msi_url = "https://downloads.cloudflareclient.com/v1/download/windows/version/2026.8.2110.0"
            msi_dest = os.path.join(os.environ.get("TEMP", "."), "Cloudflare_WARP.msi")
            try:
                with requests.get(msi_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(msi_dest, "wb") as f:
                        for chunk in r.iter_content(65536):
                            if chunk:
                                f.write(chunk)

                if progress_cb:
                    progress_cb("Launching Cloudflare WARP installer (Please confirm the prompt on your screen)...")

                subprocess.run(["msiexec.exe", "/i", msi_dest, "/passive", "/norestart"], check=True)
                time.sleep(5)

                if is_warp_installed():
                    if progress_cb:
                        progress_cb("[SUCCESS] WARP installed! Enabling UDP tunnel...")
                    connect_warp()
                else:
                    if progress_cb:
                        progress_cb("[!] Installation launched. Please complete the installer window.")
            except Exception as e:
                if progress_cb:
                    progress_cb(f"[-] Installation failed: {e}")

    t = threading.Thread(target=worker, daemon=True)
    t.start()


if __name__ == "__main__":
    print(f"WARP Installed: {is_warp_installed()}")
    status, desc = get_warp_status()
    print(f"Status: {status} -> {desc}")
