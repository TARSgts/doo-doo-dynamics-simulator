import pytest

from opensim.cat_language import cat_text
from opensim.workspace import Workspace


def test_joke_translation_keeps_numbers_units_and_identifiers():
    assert cat_text("Solve") == "Do a science, meow"
    assert cat_text("Modal analysis") == "Find da wiggles"
    assert cat_text("Density (kg/m³): 7850.0") == "Chonk density (kg/m³): 7850.0"
    assert cat_text("Mode 3 · 104.611 Hz · C3D10 · -10 N") == "Wiggle 3 · 104.611 Hz · C3D10 · -10 N"


def test_language_preference_is_persistent_and_not_a_model_parameter(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project("My beam")
    before = workspace.get_project(project["id"])
    assert workspace.ui_state()["language"] == "en"
    workspace.set_language("cat")
    assert Workspace(tmp_path).ui_state()["language"] == "cat"
    assert workspace.get_project(project["id"]) == before
    with pytest.raises(ValueError):
        workspace.set_language("dog")


def test_midnight_theme_persists_without_changing_analysis(tmp_path):
    workspace = Workspace(tmp_path)
    project = workspace.create_project('Theme persistence')
    for theme in ('light', 'dark', 'midnight'):
        workspace.set_theme(theme)
        assert Workspace(tmp_path).ui_state()['theme'] == theme
        assert workspace.get_project(project['id']) == project
    with pytest.raises(ValueError):
        workspace.set_theme('unknown')
