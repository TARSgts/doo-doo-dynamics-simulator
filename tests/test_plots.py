import csv
import json
from pathlib import Path
import time

import numpy as np
import pytest

from opensim.plots import (available_plots, load_plot_source, make_plot_data, write_plot_csv, write_plot_figure)
from opensim.workspace import Workspace


def saved_source(tmp_path, study="static", arrays=None):
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Plot test / $ brackets")
    workspace.select_study(project["id"], study)
    kind = {"static": "solve", "modal": "modal", "convergence": "convergence"}[study]
    summary = {"nodes": 3, "tetrahedra": 1, "levels": [{"level": i, "mesh_size_m": 0.01 / i, "tetrahedra": 100 * i ** 3,
                            "values": {"displacement": 0.001 / i, "response": -0.002 / i, "stress": 2e6 * i}} for i in (1, 2, 3)]}
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("plot-job", project["id"], kind, "completed", 0,
                           "{}", json.dumps(summary), None, time.time(), time.time()))
    directory = workspace.job_directory("plot-job") / kind
    directory.mkdir(parents=True)
    points = np.array([[0, 0, 0], [0.1, 0.02, 0], [0.2, 0.02, 0.01]])
    if study == "static":
        values = {"points": points, "displacement": np.array([[0, 0, 0], [1e-3, -2e-3, 0], [0, 0, 3e-3]]),
                  "von_mises_Pa": np.array([0, 1e6, 2e6])}
        if arrays is not None:
            values.update(arrays)
        np.savez(directory / "fields.npz", **values)
    elif study == "modal":
        values = {"points": points, "frequencies_Hz": np.array([10, 20]),
                  "normalized_modes": np.array([[[0, 0, 0], [1, 0, 0], [0, -0.5, 0]], [[0, 0, 0], [0, 0.2, 0], [0, 0, -1]]])}
        if arrays is not None:
            values.update(arrays)
        np.savez(directory / "modes.npz", **values)
    return workspace, project, load_plot_source(workspace, project["id"])


def test_static_scatter_uses_all_nodes_with_signed_components_and_correct_units(tmp_path):
    _, _, source = saved_source(tmp_path)
    data = make_plot_data(source, "displacement-position", axis="y", component="y")
    assert data.kind == "scatter"
    np.testing.assert_allclose(data.x, [0, 20, 20])
    np.testing.assert_allclose(data.y, [0, -2, 0])
    assert "mm" in data.xlabel and "mm" in data.ylabel
    np.testing.assert_allclose(make_plot_data(source, "stress-position").y, [0, 1, 2])
    assert "MPa" in make_plot_data(source, "stress-position").ylabel
    magnitude = make_plot_data(source, "displacement-position")
    np.testing.assert_allclose(magnitude.y, [0, np.sqrt(5), 3])
    assert len(data.columns["node_id"]) == 3


def test_histogram_counts_and_csv_edges_are_the_actual_plotted_bins(tmp_path):
    _, _, source = saved_source(tmp_path)
    data = make_plot_data(source, "stress-distribution", bins=5)
    assert sum(data.y) == 3
    assert "no volume weighting" in data.note
    path, metadata = write_plot_csv(tmp_path / "stress.csv", source, data)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5
    assert sum(int(row["node_count"]) for row in rows) == 3
    np.testing.assert_allclose([float(row["bin_lower_MPa"]) for row in rows], data.x)
    assert json.loads(metadata.read_text())["job_id"] == source.job_id
    assert json.loads(metadata.read_text())["input_revision"] == 0
    with pytest.raises(ValueError):
        make_plot_data(source, "stress-distribution", bins=0)


def test_modal_frequencies_and_shapes_keep_hz_and_dimensionless_units(tmp_path):
    _, _, source = saved_source(tmp_path, "modal")
    frequencies = make_plot_data(source, "frequencies")
    np.testing.assert_array_equal(frequencies.x, [1, 2])
    np.testing.assert_array_equal(frequencies.y, [10, 20])
    assert frequencies.kind == "bar" and "Hz" in frequencies.ylabel
    shape = make_plot_data(source, "mode-position", mode=2, component="z")
    np.testing.assert_allclose(shape.y, [0, 0, -1])
    assert "dimensionless" in shape.ylabel and "20 Hz" in shape.note
    with pytest.raises(ValueError):
        make_plot_data(source, "mode-position", mode=3)


def test_convergence_plots_use_actual_element_counts_and_each_quantity_unit(tmp_path):
    _, _, source = saved_source(tmp_path, "convergence")
    data = make_plot_data(source, "convergence-stress")
    np.testing.assert_array_equal(data.x, [100, 800, 2700])
    np.testing.assert_allclose(data.y, [2, 4, 6])
    assert data.log_x and "MPa" in data.ylabel
    displacement = make_plot_data(source, "convergence-displacement")
    np.testing.assert_allclose(displacement.y, [1, 0.5, 1 / 3])
    response = make_plot_data(source, "convergence-response")
    np.testing.assert_allclose(response.y, [-2, -1, -2 / 3])


def test_no_results_or_stale_revision_cannot_be_loaded_as_current_plots(tmp_path):
    workspace, project, source = saved_source(tmp_path)
    with pytest.raises(ValueError, match="Run the modal"):
        load_plot_source(workspace, project["id"], "modal")
    workspace.set_parameters(project["id"], {"load_N": 500})
    with pytest.raises(ValueError, match="current settings"):
        load_plot_source(workspace, project["id"])
    # An already-open immutable snapshot retains its original revision/data.
    assert source.revision == 0
    assert len(make_plot_data(source, "displacement-position").y) == 3


def test_nonfinite_and_mismatched_archives_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="nonfinite"):
        saved_source(tmp_path / "nan", arrays={"von_mises_Pa": np.array([0, np.nan, 2])})
    with pytest.raises(ValueError, match="does not match"):
        saved_source(tmp_path / "shape", arrays={"displacement": np.zeros((2, 3))})


@pytest.mark.parametrize("study", ["static", "modal", "convergence"])
def test_every_available_plot_exports_png_svg_and_data(tmp_path, study):
    pytest.importorskip("matplotlib")
    _, _, source = saved_source(tmp_path, study)
    for key in available_plots(source):
        data = make_plot_data(source, key)
        png = write_plot_figure(tmp_path / f"{key}.png", source, data)
        svg = write_plot_figure(tmp_path / f"{key}.svg", source, data, dark=True)
        assert png.read_bytes().startswith(b"\x89PNG")
        assert "<svg" in svg.read_text()
        assert "plot-job" in svg.read_text()
        path, _ = write_plot_csv(tmp_path / f"{key}.csv", source, data)
        assert Path(path).stat().st_size > 20


def test_plot_dialog_redraw_preserves_navigation_and_marks_historical_data(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    pytest.importorskip("matplotlib")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog
    from opensim.plot_dialog import PlotDialog
    application = QApplication.instance() or QApplication([])
    workspace, project, source = saved_source(tmp_path)
    dialog = PlotDialog(workspace, source, dark=True)
    try:
        figure = dialog.figure
        callback = dialog.toolbar._id_press
        dialog.component.setCurrentIndex(dialog.component.findData("y"))
        dialog.axis.setCurrentIndex(1)
        assert dialog.figure is figure
        assert callback in figure._canvas_callbacks.callbacks["button_press_event"]
        np.testing.assert_allclose(dialog.data.y, [0, -2, 0])
        dialog.plot_type.setCurrentIndex(dialog.plot_type.findData("stress-distribution"))
        assert not dialog.bins.isHidden() and dialog.axis.isHidden()
        workspace.set_parameters(project["id"], {"load_N": 500})
        dialog.update_banner()
        assert "Historical result" in dialog.banner.text()
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "dialog.svg"), "SVG figure (*.svg)"))
        dialog.save_figure()
        assert "<svg" in (tmp_path / "dialog.svg").read_text()
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "dialog.csv"), "CSV data (*.csv)"))
        dialog.export_csv()
        assert (tmp_path / "dialog.metadata.json").is_file()
    finally:
        dialog.close()
        application.processEvents()


def test_desktop_plots_follow_selected_study_and_refuse_unsolved_or_dirty_inputs(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("matplotlib")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from opensim.desktop import SimulatorWindow
    application = QApplication.instance() or QApplication([])
    workspace, project, _ = saved_source(tmp_path)
    window = SimulatorWindow(workspace)
    try:
        assert window.plots_button.isEnabled()
        dialog = window.show_plots()
        assert dialog.source.study == "static"
        assert dialog.source.job_id == "plot-job"
        assert window.show_plots() is dialog
        workspace.select_study(project["id"], "modal")
        window.refresh()
        assert not window.plots_button.isEnabled()
        with pytest.raises(ValueError, match="Run the modal"):
            window.show_plots()
        workspace.select_study(project["id"], "static")
        window.refresh()
        window.fields["load_N"].setValue(12)
        with pytest.raises(ValueError, match="edited inputs"):
            window.show_plots()
    finally:
        for dialog in list(window.plot_dialogs.values()):
            dialog.close()
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()


def test_plot_tree_action_uses_clicked_project_instead_of_previous_project(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("matplotlib")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from opensim.desktop import SimulatorWindow
    application = QApplication.instance() or QApplication([])
    workspace, first, source = saved_source(tmp_path)
    other = workspace.create_project("Other plotted project")
    with workspace.connect() as connection:
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", ("other-job", other["id"], "solve", "completed", 0,
                           "{}", json.dumps(source.summary), None, time.time(), time.time()))
    directory = workspace.job_directory("other-job") / "solve"
    directory.mkdir(parents=True)
    np.savez(directory / "fields.npz", points=source.arrays["points"], displacement=source.arrays["displacement"] * 2,
             von_mises_Pa=source.arrays["von_mises_Pa"])
    workspace.show_project(other["id"])
    workspace.show_project(first["id"])
    window = SimulatorWindow(workspace)
    window.safe = lambda action: (action(), window.refresh())
    try:
        root = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                    if window.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)[0] == other["id"])
        branch = next(root.child(i) for i in range(root.childCount())
                      if root.child(i).data(0, Qt.ItemDataRole.UserRole + 1) == "static")
        item = next(branch.child(i) for i in range(branch.childCount())
                    if branch.child(i).data(0, Qt.ItemDataRole.UserRole + 2) == "plots")
        window.select_tree_item(item, 0)
        dialog = window.plot_dialogs["other-job"]
        assert dialog.source.project_id == other["id"]
        assert dialog.source.project_name == other["name"]
        assert dialog.data.y[-1] == pytest.approx(6)
        assert window.project_id == other["id"]
    finally:
        for dialog in list(window.plot_dialogs.values()):
            dialog.close()
        window.close()
        window.view.setPage(None)
        window.deleteLater()
        application.processEvents()
