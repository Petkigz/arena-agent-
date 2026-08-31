"""Diagnostic hypothesis ranking (P2 review).

The concept bridge intentionally expands a symptom into the WHOLE
diagnostic vocabulary — that breadth is right for DISCOVERY (the planner
must be able to see every plannable probe), but it also creates a wide
candidate surface: 'my computer is slow' puts system_metrics,
list_processes, startup_programs, temperature_status, network_activity
and recent_logs in direct competition. If the next layer simply takes
the highest lexical score, the bridge has silently turned
'symptom -> tool discovery' into 'symptom -> the entire diagnostic tree',
and the winner is whichever tool description happens to share the most
tokens with the injected vocabulary.

This module is the missing layer: a deterministic hypothesis model that
ranks diagnostic probes by how much they DISCRIMINATE between the
hypotheses the fired symptom clusters actually make plausible:

  * A VAGUE symptom (plain slowness) makes many hypotheses plausible with
    no way to tell them apart -> the broad measurement that bears on the
    most hypotheses (system_metrics: CPU + memory + disk) goes FIRST.
  * A SPECIFIC symptom ('startup is taking forever') concentrates its
    cluster's weight on one hypothesis -> the specific probe
    (startup_programs) goes first, ahead of the generic broad sweep.

Weights are cluster-normalized: each fired cluster contributes a total of
1.0 spread across its active hypotheses, so a four-hypothesis cluster
gives each hypothesis 0.25 while a one-hypothesis cluster gives 1.0. A
hypothesis supported by TWO fired clusters (thermal throttling when the
owner reports heat AND crashes) accumulates weight from both —
co-occurring symptoms strengthen shared explanations.

Fully local and deterministic: no LLM, no probes executed — this only
ORDERS the candidates discovery already produced. Which probe actually
runs is still the planner's decision, behind the safety ceiling.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class DiagnosticHypothesis:
    """One explanation a symptom cluster makes plausible, and the manifest
    probes whose EVIDENCE would confirm or refute it."""
    hypothesis_id: str
    description: str
    clusters: Tuple[str, ...]      # concept-bridge cluster ids that imply it
    probes: Tuple[str, ...]        # manifest tool names bearing on it


@dataclass(frozen=True)
class ProbeRanking:
    tool: str
    score: float                   # summed weight of the hypotheses it discriminates
    hypotheses: Tuple[str, ...]    # the hypothesis ids it discriminates
    strongest: float = 0.0         # weight of the strongest hypothesis it tests


_HYPOTHESES: Tuple[DiagnosticHypothesis, ...] = (
    # performance_slowness — many hypotheses, no way to tell apart:
    # the broad measurement discriminates the most.
    DiagnosticHypothesis(
        "cpu_saturation", "CPU saturated by one or a few processes",
        ("performance_slowness",), ("list_processes", "system_metrics")),
    DiagnosticHypothesis(
        "memory_pressure", "RAM exhausted / swapping",
        ("performance_slowness",), ("system_metrics", "list_processes")),
    DiagnosticHypothesis(
        "disk_io_pressure", "Disk full or IO-thrashing",
        ("performance_slowness", "storage_pressure"), ("system_metrics",)),
    DiagnosticHypothesis(
        "background_bloat", "Too many background programs running",
        ("performance_slowness",), ("list_processes", "startup_programs")),
    # overheating_thermal
    DiagnosticHypothesis(
        "sustained_load", "Sustained high load producing the heat",
        ("overheating_thermal",), ("system_metrics", "list_processes")),
    DiagnosticHypothesis(
        "thermal_throttling", "Cooling failure / thermal throttling",
        ("overheating_thermal", "crash_instability"), ("temperature_status",)),
    # crash_instability
    DiagnosticHypothesis(
        "crash_records", "Applications or the system logged crash records",
        ("crash_instability",), ("recent_logs",)),
    DiagnosticHypothesis(
        "resource_exhaustion", "Crashes are resource-driven (e.g. OOM)",
        ("crash_instability",), ("system_metrics", "list_processes")),
    # connectivity_problems
    DiagnosticHypothesis(
        "connectivity_failure", "DNS / routing / interface failure",
        ("connectivity_problems",), ("network_activity",)),
    # storage_pressure — one concentrated hypothesis
    DiagnosticHypothesis(
        "storage_full", "Partitions are full",
        ("storage_pressure",), ("system_metrics",)),
    # slow_boot_startup — one concentrated hypothesis: the specific probe
    DiagnosticHypothesis(
        "startup_bloat", "Startup inventory is bloated",
        ("slow_boot_startup",), ("startup_programs",)),
    # security_suspicion
    DiagnosticHypothesis(
        "suspicious_process", "A miner or implant burning resources",
        ("security_suspicion",), ("list_processes", "startup_programs")),
)


def active_hypotheses(cluster_ids: Iterable[str]) -> List[DiagnosticHypothesis]:
    """The hypotheses implied by the fired concept-bridge clusters."""
    fired = {str(c) for c in cluster_ids}
    return [h for h in _HYPOTHESES if fired & set(h.clusters)]


def rank_probes_by_discrimination(
    cluster_ids: Sequence[str],
) -> List[ProbeRanking]:
    """Order diagnostic probes by discrimination power over the ACTIVE
    hypotheses. Returns [] when the fired clusters imply no hypotheses
    with probes (the caller then leaves discovery's order untouched).
    """
    fired = {str(c) for c in cluster_ids}
    active = active_hypotheses(fired)
    if not active:
        return []

    # Cluster-normalized weights: each fired cluster contributes 1.0 in
    # total, spread across its active hypotheses. Specific clusters
    # (one hypothesis) concentrate weight; vague clusters diffuse it.
    per_cluster: Dict[str, int] = defaultdict(int)
    for h in active:
        for c in fired & set(h.clusters):
            per_cluster[c] += 1

    def weight(h: DiagnosticHypothesis) -> float:
        # A hypothesis implied by TWO fired clusters accumulates weight
        # from both: co-occurring symptoms strengthen shared explanations.
        return sum(1.0 / per_cluster[c] for c in fired & set(h.clusters))

    scores: Dict[str, float] = defaultdict(float)
    covered: Dict[str, List[str]] = defaultdict(list)
    strongest: Dict[str, float] = defaultdict(float)
    for h in active:
        w = weight(h)
        for probe in h.probes:
            scores[probe] += w
            strongest[probe] = max(strongest[probe], w)
            if h.hypothesis_id not in covered[probe]:
                covered[probe].append(h.hypothesis_id)

    ranked = [
        ProbeRanking(tool=tool, score=round(scores[tool], 4),
                     hypotheses=tuple(sorted(covered[tool])),
                     strongest=round(strongest[tool], 4))
        for tool in scores
    ]
    # Deterministic order: total discrimination desc; ties go to the probe
    # testing the STRONGEST single hypothesis (when two probes discriminate
    # the same total weight, the one that can confirm or refute the leading
    # explanation is the better first question); then name asc.
    ranked.sort(key=lambda r: (-r.score, -r.strongest, r.tool))
    return ranked
