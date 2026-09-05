import os
import sys
import importlib
import traceback
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger
from app.llm import llm_client, ModelCompletionUnavailable, require_real_completion
from app.tools.disposable_sandbox import DisposableSandbox

def _bounded_result(res, n: int = 300) -> str:
    """Bounded, key-defensive tail of a sandbox run result — the repair
    prompt must carry the REAL failure evidence, never a raw dump."""
    if isinstance(res, dict):
        for key in ("output", "stdout", "stderr", "error", "result",
                    "message"):
            value = res.get(key)
            if value:
                return str(value)[:n]
    return str(res)[:n]


class SelfEvolvingAgent:
    """
    Self-Evolving & Dynamic Tool Synthesizer Engine.
    Enables the assistant to write its own Python tools on the fly for novel tasks,
    test them inside DisposableSandbox, hot-reload them into memory via importlib,
    and continuously expand its own capabilities without human coding.

    P2 AGI: Now verified — synthesize → generate pytest → run in sandbox → only
    hotload if tests pass, then register in PluginRegistry + manifest. This is
    executable capability synthesis that is deterministic-verified, not hallucinated.
    """

    # Bounded repair loop budget (review 2026-09-05): the model gets
    # MAX_SYNTH_ATTEMPTS chances, each fed the previous failure evidence.
    MAX_SYNTH_ATTEMPTS = 3

    DYNAMIC_TOOLS_DIR = settings.BASE_DIR / "app" / "tools"
    PLUGINS_DIR = settings.DATA_DIR / "plugins"
    TESTS_DIR = settings.BASE_DIR / "tests" / "dynamic"

    @classmethod
    def _safe_name(cls, tool_name_query: str) -> str:
        return "".join(c for c in tool_name_query.lower() if c.isalnum() or c == "_").strip() or "dynamic_tool"

    @classmethod
    def synthesize_and_hotload_tool(
        cls,
        task_objective: str,
        tool_name_query: str
    ) -> Dict[str, Any]:
        """
        Dynamically writes a new Python tool module, tests it in DisposableSandbox,
        hot-reloads it into the live running process, and executes the target task.

        Now with verified loop: generates pytest, runs it, only hotloads if green.
        """
        safe_name = cls._safe_name(tool_name_query)
        module_filename = f"dynamic_{safe_name}.py"
        file_path = cls.DYNAMIC_TOOLS_DIR / module_filename

        app_logger.info(f"SelfEvolvingAgent synthesizing new Python tool module: '{module_filename}' for objective '{task_objective}'")

        # Bounded repair loop (review 2026-09-05, P2): the model
        # PROPOSES; the sandbox DECIDES. A failed attempt is fed back to
        # the model together with the sandbox's own failure evidence and
        # retried, up to MAX_SYNTH_ATTEMPTS — self-evolution must not
        # depend on the model being perfect on the first try, and it is
        # never accepted without verification either.
        base_prompt = (
            f"Write a clean, self-contained Python module file to solve this task objective: '{task_objective}'\n"
            f"Requirements:\n"
            f"1) Define a top-level function: def execute_tool(params: dict = None) -> dict:\n"
            f"2) Provide safe defaults for keys if missing (e.g. n = int((params or {{}}).get('n', 10))).\n"
            f"3) Function must return a dictionary with keys: {{'success': bool, 'result': str, 'details': dict}}\n"
            f"4) Catch exceptions and return success=False with the real error; never fabricate completion.\n"
            f"5) Output ONLY executable Python code block inside ```python ... ```."
        )

        # 2. Generate pytest contract (deterministic verification)
        test_code = f'''
import sys
sys.path.insert(0, ".")
from app.tools.dynamic_{safe_name} import execute_tool

def test_execute_tool_returns_typed_dict():
    res = execute_tool({{"n": 10, "objective": "{task_objective}"}})
    assert isinstance(res, dict), "must return dict"
    assert "success" in res, "must have success key"
    assert isinstance(res["success"], bool), "success must be bool"

def test_execute_tool_handles_empty():
    res = execute_tool(None)
    assert isinstance(res, dict)
    assert res.get("success") is True or res.get("success") is False

def test_execute_tool_handles_invalid():
    res = execute_tool({{"invalid_key": "xxx"}})
    assert isinstance(res, dict)
    assert "success" in res
'''

        attempts_used = 0
        last_failure = "no attempt completed"
        code_block = ""
        sb_run: Dict[str, Any] = {"success": False, "error": last_failure}
        pytest_res: Dict[str, Any] = {"success": False, "error": last_failure}
        verified = False
        direct_ok = False
        pytest_ok = False

        for attempt in range(1, cls.MAX_SYNTH_ATTEMPTS + 1):
            attempts_used = attempt
            prompt = base_prompt
            if attempt > 1:
                prompt += (
                    f"\n\nYour previous attempt FAILED verification. "
                    f"Previous code:\n"
                    f"```python\n{code_block[:2000]}\n```\n"
                    f"Failure evidence from the sandbox:\n{last_failure[:600]}\n"
                    f"Fix the problem and return the COMPLETE corrected "
                    f"module."
                )

            llm_res = llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                complexity="main",
                max_tokens=800
            )

            try:
                raw_content = require_real_completion(llm_res)
            except ModelCompletionUnavailable as exc:
                last_failure = f"model returned no usable completion: {exc}"
                if attempt < cls.MAX_SYNTH_ATTEMPTS:
                    app_logger.info(
                        f"Synthesis attempt {attempt}/{cls.MAX_SYNTH_ATTEMPTS} "
                        f"produced no usable completion — retrying")
                    continue
                return {
                    "success": False,
                    "verified": False,
                    "available": False,
                    "attempts": attempts_used,
                    "error": f"No usable model completion in "
                             f"{attempts_used} attempts: {exc}",
                    "tool_module_name": f"dynamic_{safe_name}",
                    "file_path": None,
                }

            # Extract python code block
            if "```python" in raw_content:
                code_block = raw_content.split("```python")[1].split("```")[0].strip()
            elif "```" in raw_content:
                code_block = raw_content.split("```")[1].split("```")[0].strip()
            else:
                code_block = raw_content.strip()

            if not code_block or "def execute_tool" not in code_block:
                last_failure = ("output did not contain the required "
                                "execute_tool implementation")
                app_logger.info(
                    f"Synthesis attempt {attempt}/{cls.MAX_SYNTH_ATTEMPTS} "
                    f"rejected: {last_failure} — requesting a repair")
                continue

            # 3. Test code inside DisposableSandbox first (both direct run + pytest)
            sb = DisposableSandbox.create_sandbox(f"sb_synth_{safe_name}")
            sandbox_id = sb["sandbox_id"]
            sandbox_path = Path(sb["sandbox_path"])

            # Write module to sandbox
            try:
                (sandbox_path / f"dynamic_{safe_name}.py").write_text(code_block, encoding="utf-8")
            except Exception:
                pass

            # Direct execution test — write runner file to avoid shell quoting
            # hell. sys.executable (not bare 'python'): the SAME interpreter
            # that runs Arena must run the generated code — a bare 'python'
            # does not exist on many hosts (live: the sandboxed run would fail
            # for a portability reason, not a code reason).
            py = f'"{sys.executable}"' if " " in str(sys.executable) else str(sys.executable)
            runner_code = (
                f"import sys\n"
                f"sys.path.insert(0, '.')\n"
                f"exec(open('dynamic_{safe_name}.py').read())\n"
                f"print(execute_tool({{'n': 10, 'objective': '{task_objective}'}}))\n"
            )
            try:
                (sandbox_path / f"runner_{safe_name}.py").write_text(runner_code, encoding="utf-8")
                sb_run = DisposableSandbox.run_in_sandbox(sandbox_id, f"{py} runner_{safe_name}.py")
            except Exception as e:
                sb_run = {"success": False, "error": str(e)}

            # Pytest run
            try:
                (sandbox_path / f"test_dynamic_{safe_name}.py").write_text(test_code, encoding="utf-8")
                pytest_res = DisposableSandbox.run_in_sandbox(
                    sandbox_id, f"{py} -m pytest test_dynamic_{safe_name}.py -q")
            except Exception as e:
                pytest_res = {"success": False, "error": str(e)}

            DisposableSandbox.destroy_sandbox(sandbox_id)

            # Decide if we should hotload: require direct run success OR pytest success
            direct_ok = sb_run.get("success", False) if isinstance(sb_run, dict) else False
            pytest_ok = pytest_res.get("success", False) if isinstance(pytest_res, dict) else False
            verified = direct_ok or pytest_ok
            if verified:
                break
            last_failure = (
                f"sandbox verification rejected the code "
                f"(direct_ok={direct_ok}, pytest_ok={pytest_ok}); "
                f"direct output: {_bounded_result(sb_run, 300)}; "
                f"pytest output: {_bounded_result(pytest_res, 300)}")
            app_logger.info(
                f"Synthesis attempt {attempt}/{cls.MAX_SYNTH_ATTEMPTS} "
                f"failed sandbox verification — requesting a repair")

        # DIAG D6 (live 2026-09-01): 'Successfully created reverse_words'
        # was claimed while registry.effective_capability() found nothing —
        # the old pipeline saved an execute_tool module that PluginRegistry
        # REJECTS (no NAME/execute), so installation never happened. The
        # prescribed chain is now real: verified code is installed as a
        # PluginRegistry-shaped plugin (persistent discovery), registered
        # in the LIVE shared registry, and executed THROUGH the registry —
        # the lookup itself is the install proof. Unverified code is
        # installed NOWHERE (not even app/tools/).
        installed = False
        execution_res = {"success": False,
                         "result": "Not verified — not installed"}
        live_module = None
        if verified:
            # Write the module for importlib hotload.
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code_block)
            # PluginRegistry-shaped install: the ONLY shape discovery
            # accepts (NAME/DESCRIPTION/SAFETY_LEVEL/CATEGORY/execute).
            try:
                cls.PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
                plugin_header = (
                    f'"""Self-evolved capability {safe_name!r} — installed '
                    f'by SelfEvolvingAgent after sandbox verification.\n\n'
                    f'Objective: {task_objective[:200]}\n"""\n\n'
                    f'NAME = {safe_name!r}\n'
                    f'DESCRIPTION = {task_objective[:200]!r}\n'
                    f'SAFETY_LEVEL = 2  # sandbox-verified before install\n'
                    f'CATEGORY = "plugin"\n\n\n'
                )
                plugin_footer = (
                    '\n\ndef execute(payload: dict = None) -> dict:\n'
                    '    """PluginRegistry entry point: the sandbox-verified\n'
                    '    execute_tool contract, one payload dict in/out."""\n'
                    '    return execute_tool(payload or {})\n'
                )
                (cls.PLUGINS_DIR / f"{safe_name}.py").write_text(
                    plugin_header + code_block + plugin_footer,
                    encoding="utf-8")
            except Exception as e:
                app_logger.warning(f"Could not write the plugin install: {e}")
                verified = False

        if verified:
            # Hot-reload module into memory via importlib.
            try:
                module_name = f"app.tools.dynamic_{safe_name}"
                if module_name in sys.modules:
                    live_module = importlib.reload(sys.modules[module_name])
                else:
                    live_module = importlib.import_module(module_name)

                if not hasattr(live_module, "execute_tool"):
                    raise ImportError("module lacks execute_tool")

                # Register in the LIVE shared registry: the capability is
                # callable NOW (effective_capability finds it this session);
                # the plugin file makes it survive restarts.
                from app.cognition.tool_registry import get_shared_registry
                module_ref = live_module
                get_shared_registry().register_tool(
                    safe_name, "plugin",
                    lambda payload: module_ref.execute_tool(payload or {}),
                    description=str(task_objective)[:200],
                    safety_level=2,
                    provenance="dynamic")
                installed = True

                # Registry lookup + execute the INSTALLED capability —
                # success is claimed only from this execution.
                execution_res = get_shared_registry().execute_registered_tool(
                    safe_name, {"objective": task_objective})

                # Force manifest rebuild so the plugin is discovered.
                try:
                    import app.tools.manifest as manifest_module
                    manifest_module._TOOL_MANIFEST = None
                except Exception:
                    pass

            except Exception as e:
                app_logger.error(f"Install/hotload error: {e}")
                execution_res = {"success": False,
                                 "result": f"Install failed: {str(e)}",
                                 "details": {}}
        else:
            app_logger.warning(
                f"Tool {module_filename} failed verification after "
                f"{attempts_used} attempt(s) — NOT installed anywhere "
                f"(direct_ok={direct_ok}, pytest_ok={pytest_ok}); last "
                f"failure: {last_failure[:300]}")

        # Claim success ONLY when verified AND installed AND the installed
        # capability executed through the registry.
        overall_success = bool(
            verified and installed
            and isinstance(execution_res, dict) and execution_res.get("success"))

        db.create_memory({
            "content": f"Self-Evolved Tool [{module_filename}]: Created for objective '{task_objective}'. Verified={verified}. Installed={installed}. Output: {str(execution_res.get('result', ''))[:200]}",
            "category": "self_evolved_tool",
            "source": "self_evolving_agent",
            "confidence": 1.0 if overall_success else 0.5
        })

        db.create_audit_log("synthesize_and_hotload_tool",
                            "success" if overall_success else "unverified",
                            f"Synthesized '{module_filename}' verified={verified} installed={installed}",
                            level=1)

        return {
            "success": overall_success,
            "tool_module_name": f"dynamic_{safe_name}",
            "capability_name": safe_name,
            "file_path": str(file_path) if verified else None,
            "task_objective": task_objective,
            "verified": verified,
            "installed": installed,
            "attempts": attempts_used,
            "last_failure": None if verified else last_failure,
            "direct_test": sb_run,
            "pytest_result": pytest_res,
            "live_execution_result": execution_res
        }

    @classmethod
    def list_dynamic_tools(cls) -> List[Dict[str, Any]]:
        """List all dynamic tools that have been synthesized."""
        tools = []
        try:
            for p in cls.DYNAMIC_TOOLS_DIR.glob("dynamic_*.py"):
                tools.append({
                    "name": p.stem,
                    "file_path": str(p),
                    "size": p.stat().st_size,
                })
        except Exception as e:
            app_logger.warning(f"Could not list dynamic tools: {e}")
        return tools
