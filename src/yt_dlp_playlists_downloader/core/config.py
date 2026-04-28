"""Runtime config loading and validation."""

from __future__ import annotations

import os

from .constants import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_ENABLE_NORMALIZATION,
    DEFAULT_KEEP_ORIGINAL_METADATA,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_DIR,
)
from .errors import DownloaderError
from .paths import ensure_app_data_files, get_default_config_path
from .toml_io import load_toml_file


def resolve_config_path(config_arg):
    if config_arg:
        if not os.path.isfile(config_arg):
            raise DownloaderError(f"Config file not found: {config_arg}")
        return config_arg

    ensure_app_data_files()
    return str(get_default_config_path())


def load_config(config_path):
    if not config_path:
        return {}
    return load_toml_file(config_path, "Config file")


def build_runtime_settings(args, config_data):
    config_settings = config_data.get("settings", {})
    if config_settings and not isinstance(config_settings, dict):
        raise DownloaderError("Config file error: [settings] must be a table.")

    settings = {
        "output_dir": DEFAULT_OUTPUT_DIR,
        "max_workers": DEFAULT_MAX_WORKERS,
        "keep_original_metadata": DEFAULT_KEEP_ORIGINAL_METADATA,
        "enable_normalization": DEFAULT_ENABLE_NORMALIZATION,
        "cookies_file": None,
    }

    for key in settings:
        if key in config_settings:
            settings[key] = config_settings[key]

    if args.output_dir is not None:
        settings["output_dir"] = args.output_dir
    if args.max_workers is not None:
        settings["max_workers"] = args.max_workers
    if args.keep_original_metadata is not None:
        settings["keep_original_metadata"] = args.keep_original_metadata
    if args.enable_normalization is not None:
        settings["enable_normalization"] = args.enable_normalization
    if args.cookies_file is not None:
        settings["cookies_file"] = args.cookies_file

    validate_runtime_settings(settings)
    return settings


def validate_runtime_settings(settings):
    if not isinstance(settings["output_dir"], str) or not settings["output_dir"].strip():
        raise DownloaderError("output_dir must be a non-empty string.")

    if not isinstance(settings["max_workers"], int) or settings["max_workers"] < 1:
        raise DownloaderError("max_workers must be an integer greater than or equal to 1.")

    for key in ("keep_original_metadata", "enable_normalization"):
        if not isinstance(settings[key], bool):
            raise DownloaderError(f"{key} must be a boolean value.")

    cookies_file = settings["cookies_file"]
    if cookies_file is not None:
        if not isinstance(cookies_file, str) or not cookies_file.strip():
            raise DownloaderError("cookies_file must be a non-empty string when provided.")
        if not os.path.isfile(cookies_file):
            raise DownloaderError(f"Cookies file not found: {cookies_file}")
