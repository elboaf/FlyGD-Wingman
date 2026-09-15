# Fleet telemetry redesign — discovery evidence

Recorded 2026-09-15. No application source changed during these probes. This is
supporting evidence for the [design](fleet-telemetry-v2-design.md), not a
claim that the redesign is implemented or that every reported gap has one cause.

## Live observations

Read-only inspection of the local installed Wingman and authGD production state
established:

- Sharing-enabled clients were actively polling.
- A later fresh observation confirmed an active, continuously verified boss source,
  with current linked characters from more than one sharing-enabled account.
- Outgoing DPS did reach the relay. The initial empty snapshots were insufficient
  evidence to conclude that setup or transmission was broken.
- A trace at 18:44:16–18:44:31 UTC contained an 11-DPS row, an absent row, the same
  11-DPS row again, another gap, and later positive DPS. At the first gap the prior
  row's hard-expiry deadline had not elapsed, source proof remained fresh, and a
  real outgoing damage event was still inside the ten-second DPS window.
- A subsequent trace recorded sustained zero-DPS EWAR publications
  while the source continued refreshing. No packet payload or cached client
  eligibility was captured at the earlier gaps.

Production database queries used BEGIN READ ONLY and bounded statement timeouts.
No pairing, participation, source, database, configuration or deployment mutation
was performed. No raw session values, private keys or production credentials are
included in these documents or fixtures.

## Deterministic worker probe

The production worker and scheduler can reproduce premature withdrawal without
any local inactivity. The existing virtual owner harness is reused; only the
fake relay's eligibility deadline is changed to represent independently renewed
server proof rather than a new ten-second grant on every eligibility GET.

Run from the Wingman checkout with the existing dev environment. During discovery,
`python` below was `/mnt/c/dev/flygd-wingman/.venv/bin/python`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python - <<'PY'
import math
from dataclasses import replace
from datetime import timedelta

from test_fleetsharing_cadence import run_owner
from test_fleetsharing_worker import NOW, _date, _snapshot

for latency in (0.08, 0.2, 0.4, 0.6):
    for changing in (False, True):
        def configure(worker, client, timeline):
            original = client.fetch_eligibility

            def eligibility(**args):
                started = timeline.now
                result = original(**args)
                expiry = NOW + timedelta(
                    seconds=math.floor((started - 1000 - 2) / 6) * 6 + 2 + 10
                )
                return replace(
                    result,
                    characters=tuple(
                        replace(entry, expires_at=_date(expiry))
                        for entry in result.characters
                    ),
                )

            client.fetch_eligibility = eligibility
            if changing:
                for second in range(60):
                    timeline.at(
                        1000 + second,
                        lambda n=second: worker.submit(_snapshot(10 + n % 5)),
                    )

        client, _, _, _ = run_owner(
            publisher=True,
            watch=True,
            latency=latency,
            duration=60,
            configure=configure,
        )
        empty = [round(t - 1000, 2) for t, rows in client.published if not rows]
        times = [t for op, t, _ in client.calls if op == 'fetch_eligibility']
        gap = max((b - a for a, b in zip(times, times[1:])), default=0)
        print(latency, changing, empty, round(gap, 2))
PY
```

Observed output:

```text
0.08 False [] 2.32
0.08 True  [] 2.32
0.2  False [] 2.8
0.2  True  [] 3.0
0.4  False [] 3.6
0.4  True  [] 3.7
0.6  False [12, 24.6, 36.0, 48.1] 12.6
0.6  True  [30.0, 54.0] 4.8
```

`False` uses the harness's constant 42-DPS publisher. `True` uses varying positive
DPS. The fourth column is the maximum interval between eligibility requests, not
the configured two-second interval after completion. All scenarios keep a current
local telemetry feed and a source whose proof is renewed independently.

This is a diagnosis probe, not yet an asserted regression. Implementation must
turn it into a focused failing test, add deadline/partial-expiry/Off coverage,
and verify the final behavior against the original owner loop.

## Baseline verification in the isolated design worktree

```bash
PYTHONDONTWRITEBYTECODE=1 /mnt/c/dev/flygd-wingman/.venv/bin/python \
  -m pytest -p no:cacheprovider \
  tests/test_fleetsharing_cadence.py \
  tests/test_fleetsharing_remote_worker.py \
  tests/test_fleetsharing_projection.py \
  tests/test_remote_fleet_store.py \
  tests/test_fleet_metrics.py \
  tests/test_api_remote_fleet.py -q
```

Result: **272 passed in 17.20s**.

These tests are the unchanged baseline. They do not validate incoming-DPS sharing,
new aggressor metadata, persistent automatic mode, new schemas, or the redesigned
Windows UI. No full-suite, migration, deployment or two-PC acceptance claim is made.

## Post-fix verification — independent client timing fix

Recorded 2026-09-15 in the linked worktree
`/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-v2`. The discovery sections
above are preserved as historical evidence, not relabelled as post-fix results.

Verified implementation: **`a34541ac8c8f579efc8299049fd0a2b9e1c54f15`**
(`fix: prioritize due fleet eligibility near expiry`), including Task 1 commit
`b386a59eaa25a10c9ed88a69e7fa43c52484a7f8`. Implementation base:
`73cdeff495a2f660c8ec9a07c4a2cbb1ef59a552`.

The production diff is confined to `wingman/fleetsharing/worker.py`; tests were
added in `test_fleetsharing_remote_worker.py`, `test_fleetsharing_scheduling.py`
and `test_fleetsharing_cadence.py`. Existing test assertions were not weakened.
This checkpoint changes no v1 transport, public bridge, persisted data, scheduler
API, owner/thread, authorization rule or Alert firing/hold behavior.

- Projection considers observed eligible IDs before checking the expiry of actual
  active candidates. If any candidate's cached permission has expired, the whole
  atomic replacement is suspended (`None`), not reduced to a subset or an empty
  replacement. Expired quiet members do not block fresh active members. Genuine
  inactivity and authoritative non-ready/generation mismatch still yield `()`;
  missing authority and stale local telemetry retain their earlier guards.
- A ready cached eligibility entry within three seconds of expiry promotes
  eligibility work to priority 1. The existing two-second completion-based poll
  interval, due time, per-key retry and shared read cadence remain intact.
  Priority-0 Off/withdrawal/Stop still wins. No expired permission is renewed by
  this scheduling decision; the relay's proof and ordinary expiry remain the
  authority over remote visibility.

Tasks 1–2 were independently approved. The controller's completed
`polish-core --fix` pass against the full range reported no findings and no edits
(`.superpowers/sdd/fleet-telemetry-timing-plan/polish-report.md`). Task 3 did not
repeat that review or modify source/tests.

### Recorded implementation RED/GREEN comparisons

These are the actual historical runs preserved in this plan's local
`task-1-report.md` and `task-2-report.md`, not new rollback runs in Task 3:

| Command | Recorded result and discriminating assertion |
| --- | --- |
| `uv run --no-sync python -m pytest tests/test_fleetsharing_remote_worker.py -q` before Task 1 production edit | **2 failed, 16 passed in 3.27s**. One expired active member returned Bob's partial tuple instead of `None`; two expired active members returned `()` instead of `None`. |
| `uv run --no-sync python -m pytest tests/test_fleetsharing_remote_worker.py tests/test_fleetsharing_worker.py -q` after Task 1 | **107 passed in 16.53s**; final repeat **107 passed in 14.85s**. |
| `uv run --no-sync python -m pytest tests/test_fleetsharing_scheduling.py -q` before Task 2 production edit | **2 failed, 6 passed in 3.05s**. Remaining lifetimes 3.0s and 0.0s had priority 2 rather than 1; 3.01s and the retry/cadence guard already passed. |
| Same scheduling command after Task 2 production edit | **8 passed in 2.12s**. |
| `uv run --no-sync python -m pytest 'tests/test_fleetsharing_cadence.py::test_renewed_source_preserves_active_publications[0.6-False]' -q` with only Task 2 production edits temporarily removed | **1 failed in 3.06s**: maximum publication gap **4.500000000000114s**, failing `< 3.0`. A preceding `git diff --exit-code b386a59eaa25a10c9ed88a69e7fa43c52484a7f8 -- wingman/fleetsharing/worker.py` confirmed Task 1 remained intact. The no-empty assertion passed. |
| `uv run --no-sync python -m pytest tests/test_fleetsharing_scheduling.py tests/test_fleetsharing_cadence.py tests/test_fleetsharing_remote_worker.py -q` after restoring Task 2 | **92 passed in 8.50s**; final lint/format-checked repeat **92 passed in 8.43s**. |

### Fresh local release-boundary gates

Environment: Linux x86-64 / WSL2 (`6.6.87.2-microsoft-standard-WSL2`), Python
**3.11.15**, Node **v26.5.0**. The locked dev environment and release codec were
already installed in this checkout; Task 3 reconfirmed `codec.codec_available()`
was **True** before the full suite. The executable resolved in this worktree's
`packaging/bin/wingman-settings-codec`, not another checkout or a debug fallback.

Commands below ran from the worktree at the implementation SHA above. Output was
captured with `2>&1 | tee` under `set -o pipefail`; the test commands include their
actual fresh `/tmp` basetemps and JUnit destinations. All commands exited **0**.

```bash
node --version
uv run --no-sync python -c "import platform; from pathlib import Path; from wingman.evesettings import codec; print(platform.platform()); print(platform.python_version()); print('codec_available=', codec.codec_available()); assert codec.codec_available(), 'Native integration tests require the built codec'; print('codec=', Path('packaging/bin/wingman-settings-codec').resolve())"

uv run --no-sync python -m pytest tests/test_fleetsharing_*.py tests/test_api_fleetsharing.py tests/test_api_remote_fleet.py tests/test_fleet_runtime_integration.py tests/test_remote_fleet_store.py -q -rs --basetemp=/tmp/fleet-timing-focused-a34541ac-task3-2039 --junitxml=.superpowers/sdd/fleet-telemetry-timing-plan/task-3-focused.xml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/fleet-timing-full-a34541ac-task3-2041 --junitxml=.superpowers/sdd/fleet-telemetry-timing-plan/task-3-full.xml
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
node scripts/js_smoke.js
```

| Fresh gate | Actual result |
| --- | --- |
| Focused sharing, API, runtime and remote-store suites | **1053 passed in 88.36s**, no skips. |
| Full Ruff lint | **All checks passed!** |
| Full Ruff format check | **451 files already formatted**. |
| Full pytest `tests/ -q -rs` | **13026 passed, 13 skipped in 412.28s**. One uninterrupted run; no failure, timeout or restart. |
| Independent Cargo regression | **1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out** (`large_float_survives_the_json_and_marshal_round_trip_exactly`). |
| Standalone Node page smoke | **PASS every page module loaded** for `index.html`, `fleetbar.html`, `sigbar.html`. |

JUnit inspection confirmed 13,039 full-suite cases, zero errors/failures, and all
13 skip identities. It also confirmed no skips/failures in the 72 codec cases,
12 setup-integration cases (including the mandatory real release-codec path),
7 JS smoke cases and 123 bridge-contract cases. These are Linux executable and
synthetic-fixture checks, not Windows UI rendering or live EVE acceptance.

Every skip was inspected against its platform guard. The complete `-rs` output
was:

```text
SKIPPED [1] tests/test_evesettings_profilecopy.py:279: requires a real Windows junction
SKIPPED [1] tests/test_evesettings_profilecopy.py:318: requires a real Windows junction
SKIPPED [1] tests/test_evesettings_profilecopy.py:650: requires a real Windows junction
SKIPPED [1] tests/test_eveskills_dpapi.py:45: requires real DPAPI
SKIPPED [1] tests/test_eveskills_dpapi.py:52: requires real WinDLL
SKIPPED [1] tests/test_preview_host.py:1881: needs a real message pump and window station
SKIPPED [1] tests/test_preview_win32.py:163: binds user32/gdi32/dwmapi
SKIPPED [1] tests/test_preview_win32.py:178: binds user32/gdi32/dwmapi
SKIPPED [1] tests/test_preview_win32.py:202: binds user32/gdi32/dwmapi
SKIPPED [1] tests/test_tray.py:244: pystray Windows backend
SKIPPED [2] tests/test_ui_setup_profile.py:458: requires real Windows junction
SKIPPED [1] tests/test_wanderer_integration.py:522: real Windows user-bound DPAPI required
```

The two setup-profile skips are `core_char_31.dat` and `prefs.ini` junction
parameters. All 13 are expected Windows-only coverage gaps on Linux; **none is a
missing Node or settings-codec skip**.

### Post-fix continuity and explicit withdrawal evidence

The new committed tests passed in both the focused and full runs. A supplemental
local probe reused the committed `run_owner` and `renewed_source_proof` helpers
without editing application code, tests, authority or cadence:

```bash
PYTHONPATH=tests uv run --no-sync python .superpowers/sdd/fleet-telemetry-timing-plan/task-3-probe.py
```

Exit **0**; its unrounded publication-gap assertions retain `< 3.0s` for the
latency/load matrix and `< 10.0s` for phase/skew. Each run lasts 60 virtual seconds,
with source watch and current local telemetry. Expiry follows independently
renewed server proof, sampled before full response latency. Measurements below
are seconds rounded to three decimal places; eligibility request-start gaps are
not the two-second completion-based polling interval.

| Latency | Positive DPS | Publications | Empty replacements | Maximum publication gap | Maximum eligibility request gap |
| --- | --- | --- | --- | --- | --- |
| 0.08 | Constant 42 | 49 | 0 | 1.16 | 2.32 |
| 0.08 | Changing | 82 | 0 | 1.00 | 2.32 |
| 0.20 | Constant 42 | 40 | 0 | 1.40 | 2.80 |
| 0.20 | Changing | 74 | 0 | 0.90 | 3.00 |
| 0.40 | Constant 42 | 31 | 0 | 1.80 | 3.60 |
| 0.40 | Changing | 60 | 0 | 1.00 | 3.70 |
| 0.60 | Constant 42 | 34 | 0 | 1.60 | 6.40 |
| 0.60 | Changing | 45 | 0 | 1.20 | 4.80 |

At 600ms, discovery recorded four empty constant-DPS replacements and two empty
changing-DPS replacements. Both now have zero. The constant-DPS maximum eligibility
request gap changes from discovery's 12.6s to 6.4s; the changing-DPS gap remains
4.8s. The separate Task1-only RED demonstrated a 4.5s publication gap even with no
empty replacements; both fixes together reduce that case to 1.6s. This comparison
does not assert discovery captured the packets at every live gap.

The phase/skew matrix covers **all 12 combinations** of source renewal periods
5/6s, phases 0/2/4s and worker clock skew -0.5/+0.5s at 600ms latency. Every case
had 34 nonempty publications, no empty replacement and a 1.6s maximum publication
gap. Eligibility request gaps were 6.4s except period 6 / phase 0 / skew -0.5,
which was 7.6s. These bounded results do not establish arbitrary clock-error or
outage tolerance.

Explicit withdrawal and lifecycle assertions remain intact and passed:

- **Authoritative source loss:** the helper returns `not_verified` for eligibility
  requests started at or after virtual +30s. The probe observed exactly **one**
  empty replacement at **+34.0s**, and **zero** subsequent nonempty publications,
  despite the continuing positive local feed. The committed test asserts one
  withdrawal and no subsequent positive publication; it does not promise an
  immediate network response to source loss.
- **Off under busy metadata:** the existing cadence test asserts only
  `fetch_device`, `publish_snapshot`, `set_participation` after Off, in that order;
  the consent-write request starts within **1.5s**, withdrawal completes, consent
  ends disabled, and subsequent key access/periodic activity stays inert.
  Immediate eligibility/remote clearing and
  priority-0 precedence over urgent eligibility also pass.
- **True inactivity / partial expiry:** exact-result tests preserve `()` for
  genuine inactivity and authoritative not-verified, `None` for one/all expired
  active candidates, and Bob's fresh row when only quiet Alice has expired.
- **Retry, stale input and ownership:** retained tests cover lost Start/Stop and
  snapshot responses, per-key and 429 backoff, session/identity replacement,
  held-read Off/Stop/restart fences, real-thread latest-mailbox coalescing and
  submit-flood retry floors. Stale mailboxes stop further attempts without a
  fabricated withdrawal; delayed remote responses remain stale or expired rather
  than receiving a new freshness deadline. The real-owner harness also asserts
  durable attempt revisions and independent completion-based read/publication
  buckets with zero cadence refusals.

### Evidence locations and remaining acceptance

Local ignored artifacts are retained under
`.superpowers/sdd/fleet-telemetry-timing-plan/`: `task-3-prerequisites.log`,
`task-3-focused.log`, `task-3-focused.xml`, `task-3-ruff-check.log`,
`task-3-ruff-format.log`, `task-3-full.log`, `task-3-full.xml`, `task-3-cargo.log`,
`task-3-js-smoke.log`, `task-3-junit-inspection.log`, `task-3-probe.py`,
`task-3-probe.json` and the detailed `task-3-report.md`. They supplement this
committed record; historical discovery and task reports were not overwritten.

**Local automated timing-fix gates pass; this is not a release or live acceptance
sign-off.** Hosted Ubuntu/Windows CI, the 13 native Windows checks, frozen
Windows/WebView2 UI smoke and an actual two-PC/relay continuity plus Off/source-loss
exercise remain unperformed here. Fake latency and bounded clock-skew tests do
not replace those checks. No installed app, real EVE/profile, production service,
authGD, credential or deployment mutation was used in Task 3; no version bump,
release, push or merge was performed.

This is an independently releasable **client timing fix only**. Incoming-DPS
sharing, activity semantics, aggressor metadata, automatic/persistent setup and
versioned shared-combat protocol/UI redesign remain outside this implementation.
