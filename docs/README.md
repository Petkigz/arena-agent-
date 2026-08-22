# Documentation Index

This directory is the canonical home of Arena's documentation. The repo previously
held ~33 root-level `.md` files with contradictory status claims ("10% AGI", "35%",
"97%", "99%", "100%", "Level 4/5", "Level 5/5", test counts from 304 to 876).
That has been reconciled. Here is the authoritative layout.

## Truth — read these first

| File | What it is |
|---|---|
| `../README.md` | Project overview, architecture, setup, run instructions |
| `../AGI_MEASURED_STATUS.md` | **The single source of truth for status** — measured facts (test counts, module wiring, capability scorecard), not percentages |
| `../AUDIT_REPORT.md` | Latest full-system audit (tests, security, code quality) |
| `FULL_AUDIT_2026-08-22.md` | Full thorough audit — bugs, gaps, security, incomplete (this session) |
| `AGI_HUMAN_AUDIT_2026-08-22.md` | AGI human-intelligence audit — 12 dimensions, module depth, how far we can take it |

## Reference

| Path | Contents |
|---|---|
| `phase3-reasoning.md` | Reasoning engine architecture |
| `phase4-memory-learning.md` | Memory & learning architecture |
| `provenance-hardening-plan.md` | Evidence/provenance design |
| `roadmap-to-intelligence.md` | The original (pre-AGI-relabeling) roadmap |
| `phases/` | Per-module docs for the wired cognition modules (Phases 11–21). **Note:** their closing "X% AGI" lines are historical/inflated — the modules are real and wired, but they are *capabilities*, not steps toward a percentage. |
| `AGENT_REVIEW_FINDINGS.md`, `RECOVERED_BRANCH_REVIEW.md`, `REVIEW_2026-08-22.md` | Working review notes from the agent reconciliation sessions |

## New in this session (P1-1 → P2 AGI push)

- **Perception→Grounding loop:** `app/tools/object_detector.py` (face via Haar, objects via YOLO/SSD fallback) auto-creates `PerceptualGrounding`
- **Causal learning:** `causal_inference.py` learns from execution + surprisal (Bayesian)
- **Memory association:** `consolidate_memory()` creates `co_occurs_with` relationships
- **Curiosity:** `generate_goals_from_information_gain()` + signals for unknown entities, low-confidence groundings, weak causal edges, unexplored files
- **Resource-aware planning:** `counterfactual_simulator.py` RESOURCE_COSTS + hardware pressure penalties
- **Social from real signals:** `prosody_analyzer.py` (pitch/energy/ZCR → emotion) + text emotion
- **Multimodal chat:** `process_cognitive_cycle(image_path, attachments)` through ONE brain
- **Self-evolution verified:** `self_evolving_agent.py` synthesize→pytest→hotload only if green
- **Project management:** `project_manager.py` + `goal_decomposer.py` wired (17 modules) + `/projects` API + web/desktop/Android UI
- **VLM optional:** `vlm_analyzer.py` (Moondream2/Llava) with OCR+LLM fallback — safe, no breakage
- **LoRA continual learning:** `lora_manager.py` — adapters in `data/loras/`, datasets, training jobs, active.json
- **Desktop split:** `desktop/theme.py`, `styles.py`, `widgets/orb.py`, `workers.py` extracted from monolith
- **Bug fixes:** B5 perceptual hash, B6 magic-byte + RIFF disambiguation, B7/B8 useVoice, B9 blob revoke, B10/B11 conversationStore, B12 WS version, B13 QSettings bool, V1/V3/V4 voice, F2 AppearanceSettingsPage theme sync, D2 VisionWorker thread-safety, G7 Android notification

## Archive (historical, superseded)

`archive/` contains the old status/plan/review docs that contradicted each other
(`AGI_STATUS.md`, `AGI_LEVEL_ASSESSMENT.md`, `AGI_FINAL_SUMMARY.md`, `PHASES.md`,
`PROJECT_REVIEW.md`, the `FRONTEND_*` and `*_PLAN` process docs, etc.).

They are kept for git history but are **not authoritative**. Several contain
claims that do not match the code (invented test counts, "human-level AGI"
percentage progress, phase numbers that don't match the files). Treat them as
historical artifacts only.
