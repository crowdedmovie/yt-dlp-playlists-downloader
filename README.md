# yt-dlp-playlists-downloader

`yt-dlp-playlists-downloader` is an alpha Python script that downloads playlist tracks with `yt-dlp`, organizes them into artist and album folders, and applies ID3 metadata from an OpenDocument spreadsheet (`.ods`).

It is suitable for YouTube playlists and also for SoundCloud playlists, because source support comes from `yt-dlp`.

## Who is this for

People who needs to download multiples playlists, and apply proper metadata to them, for easy import to music player / servers.

## TODO

- Add GUI
- Replace .ods by .toml files (mushc easier to read, and to edit from multiple platforms that spreasheets)

## Features

- Reads playlist jobs from a `.ods` spreadsheet
- Supports either a direct spreadsheet path or interactive spreadsheet selection
- Downloads playlists as MP3 files
- Organizes output under `Output/<Artist>/<Artist - Album>/` by default
- Applies artist, album, year, genre, title, and track number metadata
- Embeds a custom cover image or preserves the original downloaded thumbnail
- Can normalize audio with FFmpeg when enabled via CLI
- Processes multiple playlists in parallel

## Alpha Status

This project is currently in alpha. The workflow is usable, but the interface is still simple and some configuration is still code-based.

## Requirements

- Python 3
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

## Spreadsheet Format

The script reads a sheet named `Infos`.

It expects the first 6 columns in this order:

1. `URL`
2. `Artist`
3. `Album`
4. `Year`
5. `Genre`
6. `Cover_URL`

Each non-empty row represents one playlist to process.

Example structure:

| URL | Artist | Album | Year | Genre | Cover_URL |
| --- | --- | --- | --- | --- | --- |
| `https://www.youtube.com/playlist?...` | `Artist Name` | `Album Name` | `2024` | `Rock` | `https://example.com/cover.jpg` |
| `https://soundcloud.com/...` | `Artist Name` | `Mixtape Name` | `2023` | `Electronic` | `test.jpg` |

## Cover Image Behavior

The `Cover_URL` field can contain:

- A remote image URL such as `http://...` or `https://...`
- A local file path to an image

If a custom cover is provided, the script converts it to JPEG, saves it in the album folder, copies it to `Output/Covers/` by default, and embeds it into each MP3.

If no custom cover is provided, the script asks `yt-dlp` to embed the source thumbnail when possible.

## Usage

Run with an explicit spreadsheet:

```bash
python main.py my_playlists.ods
```

Run with an explicit spreadsheet and optional cookies file:

```bash
python main.py my_playlists.ods --cookies youtube_cookies.txt
```

Run without a spreadsheet argument to select from `.ods` files found in the current directory:

```bash
python main.py
```

If no `.ods` files are found, the script exits with a message telling you to add one.

Run with additional runtime options:

```bash
python main.py my_playlists.ods --cookies youtube_cookies.txt --output-dir MyMusic --max-workers 3 --keep-original-metadata false --enable-normalization true
```

Show the built-in CLI help:

```bash
python main.py --help
```

## CLI Options

- `spreadsheet`: Optional path to the `.ods` file. If omitted, the script scans the current directory and prompts you to choose one.
- `--cookies`: Optional cookies file passed to `yt-dlp`.
- `--output-dir`: Base folder for downloads and the shared `Covers/` directory. Default: `Output`
- `--max-workers`: Number of playlists processed in parallel. Default: `5`
- `--keep-original-metadata`: `true` or `false`. When spreadsheet metadata fields are empty, keep existing tags if `true`, or clear them if `false`. Default: `true`
- `--enable-normalization`: `true` or `false`. Enables FFmpeg loudness normalization after download and tagging (requiere some CPU usage, slow down the overall process). Default: `false`

## Cookies

Some playlist sources or account-restricted content may require a cookies file.

Cookies are optional and are only passed to `yt-dlp` when you provide them with:

```bash
python main.py my_playlists.ods --cookies youtube_cookies.txt
```

Do not commit personal cookies files to GitHub.

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

## Defaults

The script currently uses these defaults unless overridden with CLI arguments:

- `SHEET_NAME = "Infos"`
- `OUTPUT_DIR = "Output"`
- `MAX_WORKERS = 5`
- `KEEP_ORIGINAL_METADATA = True`
- `ENABLE_NORMALIZATION = False`

## Notes

- Supported platforms depend on `yt-dlp`.
- YouTube and SoundCloud playlists are both supported use cases.
- Local `.ods` files, cookies files, and generated output folders should stay untracked in Git.
