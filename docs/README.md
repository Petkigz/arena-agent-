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

## Reference

| Path | Contents |
|---|---|
| `phase3-reasoning.md` | Reasoning engine architecture |
| `phase4-memory-learning.md` | Memory & learning architecture |
| `provenance-hardening-plan.md` | Evidence/provenance design |
| `roadmap-to-intelligence.md` | The original (pre-AGI-relabeling) roadmap |
| `phases/` | Per-module docs for the wired cognition modules (Phases 11–21). **Note:** their closing "X% AGI" lines are historical/inflated — the modules are real and wired, but they are *capabilities*, not steps toward a percentage. |
| `AGENT_REVIEW_FINDINGS.md`, `RECOVERED_BRANCH_REVIEW.md` | Working review notes from the agent reconciliation sessions |

## Archive (historical, superseded)

`archive/` contains the old status/plan/review docs that contradicted each other
(`AGI_STATUS.md`, `AGI_LEVEL_ASSESSMENT.md`, `AGI_FINAL_SUMMARY.md`, `PHASES.md`,
`PROJECT_REVIEW.md`, the `FRONTEND_*` and `*_PLAN` process docs, etc.).

They are kept for git history but are **not authoritative**. Several contain
claims that do not match the code (invented test counts, "human-level AGI"
percentage progress, phase numbers that don't match the files). Treat them as
historical artifacts only.
