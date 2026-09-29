"""Gate math and eval-set files."""

from __future__ import annotations

import json

from evals.run import GATE, check_gate


def _summary(**over):
    base = {
        "emitted": 400,
        "held": 2,
        "generated": {
            "tests_run": 400,
            "failures": 0,
            "errors": 0,
            "coverage": {"line_rate": 0.85, "lines_covered": 200, "lines_total": 235},
            "mutation": {"score": 0.6, "killed": 60, "survived": 40},
        },
        "reference": {"coverage": {"line_rate": 0.8}},
        "next": {"failures": 5, "errors": 0, "tests_run": 400},
    }
    base.update(over)
    return base


def test_gate_file_is_json():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert "emitted" in gate and "generated_line_rate" in gate


def test_gate_passes_a_healthy_run():
    gate = {
        "emitted": 100,
        "held_max": 20,
        "generated_line_rate": 0.7,
        "generated_mutation_score": 0.5,
        "coverage_slack": 0.05,
        "min_drift_failures": 1,
    }
    assert check_gate(_summary(), gate) == []


def test_gate_fails_on_regression_and_on_silent_drift():
    gate = {
        "emitted": 100,
        "held_max": 20,
        "generated_line_rate": 0.9,
        "generated_mutation_score": 0.8,
        "coverage_slack": 0.05,
        "min_drift_failures": 3,
    }
    fails = check_gate(_summary(), gate)
    assert any("line_rate" in f for f in fails)
    silent = _summary(next={"failures": 0, "errors": 0, "tests_run": 400})
    # compile-time drift also counts (1.5 hid a public constant)
    gate2 = {**gate, "generated_line_rate": 0.5, "generated_mutation_score": 0.1}
    fails2 = check_gate(silent, gate2)
    assert any("drift" in f for f in fails2)
