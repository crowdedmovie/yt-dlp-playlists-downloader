"""Audio loudness analysis and normalization."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from .logging import log_message
from .processes import hidden_subprocess_kwargs


def analyze_loudness(file_path, logger=print):
    cmd = [
        "ffmpeg", "-i", file_path,
        "-filter_complex", "ebur128=framelog=verbose",
        "-f", "null", "-"
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        log_message(logger, f"FFmpeg analysis failed for {file_path}: {result.stderr}")
        return None

    match = re.search(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", result.stderr)
    if match:
        return float(match.group(1))

    log_message(logger, f"Could not parse loudness for {file_path}")
    return None


def normalize_audio(input_path, target_lufs=-15.0, tolerance=3.0, logger=print):
    try:
        loudness = analyze_loudness(input_path, logger)
        if loudness is not None:
            log_message(logger, f"Loudness for {input_path}: {loudness:.1f} LUFS")
        else:
            log_message(logger, f"Loudness for {input_path}: unknown, proceeding with normalization")

        if loudness is not None and abs(loudness - target_lufs) <= tolerance:
            log_message(
                logger,
                f"Skipping normalization for {os.path.basename(input_path)} "
                f"(already {loudness:.1f} LUFS)"
            )
            return True

        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, os.path.basename(input_path))

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            output_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **hidden_subprocess_kwargs(),
        )
        if result.returncode != 0:
            log_message(logger, f"FFmpeg normalization error for {input_path}: {result.stderr}")
            return False

        shutil.move(output_path, input_path)
        log_message(logger, f"Normalization completed for {input_path}")
        return True

    except Exception as exc:
        log_message(logger, f"Error normalizing audio {input_path}: {exc}")
        return False
