# Skills Training Remaining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show and sort each Missing character by the Omega-rate training work remaining for the selected plan while preserving EVE's actual queue ETA for Training characters.

**Architecture:** Add a pure training calculator, enrich the existing skill ID cache with expiring dogma metadata, and extend each character snapshot with complete per-skill SP and supplemental attributes. `SkillsController` remains the sole state writer and produces raw sort values plus formatted labels; the ES5 page only groups, sorts, and renders those semantic results.

**Tech Stack:** Python 3.11, dataclasses, `fractions.Fraction`, EVE ESI, pywebview bridge payloads, plain HTML/CSS/ES5, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-02-skills-training-remaining-design.md`

## Global Constraints

- Estimates use current remapped attributes at Omega speed and exclude implants.
- Estimate only requirements explicitly listed in the selected plan; do not discover prerequisites.
- Keep readiness semantics and section order unchanged: Ready, Training, Locked, Missing, Unknown, Unscored.
- Missing duration includes every listed requirement with an SP deficit, including queued requirements; trained-but-inactive requirements have zero deficit.
- An estimate is all-or-nothing; never display a partial sum.
- Preserve the skills-plus-queue atomic core snapshot; supplemental attribute failure must not block readiness refresh.
- `SkillsController` remains the only writer of the skills state document; network work stays outside its lock and each mutation plus save stays in one critical section.
- No new OAuth scope: character attributes use the existing `esi-skills.read_skills.v1` grant.
- No framework, build step, bundler, or new dependency.
- The UI must fit the measured 840x625 CSS viewport floor.
- A selector that sets `display` must provide its own `[hidden]` override.
- Nothing in pytest renders the page; complete the Windows/WebView2 smoke pass in `docs/smoke-checklist.md`.

## File map

- Create `wingman/eveskills/training.py`: pure SP thresholds, attribute-rate duration calculation, status result, and duration formatting.
- Create `tests/test_eveskills_training.py`: canonical calculator and formatter fixtures.
- Modify `wingman/eveskills/skillids.py`: optional expiring training metadata in the existing ID cache plus staged public-ESI fetches.
- Modify `tests/test_eveskills_skillids.py`: metadata parsing, persistence, expiry, backfill, and failure tests.
- Modify `wingman/eveskills/state.py`: persisted SP-completeness and supplemental character-attribute fields.
- Modify `tests/test_eveskills_state.py`: tolerant migration, validation, ETag bypass, and round-trip tests.
- Modify `wingman/eveskills/controller.py`: third refresh request, independent attribute failure semantics, owner-change cleanup, metadata backfill, and estimate payload fields.
- Modify `tests/test_eveskills_controller.py`: refresh, migration, ownership, metadata integration, and payload tests.
- Modify `wingman/web/index.html`: accessible estimate-assumptions affordance.
- Modify `wingman/web/skills.js`: collapsed-row copy, tooltips, and within-section sorting.
- Modify `wingman/web/style.css`: quiet information-affordance styling and `[hidden]` behavior.
- Modify `wingman/web/dev.js`: rendered sorting, unavailable, stale, long-name, and mixed queued/unqueued fixtures.
- Modify `tests/test_skills_page.py`: lexical UI, sorting, copy, accessibility, and fixture guards.
- Modify `docs/smoke-checklist.md`: manual rendered checks at the viewport floor.

---

### Task 1: Pure training calculator

**Files:**
- Create: `wingman/eveskills/training.py`
- Create: `tests/test_eveskills_training.py`

**Interfaces:**
- Consumes: plan requirements exposing `skill_name` and `level`; case-insensitive `skill_ids`; complete `skill_points`; five named character attributes; per-type `SkillTrainingMetadata`.
- Produces:
  - `SkillTrainingMetadata(rank: int, primary_attribute: str, secondary_attribute: str, fetched_utc: datetime)`
  - `TrainingEstimate(seconds: int | None, status: str)`
  - `estimate(requirements, skill_ids, skill_points, *, skill_points_complete, attributes, metadata) -> TrainingEstimate`
  - `format_duration(seconds: int | None) -> str`
  - status constants `AVAILABLE`, `REFRESH_REQUIRED`, `ATTRIBUTES_UNAVAILABLE`, `METADATA_UNAVAILABLE`.

- [ ] **Step 1: Write failing threshold and single-skill calculation tests**

Create `tests/test_eveskills_training.py` with fixtures that avoid controller or ESI dependencies:

```python
from datetime import UTC, datetime

import pytest

from wingman.eveskills import plans, training

NOW = datetime(2026, 9, 2, tzinfo=UTC)
ATTRS = {
    "charisma": 19,
    "intelligence": 20,
    "memory": 20,
    "perception": 27,
    "willpower": 21,
}
META = training.SkillTrainingMetadata(
    rank=1,
    primary_attribute="perception",
    secondary_attribute="willpower",
    fetched_utc=NOW,
)


def req(name="Gunnery", level=5):
    return plans.Requirement(skill_name=name, level=level)


def test_cumulative_sp_thresholds_match_eve_levels():
    assert [training.skill_point_threshold(1, level) for level in range(1, 6)] == [
        250,
        1415,
        8000,
        45255,
        256000,
    ]
    assert training.skill_point_threshold(3, 5) == 768000


def test_estimate_uses_partial_sp_and_current_attribute_pair():
    result = training.estimate(
        [req(level=4)],
        {"gunnery": 3300},
        {3300: 40_000},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    # 5,255 SP at 37.5 SP/minute, rounded up once at the final second.
    assert result == training.TrainingEstimate(seconds=8408, status=training.AVAILABLE)
```

- [ ] **Step 2: Run the new tests and verify the missing module fails**

Run:

```bash
uv run --no-sync python -m pytest tests/test_eveskills_training.py -v
```

Expected: collection fails because `wingman.eveskills.training` does not exist.

- [ ] **Step 3: Implement deterministic thresholds and estimate types**

Create `wingman/eveskills/training.py` with these public shapes and integer/Fraction arithmetic:

```python
import math
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

AVAILABLE = "available"
REFRESH_REQUIRED = "refresh_required"
ATTRIBUTES_UNAVAILABLE = "attributes_unavailable"
METADATA_UNAVAILABLE = "metadata_unavailable"
ATTRIBUTE_NAMES = frozenset(
    {"charisma", "intelligence", "memory", "perception", "willpower"}
)


@dataclass(frozen=True)
class SkillTrainingMetadata:
    rank: int
    primary_attribute: str
    secondary_attribute: str
    fetched_utc: datetime


@dataclass(frozen=True)
class TrainingEstimate:
    seconds: int | None
    status: str


_RANK_ONE_THRESHOLDS = (0, 250, 1415, 8000, 45255, 256000)


def skill_point_threshold(rank: int, level: int) -> int:
    if rank <= 0 or not 1 <= level <= 5:
        raise ValueError("Skill rank and level must be positive EVE values.")
    return rank * _RANK_ONE_THRESHOLDS[level]
```

Use the canonical threshold table rather than a floating-point exponential formula; the test is the contract.

Implement `estimate()` so validation precedence is:

1. incomplete SP snapshot -> `REFRESH_REQUIRED`;
2. absent/incomplete/non-positive attributes -> `ATTRIBUTES_UNAVAILABLE`;
3. unresolved skill ID or absent/invalid metadata -> `METADATA_UNAVAILABLE`;
4. otherwise sum exact seconds without per-skill rounding and call `math.ceil()` once on the final `Fraction` total.

Use this denominator form to avoid floats:

```python
seconds += Fraction(deficit * 120, primary * 2 + secondary)
```

Treat an absent skill ID in a complete SP map as zero SP. Clamp an over-target current SP value to a zero deficit.

- [ ] **Step 4: Add failing all-or-nothing and mixed-state tests**

Add tests proving:

```python
def test_queued_position_does_not_remove_remaining_sp():
    # Queue state is intentionally not an estimator input.
    result = training.estimate(
        [req(level=5)], {"gunnery": 3300}, {3300: 45_255},
        skill_points_complete=True, attributes=ATTRS, metadata={3300: META},
    )
    assert result.seconds > 0


def test_absent_skill_is_zero_only_in_a_complete_snapshot():
    complete = training.estimate(
        [req(level=1)], {"gunnery": 3300}, {},
        skill_points_complete=True, attributes=ATTRS, metadata={3300: META},
    )
    incomplete = training.estimate(
        [req(level=1)], {"gunnery": 3300}, {},
        skill_points_complete=False, attributes=ATTRS, metadata={3300: META},
    )
    assert complete.status == training.AVAILABLE
    assert incomplete == training.TrainingEstimate(None, training.REFRESH_REQUIRED)


def test_one_missing_metadata_record_suppresses_the_whole_sum():
    result = training.estimate(
        [req("Gunnery", 3), req("Navigation", 3)],
        {"gunnery": 3300, "navigation": 3449},
        {3300: 8000, 3449: 0},
        skill_points_complete=True,
        attributes=ATTRS,
        metadata={3300: META},
    )
    assert result == training.TrainingEstimate(None, training.METADATA_UNAVAILABLE)
```

Also cover malformed rank, unknown attribute names, missing one of the five character attributes, already-trained requirements producing zero seconds, and multiple skills with different attribute pairs.

- [ ] **Step 5: Add and implement duration-format tests**

Pin the existing two-unit vocabulary and positive-subminute clamp:

```python
@pytest.mark.parametrize(
    ("seconds", "label"),
    [(None, ""), (0, "0m"), (1, "<1m"), (12 * 60, "12m"),
     (4 * 3600 + 20 * 60, "4h 20m"),
     (2 * 86400 + 4 * 3600 + 31 * 60, "2d 4h")],
)
def test_format_duration(seconds, label):
    assert training.format_duration(seconds) == label
```

Implement nearest-minute rounding as `(seconds + 30) // 60`, clamped to one minute for positive values, then emit at most two units.

- [ ] **Step 6: Run focused tests and lint**

Run:

```bash
uv run --no-sync python -m pytest tests/test_eveskills_training.py -v
uv run --extra dev ruff check wingman/eveskills/training.py tests/test_eveskills_training.py
uv run --extra dev ruff format --check wingman/eveskills/training.py tests/test_eveskills_training.py
```

Expected: all pass.

- [ ] **Step 7: Commit the calculator**

```bash
git add wingman/eveskills/training.py tests/test_eveskills_training.py
git commit -m "feat: calculate remaining skill training time"
```

---

### Task 2: Expiring skill training metadata

**Files:**
- Modify: `wingman/eveskills/skillids.py`
- Modify: `tests/test_eveskills_skillids.py`

**Interfaces:**
- Consumes: `training.SkillTrainingMetadata`; existing name-to-type IDs; public type-detail ESI responses.
- Produces:
  - `SkillIdCache.training_metadata(now: datetime) -> dict[int, SkillTrainingMetadata]`
  - `SkillIdCache.metadata_due(names: Iterable[str], now: datetime) -> tuple[tuple[str, int], ...]`
  - `SkillIdCache.merge_metadata(entries: Mapping[int, SkillTrainingMetadata]) -> int`
  - `fetch_training_metadata(requests, client, fetched_utc, *, max_workers=RESOLVE_WORKERS) -> tuple[dict[int, SkillTrainingMetadata], dict[str, str]]`.

- [ ] **Step 1: Write failing cache round-trip and migration tests**

Extend `tests/test_eveskills_skillids.py`:

```python
from datetime import UTC, datetime, timedelta
from wingman.eveskills import training

NOW = datetime(2026, 9, 2, tzinfo=UTC)
GUNNERY_META = training.SkillTrainingMetadata(
    1, "perception", "willpower", NOW
)


def test_training_metadata_round_trips_without_changing_type_id_lookup(tmp_path):
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    assert cache.merge_metadata({3300: GUNNERY_META}) == 1
    target = tmp_path / "cache.json"
    skillids.save(cache, target)
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("gunnery") == 3300
    assert loaded.training_metadata(NOW) == {3300: GUNNERY_META}


def test_version_one_id_only_cache_loads_and_requests_metadata(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({
        "version": 1,
        "entries": [{"name": "Gunnery", "type_id": 3300, "category_id": 16}],
    }), encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("gunnery") == 3300
    assert loaded.metadata_due(["Gunnery"], NOW) == (("Gunnery", 3300),)
```

- [ ] **Step 2: Run focused tests and verify missing metadata APIs fail**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_skillids.py -k "training_metadata or id_only" -v
```

Expected: failures because the metadata APIs do not exist.

- [ ] **Step 3: Extend the in-memory and disk cache without invalidating IDs**

Keep `CACHE_VERSION = 1` so existing ID-only files remain valid. Add a separate `TRAINING_METADATA_VERSION = 1`, `METADATA_MAX_AGE = timedelta(days=30)`, and optional top-level `training_metadata_version`.

Store metadata by type ID inside `SkillIdCache`, while preserving `get()`, `type_ids()`, `unresolved()`, and `merge()` behavior. Serialize valid metadata beside its existing entry:

```json
{
  "name": "gunnery",
  "type_id": 3300,
  "category_id": 16,
  "training": {
    "rank": 1,
    "primary_attribute": "perception",
    "secondary_attribute": "willpower",
    "fetched_utc": "2026-09-02T00:00:00+00:00"
  }
}
```

If `training_metadata_version` is absent or wrong, retain every valid ID and ignore only metadata. `training_metadata(now)` returns fresh records only. `metadata_due()` deduplicates by type ID and includes missing or age >= 30-day records. `merge_metadata()` accepts records only for type IDs already held by the cache.

- [ ] **Step 4: Write failing dogma parsing and staged-fetch tests**

Add captured type-detail data using the documented dogma IDs:

```python
TYPE_BODY = {
    "group_id": 255,
    "dogma_attributes": [
        {"attribute_id": 275, "value": 1.0},
        {"attribute_id": 180, "value": 167.0},
        {"attribute_id": 181, "value": 168.0},
    ],
}


def test_fetch_training_metadata_decodes_rank_and_attribute_names():
    client = FakeEsi(types={3300: TYPE_BODY})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300),), client, NOW, max_workers=1
    )
    assert accepted == {3300: GUNNERY_META}
    assert failures == {}


def test_fetch_failure_returns_no_partial_cache_mutation():
    class OneFailure(FakeEsi):
        def get(self, path, *, token=None, etag=None):
            if path.endswith("/3449/"):
                self.paths.append(path)
                return esi.EsiResponse(503, None, "boom", "", "GET", path)
            return super().get(path, token=token, etag=etag)

    cache = skillids.SkillIdCache({"Gunnery": 3300, "Navigation": 3449})
    client = OneFailure(types={3300: TYPE_BODY})
    accepted, failures = skillids.fetch_training_metadata(
        cache.metadata_due(["Gunnery", "Navigation"], NOW), client, NOW,
        max_workers=1,
    )
    assert 3300 in accepted and "Navigation" in failures
    assert cache.training_metadata(NOW) == {}, "fetch must stage, not mutate"
```

- [ ] **Step 5: Implement strict dogma decoding and staged concurrent fetch**

Add named constants:

```python
DOGMA_PRIMARY_ATTRIBUTE = 180
DOGMA_SECONDARY_ATTRIBUTE = 181
DOGMA_SKILL_TIME_CONSTANT = 275
ATTRIBUTE_ID_TO_NAME = {
    164: "charisma",
    165: "intelligence",
    166: "memory",
    167: "perception",
    168: "willpower",
}
REASON_METADATA_UNAVAILABLE = "Could not load training metadata from ESI."
```

`_training_metadata_from_type(data, fetched_utc)` must require:

- `dogma_attributes` is a list;
- rank is positive and integer-valued;
- primary and secondary IDs map to the five names;
- `fetched_utc` is aware UTC.

`fetch_training_metadata()` may use the existing four-worker bound, but it returns staged `accepted` and `failures` mappings and never mutates `SkillIdCache`. One malformed or failed type affects that type's metadata only; Task 5's calculator will suppress a character-plan estimate if the selected plan needs it.

- [ ] **Step 6: Add expiry and malformed-disk tests**

Cover:

- metadata at 29 days is fresh and at 30 days is due;
- wrong metadata sub-version preserves IDs and discards metadata;
- malformed rank, attribute IDs, timestamp, bools, and unknown fields are dropped per entry;
- duplicate names sharing one type ID produce one request;
- save/load backup recovery behavior remains unchanged.

- [ ] **Step 7: Run metadata tests and the existing cache suite**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_skillids.py -v
uv run --extra dev ruff check wingman/eveskills/skillids.py tests/test_eveskills_skillids.py
uv run --extra dev ruff format --check wingman/eveskills/skillids.py tests/test_eveskills_skillids.py
```

Expected: all pass, including existing corruption and backup tests.

- [ ] **Step 8: Commit metadata support**

```bash
git add wingman/eveskills/skillids.py tests/test_eveskills_skillids.py
git commit -m "feat: cache skill training metadata"
```

---

### Task 3: Persist complete SP and supplemental attributes

**Files:**
- Modify: `wingman/eveskills/state.py`
- Modify: `tests/test_eveskills_state.py`
- Modify: `wingman/eveskills/controller.py:1590-1615`
- Modify: `tests/test_eveskills_controller.py:1345-1375`

**Interfaces:**
- Consumes: existing tolerant state loading and owner-hash transfer detection.
- Produces these `state.Character` fields:
  - `skill_points: dict[int, int]`
  - `skill_points_complete: bool`
  - `attributes: dict[str, int]`
  - `attributes_fetched_utc: datetime | None`
  - `attributes_error: str`
  - `attributes_etag: str`.

- [ ] **Step 1: Write failing full-character round-trip tests**

Extend `test_round_trips_a_full_character` in `tests/test_eveskills_state.py` with:

```python
skill_points={3300: 256000, 3301: 40000},
skill_points_complete=True,
attributes={
    "charisma": 19,
    "intelligence": 20,
    "memory": 20,
    "perception": 27,
    "willpower": 21,
},
attributes_fetched_utc=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
attributes_error="",
attributes_etag='W/"attrs"',
```

The existing equality assertion should fail until all fields serialize and load.

- [ ] **Step 2: Write failing legacy ETag and malformed-SP tests**

Add:

```python
def test_legacy_snapshot_clears_skills_etag_until_sp_is_downloaded():
    loaded = state.from_dict({"characters": [{
        "character_id": 1,
        "fetched_utc": "2026-08-24T10:30:00+00:00",
        "active_levels": {"3300": 5},
        "trained_levels": {"3300": 5},
        "skills_etag": 'W/"legacy"',
    }]})
    ch = loaded.find(1)
    assert ch.skill_points_complete is False
    assert ch.skills_etag == ""


def test_malformed_persisted_sp_invalidates_completeness_and_etag():
    loaded = state.from_dict({"characters": [{
        "character_id": 1,
        "skill_points": {"3300": 1000, "bad": 5},
        "skill_points_complete": True,
        "skills_etag": 'W/"must-not-hide-next-body"',
    }]})
    ch = loaded.find(1)
    assert ch.skill_points_complete is False
    assert ch.skills_etag == ""
```

Also test that an empty SP map with `skill_points_complete: true` remains complete, representing a character with zero trained skills.

- [ ] **Step 3: Run state tests and verify failures**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_state.py -k "full_character or skill_points or legacy_snapshot or attributes" -v
```

Expected: failures for missing fields and migration behavior.

- [ ] **Step 4: Implement bounded tolerant state coercion**

Add the six fields to `Character`. Reuse `MAX_LEVEL_ENTRIES` for the SP map cap because both collections are keyed by the same bounded EVE skill set.

Implement `_coerce_skill_points(raw) -> tuple[dict[int, int], bool]` so:

- a dict, including `{}`, is structurally valid;
- bools, non-integers, non-positive IDs, negative SP, or entries beyond the cap make `valid` false;
- any invalid entry discards the entire SP map and makes `valid` false, while the independent active/trained level maps keep their existing tolerant behavior.

Implement `_coerce_attributes(raw) -> tuple[dict[str, int], bool]` requiring exactly the five names and positive non-bool integers. On load:

```python
points, points_valid = _coerce_skill_points(item.get("skill_points"))
points_complete = item.get("skill_points_complete") is True and points_valid
skills_etag = _coerce_text(item.get("skills_etag")) if points_complete else ""
```

Attributes without a valid complete map or valid `attributes_fetched_utc` load as unavailable with an empty ETag. Preserve `attributes_error` only as sanitized trimmed text.

Update `to_dict()` with stable string skill IDs and ISO timestamps.

- [ ] **Step 5: Extend owner-change reset tests before production reset code**

Update `test_an_ownership_change_clears_the_cached_snapshot` so its starting character has all six new fields and asserts all are cleared after reauthorization. Keep the same-owner test asserting they survive.

Run:

```bash
uv run --no-sync python -m pytest tests/test_eveskills_controller.py -k "ownership_change or same_character_keeps" -v
```

Expected: ownership-change test fails because `_upsert_identity()` does not clear the new fields.

- [ ] **Step 6: Clear all character-owned estimate data on transfer**

In the existing owner-hash-change branch, add:

```python
ch.skill_points = {}
ch.skill_points_complete = False
ch.attributes = {}
ch.attributes_fetched_utc = None
ch.attributes_error = ""
ch.attributes_etag = ""
```

Do not clear public training metadata from `SkillIdCache`; it is not character-owned.

Update `tests/test_eveskills_controller.py`'s `with_snapshot()` defaults with a
valid `skill_points` map and `skill_points_complete=True`. This keeps its stored
skills ETag valid under the new migration rule, so existing conditional-request
tests continue to represent a modern complete snapshot. Add valid attributes to
that helper only in Task 4, when the refresh path understands them.

- [ ] **Step 7: Run state and the complete controller suite**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_state.py -v
uv run --no-sync python -m pytest tests/test_eveskills_controller.py -v
uv run --extra dev ruff check wingman/eveskills/state.py wingman/eveskills/controller.py \
  tests/test_eveskills_state.py tests/test_eveskills_controller.py
uv run --extra dev ruff format --check wingman/eveskills/state.py \
  wingman/eveskills/controller.py tests/test_eveskills_state.py \
  tests/test_eveskills_controller.py
```

Expected: all pass; Task 3 does not leave legacy-ETag migration breaking the
existing controller fixtures.

- [ ] **Step 8: Commit persisted estimate inputs**

```bash
git add wingman/eveskills/state.py wingman/eveskills/controller.py \
  tests/test_eveskills_state.py tests/test_eveskills_controller.py
git commit -m "feat: persist skill estimate inputs"
```

---

### Task 4: Acquire SP and attributes without weakening readiness refresh

**Files:**
- Modify: `wingman/eveskills/controller.py:95-185, 1010-1325`
- Modify: `tests/test_eveskills_controller.py:305-600`

**Interfaces:**
- Consumes: Task 3's character fields and existing `_authorised_get()`/ETag contract.
- Produces:
  - `_attributes_path(character_id: int) -> str`
  - `_parse_skills(data) -> ParsedSkills`
  - `_parse_attributes(data) -> dict[str, int] | None`
  - a refresh that commits skills+queue even when supplemental attributes fail.

- [ ] **Step 1: Extend refresh fakes and write failing three-endpoint success test**

Add SP to `SKILLS_BODY`, an `ATTRIBUTES_BODY`, and an `attributes` script to `FakeEsi`:

```python
SKILLS_BODY = {"skills": [{
    "skill_id": 3327,
    "active_skill_level": 4,
    "trained_skill_level": 5,
    "skillpoints_in_skill": 200000,
}]}
ATTRIBUTES_BODY = {
    "charisma": 19,
    "intelligence": 20,
    "memory": 20,
    "perception": 27,
    "willpower": 21,
}
```

Route `/attributes/` separately from `/skillqueue/`. Extend `with_snapshot()`
with valid attributes, `attributes_fetched_utc=T0`, and
`attributes_etag='"old-a"'`, so 304 tests begin from a complete modern
supplemental snapshot. Rename `test_200_and_200_commits_both_halves` to
`test_200_responses_commit_core_and_attributes` and extend it to assert:

```python
assert ch.skill_points == {3327: 200000}
assert ch.skill_points_complete is True
assert ch.attributes == ATTRIBUTES_BODY
assert ch.attributes_etag == '"a1"'
assert ch.attributes_fetched_utc == clock.value
```

- [ ] **Step 2: Run the success test and verify fields remain empty**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_controller.py -k "responses_commit_core_and_attributes" -v
```

Expected: failure on SP/attributes assertions.

- [ ] **Step 3: Implement strict supplemental parsing**

Add:

```python
@dataclass(frozen=True)
class ParsedSkills:
    active_levels: dict[int, int]
    trained_levels: dict[int, int]
    skill_points: dict[int, int]
    skill_points_complete: bool
```

Preserve the existing tolerant active/trained parsing. Set
`skill_points_complete=False` and return an empty SP map if the top-level
`skills` value is not a list or if any row lacks a positive `skill_id` or a
non-negative, non-bool integer `skillpoints_in_skill`. Do not retain a partial
SP map or interpret a malformed SP row as zero.

`_parse_attributes()` returns a complete five-key dict or `None`; it accepts no
partial result. Add `_attributes_path()` returning
`f"/v1/characters/{character_id}/attributes/"`, matching the versioned,
trailing-slash convention used by the other authenticated calls.

- [ ] **Step 4: Write failing legacy-304 and malformed-body retry tests**

Seed an old document containing levels and a skills ETag but no
`skill_points_complete`; construct the controller from disk rather than through
a freshly saved `Character`; refresh and assert the skills request receives
`etag=None` and a 200 body populates SP.

Add a malformed SP response test asserting:

```python
assert ch.active_levels, "readiness levels still follow tolerant parsing"
assert ch.skill_points == {}
assert ch.skill_points_complete is False
assert ch.skills_etag == "", "the next refresh must fetch another body"
```

Then script a second valid refresh and assert it receives no skills ETag and
recovers the estimate inputs.

- [ ] **Step 5: Write failing supplemental attribute failure tests**

Cover 500, 403, malformed 200, and 304:

- 500/403/malformed 200 still commit new skills and queue;
- they set `attributes_error`, leave `attributes_fetched_utc` unchanged, and make estimate inputs unavailable;
- they do not set the core `error`, `stale`, or `needs_reauth` flags when core refresh succeeded;
- a 304 with existing valid attributes stamps `attributes_fetched_utc` to the same refresh time and clears `attributes_error`;
- a 200 attributes response with no ETag does not invent one;
- a core skills or queue failure still short-circuits before attributes because no new SP snapshot can be committed.

- [ ] **Step 6: Implement refresh and commit ordering**

In `_refresh_one()`:

1. snapshot all three ETags under the lock;
2. fetch skills, then queue, retaining current core short-circuits;
3. fetch attributes only after both core calls succeed;
4. pass an attribute response or supplemental error into `_commit_success()`;
5. return only core/degraded save errors to the existing progress error field.

Parse all 200 bodies outside the lock. Inside one lock hold:

- apply skills levels and SP only for a skills 200;
- preserve complete SP on a skills 304;
- clear `skills_etag` whenever a 200 SP body is incomplete;
- apply queue only for a queue 200;
- on valid attributes 200/304, clear `attributes_error` and stamp `attributes_fetched_utc`;
- on supplemental failure, retain last attributes for recovery/diagnostics but set `attributes_error`, making them unusable for estimates;
- stamp core `fetched_utc`, clear core error/reauth, and save once.

Do not call `_commit_failure()` for an attribute-only failure, because that path marks core data stale and can delete a working refresh token.

- [ ] **Step 7: Update pre-existing refresh assertions for the third call**

Adjust tests that intentionally count calls or assert the last request. Keep their original semantic assertions. In particular, update the “two concurrent refreshes” and re-entry comments/counts to expect an attributes call only on passes where skills and queue both succeeded; keep failing-skills and failing-queue tests asserting no attributes request.

- [ ] **Step 8: Run controller, state, and ESI tests**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_controller.py -v
uv run --no-sync python -m pytest tests/test_eveskills_state.py tests/test_eveskills_esi.py -v
uv run --extra dev ruff check wingman/eveskills/controller.py tests/test_eveskills_controller.py
uv run --extra dev ruff format --check wingman/eveskills/controller.py tests/test_eveskills_controller.py
```

Expected: all pass.

- [ ] **Step 9: Commit coherent refresh support**

```bash
git add wingman/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat: refresh skill points and attributes"
```

---

### Task 5: Backfill metadata and publish estimates

**Files:**
- Modify: `wingman/eveskills/controller.py:580-810, 1335-1400`
- Modify: `tests/test_eveskills_controller.py`

**Interfaces:**
- Consumes: Task 1's estimator/formatter, Task 2's staged metadata fetch, Task 3/4's complete snapshot inputs.
- Produces character summary fields:
  - `training_remaining_seconds: int | None`
  - `training_remaining_label: str`
  - `training_estimate_status: str`.

- [ ] **Step 1: Write failing metadata-backfill integration tests**

Build a controller with a plan, an ID-only cache file, and a fake public ESI type response. Invoke the refresh pass's plan-data resolution helper and assert:

```python
assert controller._cache.get("Gunnery") == 3300
assert controller._cache.training_metadata(clock.value)[3300].rank == 1
```

Instrument `state_payload()` during the fake network callback and assert it sees either no new metadata or the complete staged mapping, never one entry of a two-entry merge. Add a failed metadata response case proving readiness still evaluates and only estimate status becomes `metadata_unavailable`.

- [ ] **Step 2: Implement staged metadata backfill in the refresh pre-pass**

Add `_refresh_training_metadata()` and call it immediately after
`_resolve_missing_skill_ids()`:

1. under `_lock`, snapshot all explicit plan names and call `metadata_due(names, now)`;
2. outside `_lock`, call `fetch_training_metadata()`;
3. under one `_lock` hold, merge the complete staged result and save the cache once;
4. log bounded failures without changing plan readiness.

Keep `_resolve_missing_skill_ids()` focused on IDs. Do not perform public ESI
calls while holding `_lock`.

- [ ] **Step 3: Write failing payload tests**

Create a selected Missing plan and complete character inputs. Assert exact payload shape:

```python
row = controller.state_payload()["characters"][0]
assert row["training_remaining_seconds"] == expected_seconds
assert row["training_remaining_label"] == "18d 6h"
assert row["training_estimate_status"] == "available"
```

Add cases for:

- no SP completeness -> `None`, `""`, `refresh_required`;
- attributes error/absence -> `attributes_unavailable`;
- unresolved or expired metadata -> `metadata_unavailable`;
- queued requirements remain in the computed duration;
- trained-inactive target contributes zero SP;
- no selected plan keeps the existing Unscored row and supplies nullable/empty estimate fields.

- [ ] **Step 4: Run payload tests and verify missing fields fail**

```bash
uv run --no-sync python -m pytest tests/test_eveskills_controller.py -k "training_remaining or metadata_backfill" -v
```

Expected: failures because controller rows do not publish estimates.

- [ ] **Step 5: Integrate one metadata snapshot and one estimate per row**

Import `training`. In `_state_payload_locked()`, snapshot fresh metadata once:

```python
now = self._now()
metadata = self._cache.training_metadata(now)
```

Pass it into `_character_row()`. Call `training.estimate()` only when a selected plan exists. Attributes are usable only when:

- `attributes_fetched_utc` is present;
- `attributes_error` is empty;
- `skill_points_complete` is true.

Map the `TrainingEstimate` directly to raw seconds/status and call
`training.format_duration()` only for `AVAILABLE`. Do not overwrite or derive
`estimated_finish_utc`; it remains the EVE queue fact.

- [ ] **Step 6: Confirm bridge/API passthrough does not need a new handler**

Run the API tests with a controller fake carrying the three new fields:

```bash
uv run --no-sync python -m pytest tests/test_api_skills.py tests/test_skills_wiring.py -v
```

If an existing fake asserts exact dictionaries, update it to preserve the new controller fields. Do not add a bridge method or handler: the fields ride the existing `skills_state`/`onSkills` payload.

- [ ] **Step 7: Run all Python Skills suites**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveskills_training.py \
  tests/test_eveskills_skillids.py \
  tests/test_eveskills_state.py \
  tests/test_eveskills_controller.py \
  tests/test_api_skills.py \
  tests/test_skills_wiring.py -v
uv run --extra dev ruff check wingman/eveskills tests/test_eveskills_training.py \
  tests/test_eveskills_skillids.py tests/test_eveskills_state.py \
  tests/test_eveskills_controller.py
uv run --extra dev ruff format --check wingman/eveskills tests/test_eveskills_training.py \
  tests/test_eveskills_skillids.py tests/test_eveskills_state.py \
  tests/test_eveskills_controller.py
```

Expected: all pass.

- [ ] **Step 8: Commit estimate payload integration**

```bash
git add wingman/eveskills/controller.py tests/test_eveskills_controller.py \
  tests/test_api_skills.py
git commit -m "feat: publish character training estimates"
```

---

### Task 6: Render and sort collapsed rows

**Files:**
- Modify: `wingman/web/index.html:1865-1895`
- Modify: `wingman/web/skills.js:410-710, 795-870`
- Modify: `wingman/web/style.css:4560-4690`
- Modify: `wingman/web/dev.js:295-440`
- Modify: `tests/test_skills_page.py`

**Interfaces:**
- Consumes: Task 5's three estimate fields and existing queue fields/counts.
- Produces: accessible assumption tooltip, Training ETA sort, Missing duration sort, and collapsed-row summaries.

- [ ] **Step 1: Write failing lexical tests for exact sort keys and copy**

Add tests to `tests/test_skills_page.py` that comment-strip source before assertions:

```python
def test_training_rows_sort_by_real_finish_with_unknown_last():
    assert "function byTrainingFinishThenName" in CODE
    body = _function_body(CODE, "byTrainingFinishThenName")
    assert "estimated_finish_utc" in body
    assert "training_remaining_seconds" not in body


def test_missing_rows_sort_by_raw_training_seconds_with_unavailable_last():
    body = _function_body(CODE, "byTrainingRemainingThenName")
    assert "training_remaining_seconds" in body
    assert "training_remaining_label" not in body


def test_missing_status_carries_unqueued_count_and_training_work():
    body = _function_body(CODE, "statusLine")
    assert " unqueued" in body
    assert " training remaining" in body
    assert "training time unavailable" in body
```

Add this local brace-matching helper rather than a regex that stops at the first nested brace:

```python
def _function_body(text: str, name: str) -> str:
    match = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", text)
    assert match, f"{name} function is missing"
    depth = 1
    index = match.end()
    while index < len(text) and depth:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    assert depth == 0, f"{name} function has unbalanced braces"
    return text[match.end() : index - 1]
```

Assert `buildRoster()` selects the Training comparator only for Training, the Missing comparator only for Missing, and `byName` for all other sections.

- [ ] **Step 2: Run the new page tests and verify failures**

```bash
uv run --no-sync python -m pytest tests/test_skills_page.py -k "training_rows_sort or missing_rows_sort or training_work" -v
```

Expected: failures because current Missing sort uses count and Training uses name.

- [ ] **Step 3: Implement stable raw-value comparators and row text**

In `skills.js`:

```javascript
function byTrainingFinishThenName(a, b) {
  var aTime = Date.parse(a.estimated_finish_utc || '');
  var bTime = Date.parse(b.estimated_finish_utc || '');
  var aKnown = !isNaN(aTime);
  var bKnown = !isNaN(bTime);
  if (aKnown !== bKnown) return aKnown ? -1 : 1;
  if (aKnown && aTime !== bTime) return aTime - bTime;
  return byName(a, b);
}

function byTrainingRemainingThenName(a, b) {
  var aKnown = typeof a.training_remaining_seconds === 'number';
  var bKnown = typeof b.training_remaining_seconds === 'number';
  if (aKnown !== bKnown) return aKnown ? -1 : 1;
  if (aKnown && a.training_remaining_seconds !== b.training_remaining_seconds) {
    return a.training_remaining_seconds - b.training_remaining_seconds;
  }
  return byName(a, b);
}
```

Choose comparators by section inside `buildRoster()`. Update `statusLine()`:

- Training with ETA: `N queued · ready in X`;
- Training unknown: `N queued · timing unknown`;
- Missing available: `N unqueued · X training remaining`;
- Missing unavailable: `N unqueued · training time unavailable`.

Use singular `1 queued`/`1 unqueued` without changing the nouns, matching concise EVE queue vocabulary.

- [ ] **Step 4: Write failing accessible-tooltip tests**

Assert the selected-plan header contains a real `<button>` with:

- id `skills-estimate-info`;
- `type="button"`;
- an `aria-label` that includes the estimate assumptions;
- a `data-tip` containing Omega speed, implants, and unlisted requirements;
- initially `hidden`.

Assert `renderHead()` hides it with no selected plan and reveals it with one. Assert a Missing status span receives the same `data-tip` for mouse discovery. Assert CSS gives the button a restrained treatment, adds `[data-tip]:focus-visible::after` to the existing tooltip primitive, and includes an explicit `.skills-estimate-info[hidden]` override because its base rule sets `display`.

- [ ] **Step 5: Add the tooltip affordance and row tooltip**

Place the information button immediately after `#skills-plan-count`, before Copy plan. Use the visible glyph `ⓘ`, `data-tip`, and an `aria-label` containing the same assumptions. Extend the existing CSS tooltip primitive from hover-only to hover plus `:focus-visible`; native `title` is insufficient because it does not reliably open on keyboard focus.

In `renderHead()`, toggle `.hidden` from selected-plan state. In `rowNode()`, assign the same `data-tip` to the Missing status span only; avoid putting it on the whole disclosure button, which already has a different action and accessible purpose.

Style it using existing tokens, no new color, with `display: inline-flex`, quiet text, no decorative background, inherited font, and:

```css
.skills-estimate-info[hidden] { display: none; }
```

The global `:focus-visible` rule must continue to provide at least 3:1 focus contrast.

- [ ] **Step 6: Expand the dev fixture and add fixture guards**

Update `dev.js` so the selected plan includes:

- at least three Training rows: two dated out of name order and one timing-unknown;
- at least four Missing rows: short, multi-week, equal-duration/name tie-break, and unavailable;
- one Missing row that represents mixed queued/unqueued requirements through `queued_count > 0` and `missing_count > 0`;
- one stale Missing row with a valid estimate;
- long character and missing-skill names.

Every character object gets all three estimate fields. Add lexical tests proving the fixture contains each status and sort edge rather than relying on a hand-maintained comment.

- [ ] **Step 7: Run page, convention, bridge, and fixture tests**

```bash
uv run --no-sync python -m pytest \
  tests/test_skills_page.py \
  tests/test_page_conventions.py \
  tests/test_bridge_contract.py \
  tests/test_dev_harness.py -v
```

Expected: all pass.

- [ ] **Step 8: Check the UI diff for floor-width hazards**

Inspect the rendered-text lengths and CSS tracks in the diff. Confirm:

- the 240px character-name track remains the row's identity anchor;
- the status remains one line at the 840px floor;
- missing names remain a second line with a stated remainder;
- no new card, route, modal, permanent hint line, or unreachable media query was added;
- every display-setting selector has `[hidden]` coverage.

Record any measurement that changes an existing CSS width in the adjacent CSS comment; otherwise do not change the measured widths.

- [ ] **Step 9: Commit collapsed-row comparison UI**

```bash
git add wingman/web/index.html wingman/web/skills.js wingman/web/style.css \
  wingman/web/dev.js tests/test_skills_page.py
git commit -m "feat: sort Skills roster by training time"
```

---

### Task 7: Manual contract and final verification

**Files:**
- Modify: `docs/smoke-checklist.md`
- Verify: all changed files

**Interfaces:**
- Consumes: completed vertical feature.
- Produces: documented Windows render checks and a release-ready verified branch.

- [ ] **Step 1: Add the manual Skills smoke cases**

Extend the existing Skills section of `docs/smoke-checklist.md` with concrete checks:

- At 840x625, long character names remain identifiable and every collapsed status stays on one line.
- Missing rows are shortest duration first; equal durations use character name; unavailable estimates are last.
- Training rows are earliest real queue finish first; timing-unknown rows are last.
- A mixed row reads `N unqueued` while its duration still includes queued plan SP.
- Stale retains its badge beside a valid last-good estimate.
- The estimate assumptions are absent as permanent copy, appear on mouse hover, appear on keyboard focus, and say Omega/current attributes, implants excluded, unlisted requirements excluded.
- No-plan and unrefreshed legacy states show no misleading zero-duration estimate.

- [ ] **Step 2: Run focused behavior suites**

```bash
uv run --no-sync python -m pytest \
  tests/test_eveskills_training.py \
  tests/test_eveskills_skillids.py \
  tests/test_eveskills_state.py \
  tests/test_eveskills_controller.py \
  tests/test_api_skills.py \
  tests/test_skills_wiring.py \
  tests/test_skills_page.py \
  tests/test_page_conventions.py \
  tests/test_bridge_contract.py \
  tests/test_dev_harness.py -v
```

Expected: all pass.

- [ ] **Step 3: Run all CI-equivalent automated gates**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: pytest passes with only the repository's documented platform skips; Ruff check and format check exit 0.

- [ ] **Step 4: Run the Windows/WebView2 smoke pass**

On Windows, open the Skills route with the updated `?dev=1` fixture and with one real refreshed character. Complete the new checklist at 840x625 and a wider size. Verify tooltip hover/focus, row text, both sort orders, unavailable data, stale data, and expansion/forget/reauth remain usable. Record the date/result in the implementation handoff; do not claim this pass if it was not actually performed.

- [ ] **Step 5: Inspect the complete diff for scope and invariants**

```bash
git diff main...HEAD --check
git diff --stat main...HEAD
git status --short
git log --oneline main..HEAD
```

Review every changed file for debug output, placeholders, partial estimate fallback, accidental OAuth-scope changes, network calls under the controller lock, public non-method `Api` attributes, and unrelated refactors.

- [ ] **Step 6: Commit smoke-checklist updates**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: add skill estimate smoke checks"
```

- [ ] **Step 7: Request final independent review**

Dispatch one fresh reviewer over the spec, this plan, and `main...HEAD`. Resolve Blocking/HIGH findings before branch completion; document any rejected finding with repository evidence.
