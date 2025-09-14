#!/usr/bin/env python3
"""
asset_auditor.py
Audits sorted film assets, generates a Markdown report, and drafts emails for missing or oversized assets.
"""

import os
import sys
import argparse
import json
from pathlib import Path
from utils import set_log_level, log_debug, log_info, log_error

import mimetypes
import subprocess
import shlex
from datetime import datetime

# --- Helper functions ---
def get_file_details(file_path):
    """
    Returns a dict with file size (GB), aspect ratio, resolution, sound, and other details using ffprobe if available.
    """
    details = {}
    # File size
    try:
        stat = os.stat(file_path)
        details['Size (GB)'] = round(stat.st_size / (1024 ** 3), 2)
    except Exception:
        details['Size (GB)'] = 'N/A'

    # ffprobe JSON output
    try:
        # Use a list for subprocess to avoid shell splitting and quoting issues, especially on Windows
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format:stream",
            "-of", "json",
            str(file_path)
        ]
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            import json as _json
            try:
                info = _json.loads(result.stdout)
            except Exception as json_err:
                log_debug(f"ffprobe returned non-JSON output for {file_path}: {result.stdout}")
                details['FFPROBE WARNING'] = 'ffprobe returned non-JSON output. File may be corrupt or ffprobe is misconfigured.'
                raise json_err
            fmt = info.get('format', {})
            # Format
            details['Format'] = fmt.get('format_long_name') or fmt.get('format_name') or 'N/A'
            # Bitrate
            details['Bitrate'] = fmt.get('bit_rate', 'N/A')
            # Duration (seconds as float string)
            duration = fmt.get('duration')
            # Streams: find first video and first audio
            video_stream = None
            audio_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                if stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            # Video details
            if video_stream:
                details['Video Codec'] = video_stream.get('codec_long_name') or video_stream.get('codec_name') or 'N/A'
                w = video_stream.get('width')
                h = video_stream.get('height')
                details['Resolution'] = f"{w}x{h}" if w and h else 'N/A'
                # Aspect ratio: try display_aspect_ratio, else calculate
                aspect = video_stream.get('display_aspect_ratio')
                if not aspect and w and h:
                    try:
                        from fractions import Fraction
                        aspect = str(Fraction(w, h).limit_denominator(100))
                    except Exception:
                        aspect = 'N/A'
                details['Aspect Ratio'] = aspect or 'N/A'
                # Frame rate: try r_frame_rate, else avg_frame_rate
                fr = video_stream.get('r_frame_rate')
                if fr and fr != '0/0':
                    try:
                        num, den = map(int, fr.split('/'))
                        details['Frame Rate'] = f"{num/den:.2f}"
                    except Exception:
                        details['Frame Rate'] = fr
                else:
                    details['Frame Rate'] = video_stream.get('avg_frame_rate', 'N/A')
                details['Video Bitrate'] = video_stream.get('bit_rate', 'N/A')
                details['Color Space'] = video_stream.get('color_space', 'N/A')
                details['Color Primaries'] = video_stream.get('color_primaries', 'N/A')
                details['Color Transfer'] = video_stream.get('color_transfer', 'N/A') or video_stream.get('color_transfer_characteristic', 'N/A')
            else:
                details['Video Codec'] = 'N/A'
                details['Resolution'] = 'N/A'
                details['Aspect Ratio'] = 'N/A'
                details['Frame Rate'] = 'N/A'
                details['Video Bitrate'] = 'N/A'
                details['Color Space'] = 'N/A'
                details['Color Primaries'] = 'N/A'
                details['Color Transfer'] = 'N/A'
            # Audio details
            if audio_stream:
                details['Audio Codec'] = audio_stream.get('codec_long_name') or audio_stream.get('codec_name') or 'N/A'
                ch = audio_stream.get('channels')
                if ch == 6:
                    details['Sound'] = '5.1'
                elif ch == 2:
                    details['Sound'] = '2.0'
                elif ch:
                    details['Sound'] = f"{ch}ch"
                else:
                    details['Sound'] = 'N/A'
                details['Sample Rate'] = audio_stream.get('sample_rate', 'N/A')
                details['Audio Bitrate'] = audio_stream.get('bit_rate', 'N/A')
            else:
                details['Audio Codec'] = 'N/A'
                details['Sound'] = 'N/A'
                details['Sample Rate'] = 'N/A'
                details['Audio Bitrate'] = 'N/A'
            # Duration (again, for runtime)
            if duration:
                try:
                    dur = float(duration)
                    hours = int(dur // 3600)
                    mins = int((dur % 3600) // 60)
                    secs = int(dur % 60)
                    details['Runtime'] = f"{hours}:{mins:02d}:{secs:02d}"
                except Exception:
                    details['Runtime'] = 'N/A'
            else:
                details['Runtime'] = 'N/A'
        else:
            log_debug(f"ffprobe failed for {file_path}: {result.stderr}")
            details['FFPROBE WARNING'] = f'ffprobe failed: {result.stderr.strip() or "Unknown error"}'
            details['Format'] = 'N/A'
            details['Bitrate'] = 'N/A'
            details['Runtime'] = 'N/A'
            details['Video Codec'] = 'N/A'
            details['Resolution'] = 'N/A'
            details['Aspect Ratio'] = 'N/A'
            details['Frame Rate'] = 'N/A'
            details['Video Bitrate'] = 'N/A'
            details['Color Space'] = 'N/A'
            details['Color Primaries'] = 'N/A'
            details['Color Transfer'] = 'N/A'
            details['Audio Codec'] = 'N/A'
            details['Sound'] = 'N/A'
            details['Sample Rate'] = 'N/A'
            details['Audio Bitrate'] = 'N/A'
    except Exception as e:
        log_debug(f"ffprobe exception for {file_path}: {e}")
        details['FFPROBE WARNING'] = f'ffprobe exception: {e}'
        details['Format'] = 'N/A'
        details['Bitrate'] = 'N/A'
        details['Runtime'] = 'N/A'
        details['Video Codec'] = 'N/A'
        details['Resolution'] = 'N/A'
        details['Aspect Ratio'] = 'N/A'
        details['Frame Rate'] = 'N/A'
        details['Video Bitrate'] = 'N/A'
        details['Color Space'] = 'N/A'
        details['Color Primaries'] = 'N/A'
        details['Color Transfer'] = 'N/A'
        details['Audio Codec'] = 'N/A'
        details['Sound'] = 'N/A'
        details['Sample Rate'] = 'N/A'
        details['Audio Bitrate'] = 'N/A'
    return details

def scan_assets(root_dir):
    """
    Scans Features and Shorts directories for films and their assets.
    Returns: { film_name: { 'type': 'feature'|'short', 'assets': {asset_type: [file_paths]}, ... } }
    """
    films = {}
    for typ in ['Features', 'Shorts']:
        base = Path(root_dir) / typ
        if not base.exists():
            continue
        for film_dir in base.iterdir():
            if not film_dir.is_dir():
                continue
            film_name = film_dir.name
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

def generate_report(films, out_path):
    """
    Generates a Markdown report summarizing assets for each film.
    """
    lines = []
    lines.append(f"# Asset Audit Report\n")
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")
    lines.append("> **Note:** This report uses ffprobe/ffmpeg to analyze files. For best results, ensure ffmpeg and ffprobe are installed and available in your PATH. Consider including portable ffmpeg binaries in your project or documenting installation in your README.\n")

    # --- Helper: check for concerns ---
    def check_concerns(details):
        concerns = {}
        summary = []
        # Color
        allowed_color_spaces = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_primaries = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_transfer = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "iec61966-2-1", "sRGB", "srgb"}
        # Color
        if details.get("Color Space", "N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A", ""):
            concerns["Color Space"] = True
            summary.append("Unusual color space")
        if details.get("Color Primaries", "N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A", ""):
            concerns["Color Primaries"] = True
            summary.append("Unusual color primaries")
        if details.get("Color Transfer", "N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A", ""):
            concerns["Color Transfer"] = True
            summary.append("Unusual color transfer")
        # Resolution
        res = details.get("Resolution", "N/A")
        try:
            if res != "N/A":
                w, h = map(int, res.lower().split("x"))
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Video above 1080p")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Video below 720p")
        except Exception:
            pass
        # Bitrate
        try:
            br = details.get("Bitrate", "N/A")
            if br != "N/A":
                br_mbps = int(br) / 1_000_000
                if br_mbps > 50:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate above 50 Mbps")
                elif br_mbps < 2:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate below 2 Mbps")
        except Exception:
            pass
        # Audio
        if details.get("Sound", "N/A") not in ("2.0", "5.1", "N/A"):
            concerns["Sound"] = True
            summary.append("Non-standard audio channels")
        # Frame rate
        allowed_fps = {"23.98", "23.976", "24.00", "24", "25.00", "25", "29.97", "30.00", "30"}
        fr = details.get("Frame Rate", "N/A")
        if fr not in allowed_fps and fr != "N/A":
            concerns["Frame Rate"] = True
            summary.append(f"Non-standard frame rate: {fr}")
        # Missing fields
        for k, v in details.items():
            if v == "N/A" and k not in ("FFPROBE WARNING",):
                concerns[k] = True
                summary.append(f"Missing {k}")
        # File size
        try:
            sz = float(details.get("Size (GB)", 0))
            if sz > 10:
                concerns["Size (GB)"] = True
                summary.append("File over 10GB")
        except Exception:
            pass
        # Runtime
        rt = details.get("Runtime", "N/A")
        try:
            if rt != "N/A":
                h, m, s = map(int, rt.split(":"))
                total_min = h * 60 + m + s / 60
                if total_min > 180:
                    concerns["Runtime"] = True
                    summary.append("Runtime over 3 hours")
        except Exception:
            pass
        return concerns, summary

    # --- High-level summary ---
    # 1. Films missing main film asset
    # 2. Films with warnings (and number of warnings)
    # 3. Table of all films and count of each asset type
    summary_missing = []
    summary_warnings = []
    warnings_count = {}
    asset_types_set = set()
    film_asset_counts = {}
    # Pre-scan for summary
    for film, info in films.items():
        film_has_film = any(asset_type.lower() == 'film' and files for asset_type, files in info['assets'].items())
        if not film_has_film:
            summary_missing.append(film)
        warn_count = 0
        for asset_type, files in info['assets'].items():
            asset_types_set.add(asset_type)
            if asset_type.lower() == 'film' or asset_type.lower() == 'screener':
                for f in files:
                    details = get_file_details(f)
                    _, summary = check_concerns(details)
                    if summary:
                        warn_count += len(summary)
        if warn_count > 0:
            summary_warnings.append(film)
            warnings_count[film] = warn_count
        # Count assets
        film_asset_counts[film] = {atype: len(files) for atype, files in info['assets'].items()}
    # Only include canonical asset types as columns
    canonical_types = ["Film", "Trailer", "Stills", "Posters"]
    asset_types = [t for t in canonical_types if t in asset_types_set]

    # Write a separate summary report
    summary_lines = []
    summary_lines.append(f"# Asset Audit Summary\n")
    summary_lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")
    if summary_missing:
        summary_lines.append("**Films missing main film asset:**  ")
        for film in summary_missing:
            summary_lines.append(f"- {film}")
        summary_lines.append("")
    if summary_warnings:
        summary_lines.append("**Films with warnings:**  ")
        for film in summary_warnings:
            summary_lines.append(f"- {film} ({warnings_count[film]})")
        summary_lines.append("")
    # Table of all films and asset counts
    summary_lines.append("**Asset Counts by Film:**\n")
    header = '| Film | ' + ' | '.join(asset_types) + ' |'
    summary_lines.append(header)
    summary_lines.append('|' + '---|' * (len(asset_types)+1))
    for film in sorted(films.keys()):
        row = [film]
        for atype in asset_types:
            row.append(str(film_asset_counts.get(film, {}).get(atype, 0)))
        summary_lines.append('| ' + ' | '.join(row) + ' |')
    summary_lines.append("\n---\n")
    # Write summary file
    summary_path = out_path.replace('asset_audit_report', 'asset_audit_summary')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary_lines))
    # Continue with verbose report
    lines.append("\n---\n")
    lines.append("## High-Level Summary\n")
    lines.extend(summary_lines[2:])

    # Helper: check for concerns and return (concerns_dict, concern_summary)
    def check_concerns(details):
        concerns = {}
        summary = []
        # Color
        allowed_color_spaces = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_primaries = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_transfer = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "iec61966-2-1", "sRGB", "srgb"}
        # Color
        if details.get("Color Space", "N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A", ""):
            concerns["Color Space"] = True
            summary.append("Unusual color space")
        if details.get("Color Primaries", "N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A", ""):
            concerns["Color Primaries"] = True
            summary.append("Unusual color primaries")
        if details.get("Color Transfer", "N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A", ""):
            concerns["Color Transfer"] = True
            summary.append("Unusual color transfer")
        # Resolution
        res = details.get("Resolution", "N/A")
        try:
            if res != "N/A":
                w, h = map(int, res.lower().split("x"))
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Video above 1080p")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Video below 720p")
        except Exception:
            pass
        # Bitrate
        try:
            br = details.get("Bitrate", "N/A")
            if br != "N/A":
                br_mbps = int(br) / 1_000_000
                if br_mbps > 50:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate above 50 Mbps")
                elif br_mbps < 2:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate below 2 Mbps")
        except Exception:
            pass
        # Audio
        if details.get("Sound", "N/A") not in ("2.0", "5.1", "N/A"):
            concerns["Sound"] = True
            summary.append("Non-standard audio channels")
        # Frame rate
        allowed_fps = {"23.98", "23.976", "24.00", "24", "25.00", "25", "29.97", "30.00", "30"}
        fr = details.get("Frame Rate", "N/A")
        if fr not in allowed_fps and fr != "N/A":
            concerns["Frame Rate"] = True
            summary.append(f"Non-standard frame rate: {fr}")
        # Missing fields
        for k, v in details.items():
            if v == "N/A" and k not in ("FFPROBE WARNING",):
                concerns[k] = True
                summary.append(f"Missing {k}")
        # File size
        try:
            sz = float(details.get("Size (GB)", 0))
            if sz > 10:
                concerns["Size (GB)"] = True
                summary.append("File over 10GB")
        except Exception:
            pass
        # Runtime
        rt = details.get("Runtime", "N/A")
        try:
            if rt != "N/A":
                h, m, s = map(int, rt.split(":"))
                total_min = h * 60 + m + s / 60
                if total_min > 180:
                    concerns["Runtime"] = True
                    summary.append("Runtime over 3 hours")
        except Exception:
            pass
        return concerns, summary

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

    # (Removed '🚩 Films Requiring Attention' section)
    import glob
    # Delete old report files in the audit directory
    audit_dir = os.path.dirname(out_path)
    for old_report in glob.glob(os.path.join(audit_dir, 'asset_audit_report*.md')):
        try:
            os.remove(old_report)
        except Exception:
            pass
    for old_email in glob.glob(os.path.join(audit_dir, 'draft_email_*.txt')):
        try:
            os.remove(old_email)
        except Exception:
            pass

    # Helper: check for concerns and return (concerns_dict, concern_summary)
    def check_concerns(details):
        concerns = {}
        summary = []
        # Color
        allowed_color_spaces = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_primaries = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_transfer = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "iec61966-2-1", "sRGB", "srgb"}
        # Color
        if details.get("Color Space", "N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A", ""):
            concerns["Color Space"] = True
            summary.append("Unusual color space")
        if details.get("Color Primaries", "N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A", ""):
            concerns["Color Primaries"] = True
            summary.append("Unusual color primaries")
        if details.get("Color Transfer", "N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A", ""):
            concerns["Color Transfer"] = True
            summary.append("Unusual color transfer")
        # Resolution
        res = details.get("Resolution", "N/A")
        try:
            if res != "N/A":
                w, h = map(int, res.lower().split("x"))
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Video above 1080p")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Video below 720p")
        except Exception:
            pass
        # Bitrate
        try:
            br = details.get("Bitrate", "N/A")
            if br != "N/A":
                br_mbps = int(br) / 1_000_000
                if br_mbps > 50:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate above 50 Mbps")
                elif br_mbps < 2:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate below 2 Mbps")
        except Exception:
            pass
        # Audio
        if details.get("Sound", "N/A") not in ("2.0", "5.1", "N/A"):
            concerns["Sound"] = True
            summary.append("Non-standard audio channels")
        # Frame rate
        allowed_fps = {"23.98", "23.976", "24.00", "24", "25.00", "25", "29.97", "30.00", "30"}
        fr = details.get("Frame Rate", "N/A")
        if fr not in allowed_fps and fr != "N/A":
            concerns["Frame Rate"] = True
            summary.append(f"Non-standard frame rate: {fr}")
        # Missing fields
        for k, v in details.items():
            if v == "N/A" and k not in ("FFPROBE WARNING",):
                concerns[k] = True
                summary.append(f"Missing {k}")
        # File size
        try:
            sz = float(details.get("Size (GB)", 0))
            if sz > 10:
                concerns["Size (GB)"] = True
                summary.append("File over 10GB")
        except Exception:
            pass
        # Runtime
        rt = details.get("Runtime", "N/A")
        try:
            if rt != "N/A":
                h, m, s = map(int, rt.split(":"))
                total_min = h * 60 + m + s / 60
                if total_min > 180:
                    concerns["Runtime"] = True
                    summary.append("Runtime over 3 hours")
        except Exception:
            pass
        return concerns, summary

    # --- Collect all file details for combined table ---
    combined_details = []  # List of dicts: {Film, Asset Type, Filename, details, concerns, caution_count}
    all_keys = set()
    film_actions_map = {}  # film -> set of actionable recommendations
    for film, info in films.items():
        film_actions = set()
        for asset_type, files in info['assets'].items():
            if asset_type.lower() == 'film' or asset_type.lower() == 'screener':
                for f in files:
                    details = get_file_details(f)
                    concerns, summary = check_concerns(details)
                    caution_count = sum(1 for v in concerns.values() if v)
                    # For combined table
                    combined_details.append({
                        'Film': film,
                        'Asset Type': asset_type,
                        'Filename': os.path.basename(f),
                        'details': details,
                        'concerns': concerns,
                        'caution_count': caution_count
                    })
                    all_keys.update(details.keys())
                    # Actionable recommendations for email
                    if summary:
                        if any(x in summary for x in ["Missing", "N/A", "corrupt", "not found", "Invalid data"]):
                            film_actions.add("- Try re-downloading or request a new render from the filmmaker.")
                        if any(x in summary for x in ["File over 10GB"]):
                            film_actions.add("- Request a re-render under 10GB for easier playback and transfer.")
                        if any(x in summary for x in ["Video above 1080p"]):
                            film_actions.add("- Request a 1080p version for compatibility with basic playback systems.")
                        if any(x in summary for x in ["Bitrate above 50 Mbps"]):
                            film_actions.add("- Request a re-render with bitrate under 50 Mbps.")
                        if any(x in summary for x in ["Bitrate below 2 Mbps"]):
                            film_actions.add("- Request a re-render with bitrate above 2 Mbps.")
                        if any(x in summary for x in ["Non-standard audio channels"]):
                            film_actions.add("- Request a standard 2.0 or 5.1 audio mix.")
                        if any(x in summary for x in ["Non-standard frame rate"]):
                            film_actions.add("- Request a standard frame rate (23.976, 24, 25, 29.97, 30).")
                        if f.lower().endswith('.zip'):
                            film_actions.add("- Extract ZIP file and re-audit extracted contents. If still problematic, request a new render.")
        if film_actions:
            film_actions_map[film] = sorted(film_actions)

    # --- Only output summary sections and combined table ---
    # (Summary already written above)
    # --- Combined Tech Details Table ---
    if combined_details:
        lines.append("\n---\n")
        lines.append("## Combined Tech Details Table\n")
        # Compact legend for columns and caution markers
        # Value legend for common fields
        value_legend = [
            "### Legend",
            "",
            "- **Film Name - Asset Type (Cautions):** Film title and asset type. Number in parentheses = number of cautions for that file.",
            "- **Aspect Ratio:** (A) 1.33 = 4:3, (B) 1.78 = 16:9, (C) 1.85 = US Widescreen, (D) 2.35/2.39 = CinemaScope, (E) 2.00 = Univisium, (F) 2.20 = 70mm.",
            "- **Resolution:** (i) 720p = 1280x720, (ii) 1080p = 1920x1080, (iii) 2160p = 3840x2160, (iv) Other = Non-standard.",
            "- **Frame Rate:** (I) 23.976/24 = Film, (II) 25 = PAL, (III) 29.97/30 = NTSC, (IV) Other = Non-standard.",
            "- **Bitrate:** (A) <2 Mbps = Low, (B) 2-50 Mbps = Standard, (C) >50 Mbps = High.",
            "- **Runtime:** (R) >180 min = Long, (S) <60 min = Short, (N) Normal.",
            "- **Audio Codec:** (A) AAC, (B) PCM, (C) MP3, (D) AC3, (E) DTS, (F) FLAC, (G) Opus, (H) Vorbis, (I) Other. (See table for code mapping.)",
            "- **Video Codec:** (V) H.264/AVC, (W) H.265/HEVC, (X) ProRes, (Y) DNxHD, (Z) VP9, (Q) AV1, (U) MPEG-2, (T) Other. (See table for code mapping.)",
            "- **Format:** Container format as reported by ffprobe (e.g., Matroska, QuickTime, MPEG-4, etc.)",
            "- **⚠️ after a value:** Indicates a caution or concern for that field.",
            "- **N/A:** Data not available.",
            "",
            "_See column headers for additional technical fields (codecs, color, etc.)._",
            ""
        ]
        lines.extend(value_legend)
        # Choose columns: Film Name - Asset Type (number of cautions), Aspect Ratio, Audio Bitrate, and all other tech details
        keys_to_skip = {'Filename'}
        all_keys = sorted(k for k in all_keys if k not in keys_to_skip)
        def key_order(k):
            if k.lower() == 'aspect ratio': return 0
            if k.lower() == 'audio bitrate': return 1
            return 2
        all_keys = sorted(all_keys, key=lambda k: (key_order(k), k.lower()))
        header = ["Film Name - Asset Type (Cautions)"] + all_keys
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        # Codec mapping for legend codes
        def map_video_codec(val):
            v = (val or '').lower()
            if 'h.264' in v or 'avc' in v:
                return 'V'
            if 'h.265' in v or 'hevc' in v:
                return 'W'
            if 'prores' in v:
                return 'X'
            if 'dnxhd' in v or 'dnxhr' in v:
                return 'Y'
            if 'vp9' in v:
                return 'Z'
            if 'av1' in v:
                return 'Q'
            if 'mpeg-2' in v or 'mpeg2' in v:
                return 'U'
            return 'T' if v and v != 'n/a' else 'N/A'

        def map_audio_codec(val):
            a = (val or '').lower()
            if 'aac' in a:
                return 'A'
            if 'pcm' in a:
                return 'B'
            if 'mp3' in a:
                return 'C'
            if 'ac3' in a:
                return 'D'
            if 'dts' in a:
                return 'E'
            if 'flac' in a:
                return 'F'
            if 'opus' in a:
                return 'G'
            if 'vorbis' in a:
                return 'H'
            return 'I' if a and a != 'n/a' else 'N/A'

        for entry in combined_details:
            film = entry['Film']
            asset_type = entry['Asset Type']
            caution_count = entry['caution_count']
            label = f"{film} - {asset_type}"
            if caution_count > 0:
                label += f" ({caution_count}⚠️)"
            row = [label]
            details = entry['details']
            concerns = entry['concerns']
            for k in all_keys:
                v = details.get(k, "N/A")
                mark = ' ⚠️' if concerns.get(k) else ''
                # Map codec fields to legend codes
                if k == 'Video Codec':
                    v = f"{map_video_codec(v)} ({v})" if v != 'N/A' else v
                elif k == 'Audio Codec':
                    v = f"{map_audio_codec(v)} ({v})" if v != 'N/A' else v
                row.append(f"{v}{mark}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    # --- Combined Tech Details Table ---
    if combined_details:
        lines.append("\n---\n")
        lines.append("## Combined Tech Details Table\n")
        # Choose columns: Film Name - Asset Type (number of cautions), Aspect Ratio, Audio Bitrate, and all other tech details
        # Always include: Film, Asset Type, Cautions, Aspect Ratio, Audio Bitrate, plus all other keys (sorted)
        # Remove 'Filename' from details keys, and sort
        keys_to_skip = {'Filename'}
        all_keys = sorted(k for k in all_keys if k not in keys_to_skip)
        # Try to order: Aspect Ratio, Audio Bitrate, then rest
        def key_order(k):
            if k.lower() == 'aspect ratio': return 0
            if k.lower() == 'audio bitrate': return 1
            return 2
        all_keys = sorted(all_keys, key=lambda k: (key_order(k), k.lower()))
        # Table header
        header = ["Film Name - Asset Type (Cautions)"] + all_keys
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for entry in combined_details:
            film = entry['Film']
            asset_type = entry['Asset Type']
            caution_count = entry['caution_count']
            label = f"{film} - {asset_type}"
            if caution_count > 0:
                label += f" ({caution_count}⚠️)"
            row = [label]
            details = entry['details']
            concerns = entry['concerns']
            for k in all_keys:
                v = details.get(k, "N/A")
                mark = ' ⚠️' if concerns.get(k) else ''
                row.append(f"{v}{mark}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    log_info(f"Wrote asset audit report to {out_path}")

def draft_emails(films, deadline="September 23"):  # returns {film: email_text}
    emails = {}
    # Collect actionable recommendations for each film
    # Helper: check for concerns and return (concerns_dict, concern_summary)
    def check_concerns(details):
        concerns = {}
        summary = []
        # Color
        allowed_color_spaces = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_primaries = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "sRGB", "srgb"}
        allowed_transfer = {"bt709", "bt.709", "bt601", "bt.601", "smpte170m", "smpte240m", "iec61966-2-1", "sRGB", "srgb"}
        # Color
        if details.get("Color Space", "N/A").lower() not in allowed_color_spaces and details.get("Color Space") not in ("N/A", ""):
            concerns["Color Space"] = True
            summary.append("Unusual color space")
        if details.get("Color Primaries", "N/A").lower() not in allowed_primaries and details.get("Color Primaries") not in ("N/A", ""):
            concerns["Color Primaries"] = True
            summary.append("Unusual color primaries")
        if details.get("Color Transfer", "N/A").lower() not in allowed_transfer and details.get("Color Transfer") not in ("N/A", ""):
            concerns["Color Transfer"] = True
            summary.append("Unusual color transfer")
        # Resolution
        res = details.get("Resolution", "N/A")
        try:
            if res != "N/A":
                w, h = map(int, res.lower().split("x"))
                if h > 1080:
                    concerns["Resolution"] = True
                    summary.append("Video above 1080p")
                elif h < 720:
                    concerns["Resolution"] = True
                    summary.append("Video below 720p")
        except Exception:
            pass
        # Bitrate
        try:
            br = details.get("Bitrate", "N/A")
            if br != "N/A":
                br_mbps = int(br) / 1_000_000
                if br_mbps > 50:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate above 50 Mbps")
                elif br_mbps < 2:
                    concerns["Bitrate"] = True
                    summary.append("Bitrate below 2 Mbps")
        except Exception:
            pass
        # Audio
        if details.get("Sound", "N/A") not in ("2.0", "5.1", "N/A"):
            concerns["Sound"] = True
            summary.append("Non-standard audio channels")
        # Frame rate
        allowed_fps = {"23.98", "23.976", "24.00", "24", "25.00", "25", "29.97", "30.00", "30"}
        fr = details.get("Frame Rate", "N/A")
        if fr not in allowed_fps and fr != "N/A":
            concerns["Frame Rate"] = True
            summary.append(f"Non-standard frame rate: {fr}")
        # Missing fields
        for k, v in details.items():
            if v == "N/A" and k not in ("FFPROBE WARNING",):
                concerns[k] = True
                summary.append(f"Missing {k}")
        # File size
        try:
            sz = float(details.get("Size (GB)", 0))
            if sz > 10:
                concerns["Size (GB)"] = True
                summary.append("File over 10GB")
        except Exception:
            pass
        # Runtime
        rt = details.get("Runtime", "N/A")
        try:
            if rt != "N/A":
                h, m, s = map(int, rt.split(":"))
                total_min = h * 60 + m + s / 60
                if total_min > 180:
                    concerns["Runtime"] = True
                    summary.append("Runtime over 3 hours")
        except Exception:
            pass
        return concerns, summary

    def get_recommendations(film, info):
        recs = set()
        for asset_type, files in info['assets'].items():
            if asset_type.lower() in ('film', 'screener'):
                for f in files:
                    details = get_file_details(f)
                    concerns, summary = check_concerns(details)
                    if summary:
                        if any(x in summary for x in ["Missing", "N/A", "corrupt", "not found", "Invalid data"]):
                            recs.add("- Try re-downloading or request a new render from the filmmaker.")
                        if any(x in summary for x in ["File over 10GB"]):
                            recs.add("- Request a re-render under 10GB for easier playback and transfer.")
                        if any(x in summary for x in ["Video above 1080p"]):
                            recs.add("- Request a 1080p version for compatibility with basic playback systems.")
                        if any(x in summary for x in ["Bitrate above 50 Mbps"]):
                            recs.add("- Request a re-render with bitrate under 50 Mbps.")
                        if any(x in summary for x in ["Bitrate below 2 Mbps"]):
                            recs.add("- Request a re-render with bitrate above 2 Mbps.")
                        if any(x in summary for x in ["Non-standard audio channels"]):
                            recs.add("- Request a standard 2.0 or 5.1 audio mix.")
                        if any(x in summary for x in ["Non-standard frame rate"]):
                            recs.add("- Request a standard frame rate (23.976, 24, 25, 29.97, 30).")
                        if f.lower().endswith('.zip'):
                            recs.add("- Extract ZIP file and re-audit extracted contents. If still problematic, request a new render.")
        return sorted(recs)

    for film, info in films.items():
        missing = []
        # Check for missing asset types
        for required in ['film', 'screener', 'poster', 'stills']:
            if required not in info['assets'] or not info['assets'][required]:
                missing.append(required)
        # Check for large files and collect runtime
        large_files = []
        for asset_type, files in info['assets'].items():
            if asset_type.lower() in ('film', 'screener'):
                for f in files:
                    details = get_file_details(f)
                    if details.get('size_gb', 0) and details['size_gb'] > 10:
                        large_files.append((f, details['size_gb'], details.get('runtime','?')))
        recommendations = get_recommendations(film, info)
        if missing or large_files or recommendations:
            lines = [f"Subject: Asset Issues for {film}", "", f"Dear Filmmaker,"]
            if missing:
                lines.append(f"\nWe are missing the following assets for your film: {', '.join(missing)}.")
            for f, sz, runtime in large_files:
                lines.append(f"\nYour screener `{os.path.basename(f)}` is {sz} GB (Runtime: {runtime}). We may need to re-render this file for playback. If you can provide a version under 10GB, it will help ensure quality meets your expectations. If we do not hear from you by {deadline}, we will proceed as needed.")
            if recommendations:
                lines.append("\nRecommended Actions:")
                for rec in recommendations:
                    lines.append(f"  {rec}")
            lines.append("\nThank you!\nHHM Tech Team")
            emails[film] = '\n'.join(lines)
    return emails


def load_config():
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
    args = parser.parse_args()
    config = load_config()
    root = args.root or config.get('root_dir', '.')
    audit_dir = os.path.join(root, 'Audit')
    os.makedirs(audit_dir, exist_ok=True)
    out = args.out or os.path.join(audit_dir, 'asset_audit_report.md')
    set_log_level(args.log_level)

    films = scan_assets(root)
    generate_report(films, out)
    emails = draft_emails(films)
    if emails:
        for film, email in emails.items():
            email_path = os.path.join(audit_dir, f"draft_email_{film.replace(' ', '_')}.txt")
            with open(email_path, 'w', encoding='utf-8') as f:
                f.write(email)
            log_info(f"Drafted email for {film}: {email_path}")
    else:
        log_info("No missing or oversized assets found.")

if __name__ == "__main__":
    main()
