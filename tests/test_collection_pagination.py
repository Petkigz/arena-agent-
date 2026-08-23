"""Large collection endpoints expose stable, non-overlapping pages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.database import DatabaseManager
from app.main import (
    list_memories_page,
    list_projects_endpoint,
    list_workspace_files_page_endpoint,
)


def test_memory_database_pagination_and_category_count(tmp_path):
    database = DatabaseManager(str(tmp_path / "memories.db"))
    for index in range(7):
        database.create_memory({
            "content": f"memory-{index}",
            "category": "alpha" if index < 5 else "beta",
        })

    first = database.get_memories(category="alpha", limit=2, offset=0)
    second = database.get_memories(category="alpha", limit=2, offset=2)

    assert database.count_memories("alpha") == 5
    assert len(first) == 2
    assert len(second) == 2
    assert {item["id"] for item in first}.isdisjoint(
        {item["id"] for item in second}
    )
    # Equal timestamps are made deterministic by the descending id tie-break.
    assert [item["id"] for item in first] == sorted(
        [item["id"] for item in first], reverse=True
    )


def test_memory_page_contract_reports_continuation(tmp_path):
    database = DatabaseManager(str(tmp_path / "memory-page.db"))
    for index in range(3):
        database.create_memory({"content": str(index), "category": "test"})

    with patch("app.main.db", database):
        first = list_memories_page(category="test", limit=2, offset=0)
        second = list_memories_page(category="test", limit=2, offset=2)

    assert first["total"] == 3
    assert first["has_more"] is True
    assert first["next_offset"] == 2
    assert second["has_more"] is False
    assert second["next_offset"] is None
    assert len(second["memories"]) == 1


def _project(index: int, status: str = "active"):
    return SimpleNamespace(
        project_id=f"project-{index}",
        name=f"Project {index}",
        description="",
        status=SimpleNamespace(value=status),
        priority="normal",
        progress_percent=0,
        milestones_total=0,
        milestones_reached=0,
        total_sessions=0,
        tags=[],
        created_at=f"2026-01-{index + 1:02d}T00:00:00",
        updated_at=f"2026-01-{index + 1:02d}T00:00:00",
    )


def test_project_pages_are_sorted_filtered_and_bounded():
    projects = [_project(index) for index in range(6)]
    projects.append(_project(6, status="completed"))
    runtime = SimpleNamespace(
        project_manager=SimpleNamespace(
            _projects={project.project_id: project for project in projects}
        )
    )

    with patch("app.cognition.runtime.CognitiveRuntime.get_instance", return_value=runtime):
        first = list_projects_endpoint(status=None, limit=3, offset=0)
        second = list_projects_endpoint(status=None, limit=3, offset=3)
        completed = list_projects_endpoint(status="completed", limit=3, offset=0)

    assert first["total"] == 7
    assert first["has_more"] is True
    assert first["next_offset"] == 3
    assert {p["project_id"] for p in first["projects"]}.isdisjoint(
        {p["project_id"] for p in second["projects"]}
    )
    assert completed["total"] == 1
    assert completed["projects"][0]["status"] == "completed"


def test_workspace_page_filters_extension_and_has_no_overlap():
    files = [
        {
            "file_name": f"file-{index}.txt" if index % 2 == 0 else f"file-{index}.pdf",
            "relative_path": f"workspace/{index:02d}",
            "extension": ".txt" if index % 2 == 0 else ".pdf",
        }
        for index in range(8)
    ]
    with patch("app.main.DocumentManager.list_workspace_files", return_value=files):
        first = list_workspace_files_page_endpoint(limit=2, offset=0, extension="txt")
        second = list_workspace_files_page_endpoint(limit=2, offset=2, extension=".txt")

    assert first["total"] == 4
    assert first["next_offset"] == 2
    assert all(item["extension"] == ".txt" for item in first["files"])
    assert {item["relative_path"] for item in first["files"]}.isdisjoint(
        {item["relative_path"] for item in second["files"]}
    )
    assert second["has_more"] is False
