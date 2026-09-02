# Skills training remaining

Design. Base: `main` (`492b825`), 2026-09-02.

## Outcome

The Skills destination should answer not only who is missing plan requirements,
but which character is closest to completing them.

For the selected plan, each collapsed `Missing` row shows the character's
remaining plan-training duration and the section sorts shortest first. The
existing readiness sections remain intact. `Training` continues to use EVE's
actual queue finish time, now sorted by that finish time.

This extends the original “who can fly this?” workflow without turning Skills
into a queue editor, remap optimizer, or deadline planner.

## User-visible behavior

The roster keeps its existing section order:

1. Ready
2. Training
3. Locked
4. Missing
5. Unknown
6. Unscored

Rows and ordering behave as follows.

### Ready

Ready characters remain alphabetical.

### Training

A character whose remaining requirements are all queued keeps the authoritative
queue result:

> **Alice**  `2 queued · ready in 4d 2h`

Training rows sort by `estimated_finish_utc`, soonest first, then character
name. Rows whose queue timing is unknown sort after dated rows, then by name.
This ETA remains distinct from a calculated duration: it is EVE's actual queue
schedule and may include unrelated entries between plan requirements.

### Locked

Locked characters remain alphabetical. A trained-but-inactive requirement has
no remaining training cost and does not become `Missing` merely to support the
new estimate.

### Missing

A collapsed Missing row shows both the unqueued requirement count and total
remaining training work for the explicitly listed plan:

> **Bob**  `3 unqueued · 18d 6h training remaining`
>
> Heavy Assault Cruisers V, Medium Projectile Turret V, and 1 more

“Unqueued” is deliberate. A Missing plan may also contain requirements that are
already queued. The count covers requirements whose evaluator state is
`Missing`; the duration covers every explicitly listed plan requirement whose
current skill points are below its target, including queued requirements. It
does not include prerequisites omitted from the plan.

Missing rows sort by raw calculated duration, shortest first, then character
name. A character without a complete estimate renders:

> **Charlie**  `3 unqueued · training time unavailable`

Unavailable estimates sort after calculated estimates, then by name. The UI
never sorts formatted duration strings.

### Estimate assumptions

The assumptions do not occupy a permanent line. A muted, keyboard-focusable
information affordance beside the selected plan's requirement count exposes on
hover and focus:

> Estimates use current attributes at Omega speed. Implants and requirements
> not listed in this plan are excluded.

The duration text exposes the same tooltip. The affordance must have an
accessible name and visible focus treatment.

## Calculation contract

A pure Python estimator calculates attribute-rate training work. It receives
explicit values and performs no network or persistence work.

For each explicit plan requirement it:

1. Determines the canonical cumulative SP threshold for the target level,
   multiplied by the skill's training multiplier/rank.
2. Subtracts `skillpoints_in_skill`, treating an absent skill as zero SP and
   never producing a negative deficit.
3. Uses the skill's primary and secondary attributes to calculate its training
   rate from the character's current remapped attributes.
4. Converts the SP deficit to seconds and sums all requirement durations.

The result is an Omega-rate estimate with implant bonuses deliberately ignored.
It is training work, not wall-clock time and not a promised completion date.
The estimator sums unrounded per-requirement seconds and rounds the final total
up to the next whole second. Sorting uses that integer. Display formatting rounds
to the nearest minute and follows the existing two-unit convention (`2d 4h`,
`4h 20m`, `12m`); formatting never feeds back into sorting. Tests pin these
boundaries against canonical EVE level thresholds and training-rate fixtures
before production code depends on them.

Queued plan skills remain in the duration because they are still unfinished
training work. Trained-but-inactive skills contribute zero because their SP
threshold is already met. Requirement readiness and duration remain separate
concepts.

An estimate is all-or-nothing. A missing character-attributes snapshot, a
missing skills/SP snapshot, or missing training multiplier, primary attribute,
or secondary attribute yields an unavailable estimate. A skill absent from an
otherwise valid skills snapshot is the expected representation of zero SP, not
missing data. The system must not sum known requirements and present an
understated partial total.

## ESI and metadata acquisition

No OAuth scope is added. The current ESI OpenAPI assigns both character skills
and character attributes to `esi-skills.read_skills.v1`, which Wingman already
requires.

Character refresh retains `skillpoints_in_skill` from the existing skills
response and additionally requests `/characters/{character_id}/attributes/`.
Only the five remappable training attributes are needed; remap dates and counts
are not part of this feature.

Public `/universe/types/{type_id}/` responses already used during skill-name
resolution contain `dogma_attributes`. The richer metadata record retains:

- training multiplier/rank;
- primary attribute;
- secondary attribute;
- metadata fetch time/schema version.

The implementation must use named constants for the relevant dogma attribute
IDs and test them against captured type fixtures. Missing or malformed dogma
values make the estimate unavailable rather than falling back to guessed
values.

Existing cached skill IDs currently bypass type-detail lookup. The richer cache
therefore needs an explicit migration/backfill path for already-resolved plan
skills. Metadata expires after 30 days so gameplay-data changes cannot remain cached
forever. An expired record must refresh before it can support an estimate; a
failed refresh makes the estimate unavailable rather than silently using stale
training data. Backfill results are staged and published atomically; state
payload construction must not observe a partially enriched cache.

## Snapshot and failure behavior

Skills and queue remain the coherent core snapshot and keep their existing
all-or-nothing commit. Attribute estimation data is supplemental:

- an attribute request failure does not discard successfully refreshed skills
  and queue data;
- a failed attribute refresh makes the estimate unavailable for that refresh;
- persisted attributes carry their own confirmed timestamp and error/freshness
  state rather than borrowing the core snapshot's `fetched_utc`;
- an old attribute snapshot is not silently combined with newly refreshed SP;
- existing state documents without SP or attributes continue to load and show
  `training time unavailable` until one successful refresh.

Network work remains outside `SkillsController`'s mutation lock. The controller
continues to be the only state-document writer, with each state mutation and
save in the same critical section.

Public metadata failures likewise preserve readiness. They suppress only the
calculated estimate and surface enough internal reason data for expanded detail
or diagnostics without placing technical errors on collapsed rows.

## Controller and bridge payload

Python remains responsible for every semantic result. JavaScript formats no
training formula and infers no estimate from requirement counts.

Each character summary adds these estimate fields:

- `training_remaining_seconds`: a non-negative integer or `null`, used for
  sorting;
- `training_remaining_label`: the formatted duration or an empty string;
- `training_estimate_status`: `available`, `refresh_required`,
  `attributes_unavailable`, or `metadata_unavailable`.

The existing `estimated_finish_utc` remains the sole Training sort key and is
not renamed to the calculated duration. Technical status values do not appear
verbatim on collapsed rows; every non-available status renders as `training time
unavailable` there.

Plan and group selection already cross the bridge because they change Python
computation. The estimator runs for the currently selected plan and in-scope
characters as part of that state calculation; no page-local semantic duplicate
is introduced.

## Web presentation

The existing two-line collapsed row is retained. The first line gains the
count/time summary; the second line keeps up to three missing requirement names.
The change must fit the measured 840px viewport floor and the existing 240px
character-name track without hiding the character identity or forcing a third
line.

No new sort control is added. Training relevance is the default order within
Training and Missing, while the readiness sections continue to provide the
primary grouping. Ready, Locked, Unknown, and Unscored remain alphabetical.

The development fixture must include:

- short and multi-week estimates;
- equal estimates to exercise name tie-breaking;
- a Missing character with both queued and unqueued requirements;
- unavailable estimate data and an estimate attached to an existing stale core
  snapshot, which retains the character's normal stale badge;
- dated and timing-unknown Training rows;
- long character and skill names.

## Testing

### Pure estimator

Tests cover:

- canonical cumulative SP thresholds for levels I through V and multiple ranks;
- zero-SP and absent skills;
- partial progress within a level;
- no negative deficit when SP already meets the target;
- multiple primary/secondary attribute pairs;
- Omega-rate, implant-free calculations;
- queued requirements remaining part of training work;
- trained-but-inactive requirements contributing zero;
- deterministic rounding;
- all-or-nothing unavailable results for malformed or missing inputs.

### Acquisition and persistence

Tests cover:

- parsing and retaining `skillpoints_in_skill`;
- parsing character attributes under the existing authorization grant;
- core snapshot success when attribute acquisition fails;
- supplemental freshness/error behavior;
- backward-compatible loading of old character documents;
- metadata dogma parsing, named IDs, migration/backfill, expiry, malformed data,
  and atomic publication;
- controller lock and save invariants.

### Payload and page contracts

Tests cover:

- raw duration and label payload fields;
- Missing duration ordering, name tie-break, and unavailable-last behavior;
- Training queue-finish ordering and timing-unknown-last behavior;
- unchanged section order and readiness semantics;
- collapsed labels and missing-name summary;
- accessible tooltip registration and focusability;
- development-fixture completeness.

The lexical web tests do not execute JavaScript. The manual Skills section of
`docs/smoke-checklist.md` must therefore exercise the rendered row at the
minimum window size, tooltip mouse and keyboard access, stale/unavailable
states, and both sorting rules on Windows/WebView2.

## Out of scope

This version does not add:

- user deadlines or target dates;
- persisted plan schedules;
- actual ready-date prediction for Missing characters;
- implants or implant authorization;
- Alpha clone-rate detection or configuration;
- remap recommendations or optimization;
- prerequisite discovery for skills omitted from a plan;
- queue editing, reordering, or optimization;
- a user-selectable sort control;
- per-skill duration presentation in expanded details.

## Reference-project finding

`guarzo/canifly` validates the product need but does not provide the estimator.
Its product documents call for total training time, SP needed, and current-
attribute calculations. Its implementation only records the latest finish date
of relevant skills already in the EVE queue and displays days remaining. That
queue-derived behavior corresponds to Wingman's existing `Training` ETA; this
design adds the previously specified but unimplemented Missing-plan estimate.
