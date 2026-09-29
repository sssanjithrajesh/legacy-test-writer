"""Compile a throwaway Java probe, run every scenario twice, record what the legacy code does.

The probe is generated from the same setup/call strings that later become the JUnit tests.
There is no translation step: what we observed is what we assert.
"""

from __future__ import annotations

from pathlib import Path

from ltw.scenario import Observation, Observed, Scenario
from ltw.toolchain import ROOT, Toolchain, find_toolchain

PROBE_DIR = ROOT / "legacy" / "target" / "ltw-probe"
SRC_ROOT = ROOT / "legacy" / "src" / "main" / "java"


def _escape_field(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def _unescape_field(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _probe_source(scenarios: list[Scenario]) -> str:
    blocks = []
    for s in scenarios:
        body = "\n            ".join(list(s.setup) + [f"return {s.call};"])
        blocks.append(f'        run("{s.id}", () -> {{\n            {body}\n        }});')
    body = "\n".join(blocks)
    return f"""package org.apache.commons.codec.language;

import org.apache.commons.codec.EncoderException;
import org.apache.commons.codec.StringEncoder;

public class LtwProbe {{
    interface Thunk {{ Object apply() throws Exception; }}

    static String esc(String v) {{
        if (v == null) return "";
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < v.length(); i++) {{
            char c = v.charAt(i);
            if (c == '\\\\') b.append("\\\\\\\\");
            else if (c == '\\t') b.append("\\\\t");
            else if (c == '\\n') b.append("\\\\n");
            else if (c == '\\r') b.append("\\\\r");
            else b.append(c);
        }}
        return b.toString();
    }}

    static String once(Thunk t) {{
        try {{
            Object r = t.apply();
            if (r == null) return "OK\\tnull\\t";
            String type = r.getClass().getName();
            String val = String.valueOf(r);
            return "OK\\t" + type + "\\t" + esc(val);
        }} catch (Throwable e) {{
            String msg = e.getMessage();
            return "EX\\t" + e.getClass().getName() + "\\t" + esc(msg == null ? "" : msg);
        }}
    }}

    static void run(String id, Thunk t) {{
        System.out.println(id + "\\t" + once(t) + "\\t" + once(t));
    }}

    public static void main(String[] args) {{
{body}
    }}
}}
"""


def _parse_line(line: str) -> tuple[str, Observation, Observation]:
    parts = line.split("\t")
    if len(parts) != 7:
        raise ValueError(f"bad probe line ({len(parts)} fields): {line[:120]!r}")
    sid, k1, t1, v1, k2, t2, v2 = parts
    return (
        sid,
        Observation(sid, k1, t1, None if t1 == "null" else _unescape_field(v1)),
        Observation(sid, k2, t2, None if t2 == "null" else _unescape_field(v2)),
    )


def observe(scenarios: list[Scenario], tc: Toolchain | None = None) -> list[Observed]:
    tc = tc or find_toolchain()
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    src = PROBE_DIR / "LtwProbe.java"
    src.write_text(_probe_source(scenarios), encoding="ascii")

    sources = sorted(SRC_ROOT.rglob("*.java"))
    compile_args = ["-encoding", "US-ASCII", "-d", str(PROBE_DIR), *[str(p) for p in sources], str(src)]
    compiled = tc.run_javac(*compile_args, cwd=PROBE_DIR)
    if compiled.returncode != 0:
        raise RuntimeError("probe javac failed:\n" + (compiled.stderr or compiled.stdout))

    ran = tc.run_java("-cp", str(PROBE_DIR), "org.apache.commons.codec.language.LtwProbe", cwd=PROBE_DIR, timeout=120)
    if ran.returncode != 0:
        raise RuntimeError("probe java failed:\n" + (ran.stderr or ran.stdout))

    by_id = {s.id: s for s in scenarios}
    out: list[Observed] = []
    for line in ran.stdout.splitlines():
        if not line.strip():
            continue
        sid, first, second = _parse_line(line)
        out.append(Observed(by_id[sid], first, second))
    if len(out) != len(scenarios):
        raise RuntimeError(f"probe returned {len(out)} rows for {len(scenarios)} scenarios")
    return out


def write_observations(rows: list[Observed], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps([r.as_dict() for r in rows], indent=2) + "\n", encoding="utf-8")
