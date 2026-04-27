"""Theme discovery and application helpers for the GUI."""

from __future__ import annotations

import importlib
import os
from typing import Iterable

os.environ.setdefault("QT_API", "pyqt6")

from qtpy import QtWidgets

DEFAULT_THEME = "nord"


def available_theme_names() -> list[str]:
    try:
        qt_themes = importlib.import_module("qt_themes")
    except ImportError:
        return []

    themes = qt_themes.get_themes()
    return sorted(themes.keys())


def pick_startup_theme(theme_names: Iterable[str]) -> str | None:
    names = list(theme_names)
    if not names:
        return None
    if DEFAULT_THEME in names:
        return DEFAULT_THEME
    return names[0]


def apply_theme(theme_name: str | None) -> None:
    try:
        qt_themes = importlib.import_module("qt_themes")
    except ImportError:
        return

    qt_themes.set_theme(theme_name)


def ensure_app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if isinstance(app, QtWidgets.QApplication):
        return app
    return QtWidgets.QApplication([])
