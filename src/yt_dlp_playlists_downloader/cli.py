"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from .core.constants import (
    DEFAULT_ENABLE_NORMALIZATION,
    DEFAULT_KEEP_ORIGINAL_METADATA,
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_DIR,
)
from .core.downloader import run_download
from .core.errors import DownloaderError


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
            "Path to the playlists TOML file. If omitted, the app uses the "
            "playlists.toml file in its app data folder."
        ),
    )
    parser.add_argument(
        "--config",
        dest="config_file",
        help=(
            "Optional path to a config TOML file. If omitted, the app uses the "
            "config.toml file in its app data folder."
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
    parser.add_argument(
        "--log-file",
        default=None,
        help=(
            "Optional path for the run log file. If omitted, a timestamped file is "
            f"created under the app data {DEFAULT_LOG_DIR}/ folder."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        run_download(
            playlists_file_arg=args.playlists_file,
            config_file_arg=args.config_file,
            output_dir=args.output_dir,
            max_workers=args.max_workers,
            keep_original_metadata=args.keep_original_metadata,
            enable_normalization=args.enable_normalization,
            cookies_file=args.cookies_file,
            log_file=args.log_file,
            logger=print,
        )
    except DownloaderError as exc:
        print(exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
