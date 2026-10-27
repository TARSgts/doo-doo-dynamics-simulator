import json

import pytest

from opensim.results import refresh_viewer


def test_saved_results_refresh_without_executing_or_changing_data(tmp_path):
    data = {"points": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]],
            "displacement": [[0, 0, 0], [0, 0, 0.1], [0, 0, 0]], "summary": {"element_type": "C3D4"}}
    source = tmp_path / "old.html"
    original = "<script>const simulation = " + json.dumps(data) + ";throw new Error('old renderer must not execute');</script>"
    source.write_text(original, encoding="utf-8")
    target = tmp_path / "cache" / "new.html"
    refresh_viewer(source, target)
    rendered = target.read_text(encoding="utf-8")
    refreshed, _ = json.JSONDecoder().raw_decode(rendered.split("const simulation = ", 1)[1])
    assert refreshed == data
    assert "old renderer must not execute" not in rendered
    assert "createGpuRenderer" in rendered
    assert "__VIEWPORT_CODE__" not in rendered
    assert source.read_text(encoding="utf-8") == original
    assert not list(target.parent.glob("*.tmp"))


def test_unrecognized_viewer_is_rejected_before_replacing_cache(tmp_path):
    source, target = tmp_path / "bad.html", tmp_path / "cache.html"
    source.write_text("<p>No simulation data</p>")
    target.write_text("keep existing cache")
    with pytest.raises(ValueError, match="simulation data"):
        refresh_viewer(source, target)
    assert target.read_text() == "keep existing cache"


def test_viewport_is_a_true_rotation_and_axis_triad_matches_camera(tmp_path):
    """Guards against the mirrored projection: each preset must keep X, Y, Z right-handed on screen."""
    import numpy as np
    sync_api = pytest.importorskip("playwright.sync_api")
    from opensim.results import write_viewer_data
    points = [[0, 0, 0], [1, 0, 0], [0, 0.5, 0], [0, 0, 0.2]]
    data = {"points": points, "faces": [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
            "displacement": [[0, 0, 0]] * 4, "summary": {"element_type": "C3D4", "view": "mesh"}}
    viewer = tmp_path / "viewer.html"
    write_viewer_data(viewer, data)
    expected_toward = {"top": ("Z", 1), "front": ("Y", -1), "flipped-front": ("Y", -1)}
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:
            pytest.skip(f"Chromium unavailable: {error}")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(viewer.as_uri() + "?desktop=1&canvas2d=1")
        for orientation in ("isometric", "front", "top", "flipped-front"):
            page.evaluate("orientation => setViewOrientation(orientation)", orientation)
            page.wait_for_function("() => viewportStats.axisTriad && viewportStats.frames > 1")
            page.wait_for_timeout(100)
            triad = page.evaluate("() => viewportStats.axisTriad")
            # Convert screen-down to screen-up so (right, up, toward) is a right-handed frame.
            frame = np.array([[*triad[axis]["screen"], triad[axis]["toward"]] for axis in "XYZ"]) * [1, -1, 1]
            assert np.linalg.det(frame) == pytest.approx(1, abs=1e-9), orientation
            if orientation in expected_toward:
                axis, sign = expected_toward[orientation]
                assert triad[axis]["toward"] == pytest.approx(sign, abs=1e-9), orientation
        page.evaluate("() => setViewOrientation('isometric')")
        page.wait_for_timeout(100)
        assert page.evaluate("() => viewportStats.axisTriad.Z.toward") > 0  # iso looks down from above
        assert page.evaluate("() => viewportStats.axisTriad.Z.screen[1]") < 0  # with Z pointing up
        browser.close()
    assert not errors
