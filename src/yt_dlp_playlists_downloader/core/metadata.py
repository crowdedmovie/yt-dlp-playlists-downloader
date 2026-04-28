"""ID3 metadata tagging."""

from __future__ import annotations

import os

from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3


def apply_metadata(
    file_path,
    artist,
    album,
    year,
    genre,
    tracknum,
    cover_path,
    title,
    keep_original_metadata,
):
    try:
        audio = EasyID3(file_path)
    except Exception:
        audio = EasyID3()

    if artist:
        audio["artist"] = artist
    elif not keep_original_metadata and "artist" in audio:
        del audio["artist"]

    if album:
        audio["album"] = album
    elif not keep_original_metadata and "album" in audio:
        del audio["album"]

    if year:
        audio["date"] = year
    elif not keep_original_metadata:
        for key in ("date", "year"):
            if key in audio:
                del audio[key]

    if genre:
        audio["genre"] = genre
    elif not keep_original_metadata and "genre" in audio:
        del audio["genre"]

    audio["tracknumber"] = str(tracknum)
    audio["title"] = title

    for tag in ["albumartist", "discnumber", "comment"]:
        if tag in audio:
            del audio[tag]

    audio.save(file_path)

    id3 = ID3(file_path)
    if cover_path and os.path.exists(cover_path):
        id3.delall("APIC")
        with open(cover_path, "rb") as img:
            id3.add(APIC(mime="image/jpeg", type=3, desc="Cover", data=img.read()))
        id3.save(file_path)
