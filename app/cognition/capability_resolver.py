"""Capability vocabulary resolver — owner review item 7 (2026-09-01, P0).

The live problem: the LLM emits free-text capability phrases
('file searching capability', 'File system navigation skills',
'Image scanning capability', 'Report generation capabilities',
'test execution and validation capability', 'text summarization
capability', 'Photo organizing algorithms'). The old resolution chain
matched none of them — no stemming ('searching' ≠ 'search'),
no plural normalization ('files' ≠ 'file'), no noise-word stripping
('capability'/'skills'/'algorithms' are vocabulary, not stems), no
aliases — so they became `ignored_phrases`, and when every phrase was
ignored the runtime treated the action as UNCONSTRAINED
(action_available=True). The planner proceeded without possessing the
requested capability. That silent fallback is the bug this module
closes.

Resolution tiers (the owner's diagram):
    phrase → resolver
      ├── exact     normalized stem set equals a known capability's
      ├── alias     curated table of recurring LLM phrasings
      ├── semantic  strict stem overlap with real capability names
      └── unresolved → the CALLER must ask/replan/block — never
                       silently downgrade to 'unconstrained'

The resolver is deliberately vocabulary-agnostic: the caller passes the
REAL capability vocabulary (native backing keys, known-unimplemented
names, registry tool names, world-model capabilities), and every
canonical it returns is validated against that vocabulary — an alias
whose target is not actually registered resolves to UNRESOLVED, never
to a pretend capability.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from app.utils.logger import app_logger

# Vocabulary noise: these words describe the SHAPE of a capability
# phrase, not its content. They are stripped before matching so
# 'file searching capability', 'File system navigation skills' and
# 'Photo organizing algorithms' reduce to their content stems.
NOISE_WORDS = frozenset({
    "capability", "capabilities", "skill", "skills", "algorithm",
    "algorithms", "tool", "tools", "function", "functions", "ability",
    "abilities", "support", "feature", "features",
})

# Grammar filler inside capability phrases.
STOPWORDS = frozenset({
    "and", "or", "the", "a", "an", "to", "of", "for", "with", "in",
    "on", "at", "my", "your", "our", "their", "this", "that",
})

# Multi-word compounds that exist as single tokens in the real
# vocabulary ('file system' -> 'filesystem').
BIGRAM_MERGES = {
    ("file", "system"): "filesystem",
}

# Derivational suffix rules, longest first; applied ONCE per token after
# plural normalization (no over-stripping). NOTE: no bare 'tion' rule —
# it would over-strip '-ution' words ('execution' → 'execu') out of
# alignment with their verbs ('execute' → 'execut'); 'ation'+'ion' cover
# the real cases. No 'ment' rule either — 'document' is a content word
# here, not a derivation.
_DERIV_RULES = (
    ("ization", ""), ("isation", ""), ("ation", ""),
    ("ion", ""), ("ness", ""), ("ity", ""),
    ("ing", ""), ("ize", ""), ("ise", ""), ("ate", ""),
)


def _stem(token: str) -> str:
    """Tiny, deterministic stemmer: unifies the inflection gaps that
    caused the live misses (searching→search, files→file,
    generation→gener, execution→execut, summarize→summar).
    Plurals normalize FIRST so suffixed plurals agree with their
    bases ('notifications' → 'notification' → 'notific')."""
    # One family, one stem: analyze/analyse/analysis/analyzing.
    if token.startswith("analy"):
        return "analy"
    t = token
    if t.endswith("ies") and len(t) > 4:
        t = t[:-3] + "y"                       # policies → policy
    elif t.endswith(("ches", "shes", "sses", "xes", "zes")) and len(t) > 4:
        t = t[:-2]                             # matches → match
    elif t.endswith("s") and not t.endswith(("ss", "us", "is")) and len(t) > 3:
        t = t[:-1]                             # files → file, tools → tool
    for suffix, replacement in _DERIV_RULES:
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            t = t[: len(t) - len(suffix)] + replacement
            break
    # Undo consonant doubling ('scanning' → 'scann' → 'scan').
    if len(t) >= 4 and t[-1] == t[-2] and t[-1] not in "aeiouy":
        t = t[:-1]
    return t


def _merge_bigrams(tokens):
    merged, i = [], 0
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in BIGRAM_MERGES:
            merged.append(BIGRAM_MERGES[(tokens[i], tokens[i + 1])])
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged


@dataclass
class CapabilityResolution:
    """One phrase's resolution outcome. `tier` is one of
    'exact' | 'alias' | 'semantic' | 'unresolved'; `canonical` is a REAL
    vocabulary name (validated) or None."""
    phrase: str
    tier: str
    canonical: Optional[str]
    matched: Optional[str]
    detail: str

    @property
    def resolved(self) -> bool:
        return self.canonical is not None


class CapabilityResolver:
    """Normalizes LLM capability phrases onto the real capability
    vocabulary. Pure (no registry imports) so the runtime decides what
    'real' means; this class only decides what the PHRASE means."""

    # Recurring live LLM phrasings → canonical capability. Keys are
    # FROZENSETS of content stems (order-free, inflection-free). Every
    # target must exist in the caller's vocabulary at resolution time —
    # an alias to something unregistered is NOT a resolution.
    ALIASES: Dict[FrozenSet[str], str] = {
        # 'text summarization' — the LLM client is the implementation.
        frozenset({"text", "summar"}): "llm.generate",
        frozenset({"summar"}): "llm.generate",
        # 'test execution and validation' — running tests is code
        # execution (local_execute runs arbitrary snippets incl. pytest).
        frozenset({"test", "execut"}): "local_execute",
        frozenset({"test", "execut", "valid"}): "local_execute",
        # 'file system navigation' — listing/reading/traversing paths.
        frozenset({"filesystem", "navig"}): "filesystem.read",
        # 'image scanning' — examining image content is vision analysis.
        frozenset({"image", "scan"}): "vision.analyze",
        frozenset({"image", "analy"}): "vision.analyze",
        # 'report/document generation' — document tools.
        frozenset({"report", "gener"}): "generate_document",
        frozenset({"document", "gener"}): "generate_document",
        frozenset({"report", "creat"}): "generate_document",
    }

    # Semantic tier strictness: a candidate must cover at least this
    # fraction of the phrase's content stems (ceil, min 1). 0.6 means a
    # 2-stem phrase needs BOTH stems ('image scanning' cannot resolve to
    # lab_scan on the single shared stem 'scan').
    MIN_OVERLAP_RATIO = 0.6

    # ------------------------------------------------------------------
    @classmethod
    def phrase_stems(cls, phrase: str) -> FrozenSet[str]:
        """Content stems of a capability phrase: lowercase, split,
        stopword/noise stripped, bigram-merged, stemmed."""
        tokens = [t for t in re.split(r"[^a-z0-9]+", str(phrase or "").lower()) if t]
        content = [t for t in tokens if t not in NOISE_WORDS and t not in STOPWORDS]
        merged = _merge_bigrams(content)
        return frozenset(_stem(t) for t in merged)

    # ------------------------------------------------------------------
    @classmethod
    def name_stems(cls, name: str) -> FrozenSet[str]:
        """Content stems of a capability/tool NAME
        ('filesystem.search' -> {filesystem, search})."""
        tokens = [t for t in re.split(r"[^a-z0-9]+", str(name or "").lower()) if t]
        return frozenset(_stem(t) for t in tokens)

    # ------------------------------------------------------------------
    @classmethod
    def build_vocabulary(cls, names) -> Dict[str, FrozenSet[str]]:
        """name → stem-set map for a set of real capability names."""
        vocab: Dict[str, FrozenSet[str]] = {}
        for name in names:
            if name:
                vocab[str(name)] = cls.name_stems(name)
        return vocab

    # ------------------------------------------------------------------
    @classmethod
    def resolve(cls, phrase: str,
                vocabulary: Dict[str, FrozenSet[str]]) -> CapabilityResolution:
        """Resolve one phrase against the real vocabulary.

        Tiers, in order: exact (stem-set equality), alias (curated
        table), semantic (strict overlap). Unresolved is a first-class
        outcome — the caller must ask/replan/block, never treat it as
        'unconstrained'."""
        phrase_stems = cls.phrase_stems(phrase)
        if not phrase_stems:
            return CapabilityResolution(
                phrase, "unresolved", None, None,
                "phrase contains no capability content (only noise words)")

        # ── tier 1: exact — stem-set equality with a real name.
        for name, stems in vocabulary.items():
            if stems and stems == phrase_stems:
                return CapabilityResolution(
                    phrase, "exact", name, name,
                    f"exact match: stems {sorted(phrase_stems)} == {name}")

        # ── tier 2: alias — curated recurring phrasings. The target
        # must EXIST in the vocabulary or the alias does not apply.
        alias_target = cls.ALIASES.get(phrase_stems)
        if alias_target is not None and alias_target in vocabulary:
            return CapabilityResolution(
                phrase, "alias", alias_target, alias_target,
                f"alias match: '{phrase}' -> {alias_target}")

        # ── tier 3: semantic — strict stem overlap with real names.
        needed = max(1, math.ceil(cls.MIN_OVERLAP_RATIO * len(phrase_stems)))
        best_name, best_overlap, best_specificity = None, 0, 0
        for name, stems in vocabulary.items():
            if not stems:
                continue
            overlap = len(phrase_stems & stems)
            if overlap >= needed and overlap > best_overlap:
                best_name, best_overlap = name, overlap
                best_specificity = len(stems)
            elif overlap >= needed and overlap == best_overlap and best_name:
                # Tie: prefer the more specific (fewer-stem) name.
                if len(stems) < best_specificity:
                    best_name, best_specificity = name, len(stems)
        if best_name is not None:
            return CapabilityResolution(
                phrase, "semantic", best_name, best_name,
                f"semantic match: {best_overlap}/{len(phrase_stems)} content "
                f"stems of '{phrase}' are in {best_name}")

        # ── tier 4: unresolved — an honest outcome, not a failure to
        # be papered over. The caller asks/replans/blocks.
        app_logger.info(
            f"Capability phrase unresolved (no exact/alias/semantic match "
            f"in the real vocabulary): {phrase!r}")
        return CapabilityResolution(
            phrase, "unresolved", None, None,
            "unresolved: no registered capability, alias, or sufficient "
            "stem overlap matches this phrase — ask/replan, do not proceed "
            "as unconstrained")
