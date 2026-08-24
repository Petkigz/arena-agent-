"""Mandatory grounding gate for raw mouse/keyboard/hotkey input.

Every raw-coordinate path must refuse to execute unless it can show an exact
window/process grounding, a live process, an immediate target observation, a
freshly captured matching display topology digest, and (for coordinates)
containment inside the grounded display and window region.
"""
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from app.cognition.os_grounding import OSGroundingStore
from app.cognition.raw_input_guard import RawInputGuard
from app.tools.deep_os_controller import DeepOSController
from app.tools.display_topology import DisplayTopologyTool


class P:
    def __init__(self, pid, name, exe):
        self.info = {"pid": pid, "name": name, "exe": exe}


TOPOLOGY = {
    "success": True,
    "available": True,
    "monitors": [
        {"display_id": "display_0", "x": 0, "y": 0, "width": 1920, "height": 1080},
        {"display_id": "display_1", "x": 1920, "y": 0, "width": 1280, "height": 1024},
    ],
    "topology_sha256": "a" * 64,
}


class FakePyAutoGUI:
    calls = []

    @classmethod
    def click(cls, x, y):
        cls.calls.append(("click", x, y))

    @classmethod
    def doubleClick(cls, x, y):
        cls.calls.append(("double", x, y))

    @classmethod
    def write(cls, text, interval=0):
        cls.calls.append(("write", text))

    @classmethod
    def hotkey(cls, *keys):
        cls.calls.append(("hotkey", keys))


def make_grounded_store(tmp_path, *, display_id="display_0", region=None, old_updated_at=False):
    store = OSGroundingStore(tmp_path / "g.db")
    with patch("app.cognition.os_grounding.psutil.process_iter", return_value=[P(42, "editor", "/bin/editor")]):
        r = store.observe_application("editor", executable_path="/bin/editor")
        assert r["verified"] is True
        g = store.bind_window(
            r["grounding"]["grounding_id"],
            window_id="w1", title="Report", display_id=display_id,
            region=region or {"x": 0, "y": 0, "width": 800, "height": 600},
            evidence=["native window probe"],
        )
    if old_updated_at:
        with sqlite3.connect(store.path) as c:
            c.execute("UPDATE os_groundings SET updated_at='2020-01-01T00:00:00+00:00' WHERE grounding_id=?", (g.grounding_id,))
            c.commit()
    return store, g


def live_process_patches():
    return (
        patch("app.cognition.raw_input_guard.psutil.pid_exists", return_value=True),
        patch("app.cognition.raw_input_guard.psutil.Process", return_value=SimpleNamespace(exe=lambda: "/bin/editor")),
    )


def test_missing_grounding_or_digest_is_refused_before_execution():
    FakePyAutoGUI.calls = []
    with patch.dict(sys.modules, {"pyautogui": FakePyAutoGUI}):
        r1 = DeepOSController.mouse_click(10, 20)
        r2 = DeepOSController.type_text("hi", grounding_id="osg_1")
        r3 = DeepOSController.press_hotkey(["ctrl", "s"], expected_topology_sha256="b" * 64)
    for result, reason in ((r1, "missing_grounding"), (r2, "missing_topology_digest"), (r3, "missing_grounding")):
        assert result["success"] is False and result["refused"] is True
        assert result["guard_reason"] == reason
        assert result["attempted"] is False
    assert FakePyAutoGUI.calls == []  # Refusal never touches the input device.


def test_unknown_grounding_is_refused(tmp_path):
    store, _ = make_grounded_store(tmp_path)
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        r = RawInputGuard.authorize("osg_does_not_exist", "a" * 64, store=store)
    assert r["success"] is False and r["guard_reason"] == "unknown_grounding"


def test_grounding_without_window_binding_is_refused(tmp_path):
    store = OSGroundingStore(tmp_path / "g.db")
    with patch("app.cognition.os_grounding.psutil.process_iter", return_value=[P(7, "term", "/bin/term")]):
        r = store.observe_application("term", executable_path="/bin/term")
    gid = r["grounding"]["grounding_id"]
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        out = RawInputGuard.authorize(gid, "a" * 64, store=store)
    assert out["success"] is False and out["guard_reason"] == "grounding_missing_window"


def test_dead_process_or_changed_executable_is_refused(tmp_path):
    store, g = make_grounded_store(tmp_path)
    with patch("app.cognition.raw_input_guard.psutil.pid_exists", return_value=False):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, store=store)
    assert r["guard_reason"] == "process_gone"
    with patch("app.cognition.raw_input_guard.psutil.pid_exists", return_value=True), \
         patch("app.cognition.raw_input_guard.psutil.Process", return_value=SimpleNamespace(exe=lambda: "/somewhere/else")), \
         patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, store=store)
    assert r["guard_reason"] == "executable_changed"


def test_stale_window_observation_is_refused(tmp_path):
    store, g = make_grounded_store(tmp_path, old_updated_at=True)
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, store=store)
    assert r["guard_reason"] == "stale_observation" and r["attempted"] is False


def test_stale_grounding_is_allowed_with_immediate_accessibility_observation(tmp_path):
    store, g = make_grounded_store(tmp_path, old_updated_at=True)
    fresh = {"age_seconds": 1.0, "evidence": ["accessibility_snapshot:a11y_1", "node:node_1"]}
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, fresh_observation=fresh, store=store)
    assert r["success"] is True and r["observation_evidence"] == fresh["evidence"]


def test_topology_unavailable_or_changed_is_refused(tmp_path):
    store, g = make_grounded_store(tmp_path)
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value={"success": False, "error": "no display", "monitors": []}):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, store=store)
    assert r["guard_reason"] == "topology_unavailable"
    changed = dict(TOPOLOGY, topology_sha256="c" * 64)
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=changed):
        r = RawInputGuard.authorize(g.grounding_id, "a" * 64, store=store)
    assert r["guard_reason"] == "topology_changed"
    assert r["observed_topology_sha256"] == "c" * 64


def test_coordinates_must_stay_inside_grounded_display_and_region(tmp_path):
    store, g = make_grounded_store(tmp_path)  # display_0 at 0,0 1920x1080; region 800x600
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        outside_display = RawInputGuard.authorize(g.grounding_id, "a" * 64, coordinate={"x": 5000, "y": 5}, store=store)
        outside_region = RawInputGuard.authorize(g.grounding_id, "a" * 64, coordinate={"x": 900, "y": 5}, store=store)
        inside = RawInputGuard.authorize(g.grounding_id, "a" * 64, coordinate={"x": 50, "y": 50}, store=store)
    assert outside_display["guard_reason"] == "coordinate_outside_display"
    assert outside_region["guard_reason"] == "coordinate_outside_window_region"
    assert inside["success"] is True and inside["observed_display"] == "display_0"


def test_grounding_without_display_requires_point_inside_some_observed_display(tmp_path):
    store, g = make_grounded_store(tmp_path, display_id=None, region={"x": 1920, "y": 0, "width": 1280, "height": 1024})
    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY):
        off = RawInputGuard.authorize(g.grounding_id, "a" * 64, coordinate={"x": 5000, "y": 5}, store=store)
        on = RawInputGuard.authorize(g.grounding_id, "a" * 64, coordinate={"x": 2000, "y": 5}, store=store)
    assert off["guard_reason"] == "coordinate_outside_all_displays"
    assert on["success"] is True and on["observed_display"] == "display_1"


def test_valid_grounded_click_executes_with_honest_focus_observation(tmp_path, monkeypatch):
    store, g = make_grounded_store(tmp_path)
    monkeypatch.setattr(RawInputGuard, "store", store)
    FakePyAutoGUI.calls = []
    with live_process_patches()[0] as p1, live_process_patches()[1] as p2, \
         patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY), \
         patch.dict(sys.modules, {"pyautogui": FakePyAutoGUI}):
        r = DeepOSController.mouse_click(100, 150, grounding_id=g.grounding_id, expected_topology_sha256="a" * 64)
        typed = DeepOSController.type_text("report", grounding_id=g.grounding_id, expected_topology_sha256="a" * 64)
        hot = DeepOSController.press_hotkey(["ctrl", "s"], grounding_id=g.grounding_id, expected_topology_sha256="a" * 64)
    assert r["success"] is True and r["window_id"] == "w1" and r["focus_observation"] == "unknown"
    assert typed["success"] is True and hot["success"] is True
    assert FakePyAutoGUI.calls == [("click", 100, 150), ("write", "report"), ("hotkey", ("ctrl", "s"))]


def test_unavailable_display_reports_failure_not_simulation(tmp_path, monkeypatch):
    store, g = make_grounded_store(tmp_path)
    monkeypatch.setattr(RawInputGuard, "store", store)

    class Broken:
        @staticmethod
        def click(*a, **k):
            raise RuntimeError("no display")

    with live_process_patches()[0], patch.object(DisplayTopologyTool, "capture", return_value=TOPOLOGY), \
         patch.dict(sys.modules, {"pyautogui": Broken}):
        r = DeepOSController.mouse_click(50, 50, grounding_id=g.grounding_id, expected_topology_sha256="a" * 64)
    assert r["success"] is False and r["available"] is False and r["attempted"] is False
    assert "simulated" not in str(r).lower()
