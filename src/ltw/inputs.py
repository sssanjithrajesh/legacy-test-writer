"""Deterministic input generation.

No LLM is needed to write useful characterization tests for string-processing code.
The strategies below are the ones a careful engineer applies by hand:

- corpus:    words known to exercise phonetic rules (names with silent letters, doubled
             consonants, H/W separators, prefixes like KN/GN/PS that the algorithms special-case)
- boundary:  null, empty, blank, single letters, digits, punctuation, case variants, long input,
             non-ASCII letters (written as \\uXXXX escapes so the repo stays ASCII)
- literal:   every string literal found in the class body, alone and wrapped in letters.
             A literal in the source is a branch the original author cared about.
- stateful:  every setter is paired with its getter and with the main encode method,
             so "set max length to 0 then encode" is frozen too
- mapping:   constructors that take a mapping table get the default table, a modified table,
             a too-short table and null
- pair:      two-argument methods get same/similar/different/null/empty pairs
- mismatch:  Object parameters get a String, an Integer, a StringBuffer and null

Everything is ordered and capped, so two runs produce identical scenario lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ltw.javaparse import JavaClass, Method
from ltw.scenario import Scenario, jstr

CORPUS: tuple[str, ...] = (
    "Robert",
    "Rupert",
    "Rubin",
    "Ashcraft",
    "Ashcroft",
    "Tymczak",
    "Pfister",
    "Honeyman",
    "Washington",
    "Lee",
    "Gutierrez",
    "Jackson",
    "Knight",
    "Knuth",
    "Schmidt",
    "Schneider",
    "Thompson",
    "Thomas",
    "Xavier",
    "Yang",
    "Zhang",
    "Wright",
    "Phillips",
    "Philip",
    "Gnome",
    "Psychology",
    "Wrack",
    "Aeneas",
    "Whistle",
    "Ghost",
    "Laugh",
    "Church",
    "Judge",
    "Science",
    "Dumb",
    "Thumb",
    "Caesar",
    "Ciao",
    "Cough",
    "Tough",
    "Michael",
    "Michelle",
    "Rodgers",
    "Rogers",
    "Smith",
    "Smyth",
    "Smythe",
    "Catherine",
    "Kathryn",
    "Allricht",
    "Eberhard",
    "Engebrethson",
    "Heimbach",
    "Hanselmann",
    "Hildebrand",
    "Kavanagh",
    "Lind",
    "Lukaschowsky",
    "McDonnell",
    "McGee",
    "Opnian",
    "Oppenheimer",
    "Riedemanas",
    "Zita",
    "Zitzmeinn",
    "BARHAM",
    "BARONE",
    "BARRON",
    "BERNA",
    "BIRNEY",
    "BIRNIE",
    "BOOROM",
    "BOREN",
)

SIMILAR_PAIRS: tuple[tuple[str, str], ...] = (
    ("Robert", "Rupert"),
    ("Robert", "Rubin"),
    ("Smith", "Smyth"),
    ("Smith", "Smythe"),
    ("Catherine", "Kathryn"),
    ("Thompson", "Thomas"),
    ("Michael", "Michelle"),
    ("Rodgers", "Rogers"),
    ("Ashcraft", "Ashcroft"),
    ("Knight", "Night"),
    ("Philip", "Phillips"),
    ("Green", "Greene"),
    ("Blackman", "Blackmon"),
    ("Robert", "Xavier"),
    ("Washington", "Lee"),
    ("Zhang", "Chang"),
)

BOUNDARY_STRINGS: tuple[str | None, ...] = (
    None,
    "",
    " ",
    "a",
    "A",
    "Z",
    "aa",
    "AEIOU",
    "BCDFG",
    "HW",
    "WH",
    "123",
    "Robert123",
    "O'Brien",
    "van der Berg",
    "Mac Donald",
    "abc def ghi",
    "washington",
    "wAsHiNgToN",
    "!@#$%",
    "a-b_c.d",
    "tab\there",
    "M\u00fcller",
    "Jos\u00e9",
    "\u00c9cole",
    "\u00d6zil",
    "A" * 60 + "B",
    "Supercalifragilisticexpialidocious",
)

INT_VALUES: tuple[int, ...] = (-1, 0, 1, 2, 3, 4, 6, 10, 100)

STATEFUL_WORDS: tuple[str, ...] = ("Washington", "Robert", "Supercalifragilisticexpialidocious", "Lee")


@dataclass
class Budget:
    per_method_single_string: int = 80
    literals_per_method: int = 30
    pairs_per_method: int = 30
    mismatch_per_method: int = 6
    mapping_per_ctor: int = 24


@dataclass
class Generator:
    cls: JavaClass
    all_classes: dict[str, JavaClass] = field(default_factory=dict)
    budget: Budget = field(default_factory=Budget)
    _n: int = 0

    # ------------------------------------------------------------------ helpers
    def _id(self) -> str:
        self._n += 1
        return f"{self.cls.name}-{self._n:03d}"

    def _new(self, method: str, setup: tuple[str, ...], call: str, label: str, tags: tuple[str, ...]) -> Scenario:
        return Scenario(self._id(), self.cls.name, method, setup, call, label, tags)

    def _subject(self) -> tuple[str, ...]:
        if self._has_noarg_ctor():
            return (f"{self.cls.name} subject = new {self.cls.name}();",)
        return ()

    def _has_noarg_ctor(self) -> bool:
        return not self.cls.constructors or any(c.arity == 0 for c in self.cls.constructors)

    def _receiver(self, m: Method) -> str:
        return self.cls.name if m.static else "subject"

    def _main_string_method(self) -> Method | None:
        # The "encode this string" method: one String parameter, returns String, not the Encoder-interface shim.
        cands = [m for m in self.cls.methods if m.arity == 1 and m.params[0].type == "String" and m.returns == "String"]
        cands.sort(key=lambda m: (m.name == "encode", m.name))
        return cands[0] if cands else None

    def _getter_for(self, setter: Method) -> Method | None:
        if not setter.name.startswith("set"):
            return None
        want = "get" + setter.name[3:]
        for m in self.cls.methods:
            if m.name == want and m.arity == 0:
                return m
        return None

    # --------------------------------------------------------------- strategies
    def string_values(self) -> list[tuple[str | None, str]]:
        """Ordered (value, tag) pairs for one String parameter."""
        out: list[tuple[str | None, str]] = []
        for w in CORPUS:
            out.append((w, "corpus"))
        for b in BOUNDARY_STRINGS:
            out.append((b, "boundary"))
        lits = 0
        for lit in self.cls.string_literals:
            if lits >= self.budget.literals_per_method:
                break
            if not lit.isalpha():
                continue
            out.append((lit, "literal"))
            lits += 1
            if len(lit) <= 4:
                out.append(("A" + lit + "A", "literal"))
                lits += 1
        seen: set[str | None] = set()
        dedup = []
        for v, t in out:
            if v in seen:
                continue
            seen.add(v)
            dedup.append((v, t))
        return dedup

    def single_string(self, m: Method) -> list[Scenario]:
        out = []
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        if not m.static and not setup:
            return out
        for v, tag in self.string_values()[: self.budget.per_method_single_string]:
            call = f"{recv}.{m.name}({jstr(v)})"
            out.append(self._new(m.name, setup, call, f"{m.name}({jstr(v)})", (tag,)))
        return out

    def string_pairs(self, m: Method) -> list[Scenario]:
        out = []
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        if not m.static and not setup:
            return out
        pairs: list[tuple[str | None, str | None, str]] = []
        for a, b in SIMILAR_PAIRS:
            pairs.append((a, b, "pair"))
        pairs += [
            ("Robert", "Robert", "pair"),
            ("", "", "boundary"),
            ("", "Robert", "boundary"),
            (None, "Robert", "boundary"),
            ("Robert", None, "boundary"),
            (None, None, "boundary"),
            ("a", "b", "boundary"),
            ("123", "456", "boundary"),
        ]
        for a, b, tag in pairs[: self.budget.pairs_per_method]:
            call = f"{recv}.{m.name}({jstr(a)}, {jstr(b)})"
            out.append(self._new(m.name, setup, call, f"{m.name}({jstr(a)}, {jstr(b)})", (tag,)))
        return out

    def string_bool(self, m: Method) -> list[Scenario]:
        out = []
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        for v, tag in self.string_values()[:24]:
            for flag in ("true", "false"):
                call = f"{recv}.{m.name}({jstr(v)}, {flag})"
                out.append(self._new(m.name, setup, call, f"{m.name}({jstr(v)}, {flag})", (tag,)))
        return out

    def string_string_bool(self, m: Method) -> list[Scenario]:
        out = []
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        for a, b in SIMILAR_PAIRS[:10]:
            for flag in ("true", "false"):
                call = f"{recv}.{m.name}({jstr(a)}, {jstr(b)}, {flag})"
                out.append(self._new(m.name, setup, call, f"{m.name}({jstr(a)}, {jstr(b)}, {flag})", ("pair",)))
        return out

    def object_mismatch(self, m: Method) -> list[Scenario]:
        out = []
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        values = [
            ('(Object) "Robert"', "string_as_object"),
            ("Integer.valueOf(42)", "integer"),
            ('new StringBuffer("Robert")', "stringbuffer"),
            ("(Object) null", "null"),
            ('(Object) ""', "empty_as_object"),
            ("new char[] {'a', 'b'}", "char_array"),
        ]
        for expr, name in values[: self.budget.mismatch_per_method]:
            call = f"{recv}.{m.name}({expr})"
            out.append(self._new(m.name, setup, call, f"{m.name}({name})", ("mismatch",)))
        return out

    def setter_sequences(self, m: Method) -> list[Scenario]:
        out = []
        if m.static or m.arity != 1 or m.params[0].type != "int":
            return out
        getter = self._getter_for(m)
        main = self._main_string_method()
        for n in INT_VALUES:
            base = self._subject()
            if getter:
                setup = base + (f"subject.{m.name}({n});",)
                out.append(
                    self._new(
                        m.name, setup, f"subject.{getter.name}()", f"{m.name}({n}) then {getter.name}()", ("stateful",)
                    )
                )
            if main:
                for w in STATEFUL_WORDS:
                    setup = base + (f"subject.{m.name}({n});",)
                    call = f"subject.{main.name}({jstr(w)})"
                    out.append(
                        self._new(m.name, setup, call, f"{m.name}({n}) then {main.name}({jstr(w)})", ("stateful",))
                    )
        return out

    def getter_default(self, m: Method) -> list[Scenario]:
        if m.static or m.arity != 0 or m.returns == "void" or m.name.startswith("set"):
            return []
        return [
            self._new(m.name, self._subject(), f"subject.{m.name}()", f"{m.name}() on a fresh instance", ("default",))
        ]

    def mapping_constructors(self) -> list[Scenario]:
        out = []
        main = self._main_string_method()
        if main is None:
            return out
        for c in self.cls.constructors:
            if c.arity != 1 or c.params[0].type != "char[]":
                continue
            consts = [k for k in self.cls.constants if k.type == "char[]"]
            tables: list[tuple[str, str]] = []
            for k in consts:
                tables.append((f"{self.cls.name}.{k.name}", f"default table {k.name}"))
            str_consts = [k for k in self.cls.constants if k.type == "String"]
            for k in str_consts:
                tables.append((f"{self.cls.name}.{k.name}.toCharArray()", f"default table via {k.name}"))
            tables += [
                ('"01230120022455012623010203".toCharArray()', "modified last code"),
                ('"99999999999999999999999999".toCharArray()', "all nines"),
                ('"0123".toCharArray()', "short table"),
                ("new char[0]", "empty table"),
                ("(char[]) null", "null table"),
            ]
            words = ("Robert", "Tymczak", "Zita", "", "a")
            n = 0
            for table_expr, table_label in tables:
                for w in words:
                    if n >= self.budget.mapping_per_ctor:
                        break
                    setup = (f"{self.cls.name} subject = new {self.cls.name}({table_expr});",)
                    call = f"subject.{main.name}({jstr(w)})"
                    out.append(
                        self._new(main.name, setup, call, f"{table_label}: {main.name}({jstr(w)})", ("mapping",))
                    )
                    n += 1
        return out

    def static_instances(self) -> list[Scenario]:
        out = []
        main = self._main_string_method()
        if main is None:
            return out
        for k in self.cls.constants:
            if k.type == self.cls.name:
                for w in ("Robert", "Tymczak", "Lee"):
                    call = f"{self.cls.name}.{k.name}.{main.name}({jstr(w)})"
                    out.append(self._new(main.name, (), call, f"{k.name}.{main.name}({jstr(w)})", ("static_instance",)))
        return out

    def encoder_param(self, m: Method) -> list[Scenario]:
        """SoundexUtils.difference(StringEncoder, String, String) and friends."""
        out = []
        if not (m.arity == 3 and m.params[0].type == "StringEncoder"):
            return out
        recv = self._receiver(m)
        setup = () if m.static else self._subject()
        encoders = [
            f"new {name}()"
            for name, jc in sorted(self.all_classes.items())
            if not jc.is_abstract and name != self.cls.name
        ]
        for enc in encoders + ["null"]:
            for a, b in SIMILAR_PAIRS[:6]:
                call = f"{recv}.{m.name}({enc}, {jstr(a)}, {jstr(b)})"
                out.append(self._new(m.name, setup, call, f"{m.name}({enc}, {jstr(a)}, {jstr(b)})", ("pair",)))
        return out

    # ------------------------------------------------------------------ driver
    def generate(self) -> list[Scenario]:
        out: list[Scenario] = []
        for m in self.cls.methods:
            types = [p.type for p in m.params]
            if types == ["String"] and m.returns != "void":
                out += self.single_string(m)
            elif types == ["String", "String"]:
                out += self.string_pairs(m)
            elif types == ["String", "boolean"]:
                out += self.string_bool(m)
            elif types == ["String", "String", "boolean"]:
                out += self.string_string_bool(m)
            elif types == ["Object"]:
                out += self.object_mismatch(m)
            elif types == ["int"] and m.returns == "void":
                out += self.setter_sequences(m)
            elif not types:
                out += self.getter_default(m)
            elif types and types[0] == "StringEncoder":
                out += self.encoder_param(m)
        out += self.mapping_constructors()
        out += self.static_instances()
        return out


def generate_all(classes: list[JavaClass], budget: Budget | None = None) -> list[Scenario]:
    by_name = {c.name: c for c in classes}
    out: list[Scenario] = []
    for c in classes:
        out += Generator(c, by_name, budget or Budget()).generate()
    return out
