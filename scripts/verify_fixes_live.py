#!/usr/bin/env python3
"""Live verification of the P0 fixes (#6, #7, #8, #9) — run on YOUR machine.

Unit tests pin the logic; this script exercises the fixes through the REAL
runtime: the real manifest, the real shared registry, the real ActionGate,
the real FastAPI app routing, and the real system probes — no mocks. Run it
after pulling any of these fixes:

    python scripts/verify_fixes_live.py

Each check reports PASS / FAIL / SKIP:
- PASS — the fix demonstrably works against the live system.
- FAIL — the fix did not behave as claimed; investigate.
- SKIP — not verifiable in this environment (e.g. no missing optional
         dependency to observe a recovery from); not a failure.

Exit code 0 if nothing FAILED, 1 otherwise — wire into your own routine.

Covered:
  #6 availability cache   — revision semantics, REST refresh, registration
                            and execution-failure invalidation, package
                            install notification, honest unavailable probes
  #7 investigation breadth— adaptive window tiers, full-pool ranking,
                            rank evidence in planned investigations
  #8 concept bridge       — the slow-computer scenario end to end, no
                            pollution of ordinary requests, the five real
                            diagnostic probes, plan->execute with measured
                            output
  #9 single authority     — safety/availability/execution resolve ONE
                            effective capability; override raises the gate;
                            unknown still refused
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── harness (same convention as scripts/live_check.py) ──────────────────────

def run_live_checks(probes: List[Tuple[str, Callable[[], Dict[str, Any]]]]) -> Dict[str, Any]:
    checks = []
    for name, fn in probes:
        try:
            res = fn()
            if not isinstance(res, dict) or "status" not in res:
                res = {"status": "fail", "detail": "probe returned an unexpected result"}
        except Exception as e:
            res = {"status": "fail", "detail": f"raised: {e}"}
        checks.append({"check": name, **res})
    return {
        "checks": checks,
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
        "skipped": sum(1 for c in checks if c["status"] == "skip"),
    }


# ── section E (runs first: boots the REAL runtime + REST surface) ───────────

def rest_surface_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cognition.runtime import CognitiveRuntime

    client = TestClient(app)  # boots the real app + runtime singleton

    def e1_availability_endpoint():
        r = client.get("/tools/availability", params={"tool": "list_capabilities"})
        if r.status_code != 200:
            return {"status": "fail", "detail": f"HTTP {r.status_code}"}
        tool = r.json()["tool"]
        if tool.get("available") is not True:
            return {"status": "fail", "detail": f"unexpected availability: {tool}"}
        return {"status": "pass",
                "detail": f"status={tool['status']} revision={tool.get('probed_at_revision')}"}

    def e2_owner_refresh_endpoint():
        registry = CognitiveRuntime.get_instance().registry
        before = registry.environment_revision
        r = client.post("/tools/availability/refresh",
                        json={"reason": "live verification run"})
        if r.status_code != 200:
            return {"status": "fail", "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        if not data.get("success") or data["environment_revision"] <= before:
            return {"status": "fail", "detail": f"revision did not advance: {data}"}
        if registry._availability_cache:
            return {"status": "fail", "detail": "cache not cleared"}
        return {"status": "pass",
                "detail": f"revision {before} -> {data['environment_revision']}, cache cleared"}

    def e3_full_availability_listing():
        # This exact request 500'd before the function-symbol proxy fix:
        # binary_analyze/binary_strings carried a broken checker that only
        # exploded when the FULL listing probed every tool.
        r = client.get("/tools/availability")
        if r.status_code != 200:
            return {"status": "fail", "detail": f"HTTP {r.status_code}"}
        d = r.json()
        if d["count"] < 100:
            return {"status": "fail", "detail": f"only {d['count']} tools listed"}
        return {"status": "pass",
                "detail": f"{d['count']} tools: {d['available']} available, "
                          f"{d['unavailable']} unavailable, {d['not_checked']} not_checked"}

    return [("E1 GET /tools/availability (real app, real runtime)", e1_availability_endpoint),
            ("E2 POST /tools/availability/refresh (owner env-change declaration)", e2_owner_refresh_endpoint),
            ("E3 GET /tools/availability FULL listing (regression: proxy checker crash)", e3_full_availability_listing)]


# ── section A — fix #6: availability cache invalidation ─────────────────────

def availability_cache_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.tool_registry import ToolRegistry

    def a1_decisive_probe_is_revision_tagged():
        registry = CognitiveRuntime.get_instance().registry
        status = registry.get_tool_availability("list_capabilities", refresh=True)
        if status.get("available") is not True:
            return {"status": "fail", "detail": str(status)}
        if "probed_at_revision" not in status:
            return {"status": "fail", "detail": "decisive result lacks its probe revision"}
        cached = registry.get_tool_availability("list_capabilities")
        if cached.get("probed_at_revision") != status["probed_at_revision"]:
            return {"status": "fail", "detail": "cache did not serve the tagged entry"}
        return {"status": "pass",
                "detail": f"probed_at_revision={status['probed_at_revision']} served from cache"}

    def a2_environment_change_invalidates_and_emits():
        registry = CognitiveRuntime.get_instance().registry
        registry.get_tool_availability("list_capabilities", refresh=True)
        events: list = []
        unsubscribe = registry.event_bus.subscribe("environment_changed", events.append)
        try:
            before = registry.environment_revision
            revision = registry.note_environment_change("live verification", source="verify_script")
            if revision <= before:
                return {"status": "fail", "detail": "revision did not advance"}
            if registry._availability_cache:
                return {"status": "fail", "detail": "cache not cleared"}
            if not events or events[0].data.get("revision") != revision:
                return {"status": "fail", "detail": f"event missing/mismatched: {events}"}
            return {"status": "pass",
                    "detail": f"revision {before}->{revision}, cache cleared, event emitted"}
        finally:
            unsubscribe()

    def a3_registration_invalidates():
        reg = ToolRegistry()
        reg.register_tool("live_reg_probe", "verify",
                          lambda p: {"success": True},
                          availability=lambda *, probe=False: {"available": True, "status": "available"})
        reg.get_tool_availability("live_reg_probe")
        before = reg.environment_revision
        reg.register_tool("live_reg_probe", "verify",
                          lambda p: {"success": True, "v": 2},
                          availability=lambda *, probe=False: {"available": False, "status": "dependency_unavailable"})
        status = reg.get_tool_availability("live_reg_probe")
        if reg.environment_revision <= before:
            return {"status": "fail", "detail": "registration did not advance revision"}
        if status.get("available") is not False:
            return {"status": "fail", "detail": f"new registration's truth not visible: {status}"}
        return {"status": "pass", "detail": "re-registration visible immediately (no TTL wait)"}

    def a4_execution_failure_invalidates():
        # Carrier is a REAL Level-0 manifest name (overridden in a throwaway
        # registry) so the policy gate's unknown-action default does not mask
        # the behavior under test.
        reg = ToolRegistry()
        reg.register_tool("list_processes", "verify",
                          lambda p: {"success": False, "available": False, "error": "dep gone"},
                          availability=lambda *, probe=False: {"available": True, "status": "available"})
        reg.get_tool_availability("list_processes")
        result = reg.execute_registered_tool("list_processes", {})
        if result.get("available") is not False:
            return {"status": "fail", "detail": f"unexpected result: {result}"}
        if "list_processes" in reg._availability_cache:
            return {"status": "fail", "detail": "contradicted entry survived execution failure"}
        return {"status": "pass", "detail": "ground truth dropped the cached available=True"}

    def a5_package_install_notifies():
        import os
        from app.cognition.tool_registry import get_shared_registry
        from app.tools.package_installer import PackageInstaller
        registry = get_shared_registry()
        before = registry.environment_revision
        # Real pip subprocess, non-intrusive: 'pip' is always already
        # installed, so this succeeds without changing the environment.
        # Bare `pip` must resolve to the RUNNING interpreter's pip (as an
        # activated venv would), not a system pip that may be PEP-668
        # externally managed.
        venv_bin = str(Path(sys.executable).parent)
        saved_path = os.environ.get("PATH", "")
        os.environ["PATH"] = venv_bin + os.pathsep + saved_path
        try:
            result = PackageInstaller.install_package("pip")
        finally:
            os.environ["PATH"] = saved_path
        if not result.get("success"):
            return {"status": "skip",
                    "detail": f"pip reported failure: {str(result.get('error'))[:80]}"}
        if registry.environment_revision <= before:
            return {"status": "fail", "detail": "successful install did not advance the revision"}
        return {"status": "pass",
                "detail": f"real pip subprocess -> revision {before}->"
                          f"{registry.environment_revision}"}

    def a6_missing_dependency_reported_honestly():
        registry = CognitiveRuntime.get_instance().registry
        for tool in ("vlm_analyze", "camera_photo", "vlm_status"):
            status = registry.get_tool_availability(tool, probe=True, refresh=True)
            if status.get("available") is False:
                # Stale-failure recovery is unit-pinned; live we verify the
                # honest report plus a successful RE-probe (no crash).
                again = registry.get_tool_availability(tool, probe=True, refresh=True)
                return {"status": "pass",
                        "detail": f"{tool}: {status.get('status')} "
                                  f"({status.get('missing_dependency')}); re-probe ok={again is not None}"}
        return {"status": "skip",
                "detail": "no missing optional dependency in this environment to observe"}

    return [("A1 decisive probes carry probed_at_revision (real runtime registry)", a1_decisive_probe_is_revision_tagged),
            ("A2 note_environment_change clears cache + emits event (real bus)", a2_environment_change_invalidates_and_emits),
            ("A3 runtime re-registration invalidates immediately", a3_registration_invalidates),
            ("A4 execution-reported unavailability drops the cached entry", a4_execution_failure_invalidates),
            ("A5 real pip install notifies the registry (non-intrusive)", a5_package_install_notifies),
            ("A6 missing optional dependency reports honestly + re-probes", a6_missing_dependency_reported_honestly)]


# ── section B — fix #7: adaptive investigation breadth ──────────────────────

def breadth_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    from app.cognition.action_selection import InvestigationRegistry, _investigation_breadth
    from app.cognition.information_gain import InformationNeed
    from app.cognition.tool_matcher import rank_tools
    from app.tools.manifest import get_tool_manifest

    def b1_adaptive_tiers():
        simple = _investigation_breadth(InformationNeed("open chrome", "chrome", "r", 0.1))
        urgent = _investigation_breadth(InformationNeed("check the disk", "disk", "r", 0.8))
        multi = _investigation_breadth(InformationNeed(
            "find the process, check the logs, scan the network, read the database, "
            "capture the screen and list the files", "system", "r", 0.1))
        if simple != 8 or urgent != 20 or multi < 12:
            return {"status": "fail", "detail": f"simple={simple} urgent={urgent} multi={multi}"}
        return {"status": "pass", "detail": f"simple={simple}, high-priority={urgent}, multi-verb={multi}"}

    def b2_full_pool_ranking():
        # A compound multi-domain request: with the old limit=8 ceiling,
        # candidates beyond rank 8 were truncated before the planner ever
        # saw them. This text legitimately produces 15+ above-noise
        # candidates across domains.
        text = ("check running processes, cpu and memory usage, free disk space, "
                "startup programs, network connections, recent system logs, "
                "temperature sensors, capture a screenshot, search files for the "
                "report, compress the archive, merge the pdf documents, "
                "summarize the notes, translate the text to french, "
                "analyze the spreadsheet data")
        hits = rank_tools(text, limit=len(get_tool_manifest()))
        if len(hits) <= 8:
            return {"status": "fail",
                    "detail": f"only {len(hits)} candidates — the old 8-ceiling behavior"}
        return {"status": "pass",
                "detail": f"{len(hits)} above-noise candidates ranked across domains "
                          f"(ceiling gone)"}

    def b3_real_plan_carries_rank_evidence():
        plan = InvestigationRegistry().plan(InformationNeed(
            question="list all your capabilities", target="arena",
            reason="live verification", priority=0.5))
        if plan is None:
            return {"status": "fail", "detail": "no plan for a capability question"}
        if "rank" not in plan.reason or "/" not in plan.reason:
            return {"status": "fail", "detail": f"no rank evidence: {plan.reason}"}
        return {"status": "pass", "detail": f"{plan.tool} — {plan.reason[:80]}"}

    return [("B1 adaptive breadth tiers on real needs", b1_adaptive_tiers),
            ("B2 discovery ranks the full pool, not a window of 8", b2_full_pool_ranking),
            ("B3 planned investigation carries its rank evidence", b3_real_plan_carries_rank_evidence)]


# ── section C — fix #8: concept bridge + diagnostic probes ──────────────────

def concept_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    from app.cognition.concept_bridge import expand_goal
    from app.cognition.tool_matcher import rank_tools

    SCENARIO = "find why my computer suddenly became slow"
    EXPECTED = ("system_metrics", "list_processes", "startup_programs",
                "network_activity", "recent_logs", "temperature_status")

    def c1_scenario_discovers_diagnostics():
        hits = rank_tools(SCENARIO, limit=30)
        found = {h.action_type: h for h in hits}
        missing = [t for t in EXPECTED if t not in found]
        if missing:
            return {"status": "fail",
                    "detail": f"not discovered: {missing}; got {sorted(found)}"}
        with_evidence = [t for t in EXPECTED if found[t].concept_terms]
        if len(with_evidence) != len(EXPECTED):
            return {"status": "fail", "detail": "matches lack concept evidence"}
        return {"status": "pass",
                "detail": f"6/6 discovered with evidence: "
                          f"{sorted(found[t].score for t in EXPECTED)}"}

    def c2_no_pollution_of_ordinary_requests():
        for text in ("search the web for slow cooking recipes",
                     "find hot deals on laptops",
                     "compress this pdf file and merge the pages"):
            expansion = expand_goal(text)
            if expansion.fired:
                return {"status": "fail", "detail": f"bridge fired on: {text!r}"}
            hits = rank_tools(text, limit=10)
            if any(h.concept_terms for h in hits):
                return {"status": "fail", "detail": f"concept evidence polluted: {text!r}"}
        return {"status": "pass", "detail": "ordinary requests pass through untouched"}

    def _probe_tool(name: str, verify: Callable[[Dict[str, Any]], Tuple[bool, str]]):
        from app.tools.manifest import get_tool_manifest
        entry = get_tool_manifest().get(name)
        if entry is None:
            return {"status": "fail", "detail": f"{name} not registered"}
        result = entry["handler"]({})
        ok, detail = verify(result if isinstance(result, dict) else {})
        return {"status": "pass" if ok else "fail", "detail": f"{name}: {detail}"}

    def c3_system_metrics():
        return _probe_tool("system_metrics", lambda r: (
            r.get("success") and r.get("cpu", {}).get("cores_logical", 0) >= 1
            and r.get("memory", {}).get("total_gb", 0) > 0,
            f"CPU {r.get('cpu', {}).get('percent_total')}% across "
            f"{r.get('cpu', {}).get('cores_logical')} cores, RAM "
            f"{r.get('memory', {}).get('used_gb')}/{r.get('memory', {}).get('total_gb')}GB, "
            f"uptime {r.get('uptime', {}).get('uptime_hours')}h"))

    def c4_temperature():
        return _probe_tool("temperature_status", lambda r: (
            r.get("success") and (r.get("available") is True or bool(r.get("reason"))),
            "sensors reported" if r.get("available") else f"honest unavailable: {r.get('reason')}"))

    def c5_network_activity():
        return _probe_tool("network_activity", lambda r: (
            r.get("success") and "io_since_boot" in r,
            f"{r.get('active_connections')} active connections, "
            f"{r.get('io_since_boot', {}).get('bytes_recv_mb')}MB received since boot"))

    def c6_startup_programs():
        return _probe_tool("startup_programs", lambda r: (
            r.get("success") and bool(r.get("sources")),
            f"{r.get('total')} items across {len(r.get('sources', []))} sources: "
            f"{[s['status'] for s in r.get('sources', [])]}"))

    def c7_recent_logs():
        return _probe_tool("recent_logs", lambda r: (
            r.get("success") and bool(r.get("sources")),
            f"{r.get('total_entries')} entries; sources: "
            f"{[(s['source'], s['status']) for s in r.get('sources', [])]}"))

    def c8_full_chain_plan_and_execute():
        from app.cognition.action_selection import InvestigationExecutor, InvestigationRegistry
        from app.cognition.information_gain import InformationNeed
        plan = InvestigationRegistry().plan(InformationNeed(
            question=SCENARIO, target="computer",
            reason="owner performance complaint", priority=0.7))
        if plan is None:
            return {"status": "fail", "detail": "the scenario did not plan"}
        result = InvestigationExecutor().execute(plan)
        if not result.success:
            return {"status": "fail", "detail": f"execution failed: {result.error}"}
        out = result.output if isinstance(result.output, dict) else {}
        return {"status": "pass",
                "detail": f"{plan.tool}: CPU {out.get('cpu', {}).get('percent_total')}%, "
                          f"RAM {out.get('memory', {}).get('percent')}% — measured live"}

    return [("C1 slow-computer scenario discovers all 6 diagnostics (no literal words)", c1_scenario_discovers_diagnostics),
            ("C2 ordinary requests are not polluted by the bridge", c2_no_pollution_of_ordinary_requests),
            ("C3 system_metrics measures the real machine", c3_system_metrics),
            ("C4 temperature reports real sensors or honest unavailability", c4_temperature),
            ("C5 network_activity reports real counters/connections", c5_network_activity),
            ("C6 startup_programs inventories real autostart", c6_startup_programs),
            ("C7 recent_logs tails the real system log", c7_recent_logs),
            ("C8 full chain: scenario -> plan -> execute -> measured values", c8_full_chain_plan_and_execute)]


# ── section D — fix #9: ONE authority (runs last; swaps the shared registry) ─

def authority_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    import app.cognition.tool_registry as tr

    def _with_own_registry(fn):
        """Run fn with a standalone registry installed as the shared one, so
        the module-level authority (which ActionGate consults) resolves
        against it; the original is always restored."""
        def wrapper():
            original = tr._shared_registry
            reg = tr.ToolRegistry()
            tr.set_shared_registry(reg)
            try:
                return fn(reg)
            finally:
                tr.set_shared_registry(original)
        return wrapper

    @_with_own_registry
    def d1_override_raises_the_gate(reg):
        # web_search is a real manifest tool at Level 0.
        if reg.capability_safety("web_search") != 0:
            return {"status": "fail", "detail": "baseline safety reading wrong"}
        reg.register_tool("web_search", "web",
                          lambda p: {"success": True, "who": "override"},
                          safety_level=3, provenance="dynamic")
        if reg.capability_safety("web_search") != 3:
            return {"status": "fail", "detail": "safety did not follow the override"}
        result = reg.execute_registered_tool("web_search", {})
        if result.get("success") is not False or not result.get("requires_approval"):
            return {"status": "fail", "detail": f"override not gate-enforced: {result}"}
        return {"status": "pass",
                "detail": "Level 0 -> override Level 3: gate now requires approval"}

    @_with_own_registry
    def d2_three_consumers_one_view(reg):
        reg.register_tool("web_search", "web",
                          lambda p: {"success": True, "who": "override"},
                          safety_level=1, provenance="dynamic",
                          availability=lambda *, probe=False: {"available": True, "status": "available"})
        effective = reg.effective_capability("web_search")
        safety = reg.capability_safety("web_search")
        status = reg.get_tool_availability("web_search", probe=True, refresh=True)
        result = reg.execute_registered_tool("web_search", {})
        if safety != effective["safety_level"]:
            return {"status": "fail", "detail": "safety disagrees with effective entry"}
        if status.get("available") is not True:
            return {"status": "fail", "detail": f"availability disagrees: {status}"}
        if result.get("who") != "override":
            return {"status": "fail", "detail": f"execution did not run the override handler: {result}"}
        return {"status": "pass",
                "detail": f"safety={safety}, available=True, override handler ran"}

    @_with_own_registry
    def d3_unknown_still_refused(reg):
        if reg.capability_safety("definitely_not_real_live") != 99:
            return {"status": "fail", "detail": "unknown not gated at 99"}
        status = reg.get_tool_availability("definitely_not_real_live")
        if status.get("status") != "not_registered":
            return {"status": "fail", "detail": f"unexpected status: {status}"}
        result = reg.execute_registered_tool("definitely_not_real_live", {})
        if result.get("success") is not False:
            return {"status": "fail", "detail": "unknown name executed"}
        return {"status": "pass", "detail": "unknown -> 99 / not_registered / refused"}

    return [("D1 runtime override raises the level the GATE enforces", d1_override_raises_the_gate),
            ("D2 safety, availability and execution share ONE view", d2_three_consumers_one_view),
            ("D3 unknown capabilities still honestly refused", d3_unknown_still_refused)]


# ── section F — review #3: environment reconciliation (unnotified drift) ────

def reconciliation_probes() -> List[Tuple[str, Callable[[], Dict[str, Any]]]]:
    from app.cognition.tool_registry import ToolRegistry

    def f1_unnotified_external_drift_heals_immediately():
        """The reported failure mode, live: cached False survives a SILENT
        dependency install only if nothing reconciles. Simulates the human
        terminal by flipping the registry's observation of the world
        without any note_environment_change call."""
        installed = {"value": False}
        probes = {"n": 0}

        def provider():
            return {"bs4": installed["value"]}

        def checker():
            probes["n"] += 1
            if installed["value"]:
                return {"available": True, "status": "available"}
            return {"available": False, "status": "dependency_unavailable",
                    "missing_dependency": "bs4"}

        reg = ToolRegistry(environment_provider=provider, reconcile_interval_s=0.0)
        reg.register_tool("web_research", "web",
                          lambda p: {"success": True}, safety_level=0,
                          availability=checker, provenance="dynamic")
        first = reg.get_tool_availability("web_research")
        if first.get("available") is not False:
            return {"status": "fail", "detail": f"baseline probe wrong: {first}"}
        revision_before = reg.environment_revision

        installed["value"] = True  # the human's silent `pip install bs4`
        healed = reg.get_tool_availability("web_research")  # default: no probe
        if healed.get("available") is not True:
            return {"status": "fail",
                    "detail": f"silent install still served stale: {healed}"}
        if reg.environment_revision <= revision_before:
            return {"status": "fail", "detail": "drift did not bump the revision"}
        if healed.get("probed_at_revision") != reg.environment_revision:
            return {"status": "fail", "detail": "healed fact not at the new revision"}
        return {"status": "pass",
                "detail": f"silent install healed at revision "
                           f"{healed.get('probed_at_revision')} (was {revision_before})"}

    def f2_default_observer_reports_real_importability():
        """Measurement honesty, live: the DEFAULT observation must match
        importlib's view of this very interpreter for every optional
        dependency — the reconciliation layer observes the real world,
        not a stub."""
        import importlib.util
        from app.cognition.environment_state import (
            OPTIONAL_DEPENDENCIES, observe_environment)
        snapshot = observe_environment()
        if set(snapshot) != set(OPTIONAL_DEPENDENCIES):
            return {"status": "fail", "detail": "snapshot/table mismatch"}
        wrong = [
            f"{name}: observed={observed}"
            for name, observed in snapshot.items()
            if observed != (importlib.util.find_spec(name) is not None)
        ]
        if wrong:
            return {"status": "fail", "detail": ", ".join(wrong)}
        present = sum(1 for v in snapshot.values() if v)
        return {"status": "pass",
                "detail": f"{len(snapshot)} optional dependencies observed, "
                           f"{present} importable — matches importlib"}

    return [("F1 unnotified external drift heals on the next lookup", f1_unnotified_external_drift_heals_immediately),
            ("F2 default observer reports real importability", f2_default_observer_reports_real_importability)]


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    sections = [
        ("REST surface (real app)", rest_surface_probes),
        ("Fix #6 — availability cache invalidation", availability_cache_probes),
        ("Fix #7 — adaptive investigation breadth", breadth_probes),
        ("Fix #8 — concept bridge + diagnostic probes", concept_probes),
        ("Fix #9 — ONE capability authority", authority_probes),
        ("Review #3 — environment reconciliation", reconciliation_probes),
    ]
    report: Dict[str, Any] = {}
    for title, builder in sections:
        print(f"\n── {title} " + "─" * max(0, 58 - len(title)))
        result = run_live_checks(builder())
        report[title] = result
        for c in result["checks"]:
            mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
            print(f"  [{mark}] {c['check']}")
            if c.get("detail"):
                print(f"         {c['detail']}")

    total = {k: sum(r[k] for r in report.values())
             for k in ("passed", "failed", "skipped")}
    print("\n" + "═" * 72)
    print(f"TOTAL: {total['passed']} passed, {total['failed']} failed, "
          f"{total['skipped']} skipped")
    return 0 if total["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
