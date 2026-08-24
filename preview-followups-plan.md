# Preview follow-ups implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land four of the five follow-ups `eve-preview-design.md` records under "Left behind by item 11 (#23)": isolate application state in tests, and make the EVE client-layout card stop reporting successes it did not achieve.

**Architecture:** Four independent changes to existing modules. No new production module; one new test file (`tests/conftest.py`). Items 4 and 5 both edit `Api.set_restore_clients_on_launch` and share one local, so Task 4 must land before Task 5.

**Tech Stack:** Python 3.11, pytest, monkeypatch. Vanilla ES5-style browser JS (no build step, no framework, no JS test runner).

**Spec:** `preview-followups-design.md`

## Global Constraints

- **Do not open** `obs_youtube_uploader/preview/host.py`, `preview/window.py`, or `preview/chrome.py`. Roadmap items 7-10 own them.
- **Do not change** `Api.set_preview_enabled`. It has Task 4's shape and is deliberately out of scope.
- **Do not** implement item 1 (`preview/store.py` onto `settings.update()`). **It shipped on main in `#26`** — `store.py` already writes inside `settings.update()`. Nothing to do.
- **Do not** widen `evewindows.list_eve_windows()`.
- No Win32 calls in tests. CI is `ubuntu-latest` only (`.github/workflows/ci.yml:10`); nothing Win32 executes there.
- No formatter or linter is configured. Match the surrounding file's style: 4-space indent, comments wrapped near 72 columns, code near 79.
- Comments explain **intent and tradeoffs**, never restate the code. This repo's existing comments are the standard to match.
- Baseline before Task 2: **1280 passed, 4 skipped** (on base `9dc9435`).
- **`settings.update()` is a context manager**: `with settings_mod.update(doc) as d:` — NOT `update(read, mutate, path)`. It holds `_SAVE_LOCK` across the block AND **restores the live dict if the block raises**, so a failed write never leaves memory and disk disagreeing.
- **Never hold a reference to `doc["preview"]` across an `update()` call.** `_normalize` reassigns the nested sections wholesale on every call, so an inner-dict reference goes stale even though the document reference does not. Read what you need before the block, or re-read inside it.
- Never call `save()` or `update()` from inside an `update()` block — `_SAVE_LOCK` is not reentrant and the process deadlocks.

---

## File structure

| File | Change | Task |
|------|--------|------|
| `tests/conftest.py` | Create — autouse state-dir isolation | 1 |
| `obs_youtube_uploader/preview/clientlayout.py` | `_save` counts unreadable clients; `start()` gains `seed_placed` | 2, 5 |
| `obs_youtube_uploader/ui/api.py` | `save_client_layout` shape; `set_restore_clients_on_launch` returns a dict and tracks persistence; passes `seed_placed` | 2, 4, 5 |
| `obs_youtube_uploader/web/settings.js` | Card reports the `failed` count and the unpersisted toggle | 2, 4 |
| `tests/test_preview_clientlayout.py` | Extend `Harness`-based tests | 2, 5 |
| `tests/test_preview_wiring.py` | Extend `FakeClientLayouts` and `_no_disk` tests | 2, 4, 5 |

---

## Task 1: Isolate application state in the test suite

> **DONE** — commit `8200ad7` (after two rebases), review clean. The counts in
> the steps below (1070/4) were the pre-rebase baseline; the bisect was re-run
> on the current base and the docstring's 15 / 1 / 3 figures still hold.

Item 2. Independent of every other task. Land it first so later runs are already isolated.

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an autouse fixture. No symbol other tasks import.

**Background the implementer needs:** `paths.state_dir()` (`obs_youtube_uploader/paths.py:14-20`) reads `LOCALAPPDATA` and falls back to `~/.local/share/OBSYouTubeUploader`. Every other path in `paths.py` derives from it. Today the suite writes two real files into whichever of those applies on the developer's machine.

The leak was bisected file-by-file and then test-by-test. Three independent
mechanisms produce it, and **none** of them is `save_bookmarks` — every test
in `tests/test_api_bookmarks.py` already redirects `paths.settings_file()`
through its `api` fixture (`:49-59`) and leaks nothing:

| Where | Count | Mechanism |
|-------|-------|-----------|
| `tests/test_api_upload.py` | 15 tests | the upload worker persisting the channel title (`ui/api.py:748-750`) |
| `tests/test_api_upload.py` | 1 of those | the probe cache writing `durations.json` |
| `tests/test_preview_wiring.py` | 3 tests | `set_preview_enabled` (`ui/api.py:1259`) |

That spread is the argument for a fixture rather than three more stubs.

Do **not** monkeypatch `paths.settings_file()`. `tests/test_paths.py:16-19` sets `LOCALAPPDATA` itself and then asserts on that function's real return value; patching it breaks that test. Redirecting the environment variable instead lets the test's own `setenv` win, because it runs inside the test body.

- [ ] **Step 1: Reproduce the leak**

```bash
rm -rf /tmp/canary-before
mkdir -p /tmp/canary-before
LOCALAPPDATA=/tmp/canary-before python -m pytest -q
find /tmp/canary-before -type f
```

`mkdir -p` after the `rm -rf` matters: once the fixture works the directory
is never created, and `find` on a missing path errors instead of printing
nothing — which reads as a failure when it is the result you want.

Expected: `1070 passed, 4 skipped`, and `find` lists exactly two files:

```
/tmp/canary-before/OBSYouTubeUploader/settings.json
/tmp/canary-before/OBSYouTubeUploader/durations.json
```

If `find` prints nothing, stop — the leak is already fixed and this task needs re-scoping before you write anything.

- [ ] **Step 2: Create the fixture**

Create `tests/conftest.py`:

```python
"""Suite-wide isolation of the application's state directory.

Two files used to land in the developer's real state directory on every
run. Not through save_bookmarks -- test_api_bookmarks.py already
redirects settings_file() in its api fixture -- but through three other
paths nobody had stubbed: the upload worker persisting the channel title
(api.py:748-750, 15 tests in test_api_upload.py), the probe cache
writing durations.json, and set_preview_enabled (api.py:1259, 3 tests in
test_preview_wiring.py). Per-test stubs closed the instances someone
noticed; this closes the class.

LOCALAPPDATA rather than paths.settings_file(): state_dir() reads that
one variable (paths.py:14-20) and every other path derives from it, so
redirecting it moves settings, durations, token, seen, logs and tmp
together. Patching settings_file() would also break test_paths.py:16-19,
which sets this same variable and then asserts on the real function.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch):
    """Point paths.state_dir() at this test's tmp_path.

    Autouse and unreferenced by design: a test that has to remember to
    ask for isolation is a test that will forget.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
```

- [ ] **Step 3: Verify the leak is closed and nothing broke**

```bash
rm -rf /tmp/canary-after
mkdir -p /tmp/canary-after
LOCALAPPDATA=/tmp/canary-after python -m pytest -q
find /tmp/canary-after -type f
```

Expected: `1070 passed, 4 skipped`, and `find` prints **nothing**.

- [ ] **Step 4: Verify test_paths still exercises the real function**

```bash
python -m pytest tests/test_paths.py -v
```

Expected: all pass. This is the test that would have broken under the fix the design entry originally proposed; it passing is the point of the check.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py
git commit -m "test: stop the suite writing to the real state directory

Every run wrote settings.json and durations.json into the developer's
LOCALAPPDATA. Redirect state_dir()'s one input rather than patching
settings_file(), which test_paths.py asserts on directly."
```

---

## Task 2: `_save` distinguishes "nothing ran" from "nothing read"

Item 3. Depends on nothing; Task 1 first only for hygiene.

**Files:**
- Modify: `obs_youtube_uploader/preview/clientlayout.py:89-103` (`_save`)
- Modify: `obs_youtube_uploader/ui/api.py:1458-1462` (`save_client_layout`)
- Modify: `obs_youtube_uploader/web/settings.js:260-276`
- Test: `tests/test_preview_clientlayout.py`, `tests/test_preview_wiring.py`

**Note on the base:** `#26` rewrote `_persist` (the method *below* `_save`) for
the new context-manager `settings.update()`. `_save` itself is untouched and
the code block below still applies verbatim. Do not change `_persist`.

**Interfaces:**
- Consumes: nothing.
- Produces: `ClientLayoutManager._save()` and therefore `save_now()` return `{"saved": int, "persisted": bool, "failed": int}`. `Api.save_client_layout()` returns the same three keys on every path. Task 4 and Task 5 do not touch this shape.

**Background:** `_save` returns `saved: 0` both when no named client was running and when every named client's `read_placement` returned `None`. The page then says "No named clients are running", which is false in the second case. `failed` counts the clients that already produce the warning at `clientlayout.py:96`. Clients at character select are filtered out by `_named()` before the read, so they are never counted as failures.

- [ ] **Step 1: Write the failing tests**

Append to the `# ---- save` section of `tests/test_preview_clientlayout.py`, after `test_save_does_not_write_when_it_found_nothing`:

```python
def test_save_separates_nothing_running_from_nothing_readable():
    """Both return saved: 0. Reporting "no clients are running" for the
    second is false, and the user retries a button that cannot work."""
    nothing_running = Harness(clients=[])
    assert nothing_running.manager().save_now() == {
        "saved": 0, "persisted": True, "failed": 0}

    none_readable = Harness(clients=[client("Pilot One", 1),
                                     client("Pilot Two", 2)])
    assert none_readable.manager().save_now() == {
        "saved": 0, "persisted": True, "failed": 2}


def test_save_reports_the_clients_it_could_not_read():
    """Saying "Saved 1" while silently dropping the other is how a
    missing client position goes unnoticed until the next restart."""
    h = Harness(clients=[client("Good", 1), client("Unreadable", 2)],
                placements={1: Placement(Rect(0, 0, 800, 600))})
    assert h.manager().save_now() == {
        "saved": 1, "persisted": True, "failed": 1}


def test_save_does_not_count_character_select_clients_as_failures():
    """They are excluded before any read is attempted, so they are not a
    failure to report -- reporting them would send the user hunting for
    a problem that does not exist."""
    h = Harness(clients=[client("hwnd:0xdead", 1)])
    assert h.manager().save_now()["failed"] == 0
```

Update the three existing assertions in that file that compare the whole dict:

```python
# test_save_stores_every_named_client
    assert h.manager().save_now() == {"saved": 2, "persisted": True,
                                      "failed": 0}

# test_save_reports_a_failed_write_rather_than_a_false_success
    assert h.manager().save_now() == {"saved": 1, "persisted": False,
                                      "failed": 0}

# test_save_does_not_write_when_it_found_nothing
    assert h.manager().save_now() == {"saved": 0, "persisted": True,
                                      "failed": 0}
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python -m pytest tests/test_preview_clientlayout.py -v -k save
```

Expected: FAIL. The new tests fail on a missing `failed` key; the three updated ones fail on the dict comparison.

- [ ] **Step 3: Implement**

Replace `_save` in `obs_youtube_uploader/preview/clientlayout.py:89-103`:

```python
    def _save(self) -> dict:
        found = {}
        failed = 0
        with self._dpi_context():
            origin = self._work_area_origin()
            for key, c in self._named().items():
                p = self._read_placement(c.hwnd, origin)
                if p is None:
                    logger.warning("Could not read placement for %s", key)
                    # Counted, not just logged: saved: 0 alone cannot tell
                    # the page whether nothing was running or nothing could
                    # be read, and those need different messages.
                    failed += 1
                    continue
                found[key] = p
        if not found:
            return {"saved": 0, "persisted": True, "failed": failed}
        persisted = self._persist(found)
        logger.info("Saved %d client window positions", len(found))
        return {"saved": len(found), "persisted": persisted,
                "failed": failed}
```

- [ ] **Step 4: Run them to verify they pass**

```bash
python -m pytest tests/test_preview_clientlayout.py -v -k save
```

Expected: PASS.

- [ ] **Step 5: Write the failing wiring test**

In `tests/test_preview_wiring.py`, update `FakeClientLayouts.save_now` so the fake returns the real shape:

```python
    def save_now(self):
        self.saves += 1
        return {"saved": 3, "persisted": True, "failed": 0}
```

Update the two assertions that compare the whole dict:

```python
# test_save_client_layout_passes_the_count_through
    assert api.save_client_layout() == {"saved": 3, "persisted": True,
                                        "failed": 0}

# test_the_client_layout_endpoints_are_no_ops_without_a_manager
    assert api.save_client_layout() == {"saved": 0, "persisted": True,
                                        "failed": 0}
```

- [ ] **Step 6: Run it to verify it fails**

```bash
python -m pytest tests/test_preview_wiring.py -v -k client_layout
```

Expected: FAIL on `test_the_client_layout_endpoints_are_no_ops_without_a_manager` — the no-manager path still returns two keys.

- [ ] **Step 7: Implement the Api passthrough**

In `obs_youtube_uploader/ui/api.py`, change the early return in `save_client_layout` (`:1458`):

```python
    def save_client_layout(self) -> dict:
        """Snapshot where every named client sits."""
        if self._client_layouts is None:
            # Same three keys as the manager's, so the page never has to
            # ask which path produced the answer.
            return {"saved": 0, "persisted": True, "failed": 0}
        return self._client_layouts.save_now()
```

- [ ] **Step 8: Run it to verify it passes**

```bash
python -m pytest tests/test_preview_wiring.py -v -k client_layout
```

Expected: PASS.

- [ ] **Step 9: Write the failing card test**

There is no JS test runner in this repo, and no plan to add one. The
established substitute is to assert on the frontend's **source text** from
pytest — `tests/test_preview_wiring.py:415-427` already reads `index.html`
and asserts the card's element ids are in the previews route, and
`tests/test_settingsui_copy.py` exists for the same reason ("the dialog
itself has no test harness"). This pins the specific regression: the false
message becoming reachable again.

Append to `tests/test_preview_wiring.py`:

```python
def test_the_save_button_does_not_blame_an_empty_desktop_for_a_read_failure():
    """saved: 0 has two causes and the card used to name only one. The
    page has no test harness, so this asserts on its source the way
    test_the_client_window_card_lives_on_the_previews_route does."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / "obs_youtube_uploader" / "web"
          / "settings.js").read_text(encoding="utf-8")
    block = js.split("save_client_layout")[1]
    assert "res.failed" in block, "the count is returned but never read"
    # The "nothing is running" message must sit behind a res.failed check,
    # not fire for every saved: 0.
    guard = block.split("No named clients are running")[0]
    assert "res.failed" in guard.split("if (!res.saved)")[1]
```

- [ ] **Step 10: Run it to verify it fails**

```bash
python -m pytest tests/test_preview_wiring.py -v -k empty_desktop
```

Expected: FAIL — `settings.js` does not mention `res.failed` yet.

- [ ] **Step 11: Make the card tell the truth**

In `obs_youtube_uploader/web/settings.js`, replace the `save.addEventListener` block (`:260-276`):

```javascript
  save.addEventListener('click', function () {
    WM.send('save_client_layout').then(function (res) {
      if (!res) { say('Could not save client positions.'); return; }
      if (!res.persisted) {
        // Saying "Saved N" after the write failed is a lie the user
        // discovers at their next restart.
        say('Could not write client positions to settings.');
        return;
      }
      if (!res.saved) {
        // `failed` is what separates "nothing was running" from "every
        // running client refused to be read". Only the log could tell
        // them apart before (clientlayout.py:96).
        say(res.failed
            ? 'Could not read the position of any running client.'
            : 'No named clients are running. Nothing to save.');
        return;
      }
      if (res.failed) {
        say('Saved ' + plural(res.saved, 'client position.',
                              'client positions.')
            + ' Could not read ' + plural(res.failed, 'other.',
                                          'others.'));
        return;
      }
      say('Saved ' + plural(res.saved, 'client position.',
                            'client positions.'));
    });
  });
```

- [ ] **Step 12: Run the full suite**

```bash
python -m pytest -q
```

Expected: `1284 passed, 4 skipped` (four tests added).

- [ ] **Step 13: Commit**

```bash
git add obs_youtube_uploader/preview/clientlayout.py \
        obs_youtube_uploader/ui/api.py \
        obs_youtube_uploader/web/settings.js \
        tests/test_preview_clientlayout.py \
        tests/test_preview_wiring.py
git commit -m "preview: report the client positions that could not be read

_save returned saved: 0 both when nothing was running and when every
placement read failed, and the card claimed the first. A failed count
separates them, and also surfaces the partial case that used to be
silent."
```

---

## Task 3: Bookkeeping — none

Deliberately empty so the numbering matches the design's item numbers. Item 1 is deferred; there is no Task 3.

---

## Task 4: The toggle reports a failed write

Item 4. Must land before Task 5 — Task 5 reuses the `wanted_change` local this task introduces.

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py:1469-1505` (`set_restore_clients_on_launch`)
- Modify: `obs_youtube_uploader/web/settings.js:251-258`
- Test: `tests/test_preview_wiring.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Api.set_restore_clients_on_launch(enabled)` returns `{"applied": True, "persisted": bool}` — was `True`. Introduces the local `wanted_change: bool`, which Task 5 passes to `start()`.

**Background the implementer needs, in full:**

The method still returns a bare `True` and still swallows `OSError`
(`ui/api.py:1497-1501`), so the user's choice can vanish at the next restart
with nothing said. That is the bug.

Returning `False` instead is **wrong here**, and there is a test that says so:
`tests/test_preview_wiring.py` pins "an unwritable settings file does not
block the watcher — the feature still works". The watcher genuinely starts, so
unchecking the box would be a different lie. `{"applied": True, "persisted": bool}`
is the save button's own shape, four lines away in the same card.

A dict is always truthy, so the page's existing bridge-failure guard still
works: `WM.send` resolves to `null` on a bridge error (`web/app.js:38-43`), and
only `null` reverts the box.

**What `#26` changed, and what it removes from this task.** An earlier draft of
this task carried an `Api._restore_launch_persisted` flag, because the old
`settings.update(read, mutate)` mutated the document *before* the write could
fail — leaving memory holding the wanted value, so the `!=` guard would skip
every retry and report success forever. The new `settings.update()` **restores
the live dict when the block raises**. After a failed write the stored value
still reads as the old one, so the next call sees a real change and retries by
itself. **Do not add a dirty flag.** There is no state left for it to track.

Keep `wanted_change` as a local — Task 5 consumes it.

Read `section` *before* the `update()` block and do not touch it afterwards:
`_normalize` reassigns `doc["preview"]` wholesale inside the call, so the
reference goes stale.

- [ ] **Step 1: Write the failing tests**

In `tests/test_preview_wiring.py`, update the three existing assertions that expect `is True`:

```python
# test_the_client_layout_endpoints_are_no_ops_without_a_manager
    assert api.set_restore_clients_on_launch(True) == {
        "applied": True, "persisted": True}

# test_enabling_restore_on_launch_starts_the_watcher
    assert api.set_restore_clients_on_launch(True) == {
        "applied": True, "persisted": True}

# test_an_unwritable_settings_file_does_not_block_the_watcher
    assert api.set_restore_clients_on_launch(True) == {
        "applied": True, "persisted": False}
```

Then append these three tests to the same file. They need `contextlib` and
`copy` at the top of the module — both are already imported there for
`_no_disk`.

```python
def test_a_failed_persist_is_reported_rather_than_claimed_as_success(
        tmp_path, monkeypatch):
    """The checkbox stays checked -- the watcher really is running -- but
    the page has to be able to say the choice is gone at restart."""
    from obs_youtube_uploader.ui import api as api_mod

    def boom(_data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "update", boom)
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {}
    assert api.set_restore_clients_on_launch(True)["persisted"] is False
    assert manager.started == 1


def test_a_failed_write_lets_the_next_toggle_retry(tmp_path, monkeypatch):
    """settings.update() restores the live dict when the block raises, so
    the stored value still reads as the OLD one and the next call sees a
    real change. This method therefore needs no dirty-flag of its own --
    but the retry must keep working if update() ever stops providing it,
    so it is pinned here rather than assumed.

    Stubs _save_locked, not update(): the point is to exercise the REAL
    update() and its restore-on-failure, with only the disk write faked."""
    from obs_youtube_uploader.ui import api as api_mod
    calls = []
    real_save_locked = api_mod.settings_mod._save_locked

    def flaky(data, path=None):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("read-only")
        real_save_locked(data, tmp_path / "s.json")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", flaky)
    api = make_api(tmp_path, client_layouts=FakeClientLayouts())
    api._state.settings["preview"] = {}

    assert api.set_restore_clients_on_launch(True)["persisted"] is False
    # The restore means memory still says False, so this is a real change
    # again rather than a no-op the guard would skip.
    assert api.set_restore_clients_on_launch(True)["persisted"] is True
    assert len(calls) == 2


def test_an_unchanged_value_still_does_not_rewrite_the_document(
        tmp_path, monkeypatch):
    """settings.save projects every key, so a no-op toggle rewriting the
    whole file is a real cost. Retrying a FAILED write must not cost this."""
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, client_layouts=FakeClientLayouts())
    api._state.settings["preview"] = {}
    api.set_restore_clients_on_launch(True)
    api.set_restore_clients_on_launch(True)
    assert len(writes) == 1
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python -m pytest tests/test_preview_wiring.py -v -k restore_on_launch
python -m pytest tests/test_preview_wiring.py -v -k persist
```

Expected: FAIL. The `is True` replacements fail on the bare-`True` return; the retry test fails with `len(calls) == 1`.

- [ ] **Step 3: Implement the method**

Replace `set_restore_clients_on_launch` (`obs_youtube_uploader/ui/api.py:1469-1505`). Note the return annotation changes from `bool` to `dict`:

```python
    def set_restore_clients_on_launch(self, enabled) -> dict:
        """Toggle the watcher and persist the choice.

        Returns the save button's shape -- the same `persisted` key, in
        the same card -- so one failed write reads one way wherever it
        happens. Not a bare bool: the watcher changes state whether or not
        the write lands, so reverting the checkbox would trade one lie for
        another. The page keeps the box and says what will not survive.
        """
        enabled = bool(enabled)
        section = self._state.settings.setdefault("preview", {})
        wanted_change = section.get("restore_clients_on_launch") != enabled
        persisted = True
        if wanted_change:
            try:
                # Through settings.update, not save(): the mutation must
                # happen inside _SAVE_LOCK or a concurrent writer is
                # reverted. update() also restores the live dict if the
                # block raises, so a failed write leaves the stored value
                # as it was and the next toggle retries on its own --
                # which is why this needs no dirty-flag of its own.
                with settings_mod.update(self._state.settings) as doc:
                    doc.setdefault("preview", {})[
                        "restore_clients_on_launch"] = enabled
            except OSError:
                # Logged and reported, not raised. A settings file that
                # cannot be written must not block the watcher -- but the
                # page has to be able to say the choice is not saved.
                persisted = False
                logger.exception(
                    "Could not persist the client-restore setting")
        if self._client_layouts is not None:
            if enabled:
                self._client_layouts.start()
            else:
                self._client_layouts.stop()
        return {"applied": True, "persisted": persisted}
```

Do not read `section` after the `update()` block — `_normalize` reassigns
`doc["preview"]` inside the call, so that reference is stale by then.

- [ ] **Step 4: Run them to verify they pass**

```bash
python -m pytest tests/test_preview_wiring.py -v
```

Expected: PASS.

- [ ] **Step 5: Write the failing card test**

Same rationale as Task 2 Step 9 — source assertions stand in for a JS test
runner this repo does not have. Two things are worth pinning here: that the
unpersisted case is said at all, and that it does **not** revert the box,
since the watcher really did change state.

Append to `tests/test_preview_wiring.py`:

```python
def test_the_restore_toggle_says_when_the_choice_will_not_survive():
    """A silent failed write is how the user finds out at their next
    restart. Reverting the box would be the opposite lie -- the watcher
    is running -- so only a bridge failure may revert it."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / "obs_youtube_uploader" / "web"
          / "settings.js").read_text(encoding="utf-8")
    block = (js.split("set_restore_clients_on_launch")[1]
               .split("save.addEventListener")[0])
    assert "res.persisted" in block, "the flag is returned but never read"
    assert "will not survive a restart" in block
    # The revert is reachable only from the bridge-failure guard.
    assert "if (!res)" in block.split("box.checked = !wanted")[0]
```

- [ ] **Step 6: Run it to verify it fails**

```bash
python -m pytest tests/test_preview_wiring.py -v -k will_not_survive
```

Expected: FAIL — the handler still takes a bare `ok` and reads no `persisted`.

- [ ] **Step 7: Update the card**

Replace the `box.addEventListener` block in `obs_youtube_uploader/web/settings.js:251-258`:

```javascript
  box.addEventListener('change', function () {
    var wanted = box.checked;
    // WM.send resolves to null on any bridge failure rather than
    // rejecting (app.js:38-43). A dict is always truthy, so null is
    // still the only thing that reverts the box -- and a failed write
    // is no longer mistaken for one.
    WM.send('set_restore_clients_on_launch', wanted).then(function (res) {
      if (!res) { box.checked = !wanted; return; }
      if (!res.persisted) {
        // The watcher really did change state, so the box stays where
        // the user put it. What it cannot do is survive a restart, and
        // saying nothing is how they find that out the hard way.
        say('Restore-on-launch is ' + (wanted ? 'on' : 'off')
          + ' for this session, but could not be written to settings — '
          + 'it will not survive a restart.');
      }
    });
  });
```

- [ ] **Step 8: Run the full suite**

```bash
python -m pytest -q
```

Expected: `1288 passed, 4 skipped`.

- [ ] **Step 9: Commit**

```bash
git add obs_youtube_uploader/ui/api.py \
        obs_youtube_uploader/web/settings.js \
        tests/test_preview_wiring.py
git commit -m "preview: report a restore-on-launch write that did not land

The toggle swallowed OSError and returned truthy, so the choice was gone
at the next restart with nothing said. Report it through the save
button's persisted key. No retry bookkeeping is needed: settings.update
restores the live dict when the block raises, so the stored value still
reads as the old one and the next toggle retries by itself."
```

---

## Task 5: Enabling the toggle mid-session leaves running clients alone

Item 5. Requires Task 4 — it passes the `wanted_change` local that task introduces.

**Files:**
- Modify: `obs_youtube_uploader/preview/clientlayout.py:73-74` (`start`)
- Modify: `obs_youtube_uploader/ui/api.py` — the `start()` call inside the method Task 4 rewrote
- Test: `tests/test_preview_clientlayout.py`, `tests/test_preview_wiring.py`

**Interfaces:**
- Consumes: `wanted_change` from Task 4's `set_restore_clients_on_launch`.
- Produces: `ClientLayoutManager.start(seed_placed: bool = False) -> None`. `Api.start_client_layouts_if_enabled` (`ui/api.py:1450`) keeps calling `start()` with no argument.

**Background:** `_placed` starts empty, so the first `_tick` two seconds after `start()` treats every running client as fresh and places it. At launch that is the point. From the toggle it yanks windows the user positioned by hand — and `restore_now()` (`clientlayout.py:63-71`), wired to the Restore button in the same card, already exists for the user who *wants* that.

Seed on the **transition**, not on the call. `start()` runs on every enabled call, and seeding unconditionally would add clients that appeared *since* the toggle to `_placed`, suppressing the restore they were owed. `Scheduler.start` is idempotent (`ui/scheduler.py:32-37`), but that only prevents a second timer; it does nothing about a side effect in front of it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_preview_clientlayout.py`, give `_watched` a seed parameter:

```python
def _watched(h, seed_placed=False):
    timers = []

    def timer(interval, fn):
        t = FakeTimer(interval, fn)
        timers.append(t)
        return t

    m = h.manager(timer=timer)
    m.start(seed_placed=seed_placed)
    return m, timers
```

Append to the watcher section:

```python
def test_seeding_leaves_already_running_clients_where_they_are():
    """Enabling the toggle mid-session used to move every running client
    two seconds later. "Restore on launch" describes clients that launch,
    and the Restore button is right there for the user who wants the
    other thing."""
    h = Harness(clients=[client("Pilot One", 1), client("Pilot Two", 2)],
                saved={"Pilot One": entry(100, 200, 800, 600),
                       "Pilot Two": entry(300, 400, 800, 600)})
    _m, timers = _watched(h, seed_placed=True)
    _tick(timers)
    assert h.applied == []


def test_seeding_still_places_a_client_that_appears_afterwards():
    """The watcher's actual job. Only the set running at the moment of
    the toggle is exempt."""
    h = Harness(clients=[client("Already Up", 1)],
                saved={"Already Up": entry(100, 200, 800, 600),
                       "Latecomer": entry(300, 400, 800, 600)})
    _m, timers = _watched(h, seed_placed=True)
    _tick(timers)
    h.clients = [client("Already Up", 1), client("Latecomer", 2)]
    _tick(timers)
    assert [hwnd for hwnd, _p in h.applied] == [2]


def test_the_launch_path_still_places_everything_running():
    """Unseeded start() must not change: at launch, placing what is
    already running is the whole point of the feature."""
    h = Harness(clients=[client("Pilot", 1)],
                saved={"Pilot": entry(100, 200, 800, 600)})
    _m, timers = _watched(h)
    _tick(timers)
    assert len(h.applied) == 1
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python -m pytest tests/test_preview_clientlayout.py -v -k "seeding or launch_path"
```

Expected: FAIL with `TypeError: start() got an unexpected keyword argument 'seed_placed'`.

- [ ] **Step 3: Implement `start`**

Replace `start` in `obs_youtube_uploader/preview/clientlayout.py:73-74`:

```python
    def start(self, seed_placed: bool = False) -> None:
        """Arm the watcher.

        `seed_placed` marks everything currently running as already
        placed, so the first tick moves nothing. That is what the toggle
        wants: the label describes clients that LAUNCH, and yanking a
        window the user positioned by hand is the failure place-once
        exists to prevent, arriving through a side door. restore_now()
        stays the way to re-place on demand.

        The launch path leaves it False -- there, placing what is already
        running is the feature.
        """
        if seed_placed:
            with self._lock:
                self._placed |= set(self._named())
        self._scheduler.start()
```

- [ ] **Step 4: Run them to verify they pass**

```bash
python -m pytest tests/test_preview_clientlayout.py -v
```

Expected: PASS.

- [ ] **Step 5: Write the failing wiring test**

In `tests/test_preview_wiring.py`, record the argument on the fake:

```python
    def start(self, seed_placed=False):
        self.started += 1
        self.seeded = seed_placed
```

Add `self.seeded = None` to `FakeClientLayouts.__init__` beside `self.started = 0`, then append:

```python
def test_the_toggle_seeds_only_on_a_real_transition(tmp_path, monkeypatch):
    """A repeat enabled call must not seed: a client that appeared since
    the toggle would be marked placed without ever being placed, and the
    restore it was owed would never happen."""
    _no_disk(monkeypatch)
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {}

    api.set_restore_clients_on_launch(True)
    assert manager.seeded is True

    api.set_restore_clients_on_launch(True)
    assert manager.seeded is False


def test_the_launch_path_does_not_seed(tmp_path):
    """Placing what is already running is what launch is for."""
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {"restore_clients_on_launch": True}
    api.start_client_layouts_if_enabled()
    assert manager.seeded is False
```

- [ ] **Step 6: Run it to verify it fails**

```bash
python -m pytest tests/test_preview_wiring.py -v -k "seeds or launch_path"
```

Expected: FAIL — `test_the_toggle_seeds_only_on_a_real_transition` sees `seeded is False` on the first call, because `Api` still calls `start()` with no argument.

- [ ] **Step 7: Pass the transition through**

In `obs_youtube_uploader/ui/api.py`, inside `set_restore_clients_on_launch`, change the start call:

```python
        if self._client_layouts is not None:
            if enabled:
                # Seed on the transition, not on the call. start() runs on
                # every enabled call, and seeding an unchanged one would
                # mark a client that appeared since the toggle as placed
                # without ever placing it.
                self._client_layouts.start(seed_placed=wanted_change)
            else:
                self._client_layouts.stop()
```

- [ ] **Step 8: Run it to verify it passes**

```bash
python -m pytest tests/test_preview_wiring.py -v
```

Expected: PASS.

- [ ] **Step 9: Run the full suite**

```bash
python -m pytest -q
```

Expected: `1293 passed, 4 skipped`.

- [ ] **Step 10: Confirm the suite still writes nothing real**

```bash
rm -rf /tmp/canary-final
mkdir -p /tmp/canary-final
LOCALAPPDATA=/tmp/canary-final python -m pytest -q
find /tmp/canary-final -type f
```

Expected: `1293 passed, 4 skipped`, and `find` prints nothing.

- [ ] **Step 11: Commit**

```bash
git add obs_youtube_uploader/preview/clientlayout.py \
        obs_youtube_uploader/ui/api.py \
        tests/test_preview_clientlayout.py \
        tests/test_preview_wiring.py
git commit -m "preview: enabling restore-on-launch stops moving running clients

The label describes clients that launch, and the Restore button already
exists for re-placing one on demand. Seed the place-once record from the
current sweep on the toggle's transition -- not on every enabled call,
which would consume a client that appeared since."
```

---

## Task 6: Update the roadmap

**Files:**
- Modify: `eve-preview-design.md` — the "Left behind by item 11 (#23)" subsection

**Note:** another session may be editing this file concurrently for `#26`.
Re-read the subsection before editing and work from what is on disk, not from
the line numbers below.

- [ ] **Step 1: Close the four items this branch fixed**

`#27` already struck the `preview/store.py` bullet as **Done in #26**. **Leave
that bullet alone.** Four remain, and the `~~strike~~ **resolution.**` form
`#27` used is the convention to match. Do not touch the
"Left behind by item 7 (#26)" section below it.

Replace the `tests/test_api_bookmarks.py` bullet entirely — its diagnosis was
wrong, so striking it without correcting it would preserve a false claim:

```markdown
- ~~**`tests/test_api_bookmarks.py` overwrites the developer's real
  `settings.json`.**~~ **Done — and the diagnosis was wrong.** No test in
  that file ever leaked: its `api` fixture already redirected
  `paths.settings_file()`, and since that patch lands on the module object it
  covered `settings_mod.save` too. The real leak was one level up at
  `paths.state_dir()`, reached from three places nobody had stubbed — the
  upload worker's channel persist (15 tests in `test_api_upload.py`), the
  probe cache writing `durations.json`, and `set_preview_enabled` (3 tests in
  `test_preview_wiring.py`). An autouse `tests/conftest.py` redirects
  `LOCALAPPDATA`, `state_dir()`'s only input, so every derived path moves
  together. Pointing it at `settings_file()` as suggested here would have
  broken `tests/test_paths.py`, which asserts on that function's real return.
```

Then strike the remaining three:

```markdown
- ~~**"No named clients are running" is reported when every placement read
  failed.**~~ **Done.** `_save` returns a `failed` count beside `saved` and
  `persisted`, and the card reads it: nothing running and nothing readable
  are now different messages. It also made the partial case sayable — "Saved
  3 client positions. Could not read 2 others." — which was silent before.
- ~~**The restore-on-launch toggle reports success on a failed persist.**~~
  **Done.** It returns `{"applied": True, "persisted": bool}`, the save
  button's own key in the same card. The checkbox stays where the user put it,
  because the watcher really did change state; what the page reports is that
  the choice will not survive a restart. No retry bookkeeping was needed —
  `settings.update()` restores the live dict when the block raises, so the
  next toggle sees a real change and retries on its own.
- ~~**Enabling restore-on-launch mid-session places already-running
  clients**~~ **Done — fixed, not left.** `start(seed_placed=True)` marks the
  current sweep as already placed, and the toggle passes it only on a real
  transition, so a repeat enabled call cannot consume a client that appeared
  since. The launch path still calls bare `start()`. Fixed rather than left
  because `restore_now()` — the Restore button four lines away in the same
  card — already exists for the user who wants that.
```

- [ ] **Step 2: Commit**

```bash
git add eve-preview-design.md
git commit -m "docs: close the four items this branch fixed

store.py was already struck by #27, which is where it belonged. The
bookmarks entry is replaced rather than struck: no test in that file ever
leaked, and naming it kept sending readers to the wrong module."
```

---

## Self-review

**Spec coverage.** Design item 2 → Task 1 (done). Item 3 → Task 2 (Python, Api, JS). Item 4 → Task 4. Item 5 → Task 5. Item 1 → shipped on main in `#26`; Task 3 is left empty so the numbering cannot be misread as an omission. The design's Testing section lists twelve behaviours; every one has a test in Task 2, 4, or 5 — except the one the design added for the tracked persist flag, which `#26` made unreachable and which Task 4 replaces with a test that the *retry itself* still works whichever layer provides it.

**Type consistency.** `failed` is an `int` in Task 2 and never referenced again. `wanted_change` is a `bool` produced in Task 4 and consumed in Task 5 Step 7. `start(seed_placed=...)` uses the same keyword in `clientlayout.py`, the `Api` call site, `FakeClientLayouts`, and `_watched`.

**Sequencing.** Task 4 before Task 5 is the one hard dependency, stated in both. Tasks 1 and 2 are independent of everything.

**Expected counts.** 1280 → 1284 (Task 2: three manager tests plus one card-source test) → 1288 (Task 4: three wiring tests plus one card-source test) → 1293 (Task 5: three manager tests plus two wiring tests). Skips stay at 4 throughout; no task adds a `skipif`.

**Frontend verification.** Neither JS change is behaviourally tested — there is no JS runner here and this plan does not add one. Both are pinned by source assertions instead (Task 2 Step 9, Task 4 Step 6), following `tests/test_preview_wiring.py:415-427`. That catches the regression that matters — a message becoming reachable when it should not be — but it cannot catch a typo in the message text or a runtime error in the handler. `docs/smoke-checklist.md` remains the only check for those.
