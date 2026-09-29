# Write-up

The brief was: read a legacy module, generate characterization tests, measure coverage before and
after, and write down where the generated tests were wrong.

## Module

Apache Commons Codec 1.3 `org.apache.commons.codec.language` (Soundex, RefinedSoundex, Metaphone,
DoubleMetaphone) plus the three interfaces it needs. 2004 source, pre-generics, vendored unchanged.
The maintainers' JUnit 3 suite for that package is the comparison. The 1.5 sources for the same
package are the drift target.

COBOL was the other option in the brief. This package is the better hiring artifact: a real
open-source module, a real maintainer suite, and a real later release that hid a public constant.

## Pipeline

1. Regex reader: public constructors, methods, constants, string and int literals. Inner classes
   skipped so tests read like a caller.
2. Deterministic input strategies (corpus, boundary, literal, stateful, mapping, pair, mismatch).
3. A generated Java probe runs every call twice and prints type + value.
4. Review emits a test only when both runs agree and the type is assertable. Exception tests use
   `assertThrows(Class, ...)` and never the message.
5. JaCoCo on the generated suite, on the empty suite, and on the maintainers' suite.
6. The generated tests compiled against the 1.5 sources.

Pynguin is a Python test generator; this module is Java, so the observation-then-freeze idea is
implemented directly. PIT is wired in the POM (`uv run ltw measure --pit`) and left off the CI
gate: 1,020 tests times the DoubleMetaphone mutation set is a long job, and the 1.5 compile errors
already prove the suite notices change.

## Numbers (docs/latest-run.json)

| Suite | Tests | Line coverage |
|---|---:|---:|
| empty | 0 | n/a |
| generated | 1,020 / 0 fail | 84% (607 / 721) |
| maintainers | 74 / 0 fail | 92% (665 / 721) |
| generated on 1.5 | compile, 20 errors | n/a |

Soundex is fully covered by both. The gap is DoubleMetaphone branches the name corpus does not hit.

## Where the generated tests were wrong

1. **Null vs empty.** First Surefire run: 37 failures, all `expected: <null> but was: <>`. The
   probe used an empty TSV field for both a null return and an empty string. Caught by running the
   emitted tests, not by inspection.
2. **Checked exceptions.** `encode(Object) throws EncoderException` does not compile inside a JUnit
   method that does not declare throws. Caught by `testCompile`.
3. **Exception messages.** Deliberately never asserted. If they had been, the 1.5 message edits
   would have been 20 more false failures on top of the real API hide.
4. **`setMaxCodeLen(-1)`.** Throws `NegativeArraySizeException`. First review pass held it. That
   was the wrong call: it is a caller-visible footgun. The type is now pinned.
5. **1.5 `US_ENGLISH_MAPPING`.** Twenty generated tests name the constant. 1.5 made it private.
   The suite fails to compile. That is a correct characterization of 1.3 and a correct detection
   of an API change.

## What I would not ship

I would not replace the maintainers' suite. I would commit the generated suite next to it, keep
the 1.5 (or `main`) compile in CI, and refuse any generator change that drops emitted count or
line coverage below `evals/gate.json`.
