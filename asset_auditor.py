# --- Minimal scan_assets stub to resolve missing definition ---
def scan_assets(root_dir, include_titles=None):
    films = {}
    asset_type_folders = {"Film", "Posters", "Stills", "Trailer"}
    include_set = set(t.strip().lower() for t in include_titles) if include_titles else None
    for typ in ['Features', 'Shorts']:
        base = Path(root_dir) / typ
        if not base.exists():
            continue
        for film_dir in base.iterdir():
            if not film_dir.is_dir():
                continue
            if film_dir.name in asset_type_folders:
                continue
            if include_set and film_dir.name.lower() not in include_set:
                continue
            # For Shorts, skip the main block folders (e.g., 'Shorts 1', 'Shorts 2', etc.)
            if typ == 'Shorts' and all((subdir.is_dir() for subdir in film_dir.iterdir())):
                for numbered_short in film_dir.iterdir():
                    if not numbered_short.is_dir():
                        continue
                    if numbered_short.name in asset_type_folders:
                        continue
                    short_name = numbered_short.name
                    if include_set and short_name.lower() not in include_set:
                        continue
                    film_entry = films.setdefault(short_name, {'type': 'short', 'assets': {}})
                    for asset_type_dir in numbered_short.iterdir():
                        if not asset_type_dir.is_dir():
                            continue
                        asset_type = asset_type_dir.name
                        film_entry['assets'].setdefault(asset_type, [])
                        for f in asset_type_dir.iterdir():
                            if f.is_file():
                                film_entry['assets'][asset_type].append(str(f))
                continue
            film_name = film_dir.name
            if include_set and film_name.lower() not in include_set:
                continue
            film_entry = films.setdefault(film_name, {'type': typ[:-1].lower(), 'assets': {}})
            for asset_type_dir in film_dir.iterdir():
                if not asset_type_dir.is_dir():
                    continue
                asset_type = asset_type_dir.name
                film_entry['assets'].setdefault(asset_type, [])
                for f in asset_type_dir.iterdir():
                    if f.is_file():
                        film_entry['assets'][asset_type].append(str(f))
    return films
import os
import subprocess
import argparse
from datetime import datetime
import csv
# --- Logging stubs ---
def log_info(msg):
    print(msg)

def set_log_level(level):
    pass

def check_concerns(details):
    """
    Returns (concerns_dict, summary_list):
    - concerns_dict: {field: True} for any field that is concerning
    - summary_list: [messages] for summary section
    """
    concerns = {}
    summary = []
    # Example rules (customize as needed for your festival):
    # - Resolution < 1920x1080
    # - Aspect Ratio not 16:9, 1.85:1, or 2.39:1
    # - Format not mov/mp4/mkv
    # - Video Codec not h264/prores
    # - Audio Codec not AAC/PCM
    # - Channels < 2
    # - Bitrate < 10 Mbps
    # - Frame Rate < 23.97 or > 60
    # - Runtime > 180 min or < 1 min
    # - Size < 2GB
    res = details.get('Resolution', '')
    if res and 'x' in res:
        try:
            w, h = [int(x) for x in res.split('x')]
            if w != 1920 or h != 1080:
                concerns['Resolution'] = True
                summary.append(f"Non-1080p resolution: {w}x{h}")
        except Exception:
            pass
    aspect = details.get('Aspect Ratio', '')
    # Acceptable aspect ratios (as floats and strings)
    allowed_ratios = {
        '16:9': 16/9,
        '1.85:1': 1.85,
        '2.39:1': 2.39,
        '2.40:1': 2.40,
        '1.78:1': 1.78,
        '4:3': 4/3,
        '1.33:1': 1.33
    }
    def aspect_str_to_float(val):
        if not val or val == 'N/A':
            return None
        if ':' in val:
            try:
                num, denom = val.split(':')
                return float(num) / float(denom)
            except Exception:
                return None
        try:
            return float(val)
        except Exception:
            return None
    aspect_ok = False
    if aspect:
        # Accept if exact string match
        if aspect in allowed_ratios:
            aspect_ok = True
        else:
            # Accept if float value is close to any allowed
            aspect_val = aspect_str_to_float(aspect)
            if aspect_val:
                for allowed in allowed_ratios.values():
                    if abs(aspect_val - allowed) < 0.02:
                        aspect_ok = True
                        break
    if aspect and not aspect_ok:
        concerns['Aspect Ratio'] = True
        summary.append(f"Unusual aspect ratio: {aspect}")
    fmt = details.get('Format', '').lower()
    # Do not flag yuv420p
    if fmt and not any(x in fmt for x in ['yuv420p', 'mov', 'mp4', 'mkv']):
        concerns['Format'] = True
        summary.append(f"Unusual format: {fmt}")
    vcodec = details.get('Video Codec', '').lower()
    if vcodec and not any(x in vcodec for x in ['h264']):
        concerns['Video Codec'] = True
        summary.append(f"Unusual video codec: {vcodec}")
    acodec = details.get('Audio Codec', '').lower()
    if acodec and not any(x in acodec for x in ['aac', 'pcm']):
        concerns['Audio Codec'] = True
        summary.append(f"Unusual audio codec: {acodec}")
    # Sound (Channels): flag if not 2.0 or 5.1
    sound = details.get('Sound', '')
    if sound not in {'2.0', '5.1'}:
        concerns['Sound'] = True
        summary.append(f"Unusual audio channel count: {sound}")
    # Bitrate: flag if <4 Mbps or >20 Mbps
    try:
        br = float(details.get('Bitrate', 0))
        if br and (br < 4_000_000 or br > 20_000_000):
            concerns['Bitrate'] = True
            summary.append(f"Unusual bitrate: {br}")
    except Exception:
        pass
    # Frame Rate: flag if <23.5 or >60
    try:
        fr = float(details.get('Frame Rate', 0))
        if fr and (fr < 23.5 or fr > 60):
            concerns['Frame Rate'] = True
            summary.append(f"Unusual frame rate: {fr}")
    except Exception:
        pass
    # Runtime: flag if <1 or >180 min
    try:
        rt = float(details.get('Runtime', 0))
        if rt and (rt < 1 or rt > 180):
            concerns['Runtime'] = True
            summary.append(f"Unusual runtime: {rt} min")
    except Exception:
        pass
    # File size: flag if <.7GB or >10GB
    try:
        sz = float(details.get('Size (GB)', 0))
        if sz and (sz < .7 or sz > 10):
            concerns['Size (GB)'] = True
            summary.append(f"Unusual file size: {sz} GB")
    except Exception:
        pass
    # 5.1 mapping: SMPTE is standard for DCP/festival; flag Film/ITU mapping if detected
    # (ffprobe does not provide channel layout by default; if available, check details['Channel Layout'])
    ch_layout = details.get('Channel Layout', '').lower()
    if sound == '5.1':
        # SMPTE: L R C LFE Ls Rs; Film/ITU: L C R LFE Ls Rs
        # If channel layout is available, check for SMPTE order
        if ch_layout:
            smpte = ['l', 'r', 'c', 'lfe', 'ls', 'rs']
            film = ['l', 'c', 'r', 'lfe', 'ls', 'rs']
            layout = [x.strip() for x in ch_layout.replace('(', '').replace(')', '').replace('/', ' ').replace(',', ' ').split() if x.strip()]
            if layout[:6] == smpte:
                pass  # OK
            elif layout[:6] == film:
                concerns['Sound Standard'] = True
                summary.append("5.1 channel order is Film/ITU (not SMPTE)")
            else:
                concerns['Sound Standard'] = True
                summary.append(f"5.1 channel order is nonstandard: {ch_layout}")
        else:
            # If channel layout is not available, cannot determine mapping
            summary.append("5.1 audio: channel mapping unknown (cannot verify SMPTE vs Film order)")
    return concerns, summary
from pathlib import Path

def get_file_details(file_path):
    details = {}
    try:
        import subprocess
        import json
        # Use ffprobe to get metadata
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-show_entries',
            'format=duration,size,bit_rate',
            '-show_entries',
            'stream=index,codec_type,codec_name,width,height,bit_rate,avg_frame_rate,display_aspect_ratio,pix_fmt,channels,sample_rate,color_space,color_primaries,color_transfer',
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            details['FFPROBE WARNING'] = result.stderr.strip()
            return details
        info = json.loads(result.stdout)
        # Format info
        fmt = info.get('format', {})
        details['Filename'] = file_path.split("\\")[-1]
        details['Size (GB)'] = round(float(fmt.get('size', 0)) / (1024 ** 3), 2) if fmt.get('size') else 'N/A'
        details['Bitrate'] = fmt.get('bit_rate', 'N/A')
        # Duration
        try:
            dur = float(fmt.get('duration', 0))
            h = int(dur // 3600)
            m = int((dur % 3600) // 60)
            s = int(dur % 60)
            details['Runtime'] = f"{h:02}:{m:02}:{s:02}"
        except Exception:
            details['Runtime'] = 'N/A'
        # Streams
        video_stream = None
        audio_stream = None
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video' and video_stream is None:
                video_stream = stream
            if stream.get('codec_type') == 'audio' and audio_stream is None:
                audio_stream = stream
        # Video
        if video_stream:
            details['Resolution'] = f"{video_stream.get('width','N/A')}x{video_stream.get('height','N/A')}"
            details['Format'] = video_stream.get('pix_fmt', 'N/A')
            details['Video Codec'] = video_stream.get('codec_name', 'N/A')
            details['Frame Rate'] = str(eval(video_stream.get('avg_frame_rate','0')) if video_stream.get('avg_frame_rate','0') != '0/0' else 'N/A')
            details['Aspect Ratio'] = video_stream.get('display_aspect_ratio', 'N/A')
            details['Color Space'] = video_stream.get('color_space', 'N/A')
            details['Color Primaries'] = video_stream.get('color_primaries', 'N/A')
            details['Color Transfer'] = video_stream.get('color_transfer', 'N/A')
        else:
            details['Resolution'] = details['Format'] = details['Video Codec'] = details['Frame Rate'] = details['Aspect Ratio'] = details['Color Space'] = details['Color Primaries'] = details['Color Transfer'] = 'N/A'
        # Audio
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
    except Exception as e:
        details['FFPROBE WARNING'] = str(e)
    return details

def generate_report(films, out_path, include_titles=None):
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("# Asset Audit Report\n\n")
        f.write(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
        if not films:
            f.write("No films found.\n")
            return

        # --- Summary Section ---
        # Find films missing main film asset
        missing_main = []
        caution_films = []
        film_cautions = {}
        for film, info in films.items():
            has_film = any(asset_type.lower() == 'film' and files for asset_type, files in info.get('assets', {}).items())
            if not has_film:
                missing_main.append(film)
            cautions = set()
            for asset_type, files in info.get('assets', {}).items():
                if asset_type.lower() in ('film', 'screener'):
                    for fpath in files:
                        details = get_file_details(fpath)
                        _, summary = check_concerns(details)
                        cautions.update(summary)
            if cautions:
                caution_films.append(film)
                film_cautions[film] = sorted(cautions)

        if missing_main:
            f.write("## Films Missing Main Film Asset\n\n")
            for film in missing_main:
                f.write(f"- {film}\n")
            f.write("\n")

        # --- Asset Counts Table ---
        f.write("## Asset Counts Table\n\n")
        f.write("| Film | Stills | Posters | Trailers | Films |\n")
        f.write("|------|--------|---------|----------|-------|\n")
        for film, info in films.items():
            assets = info.get('assets', {})
            stills = len(assets.get('Stills', []))
            posters = len(assets.get('Posters', []))
            trailers = len(assets.get('Trailer', []))
            films_count = len(assets.get('Film', []))
            f.write(f"| {film} | {stills} | {posters} | {trailers} | {films_count} |\n")

        # --- Tech Specs Table ---
        f.write("\n## Main Film File Technical Specs\n\n")
        # Legend for allowed values/ranges
        f.write(
            "**Legend: Allowed/Recommended Values**\n\n"
            "- Resolution: 1920x1080 (1080p)\n"
            "- Aspect Ratio: 16:9, 1.85:1, 2.39:1, 2.40:1, 1.78:1\n"
            "- Format: yuv420p, mov, mp4, mkv\n"
            "- Video Codec: h264\n"
            "- Audio Codec: aac, pcm\n"
            "- Channels: 2.0 (Stereo), 5.1 (Surround)\n"
            "- Sound Standard: SMPTE (for 5.1), Stereo (for 2.0)\n"
            "- Bitrate: 4–20 Mbps\n"
            "- Frame Rate: 23.98–30.00 fps (acceptable: 23.5–60)\n"
            "- Runtime: 1–180 min\n"
            "- Size (GB): 0.7–10 GB\n\n"
        )
        tech_fields = [
            'Resolution', 'Aspect Ratio', 'Format', 'Video Codec', 'Audio Codec', 'Channels', 'Sound Standard', 'Bitrate', 'Frame Rate', 'Runtime', 'Size (GB)'
        ]
        f.write("| Film | " + " | ".join(tech_fields) + " |\n")
        f.write("|------|" + "------|" * len(tech_fields) + "\n")
        for film, info in films.items():
            assets = info.get('assets', {})
            film_files = assets.get('Film', [])
            if film_files:
                fpath = film_files[0]
                details = get_file_details(fpath)
                # Get concerns for this file
                concerns, _ = check_concerns(details)
                # Sound (Channels)
                sound_channels = details.get('Sound', 'N/A')
                # Sound Standard: show detected mapping or layout
                sound_standard = 'N/A'
                ch_layout = details.get('Channel Layout', '').lower()
                sound = details.get('Sound', 'N/A')
                if sound == '5.1':
                    if ch_layout:
                        smpte = ['l', 'r', 'c', 'lfe', 'ls', 'rs']
                        film = ['l', 'c', 'r', 'lfe', 'ls', 'rs']
                        layout = [x.strip() for x in ch_layout.replace('(', '').replace(')', '').replace('/', ' ').replace(',', ' ').split() if x.strip()]
                        if layout[:6] == smpte:
                            sound_standard = 'SMPTE'
                        elif layout[:6] == film:
                            sound_standard = 'Film/ITU'
                        else:
                            sound_standard = ch_layout
                    else:
                        sound_standard = 'Unknown'
                elif sound == '2.0':
                    sound_standard = 'Stereo'
                elif sound != 'N/A':
                    sound_standard = f"{sound}ch"
                else:
                    sound_standard = 'N/A'
                # Bitrate (Mbps, rounded)
                try:
                    br = float(details.get('Bitrate', 0))
                    bitrate = f"{br/1_000_000:.2f}" if br else 'N/A'
                except Exception:
                    bitrate = 'N/A'
                # Frame Rate (rounded)
                try:
                    fr = float(details.get('Frame Rate', 0))
                    frame_rate = f"{fr:.2f}"
                except Exception:
                    frame_rate = details.get('Frame Rate', 'N/A')
                # Size (GB, rounded)
                try:
                    sz = float(details.get('Size (GB)', 0))
                    size_gb = f"{sz:.2f}"
                except Exception:
                    size_gb = details.get('Size (GB)', 'N/A')
                # Aspect Ratio: use explicit, else infer from resolution
                aspect_ratio = details.get('Aspect Ratio', 'N/A')
                if (not aspect_ratio or aspect_ratio == 'N/A') and details.get('Resolution', 'N/A') != 'N/A':
                    try:
                        w, h = [int(x) for x in details['Resolution'].split('x')]
                        def gcd(a, b):
                            while b:
                                a, b = b, a % b
                            return a
                        g = gcd(w, h)
                        aspect_ratio = f"{w//g}:{h//g}"
                    except Exception:
                        aspect_ratio = 'N/A'
                # Add caution emoji to concerning fields
                def caution(val, key):
                    return f"{val} ⚠️" if concerns.get(key) else val
                row = [
                    film,
                    caution(details.get('Resolution', 'N/A'), 'Resolution'),
                    caution(aspect_ratio, 'Aspect Ratio'),
                    caution(details.get('Format', 'N/A'), 'Format'),
                    caution(details.get('Video Codec', 'N/A'), 'Video Codec'),
                    caution(details.get('Audio Codec', 'N/A'), 'Audio Codec'),
                    caution(sound_channels, 'Sound'),
                    caution(sound_standard, 'Sound Standard'),
                    caution(bitrate, 'Bitrate'),
                    caution(frame_rate, 'Frame Rate'),
                    caution(details.get('Runtime', 'N/A'), 'Runtime'),
                    caution(size_gb, 'Size (GB)')
                ]
                f.write("| " + " | ".join(row) + " |\n")
            else:
                row = [film] + ['N/A'] * len(tech_fields)
                f.write("| " + " | ".join(row) + " |\n")


    # --- Collect summary of films missing main film asset or with concerns ---
    summary_missing = []
    summary_caution = []
    film_concerns_map = {}  # film -> list of concerns
    for film, info in films.items():
        film_has_film = any(asset_type.lower() == 'film' and files for asset_type, files in info['assets'].items())
        film_concerns = []
        for asset_type, files in info['assets'].items():
            if asset_type.lower() == 'film' or asset_type.lower() == 'screener':
                for f in files:
                    details = get_file_details(f)
                    _, summary = check_concerns(details)
                    if summary:
                        film_concerns.extend(summary)
        if not film_has_film:
            summary_missing.append(film)
        if film_concerns:
            summary_caution.append(film)
            film_concerns_map[film] = sorted(set(film_concerns))
    import glob

# --- Mail-merge CSV generation ---
def generate_mail_merge_csv(films, csv_path):
    """Write a CSV for mail-merge with columns: Film, Issue, Advice"""
    rows = []
    def check_concerns(details):
        concerns = {}
        summary = []
        allowed_color_spaces = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_primaries = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_transfer = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "iec61966-2-1", "sRGB", "srgb"}
        if details.get("Color Space", "N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A", ""):
            concerns["Color Space"] = True
            summary.append("The color space of your file is unusual. This can sometimes cause playback issues at festivals. If possible, please export using the standard BT.709 color space.")
        if details.get("Color Primaries", "N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A", ""):
            concerns["Color Primaries"] = True
            summary.append("The color primaries in your file are non-standard. For best results, please use BT.709 primaries when exporting.")
        if details.get("Color Transfer", "N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A", ""):
            concerns["Color Transfer"] = True
            summary.append("The color transfer function is non-standard. Please use BT.709 or sRGB for best compatibility.")
        res = details.get("Resolution", "N/A")
        try:
            if res != "N/A":
                w, h = map(int, res.lower().split("x"))
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Your video is above 1080p. For smooth playback at the festival, we recommend exporting a 1080p (1920x1080) version if possible.")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Your video is below 720p. For best projection quality, please provide a 1080p (1920x1080) version if available.")
        except Exception:
            pass
        try:
            br = details.get("Bitrate", "N/A")
            if br != "N/A":
                br_mbps = int(br) / 1_000_000
                if br_mbps > 50:
                    concerns["Bitrate"] = True
                    summary.append("The bitrate of your file is very high. If you experience upload or playback issues, try exporting with a bitrate under 50 Mbps.")
                elif br_mbps < 2:
                    concerns["Bitrate"] = True
                    summary.append("The bitrate of your file is quite low. For best quality, please export with a bitrate above 2 Mbps.")
        except Exception:
            pass
        if details.get("Sound", "N/A") not in ("2.0", "5.1", "N/A"):
            concerns["Sound"] = True
            summary.append("Your audio channels are non-standard. Please provide a stereo (2.0) or surround (5.1) mix if possible.")
        allowed_fps = {"23.98", "23.976", "24.00", "24", "25.00", "25", "29.97", "30.00", "30"}
        fr = details.get("Frame Rate", "N/A")
        if fr not in allowed_fps and fr != "N/A":
            concerns["Frame Rate"] = True
            summary.append(f"Your frame rate is non-standard ({fr}). For best results, please use 23.976, 24, 25, 29.97, or 30 fps.")
        for k, v in details.items():
            if v == "N/A" and k not in ("FFPROBE WARNING",):
                concerns[k] = True
                summary.append(f"Some technical details could not be read from your file. If you exported from a non-standard tool, consider re-exporting from a mainstream editor.")
        try:
            sz = float(details.get("Size (GB)", 0))
            if sz > 10:
                concerns["Size (GB)"] = True
                summary.append("Your file is over 10GB. If you have trouble uploading or transferring, try exporting a version under 10GB.")
        except Exception:
            pass
        rt = details.get("Runtime", "N/A")
        try:
            if rt != "N/A":
                h, m, s = map(int, rt.split(":"))
                total_min = h * 60 + m + s / 60
                if total_min > 180:
                    concerns["Runtime"] = True
                    summary.append("Your film is over 3 hours long. Please confirm with the festival if this is intentional.")
        except Exception:
            pass
        return concerns, summary

    def get_advice(film, info):
        advice = set()
        for asset_type, files in info['assets'].items():
            if asset_type.lower() in ('film', 'screener'):
                if not files:
                    advice.add("We could not find your main film file. Please upload your film to the festival folder or contact us if you need help.")
                for f in files:
                    details = get_file_details(f)
                    concerns, summary = check_concerns(details)
                    for s in summary:
                        advice.add(s)
                    if f.lower().endswith('.zip'):
                        advice.add("We found a ZIP file. Please extract your film and upload the video file directly, or let us know if you need help.")
        return sorted(advice)

    for film, info in films.items():
        advice = get_advice(film, info)
        if advice:
            advice_str = '\n'.join(advice)
            rows.append({'Film': film, 'Issue': '', 'Advice': advice_str})
    if rows:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Film', 'Issue', 'Advice'])
            writer.writeheader()
            writer.writerows(rows)
        log_info(f"Wrote mail-merge CSV to {csv_path}")
    else:
        log_info("No flagged films to write to mail-merge CSV.")

# --- Programmatic API ---
def audit_assets(root_dir, out_path, film_titles=None, csv_path=None, log_level='info'):

    set_log_level(log_level)
    titles = None
    if film_titles:
        titles = film_titles
    elif csv_path:
        import csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            field = next((h for h in reader.fieldnames if 'film' in h.lower() or 'title' in h.lower()), None)
            if field:
                titles = [row[field].strip() for row in reader if row[field].strip()]
    # Always scan all films
    all_films = scan_assets(root_dir)
    # If titles is provided, filter to only those films for reporting
    if titles:
        films = {k: v for k, v in all_films.items() if k in titles}
    else:
        films = all_films
    generate_report(films, out_path, include_titles=titles)
    # Write mail-merge CSV if requested
    if csv_path:
        generate_mail_merge_csv(films, csv_path)
    return films


def load_config():

    CONFIG_FILE = '.film_downloader_config.json'
    import os, json
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# --- Acceptance CSV parsing helper ---
def parse_acceptance_csv(path):
    """Parse an acceptance CSV and return a normalized title-to-row mapping."""
    import csv
    def norm_title(t):
        return ' '.join(t.strip().lower().replace('"','').split())
    result = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = None
            for k in row:
                if 'title' in k.lower():
                    title = norm_title(row[k])
                    break
            if not title:
                continue
            # Email priority
            email = row.get('Email') or row.get('Contact Email') or row.get('Producer Email') or row.get('Director Email') or ''
            email = email.strip()
            # First name
            name = row.get('Name','').strip()
            first_name = name.split()[0] if name else ''
            # Virtual
            v = row.get('Virtual','') or row.get('Virtual Choice','') or row.get('Virtual?','') or ''
            v = v.strip().lower()
            if v.startswith('y'):
                virtual_choice = 'Yes'
            elif v.startswith('n'):
                virtual_choice = 'No'
            else:
                virtual_choice = ''
            result[title] = {'email': email, 'first_name': first_name, 'virtual_choice': virtual_choice}
    return result

# --- Mail merge row builder ---
def build_mail_row(film_name, film_info, analysis, acceptance_map, subject_idx):
    # Subject
    subject = 'HHM tech check and assets for {Film}'
    # Acceptance info
    norm = lambda t: ' '.join(t.strip().lower().replace('"','').split())
    acc = acceptance_map.get(norm(film_name), {}) if acceptance_map else {}
    email = acc.get('email','')
    first_name = acc.get('first_name','')
    virtual_choice = acc.get('virtual_choice','')
    # AssetCheckStatement logic
    # If no main film file
    if not film_info['assets'].get('Film'):
        asset_stmt = 'We do not have the main film file yet. Please send H.264 .mp4 or .mov at 1080p.'
    else:
        # Use analysis (concerns, summary)
        details = analysis.get('Film', [{}])[0] if analysis.get('Film') else {}
        concerns, summary = check_concerns(details)
        # 1080p H.264, AAC 2.0/5.1 compliant
        vcodec = details.get('Video Codec','').lower()
        acodec = details.get('Audio Codec','').lower()
        res = details.get('Resolution','')
        br = details.get('Bitrate','N/A')
        try:
            br_mbps = int(br)/1_000_000 if br and br!='N/A' else 8
        except Exception:
            br_mbps = 8
        compliant = (
            ('h264' in vcodec or 'avc' in vcodec) and
            res in ('1920x1080','1080x1920') and
            ('aac' in acodec) and
            details.get('Sound') in ('2.0','5.1') and
            2 <= br_mbps <= 50
        )
        if compliant:
            asset_stmt = 'Looks good for our venues. No action needed.'
        else:
            # Smallest-change recommendation
            if res not in ('1920x1080','1080x1920'):
                asset_stmt = 'Please share a 1920x1080 H.264 export (.mp4 or .mov).'
            elif any(x in vcodec for x in ['hevc','prores','dnx','vp9','av1']):
                asset_stmt = 'Please send H.264 in .mp4 or .mov with AAC audio.'
            elif details.get('Sound') == '5.1' and details.get('Audio Codec','').lower().startswith('aac'):
                asset_stmt = 'Please include a stereo 2.0 AAC 48 kHz also.'
            elif br_mbps > 50 or br_mbps < 2:
                asset_stmt = 'Please re-export around 8-20 Mbps video for 1080p.'
            else:
                asset_stmt = 'Please confirm your file is playable on a basic Windows or Mac laptop.'
    # VirtualStatement
    if virtual_choice == 'Yes':
        virtual_stmt = 'You indicated you are open to the Virtual Festival. Please confirm any geographic restrictions: none, only allow specific regions (we recommend United States or Michigan), or allow all except specific regions.'
    elif virtual_choice == 'No':
        virtual_stmt = 'You indicated you do not want to participate in the Virtual Festival. If you change your mind, reply and we can try to include it.'
    else:
        virtual_stmt = ''
    return {
        'Email': email,
        'Subject': subject,
        'AssetCheckStatement': asset_stmt,
        'Film': film_name,
        'First Name': first_name,
        'VirtualStatement': virtual_stmt
    }
    CONFIG_FILE = '.film_downloader_config.json'
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Audit sorted film assets and generate a Markdown report and draft emails.")
    parser.add_argument('--root', default=None, help='Root directory containing Features/Shorts')
    parser.add_argument('--out', default=None, help='Output Markdown file')
    parser.add_argument('--log-level', default='info', choices=['debug', 'info', 'none'], help='Set log level')
    parser.add_argument('--include-list', default=None, help='Path to text file with film/short titles to include (one per line)')
    parser.add_argument('--include-csv', default=None, help='Path to CSV file with film/short titles in a column (header must contain "film" or "title")')
    parser.add_argument('--mail-merge', action='store_true', help='If set, write Gmail mail-merge CSV to Audit dir')
    parser.add_argument('--acceptance-csv', default=None, help='Optional: path to acceptance CSV for submitter info')
    args = parser.parse_args()
    config = load_config()
    root = args.root or config.get('root_dir', '.')
    audit_dir = os.path.join(root, 'Audit')
    os.makedirs(audit_dir, exist_ok=True)
    out = args.out or os.path.join(audit_dir, 'asset_audit_report.md')
    set_log_level(args.log_level)

    include_titles = None
    csv_path = None
    if args.include_list:
        with open(args.include_list, 'r', encoding='utf-8') as f:
            include_titles = [line.strip() for line in f if line.strip()]
    elif args.include_csv:
        csv_path = args.include_csv
    # Allow for global variable to be set by another script (e.g., create_drives.py)
    global SELECTED_CSV_PATH
    if not include_titles and not csv_path:
        try:
            if SELECTED_CSV_PATH:
                csv_path = SELECTED_CSV_PATH
        except NameError:
            pass

    emails = None
    mail_merge_rows = []
    import sys
    from utils import choose_csv_file
    acceptance_csv = args.acceptance_csv
    if args.mail_merge and not acceptance_csv:
        print("Mail-merge requires a film submission CSV with filmmaker emails and names.")
        acceptance_csv = choose_csv_file(prompt="Enter path to film submission CSV:")
        if not acceptance_csv or not os.path.exists(acceptance_csv):
            print(f"File not found: {acceptance_csv}")
            sys.exit(1)
    acceptance_map = parse_acceptance_csv(acceptance_csv) if acceptance_csv else {}
    # Always run audit and report
    all_films = scan_assets(root)
    titles = set(include_titles) if include_titles else None
    if titles:
        films = {k: v for k, v in all_films.items() if k in titles}
    else:
        films = all_films
    generate_report(films, out, include_titles=include_titles)
    # If mail-merge, build CSV rows; else, draft emails as before
    if args.mail_merge:
        import csv
        # For each film, analyze and build row
        for idx, (film, info) in enumerate(films.items()):
            # For each asset type, get details for analysis
            analysis = {}
            for asset_type, files in info['assets'].items():
                analysis[asset_type] = [get_file_details(f) for f in files]
            # Gather all recommendations (additive)
            all_advice = set()
            flagged = False
            for asset_type, files in info['assets'].items():
                if asset_type.lower() in ('film', 'screener'):
                    if not files:
                        all_advice.add("We could not find your main film file. Please upload your film to the festival folder or contact us if you need help.")
                        flagged = True
                    for f in files:
                        details = get_file_details(f)
                        _, summary = check_concerns(details)
                        if summary:
                            flagged = True
                        for s in summary:
                            all_advice.add(s)
                        if f.lower().endswith('.zip'):
                            all_advice.add("We found a ZIP file. Please extract your film and upload the video file directly, or let us know if you need help.")
                            flagged = True
            if flagged and all_advice:
                # Compose single row per film, combine all advice
                advice_str = '\n'.join(sorted(all_advice))
                acc = acceptance_map.get(' '.join(film.strip().lower().replace('"','').split()), {})
                email = acc.get('email','')
                first_name = acc.get('first_name','')
                row = {
                    "Email": email,
                    "Film": film,
                    "First Name": first_name,
                    "Advice": advice_str
                }
                mail_merge_rows.append(row)
        out_csv = os.path.join(audit_dir, 'mail_merge_emails.csv')
        with open(out_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["Email","Film","First Name","Advice"], quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for row in mail_merge_rows:
                writer.writerow(row)
        log_info(f"Wrote mail merge CSV to {out_csv}")
    else:
        # Summarize audit results for CLI output
        missing_main = []
        caution_films = []
        for film, info in films.items():
            has_film = any(asset_type.lower() == 'film' and files for asset_type, files in info.get('assets', {}).items())
            if not has_film:
                missing_main.append(film)
            cautions = set()
            for asset_type, files in info.get('assets', {}).items():
                if asset_type.lower() in ('film', 'screener'):
                    for fpath in files:
                        details = get_file_details(fpath)
                        _, summary = check_concerns(details)
                        cautions.update(summary)
            if cautions:
                caution_films.append(film)
        if missing_main or caution_films:
            if missing_main:
                log_info(f"Films missing main film asset: {', '.join(missing_main)}")
            if caution_films:
                log_info(f"Films with technical cautions: {', '.join(caution_films)}")
        else:
            log_info("No missing or oversized assets found.")

if __name__ == "__main__":
    main()
