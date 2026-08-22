"""Styles — QSS helpers that read current theme globals.

Extracted from desktop/app.py monolith.
"""

from __future__ import annotations

from desktop.theme import BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY, _lighten


def _button_style(bg: str, fg: str) -> str:
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: 10px;"
        f" padding: 10px 14px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {_lighten(bg, 0.15).name()}; }}"
        f"QPushButton:disabled {{ opacity: 0.5; }}"
    )


def _input_style() -> str:
    from desktop.theme import BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY
    return (
        f"QLineEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BG_SURFACE}; border-radius: 8px; padding: 8px 10px; }}"
        f"QComboBox {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BG_SURFACE}; border-radius: 8px; padding: 8px 10px; }}"
    )


def _textarea_style() -> str:
    from desktop.theme import BG_SECONDARY, BG_SURFACE, TEXT_PRIMARY
    return (
        f"QTextEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BG_SURFACE}; border-radius: 8px; padding: 8px; }}"
    )
