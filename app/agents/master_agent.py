import os
import re
import json
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.llm import llm_client, ModelCompletionUnavailable, require_real_completion
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_monitor import HardwareMonitor

# Tool modules are imported inside the branch that invokes them.  Importing the
# orchestrator must not require every optional tool dependency to be installed.
from app.memory.human_nature_engine import HumanNatureEngine
from app.memory.coworker_brain import CoworkerBrain

# Media-consumption verbs: the second step of compound requests like
# 'find the file kaba and play it'. They are instruction vocabulary (never
# filename content — see goal_interpreter._QUERY_COMMAND_WORDS) and they
# name a capability class (playback) the tool universe may or may not
# provide. Underscore is a SEPARATOR, not a word char, so tool names like
# 'play_media_file' match while 'display'/'playlist' never do.
_MEDIA_VERB_RE = re.compile(r"(?:^|[^a-z0-9])(?:play|plays|playing|watch|listen|stream|view)(?:$|[^a-z0-9])", re.IGNORECASE)
_PLAYBACK_AD_RE = re.compile(r"(?:^|[^a-z0-9])play(?:s|back|ing)?(?:$|[^a-z0-9])", re.IGNORECASE)


def _no_media_playback_capability() -> bool:
    """True when NO registered capability advertises media playback.

    Checks the manifest (action name + description) and the dynamic tool
    registry. Self-limiting by design: the day a playback tool is
    installed (runtime or manifest), this returns False and the honest
    'cannot play' note disappears — the note tracks reality, it is not a
    hardcoded confession."""
    try:
        from app.tools.manifest import get_tool_manifest
        for name, entry in get_tool_manifest().items():
            blob = f"{name} {entry.get('description') or ''}"
            if _PLAYBACK_AD_RE.search(blob):
                return False
    except Exception:
        pass
    try:
        from app.cognition.tool_registry import get_shared_registry
        for name in list(getattr(get_shared_registry(), "_registry", {}) or {}):
            if _PLAYBACK_AD_RE.search(str(name)):
                return False
    except Exception:
        pass
    return True
from app.cognition.reasoning_cycle import ReasoningCycle, ReasoningAction, ReasoningDecision
from app.cognition.belief_engine import BeliefEngine
from app.cognition.execution_result import ExecutionResult, ExecutionStatus

class MasterAgentOrchestrator:
    """
    Unified Master Agent & All-in-One Autonomous Router.
    Merates ALL domain tools (OS control, app launching, file search, vision, web research,
    cybersecurity/pentesting, OpSec, data analysis, sandboxes, and taught skills) into a single
    intelligent human-like agent.
    """

    @classmethod
    def execute_proposal(
        cls,
        proposal: Any,
        user_text: str,
        complexity: str = "fast",
        world_model: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes a specific ActionProposal directly through capability resolvers,
        producing a structured ExecutionResult carrying raw execution facts and outputs.
        Uses the provided authoritative world_model instance if supplied.
        Does NOT directly write WorldModel observations; environmental observations are ingested
        downstream via the Perception Layer (ObservationCollector).
        """
        action_type = getattr(proposal, "action_type", str(proposal)).lower().strip()
        proposal_id = getattr(proposal, "proposal_id", f"prop_{os.urandom(4).hex()}")
        payload = getattr(proposal, "payload", {}) if hasattr(proposal, "payload") else {}
        executed_actions = []
        execution_facts: List[Dict[str, Any]] = []
        raw_output_data: Dict[str, Any] = {}
        execution_success = True

        if action_type in ["open_application", "launch_app"]:
            from app.tools.app_inventory import SystemAppInventory

            app_name = payload.get("app_name") or payload.get("app") or payload.get("app_query") or payload.get("query")
            if not app_name:
                match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', user_text.lower())
                app_name = match.group(1).strip() if match else ""
                # A capture that is ONLY a generic placeholder names nothing
                # ('open the app' must not launch an app literally named
                # 'app' — same invention family as the old explorer default).
                if app_name.lower().strip() in {
                    "app", "application", "the app", "it", "that", "them",
                    "please", "now", "something",
                }:
                    app_name = ""
            if not app_name:
                # P0 bottleneck #9: NEVER invent a default application. The
                # old 'explorer' fallback turned an ambiguous request into a
                # silently WRONG action — and because explorer is actually
                # installed, the wrong request SUCCEEDED. Ambiguity is a
                # clarification request, not a guess.
                execution_success = False
                clarification = (
                    "No application was specified — I don't know which application "
                    "you mean. Which application should I open?"
                )
                executed_actions.append(clarification)
                raw_output_data["launch_res"] = {
                    "success": False,
                    "error": "No application specified in the request.",
                    "clarification_required": True,
                }
                execution_facts.append({
                    "subject": "application_launch",
                    "predicate": "launch_target",
                    "value": "unspecified",
                    "source": "master_agent",
                })
            else:
                res = SystemAppInventory.launch_any_app(app_name)
                raw_output_data["launch_res"] = res
                if res.get("success"):
                    executed_actions.append(f"Launched application '{res.get('app_name', app_name).title()}' on your PC.")
                    execution_facts.append({
                        "subject": res.get("app_name", app_name).lower(),
                        "predicate": "launch_command",
                        "value": "succeeded",
                        "source": "system_app_inventory"
                    })
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to launch application '{app_name}': {res.get('error', 'Launch error')}")
                    execution_facts.append({
                        "subject": app_name.lower(),
                        "predicate": "launch_command",
                        "value": "failed",
                        "source": "system_app_inventory"
                    })

        elif action_type == "web_search":
            from app.tools.desktop_control import DesktopControl

            query_term = payload.get("query_term") or payload.get("query") or ""
            if not query_term:
                # Fall back to deterministic extraction before using the raw text.
                try:
                    from app.cognition.tool_matcher import _SEARCH_AFTER_RE
                    import re as _re
                    cleaned = _re.sub(r"(?:can\s+you\s+)?(?:open|launch|start|use)\s+\w+\s+(?:and|then|to)\s+", "", user_text, flags=_re.I)
                    search = _SEARCH_AFTER_RE.search(cleaned)
                    if search:
                        query_term = search.group(1).strip().rstrip("?.!")
                        query_term = _re.sub(r"^\s*(?:for\s+)?(?:me\s+|my\s+)", "", query_term, flags=_re.I).strip()
                except Exception:
                    pass
            if not query_term:
                query_term = user_text  # honest: couldn't extract a clean query
            url = f"https://www.youtube.com/results?search_query={str(query_term).replace(' ', '+')}" if "youtube" in str(query_term).lower() or "youtube" in user_text.lower() else f"https://www.google.com/search?q={str(query_term).replace(' ', '+')}"
            # Use the OS default browser — webbrowser.open() picks whatever
            # the owner has configured (Chrome, Edge, Firefox, Brave, ...).
            # Never hardcode a specific browser.
            d_res = DesktopControl.open_url(url)
            raw_output_data["url"] = url
            raw_output_data["query_term"] = query_term
            if d_res.get("success", False):
                executed_actions.append(f"Opened default browser and searched for '{query_term}'.")
                execution_facts.append({
                    "subject": "web_search",
                    "predicate": "search_results",
                    "value": url,
                    "source": "web_researcher"
                })
            else:
                execution_success = False
                executed_actions.append(f"Failed to open web browser for search '{query_term}'.")

        elif action_type == "search_files":
            from app.tools.universal_filesystem import UniversalFilesystem

            search_query = payload.get("query") or payload.get("file_name") or payload.get("search_term") or user_text

            # Determine search limit: normal=5, "all" or all_matches=up to 1000
            search_limit = 5
            all_matches = payload.get("all_matches", False)
            explicit_max = payload.get("max_results")

            if explicit_max is not None:
                search_limit = max(1, min(int(explicit_max), 1000))
            elif all_matches or "all" in str(search_query).lower().split():
                search_limit = 1000

            # D7 (live 2026-09-01): the payload's scope/root_dir used to be
            # DROPPED here — a planner that picked a scope had it silently
            # ignored (payload contract leak). They are honored now.
            # Owner report #5 (2026-09-02): an explicit root_dir is a
            # CONSTRAINT — no silent escalation to other drives. A planner
            # that wants the D7 wrong-root recovery must request it in the
            # payload (allow_escalation=true); a constrained miss is honest
            # evidence the replan layer acts on.
            matched = UniversalFilesystem.search_filesystem(
                search_query,
                root_dir=payload.get("root_dir"),
                scope=payload.get("scope"),
                max_results=search_limit + 1,
                allow_escalation=bool(payload.get("allow_escalation", False)))
            truncated = len(matched) > search_limit
            if truncated:
                matched = matched[:search_limit]
            result_found = bool(matched)
            raw_output_data["matched_files"] = matched
            raw_output_data["result_found"] = result_found
            raw_output_data["query"] = search_query
            raw_output_data["max_results"] = search_limit
            raw_output_data["truncated"] = truncated

            if result_found:
                executed_actions.append(f"Found local file '{matched[0]['file_name']}' at {matched[0]['file_path']}.")
                execution_facts.append({
                    "subject": "filesystem",
                    "predicate": "file_path",
                    "value": matched[0]['file_path'],
                    "source": "universal_filesystem"
                })
                execution_facts.append({
                    "subject": matched[0]['file_name'],
                    "predicate": "status",
                    "value": "identified",
                    "source": "universal_filesystem",
                    "entity_type": "file",
                    "attributes": {"file_path": matched[0]['file_path']}
                })
                # Add execution facts for additional results (beyond first)
                for extra_file in matched[1:]:
                    if isinstance(extra_file, dict) and extra_file.get("file_path"):
                        execution_facts.append({
                            "subject": extra_file.get("file_name", "file"),
                            "predicate": "status",
                            "value": "identified",
                            "source": "universal_filesystem",
                            "entity_type": "file",
                            "attributes": {"file_path": extra_file["file_path"]}
                        })
                if len(matched) > 1:
                    executed_actions.append(f"({len(matched)} total matches found, limit={search_limit})")
            else:
                executed_actions.append(f"Searched local filesystem for '{search_query}' (no matching files found).")
                execution_facts.append({
                    "subject": "filesystem",
                    "predicate": "file_search_result",
                    "value": "no_matching_files_found",
                    "source": "universal_filesystem"
                })

            # Honest partial-completion (live owner report 2026-09-05):
            # a compound request whose consumption step ('find kaba and
            # PLAY it') has no registered capability must not silently
            # drop the unfulfilled half. The grounded step (search) runs
            # and reports; the ungrounded step is stated honestly — the
            # assistant never pretends the request was fully served, and
            # never asks the owner for information (file type) it can
            # determine itself from the search results.
            if _MEDIA_VERB_RE.search(user_text or "") and _no_media_playback_capability():
                executed_actions.append(
                    "No media playback capability is registered — I can locate media files but not play them."
                )

        elif action_type in ("move_file", "copy_file_verified"):
            # File management: resolve bare names ('move kaba.mp3 to my music
            # folder') to real paths via filesystem search, then execute the
            # verified move/copy. Live bug: the matcher routed these but the
            # payload carried no operands, execution failed, and the LLM
            # apologized about lacking file access.
            from pathlib import Path as _P
            from app.tools.universal_filesystem import UniversalFilesystem

            def _find_by_name(name: str) -> Dict[str, Any]:
                """Bare name -> path evidence under the user's home dir."""
                direct = _P(name).expanduser()
                if direct.exists():
                    return {"resolved": str(direct)}
                hits = UniversalFilesystem.search_filesystem(
                    name, root_dir=str(_P.home()), max_results=4)
                exact = [h for h in hits if h.get("file_name", "").lower() == name.lower()]
                pool = exact or hits
                if len(pool) == 1:
                    return {"resolved": pool[0]["file_path"]}
                if not pool:
                    return {"error": f"couldn't find any file matching '{name}'"}
                return {
                    "error": f"found {len(pool)} files matching '{name}': "
                             + "; ".join(h["file_path"] for h in pool[:4])
                             + " — tell me which one",
                    "matches": [h["file_path"] for h in pool[:4]],
                }

            _KNOWN_FOLDERS = {
                "music": "Music", "music folder": "Music", "my music": "Music",
                "my music folder": "Music", "desktop": "Desktop",
                "my desktop": "Desktop", "documents": "Documents",
                "my documents": "Documents", "documents folder": "Documents",
                "downloads": "Downloads", "download folder": "Downloads",
                "my downloads": "Downloads", "pictures": "Pictures",
                "my pictures": "Pictures", "photos": "Pictures",
                "videos": "Videos", "my videos": "Videos", "movies": "Videos",
            }

            src = payload.get("source_path")
            if not src:
                src_name = payload.get("source_name")
                if not src_name:
                    # LLM-proposed payloads may carry other key spellings.
                    src_name = (payload.get("file_name") or payload.get("name")
                                or payload.get("query"))
                if src_name:
                    found = _find_by_name(str(src_name))
                    if found.get("error"):
                        executed_actions.append(
                            f"Couldn't {action_type}: {found['error']}.")
                        execution_success = False
                        src = None
                    else:
                        src = found["resolved"]
            dst = payload.get("destination_path")
            dst_name = payload.get("destination_name")
            if src and not dst:
                if dst_name:
                    key = str(dst_name).strip().lower().rstrip(".,!?")
                    folder = _KNOWN_FOLDERS.get(key)
                    if folder:
                        dst = str(_P.home() / folder / _P(src).name)
                    elif re.search(r"\.[A-Za-z0-9]{2,6}$", str(dst_name)):
                        # 'rename london.mp3 to test.mp3' — same directory.
                        dst = str(_P(src).parent / str(dst_name))
                    else:
                        dst_dir = _P(dst_name).expanduser()
                        if dst_dir.is_dir():
                            dst = str(dst_dir / _P(src).name)
                        else:
                            executed_actions.append(
                                f"Couldn't resolve destination '{dst_name}' — name the "
                                "folder (e.g. 'my music folder' or 'my desktop').")
                            execution_success = False
            if src and dst and execution_success:
                if action_type == "move_file":
                    res = UniversalFilesystem.rename_or_move(src, dst)
                else:
                    res = UniversalFilesystem.copy_file_verified(src, dst)
                raw_output_data["file_op_res"] = res
                if res.get("success"):
                    verb = "Moved" if action_type == "move_file" else "Copied"
                    executed_actions.append(
                        f"{verb} '{_P(src).name}' -> '{dst}'.")
                    execution_facts.append({
                        "subject": _P(src).name.lower(),
                        "predicate": "file_path",
                        "value": dst,
                        "source": "universal_filesystem",
                    })
                else:
                    execution_success = False
                    executed_actions.append(f"File operation failed: {res.get('error')}")
            elif not execution_success:
                raw_output_data["file_op_error"] = executed_actions
            else:
                executed_actions.append(
                    "Couldn't identify which file to operate on — name the file "
                    "(e.g. 'move kaba.mp3 to my music folder').")
                execution_success = False

        elif action_type == "delete_files":
            # Reversible delete: resolve names -> paths under the home
            # directory, then move to the recoverable trash area. Level 3:
            # this branch only runs after the owner approved it in chat.
            from pathlib import Path as _P
            from app.tools.universal_filesystem import UniversalFilesystem

            names = payload.get("names") or ([payload["name"]] if payload.get("name") else [])
            explicit_paths = payload.get("file_paths") or payload.get("paths") or []
            targets: list = list(explicit_paths)
            unresolved: list = []
            for n in names:
                if not n:
                    continue
                direct = _P(str(n)).expanduser()
                if direct.exists():
                    targets.append(str(direct))
                    continue
                hits = UniversalFilesystem.search_filesystem(
                    str(n), root_dir=str(_P.home()), max_results=50)
                if not hits:
                    unresolved.append(n)
                else:
                    targets.extend(h["file_path"] for h in hits)
            if unresolved:
                executed_actions.append(
                    "Couldn't find: " + ", ".join(f"'{u}'" for u in unresolved) + ".")
            if targets:
                res = UniversalFilesystem.trash_files(targets)
                raw_output_data["delete_res"] = res
                if res.get("trashed"):
                    executed_actions.append(
                        f"Deleted (moved to trash, recoverable): "
                        + ", ".join(m["original"] for m in res["trashed"])
                        + f". Restore from: {res.get('trash_session')}")
                    execution_facts.append({
                        "subject": "filesystem",
                        "predicate": "file_delete",
                        "value": f"{len(res['trashed'])} files to trash",
                        "source": "universal_filesystem",
                    })
                if res.get("errors"):
                    execution_success = False
                    executed_actions.append("Some deletions failed: " + "; ".join(res["errors"]))
            else:
                execution_success = False
                if not unresolved:
                    executed_actions.append("No files matched — nothing was deleted.")

        elif action_type in ["phone_command", "make_phone_call", "send_sms"]:
            from app.tools.android_adb_controller import AndroidADBController
            phone_query = payload.get("query") or payload.get("command") or payload.get("action") or user_text
            phone_lower = str(phone_query).lower()

            def _resolve_phone_target(query_text: str) -> tuple[str, str]:
                """Resolve a phone target WITHOUT EVER inventing a number
                (P0 bottleneck #10 — the old code fell back to a fake
                a hardcoded fake fallback number, which could text a real wrong person).

                Order: explicit payload number > dialable number in the
                request's recipient slot > contacts-store lookup by name.
                Unknown or ambiguous names become clarifications, never
                guesses. Returns (number, provenance_or_problem)."""
                num = str(payload.get("phone_number") or payload.get("number") or "").strip()
                if num:
                    return num, ""
                # A number in the recipient slot: 'text 0771234567 ...' or
                # 'call +256 700 123456'. Digits elsewhere (dates, quantities
                # in the message body) must never be assembled into a number.
                m_num = re.search(
                    r"(?:text|sms|call|dial|ring)\s+([+][0-9][0-9\s\-().]{5,}|[0-9][0-9\s\-().]{5,})",
                    str(query_text).lower())
                if m_num:
                    digits = "".join(c for c in m_num.group(1) if c.isdigit() or c == "+")
                    if len(digits) >= 3:
                        return digits, ""
                # Contact-name resolution against the REAL contacts store.
                m_name = re.search(
                    r"(?:text|sms|call|dial|ring)\s+([a-z][a-z'\u2019.\-]*)",
                    str(query_text).lower())
                # Filler words after the verb are not a recipient
                # ('send a text message', 'text me when you're done').
                _FILLER = {
                    "a", "an", "the", "to", "me", "him", "her", "them",
                    "back", "now", "please", "message", "msg", "text",
                    "sms", "someone", "anybody",
                }
                if m_name and m_name.group(1).strip() in _FILLER:
                    m_name = None
                if m_name:
                    name = m_name.group(1).strip()
                    try:
                        from app.tools.contacts import ContactsTool
                        matches = [c for c in ContactsTool.list_contacts(name) if c.get("name")]
                    except Exception as exc:
                        return "", f"contact lookup failed ({exc})"
                    with_phone = [c for c in matches if str(c.get("phone", "")).strip()]
                    if len(with_phone) == 1:
                        return str(with_phone[0]["phone"]).strip(), (
                            f"number resolved from contact '{with_phone[0]['name']}'")
                    if len(with_phone) > 1:
                        listing = ", ".join(
                            f"{c['name']} ({c['phone']})" for c in with_phone[:5])
                        return "", f"multiple contacts match '{name}': {listing}. Which one?"
                    if matches:
                        return "", (f"contact '{matches[0].get('name', name)}' has no "
                                    f"phone number stored")
                    return "", f"I don't have a contact named '{name}' with a phone number"
                return "", "no phone number or contact name was given"

            if "sms" in phone_lower or "text" in phone_lower or payload.get("sms_body"):
                num, resolution = _resolve_phone_target(phone_query)
                if not num:
                    # P0 #10: STOP. Never invent a number.
                    execution_success = False
                    executed_actions.append(
                        f"SMS not sent — {resolution}. Which number should I text?")
                    raw_output_data["phone_res"] = {
                        "success": False,
                        "error": f"Phone target unresolved: {resolution}.",
                        "clarification_required": True,
                    }
                else:
                    sms_msg = payload.get("sms_body") or payload.get("message")
                    if not sms_msg:
                        # Prefer the message body after the recipient name
                        # ('text John I'm running late' -> "I'm running late").
                        m_body = re.search(
                            r"(?:text|sms)\s+(?:[+]?[0-9][0-9\s\-().]{5,}|[a-z][a-z'\u2019.\-]*)\s+(.+)",
                            str(phone_query), re.I)
                        sms_msg = m_body.group(1).strip() if m_body else phone_query
                    adb_res = AndroidADBController.send_sms(num, str(sms_msg))
                    raw_output_data["phone_res"] = adb_res
                    if adb_res.get("success"):
                        provenance = f" ({resolution})" if resolution else ""
                        executed_actions.append(f"Sent SMS text to {num} via Android ADB{provenance}.")
                    else:
                        execution_success = False
                        executed_actions.append(f"Failed to send SMS to {num}: {adb_res.get('error', 'Device offline')}")

            elif "call" in phone_lower or "dial" in phone_lower or action_type == "make_phone_call":
                num, resolution = _resolve_phone_target(phone_query)
                if not num:
                    # P0 #10: STOP. Never invent a number.
                    execution_success = False
                    executed_actions.append(
                        f"Call not placed — {resolution}. Which number should I call?")
                    raw_output_data["phone_res"] = {
                        "success": False,
                        "error": f"Phone target unresolved: {resolution}.",
                        "clarification_required": True,
                    }
                else:
                    adb_res = AndroidADBController.make_phone_call(num)
                    raw_output_data["phone_res"] = adb_res
                    if adb_res.get("success"):
                        provenance = f" ({resolution})" if resolution else ""
                        executed_actions.append(f"Initiated phone call to {num} via Android ADB{provenance}.")
                    else:
                        execution_success = False
                        executed_actions.append(f"Failed to make phone call to {num}: {adb_res.get('error', 'Device offline')}")

            elif "photo" in phone_lower or "camera" in phone_lower:
                adb_res = AndroidADBController.take_camera_photo()
                if adb_res.get("success"):
                    executed_actions.append("Captured camera photo via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to capture camera photo: {adb_res.get('error', 'Device offline')}")

            elif "tap" in phone_lower and payload.get("x") is not None and payload.get("y") is not None:
                adb_res = AndroidADBController.tap_screen(int(payload["x"]), int(payload["y"]))
                if adb_res.get("success"):
                    executed_actions.append(f"Tapped screen coordinates ({payload['x']}, {payload['y']}) via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append("Failed to tap screen coordinates via ADB.")

            elif any(k in phone_lower for k in ["battery", "charge", "power", "level"]):
                adb_res = AndroidADBController.get_battery_status()
                if adb_res.get("success"):
                    executed_actions.append(adb_res.get("message", "Queried phone battery level via Android ADB."))
                else:
                    execution_success = False
                    executed_actions.append("Failed to query phone status via Android ADB.")

            elif any(k in phone_lower for k in ["open", "launch", "start"]) and any(app_k in phone_lower for app_k in ["whatsapp", "chrome", "settings", "camera", "youtube"]):
                pkg = "com.whatsapp" if "whatsapp" in phone_lower else ("com.android.chrome" if "chrome" in phone_lower else "com.android.settings")
                adb_res = AndroidADBController.launch_android_app(pkg)
                if adb_res.get("success"):
                    executed_actions.append(f"Launched Android app package '{pkg}' via ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to launch Android app '{pkg}': Device offline or package missing")

            else:
                # P0 Fix: Eliminates dangerous fallback that substituted battery status for unrecognized phone commands.
                # Returns explicit structured capability failure to trigger Plan B replanning.
                app_logger.warning(f"AndroidADBController: Unsupported phone_command query '{phone_query}'")
                return ExecutionResult(
                    proposal_id=proposal_id,
                    action_type=action_type,
                    execution_status=ExecutionStatus.FAILED,
                    attempted=True,
                    executed_actions=[],
                    assistant_reply=f"Capability execution failed: Unrecognized or unsupported phone command '{phone_query}'.",
                    error=f"Unsupported phone_command query '{phone_query}'",
                    outputs={"unsupported_capability": "unsupported_phone_command"}
                )

            if execution_success:
                execution_facts.append({
                    "subject": "phone",
                    "predicate": "adb_status",
                    "value": "succeeded",
                    "source": "android_adb"
                })

        elif action_type == "screen_capture":
            from app.tools.screen_capture import ScreenCaptureTool

            cap_res = ScreenCaptureTool.capture_screen()
            raw_output_data["cap_res"] = cap_res
            if cap_res.get("success"):
                executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")
                execution_facts.append({
                    "subject": "screen_capture",
                    "predicate": "screenshot",
                    "value": cap_res.get("file_name"),
                    "source": "screen_capture_tool"
                })
            else:
                execution_success = False
                executed_actions.append(f"Failed to capture desktop screen window: {cap_res.get('error', 'Capture error')}")

        elif action_type == "opsec_audit":
            from app.tools.opsec_manager import OpSecManagerTool

            audit_res = OpSecManagerTool.audit_digital_footprint("user@example.com")
            raw_output_data["audit_res"] = audit_res
            if audit_res.get("success", True):
                executed_actions.append(f"Audited OpSec footprint: {audit_res.get('total_exposures_found', 0)} findings.")
            else:
                execution_success = False
                executed_actions.append(f"OpSec audit failed: {audit_res.get('error', 'Audit failed')}")

        elif action_type == "daily_briefing":
            from app.tools.daily_briefing import DailyBriefingEngine

            brief_res = DailyBriefingEngine.generate_briefing(generate_audio=False)
            raw_output_data["brief_res"] = brief_res
            if brief_res.get("success", True):
                executed_actions.append("Generated Daily Executive Briefing.")
            else:
                execution_success = False
                executed_actions.append("Failed to generate Daily Executive Briefing.")

        elif action_type in ["investigate", "diagnostic"]:
            from app.tools.universal_filesystem import UniversalFilesystem

            probe_query = payload.get("query") or user_text
            matched_evidence = UniversalFilesystem.search_filesystem(probe_query, max_results=3)
            hw_stats = HardwareMonitor.get_hardware_stats()

            diag_details = []
            if matched_evidence:
                diag_details.append(f"Located {len(matched_evidence)} relevant file/log path(s): {matched_evidence[0]['file_path']}")
            diag_details.append(f"System status: CPU {hw_stats.get('cpu_used_percent', 0)}%, RAM {hw_stats.get('ram_used_percent', 0)}%")

            probe_summary = f"Gathered diagnostic evidence for '{probe_query[:40]}': " + "; ".join(diag_details)
            executed_actions.append(probe_summary)
            execution_facts.append({
                "subject": "diagnostic",
                "predicate": "evidence",
                "value": probe_summary,
                "source": "investigation_probe"
            })
            raw_output_data["probe_summary"] = probe_summary

        elif action_type in ["formulate_answer", "answer"]:
            executed_actions.append("Formulated direct conversational answer.")

        elif action_type == "workflow_execute":
            from app.tools.workflow_engine import WorkflowEngine

            wf_res = WorkflowEngine.execute_workflow(payload.get("workflow_name", "Task Workflow"), payload.get("steps", []))
            raw_output_data["wf_res"] = wf_res
            if wf_res.get("overall_success", True):
                executed_actions.append(f"Executed workflow '{wf_res.get('workflow_name')}'.")
            else:
                execution_success = False
                executed_actions.append(f"Workflow execution failed: '{wf_res.get('workflow_name')}'.")

        else:
            # Check ToolRegistry for dynamically registered capabilities
            try:
                # ONE runtime ToolRegistry (P0 #20): reuse the runtime's
                # event-bus-wired registry — a fresh ToolRegistry() here built
                # a duplicate on a second EventBus, missing dynamic
                # registrations and losing tool events.
                from app.cognition.tool_registry import get_shared_registry
                tr = get_shared_registry()
                if action_type in tr._registry:
                    tr_res = tr.execute_registered_tool(action_type, payload)
                    raw_output_data["tr_res"] = tr_res
                    if tr_res.get("success"):
                        executed_actions.append(f"Executed registered tool '{action_type}'.")
                    else:
                        # Honest owner-facing reply for missing operands
                        # (live owner report 2026-09-05): the raw validation
                        # string ('missing required parameter(s): …') is
                        # machine detail — the owner is told WHICH capability
                        # matched and WHAT it still needs, never a raw stack
                        # of payload keys as the answer.
                        tr_error = tr_res.get("error") or "unknown error"
                        missing_note = ""
                        if "missing required parameter" in str(tr_error):
                            missing_note = (" — your request didn't include "
                                            "the information this capability needs, "
                                            "and I won't invent it")
                        return ExecutionResult(
                            proposal_id=proposal_id,
                            action_type=action_type,
                            execution_status=ExecutionStatus.FAILED,
                            attempted=True,
                            executed_actions=[],
                            assistant_reply=(
                                f"I matched the capability '{action_type}' but couldn't run it"
                                f"{missing_note}. Details: {tr_error}"),
                            error=tr_res.get("error"),
                            outputs={"unsupported_capability": action_type}
                        )
                else:
                    # Manifest fallback (owner run 2026-09-04, D6 live):
                    # the forced synthesize_tool proposal reached this
                    # dispatcher with no elif branch and no dynamic
                    # registration — routing worked (manifest-first match),
                    # execution couldn't, and the replanner papered over
                    # the gap with a conversational answer while the tool
                    # was never installed. The manifest is the authority
                    # for what EXISTS: an action the ActionGate already
                    # approved deserves the manifest handler, not an
                    # 'unsupported' dead end.
                    manifest_res = None
                    try:
                        from app.tools.manifest import get_tool_manifest
                        entry = get_tool_manifest().get(action_type)
                        if entry and callable(entry.get("handler")):
                            handler = entry["handler"]
                            manifest_res = handler(dict(payload))
                    except Exception as exc:
                        from app.cognition.execution_control import ExecutionCancelled
                        if isinstance(exc, ExecutionCancelled):
                            raise
                        app_logger.warning(
                            f"Manifest handler for '{action_type}' raised: {exc}")
                        manifest_res = {"success": False,
                                        "error": f"manifest handler error: {exc}"}
                    if isinstance(manifest_res, dict) and manifest_res.get("success"):
                        raw_output_data["manifest_res"] = manifest_res
                        executed_actions.append(
                            f"Executed manifest capability '{action_type}'.")
                    elif isinstance(manifest_res, dict):
                        mf_error = manifest_res.get("error") or "unknown error"
                        missing_note = ""
                        if "missing required parameter" in str(mf_error):
                            missing_note = (" — your request didn't include "
                                            "the information this capability needs, "
                                            "and I won't invent it")
                        return ExecutionResult(
                            proposal_id=proposal_id,
                            action_type=action_type,
                            execution_status=ExecutionStatus.FAILED,
                            attempted=True,
                            executed_actions=[],
                            assistant_reply=(
                                f"I matched the capability '{action_type}' but couldn't run it"
                                f"{missing_note}. Details: {mf_error}"),
                            error=manifest_res.get("error"),
                            outputs={"manifest_capability": action_type,
                                     "manifest_result": manifest_res},
                        )
                    else:
                        # CapabilityResolver: Unsupported capability proposal -> Structured Failure
                        app_logger.warning(f"CapabilityResolver: Proposal action_type '{action_type}' is unsupported.")
                        return ExecutionResult(
                            proposal_id=proposal_id,
                            action_type=action_type,
                            execution_status=ExecutionStatus.FAILED,
                            attempted=True,
                            executed_actions=[],
                            assistant_reply=f"Capability execution failed: Action proposal type '{action_type}' is unsupported by capability resolvers.",
                            error=f"Unsupported proposal action_type '{action_type}'",
                            outputs={"unsupported_capability": action_type}
                        )
            except Exception as e:
                from app.cognition.execution_control import ExecutionCancelled

                if isinstance(e, ExecutionCancelled):
                    raise
                app_logger.warning(f"CapabilityResolver lookup exception for '{action_type}': {e}")
                return ExecutionResult(
                    proposal_id=proposal_id,
                    action_type=action_type,
                    execution_status=ExecutionStatus.FAILED,
                    attempted=True,
                    executed_actions=[],
                    assistant_reply=f"Capability execution failed: Action proposal type '{action_type}' is unsupported.",
                    error=str(e),
                    outputs={"unsupported_capability": action_type}
                )

        system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=executed_actions)
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
        from app.llm import output_budget
        llm_res = llm_client.generate_chat_completion(
            messages=messages, complexity=complexity,
            max_tokens=output_budget("action_summary", complexity),
        )
        try:
            assistant_reply = require_real_completion(llm_res)
            HumanNatureEngine.assimilate_human_experience(user_text, assistant_reply)
        except ModelCompletionUnavailable:
            # Preserve real action facts without laundering offline diagnostic
            # text into conversation, social learning, or memory.
            assistant_reply = (
                " ".join(executed_actions)
                if executed_actions else
                "Capability execution finished without a model-generated summary."
            )

        status = ExecutionStatus.SUCCEEDED if execution_success else ExecutionStatus.FAILED
        return ExecutionResult(
            proposal_id=proposal_id,
            action_type=action_type,
            execution_status=status,
            attempted=True,
            executed_actions=executed_actions,
            assistant_reply=assistant_reply,
            execution_facts=execution_facts,
            outputs=raw_output_data,
            model_used=llm_res.get("model", "")
        )

    @classmethod
    def process_user_task(cls, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """
        Adapter route wrapping canonical CognitivePipeline -> CognitiveRuntime.
        Ensures backwards compatibility for legacy callers while routing all processing
        through the single authoritative cognitive cycle.
        """
        app_logger.info(f"MasterAgentOrchestrator adapter delegating '{user_text[:60]}' to CognitivePipeline...")
        from app.cognition.pipeline import CognitivePipeline
        return CognitivePipeline.process_request(user_text, complexity=complexity)
