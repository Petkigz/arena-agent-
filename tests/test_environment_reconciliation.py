"""Environment reconciliation (review #3): the invalidation contract is
enforced, not just notified.

The revision epoch + note_environment_change() contract was sound but
relied on every environmental change NOTifying Arena. A human running
``pip install`` in a terminal sends no event — the availability cache
served stale facts until the 300s TTL backstop. The reconciliation layer
re-reads the observable environment surface and feeds fingerprint drift
into the SAME revision epoch:

    observed state -> snapshot -> fingerprint drift -> revision -> availability

These tests pin the CONTRACT (drift detected without notification →
revision bumps → stale cache healed on the very next lookup), the
baseline/throttle/error semantics of the observer, and the honesty of
the default observation itself (it measures real optional-dependency
importability — not a shape, the measurement).
"""

import importlib.util
from typing import Any, Dict

from app.cognition import tool_registry as tr
from app.cognition.environment_state import (
    OPTIONAL_DEPENDENCIES,
    environment_fingerprint,
    observe_environment,
)
from app.cognition.tool_registry import ToolRegistry


class FlippingWorld:
    """Simulates the human's terminal: the dependency's importability and
    the probe's answer BOTH live in the world — flipping this object is
    `pip install` / `pip uninstall` from Arena's point of view: nothing
    notifies the registry."""

    def __init__(self, installed: bool) -> None:
        self.installed = installed
        self.probe_calls = 0

    # environment provider half
    def __call__(self) -> Dict[str, bool]:
        return {"bs4": self.installed}

    # availability checker half — reads the same world the snapshot reads
    def checker(self) -> Dict[str, Any]:
        self.probe_calls += 1
        if self.installed:
            return {"available": True, "status": "available"}
        return {"available": False, "status": "dependency_unavailable",
                "missing_dependency": "bs4"}


def make_registry(world: FlippingWorld) -> ToolRegistry:
    reg = ToolRegistry(environment_provider=world, reconcile_interval_s=0.0)
    reg.register_tool("web_research", "web",
                      lambda p: {"success": True}, safety_level=0,
                      availability=world.checker, provenance="dynamic")
    return reg


def test_external_install_detected_without_notification():
    """The reported failure mode: dependency missing -> cached False ->
    HUMAN installs it (no note_environment_change anywhere) -> the very
    next availability lookup serves True. No 300s wait, no notification."""
    world = FlippingWorld(installed=False)
    reg = make_registry(world)

    first = reg.get_tool_availability("web_research")
    assert first["available"] is False, "dependency missing at probe time"
    assert world.probe_calls == 1

    world.installed = True  # the human's `pip install bs4` — silent to Arena
    second = reg.get_tool_availability("web_research")
    assert second["available"] is True, \
        "unnotified external install must not be served stale"
    assert world.probe_calls == 2, "the stale entry was re-probed, not replayed"


def test_external_uninstall_detected_without_notification():
    """The reverse drift: cached True must not survive a silent uninstall."""
    world = FlippingWorld(installed=True)
    reg = make_registry(world)

    assert reg.get_tool_availability("web_research")["available"] is True

    world.installed = False  # silent `pip uninstall`
    result = reg.get_tool_availability("web_research")
    assert result["available"] is False, \
        "unnotified external uninstall must not be served stale"


def test_drift_bumps_the_environment_revision():
    """The snapshot feeds the ONE invalidation contract: drift re-enters
    through the revision epoch (so every cached fact goes stale at once,
    not just the one tool whose lookup noticed the drift)."""
    world = FlippingWorld(installed=False)
    reg = make_registry(world)
    reg.get_tool_availability("web_research")  # baseline observation taken
    revision_before = reg.environment_revision

    world.installed = True
    reg.get_tool_availability("web_research")

    assert reg.environment_revision > revision_before, \
        "observed drift must advance the environment revision"


def test_no_drift_no_reprobe():
    """A stable environment keeps serving the cache — reconciliation must
    not turn every lookup into a probe."""
    world = FlippingWorld(installed=False)
    reg = make_registry(world)

    reg.get_tool_availability("web_research")
    reg.get_tool_availability("web_research")
    reg.get_tool_availability("web_research")

    assert world.probe_calls == 1, \
        "unchanged environment must keep serving the cached fact"


def test_first_observation_is_a_baseline_not_a_change():
    """Booting (or a registry's first lookup) must not bump the revision:
    the first observation defines 'unchanged', it is not drift."""
    world = FlippingWorld(installed=False)
    reg = make_registry(world)
    # revision after all registrations is the baseline to compare against
    revision_after_boot = reg.environment_revision

    reg.get_tool_availability("web_research")

    assert reg.environment_revision == revision_after_boot, \
        "the baseline observation must not be reported as drift"


def test_reconciliation_is_throttled():
    """The observation runs on the availability path (planner cadence) —
    it must be throttled to once per reconcile interval, not per lookup."""
    world = FlippingWorld(installed=False)
    reg = ToolRegistry(environment_provider=world, reconcile_interval_s=60.0)
    reg.register_tool("web_research", "web",
                      lambda p: {"success": True}, safety_level=0,
                      availability=world.checker, provenance="dynamic")

    reg.get_tool_availability("web_research")  # first call: observes (baseline)
    world.observation_calls = 0

    class CountingWorld:
        def __call__(self):
            world.observation_calls += 1
            return {"bs4": False}

    reg._environment_provider = CountingWorld()
    reg.get_tool_availability("web_research")
    reg.get_tool_availability("web_research")
    reg.get_tool_availability("web_research")

    assert world.observation_calls == 0, \
        "within the interval the observation must not re-run"


def test_observation_failure_never_breaks_availability():
    """Observation is best-effort by contract: a provider that raises must
    never take the availability path down (the TTL backstop still covers
    drift while observation is broken)."""
    def broken_provider():
        raise RuntimeError("observation surface unavailable")

    reg = ToolRegistry(environment_provider=broken_provider,
                       reconcile_interval_s=0.0)
    reg.register_tool("some_tool", "test",
                      lambda p: {"success": True}, safety_level=0,
                      availability=lambda: {"available": True,
                                            "status": "available"},
                      provenance="dynamic")

    result = reg.get_tool_availability("some_tool")
    assert result["available"] is True, \
        "a broken observer must not corrupt the availability answer"
    assert reg.get_tool_availability("some_tool")["available"] is True


def test_drift_heal_forces_a_real_probe_not_a_replay():
    """The lazy proxies replay their last load failure when merely
    re-asked (probe=False) — a drift-healed lookup must re-read the world
    (probe=True), or reconciliation would detect the drift and then serve
    the stale failure anyway. This checker replays stale state unless
    actually probed, exactly like a _LazyImportProxy."""
    world = FlippingWorld(installed=False)
    reg = ToolRegistry(environment_provider=world, reconcile_interval_s=0.0)

    def proxy_like_checker(*, probe: bool = False) -> Dict[str, Any]:
        world.probe_calls += 1
        if probe:  # a real probe re-attempts the import
            return ({"available": True, "status": "available"}
                    if world.installed else
                    {"available": False, "status": "dependency_unavailable",
                     "missing_dependency": "bs4"})
        # unprobed re-ask replays the last observed failure, like the proxy
        return {"available": False, "status": "dependency_unavailable",
                "missing_dependency": "bs4"}

    reg.register_tool("web_research", "web",
                      lambda p: {"success": True}, safety_level=0,
                      availability=proxy_like_checker, provenance="dynamic")

    assert reg.get_tool_availability("web_research")["available"] is False
    world.installed = True  # silent install

    healed = reg.get_tool_availability("web_research")  # default probe=False!
    assert healed["available"] is True, \
        "drift must force a REAL re-probe, never a stale-failure replay"


def test_default_observer_measures_real_importability():
    """Measurement honesty: the default observation must measure what it
    claims — for every optional distribution, importability RIGHT NOW —
    not a shape or a constant. Cross-checked against importlib directly."""
    snapshot = observe_environment()
    assert set(snapshot) == set(OPTIONAL_DEPENDENCIES), \
        "the observation table and the snapshot must agree"
    for name, observed in snapshot.items():
        expected = importlib.util.find_spec(name) is not None
        assert observed is expected, \
            f"{name}: observed {observed}, importlib says {expected}"
    assert all(isinstance(v, bool) for v in snapshot.values())


def test_fingerprint_is_stable_and_names_the_drift():
    """The fingerprint is deterministic and human-readable, so a drift
    event can state exactly which predicate moved (no opaque hash)."""
    a = {"bs4": False, "pypdf": True}
    assert environment_fingerprint(a) == environment_fingerprint(dict(a))
    assert environment_fingerprint(a) == "bs4=0; pypdf=1"
    drifted = {"bs4": True, "pypdf": True}
    assert environment_fingerprint(drifted) != environment_fingerprint(a)


def test_drift_invalidates_every_cached_tool_at_once():
    """Drift re-enters through note_environment_change — the whole cache
    clears (one environment, one epoch), not just the noticing tool."""
    world = FlippingWorld(installed=False)
    reg = ToolRegistry(environment_provider=world, reconcile_interval_s=0.0)
    reg.register_tool("web_research", "web",
                      lambda p: {"success": True}, safety_level=0,
                      availability=world.checker, provenance="dynamic")
    reg.register_tool("unrelated_tool", "test",
                      lambda p: {"success": True}, safety_level=0,
                      availability=lambda: {"available": True,
                                            "status": "available"},
                      provenance="dynamic")

    reg.get_tool_availability("unrelated_tool")  # cached at baseline
    world.installed = True
    reg.get_tool_availability("web_research")    # notices the drift

    # the UNRELATED tool's cached entry died with the revision bump:
    # its next lookup re-probes (checker call count proves it)
    calls = reg.get_tool_availability("unrelated_tool").get("probed_at_revision")
    assert calls == reg.environment_revision, \
        "unrelated cached facts must be re-derived at the new revision"
