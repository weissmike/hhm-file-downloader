ASSET_TYPE_FOLDERS = {
    'film': 'Film',
    'poster': 'Posters',
    'still': 'Stills',
    'trailer': 'Trailer',
}
#!/usr/bin/env python3

import sys
import os
import re
import csv
import time
import argparse
import subprocess
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import set_log_level, log_debug, log_info, log_error, choose_csv_file

######################################################################
# Dependency Management
######################################################################

REQUIRED_PACKAGES = [
    "tqdm",
    "yt-dlp",   # For Vimeo / YouTube / streaming fallback
    "gdown"     # For reliable Google Drive handling
]

_installed_checked = False
def ensure_dependencies():
    global _installed_checked
    if _installed_checked:
        return
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[INFO] Installing missing packages: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *missing])
    _installed_checked = True

ensure_dependencies()

from tqdm import tqdm
import requests

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import gdown
except ImportError:
    gdown = None

try:
    import readline
except ImportError:
    readline = None

######################################################################
# CLI Argument Parsing
######################################################################


CONFIG_FILE = ".film_downloader_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def parse_args():
    parser = argparse.ArgumentParser(description="Festival Film / Trailer Bulk Downloader")
    parser.add_argument("--csv", help="Path to the CSV file")
    parser.add_argument("--out", default=None, help="Root output directory (persists for future runs)")
    parser.add_argument("--include-stills", action="store_true", help="Include still image URLs")
    parser.add_argument("--include-poster", action="store_true", help="Include poster URLs")
    parser.add_argument("--include-all-http", action="store_true", help="Include ALL http(s) URLs (broad)")
    parser.add_argument("--films-only", action="store_true", help="Only download film assets (skip trailers)")
    parser.add_argument("--max-workers", type=int, default=4, help="Max concurrent downloads")
    parser.add_argument("--retry", type=int, default=1, help="Retry count for direct downloads")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not download")
    parser.add_argument("--browser", default=None, help="Browser for cookies-from-browser (chrome, firefox, edge, safari)")
    parser.add_argument("--browser-profile", default=None, help="Browser profile name for cookies-from-browser (optional)")
    parser.add_argument("--cookies", default=None, help="Path to cookies.txt file for yt-dlp (Vimeo login)")
    parser.add_argument("--log-level", default="debug", choices=["debug", "info", "none"], help="Set log level: debug, info, or none (default: debug)")
    return parser.parse_args()

ARGS = parse_args()


# Load and update config for persistent download directory
_config = load_config()
if ARGS.out:
    _config["download_dir"] = ARGS.out
    save_config(_config)
if not ARGS.out:
    ARGS.out = _config.get("download_dir", "downloads")

# --- Google Sheets support ---
import io
import urllib.parse
import requests

def is_google_sheet_link(link):
    if not link:
        return False
    return "docs.google.com/spreadsheets" in link or (len(link) == 44 and link.isalnum())

def get_sheet_id_from_link(link):
    if "/d/" in link:
        return link.split("/d/")[1].split("/")[0]
    return link

def fetch_google_sheet_csv(sheet_link_or_id):
    sheet_id = get_sheet_id_from_link(sheet_link_or_id)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    resp = requests.get(export_url)
    resp.raise_for_status()
    return io.StringIO(resp.text)

COLOR = not ARGS.no_color and sys.stdout.isatty()

def c(text, code):
    if not COLOR: return text
    return f"\033[{code}m{text}\033[0m"

def green(s): return c(s, "32")
def yellow(s): return c(s, "33")
def red(s): return c(s, "31")
def blue(s): return c(s, "34")

######################################################################
# CSV Parsing
######################################################################

HTTP_URL_PATTERN = re.compile(r"https?://[^\s]+")

FILM_KEYWORDS = [
    "link and password to download your film",
    "download your film",
    "festivaldelivery",
    "film delivery",
    "film download",
    "link to download your film",
    "link and password"
]
TRAILER_KEYWORDS = ["trailer", "teaser"]
STILLS_KEYWORDS = ["still"]
POSTER_KEYWORDS = ["poster"]

def normalize_header(h):
    return (h or "").strip().lower()

def classify_column(header):
    h = normalize_header(header)
    if any(k in h for k in FILM_KEYWORDS): return "Film"
    if any(k in h for k in TRAILER_KEYWORDS): return "Trailer"
    if any(k in h for k in STILLS_KEYWORDS): return "Stills"
    if any(k in h for k in POSTER_KEYWORDS): return "Posters"
    return "other"

def extract_urls(cell):
    if not cell:
        return []
    urls = []
    for f in HTTP_URL_PATTERN.findall(cell):
        f2 = f.strip().rstrip('),.;]')
        if f2 not in urls:
            urls.append(f2)
    return urls

# Extract URLs and possible passwords from a cell
def extract_urls_and_password(cell):
    if not cell:
        return []
    urls = []
    # Look for password patterns
    pw_match = re.search(r'(?:password|pw|pass)\s*[:=\-]?\s*([\w\d!@#$%^&*()_+\-]+)', cell, re.IGNORECASE)
    password = pw_match.group(1) if pw_match else None
    for f in HTTP_URL_PATTERN.findall(cell):
        f2 = f.strip().rstrip('),.;]')
        if f2 not in urls:
            urls.append(f2)
    # Return list of dicts: [{url, password}]
    return [{"url": u, "password": password} for u in urls]

######################################################################
# URL Normalization & Strategy
######################################################################

def is_google_drive(url): return "drive.google.com" in url or "docs.google.com/uc" in url
def is_dropbox(url): return "dropbox.com" in url
def is_vimeo_or_stream(url): return any(d in url for d in ["vimeo.com", "youtube.com", "youtu.be"])
def looks_like_box(url): return "box.com" in url
def looks_like_wetransfer(url): return "wetransfer.com" in url or "we.tl" in url

def direct_download_transform(url):
    if is_google_drive(url):
        file_id = None
        m = re.search(r"[?&]id=([A-Za-z0-9_\-]+)", url) or re.search(r"/file/d/([A-Za-z0-9_\-]+)/", url)
        if m:
            file_id = m.group(1)
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}", "gdrive"
        return url, "gdrive"
    if is_dropbox(url):
        if "?dl=0" in url: return url.replace("?dl=0", "?dl=1"), "direct"
        if "dl=1" not in url:
            sep = "&" if "?" in url else "?"
            return url + sep + "dl=1", "direct"
        return url, "direct"
    if is_vimeo_or_stream(url): return url, "yt-dlp"
    if looks_like_box(url) or looks_like_wetransfer(url): return url, "direct"
    return url, "direct"

######################################################################
# Filenames / Sanitization
######################################################################

INVALID_FS_CHARS = re.compile(r"[<>:\"/\\|?*\x00-\x1F]")

def safe_filename(name, maxlen=180):
    name = INVALID_FS_CHARS.sub("_", (name or "").strip())
    if len(name) > maxlen:
        base, ext = os.path.splitext(name)
        name = base[: maxlen - len(ext) - 1] + "_" + ext
    return name or "file"

def guess_extension_from_headers(headers, fallback=".bin"):
    cd = headers.get("content-disposition")
    if cd:
        m = re.search(r'filename="([^"]+)"', cd)
        if m:
            return os.path.splitext(m.group(1))[1] or fallback
    ct = headers.get("content-type", "").lower()
    mapping = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-matroska": ".mkv",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "application/pdf": ".pdf",
    }
    for k, v in mapping.items():
        if k in ct:
            return v
    return fallback

######################################################################
# Download Functions
######################################################################

lock_print = threading.Lock()


def download_google_drive(url, out_path):
    if gdown:
        try:
            gdown.download(url=url, output=out_path, quiet=True, fuzzy=True)
            return True, None
        except Exception as e:
            return False, f"gdown error: {e}"
    # Minimal fallback
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            _write_stream(r, out_path)
        return True, None
    except Exception as e:
        return False, str(e)

def _content_total_from_resp(resp, resume_pos):
    # Try to compute total for progress bar
    # For 206, Content-Range: bytes start-end/total
    cr = resp.headers.get("content-range")
    if cr:
        m = re.search(r"/(\d+)$", cr)
        if m:
            return int(m.group(1))
    try:
        cl = int(resp.headers.get("content-length", "0") or 0)
    except Exception:
        cl = 0
    return cl + (resume_pos or 0)

def download_direct(url, out_path, retries=1):
    # Duplicate prevention
    if os.path.exists(out_path):
        return True, None, out_path

    tmp = out_path + ".part"
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            headers = {}
            resume_pos = 0
            if os.path.exists(tmp):
                resume_pos = os.path.getsize(tmp)
                headers["Range"] = f"bytes={resume_pos}-"

            with requests.get(url, stream=True, timeout=60, headers=headers, allow_redirects=True) as r:
                if r.status_code not in (200, 206):
                    last_err = f"HTTP {r.status_code}"
                    continue

                # refine extension if placeholder
                if os.path.splitext(out_path)[1] == ".bin":
                    ext = guess_extension_from_headers(r.headers)
                    if ext and not out_path.endswith(ext):
                        # adjust tmp name as well
                        new_out = out_path + ext
                        new_tmp = new_out + ".part"
                        # rename existing tmp if present
                        if os.path.exists(tmp):
                            os.replace(tmp, new_tmp)
                        out_path, tmp = new_out, new_tmp

                _write_stream_with_resume(r, tmp, resume_pos)
                os.replace(tmp, out_path)
                return True, None, out_path
        except Exception as e:
            last_err = str(e)
            time.sleep(1.5)
    return False, last_err, out_path

def download_with_ytdlp(url, out_dir, base_name, browser=None, browser_profile=None, cookies=None, video_password=None, tqdm_position=None):
    if not yt_dlp:
        return False, "yt-dlp not installed"
    ydl_opts = {
        "outtmpl": os.path.join(out_dir, base_name + ".%(ext)s"),
        "quiet": True,  # Suppress yt-dlp's own progress output
        "no_warnings": True,
        "ignoreerrors": True,
        "retries": 2,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    }
    if browser:
        # Use tuple form to avoid arg parsing errors in yt-dlp
        if browser_profile:
            ydl_opts["cookiesfrombrowser"] = (browser, browser_profile)
        else:
            ydl_opts["cookiesfrombrowser"] = (browser,)
    if cookies:
        ydl_opts["cookiefile"] = cookies
    if video_password:
        ydl_opts["video_password"] = video_password

    # Show a tqdm bar for yt-dlp (simulate progress, since yt-dlp's is suppressed)
    desc = f"yt-dlp: {base_name[:40]}"
    pbar = tqdm(total=1, desc=desc, position=tqdm_position, leave=True, bar_format='{desc} | {bar} {n_fmt}/{total_fmt}')
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            r = ydl.download([url])
        pbar.update(1)
        pbar.close()
        if r == 0:
            # locate output
            for f in os.listdir(out_dir):
                if f.startswith(base_name + "."):
                    return True, None
            return False, "Downloaded but file not found"
        else:
            return False, f"yt-dlp returned code {r}"
    except Exception as e:
        pbar.close()
        return False, str(e)

def _write_stream_with_resume(resp, tmp_path, resume_pos):
    total = _content_total_from_resp(resp, resume_pos)
    chunk = 1024 * 64
    mode = "ab" if resume_pos > 0 else "wb"
    initial = resume_pos if total > 0 else 0
    with open(tmp_path, mode) as f, tqdm(
        total=total if total > 0 else None,
        unit="B",
        unit_scale=True,
        desc=os.path.basename(tmp_path).replace(".part", "")[:50],
        leave=False,
        initial=initial
    ) as pbar:
        for data in resp.iter_content(chunk_size=chunk):
            if not data:
                continue
            f.write(data)
            if total > 0:
                pbar.update(len(data))

def _write_stream(resp, path):
    # non-resume helper (used by gdrive fallback)
    tmp = path + ".part"
    total = int(resp.headers.get("content-length", "0") or 0)
    chunk = 1024 * 64
    with open(tmp, "wb") as f, tqdm(
        total=total if total > 0 else None,
        unit="B",
        unit_scale=True,
        desc=os.path.basename(path)[:50],
        leave=False
    ) as pbar:
        for data in resp.iter_content(chunk_size=chunk):
            if data:
                f.write(data)
                if total > 0:
                    pbar.update(len(data))
    os.replace(tmp, path)

######################################################################
# Task Orchestration
######################################################################

def determine_asset_type(col_class, header_text, url):
    if col_class in ("Film", "Trailer", "Stills", "Posters"):
        return col_class
    h = normalize_header(header_text)
    if any(k in h for k in FILM_KEYWORDS): return "film"
    if any(k in h for k in TRAILER_KEYWORDS): return "trailer"
    if any(k in h for k in STILLS_KEYWORDS): return "stills"
    if any(k in h for k in POSTER_KEYWORDS): return "poster"
    if "trailer" in (url or "").lower() or "teaser" in (url or "").lower():
        return "trailer"
    return "other"

def should_include(asset_type):
    if asset_type == "Film": return True
    if asset_type == "Trailer" and not ARGS.films_only: return True
    if asset_type == "Stills" and ARGS.include_stills: return True
    if asset_type == "Posters" and ARGS.include_poster: return True
    if ARGS.include_all_http: return True
    return False

def load_csv_rows(path):
    rows = []
    # Accept either a file path or a Google Sheet link/ID
    if is_google_sheet_link(path):
        f = fetch_google_sheet_csv(path)
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    else:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows

def gather_download_jobs(csv_path):
    rows = load_csv_rows(csv_path)
    jobs = []
    for idx, row in enumerate(rows):
        film_name = row.get("Film Name") or row.get("Film") or f"Row{idx+1}"
        film_name = film_name.strip() if film_name else f"Row{idx+1}"
        for header, value in row.items():
            if not value:
                continue
            url_pw_list = extract_urls_and_password(value)
            if not url_pw_list:
                continue
            col_class = classify_column(header)
            for up in url_pw_list:
                url = up["url"]
                password = up["password"]
                asset_type = determine_asset_type(col_class, header, url)
                if should_include(asset_type):
                    jobs.append({
                        "row_index": idx + 1,
                        "film_name": film_name,
                        "header": header,
                        "url": url,
                        "asset_type": asset_type,
                        "video_password": password
                    })
    return rows, jobs

######################################################################
# Execution
######################################################################

def main():

    csv_path = ARGS.csv or choose_csv_file(prompt="Enter path to CSV file:", file_ext=".csv")
    if not csv_path or not os.path.isfile(csv_path):
        print(red(f"ERROR: CSV file not found: {csv_path}"))
        sys.exit(1)

    os.makedirs(ARGS.out, exist_ok=True)

    log_info("[STEP] Parsing CSV...")
    rows, jobs = gather_download_jobs(csv_path)
    log_info(f"  Found {len(rows)} data rows.")
    log_info(f"  Extracted {len(jobs)} candidate download URLs after filtering.\n")

    if ARGS.dry_run:
        log_info("[DRY RUN] Listing parsed jobs:")
        for j in jobs[:50]:
            log_info(f" - Row {j['row_index']} [{j['asset_type']}] {j['film_name']}: {j['url']}")
        if len(jobs) > 50:
            log_info(f"... ({len(jobs) - 50} more)")
        log_info("\n(No downloads performed in dry-run mode.)")
        return

    log_info("[STEP] Starting downloads...")
    report_rows = []
    counter = 0


    def worker(job, tqdm_position):
        nonlocal counter
        film_dir_name = safe_filename(job["film_name"]) or f"Film_{job['row_index']}"
        # Always use canonical asset folder; fallback to 'Film' if unknown
        canonical_folder = ASSET_TYPE_FOLDERS.get(job["asset_type"].lower(), 'Film')
        dest_dir = os.path.join(ARGS.out, film_dir_name, canonical_folder)
        os.makedirs(dest_dir, exist_ok=True)

        raw_url = job["url"].strip()
        transformed_url, strategy = direct_download_transform(raw_url)

        base_file_name = safe_filename(f"{job['film_name']}_{job['asset_type']}")
        counter += 1

        # Try to guess extension up-front
        ext = ".bin"
        try:
            head_resp = requests.head(raw_url, allow_redirects=True, timeout=10)
            if head_resp.status_code == 200:
                ext = guess_extension_from_headers(head_resp.headers, fallback=ext)
        except Exception:
            pass

        out_path = os.path.join(dest_dir, base_file_name + ext)
        log_debug(f"base_file_name: '{base_file_name}', ext: '{ext}', out_path: '{out_path}'")


        # Check if file already exists, is complete, or a stub exists BEFORE any download attempt
        skip = False
        local_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        remote_size = None
        log_debug(f"Checking for completed file: '{out_path}'")
        found_completed = False
        completed_path = None
        completed_size = 0
        found_part = False
        part_path = None
        # Robust base name matching for all strategies before any download attempt
        base_dir = os.path.dirname(out_path)
        dir_files = os.listdir(base_dir)
        log_debug(f"Files in directory '{base_dir}': {dir_files}")
        def strip_all_ext(name):
            while True:
                root, ext = os.path.splitext(name)
                if ext:
                    name = root
                else:
                    break
            return name

        base_stripped = strip_all_ext(base_file_name)
        # Normalize all filenames for matching (case-insensitive, extension-insensitive)
        def normalize_for_match(path):
            # Lowercase, remove all extensions
            name = os.path.basename(path).lower()
            while True:
                root, ext = os.path.splitext(name)
                if ext:
                    name = root
                else:
                    break
            return name

        out_norm = normalize_for_match(out_path)
        stub_found = False
        for fname in dir_files:
            candidate_path = os.path.join(base_dir, fname)
            candidate_norm = normalize_for_match(fname)
            if candidate_norm == out_norm and fname.lower().endswith('.stub'):
                log_debug(f"Stub file exists for {out_path} (matched: {fname}), skipping download.")
                stub_found = True
                break
        if stub_found:
            skip = True
        else:
            for fname in dir_files:
                candidate_path = os.path.join(base_dir, fname)
                candidate_norm = normalize_for_match(fname)
                if candidate_norm == out_norm:
                    if fname.endswith('.part'):
                        found_part = True
                        part_path = candidate_path
                        log_debug(f"Found .part file: '{candidate_path}' (will resume)")
                    else:
                        candidate_size = os.path.getsize(candidate_path)
                        log_debug(f"Found candidate: '{candidate_path}' ({candidate_size} bytes)")
                        # Consider 'large' as >10MB (10*1024*1024)
                        if candidate_size > 10*1024*1024:
                            found_completed = True
                            completed_path = candidate_path
                            completed_size = candidate_size
            if found_part:
                log_debug(f"Resume enabled: .part file exists at '{part_path}'")
                skip = False
            elif found_completed:
                log_debug(f"Found completed file: '{completed_path}' ({completed_size} bytes)")
                skip = True
            # For direct, if not found, check remote size if file exists at out_path
            if not skip:
                if os.path.exists(out_path) and local_size > 0:
                    log_debug(f"Found file: '{out_path}' ({local_size} bytes)")
                    if strategy == "direct":
                        try:
                            head = requests.head(raw_url, allow_redirects=True, timeout=10)
                            if head.status_code == 200:
                                remote_size = int(head.headers.get("content-length", "0") or 0)
                        except Exception:
                            pass
                        if remote_size and local_size == remote_size:
                            skip = True
                else:
                    log_debug(f"Not found: '{out_path}'")

        final_path = completed_path if found_completed else out_path
        if skip:
            status = "SKIPPED"
            detail = f"File already exists or stub present. Local size: {completed_size if found_completed else local_size} bytes. Remote size: {remote_size if remote_size is not None else 'unknown'} bytes."
            # Only print skip line if log-level is debug
            if globals().get('LOG_LEVEL', 'debug') == "debug":
                log_info(f"[SKIP] {job['asset_type']} | {job['film_name']} -> {os.path.basename(final_path)} | Local: {completed_size if found_completed else local_size} | Remote: {remote_size if remote_size is not None else 'unknown'} | Stub found: {stub_found}")
            report_rows.append({
                "row_index": job["row_index"],
                "film_name": job["film_name"],
                "asset_type": job["asset_type"],
                "header": job["header"],
                "original_url": raw_url,
                "transformed_url": transformed_url,
                "strategy": strategy,
                "status": status,
                "detail": detail,
                "saved_path": final_path
            })
            return

        status = "FAILED"
        detail = ""
        final_path = ""

        try:
            if strategy == "gdrive":
                ok, err = download_google_drive(transformed_url, out_path)
                if ok:
                    status = "OK"
                    final_path = out_path
                else:
                    detail = err or "unknown gdrive error"

            elif strategy == "yt-dlp":
                log_level = globals().get('LOG_LEVEL', 'debug')
                if log_level == "none":
                    ok, err = download_with_ytdlp(
                        transformed_url,
                        dest_dir,
                        base_file_name,
                        browser=ARGS.browser,
                        browser_profile=ARGS.browser_profile,
                        cookies=ARGS.cookies,
                        video_password=job.get("video_password"),
                        tqdm_position=None
                    )
                else:
                    ok, err = download_with_ytdlp(
                        transformed_url,
                        dest_dir,
                        base_file_name,
                        browser=ARGS.browser,
                        browser_profile=ARGS.browser_profile,
                        cookies=ARGS.cookies,
                        video_password=job.get("video_password"),
                        tqdm_position=tqdm_position
                    )
                if ok:
                    status = "OK"
                    for f in os.listdir(dest_dir):
                        if f.startswith(base_file_name + "."):
                            final_path = os.path.join(dest_dir, f)
                            break
                else:
                    detail = err or "yt-dlp error"

            else:
                log_level = globals().get('LOG_LEVEL', 'debug')
                if log_level == "none":
                    ok, err, maybe_path = download_direct(transformed_url, out_path, retries=ARGS.retry)
                else:
                    with tqdm(total=1, desc=f"direct: {base_file_name[:40]}", position=tqdm_position, leave=True, bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
                        ok, err, maybe_path = download_direct(transformed_url, out_path, retries=ARGS.retry)
                        pbar.update(1)
                if ok:
                    status = "OK"
                    final_path = maybe_path
                else:
                    detail = err or "direct download error"

        except Exception as e:
            detail = str(e)
        if status == "OK":
            log_info(f"[OK] {job['asset_type']} | {job['film_name']} -> {os.path.basename(final_path)}")
        else:
            log_error(f"[FAIL] {job['asset_type']} | {job['film_name']} | {raw_url} | {detail}")
            # Always print errors to console regardless of log level
            print(f"[FAIL] {job['asset_type']} | {job['film_name']} | {raw_url} | {detail}")

        report_rows.append({
            "row_index": job["row_index"],
            "film_name": job["film_name"],
            "asset_type": job["asset_type"],
            "header": job["header"],
            "original_url": raw_url,
            "transformed_url": transformed_url,
            "strategy": strategy,
            "status": status,
            "detail": detail,
            "saved_path": final_path
        })


    with ThreadPoolExecutor(max_workers=ARGS.max_workers) as ex:
        # Assign a tqdm position to each job (up to max_workers)
        futures = []
        for i, job in enumerate(jobs):
            pos = i % ARGS.max_workers
            futures.append(ex.submit(worker, job, pos))
        for _ in tqdm(as_completed(futures), total=len(futures), desc="All Downloads", unit="file"):
            pass

    report_path = os.path.join(ARGS.out, "download_report.csv")

    fieldnames = [
        "row_index", "film_name", "asset_type", "header", "original_url",
        "transformed_url", "strategy", "status", "detail", "saved_path"
    ]


# Entry point for script execution
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Festival Film / Trailer Bulk Downloader")
    parser.add_argument("--csv", help="Path to the CSV file")
    parser.add_argument("--out", default=None, help="Root output directory (persists for future runs)")
    parser.add_argument("--include-stills", action="store_true", help="Include still image URLs")
    parser.add_argument("--include-poster", action="store_true", help="Include poster URLs")
    parser.add_argument("--include-all-http", action="store_true", help="Include ALL http(s) URLs (broad)")
    parser.add_argument("--films-only", action="store_true", help="Only download film assets (skip trailers)")
    parser.add_argument("--max-workers", type=int, default=4, help="Max concurrent downloads")
    parser.add_argument("--retry", type=int, default=1, help="Retry count for direct downloads")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not download")
    parser.add_argument("--browser", default=None, help="Browser for cookies-from-browser (chrome, firefox, edge, safari)")
    parser.add_argument("--browser-profile", default=None, help="Browser profile name for cookies-from-browser (optional)")
    parser.add_argument("--cookies", default=None, help="Path to cookies.txt file for yt-dlp (Vimeo login)")
    parser.add_argument("--log-level", default="debug", choices=["debug", "info", "none"], help="Set log level: debug, info, or none (default: debug)")
    parser.add_argument("--log", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--loglevel", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-level", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-format", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-date", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay2", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay3", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay4", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay5", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay6", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay7", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay8", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay9", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-encoding10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-rotate10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-backup10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-maxsize10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-count10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-interval10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-when10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-utc10", default=None, help="(Unused, for compatibility)")
    parser.add_argument("--logfile-delay10", default=None, help="(Unused, for compatibility)")
    args, unknown = parser.parse_known_args()
    set_log_level(args.log_level)
    print(blue("\n[INFO] For Vimeo downloads requiring login, use --cookies <cookies.txt> (see yt-dlp wiki for details)."))
    main()


    pass

