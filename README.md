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

### Examples

Download all films and trailers:

```bash
python film_downloader.py --csv path/to/file.csv
```

Perform a dry run to preview parsed jobs:

```bash
python film_downloader.py --csv path/to/file.csv --dry-run
```

### Output

- Files are saved in the output directory, organized by film name and asset type.
- A `download_report.csv` is created, detailing the success or failure of each download.

### Notes

- Ensure the CSV file is properly formatted with headers and valid URLs.
- Review the `download_report.csv` for any issues with downloads.