"""Optional extra scenarios from Claude, behind ANTHROPIC_API_KEY.

The model only proposes inputs. The probe still runs them twice against the real class,
and review.py still decides whether they become tests. A hallucinated expected value
cannot reach the suite.
"""

from __future__ import annotations

import json
import os
import re

from ltw.javaparse import JavaClass
from ltw.scenario import Scenario


def extra_scenarios(cls: JavaClass, existing: list[Scenario], client=None) -> list[Scenario]:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and client is None:
        return []
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    prompt = (
        f"Propose up to 12 additional characterization-test inputs for Java class {cls.fqcn}.\n"
        f"Public methods:\n" + "\n".join(f"- {m.signature}" for m in cls.methods) + "\n"
        "Return JSON array of objects: method, args (array of Java expressions as strings), label.\n"
        "Only String-typed methods. No comments."
    )
    resp = client.messages.create(
        model=os.environ.get("LTW_LLM_MODEL", "claude-sonnet-4-5"),
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        rows = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[Scenario] = []
    methods = {x.name: x for x in cls.methods}
    n = 0
    for row in rows:
        name = row.get("method")
        meth = methods.get(name)
        if meth is None or meth.arity != len(row.get("args") or []):
            continue
        n += 1
        args = ", ".join(str(a) for a in row["args"])
        setup = () if meth.static else (f"{cls.name} subject = new {cls.name}();",)
        recv = cls.name if meth.static else "subject"
        out.append(
            Scenario(
                id=f"{cls.name}-L{n:02d}",
                cls=cls.name,
                method=name,
                setup=setup,
                call=f"{recv}.{name}({args})",
                label=str(row.get("label") or args),
                tags=("llm",),
                source="llm",
            )
        )
    return out
