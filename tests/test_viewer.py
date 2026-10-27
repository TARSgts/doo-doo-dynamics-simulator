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
