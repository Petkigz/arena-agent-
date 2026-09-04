"""Probe-evidence rendering (owner run 2026-09-04, D7 live failure).

The investigation summary rendered each probe output as str()[:80] —
for a search result that slice ends inside the first dict's opening
keys, so the found file PATH never appeared in the executed-actions
evidence nor in the model's grounding instruction. D7's marker WAS
found by the probe; the evidence layer buried it. Path-bearing results
must render as raw paths (not JSON-escaped — D7 matches the plain
str(marker_path) in the evidence blob)."""

from app.cognition.runtime import probe_evidence_str


def test_search_results_render_raw_file_paths():
    out = [{
        "file_name": "arena_diag_marker_2de47246",
        "file_path": "C:\\Users\\PETAR\\arena_diag_marker_2de47246",
        "size_bytes": 63, "extension": "", "type": "file", "match": "exact",
    }]
    rendered = probe_evidence_str(out)
    assert "C:\\Users\\PETAR\\arena_diag_marker_2de47246" in rendered, rendered
    assert "1 hit(s):" in rendered, rendered
    # raw path, not JSON-escaped: single backslash pairs stay intact
    assert "C:\\\\Users" not in rendered, rendered


def test_empty_result_renders_as_empty():
    """The emptiness-stated-as-emptiness grounding (2026-09-02 fix) relies
    on an honest [] rendering — it must survive the new renderer."""
    assert probe_evidence_str([]) == "[]"


def test_scalar_list_is_bounded_but_visible():
    rendered = probe_evidence_str(["alpha", "beta", "gamma"])
    assert "alpha" in rendered and "beta" in rendered and "gamma" in rendered


def test_many_paths_are_capped_with_an_honest_count():
    out = [{"file_path": f"C:\\Users\\PETAR\\file_{i}.txt"} for i in range(9)]
    rendered = probe_evidence_str(out)
    assert "9 hit(s):" in rendered, rendered
    assert "file_0.txt" in rendered and "file_4.txt" in rendered, rendered
    assert "file_8.txt" not in rendered, rendered   # capped
    assert "+4 more" in rendered, rendered


def test_non_list_output_is_bounded_str():
    rendered = probe_evidence_str({"available": False, "error": "x" * 500})
    assert rendered.startswith("{") and len(rendered) <= 300


def test_dict_without_paths_still_bounded():
    rendered = probe_evidence_str([{"cpu_used_percent": 10.1}])
    assert "cpu_used_percent" in rendered and len(rendered) <= 300
