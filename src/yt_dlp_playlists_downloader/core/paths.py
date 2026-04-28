"""Cross-platform app data paths and default file seeding."""

from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from .constants import APP_NAME, DEFAULT_CONFIG_FILE, DEFAULT_LOG_DIR, DEFAULT_PLAYLISTS_FILE

RESOURCE_PACKAGE = "yt_dlp_playlists_downloader.resources"


def get_app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def get_default_config_path() -> Path:
    return get_app_data_dir() / DEFAULT_CONFIG_FILE


def get_default_playlists_path() -> Path:
    return get_app_data_dir() / DEFAULT_PLAYLISTS_FILE


def get_default_log_dir() -> Path:
    return get_app_data_dir() / DEFAULT_LOG_DIR


def ensure_app_data_files() -> None:
    app_data_dir = get_app_data_dir()
    app_data_dir.mkdir(parents=True, exist_ok=True)
    get_default_log_dir().mkdir(parents=True, exist_ok=True)

    _seed_default_file(DEFAULT_CONFIG_FILE, get_default_config_path())
    _seed_default_file(DEFAULT_PLAYLISTS_FILE, get_default_playlists_path())


def _seed_default_file(resource_name: str, destination: Path) -> None:
    if destination.exists():
        return

    resource = resources.files(RESOURCE_PACKAGE).joinpath(resource_name)
    with resources.as_file(resource) as source:
        shutil.copyfile(source, destination)
