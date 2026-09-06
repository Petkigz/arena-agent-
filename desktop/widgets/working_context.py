"""WorkingContextCard — the inline 'Working context' card (design review section 4).

While Beanie works, the conversation carries a compact card with what Beanie
is working on (project, objective, memory footprint). The card composes from
the same backend endpoints the web's context panels use — one API contract,
presented in the conversation instead of a permanent side column.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from desktop.theme import BG_SECONDARY, BG_SURFACE, TEXT_MUTED, TEXT_SECONDARY


class WorkingContextCard(QFrame):
    """Compact context card; hidden until Beanie is working and context exists."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = {}
        self.hide()
        self.setStyleSheet(self._card_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self._title = QLabel("Working context")
        self._title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_MUTED};")
        layout.addWidget(self._title)

        for key, label_text in (
            ("project", "Project"),
            ("objective", "Objective"),
            ("memories", "Memories"),
        ):
            row = QLabel("")
            row.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
            row.setWordWrap(True)
            self._rows[key] = (label_text, row)
            layout.addWidget(row)

    # ── card style ─────────────────────────────────────────────────────────
    def _card_style(self) -> str:
        return f"QFrame {{ background: {BG_SECONDARY}; border: 1px solid {BG_SURFACE}; border-radius: 12px; }}"

    # ── API ────────────────────────────────────────────────────────────────
    def set_context(self, context: dict) -> None:
        """Populate from {project, objective, memories}; visible only if something shows."""
        shown = False
        for key, (label_text, row) in self._rows.items():
            value = context.get(key)
            if value in (None, "", 0):
                row.hide()
                continue
            text = f"{label_text}: {value} memories" if key == "memories" else f"{label_text}: {value}"
            row.setText(text)
            row.show()
            shown = True
        self.setVisible(shown)

    def clear(self) -> None:
        self.set_context({})

    def refresh_theme(self) -> None:
        self.setStyleSheet(self._card_style())
        self._title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_MUTED};")
        for _label_text, row in self._rows.values():
            row.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
