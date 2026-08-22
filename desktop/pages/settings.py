"""SettingsPage — extracted."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget, QFrame

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.settings import DesktopSettings
from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT
from desktop.styles import _button_style, _input_style
from app.utils.logger import app_logger

class SettingsPage(QWidget):
    """Full settings form (shared across web / desktop / Android via the backend).

    Editable: server URL, API key, wake word, voice (Piper), voice speed, theme,
    language, voice on/off, VAD sensitivity, response delay, and fast/main models.
    Everything except the server URL (which is a local QSettings value) is
    persisted on the backend's shared settings store.

    Now supports live theme switching: saving a theme calls on_theme_change so
    MainWindow can re-skin instantly without restart (closes G4).
    """

    def __init__(self, settings: DesktopSettings, client: ArenaBackendClient, on_save, on_theme_change=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._client = client
        self._on_save = on_save
        self._on_theme_change = on_theme_change

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        self._title = QLabel("Settings")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        outer.addWidget(self._title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {BG_PRIMARY};")
        container = QWidget()
        container.setStyleSheet(f"background: {BG_PRIMARY};")
        form = QVBoxLayout(container)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(8)

        def section(label_text: str) -> QLabel:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 700; margin-top: 6px;")
            form.addWidget(lbl)
            return lbl

        def field(label_text: str) -> QLineEdit:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            form.addWidget(lbl)
            edit = QLineEdit()
            edit.setStyleSheet(_input_style())
            form.addWidget(edit)
            return edit

        # ── Connection ──
        section("Connection")
        self.url_input = field("Server URL")
        self.url_input.setText(settings.get("server_url"))
        self.api_key_input = field("API key (optional)")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        # ── Voice ──
        section("Voice")
        self.wake_input = field("Wake word")
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.setStyleSheet(_input_style())
        self.voice_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._voice_label = QLabel("Voice (Piper)")
        self._voice_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        form.addWidget(self._voice_label)
        form.addWidget(self.voice_combo)
        self.speed_input = field("Voice speed (0.5–2.0)")
        self.language_combo = QComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.setStyleSheet(_input_style())
        for lang in ("en_US", "en_GB", "es_ES", "fr_FR", "de_DE", "it_IT", "pt_PT", "nl_NL"):
            self.language_combo.addItem(lang)
        self._lang_label = QLabel("Language")
        self._lang_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        form.addWidget(self._lang_label)
        form.addWidget(self.language_combo)
        self.voice_enabled_check = QCheckBox("Voice enabled")
        self.voice_enabled_check.setStyleSheet(f"color: {TEXT_PRIMARY};")
        form.addWidget(self.voice_enabled_check)
        self.vad_input = field("VAD sensitivity (0–100)")
        self.delay_input = field("Response delay (ms)")

        # ── Appearance ──
        section("Appearance")
        self.theme_combo = QComboBox()
        self.theme_combo.setStyleSheet(_input_style())
        self.theme_combo.addItems(["dark", "light", "system"])
        self._theme_label = QLabel("Theme")
        self._theme_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        form.addWidget(self._theme_label)
        form.addWidget(self.theme_combo)

        # ── Models ──
        section("Models (LM Studio)")
        self.fast_model_combo = QComboBox()
        self.fast_model_combo.setEditable(True)
        self.fast_model_combo.setStyleSheet(_input_style())
        self.fast_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fast_label = QLabel("Fast model")
        self._fast_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        form.addWidget(self._fast_label)
        form.addWidget(self.fast_model_combo)
        self.main_model_combo = QComboBox()
        self.main_model_combo.setEditable(True)
        self.main_model_combo.setStyleSheet(_input_style())
        self.main_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._main_label = QLabel("Main model")
        self._main_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        form.addWidget(self._main_label)
        form.addWidget(self.main_model_combo)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.status_label.setWordWrap(True)
        form.addWidget(self.status_label)

        form.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._save_btn.clicked.connect(self._save)
        outer.addWidget(self._save_btn)

        self._load()

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self._save_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        # Re-apply input styles (they read current globals)
        for w in self.findChildren(QLineEdit):
            w.setStyleSheet(_input_style())
        for w in self.findChildren(QComboBox):
            w.setStyleSheet(_input_style())
        self.voice_enabled_check.setStyleSheet(f"color: {TEXT_PRIMARY};")
        for lbl in [self._voice_label, self._lang_label, self._theme_label, self._fast_label, self._main_label]:
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")

    # ── load / save ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        # Start from the local cache (fast, no network) so the theme + fields
        # are populated even if the backend is offline at startup.
        self._set_combo(self.theme_combo, str(self._settings.get("theme") or "dark"))
        self.wake_input.setText(str(self._settings.get("wake_word") or "hey_arena"))

        # Shared settings (wake word, voice, speed, theme, language, api key, models).
        try:
            data = self._client.get_shared_settings()
            self.wake_input.setText(str(data.get("wake_word", "hey_arena")))
            self.speed_input.setText(str(data.get("voice_speed", 1.0)))
            self.vad_input.setText(str(data.get("vad_sensitivity", 50)))
            self.delay_input.setText(str(data.get("response_delay", 500)))
            self.voice_enabled_check.setChecked(bool(data.get("voice_enabled", True)))
            self.api_key_input.setText(str(data.get("api_key", "")))
            self._set_combo(self.theme_combo, str(data.get("theme", "dark")))
            self._set_combo(self.language_combo, str(data.get("language", "en_US")))
            voice = str(data.get("voice", "en_US-lessac-medium"))
            self._set_combo(self.voice_combo, voice)
            self._set_combo(self.fast_model_combo, str(data.get("fast_model", "")))
            self._set_combo(self.main_model_combo, str(data.get("main_model", "")))
        except BackendConnectionError as e:
            self.status_label.setText(f"⚠ {e}")

        # Piper voices (populate the dropdown).
        try:
            voices = self._client.list_piper_voices()
            for v in voices:
                self.voice_combo.addItem(str(v.get("id", "")), str(v.get("id", "")))
        except BackendConnectionError as e:
            from app.utils.logger import app_logger
            app_logger.warning(f"Could not list Piper voices: {e}")

        # LM Studio models (populate fast/main dropdowns).
        try:
            data = self._client.list_models()
            loaded = data.get("loaded_models") or []
            for m in loaded:
                self.fast_model_combo.addItem(str(m))
                self.main_model_combo.addItem(str(m))
        except BackendConnectionError as e:
            from app.utils.logger import app_logger
            app_logger.warning(f"Could not list models: {e}")

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        if not value:
            return
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(value)

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _save(self) -> None:
        url = self.url_input.text().strip()
        self._settings.set("server_url", url)

        theme = self._combo_text(self.theme_combo)
        self._settings.set("theme", theme)

        voice = self._combo_text(self.voice_combo)
        try:
            # Shared settings: wake word / voice / speed / theme / language / …
            self._client.update_shared_settings({
                "wake_word": self.wake_input.text().strip(),
                "voice": voice,
                "voice_speed": float(self.speed_input.text().strip() or "1.0"),
                "voice_enabled": self.voice_enabled_check.isChecked(),
                "language": self._combo_text(self.language_combo),
                "vad_sensitivity": int(float(self.vad_input.text().strip() or "50")),
                "response_delay": int(float(self.delay_input.text().strip() or "500")),
                "theme": self._combo_text(self.theme_combo),
                "api_key": self.api_key_input.text().strip(),
            })
            # Models (LM Studio).
            self._client.update_model_config(
                fast_model=self._combo_text(self.fast_model_combo),
                main_model=self._combo_text(self.main_model_combo),
            )
            # Ensure the active Piper voice matches (idempotent; /settings already
            # applies it, but this also drives /voice/piper-voices active flag).
            if voice:
                self._client.select_piper_voice(voice)
            self.status_label.setText("✓ Saved — theme applied live.")
            # Live theme switch (G4): re-skin the whole desktop instantly.
            if self._on_theme_change:
                self._on_theme_change(theme)
        except (BackendConnectionError, ValueError) as e:
            self.status_label.setText(f"⚠ Could not save: {e}")

        if self._on_save:
            self._on_save(url)

