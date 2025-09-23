import re
def sanitize_filename(name):
    # Remove or replace characters not allowed in Windows filenames
    # Replace both colons and dashes with a dash for time consistency
    name = re.sub(r'[:\-]', '-', name)
    return re.sub(r'[<>"/\\|?*]', '_', name)
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
    CONFIG_FILE = 'config.json'
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

    # --- Check if output drive exists ---
    output_root_path = Path(args.output_root)
    drive = output_root_path.drive or str(output_root_path).split(os.sep)[0] + os.sep
    if drive and not os.path.exists(drive):
        print(f"\n[ERROR] Output drive '{drive}' does not exist. Please insert or mount the drive and try again.")
        sys.exit(1)

    # Prompt for CSVs
    from utils import choose_csv_file
    print("Select the Festival Schedule CSV file:")
    schedule_csv = choose_csv_file(prompt="Select the Festival Schedule CSV file:")
    print("Select the Shorts Blocks CSV file:")
    shorts_blocks_csv = choose_csv_file(prompt="Select the Shorts Blocks CSV file:")
    print("Select the Film Submissions CSV file:")
    film_submissions_csv = choose_csv_file(prompt="Select the Film Submissions CSV file:")

    # Parse Festival Schedule CSV (repeating 3-column groups for each venue, venue name can be in any of the three columns)
    import csv
    showings = []
    with open(schedule_csv, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        # Find all venue names and their starting column indices
        venue_groups = []  # List of (venue_name, start_col_idx)
        col = 0
        while col < len(header):
            group = header[col:col+3]
            venue = next((cell.strip() for cell in group if cell and cell.strip()), None)
            if venue:
                venue_groups.append((venue, col))
            col += 3
        if not venue_groups:
            print("No venue columns found in schedule CSV header.")
            return
        print("Available venues:")
        for i, (venue, idx) in enumerate(venue_groups):
            print(f"{i+1}. {venue}")
        print(f"{len(venue_groups)+1}. Backup (recursive copy of root folder)")
        venue_choice = input(f"Select a venue (1-{len(venue_groups)+1}): ").strip()
        try:
            venue_idx = int(venue_choice) - 1
            if venue_idx == len(venue_groups):
                # Backup mode
                log_info("Backup mode selected. Copying entire root folder recursively.")
                shutil.copytree(assets_root, args.output_root, dirs_exist_ok=True)
                return
            selected_venue, start_col = venue_groups[venue_idx]
        except Exception:
            print("Invalid venue selection.")
            return

        # For the selected venue, collect (day, time, block) for all non-empty blocks in that venue's 3-column group
        for row in reader:
            if len(row) <= start_col+2:
                continue
            day = row[start_col].strip()
            time = row[start_col+1].strip()
            block = row[start_col+2].strip()
            if block:
                showings.append((day, time, block))

    # 1. Create the output folder if not exist
    Path(args.output_root).mkdir(parents=True, exist_ok=True)

    # 2. Copy _Sponsors, _Preroll and _Trailers to that folder
    sponsors_src = Path(assets_root) / '_Sponsors'
    sponsors_dst = Path(args.output_root) / 'Sponsors'
    if sponsors_src.exists() and sponsors_src.is_dir():
        log_info(f"Ensuring all _Sponsors assets exist in {sponsors_dst}")
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

    preroll_src = Path(assets_root) / '_Preroll'
    preroll_dst = Path(args.output_root) / '_Preroll'
    if preroll_src.exists() and preroll_src.is_dir():
        log_info(f"Ensuring all _Preroll assets exist in {preroll_dst}")
        copy_missing(preroll_src, preroll_dst)
    else:
        log_info("No _Preroll folder found to copy.")

    # 3. Build file structure from showings
    shorts_dir = Path(assets_root) / 'Shorts'
    features_dir = Path(assets_root) / 'Features'
    film_names = set(block for _, _, block in showings if block)
    # --- Add all shorts in each shorts block to film_names ---
    shorts_dir = Path(assets_root) / 'Shorts'
    for _, _, block in showings:
        if 'shorts' in block.lower():
            block_folder = shorts_dir / block
            if block_folder.exists() and block_folder.is_dir():
                for numbered_short in block_folder.iterdir():
                    if numbered_short.is_dir():
                        # Add the short's folder name (should match film name)
                        film_names.add(numbered_short.name)

    import subprocess
    for day, time, name in showings:
        def sanitize(s):
            return sanitize_filename(s)
        safe_time = sanitize(time)
        safe_name = sanitize(name)
        show_folder = f"{sanitize_filename(day)}\{safe_time} - {safe_name}"
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
                                dest = show_dir / f"{sanitize_filename(numbered_short.name)}_{sanitize_filename(film_file.name)}"
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
            dest = show_dir / (sanitize_filename(asset.name) if asset else f"{sanitize_filename(name)} (NOT FOUND)")
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

        # --- Call create_qcpx.py for this block ---
        try:
            qcpx_args = [
                sys.executable, 'create_qcpx.py',
                '--festival-schedule', schedule_csv,
                '--shorts-blocks', shorts_blocks_csv,
                '--submissions', film_submissions_csv,
                '--block-path', str(show_dir),
                '--block-name', name
            ]
            log_info(f"Generating QCPX for block '{name}' at {show_dir}...")
            subprocess.run(qcpx_args, check=True)
        except Exception as e:
            log_error(f"Failed to generate QCPX for block '{name}': {e}")

    # 4. Fuzzy match film_names to actual asset names in Features/Shorts
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

    # 5. Call asset_auditor.py as a subprocess, passing the film list
    import subprocess
    audit_path = Path(args.output_root) / 'asset_audit_report.md'
    film_list_arg = ','.join(final_film_list)
    cmd = [
        sys.executable, 'asset_auditor.py',
        '--root', str(assets_root),
        '--out', str(audit_path),
        '--film-list', film_list_arg
    ]
    log_info(f"Running asset_auditor.py for films: {final_film_list}")
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        log_error(f"Failed to generate audit report: {e}")

    # --- Print dry-run tree summary at the very end ---
    dry_run_paths = []  # Placeholder for future dry-run path tracking

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

    # (Removed duplicate/old programmatic audit_assets call. Only subprocess call is used.)

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
