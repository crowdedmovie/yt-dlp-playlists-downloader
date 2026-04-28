"""Subprocess helpers."""

from __future__ import annotations

import subprocess
import threading

from .logging import log_message


def hidden_subprocess_kwargs():
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def run_streamed_process(cmd, logger=print, cancel_event=None):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **hidden_subprocess_kwargs(),
    )
    killer = _start_process_killer(process, cancel_event, logger)

    if process.stdout is not None:
        for line in process.stdout:
            log_message(logger, line.rstrip())

    returncode = process.wait()
    if killer is not None:
        killer.join(timeout=0.1)
    return returncode


def run_captured_process(cmd, cancel_event=None):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **hidden_subprocess_kwargs(),
    )
    killer = _start_process_killer(process, cancel_event, None)
    stdout, stderr = process.communicate()
    if killer is not None:
        killer.join(timeout=0.1)
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _start_process_killer(process, cancel_event, logger):
    if cancel_event is None:
        return None

    def terminate_when_cancelled():
        while not cancel_event.wait(timeout=0.2):
            if process.poll() is not None:
                return

        if process.poll() is not None:
            return

        log_message(logger, "Stopping active subprocess...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    thread = threading.Thread(target=terminate_when_cancelled, daemon=True)
    thread.start()
    return thread
