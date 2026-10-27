import numpy as np
import pytest

from opensim.geometry import import_and_mesh, make_box
from opensim.loads import assemble_load
from opensim.region_settings import validate_region
from opensim.regions import selected_faces, support_nodes
from opensim.stress import read_stress, von_mises
from opensim.cli import solve


@pytest.mark.parametrize("region", [{"faces": [True]}, {"faces": [1.5]}, {"faces": [-1]}, {"unknown": 1},
                                    {"faces": []}, {"box_m": [0, 0, 0, 1, 0, 1]}, {"box_m": [0, 0, 0, 1, 1, float("nan")]}])
def test_invalid_regions_are_rejected(region):
    with pytest.raises(ValueError):
        validate_region(region)


def test_von_mises_uniaxial_hydrostatic_and_pure_shear():
    stress = np.array([[100, 0, 0, 0, 0, 0], [100, 100, 100, 0, 0, 0], [0, 0, 0, 10, 0, 0]])
    np.testing.assert_allclose(von_mises(stress), [100, 0, np.sqrt(3) * 10])


def test_frd_stress_parser_requires_complete_finite_tensor(tmp_path):
    names = ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]
    header = " -4 STRESS\n" + "".join(f" -5 {name}\n" for name in names)
    row = " -1" + f"{1:10d}" + "".join(f"{value:12.5E}" for value in [100, -50, 10, -2, 3, 4])
    path = tmp_path / "stress.frd"
    path.write_text(header + row + "\n -3\n")
    np.testing.assert_allclose(read_stress(path, 1), [[100, -50, 10, -2, 3, 4]])
    with pytest.raises(ValueError):
        read_stress(path, 2)
    path.write_text(header + row + "\n" + row + "\n -3\n")
    with pytest.raises(ValueError):
        read_stress(path, 1)


@pytest.mark.integration
def test_custom_face_regions_match_uniform_bar_and_unit_conversion(tmp_path):
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    cad = tmp_path / "bar.step"
    make_box(cad, (1, 0.1, 0.1))
    mesh = import_and_mesh(cad, 0.05, 1, tmp_path / "mesh.msh", order=2)
    minimum = [int(tag) for tag, faces in mesh.surface_groups.items() if np.allclose(mesh.points[np.asarray(faces), 0], 0, atol=1e-8)]
    maximum = [int(tag) for tag, faces in mesh.surface_groups.items() if np.allclose(mesh.points[np.asarray(faces), 0], 1, atol=1e-8)]
    assert len(minimum) == len(maximum) == 1
    assert len(mesh.surface_catalog()) == 6
    load = assemble_load(mesh, 1000, "x", "traction", "x-max", {"faces": maximum})
    np.testing.assert_allclose(load.forces, assemble_load(mesh, 1000, "x", "traction", "x-max").forces)
    assert len(support_nodes(mesh, {"faces": minimum})) > 3
    with pytest.raises(ValueError):
        selected_faces(mesh, {"faces": [9999]})
    result = solve(cad, tmp_path / "custom", size=0.05, young=210e9, poisson=0, load=-1000, order=2,
                   load_axis="x", load_kind="traction", support_region={"faces": maximum}, load_region={"faces": minimum})
    assert result["loaded_surface_mean_displacement_m"][0] == pytest.approx(-1000 / (210e9 * 0.01), rel=1e-5)
    assert result["maximum_von_mises_Pa"] == pytest.approx(100000, rel=1e-4)
    assert result["reaction_N"][0] == pytest.approx(1000, rel=1e-5)
    assert result["relative_moment_imbalance"] < 1e-5
    from opensim.modal import solve_modal
    baseline = solve_modal(cad, tmp_path / "modal-si", size=0.05, mode_count=2)
    scaled = solve_modal(cad, tmp_path / "modal-mm", size=0.05, mode_count=2, support_region={"faces": minimum})
    np.testing.assert_allclose(scaled["frequencies_Hz"], baseline["frequencies_Hz"], rtol=1e-5)


def test_importing_new_cad_clears_regions_bound_to_previous_topology(tmp_path):
    from opensim.workspace import Workspace
    workspace = Workspace(tmp_path / "workspace")
    project = workspace.create_project("Regions")
    workspace.set_parameters(project["id"], {"load_kind": "traction", "support_region": {"faces": [1]}, "load_region": {"faces": [2]}})
    path = tmp_path / "new.step"
    path.write_text("CAD is imported by the worker later")
    updated = workspace.import_cad(project["id"], str(path))
    assert updated["parameters"]["support_region"] == {}
    assert updated["parameters"]["load_region"] == {}
