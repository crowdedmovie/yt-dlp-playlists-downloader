"""GUI application entrypoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt6")

if __package__ in (None, ""):
    package_parent = Path(__file__).resolve().parents[2]
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))
    from yt_dlp_playlists_downloader.gui.main_window import MainWindow
    from yt_dlp_playlists_downloader.gui.theme_service import ensure_app
else:
    from .main_window import MainWindow
    from .theme_service import ensure_app


def main() -> int:
    app = ensure_app()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
