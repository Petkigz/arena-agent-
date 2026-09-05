"""Owner-machine diagnostics (run where LM Studio / hardware live).

The sandbox can exercise the deterministic layer only. This pack runs on
the OWNER's machine — where the local LLM, the real browser, the phone
and the GPU are — and measures the things that cannot be measured
anywhere else, with GROUND TRUTH checked programmatically (never trust
the agent's own claim of success: arithmetic answers, created files,
installed tools and DB rows are verified independently).

Sections:
  0  Environment      — LM Studio reachability, loaded models, latency
  A  Brain online     — the chat battery whose OFFLINE baseline is known,
                        now with the model driving intent + reasoning
  B  Hardware probes  — screen, VLM, LoRA/GPU, ADB phone, audio, browser

Every check is independent: one failure never stops the pack. Output is
a human summary PLUS a compact paste-back block (also saved under
data/owner_diagnostics_<timestamp>.json) — paste that block back to the
agent session so failures map to exact fixes.

Usage (PowerShell, from the repo root, LM Studio running):
    .\.venv\Scripts\python.exe scripts\owner_diagnostics.py

Notes:
  * chat tasks create real goals/projects in data/assistant.db (that is
    what a real session does; keep it in mind);
  * if self-evolution succeeds it installs a real 'reverse_words' tool;
  * nothing destructive runs: all probes are read-only or reversible,
    and Level 2/3 write actions are never bypassed.
"""

from __future__ import annotations

import json
import platform
import re
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
logging.disable(logging.INFO)  # keep the paste-back output readable

RESULTS: List[Dict[str, Any]] = []


def record(section: str, name: str, status: str, detail: str = "",
           **extra: Any) -> None:
    RESULTS.append({"section": section, "name": name, "status": status,
                    "detail": str(detail)[:300], **extra})
    mark = {"pass": "[PASS]", "fail": "[FAIL]", "skip": "[SKIP]",
            "offline": "[OFFLINE]"}.get(status, "[????]")
    print(f"  {mark} {name}")
    if detail:
        print(f"         {str(detail)[:240]}")


def guard(section: str, name: str, fn: Callable[[], Tuple[str, str]]) -> None:
    """One broken check must never stop the pack."""
    try:
        status, detail = fn()
        record(section, name, status, detail)
    except Exception as exc:
        record(section, name, "fail", f"harness error: {exc!r}")


# ── section 0: environment ───────────────────────────────────────────────────

def lm_studio_reachability() -> Tuple[str, str]:
    import httpx
    from app.config import settings
    base = str(settings.LM_STUDIO_URL).rstrip("/")
    try:
        t0 = time.monotonic()
        res = httpx.get(f"{base}/models", timeout=5.0)
        elapsed = (time.monotonic() - t0) * 1000
        if res.status_code != 200:
            return "fail", f"HTTP {res.status_code} from {base}/models"
        models = [m.get("id") for m in res.json().get("data", [])]
        record("env", "loaded models", "pass",
               f"{len(models)}: {', '.join(str(m) for m in models[:6])}")
        want = {settings.FAST_MODEL: "fast",
                settings.MAIN_MODEL: "main"}
        # Exact id match only (a leading '<vendor>/' prefix is stripped —
        # 'qwen/qwen3-14b' is 'qwen3-14b'). A substring test would report
        # 'qwen3.5-9b' as loaded when only the 'omnicoder-qwen3.5-9b-…'
        # merge is — a different model.
        def _loaded(model_id):
            ids = {str(m) for m in models}
            stripped = {str(m).split("/", 1)[-1] for m in models
                        if "/" in str(m)}
            return str(model_id) in ids or str(model_id) in stripped
        from app.llm import llm_client
        for model_id, role in want.items():
            label = f"model for {role} route"
            configured = str(model_id or "").strip()
            if configured.lower() in ("", "auto"):
                # MAIN_MODEL/FAST_MODEL=auto: the runtime scans the loaded
                # models and uses the best one for the route (role-scored:
                # size, chat tuning, specialism — never closeness to a
                # stale id, and fine-tunes are never excluded for their
                # tuning). That is a policy, not a failure.
                picked = llm_client.select_loaded_fallback(
                    "auto", models, role=role)
                record("env", f"{label}: auto", "pass" if picked else "fail",
                       f"auto → '{picked}' (role-scored best loaded {role} "
                       f"model)" if picked else
                       "auto set but no chat-capable model is loaded")
                continue
            if _loaded(configured):
                record("env", f"{label}: {configured}", "pass", "loaded")
            else:
                # The runtime routes to the best loaded model for the
                # route (llm.py, 2026-09-05 role-scored selection) — name
                # that decision and the escape hatches in the paste-back,
                # while the row itself stays FAIL: the config is still
                # not pointing at a loaded id.
                chosen = llm_client.select_loaded_fallback(
                    configured, models, role=role)
                detail = (f"NOT loaded — runtime auto-picks '{chosen}' "
                          f"(best loaded {role} model); set "
                          f"{role.upper()}_MODEL=auto or a loaded id"
                          if chosen else
                          "NOT loaded — no other usable models loaded; "
                          "simulation")
                record("env", f"{label}: {configured}", "fail", detail)
        return "pass", f"reachable at {base} ({elapsed:.0f} ms)"
    except Exception as exc:
        return "fail", f"LM Studio unreachable at {base}: {exc}"


def llm_latency_probe() -> Tuple[str, str]:
    from app.llm import llm_client
    t0 = time.monotonic()
    res = llm_client.generate_chat_completion(
        [{"role": "user", "content": "Reply with exactly: ok"}],
        complexity="fast", max_tokens=8)
    elapsed = time.monotonic() - t0
    content = (((res or {}).get("choices") or [{}])[0]
               .get("message", {}).get("content", ""))
    if "simulated" in str(content).lower() or not str(content).strip():
        return "offline", f"provider offline (reply: {str(content)[:60]!r})"
    return "pass", f"{elapsed:.1f}s — first tokens: {str(content)[:40]!r}"


# ── section A: brain-online chat battery ─────────────────────────────────────

def _chat(task: str, complexity: str = "fast") -> Dict[str, Any]:
    from app.cognition.cognitive_pipeline import CognitivePipeline
    return CognitivePipeline.process_chat(user_text=task, complexity=complexity)


def _reply(res: Dict[str, Any]) -> str:
    return str(res.get("assistant_reply", ""))


def _extract_numbers(text: str) -> List[float]:
    return [float(m.replace(",", "")) for m in
            re.findall(r"\d+(?:[.,]\d+)?", text)]


SCRATCH = Path("data").resolve() / "diagnostics_scratch"


def d1_arithmetic() -> Tuple[str, str]:
    res = _chat("What is 17 * 24?")
    numbers = _extract_numbers(_reply(res))
    gt = 408 in numbers or any(abs(n - 408) < 0.01 for n in numbers)
    status = "pass" if gt and res.get("success") else "fail"
    return status, (f"verified answer 408={gt} | lifecycle="
                    f"{res.get('goal_lifecycle_state')} | reply="
                    f"{_reply(res)[:120]!r}")


def d2_csv_analysis() -> Tuple[str, str]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    csv = SCRATCH / "sales.csv"
    amounts = [120.50, 89.99, 230.00, 45.25, 310.75]
    csv.write_text("date,product,amount\n"
                   "2026-08-01,widget,120.50\n2026-08-02,gadget,89.99\n"
                   "2026-08-03,widget,230.00\n2026-08-04,gizmo,45.25\n"
                   "2026-08-05,gadget,310.75\n")
    gt_mean = statistics.mean(amounts)  # 159.298
    res = _chat(f"Analyze the CSV file at {csv} and tell me the average "
                f"of the amount column.")
    numbers = _extract_numbers(_reply(res))
    got = any(abs(n - gt_mean) < 0.01 for n in numbers)
    used_data_tool = any("analyz" in str(a).lower() or "data" in str(a).lower()
                         for a in res.get("executed_actions") or [])
    status = "pass" if got else "fail"
    # F8: the reply is the attribution evidence for a 'mean missing' fail
    # (the action list is summarized by used_data_tool above).
    return status, (f"mean {gt_mean:.3f} verified={got} | data tool used="
                    f"{used_data_tool} | lifecycle="
                    f"{res.get('goal_lifecycle_state')} | reply="
                    f"{_reply(res)[:140]!r}")


def d3_task_creation() -> Tuple[str, str]:
    marker = f"diag-{uuid.uuid4().hex[:6]}"
    res = _chat(f"Create a task: review the quarterly budget report "
                f"({marker}), with priority high.")
    time.sleep(0.2)
    from app.tasks import TaskManager
    rows = TaskManager.get_all_tasks()
    created = any(marker in str(getattr(t, "title", "")) for t in rows)
    status = "pass" if created else "fail"
    return status, (f"task row with marker exists={created} | lifecycle="
                    f"{res.get('goal_lifecycle_state')} | actions="
                    f"{[str(a)[:60] for a in (res.get('executed_actions') or [])][:2]}")


def d4_compound_goal_conditions() -> Tuple[str, str]:
    """1A evidence: with the model ONLINE, does the semantic interpreter
    enumerate success conditions for EVERY step of a compound request,
    or still just step 1?"""
    task = ("Find files matching requirements, read the first one, "
            "summarize it, then check the tests still pass.")
    res = _chat(task)
    from app.cognition.goal_interpreter import SemanticGoalInterpreter
    rep = SemanticGoalInterpreter.interpret_goal(task)
    conditions = [str(c) for c in rep.success_conditions]
    steps_covered = sum(1 for kw in ["path", "read", "summar", "test"]
                        if any(kw in c.lower() for c in conditions))
    status = "pass" if steps_covered >= 3 else "fail"
    return status, (f"{steps_covered}/4 step-keywords appear in conditions "
                    f"{conditions} | lifecycle="
                    f"{res.get('goal_lifecycle_state')} | actions="
                    f"{[str(a)[:60] for a in (res.get('executed_actions') or [])][:3]}")


def d5_diagnostic_interpretation() -> Tuple[str, str]:
    res = _chat("Why is my computer so slow lately?")
    reply = _reply(res)
    offline = "simulated response" in reply.lower()
    mentions_evidence = any(k in reply.lower() for k in
                            ["cpu", "memory", "disk", "process", "load",
                             "temperature", "startup"])
    status = "skip" if offline else ("pass" if mentions_evidence else "fail")
    return status, (f"interpreted real evidence={mentions_evidence} | "
                    f"lifecycle={res.get('goal_lifecycle_state')} | "
                    f"reply={reply[:160]!r}")


def d6_self_evolution() -> Tuple[str, str]:
    """The system's hardest capability. Ground truth: after the cycle, a
    reverse_words capability exists AND actually reverses words."""
    res = _chat("Create a new tool called reverse_words that takes a "
                "string and returns the words in reverse order. Write it, "
                "test it, and install it as a permanent capability.")
    # F8: the reply is the attribution evidence ('plan document instead of
    # an installed tool' is only visible in what the agent actually said).
    reply_excerpt = _reply(res)[:160]
    time.sleep(0.2)
    from app.cognition import tool_registry as tr
    reg = tr.get_shared_registry()
    entry = reg.effective_capability("reverse_words")
    if entry is None:
        # Actions BEFORE the reply (the d7 precedent): the 300-char record
        # cap then eats only the reply tail. 'Executed registered tool
        # synthesize_tool' vs no such action distinguishes a synthesis
        # FAILURE (model wrote unusable code) from the chain never being
        # reached at all — the two need different fixes.
        actions = [str(a)[:60] for a in (res.get("executed_actions") or [])][:2]
        return "fail", (f"tool NOT installed | lifecycle="
                        f"{res.get('goal_lifecycle_state')} | "
                        f"actions={actions} | "
                        f"reply={reply_excerpt!r}")
    out = reg.execute_registered_tool(
        "reverse_words", {"text": "one two three"}) or {}
    got = str(out.get("result", out.get("output", out))).strip()
    ok = "three two one" in got
    return ("pass" if ok else "fail"), (
        f"tool installed=True, executes correctly={ok} "
        f"(got {got!r}) | lifecycle={res.get('goal_lifecycle_state')} | "
        f"reply={reply_excerpt!r}")


def d8_code_execution() -> Tuple[str, str]:
    """Offline baseline: arity crash on code_explain. With the brain on,
    does code execution complete with the right output? (GT 5050)"""
    res = _chat("Run this Python code and tell me the output: "
                "print(sum(range(1, 101)))")
    numbers = _extract_numbers(_reply(res))
    ok = any(abs(n - 5050) < 0.01 for n in numbers)
    return ("pass" if ok else "fail"), (
        "verified 5050=%s | lifecycle=%s | actions=%s | reply=%r"
        % (ok, res.get("goal_lifecycle_state"),
           [str(a)[:60] for a in (res.get("executed_actions") or [])][:2],
           _reply(res)[:140]))


def d9_project_setup() -> Tuple[str, str]:
    """Offline baseline: misrouted to read_document (arity crash) while the
    decomposition side-effect still created the project. GT: a project row
    exists whose DESCRIPTION is the original request (not clobbered by a
    milestone) and which carries milestones."""
    marker = "diag-%s" % uuid.uuid4().hex[:6]
    task = ("Set up a project to organize my photo collection (%s): "
            "scan the pictures folder, group photos by date, find "
            "duplicates, then report a summary." % marker)
    res = _chat(task)
    time.sleep(0.2)
    from app.cognition.runtime import CognitiveRuntime
    projects = list(getattr(CognitiveRuntime.get_instance(),
                            "project_manager")._projects.values())
    hit = next((p for p in projects
                if marker in str(getattr(p, "description", ""))), None)
    if hit is None:
        any_marker = any(marker in str(getattr(p, "name", "")) for p in projects)
        return "fail", ("no project with intact description (name-only hit=%s) "
                        "| lifecycle=%s | actions=%s"
                        % (any_marker, res.get("goal_lifecycle_state"),
                           [str(a)[:60] for a in (res.get("executed_actions") or [])][:2]))
    milestones = list(getattr(hit, "milestones", []) or [])
    return "pass", ("project created, description intact, %d milestones | "
                    "lifecycle=%s | actions=%s"
                    % (len(milestones), res.get("goal_lifecycle_state"),
                       [str(a)[:60] for a in (res.get("executed_actions") or [])][:2]))


def d7_control_file_search() -> Tuple[str, str]:
    """Control: local file search must FIND a file genuinely in scope.

    Live incident (2026-09-01): D7 searched 'goal_verifier' — a REPO file
    — but the repo lives on F:\\, outside the C:\\Users\\<owner> scope the
    search walks, so the control measured the repo's LOCATION, not the
    search capability. The searched term is now a unique marker planted
    in the OWNER'S HOME (in scope on every platform) and deleted after
    the check. Ground truth is the marker's FOUND PATH in the tool
    results/reply — a query mention alone is not evidence (the query
    name is already known to the agent)."""
    marker_name = f"arena_diag_marker_{uuid.uuid4().hex[:8]}"
    marker_path = Path.home() / marker_name
    marker_path.write_text(
        "Arena owner diagnostics marker — safe to delete.\n", encoding="utf-8")
    try:
        res = _chat(f"Find files matching {marker_name}, then tell me "
                    f"how many you found.")
    finally:
        try:
            marker_path.unlink()
        except OSError:
            pass  # best-effort cleanup; the marker file is inert
    blob = " ".join(str(a) for a in (res.get("executed_actions") or []))
    reply = _reply(res)
    found = str(marker_path) in blob or str(marker_path) in reply
    no_browser = not any("browser" in str(a).lower()
                         for a in (res.get("executed_actions") or []))
    status = "pass" if found and no_browser else "fail"
    # The executed actions are the primary attribution evidence for a miss
    # (the 2026-09-01 live run truncated the reply excerpt at
    # '[NATIVE OS ACTIONS E' — exactly where the evidence was). They are
    # placed BEFORE the reply excerpt so record()'s 300-char cap eats only
    # the reply tail.
    actions = [str(a)[:60] for a in (res.get("executed_actions") or [])][:2]
    return status, (f"marker in home found={found}, "
                    f"browser_touched={not no_browser} | "
                    f"lifecycle={res.get('goal_lifecycle_state')} | "
                    f"actions={actions} | "
                    f"reply={reply[:70]!r}")


# ── section B: hardware-bound tool probes ────────────────────────────────────

def h_screen_capture() -> Tuple[str, str]:
    """PASS: capture saved a real file. FAIL: claimed success with no
    file (dishonest). SKIP: honest typed unavailability (no display in
    this environment) - an environment fact, not a tool bug."""
    from app.tools.screen_capture import ScreenCaptureTool
    res = ScreenCaptureTool.capture_screen() or {}
    path = str(res.get("file_path") or res.get("path") or "")
    exists = bool(path) and Path(path).exists()
    if res.get("success") and exists:
        return "pass", "captured %s (%d bytes)" % (path[:90], Path(path).stat().st_size)
    if res.get("success"):
        return "fail", "claimed success but no file at %r" % path[:90]
    return "skip", "unavailable: %s" % str(res.get("error", ""))[:140]


def h_vlm_status() -> Tuple[str, str]:
    """The tool's CONTRACT is an honest status report - 'VLM not
    installed' is a PASS of the contract (the ping-test lesson: judge
    the measurement, not the environment)."""
    from app.cognition import tool_registry as tr
    out = tr.get_shared_registry().execute_registered_tool("vlm_status", {}) or {}
    honest = "available" in out and ("note" in out or "engine" in out)
    return ("pass" if honest else "fail"), (
        "available=%s | %s" % (out.get("available"),
                               str(out.get("note", ""))[:120]))


def h_lora_status() -> Tuple[str, str]:
    from app.cognition import tool_registry as tr
    out = tr.get_shared_registry().execute_registered_tool("lora_status", {})
    return "pass" if (out or {}).get("success") else "fail", str(out)[:180]


def h_adb_phone() -> Tuple[str, str]:
    from app.tools.android_adb_controller import AndroidADBController
    if not AndroidADBController.is_adb_available():
        return "skip", "adb binary not on PATH"
    res = AndroidADBController.list_connected_devices() or {}
    devices = res.get("devices") or res.get("result") or res
    n = len(devices) if isinstance(devices, list) else "?"
    return "pass", f"connected devices: {str(devices)[:160]}"


def h_audio() -> Tuple[str, str]:
    try:
        import pyaudio  # noqa: F401
    except Exception as exc:
        return "skip", f"pyaudio unavailable: {exc}"
    try:
        pa = pyaudio.PyAudio()
        count = pa.get_device_count()
        pa.terminate()
        return "pass", f"{count} audio devices"
    except Exception as exc:
        return "fail", f"pyaudio present but device listing failed: {exc}"


def h_browser_extract() -> Tuple[str, str]:
    from app.cognition import tool_registry as tr
    out = tr.get_shared_registry().execute_registered_tool(
        "browser_extract", {"url": "https://example.com"}) or {}
    blob = json.dumps(out, default=str)[:400]
    ok = (out.get("success") and
          any(k in blob.lower() for k in ["example", "domain", "title"]))
    return ("pass" if ok else "fail"), blob[:220]


def h_list_apps() -> Tuple[str, str]:
    from app.tools.app_inventory import SystemAppInventory
    res = SystemAppInventory.scan_installed_applications() or {}
    n = res.get("total_apps_count")
    return ("pass" if isinstance(n, int) and n > 0 else "fail"), \
        f"{n} applications discovered"


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("═" * 72)
    print("ARENA OWNER DIAGNOSTICS — run on the machine with LM Studio/hardware")
    print(f"python {sys.version.split()[0]} | {platform.system()} "
          f"{platform.release()} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 72)

    print("\n── Section 0: environment " + "─" * 44)
    guard("env", "LM Studio reachability", lm_studio_reachability)
    guard("env", "LLM latency probe (fast route)", llm_latency_probe)

    print("\n── Section A: brain-online chat battery " + "─" * 32)
    guard("A", "D1 arithmetic 17*24 (GT 408)", d1_arithmetic)
    guard("A", "D2 CSV mean (GT 159.298)", d2_csv_analysis)
    guard("A", "D3 task creation (GT DB row)", d3_task_creation)
    guard("A", "D4 compound goal conditions (1A evidence)", d4_compound_goal_conditions)
    guard("A", "D5 diagnostic interpretation (real evidence)", d5_diagnostic_interpretation)
    guard("A", "D6 self-evolution reverse_words (GT executes)", d6_self_evolution)
    guard("A", "D7 control: home-marker file search (offline PASS)", d7_control_file_search)
    guard("A", "D8 code execution (GT 5050)", d8_code_execution)
    guard("A", "D9 project setup (GT project + intact description)", d9_project_setup)

    print("\n── Section B: hardware-bound probes " + "─" * 36)
    guard("B", "screen capture (GT file exists)", h_screen_capture)
    guard("B", "VLM status", h_vlm_status)
    guard("B", "LoRA/GPU status", h_lora_status)
    guard("B", "ADB phone devices", h_adb_phone)
    guard("B", "audio devices", h_audio)
    guard("B", "browser extract example.com (GT content)", h_browser_extract)
    guard("B", "installed apps scan", h_list_apps)

    # ── paste-back block ─────────────────────────────────────────────────
    counts: Dict[str, int] = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + "═" * 72)
    print(f"TOTAL: {counts.get('pass', 0)} passed, {counts.get('fail', 0)} "
          f"failed, {counts.get('skip', 0)} skipped, "
          f"{counts.get('offline', 0)} offline-only")

    compact = [{"s": r["section"], "n": r["name"], "st": r["status"],
                "d": r["detail"][:200]} for r in RESULTS]
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = Path("data") / f"owner_diagnostics_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compact, indent=1, ensure_ascii=False),
                        encoding="utf-8")

    print("\n────────────── PASTE THIS BLOCK BACK ──────────────")
    print("<<<DIAG")
    print(json.dumps(compact, ensure_ascii=False))
    print("DIAG>>>")
    print(f"(also saved to {out_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
