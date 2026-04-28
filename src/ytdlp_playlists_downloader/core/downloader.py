"""Download orchestration for CLI and GUI."""

from __future__ import annotations

import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .audio import normalize_audio
from .config import build_runtime_settings, load_config, resolve_config_path
from .constants import DEFAULT_KEEP_ORIGINAL_METADATA, DEFAULT_OUTPUT_DIR
from .covers import download_and_prepare_cover
from .filenames import build_final_track_filename, normalize_track_title, sanitize_name
from .logging import FileTeeLogger, create_run_log_path, log_message
from .metadata import apply_metadata
from .playlists import load_playlist_entries, resolve_playlists_file
from .processes import run_streamed_process


def download_playlist(
    url,
    artist,
    album,
    year,
    genre,
    cover_url,
    cookies_file=None,
    output_dir=DEFAULT_OUTPUT_DIR,
    cover_dir=None,
    keep_original_metadata=DEFAULT_KEEP_ORIGINAL_METADATA,
    enable_normalization=False,
    logger=print,
):
    if cover_dir is None:
        cover_dir = os.path.join(output_dir, "Covers")

    artist_name = sanitize_name(artist) if artist else "Unknown Artist"
    artist_dir = os.path.join(output_dir, artist_name)
    os.makedirs(artist_dir, exist_ok=True)

    album_name = sanitize_name(album) if album else "Unknown Album"
    folder_name = f"{album_name} - {artist_name}" if artist_name != "Unknown Artist" else album_name
    target_dir = os.path.join(artist_dir, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    cover_path = (
        download_and_prepare_cover(cover_url, album, artist, target_dir, cover_dir, logger)
        if cover_url else None
    )

    yt_args = [
        "yt-dlp",
        "--sleep-requests", "0",
        "-x", "--audio-format", "mp3",
    ]
    if cookies_file:
        yt_args += ["--cookies", cookies_file]
    if not cover_url:
        yt_args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    yt_args += [
        "--output", os.path.join(target_dir, "%(playlist_index)03d - %(title)s.%(ext)s"),
        url
    ]
    log_message(logger, f"Downloading playlist: {url}")
    download_returncode = run_streamed_process(yt_args, logger)

    files_to_process = []
    for file_name in sorted(os.listdir(target_dir)):
        if file_name.endswith(".mp3"):
            file_path = os.path.join(target_dir, file_name)
            track_num = file_name.split(" - ")[0]
            raw_title = " - ".join(file_name.split(" - ")[1:]).replace(".mp3", "")
            title = normalize_track_title(raw_title, album, artist)
            apply_metadata(
                file_path,
                artist,
                album,
                year,
                genre,
                track_num,
                cover_path,
                title,
                keep_original_metadata,
            )
            files_to_process.append((file_path, title))

    if enable_normalization:
        log_message(
            logger,
            f"\nNormalizing audio files for Album: {album or 'unknown album'} - {artist or 'unknown artist'}",
        )
        for file_path, _ in files_to_process:
            normalize_audio(file_path, logger=logger)

    for file_name in sorted(os.listdir(target_dir)):
        if file_name.endswith(".mp3"):
            old_path = os.path.join(target_dir, file_name)
            raw_title = os.path.splitext(file_name)[0].split(" - ", 1)[-1]
            title = normalize_track_title(raw_title, album, artist)
            new_file_name = build_final_track_filename(title, album, artist)
            new_path = os.path.join(target_dir, new_file_name)
            if os.path.normcase(os.path.abspath(old_path)) != os.path.normcase(os.path.abspath(new_path)):
                os.replace(old_path, new_path)
                log_message(logger, f"Renamed: {file_name} -> {os.path.basename(new_path)}")

    if download_returncode != 0:
        if files_to_process:
            log_message(
                logger,
                f"yt-dlp returned exit code {download_returncode} for playlist {url}, "
                "but downloaded files were still processed."
            )
        else:
            raise subprocess.CalledProcessError(download_returncode, yt_args)


def run_download(
    playlists_file_arg=None,
    config_file_arg=None,
    output_dir=None,
    max_workers=None,
    keep_original_metadata=None,
    enable_normalization=None,
    cookies_file=None,
    log_file=None,
    logger=print,
):
    log_path = create_run_log_path(log_file)
    log_parent = os.path.dirname(log_path)
    if log_parent:
        os.makedirs(log_parent, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as run_log:
        tee_logger = FileTeeLogger(logger, run_log)
        _run_download(
            playlists_file_arg=playlists_file_arg,
            config_file_arg=config_file_arg,
            output_dir=output_dir,
            max_workers=max_workers,
            keep_original_metadata=keep_original_metadata,
            enable_normalization=enable_normalization,
            cookies_file=cookies_file,
            logger=tee_logger,
            log_path=log_path,
        )


def _run_download(
    playlists_file_arg=None,
    config_file_arg=None,
    output_dir=None,
    max_workers=None,
    keep_original_metadata=None,
    enable_normalization=None,
    cookies_file=None,
    logger=print,
    log_path=None,
):
    args = argparse.Namespace(
        playlists_file=playlists_file_arg,
        config_file=config_file_arg,
        output_dir=output_dir,
        max_workers=max_workers,
        keep_original_metadata=keep_original_metadata,
        enable_normalization=enable_normalization,
        cookies_file=cookies_file,
    )

    playlists_file = resolve_playlists_file(args.playlists_file)
    config_path = resolve_config_path(args.config_file)
    config_data = load_config(config_path)
    settings = build_runtime_settings(args, config_data)
    output_dir = settings["output_dir"]

    log_message(logger, f"Run started: {datetime.now().isoformat(timespec='seconds')}")
    if log_path:
        log_message(logger, f"Log file: {log_path}")
    log_message(logger, f"Using playlists file: {playlists_file}")
    log_message(logger, f"Using config file: {config_path or 'built-in defaults'}")
    log_message(logger, f"Output directory: {output_dir}")
    log_message(logger, f"Cookies file: {settings['cookies_file'] or 'not set'}")
    log_message(logger, f"Keep original metadata: {settings['keep_original_metadata']}")
    log_message(logger, f"Enable normalization: {settings['enable_normalization']}")

    tasks = load_playlist_entries(playlists_file)

    if not tasks:
        log_message(logger, "No playlists found in the playlists file.")
        return

    cover_dir = os.path.join(output_dir, "Covers")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cover_dir, exist_ok=True)

    log_message(logger, f"Processing {len(tasks)} playlist(s) with {settings['max_workers']} worker(s).")

    with ThreadPoolExecutor(max_workers=settings["max_workers"]) as executor:
        futures = [
            executor.submit(
                download_playlist,
                *task,
                settings["cookies_file"],
                output_dir,
                cover_dir,
                settings["keep_original_metadata"],
                settings["enable_normalization"],
                logger,
            )
            for task in tasks
        ]
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                log_message(logger, f"Error in playlist task: {exc}")

    log_message(logger, "Download run complete.")
