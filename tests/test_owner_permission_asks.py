"""Owner charter §2: file-scope and conflict points ASK, they never refuse.

Every converted site returns a typed ``requires_owner_approval`` result with
the real conflict stated, and proceeds once the owner's approval is expressed
through the explicit retry flag."""

from pathlib import Path

from app.tools.universal_filesystem import UniversalFilesystem


def _write(tmp_path, name, content="data"):
    target = tmp_path / name
    target.write_text(content)
    return target


def test_copy_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    dst = _write(tmp_path, "dst.txt", "existing")

    ask = UniversalFilesystem.copy_file_verified(str(src), str(dst))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"
    assert Path(ask["destination"]) == dst
    assert dst.read_text() == "existing"  # untouched while asking

    granted = UniversalFilesystem.copy_file_verified(str(src), str(dst), overwrite=True)
    assert granted["success"] is True
    assert dst.read_text() == "data"


def test_move_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    dst = _write(tmp_path, "dst.txt", "existing")

    ask = UniversalFilesystem.rename_or_move(str(src), str(dst))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"
    assert src.exists()  # untouched while asking

    granted = UniversalFilesystem.rename_or_move(str(src), str(dst), overwrite=True)
    assert granted["success"] is True
    assert not src.exists()


def test_zip_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    archive = _write(tmp_path, "out.zip", "old archive")

    ask = UniversalFilesystem.compress_zip([str(src)], str(archive))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"

    granted = UniversalFilesystem.compress_zip([str(src)], str(archive), overwrite=True)
    assert granted["success"] is True


def test_trash_outside_home_asks_before_anything_moves(tmp_path):
    inside = _write(tmp_path, "inside.txt")
    outside = Path(tmp_path.parent) / "outside-charter-test.txt"
    outside.write_text("outside")

    try:
        ask = UniversalFilesystem.trash_files([str(inside), str(outside)])
        # The ask fires BEFORE any move: nothing is trashed yet.
        assert ask["requires_owner_approval"] is True
        assert ask["conflict"] == "outside_home_scope"
        assert any(p.endswith("outside-charter-test.txt") for p in ask["paths"])
        assert inside.exists() and outside.exists()

        granted = UniversalFilesystem.trash_files(
            [str(inside), str(outside)], trash_root=str(tmp_path / ".arena_trash"),
            allow_outside_home=True,
        )
        assert granted["success"] is True
        assert not inside.exists() and not outside.exists()
    finally:
        if outside.exists():
            outside.unlink()
