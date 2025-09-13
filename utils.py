# utils.py
# Shared utility functions for hhm-file-downloader

import os
import sys
# utils.py
# Shared utility functions for hhm-file-downloader


import threading

# --- Logging (thread-safe, multi-level) ---
LOG_LEVELS = {"debug": 2, "info": 1, "none": 0}
LOG_LEVEL = 2  # default to debug
log_lock = threading.Lock()

def set_log_level(level):
    global LOG_LEVEL
    LOG_LEVEL = LOG_LEVELS.get(str(level).lower(), 2)

def log_debug(msg):
    if LOG_LEVEL >= 2:
        with log_lock:
            print(f"[DEBUG] {msg}")

def log_info(msg):
    if LOG_LEVEL >= 1:
        with log_lock:
            print(f"[INFO] {msg}")

def log_error(msg):
    with log_lock:
        print(f"[ERROR] {msg}", file=sys.stderr)

# --- File chooser helper ---
def choose_csv_file(prompt="Enter path to CSV file:", file_ext=".csv", prefill=None):
    """
    Interactive file chooser for CSV files. Returns the chosen file path or None.
    """
    import glob
    try:
        import readline
    except ImportError:
        readline = None

    csv_files = [f for f in os.listdir('.') if f.lower().endswith(file_ext)]
    if len(csv_files) == 1:
        csv_file = csv_files[0]
        print(f"Found {file_ext} file in current directory: {csv_file}")
        confirm = input("Is this the correct file? (Y/n): ").strip().lower()
        if confirm in ("", "y", "yes"):
            return csv_file
    elif len(csv_files) > 1:
        print(f"Multiple {file_ext} files found in the current directory:")
        for i, f in enumerate(csv_files, 1):
            print(f"  {i}. {f}")
        choice = input(f"Enter the number of the file to use, or press Enter to specify manually: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(csv_files):
            return csv_files[int(choice) - 1]

    # Enable tab-completion for file path input if possible
    if readline:
        try:
            import platform
            if platform.system() == 'Windows':
                try:
                    import pyreadline3  # noqa: F401
                except ImportError:
                    # pyreadline3 is optional for Windows tab-completion; ignore if not installed
                    pass
            def complete_path(text, state):
                line = readline.get_line_buffer()
                matches = glob.glob(line + '*')
                try:
                    return matches[state]
                except IndexError:
                    return None
            readline.set_completer_delims(' \t\n;')
            readline.set_completer(complete_path)
            readline.parse_and_bind('tab: complete')
        except Exception:
            pass
    while True:
        try:
            user_input = input(prompt + " ").strip()
        except EOFError:
            print("\nInput cancelled.")
            return None
        if not user_input:
            print("You must enter a file path.")
            continue
        if not os.path.exists(user_input):
            print(f"File not found: {user_input}")
            continue
        if not user_input.lower().endswith(file_ext):
            print(f"File does not end with '{file_ext}': {user_input}")
            continue
        return user_input
