# Attribution

## Legacy module under test

`legacy/src/main/java` is the `org.apache.commons.codec.language` package of
[Apache Commons Codec 1.3](https://github.com/apache/commons-codec) (2004-2005), plus the three
interfaces it needs (`Encoder`, `StringEncoder`, `EncoderException`). Copied unchanged.
Copyright The Apache Software Foundation. Licensed under the Apache License, Version 2.0.
See `legacy/NOTICE.txt`.

`legacy-next/src/main/java` is the same package from Commons Codec 1.5 (2007), used only to
show which generated tests fail when the implementation moves. Same license.

`evals/reference/java` is the maintainers' original JUnit 3 suite for that package (Codec 1.3),
used as the comparison baseline. Same license.

## Everything else

Input strategies, probe, review rules, JUnit emitter, evals, and this repository's own tests
are original (MIT).
