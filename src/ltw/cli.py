"""Generate characterization tests, measure them, write the report.

uv run ltw generate          # parse, propose, probe twice, emit JUnit, hold the rest
uv run ltw measure           # JaCoCo on generated suite (add --pit for mutation, --reference, --next)
uv run ltw report            # SVG + HTML from the last generate + measure
uv run ltw all               # generate, measure generated + reference + next, write report
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ltw.emit import emit
from ltw.inputs import generate_all
from ltw.javaparse import parse_package
from ltw.llm import extra_scenarios
from ltw.measure import run_suite
from ltw.probe import observe, write_observations
from ltw.report import coverage_chart, headline_chart, mutation_chart
from ltw.review import review
from ltw.toolchain import GENERATED_TESTS, LEGACY, PACKAGE, ROOT, describe, find_toolchain, toolchain_available

DOCS = ROOT / "docs"
IMG = DOCS / "img"
LATEST = DOCS / "latest-run.json"
OBS = ROOT / "evals" / "results" / "observations.json"
HELD = DOCS / "review-queue.md"


def _classes():
    src = LEGACY / "src" / "main" / "java"
    return [c for c in parse_package(src, PACKAGE) if c.is_public]


def cmd_generate(console: Console, use_llm: bool) -> dict:
    classes = _classes()
    scenarios = generate_all(classes)
    if use_llm:
        for c in classes:
            scenarios += extra_scenarios(c, [s for s in scenarios if s.cls == c.name])
    console.print(f"proposed {len(scenarios)} scenarios across {len(classes)} classes")
    tc = find_toolchain()
    console.print(describe(tc))
    rows = observe(scenarios, tc)
    write_observations(rows, OBS)
    verdicts = review(rows)
    held = [v for v in verdicts if v.action == "hold"]
    kept = [v for v in verdicts if v.action == "emit"]
    paths = emit(verdicts)
    HELD.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Held for review", "", "These scenarios were observed but not emitted as tests.", ""]
    for v in held:
        s = v.observed.scenario
        lines.append(f"- `{s.id}` {s.label}: **{v.reason}** ({'; '.join(v.notes)})")
    HELD.write_text("\n".join(lines) + "\n", encoding="ascii")
    console.print(f"emitted {len(kept)} tests in {len(paths)} files; held {len(held)} for review")
    return {
        "classes": [c.name for c in classes],
        "proposed": len(scenarios),
        "emitted": len(kept),
        "held": len(held),
        "held_reasons": {r: sum(1 for v in held if v.reason == r) for r in {v.reason for v in held}},
        "by_class": {
            c.name: {
                "methods": len(c.methods),
                "emitted": sum(1 for v in kept if v.observed.scenario.cls == c.name),
                "held": sum(1 for v in held if v.observed.scenario.cls == c.name),
            }
            for c in classes
        },
        "llm": use_llm,
    }


def cmd_measure(console: Console, pit: bool, profile: str | None) -> dict:
    tc = find_toolchain()
    result = run_suite(profile=profile, pit=pit, tc=tc)
    label = profile or "generated"
    console.print(
        f"{label}: {result.tests_run} tests, {result.failures} failures, {result.errors} errors"
        + (f", line coverage {result.coverage.line_rate:.0%}" if result.coverage else "")
        + (f", mutation {result.mutation.score:.0%}" if result.mutation else "")
    )
    if result.failures or result.errors:
        console.print(result.log_tail[-800:])
    return result.as_dict()


def _write_html(summary: dict) -> None:
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>legacy-test-writer</title>
<style>
body {{ font-family: Segoe UI, Helvetica, Arial, sans-serif; margin: 24px; color: #1a1a1a; }}
.stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0 20px; }}
.stat {{ border: 1px solid #e6e6e6; border-radius: 6px; padding: 10px 14px; min-width: 120px; }}
.stat b {{ display: block; font-size: 22px; }}
.stat span {{ font-size: 12px; color: #555; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #e6e6e6; padding: 6px 8px; text-align: left; font-size: 13px; }}
img {{ max-width: 100%; }}
code {{ background: #f3f3f3; padding: 1px 4px; }}
</style></head><body>
<h1>legacy-test-writer</h1>
<p>Characterization tests for Apache Commons Codec 1.3 <code>language</code> (2004).
Generated tests pin what the code does today. The maintainers' JUnit 3 suite is the comparison.</p>
<div class="stats">
  <div class="stat"><b>{summary.get("proposed", 0)}</b><span>scenarios proposed</span></div>
  <div class="stat"><b>{summary.get("emitted", 0)}</b><span>tests emitted</span></div>
  <div class="stat"><b>{summary.get("held", 0)}</b><span>held for review</span></div>
  <div class="stat"><b>{(summary.get("generated") or {}).get("coverage", {}).get("line_rate", 0):.0%}</b>
      <span>generated line coverage</span></div>
  <div class="stat"><b>{(summary.get("reference") or {}).get("coverage", {}).get("line_rate", 0):.0%}</b>
      <span>maintainers line coverage</span></div>
  <div class="stat"><b>{((summary.get("generated") or {}).get("mutation") or {}).get("score", 0):.0%}</b>
      <span>generated mutation score</span></div>
</div>
<h2>Line coverage</h2>
<img src="img/coverage.svg" alt="coverage">
<h2>Per class</h2>
<img src="img/by-class.svg" alt="by class">
<h2>Mutation score</h2>
<img src="img/mutation.svg" alt="mutation">
<h2>What the 1.5 sources changed</h2>
<p>Generated tests run against Commons Codec 1.5: {summary.get("next", {}).get("failures", "?")} failures,
{summary.get("next", {}).get("errors", "?")} errors of {summary.get("next", {}).get("tests_run", "?")}.</p>
<p>Held cases: <a href="review-queue.md">review-queue.md</a></p>
</body></html>
"""
    (DOCS / "report.html").write_text(html, encoding="ascii")


def cmd_report(console: Console, summary: dict) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    gen_c = (summary.get("generated") or {}).get("coverage") or {}
    ref_c = (summary.get("reference") or {}).get("coverage") or {}
    empty_c = (summary.get("empty") or {}).get("coverage")
    from ltw.measure import Coverage, Mutation

    def cov(d: dict | None) -> Coverage | None:
        if not d:
            return None
        by = {k: (v["covered"], v["total"]) for k, v in d.get("by_class", {}).items()}
        return Coverage(d["lines_covered"], d["lines_total"], d["branches_covered"], d["branches_total"], by)

    g, r, e = cov(gen_c), cov(ref_c), cov(empty_c)
    if g:
        (IMG / "coverage.svg").write_text(headline_chart(e, g, r), encoding="ascii")
        names = sorted(set(g.by_class) | set(r.by_class if r else {}))
        rows = []
        for n in names:
            gc, gt = g.by_class.get(n, (0, 1))
            rc, rt = r.by_class.get(n, (0, 1)) if r else (0, 1)
            rows.append((n, gc / gt if gt else 0, rc / rt if rt else 0))
        (IMG / "by-class.svg").write_text(coverage_chart(rows), encoding="ascii")
    gm = (summary.get("generated") or {}).get("mutation")
    rm = (summary.get("reference") or {}).get("mutation")

    def mut(d: dict | None) -> Mutation | None:
        if not d:
            return None
        return Mutation(d["killed"], d["survived"], d["no_coverage"], d["timed_out"], d["total"])

    if gm:
        (IMG / "mutation.svg").write_text(mutation_chart(mut(gm), mut(rm)), encoding="ascii")
    _write_html(summary)
    LATEST.write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    console.print(f"wrote {LATEST.relative_to(ROOT)} and {IMG}")


def _print_summary(console: Console, summary: dict) -> None:
    table = Table(title="legacy-test-writer")
    table.add_column("suite")
    table.add_column("tests", justify="right")
    table.add_column("fail", justify="right")
    table.add_column("line cov", justify="right")
    table.add_column("mutation", justify="right")
    for name in ("empty", "generated", "reference", "next"):
        block = summary.get(name) or {}
        cov = (block.get("coverage") or {}).get("line_rate")
        mut = (block.get("mutation") or {}).get("score")
        table.add_row(
            name,
            str(block.get("tests_run", "-")),
            str(block.get("failures", "-")),
            f"{cov:.0%}" if isinstance(cov, float) else "-",
            f"{mut:.0%}" if isinstance(mut, float) else "-",
        )
    console.print(table)


def _park_tests() -> Path:
    parked = ROOT / ".ltw-parked"
    if parked.exists():
        shutil.rmtree(parked)
    if GENERATED_TESTS.exists():
        shutil.copytree(GENERATED_TESTS, parked)
    return parked


def _restore_tests(parked: Path) -> None:
    if not parked.exists():
        return
    if GENERATED_TESTS.exists():
        shutil.rmtree(GENERATED_TESTS)
    shutil.copytree(parked, GENERATED_TESTS)


def cmd_all(console: Console, pit: bool, use_llm: bool) -> dict:
    gen_meta = cmd_generate(console, use_llm)
    generated = cmd_measure(console, pit=pit, profile=None)
    parked = _park_tests()
    try:
        for p in GENERATED_TESTS.rglob("*CharacterizationTest.java"):
            p.unlink()
        empty = cmd_measure(console, pit=False, profile=None)
        empty["suite"] = "empty"
        _restore_tests(parked)
        reference = cmd_measure(console, pit=pit, profile="reference")
        _restore_tests(parked)
        nxt = cmd_measure(console, pit=False, profile="next")
        _restore_tests(parked)
    finally:
        _restore_tests(parked)
        if parked.exists():
            shutil.rmtree(parked, ignore_errors=True)
    summary = {**gen_meta, "generated": generated, "empty": empty, "reference": reference, "next": nxt}
    cmd_report(console, summary)
    _print_summary(console, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ltw")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--llm", action="store_true")
    m = sub.add_parser("measure")
    m.add_argument("--pit", action="store_true")
    m.add_argument("--profile", default=None)
    sub.add_parser("report")
    a = sub.add_parser("all")
    a.add_argument("--pit", action="store_true")
    a.add_argument("--llm", action="store_true")
    args = ap.parse_args(argv)
    console = Console()
    if not toolchain_available() and args.cmd != "report":
        console.print("JDK/Maven not found. See README.")
        return 2
    if args.cmd == "generate":
        cmd_generate(console, args.llm)
    elif args.cmd == "measure":
        cmd_measure(console, args.pit, args.profile)
    elif args.cmd == "report":
        summary = json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}
        cmd_report(console, summary)
    else:
        cmd_all(console, args.pit, args.llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
