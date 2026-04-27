"""Compatibility import for the packaged GUI main window."""

from __future__ import annotations

import sys
from pathlib import Path

src_path = Path(__file__).resolve().parents[1] / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ytdlp_playlists_downloader.gui.main_window import MainWindow

__all__ = ["MainWindow"]
