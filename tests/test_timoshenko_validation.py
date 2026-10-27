import numpy as np
import pytest

from opensim.timoshenko_validation import timoshenko_components, run_timoshenko_validation


def test_timoshenko_independent_tip_values_and_shear_scaling():
    bending, shear = timoshenko_components(np.array([0, 0.5, 1]))
    assert bending[0] == shear[0] == 0
    assert bending[-1] == pytest.approx(-0.0011904761904761905)
    assert shear[-1] == pytest.approx(-3.714285714285714e-7)
    assert shear[-1] / bending[-1] == pytest.approx(0.000312)
    double_bending, double_shear = timoshenko_components(2, length=2)
    assert double_bending == pytest.approx(8 * bending[-1])
    assert double_shear == pytest.approx(2 * shear[-1])
    control_bending, control_shear = timoshenko_components(0.1, length=0.1, poisson=0)
    assert control_shear / control_bending == pytest.approx(0.024)
    assert control_bending + control_shear == pytest.approx(-1.219047619047619e-6)
    reversed_bending, reversed_shear = timoshenko_components(1, force=10)
    assert reversed_bending == pytest.approx(-bending[-1])
    assert reversed_shear == pytest.approx(-shear[-1])


@pytest.mark.parametrize("parameters", [{"length": 0}, {"width": -1}, {"height": float("nan")},
                                      {"young": float("inf")}, {"poisson": 0.5}, {"shear_factor": 0}])
def test_timoshenko_rejects_invalid_physical_parameters(parameters):
    with pytest.raises(ValueError):
        timoshenko_components(0, **parameters)


def test_timoshenko_rejects_coordinates_outside_span():
    for coordinate in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError, match="Coordinates"):
            timoshenko_components(coordinate)


@pytest.mark.integration
def test_real_timoshenko_thin_beam_shear_control_and_poisson_diagnostic(tmp_path):
    pytest.importorskip("matplotlib")
    from opensim.solver import find_solver
    try:
        find_solver()
    except FileNotFoundError:
        pytest.skip("CalculiX unavailable")
    report = run_timoshenko_validation(tmp_path / "validation")
    assert report["result"] == "PASS"
    assert all(report["criteria"].values())
    thin, control, diagnostic = report["studies"]
    assert thin["length_over_height"] == 50
    assert control["cases"][-1]["excess_over_bending_divided_by_theoretical_shear"] == pytest.approx(1, abs=0.1)
    for study in report["studies"]:
        assert len(study["cases"]) == 3
        assert study["cases"][-1]["elements"] > study["cases"][0]["elements"]
        assert study["cases"][-1]["reaction_z_N"] == pytest.approx(10, rel=1e-5)
        assert study["cases"][-1]["root_moment_y_Nm"] == pytest.approx(-10 * study["geometry_m"][0], rel=1e-5)
    assert diagnostic["poisson"] == 0.3
    assert (tmp_path / "validation" / "validation.png").is_file()
    with pytest.raises(FileExistsError):
        run_timoshenko_validation(tmp_path / "validation")
