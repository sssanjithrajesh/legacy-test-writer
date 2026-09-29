"""Decide which observed scenarios become tests and which wait for a human.

Emitted tests assert only the type of a result or exception, never the exception message.
A message is an implementation accident; pinning it is how generated suites rot.

Held for review:
- first run and second run disagreed (not frozen; the code is not deterministic on this input)
- result type we cannot assert (arrays, unknown objects)
- LLM-proposed scenario the probe could not compile (recorded as a note)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ltw.scenario import Observed

ASSERTABLE_OK = {
    "java.lang.String",
    "java.lang.Integer",
    "java.lang.Boolean",
    "java.lang.Long",
    "int",
    "boolean",
    "long",
    "null",
}
ASSERTABLE_EX = {
    "org.apache.commons.codec.EncoderException",
    "java.lang.IllegalArgumentException",
    "java.lang.NullPointerException",
    "java.lang.ArrayIndexOutOfBoundsException",
    "java.lang.StringIndexOutOfBoundsException",
    "java.lang.NegativeArraySizeException",
}


@dataclass
class Verdict:
    observed: Observed
    action: str  # emit | hold
    reason: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.observed.scenario.id,
            "action": self.action,
            "reason": self.reason,
            "notes": list(self.notes),
            "deterministic": self.observed.deterministic,
        }


def decide(row: Observed) -> Verdict:
    if not row.deterministic:
        return Verdict(row, "hold", "not_deterministic", ["first and second probe runs disagreed"])
    obs = row.first
    if obs.kind == "OK":
        if obs.type not in ASSERTABLE_OK:
            return Verdict(row, "hold", "unassertable_type", [f"result type {obs.type} has no simple equality"])
        return Verdict(row, "emit", "ok")
    if obs.type not in ASSERTABLE_EX:
        return Verdict(row, "hold", "unassertable_exception", [f"exception {obs.type} is not on the expected list"])
    return Verdict(row, "emit", "expected_exception")


def review(rows: list[Observed]) -> list[Verdict]:
    return [decide(r) for r in rows]
