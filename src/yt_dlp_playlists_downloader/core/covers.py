"""Cover image download, conversion, and placement."""

from __future__ import annotations

import os
from io import BytesIO

import requests
from PIL import Image

from .filenames import sanitize_name
from .logging import log_message


def download_and_prepare_cover(url_or_path, album, artist, target_dir, cover_dir, logger=print):
    try:
        if url_or_path.startswith(("http://", "https://")):
            response = requests.get(url_or_path, timeout=15)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGB")
        else:
            if not os.path.isfile(url_or_path):
                log_message(logger, f"Local cover file not found: {url_or_path}")
                return None
            log_message(logger, f"Local cover file found: {url_or_path}")
            img = Image.open(url_or_path).convert("RGB")

        safe_album = sanitize_name(album)
        safe_artist = sanitize_name(artist)
        cover_filename = f"{safe_artist}-{safe_album}-cover.jpg"

        album_cover_path = os.path.join(target_dir, cover_filename)
        img.save(album_cover_path, "JPEG")

        global_cover_path = os.path.join(cover_dir, cover_filename)
        img.save(global_cover_path, "JPEG")

        return album_cover_path
    except Exception as exc:
        log_message(logger, f"Failed to process cover: {exc}")
        return None
