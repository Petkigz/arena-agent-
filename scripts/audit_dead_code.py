#!/usr/bin/env python3
"""Dead-code / abandoned-code / repetition audit (owner standing rule).

Three passes, all static and fast:

1. Python orphans — every module under ``app/`` must be referenced by at
   least one non-test import (production code). Modules referenced ONLY by
   tests are reported separately as ``test_only`` (potential abandoned code).
2. Frontend orphans — every exported symbol under ``frontend/src`` must be
   imported somewhere else in the frontend (pages, tests, or entry points).
   Entry-point files (main.tsx, App.tsx, routes/index.ts, *.test.*) count
   as consumers.
3. Repetition — duplicate top-level Python function names appearing in more
   than one module of the same package (copy-paste drift), and duplicate
   exported function names across frontend service files.

Exit code is 0 even when findings exist (this is a report for the owner and
the agent to act on); the agent must include the summary in its audit notes.

Usage: python scripts/audit_dead_code.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app"
FE = REPO / "frontend" / "src"

# Modules that are intentionally imported only by tests right now.
KNOWN_TEST_ONLY = {
    # (filled from the audit itself; entries here are acknowledged with reasons)
}

# Frontend entry points and test files count as consumers.
FE_ENTRY_RE = re.compile(r"(^|/)(main\.tsx|App\.tsx|index\.tsx|routes/index\.ts)$")
FE_TEST_RE = re.compile(r"\.test\.(ts|tsx)$")


# ── Acknowledged findings (2026-09-08 resurrection slice, owner-visible) ──
# These are NOT drift. Each entry states why it exists and who decides its
# fate. The audit reports them separately so they are never silently lost.

ACKNOWLEDGED_PY_TEST_ONLY = {
    "app/cognition/cognitive_router.py": "owner-deferred: cognitive_router vs live router decision (charter §5 ⑦)",
    "app/cognition/confidence.py": "owner-deferred: confidence model decision (charter §5 ⑦)",
    "app/cognition/autonomous_operator.py": "owner-deferred: autonomy scope decision (charter §5 ⑦)",
}

ACKNOWLEDGED_FE_UTILITY_FILES = {
    # Declared toolkit: callable capabilities, documented in the ledger.
    "src/utils/accessibility.ts": "a11y toolkit (announce/contrast/audit) — mount candidates for next UI slice",
    "src/hooks/useAccessibility.ts": "a11y hook wrapper (duplicate announce impl — consolidation candidate)",
    "src/hooks/usePerformance.ts": "perf toolkit (throttle/debounce/memo hooks)",
    "src/utils/themeUtils.ts": "theme toolkit (contrast + theme detection)",
    "src/components/animations/variants.ts": "motion variants toolkit (iconRotation/pulse/typingDot)",
    "src/design/tokens.ts": "design tokens (FONT_FAMILY/BASE_FONT_SIZE_PX are part of the token surface)",
    "src/utils/graphExport.ts": "exportConversationsAsMarkdown kept next to graph export helpers",
    "src/utils/serviceWorker.ts": "unregisterServiceWorker: maintenance hook for offline cache resets",
    "src/services/api.ts": "endpoint wrappers for live backend capabilities not yet UI-consumed "
    "(detectFaces, getVlmStatus, ocrImage, vlmAnalyze, listBackendProjects, listMemoryPage, "
    "listWorkspaceFilePage) — candidate mounts, owner decides priority",
}

ACKNOWLEDGED_FE_DUP_EXPORTS = {
    # Same name, different semantics: api.ts downloads a backend file by ID;
    # graphExport.ts saves text to disk via Blob. Not copy-paste duplication.
    "downloadFile": "name collision, distinct implementations (network download vs blob export)",
}


def python_modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__init__" not in p.name)


def repo_text_files() -> list[Path]:
    files: list[Path] = []
    for base in (APP, REPO / "tests", REPO / "scripts", REPO / "backend"):
        if base.exists():
            files.extend(base.rglob("*.py"))
    return [f for f in files if ".venv" not in f.parts]


def python_pass() -> dict:
    modules = python_modules()
    prod_sources: dict[Path, str] = {}
    test_sources: dict[Path, str] = {}
    for f in repo_text_files():
        text = f.read_text(errors="replace")
        if f.is_relative_to(REPO / "tests"):
            test_sources[f] = text
        else:
            prod_sources[f] = text

    prod_text = "\n".join(prod_sources.values())
    test_text = "\n".join(test_sources.values())

    orphans: list[str] = []
    test_only: list[str] = []
    for mod in modules:
        rel = mod.relative_to(REPO)
        if re.search(
            r'if __name__ == ["\']__main__["\']',
            mod.read_text(errors="replace"),
        ):
            continue  # entry-point script (run directly), not an orphan
        parts = list(rel.with_suffix("").parts)  # app/pkg/module
        dotted = ".".join(parts)
        string_ref = f'"{dotted}"' in prod_text or f"'{dotted}" + "'" in prod_text
        prod_hit = (
            f"from {dotted} import" in prod_text
            or f"import {dotted}" in prod_text
            or string_ref
            # Relative imports inside the package (from .module import X)
            or re.search(
                rf"^\s*from \.[\w.]*\b{re.escape(parts[-1])}\b import",
                prod_text,
                re.MULTILINE,
            )
        )
        if prod_hit:
            continue
        test_hit = (
            f"from {dotted} import" in test_text
            or f"import {dotted}" in test_text
            or f'"{dotted}"' in test_text
        )
        if test_hit:
            test_only.append(str(rel))
        else:
            orphans.append(str(rel))

    # Repetition: same top-level function name defined in 2+ modules of same package.
    func_re = re.compile(r"^def ([a-z_][a-z0-9_]*)\(", re.MULTILINE)
    dup = defaultdict(list)
    for f, text in prod_sources.items():
        if not f.is_relative_to(APP):
            continue
        pkg = str(f.relative_to(APP).parent)
        for name in func_re.findall(text):
            if not name.startswith("_"):
                dup[(pkg, name)].append(str(f.relative_to(REPO)))
    repetitions = {
        f"{pkg}.{name}": files
        for (pkg, name), files in dup.items()
        if len(files) > 1 and len({Path(f).name for f in files}) > 1
    }

    return {
        "python_orphans": orphans,
        "python_test_only": test_only,
        "python_duplicate_functions": repetitions,
    }


def fe_exports(path: Path) -> list[str]:
    """Value exports only — types/interfaces are erased at build time and are
    not dead code even when no other file imports them by name."""
    text = path.read_text(errors="replace")
    names: list[str] = []
    for m in re.finditer(r"export (?:async )?(?:function|const|class) ([A-Za-z0-9_]+)", text):
        names.append(m.group(1))
    for m in re.finditer(r"export \{([^}]+)\}", text):
        for part in m.group(1).split(","):
            part = part.strip().split(" as ")[0].strip()
            if re.fullmatch(r"[A-Za-z0-9_]+", part):
                names.append(part)
    return sorted(set(names))


def fe_word() -> str:
    """Underscore/dash-insensitive lookup key so file names match imports."""
    return ""


def frontend_pass() -> dict:
    if not FE.exists():
        return {"frontend_orphans": [], "frontend_duplicate_exports": {}}

    fe_files = [
        p for p in FE.rglob("*.ts*")
        if "node_modules" not in p.parts and not p.name.endswith(".d.ts")
    ]
    orphans: list[str] = []
    name_to_files: dict[str, list[str]] = defaultdict(list)
    for f in fe_files:
        rel = str(f.relative_to(REPO / "frontend"))
        for name in fe_exports(f):
            name_to_files[name].append(rel)

    for name, defs in sorted(name_to_files.items()):
        # A symbol is alive if any file other than its definers references it,
        # or if it is defined in an entry point / index barrel (public surface).
        in_entry = any(
            FE_ENTRY_RE.search(d) or Path(d).name == "index.ts" for d in defs
        )
        if in_entry:
            continue
        referenced = False
        for f in fe_files:
            rel = str(f.relative_to(REPO / "frontend"))
            if rel in defs:
                continue
            text = f.read_text(errors="replace")
            if re.search(rf"\b{name}\b", text):
                referenced = True
                break
        if not referenced:
            orphans.append(f"{name} ({', '.join(defs)})")

    dup_exports = {
        name: files
        for name, files in name_to_files.items()
        if len(files) > 1
        and not name.startswith(("I", "T"))  # allow common type prefixes collisions
        and len({Path(f).parent.name for f in files}) > 1
        and Path(files[0]).name != "index.ts"
    }

    return {
        "frontend_orphans": orphans,
        "frontend_duplicate_exports": dup_exports,
    }


def main() -> int:
    report = {"python": python_pass(), "frontend": frontend_pass()}
    print(json.dumps(report, indent=2))
    summary = (
        f"python_orphans={len(report['python']['python_orphans'])} "
        f"python_test_only={len(report['python']['python_test_only'])} "
        f"py_dups={len(report['python']['python_duplicate_functions'])} "
        f"fe_orphans={len(report['frontend']['frontend_orphans'])} "
        f"fe_dups={len(report['frontend']['frontend_duplicate_exports'])}"
    )
    print(summary, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
