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
| 1 | `preview/store.py` onto `settings.update()` | **Deferred.** See below. |
| 2 | Autouse fixture isolating application state in tests | In |
| 3 | `_save` cannot distinguish "nothing ran" from "nothing read" | In |
| 4 | Restore-on-launch toggle reports success on a failed write | In |
| 5 | Enabling the toggle mid-session moves running clients | In |

### Why item 1 is deferred

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

`web/settings.js` is edited by both. That branch moves the *preview-enabled*
block out into a new `previews.js`; the client-layout card items 3 and 4
touch arrived with #23 and is not part of that move.

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

The method already skips the write when the stored value equals the wanted
one (`ui/api.py:1319`), for the reason `set_preview_enabled` documents at
`:1244-1256` — the page can emit a no-op toggle on re-render, and a rewrite
of the whole projected document for nothing is a real cost. That path
returns `persisted: True`: nothing needed writing, so nothing failed.

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
  calls `start(seed_placed=True)`.

Default `False` so the launch path reads as it does now and an unseeded
`start()` keeps its current meaning.

Clients that appear *after* the toggle are still placed: they are not in
`_placed`, and `_tick` finds them on the sweep that discovers them. Only the
set already running at the moment of the toggle is exempted.

`Scheduler.start` is idempotent (`ui/scheduler.py:32-37`), so a double
toggle re-seeds without doubling the tick rate.

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
- `start(seed_placed=True)` with two clients running: the first tick places
  neither.
- `start(seed_placed=True)` then a third client appears: the tick places
  only the third.
- `start()` with two clients running: the first tick places both
  (the launch path, unchanged).

Item 2 is verified by the suite itself plus the canary check: run with
`LOCALAPPDATA` at an empty directory and assert nothing is written there.

Full suite before and after, both numbers reported. Baseline on this branch
is 1070 passed, 4 skipped.

## What this slice does not do

- Item 1, for the reason recorded above.
- `set_preview_enabled`, which has item 4's shape and is out of scope.
- Any widening of `evewindows.list_eve_windows()`.
- Anything that reads EVE process memory, injects input, performs OCR, or
  automates gameplay. This slice touches no Win32 surface at all.
