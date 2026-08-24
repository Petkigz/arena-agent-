import pytest
from pathlib import Path
import tempfile
from app.tools.deep_os_controller import DeepOSController
from app.tools.android_adb_controller import AndroidADBController
from app.tools.universal_filesystem import UniversalFilesystem
from app.tools.data_analyzer import DataAnalysisEngine

def test_deep_os_controller(monkeypatch):
    """Raw input without exact grounding is refused before touching any device."""
    import sys
    from types import SimpleNamespace

    broken = SimpleNamespace(
        click=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no display")),
        doubleClick=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no display")),
        write=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no display")),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", broken)
    res = DeepOSController.mouse_click(100, 200)
    type_res = DeepOSController.type_text("Hello World")

    assert res["success"] is False and res["refused"] is True
    assert res["guard_reason"] == "missing_grounding" and res["attempted"] is False
    assert type_res["success"] is False and type_res["refused"] is True
    assert broken is not None

def test_android_adb_controller():
    devs = AndroidADBController.list_connected_devices()
    assert devs["success"] is True
    assert "connected_android_devices" in devs

def test_universal_filesystem_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source_file.txt"
        dst = Path(tmpdir) / "moved_file.txt"
        with open(src, "w", encoding="utf-8") as f:
            f.write("Universal Filesystem Test Content")

        # Search
        search_res = UniversalFilesystem.search_filesystem("source_file", root_dir=tmpdir)
        assert len(search_res) >= 1

        # Move / Rename
        move_res = UniversalFilesystem.rename_or_move(str(src), str(dst))
        assert move_res["success"] is True
        assert dst.exists()

def test_data_analysis_and_chart():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test_data.csv"
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Month,Revenue\nJan,1000\nFeb,1500\nMar,2200\n")

        # Analyze
        analysis = DataAnalysisEngine.analyze_dataset(str(csv_file))
        assert analysis["success"] is True
        assert analysis["rows_count"] == 3

        # Generate Chart
        chart = DataAnalysisEngine.generate_chart_visualization(str(csv_file), "Month", "Revenue", chart_type="bar")
        assert chart["success"] is True
        assert Path(chart["chart_file_path"]).exists()
