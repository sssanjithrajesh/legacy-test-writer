"""Read JaCoCo and PIT XML and run Maven profiles.

Empty suite = compile + test with no generated tests (baseline coverage 0).
Generated suite = default profile.
Reference suite = -Preference (maintainers' JUnit 3 tests).
Next suite = generated tests compiled against Commons Codec 1.5 sources (drift).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ltw.toolchain import LEGACY, Toolchain, find_toolchain

JACOCO = LEGACY / "target" / "site" / "jacoco" / "jacoco.xml"
MUTATIONS = LEGACY / "target" / "pit-reports" / "mutations.xml"
LANGUAGE = "org/apache/commons/codec/language"


@dataclass
class Coverage:
    lines_covered: int
    lines_total: int
    branches_covered: int
    branches_total: int
    by_class: dict[str, tuple[int, int]]

    @property
    def line_rate(self) -> float:
        return self.lines_covered / self.lines_total if self.lines_total else 0.0

    @property
    def branch_rate(self) -> float:
        return self.branches_covered / self.branches_total if self.branches_total else 0.0

    def as_dict(self) -> dict:
        return {
            "lines_covered": self.lines_covered,
            "lines_total": self.lines_total,
            "line_rate": round(self.line_rate, 4),
            "branches_covered": self.branches_covered,
            "branches_total": self.branches_total,
            "branch_rate": round(self.branch_rate, 4),
            "by_class": {k: {"covered": a, "total": b} for k, (a, b) in sorted(self.by_class.items())},
        }


@dataclass
class Mutation:
    killed: int
    survived: int
    no_coverage: int
    timed_out: int
    total: int

    @property
    def score(self) -> float:
        # PIT convention: killed / (killed + survived). noCoverage is a coverage problem, not a weak assertion.
        denom = self.killed + self.survived
        return self.killed / denom if denom else 0.0

    def as_dict(self) -> dict:
        return {
            "killed": self.killed,
            "survived": self.survived,
            "no_coverage": self.no_coverage,
            "timed_out": self.timed_out,
            "total": self.total,
            "score": round(self.score, 4),
        }


def parse_jacoco(path: Path = JACOCO) -> Coverage:
    root = ET.parse(path).getroot()
    lines_c = lines_t = br_c = br_t = 0
    by_class: dict[str, tuple[int, int]] = {}
    for pkg in root.findall("package"):
        name = pkg.get("name") or ""
        if not name.startswith(LANGUAGE):
            continue
        for cls in pkg.findall("class"):
            cname = (cls.get("name") or "").split("/")[-1]
            if "Test" in cname or cname.startswith("Ltw"):
                continue
            c_lines = c_total = 0
            for counter in cls.findall("counter"):
                if counter.get("type") == "LINE":
                    covered = int(counter.get("covered", 0))
                    missed = int(counter.get("missed", 0))
                    c_lines, c_total = covered, covered + missed
            by_class[cname] = (c_lines, c_total)
        for counter in pkg.findall("counter"):
            t = counter.get("type")
            covered = int(counter.get("covered", 0))
            missed = int(counter.get("missed", 0))
            if t == "LINE":
                lines_c, lines_t = covered, covered + missed
            elif t == "BRANCH":
                br_c, br_t = covered, covered + missed
    return Coverage(lines_c, lines_t, br_c, br_t, by_class)


def parse_mutations(path: Path = MUTATIONS) -> Mutation:
    root = ET.parse(path).getroot()
    counts = {"KILLED": 0, "SURVIVED": 0, "NO_COVERAGE": 0, "TIMED_OUT": 0}
    total = 0
    for mut in root.findall("mutation"):
        status = mut.get("status") or ""
        total += 1
        if status in counts:
            counts[status] += 1
    return Mutation(counts["KILLED"], counts["SURVIVED"], counts["NO_COVERAGE"], counts["TIMED_OUT"], total)


@dataclass
class SuiteResult:
    tests_run: int
    failures: int
    errors: int
    coverage: Coverage | None
    mutation: Mutation | None
    log_tail: str = ""

    def as_dict(self) -> dict:
        return {
            "tests_run": self.tests_run,
            "failures": self.failures,
            "errors": self.errors,
            "coverage": self.coverage.as_dict() if self.coverage else None,
            "mutation": self.mutation.as_dict() if self.mutation else None,
        }


def _surefire_counts() -> tuple[int, int, int]:
    reports = LEGACY / "target" / "surefire-reports"
    run = fail = err = 0
    if not reports.is_dir():
        return 0, 0, 0
    for p in reports.glob("TEST-*.xml"):
        root = ET.parse(p).getroot()
        run += int(root.get("tests", 0))
        fail += int(root.get("failures", 0))
        err += int(root.get("errors", 0))
    return run, fail, err


def run_suite(profile: str | None = None, pit: bool = False, tc: Toolchain | None = None) -> SuiteResult:
    tc = tc or find_toolchain()
    goals = ["clean", "test"]
    if pit:
        goals.append("org.pitest:pitest-maven:mutationCoverage")
    proc = tc.run_mvn(*goals, profile=profile, timeout=2400)
    full = (proc.stdout or "") + (proc.stderr or "")
    tail = full[-2000:]
    run, fail, err = _surefire_counts()
    cov = parse_jacoco() if JACOCO.is_file() else None
    mut = parse_mutations() if pit and MUTATIONS.is_file() else None
    if proc.returncode != 0 and run == 0:
        compile_hit = any(
            s in full for s in ("Compilation failure", "COMPILATION ERROR", "has private access", "cannot find symbol")
        )
        if compile_hit:
            n = full.count("has private access") + full.count("cannot find symbol")
            return SuiteResult(0, 0, max(n, 1), None, None, tail)
        raise RuntimeError(f"maven failed (profile={profile}):\n{tail}")
    return SuiteResult(run, fail, err, cov, mut, tail)
