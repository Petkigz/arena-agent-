"""LoRA page — continual learning via LoRA adapters (P3 AGI).

Extracted as modular page for desktop.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.theme import TEXT_PRIMARY, BG_SECONDARY, BG_SURFACE, ACCENT
from desktop.styles import _button_style, _input_style, _textarea_style


class LoraPage(QWidget):
    """LoRA continual learning — list, activate, deactivate, status."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("LoRA — Continual Learning")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        desc = QLabel("LoRA enables the agent to get better at seen tasks without catastrophic forgetting. Adapters live in data/loras/.")
        desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.refresh_btn.clicked.connect(self._load)
        row.addWidget(self.refresh_btn)

        self.deactivate_btn = QPushButton("Deactivate (base model)")
        self.deactivate_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.deactivate_btn.clicked.connect(self._deactivate)
        row.addWidget(self.deactivate_btn)

        layout.addLayout(row)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        layout.addWidget(self.list, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(_textarea_style())
        self.detail.setFixedHeight(120)
        layout.addWidget(self.detail)

        self.list.itemClicked.connect(self._on_item_clicked)

        self._load()

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.refresh_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.deactivate_btn.setStyleSheet(_button_style(BG_SURFACE, TEXT_PRIMARY))
        self.list.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BG_SURFACE}; border-radius: 8px;"
        )
        self.detail.setStyleSheet(_textarea_style())

    def _load(self) -> None:
        self.list.clear()
        try:
            data = self._client.lora_status()
            adapters = data.get("adapters", []) if isinstance(data, dict) else []
            active = data.get("active")
            datasets = data.get("datasets", [])

            self.detail.setPlainText(
                f"Active: {active or '(none — base model)'}\n"
                f"Adapters: {len(adapters)}\n"
                f"Datasets: {', '.join(datasets) if datasets else '(none)'}\n"
                f"Dir: {data.get('loras_dir','')}\n"
                f"Note: {data.get('note','')}"
            )

            for a in adapters[:100]:
                label = f"{a.get('name','')} — {a.get('base_model','')} — {a.get('size_mb',0)} MB"
                if a.get("name") == active:
                    label += " [ACTIVE]"
                self.list.addItem(label)

            if not adapters:
                self.list.addItem("(no adapters yet — prepare dataset via /loras/dataset then train)")

        except Exception as e:
            self.list.addItem(f"⚠ {e}")
            self.detail.setPlainText(f"⚠ {e}")

    def _deactivate(self) -> None:
        try:
            from desktop.backend_client import ArenaBackendClient
            client = ArenaBackendClient(base_url=self._client.base_url, timeout=10.0)
            try:
                client._client.post(f"{client.base_url}/loras/deactivate").raise_for_status()
            finally:
                client.close()
            self._load()
        except Exception as e:
            self.detail.setPlainText(f"⚠ Could not deactivate: {e}")

    def _on_item_clicked(self, item) -> None:
        text = item.text()
        name = text.split(" — ")[0].strip()
        if not name or name.startswith("(") or name.startswith("⚠"):
            return
        try:
            res = self._client.activate_lora(name)
            self.detail.setPlainText(f"Activate result: {res}")
            self._load()
        except Exception as e:
            self.detail.setPlainText(f"⚠ Could not activate {name}: {e}")
