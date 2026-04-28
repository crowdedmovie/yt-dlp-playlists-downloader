"""Subprocess helpers."""

from __future__ import annotations

import subprocess

from .logging import log_message


def run_streamed_process(cmd, logger=print):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    if process.stdout is not None:
        for line in process.stdout:
            log_message(logger, line.rstrip())

    return process.wait()
