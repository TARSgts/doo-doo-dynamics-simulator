import pytest

from opensim.workspace import Workspace


def test_study_selection_is_per_project_persistent_and_does_not_change_physics(tmp_path):
    workspace = Workspace(tmp_path)
    first = workspace.create_project("First")
    second = workspace.create_project("Second")
    workspace.show_project(first["id"])
    for study in ("static", "modal", "convergence"):
        state = workspace.select_study(first["id"], study)
        assert state["study"] == study and state["view"] == "geometry"
        assert workspace.get_project(first["id"]) == first
        assert workspace.list_jobs(first["id"]) == []
    assert Workspace(tmp_path).ui_state()["study"] == "convergence"
    assert workspace.show_project(first["id"], "mesh")["study"] == "convergence"
    assert workspace.show_project(first["id"], "results")["study"] == "static"
    assert workspace.show_project(first["id"], "modal")["study"] == "modal"
    assert workspace.show_project(second["id"])["study"] == "static"
    assert workspace.show_project(first["id"])["study"] == "modal"
    workspace.close_project(first["id"])
    assert workspace.show_project(first["id"])["study"] == "modal"
    with pytest.raises(ValueError):
        workspace.select_study(first["id"], "thermal")


def test_legacy_modal_view_seeds_modal_study_on_migration(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Legacy modal")
    workspace.show_project(project["id"], "modal")
    with workspace.connect() as connection:
        connection.execute("DROP TABLE project_studies")
    assert Workspace(tmp_path).ui_state()["study"] == "modal"
