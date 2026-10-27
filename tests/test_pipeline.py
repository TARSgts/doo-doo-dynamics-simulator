from pathlib import Path

import numpy as np
import pytest

from opensim.cli import solve
from opensim.geometry import Mesh, import_and_mesh, make_box
from opensim.results import write_vtk
from opensim.solver import find_solver, parse_dat, run_solver, write_deck


def test_boundary_surface_omits_shared_face():
    mesh = Mesh(np.zeros((5, 3)), np.array([[0, 1, 2, 3], [0, 1, 2, 4]]))
    assert len(mesh.boundary_faces()) == 6
    assert [0, 1, 2] not in mesh.boundary_faces()


@pytest.mark.parametrize("contents", [
    "displacements\n1 0 0 0\nforces\n1 -1 0 0\n",
    "displacements\n1 NaN 0 0\n2 0 0 0\nforces\n1 -1 0 0\n",
    "displacements\n1 0 0 0\n1 1 1 1\n2 0 0 0\n",
])
def test_rejects_incomplete_nonfinite_or_duplicate_results(tmp_path, contents):
    result = tmp_path / "model.dat"
    result.write_text(contents)
    with pytest.raises(ValueError):
        parse_dat(result, 2)


def test_parses_actual_dat_style_and_fortran_exponents(tmp_path):
    result = tmp_path / "model.dat"
    result.write_text(" displacements (vx,vy,vz) for set NALL and time 1.0\n\n"
                      " 1 0.000000E+00 0.000000E+00 0.000000E+00\n"
                      " 2 1.000000D-03 0.000000E+00 0.000000E+00\n\n"
                      " forces (fx,fy,fz) for set FIX and time 1.0\n\n"
                      " 1 -1.000000E+03 0.000000E+00 0.000000E+00\n")
    vectors, reactions = parse_dat(result, 2)
    assert vectors[1, 0] == 0.001
    assert reactions[1][0] == -1000


@pytest.fixture
def bar_mesh(tmp_path):
    cad = tmp_path / "bar.step"
    make_box(cad)
    return import_and_mesh(cad, 0.05, 1.0, tmp_path / "mesh.msh")


@pytest.mark.parametrize("young,poisson,load", [(0, 0.3, 1), (1, 0.5, 1), (1, 0.3, float('nan'))])
def test_rejects_invalid_material_and_load(bar_mesh, tmp_path, young, poisson, load):
    with pytest.raises(ValueError):
        write_deck(bar_mesh, tmp_path / "bad.inp", young, poisson, load)


def test_mesh_scaling_and_vtk_connectivity(tmp_path):
    cad = tmp_path / "millimeters.step"
    make_box(cad, (1000, 100, 100))
    mesh = import_and_mesh(cad, 0.05, 0.001, tmp_path / "mesh.msh")
    np.testing.assert_allclose(np.ptp(mesh.points, axis=0), [1, 0.1, 0.1], atol=1e-8)
    assert mesh.tetrahedra.min() >= 0
    assert mesh.tetrahedra.max() < len(mesh.points)
    vtk = tmp_path / "results.vtk"
    write_vtk(vtk, mesh, np.zeros_like(mesh.points))
    assert f"CELLS {len(mesh.tetrahedra)} {5 * len(mesh.tetrahedra)}" in vtk.read_text()


def test_rejects_unsupported_or_missing_cad(tmp_path):
    with pytest.raises(ValueError, match="Supported CAD"):
        import_and_mesh(tmp_path / "untrusted.geo", 0.1, 1, tmp_path / "mesh.msh")
    with pytest.raises(FileNotFoundError):
        import_and_mesh(tmp_path / "missing.step", 0.1, 1, tmp_path / "mesh.msh")


def test_solver_failure_and_timeout_keep_log(tmp_path, monkeypatch):
    import subprocess

    class FakeProcess:
        def __init__(self, stdout="", hang=False):
            self.stdout_text, self.hang, self.returncode, self.killed = stdout, hang, None, False

        def communicate(self, timeout=None):
            if self.hang and not self.killed:
                raise subprocess.TimeoutExpired("ccx", timeout)
            self.returncode = -9 if self.killed else 0
            return self.stdout_text, ""

        def kill(self):
            self.killed = True

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess("*ERROR invalid material"))
    with pytest.raises(RuntimeError, match="successfully"):
        run_solver(Path("ccx"), tmp_path)
    assert "*ERROR" in (tmp_path / "solver.log").read_text()

    hung = FakeProcess(hang=True)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: hung)
    with pytest.raises(RuntimeError, match="exceeded"):
        run_solver(Path("ccx"), tmp_path, timeout=1)
    assert hung.killed


@pytest.mark.integration
def test_real_cad_mesh_solve_matches_axial_bar_and_equilibrium(tmp_path):
    try:
        executable = find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX not available")
    cad = tmp_path / "bar.step"
    make_box(cad)
    coarse = solve(cad, tmp_path / "coarse", size=0.05, ccx=str(executable))
    fine = solve(cad, tmp_path / "fine", size=0.035, ccx=str(executable))
    exact = 1000.0 * 1.0 / (210e9 * 0.1 * 0.1)
    for summary in (coarse, fine):
        assert summary["mean_loaded_ux_m"] == pytest.approx(exact, rel=0.02)
        assert summary["reaction_N"][0] == pytest.approx(-1000, rel=1e-5)
        assert summary["relative_force_imbalance"] < 1e-5
    assert fine["tetrahedra"] > coarse["tetrahedra"]
    assert abs(fine["mean_loaded_ux_m"] - coarse["mean_loaded_ux_m"]) / exact < 0.03
    for name in ("mesh.msh", "model.inp", "model.dat", "model.frd", "results.vtk", "results.html", "manifest.json"):
        assert (tmp_path / "fine" / name).is_file()
    with pytest.raises(FileExistsError):
        solve(cad, tmp_path / "fine", ccx=str(executable))


@pytest.mark.parametrize("extension", [".iges", ".brep"])
def test_other_cad_formats(tmp_path, extension):
    cad = tmp_path / f"bar{extension}"
    make_box(cad)
    mesh = import_and_mesh(cad, 0.05, 1.0, tmp_path / "mesh.msh")
    np.testing.assert_allclose(np.ptp(mesh.points, axis=0), [1, 0.1, 0.1], atol=1e-6)


def test_rejects_multiple_solids_and_invalid_mesh_parameters(tmp_path):
    import gmsh
    from opensim.geometry import gmsh_session

    cad = tmp_path / "two.step"
    with gmsh_session():
        gmsh.model.add("two")
        gmsh.model.occ.addBox(0, 0, 0, 1, 1, 1)
        gmsh.model.occ.addBox(2, 0, 0, 1, 1, 1)
        gmsh.model.occ.synchronize()
        gmsh.write(str(cad))
    with pytest.raises(ValueError, match="one closed solid"):
        import_and_mesh(cad, 0.1, 1, tmp_path / "mesh.msh")
    with pytest.raises(ValueError, match="positive and finite"):
        import_and_mesh(cad, -0.1, 1, tmp_path / "mesh.msh")
