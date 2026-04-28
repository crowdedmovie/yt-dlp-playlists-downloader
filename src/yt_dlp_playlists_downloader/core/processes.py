"""Subprocess helpers."""

from __future__ import annotations

import subprocess

from .logging import log_message


def hidden_subprocess_kwargs():
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def run_streamed_process(cmd, logger=print):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **hidden_subprocess_kwargs(),
    )

    if process.stdout is not None:
        for line in process.stdout:
            log_message(logger, line.rstrip())

    return process.wait()
