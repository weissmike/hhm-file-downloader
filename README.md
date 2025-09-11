# Film & Trailer Bulk Downloader

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

## Asset Organization Workflow

The `organize_assets.py` script uses the same configuration as the downloader to keep your workflow consistent and flexible.

- **Config file:** `.film_downloader_config.json` stores the following keys:
  - `root_dir`: The root directory for all assets (default: `D:/HHM`)
  - `download_dir`: The folder where the downloader puts new files (default: `<root>/downloads`)
  - `unsorted_dir`: A drop zone for any loose or extra files you want to organize (default: `<root>/Unsorted`)

- **How it works:**
  - The script reads these paths from the config file (and adds missing keys if needed).
  - It recursively processes both the `download_dir` and `unsorted_dir`, moving files into the correct `Features` and `Shorts` folders and subfolders by asset type.
  - Aggregate folders (e.g., `_Films`, `_Trailers`, etc.) are rebuilt as symlink collections for easy access.

- **Workflow:**
  1. Drop any new/loose files into your `unsorted_dir` (see config).
  2. Run `film_downloader.py` as usual to fetch new downloads into `download_dir`.
  3. Run `organize_assets.py` to sort everything into the master structure.
  4. All config paths can be changed by editing `.film_downloader_config.json`.

- **Example config:**

```json
{
  "root_dir": "D:/HHM",
  "download_dir": "D:/HHM/downloads",
  "unsorted_dir": "D:/HHM/Unsorted"
}
```

- **Tip:**
  - You can add or change these paths in the config file at any time to match your storage layout.
  - The organizer will always use the latest config values.

---

- Ensure the CSV file is properly formatted with headers and valid URLs.
- Review the `download_report.csv` for any issues with downloads.