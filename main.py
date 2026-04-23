import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import requests
from PIL import Image
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3

DEFAULT_PLAYLISTS_FILE = "playlists.toml"
DEFAULT_CONFIG_FILE = "config.toml"
DEFAULT_OUTPUT_DIR = "Output"
DEFAULT_MAX_WORKERS = 5
DEFAULT_KEEP_ORIGINAL_METADATA = True
DEFAULT_ENABLE_NORMALIZATION = False


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
        description="Download playlist tracks from a TOML file and apply metadata."
    )
    parser.add_argument(
        "playlists_file",
        nargs="?",
        help=(
            "Path to the playlists TOML file. If omitted, the script uses "
            f"{DEFAULT_PLAYLISTS_FILE} in the current directory."
        ),
    )
    parser.add_argument(
        "--config",
        dest="config_file",
        help=(
            "Optional path to a config TOML file. If omitted, the script uses "
            f"{DEFAULT_CONFIG_FILE} when present."
        ),
    )
    parser.add_argument(
        "--cookies",
        dest="cookies_file",
        default=None,
        help="Optional path to a cookies file passed to yt-dlp.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Base output directory for downloaded files and covers. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help=f"Maximum number of playlists to process in parallel. Default: {DEFAULT_MAX_WORKERS}",
    )
    parser.add_argument(
        "--keep-original-metadata",
        type=str_to_bool,
        default=None,
        help=(
            "When artist/album/year/genre values are missing in the playlist entry, keep existing "
            f"tags in downloaded files instead of clearing them. Default: {DEFAULT_KEEP_ORIGINAL_METADATA}"
        ),
    )
    parser.add_argument(
        "--enable-normalization",
        type=str_to_bool,
        default=None,
        help=(
            "Normalize downloaded MP3 files with FFmpeg loudness normalization after tagging. "
            f"Default: {DEFAULT_ENABLE_NORMALIZATION}"
        ),
    )
    return parser.parse_args()


def load_toml_file(path, label):
    try:
        with open(path, "rb") as toml_file:
            return tomllib.load(toml_file)
    except FileNotFoundError:
        print(f"{label} not found: {path}")
        sys.exit(1)
    except tomllib.TOMLDecodeError as exc:
        print(f"Failed to parse {label} {path}: {exc}")
        sys.exit(1)


def resolve_playlists_file(playlists_arg):
    playlists_file = playlists_arg or DEFAULT_PLAYLISTS_FILE
    if not os.path.isfile(playlists_file):
        print(f"Playlists file not found: {playlists_file}")
        print("Create a playlists.toml file or pass a custom file path.")
        sys.exit(1)
    return playlists_file


def resolve_config_path(config_arg):
    if config_arg:
        if not os.path.isfile(config_arg):
            print(f"Config file not found: {config_arg}")
            sys.exit(1)
        return config_arg

    if os.path.isfile(DEFAULT_CONFIG_FILE):
        return DEFAULT_CONFIG_FILE

    return None


def load_config(config_path):
    if not config_path:
        return {}
    return load_toml_file(config_path, "Config file")


def build_runtime_settings(args, config_data):
    config_settings = config_data.get("settings", {})
    if config_settings and not isinstance(config_settings, dict):
        print("Config file error: [settings] must be a table.")
        sys.exit(1)

    settings = {
        "output_dir": DEFAULT_OUTPUT_DIR,
        "max_workers": DEFAULT_MAX_WORKERS,
        "keep_original_metadata": DEFAULT_KEEP_ORIGINAL_METADATA,
        "enable_normalization": DEFAULT_ENABLE_NORMALIZATION,
        "cookies_file": None,
    }

    for key in settings:
        if key in config_settings:
            settings[key] = config_settings[key]

    if args.output_dir is not None:
        settings["output_dir"] = args.output_dir
    if args.max_workers is not None:
        settings["max_workers"] = args.max_workers
    if args.keep_original_metadata is not None:
        settings["keep_original_metadata"] = args.keep_original_metadata
    if args.enable_normalization is not None:
        settings["enable_normalization"] = args.enable_normalization
    if args.cookies_file is not None:
        settings["cookies_file"] = args.cookies_file

    validate_runtime_settings(settings)
    return settings


def validate_runtime_settings(settings):
    if not isinstance(settings["output_dir"], str) or not settings["output_dir"].strip():
        print("output_dir must be a non-empty string.")
        sys.exit(1)

    if not isinstance(settings["max_workers"], int) or settings["max_workers"] < 1:
        print("max_workers must be an integer greater than or equal to 1.")
        sys.exit(1)

    for key in ("keep_original_metadata", "enable_normalization"):
        if not isinstance(settings[key], bool):
            print(f"{key} must be a boolean value.")
            sys.exit(1)

    cookies_file = settings["cookies_file"]
    if cookies_file is not None:
        if not isinstance(cookies_file, str) or not cookies_file.strip():
            print("cookies_file must be a non-empty string when provided.")
            sys.exit(1)
        if not os.path.isfile(cookies_file):
            print(f"Cookies file not found: {cookies_file}")
            sys.exit(1)


def load_playlist_entries(playlists_file):
    playlists_data = load_toml_file(playlists_file, "Playlists file")
    playlists = playlists_data.get("playlists")

    if playlists is None:
        print(f"Playlists file error: {playlists_file} must define at least one [[playlists]] entry.")
        sys.exit(1)

    if not isinstance(playlists, list):
        print("Playlists file error: playlists must be an array of tables.")
        sys.exit(1)

    tasks = []
    for index, playlist in enumerate(playlists, start=1):
        if not isinstance(playlist, dict):
            print(f"Playlists file error: entry #{index} must be a table.")
            sys.exit(1)

        url = require_string_field(playlist, "url", index)
        artist = optional_string_field(playlist, "artist")
        album = optional_string_field(playlist, "album")
        year = optional_year_field(playlist, index)
        genre = optional_string_field(playlist, "genre")
        cover_url = optional_string_field(playlist, "cover_url")

        tasks.append((url, artist, album, year, genre, cover_url))

    if not tasks:
        print("No playlists found in the playlists file.")
        sys.exit(0)

    return tasks


def require_string_field(entry, field_name, index):
    value = entry.get(field_name)
    if not isinstance(value, str) or not value.strip():
        print(f"Playlists file error: entry #{index} requires a non-empty '{field_name}' value.")
        sys.exit(1)
    return value.strip()


def optional_string_field(entry, field_name):
    value = entry.get(field_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        print(f"Playlists file error: '{field_name}' must be a string when provided.")
        sys.exit(1)
    return value.strip()


def optional_year_field(entry, index):
    value = entry.get("year")
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    print(f"Playlists file error: entry #{index} field 'year' must be an integer or non-empty string.")
    sys.exit(1)


def sanitize_name(name: str | None) -> str:
    if name is None:
        return "Unknown"

    name = str(name)
    cleaned = name.strip()

    quote_chars = ['"', "\uFF02", "'", "\uFF07"]

    while len(cleaned) > 0 and cleaned[0] in quote_chars:
        cleaned = cleaned[1:]
    while len(cleaned) > 0 and cleaned[-1] in quote_chars:
        cleaned = cleaned[:-1]

    for quote in quote_chars:
        cleaned = cleaned.replace(quote, "")

    cleaned = re.sub(r"^\s*(?:\d{1,3}\s*[.-]\s*|\d{1,3}\s+)", "", cleaned)
    cleaned = re.sub(r'[<>:"/\\|?*]+', "", cleaned)
    cleaned = cleaned.strip().rstrip(".")

    return cleaned or "Unknown"


def normalize_track_title(title, album, artist):
    normalized_title = str(title).strip()

    if artist and album:
        prefix_pattern = re.compile(
            rf"^\s*{re.escape(artist.strip())}\s*-\s*{re.escape(album.strip())}\s*-\s*",
            re.IGNORECASE,
        )
        normalized_title = prefix_pattern.sub("", normalized_title, count=1).strip()

    return normalized_title or "Unknown"


def build_final_track_filename(title, album, artist):
    return f"{sanitize_name(normalize_track_title(title, album, artist))}.mp3"


def download_and_prepare_cover(url_or_path, album, artist, target_dir, cover_dir):
    try:
        if url_or_path.startswith(("http://", "https://")):
            response = requests.get(url_or_path, timeout=15)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGB")
        else:
            if not os.path.isfile(url_or_path):
                print(f"Local cover file not found: {url_or_path}")
                return None
            print("Local cover file found:", url_or_path)
            img = Image.open(url_or_path).convert("RGB")

        safe_album = sanitize_name(album)
        safe_artist = sanitize_name(artist)
        cover_filename = f"{safe_artist}-{safe_album}-cover.jpg"

        album_cover_path = os.path.join(target_dir, cover_filename)
        img.save(album_cover_path, "JPEG")

        global_cover_path = os.path.join(cover_dir, cover_filename)
        img.save(global_cover_path, "JPEG")

        return album_cover_path
    except Exception as exc:
        print(f"Failed to process cover: {exc}")
        return None


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
    elif not keep_original_metadata and "artist" in audio:
        del audio["artist"]

    if album:
        audio["album"] = album
    elif not keep_original_metadata and "album" in audio:
        del audio["album"]

    if year:
        audio["date"] = year
    elif not keep_original_metadata:
        for key in ("date", "year"):
            if key in audio:
                del audio[key]

    if genre:
        audio["genre"] = genre
    elif not keep_original_metadata and "genre" in audio:
        del audio["genre"]

    audio["tracknumber"] = str(tracknum)
    audio["title"] = title

    for tag in ["albumartist", "discnumber", "comment"]:
        if tag in audio:
            del audio[tag]

    audio.save(file_path)

    id3 = ID3(file_path)
    if cover_path and os.path.exists(cover_path):
        id3.delall("APIC")
        with open(cover_path, "rb") as img:
            id3.add(APIC(mime="image/jpeg", type=3, desc="Cover", data=img.read()))
        id3.save(file_path)


def analyze_loudness(file_path):
    cmd = [
        "ffmpeg", "-i", file_path,
        "-filter_complex", "ebur128=framelog=verbose",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"FFmpeg analysis failed for {file_path}: {result.stderr}")
        return None

    match = re.search(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", result.stderr)
    if match:
        return float(match.group(1))

    print(f"Could not parse loudness for {file_path}")
    return None


def normalize_audio(input_path, target_lufs=-15.0, tolerance=3.0):
    try:
        loudness = analyze_loudness(input_path)
        if loudness is not None:
            print(f"Loudness for {input_path}: {loudness:.1f} LUFS")
        else:
            print(f"Loudness for {input_path}: unknown, proceeding with normalization")

        if loudness is not None and abs(loudness - target_lufs) <= tolerance:
            print(
                f"Skipping normalization for {os.path.basename(input_path)} "
                f"(already {loudness:.1f} LUFS)"
            )
            return True

        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, os.path.basename(input_path))

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

    except Exception as exc:
        print(f"Error normalizing audio {input_path}: {exc}")
        return False


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

    artist_name = sanitize_name(artist) if artist else "Unknown Artist"
    artist_dir = os.path.join(output_dir, artist_name)
    os.makedirs(artist_dir, exist_ok=True)

    album_name = sanitize_name(album) if album else "Unknown Album"
    folder_name = f"{artist_name} - {album_name}" if artist_name != "Unknown Artist" else album_name
    target_dir = os.path.join(artist_dir, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    cover_path = (
        download_and_prepare_cover(cover_url, album, artist, target_dir, cover_dir)
        if cover_url else None
    )

    yt_args = [
        "yt-dlp",
        "--sleep-requests", "0",
        "-x", "--audio-format", "mp3",
    ]
    if cookies_file:
        yt_args += ["--cookies", cookies_file]
    if not cover_url:
        yt_args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    yt_args += [
        "--output", f"{target_dir}/%(playlist_index)03d - %(title)s.%(ext)s",
        url
    ]
    download_result = subprocess.run(yt_args)

    files_to_process = []
    for file_name in sorted(os.listdir(target_dir)):
        if file_name.endswith(".mp3"):
            file_path = os.path.join(target_dir, file_name)
            track_num = file_name.split(" - ")[0]
            raw_title = " - ".join(file_name.split(" - ")[1:]).replace(".mp3", "")
            title = normalize_track_title(raw_title, album, artist)
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

    for file_name in sorted(os.listdir(target_dir)):
        if file_name.endswith(".mp3"):
            old_path = os.path.join(target_dir, file_name)
            raw_title = os.path.splitext(file_name)[0].split(" - ", 1)[-1]
            title = normalize_track_title(raw_title, album, artist)
            new_file_name = build_final_track_filename(title, album, artist)
            new_path = os.path.join(target_dir, new_file_name)
            if os.path.normcase(os.path.abspath(old_path)) != os.path.normcase(os.path.abspath(new_path)):
                os.replace(old_path, new_path)
                print(f"Renamed: {file_name} -> {os.path.basename(new_path)}")

    if download_result.returncode != 0:
        if files_to_process:
            print(
                f"yt-dlp returned exit code {download_result.returncode} for playlist {url}, "
                "but downloaded files were still processed."
            )
        else:
            raise subprocess.CalledProcessError(download_result.returncode, yt_args)


def main():
    args = parse_args()
    playlists_file = resolve_playlists_file(args.playlists_file)
    config_path = resolve_config_path(args.config_file)
    config_data = load_config(config_path)
    settings = build_runtime_settings(args, config_data)
    tasks = load_playlist_entries(playlists_file)

    output_dir = settings["output_dir"]
    cover_dir = os.path.join(output_dir, "Covers")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cover_dir, exist_ok=True)

    with ThreadPoolExecutor(max_workers=settings["max_workers"]) as executor:
        futures = [
            executor.submit(
                download_playlist,
                *task,
                settings["cookies_file"],
                output_dir,
                cover_dir,
                settings["keep_original_metadata"],
                settings["enable_normalization"],
            )
            for task in tasks
        ]
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                print(f"Error in playlist task: {exc}")


if __name__ == "__main__":
    main()
