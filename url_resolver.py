"""
Smart URL & Stream Resolver for Ushcodex Download Manager
==========================================================
Automatically resolves sharing URLs (Mediafire, Google Drive, direct links)
into raw, direct high-speed download streams.
"""

import os
import re
from urllib.parse import urlparse, unquote, parse_qs
import requests
import bs4

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

def sanitize_filename(filename):
    if not filename:
        return "download_file.bin"
    # Remove illegal Windows characters: < > : " / \ | ? *
    clean = re.sub(r'[<>:"/\\|?*]', '_', filename)
    clean = clean.strip('. ')
    return clean if clean else "download_file.bin"

def extract_filename_from_headers(headers):
    if not headers:
        return None
    cd = headers.get("Content-Disposition", "")
    if cd:
        # Check filename*=UTF-8''...
        fn_star = re.search(r"filename\*=(?:UTF-8''|utf-8'')([^;]+)", cd, re.IGNORECASE)
        if fn_star:
            return sanitize_filename(unquote(fn_star.group(1).strip('"\' ')))
        
        # Check standard filename="..."
        fn = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
        if fn:
            return sanitize_filename(fn.group(1).strip('"\' '))
    return None

def extract_filename_from_url(url):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    base = os.path.basename(path.rstrip('/'))
    if base and "." in base and not base.lower().endswith(('.php', '.html', '.htm', '.jsp', '.asp', '.file')):
        return sanitize_filename(base)
    return None

def resolve_mediafire(url, session):
    """Resolves MediaFire webpage into direct download CDN URL."""
    resp = session.get(url, timeout=15)
    soup = bs4.BeautifulSoup(resp.text, 'html.parser')
    
    # 1. Look for download button
    btn = soup.find('a', {'id': 'downloadButton'})
    if btn and btn.get('href'):
        direct_url = btn.get('href')
        # Try getting filename from page or link
        fn = extract_filename_from_url(direct_url)
        if not fn:
            fn_div = soup.find('div', {'class': 'filename'})
            if fn_div:
                fn = sanitize_filename(fn_div.text.strip())
        return direct_url, fn
        
    # 2. Look for aria-label or fallback links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if "download" in href and "mediafire.com" in href:
            return href, extract_filename_from_url(href)
            
    return None, None

def resolve_google_drive(url):
    """Resolves Google Drive view/sharing links into direct download links."""
    file_id = None
    # Match /file/d/FILE_ID/view
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        file_id = m.group(1)
    else:
        # Match ?id=FILE_ID
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "id" in qs:
            file_id = qs["id"][0]

    if file_id:
        return f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    return url

def resolve_download_url(raw_url, custom_headers=None):
    """
    Main resolution engine:
    Takes any URL (raw link, landing page, sharing link), inspects headers,
    resolves direct download endpoint, and extracts exact filename & total size.
    Returns: (final_download_url, filename, total_size, accepts_ranges, error_msg)
    """
    headers = {"User-Agent": DEFAULT_UA}
    if custom_headers:
        headers.update(custom_headers)

    session = requests.Session()
    session.headers.update(headers)

    url = raw_url.strip()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Special handler: MediaFire
    if "mediafire.com" in domain and ("/file/" in url or "/download/" in url):
        direct_url, fn = resolve_mediafire(url, session)
        if direct_url:
            url = direct_url
            suggested_filename = fn
        else:
            suggested_filename = None
    # Special handler: Google Drive
    elif "drive.google.com" in domain:
        url = resolve_google_drive(url)
        suggested_filename = None
    else:
        suggested_filename = None

    # Probe target endpoint
    try:
        probe = session.head(url, allow_redirects=True, timeout=15)
        final_url = probe.url
        resp_headers = probe.headers
    except Exception:
        # Some servers block HEAD; try GET with stream=True
        try:
            probe = session.get(url, stream=True, allow_redirects=True, timeout=15)
            final_url = probe.url
            resp_headers = probe.headers
        except Exception as e:
            return None, None, 0, False, f"Could not connect to URL: {e}"

    # Check if target is an unhandled HTML page
    content_type = resp_headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
        # If it returned HTML but wasn't handled, check for inline redirects or meta refresh
        return final_url, "webpage.html", int(resp_headers.get("Content-Length", 0)), False, "Warning: Link returned an HTML webpage rather than a direct downloadable file. Please verify the direct file link."

    # Determine filename
    filename = suggested_filename
    if not filename:
        filename = extract_filename_from_headers(resp_headers)
    if not filename:
        filename = extract_filename_from_url(final_url)
    if not filename:
        filename = extract_filename_from_url(raw_url)
    if not filename:
        # Infer extension from content-type
        ext = ".bin"
        if "iso" in content_type:
            ext = ".iso"
        elif "mp4" in content_type:
            ext = ".mp4"
        elif "zip" in content_type:
            ext = ".zip"
        elif "pdf" in content_type:
            ext = ".pdf"
        filename = f"download_{int(time.time())}{ext}"

    total_size = int(resp_headers.get("Content-Length", 0))
    accepts_ranges = "bytes" in resp_headers.get("Accept-Ranges", "").lower() or total_size > 0

    return final_url, filename, total_size, accepts_ranges, None


if __name__ == "__main__":
    test_link = "https://www.mediafire.com/file/wpq2azdi2d1z3i0/Plants.vs.Zombies.Replanted.v1.5.1469.iso/file"
    print("Testing resolver on:", test_link)
    f_url, fn, sz, rng, err = resolve_download_url(test_link)
    print("Resolved URL :", f_url[:80], "...")
    print("Filename     :", fn)
    print("Size         :", f"{sz / (1024*1024):.2f} MB")
    print("Accepts Range:", rng)
    print("Error        :", err)
