"""ProjectManager.create_project description integrity.

Found by an external sandbox audit (2026-09): create_project's milestone
loop reused the name ``description`` — the function's own parameter — so
after the loop the PROJECT's description silently became the LAST
milestone's text (or an empty string when every milestone entry was
blank). Silent data corruption: the owner's project description is
destroyed exactly when the project has milestones, which is the normal
case for decomposed goals.
"""

from app.cognition.project_manager import ProjectManager


def make_manager(tmp_path):
    return ProjectManager(db_path=str(tmp_path / "projects.db"))


def test_project_description_survives_milestone_creation(tmp_path):
    """The reported bug, verbatim: a project with milestones must keep the
    description it was CREATED with — not the last milestone's text."""
    manager = make_manager(tmp_path)
    project = manager.create_project(
        name="Website Redesign",
        description="Rebuild the marketing site with the new brand system",
        priority="high",
        milestones=[
            {"description": "Audit the current site"},
            {"description": "Design the new homepage"},
            {"description": "Ship the contact page"},
        ],
    )
    assert project.description == ("Rebuild the marketing site "
                                   "with the new brand system"), \
        "project description was clobbered by a milestone's text"


def test_milestone_descriptions_still_land_on_the_milestones(tmp_path):
    """The fix must not break what the loop was FOR: milestone text and
    source sub-goal ids still attach to their milestones."""
    manager = make_manager(tmp_path)
    project = manager.create_project(
        name="P",
        description="project description",
        milestones=[
            {"description": "first step", "source_sub_goal_id": "sg-1"},
            "second step",
        ],
    )
    assert [m.description for m in project.milestones] == \
        ["first step", "second step"]
    assert project.milestones[0].source_sub_goal_id == "sg-1"


def test_blank_milestone_entries_do_not_zero_the_description(tmp_path):
    """Edge of the same bug: with only blank milestone entries the loop's
    last assignment left description == '' — the description was destroyed
    even though no milestone was created at all."""
    manager = make_manager(tmp_path)
    project = manager.create_project(
        name="P",
        description="keep me",
        milestones=[{"description": "   "}, ""],
    )
    assert project.milestones == []
    assert project.description == "keep me"


def test_description_persists_to_db_roundtrip(tmp_path):
    """The corruption is persisted: _save_to_db wrote the clobbered value,
    so the fix must survive a reload too."""
    manager = make_manager(tmp_path)
    manager.create_project(
        name="P",
        description="persisted description",
        milestones=[{"description": "milestone text"}],
    )
    reloaded = ProjectManager(db_path=str(tmp_path / "projects.db"))
    assert reloaded._projects, "project did not persist"
    assert all(
        p.description == "persisted description"
        for p in reloaded._projects.values()
    )
