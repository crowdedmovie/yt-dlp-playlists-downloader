"""TOML file loading helpers."""

from __future__ import annotations

import tomllib

from .errors import DownloaderError


def load_toml_file(path, label):
    try:
        with open(path, "rb") as toml_file:
            return tomllib.load(toml_file)
    except FileNotFoundError:
        raise DownloaderError(f"{label} not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise DownloaderError(f"Failed to parse {label} {path}: {exc}") from exc
