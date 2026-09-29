"""Score the last generate+measure run against a recorded gate.

uv run ltw-eval --gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ltw.toolchain import ROOT

GATE = ROOT / "evals" / "gate.json"
LATEST = ROOT / "docs" / "latest-run.json"
RESULTS = ROOT / "evals" / "results" / "latest.json"


def check_gate(summary: dict, gate: dict) -> list[str]:
    fails = []
    g = summary.get("generated") or {}
    cov = g.get("coverage") or {}
    mut = g.get("mutation") or {}
    if summary.get("emitted", 0) < gate.get("emitted", 0):
        fails.append(f"emitted {summary.get('emitted')} < {gate['emitted']}")
    if summary.get("held", 0) > gate.get("held_max", 10**9):
        fails.append(f"held {summary.get('held')} > {gate['held_max']}")
    if cov.get("line_rate", 0) < gate.get("generated_line_rate", 0):
        fails.append(f"generated line_rate {cov.get('line_rate')} < {gate['generated_line_rate']}")
    if gate.get("generated_mutation_score") is not None and mut:
        if mut.get("score", 0) < gate["generated_mutation_score"]:
            fails.append(f"mutation {mut.get('score')} < {gate['generated_mutation_score']}")
    if g.get("failures", 0) > 0 or g.get("errors", 0) > 0:
        fails.append("generated suite is not green")
    ref = (summary.get("reference") or {}).get("coverage") or {}
    if ref and cov.get("line_rate", 0) + 1e-9 < ref.get("line_rate", 0) - gate.get("coverage_slack", 0.05):
        fails.append(
            f"generated coverage {cov.get('line_rate')} lagged maintainers {ref.get('line_rate')} by more than slack"
        )
    nxt = summary.get("next") or {}
    drift = int(nxt.get("failures") or 0) + int(nxt.get("errors") or 0)
    if drift < gate.get("min_drift_failures", 0):
        fails.append(f"1.5 drift {drift} < {gate['min_drift_failures']} (suite no longer detects change)")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--summary", type=Path, default=LATEST)
    args = ap.parse_args(argv)
    if not args.summary.is_file():
        print(f"no summary at {args.summary}; run uv run ltw all first")
        return 2
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"emitted {summary.get('emitted')}  held {summary.get('held')}  "
        f"gen cov {(summary.get('generated') or {}).get('coverage', {}).get('line_rate')}  "
        f"ref cov {(summary.get('reference') or {}).get('coverage', {}).get('line_rate')}  "
        f"drift fail {(summary.get('next') or {}).get('failures')}"
    )
    if args.gate:
        gate = json.loads(GATE.read_text(encoding="utf-8"))
        fails = check_gate(summary, gate)
        if fails:
            print("EVAL GATE FAILED:\n  " + "\n  ".join(fails))
            return 1
        print("eval gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
