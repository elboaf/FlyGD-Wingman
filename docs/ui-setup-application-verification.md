# Pure setup application checkpoint — Task 4a

**Verified code: `c282dd5`. Task 4a is complete and independently reviewed; the
whole of Task 4 and the user-facing feature are not complete.** This follows the
[case-based reassessment](overview-layout-sharing-reassessment.md), not a new
product scope or permission to write unproved settings.

## What changed

`f97a65a` added `wingman/evesettings/setup_documents.py` and its behavioral tests.
`c282dd5` corrected two Important task-review findings. No existing parser,
model, controller, GUI, dependency or filesystem writer was changed.

`apply_setup(account, character, parsed, *, keep_ship_labels, now)` returns new
recipient documents. It does not read/write files, run a codec process, publish
a profile or expose an application endpoint. The input documents and parsed
model remain unchanged on both success and refusal; CRC flags are retained.

## How it works

The operation revalidates incoming semantic data, deep-copies recipient
documents, checks the specific topology/reference/stack dependencies, then
constructs only owned settings in known physical representations. It preserves
recipient identity, default metadata, history, unrelated definitions and windows.

Each tab retains its own overview/bracket assignments. The adapter does not treat
`activeOverviewPreset` as a single global filter or overwrite it with an arbitrary
imported choice. Existing valid named references and unaffected selectors remain
recipient state; ambiguous invalidation refuses.

Supported noncolliding definitions can be added. Identical collisions preserve
the existing physical record; differing unclassified collisions refuse. Only
imported-name unsaved overrides are removed. Preserved nonimported definitions
remain opaque even when old tabs reference them.

Geometry retains all six integers without fitting. The seven state maps and
other supported layout values distinguish absence from false. Full missing
owned overrides clear narrowly; native omissions retain recipient values.
Ambiguous native labels require explicit retention, preserving the complete
recipient stamped label sequence. Native input never acquires source layout.

## Case limits remain explicit

This slice refuses, rather than claims to implement:

- differing exact-name collisions without established custom/protected status;
- new unclassified reserved-looking definition names;
- unsupported/dangling named references and ambiguous selector invalidation;
- affected stack associations and surplus active overview retirement;
- missing or unsupported recipient topology/physical variants, including the
  still-unproved special target-lock encoding;
- unsupported legacy non-null dependency records.

The supported synthetic recipient remains different from the sender but has
explicit understood topology and no ambiguous selectors. The original richer
four-group recipient remains a retirement-refusal case. **These test scenarios
are not proof that a fresh real EVE profile is already supported.**

Full exporter/classification, eligible differing-name replacement, selector
repair and surplus retirement remain Task 4b requirements. Staging, confirmed
pair/controller integration, GUI and real-EVE acceptance remain later work.
No incomplete exporter/classifier stub or production caller was added.

## Review corrections

1. Topology validation previously decoded old referenced definition bodies through
   the portable schema unnecessarily. It now checks their names/references and
   uses validation-only name witnesses; real bodies are decoded only where a
   collision or another actual dependency requires it. Witnesses are never
   returned or written as definitions.
2. Ordinary dictionary equality silently skipped order-only tab replacement.
   Only the outer `tabsettings_new` map now compares its key sequence as well as
   values. Nested/opaque maps retain ordinary equality and existing stamps when
   unchanged. No physical IDs or group members are remapped.

Synthetic native experiments established that the existing codec preserves map
encounter order with both CRC variants, including nonnumeric encounter order.
Regression tests inspect actual decoded key/name order rather than sorted JSON
or ordinary dictionary equality. This verifies transport fidelity, **not which
ordering EVE's UI treats as authoritative**.

The two findings had observed RED/GREEN regressions and a scoped independent
re-review found both addressed with no new breakage. Task-local safe polish and
formatting edits were inspected before fresh verification.

## Verification actually performed

Final adapter run: **81 passed**, including four real native transport cases.
Focused model/parser/formation/codec regressions: **1,342 passed, one skipped**.
The implementer ran the full suite, and the parent independently reran it at the
same final code SHA:

```bash
uv run --no-sync python - <<'PY'
from pathlib import Path
from tests import test_evesettings_codec as seam
import pytest
seam.CODEC = Path('../../packaging/settings-codec/target/debug/wingman-settings-codec').resolve()
assert seam.CODEC.is_file()
raise SystemExit(pytest.main(['tests/', '-q', '-rs', '--basetemp=/tmp/wingman-adapter-checkpoint-full']))
PY
# 7,654 passed, 37 skipped in 258.02s

uv run --no-sync ruff check .
# All checks passed
uv run --no-sync ruff format --check .
# 309 files already formatted
git diff 92f9b12..HEAD --check
# Passed
```

Run from the linked worktree. The executed command used the equivalent absolute
path to the existing native binary; the relative spelling above avoids embedding
a machine-specific checkout path. No binary was built, installed or copied.

The seam activates adapter/schema native tests only. The 37 remaining skips are
28 other unavailable-binary checks and nine Windows-only checks; they are not
passes. No private captures, live EVE actions, real-profile writes, browser/UI
checks or frozen-build acceptance occurred during this coding slice.

## Reviewer focus and knowledge check

Keep the supported-case contract distinct from completed product behavior.
Review preservation versus necessary validation, reference closure, stack scope,
full-clear/native-retain semantics and exact physical output without inferring
unproved game behavior from codec round-trips.

1. When does an existing definition need body validation rather than name existence?
2. Why must identical collisions preserve their physical recipient records?
3. Which topology changes still require an explicit refusal in this slice?
4. Why is outer tab-map ordering checked separately from nested/opaque maps?
5. Which claims require actual EVE acceptance rather than native codec verification?
