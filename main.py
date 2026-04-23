import os
import sys
import subprocess
import argparse
import requests
from PIL import Image
from io import BytesIO
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from concurrent.futures import ThreadPoolExecutor
import re
import pandas as pd
import tempfile
import shutil

SHEET_NAME = "Infos"
DEFAULT_OUTPUT_DIR = "Output"
DEFAULT_MAX_WORKERS = 5
DEFAULT_KEEP_ORIGINAL_METADATA = True
DEFAULT_ENABLE_NORMALIZATION = False

# --- Utilities ---
def str_to_bool(value):
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        "Expected a boolean value: true/false, yes/no, 1/0, on/off."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download playlist tracks from a spreadsheet and apply metadata."
    )
    parser.add_argument(
        "spreadsheet",
        nargs="?",
        help=(
            "Path to the .ods spreadsheet to use. If omitted, the script scans the current "
            "directory for .ods files and asks you to choose one."
        ),
    )
    parser.add_argument(
        "--cookies",
        dest="cookies_file",
        help="Optional path to a cookies file passed to yt-dlp.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=(
            f"Base output directory for downloaded files and covers. "
            f"Default: {DEFAULT_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=(
            "Maximum number of playlists to process in parallel. "
            f"Default: {DEFAULT_MAX_WORKERS}"
        ),
    )
    parser.add_argument(
        "--keep-original-metadata",
        type=str_to_bool,
        default=DEFAULT_KEEP_ORIGINAL_METADATA,
        help=(
            "When spreadsheet Artist/Album/Year/Genre cells are empty, keep existing tags "
            f"in downloaded files instead of clearing them. Default: {DEFAULT_KEEP_ORIGINAL_METADATA}"
        ),
    )
    parser.add_argument(
        "--enable-normalization",
        type=str_to_bool,
        default=DEFAULT_ENABLE_NORMALIZATION,
        help=(
            "Normalize downloaded MP3 files with FFmpeg loudness normalization after tagging. "
            f"Default: {DEFAULT_ENABLE_NORMALIZATION}"
        ),
    )
    return parser.parse_args()


def validate_args(args):
    if args.max_workers < 1:
        print("--max-workers must be at least 1.")
        sys.exit(1)


def list_spreadsheet_files():
    return sorted(
        file for file in os.listdir(".")
        if file.lower().endswith(".ods") and os.path.isfile(file)
    )


def prompt_for_spreadsheet(spreadsheet_files):
    if len(spreadsheet_files) == 1:
        selected = spreadsheet_files[0]
        print(f"Using spreadsheet: {selected}")
        return selected

    print("Available spreadsheet files:")
    for index, file_name in enumerate(spreadsheet_files, start=1):
        print(f"{index}. {file_name}")

    while True:
        choice = input("Choose a spreadsheet by number: ").strip()
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue

        selected_index = int(choice)
        if 1 <= selected_index <= len(spreadsheet_files):
            return spreadsheet_files[selected_index - 1]

        print(f"Please enter a number between 1 and {len(spreadsheet_files)}.")


def resolve_spreadsheet_path(spreadsheet_arg):
    if spreadsheet_arg:
        if not os.path.isfile(spreadsheet_arg):
            print(f"Spreadsheet not found: {spreadsheet_arg}")
            sys.exit(1)
        return spreadsheet_arg

    spreadsheet_files = list_spreadsheet_files()
    if not spreadsheet_files:
        print("No .ods spreadsheet files were found in the current directory.")
        print("Add a spreadsheet file or create one from the documented template format.")
        sys.exit(1)

    return prompt_for_spreadsheet(spreadsheet_files)


def validate_cookies_file(cookies_file):
    if cookies_file and not os.path.isfile(cookies_file):
        print(f"Cookies file not found: {cookies_file}")
        sys.exit(1)


def sanitize_name(name: str | None) -> str:
    if name is None:
        return "Unknown"

    # Convert everything to string first
    name = str(name)

    # First, normalize the string
    cleaned = name.strip()
    
    # Define all possible quote characters we want to remove
    quote_chars = [
        '"',       # regular double quote (U+0022)
        '\uFF02',  # fullwidth double quote (＂, U+FF02)
        "'",       # regular single quote (U+0027)
        '\uFF07'   # fullwidth single quote (＇, U+FF07)
    ]
    
    # Remove quotes from start and end
    while len(cleaned) > 0 and cleaned[0] in quote_chars:
        cleaned = cleaned[1:]
    while len(cleaned) > 0 and cleaned[-1] in quote_chars:
        cleaned = cleaned[:-1]
    
    # Remove any remaining quotes in the middle
    for quote in quote_chars:
        cleaned = cleaned.replace(quote, '')
    
    # Remove numeric prefixes like X., X , X-, X - where X is 1-999
    cleaned = re.sub(r'^\s*(?:\d{1,3}\s*[.-]\s*|\d{1,3}\s+)', '', cleaned)
    
    # Clean up any remaining special characters and whitespace
    cleaned = re.sub(r'[<>:"/\\|?*]+', '', cleaned)
    cleaned = cleaned.strip().rstrip('.')
    
    return cleaned or "Unknown"

# --- Cover handling ---
def download_and_prepare_cover(url_or_path, album, artist, target_dir, cover_dir):
    try:
        if url_or_path.startswith(('http://', 'https://')):
            # Handle URL
            response = requests.get(url_or_path, timeout=15)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGB")
        else:
            # Handle local file path
            if not os.path.isfile(url_or_path):
                print(f"Local cover file not found: {url_or_path}")
                return None
            print("Local cover file found:", url_or_path)
            img = Image.open(url_or_path).convert("RGB")

        safe_album = sanitize_name(album)
        safe_artist = sanitize_name(artist)
        cover_filename = f"{safe_artist}-{safe_album}-cover.jpg"

        # Save in album folder
        album_cover_path = os.path.join(target_dir, cover_filename)
        img.save(album_cover_path, "JPEG")

        # Save in global Covers folder
        global_cover_path = os.path.join(cover_dir, cover_filename)
        img.save(global_cover_path, "JPEG")

        return album_cover_path
    except Exception as e:
        print(f"Failed to process cover: {e}")
        return None

# --- Metadata tagging ---
def apply_metadata(
    file_path,
    artist,
    album,
    year,
    genre,
    tracknum,
    cover_path,
    title,
    keep_original_metadata,
):
    try:
        audio = EasyID3(file_path)
    except Exception:
        audio = EasyID3()

    if artist:
        audio["artist"] = artist
    else:
        if not keep_original_metadata and "artist" in audio:
            del audio["artist"]

    if album:
        audio["album"] = album
    else:
        if not keep_original_metadata and "album" in audio:
            del audio["album"]

    if year:
        audio["date"] = year
    else:
        # Remove any date/year related tags if present only when not keeping originals
        if not keep_original_metadata:
            for k in ("date", "year"):
                if k in audio:
                    del audio[k]

    if genre:
        audio["genre"] = genre
    else:
        if not keep_original_metadata and "genre" in audio:
            del audio["genre"]

    audio["tracknumber"] = str(tracknum)
    audio["title"] = title

    # remove unwanted tags
    for tag in ["albumartist", "discnumber", "comment"]:
        if tag in audio:
            del audio[tag]

    audio.save(file_path)

    # Cover art handling
    # If a custom cover is provided, replace any existing APIC with it.
    # If no custom cover is provided, preserve any existing embedded artwork (e.g., from yt-dlp).
    id3 = ID3(file_path)
    if cover_path and os.path.exists(cover_path):
        id3.delall("APIC")
        with open(cover_path, "rb") as img:
            id3.add(APIC(mime="image/jpeg", type=3, desc=u"Cover", data=img.read()))
        id3.save(file_path)
    else:
        # No custom cover: do not touch APIC frames
        pass

def analyze_loudness(file_path):
    """
    Analyze file loudness using FFmpeg ebur128 filter.
    Returns integrated loudness in LUFS (float) or None if failed.
    """
    cmd = [
        "ffmpeg", "-i", file_path,
        "-filter_complex", "ebur128=framelog=verbose",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"FFmpeg analysis failed for {file_path}: {result.stderr}")
        return None

    # Look for the line starting with 'I:' and ending with 'LUFS'
    match = re.search(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", result.stderr)
    if match:
        return float(match.group(1))

    print(f"Could not parse loudness for {file_path}")
    return None


def normalize_audio(input_path, target_lufs=-15.0, tolerance=3.0):
    """
    Normalize audio if outside target LUFS range, otherwise skip.
    Returns True if successful, False otherwise.
    """
    try:
        loudness = analyze_loudness(input_path)
        if loudness is not None:
            print(f"Loudness for {input_path}: {loudness:.1f} LUFS")
        else:
            print(f"Loudness for {input_path}: unknown, proceeding with normalization")

        # Skip normalization only if loudness is known and within tolerance
        if loudness is not None and abs(loudness - target_lufs) <= tolerance:
            print(f"Skipping normalization for {os.path.basename(input_path)} "
                  f"(already {loudness:.1f} LUFS)")
            return True  # Nothing to do

        # Prepare temporary output path
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, os.path.basename(input_path))

        # Run FFmpeg normalization
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"FFmpeg normalization error for {input_path}: {result.stderr}")
            return False

        shutil.move(output_path, input_path)
        print(f"Normalization completed for {input_path}")
        return True

    except Exception as e:
        print(f"Error normalizing audio {input_path}: {str(e)}")
        return False

# --- Playlist processing ---
def download_playlist(
    url,
    artist,
    album,
    year,
    genre,
    cover_url,
    cookies_file=None,
    output_dir=DEFAULT_OUTPUT_DIR,
    cover_dir=None,
    keep_original_metadata=DEFAULT_KEEP_ORIGINAL_METADATA,
    enable_normalization=False,
):
    if cover_dir is None:
        cover_dir = os.path.join(output_dir, "Covers")

    # Create artist directory if artist is provided
    artist_name = sanitize_name(artist) if artist else "Unknown Artist"
    artist_dir = os.path.join(output_dir, artist_name)
    os.makedirs(artist_dir, exist_ok=True)
    
    # Create album directory inside artist directory with format 'Album - Artist'
    album_name = sanitize_name(album) if album else "Unknown Album"
    folder_name = f"{artist_name} - {album_name}" if artist_name != "Unknown Artist" else album_name
    target_dir = os.path.join(artist_dir, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    cover_path = (
        download_and_prepare_cover(cover_url, album, artist, target_dir, cover_dir)
        if cover_url else None
    )

    # Download playlist
    yt_args = [
        "yt-dlp",
        "--sleep-requests", "0",
        "-x", "--audio-format", "mp3",
    ]
    if cookies_file:
        yt_args += ["--cookies", cookies_file]
    # If no custom cover provided, embed original thumbnail and convert to JPG for MP3 compatibility
    if not cover_url:
        yt_args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    yt_args += [
        "--output", f"{target_dir}/%(playlist_index)03d - %(title)s.%(ext)s",
        url
    ]
    download_result = subprocess.run(yt_args)

    files_to_process = []
    for file in sorted(os.listdir(target_dir)):
        if file.endswith('.mp3'):
            file_path = os.path.join(target_dir, file)
            # Apply metadata first
            track_num = file.split(' - ')[0]
            title = ' - '.join(file.split(' - ')[1:]).replace('.mp3', '')
            apply_metadata(
                file_path,
                artist,
                album,
                year,
                genre,
                track_num,
                cover_path,
                title,
                keep_original_metadata,
            )
            files_to_process.append((file_path, title))

    if enable_normalization:
        print(f"\nNormalizing audio files for Album: {album or 'unknown album'} - {artist or 'unknown artist'}")
        for file_path, _ in files_to_process:
            normalize_audio(file_path)

    # Rename after normalization
    for file in sorted(os.listdir(target_dir)):
        if file.endswith('.mp3'):
            old_path = os.path.join(target_dir, file)
            title = os.path.splitext(file)[0].split(' - ', 1)[-1]
            new_path = os.path.join(target_dir, f"{title}.mp3")
            if os.path.normcase(os.path.abspath(old_path)) != os.path.normcase(os.path.abspath(new_path)):
                os.replace(old_path, new_path)
                print(f"Renamed: {file} -> {os.path.basename(new_path)}")

    if download_result.returncode != 0:
        if files_to_process:
            print(
                f"yt-dlp returned exit code {download_result.returncode} for playlist {url}, "
                "but downloaded files were still processed."
            )
        else:
            raise subprocess.CalledProcessError(download_result.returncode, yt_args)

# --- Main ---
def main():
    args = parse_args()
    validate_args(args)
    spreadsheet_path = resolve_spreadsheet_path(args.spreadsheet)
    validate_cookies_file(args.cookies_file)
    output_dir = args.output_dir
    cover_dir = os.path.join(output_dir, "Covers")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cover_dir, exist_ok=True)

    # Read the spreadsheet, headers are in the first row
    try:
        df = pd.read_excel(spreadsheet_path, engine="odf", sheet_name=SHEET_NAME, usecols=range(6))
        # Ensure column names are correct
        df.columns = ['URL', 'Artist', 'Album', 'Year', 'Genre', 'Cover_URL']
    except ValueError as e:
        print(f"Failed to read sheet '{SHEET_NAME}' from {spreadsheet_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to read {spreadsheet_path}: {e}")
        sys.exit(1)

    tasks = []
    for _, row in df.iterrows():
        # Convert all values to string and strip whitespace
        url = str(row['URL']).strip() if not pd.isna(row['URL']) else None
        artist = str(row['Artist']).strip() if not pd.isna(row['Artist']) else ""
        album = str(row['Album']).strip() if not pd.isna(row['Album']) else ""
        year = str(int(row['Year'])) if not pd.isna(row['Year']) else ""
        genre = str(row['Genre']).strip() if not pd.isna(row['Genre']) else ""
        cover = str(row['Cover_URL']).strip() if not pd.isna(row['Cover_URL']) else ""

        if url:
            tasks.append((url, artist, album, year, genre, cover))

    if not tasks:
        print("No playlists found in the spreadsheet.")
        sys.exit(0)

    # Use existing ThreadPoolExecutor for downloads
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(
                download_playlist,
                *task,
                args.cookies_file,
                output_dir,
                cover_dir,
                args.keep_original_metadata,
                args.enable_normalization,
            )
            for task in tasks
        ]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"Error in playlist task: {e}")

if __name__ == "__main__":
    main()
