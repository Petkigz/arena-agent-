"""Data Analysis Agent — a thin, read-only analysis loop.

Mirrors the CodingAgent's shape but for data: inspect → plan → query → verify →
answer. It is *read-only by construction* (only SELECT/PRAGMA SQL is ever run,
enforced by `SQLQueryTool.is_read_only`), so it can be granted Level 0 autonomy
without touching the owner's data.

Strong-tools-thin-model: the actual analysis is deterministic —

- `DataAnalysisEngine.analyze_dataset` computes the schema, summary statistics,
  missing-value counts, and correlations (pandas/numpy, no LLM).
- `SQLQueryTool.query_csv` / a pandas→sqlite path executes the question's SQL and
  returns exact rows (no LLM).
- The model only (a) writes a short plan, (b) writes ONE read-only SQL query, and
  (c) writes the final prose answer **given the exact rows already computed**.
  Correctness is checked by *running the query*, not by trusting the model.

One-brain principle: the agent shares the ONE `CognitiveRuntime` and the ONE
`llm_client`; it never loads a second model and keeps no memory of its own — it
records outcomes back into the brain so the brain learns from data work too.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.llm import llm_client, extract_reply
from app.tools.data_analyzer import DataAnalysisEngine
from app.tools.sql_query import SQLQueryTool
from app.utils.logger import app_logger, audit_logger


class DataAnalysisAgent:
    """Inspect → plan → query → verify → answer loop for read-only data tasks.

    Thin by design: no second model, no private memory, no mini cognition. It
    reuses the brain's runtime (for hardware-aware complexity + learning) and the
    system's single llm_client.
    """

    def __init__(
        self,
        workdir: Optional[str] = None,
        max_attempts: int = 3,
        llm=None,
        runtime=None,
        limit: int = 100,
    ) -> None:
        self.workdir = Path(workdir) if workdir else Path(settings.BASE_DIR)
        self.max_attempts = max(1, min(int(max_attempts), 5))
        self.limit = max(1, min(int(limit), 1000))
        self._llm = llm or llm_client
        self.runtime = runtime  # optional — the one brain to record into

    # ── main loop ───────────────────────────────────────────────────────────
    def run(self, dataset_path: str, question: str) -> Dict[str, Any]:
        """Answer a question about a dataset using read-only SQL, with retries."""
        if not question or not question.strip():
            return {"success": False, "error": "A question is required."}
        if not dataset_path or not str(dataset_path).strip():
            return {"success": False, "error": "A dataset path is required."}

        start = time.time()
        path = self._resolve(dataset_path)
        inspection = self._inspect(path)
        if not inspection.get("success"):
            return {
                "success": False,
                "error": inspection.get("error", "Could not inspect dataset."),
            }

        attempts: List[Dict[str, Any]] = []

        for attempt in range(1, self.max_attempts + 1):
            app_logger.info(
                f"DataAnalysisAgent attempt {attempt}/{self.max_attempts} for '{question[:60]}'"
            )

            plan = self._plan(question, inspection, attempts)
            query = self._generate_query(question, plan, inspection, attempts)

            if not query:
                attempts.append({"attempt": attempt, "error": "Model produced no query."})
                continue

            result = self._execute_query(path, query)
            attempts.append({"attempt": attempt, "plan": plan, "query": query, "exec": result})

            if result.get("success"):
                answer = self._summarize(question, inspection, query, result.get("rows", []), plan)
                audit_logger.info(
                    f"DataAnalysisAgent answered '{question[:40]}' on attempt {attempt}"
                )
                self._record(question, success=True, latency_ms=(time.time() - start) * 1000, attempts=attempts)
                return {
                    "success": True,
                    "question": question,
                    "dataset": str(path),
                    "query": query,
                    "rows": result.get("rows", []),
                    "count": result.get("count", 0),
                    "answer": answer,
                    "attempts": attempt,
                    "history": attempts,
                }

            app_logger.warning(
                f"Attempt {attempt} query failed: {result.get('error', '')[:200]}"
            )
            continue

        self._record(question, success=False, latency_ms=(time.time() - start) * 1000, attempts=attempts)
        return {
            "success": False,
            "question": question,
            "dataset": str(path),
            "attempts": attempts,
            "message": f"Failed after {self.max_attempts} attempts.",
        }

    # ── brain integration (the "one brain" principle) ───────────────────────
    def _select_complexity(self) -> str:
        """Choose the model route, deferring to the runtime's hardware-aware logic."""
        if self.runtime is not None:
            try:
                return self.runtime._select_effective_complexity("main")
            except Exception:
                pass
        return "main"

    def _record(self, question: str, success: bool, latency_ms: float, attempts: List[Dict[str, Any]]) -> None:
        """Record the data-analysis outcome back into the brain (best-effort)."""
        if self.runtime is None:
            return
        try:
            self.runtime.memory.add(
                "episodic",
                f"data analysis task: {question}",
                source="data_analysis_agent",
                outcome="success" if success else "failed",
                success=success,
                importance=0.7,
            )
        except Exception as e:
            app_logger.warning(f"DataAnalysisAgent memory record failed: {e}")

        try:
            self.runtime.outcomes.record_outcome(
                goal_type="data_analysis",
                action_type="run_data_analysis",
                success=success,
                latency_ms=round(latency_ms, 2),
                surprisal=0.0 if success else 1.0,
                goal_text=question,
            )
        except Exception as e:
            app_logger.warning(f"DataAnalysisAgent outcome record failed: {e}")

        try:
            failed = [
                a.get("exec", {}).get("error", "")[:200]
                for a in attempts if a.get("exec") and not a["exec"].get("success")
            ]
            self.runtime.lessons.extract_lesson(
                task_type="data_analysis",
                action_type="run_data_analysis",
                final_state="achieved" if success else "failed",
                verified_success=success,
                failed_conditions=failed,
                reply_text=f"data analysis agent {'succeeded' if success else 'failed'} after {len(attempts)} attempt(s)",
                goal_text=question,
                latency_ms=round(latency_ms, 2),
                surprisal=0.0 if success else 1.0,
            )
        except Exception as e:
            app_logger.warning(f"DataAnalysisAgent lesson record failed: {e}")

    # ── deterministic helpers (testable, no LLM) ────────────────────────────
    def _resolve(self, dataset_path: str) -> Path:
        p = Path(dataset_path)
        if not p.is_absolute():
            p = self.workdir / p
        return p

    def _inspect(self, path: Path) -> Dict[str, Any]:
        """Deterministic schema + summary statistics via DataAnalysisEngine."""
        try:
            return DataAnalysisEngine.analyze_dataset(str(path))
        except Exception as e:
            app_logger.warning(f"Inspection failed for {path}: {e}")
            return {"success": False, "error": f"Inspection failed: {e}"}

    def _execute_query(self, path: Path, query: str) -> Dict[str, Any]:
        """Deterministic read-only query execution (SQL enforced, never the model)."""
        if not SQLQueryTool.is_read_only(query):
            return {"success": False, "error": "Only read-only SQL (SELECT/PRAGMA) is allowed."}

        ext = path.suffix.lower()
        if ext == ".csv":
            return SQLQueryTool.query_csv(str(path), query, limit=self.limit)

        # Excel → load with pandas, run the query against an in-memory sqlite table.
        try:
            import pandas as pd

            df = pd.read_excel(str(path))
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            df.to_sql("data", conn, index=False)
            cur = conn.execute(query)
            rows = [dict(r) for r in cur.fetchmany(self.limit + 1)]
            truncated = len(rows) > self.limit
            rows = rows[: self.limit]
            conn.close()
            return {"success": True, "rows": rows, "count": len(rows), "truncated": truncated}
        except Exception as e:
            app_logger.warning(f"Excel query failed: {e}")
            return {"success": False, "error": f"Query failed: {e}"}

    def _summarize(self, question: str, inspection: Dict[str, Any], query: str,
                   rows: List[Dict[str, Any]], plan: str) -> str:
        """Ask the model to write the answer *given the exact rows already computed*.

        The model is only ever shown numbers that were actually produced by the
        deterministic query. If it returns nothing (or the server is offline), we
        fall back to a deterministic summary of the rows — never a hallucinated one.
        """
        schema = {
            "columns": inspection.get("columns", []),
            "rows_count": inspection.get("rows_count"),
            "columns_count": inspection.get("columns_count"),
        }
        system = (
            "You are a careful data analyst. Write a concise answer to the question "
            "using ONLY the numbers present in the 'Query results' below. Do not invent "
            "any figures, percentages, or trends that are not literally in the results. "
            "If the results are empty, say so plainly. Output a short prose answer."
        )
        user = (
            f"Question: {question}\n\n"
            f"Plan: {plan}\n\n"
            f"Schema: {schema}\n\n"
            f"SQL run: {query}\n\n"
            f"Query results (exact): {rows[:50]}"
        )
        answer = extract_reply(
            self._llm.generate_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                complexity=self._select_complexity(), max_tokens=600,
            ),
            fallback="",
        )
        if answer.strip():
            return answer.strip()
        # Deterministic fallback: describe the result shape, never fabricate values.
        if not rows:
            return "The query ran successfully but returned no rows."
        return (
            f"The query returned {len(rows)} row(s). First row: {rows[0]}"
            + (f"; last row: {rows[-1]}" if len(rows) > 1 else "")
        )

    # ── LLM steps (injectable, keep the model's reasoning minimal) ──────────
    def _plan(self, question: str, inspection: Dict[str, Any], attempts: List[Dict[str, Any]]) -> str:
        failures = "\n".join(
            a.get("exec", {}).get("error", "")[:400] for a in attempts if a.get("exec") and not a["exec"].get("success")
        )
        schema = {
            "columns": inspection.get("columns", []),
            "rows_count": inspection.get("rows_count"),
        }
        system = (
            "You are a data analyst. Produce a concise plan to answer the question "
            "using read-only SQL against the dataset described. If there were prior "
            "failed queries, address the specific SQL errors listed. Output ONLY the plan."
        )
        user = (
            f"Question: {question}\n\nSchema: {schema}\n\n"
            f"Prior query errors:\n{failures or '(none)'}"
        )
        return extract_reply(self._llm.generate_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            complexity=self._select_complexity(), max_tokens=400,
        ), fallback="Query the dataset and answer the question.")

    def _generate_query(self, question: str, plan: str, inspection: Dict[str, Any],
                        attempts: List[Dict[str, Any]]) -> str:
        failures = "\n".join(
            a.get("exec", {}).get("error", "")[:400] for a in attempts if a.get("exec") and not a["exec"].get("success")
        )
        schema = {
            "columns": inspection.get("columns", []),
            "rows_count": inspection.get("rows_count"),
        }
        system = (
            "You write ONE read-only SQLite SELECT query to answer a data question. "
            "Output ONLY the SQL (no explanation, no markdown fences). The data is in a "
            "table named 'data'. Never write INSERT/UPDATE/DELETE/DDL. If a prior query "
            "failed, fix the specific error. Columns may need double-quoting."
        )
        user = (
            f"Question: {question}\n\nPlan: {plan}\n\nSchema: {schema}\n\n"
            f"Prior query errors:\n{failures or '(none)'}\n\nSQL:"
        )
        query = extract_reply(self._llm.generate_chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            complexity=self._select_complexity(), max_tokens=400,
        ), fallback="")
        return self._strip_fences(query)

    @staticmethod
    def _strip_fences(query: str) -> str:
        q = query.strip()
        for fence in ("```sql", "```"):
            if q.startswith(fence):
                q = q[len(fence):].lstrip("\n")
        if q.endswith("```"):
            q = q[:-3].rstrip()
        return q.strip()
