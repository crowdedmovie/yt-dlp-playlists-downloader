"""Filename and track title cleanup helpers."""

from __future__ import annotations

import re


def sanitize_name(name: str | None) -> str:
    if name is None:
        return "Unknown"

    name = str(name)
    cleaned = name.strip()

    quote_chars = ['"', "\uFF02", "'", "\uFF07"]

    while len(cleaned) > 0 and cleaned[0] in quote_chars:
        cleaned = cleaned[1:]
    while len(cleaned) > 0 and cleaned[-1] in quote_chars:
        cleaned = cleaned[:-1]

    for quote in quote_chars:
        cleaned = cleaned.replace(quote, "")

    cleaned = re.sub(r"^\s*(?:\d{1,3}\s*[.-]\s*|\d{1,3}\s+)", "", cleaned)
    cleaned = re.sub(r'[<>:"/\\|?*]+', "", cleaned)
    cleaned = cleaned.strip().rstrip(".")

    return cleaned or "Unknown"


def normalize_track_title(title, album, artist):
    normalized_title = str(title).strip()

    if artist and album:
        prefix_pattern = re.compile(
            rf"^\s*{re.escape(artist.strip())}\s*-\s*{re.escape(album.strip())}\s*-\s*",
            re.IGNORECASE,
        )
        normalized_title = prefix_pattern.sub("", normalized_title, count=1).strip()

    return normalized_title or "Unknown"


def build_final_track_filename(title, album, artist):
    return f"{sanitize_name(normalize_track_title(title, album, artist))}.mp3"
