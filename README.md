# yt-dlp-playlists-downloader

`yt-dlp-playlists-downloader` is an alpha Python script that downloads playlist tracks with `yt-dlp`, organizes them into artist and album folders, and applies ID3 metadata from TOML files.

It works well for YouTube and SoundCloud playlists because media extraction is handled by `yt-dlp`.

## Who Is This For

People who want to download multiple playlists and tag them cleanly for use in music players or media servers.

## Features

- Reads playlist entries from `playlists.toml`
- Reads persistent defaults from `config.toml`
- Lets CLI flags override config values for one-off runs
- Downloads playlists as MP3 files
- Organizes output under `Output/<Artist>/<Artist - Album>/` by default
- Applies artist, album, year, genre, title, and track number metadata
- Embeds a custom cover image or preserves the original downloaded thumbnail
- Can normalize audio with FFmpeg
- Processes multiple playlists in parallel

## Alpha Status

This project is currently in alpha. The workflow is usable, but the interface and data model may still evolve.

## Requirements

- Python 3.11 or newer
- `yt-dlp`
- FFmpeg

Python packages used by the script are listed in `requirements.txt`.

## Installation

1. Clone the repository.
2. Install the Python dependencies:

```bash
pip install -r requirements.txt
```

3. Install `yt-dlp` if it is not already available:

```bash
python -m pip install -U "yt-dlp[default]"
```

4. Make sure `ffmpeg` is installed and available in your `PATH`.

## Data Files

The project now uses two TOML files:

- `playlists.toml`: playlist entries and metadata
- `config.toml`: persistent runtime defaults

CLI flags can override values from `config.toml` when needed.

## `playlists.toml` Format

Each playlist is defined as a `[[playlists]]` entry.

Example:

```toml
[[playlists]]
url = "https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID"
artist = "Artist Name"
album = "Album Name"
year = 2024
genre = "Genre"
cover_url = "https://example.com/cover.jpg"

[[playlists]]
url = "https://soundcloud.com/artist/sets/example-playlist"
artist = "Another Artist"
album = "Example Mixtape"
genre = "Electronic"
```

Supported playlist fields:

- `url`: required
- `artist`: optional
- `album`: optional
- `year`: optional
- `genre`: optional
- `cover_url`: optional

Optional fields may be omitted entirely.

## `config.toml` Format

`config.toml` stores persistent defaults for runtime behavior.

Example:

```toml
[settings]
output_dir = "Output"
max_workers = 5
keep_original_metadata = true
enable_normalization = false

# Optional:
# cookies_file = "youtube_cookies.txt"
```

Supported settings:

- `output_dir`
- `max_workers`
- `keep_original_metadata`
- `enable_normalization`
- `cookies_file`

## Config Precedence

Settings are resolved in this order:

1. CLI flags
2. `config.toml`
3. Built-in defaults

This means `config.toml` is used for usual preferences, while CLI flags remain available for temporary overrides.

## Cover Image Behavior

The `cover_url` field can contain:

- A remote image URL such as `http://...` or `https://...`
- A local file path to an image

If a custom cover is provided, the script converts it to JPEG, saves it in the album folder, copies it to `Output/Covers/` by default, and embeds it into each MP3.

If no custom cover is provided, the script asks `yt-dlp` to embed the source thumbnail when possible.

## Usage

Run with the default files in the current directory:

```bash
python main.py
```

Run with a custom playlists file:

```bash
python main.py my_playlists.toml
```

Run with a custom playlists file and cookies:

```bash
python main.py my_playlists.toml --cookies youtube_cookies.txt
```

Run with a custom config file:

```bash
python main.py my_playlists.toml --config my_config.toml
```

Run with runtime overrides:

```bash
python main.py my_playlists.toml --config my_config.toml --output-dir MyMusic --max-workers 3 --keep-original-metadata false --enable-normalization true
```

Show the built-in CLI help:

```bash
python main.py --help
```

## CLI Options

- `playlists_file`: Optional path to the playlists TOML file. Default: `playlists.toml`
- `--config`: Optional path to a config TOML file. If omitted, the script uses `config.toml` when present.
- `--cookies`: Optional cookies file passed to `yt-dlp`
- `--output-dir`: Base folder for downloads and the shared `Covers/` directory. Default: `Output`
- `--max-workers`: Number of playlists processed in parallel. Default: `5`
- `--keep-original-metadata`: `true` or `false`. When playlist metadata fields are missing, keep existing tags if `true`, or clear them if `false`. Default: `true`
- `--enable-normalization`: `true` or `false`. Enables FFmpeg loudness normalization after download and tagging. Default: `false`

## Output Structure

Downloaded files are stored like this:

```text
Output/
  Covers/
  Artist Name/
    Artist Name - Album Name/
      Song Title.mp3
      Artist Name-Album Name-cover.jpg
```

## Notes

- Supported platforms depend on `yt-dlp`.
- YouTube and SoundCloud playlists are both supported use cases.
- `config.toml` and `playlists.toml` are editable by hand and intended to replace the old spreadsheet workflow.
- Cookies files and generated output folders should stay untracked in Git.
