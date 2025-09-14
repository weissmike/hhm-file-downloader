
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

def parse_shorts_blocks_from_csv(csv_path):
    """
    Parse the Shorts Order CSV to extract block names and ordered lists of shorts.
    Returns: OrderedDict {block_name: [short1, short2, ...]}
    Ignores rows with 'Runtime'.
    """
    from collections import OrderedDict
    blocks = OrderedDict()
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)
        if not rows:
            return blocks
        # Assume first non-empty row is header
        header = rows[0]
        for col_idx, col_name in enumerate(header):
            block = col_name.strip()
            if not block:
                continue
            blocks[block] = []
            for row in rows[1:]:
                if col_idx < len(row):
                    val = (row[col_idx] or '').strip()
                    # Skip empty, time, or number cells
                    if not val:
                        continue
                    if ':' in val and val.replace(':','').replace('.','').isdigit():
                        continue
                    if val.replace('.','',1).isdigit():
                        continue
                    # Skip generic tags
                    skip_vals = {'Yes', 'Attending?', 'Narrative Short', 'Documentary Short', 'Female Directed', 'LGBTQ Short', 'Drama', 'Doc', 'C', 'D', 'LD', 'HD', 'RC', 'H', 'DC', 'DR', 'C = Comedy', 'D = Drama', 'LD = Light Drama', 'HD = Heavy Drama', 'RC = Rom Com', 'H = Horror', 'DC =Dark Comedy', 'Doc HD', 'RUNTIME'}
                    if val in skip_vals:
                        continue
                    if len(val) <= 3 and val.isupper():
                        continue
                    blocks[block].append(val)
    return blocks

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
            # Skip stub files (either .stub extension or .stub in name)
            if '.stub' in file.name.lower() or file.suffix.lower() == '.stub':
                continue
            ext = file.suffix.lower()
            fname = file.name.lower()
            moved = False
            # Consistent asset folder naming
            if 'trailer' in fname:
                dest = film_dir / 'Trailer'
                moved = True
            elif 'poster' in fname:
                dest = film_dir / 'Posters'
                moved = True
            elif 'still' in fname or ext in IMG_EXT:
                dest = film_dir / 'Stills'
                moved = True
            elif 'film' in fname or 'screener' in fname or ext in VID_EXT:
                dest = film_dir / 'Film'
                moved = True
            if moved:
                dest_path = dest / file.name
                replaced = dest_path.exists()
                if 'DRY_RUN' in globals() and DRY_RUN:
                    if replaced:
                        print(f"[DRY RUN] Would skip (already exists): {dest_path}")
                        if stub_unsorted:
                            print(f"[DRY RUN] Would stub: {file.with_suffix(file.suffix + '.stub')}")
                    else:
                        if copy_only:
                            print(f"[DRY RUN] Would copy: {file} -> {dest_path}")
                            if stub_unsorted:
                                print(f"[DRY RUN] Would stub: {file.with_suffix(file.suffix + '.stub')}")
                        else:
                            print(f"[DRY RUN] Would move: {file} -> {dest_path}")
                            if stub_unsorted:
                                print(f"[DRY RUN] Would stub: {file.with_suffix(file.suffix + '.stub')}")
                else:
                    if replaced:
                        log_info(f"File already exists, skipping: {dest_path}")
                        if stub_unsorted:
                            # Create a stub file to prevent reprocessing
                            stub = file.with_suffix(file.suffix + '.stub')
                            stub.touch(exist_ok=True)
                    else:
                        if copy_only:
                            shutil.copy2(str(file), str(dest_path))
                            log_debug(f"File copied: {file} -> {dest_path}")
                            if stub_unsorted:
                                stub = file.with_suffix(file.suffix + '.stub')
                                stub.touch(exist_ok=True)
                        else:
                            shutil.move(str(file), str(dest_path))
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
    # Always convert file to absolute Path for consistent logic
    try:
        file_path = Path(file).resolve()
        full_path = str(file_path)
        parent_dir = str(file_path.parent)
    except Exception:
        file_path = Path(file)
        full_path = str(file_path)
        parent_dir = '[unknown]'
    # Guess asset type
    fname = file_path.name.lower()
    ext = file_path.suffix.lower()
    asset_guess = None
    if 'trailer' in fname:
        asset_guess = 'Trailer'
    elif 'poster' in fname:
        asset_guess = 'Posters'
    elif 'still' in fname or ext in IMG_EXT:
        asset_guess = 'Stills'
    elif 'film' in fname or 'screener' in fname or ext in VID_EXT:
        asset_guess = 'Film'
    print(f"\nUnmatched file: [{full_path}]\n  In directory: [{parent_dir}]")
    if asset_guess:
        print(f"  Guessed asset type: {asset_guess}")
    # Try to guess a match using fuzzy logic on filename and parent directory
    # Use full relative path + filename for matching
    global FILE_MATCH_THRESHOLD
    rel_path = str(file_path).replace(str(ROOT), '').replace('\\', '/').lower()
    base = file_path.stem.lower()
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
    # Remove duplicates while preserving order
    seen = set()
    unique_zipped = []
    for score, title in sorted(zipped, key=lambda x: (-x[0], x[1].lower())):
        if title not in seen:
            unique_zipped.append((score, title))
            seen.add(title)
    top5 = unique_zipped[:5]
    rest_titles = set(t for _, t in top5)
    rest = sorted([(s, t) for s, t in unique_zipped[5:] if t not in rest_titles], key=lambda x: x[1].lower())
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
        print(f"Auto-matching file '{full_path}' to '{best_title}' (confidence: {int(best_score*100)}%)")
        if best_title in features:
            remembered[str(file_path)] = (best_title, 'feature')
            return best_title, 'feature'
        elif best_title in shorts:
            remembered[str(file_path)] = (best_title, 'short')
            return best_title, 'short'
    else:
        print(f"Select a destination:")
        col_width = max(len(opt) for opt in options) + 7  # extra for number
        try:
            term_width = shutil.get_terminal_size((120, 30)).columns
        except Exception:
            term_width = 120
        cols = max(2, term_width // col_width)
        rows = (len(options) + cols - 1) // cols
        for row_idx in range(rows):
            row = []
            for col_idx in range(cols):
                opt_idx = col_idx * rows + row_idx
                if opt_idx < len(options):
                    row.append(f"{opt_idx+1}. {options[opt_idx]}".ljust(col_width))
            print(''.join(row))
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
            remembered[str(file_path)] = None
            return None, None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                if options[idx] == "Skip":
                    remembered[str(file_path)] = None
                    return None, None
                # Determine type for session memory
                opt_title = all_titles_sorted[idx] if idx < len(all_titles_sorted) else None
                if opt_title in features:
                    remembered[str(file_path)] = (opt_title, 'feature')
                    return opt_title, 'feature'
                elif opt_title in shorts:
                    remembered[str(file_path)] = (opt_title, 'short')
                    return opt_title, 'short'
        print("Invalid input. Try again.")

def organize_from_sources(sources, features_dir, shorts_dir, features, shorts):
    remembered = {}
    global DIR_MATCH_THRESHOLD, FILE_MATCH_THRESHOLD
    # Only match directories to asset type, never move/copy the directory itself
    for source_dir in sources:
        is_downloads = str(source_dir).lower().endswith('downloads')
        for entry in os.scandir(source_dir):
            if entry.is_dir():
                dir_name = entry.name.lower()
                batch_keywords = ['shorts', 'features', 'trailers', 'stills', 'posters', 'collection', 'batch', 'all']
                # If folder name contains batch/collection keywords, treat as batch folder
                if any(kw in dir_name for kw in batch_keywords):
                    log_info(f"Processing batch/collection folder: '{entry.name}' (distributing files by filename)")
                    for item in os.scandir(entry.path):
                        if item.is_file() and not ('.stub' in item.name.lower() or item.name.lower().endswith('.stub')):
                            # Use the same matching logic as for loose files
                            file_path = Path(item.path)
                            ext = file_path.suffix.lower()
                            matched_title = None
                            film_dir = None
                            for t in features:
                                if t.lower() in item.name.lower():
                                    matched_title = t
                                    film_dir = features_dir / sanitize(t)
                                    break
                            if not matched_title:
                                for t in shorts:
                                    if t.lower() in item.name.lower():
                                        matched_title = t
                                        film_dir = shorts_dir / sanitize(t)
                                        break
                            if not matched_title:
                                # Prompt user as usual, but pass the Path object so parent dir is visible
                                matched_title, typ = prompt_user_for_match(file_path, features, shorts, remembered)
                                if not matched_title:
                                    continue
                                film_dir = (features_dir if typ == 'feature' else shorts_dir) / sanitize(matched_title)
                            # Determine asset type
                            if 'trailer' in item.name.lower():
                                dest = film_dir / 'Trailer'
                            elif 'poster' in item.name.lower():
                                dest = film_dir / 'Posters'
                            elif ext in IMG_EXT:
                                dest = film_dir / 'Stills'
                            elif ext in VID_EXT:
                                dest = film_dir / 'Film'
                            else:
                                continue
                            dest.mkdir(parents=True, exist_ok=True)
                            dest_file = dest / item.name
                            if 'DRY_RUN' in globals() and DRY_RUN:
                                log_debug(f"Would move/copy {item.path} -> {dest_file}")
                            elif is_downloads:
                                shutil.move(item.path, str(dest_file))
                                log_debug(f"File moved: {item.path} -> {dest_file}")
                            else:
                                shutil.move(item.path, str(dest_file))
                                log_debug(f"File moved: {item.path} -> {dest_file}")
                else:
                    # Only process directories that match asset types (stills, posters, trailer, film)
                    asset_type = None
                    for atype in ASSET_TYPES:
                        if atype.lower() in dir_name:
                            asset_type = atype
                            break
                    if asset_type:
                        # Try to match parent directory to a film title
                        parent_dir = Path(entry.path).parent
                        parent_name = parent_dir.name.lower()
                        all_titles = features + shorts
                        best_match = None
                        best_score = 0.0
                        for t in all_titles:
                            score = difflib.SequenceMatcher(None, parent_name, t.lower()).ratio()
                            if score > best_score:
                                best_score = score
                                best_match = t
                        if best_score >= DIR_MATCH_THRESHOLD:
                            log_info(f"Matched asset folder '{entry.name}' under '{parent_dir.name}' to '{best_match}' [{asset_type}] (confidence: {int(best_score*100)}%). Moving files to canonical asset subfolder.")
                            if best_match in features:
                                dest_dir = features_dir / sanitize(best_match) / asset_type
                            else:
                                dest_dir = shorts_dir / sanitize(best_match) / asset_type
                            for item in os.scandir(entry.path):
                                if item.is_file() and not ('.stub' in item.name.lower() or item.name.lower().endswith('.stub')):
                                    dest_path = dest_dir / item.name
                                    replaced = dest_path.exists()
                                    if 'DRY_RUN' in globals() and DRY_RUN:
                                        log_debug(f"Would move/copy {item.path} -> {dest_path}")
                                    elif is_downloads:
                                        shutil.move(item.path, str(dest_path))
                                        if replaced:
                                            log_info(f"File replaced (moved over): {dest_path}")
                                        else:
                                            log_debug(f"File moved: {item.path} -> {dest_path}")
                                    else:
                                        shutil.move(item.path, str(dest_path))
                                        if replaced:
                                            log_info(f"File replaced (moved over): {dest_path}")
                                        else:
                                            log_debug(f"File moved: {item.path} -> {dest_path}")
                        else:
                            log_info(f"Could not confidently match asset folder '{entry.name}' under '{parent_dir.name}' to a film title. Skipping.")
                    else:
                        # Skip folders that don't match asset type
                        log_info(f"Skipping folder: '{entry.name}' (does not match asset type)")
        # Now process individual files as before
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                # Skip stub files (either .stub extension or .stub in name)
                if '.stub' in file.lower() or file.lower().endswith('.stub'):
                    continue
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
                    file_key = str(file_path.resolve())
                    if file_key in remembered:
                        val = remembered[file_key]
                        if val is None:
                            continue
                        matched_title, typ = val
                        film_dir = (features_dir if typ == 'feature' else shorts_dir) / sanitize(matched_title)
                    elif AUTO_SKIP_UNCLEAR:
                        # Show correct parent dir for unmatched file
                        parent_dir = str(file_path.parent)
                        log_info(f"[AUTO-SKIP] Unmatched file: [{file_path}] In directory: [{parent_dir}] (skipped due to --auto-skip-unclear)")
                        continue
                    else:
                        matched_title, typ = prompt_user_for_match(file_path, features, shorts, remembered)
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
                dest_file = dest / file
                stub = file_path.with_suffix(file_path.suffix + '.stub')
                if 'DRY_RUN' in globals() and DRY_RUN:
                    if dest_file.exists():
                        print(f"[DRY RUN] Would skip (already exists): {dest_file}")
                        print(f"[DRY RUN] Would stub: {stub}")
                    else:
                        print(f"[DRY RUN] Would move/copy: {file_path} -> {dest_file}")
                        print(f"[DRY RUN] Would stub: {stub}")
                else:
                    if dest_file.exists():
                        log_info(f"File already exists, skipping: {dest_file}")
                        if not stub.exists():
                            stub.touch(exist_ok=True)
                    else:
                        if is_downloads:
                            shutil.copy2(str(file_path), str(dest_file))
                        else:
                            try:
                                shutil.move(str(file_path), str(dest_file))
                            except Exception:
                                pass
                        if not stub.exists():
                            stub.touch(exist_ok=True)

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
                    # Use correct folder name: plural for Stills/Posters, singular for Film/Trailer
                    if agg in ['Stills', 'Posters']:
                        asset_dir = film_dir / agg
                    elif agg == 'Films':
                        asset_dir = film_dir / 'Film'
                    elif agg == 'Trailers':
                        asset_dir = film_dir / 'Trailer'
                    else:
                        asset_dir = film_dir / agg
                    if not asset_dir.exists():
                        continue
                    for asset in asset_dir.iterdir():
                        if asset.is_file():
                            link_name = f"{film_dir.name} - {asset.name}"
                            link_path = agg_path / link_name
                            try:
                                link_path.symlink_to(asset.resolve())
                            except Exception as e:
                                log_error(f"Failed to symlink {asset} to {link_path}: {e}")

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
    csv_file = choose_csv_file(prompt="Enter path to FILMS CSV file (for feature/short titles):", file_ext=".csv")
    if not csv_file or not os.path.exists(csv_file):
        print(f"ERROR: File not found: {csv_file}")
        exit(1)
    # Prompt for Shorts Blocks CSV (can be the same or different)
    shorts_blocks_csv = choose_csv_file(prompt="Enter path to SHORTS BLOCKS CSV file (for shorts block play order):", file_ext=".csv")
    if not shorts_blocks_csv or not os.path.exists(shorts_blocks_csv):
        print(f"ERROR: File not found: {shorts_blocks_csv}")
        exit(1)
    # Load titles
    FEATURE_TITLES, SHORT_TITLES = load_titles_from_csv(csv_file)
    # Parse shorts blocks and order from Shorts Blocks CSV
    shorts_blocks = parse_shorts_blocks_from_csv(shorts_blocks_csv)
    # Ensure structure from CSV
    for t in FEATURE_TITLES:
        ensure_film_dirs(t, FEATURES)
    for t in SHORT_TITLES:
        ensure_film_dirs(t, SHORTS)
    # --- Organize Shorts into block subfolders by play order ---
    from collections import defaultdict
    shorts_dir = SHORTS
    # Map short title to its canonical folder
    short_to_dir = {t: shorts_dir / sanitize(t) for t in SHORT_TITLES}
    # Track which shorts are sorted into blocks
    sorted_shorts = set()
    # For each block, create a subfolder and move shorts in order
    from utils import fuzzy_match_title
    for block, shorts_list in shorts_blocks.items():
        block_folder = shorts_dir / block
        block_folder.mkdir(exist_ok=True)
        for idx, short_title in enumerate(shorts_list, 1):
            # Use file_match_threshold from config
            match, score = fuzzy_match_title(short_title, list(short_to_dir.keys()), threshold=FILE_MATCH_THRESHOLD)
            src_dir = short_to_dir.get(match) if match else None
            dest_dir = block_folder / f"{idx:02d}_{sanitize(short_title)}"
            if src_dir and src_dir.exists():
                # Move all asset subfolders/files into block subfolder, prefix with order
                if not dest_dir.exists():
                    shutil.move(str(src_dir), str(dest_dir))
                else:
                    log_info(f"Block dest already exists: {dest_dir}")
                sorted_shorts.add(match)
            else:
                # Create empty placeholder folder for missing short
                if not dest_dir.exists():
                    dest_dir.mkdir(parents=True, exist_ok=True)
                log_info(f"[BLOCK PLACEHOLDER] No assets found for short '{short_title}' in block '{block}'. Created empty folder: {dest_dir}")
    # Log any shorts that were not sorted into a block
    unsorted_shorts = [t for t in SHORT_TITLES if (short_to_dir[t].exists() and t not in sorted_shorts)]
    if unsorted_shorts:
        log_info(f"Shorts not sorted into any block: {unsorted_shorts}")
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
