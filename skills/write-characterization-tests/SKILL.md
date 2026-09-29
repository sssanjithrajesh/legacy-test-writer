---
name: write-characterization-tests
description: Generate characterization tests for the vendored Commons Codec 1.3 language package, measure coverage against the maintainers' suite, and hold non-deterministic cases for review.
---

# Write characterization tests

Run from the `legacy-test-writer` repo root.

```
uv sync --extra dev
uv run ltw all            # generate, measure generated + maintainers + 1.5 drift, write docs/
uv run ltw-eval --gate    # fail if coverage or emission dropped
uv run pytest             # parser, strategies, review rules
```

Do not hand-edit files under `legacy/src/test/java`. They are emitted by `ltw generate`.
Do not assert exception messages; `review.py` already refuses that.
The LLM extra (`ltw generate --llm`) only proposes inputs. The probe still observes the real class.
