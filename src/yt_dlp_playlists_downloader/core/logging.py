"""Logging helpers for CLI, GUI, and local run logs."""

from __future__ import annotations

import os
import threading
from datetime import datetime

from .paths import ensure_app_data_files, get_default_log_dir


def log_message(logger, message):
    if logger is not None:
        logger(message)


class FileTeeLogger:
    def __init__(self, logger, log_file):
        self._logger = logger
        self._log_file = log_file
        self._lock = threading.Lock()

    def __call__(self, message):
        text = str(message)
        if self._logger is not None:
            self._logger(text)
        with self._lock:
            self._log_file.write(f"{text}\n")
            self._log_file.flush()


def create_run_log_path(log_file=None):
    if log_file:
        return log_file

    ensure_app_data_files()
    log_dir = get_default_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return str(log_dir / f"download-{timestamp}.log")
