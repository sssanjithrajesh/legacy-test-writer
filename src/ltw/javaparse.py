"""A deliberately small Java reader.

We do not need a full parser. Characterization tests only call the public surface of a
class, so we need: the class name, its public constructors and methods (with parameter
types), whether it is abstract, and the string and integer literals in the body (they
are excellent test inputs: a literal in the source is a branch someone cared about).

Regexes on comment-stripped source are enough for the pre-generics Java this tool targets.
Inner classes are skipped on purpose: their members are only reached through the outer
class, and the generated tests should read like a user of the API, not a maintainer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_INT = re.compile(r"(?<![\w.])(-?\d+)(?![\w.])")
_CLASS = re.compile(r"\b(public\s+)?(abstract\s+)?(final\s+)?class\s+(\w+)")
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_MEMBER = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized)\s+)*)"
    r"(?:(?P<ret>[\w\[\]<>.]+)\s+)?(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*"
    r"(?:throws\s+(?P<throws>[\w.,\s]+))?\s*\{"
)
_FIELD = re.compile(r"public\s+static\s+final\s+(?P<type>[\w\[\]]+)\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=")


@dataclass(frozen=True)
class Param:
    type: str
    name: str


@dataclass(frozen=True)
class Method:
    name: str
    params: tuple[Param, ...]
    returns: str  # "void" for setters, class name for constructors
    static: bool = False
    throws: tuple[str, ...] = ()

    @property
    def signature(self) -> str:
        ps = ", ".join(f"{p.type} {p.name}" for p in self.params)
        return f"{self.returns} {self.name}({ps})"

    @property
    def arity(self) -> int:
        return len(self.params)


@dataclass
class JavaClass:
    name: str
    package: str
    path: Path
    is_abstract: bool = False
    is_public: bool = True
    constructors: list[Method] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    constants: list[Param] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    int_literals: list[int] = field(default_factory=list)
    lines: int = 0

    @property
    def fqcn(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name

    def public_methods(self) -> list[Method]:
        return [m for m in self.methods]


def strip_comments(src: str) -> str:
    # Keep line structure so line counts stay meaningful.
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), src)


def _top_level_body(src: str, class_name: str) -> str:
    """Return the text of the class body at brace depth 1, with nested classes removed."""
    m = re.search(r"\bclass\s+" + re.escape(class_name) + r"\b[^{]*\{", src)
    if not m:
        return ""
    i = m.end()
    depth = 1
    out: list[str] = []
    nested_start = None
    nested_depth = 0
    while i < len(src) and depth > 0:
        ch = src[i]
        if nested_start is None:
            # Detect the start of a nested class/interface declaration at depth 1.
            nm = re.match(
                r"(?:(?:public|protected|private|static|final|abstract)\s+)*(?:class|interface)\s+\w+", src[i:]
            )
            if nm and (i == 0 or not src[i - 1].isalnum()):
                nested_start = i
                nested_depth = 0
                i += len(nm.group(0))
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth > 0:
                out.append(ch)
        else:
            if ch == "{":
                nested_depth += 1
            elif ch == "}":
                nested_depth -= 1
                if nested_depth == 0:
                    nested_start = None
        i += 1
    return "".join(out)


def _params(text: str) -> tuple[Param, ...]:
    text = text.strip()
    if not text:
        return ()
    out = []
    for raw in text.split(","):
        bits = raw.replace("final ", "").strip().split()
        if len(bits) >= 2:
            ptype, pname = bits[-2], bits[-1]
            if pname.endswith("[]"):
                ptype, pname = ptype + "[]", pname[:-2]
            out.append(Param(ptype, pname))
    return tuple(out)


def parse_java(path: Path) -> JavaClass:
    raw = path.read_text(encoding="utf-8", errors="replace")
    src = strip_comments(raw)
    pkg = _PACKAGE.search(src)
    cm = _CLASS.search(src)
    if not cm:
        raise ValueError(f"no class declaration in {path}")
    name = cm.group(4)
    jc = JavaClass(
        name=name,
        package=pkg.group(1) if pkg else "",
        path=path,
        is_abstract=bool(cm.group(2)),
        is_public=bool(cm.group(1)),
        lines=raw.count("\n") + 1,
    )
    body = _top_level_body(src, name)
    for fm in _FIELD.finditer(body):
        jc.constants.append(Param(fm.group("type"), fm.group("name")))
    for mm in _MEMBER.finditer(body):
        mods = mm.group("mods") or ""
        if "public" not in mods:
            continue
        mname = mm.group("name")
        if mname in {"if", "for", "while", "switch", "synchronized", "catch", "return", "else", "do", "try"}:
            continue
        throws = tuple(t.strip() for t in (mm.group("throws") or "").split(",") if t.strip())
        if mname == name and mm.group("ret") is None:
            jc.constructors.append(Method(name, _params(mm.group("params")), name, False, throws))
        elif mm.group("ret"):
            jc.methods.append(Method(mname, _params(mm.group("params")), mm.group("ret"), "static" in mods, throws))
    seen: set[str] = set()
    for sm in _STRING.finditer(body):
        lit = sm.group(1)
        if lit and lit not in seen and len(lit) <= 40:
            seen.add(lit)
            jc.string_literals.append(lit)
    ints: set[int] = set()
    for im in _INT.finditer(body):
        ints.add(int(im.group(1)))
    jc.int_literals = sorted(ints)
    return jc


def parse_package(src_root: Path, package: str) -> list[JavaClass]:
    folder = src_root.joinpath(*package.split("."))
    classes = [parse_java(p) for p in sorted(folder.glob("*.java"))]
    return [c for c in classes if not c.is_abstract]
