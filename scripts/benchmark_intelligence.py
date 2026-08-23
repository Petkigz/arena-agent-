#!/usr/bin/env python3
"""Run Arena's isolated longitudinal intelligence benchmark suite."""

from __future__ import annotations

import json
import sys

from app.cognition.intelligence_benchmark import IntelligenceBenchmarkSuite


def main() -> int:
    report = IntelligenceBenchmarkSuite().run()
    print(json.dumps(report.to_dict(), indent=2))
    if report.regressions:
        print(f"\nREGRESSIONS: {', '.join(report.regressions)}", file=sys.stderr)
    return 0 if report.passed_count == report.total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
