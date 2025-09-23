
# HHM Film Festival Asset Management Toolkit

This toolkit streamlines the process of downloading, organizing, auditing, and preparing film assets for the festival. It is designed for repeatable, robust workflows and supports both features and shorts blocks.

---

## Overview & Step-by-Step Example

**Typical Workflow:**

1. **Download new assets:**
   - Run `film_downloader.py` to fetch new files into your downloads folder.
2. **Organize everything:**
   - Run `organize_assets.py` to sort all files into the master structure.
3. **Audit your collection:**
   - Run `asset_auditor.py` to check for missing or problematic files.
4. **Create drive folders:**
   - Run `create_drives.py` to build the folder structure for each showing.
5. **(Optional) Generate QCPX files:**
   - Run `create_qcpx.py` to create QuickCinema XML playlists for playback.

**Repeat steps 1–4 as needed** until all assets are downloaded, sorted, and ready. All scripts are safe to re-run—they will skip or stub files as appropriate.

---

## Key CSV Files

### 1. Festival Schedule CSV
Defines the full festival schedule, including venues, showtimes, and block names (feature films or shorts blocks).
  - **First Row:** [Venue], [Venue], [Venue]...
  - **Columns:** [Day], [Time], [Block Name] (repeats for each venue) ...
  - **Usage:** Used by scripts to determine which blocks/films to prepare for each venue and time slot.

### 2. Shorts Blocks CSV
Lists all shorts blocks and the ordered list of shorts in each block.
  - **Columns:** [Block Name 1], [Block Name 2], ...
  - **Usage:** Used to organize shorts into their correct block folders and ensure block names match the schedule.

### 3. Film Submissions CSV
Contains all film submission data, including contact info, download links, and asset details.
  - **Columns:** [Film Name], [Contact Info], [Download Links], [Stills], [Poster], [Runtime], etc.
  - **Usage:** Used by the downloader and asset auditor scripts to collect file information and generate mail-merge outputs.

> **Note:** Block names must match exactly between the Festival Schedule and Shorts Blocks CSVs for correct matching. See the sample CSVs in this repo for reference.

---

## Configuration: `config.json`

All scripts use a shared `config.json` file for paths and settings. Example:

```json
{
  "root_dir": "D:/HHM",
  "download_dir": "D:/HHM/downloads",
  "unsorted_dir": "D:/HHM/Unsorted",
  "TRAILERS_DIR": "_Trailers",
  "PROMOS_DIR": "_Promos",
  "BUMPER_DIR": "_Bumpers",
  "SPONSORS_DIR": "_Sponsors",
  "GAP_FILE": "3sec.mov",
  "STEP_REPEAT_FILE": "StepAndRepeat.png",
  "FILMS_DIR": "_Films",
  "dir_match_threshold": 0.5,
  "file_match_threshold": 0.4
}
```

You can edit this file to match your storage layout. The organizer and all scripts will use the latest config values.

---

# Script Details

## film_downloader.py


**Purpose:**
- Downloads films, trailers, posters, and stills in bulk from a CSV file of links.
- Organizes downloads by film name and asset type (Film, Posters, Stills, Trailer).
- Skips files that are already downloaded or stubbed, and resumes partial downloads.
- Generates a `download_report.csv` summarizing all download attempts.

**How to use:**
1. Prepare your CSV file with the required links.
2. Open Command Prompt/Terminal in the script folder.
3. Run:
   ```
   python film_downloader.py
   ```
   - The script will prompt you to select your CSV file, or you can use `--csv path/to/file.csv`.
   - Downloads will be saved in the `download_dir` (see config).

**Features:**
- Handles Google Drive, Dropbox, Vimeo, YouTube, direct links, and more.
- Automatically resumes interrupted downloads and skips files that already exist or are stubbed.
- Organizes files into subfolders by film and asset type.
- Supports cookies for authenticated downloads (see below).
- Allows optional CSV inputs for submissions, festival schedules, and shorts blocks.
- Comprehensive logging and error handling.


---

## organize_assets.py


**Purpose:**
- Sorts and organizes downloaded and unsorted files into a master folder structure for easy access.
- Uses the same config as the downloader for consistent paths.
- Moves files into `Features` and `Shorts` folders, with subfolders for each asset type (Film, Trailer, Stills, Posters).
- Rebuilds aggregate folders (symlinks/shortcuts) for quick browsing.
- Adds trailer identification logic to streamline asset organization.

**How to use:**
1. Place any loose or extra files in your `unsorted_dir` (see config).
2. Run:
   ```
   python organize_assets.py
   ```
   - The script will read your config and organize everything into the correct structure.
   - No files are deleted—everything is moved or stubbed for safety.

**Features:**
- Fuzzy-matches film names and asset types for robust sorting.
- Logs all actions for transparency.
- Uses filename sanitization for Windows compatibility.



---

## asset_auditor.py


**Purpose:**
- Audits your organized asset folders to find missing, oversized, or misplaced files.
- Generates a Markdown report and a mail-merge CSV for filmmaker follow-up.

**How to use:**
1. After organizing assets, run:
   ```
   python asset_auditor.py --root D:/HHM --out D:/HHM/Audit/asset_audit_report.md --mail-merge
   ```
   - The script will scan your folders and produce a report in Markdown format.
   - It will also generate a mail-merge CSV (`mail_merge_emails.csv`) in the `Audit` folder with friendly advice for each filmmaker if any issues are found.

**Features:**
- Checks for missing, stubbed, or oversized files.
- Summarizes issues in a human-readable report.
- Generates a mail-merge CSV for personalized filmmaker outreach.
- Uses ffprobe/ffmpeg for technical details (see below for install instructions).

### Mail-Merge CSV Columns

- `Film`: The title of the film or short.
- `Issue`: (reserved for future use, currently blank)
- `Advice`: Friendly, filmmaker-facing advice or suggestions for improving asset quality or compatibility.

### Sample Mail-Merge Email

You can use the following template for your mail-merge:

```
Subject: Quick Check: Your Festival Film Submission

Dear Filmmaker,

Thank you for submitting your film, {{Film}}, to the festival! As part of our technical review, we noticed the following:

{{Advice}}

These suggestions are just to help ensure your film looks and sounds its best on the big screen. If you have any questions or need help with re-exporting or uploading, please let us know.

If you'd like to resubmit your film assets, you may do so using this link: 

Thank you!
Festival Tech Team
```

You can use your favorite mail-merge tool (e.g., Google Sheets, Outlook, Mailchimp) to send personalized emails using the CSV generated by this script.


---

## create_drives.py


**Purpose:**
- Interactively builds a drive/folder structure for each festival showing, copying only the needed film assets for each block or feature.
- For shorts blocks, copies the entire numbered subfolders (created by `organize_assets.py`) directly from `Shorts` to the output, preserving numbering and order.
- For features or other films, copies the main film file as usual.
- Supports dry-run mode to preview what would be created/copied.
- Handles CSV file selection and drive existence checks.

**How to use:**
1. Run:
  ```
  python create_drives.py --output-root D:/Path/To/DriveRoot
  ```
  - Optionally add `--dry-run` to preview the folder/file tree without copying.
  - You can also set `--assets-root` if your assets are not in the default location (from config).
2. When prompted, paste a tab-delimited list of showings (one per line):
  - Format: `Day<TAB>Time<TAB>Block or Film Name`
  - Example:
    ```
    Friday	7:00 PM	Shorts 1
    Friday	9:00 PM	Feature Film Title
    Saturday	2:00 PM	Shorts 2
    Saturday	4:00 PM	Another Feature
    ```
  - End input with an empty line.
---

## create_qcpx.py

**Purpose:**
- Generates QuickCinema QCPX XML playlist files for playback, based on festival CSVs and config.
- Ensures all referenced files exist in the drive/block folder.

**How to use:**
1. Run:
  ```
  python create_qcpx.py --festival-schedule path/to/schedule.csv --shorts-blocks path/to/shorts.csv --submissions path/to/submissions.csv --block-path path/to/block/folder --block-name "Block Name"
  ```
  - Optionally set `--output` to specify the QCPX file path (default: `<block-path>/<block-name>.qcpx`).
  - The script will look up films for the block, find their files, and generate the QCPX XML.

**Features:**
- Uses config for root and asset directories.
- Finds films for the block (feature or shorts block) and adds them in order.
- Optionally includes trailers, promos, sponsors, bumpers, and step-and-repeat graphics if present in config.
- Sanitizes filenames for Windows compatibility.
- Logs warnings if any film file is missing.

---

**Notes:**
- For shorts blocks, the script will copy each numbered subfolder (e.g., `Shorts 1/01_FilmName`, `Shorts 1/02_FilmName`, etc.) into the output, preserving the order and folder names.
- For features, the script will copy the main film file into the appropriate folder.
- If a shorts block or film is missing, you will see an error message in the log.
- If a destination folder already exists, it will be skipped (not overwritten).

**Troubleshooting:**
- If you see `[ERROR] Shorts block folder not found`, check that the block name matches exactly (including spaces/case) with the folder in `Shorts`.
- If you see `[ERROR] No film file found` or `FileNotFoundError`, check that the film file exists in the expected location.
- If you see a traceback with `shutil.copy2`, it means the source file was not found—double-check your asset folders and names.
- Use `--dry-run` to preview the folder/file tree before actually copying files.

---


# Quick Start: Setting Up Python

If you have never used Python before, follow these steps to get started:

1. **Install Python 3.8 or higher:**
   - Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version for your operating system (Windows or macOS).
   - Run the installer. **On Windows, make sure to check the box that says "Add Python to PATH" before clicking Install.**
   - After installation, open a new Command Prompt (Windows) or Terminal (macOS) and type:
     ```
     python --version
     ```
     You should see something like `Python 3.10.0` or higher.

2. **Download the scripts:**
   - Place all the `.py` files and your CSV files in the same folder.

3. **First Run:**
   - Open a Command Prompt or Terminal in that folder.
   - Run the script you want (see above). The script will automatically install any missing Python packages the first time you run it. You may see some installation messages—this is normal.

---

---

# Additional Notes

## Purpose

This script is designed to streamline the process of downloading films and trailers in bulk. Using a festival acceptance CSV file, it:

1. Prompts for the CSV file path (or accepts it via the `--csv` argument).
2. Extracts download URLs for films, trailers, and optionally other media assets.
3. Downloads the files into a structured directory.
4. Generates a `download_report.csv` summarizing the download results.

## Platforms

- **Supported OS**: macOS & Windows
- **Python Version**: 3.8 or higher
- **Dependencies**: Automatically installed by the script (no pre-installed packages required).

## Supported Links

- **Google Drive**: Handles various link formats (e.g., `open?id=`, `file/d/<id>/view`, `uc?id=...`).
- **Dropbox**: Converts links to direct downloads (`?dl=1`).
- **Streaming Platforms**: Supports Vimeo, YouTube, and others via `yt-dlp`.
- **Direct Links**: Downloads files from HTTP/HTTPS URLs.
- **Other Platforms**: Attempts downloads from Box.com, WeTransfer, etc., with varying success.

## Limitations

- **Restricted Links**: Password-protected or permission-restricted URLs require manual intervention.
- **Expiring Links**: Tokenized links (e.g., WeTransfer) may fail if expired.
- **JavaScript-Dependent Platforms**: Some platforms requiring JavaScript or APIs may not work.

## Usage

### Interactive Mode

Run the script without arguments to be prompted for the CSV file path:

```bash
python film_downloader.py
```

### Command-Line Options

Customize the script's behavior using the following options:

- `--csv <path>`: Path to the CSV file.
- `--out <path>`: Output directory (default: `downloads`).
- `--include-stills`: Include still image URLs.
- `--include-poster`: Include poster URLs.
- `--include-all-http`: Include all HTTP(S) URLs.
- `--films-only`: Download only film assets (skip trailers).
- `--max-workers <int>`: Set the number of concurrent downloads (default: 4).
- `--retry <int>`: Retry count for failed downloads (default: 1).
- `--no-color`: Disable colored output.
- `--dry-run`: Parse the CSV without downloading.

### Additional Options

- `--log-level <debug|none>`: Control output verbosity. `debug` (default) shows detailed logs and progress bars; `none` suppresses logs and progress bars except for final summary.

### Examples

Download all films and trailers:

```bash
python film_downloader.py --csv path/to/file.csv
```

Perform a dry run to preview parsed jobs:

```bash
python film_downloader.py --csv path/to/file.csv --dry-run
```

### Output & Logging

- Files are saved in the output directory, organized by film name and asset type.
- A `download_report.csv` is created, detailing the success or failure of each download.
- Progress bars are only shown for files actively being downloaded (not for skipped or already completed files).
- If `--log-level none` is set, all logs and progress bars are suppressed except for the final summary.
- To save all output to a file, run:

  ```powershell
  python film_downloader.py ...args... *> out.log 2>&1
  ```

- `out.log` and `cookies.txt` are excluded from source control via `.gitignore`.

### Vimeo & Authenticated Downloads: Using a Cookies File

Some Vimeo links require you to be logged in to download. To allow yt-dlp to access these, you can export your browser cookies and pass them to the script:

1. **Install the "Get cookies.txt" browser extension:**
	- [Chrome/Edge/Brave/Opera](https://chrome.google.com/webstore/detail/get-cookiestxt/)
	- [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. **Log in to Vimeo in your browser.**

3. **Click the extension icon and export cookies for `vimeo.com` as `cookies.txt`.**

4. **Pass the cookies file to the script:**

	```bash
	python film_downloader.py --csv path/to/file.csv --cookies path/to/cookies.txt
	```

For more details, see the [yt-dlp cookies guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).


## ffprobe/ffmpeg Requirement for Asset Auditing

To extract technical details (runtime, codecs, resolution, etc.) for video files, the `asset_auditor.py` script requires `ffprobe` (part of the free [ffmpeg](https://ffmpeg.org/) toolkit).

**If you see only `N/A` for all fields except file size in your audit report, you need to install ffprobe.**

## Windows: Step-by-Step ffprobe Installation

1. **Download ffmpeg static build:**
   - Go to the official [ffmpeg download page](https://ffmpeg.org/download.html).
   - Under "Get packages & executable files", click the link for Windows builds (e.g., "Windows builds by Gyan").
   - On the Gyan.dev page, under "Release builds", click the link for the latest "ffmpeg-release-essentials.zip".

2. **Extract the ZIP file:**
   - Right-click the downloaded ZIP and choose "Extract All...".
   - Open the extracted folder. Inside, you'll find a `bin` folder containing `ffprobe.exe` and `ffmpeg.exe`.

3. **Add ffmpeg/bin to your PATH:**
   - Copy the full path to the `bin` folder (e.g., `C:\Users\yourname\Downloads\ffmpeg-release-essentials\bin`).
   - Press `Win + X` and select **System** > **Advanced system settings** > **Environment Variables**.
   - Under **System variables**, select `Path` and click **Edit**.
   - Click **New** and paste the path to your `bin` folder.
   - Click **OK** to save and close all dialogs.

4. **Verify installation:**
   - Open a new Command Prompt (important: must be a new window).
   - Type:
     ```
     ffprobe -version
     ```
   - If you see version info, ffprobe is installed and ready to use.
   - If you see "not recognized", double-check that you added the correct `bin` path and opened a new terminal.

## macOS/Linux
- Install via Homebrew: `brew install ffmpeg`
- Or use your package manager: `sudo apt install ffmpeg` (Linux)

After installing, re-run `asset_auditor.py` to get full technical details in your Markdown report.

---

- Ensure the CSV file is properly formatted with headers and valid URLs.
- Review the `download_report.csv` for any issues with downloads.