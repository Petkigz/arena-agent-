"""FilesPage — extracted from monolithic app.py."""

from __future__ import annotations


from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.theme import BG_SECONDARY, BORDER_SUBTLE, TEXT_PRIMARY, ACCENT
from desktop.styles import _button_style, _input_style



class FilesPage(QWidget):
    """File search — mirrors the web Files page."""

    def __init__(self, client: ArenaBackendClient, parent=None):
        super().__init__(parent)
        self._client = client
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._title = QLabel("Files")
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(self._title)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search files…")
        self.input.setStyleSheet(_input_style())
        self.input.returnPressed.connect(self._search)
        row.addWidget(self.input, 1)
        self._search_btn = QPushButton("Search")
        self._search_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._search_btn.clicked.connect(self._search)
        row.addWidget(self._search_btn)
        layout.addLayout(row)

        self.results = QListWidget()
        self.results.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )
        layout.addWidget(self.results, 1)

    def refresh_theme(self) -> None:
        self._title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        self.input.setStyleSheet(_input_style())
        self._search_btn.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self.results.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )

    def _search(self) -> None:
        q = self.input.text().strip()
        if not q:
            return
        self.results.clear()
        try:
            res = self._client.search_files(q)
            results = res if isinstance(res, list) else res.get("results", [])
            for item in results[:100]:
                self.results.addItem(str(item.get("name") or item.get("path") or item))
            if not results:
                self.results.addItem("(no results)")
        except BackendConnectionError as e:
            self.results.addItem(f"⚠ {e}")

