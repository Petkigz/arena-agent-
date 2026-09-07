"""ResponseReviewBar — native "Review response" controls (PySide6).

The desktop counterpart of the web slice (frontend/src/components/chat/
ResponseFeedback.tsx) against the SAME endpoints and stores:

- Usefulness feedback (helpful / partially helpful / not helpful + note)
  feeds the existing bounded strategy-learning path.
- Task evaluations are MEASUREMENT ONLY and say so in the UI: recording one
  changes no runtime truth, authorizes no work, and approves no training.
- The bar is mounted ONLY on replies carrying their exact trace id — older
  unlinked replies are intentionally unreviewable, never guessable.
- submission_id retry identity: the same id is reused until the backend
  returns its matching receipt, so retries never inflate evidence counts.
- "Why this response?" reuses the grounded introspection endpoint; it never
  asks a model to explain itself.

Widget tests run offscreen and skip automatically where PySide6 is not
installed (the GUI-free logic lives in desktop/response_review.py).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.response_review import (
    EVALUATION_CONDITIONS,
    EVALUATION_SPLITS,
    TASK_OUTCOMES,
    USEFULNESS_LEVELS,
    ResponseReviewError,
    build_task_evaluation_payload,
    build_usefulness_payload,
    new_submission_id,
    parse_evidence_ids,
)
from desktop.styles import _button_style
from desktop.theme import BG_SECONDARY, BORDER_SUBTLE, TEXT_MUTED, TEXT_SECONDARY, TEXT_PRIMARY, ACCENT

_USEFULNESS_LABELS = {
    "helpful": "Helpful",
    "partially_helpful": "Partially helpful",
    "not_helpful": "Not helpful",
}
_OUTCOME_LABELS = {
    "success": "Observed: success",
    "failure": "Observed: failure",
    "unknown": "Observed: unknown",
}


class ResponseReviewWorker(QThread):
    """One HTTP call off the GUI thread; emits a typed result or failure."""

    succeeded = Signal(str, object)  # kind, response payload
    failed = Signal(str, str)        # kind, error text

    def __init__(self, kind: str, fn, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._fn = fn

    def run(self) -> None:
        try:
            self.succeeded.emit(self._kind, self._fn())
        except Exception as exc:  # noqa: BLE001 — surfaced to the owner, never swallowed
            self.failed.emit(self._kind, str(exc))


class ResponseReviewBar(QWidget):
    """Review controls bound to one exact trace. Create it only when the
    reply carries a trace id (see desktop.response_review.reviewable_trace)."""

    def __init__(self, client, trace_id: str, message_id: str = "", parent=None):
        super().__init__(parent)
        self._client = client
        self._trace_id = (trace_id or "").strip()
        self._message_id = (message_id or "").strip()
        # Retry identity lives until its receipt comes back (then a fresh
        # submission gets a fresh id). One per kind.
        self._usefulness_submission_id = new_submission_id()
        self._evaluation_submission_id = new_submission_id()
        self._workers: list = []

        frame_layout = QVBoxLayout(self)
        frame_layout.setContentsMargins(44, 0, 0, 4)
        frame_layout.setSpacing(6)

        self._frame = QFrame()
        self._frame.setStyleSheet(
            f"QFrame {{ background: {BG_SECONDARY}; border: 1px solid {BORDER_SUBTLE};"
            f" border-radius: 8px; }}"
        )
        frame_layout.addWidget(self._frame)

        box = QVBoxLayout(self._frame)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        # ── collapsed header row ────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)
        self._toggle = QPushButton("Review response")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(_button_style(BG_SECONDARY, TEXT_PRIMARY) +
                                   f" QPushButton {{ border: 1px solid {BORDER_SUBTLE}; }}")
        self._toggle.clicked.connect(self._toggle_expanded)
        header.addWidget(self._toggle)
        self._why_button = QPushButton("Why this response?")
        self._why_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._why_button.setStyleSheet(_button_style(BG_SECONDARY, TEXT_SECONDARY))
        self._why_button.clicked.connect(self._show_explanation)
        header.addWidget(self._why_button)
        self._header_status = QLabel("")
        self._header_status.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none;")
        header.addWidget(self._header_status, stretch=1)
        box.addLayout(header)

        # ── usefulness section ──────────────────────────────────────────────
        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 2, 0, 2)
        body_layout.setSpacing(6)
        rating_row = QHBoxLayout()
        rating_row.setSpacing(6)
        self._usefulness_buttons: Dict[str, QPushButton] = {}
        for level in USEFULNESS_LEVELS:
            btn = QPushButton(_USEFULNESS_LABELS[level])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_button_style(BG_SECONDARY, TEXT_PRIMARY))
            btn.clicked.connect(lambda _=False, lv=level: self._submit_usefulness(lv))
            self._usefulness_buttons[level] = btn
            rating_row.addWidget(btn)
        rating_row.addStretch(1)
        body_layout.addLayout(rating_row)
        self._feedback_note = QLineEdit()
        self._feedback_note.setPlaceholderText("Note (optional) — what worked or what missed")
        self._feedback_note.setStyleSheet(
            f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
            f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 6px 10px;")
        body_layout.addWidget(self._feedback_note)
        self._feedback_status = QLabel("")
        self._feedback_status.setWordWrap(True)
        self._feedback_status.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none;")
        body_layout.addWidget(self._feedback_status)
        box.addWidget(self._body)

        # ── task evaluation (measurement only) ──────────────────────────────
        self._eval_toggle = QPushButton("Record a task evaluation ▸")
        self._eval_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eval_toggle.setStyleSheet(_button_style(BG_SECONDARY, TEXT_SECONDARY))
        self._eval_toggle.clicked.connect(self._toggle_evaluation)
        box.addWidget(self._eval_toggle)

        self._eval_panel = QWidget()
        eval_layout = QVBoxLayout(self._eval_panel)
        eval_layout.setContentsMargins(0, 2, 0, 2)
        eval_layout.setSpacing(6)
        self._eval_hint = QLabel(
            "Measurement only — recorded against this exact trace. It does not "
            "change runtime truth, authorize work, or approve training.")
        self._eval_hint.setWordWrap(True)
        self._eval_hint.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none;")
        eval_layout.addWidget(self._eval_hint)
        grid = QHBoxLayout()
        grid.setSpacing(6)
        self._task_key = QLineEdit()
        self._task_key.setPlaceholderText("Task key (required, e.g. budget-report-q3)")
        self._task_key.setStyleSheet(self._field_style())
        grid.addWidget(self._task_key, stretch=2)
        self._split = QComboBox()
        self._split.addItems(EVALUATION_SPLITS)
        self._condition = QComboBox()
        self._condition.addItems(EVALUATION_CONDITIONS)
        for combo in (self._split, self._condition):
            combo.setStyleSheet(self._field_style())
            grid.addWidget(combo, stretch=1)
        eval_layout.addLayout(grid)
        grid2 = QHBoxLayout()
        grid2.setSpacing(6)
        self._outcome = QComboBox()
        for value in TASK_OUTCOMES:
            self._outcome.addItem(_OUTCOME_LABELS[value], value)
        self._eval_usefulness = QComboBox()
        self._eval_usefulness.addItem("Usefulness: unknown", "unknown")
        for level in USEFULNESS_LEVELS:
            self._eval_usefulness.addItem(_USEFULNESS_LABELS[level], level)
        for combo in (self._outcome, self._eval_usefulness):
            combo.setStyleSheet(self._field_style())
            grid2.addWidget(combo, stretch=1)
        self._correction = QCheckBox("A correction was received")
        self._correction.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; border: none;")
        grid2.addWidget(self._correction, stretch=1)
        eval_layout.addLayout(grid2)
        self._evidence = QLineEdit()
        self._evidence.setPlaceholderText("Evidence ids (comma-separated, optional)")
        self._evidence.setStyleSheet(self._field_style())
        eval_layout.addWidget(self._evidence)
        self._eval_note = QLineEdit()
        self._eval_note.setPlaceholderText("Note (optional)")
        self._eval_note.setStyleSheet(self._field_style())
        eval_layout.addWidget(self._eval_note)
        eval_row = QHBoxLayout()
        self._eval_save = QPushButton("Save evaluation")
        self._eval_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eval_save.setStyleSheet(_button_style(ACCENT, "#FFFFFF"))
        self._eval_save.clicked.connect(self._submit_evaluation)
        eval_row.addWidget(self._eval_save)
        self._eval_status = QLabel("")
        self._eval_status.setWordWrap(True)
        self._eval_status.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none;")
        eval_row.addWidget(self._eval_status, stretch=1)
        eval_layout.addLayout(eval_row)
        box.addWidget(self._eval_panel)

        self._body.setVisible(False)
        self._eval_panel.setVisible(False)
        self._explanation_worker: Optional[ResponseReviewWorker] = None

    # ── styling helper ──────────────────────────────────────────────────────
    def _field_style(self) -> str:
        return (f"background: {BG_SECONDARY}; color: {TEXT_PRIMARY};"
                f" border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 4px 8px;")

    # ── expansion / loading ─────────────────────────────────────────────────
    def _toggle_expanded(self) -> None:
        showing = not self._body.isVisible()
        self._body.setVisible(showing)
        if not showing:
            self._eval_panel.setVisible(False)
            return
        if not self._feedback_status.text():
            self._load_existing()

    def _toggle_evaluation(self) -> None:
        showing = not self._eval_panel.isVisible()
        self._eval_panel.setVisible(showing)
        self._eval_toggle.setText("Record a task evaluation ▾" if showing
                                  else "Record a task evaluation ▸")

    def _load_existing(self) -> None:
        """Show what is already recorded for this trace — absence stays explicit."""
        client = self._client
        trace = self._trace_id

        def work() -> Dict[str, Any]:
            feedback = client.trace_usefulness(trace).get("feedback") or []
            evaluations: list = []
            for split in EVALUATION_SPLITS:
                evaluations.extend(
                    client.trace_task_evaluations(trace, split=split).get("evaluations") or [])
            return {"feedback": feedback, "evaluations": evaluations}

        self._start_worker("load", work)

    # ── submissions ─────────────────────────────────────────────────────────
    def _submit_usefulness(self, level: str) -> None:
        try:
            payload = build_usefulness_payload(
                level,
                note=self._feedback_note.text(),
                submission_id=self._usefulness_submission_id,
            )
        except ResponseReviewError as exc:
            self._feedback_status.setText(str(exc))
            return
        client = self._client
        trace = self._trace_id
        self._set_feedback_saving(True)
        self._start_worker(
            "usefulness",
            lambda: client.record_trace_usefulness(trace, submission_id=payload["submission_id"],
                                                   usefulness=payload["usefulness"],
                                                   note=payload["note"]),
        )

    def _submit_evaluation(self) -> None:
        try:
            payload = build_task_evaluation_payload(
                trace_id=self._trace_id,
                task_key=self._task_key.text(),
                observed_outcome=self._outcome.currentData(),
                usefulness=self._eval_usefulness.currentData() or "unknown",
                split=self._split.currentText(),
                condition=self._condition.currentText(),
                correction_received=self._correction.isChecked(),
                evidence_ids=parse_evidence_ids(self._evidence.text()),
                note=self._eval_note.text(),
                submission_id=self._evaluation_submission_id,
            )
        except ResponseReviewError as exc:
            self._eval_status.setText(str(exc))
            return
        client = self._client
        self._set_eval_saving(True)
        self._start_worker(
            "evaluation",
            lambda: client.record_trace_task_evaluation(payload),
        )

    # ── worker plumbing ─────────────────────────────────────────────────────
    def _start_worker(self, kind: str, fn) -> None:
        worker = ResponseReviewWorker(kind, fn, parent=self)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        self._workers.append(worker)  # keep alive until the call finishes
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        worker.start()

    def _on_success(self, kind: str, result: Any) -> None:
        if kind == "load":
            feedback = result.get("feedback") or []
            evaluations = result.get("evaluations") or []
            if feedback or evaluations:
                self._header_status.setText(
                    f"Already recorded: {len(feedback)} feedback · {len(evaluations)} evaluation(s)")
            else:
                self._header_status.setText("")
            return
        if kind == "usefulness":
            receipt = ""
            if isinstance(result, dict):
                receipt = str((result.get("feedback") or {}).get("feedback_id") or "")
            self._feedback_status.setText(
                f"Saved ✓ (receipt {receipt})" if receipt else "Saved ✓")
            # The submission is now durable — a NEW review gets a NEW identity.
            self._usefulness_submission_id = new_submission_id()
            self._set_feedback_saving(False)
            return
        if kind == "evaluation":
            receipt = ""
            if isinstance(result, dict):
                receipt = str((result.get("evaluation") or {}).get("evaluation_id") or "")
            self._eval_status.setText(
                f"Evaluation saved ✓ (receipt {receipt})" if receipt else "Evaluation saved ✓")
            self._evaluation_submission_id = new_submission_id()
            self._set_eval_saving(False)

    def _on_failure(self, kind: str, error: str) -> None:
        if kind == "load":
            self._header_status.setText(f"Could not load history: {error}")
            return
        # Keep the SAME submission id so a retry is idempotent server-side.
        if kind == "usefulness":
            self._feedback_status.setText(f"Not saved — retry the same rating. ({error})")
            self._set_feedback_saving(False)
        elif kind == "evaluation":
            self._eval_status.setText(f"Not saved — retry the same submission. ({error})")
            self._set_eval_saving(False)

    def _set_feedback_saving(self, saving: bool) -> None:
        for btn in self._usefulness_buttons.values():
            btn.setEnabled(not saving)
        self._feedback_status.setText("Saving…" if saving else self._feedback_status.text())

    def _set_eval_saving(self, saving: bool) -> None:
        self._eval_save.setEnabled(not saving)

    # ── grounded explanation ────────────────────────────────────────────────
    def _show_explanation(self) -> None:
        if self._explanation_worker is not None and self._explanation_worker.isRunning():
            return
        self._header_status.setText("Loading trace explanation…")
        client = self._client
        trace = self._trace_id
        self._explanation_worker = ResponseReviewWorker(
            "explanation", lambda: client.response_explanation(trace), parent=self)
        self._explanation_worker.succeeded.connect(self._on_explanation)
        self._explanation_worker.failed.connect(
            lambda _k, err: self._header_status.setText(f"Explanation unavailable: {err}"))
        self._explanation_worker.start()

    def _on_explanation(self, _kind: str, result: Any) -> None:
        facts = (result or {}).get("facts") or {}
        lines = (result or {}).get("explanation") or []
        verified = bool(facts.get("goal_verified"))
        summary = "; ".join(str(line) for line in lines[:4]) if lines else "No trace facts recorded."
        label = "goal verified" if verified else "goal not verified"
        self._header_status.setText(f"{label} — {summary}")
        self._header_status.setToolTip("\n".join(str(line) for line in lines))

    # ── theme ───────────────────────────────────────────────────────────────
    def refresh_theme(self) -> None:
        self._frame.setStyleSheet(
            f"QFrame {{ background: {BG_SECONDARY}; border: 1px solid {BORDER_SUBTLE};"
            f" border-radius: 8px; }}"
        )
