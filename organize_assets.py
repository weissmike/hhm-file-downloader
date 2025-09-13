
import os
import shutil
import json
from pathlib import Path
import argparse
import threading

# --- Load config ---
CONFIG_FILE = '.film_downloader_config.json'
DEFAULT_ROOT = Path('D:/HHM')
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}
def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

_config = load_config()
ROOT = Path(_config.get('root_dir', str(DEFAULT_ROOT)))
DOWNLOADS = Path(_config.get('download_dir', str(ROOT / 'downloads')))
UNSORTED = Path(_config.get('unsorted_dir', str(ROOT / 'Unsorted')))
DIR_MATCH_THRESHOLD = float(_config.get('dir_match_threshold', 0.6))
FILE_MATCH_THRESHOLD = float(_config.get('file_match_threshold', 0.8))
_changed = False
if 'download_dir' not in _config:
    _config['download_dir'] = str(DOWNLOADS)
    _changed = True
if 'unsorted_dir' not in _config:
    _config['unsorted_dir'] = str(UNSORTED)
    _changed = True
if 'root_dir' not in _config:
    _config['root_dir'] = str(ROOT)
    _changed = True
if 'dir_match_threshold' not in _config:
    _config['dir_match_threshold'] = DIR_MATCH_THRESHOLD
    _changed = True
if 'file_match_threshold' not in _config:
    _config['file_match_threshold'] = FILE_MATCH_THRESHOLD
    _changed = True
if _changed:
    save_config(_config)

from utils import set_log_level, log_debug, log_info, log_error, choose_csv_file

FEATURES = ROOT / 'Features'
SHORTS = ROOT / 'Shorts'

ASSET_TYPES = ['Film', 'Trailer', 'Stills', 'Posters']
AGGREGATES = {
    'Films': ROOT / '_Films',
    'Trailers': ROOT / '_Trailers',
    'Stills': ROOT / '_Stills',
    'Posters': ROOT / '_Posters',
}

# --- Load film/short titles from CSV ---
import csv

def load_titles_from_csv(csv_path):
    features = []
    shorts = []
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            tags = row.get('tags', '')
            name = row.get('name', '').strip()
            if not name:
                continue
            tags_lower = tags.lower() if tags else ''
            if 'feature' in tags_lower:
                features.append(name)
            elif 'short' in tags_lower:
                shorts.append(name)
    return features, shorts



IMG_EXT = {'.jpg','.jpeg','.png','.tif','.tiff','.webp','.heic','.bmp','.gif'}
VID_EXT = {'.mp4','.mov','.m4v','.mkv','.webm','.avi'}


def sanitize(name):
    # Remove forbidden characters and trim
    reserved = {'CON','PRN','AUX','NUL','COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9','LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9'}
    name = ''.join('_' if c in '<>:"/\\|?*' else c for c in name).strip()
    name = ' '.join(name.split())
    if name.upper() in reserved:
        name = '_' + name
    return name.rstrip('.')

def ensure_film_dirs(title, parent):
    name = sanitize(title)
    film_dir = parent / name
    film_dir.mkdir(parents=True, exist_ok=True)
    for sub in ASSET_TYPES:
        (film_dir / sub).mkdir(exist_ok=True)
    return film_dir

def organize_one(film_dir, copy_only=False, stub_unsorted=False):
    # Move or copy files into subfolders by asset type
    for file in film_dir.iterdir():
        if file.is_file():
            ext = file.suffix.lower()
            moved = False
            if 'trailer' in file.name.lower():
                dest = film_dir / 'Trailer'
                moved = True
            elif 'poster' in file.name.lower():
                dest = film_dir / 'Posters'
                moved = True
            elif ext in IMG_EXT:
                dest = film_dir / 'Stills'
                moved = True
            elif ext in VID_EXT:
                dest = film_dir / 'Film'
                moved = True
            if moved:
                dest_path = dest / file.name
                replaced = dest_path.exists()
                if copy_only:
                    shutil.copy2(str(file), str(dest_path))
                    if replaced:
                        log_info(f"File replaced (copied over): {dest_path}")
                    else:
                        log_debug(f"File copied: {file} -> {dest_path}")
                    if stub_unsorted:
                        # Create a stub file to prevent reprocessing
                        stub = file.with_suffix(file.suffix + '.stub')
                        stub.touch(exist_ok=True)
                else:
                    shutil.move(str(file), str(dest_path))
                    if replaced:
                        log_info(f"File replaced (moved over): {dest_path}")
                    else:
                        log_debug(f"File moved: {file} -> {dest_path}")

def organize_all(parent, copy_only=False, stub_unsorted=False):
    for film_dir in parent.iterdir():
        if film_dir.is_dir():
            organize_one(film_dir, copy_only=copy_only, stub_unsorted=stub_unsorted)



# --- Interactive matching for unmatched files ---
import sys
import difflib
import shutil

def prompt_user_for_match(file, features, shorts, remembered):
    # Show full path, highlighted
    full_path = None
    if hasattr(file, 'parent'):
        full_path = str(file)
    elif isinstance(file, str):
        full_path = file
    else:
        full_path = str(file)
    # Show parent directory for context
    parent_dir = None
    if hasattr(file, 'parent'):
        parent_dir = str(file.parent)
    elif isinstance(file, str):
        parent_dir = os.path.dirname(file)
    else:
        parent_dir = ''
    print(f"\nUnmatched file: [{full_path}]\n  In directory: [{parent_dir}]")
    # Try to guess a match using fuzzy logic on filename and parent directory
    # Use full relative path + filename for matching
    global FILE_MATCH_THRESHOLD
    if isinstance(file, str):
        rel_path = file.replace(str(ROOT), '').replace('\\', '/').replace('\\', '/').lower()
    else:
        rel_path = str(file).lower()
    base = Path(file).stem.lower()
    candidates = features + shorts
    best_match = None
    best_score = 0
    for t in candidates:
        score = difflib.SequenceMatcher(None, rel_path, t.lower()).ratio()
        score = max(score, difflib.SequenceMatcher(None, base, t.lower()).ratio())
        if score > best_score:
            best_score = score
            best_match = t
    # Build options list
    all_titles = features + shorts
    # Calculate fuzzy scores for all titles
    scores = []
    for t in all_titles:
        score = difflib.SequenceMatcher(None, rel_path, t.lower()).ratio()
        score = max(score, difflib.SequenceMatcher(None, base, t.lower()).ratio())
        scores.append(score)
        zipped = list(zip(scores, all_titles))
        top5 = sorted(zipped, key=lambda x: (-x[0], x[1].lower()))[:5]
        rest = sorted(zipped, key=lambda x: x[1].lower())[5:]
        combined = top5 + rest
        all_titles_sorted = [t for _, t in combined]
        sorted_scores = [s for s, _ in combined]
    def asset_type(t):
        if t in features:
            return "Feature"
        elif t in shorts:
            return "Short"
        return ""
    options = [f"{t} ({asset_type(t)}) [{int(s*100)}%]" for t, s in zip(all_titles_sorted, sorted_scores)] + ["Skip"]
    # Auto-match if best score >= threshold
    best_score = sorted_scores[0] if sorted_scores else 0
    best_title = all_titles_sorted[0] if all_titles_sorted else None
    if best_score >= FILE_MATCH_THRESHOLD:
        print(f"Auto-matching file '{file}' to '{best_title}' (confidence: {int(best_score*100)}%)")
        if best_title in features:
            remembered[file] = (best_title, 'feature')
            return best_title, 'feature'
        elif best_title in shorts:
            remembered[file] = (best_title, 'short')
            return best_title, 'short'
    else:
        print(f"Uncertain match for '{file}'. Top candidates:")
        for i in range(min(5, len(all_titles_sorted))):
            t = all_titles_sorted[i]
            s = sorted_scores[i]
            print(f"  {i+1}. {t} ({asset_type(t)}) [{int(s*100)}%]")
            if len(all_titles_sorted) > 5:
                print("  ...other possible matches (alphabetical):")
                for i in range(5, len(all_titles_sorted)):
                    t = all_titles_sorted[i]
                    s = sorted_scores[i]
                    print(f"  {i+1}. {t} ({asset_type(t)}) [{int(s*100)}%]")
    col_width = max(len(opt) for opt in options) + 7  # extra for number
    cols = max(1, shutil.get_terminal_size((80, 20)).columns // col_width)
    print("Select a destination:")
    for i in range(0, len(options), cols):
        row = options[i:i+cols]
        numbered = [f"{i+j+1}. {opt}".ljust(col_width) for j, opt in enumerate(row)]
        print(''.join(numbered))
    # Pre-select likely match
    preselect_idx = None
    if best_match:
        for idx, opt in enumerate(options):
            if best_match in opt:
                preselect_idx = idx
                break
    prompt = f"Enter number (1-{len(options)}) or press Enter to skip: "
    # Try to prefill the prompt with the default number (works in some terminals)
    def input_with_prefill(prompt, prefill):
        try:
            import readline
            readline.set_startup_hook(lambda: readline.insert_text(str(prefill)))
            try:
                return input(prompt)
            finally:
                readline.set_startup_hook()
        except Exception:
            return input(prompt)
    while True:
        choice = input(prompt).strip()
        if not choice:
            remembered[file] = None
            return None, None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                if options[idx] == "Skip":
                    remembered[file] = None
                    return None, None
                # Determine type for session memory
                opt_title = all_titles_sorted[idx] if idx < len(all_titles_sorted) else None
                if opt_title in features:
                    remembered[file] = (opt_title, 'feature')
                    return opt_title, 'feature'
                elif opt_title in shorts:
                    remembered[file] = (opt_title, 'short')
                    return opt_title, 'short'
        print("Invalid input. Try again.")

def organize_from_sources(sources, features_dir, shorts_dir, features, shorts):
    remembered = {}
    global DIR_MATCH_THRESHOLD, FILE_MATCH_THRESHOLD
    # First, try to match and move/copy entire directories
    for source_dir in sources:
        is_downloads = str(source_dir).lower().endswith('downloads')
        for entry in os.scandir(source_dir):
            if entry.is_dir():
                dir_name = entry.name.lower()
                all_titles = features + shorts
                # Use full relative path for matching
                rel_path = os.path.relpath(entry.path, str(ROOT)).replace('\\', '/').lower()
                best_match = None
                best_score = 0.0
                for t in all_titles:
                    score = difflib.SequenceMatcher(None, rel_path, t.lower()).ratio()
                    score = max(score, difflib.SequenceMatcher(None, dir_name, t.lower()).ratio())
                    if score > best_score:
                        best_score = score
                        best_match = t
                # If a close match (score >= threshold), auto-match and move/copy the whole directory
                if best_score >= DIR_MATCH_THRESHOLD:
                    log_info(f"Auto-matching directory '{entry.name}' to '{best_match}' (confidence: {int(best_score*100)}%)")
                    if best_match in features:
                        dest_dir = features_dir / sanitize(best_match)
                    else:
                        dest_dir = shorts_dir / sanitize(best_match)
                    # Only move/copy Screener subfolder if both Film and Screener exist
                    subdirs = {d.name.lower(): d for d in os.scandir(entry.path) if d.is_dir()}
                    if 'screener' in subdirs:
                        screener_dir = subdirs['screener']
                        dest_path = dest_dir / 'Screener'
                        replaced = dest_path.exists()
                        if 'DRY_RUN' in globals() and DRY_RUN:
                            log_debug(f"Would move/copy {screener_dir.path} -> {dest_path}")
                        elif is_downloads:
                            shutil.copytree(screener_dir.path, str(dest_path), dirs_exist_ok=True)
                            if replaced:
                                log_info(f"Directory replaced (copied over): {dest_path}")
                            else:
                                log_debug(f"Directory copied: {screener_dir.path} -> {dest_path}")
                        else:
                            shutil.move(screener_dir.path, str(dest_path))
                            if replaced:
                                log_info(f"Directory replaced (moved over): {dest_path}")
                            else:
                                log_debug(f"Directory moved: {screener_dir.path} -> {dest_path}")
                        # Optionally remove Film subdir if present
                        if 'film' in subdirs:
                            try:
                                if not is_downloads and not (('DRY_RUN' in globals()) and DRY_RUN):
                                    shutil.rmtree(subdirs['film'].path)
                            except Exception:
                                pass
                    else:
                        # Fallback: move/copy all contents as before
                        for item in os.scandir(entry.path):
                            dest_path = dest_dir / item.name
                            replaced = dest_path.exists()
                            if 'DRY_RUN' in globals() and DRY_RUN:
                                log_debug(f"Would move/copy {item.path} -> {dest_path}")
                            elif is_downloads:
                                if item.is_file():
                                    shutil.copy2(item.path, str(dest_path))
                                    if replaced:
                                        log_info(f"File replaced (copied over): {dest_path}")
                                    else:
                                        log_debug(f"File copied: {item.path} -> {dest_path}")
                                    stub = Path(item.path).with_suffix(Path(item.path).suffix + '.stub')
                                    if not stub.exists():
                                        stub.touch(exist_ok=True)
                                else:
                                    shutil.copytree(item.path, str(dest_path), dirs_exist_ok=True)
                                    if replaced:
                                        log_info(f"Directory replaced (copied over): {dest_path}")
                                    else:
                                        log_debug(f"Directory copied: {item.path} -> {dest_path}")
                            else:
                                shutil.move(item.path, str(dest_path))
                                if replaced:
                                    log_info(f"File/Directory replaced (moved over): {dest_path}")
                                else:
                                    log_debug(f"Moved: {item.path} -> {dest_path}")
                    if not is_downloads:
                        try:
                            if not (('DRY_RUN' in globals()) and DRY_RUN):
                                os.rmdir(entry.path)
                        except Exception:
                            pass
                else:
                    log_info(f"Uncertain directory match for '{entry.name}'. Top candidates:")
                    # Show top 5 candidates with scores
                    scores = []
                    for t in all_titles:
                        score = difflib.SequenceMatcher(None, dir_name, t.lower()).ratio()
                        scores.append(score)
                    all_titles_sorted = [t for _, t in sorted(zip(scores, all_titles), key=lambda x: (-x[0], x[1].lower()))]
                    sorted_scores = [s for s, _ in sorted(zip(scores, all_titles), key=lambda x: (-x[0], x[1].lower()))]
                    for i in range(min(5, len(all_titles_sorted))):
                        log_info(f"  {i+1}. {all_titles_sorted[i]} [{int(sorted_scores[i]*100)}%]")
        # Now process individual files as before
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                matched_title = None
                film_dir = None
                # Try to match by title
                for t in features:
                    if t.lower() in file.lower():
                        matched_title = t
                        film_dir = features_dir / sanitize(t)
                        break
                if not matched_title:
                    for t in shorts:
                        if t.lower() in file.lower():
                            matched_title = t
                            film_dir = shorts_dir / sanitize(t)
                            break
                # If still not matched, prompt user (with session memory)
                if not matched_title:
                    if file in remembered:
                        val = remembered[file]
                        if val is None:
                            continue
                        matched_title, typ = val
                        film_dir = (features_dir if typ == 'feature' else shorts_dir) / sanitize(matched_title)
                    elif AUTO_SKIP_UNCLEAR:
                        log_info(f"[AUTO-SKIP] Unmatched file: {file} (skipped due to --auto-skip-unclear)")
                        continue
                    else:
                        matched_title, typ = prompt_user_for_match(file, features, shorts, remembered)
                        if not matched_title:
                            continue
                        film_dir = (features_dir if typ == 'feature' else shorts_dir) / sanitize(matched_title)

                # Determine asset type
                if 'trailer' in file.lower():
                    dest = film_dir / 'Trailer'
                elif 'poster' in file.lower():
                    dest = film_dir / 'Posters'
                elif ext in IMG_EXT:
                    dest = film_dir / 'Stills'
                elif ext in VID_EXT:
                    dest = film_dir / 'Film'
                else:
                    continue
                dest.mkdir(parents=True, exist_ok=True)
                if 'DRY_RUN' in globals() and DRY_RUN:
                    print(f"{file_path} -> {dest / file}")
                elif is_downloads:
                    shutil.copy2(str(file_path), str(dest / file))
                    stub = file_path.with_suffix(file_path.suffix + '.stub')
                    if not stub.exists():
                        stub.touch(exist_ok=True)
                else:
                    try:
                        shutil.move(str(file_path), str(dest / file))
                    except Exception:
                        pass

def rebuild_aggregates():
    for agg, agg_path in AGGREGATES.items():
        agg_path.mkdir(parents=True, exist_ok=True)
        # Remove old links/files
        for f in agg_path.iterdir():
            if f.is_file() or f.is_symlink():
                f.unlink()
        # Collect from Features and Shorts
        for parent in [FEATURES, SHORTS]:
            for film_dir in parent.iterdir():
                if film_dir.is_dir():
                    asset_dir = film_dir / agg.rstrip('s')  # e.g., 'Film', 'Trailer'
                    if asset_dir.exists():
                        for asset in asset_dir.iterdir():
                            link_name = f"{film_dir.name} - {asset.name}"
                            link_path = agg_path / link_name
                            try:
                                link_path.symlink_to(asset.resolve())
                            except Exception:
                                pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Organize film assets with fuzzy matching and dry-run support.")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be moved/copied/auto-matched, but make no changes')
    parser.add_argument('--log-level', default='debug', choices=['debug', 'info', 'none'], help='Set log level: debug, info, or none (default: debug)')
    parser.add_argument('--auto-skip-unclear', action='store_true', help='Automatically skip files that cannot be confidently matched (for unattended/batch runs)')
    args, unknown = parser.parse_known_args()
    DRY_RUN = args.dry_run
    AUTO_SKIP_UNCLEAR = args.auto_skip_unclear

    set_log_level(args.log_level)
    # --- Interactive CSV selection (align with film_downloader.py) ---
    csv_file = choose_csv_file(prompt="Enter path to films CSV file:", file_ext=".csv")
    if not csv_file or not os.path.exists(csv_file):
        print(f"ERROR: File not found: {csv_file}")
        exit(1)
    # Load titles
    FEATURE_TITLES, SHORT_TITLES = load_titles_from_csv(csv_file)
    # Ensure structure from CSV
    for t in FEATURE_TITLES:
        ensure_film_dirs(t, FEATURES)
    for t in SHORT_TITLES:
        ensure_film_dirs(t, SHORTS)
    # Organize dumped files
    organize_all(FEATURES)
    organize_all(SHORTS)
    # Organize from Unsorted and downloads (recursively, move only)
    sources = []
    if UNSORTED.exists():
        sources.append(UNSORTED)
    if DOWNLOADS.exists():
        sources.append(DOWNLOADS)
    if sources:
        organize_from_sources(sources, FEATURES, SHORTS, FEATURE_TITLES, SHORT_TITLES)
    # Rebuild aggregate collections
    rebuild_aggregates()
    print('Done.')
