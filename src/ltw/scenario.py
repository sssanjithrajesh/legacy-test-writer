"""The unit of work: one call whose result we observe and then freeze into a test.

A Scenario is pure Java text (setup statements plus one expression). The same text is
compiled twice: once inside the probe that records what the legacy code actually does,
and once inside the emitted JUnit test that asserts it keeps doing that. Sharing the text
is what makes the tests trustworthy: there is no translation step where the assertion
could drift from what was observed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Scenario:
    id: str
    cls: str
    method: str
    setup: tuple[str, ...]
    call: str
    label: str
    tags: tuple[str, ...] = ()
    source: str = "deterministic"  # or "llm"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["setup"] = list(self.setup)
        d["tags"] = list(self.tags)
        return d

    @staticmethod
    def from_dict(d: dict) -> Scenario:
        return Scenario(
            id=d["id"],
            cls=d["cls"],
            method=d["method"],
            setup=tuple(d.get("setup", ())),
            call=d["call"],
            label=d["label"],
            tags=tuple(d.get("tags", ())),
            source=d.get("source", "deterministic"),
        )


@dataclass
class Observation:
    """What the probe saw for one scenario. `kind` is OK or EX."""

    scenario_id: str
    kind: str
    type: str  # java type name for OK ("java.lang.String", "int", ...) or exception class for EX
    value: str | None  # decoded value or exception message; None for a null result

    @property
    def ok(self) -> bool:
        return self.kind == "OK"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Observed:
    scenario: Scenario
    first: Observation
    second: Observation | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def deterministic(self) -> bool:
        return self.second is not None and _same(self.first, self.second)

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario.as_dict(),
            "first": self.first.as_dict(),
            "second": self.second.as_dict() if self.second else None,
            "deterministic": self.deterministic,
            "notes": list(self.notes),
        }


def _same(a: Observation, b: Observation) -> bool:
    return (a.kind, a.type, a.value) == (b.kind, b.type, b.value)


def jstr(value: str | None) -> str:
    """Render a Python string as an ASCII-only Java string literal."""
    if value is None:
        return "null"
    out = ['"']
    for ch in value:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif 32 <= o < 127:
            out.append(ch)
        else:
            out.append(f"\\u{o:04x}")
    out.append('"')
    return "".join(out)


_IDENT_BAD = re.compile(r"[^A-Za-z0-9_]")


def slug(text: str, limit: int = 40) -> str:
    """Turn an input description into a readable identifier fragment."""
    if text == "null":
        return "null"
    if text == '""':
        return "empty"
    if text.strip('"') == " ":
        return "blank"
    t = text.strip('"')
    t = t.replace("\\u", "u").replace(" ", "_")
    t = _IDENT_BAD.sub("", t)
    if not t:
        return "symbols"
    if t[0].isdigit():
        t = "n" + t
    return t[:limit]
