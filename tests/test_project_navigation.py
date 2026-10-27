import json
import time
from pathlib import Path

import pytest

from opensim.workspace import Workspace


def test_close_rename_and_reopen_keep_files_parameters_and_results(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    first = workspace.create_project("First")
    second = workspace.create_project("Second")
    workspace.create_project("Closed library item")
    cad = tmp_path / "my hanger.step"
    cad.write_text("original CAD bytes")
    first = workspace.import_cad(first["id"], cad)
    workspace.show_project(first["id"])
    workspace.show_project(second["id"])
    folder = workspace.root / first["id"]
    result = folder / "retained-result.txt"
    result.write_text("saved result")
    renamed = workspace.rename_project(first["id"], "  Hanger / renamed  ")
    assert renamed == first | {"name": "Hanger / renamed"}
    assert result.read_text() == "saved result"
    assert Path(renamed["cad"]).read_text() == cad.read_text()
    workspace.close_project(second["id"])
    assert workspace.ui_state()["project_id"] == first["id"]
    workspace.close_project(first["id"])
    restored = Workspace(workspace.root)
    assert restored.list_open_projects() == []
    assert restored.ui_state()["project_id"] is None
    assert len(restored.list_projects()) == 3
    restored.show_project(first["id"])
    assert [item["id"] for item in restored.list_open_projects()] == [first["id"]]
    assert restored.get_project(first["id"]) == renamed
    assert result.read_text() == "saved result"
    with pytest.raises(ValueError):
        restored.rename_project(first["id"], " ")
    with pytest.raises(ValueError):
        restored.rename_project(first["id"], "x" * 121)


def test_legacy_workspace_migration_opens_only_selected_project_once(tmp_path):
    workspace = Workspace(tmp_path)
    first, second = workspace.create_project("Legacy one"), workspace.create_project("Legacy two")
    workspace.show_project(first["id"])
    workspace.show_project(second["id"])
    with workspace.connect() as connection:
        connection.execute("DROP TABLE open_projects")
    migrated = Workspace(tmp_path)
    assert [item["id"] for item in migrated.list_open_projects()] == [second["id"]]
    migrated.close_project(second["id"])
    assert Workspace(tmp_path).list_open_projects() == []
    assert len(migrated.list_projects()) == 2


def test_close_does_not_cancel_background_jobs(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("Background job")
    workspace.show_project(project["id"])
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("background", project["id"], "mesh", "running", 0,
                           json.dumps({}), None, None, time.time(), time.time()))
    workspace.close_project(project["id"])
    workspace.rename_project(project["id"], "Still computing")
    assert workspace.get_job("background")["status"] == "running"
    assert workspace.list_open_projects() == []


def test_file_locations_report_model_copy_original_and_latest_run(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Files")
    source = tmp_path / "source.step"
    source.write_text("model")
    project = workspace.import_cad(project["id"], source)
    paths = workspace.project_locations(project["id"])
    assert Path(paths["cad_file"]).read_text() == "model"
    assert Path(paths["source_file"]) == source
    assert Path(paths["project_folder"]) == workspace.root / project["id"]
    assert paths["latest_run"] is None
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("saved", project["id"], "solve", "failed", project["revision"],
                           "{}", None, "test", 1, 2))
    assert Path(workspace.project_locations(project["id"])["latest_run"]) == workspace.job_directory("saved")
    generated = workspace.root / project["id"] / "example.step"
    generated.write_text("new example")
    with workspace.connect() as connection:
        connection.execute("UPDATE projects SET cad=? WHERE id=?", (str(generated), project["id"]))
    assert workspace.project_locations(project["id"])["source_file"] is None
