
import os
import shutil
import json
from pathlib import Path

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
if _changed:
    save_config(_config)

FEATURES = ROOT / 'Features'
SHORTS = ROOT / 'Shorts'

ASSET_TYPES = ['Film', 'Trailer', 'Stills', 'Posters']
AGGREGATES = {
    'Films': ROOT / '_Films',
    'Trailers': ROOT / '_Trailers',
    'Stills': ROOT / '_Stills',
    'Posters': ROOT / '_Posters',
}

# Example titles (replace with actual lists or load from file)
FEATURE_TITLES = [
    'The Snare','The Pantone Guy','Queens of the Dead','Pilgrim','Color Book','Under the Lights',
    'Aontas','Daughters of the Domino','Sunset Somewhere','ITCH!','Any Other Way: The Jackie Shane Story',
    'Sunfish & Other Stories on Green Lake','Beyond the Gaze','Rivalry: Battle of the Bay','Throuple',
    'Bad Shabbos','Darkest Miriam','StartUp Movie','Kill Will','Séance','F*CKTOYS','Didn''t Die',
    'The Devil and the Daylong Brothers'
]
SHORT_TITLES = [
    'Jean Jacket','Theo''s Friend','Sorority','Who Raised You?','Building Bub''s Grubs',
    'Adidas Owns the Reality','THE PEARL COMB','BELIEF','Five Star','Baby Tooth','i want to go to moscow',
    'The Beguiling','Valentine''s Day','The Big Everything','Foxhole','CHECK PLEASE','Theft 101',
    'Confessions of a Homeless Coming Queen','Randy As Himself','Endzgiving','Triptych','A LADY OF PARIS',
    'Got Your Nose','The Viewing','Kansas, 1989','Palestine Islands','Last Hope','Shorthand','Pure Magic',
    'Work Friends','There Goes Stacy','KIKO','C-NOTE','Left on Read','Murder She Wants','Land of Lost Toys',
    'Recesses','Metal'
]

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
                if copy_only:
                    shutil.copy2(str(file), str(dest / file.name))
                    if stub_unsorted:
                        # Create a stub file to prevent reprocessing
                        stub = file.with_suffix(file.suffix + '.stub')
                        stub.touch(exist_ok=True)
                else:
                    shutil.move(str(file), str(dest / file.name))

def organize_all(parent, copy_only=False, stub_unsorted=False):
    for film_dir in parent.iterdir():
        if film_dir.is_dir():
            organize_one(film_dir, copy_only=copy_only, stub_unsorted=stub_unsorted)


def organize_from_sources(sources, features_dir, shorts_dir):
    # Recursively comb all sources, move files to correct asset folders
    for source_dir in sources:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                # Guess film/short by filename (could be improved with metadata)
                matched_title = None
                for t in FEATURE_TITLES:
                    if t.lower() in file.lower():
                        matched_title = t
                        film_dir = features_dir / sanitize(t)
                        break
                if not matched_title:
                    for t in SHORT_TITLES:
                        if t.lower() in file.lower():
                            matched_title = t
                            film_dir = shorts_dir / sanitize(t)
                            break
                if not matched_title:
                    continue  # skip files that don't match any title
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
    # Ensure structure
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
        organize_from_sources(sources, FEATURES, SHORTS)
    # Rebuild aggregate collections
    rebuild_aggregates()
    print('Done.')
