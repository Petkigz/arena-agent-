"""Styles — QSS helpers that read current theme globals + shared design tokens.

Extracted from desktop/app.py monolith.

All radius / padding / weight values come from design/tokens.json (via
desktop.design_tokens) so the desktop renders the same scale the web compiles
to. State coverage mirrors the web's professional baseline: hover, pressed,
:focus (accent ring — web's focus:ring-2) and :disabled.
"""

from __future__ import annotations

from desktop.theme import _lighten


def _button_style(bg: str, fg: str) -> str:
    from desktop.design_tokens import FOCUS_RING_WIDTH_PX, FONT_WEIGHTS, RADIUS, SPACING
    from desktop.theme import ACCENT, BG_SECONDARY, TEXT_MUTED

    hover = _lighten(bg, 0.15).name()
    pressed = _lighten(bg, -0.15).name()
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: none; border-radius: {RADIUS['lg_px']}px;"
        f" padding: {SPACING['control_padding_y_px']}px {SPACING['control_padding_x_px']}px;"
        f" font-weight: {FONT_WEIGHTS['semibold']}; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:pressed {{ background: {pressed}; }}"
        f"QPushButton:focus {{ border: 1px solid {ACCENT}; }}"
        f"QPushButton:disabled {{ background: {BG_SECONDARY}; color: {TEXT_MUTED}; }}"
    )


def _input_style() -> str:
    from desktop.design_tokens import FOCUS_RING_WIDTH_PX, RADIUS, SPACING
    from desktop.theme import ACCENT, BG_SECONDARY, BORDER_SUBTLE, TEXT_PRIMARY

    pad_y = SPACING["field_padding_y_px"]
    pad_x = SPACING["field_padding_x_px"]
    ring = FOCUS_RING_WIDTH_PX  # compensate padding so text does not shift on focus
    base = (
        f"QLineEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS['lg_px']}px; padding: {pad_y}px {pad_x}px; }}"
        f"QComboBox {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS['lg_px']}px; padding: {pad_y}px {pad_x}px; }}"
    )
    focus = (
        f"QLineEdit:focus {{ border: {ring}px solid {ACCENT}; padding: {pad_y - ring + 1}px {pad_x - ring + 1}px; }}"
        f"QComboBox:focus {{ border: {ring}px solid {ACCENT}; padding: {pad_y - ring + 1}px {pad_x - ring + 1}px; }}"
    )
    return base + focus


def _textarea_style() -> str:
    from desktop.design_tokens import FOCUS_RING_WIDTH_PX, RADIUS, SPACING
    from desktop.theme import ACCENT, BG_SECONDARY, BORDER_SUBTLE, TEXT_PRIMARY

    pad_y = SPACING["field_padding_y_px"]
    ring = FOCUS_RING_WIDTH_PX
    base = (
        f"QTextEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS['lg_px']}px; padding: {pad_y}px; }}"
    )
    focus = f"QTextEdit:focus {{ border: {ring}px solid {ACCENT}; padding: {pad_y - ring + 1}px; }}"
    return base + focus


def _composer_style() -> str:
    """Chat composer input — mirrors the web composer (rounded-2xl, generous padding)."""
    from desktop.design_tokens import FOCUS_RING_WIDTH_PX, RADIUS, SPACING
    from desktop.theme import ACCENT, BG_SECONDARY, BORDER_SUBTLE, TEXT_PRIMARY

    pad_y = SPACING["bubble_padding_y_px"]
    pad_x = SPACING["bubble_padding_x_px"]
    ring = FOCUS_RING_WIDTH_PX
    base = (
        f"QLineEdit {{ background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
        f" border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS['xxl_px']}px; padding: {pad_y}px {pad_x}px; }}"
        f"QLineEdit::placeholder {{ color: {TEXT_PRIMARY}; }}"
    )
    focus = f"QLineEdit:focus {{ border: {ring}px solid {ACCENT}; padding: {pad_y - ring + 1}px {pad_x - ring + 1}px; }}"
    return base + focus


def _app_style() -> str:
    """App-level stylesheet: window canvas + theme-aware scrollbars.

    Mirrors the web scrollbar spec exactly (index.css): 8px, track on
    background-secondary, pill thumb on background-surface, muted on hover —
    so the desktop never shows raw OS scrollbars over the Arena palette.
    """
    from desktop.design_tokens import RADIUS
    from desktop.theme import BG_PRIMARY, BG_SECONDARY, BG_SURFACE, TEXT_MUTED

    thumb_radius = max(2, RADIUS["sm_px"] // 2)  # pill for an 8px-wide thumb
    return (
        f"QMainWindow {{ background: {BG_PRIMARY}; }}"
        f"QScrollBar:vertical {{ background: {BG_SECONDARY}; width: 8px; margin: 0; }}"
        f"QScrollBar:horizontal {{ background: {BG_SECONDARY}; height: 8px; margin: 0; }}"
        f"QScrollBar::handle:vertical {{ background: {BG_SURFACE}; border-radius: {thumb_radius}px; min-height: 24px; }}"
        f"QScrollBar::handle:horizontal {{ background: {BG_SURFACE}; border-radius: {thumb_radius}px; min-width: 24px; }}"
        f"QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}"
        f"QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}"
        f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}"
        f"QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
    )
