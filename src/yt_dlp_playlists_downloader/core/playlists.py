"""Playlist TOML loading and validation."""

from __future__ import annotations

import os

from .constants import DEFAULT_PLAYLISTS_FILE
from .errors import DownloaderError
from .toml_io import load_toml_file

PLAYLIST_COLUMNS = ["url", "artist", "album", "year", "genre", "cover_url"]


def resolve_playlists_file(playlists_arg):
    playlists_file = playlists_arg or DEFAULT_PLAYLISTS_FILE
    if not os.path.isfile(playlists_file):
        raise DownloaderError(
            f"Playlists file not found: {playlists_file}\n"
            "Create a playlists.toml file or pass a custom file path."
        )
    return playlists_file


def load_playlist_entries(playlists_file):
    playlists_data = load_toml_file(playlists_file, "Playlists file")
    playlists = playlists_data.get("playlists")

    if playlists is None:
        raise DownloaderError(
            f"Playlists file error: {playlists_file} must define at least one [[playlists]] entry."
        )

    if not isinstance(playlists, list):
        raise DownloaderError("Playlists file error: playlists must be an array of tables.")

    tasks = []
    for index, playlist in enumerate(playlists, start=1):
        if not isinstance(playlist, dict):
            raise DownloaderError(f"Playlists file error: entry #{index} must be a table.")

        url = require_string_field(playlist, "url", index)
        artist = optional_string_field(playlist, "artist")
        album = optional_string_field(playlist, "album")
        year = optional_year_field(playlist, index)
        genre = optional_string_field(playlist, "genre")
        cover_url = optional_string_field(playlist, "cover_url")

        tasks.append((url, artist, album, year, genre, cover_url))

    return tasks


def require_string_field(entry, field_name, index):
    value = entry.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise DownloaderError(
            f"Playlists file error: entry #{index} requires a non-empty '{field_name}' value."
        )
    return value.strip()


def optional_string_field(entry, field_name):
    value = entry.get(field_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DownloaderError(f"Playlists file error: '{field_name}' must be a string when provided.")
    return value.strip()


def optional_year_field(entry, index):
    value = entry.get("year")
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    raise DownloaderError(
        f"Playlists file error: entry #{index} field 'year' must be an integer or string."
    )
