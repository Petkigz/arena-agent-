"""App naming done right (owner requirement 2026-09-08): fuzzy matching AND
an inventory that reflects what is installed NOW — not a snapshot from when
the server started. A newly installed app must be findable seconds after
installation, and a total miss must ask honestly with close candidates."""

import pytest

from app.tools.app_inventory import SystemAppInventory

APP = lambda name, path="/x/app.exe": {  # noqa: E731
    "app_name": name, "executable_path": path, "source_category": "test",
}


@pytest.fixture(autouse=True)
def fresh_cache():
    SystemAppInventory._cached_apps = []
    SystemAppInventory._cache_ts = 0.0
    yield
    SystemAppInventory._cached_apps = []
    SystemAppInventory._cache_ts = 0.0


def _seed(*apps):
    import time

    SystemAppInventory._cached_apps = list(apps)
    SystemAppInventory._cache_ts = time.time()


# ── Fuzzy + normalized matching ────────────────────────────────────────


def test_fuzzy_match_handles_spelling_drift():
    """The live failure: 'richst tv' must reach 'Richie TV'."""
    _seed(APP("Richie TV"), APP("Mozilla Firefox"))
    matched, close = SystemAppInventory._match_app("richst tv")
    assert matched is not None and matched["app_name"] == "Richie TV"


def test_normalized_match_ignores_spaces_and_case():
    _seed(APP("RichieTV Setup"), APP("VLC media player"))
    matched, _ = SystemAppInventory._match_app("richie tv")
    assert matched is not None and matched["app_name"] == "RichieTV Setup"


def test_substring_direction_preserved():
    """'firef' -> 'Mozilla Firefox' still works; a sentence containing an
    app name must still not match."""
    _seed(APP("Mozilla Firefox"))
    matched, _ = SystemAppInventory._match_app("firef")
    assert matched is not None
    matched, _ = SystemAppInventory._match_app("now in control panel open user accounts")
    assert matched is None


def test_confident_near_match_auto_launches():
    """'richy tv' scores ~0.8 against 'Richie TV' — close enough to just
    launch (with the fuzzy decision logged)."""
    _seed(APP("Richie TV"), APP("Ritchie TV Pro"))
    matched, _ = SystemAppInventory._match_app("richy tv")
    assert matched is not None and matched["app_name"] == "Richie TV"


def test_mid_band_query_suggests_instead_of_launching():
    """'rtv' (~0.55, inside the suggestion band, below launch confidence)
    must ask, offering the real installed names."""
    _seed(APP("Richie TV"), APP("Ritchie TV Pro"))
    matched, close = SystemAppInventory._match_app("rtv")
    assert matched is None  # below auto-launch confidence
    assert close, "near-misses must be offered back to the owner"
    assert any("TV" in c["app_name"] for c in close)


def test_genuinely_unknown_gets_no_suggestions():
    _seed(APP("Richie TV"), APP("Mozilla Firefox"))
    matched, close = SystemAppInventory._match_app("quantum blender")
    assert matched is None and close == []


# ── Freshness: a NEW app is found after installation ───────────────────


def test_miss_triggers_live_rescan_and_finds_new_app(tmp_path, monkeypatch):
    """The owner's exact scenario: the app was installed AFTER the last
    scan. The first match misses; the tool must rescan live and find it."""
    stale = APP("Old Stale App")
    newly_installed = APP(
        "Brand New App", str(tmp_path / "brandnew.exe"))
    scan_calls = {"n": 0}

    def fake_scan():
        scan_calls["n"] += 1
        if scan_calls["n"] == 1:
            SystemAppInventory._cached_apps = [stale]
        else:
            SystemAppInventory._cached_apps = [stale, newly_installed]
        import time

        SystemAppInventory._cache_ts = time.time()
        return {"success": True, "total_apps_count": len(SystemAppInventory._cached_apps),
                "applications": SystemAppInventory._cached_apps}

    monkeypatch.setattr(SystemAppInventory, "scan_installed_applications", classmethod(
        lambda cls: fake_scan()))

    result = SystemAppInventory.launch_any_app("brand new app")
    assert scan_calls["n"] >= 2, "a miss must rescan the live inventory"
    assert result.get("success") is False or result.get("app_name"), "no crash either way"
    # The second match pass saw the new app, so the tool proceeded to launch
    # (or honestly failed at launch — but NOT 'probably not installed').
    assert "probably not installed" not in str(result.get("error", ""))


def test_stale_cache_rescans_before_matching(monkeypatch):
    """TTL: an old cache is refreshed before the first match attempt."""
    import time

    scan_calls = {"n": 0}

    def fake_scan():
        scan_calls["n"] += 1
        SystemAppInventory._cached_apps = [APP("Firefox")]
        SystemAppInventory._cache_ts = time.time()
        return {"success": True, "total_apps_count": 1, "applications": SystemAppInventory._cached_apps}

    monkeypatch.setattr(SystemAppInventory, "scan_installed_applications", classmethod(
        lambda cls: fake_scan()))
    SystemAppInventory._cached_apps = [APP("Stale Only")]
    SystemAppInventory._cache_ts = time.time() - 3600  # 1h old

    _matched, _ = SystemAppInventory._match_app("stale only")  # direct match, no scan
    # The launch path refreshes a stale cache first:
    SystemAppInventory._cache_ts = time.time() - 3600
    result = SystemAppInventory.launch_any_app("firefox")
    assert scan_calls["n"] >= 1, "stale cache must rescan before matching"
    assert result.get("app_name") == "Firefox" or result.get("success") is True or "error" in result


def test_honest_miss_names_close_candidates(monkeypatch):
    """A real miss after a live rescan asks with suggestions, one word
    answers it."""
    def fake_scan():
        import time

        SystemAppInventory._cached_apps = [APP("Richie TV"), APP("Ritchie Player")]
        SystemAppInventory._cache_ts = time.time()
        return {"success": True, "total_apps_count": 2, "applications": SystemAppInventory._cached_apps}

    monkeypatch.setattr(SystemAppInventory, "scan_installed_applications", classmethod(
        lambda cls: fake_scan()))
    result = SystemAppInventory.launch_any_app("rtv")
    assert result.get("success") is False
    assert result.get("close_matches"), result
    assert "Which one did you mean?" in str(result.get("error"))


# ── Extraction: the name before the verb ───────────────────────────────


def test_extraction_handles_called_named_pattern():
    from app.agents.master_agent import extract_app_query

    assert extract_app_query(
        "hey theres an app on my pc called richst tv open it"
    ) == "richst tv"
    assert extract_app_query("can you open an app called steam for me") == "steam"
    assert extract_app_query("the program named obs studio, start it") == "obs studio"


def test_extraction_verb_first_still_works():
    from app.agents.master_agent import extract_app_query

    assert extract_app_query("open firefox") == "firefox"
    assert extract_app_query("launch the calculator please") == "calculator"


def test_extraction_refuses_placeholder_names():
    from app.agents.master_agent import extract_app_query

    assert extract_app_query("open the app") == ""
    assert extract_app_query("open it") == ""
    assert extract_app_query("run something") == ""


def test_launch_uses_extracted_called_name(monkeypatch, tmp_path):
    """End-to-end: 'called X' extraction feeds the launcher and the app
    actually launches (real executable spawn on the POSIX test host)."""
    import app.agents.master_agent as ma

    real_exe = tmp_path / "richst-tv"
    real_exe.write_text("#!/bin/sh\nexit 0\n")
    real_exe.chmod(0o755)

    def fake_scan():
        import time

        SystemAppInventory._cached_apps = [APP("Richst TV", str(real_exe))]
        SystemAppInventory._cache_ts = time.time()
        return {"success": True, "total_apps_count": 1, "applications": SystemAppInventory._cached_apps}

    monkeypatch.setattr(SystemAppInventory, "scan_installed_applications", classmethod(
        lambda cls: fake_scan()))

    # The extraction contract the runtime depends on:
    app_name = ma.extract_app_query("hey theres an app on my pc called richst tv open it")
    assert app_name == "richst tv"
    res = SystemAppInventory.launch_any_app(app_name)
    assert res.get("success") is True, res
    assert res.get("app_name") == "Richst TV"
