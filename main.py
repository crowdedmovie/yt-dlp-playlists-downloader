"""Compatibility wrapper for the packaged CLI.

The application code lives under src/ytdlp_playlists_downloader.
"""

from __future__ import annotations

import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ytdlp_playlists_downloader.cli import main
from ytdlp_playlists_downloader.core.config import build_runtime_settings, load_config
from ytdlp_playlists_downloader.core.constants import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_ENABLE_NORMALIZATION,
    DEFAULT_KEEP_ORIGINAL_METADATA,
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLAYLISTS_FILE,
)
from ytdlp_playlists_downloader.core.downloader import download_playlist, run_download
from ytdlp_playlists_downloader.core.errors import DownloaderError
from ytdlp_playlists_downloader.core.filenames import (
    build_final_track_filename,
    normalize_track_title,
    sanitize_name,
)
from ytdlp_playlists_downloader.core.playlists import load_playlist_entries


if __name__ == "__main__":
    sys.exit(main())
