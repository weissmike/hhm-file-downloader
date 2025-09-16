"""
create_drives.py (interactive version)

Prompts user to paste a tab-delimited list of showings (Day, Time, Block/Film Name).
For any "Shorts" block, prompts for playback order (one film per line).
Organizes output as:
    Day\\Time - Film Name\\movie file.ext
    Day\\Time - Block Name\\1_movie file.ext
"""

import argparse
import os
import sys
import json
import shutil
from pathlib import Path
from utils import log_info, log_error, log_debug, set_log_level

# Import the asset auditor's programmatic API
from asset_auditor import audit_assets

def load_config():
    CONFIG_FILE = '.film_downloader_config.json'
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

from utils import fuzzy_match_title
def find_asset(film_name, assets_root, all_titles=None, threshold=0.8):
    import unicodedata
    video_exts = {'.mp4', '.mov', '.mkv', '.avi', '.wmv', '.m4v', '.mpg', '.mpeg', '.webm'}
    def normalize(s):
        return unicodedata.normalize('NFKC', s).strip().casefold()
    # Try robust exact match first
    for sub in ['Features', 'Shorts']:
        folder = Path(assets_root) / sub
        if not folder.exists():
            continue
        for d in folder.iterdir():
            if d.is_dir():
                log_debug(f"Checking folder: {d.name}")
                if normalize(d.name) == normalize(film_name):
                    # Look for a main film file in this folder or its Film subfolder
                    candidates = []
                    for search_dir in [d, d / 'Film']:
                        if search_dir.exists():
                            for f in search_dir.iterdir():
                                if f.is_file() and not f.name.endswith('.stub') and f.suffix.lower() in video_exts:
                                    candidates.append(f)
                    if candidates:
                        return candidates[0]  # Return the first found
    # Fuzzy match if not found
    if all_titles:
        best_match, score = fuzzy_match_title(film_name, all_titles, threshold=threshold)
        if best_match:
            for sub in ['Features', 'Shorts']:
                folder = Path(assets_root) / sub
                if not folder.exists():
                    continue
                for d in folder.iterdir():
                    if d.is_dir() and normalize(d.name) == normalize(best_match):
                        candidates = []
                        for search_dir in [d, d / 'Film']:
                            if search_dir.exists():
                                for f in search_dir.iterdir():
                                    if f.is_file() and not f.name.endswith('.stub') and f.suffix.lower() in video_exts:
                                        candidates.append(f)
                        if candidates:
                            log_info(f"[FUZZY MATCH] '{film_name}' matched to '{best_match}' (score {int(score*100)}%)")
                            return candidates[0]
    return None

def copy_asset(src, dest, dry_run=False):
    if dry_run:
        log_info(f"[DRY RUN] Would copy: {src} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return  # Don't overwrite
    try:
        file_size = os.path.getsize(src)
        threshold = 100 * 1024 * 1024  # 100MB
        if file_size > threshold:
            try:
                from tqdm import tqdm
            except ImportError:
                log_info("tqdm not installed, copying without progress bar.")
                shutil.copy2(src, dest)
                return
            chunk_size = 4 * 1024 * 1024  # 4MB
            with open(src, 'rb') as fsrc, open(dest, 'wb') as fdst, tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Copying {os.path.basename(src)}") as pbar:
                while True:
                    buf = fsrc.read(chunk_size)
                    if not buf:
                        break
                    fdst.write(buf)
                    pbar.update(len(buf))
            shutil.copystat(src, dest)
        else:
            shutil.copy2(src, dest)
    except Exception as e:
        log_error(f"Error copying file {src} to {dest}: {e}")

def main():


    parser = argparse.ArgumentParser(description="Interactive: Organize assets for showings/blocks pasted by user.")
    parser.add_argument('--assets-root', default=None, help='Root directory containing Features/Shorts (default: from config)')
    parser.add_argument('--output-root', required=True, help='Root directory for output drives/folders')
    parser.add_argument('--log-level', default='info', choices=['debug', 'info', 'none'], help='Set log level')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be created/copied, but do not actually copy')
    parser.add_argument('--shorts-csv', default=None, help='Path to Shorts CSV file to use for drive audit report (film list)')
    args = parser.parse_args()

    set_log_level(args.log_level)
    config = load_config()
    assets_root = args.assets_root or config.get('root_dir', '.')
    log_info(f"Using assets root: {assets_root}")
    log_info(f"Output root: {args.output_root}")
    if args.dry_run:
        log_info("Running in DRY RUN mode. No files or folders will be created.")


    # Helper to copy missing files/folders
    def copy_with_progress(src, dst):
        """Copy a file with a progress bar if tqdm is available."""
        try:
            from tqdm import tqdm
            total = os.path.getsize(src)
            chunk_size = 4 * 1024 * 1024
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst, tqdm(total=total, unit='B', unit_scale=True, desc=f"Copying {os.path.basename(src)}") as pbar:
                while True:
                    buf = fsrc.read(chunk_size)
                    if not buf:
                        break
                    fdst.write(buf)
                    pbar.update(len(buf))
            shutil.copystat(src, dst)
        except ImportError:
            shutil.copy2(src, dst)

    def copy_missing(src, dst):
        """Recursively copy all files/folders from src to dst, skipping files that already exist."""
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            s = src / item.name
            d = dst / item.name
            if s.is_dir():
                log_info(f"Copying folder: {s} -> {d}")
                copy_missing(s, d)
            else:
                if not d.exists():
                    log_info(f"Copying file: {s} -> {d}")
                    copy_with_progress(s, d)

    # Helper to parse shorts CSV for film list
    def parse_shorts_csv(csv_path):
        import csv
        films = set()
        if not csv_path or not os.path.exists(csv_path):
            return []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            field = next((h for h in reader.fieldnames if 'film' in h.lower() or 'title' in h.lower()), None)
            if not field:
                return []
            for row in reader:
                val = row[field].strip()
                if val:
                    films.add(val)
        return sorted(films)

    # 1. Create the output folder if not exist
    Path(args.output_root).mkdir(parents=True, exist_ok=True)

    # 2. Copy Sponsors and _Trailers to that folder
    sponsors_src = Path(assets_root) / 'Sponsors'
    sponsors_dst = Path(args.output_root) / 'Sponsors'
    if sponsors_src.exists() and sponsors_src.is_dir():
        log_info(f"Ensuring all Sponsors assets exist in {sponsors_dst}")
        copy_missing(sponsors_src, sponsors_dst)
    else:
        log_info("No Sponsors folder found to copy.")

    trailers_src = Path(assets_root) / '_Trailers'
    trailers_dst = Path(args.output_root) / '_Trailers'
    if trailers_src.exists() and trailers_src.is_dir():
        log_info(f"Ensuring all _Trailers assets exist in {trailers_dst}")
        copy_missing(trailers_src, trailers_dst)
    else:
        log_info("No _Trailers folder found to copy.")

    # 3. Prompt for showings and build file structure
    print("Paste your showings (tab-delimited: Day<TAB>Time<TAB>Block/Film Name), one per line. End with an empty line:")
    showings = []
    while True:
        line = input()
        if not line.strip():
            break
        parts = line.split('\t')
        if len(parts) < 3:
            print("Invalid line, must have Day, Time, Block/Film Name (tab-delimited). Skipping.")
            continue
        day, time, title = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not title:
            continue
        showings.append((day, time, title))

    # 4. If shorts blocks found, prompt for Shorts CSV and parse it
    shorts_blocks = [title for _, _, title in showings if 'shorts' in title.lower()]
    shorts_csv_list = []
    shorts_csv_path = None
    if shorts_blocks:
        from utils import choose_csv_file
        shorts_csv_path = args.shorts_csv or choose_csv_file(prompt="Select the Shorts CSV file for the drive audit report:")
        if shorts_csv_path:
            shorts_csv_list = parse_shorts_csv(shorts_csv_path)

    # 5. Build the full film list
    film_names = set(title for _, _, title in showings if title)
    film_names.update(shorts_csv_list)

    # 6. Create file structure and copy screener assets
    shorts_dir = Path(assets_root) / 'Shorts'
    features_dir = Path(assets_root) / 'Features'
    for day, time, name in showings:
        def sanitize(s):
            return ''.join(c if c not in '<>:"/\\|?*' else '-' for c in s)
        safe_time = sanitize(time)
        safe_name = sanitize(name)
        show_folder = f"{day}\\{safe_time} - {safe_name}"
        show_dir = Path(args.output_root) / show_folder
        show_dir.mkdir(parents=True, exist_ok=True)
        if 'shorts' in name.lower():
            block_folder = shorts_dir / name
            if block_folder.exists() and block_folder.is_dir():
                for numbered_short in sorted(block_folder.iterdir()):
                    if numbered_short.is_dir():
                        film_dir = numbered_short / 'Film'
                        if film_dir.exists() and film_dir.is_dir():
                            film_files = [f for f in film_dir.iterdir() if f.is_file() and f.suffix.lower() in {'.mp4', '.mov', '.mkv', '.avi', '.wmv', '.m4v', '.mpg', '.mpeg', '.webm'}]
                            for film_file in film_files:
                                dest = show_dir / f"{numbered_short.name}_{film_file.name}"
                                if dest.exists():
                                    src_size = film_file.stat().st_size
                                    dest_size = dest.stat().st_size
                                    if src_size > dest_size:
                                        log_info(f"OVERWRITE (src larger): {film_file} ({src_size}) -> {dest} ({dest_size})")
                                        copy_with_progress(film_file, dest)
                                    else:
                                        log_info(f"SKIP (already exists, same or larger): {film_file} ({src_size}) -> {dest} ({dest_size})")
                                else:
                                    log_info(f"Copying short: {film_file} -> {dest}")
                                    copy_with_progress(film_file, dest)
                        else:
                            log_error(f"No Film subfolder in {numbered_short}")
            else:
                log_error(f"Shorts block folder not found: {block_folder}")
        else:
            # Feature or other film
            all_titles = set()
            for sub in ['Features', 'Shorts']:
                folder = Path(assets_root) / sub
                if folder.exists():
                    for d in folder.iterdir():
                        if d.is_dir():
                            all_titles.add(d.name)
            asset = find_asset(name, assets_root, all_titles=all_titles)
            dest = show_dir / (asset.name if asset else f"{name} (NOT FOUND)")
            if asset:
                if dest.exists():
                    src_size = asset.stat().st_size
                    dest_size = dest.stat().st_size
                    if src_size > dest_size:
                        log_info(f"OVERWRITE (src larger): {asset} ({src_size}) -> {dest} ({dest_size})")
                        copy_with_progress(asset, dest)
                    else:
                        log_info(f"SKIP (already exists, same or larger): {asset} ({src_size}) -> {dest} ({dest_size})")
                else:
                    log_info(f"Copying feature: {asset} -> {dest}")
                    copy_with_progress(asset, dest)
            else:
                log_error(f"[FEATURE NOT FOUND] '{name}' not matched.")

    # 7. Fuzzy match film_names to actual asset names in Features/Shorts
    from utils import fuzzy_match_title
    all_titles = set()
    for sub in ['Features', 'Shorts']:
        folder = Path(assets_root) / sub
        if folder.exists():
            for d in folder.iterdir():
                if d.is_dir():
                    all_titles.add(d.name)
    matched_titles = set()
    for title in film_names:
        best_match, score = fuzzy_match_title(title, list(all_titles), threshold=0.7)
        if best_match:
            matched_titles.add(best_match)
    final_film_list = sorted(matched_titles)

    # 8. Call asset auditor, passing the list of films we are interested in
    try:
        audit_path = Path(args.output_root) / 'asset_audit_report.md'
        if final_film_list:
            log_info(f"Generating audit report at {audit_path} for films: {final_film_list}, scanning assets root: {assets_root}")
        else:
            log_info(f"Generating audit report at {audit_path} (no film list provided), scanning assets root: {assets_root}")
        audit_assets(assets_root, str(audit_path), film_titles=final_film_list, log_level=args.log_level)
    except Exception as e:
        log_error(f"Failed to generate audit report: {e}")

    # --- Print dry-run tree summary at the very end ---
    if args.dry_run:
        from collections import defaultdict
        def build_tree(paths, root):
            tree = defaultdict(list)
            for p in paths:
                try:
                    rel = p.relative_to(root)
                except Exception:
                    continue
                parts = rel.parts
                if not parts:
                    continue
                for i in range(1, len(parts)+1):
                    parent = parts[:i-1]
                    child = parts[i-1]
                    if child not in tree[parent]:
                        tree[parent].append(child)
            return tree
        def print_tree(tree, path_tuple=(), prefix="", is_last=True):
            children = sorted(tree.get(path_tuple, []))
            for idx, name in enumerate(children):
                is_last_child = idx == len(children) - 1
                branch = "└── " if is_last_child else "├── "
                print(prefix + branch + name)
                new_tuple = path_tuple + (name,)
                extension = "    " if is_last_child else "│   "
                print_tree(tree, new_tuple, prefix + extension, is_last_child)
        print(f"\n[DRY RUN] Folder/file tree for {args.output_root}:")
        if not dry_run_paths:
            print("(No folders or files would be created/copied.)")
        else:
            tree_dict = build_tree(dry_run_paths, Path(args.output_root))
            print_tree(tree_dict)

if __name__ == "__main__":
    main()
