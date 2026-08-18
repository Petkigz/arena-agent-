import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
DASHBOARD_PATH = STATIC_DIR / "index.html"


def _dashboard() -> BeautifulSoup:
    return BeautifulSoup(DASHBOARD_PATH.read_text(encoding="utf-8"), "html.parser")


def test_every_dashboard_panel_has_a_valid_navigation_target():
    soup = _dashboard()
    panel_ids = {panel["id"] for panel in soup.select(".tab-content[id]")}

    targets = set()
    for button in soup.select("nav .nav-btn[onclick]"):
        match = re.search(r"switchTab\('([^']+)'", button["onclick"])
        assert match, f"Navigation button has no switchTab target: {button}"
        targets.add(f"tab-{match.group(1)}")

    assert targets == panel_ids


def test_dashboard_controls_have_accessible_names():
    soup = _dashboard()
    label_targets = {label.get("for") for label in soup.find_all("label") if label.get("for")}

    unnamed = []
    for control in soup.find_all(["input", "select", "textarea"]):
        control_id = control.get("id")
        nested_label = control.find_parent("label") is not None
        has_name = bool(
            nested_label
            or control.get("aria-label")
            or control.get("aria-labelledby")
            or (control_id and control_id in label_targets)
        )
        if not has_name:
            unnamed.append(control_id or str(control))

    assert unnamed == []


def test_manifest_icons_exist_with_declared_dimensions():
    manifest = json.loads((STATIC_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["icons"]

    for icon in manifest["icons"]:
        icon_path = STATIC_DIR / Path(icon["src"]).name
        assert icon_path.is_file(), f"Missing PWA icon: {icon_path}"

        expected_size = tuple(int(value) for value in icon["sizes"].split("x"))
        with Image.open(icon_path) as image:
            assert image.size == expected_size
            assert image.format == "PNG"


def test_service_worker_caches_only_same_origin_app_shell():
    worker = (STATIC_DIR / "service-worker.js").read_text(encoding="utf-8")

    assert "requestUrl.origin !== self.location.origin" in worker
    assert "request.mode === 'navigate' && requestUrl.pathname === '/'" in worker
    assert "requestUrl.pathname.startsWith('/static/')" in worker
    assert "if (!isCacheableAppShellRequest(event.request))" in worker


def test_dashboard_warns_that_remote_access_is_not_authenticated():
    text = _dashboard().get_text(" ", strip=True)

    assert "API authentication is not implemented yet" in text
    assert "127.0.0.1" in text
    assert "does not clone a person's timbre" in text
