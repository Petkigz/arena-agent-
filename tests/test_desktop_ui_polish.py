"""Desktop UI polish (round-21c): progressive context panel + professional QSS states.

QSS helper tests run EVERYWHERE (Qt stubbed when no GUI runtime exists — the
helpers only need QColor for _lighten). True widget tests run OFFSCREEN and
skip automatically where no Qt GUI runtime exists, so clean CI is unaffected.
"""

import pytest


def _import_styles():
    """Import desktop.styles; when no GUI runtime exists, stub QtGui for the session.

    desktop.styles' helpers re-import desktop.theme at CALL time (function-local
    imports, the fresh-values pattern), so a stub that is torn down immediately
    would break on the next call. When real Qt is unavailable we therefore
    install a minimal PySide6.QtGui stand-in (QColor only) and leave it in
    sys.modules — real-Qt machines never stub, and Qt widget tests skip anyway.
    """
    import importlib
    import sys
    import types

    try:
        from PySide6.QtGui import QColor  # noqa: F401

        return importlib.import_module("desktop.styles")
    except Exception:
        pass

    gui = types.ModuleType("PySide6.QtGui")

    class _QColor:
        def __init__(self, *args, **kwargs):
            self._args = args

        def red(self):
            return 0

        def green(self):
            return 0

        def blue(self):
            return 0

        def name(self):
            return "#000000"

    gui.QColor = _QColor
    sys.modules["PySide6.QtGui"] = gui
    sys.modules.pop("desktop.theme", None)
    sys.modules.pop("desktop.styles", None)
    importlib.import_module("desktop.theme")
    return importlib.import_module("desktop.styles")


def test_button_style_covers_professional_states():
    styles = _import_styles()
    qss = styles._button_style("#3B82F6", "#FFFFFF")
    for state in (":hover", ":pressed", ":focus", ":disabled"):
        assert state in qss, f"_button_style lost {state}"
    # Web-canonical geometry: rounded-lg + py-2 px-4.
    assert "border-radius: 8px" in qss
    assert "padding: 8px 16px" in qss


def test_input_style_has_focus_ring():
    styles = _import_styles()
    qss = styles._input_style()
    assert ":focus" in qss
    assert "border-radius: 8px" in qss
    assert "padding: 8px 12px" in qss


def test_composer_style_matches_web_composer():
    styles = _import_styles()
    qss = styles._composer_style()
    assert "border-radius: 16px" in qss  # web composer is rounded-2xl
    assert ":focus" in qss


@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # missing system GL/Qt runtime libs
        pytest.skip(f"Qt GUI runtime unavailable: {exc}")
    yield app


def test_context_panel_collapses(qapp):
    from desktop.widgets.context import ContextPanel

    fired = []
    panel = ContextPanel(on_collapsed=fired.append)
    try:
        assert panel.collapsed is False
        assert panel.width() == ContextPanel.EXPANDED_WIDTH
        assert not panel.body.isHidden()

        panel.toggle_collapsed()
        assert panel.collapsed is True
        assert panel.width() == ContextPanel.COLLAPSED_WIDTH
        assert panel.body.isHidden()
        assert panel._title.isHidden()
        assert fired == [True]

        panel.toggle_collapsed()
        assert panel.collapsed is False
        assert panel.width() == ContextPanel.EXPANDED_WIDTH
        assert not panel.body.isHidden()
        assert fired == [True, False]
    finally:
        panel.deleteLater()


def test_context_panel_starts_collapsed_without_notifying(qapp):
    from desktop.widgets.context import ContextPanel

    fired = []
    panel = ContextPanel(collapsed=True, on_collapsed=fired.append)
    try:
        assert panel.collapsed is True
        assert panel.width() == ContextPanel.COLLAPSED_WIDTH
        assert panel.body.isHidden()
        assert fired == []  # the initial state must not fire the callback
        panel.set_collapsed(True)  # idempotent: no callback spam
        assert fired == []
    finally:
        panel.deleteLater()
