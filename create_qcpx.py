import os
import json
import argparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from datetime import datetime

CONFIG_FILE = 'config.json'

def load_config(config_path=CONFIG_FILE):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- MAIN FUNCTION ---
def create_qcpx(
    output_path,
    films,
    trailers=None,
    promos=None,
    sponsors=None,
    bumper=None,
    gap=None,
    step_repeat=None
):
    """
    Create a Quick Cinema XML (QCPX) file for a block.
    films: list of film filenames (in order)
    trailers: list of trailer filenames (for films after this block)
    promos: list of promo image/video filenames
    sponsors: list of sponsor commercial filenames
    bumper: path to bumper file
    gap: path to 3sec gap file
    step_repeat: path to step and repeat graphic
    """
    db = Element('database')
    db_info = SubElement(db, 'databaseInfo')
    SubElement(db_info, 'version').text = '134481920'
    SubElement(db_info, 'UUID').text = 'GENERATED-' + datetime.now().strftime('%Y%m%d%H%M%S')
    SubElement(db_info, 'nextObjectID').text = '1000'
    # Metadata stub
    metadata = SubElement(db_info, 'metadata')
    plist = SubElement(metadata, 'plist', {'version': '1.0'})
    dict_ = SubElement(plist, 'dict')
    # ... (stub, not used by FCPX)

    obj_id = 100
    def add_video(path, label=None, position=None, block_folder=None):
        nonlocal obj_id
        # Only add if file exists in the block folder (drive)
        if not path:
            return
        # If block_folder is provided, check for file existence relative to block_folder
        rel_path = None
        if block_folder:
            try:
                abs_block = os.path.abspath(block_folder)
                abs_path = os.path.abspath(path)
                if not abs_path.startswith(abs_block):
                    # Try to find the file in the block folder by basename
                    candidate = os.path.join(abs_block, os.path.basename(path))
                    if os.path.exists(candidate):
                        rel_path = os.path.relpath(candidate, abs_block)
                    else:
                        return  # File not present in drive, skip
                else:
                    rel_path = os.path.relpath(abs_path, abs_block)
                if not os.path.exists(os.path.join(abs_block, rel_path)):
                    return  # File not present in drive, skip
            except Exception:
                return
        else:
            if not os.path.exists(path):
                return
            rel_path = os.path.basename(path)
        obj = SubElement(db, 'object', {'type': 'VIDEO', 'id': f'z{obj_id}'})
        SubElement(obj, 'attribute', {'name': 'volume', 'type': 'decimal'}).text = '0.5'
        # Use relative path for url
        url = f'file://{rel_path.replace(os.sep, "/").replace(" ", "%20")}'
        SubElement(obj, 'attribute', {'name': 'url', 'type': 'string'}).text = url
        SubElement(obj, 'attribute', {'name': 'starttimeoffset', 'type': 'float'}).text = '0'
        SubElement(obj, 'attribute', {'name': 'startpadding', 'type': 'float'}).text = '0'
        if position is not None:
            SubElement(obj, 'attribute', {'name': 'position', 'type': 'int16'}).text = str(position)
        SubElement(obj, 'attribute', {'name': 'label', 'type': 'string'}).text = label or os.path.basename(path)
        SubElement(obj, 'attribute', {'name': 'endtimeoffset', 'type': 'float'}).text = '0'
        SubElement(obj, 'attribute', {'name': 'endpadding', 'type': 'float'}).text = '0'
        SubElement(obj, 'attribute', {'name': 'endinstruction', 'type': 'int64'}).text = '0'
        # Bookmark stub
        SubElement(obj, 'attribute', {'name': 'bookmark', 'type': 'binary'}).text = ''
        obj_id += 1

    pos = 0
    # Get block folder (drive folder) for relative pathing and existence check
    block_folder = os.path.dirname(output_path)
    # 1. Trailers for films after this block
    if trailers:
        for t in trailers:
            add_video(t, label=os.path.basename(t), position=pos, block_folder=block_folder)
            pos += 1
    # 1a. Promos
    if promos:
        for p in promos:
            add_video(p, label=os.path.basename(p), position=pos, block_folder=block_folder)
            pos += 1
    # 2. HHM Bumper
    if bumper:
        add_video(bumper, label=os.path.basename(bumper), position=pos, block_folder=block_folder)
        pos += 1
    # 3. Sponsor Commercials
    if sponsors:
        for s in sponsors:
            add_video(s, label=os.path.basename(s), position=pos, block_folder=block_folder)
            pos += 1
    # 4. Films (with 3sec gap between shorts)
    for i, film in enumerate(films):
        add_video(film, label=os.path.basename(film), position=pos, block_folder=block_folder)
        pos += 1
        if gap and i < len(films) - 1:
            add_video(gap, label=os.path.basename(gap), position=pos, block_folder=block_folder)
            pos += 1
    # 5. Step and Repeat Graphic
    if step_repeat:
        add_video(step_repeat, label=os.path.basename(step_repeat), position=pos, block_folder=block_folder)
        pos += 1

    # Write XML
    tree = ElementTree(db)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"Wrote QCPX file to {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a QCPX file for a block using festival CSVs and config.")
    parser.add_argument('--festival-schedule', required=True, help='Path to Festival Schedule CSV')
    parser.add_argument('--shorts-blocks', required=True, help='Path to Shorts Blocks CSV')
    parser.add_argument('--submissions', required=True, help='Path to Film Submissions CSV')
    parser.add_argument('--block-path', required=True, help='Path to the current block folder (output location)')
    parser.add_argument('--block-name', required=True, help='Name of the block (feature or shorts block)')
    parser.add_argument('--output', default=None, help='Output QCPX file path (default: <block-path>/<block-name>.qcpx)')
    args = parser.parse_args()

    config = load_config()
    root_dir = config.get('root_dir', '.')
    # For now, we assume all assets are organized under root_dir

    # Helper to read CSVs
    import csv
    def read_csv(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            return list(csv.reader(f))

    # Helper to sanitize filenames for Windows
    import re
    def sanitize_filename(name):
        # Remove or replace characters not allowed in Windows filenames
        return re.sub(r'[<>:"/\\|?*]', '', name).strip().strip("'").strip('"')

    # Load Shorts Blocks CSV to get shorts order for this block
    shorts_blocks = read_csv(args.shorts_blocks)
    shorts_block_map = {}
    if shorts_blocks:
        headers = shorts_blocks[0]
        for col, block_name in enumerate(headers):
            block_name_clean = block_name.strip().strip("'").strip('"')
            shorts = [row[col].strip().strip("'").strip('"') for row in shorts_blocks[1:] if row[col].strip()]
            shorts_block_map[block_name_clean] = shorts

    # Load Submissions CSV to map film name to asset paths
    submissions = read_csv(args.submissions)
    sub_headers = submissions[0]
    film_name_idx = sub_headers.index('Film Name') if 'Film Name' in sub_headers else 0
    # Map: film name -> dict of all fields
    film_info = {}
    for row in submissions[1:]:
        if len(row) > film_name_idx:
            name_clean = row[film_name_idx].strip().strip("'").strip('"')
            film_info[name_clean] = {sub_headers[i]: row[i] for i in range(len(row)) if i < len(sub_headers)}

    # Determine films for this block
    block_name_clean = args.block_name.strip().strip("'").strip('"')
    if block_name_clean in shorts_block_map:
        # Shorts block
        films_in_block = shorts_block_map[block_name_clean]
    else:
        # Feature block: block name is film name
        films_in_block = [block_name_clean]

    # Find asset files for each film
    films = []
    for film in films_in_block:
        film_clean = film.strip().strip("'").strip('"')
        info = film_info.get(film_clean)
        if info:
            # Try to find the main film file in Features or Shorts
            # Assume organized as <root_dir>/Features/<Film Name>/*.mp4 or Shorts/<Block>/<Short Name>/*.mp4
            import glob
            feature_path = os.path.join(root_dir, 'Features', film_clean)
            shorts_path = os.path.join(root_dir, 'Shorts', block_name_clean, film_clean)
            found = False
            for search_path in [feature_path, shorts_path]:
                if os.path.isdir(search_path):
                    mp4s = glob.glob(os.path.join(search_path, '*.mp4'))
                    if mp4s:
                        films.append(mp4s[0])
                        found = True
                        break
            if not found:
                print(f"[WARN] Film file not found for '{film_clean}' in Features or Shorts.")
        else:
            print(f"[WARN] Film info not found in submissions for '{film_clean}'")

    # TODO: Optionally add trailers, promos, sponsors, bumper, gap, step_repeat from config or block folder
    bumper = os.path.join(root_dir, config.get('BUMPER_FILE', 'HHM_Bumper.mov'))
    gap = os.path.join(root_dir, config.get('GAP_FILE', '3sec.mov'))
    step_repeat = os.path.join(root_dir, config.get('STEP_REPEAT_FILE', 'StepAndRepeat.png'))
    sponsors_dir = os.path.join(root_dir, config.get('SPONSORS_DIR', '_Sponsors'))
    sponsors = []
    if os.path.isdir(sponsors_dir):
        for f in os.listdir(sponsors_dir):
            if f.lower().endswith(('.mp4', '.mov')):
                sponsors.append(os.path.join(sponsors_dir, f))

    # Sanitize output filename
    output_filename = sanitize_filename(args.block_name) + ".qcpx"
    output_path = args.output or os.path.join(args.block_path, output_filename)
    create_qcpx(output_path, films, [], [], sponsors, bumper, gap, step_repeat)
