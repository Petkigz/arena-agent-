"""Goal-side concept expansion: colloquial SYMPTOMS -> diagnostic CONCEPTS.

P0 #8 — the intelligence upgrade for capability discovery. Lexical matching
(synonyms, keywords, domain priors) knows WHAT TOOLS EXIST; it does not
understand WHAT A COMPLAINT MEANS. "Find why my computer suddenly became
slow" shares no tokens with process inspection, CPU metrics, memory
pressure, disk IO, startup load, network activity, logs or thermals — so
the discovery funnel never proposed any of them, and the embedding backend
only helps when an embedding model happens to be loaded in LM Studio.

This module is the deterministic knowledge layer that closes that gap
locally, with no model required:

    "computer suddenly became slow"  ->  the standard diagnostic tree:
        process, cpu, memory, disk io, startup, network, logs, temperature

It is deliberately a KNOWLEDGE BRIDGE, not a heuristic guess:

  * It fires only on recognized SYMPTOM PATTERNS — colloquial problem
    statements people actually say — never on every input.
  * Each cluster carries its REASON (why these concepts follow from that
    symptom) — expansion is inspectable evidence, not a score adjustment.
  * It EXPANDS the matching text for discovery only. It never rewrites the
    goal, never selects the tool, never bypasses the planner, the
    availability probes or the gates: discovery PROPOSES, the planner and
    the owner decide (the invariant that already governs rank_tools).
  * Concepts are shared vocabulary, not tool names: they describe the
    DIAGNOSTIC SPACE a symptom opens, and the manifest's tools compete for
    those terms exactly as they do for the goal's own words.

The embedding backend stays the general-purpose semantic layer (true
synonymy for arbitrary text). The bridge covers the high-value,
high-frequency domain where determinism matters most: the owner describing
a machine problem in plain language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ConceptCluster:
    """One symptom class and the diagnostic concepts it opens.

    ``context_patterns`` (optional): for clusters whose symptom words are
    ambiguous in ordinary language ("slow cooking", "hot song"), the
    cluster fires only when the goal ALSO names the affected SUBJECT —
    the machine. A slowness complaint about a RECIPE is not a performance
    complaint; requiring the context keeps the bridge from polluting
    ordinary requests with diagnostic vocabulary.
    """
    cluster_id: str
    patterns: Tuple[str, ...]          # regexes over the raw goal text
    concepts: Tuple[str, ...]          # shared diagnostic vocabulary
    reason: str
    context_patterns: Tuple[str, ...] = ()  # if set: at least one must match


@dataclass(frozen=True)
class ConceptExpansion:
    """The result of expanding one goal text through the concept bridge."""
    original: str
    expanded: str                      # original + ' ' + concept terms
    concepts: Tuple[str, ...] = ()     # deduplicated, in fire order
    evidence: Tuple[Dict[str, Any], ...] = ()  # one record per fired cluster

    @property
    def fired(self) -> bool:
        return bool(self.concepts)


# ── the knowledge: symptom classes -> diagnostic concepts ───────────────────
#
# Concepts are matched against tool NAMES + DESCRIPTIONS (see rank_tools),
# so they are written in the vocabulary those actually use. Morphological
# variants are listed explicitly (process/processes, log/logs) — the lexical
# layer matches whole tokens.

_CONCEPT_CLUSTERS: Tuple[ConceptCluster, ...] = (
    ConceptCluster(
        cluster_id="performance_slowness",
        patterns=(
            r"\b(?:slow|slowly|sluggish|lag(?:gy|ging|s)?|stutter(?:ing)?)\b",
            r"\b(?:slowed|slowing)\s+(?:down|to)\b",
            r"\bperformance\s+(?:problem|issue|degraded?)\b",
            r"\b(?:taking|takes)\s+(?:forever|ages|a\s+long\s+time)\b",
        ),
        # "slow" alone is ambiguous ("slow cooking", "a slow song") — the
        # cluster fires only when the machine is the named subject.
        context_patterns=(
            r"\b(?:computer|pc|laptop|notebook|machine|system|desktop|"
            r"windows|mac|macbook|linux|ubuntu|everything|games?|gaming|"
            r"programs?|apps?|software)\b",
        ),
        concepts=(
            "performance", "process", "processes", "cpu", "memory", "ram",
            "disk", "io", "startup", "boot", "load", "temperature", "thermal",
            "network", "activity", "log", "logs", "metrics", "usage",
        ),
        reason="A slowness complaint has a standard diagnostic tree: process "
               "load, CPU, memory pressure, disk IO, startup load, network "
               "activity, thermal throttling and recent logs.",
    ),
    ConceptCluster(
        cluster_id="overheating_thermal",
        patterns=(
            r"\b(?:overheat(?:ing|s|ed)?|running\s+hot|getting\s+hot)\b",
            r"\b(?:too|so|very|really|extremely|quite|feels?)\s+hot\b",
            r"\bhot\s+to\s+the\s+touch\b",
            r"\bfan\s+(?:is\s+(?:really\s+|very\s+|quite\s+)?|makes?\s+)?(?:noise|noisy|loud|running|spinning)\b",
            r"\bthermal\b",
        ),
        # "hot" alone means many things ("hot deals") — require the machine.
        context_patterns=(
            r"\b(?:computer|pc|laptop|notebook|machine|system|desktop|cpu|gpu|"
            r"windows|mac|macbook|linux|ubuntu|idle|gaming|while\s+(?:i\s+)?"
            r"(?:play|game|work|render|compile|train))\b",
        ),
        concepts=("temperature", "thermal", "cpu", "load", "fan", "sensors"),
        reason="Heat complaints map to thermal sensors, CPU load (sustained "
               "load = heat), and throttling risk.",
    ),
    ConceptCluster(
        cluster_id="crash_instability",
        patterns=(
            r"\b(?:crash(?:es|ed|ing)?|freez(?:e|es|ed|ing)|hang(?:s|ed|ing)?|bsod|blue\s+screen)\b",
            r"\bunstable\b",
            r"\b(?:reboot|restart)(?:s|ing)?\s+(?:itself|randomly|on\s+its\s+own)\b",
            r"\b(?:keeps?|kept)\s+(?:rebooting|restarting|freezing|crashing)\b",
        ),
        # "crash", "freeze", "hang" and "unstable" are ordinary English with
        # strong non-computer meanings ("the stock market crashed", "the
        # recipe is freezing", "the business is unstable", "let's hang out")
        # — and this bridge sits BEFORE capability discovery, so an ungated
        # fire pollutes every downstream candidate with machine-diagnostics
        # vocabulary. Same treatment as "slow"/"hot": the cluster fires only
        # when the machine (or something that runs on one) is the named
        # subject. The second pattern lists symptoms that ARE machine-only
        # vocabulary — a blue screen is its own context evidence.
        context_patterns=(
            r"\b(?:computer|pc|laptop|notebook|machine|system|desktop|"
            r"windows|mac|macbook|linux|ubuntu|everything|games?|gaming|"
            r"programs?|apps?|software|browsers?|servers?|os)\b",
            r"\b(?:bsod|blue\s+screen)s?\b",
        ),
        concepts=("memory", "ram", "log", "logs", "process", "processes",
                  "temperature", "disk", "metrics"),
        reason="Crashes/freezes call for memory pressure, system logs "
               "(crash records), process state, disk health and thermals.",
    ),
    ConceptCluster(
        cluster_id="connectivity_problems",
        patterns=(
            r"\b(?:no|lost|dropped|keeps\s+dropping|slow)\s+(?:internet|wifi|wi-fi|network|connection)\b",
            r"\b(?:can'?t|cannot|won'?t)\s+(?:connect|reach)\b",
            r"\binternet\s+(?:is\s+)?(?:down|slow|not\s+working)\b",
        ),
        concepts=("network", "dns", "connectivity", "ping", "port", "wifi",
                  "activity", "connections"),
        reason="Connectivity complaints map to DNS resolution, port checks, "
               "ping/latency and local network activity.",
    ),
    ConceptCluster(
        cluster_id="storage_pressure",
        patterns=(
            r"\b(?:disk|drive|storage|space)\s+(?:is\s+)?(?:full|almost\s+full|low|running\s+out)\b",
            r"\bnot\s+enough\s+(?:disk|storage|space)\b",
            r"\bfree\s+up\s+space\b",
        ),
        concepts=("disk", "storage", "usage", "space", "large", "files",
                  "partitions", "cleanup"),
        reason="Storage pressure maps to per-partition usage and finding what "
               "consumes the space.",
    ),
    ConceptCluster(
        cluster_id="slow_boot_startup",
        patterns=(
            r"\b(?:slow|slowly|long)\s+(?:boot|startup|start\s*up|login|log\s*on)\b",
            r"\b(?:boot(?:s|ing|ed)?|start(?:s|ing|ed)?(?:\s*up)?|startups?|login|log\s*(?:in|on|ging)?)\s+(?:is\s+|takes?\s+|taking\s+)*(?:slow(?:ly)?|long|forever|ages)\b",
            r"\btakes\s+(?:forever|ages|a\s+long\s+time)\s+to\s+(?:boot|start(?:\s*up)?|log\s*(?:in|on))\b",
            r"\bstartup\s+(?:programs?|items?|apps?)\b",
        ),
        concepts=("startup", "boot", "programs", "services", "autostart",
                  "login"),
        reason="Boot-time complaints map directly to the startup/autostart "
               "inventory.",
    ),
    ConceptCluster(
        cluster_id="power_battery",
        patterns=(
            r"\bbattery\s+(?:drains?|draining|dies?|dying|life)\b",
            r"\b(?:power|energy)\s+(?:usage|consumption|drain)\b",
        ),
        concepts=("battery", "power", "process", "processes", "cpu", "usage",
                  "metrics"),
        reason="Battery drain maps to per-process CPU/energy usage and system "
               "metrics.",
    ),
    ConceptCluster(
        cluster_id="security_suspicion",
        patterns=(
            r"\b(?:infected|malware|virus|trojan|keylogger|crypto\s*miner|miner)\b",
            r"\bsuspicious\s+(?:process|program|activity|connection)s?\b",
            r"\b(?:is|has)\s+(?:my\s+)?(?:computer|pc|system|machine)\s+been\s+(?:hacked|compromised)\b",
        ),
        concepts=("process", "processes", "network", "connections", "activity",
                  "startup", "log", "logs", "cpu", "usage"),
        reason="Compromise suspicion has a standard triage: unknown processes, "
               "unexpected network connections, new startup entries, and log "
               "anomalies.",
    ),
)

# Pre-compiled pattern cache (module load, once).
_COMPILED = tuple(
    (
        cluster,
        tuple(re.compile(p, re.IGNORECASE) for p in cluster.patterns),
        tuple(re.compile(p, re.IGNORECASE) for p in cluster.context_patterns),
    )
    for cluster in _CONCEPT_CLUSTERS
)


def expand_goal(text: str) -> ConceptExpansion:
    """Expand a goal text through the symptom->concept bridge.

    Non-symptom texts pass through VERBATIM with no concepts (the bridge
    never fires on ordinary requests — that would pollute discovery).
    """
    original = str(text or "")
    if len(original.strip()) < 4:
        return ConceptExpansion(original=original, expanded=original)

    fired: List[ConceptCluster] = []
    for cluster, compiled, compiled_context in _COMPILED:
        if not any(p.search(original) for p in compiled):
            continue
        # Context-gated clusters fire only when the affected subject (the
        # machine) is named — see ConceptCluster.context_patterns.
        if compiled_context and not any(p.search(original) for p in compiled_context):
            continue
        fired.append(cluster)

    if not fired:
        return ConceptExpansion(original=original, expanded=original)

    concepts: List[str] = []
    seen = set()
    for cluster in fired:
        for concept in cluster.concepts:
            if concept not in seen:
                seen.add(concept)
                concepts.append(concept)

    evidence = tuple(
        {
            "cluster": c.cluster_id,
            "concepts": list(c.concepts),
            "reason": c.reason,
        }
        for c in fired
    )
    expanded = f"{original} {' '.join(concepts)}".strip()
    return ConceptExpansion(
        original=original,
        expanded=expanded,
        concepts=tuple(concepts),
        evidence=evidence,
    )
