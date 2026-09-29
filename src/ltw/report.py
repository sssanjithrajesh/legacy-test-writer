"""SVG charts and a one-page HTML report. No matplotlib."""

from __future__ import annotations

from xml.sax.saxutils import escape

from ltw.measure import Coverage, Mutation

FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"
C_GEN, C_REF, C_BASE = "#2b7a4b", "#2f6db3", "#b0b0b0"


def _bar(x: float, y: int, w: float, h: int, colour: str) -> str:
    return f"<rect x='{x:.1f}' y='{y}' width='{max(w, 0):.1f}' height='{h}' fill='{colour}'/>"


def coverage_chart(rows: list[tuple[str, float, float]], width: int = 640) -> str:
    """Per class: generated line coverage vs reference line coverage."""
    if not rows:
        return ""
    row_h, top, left = 32, 36, 160
    scale = (width - left - 80) / 1.0
    h = top + row_h * len(rows) + 12
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{h}' {FONT} font-size='12'>"]
    out.append(
        f"<rect x='{left}' y='8' width='12' height='12' fill='{C_GEN}'/><text x='{left + 16}' y='18'>generated</text>"
    )
    out.append(
        f"<rect x='{left + 120}' y='8' width='12' height='12' fill='{C_REF}'/>"
        f"<text x='{left + 136}' y='18'>maintainers</text>"
    )
    for i, (label, gen, ref) in enumerate(rows):
        y = top + i * row_h
        out.append(f"<text x='{left - 6}' y='{y + 14}' text-anchor='end' font-weight='600'>{escape(label)}</text>")
        out.append(_bar(left, y, gen * scale, 11, C_GEN))
        out.append(_bar(left, y + 13, ref * scale, 11, C_REF))
        out.append(f"<text x='{left + gen * scale + 4:.1f}' y='{y + 10}' fill='#333'>{gen:.0%}</text>")
        out.append(f"<text x='{left + ref * scale + 4:.1f}' y='{y + 23}' fill='#333'>{ref:.0%}</text>")
    out.append("</svg>")
    return "".join(out)


def mutation_chart(gen: Mutation, ref: Mutation | None, width: int = 640) -> str:
    rows = [("generated", gen.killed, gen.survived, gen.no_coverage)]
    if ref:
        rows.append(("maintainers", ref.killed, ref.survived, ref.no_coverage))
    row_h, top, left = 36, 36, 130
    mx = max(k + s + n for _, k, s, n in rows) or 1
    scale = (width - left - 80) / mx
    h = top + row_h * len(rows) + 12
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{h}' {FONT} font-size='12'>"]
    out.append(
        f"<rect x='{left}' y='8' width='12' height='12' fill='{C_GEN}'/><text x='{left + 16}' y='18'>killed</text>"
    )
    out.append(
        f"<rect x='{left + 90}' y='8' width='12' height='12' fill='#d9a21b'/>"
        f"<text x='{left + 106}' y='18'>survived</text>"
    )
    out.append(
        f"<rect x='{left + 200}' y='8' width='12' height='12' fill='{C_BASE}'/>"
        f"<text x='{left + 216}' y='18'>no coverage</text>"
    )
    for i, (label, k, s, n) in enumerate(rows):
        y = top + i * row_h
        out.append(f"<text x='{left - 6}' y='{y + 16}' text-anchor='end' font-weight='600'>{escape(label)}</text>")
        x = left
        out.append(_bar(x, y, k * scale, 20, C_GEN))
        x += k * scale
        out.append(_bar(x, y, s * scale, 20, "#d9a21b"))
        x += s * scale
        out.append(_bar(x, y, n * scale, 20, C_BASE))
        score = k / (k + s) if (k + s) else 0
        out.append(f"<text x='{x + 8:.1f}' y='{y + 15}' fill='#333'>{score:.0%} kill</text>")
    out.append("</svg>")
    return "".join(out)


def headline_chart(empty: Coverage | None, gen: Coverage, ref: Coverage | None, width: int = 640) -> str:
    items = [("empty suite", empty.line_rate if empty else 0.0, C_BASE), ("generated", gen.line_rate, C_GEN)]
    if ref:
        items.append(("maintainers", ref.line_rate, C_REF))
    top, left, bar_h = 36, 140, 22
    h = top + 34 * len(items) + 16
    scale = width - left - 80
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{h}' {FONT} font-size='12'>"]
    out.append(f"<text x='{left}' y='20' font-size='14' font-weight='600'>Line coverage</text>")
    for i, (label, rate, colour) in enumerate(items):
        y = top + i * 34
        out.append(f"<text x='{left - 8}' y='{y + 16}' text-anchor='end' font-weight='600'>{escape(label)}</text>")
        out.append(_bar(left, y, rate * scale, bar_h, colour))
        out.append(f"<text x='{left + rate * scale + 6:.1f}' y='{y + 16}' fill='#333'>{rate:.0%}</text>")
    out.append("</svg>")
    return "".join(out)
