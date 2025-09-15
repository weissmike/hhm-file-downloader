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
    args = parser.parse_args()

    set_log_level(args.log_level)
    config = load_config()
    assets_root = args.assets_root or config.get('root_dir', '.')
    log_info(f"Using assets root: {assets_root}")
    log_info(f"Output root: {args.output_root}")
    if args.dry_run:
        log_info("Running in DRY RUN mode. No files or folders will be created.")

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
        showings.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

    if not showings:
        print("No showings entered. Exiting.")
        return

    dry_run_paths = set()
    shorts_dir = Path(assets_root) / 'Shorts'
    for day, time, name in showings:
        def sanitize(s):
            return ''.join(c if c not in '<>:"/\\|?*' else '-' for c in s)
        safe_time = sanitize(time)
        safe_name = sanitize(name)
        show_folder = f"{day}\\{safe_time} - {safe_name}"
        show_dir = Path(args.output_root) / show_folder
        show_dir.mkdir(parents=True, exist_ok=True)
        if 'shorts' in name.lower():
            # Copy only the main film file from each numbered block subfolder
            block_folder = shorts_dir / name
            if block_folder.exists() and block_folder.is_dir():
                for numbered_short in sorted(block_folder.iterdir()):
                    if numbered_short.is_dir():
                        # Look for the main film file in the 'Film' subfolder
                        film_dir = numbered_short / 'Film'
                        if film_dir.exists() and film_dir.is_dir():
                            film_files = [f for f in film_dir.iterdir() if f.is_file() and f.suffix.lower() in {'.mp4', '.mov', '.mkv', '.avi', '.wmv', '.m4v', '.mpg', '.mpeg', '.webm'}]
                            if film_files:
                                film_file = film_files[0]  # Take the first film file found
                                dest = show_dir / f"{numbered_short.name}_{film_file.name}"
                                if args.dry_run:
                                    dry_run_paths.add(dest)
                                else:
                                    shutil.copy2(film_file, dest)
                            else:
                                log_error(f"No film file found in {film_dir}")
                        else:
                            log_error(f"No Film subfolder in {numbered_short}")
            else:
                log_error(f"Shorts block folder not found: {block_folder}")
        else:
            # Feature or other film: copy as before
            all_titles = set()
            for sub in ['Features', 'Shorts']:
                folder = Path(assets_root) / sub
                if folder.exists():
                    for d in folder.iterdir():
                        if d.is_dir():
                            all_titles.add(d.name)
            all_titles = list(all_titles)
            asset = find_asset(name, assets_root, all_titles=all_titles)
            log_debug(f"find_asset('{name}') returned: {asset}")
            dest = show_dir / (asset.name if asset else f"{name} (NOT FOUND)")
            if asset:
                copy_asset(asset, dest, dry_run=args.dry_run)
            else:
                log_error(f"[FEATURE NOT FOUND] '{name}' not matched.")
            if args.dry_run:
                dry_run_paths.add(dest)

    log_info("Drive/folder creation complete.")

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
