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
