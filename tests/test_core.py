"""Parser, input strategies, review rules, emitter. No JDK required."""

from __future__ import annotations

from pathlib import Path

from ltw.emit import render_class
from ltw.inputs import CORPUS, generate_all
from ltw.javaparse import parse_java, parse_package
from ltw.review import decide, review
from ltw.scenario import Observation, Observed, Scenario, jstr
from ltw.toolchain import LEGACY, PACKAGE


def _soundex() -> Path:
    return LEGACY / "src" / "main" / "java" / "org" / "apache" / "commons" / "codec" / "language" / "Soundex.java"


def test_parse_soundex_public_surface():
    jc = parse_java(_soundex())
    assert jc.name == "Soundex" and jc.package.endswith("language")
    names = {m.name for m in jc.methods}
    assert {"encode", "soundex", "difference", "setMaxLength", "getMaxLength"} <= names
    assert any(c.arity == 0 for c in jc.constructors)
    assert any(c.arity == 1 and c.params[0].type == "char[]" for c in jc.constructors)
    assert "US_ENGLISH_MAPPING_STRING" in {k.name for k in jc.constants}
    assert "01230120022455012623010202" in jc.string_literals


def test_inner_classes_are_skipped():
    classes = parse_package(LEGACY / "src" / "main" / "java", PACKAGE)
    names = {c.name for c in classes}
    assert "DoubleMetaphone" in names
    assert not any("DoubleMetaphoneResult" in n for n in names)


def test_jstr_is_ascii_java():
    assert jstr(None) == "null"
    assert jstr('a"b') == '"a\\"b"'
    rendered = jstr("Muller").replace("Muller", "x")  # sanity
    umlaut = jstr("M\u00fcller")
    assert "\\u00fc" in umlaut
    assert all(ord(c) < 128 for c in umlaut)
    assert rendered.startswith('"')


def test_generate_is_deterministic_and_covers_strategies():
    classes = [c for c in parse_package(LEGACY / "src" / "main" / "java", PACKAGE) if c.is_public]
    a = generate_all(classes)
    b = generate_all(classes)
    assert [s.id for s in a] == [s.id for s in b]
    assert [s.call for s in a] == [s.call for s in b]
    assert len(a) > 200
    tags = {t for s in a for t in s.tags}
    assert {"corpus", "boundary", "pair", "mismatch", "stateful"} <= tags
    assert any("Robert" in s.call for s in a)
    assert any("null" in s.call for s in a)
    soundex = [s for s in a if s.cls == "Soundex"]
    assert any("setMaxLength(0)" in s.label for s in soundex)


def test_review_holds_nondeterministic_and_emits_ok():
    sc = Scenario(
        "Soundex-001",
        "Soundex",
        "encode",
        ("Soundex subject = new Soundex();",),
        'subject.encode("Robert")',
        "encode Robert",
    )
    ok = Observation("Soundex-001", "OK", "java.lang.String", "R163")
    bad = Observation("Soundex-001", "OK", "java.lang.String", "R000")
    assert decide(Observed(sc, ok, ok)).action == "emit"
    assert decide(Observed(sc, ok, bad)).action == "hold"
    held = decide(
        Observed(sc, Observation("Soundex-001", "OK", "char[]", "ab"), Observation("Soundex-001", "OK", "char[]", "ab"))
    )
    assert held.action == "hold" and held.reason == "unassertable_type"
    ex = Observation("Soundex-002", "EX", "org.apache.commons.codec.EncoderException", "no")
    sc2 = Scenario("Soundex-002", "Soundex", "encode", (), "subject.encode(Integer.valueOf(42))", "mismatch")
    v = decide(Observed(sc2, ex, ex))
    assert v.action == "emit" and v.reason == "expected_exception"


def test_emitter_never_asserts_exception_message():
    sc = Scenario(
        "Soundex-002",
        "Soundex",
        "encode",
        ("Soundex subject = new Soundex();",),
        "subject.encode(Integer.valueOf(42))",
        "integer",
    )
    ex = Observation("Soundex-002", "EX", "org.apache.commons.codec.EncoderException", "Parameter supplied")
    src = render_class("Soundex", review([Observed(sc, ex, ex)]))
    assert "assertThrows(org.apache.commons.codec.EncoderException.class" in src
    assert "Parameter supplied" not in src
    assert "Characterization tests generated" in src


def test_emitter_pins_string_result():
    sc = Scenario(
        "Soundex-001",
        "Soundex",
        "encode",
        ("Soundex subject = new Soundex();",),
        'subject.encode("Robert")',
        'encode("Robert")',
    )
    ok = Observation("Soundex-001", "OK", "java.lang.String", "R163")
    src = render_class("Soundex", review([Observed(sc, ok, ok)]))
    assert 'assertEquals("R163", subject.encode("Robert"))' in src
    assert CORPUS[0] == "Robert"
