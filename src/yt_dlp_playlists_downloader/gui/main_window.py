"""Main window for the downloader GUI."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets, uic

from yt_dlp_playlists_downloader.core.config import build_runtime_settings, load_config
from yt_dlp_playlists_downloader.core.constants import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLAYLISTS_FILE,
)
from yt_dlp_playlists_downloader.core.downloader import run_download
from yt_dlp_playlists_downloader.core.errors import DownloaderError
from yt_dlp_playlists_downloader.core.logging import create_run_log_path
from yt_dlp_playlists_downloader.core.playlists import PLAYLIST_COLUMNS, load_playlist_entries

from .icon_service import apply_widget_icons
from .theme_service import apply_theme, available_theme_names, pick_startup_theme

WINDOW_ICON_REL_PATH = ("assets", "icon.png")


class DownloadWorker(QtCore.QThread):
    log_line = QtCore.Signal(str)
    completed = QtCore.Signal(bool, str)

    def __init__(self, options: dict[str, object]) -> None:
        super().__init__()
        self._options = options

    def run(self) -> None:
        try:
            run_download(logger=self.log_line.emit, **self._options)
        except Exception as exc:
            self.completed.emit(False, str(exc))
            return

        self.completed.emit(True, "")


class MainWindow(QtWidgets.QMainWindow):
    """Qt wrapper around the existing TOML workflow."""

    def __init__(self) -> None:
        super().__init__()
        self._worker: DownloadWorker | None = None
        self._theme_names = available_theme_names()
        self._theme_menu: QtWidgets.QMenu | None = None
        self._theme_actions: dict[str, QtGui.QAction] = {}
        self._is_loading_table = False
        self._has_unsaved_playlist_changes = False
        self._last_log_path: Path | None = None

        self._load_ui()
        self._wire_ui()
        self._load_initial_values()
        self._apply_startup_theme()
        self.refresh_preview()

    def _load_ui(self) -> None:
        ui_resource = importlib.resources.files("yt_dlp_playlists_downloader.gui").joinpath("ui", "main_window.ui")
        with importlib.resources.as_file(ui_resource) as ui_file:
            uic.loadUi(str(ui_file), self)

        icon_resource = importlib.resources.files("yt_dlp_playlists_downloader.gui").joinpath(*WINDOW_ICON_REL_PATH)
        with importlib.resources.as_file(icon_resource) as icon_file:
            if icon_file.exists():
                icon = QtGui.QIcon(str(icon_file))
            else:
                icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowDown)

        self.setWindowIcon(icon)
        QtWidgets.QApplication.setWindowIcon(icon)

        header = self.previewTable.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.progressBar.setRange(0, 0)
        self.progressBar.hide()
        warning_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.unsavedChangesIconLabel.setPixmap(warning_icon.pixmap(16, 16))
        self.unsavedChangesIconLabel.setStyleSheet("font-weight: 700; color: #d97706;")
        self.unsavedChangesLabel.setStyleSheet("font-weight: 600; color: #d97706;")
        self.mainSplitter.setStretchFactor(0, 4)
        self.mainSplitter.setStretchFactor(1, 1)
        self.mainSplitter.setSizes([440, 180])
        self._set_unsaved_playlist_changes(False)

    def _wire_ui(self) -> None:
        self.browsePlaylistsButton.clicked.connect(self._browse_playlists)
        self.browseConfigButton.clicked.connect(self._browse_config)
        self.browseOutputButton.clicked.connect(self._browse_output)
        self.browseCookiesButton.clicked.connect(self._browse_cookies)
        self.refreshSettingsButton.clicked.connect(self.refresh_settings)
        self.refreshPreviewButton.clicked.connect(self.refresh_preview)
        self.addPlaylistRowButton.clicked.connect(self.add_playlist_row)
        self.removePlaylistRowButton.clicked.connect(self.remove_selected_playlist_rows)
        self.savePlaylistsButton.clicked.connect(self.save_playlists)
        self.runButton.clicked.connect(self.start_download)
        self.openLogButton.clicked.connect(self.open_latest_log)
        self.previewTable.itemChanged.connect(self._on_playlist_table_changed)

        self.actionExit.triggered.connect(self.close)
        self.actionUsage.triggered.connect(self._show_usage)
        self.actionAbout.triggered.connect(self._show_about)
        self._theme_menu = self.findChild(QtWidgets.QMenu, "menuThemes")
        self._rebuild_theme_menu()

        apply_widget_icons(self)

    def _rebuild_theme_menu(self) -> None:
        if self._theme_menu is None:
            return

        self._theme_menu.clear()
        self._theme_actions.clear()
        for theme_name in self._theme_names:
            action = self._theme_menu.addAction(theme_name)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, name=theme_name: self._set_theme_from_menu(name, checked)
            )
            self._theme_actions[theme_name] = action

    def _set_theme_from_menu(self, theme_name: str, checked: bool) -> None:
        if checked:
            self._on_theme_changed(theme_name)

    def _load_initial_values(self) -> None:
        self.playlistsEdit.setText(DEFAULT_PLAYLISTS_FILE)
        self.configEdit.setText(DEFAULT_CONFIG_FILE if Path(DEFAULT_CONFIG_FILE).is_file() else "")
        self.refresh_settings()

    def refresh_settings(self) -> None:
        self._apply_settings_from_config()
        self.statusBar().showMessage("Settings refreshed from config.")

    def _apply_settings_from_config(self) -> None:
        settings = self._current_config_settings()

        self.outputEdit.setText(str(settings.get("output_dir", DEFAULT_OUTPUT_DIR)))
        self.maxWorkersSpin.setValue(int(settings.get("max_workers", DEFAULT_MAX_WORKERS)))
        self.keepMetadataCheck.setChecked(bool(settings.get("keep_original_metadata", True)))
        self.normalizeCheck.setChecked(bool(settings.get("enable_normalization", False)))
        self.cookiesEdit.setText(str(settings.get("cookies_file") or ""))

    def _current_config_settings(self) -> dict[str, object]:
        config_path = self.configEdit.text().strip() or None
        if not config_path:
            return {}

        try:
            settings = load_config(config_path).get("settings", {})
        except DownloaderError as exc:
            self.append_log(str(exc))
            return {}

        if settings and not isinstance(settings, dict):
            self.append_log("Config file error: [settings] must be a table.")
            return {}

        return settings

    def _browse_playlists(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose playlists TOML",
            "",
            "TOML files (*.toml);;All files (*)",
        )
        if path:
            self.playlistsEdit.setText(path)
            self.refresh_preview()

    def _browse_config(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose config TOML",
            "",
            "TOML files (*.toml);;All files (*)",
        )
        if path:
            self.configEdit.setText(path)
            self.refresh_settings()
            self.refresh_preview()

    def _browse_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder", self.outputEdit.text())
        if path:
            self.outputEdit.setText(path)

    def _browse_cookies(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose cookies file",
            "",
            "Cookie files (*.txt *.cookies);;All files (*)",
        )
        if path:
            self.cookiesEdit.setText(path)

    def refresh_preview(self) -> None:
        try:
            tasks = load_playlist_entries(self.playlistsEdit.text().strip() or DEFAULT_PLAYLISTS_FILE)
        except DownloaderError as exc:
            self._is_loading_table = True
            self.previewTable.setRowCount(0)
            self._is_loading_table = False
            self._set_unsaved_playlist_changes(False)
            self.statusBar().showMessage("Could not load playlist preview.")
            self.append_log(str(exc))
            return

        self._is_loading_table = True
        self.previewTable.setRowCount(len(tasks))
        for row, (url, artist, album, year, genre, cover_url) in enumerate(tasks):
            for column, value in enumerate([url, artist, album, year, genre, cover_url]):
                self.previewTable.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        self._is_loading_table = False
        self._set_unsaved_playlist_changes(False)

        self.statusBar().showMessage(f"Loaded {len(tasks)} playlist(s).")

    def add_playlist_row(self) -> None:
        row = self.previewTable.rowCount()
        self.previewTable.insertRow(row)
        for column in range(len(PLAYLIST_COLUMNS)):
            self.previewTable.setItem(row, column, QtWidgets.QTableWidgetItem(""))
        self.previewTable.setCurrentCell(row, 0)
        self._set_unsaved_playlist_changes(True)
        self.statusBar().showMessage("Added playlist row.")

    def remove_selected_playlist_rows(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.previewTable.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            self.statusBar().showMessage("Select one or more playlist rows to remove.")
            return

        for row in selected_rows:
            self.previewTable.removeRow(row)
        self._set_unsaved_playlist_changes(True)
        self.statusBar().showMessage(f"Removed {len(selected_rows)} playlist row(s).")

    def save_playlists(self) -> None:
        try:
            entries = self._playlist_entries_from_table()
            self._write_playlists_file(self.playlistsEdit.text().strip() or DEFAULT_PLAYLISTS_FILE, entries)
        except DownloaderError as exc:
            self.append_log(str(exc))
            self.statusBar().showMessage("Could not save playlists.")
            return

        self.statusBar().showMessage(f"Saved {len(entries)} playlist row(s).")
        self._set_unsaved_playlist_changes(False)
        self.append_log(f"Saved playlists file: {self.playlistsEdit.text().strip() or DEFAULT_PLAYLISTS_FILE}")

    def _playlist_entries_from_table(self) -> list[dict[str, str]]:
        entries = []
        for row in range(self.previewTable.rowCount()):
            entry = {}
            for column, field_name in enumerate(PLAYLIST_COLUMNS):
                item = self.previewTable.item(row, column)
                value = item.text().strip() if item is not None else ""
                entry[field_name] = value

            if not any(entry.values()):
                continue
            if not entry.get("url"):
                raise DownloaderError(f"Playlist row {row + 1} requires a URL before saving.")

            entries.append(entry)

        if not entries:
            raise DownloaderError("Add at least one playlist row before saving.")

        return entries

    def _write_playlists_file(self, path: str, entries: list[dict[str, str]]) -> None:
        output = []
        for entry in entries:
            output.append("[[playlists]]")
            for field_name in PLAYLIST_COLUMNS:
                value = entry.get(field_name, "")
                output.append(f'{field_name} = "{self._escape_toml_string(value)}"')
            output.append("")

        try:
            Path(path).write_text("\n".join(output), encoding="utf-8")
        except OSError as exc:
            raise DownloaderError(f"Could not write playlists file {path}: {exc}") from exc

    def _escape_toml_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _on_playlist_table_changed(self, item=None) -> None:
        if not self._is_loading_table:
            self._set_unsaved_playlist_changes(True)

    def _set_unsaved_playlist_changes(self, has_changes: bool) -> None:
        self._has_unsaved_playlist_changes = has_changes
        self.unsavedChangesIconLabel.setVisible(has_changes)
        self.unsavedChangesLabel.setVisible(has_changes)

    def start_download(self) -> None:
        if self._has_unsaved_playlist_changes:
            response = QtWidgets.QMessageBox.question(
                self,
                "Unsaved Playlist Changes",
                "The playlist table has unsaved changes. Run using the last saved playlists.toml file?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Save playlist changes before running downloads.")
                return

        self._last_log_path = Path(create_run_log_path())
        self.openLogButton.setEnabled(False)

        options = {
            "playlists_file_arg": self.playlistsEdit.text().strip() or None,
            "config_file_arg": self.configEdit.text().strip() or None,
            "output_dir": self.outputEdit.text().strip() or None,
            "max_workers": self.maxWorkersSpin.value(),
            "keep_original_metadata": self.keepMetadataCheck.isChecked(),
            "enable_normalization": self.normalizeCheck.isChecked(),
            "cookies_file": self.cookiesEdit.text().strip() or None,
            "log_file": str(self._last_log_path),
        }

        try:
            self._validate_options(options)
        except DownloaderError as exc:
            self.append_log(str(exc))
            self.statusBar().showMessage("Download could not start.")
            return

        self.logEdit.clear()
        self.append_log("Starting download run...")
        self._set_running(True)
        self._worker = DownloadWorker(options)
        self._worker.log_line.connect(self.append_log)
        self._worker.completed.connect(self._on_download_completed)
        self._worker.start()

    def open_latest_log(self) -> None:
        if self._last_log_path is None or not self._last_log_path.is_file():
            self.statusBar().showMessage("No log file is available yet.")
            return

        url = QtCore.QUrl.fromLocalFile(str(self._last_log_path.resolve()))
        if not QtGui.QDesktopServices.openUrl(url):
            self.statusBar().showMessage(f"Could not open log file: {self._last_log_path}")

    def _validate_options(self, options: dict[str, object]) -> None:
        config_data = load_config(options["config_file_arg"]) if options["config_file_arg"] else {}
        args = type("Args", (), options)()
        build_runtime_settings(args, config_data)

    def _on_download_completed(self, success: bool, message: str) -> None:
        self.append_log(message)
        self._set_running(False)
        self.openLogButton.setEnabled(self._last_log_path is not None and self._last_log_path.is_file())
        self.statusBar().showMessage("Download finished." if success else "Download failed.")
        self._worker = None

    def _set_running(self, is_running: bool) -> None:
        for widget in [
            self.playlistsEdit,
            self.configEdit,
            self.outputEdit,
            self.cookiesEdit,
            self.maxWorkersSpin,
            self.keepMetadataCheck,
            self.normalizeCheck,
            self.refreshSettingsButton,
            self.refreshPreviewButton,
            self.addPlaylistRowButton,
            self.removePlaylistRowButton,
            self.savePlaylistsButton,
            self.runButton,
        ]:
            widget.setEnabled(not is_running)
        self.progressBar.setVisible(is_running)

    def append_log(self, message: str) -> None:
        if message:
            self.logEdit.appendPlainText(message)

    def _apply_startup_theme(self) -> None:
        startup_theme = pick_startup_theme(self._theme_names)
        if not startup_theme:
            self.statusBar().showMessage("qt-themes is not installed; using the default Qt theme.")
            apply_widget_icons(self)
            return

        self._on_theme_changed(startup_theme)

    def _on_theme_changed(self, theme_name: str) -> None:
        apply_theme(theme_name)
        apply_widget_icons(self)
        for name, action in self._theme_actions.items():
            blocker = QtCore.QSignalBlocker(action)
            action.setChecked(name == theme_name)
            del blocker
        self.statusBar().showMessage(f"Active theme: {theme_name}")

    def _show_about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "About",
            "yt-dlp Playlists Downloader\n\nA PyQt6 wrapper around the existing TOML workflow.",
        )

    def _show_usage(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Usage",
            (
                "Choose playlists.toml and config.toml files, then refresh settings or preview when needed.\n\n"
                "Edit playlist rows directly in the table. Use Add Row and Remove Row to change the list, "
                "then Save Playlists before running downloads.\n\n"
                "Runtime settings in the GUI override config values for the current run."
            ),
        )

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            QtWidgets.QMessageBox.warning(
                self,
                "Download Running",
                "Wait for the current download to finish before closing.",
            )
            event.ignore()
            return
        event.accept()
