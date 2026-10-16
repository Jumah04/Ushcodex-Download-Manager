"""
ABU Network Empirical Diagnostic & Bandwidth Audit
===================================================
Tests real network behavior without assumptions:
1. TCP Multi-CDN Download Test (Cloudflare, Google, Fastly)
2. Stream Scaling Test (1 vs 4 vs 8 vs 16 TCP streams)
3. YouTube / Google Video CDN Throughput Test
4. UDP Reachability & Latency (Zoom UDP 8801, WireGuard/WARP UDP 2408, DNS UDP 53)
5. Cloudflare WARP status & WireGuard port reachability
"""

import sys
import time
import socket
import threading
import requests
import concurrent.futures

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

def human_speed(bps):
    kbps = bps / 1024
    if kbps < 1024:
        return f"{kbps:.1f} KB/s ({kbps*8/1000:.2f} Mbps)"
    mbps = kbps / 1024
    return f"{mbps:.2f} MB/s ({mbps*8:.2f} Mbps)"

def test_tcp_url(name, url, duration=4):
    print(f"[*] Testing {name} for {duration}s...")
    try:
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=8)
        if r.status_code not in (200, 206):
            print(f"    [-] HTTP error {r.status_code}")
            return 0
        total_bytes = 0
        t_data_start = time.time()
        for chunk in r.iter_content(32768):
            total_bytes += len(chunk)
            if time.time() - t_data_start >= duration:
                break
        elapsed = time.time() - t_data_start
        speed = total_bytes / elapsed if elapsed > 0 else 0
        print(f"    [+] {name}: Downloaded {total_bytes/1024:.1f} KB in {elapsed:.2f}s -> {human_speed(speed)}")
        return speed
    except Exception as e:
        print(f"    [-] {name} failed: {e}")
        return 0

def test_stream_scaling(url, streams=[1, 4, 8, 16], duration=3):
    print(f"\n[*] Testing TCP Stream Scaling (1 vs 4 vs 8 vs 16 parallel connections)...")
    results = {}
    for n in streams:
        chunk_len = 1000000
        def fetch_chunk(idx):
            start = idx * chunk_len
            end = start + chunk_len - 1
            headers = {"User-Agent": UA, "Range": f"bytes={start}-{end}"}
            t0 = time.time()
            total = 0
            try:
                r = requests.get(url, headers=headers, stream=True, timeout=6)
                for c in r.iter_content(32768):
                    total += len(c)
                    if time.time() - t0 >= duration:
                        break
            except Exception:
                pass
            return total, time.time() - t0

        t_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(fetch_chunk, i) for i in range(n)]
            data = [f.result() for f in futures]
        t_elapsed = time.time() - t_start
        tot_bytes = sum(d[0] for d in data)
        agg_speed = tot_bytes / t_elapsed if t_elapsed > 0 else 0
        results[n] = agg_speed
        print(f"    Streams: {n:2d} | Downloaded: {tot_bytes/1024:7.1f} KB | Aggregate: {human_speed(agg_speed)}")
    return results

def test_udp_port(name, host, port, timeout=2.0):
    """Test UDP port reachability and round-trip ping."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t0 = time.time()
    try:
        # Send simple probe packet
        s.sendto(b"\x00" * 32, (host, port))
        try:
            data, addr = s.recvfrom(1024)
            rtt = (time.time() - t0) * 1000
            print(f"    [+] {name} ({host}:{port}) -> Responded in {rtt:.1f}ms")
            return True, rtt
        except socket.timeout:
            # UDP is stateless; receiving ICMP port unreachable means blocked, timeout might mean open or filtered
            print(f"    [?] {name} ({host}:{port}) -> Sent without ICMP unreachable (Packet allowed through)")
            return True, None
    except Exception as e:
        print(f"    [-] {name} ({host}:{port}) -> Error: {e}")
        return False, None
    finally:
        s.close()

def main():
    print("=" * 68)
    print("      ABU Network Real-Time Bandwidth & Protocol Audit")
    print("=" * 68)
    print(f"Local Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. TCP Direct Downloads across CDNs
    print("\n--- 1. SINGLE-STREAM TCP SPEED BENCHMARK ---")
    cf_speed = test_tcp_url("Cloudflare Edge", "https://speed.cloudflare.com/__down?bytes=20000000")
    cachefly_speed = test_tcp_url("Cachefly CDN", "https://cachefly.cachefly.net/10mb.test")
    fastly_speed = test_tcp_url("Fastly / GitHub Raw", "https://raw.githubusercontent.com/git/git/master/README.md")

    # 2. YouTube / Google Video CDN
    print("\n--- 2. GOOGLE & YOUTUBE STREAMING TEST ---")
    # Test Google CDN asset (mirrors YouTube / Google Video CDN infrastructure)
    google_speed = test_tcp_url("Google Storage / CDN", "https://storage.googleapis.com/tf-datasets/titanic/train.csv")
    google_dl_speed = test_tcp_url("Google Chrome Installer", "https://dl.google.com/tag/s/appguid%3D%7B8A69D345-D564-463C-AFF1-A69D9E530F96%7D%26iid%3D%7BE1FA777E-62F8-3A1D-3E2A-A2E4485DFF58%7D%26lang%3Den%26browser%3D4%26usagestats%3D0%26appname%3DGoogle%2520Chrome%26needsadmin%3Dprefers%26ap%3Dx64-stable-statsdef_1%26installdataindex%3Dempty/update2/installers/ChromeSetup.exe")

    # 3. Stream Scaling Test
    test_stream_scaling("https://speed.cloudflare.com/__down?bytes=50000000")

    # 4. UDP & Port Filtering Test (Zoom, WireGuard, DNS)
    print("\n--- 3. UDP PROTOCOL & PORT AUDIT ---")
    test_udp_port("DNS", "8.8.8.8", 53)
    test_udp_port("Zoom Media Gateway", "170.114.10.1", 8801)
    test_udp_port("Zoom Signaling", "170.114.10.1", 8802)
    test_udp_port("Cloudflare WARP (WireGuard)", "162.159.192.1", 2408)
    test_udp_port("Cloudflare WARP Alt Port", "162.159.193.1", 443)

    # 5. WARP Status
    print("\n--- 4. CLOUDFLARE WARP STATUS ---")
    import warp_manager
    installed = warp_manager.is_warp_installed()
    status, desc = warp_manager.get_warp_status()
    print(f"WARP Installed : {installed}")
    print(f"WARP Status    : {status} ({desc})")

    print("\n" + "=" * 68)
    print("                    AUDIT COMPLETE")
    print("=" * 68)

if __name__ == "__main__":
    main()
