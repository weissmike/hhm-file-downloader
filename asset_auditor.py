import os
import csv
import argparse
import subprocess
import json
from datetime import datetime
from pathlib import Path
from utils import fuzzy_match_title

# --- Logging ---
def log_info(msg):
    print(msg)

# --- File details with ffprobe ---
def get_file_details(file_path):
    details = {}
    try:
        # Get file size in GB
        try:
            size_bytes = os.path.getsize(file_path)
            size_gb = round(size_bytes / (1024 ** 3), 2)
            details['Size (GB)'] = size_gb
        except Exception:
            details['Size (GB)'] = 'N/A'
        # Get runtime using ffprobe -show_format
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            # Runtime extraction
            duration = None
            if 'format' in info and 'duration' in info['format']:
                try:
                    duration = float(info['format']['duration'])
                except Exception:
                    duration = None
            if duration:
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                details['Runtime'] = f"{hours:02}:{minutes:02}:{seconds:02}"
            else:
                details['Runtime'] = 'N/A'
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            audio_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
            if video_stream:
                width = video_stream.get('width', 'N/A')
                height = video_stream.get('height', 'N/A')
                details['Resolution'] = f"{width}x{height}"
                details['Format'] = video_stream.get('pix_fmt', 'N/A')
                details['Video Codec'] = video_stream.get('codec_name', 'N/A')
                details['Frame Rate'] = video_stream.get('r_frame_rate', 'N/A')
                aspect = video_stream.get('display_aspect_ratio', None)
                if not aspect or aspect in ('N/A', '', None):
                    try:
                        w = int(width)
                        h = int(height)
                        if w > 0 and h > 0:
                            from math import gcd
                            g = gcd(w, h)
                            aspect = f"{w//g}:{h//g}"
                        else:
                            aspect = 'N/A'
                    except Exception:
                        aspect = 'N/A'
                details['Aspect Ratio'] = aspect
                details['Color Space'] = video_stream.get('color_space', 'N/A')
                details['Color Primaries'] = video_stream.get('color_primaries', 'N/A')
                details['Color Transfer'] = video_stream.get('color_transfer', 'N/A')
                # Bitrate (bps)
                br = video_stream.get('bit_rate') or video_stream.get('bitrate')
                if br:
                    try:
                        details['Bitrate'] = int(br)
                    except Exception:
                        details['Bitrate'] = br
            else:
                details.update({k: 'N/A' for k in [
                    'Resolution','Format','Video Codec','Frame Rate','Aspect Ratio',
                    'Color Space','Color Primaries','Color Transfer'
                ]})
            if audio_stream:
                details['Audio Codec'] = audio_stream.get('codec_name', 'N/A')
                ch = audio_stream.get('channels', 'N/A')
                if ch == 2:
                    details['Sound'] = '2.0'
                elif ch == 6:
                    details['Sound'] = '5.1'
                else:
                    details['Sound'] = str(ch)
            else:
                details['Audio Codec'] = details['Sound'] = 'N/A'
        else:
            details['FFPROBE WARNING'] = result.stderr.strip()
    except Exception as e:
        details['FFPROBE WARNING'] = str(e)
    return details

# --- Check concerns ---
def check_concerns(details):
    concerns = {}
    summary = []
    allowed_color_spaces = {"bt709","bt.709","bt601","bt.601","smpte170m","smpte240m","sRGB","srgb"}
    allowed_primaries   = allowed_color_spaces
    allowed_transfer    = {"bt709","bt.709","bt601","bt.601","smpte170m","iec61966-2-1","sRGB","srgb"}

    if details.get("Color Space","N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A",""):
        concerns["Color Space"] = True
        summary.append("The color space of your file is unusual. Please export using BT.709.")

    if details.get("Color Primaries","N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A",""):
        concerns["Color Primaries"] = True
        summary.append("The color primaries are non-standard. Use BT.709 primaries.")

    if details.get("Color Transfer","N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A",""):
        concerns["Color Transfer"] = True
        summary.append("Non-standard color transfer. Use BT.709 or sRGB.")

    res = details.get("Resolution","N/A")
    try:
        if res != "N/A":
            w,h = map(int,res.lower().split("x"))
            # Only flag as concern if not a standard safe resolution
            safe_res = [(1920,1080), (1280,720), (3840,2160), (4096,2160), (2048,858), (2048,1080), (1998,1080)]
            if (w,h) not in safe_res:
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Above 1080p. Recommend 1920x1080 export.")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Below 720p. Recommend 1080p export.")
    except Exception:
        pass

    try:
        br = details.get("Bitrate","N/A")
        if br != "N/A":
            br_mbps = int(br)/1_000_000
            if br_mbps > 50:
                concerns["Bitrate"] = True
                summary.append("Bitrate > 50 Mbps. Try exporting under 50 Mbps.")
            elif br_mbps < 2:
                concerns["Bitrate"] = True
                summary.append("Bitrate < 2 Mbps. Use at least 2 Mbps.")
    except Exception:
        pass

    if details.get("Sound","N/A") not in ("2.0","5.1","N/A"):
        concerns["Sound"] = True
        summary.append("Audio channels non-standard. Use stereo (2.0) or surround (5.1).")

    # Accept 23.98, 24, 25 as standard (numeric tolerance)
    allowed_fps_values = [23.98, 24.0, 25.0, 29.97]
    fr = details.get("Frame Rate","N/A")
    try:
        if fr != "N/A":
            if "/" in fr:
                num, denom = fr.split("/")
                num = float(num)
                denom = float(denom)
                fps_val = round(num/denom, 2) if denom != 0 else None
            else:
                fps_val = float(fr)
            if fps_val is not None and not any(abs(fps_val - std) < 0.02 for std in allowed_fps_values):
                concerns["Frame Rate"] = True
                summary.append(f"Frame rate non-standard ({fps_val}). Use 23.98, 24, or 25 fps.")
    except Exception:
        pass

    for k,v in details.items():
        if v == "N/A" and k not in ("FFPROBE WARNING",):
            concerns[k] = True
            summary.append(f"Missing technical detail: {k}.")

    try:
        sz = float(details.get("Size (GB)",0))
        if sz > 10:
            concerns["Size (GB)"] = "critical"
            summary.append("File size > 10GB. Please export a smaller file if possible. ❌")
        elif sz < 0.7 and sz > 0:
            concerns["Size (GB)"] = "caution"
            summary.append("File size < 0.7GB. May be too low quality. ⚠️")
    except Exception:
        pass

    rt = details.get("Runtime","N/A")
    try:
        if rt != "N/A":
            h,m,s = map(int,rt.split(":"))
            total_min = h*60 + m + s/60
            if total_min > 180:
                concerns["Runtime"] = True
                summary.append("Film > 3 hours. Confirm with festival.")
    except Exception:
        pass

    return concerns, summary

# --- Extract titles from CSV ---

# --- Robust title extraction for all CSVs ---
def extract_titles_from_csv(path, possible_fields=None, mode=None):
    """
    mode: 'schedule', 'submissions', 'shorts', or None (auto-detect by filename)
    """
    titles = set()
    if not os.path.exists(path):
        log_info(f"[WARN] CSV not found: {path}")
        return titles
    fname = os.path.basename(path).lower()
    if mode is None:
        if 'schedule' in fname:
            mode = 'schedule'
        elif 'submissions' in fname or 'export' in fname:
            mode = 'submissions'
        elif 'shorts' in fname:
            mode = 'shorts'
        else:
            mode = 'default'
    # --- Schedule CSV: scan all non-empty, non-block-name cells except first column ---
    if mode == 'schedule':
        import re
        with open(path, 'r', encoding='utf-8') as f:
            reader = list(csv.reader(f))
            if not reader:
                print(f"[DEBUG] [schedule] No rows in {path}")
                return titles
            header = reader[0]
            block_col_indices = [3,6,9]  # 0-based indices for block name columns
            block_names = set()
            for row in reader[1:]:
                for idx in block_col_indices:
                    if idx < len(row):
                        val = row[idx].strip()
                        # Only collect non-empty, non-time, non-duplicate block names
                        if not val:
                            continue
                        if re.match(r'^(\d{1,2}:\d{2}\s*[AP]M)$', val, re.IGNORECASE):
                            continue
                        block_names.add(val)
            titles = block_names
        print(f"[DEBUG] [schedule-blocks] Extracted {len(titles)} block names from {path}: {list(titles)[:5]}")
        return titles
    # --- Submissions CSV: use 'name' column ---
    if mode == 'submissions':
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            print(f"[DEBUG] Fieldnames in {path}: {reader.fieldnames}")
            if 'name' in reader.fieldnames:
                for row in reader:
                    val = row.get('name','').strip()
                    if val:
                        titles.add(val)
            else:
                print(f"[WARN] No 'name' column in {path}")
        print(f"[DEBUG] [submissions] Extracted {len(titles)} titles from {path}: {list(titles)[:5]}")
        return titles
    # --- Shorts CSV: all non-empty cells in all columns ---
    if mode == 'shorts':
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            print(f"[DEBUG] Fieldnames in {path}: {reader.fieldnames}")
            for row in reader:
                for field in reader.fieldnames:
                    val = row.get(field,'').strip()
                    if val:
                        titles.add(val)
        print(f"[DEBUG] [shorts] Extracted {len(titles)} titles from {path}: {list(titles)[:5]}")
        return titles
    # --- Default: fallback to old logic ---
    with open(path,'r',encoding='utf-8') as f:
        reader = csv.DictReader(f)
        print(f"[DEBUG] Fieldnames in {path}: {reader.fieldnames}")
        fields = [h for h in reader.fieldnames if any(key in h.lower() for key in (possible_fields or []))]
        print(f"[DEBUG] Matched fields in {path}: {fields}")
        for row in reader:
            for field in fields:
                val = row.get(field,'').strip()
                if val:
                    titles.add(val)
    return titles

# --- Asset discovery ---
def discover_assets(root, all_titles, log_info=print):
    def strip_number_prefix(name):
        import re
        return re.sub(r'^\d+[_\-\s]+','',name).strip()
    def norm(s):
        s = strip_number_prefix(s)
        return ''.join(e for e in s.lower() if e.isalnum())

    asset_root = Path(root)
    asset_type_folders = {"Film","Posters","Stills","Trailer"}
    asset_names = []
    all_films = {}
    asset_name_to_display = {}

    # Features
    features_base = asset_root/'Features'
    if features_base.exists():
        for film_dir in features_base.iterdir():
            if not film_dir.is_dir() or film_dir.name in asset_type_folders:
                continue
            norm_name = norm(film_dir.name)
            asset_names.append(norm_name)
            asset_name_to_display[norm_name] = film_dir.name
            film_entry = all_films.setdefault(norm_name, {'type': 'feature', 'assets': {}})
            for asset_type_dir in film_dir.iterdir():
                if not asset_type_dir.is_dir():
                    continue
                asset_type = asset_type_dir.name
                film_entry['assets'].setdefault(asset_type, [])
                for f in asset_type_dir.iterdir():
                    if f.is_file():
                        film_entry['assets'][asset_type].append(str(f))
    print(f"[DEBUG] Asset folder normalized names: {asset_names}")

    # Shorts
    shorts_base = asset_root/'Shorts'
    if shorts_base.exists():
        for block_dir in shorts_base.iterdir():
            if not block_dir.is_dir() or block_dir.name in asset_type_folders:
                continue
            for short_dir in block_dir.iterdir():
                if not short_dir.is_dir() or short_dir.name in asset_type_folders:
                    continue
                stripped_name = strip_number_prefix(short_dir.name)
                norm_name = norm(stripped_name)
                asset_names.append(norm_name)
                asset_name_to_display[norm_name] = short_dir.name
                film_entry = {'type':'short','assets':{}}
                for asset_type_dir in short_dir.iterdir():
                    if not asset_type_dir.is_dir():
                        continue
                    asset_type = asset_type_dir.name
                    film_entry['assets'].setdefault(asset_type,[])
                    for f in asset_type_dir.iterdir():
                        if f.is_file():
                            film_entry['assets'][asset_type].append(str(f))
                all_films[norm_name] = film_entry

    # Fuzzy match
    films = {}
    display_to_key = {}
    for t in all_titles:
        norm_t = norm(t)
        best_match, score = fuzzy_match_title(norm_t, asset_names, threshold=0.7)
        if best_match:
            films[best_match] = all_films[best_match]
            display_to_key[t] = best_match
    return films, display_to_key

# --- Report ---
def generate_report(films, out_path, include_titles=None, display_to_key=None):
    print(f"[DEBUG] generate_report called: {len(films)} films, out_path={out_path}")
    with open(out_path,'w',encoding='utf-8') as f:
        f.write("# Asset Audit Report\n\n")
        f.write(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
        if not films:
            print("[DEBUG] No films found to write in report.")
            f.write("No films found.\n")
            return

        # Missing film assets (use display names)
        missing_main = []
        for film, info in films.items():
            has_film = any(asset_type.lower()=='film' and files for asset_type, files in info['assets'].items())
            if not has_film:
                # Find all display names for this key
                display_names = [disp for disp, key in (display_to_key or {}).items() if key == film]
                if display_names:
                    missing_main.extend(display_names)
                else:
                    missing_main.append(film)
        if missing_main:
            f.write("## Films Missing Main Film Asset\n\n")
            for film in sorted(set(missing_main)):
                f.write(f"- {film}\n")
            f.write("\n")

        # Asset counts
        f.write("## Asset Counts Table\n\n")
        titles_to_report = include_titles if include_titles else list(films.keys())
        print(f"[DEBUG] Writing asset counts for {len(titles_to_report)} titles.")
        # Split into two columns
        n = len(titles_to_report)
        mid = (n + 1) // 2
        col1 = sorted(titles_to_report)[:mid]
        col2 = sorted(titles_to_report)[mid:]
        # Prepare rows for each column
        def asset_row(film):
            key = display_to_key.get(film,film) if display_to_key else film
            info = films.get(key)
            if not info:
                return f"| {film} | 0 ⚠️ | 0 ❌ | N/A | 0 ❌ |"
            assets = info.get('assets',{})
            stills = len(assets.get('Stills',[]))
            posters = len(assets.get('Posters',[]))
            trailers = len(assets.get('Trailer',[]))
            films_count = len(assets.get('Film',[]))
            if stills == 0:
                stills_str = "0 ⚠️"
            elif stills < 3:
                stills_str = f"{stills} ⚠️"
            else:
                stills_str = str(stills)
            if posters == 0:
                posters_str = "0 ❌"
            else:
                posters_str = str(posters)
            if trailers == 0:
                trailers_str = "0 ⚠️"
            else:
                trailers_str = str(trailers)
            if films_count == 0:
                films_str = "0 ❌"
            elif films_count > 1:
                films_str = f"{films_count} ❌"
            else:
                films_str = str(films_count)
            return f"| {film} | {stills_str} | {posters_str} | {trailers_str} | {films_str} |"

        # Write two tables side by side
        f.write("| Film | Stills | Posters | Trailers | Films | Title | Stills | Posters | Trailers | Films |\n")
        f.write("|------|--------|---------|----------|-------|-------|--------|---------|----------|-------|\n")
        for i in range(max(len(col1), len(col2))):
            row1 = asset_row(col1[i]) if i < len(col1) else "|  |  |  |  |"
            row2 = asset_row(col2[i]) if i < len(col2) else "|  |  |  |  |  |"
            # Remove leading and trailing | for row2, then join
            row2 = row2.strip('|').rstrip()
            f.write(f"{row1}    {row2}\n")

        # Tech checks table
        f.write("\n## Technical Checks Table\n\n")
        f.write(
            "**Legend:**\n"
            "- **Resolution:** 1920x1080, 1280x720, 3840x2160, 4096x2160, 2048x858, 2048x1080, 1998x1080\n"
            "- **Frame Rate:** 23.98, 24, 25, 29.97\n"
            "- **Aspect Ratio:** Derived from resolution if missing\n"
            "- **Color Space/Primaries/Transfer:** bt709\n"
            "- **Sound:** 2.0 (stereo) or 5.1 (surround)\n"
            "- **⚠️:** Indicates a value is out of spec or missing\n\n"
        )
        f.write("| Film | Resolution | Format | Video Codec | Bitrate | Frame Rate | Aspect Ratio | Color Space | Color Primaries | Color Transfer | Audio Codec | Sound | Runtime | File Size (GB) |\n")
        f.write("|------|------------|--------|-------------|---------|------------|--------------|-------------|-----------------|---------------|-------------|-------|---------|---------------|\n")
        tech_fields = [
            'Resolution', 'Format', 'Video Codec', 'Bitrate', 'Frame Rate', 'Aspect Ratio',
            'Color Space', 'Color Primaries', 'Color Transfer', 'Audio Codec', 'Sound', 'Runtime', 'Size (GB)'
        ]
        for film in sorted(titles_to_report):
            key = display_to_key.get(film,film) if display_to_key else film
            info = films.get(key)
            if not info:
                f.write(f"| {film} |  |  |  |  |  |  |  |  |  |  |\n")
                continue
            film_files = info.get('assets',{}).get('Film',[])
            if film_files:
                details = get_file_details(film_files[0])
                concerns, summary = check_concerns(details)
            else:
                details = {}
                concerns = {}
            row = [film]
            for field in tech_fields:
                val = details.get(field, '')
                # Special formatting for Frame Rate
                if field == 'Frame Rate' and val:
                    try:
                        if '/' in val:
                            num, denom = val.split('/')
                            num = float(num)
                            denom = float(denom)
                            if denom != 0:
                                rounded = round(num/denom, 2)
                                val_fmt = f"{rounded:.2f}"
                            else:
                                val_fmt = val
                        else:
                            val_fmt = val
                    except Exception:
                        val_fmt = val
                    if field in concerns:
                        val_fmt += " ⚠️"
                    row.append(val_fmt)
                    continue
                # Special formatting for Bitrate (show in Mbps if possible)
                if field == 'Bitrate' and val not in ('', 'N/A'):
                    try:
                        mbps = float(val) / 1_000_000
                        val_fmt = f"{mbps:.2f} Mbps"
                    except Exception:
                        val_fmt = str(val)
                    if field in concerns:
                        val_fmt += " ⚠️"
                    row.append(val_fmt)
                    continue
                # Special formatting for Size (GB)
                if field == 'Size (GB)':
                    if 'Size (GB)' in concerns:
                        if concerns['Size (GB)'] == 'critical':
                            val = f"{val} ❌"
                        elif concerns['Size (GB)'] == 'caution':
                            val = f"{val} ⚠️"
                    row.append(val)
                    continue
                # Special formatting for Runtime (add warning if in concerns)
                if field == 'Runtime' and field in concerns:
                    val = f"{val} ⚠️"
                    row.append(val)
                    continue
                if field in concerns:
                    val = f"{val} ⚠️"
                row.append(val)
            f.write("| " + " | ".join(str(x) for x in row) + " |\n")
    print(f"[DEBUG] Report written to {out_path}")

# --- Mail merge ---
def generate_mail_merge_csv(films, csv_path):
    rows = []
    def get_advice(film, info):
        advice = set()
        for asset_type, files in info['assets'].items():
            if asset_type.lower() in ('film','screener'):
                if not files:
                    advice.add("Main film file missing. Please upload.")
                for f in files:
                    details = get_file_details(f)
                    _, summary = check_concerns(details)
                    for s in summary:
                        advice.add(s)
                    if f.lower().endswith('.zip'):
                        advice.add("ZIP found. Please upload video file directly.")
        return sorted(advice)
    for film, info in films.items():
        advice = get_advice(film, info)
        if advice:
            rows.append({'Film':film,'Issue':'','Advice':'\n'.join(advice)})
    if rows:
        with open(csv_path,'w',newline='',encoding='utf-8') as f:
            writer = csv.DictWriter(f,fieldnames=['Film','Issue','Advice'])
            writer.writeheader()
            writer.writerows(rows)
        log_info(f"Wrote mail-merge CSV to {csv_path}")
    else:
        log_info("No flagged films to write to mail-merge CSV.")

# --- CLI entry point ---
def main():


    parser = argparse.ArgumentParser(description="Audit film and shorts assets for festival.")
    parser.add_argument('--root', type=str, default='.', help='Root directory containing Features and Shorts folders')
    parser.add_argument('--schedule', type=str, default='2025 Festival Schedule - Film Festival Schedule Simplified.csv')
    parser.add_argument('--shorts', type=str, default='HHM 2025 Film Selections - Shorts in Columns.csv')
    parser.add_argument('--submissions', type=str, default='films-export-2025-09-12T00_30_55.724Z.csv')
    parser.add_argument('--out', type=str, default='Audit/asset_audit_report.md', help='Output report file')
    parser.add_argument('--mail-merge', action='store_true', help='Generate mail-merge CSV for flagged films')
    parser.add_argument('--film-list', type=str, default=None, help='Comma-separated list of film titles to restrict report (not a file)')
    args = parser.parse_args()

    # Use choose_csv_file from utils.py for missing CSVs
    from utils import choose_csv_file
    if not os.path.exists(args.schedule):
        args.schedule = choose_csv_file(prompt=f"Schedule CSV not found at '{args.schedule}'. Please select the schedule CSV:")
    if not os.path.exists(args.shorts):
        args.shorts = choose_csv_file(prompt=f"Shorts CSV not found at '{args.shorts}'. Please select the shorts CSV:")
    if not os.path.exists(args.submissions):
        args.submissions = choose_csv_file(prompt=f"Submissions CSV not found at '{args.submissions}'. Please select the submissions CSV:")

    print(f"[DEBUG] Using schedule CSV: {args.schedule}")
    print(f"[DEBUG] Using shorts CSV: {args.shorts}")
    print(f"[DEBUG] Using submissions CSV: {args.submissions}")



    # --- Step 1: Parse shorts block names referenced in schedule ---
    referenced_blocks = set()
    with open(args.schedule, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            for cell in row:
                val = cell.strip()
                if val and val.lower().startswith('shorts') or val.lower() == 'michigan shorts':
                    referenced_blocks.add(val.strip())
    print(f"[DEBUG] Shorts blocks referenced in schedule: {referenced_blocks}")

    # --- Step 2: For each referenced block, extract all films from that column in shorts CSV ---
    shorts_block_films = set()
    with open(args.shorts, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        block_fields = [field for field in reader.fieldnames if field.strip() in referenced_blocks]
        print(f"[DEBUG] Shorts block columns found in shorts CSV: {block_fields}")
        for row in reader:
            for field in block_fields:
                val = row.get(field, '').strip()
                if val:
                    shorts_block_films.add(val)
    print(f"[DEBUG] Shorts films scheduled: {list(shorts_block_films)[:10]}")

    # --- Step 3: Extract all feature/other titles as before ---
    submission_titles = extract_titles_from_csv(args.submissions, mode='submissions')

    # --- Step 4: Combine all titles for audit ---
    import re
    def normalize_title(title):
        # Lowercase, trim, collapse whitespace, remove punctuation
        t = title.lower().strip()
        t = re.sub(r'\s+', ' ', t)
        t = re.sub(r'[\W_]+', '', t)  # Remove all non-alphanumeric
        return t

    # Combine and normalize titles, deduplicate by normalized form
    all_titles_raw = list(shorts_block_films | submission_titles)
    norm_to_display = {}
    for t in all_titles_raw:
        norm = normalize_title(t)
        if norm and norm not in norm_to_display:
            norm_to_display[norm] = t
    titles = sorted(norm_to_display.values())

    # If --film-list is provided, restrict titles to those in the list
    if args.film_list:
        film_list_titles = [t.strip() for t in args.film_list.split(',') if t.strip()]
        film_list_norms = set(normalize_title(t) for t in film_list_titles)
        titles = [t for t in titles if normalize_title(t) in film_list_norms]

    print(f"[DEBUG] Combined unique titles ({len(titles)}): {titles[:10]}")
    print(f"[SUMMARY] Shorts blocks scheduled: {len(referenced_blocks)}")
    print(f"[SUMMARY] Shorts films scheduled: {len(shorts_block_films)}")
    print(f"[SUMMARY] Submission titles: {len(submission_titles)}")
    print(f"[SUMMARY] Total unique titles for audit: {len(titles)}")
    if not titles:
        print("No titles found. Exiting.")
        return


    # Load config.json to get FILMS_DIR as the true asset root
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    # Determine root_dir for assets and reports
    root_dir = config.get('root_dir', args.root)
    print(f"[DEBUG] Using root_dir: {root_dir}")
    asset_root = root_dir  # Always use root_dir for Features/Shorts
    print(f"[DEBUG] Asset discovery will use: {asset_root}/Features and {asset_root}/Shorts")

    # Determine report output path
    if args.out != parser.get_default('out'):
        report_path = args.out
    else:
        report_dir = os.path.join(root_dir, 'Audit')
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, 'asset_audit_report.md')
    print(f"[DEBUG] Report will be written to: {report_path}")

    films, display_to_key = discover_assets(asset_root, titles, log_info=log_info)
    print(f"[SUMMARY] Number of films discovered: {len(films)}")
    for film, info in films.items():
        print(f"[DEBUG] Film: {film}, asset types: {list(info.get('assets', {}).keys())}")

    generate_report(films, report_path, include_titles=titles, display_to_key=display_to_key)
    print(f"Report written to {report_path}")

    if args.mail_merge:
        mail_merge_csv = os.path.splitext(report_path)[0]+"_mail_merge.csv"
        generate_mail_merge_csv(films, mail_merge_csv)
        print(f"Mail-merge CSV written to {mail_merge_csv}")

if __name__ == "__main__":
    main()
