# Preview follow-ups left behind by item 11

Design. Base: `main` (1425cd1), 2026-08-24.

## Outcome

Four of the five items `eve-preview-design.md` records under "Left behind by
item 11 (#23)". Each is small; none of them shares a file with roadmap items
7-10. `preview/host.py`, `preview/window.py` and `preview/chrome.py` are not
opened by this slice.

Two of the four fix a card that reports success it did not achieve. One stops
the test suite writing to the developer's real application state. One removes
a window placement nobody asked for.

## Scope, and one deferral

| # | Item | Status |
|---|------|--------|
| 1 | `preview/store.py` onto `settings.update()` | **Deferred — and it shipped elsewhere.** See below. |
| 2 | Autouse fixture isolating application state in tests | In |
| 3 | `_save` cannot distinguish "nothing ran" from "nothing read" | In |
| 4 | Restore-on-launch toggle reports success on a failed write | In |
| 5 | Enabling the toggle mid-session moves running clients | In |

### Why item 1 is deferred

> **Resolved while this branch was being implemented.** `#26 Preview hotkeys`
> merged the hotkeys branch to `main`, carrying `34cf48e Fix client-layout
> persistence silently no-op'd by the merge`. `preview/store.py` now writes
> inside `settings.update()`, and `settings.update()` itself is the
> context-manager form. Item 1 is **done**, by the branch this section
> predicted would do it. The reasoning below is kept as the record of why
> this slice did not race it.

It is already implemented, on an unmerged branch, in a shape incompatible
with the one main would give it.

`worktree-preview-hotkeys` (roadmap item 7) branched at `b2bac93` — before
#23 — and carries four relevant commits: `settings: add update()`,
`settings: route every writer through update()`, `settings: convert
save_bookmarks to update() too`, and a `store.py` retrofit. That retrofit
uses a **context manager**:

```python
with self._update_settings() as live:
    ...
```

Main's helper is `settings.update(read, mutate, path=None)` — a different
API for the same guarantee. Implementing item 1 here against main's form
would put two incompatible spellings of one idea on two branches, and the
merge would settle a design question by accident rather than on purpose.

That branch has to rebase onto main regardless: it predates #23, so it has
never seen `preview/clientlayout.py`, `clientwin32.py` or `placement.py`.
Item 1 belongs to whoever performs that rebase, because that is the moment
the two `update()` shapes have to be reconciled anyway.

Recorded here rather than dropped: `preview/store.py` on main still does
read-then-`save()`, and still has the window in which a concurrent writer is
reverted.

### Collision surface for the four that are in

`worktree-preview-hotkeys` does not contain `preview/clientlayout.py` or its
test module, so items 3 and 5 cannot conflict with it. Item 2 adds a file
that exists on neither branch. Item 4 touches `ui/api.py`, which that branch
edits heavily — but `set_restore_clients_on_launch` arrived with #23 and is
not present there, so any conflict is textual and mechanical.

`web/settings.js` is edited by both, but not in the same place. That
branch's 69 removed lines *are* the client-layout card — the block items 3
and 4 edit — showing as removals only because the branch predates #23 and
never had them. The preview-enabled block above it does not move; it stays
at `web/settings.js:211-232` on main and at `:200-232` there. So the rebase
re-adds the card wholesale, and edits made inside it here cannot conflict
textually with anything that branch contains.

## Item 2 — the suite writes to real application state

### What is actually wrong

`eve-preview-design.md:522-528` describes this as two tests in
`tests/test_api_bookmarks.py` reaching `settings_mod.save` with nothing
redirecting `paths.settings_file()`. That description no longer matches the
code: every test in that module goes through an `api` fixture
(`tests/test_api_bookmarks.py:49-59`) which monkeypatches
`api_mod.paths.settings_file` — and because `api_mod.paths` is the module
object, that patch is global.

The leak is nonetheless real, and wider than described. Running the suite
with `LOCALAPPDATA` pointed at an empty directory produces two files:

```
$CANARY/OBSYouTubeUploader/settings.json
$CANARY/OBSYouTubeUploader/durations.json
```

So `durations.json` leaks too, which the entry did not notice.

### Why not the fix the entry proposes

An autouse fixture patching `paths.settings_file()` would break
`tests/test_paths.py:16-19`, which sets `LOCALAPPDATA` itself and then
asserts on the real function's return value:

```python
monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
root = tmp_path / "OBSYouTubeUploader"
assert paths.settings_file() == root / "settings.json"
```

That is a test legitimately depending on the unpatched path, which the task
asked to be reported rather than worked around.

### The fix

Redirect `state_dir()` at its one real input instead — the environment
variable it reads at `paths.py:16`:

```python
@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
```

Every derived path moves together: `settings.json`, `durations.json`,
`token.json`, `seen.json`, `logs/`, `tmp/`. `test_paths.py` keeps passing
because its own `setenv` runs inside the test and wins. Verified: the full
suite passes and the canary directory stays empty.

`testpaths = ["tests"]` (`pyproject.toml:70-71`), so the file is
`tests/conftest.py`.

Existing per-test stubs stay. They are now belt-and-braces rather than the
only guard, and each one carries a comment explaining a hazard that deleting
the stub would delete too — `tests/test_preview_wiring.py:238-241` is the
clearest example.

## Item 3 — "No named clients are running" when every read failed

`clientlayout._save` (`preview/clientlayout.py:89-103`) returns
`{"saved": 0, "persisted": True}` for two unrelated outcomes: no named
client was running, and every named client's `read_placement` returned
`None`. The second logs a warning per client (`clientlayout.py:96`); the
page says "No named clients are running. Nothing to save."
(`web/settings.js:270`), which is false.

### Decision: a new `failed` field

`_save` returns `{"saved": n, "persisted": bool, "failed": m}`, where `m`
counts named clients whose placement could not be read.

A third field rather than a reinterpretation of `saved` or `persisted`,
because those two keep exactly their current meanings and the page reads
them unchanged. A frontend that has not been updated degrades to today's
behaviour instead of misreading a field whose meaning moved underneath it.

This also closes a second, unlisted lie in the same function. Today, five
clients running with two unreadable reports "Saved 3 client positions" and
never mentions the two. `failed` makes that sayable.

### The card

```
!res.persisted            -> "Could not write client positions to settings."
!res.saved && res.failed  -> "Could not read the position of any running client."
!res.saved                -> "No named clients are running. Nothing to save."
res.saved && res.failed   -> "Saved N. Could not read M."
otherwise                 -> "Saved N client positions."
```

First and last branches are unchanged. Third is now true when it fires.

`Api.save_client_layout`'s no-manager early return (`ui/api.py:1301-1302`)
gains `"failed": 0` so one shape comes back on every path;
`tests/test_preview_wiring.py:278` asserts that dict exactly and is updated.

## Item 4 — the toggle reports success on a failed write

`Api.set_restore_clients_on_launch` (`ui/api.py:1310-1340`) catches `OSError`
from `settings_mod.update`, logs it, and returns `True`. The checkbox stays
checked and the choice is gone at the next restart.

### The complication

The obvious fix — return `False` — collides with a decision #23 made on
purpose. `tests/test_preview_wiring.py:305-311` pins it:

> `test_an_unwritable_settings_file_does_not_block_the_watcher`
> "Same posture as `set_preview_enabled`: the feature still works."

The watcher *does* start. Returning `False` makes `web/settings.js:256`
uncheck the box while the thing it describes is running — one lie traded for
a different one.

### Decision: the save button's `persisted` key

```python
return {"applied": True, "persisted": persisted}
```

This is what "make the two consistent" should mean: the same key, carrying
the same fact, as the save button four lines away in the same card.

- The watcher still starts or stops. #23's decision survives.
- The checkbox stays checked, which is true — restore-on-launch *is* on.
- The message carries the real news: it will not survive a restart.

### The skip-guard makes `persisted` a lie unless it is tracked

> **Overtaken by `#26`.** The tracked flag described below is **not
> implemented**, and the plan does not build it. `settings.update()` is now a
> context manager that *restores the live dict when the block raises*, so a
> failed write no longer leaves memory holding the wanted value. The guard
> sees a real change on the next call and retries by itself. The flag would
> defend against a state the code can no longer reach.
>
> What survives is the requirement, not the mechanism: a failed write must
> still be retried rather than skipped. The plan pins that with a test that
> exercises the real `update()` and fakes only the disk write, so the
> behaviour stays covered whichever layer provides it.

The method skips the write when the stored value already equals the wanted
one (`ui/api.py:1319`), for the reason `set_preview_enabled` documents at
`:1244-1256` — a rewrite of the whole projected document for nothing is a
real cost.

That guard reads memory, and `settings.update` mutates memory *before* the
write can fail (`settings.py:213-216`, `ui/api.py:1319-1334` retains the
mutation deliberately). So after a failed write the document is dirty: a
later call with the same value finds memory already correct, skips the
write, and would return `persisted: True` while the disk still holds the old
value. The contract would be false in exactly the case it exists to report.

The fix is to make the guard consult the write, not only the value:

```python
self._restore_launch_persisted = True     # in __init__

wanted_change = section.get("restore_clients_on_launch") != enabled
if wanted_change or not self._restore_launch_persisted:
    ...
    try:
        settings_mod.update(lambda: self._state.settings, mutate)
        self._restore_launch_persisted = True
    except OSError:
        self._restore_launch_persisted = False
        logger.exception("Could not persist the client-restore setting")
```

Two things follow, both wanted. `persisted` becomes true only when the value
is genuinely on disk. And a failed write **self-heals**: the next call
retries rather than skipping, so a settings file that was briefly unwritable
recovers without the user knowing there was anything to recover from.

No production caller currently makes a repeat same-value call — the one
caller is a `change` listener (`web/settings.js:255`), and `change` fires
only on a real transition; the re-render path assigns `box.checked` without
dispatching (`:299`). This is therefore a latent hole rather than a live
bug. It is closed anyway: roadmap item 8 adds Previews-tab UI over
`ui/api.py`, and a second caller is precisely how a latent hole becomes a
live one.

A dict is always truthy, so the existing bridge-failure guard keeps working
unchanged — `WM.send` resolves to `null` on a bridge error
(`web/app.js:38-43`), and `null` is still the only thing that reverts the
box:

```js
.then(function (res) {
  if (!res) { box.checked = !wanted; return; }
  if (!res.persisted) {
    say('Restore-on-launch is on for this session, but could not be '
      + 'written to settings — it will not survive a restart.');
  }
});
```

Return type moves from `bool` to `dict`; `tests/test_preview_wiring.py:280`
asserts `is True` and is updated.

`set_preview_enabled` is untouched. It has the same shape and predates this
work; changing it is a separate decision with its own frontend.

## Item 5 — enabling the toggle mid-session moves running clients

`_placed` starts empty, so the first `_tick` two seconds after `start()`
treats every running client as fresh and places it
(`preview/clientlayout.py:158-175`). At launch that is the whole point. From
the toggle it moves windows the user did not ask to move.

### Decision: fix it

The task noted "leave it" is defensible. It is not chosen, for a reason
specific to this module: the capability the surprise placement provides
already exists, deliberately, as a button.

`restore_now()` (`clientlayout.py:63-71`) is the documented "re-place a
client without restarting it" path, wired to the Restore button four lines
from the checkbox in the same card. The mid-session placement is not giving
the user something they otherwise lack — it is duplicating a button they did
not press, on a two-second delay, with no undo.

`_prune`'s own docstring already names this failure:

> "Pruning immediately would let a transient miss re-place a running client
> the user has since dragged — which is exactly the undraggable window
> place-once exists to prevent, arriving through a side door."

Enabling the toggle mid-session is another side door to the same room.

### The change

```python
def start(self, seed_placed: bool = False) -> None:
    if seed_placed:
        with self._lock:
            self._placed |= set(self._named())
    self._scheduler.start()
```

The two call sites are already separate, so nothing new has to be plumbed:

- `Api.start_client_layouts_if_enabled` (`ui/api.py:1291-1297`), at launch —
  calls `start()`, unchanged.
- `Api.set_restore_clients_on_launch` (`ui/api.py:1337`), from the toggle —
  calls `start(seed_placed=wanted_change)`.

Seeding is bound to the **transition**, not to the call. `start()` runs on
every enabled call, including one whose value was already enabled, and
seeding unconditionally there would add clients that appeared *since* the
toggle to `_placed` — suppressing the restore they were owed.
`Scheduler.start` is idempotent (`ui/scheduler.py:32-37`), but that only
prevents a second timer; it does nothing about a side effect placed in front
of it. `wanted_change` is the same flag item 4 computes, so the two fixes
share one variable.

Default `False` so the launch path reads as it does now and an unseeded
`start()` keeps its current meaning.

Clients that appear *after* the toggle are still placed: they are not in
`_placed`, and `_tick` finds them on the sweep that discovers them. Only the
set already running at the moment of the toggle is exempted.

`Scheduler.start` is idempotent (`ui/scheduler.py:32-37`), so a repeat
enabled call re-arms nothing and, with the transition flag above, re-seeds
nothing either.

## Testing

`tests/test_preview_clientlayout.py`'s `Harness` is the pattern for items 3
and 5 and is extended, not replaced. It already supports everything both
need: `placements` maps hwnd to placement, so an absent key makes
`read_placement` return `None` — item 3's failure case with no new
machinery — and `timer` is injectable through `manager(**kw)`, so item 5's
seeding is observable without the scheduler ever firing.

Item 4 extends `tests/test_preview_wiring.py`, whose `_no_disk` helper
(`:238-246`) already stubs `settings_mod.update`; its `raise`-ing variant at
`:305-311` becomes the failed-persist case.

Behaviour to pin:

- `_save` with every read failing: `saved == 0`, `failed == n`.
- `_save` with a partial read: `saved + failed` equals the number of named
  clients.
- `_save` with nothing running: `saved == 0`, `failed == 0`.
- Toggle with a raising `update`: `persisted is False`, and the watcher
  started anyway.
- Toggle with a working `update`: `persisted is True`.
- Toggle raises, then the same value is sent again: the second call
  **retries** the write rather than skipping it, and reports the retry's
  outcome. This is the contract hole; it needs a test or it comes back.
- Toggle to a value that is already stored, with a healthy `update`: no
  write is attempted, and `persisted is True`.
- `start(seed_placed=True)` with two clients running: the first tick places
  neither.
- `start(seed_placed=True)` then a third client appears: the tick places
  only the third.
- Repeat enabled toggle while a client has appeared but not yet ticked: that
  client is still placed — seeding is bound to the transition, so the
  no-op call does not consume it.
- `start()` with two clients running: the first tick places both
  (the launch path, unchanged).

Item 2 is verified by the suite itself plus the canary check: run with
`LOCALAPPDATA` at an empty directory and assert nothing is written there.

Full suite before and after, both numbers reported. Baseline on this branch
is 1371 passed, 4 skipped.

## Known limits, recorded rather than fixed

Surfaced by the whole-branch review. None is a defect in this slice; each is
something the next person over this code would otherwise have to rediscover.

**The design's own justification for item 4 is weaker than it reads.** This
document argues the checkbox should stay checked after a failed write because
"the watcher really is on". That holds for the toggle's own round-trip. It does
not hold across an unrelated settings push: `#26`'s `update()` reverts the live
dict on failure, so `_settings_payload()` ships the *old* value and the
`wm:settings` listener assigns `box.checked` from it — unchecking a box whose
watcher is running. This is a consequence of `#26`, not of this branch, and the
branch strictly improves on what came before (the same revert-and-repaint
happened, with no message at all to explain it). But the next person to revisit
this card should not read the justification above and assume it covers more
than it does.

**A failed `EnumWindows` at seed time seeds nothing.** `start(seed_placed=True)`
seeds from `_named()`, and discovery returns `[]` when enumeration fails. An
empty seed means the first tick treats every running client as fresh and places
it — exactly what item 5 removes. The window is one enumeration wide, on a
user-initiated action, and the module already accepts this class of miss
elsewhere ("an EMPTY result prunes nothing"). Not worth new machinery; worth
knowing about.

**Two adjacent toggles now have different contracts.** `set_preview_enabled`
returns bare `True` and swallows `OSError`; `set_restore_clients_on_launch`
returns a dict and reports. That asymmetry is the stated exclusion above, not
an accident. The next slice over `ui/api.py` inherits the choice of whether to
close it.

**`applied` is never read by the page.** The toggle returns
`{"applied": True, "persisted": bool}` and `settings.js` checks only `!res` and
`res.persisted`. `applied` earns its place by mirroring the save button's
`saved`/`persisted` pairing — the coherence this slice was buying — not by
being consumed.

**The `failed`-branch source assertion has a blind spot.** It pins that
"No named clients are running" sits behind a `res.failed` check, but it would
still pass if the ternary's arms were swapped, since its split anchor sits
after the token either way. That is the cost Ruling 2 accepted when this repo
declined to add a JS test runner.

**The autouse fixture costs about 20% of suite wall-clock** (11.4s → 13.9s
measured), because every test now materialises a `tmp_path`. Acceptable for
per-test isolation of real application state.

## What this slice does not do

- Item 1, for the reason recorded above.
- `set_preview_enabled`, which has item 4's shape and is out of scope.
- Any widening of `evewindows.list_eve_windows()`.
- Anything that reads EVE process memory, injects input, performs OCR, or
  automates gameplay. This slice touches no Win32 surface at all.
