# Fleet Telemetry Timing Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop cached-eligibility expiry from withdrawing ongoing combat telemetry, while servicing eligibility before ordinary reads can starve it.

**Architecture:** Keep the existing serialized FleetSharingWorker and Scheduler. Distinguish an uncertain replacement from a genuine empty publication, and use existing priority/cadence machinery to promote due eligibility refreshes near expiry. No relay, protocol, database, consent, display or collection changes are part of this first delivery.

**Tech Stack:** Python, pytest, the existing virtual owner-loop harness; no new dependencies.

**Spec:** [Fleet telemetry redesign](fleet-telemetry-v2-design.md), §1. [Discovery evidence](fleet-telemetry-v2-evidence.md).

## Global Constraints

- All signed requests share a revision and must remain serialized.
- An expired cached observation alone must not be treated as a fresh assertion of inactivity.
- Suspend uncertain replacements while reacquiring authority and let the relay's current proof and normal expiry enforce visibility.
- Do not republish using expired permission, prolong freshness, or reinterpret an authoritative empty/refused response as permission to keep sending.
- Preserve independent publication cadence and the existing critical Off/withdrawal priority.
- Do not change Alert firing/hold behavior as a side effect of changing the Fleet combat model.
- No production data, credentials, deployment, or mutation is needed to execute this plan.
- Use a linked worktree before writes. Do not amend the already-reviewed design commits.

This plan intentionally implements only timing reliability. Incoming DPS, NEUT/
aggressor sharing, thirty-second local/remote activity and automatic setup remain
in the approved master design and will receive separate contract/data and setup
plans. This patch must remain independently releasable on the existing protocol.

## Review-risk decisions

1. **An atomic replacement cannot silently lose an active expired-cache member.**
   Build candidate rows from the currently observed eligible IDs, then suspend the
   whole replacement if any candidate's cached permission has expired. Do not
   publish the still-fresh subset, which would delete the other active rows.
2. **Genuine inactivity is not blocked by an irrelevant expired entry.** If an
   expired character has no publishable local activity, it need not suspend an
   otherwise justified replacement. A genuinely empty candidate set remains `()`.
3. **Authoritative loss remains distinct.** `not_verified`, changed participation
   generation and missing participation retain their existing no-permission
   behavior. Missing catalogue/eligibility or a stale mailbox remain `None`.
4. **Refresh urgency does not create a second request lane or bypass backoff.**
   Keep the existing two-second eligibility due time. Promote a due refresh to
   priority 1 when any ready cached entry has at most three seconds left. Explicit
   Off/withdrawal/Stop retain priority 0; Scheduler still enforces bucket and
   retry deadlines before considering priority.
5. **Three seconds is a scheduling reserve, not extended authority.** Name the
   existing two-second poll interval and derive the reserve as that interval plus
   two existing 500 ms signed-cadence slots. No expiry timestamp or server TTL is
   increased. A request already in flight cannot be preempted; genuinely degraded
   networks may still stale/expire naturally, never via a fabricated quiet row.

The in-memory feasibility exercise used the unchanged real owner with wrappers
representing decisions 1 and 4. With 600 ms responses and independently renewed
six-second server proof, constant DPS went from four withdrawals per minute to
none; its maximum nonempty-publication interval fell from 6.1 to 1.6 seconds.
These are planning-probe results, not a claim that the checked-in worker is fixed.
Executors must establish red and green with the actual file changes below.

## Files and ownership

| File | Responsibility in this plan |
| --- | --- |
| `wingman/fleetsharing/worker.py` | Candidate validation and urgency of existing eligibility work |
| `wingman/fleetsharing/scheduling.py` | Existing priority and cadence contract; no production edit intended |
| `tests/test_fleetsharing_remote_worker.py` | Exact `None` versus empty/subset publication semantics |
| `tests/test_fleetsharing_cadence.py` | Real owner-loop continuity under independently renewed proof |
| `tests/test_fleetsharing_scheduling.py` | Urgent work still obeys retries/cadence and yields to explicit Stop/Off |
| `tests/test_fleetsharing_worker.py` | Existing fake/store/rig helpers and lifecycle regression coverage |
| `docs/fleet-telemetry-v2-evidence.md` | Append actual post-fix results without rewriting discovery observations |

Start from the current approved design branch or a fresh implementation branch
based on it. Record the exact implementation base SHA. The design worktree has
already run 272 focused baseline tests; rerun the relevant baseline in the
execution checkout before introducing a new regression:

```bash
uv sync --locked --extra dev
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_remote_worker.py \
  tests/test_fleetsharing_scheduling.py \
  tests/test_fleetsharing_cadence.py -q
```

---

## Task 1: Separate uncertain authority from destructive replacement

**Files:**
- Modify: `wingman/fleetsharing/worker.py`, `FleetSharingWorker._publication`.
- Test: `tests/test_fleetsharing_remote_worker.py`.

**Interfaces:**
- Consumes existing `projection.project_snapshot(snapshot, catalogue, *, eligible_character_ids)` and `p.Eligibility` / `p.EligibilityEntry`.
- Produces the unchanged `_publication(self) -> tuple[PublishRow, ...] | None` convention: `None` means do not publish; `()` is an intentional empty replacement.
- No new public API, persisted field, exception type, or callback.

- [ ] **Step 1: Add focused red tests.** Extend the test module's existing imports
  with `timedelta`, and `NOW`, `_date` from `tests.test_fleetsharing_worker`. Add:

```python
def _publication_case(expired_ids=(), amounts=(10, 20)):
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    worker._catalogue = FleetCatalogue(
        9, (CatalogueCharacter(1, "Alice"), CatalogueCharacter(2, "Bob"))
    )
    template = worker._eligibility.characters[0]
    now = NOW + timedelta(seconds=mono[0] - 1000)
    worker._eligibility = replace(
        worker._eligibility,
        characters=tuple(
            replace(
                template,
                character_id=cid,
                expires_at=_date(
                    now + timedelta(seconds=0 if cid in expired_ids else 10)
                ),
            )
            for cid in (1, 2)
        ),
    )
    worker.submit(
        FleetSnapshot(
            (FleetRow("Alice", amounts[0]), FleetRow("Bob", amounts[1])),
            StreamHealth("active"),
        )
    )
    return worker


@pytest.mark.parametrize("expired_ids", [(1,), (1, 2)])
def test_expired_active_permission_suspends_whole_replacement(expired_ids):
    worker = _publication_case(expired_ids)
    assert worker._publication() is None


def test_expired_quiet_member_does_not_block_fresh_active_member():
    worker = _publication_case((1,), amounts=(0, 20))
    assert worker._publication() == (PublishRow(2, 20, ()),)


def test_real_inactivity_remains_an_empty_replacement():
    worker = _publication_case((1, 2), amounts=(0, 0))
    assert worker._publication() == ()


def test_authoritative_not_verified_remains_an_empty_replacement():
    worker = _publication_case()
    worker._eligibility = replace(
        worker._eligibility, state="not_verified", characters=()
    )
    assert worker._publication() == ()
```

- [ ] **Step 2: Run red.**

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_remote_worker.py -q
```

Expected: the two expired-active cases fail because production currently returns
an empty or partial tuple, not `None`. Record those failures; a setup/import
failure does not count as the red test.

- [ ] **Step 3: Change `_publication` after its existing catalogue/eligibility and
  mailbox freshness checks.** Preserve those earlier checks. Replace the current
  expiry-filtered eligible-ID construction and final projection with:

```python
        if (
            self._eligibility.state != "ready"
            or self._eligibility.participation_generation
            != getattr(self._state.observed_participation, "generation", None)
        ):
            return ()
        entries = {c.character_id: c for c in self._eligibility.characters}
        rows = projection.project_snapshot(
            latest[0],
            self._catalogue,
            eligible_character_ids=frozenset(entries),
        )
        # An atomic subset would withdraw active members whose cached proof
        # merely needs refresh. The relay still enforces current authority.
        if any(
            self._remaining(entries[row.character_id].expires_at) <= 0
            for row in rows
        ):
            return None
        return rows
```

This never sends the candidate rows until every candidate has unexpired observed
permission. It does not replace `None` eligibility with all owned characters.

- [ ] **Step 4: Run green and existing lifecycle regressions.**

```bash
uv run --extra dev ruff format \
  wingman/fleetsharing/worker.py tests/test_fleetsharing_remote_worker.py
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_remote_worker.py \
  tests/test_fleetsharing_worker.py -q
```

Expected: new exact-result assertions and existing Off, publication-refusal,
identity-reset, stale-mailbox and latest-snapshot tests pass.

- [ ] **Step 5: Review and commit the independently useful guard.**

```bash
git diff --check
git add wingman/fleetsharing/worker.py tests/test_fleetsharing_remote_worker.py
git commit -m "fix: avoid telemetry withdrawal on expired cached eligibility"
```

## Task 2: Service prerequisite refreshes before normal reads starve them

**Files:**
- Modify: `wingman/fleetsharing/worker.py`, constants, `_work`, `_accept`.
- Test: `tests/test_fleetsharing_cadence.py`, `tests/test_fleetsharing_scheduling.py`.

**Interfaces:**
- Consumes Task 1's non-destructive `_publication` and existing `Scheduler.choose` / `Scheduler.completed`.
- Produces private `_eligibility_work(self) -> Work` using the existing operation/key `fetch_eligibility` / `eligibility`.
- Introduces `ELIGIBILITY_REFRESH_INTERVAL_S = 2.0` and derived `ELIGIBILITY_URGENCY_WINDOW_S`; no scheduler API changes.

- [ ] **Step 1: Add urgency tests to `test_fleetsharing_scheduling.py`.** Extend
  imports with pytest, `timedelta`, `NOW`, `_date`, `drive`, and `rig` from the
  existing worker-test helper module. Add:

```python
@pytest.mark.parametrize("remaining, expected", [(3.01, 2), (3.0, 1), (0.0, 1)])
def test_due_eligibility_becomes_urgent_near_expiry(remaining, expected):
    from wingman.fleetsharing.scheduling import Scheduler, Work

    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    expiry = NOW + timedelta(seconds=mono[0] - 1000 + remaining)
    worker._eligibility = replace(
        worker._eligibility,
        characters=tuple(
            replace(entry, expires_at=_date(expiry))
            for entry in worker._eligibility.characters
        ),
    )
    worker._due["eligibility"] = mono[0]
    work = next(w for w in worker._work(True) if w.key == "eligibility")
    assert work.priority == expected
    assert work.due == mono[0]
    if expected == 1:
        scheduler = Scheduler()
        snapshot = Work("read_snapshot", "read", periodic=True)
        assert scheduler.choose((snapshot, work), mono[0]) == work
        off = Work("publish_snapshot", "withdraw", priority=0, payload=())
        assert scheduler.choose((work, off), mono[0]) == off


def test_urgent_eligibility_still_obeys_retry_and_shared_read_cadence():
    from wingman.fleetsharing.scheduling import Scheduler, Work

    scheduler = Scheduler()
    urgent = Work("fetch_eligibility", "eligibility", priority=1, periodic=True)
    snapshot = Work("read_snapshot", "read", periodic=True)
    scheduler.completed(urgent, 10, failed=True)
    assert scheduler.choose((urgent, snapshot), 10.49) is None
    assert scheduler.choose((urgent,), 10.5) is None
    assert scheduler.choose((urgent, snapshot), 10.5) == snapshot
    assert scheduler.choose((urgent,), 11) == urgent
```

- [ ] **Step 2: Run red.**

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_scheduling.py -q
```

Expected: near/exact-expiry cases currently receive priority 2 instead of 1.
The backoff/cadence test should already pass and protects the existing scheduler.

- [ ] **Step 3: Reuse existing priority machinery.** Import `SIGNED_INTERVAL_S`
  from `.scheduling`, name the current poll interval, and derive the reserve:

```python
ELIGIBILITY_REFRESH_INTERVAL_S = 2.0
ELIGIBILITY_URGENCY_WINDOW_S = (
    ELIGIBILITY_REFRESH_INTERVAL_S + 2 * SIGNED_INTERVAL_S
)
```

Add the private work constructor:

```python
    def _eligibility_work(self) -> Work:
        eligibility = self._eligibility
        urgent = (
            eligibility is not None
            and eligibility.state == "ready"
            and any(
                self._remaining(entry.expires_at) <= ELIGIBILITY_URGENCY_WINDOW_S
                for entry in eligibility.characters
            )
        )
        return Work(
            "fetch_eligibility",
            "eligibility",
            due=self._due["eligibility"],
            priority=1 if urgent else 2,
            periodic=True,
        )
```

Replace only the existing `Work("fetch_eligibility", ...)` entry in `_work` with
`self._eligibility_work()`. In `_accept`, retain completion-based polling:

```python
            self._due["eligibility"] = (
                self._clock() + ELIGIBILITY_REFRESH_INTERVAL_S
            )
```

Do not shorten scheduler retry deadlines, clear failure counts, change the due
time to zero every turn, or change `Scheduler.choose` globally. Urgency is not a
new retry loop or permission to bypass the shared read bucket.

- [ ] **Step 4: Add the independently renewed proof helper to the cadence test
  module.** Add `math` and `_date` to its imports. Define:

```python
def renewed_source_proof(
    *, changing=False, source_until=None,
    source_period=6, source_phase=2, clock_skew=0,
):
    def configure(worker, client, timeline):
        original = client.fetch_eligibility
        server_utc = client.utc
        worker._utc_clock = lambda: server_utc() + timedelta(seconds=clock_skew)

        def eligibility(**args):
            started = timeline.now
            result = original(**args)
            if source_until is not None and started >= source_until:
                return replace(result, state="not_verified", characters=())
            expiry = NOW + timedelta(
                seconds=(
                    math.floor((started - 1000 - source_phase) / source_period)
                    * source_period + source_phase + 10
                )
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
    return configure
```

This helper models the deadline at request sampling, before response latency.
It does not claim to be a real server; it supplies the independently changing
external condition absent from the original fake.

Add continuity and authority-loss tests:

```python
@pytest.mark.parametrize("changing", [False, True])
@pytest.mark.parametrize("latency", [0.08, 0.2, 0.4, 0.6])
def test_renewed_source_preserves_active_publications(changing, latency):
    client, _, _, _ = run_owner(
        publisher=True,
        watch=True,
        latency=latency,
        duration=60,
        configure=renewed_source_proof(changing=changing),
    )
    assert client.published
    assert all(rows for _, rows in client.published)
    times = [t for t, _ in client.published]
    assert max(b - a for a, b in pairwise(times)) < 3.0
    operations = {op for op, _, _ in client.calls}
    assert {"fetch_sources", "fetch_catalogue", "read_snapshot"} <= operations


def test_authoritative_source_loss_still_withdraws_active_local_metrics():
    client, _, _, _ = run_owner(
        publisher=True,
        watch=True,
        latency=0.6,
        duration=60,
        configure=renewed_source_proof(source_until=1030),
    )
    empty = [(t, rows) for t, rows in client.published if not rows]
    assert len(empty) == 1
    assert empty[0][0] >= 1030
    assert all(not rows for t, rows in client.published if t >= empty[0][0])


@pytest.mark.parametrize("period", [5, 6])
@pytest.mark.parametrize("phase", [0, 2, 4])
@pytest.mark.parametrize("skew", [-0.5, 0.5])
def test_source_phase_and_small_clock_skew_do_not_withdraw(period, phase, skew):
    client, _, _, _ = run_owner(
        publisher=True,
        watch=True,
        latency=0.6,
        duration=60,
        configure=renewed_source_proof(
            source_period=period, source_phase=phase, clock_skew=skew,
        ),
    )
    assert client.published
    assert all(rows for _, rows in client.published)
    times = [t for t, _ in client.published]
    assert max(b - a for a, b in pairwise(times)) < 10.0
```

The publication-gap bound checks the sender's continuity for this specified
latency matrix, not a promise that all remote reads are forever live at arbitrary
latency. Existing receiver tests continue checking low-latency freshness and
non-rejuvenating age. Task 1 alone must fail the constant-DPS 600 ms gap assertion;
without either production fix, that case must also fail the no-empty assertion.

- [ ] **Step 5: Verify the regression is discriminating.** Temporarily remove
  only Task 2's production changes, keeping Task 1 and every new test in place;
  record the constant-DPS 600 ms gap failure. Do not stash away the tests or reset
  the whole branch. Restore Task 2's production edit and rerun:

```bash
uv run --extra dev ruff format \
  wingman/fleetsharing/worker.py \
  tests/test_fleetsharing_scheduling.py tests/test_fleetsharing_cadence.py
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_scheduling.py \
  tests/test_fleetsharing_cadence.py \
  tests/test_fleetsharing_remote_worker.py -q
```

If actual timings violate the proposed gap bounds, inspect the trace and revise
scheduling, not the bounds merely to get green. The phase/skew matrix checks
five- and six-second proof renewal with small clock disagreement; it is not a
claim that arbitrary clock errors are harmless. The expiry-boundary and source-
loss tests must continue to prove that missing authority never becomes a grant.

- [ ] **Step 6: Review and commit.**

```bash
git diff --check
git add wingman/fleetsharing/worker.py tests/test_fleetsharing_scheduling.py \
  tests/test_fleetsharing_cadence.py
git commit -m "fix: prioritize due fleet eligibility near expiry"
```

## Task 3: Verify the release boundary and record actual results

**Files:**
- Verify: the source/tests changed in Tasks 1–2 and existing sharing/bridge suites.
- Modify documentation only: `docs/fleet-telemetry-v2-evidence.md`.

**Interfaces:**
- Consumes Tasks 1–2 with unchanged v1 transport and unchanged public bridge.
- Produces a reviewed, independently releasable client timing fix and a factual
  verification record. Does not enable any later redesign feature.

- [ ] **Step 1: Run the focused sharing and runtime gates.**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_*.py \
  tests/test_api_fleetsharing.py \
  tests/test_api_remote_fleet.py \
  tests/test_fleet_runtime_integration.py \
  tests/test_remote_fleet_store.py -q -rs
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Inspect existing tests for immediate Off, lost requests, backoff, stale telemetry,
identity/session replacement and real-thread mailbox ownership. Their assertions
must remain intact; do not weaken them to accommodate urgency.

- [ ] **Step 2: Run the final quality pass.** Use `polish-core --fix` against the
  recorded implementation base, inspect every edit, and rerun the affected gates.
  The resulting production diff should remain within `fleetsharing/worker.py`
  unless review produces a concrete reason for a wider change.

- [ ] **Step 3: Run broader verification with real prerequisites.** Follow
  `docs/overview-layout-sharing-verification.md#local-verification-prerequisites`
  for Node and the release settings codec, then run:

```bash
uv run --no-sync python -m pytest tests/ -rs
```

Do not describe Node/native skips or an absent codec as full-suite coverage.
If an unrelated hook or baseline failure blocks this, report it and stop rather
than modifying unrelated code or using `--no-verify`.

- [ ] **Step 4: Record results and remaining acceptance honestly.** Append a
  new post-fix section to `docs/fleet-telemetry-v2-evidence.md`, preserving the
  original discovery reproduction. Include the implementation SHA, actual red/
  green outputs, continuity matrix, explicit Off/source-loss results and any
  unavailable Windows/two-PC smoke. Use `change-explainer` for the completion
  write-up; do not claim the incoming-DPS, activity, aggressor or setup work is
  included.

- [ ] **Step 5: Commit the verification record.**

```bash
git diff --check
git add docs/fleet-telemetry-v2-evidence.md
git commit -m "docs: record fleet timing fix verification"
```

No deployment or live mutation is authorized by this plan. A normal reviewed
release can deliver this fix independently while the remaining approved work is
planned against the versioned shared-combat contract.

## Plan preflight and coverage

The plan's Python snippets were parsed and exercised against the existing harness
without editing production files. The unchanged worker failed the new expired-
active and urgency checks. An in-memory candidate built from the proposed method
bodies passed 30 cases: five publication decisions, four urgency/cadence cases,
eight continuity cases, one authoritative source-loss case, and twelve source-
phase/clock-skew cases. This establishes that the proposed test/code interfaces
fit the current repository; it does not replace implementation red/green,
formatting, broader tests or live acceptance.

Scoped spec coverage:
- §1 destructive empty and partial replacements: Task 1.
- §1 prerequisite scheduling and one-lane cadence: Task 2.
- §1 source-loss/Off, freshness, retries and lifecycle safety: Tasks 1–3, with the
  existing lifecycle suite retained and new exact-result/cadence assertions.
- §1 verification and independently releasable patch: Task 3.
- Spec §§2–6 are explicitly outside this first plan; they remain approved work,
  not silently satisfied by the timing fix.
