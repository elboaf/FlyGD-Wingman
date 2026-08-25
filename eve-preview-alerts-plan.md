# Preview alerts implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** EVE gamelog watching that pulses a client's preview and plays a sound when a player shoots, scrambles or decloaks it, and an active-client border so an unselected preview carries no ring at all.

**Architecture:** Three new pure-ish modules under `obs_youtube_uploader/alerts/` — `patterns.py` parses one log line, `state.py` decides what an alert does over time, `tailer.py` polls the Gamelogs folder — plus `service.py`, which owns cooldowns and hands alerts to the existing preview thread through a lock-protected mailbox and a bare `PostMessageW` signal. The preview thread gains a second `SetTimer` that pulses a pre-rendered ring, and finally sets `PreviewWindow.selected`, which has existed unassigned since the first slice.

**Tech Stack:** Python 3.11+, ctypes/Win32 (DWM thumbnails, layered windows), Pillow, `winsound`, pywebview bridge, vanilla JS page, pytest.

**Spec:** `eve-preview-alerts-design.md` (parent: `eve-preview-design.md`)

## Global Constraints

- **Every new module must import cleanly on Linux.** CI is `ubuntu-latest` only. `import winsound` is deferred inside a function, never at module scope — a top-level import fails collection (`evewindows.py:1-14` is the pattern; `eve-preview-plan.md:32`).
- **Every ctypes function gets `argtypes` and `restype`.** Undeclared, ctypes truncates pointer-sized values to 32 bits and the symptom appears nowhere near the cause (`preview/win32.py:1-16`).
- **Every HWND touch happens on the preview thread.** Marshal with `PostMessageW`, never call across threads.
- **`PostMessageW` carries integers only** — it is bound `[HWND, UINT, WPARAM, LPARAM]`. Alert data travels in a lock-protected field on the host and only the signal is posted, the same shape `_desired_hotkeys` already uses (`preview/host.py:122-130`).
- **No writer may save from a stale settings snapshot.** `_normalize` reassigns `data["preview"]` wholesale on every call, so hold `data`, not `data["preview"]`, across an `update()` (`settings.py:373-378`).
- **`alerts` must be added to `pyproject.toml` packages.** A missing entry installs cleanly and fails at import time in the built artifact, not in the checkout (`pyproject.toml:67-70`).
- **No new runtime dependencies.**
- **Wingman must never move, resize or reposition a running EVE client window, and must never call `SetForegroundWindow` from the alert path.** Focus-stealing mid-fight sends the user's keystrokes to the wrong ship (`PRODUCT.md`).
- **Alerts default off.** No polling thread exists unless previews are enabled *and* alerts are enabled *and* `gamelogs_dir` resolves.
- Run the full suite with `python -m pytest -q` from the worktree root.

---

## File structure

| File | Responsibility | Platform |
|---|---|---|
| `obs_youtube_uploader/alerts/__init__.py` | **Create.** Package marker | Pure |
| `obs_youtube_uploader/alerts/patterns.py` | **Create.** One log line → `(event, source)`; markup stripping; NPC heuristic | Pure |
| `obs_youtube_uploader/alerts/state.py` | **Create.** Arm, severity, expiry, acknowledgement | Pure |
| `obs_youtube_uploader/alerts/tailer.py` | **Create.** Folder polling, file positions, character attribution | Pure + filesystem |
| `obs_youtube_uploader/alerts/service.py` | **Create.** Cooldowns, filter, sound, health, `reconcile()` | Windows for sound only |
| `obs_youtube_uploader/settings.py` | **Modify.** `alerts` subtree, validation, the copy branch | Pure |
| `obs_youtube_uploader/preview/win32.py` | **Modify.** `WM_APP_ALERT`, GDI bindings for the frame cache | Windows types |
| `obs_youtube_uploader/preview/chrome.py` | **Modify.** Ring painted only when selected; alert ring | Pure |
| `obs_youtube_uploader/preview/geometry.py` | **Modify.** Inset becomes a parameter, not a constant | Pure |
| `obs_youtube_uploader/preview/alertframes.py` | **Create.** Pre-rendered DIB ring, cleanup | Windows |
| `obs_youtube_uploader/preview/window.py` | **Modify.** `selected`, conditional inset, forced redraw, cleanup | Windows |
| `obs_youtube_uploader/preview/host.py` | **Modify.** Mailbox, alert timer, selection resolution | Windows |
| `obs_youtube_uploader/assets/sounds/*.wav` | **Create.** `chime`, `bell` | Asset |
| `packaging/uploader.spec` | **Modify.** Collect `assets/sounds` | Build |
| `pyproject.toml` | **Modify.** Register the `alerts` package | Build |
| `obs_youtube_uploader/ui/api.py` | **Modify.** Bridge methods, `reconcile()` wiring, `set_folder` hook | Any |
| `obs_youtube_uploader/__main__.py` | **Modify.** Build and own the service | Any |
| `obs_youtube_uploader/web/alerts.js` | **Create.** The Alerts card | Page |
| `obs_youtube_uploader/web/index.html` | **Modify.** Alerts card markup | Page |
| `obs_youtube_uploader/web/style.css` | **Modify.** Swatch and health-line styles | Page |
| `docs/smoke-checklist.md` | **Modify.** Windows-only checks | Docs |

Task 1 is a throwaway probe and produces no shipped code. Tasks 2, 4 and 5 are
pure and can be built in any order. Task 3 is a gate that needs real gamelogs
from the user; it blocks shipping, not the tasks after it. Tasks 6-14 depend on
what precedes them.

**Conventions this plan follows, taken from the code it extends:**

- Value objects in `alerts/` are `typing.NamedTuple`, matching `preview/*`
  (`preview/layout.py:11`, `preview/discovery.py:25`, `preview/geometry.py:15`).
  `combatlog.py` uses frozen dataclasses; that split is deliberate and this
  package sits on the preview side of it.
- Tests are free functions named as claims, package-absolute imports, and
  `@pytest.mark.parametrize` with a positional spec. Docstrings explain *why a
  behaviour is right*, not what the test does. `tests/conftest.py` is autouse
  and already isolates `%LOCALAPPDATA%`.
- Ruff selects `DTZ`, so every `datetime.now()` takes `tz=`; `BLE`, so no bare
  `except Exception` without a logged reason; and `S110`/`S112`, so no silent
  `try/except: pass` outside `tests/`.
- `settings.py` imports from `preview/*` at module scope, and `preview/*` never
  imports `settings`. `alerts/` follows the same rule: `settings.py` may import
  `alerts.patterns`, and nothing in `alerts/` imports `settings`.

---

### Task 1: Probe the two Win32 claims the render path rests on

Throwaway, Windows-only, hand-run. It produces no shipped code and no tests —
the same shape as the five probes that preceded the parent design
(`eve-preview-design.md:28-44`). It goes first because Task 10 picks an approach
based on its answers.

The spec asserts two things it cannot prove from Linux
(`eve-preview-alerts-design.md`, "The alert render path" and "Risks"):

1. That a ring drawn wider than the thumbnail inset renders as four corner
   blocks joined by thin edges — the thumbnail clipping left/right/bottom, the
   label band overpainting the top at `chrome.py:84` — rather than as a thicker
   ring.
2. That `SetLayeredWindowAttributes` cannot pulse the ring alone, and what it
   does to an existing `UpdateLayeredWindow` surface and to the per-pixel alpha
   the hit region depends on.

**Files:**
- Create: `tmp/probe_alert_ring.py` (throwaway, never committed)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing in code. Produces *findings*, written into
  `eve-preview-alerts-design.md`.

- [ ] **Step 1: Write the probe**

Create `tmp/probe_alert_ring.py`. It creates one layered preview-shaped window
with a DWM thumbnail of any window, exactly as `preview/window.py` does, and
renders three variants side by side:

```python
"""Throwaway. Answers two questions, then gets deleted.

1. Does a ring wider than the thumbnail inset render as a ring, or as
   corner brackets?
2. What does SetLayeredWindowAttributes do to a window already driven by
   UpdateLayeredWindow?

Run on Windows with an EVE client (or any window) open:
    python tmp/probe_alert_ring.py
"""

import ctypes
import time

from obs_youtube_uploader.preview import chrome, geometry, layered, thumbnail, win32

VARIANTS = (
    # (border_for_chrome, inset_for_thumbnail, label)
    (2, 2, "ring 2 / inset 2  -- baseline"),
    (6, 2, "ring 6 / inset 2  -- the claim: corner brackets"),
    (6, 6, "ring 6 / inset 6  -- what the design ships"),
)
```

For each variant, render chrome with `border=` the ring width, push it with
`layered.push`, and register the thumbnail with
`geometry.thumbnail_rect(rect, inset, chrome.LABEL_H)`. Leave each on screen
long enough to photograph.

Then, on the last window, call
`SetLayeredWindowAttributes(hwnd, 0, 128, win32.LWA_ALPHA)` and observe: does
the window blank, does the thumbnail dim with the chrome, does the window still
receive a click, and does a subsequent `layered.push` restore it?

- [ ] **Step 2: Run it on Windows and record what happened**

Run: `python tmp/probe_alert_ring.py`

There is no pass/fail. Write down, for each variant, whether the ring reads as
a ring; and for the `SetLayeredWindowAttributes` call, all four observations
above.

- [ ] **Step 3: Fold the findings into the design doc**

Edit `eve-preview-alerts-design.md`. In "The alert render path", replace the
prose description of the occlusion with what was actually seen. In "Risks",
replace "**The `SetLayeredWindowAttributes` interaction is unprobed**" with the
result.

**If the probe contradicts the spec** — if a 6 px ring inside a 2 px inset does
render as a usable ring — then the conditional inset in Task 10 is unnecessary
and should be dropped, and Task 10's step that swaps the inset on arm/clear goes
away. Say so in the doc and stop to raise it rather than building both.

- [ ] **Step 4: Delete the probe and commit the findings**

```bash
rm tmp/probe_alert_ring.py
git add eve-preview-alerts-design.md
git commit -m "docs: probe the alert ring geometry and the layered-alpha interaction"
```

The probe is deleted, not committed. `tmp/` is scratch; the findings are the
artifact.

---

### Task 2: `alerts/patterns.py` — one log line in, one event out

Pure, Linux-testable, no I/O and no clock. Every matcher and both extraction
regexes live here, and nothing else in the feature parses a log line.

The fixtures in this task encode **TriffView's matcher contract**, not verified
EVE output — neither repository contains log bodies. Task 3 replaces them with
real lines. Build against these, then let Task 3 correct them.

**Files:**
- Create: `obs_youtube_uploader/alerts/__init__.py` (empty)
- Create: `obs_youtube_uploader/alerts/patterns.py`
- Modify: `pyproject.toml:71-77`
- Test: `tests/test_alerts_patterns.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `EVENTS: tuple[str, ...]` — `("combat", "warp_scramble", "decloak")`, the
    canonical event list. `settings.py` imports this so the schema and the
    parser cannot drift.
  - `SEVERITY: dict[str, int]` — `{"warp_scramble": 3, "combat": 2, "decloak": 1}`
  - `class Match(NamedTuple): event: str; source: str`
  - `match_line(line: str) -> Match | None`
  - `strip_markup(text: str) -> str`
  - `is_likely_npc(source: str) -> bool`
  - `FILTERED_EVENTS: frozenset[str]` — `{"combat", "warp_scramble"}`, the
    events `is_likely_npc` applies to.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alerts_patterns.py`:

```python
"""One log line in, one event out.

Every line here encodes TriffView's matcher contract rather than verified
EVE output: neither repository carries log bodies, so these are the shapes
the matchers were written against. The real corpus arrives in a later task
and is authoritative over anything asserted here.
"""

from pathlib import Path

import pytest

from obs_youtube_uploader.alerts import patterns

DAMAGE = (
    "[ 2026.08.24 20:42:50 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>"
)
MISS = (
    "[ 2026.08.24 20:42:51 ] (combat) Bob Smith[BURN](Rifter) "
    "misses you completely"
)
SCRAMBLE = (
    "[ 2026.08.24 20:43:02 ] (combat) <color=0xffe57f7f>"
    "<b>Warp scramble attempt</b> <color=0xffffffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b> <font size=10>to</font> <b>you!</b>"
)
DECLOAK = (
    "[ 2026.08.24 20:43:10 ] (notify) Your cloak deactivates due to a "
    "nearby object."
)
NPC_DAMAGE = (
    "[ 2026.08.24 20:44:00 ] (combat) <color=0xffcc0000><b>88</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Sleepless Sentinel</b><font size=10> - Hits</font>"
)
OUTGOING = (
    "[ 2026.08.24 20:42:50 ] (combat) <color=0xff00ffff><b>210</b> "
    "<color=0xff7fffff><font size=10>to</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>"
)


@pytest.mark.parametrize(
    "line,event",
    [
        (DAMAGE, "combat"),
        (MISS, "combat"),
        (SCRAMBLE, "warp_scramble"),
        (DECLOAK, "decloak"),
    ],
)
def test_each_shape_matches_its_event(line, event):
    assert patterns.match_line(line).event == event


def test_damage_and_miss_are_one_event():
    """TriffView splits these because the two lines look nothing alike --
    a colour code versus a literal. That is a parsing detail; a pilot being
    shot at and missed is being shot at."""
    assert patterns.match_line(DAMAGE).event == patterns.match_line(MISS).event


def test_outgoing_damage_does_not_alert():
    """The colour code is the whole discriminator. Without it, every shot
    you fire alerts you about yourself, continuously, during every fight."""
    assert patterns.match_line(OUTGOING) is None


@pytest.mark.parametrize("line", ["", "   ", "[ 2026.08.24 20:42:50 ] (None) x"])
def test_uninteresting_lines_return_none(line):
    assert patterns.match_line(line) is None


def test_source_is_extracted_without_markup():
    assert patterns.match_line(DAMAGE).source == "Bob Smith[BURN](Rifter)"


def test_miss_source_is_extracted():
    assert patterns.match_line(MISS).source == "Bob Smith[BURN](Rifter)"


def test_strip_markup_drops_the_timestamp():
    """Everything up to the first "] " goes, or the timestamp's digits and
    brackets reach is_likely_npc and every NPC reads as a player."""
    assert "2026" not in patterns.strip_markup(DAMAGE)


@pytest.mark.parametrize(
    "source,npc",
    [
        ("Sleepless Sentinel", True),
        ("Bob Smith[BURN](Rifter)", False),
        ("Bob Smith's Hobgoblin II", False),
        ("Emergent Patroller", True),
    ],
)
def test_npc_heuristic(source, npc):
    """A corp ticker in brackets, a hull in parens, or "'s " for a drone.
    NPCs are a bare name. This is a heuristic and the corpus task is what
    validates it -- a false negative here means silence while a player
    opens fire."""
    assert patterns.is_likely_npc(source) is npc


def test_decloak_is_not_filtered():
    """Its line carries no attacker source, so there is nothing to test
    and the filter must not be applied to it."""
    assert "decloak" not in patterns.FILTERED_EVENTS


def test_events_and_severity_agree():
    """settings.py builds its schema from EVENTS. If the two lists drift,
    the schema grows an event the renderer cannot draw."""
    assert set(patterns.EVENTS) == set(patterns.SEVERITY)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_alerts_patterns.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'obs_youtube_uploader.alerts'`

- [ ] **Step 3: Create the package and register it**

```bash
mkdir -p obs_youtube_uploader/alerts
touch obs_youtube_uploader/alerts/__init__.py
```

Edit `pyproject.toml:71-77` to add the subpackage:

```toml
packages = [
    "obs_youtube_uploader",
    "obs_youtube_uploader.ui",
    "obs_youtube_uploader.preview",
    "obs_youtube_uploader.alerts",
    "obs_youtube_uploader.evesettings",
    "obs_youtube_uploader.eveskills",
]
```

Subpackages are not implied by their parent here. `tests/test_packaging_completeness.py`
enforces this, so a missing entry fails the suite rather than only the frozen
build.

- [ ] **Step 4: Write the implementation**

Create `obs_youtube_uploader/alerts/patterns.py`:

```python
"""One EVE gamelog line in, one alert event out.

Pure: no I/O, no clock, no Win32. Everything that decides *whether* a line
is interesting lives here, so the tailer can stay about files and the
service about cooldowns.

The matchers are substring tests on the lowercased line rather than
regexes, which is what TriffView does and is the right call: the lines
carry nested colour and font markup whose exact shape varies, and a regex
over that is a way to stop matching after a patch that changed nothing
anyone cares about.
"""

import re
from typing import NamedTuple

EVENTS = ("combat", "warp_scramble", "decloak")

# warp_scramble outranks combat because "I cannot leave" changes a
# different decision than "I am taking damage". A live higher-severity
# alert is never repainted by a lower one.
SEVERITY = {"warp_scramble": 3, "combat": 2, "decloak": 1}

# decloak carries no attacker source, so there is nothing for the NPC
# heuristic to test and it must not be applied.
FILTERED_EVENTS = frozenset({"combat", "warp_scramble"})

# Incoming damage is red. Outgoing is not, and that colour code is the
# only thing separating "someone is shooting me" from "I am shooting".
_INCOMING_COLOR = "0xffcc0000"

_SOURCE_RE = re.compile(
    r"<font[^>]*>\s*from\s*</font>\s*(?P<source>.+?)"
    r"(?:\s*<font|\s*-\s*|\s*to\s*<|$)",
    re.IGNORECASE,
)
_SOURCE_FALLBACK_RE = re.compile(
    r"from\s+(?P<source>.+?)(?:\s+to\s+|\s+-\s+|$)", re.IGNORECASE
)
_MISS_RE = re.compile(
    r"\]\s*\(combat\)\s*(?P<source>.+?)\s+misses you", re.IGNORECASE
)
_TAG_RE = re.compile(r"<.*?>")
_WS_RE = re.compile(r"\s+")


class Match(NamedTuple):
    event: str
    source: str


def strip_markup(text: str) -> str:
    """Tags out, whitespace collapsed, timestamp dropped.

    The timestamp has to go before is_likely_npc sees the text: it is
    full of digits and brackets, and every NPC would read as a player.
    """
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    head, sep, tail = clean.partition("] ")
    return tail.strip() if sep else clean


def is_likely_npc(source: str) -> bool:
    """A bare name is an NPC; a player carries punctuation.

    Player attackers render with a corp ticker in brackets and a hull in
    parentheses, and player drones as "Name's Hull". NPCs are a bare
    name. It is a heuristic, which is why pve_filter is a toggle.
    """
    if not source:
        return False
    if "'s " in source:
        return False
    return not any(ch in source for ch in "[]()")


def _extract_source(line: str) -> str:
    m = _SOURCE_RE.search(line)
    if m:
        return strip_markup(m.group("source"))
    m = _SOURCE_FALLBACK_RE.search(strip_markup(line))
    if m:
        return m.group("source").strip()
    return ""


def match_line(line: str) -> Match | None:
    """The only entry point. None means "not interesting"."""
    if not line:
        return None
    lower = line.lower()

    if "(combat)" in lower:
        if _INCOMING_COLOR in lower and "from</font>" in lower.replace(" ", ""):
            return Match("combat", _extract_source(line))
        m = _MISS_RE.search(line)
        if m:
            return Match("combat", strip_markup(m.group("source")))
        if (
            "warp scramble attempt" in lower
            or "warp disruption attempt" in lower
            or "warp disruption zone" in lower
        ):
            return Match("warp_scramble", _extract_source(line))

    if "(notify)" in lower and "cloak deactivates" in lower:
        return Match("decloak", "")

    return None
```

Note the `lower.replace(" ", "")` on the `from</font>` test: TriffView checks
two spellings (`" from</font>"` and `">from</font>"`) because the whitespace
around the word varies. Collapsing spaces covers both and any third spelling.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_alerts_patterns.py -q`
Expected: PASS (parametrized cases expand the count).

Then the whole suite, because `pyproject.toml` changed:

Run: `python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Lint**

Run: `python -m ruff check obs_youtube_uploader/alerts/ tests/test_alerts_patterns.py`
Run: `python -m ruff format --check obs_youtube_uploader/alerts/ tests/test_alerts_patterns.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/alerts/ tests/test_alerts_patterns.py pyproject.toml
git commit -m "alerts: parse one gamelog line into an event and a source"
```

---

### Task 3: Validate the NPC heuristic against real gamelogs

A gate, not a code task. It needs log files from the user and it can run any
time after Task 2 — it blocks shipping, not Tasks 4-14.

The heuristic decides whether a persistent alert fires at all. A false negative
is silence while a player opens fire, which is the failure the whole feature
exists to prevent, and it is ported from TriffView on trust.

**Files:**
- Create: `tests/fixtures/gamelogs/*.txt`
- Modify: `tests/test_alerts_patterns.py`

**Interfaces:**
- Consumes: `patterns.match_line`, `patterns.is_likely_npc` from Task 2.
- Produces: a corpus other tasks' tests may read. No new code symbols.

- [ ] **Step 1: Collect the logs**

Ask the user for excerpts from `Documents/EVE/logs/Gamelogs/*.txt` covering:

- a genuine PvP engagement — another player shooting them, ideally including a
  miss line;
- player drone damage;
- Sleeper or Drifter fire from a wormhole site;
- a warp scramble, from an NPC **and** from a player if both can be found;
- a decloak.

Excerpts are fine. Character names stay as they are — these files never leave
`tests/`.

- [ ] **Step 2: Write the corpus test**

Add to `tests/test_alerts_patterns.py`:

```python
FIXTURES = Path(__file__).parent / "fixtures" / "gamelogs"


def _corpus_lines():
    if not FIXTURES.is_dir():
        return []
    lines = []
    for path in sorted(FIXTURES.glob("*.txt")):
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            lines.extend(fh.read().splitlines())
    return lines


@pytest.mark.skipif(not FIXTURES.is_dir(), reason="no gamelog corpus committed")
def test_corpus_yields_at_least_one_of_every_event():
    """A corpus that cannot produce an event is not exercising that
    matcher, and the matcher's first real input would be a fight."""
    seen = {m.event for m in filter(None, map(patterns.match_line, _corpus_lines()))}
    assert seen == set(patterns.EVENTS)


@pytest.mark.skipif(not FIXTURES.is_dir(), reason="no gamelog corpus committed")
def test_no_player_attack_in_the_corpus_is_classified_as_an_npc():
    """The load-bearing assertion of the whole feature. Any line here that
    a human confirmed was a player must survive the filter."""
    # PLAYER_SOURCES is filled in by hand from the corpus, by reading it.
    for source in PLAYER_SOURCES:
        assert patterns.is_likely_npc(source) is False
```

`PLAYER_SOURCES` is a literal list, written by reading the corpus and
identifying which sources were players. That hand step is the point — an
automated check would only re-assert the heuristic against itself.

- [ ] **Step 3: Run it and read the failures**

Run: `python -m pytest tests/test_alerts_patterns.py -q`

**If a real player is classified as an NPC**, do not weaken the test. Fix
`is_likely_npc` and add the offending line to the synthetic fixtures in Task 2
so the case is covered without needing the corpus.

**If a scramble line yields no source**, `_extract_source` needs a scramble-shaped
branch — the spec flags this as unknown, since the scramble line's markup
differs from the damage line's.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/gamelogs/ tests/test_alerts_patterns.py
git commit -m "alerts: validate the NPC heuristic against real gamelogs"
```

---

### Task 4: `alerts/state.py` — what an alert does over time

Pure: no I/O, no Win32, no wall clock of its own — the caller passes `now`. This
is where arm, severity, expiry, acknowledgement and the pulse phase live, so
`preview/host.py` stays about messages and `window.py` about pixels. Same
posture as `preview/geometry.py`, which exists so the placement decisions are
testable on Linux.

**Files:**
- Create: `obs_youtube_uploader/alerts/state.py`
- Test: `tests/test_alerts_state.py`

**Interfaces:**
- Consumes: `patterns.SEVERITY` from Task 2.
- Produces:
  - `class Alert(NamedTuple): event: str; color: str; started: float; expires: float | None; duration_ms: int; pulses: int` — `expires is None` means persistent.
  - `FRAME_ALPHAS: tuple[int, ...]` — the six pre-rendered alpha steps.
  - `is_active(alert: Alert | None, now: float) -> bool`
  - `arm(current, event, color, now, *, duration_ms, pulses, persist, target_is_selected) -> Alert`
  - `clear_expired(alert, now) -> Alert | None`
  - `acknowledge(alert) -> Alert | None`
  - `progress(alert, now) -> float`
  - `alpha_for(progress: float, pulses: int) -> int`
  - `frame_index(alert, now) -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alerts_state.py`:

```python
"""Arm, severity, expiry, acknowledgement, pulse phase.

Pure by construction: every function takes `now` rather than reading a
clock, which is what makes the whole state machine testable on Linux --
the same reason preview/geometry.py exists.
"""

import pytest

from obs_youtube_uploader.alerts import state

ARM = dict(duration_ms=1200, pulses=3, persist=False, target_is_selected=False)


def _arm(current, event, now, **over):
    kwargs = {**ARM, **over}
    return state.arm(current, event, "#ff4d4d", now, **kwargs)


def test_arming_from_nothing_returns_the_incoming_alert():
    a = _arm(None, "combat", 0.0)
    assert a.event == "combat" and a.expires == pytest.approx(1.2)


def test_persist_makes_the_alert_never_expire():
    a = _arm(None, "combat", 0.0, persist=True)
    assert a.expires is None
    assert state.is_active(a, 99999.0) is True


def test_an_alert_on_an_already_selected_client_is_not_persistent():
    """You are looking at that client, so there is nothing to acknowledge
    and a persistent ring would pulse until you tabbed away and back."""
    a = _arm(None, "combat", 0.0, persist=True, target_is_selected=True)
    assert a.expires is not None


def test_higher_severity_replaces_outright():
    combat = _arm(None, "combat", 0.0)
    scram = _arm(combat, "warp_scramble", 0.5)
    assert scram.event == "warp_scramble"


def test_lower_severity_extends_but_does_not_repaint():
    """Without this a decloak repaints a live scramble as the milder
    alert, which is the opposite of what severity is for."""
    scram = _arm(None, "warp_scramble", 0.0)
    after = _arm(scram, "decloak", 0.5)
    assert after.event == "warp_scramble"
    assert after.expires > scram.expires


def test_equal_severity_restarts_the_pulse():
    """The common case: a fight emits a combat line every server tick, and
    each one should restart the pulse rather than let it finish."""
    first = _arm(None, "combat", 0.0)
    second = _arm(first, "combat", 0.9)
    assert second.started == 0.9
    assert second.event == "combat"


def test_lower_severity_over_a_persistent_alert_changes_nothing():
    """With persistence on there is no expiry to extend, so the extend
    rule is inert. It is written down so that turning persistence OFF does
    not quietly change which colour is showing."""
    scram = _arm(None, "warp_scramble", 0.0, persist=True)
    after = _arm(scram, "decloak", 0.5, persist=True)
    assert after == scram


def test_clear_expired_drops_a_timed_alert_and_keeps_a_persistent_one():
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.clear_expired(timed, 99.0) is None
    assert state.clear_expired(persistent, 99.0) == persistent


def test_acknowledge_clears_only_a_persistent_alert():
    """A timed alert is already going away; acknowledging it would make
    selecting a client cut short a ring that had just appeared."""
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.acknowledge(timed) == timed
    assert state.acknowledge(persistent) is None


def test_progress_clamps_for_timed_and_free_runs_for_persistent():
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.progress(timed, 99.0) == 1.0
    assert 0.0 <= state.progress(persistent, 99.0) < 1.0


def test_alpha_never_reaches_zero():
    """The ring pulses rather than blinking off. An alpha of 0 mid-pulse
    reads as the alert having ended."""
    alphas = [state.alpha_for(i / 50, 3) for i in range(51)]
    assert min(alphas) >= 90 and max(alphas) <= 255


def test_frame_index_is_in_range():
    a = _arm(None, "combat", 0.0, persist=True)
    for i in range(60):
        assert 0 <= state.frame_index(a, i * 0.08) < len(state.FRAME_ALPHAS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_alerts_state.py -q`
Expected: FAIL — `ImportError: cannot import name 'state'`

- [ ] **Step 3: Write the implementation**

Create `obs_youtube_uploader/alerts/state.py`:

```python
"""What an alert does over time.

Pure: `now` is always passed in, never read. That is what lets the whole
state machine be covered on ubuntu-latest, and it is the same trade
preview/geometry.py makes for placement.

One predicate -- is_active -- backs the query, the expiry sweep and the
severity guard. Three call sites disagreeing about whether an alert is
still live is exactly how a persistent alert gets silently downgraded by
a lower-severity event.
"""

import math
from typing import NamedTuple

from .patterns import SEVERITY

# Six steps is past what the eye resolves in a 1200ms pulse, and each one
# costs a DIB while an alert is armed.
FRAME_ALPHAS = (110, 139, 168, 197, 226, 255)


class Alert(NamedTuple):
    event: str
    color: str
    started: float
    # None means persistent: it clears on acknowledgement, never on time.
    expires: float | None
    duration_ms: int
    pulses: int


def is_active(alert, now: float) -> bool:
    return alert is not None and (alert.expires is None or alert.expires > now)


def arm(
    current,
    event: str,
    color: str,
    now: float,
    *,
    duration_ms: int,
    pulses: int,
    persist: bool,
    target_is_selected: bool,
) -> Alert:
    """Fold an incoming event into whatever is already showing."""
    expires = None if (persist and not target_is_selected) else now + duration_ms / 1000
    incoming = Alert(event, color, now, expires, duration_ms, pulses)
    if not is_active(current, now):
        return incoming

    rank, current_rank = SEVERITY[event], SEVERITY[current.event]
    if rank > current_rank:
        return incoming
    if rank == current_rank:
        # Restart the pulse and re-stamp the expiry. Colour comes from the
        # incoming event so a live colour change in settings takes effect.
        return current._replace(started=now, expires=expires, color=color)

    # Lower severity: extend only, never repaint.
    if current.expires is None or expires is None:
        # Mixed persistent/timed cannot arise for one preview in one tick --
        # persist and target_is_selected are the same for both -- so the
        # safe reading is "leave the higher-severity alert exactly as is".
        return current
    return current._replace(expires=max(current.expires, expires))


def clear_expired(alert, now: float):
    return alert if is_active(alert, now) else None


def acknowledge(alert):
    """Clear a persistent alert. A timed one is left to expire.

    Acknowledging a timed alert would make selecting a client cut short a
    ring that had only just appeared.
    """
    if alert is not None and alert.expires is None:
        return None
    return alert


def progress(alert, now: float) -> float:
    if alert.duration_ms <= 0:
        return 1.0
    p = (now - alert.started) * 1000.0 / alert.duration_ms
    if alert.expires is None:
        # Free-running, so a persistent alert keeps pulsing at the same
        # cadence instead of finishing and holding.
        return p % 1.0
    return min(1.0, max(0.0, p))


def alpha_for(progress: float, pulses: int) -> int:
    wave = (math.sin(progress * pulses * 2 * math.pi) + 1) / 2
    # Floored well above zero: the ring pulses rather than blinking off,
    # because an alpha of 0 mid-pulse reads as the alert having ended.
    return max(90, min(255, int(110 + wave * 145)))


def frame_index(alert, now: float) -> int:
    alpha = alpha_for(progress(alert, now), alert.pulses)
    return min(
        range(len(FRAME_ALPHAS)), key=lambda i: abs(FRAME_ALPHAS[i] - alpha)
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_alerts_state.py -q`
Expected: PASS (parametrized cases expand the count).

- [ ] **Step 5: Lint and commit**

Run: `python -m ruff check obs_youtube_uploader/alerts/ tests/test_alerts_state.py`
Run: `python -m ruff format --check obs_youtube_uploader/alerts/ tests/test_alerts_state.py`

```bash
git add obs_youtube_uploader/alerts/state.py tests/test_alerts_state.py
git commit -m "alerts: the alert state machine, severity rules included"
```

---

### Task 5: `alerts/tailer.py` — follow the Gamelogs folder

Filesystem, but no Win32 and no threading in the tested surface: `rescan()` and
`poll()` are called by the thread in Task 7 and directly by tests. That split is
what makes the awkward parts — open-at-EOF, rotation, partial lines — coverable
on Linux.

**Files:**
- Create: `obs_youtube_uploader/alerts/tailer.py`
- Test: `tests/test_alerts_tailer.py`

**Interfaces:**
- Consumes: `patterns.match_line` (Task 2); `combatlog.parse_header`,
  `combatlog.LogHeader` (existing, `combatlog.py:44-79`).
- Produces:
  - `class Event(NamedTuple): character: str; event: str; source: str`
  - `MAX_AGE: datetime.timedelta` — 12 hours
  - `MAX_FILES: int` — 64
  - `class Tailer:`
    - `__init__(self, folder: Path)`
    - `rescan(self, now_utc: datetime.datetime) -> None`
    - `poll(self) -> list[Event]`
    - `characters(self) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alerts_tailer.py`:

```python
"""Following the Gamelogs folder.

Every awkward case here is one TriffView hit in production: replaying an
old fight on enable, a read landing mid-write, and a log rotating under
the reader.
"""

import datetime

import pytest

from obs_youtube_uploader.alerts import tailer

UTC = datetime.UTC
NOW = datetime.datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

HEADER = (
    "------------------------------------------------------------\n"
    "  Gamelog\n"
    "  Listener: {name}\n"
    "  Session Started: 2026.08.25 11:00:00\n"
    "------------------------------------------------------------\n"
)
DAMAGE = (
    "[ 2026.08.25 11:30:00 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>\n"
)


def _log(folder, name, body="", stem="20260825_110000_123"):
    path = folder / f"{stem}.txt"
    path.write_text(HEADER.format(name=name) + body, encoding="utf-8")
    return path


def test_a_preexisting_file_is_opened_at_its_end(tmp_path):
    """Ticking Enable must not replay this morning's fight as a burst of
    alerts. This is the single most user-visible rule in the module."""
    _log(tmp_path, "Alice", DAMAGE)
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.poll() == []


def test_lines_appended_after_the_first_rescan_are_emitted(tmp_path):
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(DAMAGE)
    events = t.poll()
    assert [(e.character, e.event) for e in events] == [("Alice", "combat")]


def test_a_file_appearing_later_is_read_from_the_start(tmp_path):
    """A client that logs in mid-session is live, so its whole log is new
    -- unlike one that was already there when alerts were switched on."""
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    _log(tmp_path, "Bravo", DAMAGE, stem="20260825_113000_456")
    t.rescan(NOW)
    assert [e.character for e in t.poll()] == ["Bravo"]


def test_a_partial_trailing_line_is_buffered_until_its_newline(tmp_path):
    """A poll can land mid-write. Emitting half a line drops the event,
    because the colour code and the source are at opposite ends of it."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    head, tail = DAMAGE[:40], DAMAGE[40:]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(head)
    assert t.poll() == []
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(tail)
    assert len(t.poll()) == 1


def test_truncation_resets_the_read_position(tmp_path):
    """If the file shrank it rotated. Without the reset the reader sits
    past the end and never emits again for that character."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    path.write_text(HEADER.format(name="Alice") + DAMAGE, encoding="utf-8")
    assert len(t.poll()) == 1


def test_files_older_than_the_cutoff_are_ignored(tmp_path):
    import os

    path = _log(tmp_path, "Alice", DAMAGE)
    old = (NOW - datetime.timedelta(hours=13)).timestamp()
    os.utime(path, (old, old))
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.characters() == []


def test_a_listener_of_EVE_is_not_a_character(tmp_path):
    """A client sitting at character-select writes a log with no pilot.
    Treating it as one produces a character nothing can ever alert."""
    _log(tmp_path, "EVE", DAMAGE)
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.characters() == []


def test_the_newest_session_wins_when_one_character_has_several_logs(tmp_path):
    """A relog leaves the old log on disk. Reading both would alert twice
    for one event, and the stale one never gets new lines anyway."""
    _log(tmp_path, "Alice", stem="20260825_100000_1")
    newer = _log(tmp_path, "Alice", stem="20260825_113000_1")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(newer, "a", encoding="utf-8") as fh:
        fh.write(DAMAGE)
    assert len(t.poll()) == 1


def test_undecodable_bytes_do_not_kill_the_tailer(tmp_path):
    """One bad byte must cost one line, not the feature for the session."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(path, "ab") as fh:
        fh.write(b"\xff\xfe garbage\n")
        fh.write(DAMAGE.encode("utf-8"))
    assert len(t.poll()) == 1


def test_a_missing_folder_is_not_an_error(tmp_path):
    """The folder can be deleted or unmounted while running; that is a
    quiet tailer, not a crashed one."""
    t = tailer.Tailer(tmp_path / "gone")
    t.rescan(NOW)
    assert t.poll() == [] and t.characters() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_alerts_tailer.py -q`
Expected: FAIL — `ImportError: cannot import name 'tailer'`

- [ ] **Step 3: Write the implementation**

Create `obs_youtube_uploader/alerts/tailer.py`:

```python
"""Follow the EVE Gamelogs folder and turn new lines into events.

Polled, not watched: there is no FileSystemWatcher in the standard
library and watchdog would be a new runtime dependency. TriffView polls
at 1s anyway underneath its watcher, so this is its mechanism without
its optimisation, and one second of latency on "you are being shot" does
not change the decision the alert exists to prompt.

rescan() and poll() are separate and take no locks, so the thread in
service.py drives them on its own cadence and the tests drive them
directly.
"""

import datetime
import logging
from pathlib import Path
from typing import NamedTuple

from .. import combatlog
from . import patterns

logger = logging.getLogger(__name__)

UTC = datetime.UTC

# Bounds the working set on a machine with months of logs.
MAX_AGE = datetime.timedelta(hours=12)
# Matches combatlog.MAX_FILES. Six clients that each relog once inside the
# cutoff is already twelve real logs before stubs, and combatlog.py:48-50
# records that character-less stubs are 47% of a real folder -- which is
# why the cap is applied AFTER header filtering, not before.
MAX_FILES = 64


class Event(NamedTuple):
    character: str
    event: str
    source: str


class _Tracked:
    __slots__ = ("path", "position", "partial")

    def __init__(self, path: Path, position: int):
        self.path = path
        self.position = position
        self.partial = ""


class Tailer:
    def __init__(self, folder: Path):
        self._folder = Path(folder)
        # character -> _Tracked. One log per character: a relog leaves the
        # old file on disk and reading both would alert twice.
        self._tracked: dict[str, _Tracked] = {}
        self._seen_first_scan = False

    def characters(self) -> list[str]:
        return sorted(self._tracked)

    def rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and attribute them to characters."""
        candidates = []
        try:
            entries = list(self._folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", self._folder)
            return
        cutoff = now_utc - MAX_AGE
        for path in entries:
            try:
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, UTC)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            header = combatlog.parse_header(path)
            if header is None or header.listener.strip().upper() == "EVE":
                # No pilot logged in. Excluding these here keeps them from
                # consuming the cap.
                continue
            candidates.append((header, path, mtime))

        # Newest first, then capped: an unordered cap drops live logs.
        candidates.sort(key=lambda c: c[0].session_start, reverse=True)
        best: dict[str, tuple] = {}
        for header, path, mtime in candidates[:MAX_FILES]:
            best.setdefault(header.listener, (path, mtime))

        for character, (path, _mtime) in best.items():
            existing = self._tracked.get(character)
            if existing is not None and existing.path == path:
                continue
            # A file already on disk at the first scan is history; one that
            # appears later is live. Without this, enabling alerts replays
            # the morning's fight as a burst.
            start = 0
            if not self._seen_first_scan:
                try:
                    start = path.stat().st_size
                except OSError:
                    start = 0
            self._tracked[character] = _Tracked(path, start)

        for character in list(self._tracked):
            if character not in best:
                del self._tracked[character]

        self._seen_first_scan = True

    def poll(self) -> list[Event]:
        """Read whatever has been appended since the last call."""
        events: list[Event] = []
        for character, tracked in self._tracked.items():
            events.extend(self._read(character, tracked))
        return events

    def _read(self, character: str, tracked: _Tracked) -> list[Event]:
        try:
            size = tracked.path.stat().st_size
        except OSError:
            return []
        if size < tracked.position:
            # Smaller than where we were: the file rotated.
            tracked.position = 0
            tracked.partial = ""
        if size == tracked.position:
            return []
        try:
            with open(tracked.path, "rb") as fh:
                fh.seek(tracked.position)
                chunk = fh.read(size - tracked.position)
                tracked.position = fh.tell()
        except OSError:
            return []

        text = tracked.partial + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # The last element is whatever follows the final newline: either
        # empty, or half a line that is still being written.
        tracked.partial = lines.pop()

        events = []
        for line in lines:
            match = patterns.match_line(line)
            if match is not None:
                events.append(Event(character, match.event, match.source))
        return events
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_alerts_tailer.py -q`
Expected: PASS (parametrized cases expand the count).

- [ ] **Step 5: Lint and commit**

```bash
git add obs_youtube_uploader/alerts/tailer.py tests/test_alerts_tailer.py
git commit -m "alerts: tail the Gamelogs folder without replaying history"
```

---

### Task 6: The settings schema, and the copy branch that stops it vanishing

The sharpest trap in the change. `validated_preview` rebuilds the section from
`_preview_defaults()` at `settings.py:145` and copies across **only** the keys it
explicitly handles, and `_normalize` runs it on every `update()`
(`settings.py:302`, `:387`). Add `alerts` to the defaults without adding the copy
branch and the user's colours revert within a second of them dragging a preview,
via `LayoutStore`'s debounce — no crash, no log line.

**Files:**
- Modify: `obs_youtube_uploader/settings.py:19-44` (defaults), `:142-188` (validation)
- Test: `tests/test_settings_alerts.py`

**Interfaces:**
- Consumes: `alerts.patterns.EVENTS` (Task 2).
- Produces:
  - `settings._alerts_defaults() -> dict`
  - `settings.validated_alerts(raw) -> dict`
  - `settings.VALID_SOUNDS: set[str]` — `{"none", "chime", "bell"}`
  - `preview["alerts"]` in every loaded document.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_alerts.py`:

```python
"""Alert section validation. Mirrors test_settings_preview.py's cases.

The clobber test at the bottom is the one that matters: it is the failure
mode that produces no error and loses the user's configuration.
"""

import json

import pytest

from obs_youtube_uploader import settings


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_whole_section_of_wrong_type_falls_back(raw):
    assert settings.validated_alerts(raw) == settings._alerts_defaults()


def test_alerts_ship_off():
    """Enabling costs a polling thread on top of the preview thread."""
    assert settings._alerts_defaults()["enabled"] is False


def test_the_filter_and_persistence_ship_on():
    """The filter is what makes combat mean "a player is shooting you",
    and that is what makes a persistent alert tolerable rather than a
    ring that never stops during a Sleeper site."""
    d = settings._alerts_defaults()
    assert d["pve_filter"] is True and d["persist_until_selected"] is True


def test_every_parser_event_has_a_config_entry():
    """The schema is built from patterns.EVENTS. If the two drift, the
    section grows an event the renderer cannot draw, or loses one the
    tailer will emit."""
    from obs_youtube_uploader.alerts import patterns

    assert set(settings._alerts_defaults()["events"]) == set(patterns.EVENTS)


@pytest.mark.parametrize(
    "key,given,expected",
    [
        ("cooldown_s", -5, 0),
        ("cooldown_s", 9999, 120),
        ("duration_ms", 1, 250),
        ("duration_ms", 999999, 15000),
        ("pulses", 0, 1),
        ("pulses", 99, 16),
    ],
)
def test_event_numbers_are_clamped(key, given, expected):
    out = settings.validated_alerts({"events": {"combat": {key: given}}})
    assert out["events"]["combat"][key] == expected


def test_a_bad_colour_falls_back_rather_than_reaching_pillow():
    """chrome.render passes the colour straight to Pillow, which raises on
    a malformed value -- on the preview thread, inside the paint path."""
    out = settings.validated_alerts({"events": {"combat": {"color": "red"}}})
    assert out["events"]["combat"]["color"] == "#ff4d4d"


def test_an_unknown_sound_becomes_silence_not_a_crash():
    out = settings.validated_alerts({"events": {"combat": {"sound": "airhorn"}}})
    assert out["events"]["combat"]["sound"] == "none"


def test_booleans_are_not_accepted_as_numbers():
    """bool is an int in Python; True would silently become a 1s cooldown."""
    out = settings.validated_alerts({"events": {"combat": {"cooldown_s": True}}})
    assert out["events"]["combat"]["cooldown_s"] == 1


def test_one_malformed_event_drops_alone():
    """Same two-tier posture validated_preview already documents: a
    corrupt entry costs that event, not the whole section."""
    out = settings.validated_alerts(
        {"events": {"combat": {"cooldown_s": 7}, "decloak": "nonsense"}}
    )
    assert out["events"]["combat"]["cooldown_s"] == 7
    assert out["events"]["decloak"] == settings._alerts_defaults()["events"]["decloak"]


def test_unknown_events_are_dropped():
    """A hand-edited file must not be able to produce an event the
    renderer has no colour or severity rank for."""
    out = settings.validated_alerts({"events": {"nonsense": {"enabled": True}}})
    assert "nonsense" not in out["events"]


def test_the_section_survives_a_load_round_trip(tmp_path):
    """The key must be in _preview_defaults(), or validated_preview drops
    it from the section on every load and every update()."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["alerts"]["events"]["combat"]["color"] = "#00ff00"
    settings.save(data, path)
    loaded = settings.load(path)
    assert loaded["preview"]["alerts"]["events"]["combat"]["color"] == "#00ff00"


def test_a_layout_write_does_not_reset_the_alerts_section(tmp_path):
    """The regression this whole task exists to prevent.

    validated_preview rebuilds the section from _preview_defaults() on
    every _normalize, which every update() runs. A writer that touches
    only `layouts` -- which LayoutStore does, debounced by one second
    after any drag -- would silently revert the user's alert colours if
    `alerts` had no copy branch. No crash, no log line, and the user
    finds out the next time they look at the card.
    """
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["alerts"]["events"]["combat"]["color"] = "#00ff00"
    data["preview"]["alerts"]["persist_until_selected"] = False
    settings.save(data, path)

    live = settings.load(path)
    with settings.update(live, path) as doc:
        doc["preview"]["layouts"]["Alice"] = {"x": 1, "y": 2, "w": 3, "h": 4}

    on_disk = json.loads(path.read_text(encoding="utf-8"))["preview"]["alerts"]
    assert on_disk["events"]["combat"]["color"] == "#00ff00"
    assert on_disk["persist_until_selected"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings_alerts.py -q`
Expected: FAIL — `AttributeError: module 'obs_youtube_uploader.settings' has no attribute 'validated_alerts'`

- [ ] **Step 3: Add the defaults**

In `obs_youtube_uploader/settings.py`, add the import beside the existing
`preview` ones (around line 14-16):

```python
from .alerts import patterns as alert_patterns
```

`alerts/patterns.py` imports nothing from this package, so this cannot cycle —
the same reason `preview.gestures` can be imported here.

Add above `_preview_defaults()`:

```python
# Sounds that ship. An id present in the UI dropdown but missing here
# normalises to silence, which is indistinguishable from a broken alert --
# so the two lists are checked against the assets folder in the sound task.
VALID_SOUNDS = {"none", "chime", "bell"}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Per-event shape. Colours are picked so the three are distinguishable at a
# glance on a small tile: red for damage, yellow for "you cannot leave",
# cyan for a decloak.
_ALERT_EVENT_DEFAULTS = {
    "combat": {"cooldown_s": 1, "color": "#ff4d4d", "sound": "chime"},
    "warp_scramble": {"cooldown_s": 8, "color": "#ffd24d", "sound": "bell"},
    "decloak": {"cooldown_s": 8, "color": "#4dd2ff", "sound": "chime"},
}


def _alerts_defaults() -> dict:
    """Fresh nested structure every call, like _preview_defaults.

    Off by default: enabling costs a second thread and a 1s folder poll on
    top of what previews already pay.
    """
    return {
        "enabled": False,
        # The filter is what makes `combat` mean "a player is shooting
        # you". Without it a Sleeper site alerts continuously on every
        # client, and a player landing mid-site is indistinguishable from
        # the NPCs already firing.
        "pve_filter": True,
        # An alert that expires while you are in a browser has told you
        # nothing, which is the whole case for the feature.
        "persist_until_selected": True,
        # Carried from the start on TriffView's evidence: it needed exactly
        # this migration, and rewrote only values that still equalled the
        # previous default so a customised setting was never overwritten.
        # No migration code exists yet and none should: at version 1 there
        # is nothing to migrate from. The field is here so a future v2 can
        # compare against a retained table of v1 defaults -- building that
        # harness now would be speculative machinery with no caller.
        "defaults_version": 1,
        "events": {
            name: {
                "enabled": True,
                "duration_ms": 1200,
                "pulses": 3,
                **_ALERT_EVENT_DEFAULTS[name],
            }
            for name in alert_patterns.EVENTS
        },
    }
```

Add `import re` to the module imports if it is not already there.

Then add the key to `_preview_defaults()`'s returned dict, after
`"restore_preview_positions": True,`:

```python
        "alerts": _alerts_defaults(),
```

- [ ] **Step 4: Add the validator and the copy branch**

Add beside `validated_preview`:

```python
def _validated_alert_event(raw, defaults: dict) -> dict:
    event = dict(defaults)
    if not isinstance(raw, dict):
        return event
    if isinstance(raw.get("enabled"), bool):
        event["enabled"] = raw["enabled"]
    for key, low, high in (
        ("cooldown_s", 0, 120),
        ("duration_ms", 250, 15000),
        ("pulses", 1, 16),
    ):
        value = raw.get(key)
        # `not isinstance(value, bool)` because bool is an int in Python,
        # and True would silently become a one-second cooldown.
        if isinstance(value, int) and not isinstance(value, bool):
            event[key] = max(low, min(high, value))
    colour = raw.get("color")
    if isinstance(colour, str) and _HEX_RE.match(colour):
        # Rejected rather than coerced: chrome.render hands this to Pillow,
        # which raises on a malformed value -- on the preview thread, inside
        # the paint path.
        event["color"] = colour
    sound = raw.get("sound")
    if isinstance(sound, str):
        event["sound"] = sound if sound in VALID_SOUNDS else "none"
    return event


def validated_alerts(raw) -> dict:
    """Same two-tier posture as validated_preview: a malformed section
    falls back whole, a malformed event falls back alone."""
    section = _alerts_defaults()
    if not isinstance(raw, dict):
        return section
    for key in ("enabled", "pve_filter", "persist_until_selected"):
        if isinstance(raw.get(key), bool):
            section[key] = raw[key]
    version = raw.get("defaults_version")
    if isinstance(version, int) and not isinstance(version, bool):
        section["defaults_version"] = max(1, version)
    raw_events = raw.get("events")
    if isinstance(raw_events, dict):
        # Iterating EVENTS rather than raw_events is what drops an unknown
        # event: a hand-edited file cannot introduce one the renderer has
        # no colour or severity rank for.
        for name in alert_patterns.EVENTS:
            section["events"][name] = _validated_alert_event(
                raw_events.get(name), section["events"][name]
            )
    return section
```

And in `validated_preview`, before `return section` (currently `settings.py:188`):

```python
    # Without this line the whole section is rebuilt from defaults on every
    # _normalize -- which every update() runs -- so any writer touching any
    # preview key silently reverts the user's alert configuration.
    section["alerts"] = validated_alerts(raw.get("alerts"))
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_settings_alerts.py -q`
Expected: PASS (parametrized cases expand the count).

Run: `python -m pytest -q`
Expected: PASS. `tests/test_settings.py:9` asserts `settings.DEFAULTS` as a
literal — if it fails, the new key has to be reflected there too.

- [ ] **Step 6: Lint and commit**

```bash
git add obs_youtube_uploader/settings.py tests/test_settings_alerts.py
git commit -m "settings: an alerts section that survives a layout write"
```

---

### Task 7: `alerts/service.py` — cooldowns, filter, sound, health, lifecycle

Owns everything between a tailer event and the preview thread. The decision core
(`_handle`) is a plain method taking `now`, so cooldowns and the filter are
covered on Linux; the thread is thin and drives it.

Note `host.reconcile()` already exists as an unrelated pure set-diff helper
(`preview/host.py:30-36`). This is `AlertService.reconcile()`, a lifecycle
method. Different module, different thing.

**Files:**
- Create: `obs_youtube_uploader/alerts/service.py`
- Test: `tests/test_alerts_service.py`

**Interfaces:**
- Consumes: `patterns.FILTERED_EVENTS`, `patterns.is_likely_npc` (Task 2);
  `tailer.Tailer`, `tailer.Event` (Task 5).
- Produces:
  - `class Health(NamedTuple): running: bool; last_poll: float | None; last_error: str | None; characters: tuple[str, ...]`
  - `class AlertService:`
    - `__init__(self, config, folder, on_alert, *, sound=None, clock=time.monotonic)` —
      `config` and `folder` are **callables**, not values.
    - `reconcile(self) -> None`
    - `health(self) -> Health`
    - `stop(self) -> None`
    - `_handle(self, events, now) -> list[tuple[str, str, str]]` — the tested core.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alerts_service.py`:

```python
"""Cooldowns, the NPC filter, health, and lifecycle.

_handle takes `now` and returns what it dispatched, so the whole decision
layer is covered without a thread or a clock.
"""

from obs_youtube_uploader.alerts import service, tailer

PLAYER = "Bob Smith[BURN](Rifter)"
NPC = "Sleepless Sentinel"


def _config(**over):
    cfg = {
        "enabled": True,
        "pve_filter": True,
        "persist_until_selected": True,
        "defaults_version": 1,
        "events": {
            "combat": {"enabled": True, "cooldown_s": 1, "color": "#ff4d4d",
                       "sound": "chime", "duration_ms": 1200, "pulses": 3},
            "warp_scramble": {"enabled": True, "cooldown_s": 8, "color": "#ffd24d",
                              "sound": "bell", "duration_ms": 1200, "pulses": 3},
            "decloak": {"enabled": True, "cooldown_s": 8, "color": "#4dd2ff",
                        "sound": "chime", "duration_ms": 1200, "pulses": 3},
        },
    }
    cfg.update(over)
    return cfg


def _service(config=None, sounds=None):
    cfg = config or _config()
    return service.AlertService(
        config=lambda: cfg,
        folder=lambda: None,
        on_alert=lambda *a: None,
        sound=(sounds.append if sounds is not None else lambda _id: None),
    )


def test_a_player_attack_is_dispatched():
    s = _service()
    out = s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert [e[1] for e in out] == ["combat"]


def test_an_npc_attack_is_filtered():
    """Sleeper sites put every client under continuous NPC fire. Without
    this the border never stops and a player landing mid-site is
    indistinguishable from the NPCs already firing."""
    s = _service()
    assert s._handle([tailer.Event("Alice", "combat", NPC)], 0.0) == []


def test_the_filter_also_covers_scrambles():
    """Sleepers and Drifters apply warp disruption routinely. Filtering
    only combat would leave any site producing a continuous, persistent,
    top-severity alert on every client."""
    s = _service()
    assert s._handle([tailer.Event("Alice", "warp_scramble", NPC)], 0.0) == []


def test_the_filter_does_not_touch_decloak():
    """Its line carries no attacker source, so an empty source must not
    be read as "bare name, therefore NPC" and swallowed."""
    s = _service()
    assert len(s._handle([tailer.Event("Alice", "decloak", "")], 0.0)) == 1


def test_the_filter_can_be_turned_off():
    s = _service(_config(pve_filter=False))
    assert len(s._handle([tailer.Event("Alice", "combat", NPC)], 0.0)) == 1


def test_a_second_event_inside_the_cooldown_is_suppressed():
    s = _service()
    ev = tailer.Event("Alice", "combat", PLAYER)
    assert len(s._handle([ev], 0.0)) == 1
    assert s._handle([ev], 0.5) == []
    assert len(s._handle([ev], 1.5)) == 1


def test_cooldowns_are_per_character_and_per_event():
    """One character being shot must not silence another's alert, and a
    scramble must not be swallowed by a combat cooldown."""
    s = _service()
    assert len(s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)) == 1
    assert len(s._handle([tailer.Event("Bravo", "combat", PLAYER)], 0.0)) == 1
    assert len(s._handle([tailer.Event("Alice", "warp_scramble", PLAYER)], 0.0)) == 1


def test_a_disabled_event_dispatches_nothing_and_burns_no_cooldown():
    cfg = _config()
    cfg["events"]["combat"]["enabled"] = False
    s = _service(cfg)
    assert s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0) == []


def test_a_suppressed_event_plays_no_sound():
    """Cooldown is checked before anything else happens. A suppressed
    event that still made a noise would be the worst of both."""
    sounds = []
    s = _service(sounds=sounds)
    ev = tailer.Event("Alice", "combat", PLAYER)
    s._handle([ev], 0.0)
    s._handle([ev], 0.5)
    assert sounds == ["chime"]


def test_a_sound_of_none_is_not_played():
    cfg = _config()
    cfg["events"]["combat"]["sound"] = "none"
    sounds = []
    s = _service(cfg, sounds=sounds)
    s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)
    assert sounds == []


def test_config_is_read_per_event_not_captured():
    """settings._normalize reassigns data["preview"] wholesale on every
    call, so a captured subtree is orphaned after the first write. The
    service holds a callable for exactly this reason."""
    cfg = _config()
    holder = {"cfg": cfg}
    s = service.AlertService(
        config=lambda: holder["cfg"],
        folder=lambda: None,
        on_alert=lambda *a: None,
        sound=lambda _id: None,
    )
    assert len(s._handle([tailer.Event("Alice", "combat", PLAYER)], 0.0)) == 1
    replacement = _config()
    replacement["events"]["combat"]["enabled"] = False
    holder["cfg"] = replacement
    assert s._handle([tailer.Event("Alice", "combat", PLAYER)], 10.0) == []


def test_health_reports_a_dead_thread():
    """A character count alone keeps reading "watching 4 characters"
    after the thread has died, which puts a healthy-looking card above a
    feature that has silently stopped alerting."""
    s = _service()
    assert s.health().running is False


def test_a_raising_poll_is_recorded_rather_than_killing_the_loop():
    s = _service()
    s._record_error(RuntimeError("disk gone"))
    assert "disk gone" in s.health().last_error
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_alerts_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'service'`

- [ ] **Step 3: Write the implementation**

Create `obs_youtube_uploader/alerts/service.py`:

```python
"""Between the tailer and the preview thread.

Owns the cooldown map, the NPC filter, sound, and the polling thread's
lifecycle. Everything it decides lives in _handle, which takes `now` and
returns what it dispatched -- so the decision layer is covered on
ubuntu-latest and the thread stays thin enough not to need covering.

Settings arrive through a CALLABLE, never a captured dict.
settings._normalize reassigns data["preview"] wholesale on every call
(settings.py:373-378), so a subtree captured at construction is orphaned
after the first write and this would silently run on stale config.
"""

import datetime
import logging
import threading
import time
from typing import NamedTuple

from . import patterns, tailer

logger = logging.getLogger(__name__)

UTC = datetime.UTC

POLL_INTERVAL_S = 1.0
RESCAN_INTERVAL_S = 5.0


class Health(NamedTuple):
    running: bool
    last_poll: float | None
    last_error: str | None
    characters: tuple[str, ...]


class AlertService:
    def __init__(self, config, folder, on_alert, *, sound=None, clock=time.monotonic):
        self._config = config
        self._folder = folder
        self._on_alert = on_alert
        self._sound = sound if sound is not None else play_sound
        self._clock = clock

        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._tailer = None
        # (character, event) -> when it last dispatched.
        self._cooldowns = {}
        self._last_poll = None
        self._last_error = None

    # ---- lifecycle -----------------------------------------------------

    def _wanted(self) -> bool:
        """Running iff previews are on, alerts are on, and a folder resolves.

        Gating on alerts as well as previews is what stops a user with
        previews on and alerts off paying for a polling thread.
        """
        cfg = self._config() or {}
        return bool(cfg.get("enabled")) and self._folder() is not None

    def reconcile(self) -> None:
        """Bring the thread in line with settings. Idempotent, any thread.

        Called from every setting that can change the answer, including
        the Gamelogs folder -- api.set_folder's gamelogs branch drives no
        watcher of its own, and the docstring above it records the bug
        that costs: a folder that persisted while the window looked
        healthy and nothing ever polled.
        """
        if not self._wanted():
            self.stop()
            return
        folder = self._folder()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._tailer is not None and self._tailer._folder == folder:
                    return
                # The folder moved. Tear down and rebuild rather than
                # repoint, so file positions cannot carry across.
                self._stop.set()
                thread = self._thread
                self._thread = None
            else:
                thread = None
        if thread is not None:
            thread.join(timeout=POLL_INTERVAL_S * 3)
        with self._lock:
            self._stop = threading.Event()
            self._tailer = tailer.Tailer(folder)
            self._cooldowns.clear()
            self._thread = threading.Thread(
                target=self._run, name="wingman-alerts", daemon=False
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread, self._thread = self._thread, None
            self._stop.set()
        if thread is not None:
            thread.join(timeout=POLL_INTERVAL_S * 3)

    def health(self) -> Health:
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            names = tuple(self._tailer.characters()) if self._tailer else ()
            return Health(alive, self._last_poll, self._last_error, names)

    def _record_error(self, exc: BaseException) -> None:
        with self._lock:
            self._last_error = f"{type(exc).__name__}: {exc}"

    # ---- the thread ----------------------------------------------------

    def _run(self) -> None:
        last_rescan = 0.0
        while not self._stop.is_set():
            try:
                now = self._clock()
                if now - last_rescan >= RESCAN_INTERVAL_S:
                    self._tailer.rescan(datetime.datetime.now(UTC))
                    last_rescan = now
                self._handle(self._tailer.poll(), now)
                with self._lock:
                    self._last_poll = now
            except Exception as exc:  # noqa: BLE001 - see below
                # Guarded deliberately: one unreadable file, a folder that
                # went away, or a decode surprise must cost one poll, not
                # the feature for the session. Recorded so the card can
                # say so -- silence is this feature's worst failure mode.
                logger.exception("Alert poll failed")
                self._record_error(exc)
            self._stop.wait(POLL_INTERVAL_S)

    # ---- the decision core ---------------------------------------------

    def _handle(self, events, now: float) -> list:
        """Filter, apply cooldowns, play sound, dispatch.

        Returns the dispatched (character, event, colour) triples, which is
        what the tests assert on.
        """
        cfg = self._config() or {}
        table = cfg.get("events") or {}
        pve = bool(cfg.get("pve_filter"))
        dispatched = []
        for event in events:
            spec = table.get(event.event)
            if not spec or not spec.get("enabled"):
                continue
            if (
                pve
                and event.event in patterns.FILTERED_EVENTS
                and patterns.is_likely_npc(event.source)
            ):
                continue
            key = (event.character, event.event)
            last = self._cooldowns.get(key)
            if last is not None and now - last < spec.get("cooldown_s", 0):
                # Checked before anything else happens: a suppressed event
                # is invisible everywhere, sound included.
                continue
            self._cooldowns[key] = now
            sound = spec.get("sound") or "none"
            if sound != "none":
                self._sound(sound)
            # persist_until_selected is global but travels merged into the
            # per-event spec, so PreviewWindow.arm_alert reads one dict and
            # the host does not have to know the section's shape.
            payload = dict(spec)
            payload["persist_until_selected"] = bool(cfg.get("persist_until_selected"))
            self._on_alert(event.character, event.event, payload)
            dispatched.append((event.character, event.event, spec.get("color")))
        return dispatched
```

`play_sound` is added in Task 11; until then, stub it at the bottom of the
module so the import resolves:

```python
def play_sound(sound_id: str) -> None:
    """Replaced in the sound task."""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_alerts_service.py -q`
Expected: PASS (parametrized cases expand the count).

- [ ] **Step 5: Lint and commit**

```bash
git add obs_youtube_uploader/alerts/service.py tests/test_alerts_service.py
git commit -m "alerts: cooldowns, the NPC filter, and a thread that reports its health"
```

---

### Task 8: `WM_APP_ALERT` and the host mailbox

`PostMessageW` is bound `[HWND, UINT, WPARAM, LPARAM]` (`win32.py:305`) and
carries integers only. The value travels in a lock-protected field and only the
signal is posted — the shape `_desired_hotkeys` already uses and documents
(`host.py:126-130`).

**Files:**
- Modify: `obs_youtube_uploader/preview/win32.py:52-54`
- Modify: `obs_youtube_uploader/preview/host.py:120-133`, `:289-308`
- Test: `tests/test_preview_host.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `win32.WM_APP_ALERT` — `WM_APP + 4`
  - `PreviewHost.raise_alert(character: str, event: str, spec: dict) -> None` —
    callable from any thread. This is the `on_alert` callback `AlertService`
    takes in Task 7.

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_preview_host.py`. Update the existing constant test at
`:271-286` from three commands to four, and add:

```python
def test_raise_alert_queues_without_a_window():
    """The service can raise before the pump exists: start() returns
    immediately and _hwnd is created later on the preview thread
    (host.py:139-147, :219-235). A queued alert must survive that gap
    rather than being posted into nothing."""
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert len(h._pending_alerts) == 1


def test_draining_returns_and_clears():
    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert len(h._drain_alerts()) == 1
    assert h._drain_alerts() == []


def test_raise_alert_posts_only_a_signal():
    """PostMessageW carries integers only, so wparam/lparam must stay
    zero and the payload must travel in the field."""
    posted = []

    class _User32:
        def PostMessageW(self, hwnd, msg, wparam, lparam):
            posted.append((msg, wparam, lparam))
            return 1

    h = host.PreviewHost(on_layout_changed=lambda *a: None)
    h._hwnd = 0x99
    h._post = lambda msg: posted.append((msg, 0, 0))
    h.raise_alert("Alice", "combat", {"color": "#ff4d4d"})
    assert posted == [(host.win32.WM_APP_ALERT, 0, 0)]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_preview_host.py -q`
Expected: FAIL — `AttributeError: 'PreviewHost' object has no attribute 'raise_alert'`

- [ ] **Step 3: Add the message constant**

`obs_youtube_uploader/preview/win32.py`, after line 54:

```python
WM_APP_ALERT = WM_APP + 4
```

- [ ] **Step 4: Add the mailbox**

In `PreviewHost.__init__`, beside `_desired_hotkeys`:

```python
        # Same shape as _desired_hotkeys above, and for the same reason:
        # PostMessageW carries integers only, so the payload travels in a
        # field under the lock and only the signal is posted. A list, not
        # one slot, because two clients can be alerted between ticks.
        self._pending_alerts = []
```

Add the public method beside `set_hotkeys`:

```python
    def raise_alert(self, character: str, event: str, spec: dict) -> None:
        """Queue an alert and nudge the pump. Safe from any thread.

        The queue is filled whether or not a window exists to post to:
        start() returns before the preview thread has created _hwnd, and
        an alert raised in that gap would otherwise be dropped.
        """
        with self._lock:
            self._pending_alerts.append((character, event, dict(spec)))
        self._post(win32.WM_APP_ALERT)

    def _post(self, msg) -> None:
        if self._hwnd:
            win32.bind().user32.PostMessageW(self._hwnd, msg, 0, 0)

    def _drain_alerts(self) -> list:
        with self._lock:
            pending, self._pending_alerts = self._pending_alerts, []
        return pending
```

Rewrite `request_sweep` to use `_post` so there is one guard rather than three.

In `_run`, after `self._ready.set()`, drain once — anything queued during
startup is delivered rather than waiting for the next event:

```python
        self._apply_alerts(libs, self._drain_alerts())
```

Add the dispatch branch in `_host_proc`, before the `WM_HOTKEY` branch:

```python
        if msg == win32.WM_APP_ALERT:
            self._apply_alerts(libs, self._drain_alerts())
            return 0
```

`_apply_alerts` is a stub in this task and filled in by Task 10:

```python
    def _apply_alerts(self, libs, pending) -> None:
        """Arm each alert on the preview showing that character."""
        for character, event, spec in pending:
            win = self._windows.get(character)
            if win is None:
                # No preview for that character -- it may be at
                # character-select, or its window failed to create. The
                # cooldown is already spent; see the design's note on why
                # that is accepted rather than acknowledged back.
                continue
            win.arm_alert(event, spec, time.monotonic())
        self._update_alert_timer(libs)
```

Add `import time` to `host.py`.

- [ ] **Step 5: Run, lint, commit**

Run: `python -m pytest tests/test_preview_host.py tests/test_preview_win32.py -q`

Add `WM_APP_ALERT` to `tests/test_preview_win32.py`'s `REQUIRED` list if it
enumerates message constants as well as function names.

```bash
git add obs_youtube_uploader/preview/win32.py obs_youtube_uploader/preview/host.py tests/
git commit -m "previews: a mailbox for alerts, because PostMessage carries integers"
```

---

### Task 9: Selection tracking, and a border only on the selected preview

`PreviewWindow.selected` is assigned `False` at `window.py:261` and never set
true by any code path. This task finally sets it, and drops `BORDER` from 5 to 2.

**Deviation from the spec, deliberate.** The design says selection resolves on
the 80 ms alert tick, to avoid racing the sweep. Resolving it *in* `_sweep` is
simpler and removes the race outright: `_sweep` is the only place `_clients` is
refreshed (`host.py:343`), the hook already posts a sweep
(`host.py:315-316`), and there is then one message rather than two whose order
could matter. It also means selection works with the alert timer stopped, which
the tick-based version would have needed a reason to arm. Record this in the
design doc when the task lands.

**Files:**
- Modify: `obs_youtube_uploader/preview/chrome.py:79-80`
- Modify: `obs_youtube_uploader/preview/window.py:30`, `:333-354`
- Modify: `obs_youtube_uploader/preview/host.py:310-333`, `:335-392`
- Test: `tests/test_preview_chrome.py`, `tests/test_preview_host.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `chrome.render(..., selected=...)` paints the ring only when `selected`.
  - `PreviewHost._selected_key: str | None`
  - `window.BORDER == 2`

- [ ] **Step 1: Write the failing tests**

`tests/test_preview_chrome.py` — replace the existing "selected draws a thicker
border" test:

```python
def test_an_unselected_preview_draws_no_ring():
    """The alert ring is then the only coloured ring on screen, which is
    what makes it legible on a small tile."""
    img = chrome.render((200, 150), "Alice", border_color=(0, 200, 220, 255),
                        border=2, selected=False)
    assert img.getpixel((0, 100))[:3] != (0, 200, 220)


def test_the_selected_preview_draws_its_ring():
    img = chrome.render((200, 150), "Alice", border_color=(0, 200, 220, 255),
                        border=2, selected=True)
    assert img.getpixel((0, 100))[:3] == (0, 200, 220)


def test_the_interior_stays_opaque_either_way():
    """Opacity is load-bearing, not cosmetic: a layered window is
    hit-tested against its own alpha, so a transparent pixel is
    click-through and drag breaks (chrome.py:22-30)."""
    for selected in (True, False):
        img = chrome.render((200, 150), "Alice", border_color=(0, 200, 220, 255),
                            border=2, selected=selected)
        assert img.getpixel((100, 100))[3] == 255
```

`tests/test_preview_host.py`:

```python
def test_the_foreground_client_becomes_the_selected_preview(monkeypatch):
    h = _swept_host(monkeypatch, ["Alice", "Bravo"], foreground=0x1000)
    assert h._selected_key == "Alice"


def test_a_foreground_window_that_is_not_a_client_selects_nothing(monkeypatch):
    """Deliberately not "the last EVE client used". A sticky highlight
    could not be told apart from an alert on that same client, and
    acknowledgement would clear alerts the user never saw."""
    h = _swept_host(monkeypatch, ["Alice"], foreground=0xDEAD)
    assert h._selected_key is None
```

`_swept_host` is a helper following the existing `_sweep` fake set — patch
`host.discovery.list_clients`, `host.discovery.flush_image_cache_periodically`,
`host.PreviewWindow.create`, `h._screen`, `h._monitors`, and add
`GetForegroundWindow` to the fake `libs.user32`.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_preview_chrome.py tests/test_preview_host.py -q`

- [ ] **Step 3: Paint the ring only when selected**

`chrome.py`, replacing lines 79-80:

```python
    # Only the selected preview carries a ring. An unselected one shows the
    # interior fill at the inset width instead -- near-black, which reads as
    # nothing over a dark desktop and as a thin dark edge over bright game
    # content. That is the intended look; see the design's Outcome section.
    if selected:
        d.rectangle([0, 0, w - 1, h - 1], outline=border_color, width=border)
```

- [ ] **Step 4: Drop BORDER to 2**

`window.py:30`: `BORDER = 2`.

This moves every existing preview's video area out by 3 px a side and shifts the
label band, because `BORDER` feeds `thumbnail_rect` (`:321`, `:375`) and
`chrome.render(border=BORDER)` (`:349`), where it also positions the label text
(`chrome.py:82-88`). Expected, and worth eyeballing in the smoke pass.

- [ ] **Step 5: Resolve selection in the sweep**

`host.py`, in `__init__`: `self._selected_key = None`.

In `_install_hook`, carry the hwnd rather than discarding it:

```python
        def on_event(hook, event, hwnd, obj, child, tid, ms):
            # Recorded, not resolved: this callback arrives on an arbitrary
            # thread and must not touch a preview. _sweep resolves it, which
            # is also the only place _clients is refreshed -- so a
            # just-launched client's first focus cannot resolve against a
            # stale registry.
            self._foreground = int(hwnd) if hwnd else 0
            self.request_sweep()
```

with `self._foreground = 0` in `__init__`.

At the end of `_sweep`, after `self._clients = clients` and the window
reconcile:

```python
        self._apply_selection(libs)
```

```python
    def _apply_selection(self, libs) -> None:
        """Mark the preview whose client owns the foreground window.

        Nothing is selected when the foreground is not an EVE client -- a
        browser, Discord, or Wingman itself. That is deliberate: a sticky
        "last client used" highlight could not be distinguished from an
        alert on that same client.
        """
        foreground = self._foreground or (
            libs.user32.GetForegroundWindow() if libs is not None else 0
        )
        key = next(
            (k for k, c in self._clients.items() if c.hwnd == foreground), None
        )
        if key == self._selected_key:
            return
        previous, self._selected_key = self._selected_key, key
        for candidate in (previous, key):
            win = self._windows.get(candidate) if candidate else None
            if win is not None:
                win.set_selected(candidate == key)
```

`window.py` gains:

```python
    def set_selected(self, selected: bool) -> None:
        if selected == self.selected:
            return
        self.selected = selected
        # In _chrome_key already (window.py:330), so this repaints.
        self.redraw()
```

- [ ] **Step 6: Run, lint, commit**

Run: `python -m pytest -q`

```bash
git add obs_youtube_uploader/preview/ tests/
git commit -m "previews: a border on the client you are looking at, and none on the rest"
```

---

### Task 10: The alert render path

The frame cache, the conditional inset, the forced redraw, and cleanup. Windows
only; CI covers the pure index arithmetic from Task 4 and nothing else here.

**Do not start this before Task 1's probe has run.** If a ring wider than the
inset turns out to render usefully, the conditional inset below is unnecessary
and should be dropped.

**Files:**
- Create: `obs_youtube_uploader/preview/alertframes.py`
- Modify: `obs_youtube_uploader/preview/window.py`
- Modify: `obs_youtube_uploader/preview/host.py`
- Test: `tests/test_preview_alertframes.py`

**Interfaces:**
- Consumes: `alerts.state` (Task 4); `win32` GDI bindings (existing).
- Produces:
  - `ALERT_BORDER = 6`, `BLINK_AREA = 640 * 480`, `frame_count(size) -> int`
  - `class FrameCache:` — `build(libs, size, label, selected, color)`,
    `frame_for(index)`, `close(libs)`
  - `PreviewWindow.arm_alert(event, spec, now)`, `.tick_alert(now)`,
    `.clear_alert()`
  - `PreviewHost._update_alert_timer(libs)`, `ALERT_TIMER_ID = 2`, `ALERT_MS = 80`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview_alertframes.py` — pure parts only, no DIBs:

```python
"""The size ceiling and the frame count. The GDI path itself is Windows
only and is covered by the smoke checklist, not here."""

from obs_youtube_uploader.preview import alertframes


def test_a_small_preview_gets_the_full_pulse():
    assert alertframes.frame_count((320, 210)) == 6


def test_a_large_preview_falls_back_to_a_blink():
    """Six frames at 1920x1080 is ~50MB held indefinitely under
    persistence, and a fleet-wide aggression arms every preview at once."""
    assert alertframes.frame_count((1920, 1080)) == 2


def test_the_ceiling_is_on_area_not_either_edge():
    """A wide, short preview and a tall, narrow one cost the same."""
    assert alertframes.frame_count((1280, 200)) == alertframes.frame_count((200, 1280))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_preview_alertframes.py -q`

- [ ] **Step 3: Write `alertframes.py`**

```python
"""Pre-rendered alert ring frames.

The flash must never go through PreviewWindow.redraw(): that method is
cache-keyed and a pulse defeats the key, putting a full Pillow render plus
a ~67k-pixel push on an 80ms timer -- "the cost that made dragging
stutter" (eve-preview-design.md:468-471).

So the frames are rendered once on arm, each into its own DIB with one
shared memory DC, and the tick does SelectObject plus UpdateLayeredWindow.
Cleanup is ordered the way layered.push documents at layered.py:63-67:
restore the DC's original object before deleting ours, or the DIBs leak
for the life of the process.
"""

import ctypes

from ..alerts import state
from . import chrome, win32

ALERT_BORDER = 6
# Above this area the cache falls back to a two-frame blink. Six frames at
# 320x210 is ~1.6MB; at 1920x1080 it is ~50MB, held for as long as an
# unacknowledged persistent alert lasts.
BLINK_AREA = 640 * 480


def frame_count(size) -> int:
    return 6 if size[0] * size[1] <= BLINK_AREA else 2


def alphas_for(size) -> tuple:
    n = frame_count(size)
    if n == len(state.FRAME_ALPHAS):
        return state.FRAME_ALPHAS
    return (state.FRAME_ALPHAS[0], state.FRAME_ALPHAS[-1])
```

The `FrameCache` class holds `_dcs`, `_dibs`, `_old`, builds each frame by
calling `chrome.render(size, label, border_color=colour_with_alpha,
border=ALERT_BORDER, selected=True)`, and exposes `close(libs)` performing the
ordered teardown. Follow `layered.push` (`layered.py:26-68`) for the
`CreateDIBSection` / `SelectObject` sequence, but keep the DC and DIBs rather
than destroying them per call.

- [ ] **Step 4: Wire the window**

`PreviewWindow` gains `self._alert = None` and `self._frames = None`, the import
`from ..alerts import state as alerts_state`, and:

```python
    def arm_alert(self, event: str, spec: dict, now: float) -> None:
        colour = spec.get("color", "#ff4d4d")
        self._alert = alerts_state.arm(
            self._alert, event, colour, now,
            duration_ms=spec.get("duration_ms", 1200),
            pulses=spec.get("pulses", 3),
            # Global, not per-event: persist_until_selected lives beside
            # `events` in the alerts section, and AlertService merges it
            # into the spec it dispatches so this stays one dict.
            persist=bool(spec.get("persist_until_selected")),
            target_is_selected=self.selected,
        )
        if self._frames is None or self._frames.colour != self._alert.color:
            self._rebuild_frames()
            # The ring is capped at the inset, so the inset has to grow for
            # the duration. Two DwmUpdateThumbnailProperties calls per alert
            # -- on arm and on clear -- not one per tick.
            self._set_inset(alertframes.ALERT_BORDER)

    def tick_alert(self, now: float) -> bool:
        """Push the current phase. Returns False when the alert is done."""
        self._alert = alerts_state.clear_expired(self._alert, now)
        if self._alert is None:
            self.clear_alert()
            return False
        self._frames.push(self._libs, self.hwnd, self.rect,
                          alerts_state.frame_index(self._alert, now))
        return True

    def clear_alert(self) -> None:
        self._alert = None
        if self._frames is not None:
            self._frames.close(self._libs)
            self._frames = None
        self._set_inset(BORDER)
        # force=True: pushing alert frames does not change _chrome_key, so
        # redraw() would early-return (window.py:341-343) and the last alert
        # frame would stay on screen.
        self.redraw(force=True)

    def acknowledge_alert(self) -> bool:
        if alerts_state.acknowledge(self._alert) is None and self._alert is not None:
            self.clear_alert()
            return True
        return False
```

`_set_inset(px)` stores the inset and calls
`self._thumb.update(geometry.thumbnail_rect(self.rect, px, LABEL_H))`. Every
existing `thumbnail_rect` call site (`:321`, `:375`) uses the stored inset
rather than `BORDER` directly.

`close()` (`window.py:478-485`) must call `self.clear_alert()` before destroying
the window, or the DIBs leak when a client quits mid-alert.

Acknowledge-on-click: in `_on_message`'s `WM_LBUTTONUP` branch, where `action ==
"activate"`, call `self.acknowledge_alert()` **before** `activate(...)` and
regardless of its result. Windows refuses foreground changes from a process
without recent input (`window.py:102-116`), and acknowledging only on real
foreground would leave the ring pulsing forever with clicking it doing nothing.

- [ ] **Step 5: Wire the host timer**

`ALERT_TIMER_ID = 2`, `ALERT_MS = 80` in `host.py`. `_update_alert_timer(libs)`
starts the timer when any window has a live alert and kills it when none does.
`_host_proc` gains a `WM_TIMER`/`ALERT_TIMER_ID` branch calling `_tick_alerts`,
which ticks every armed window, acknowledges the selected one, and calls
`_update_alert_timer` again. `_teardown` (`host.py:650-660`) kills
`ALERT_TIMER_ID` alongside `SWEEP_TIMER_ID`.

- [ ] **Step 6: Run, lint, commit**

Run: `python -m pytest -q`

```bash
git add obs_youtube_uploader/preview/ tests/
git commit -m "previews: pulse a pre-rendered ring without going through redraw"
```

---

### Task 11: Sounds, and the packaging entry that makes them exist

**Files:**
- Create: `obs_youtube_uploader/assets/sounds/chime.wav`, `bell.wav`
- Modify: `obs_youtube_uploader/alerts/service.py`
- Modify: `packaging/uploader.spec`
- Test: `tests/test_alerts_sound.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Sound ids, resolution, and the packaging entry.

The frozen build is where this breaks and nowhere else, so the tests
assert on paths and the spec file rather than on playback.
"""

from obs_youtube_uploader import settings
from obs_youtube_uploader.alerts import service


def test_every_valid_sound_has_a_file():
    """An id in the dropdown with no file behind it plays nothing, which
    is indistinguishable from a broken alert."""
    for name in settings.VALID_SOUNDS - {"none"}:
        assert service.sound_path(name).is_file(), name


def test_an_unknown_id_resolves_to_none():
    assert service.sound_path("airhorn") is None


def test_the_spec_collects_the_sounds_folder():
    """chrome.py's font is collected to a destination that does not match
    where it looks (assets/fonts vs obs_youtube_uploader/assets/fonts), so
    it is not the precedent to copy. These go through paths.bundle_dir()."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert "assets/sounds" in spec or "assets\\\\sounds" in spec
```

- [ ] **Step 2: Add the sounds**

Two short WAVs, CC0 or self-generated, under a second each. Record their
provenance in `THIRD-PARTY-NOTICES.md` if they are not self-generated.

- [ ] **Step 3: Implement resolution and playback**

Replace the `play_sound` stub in `service.py`:

```python
def sound_path(sound_id: str):
    """Resolve a sound id to a file, or None.

    Through paths.bundle_dir(), NOT Path(__file__).parent: uploader.spec
    collects to a destination bundle_dir() resolves, which is the whole
    reason the web/ destination was chosen the way it was
    (uploader.spec:32-36). chrome.py's font handling does the other thing
    and is very likely broken in the frozen build -- do not copy it.
    """
    if sound_id in (None, "", "none"):
        return None
    candidate = paths.bundle_dir() / "assets" / "sounds" / f"{sound_id}.wav"
    return candidate if candidate.is_file() else None


def play_sound(sound_id: str) -> None:
    path = sound_path(sound_id)
    if path is None:
        # Logged, not silent: a missing file looks exactly like a broken
        # alert from the user's side.
        logger.warning("No sound file for id %r; alert will be silent", sound_id)
        return
    try:
        import winsound  # Deferred: CI is ubuntu-latest.
    except ImportError:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError:
        logger.exception("Could not play alert sound %s", path)
```

- [ ] **Step 4: Add the packaging entry**

In `packaging/uploader.spec`'s `datas`, beside the fonts entry at `:63`:

```python
    (str(ROOT / "obs_youtube_uploader" / "assets" / "sounds"), "assets/sounds"),
```

- [ ] **Step 5: Run, lint, commit**

```bash
git add obs_youtube_uploader/assets/sounds/ obs_youtube_uploader/alerts/service.py packaging/uploader.spec tests/
git commit -m "alerts: ship two sounds, and collect them in the frozen build"
```

---

### Task 12: Bridge methods and the one reconciliation path

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py:1527-1549`, `:1633-1701`, and a new alerts block
- Modify: `obs_youtube_uploader/__main__.py:321-397`, `:591-597`
- Test: `tests/test_alerts_wiring.py`

**Interfaces:**
- Produces: `set_alert_enabled`, `set_alert_pve_filter`, `set_alert_persist`,
  `set_alert_event(event, field, value)`, `test_alert(event)`,
  `get_alert_state()`, each returning `{applied, persisted, error}`.

`_write_setting` (`api.py:1420`) writes **top-level** scalars only — it cannot
reach `preview.alerts`. Follow `set_restore_preview_positions`
(`api.py:1852-1853`), which hand-rolls `settings_mod.update` plus
`doc.setdefault("preview", {})`. Add one private `_write_alert_setting(path,
value)` helper rather than repeating that six times.

Every one of these calls `self._alerts.reconcile()` afterwards, and so does
`set_preview_enabled`, `start_previews_if_enabled`, `shutdown_previews`, and
`set_folder`'s gamelogs branch. Tests must pin all five, because the gamelogs
one is the case with a documented precedent for going wrong.

Key tests:

```python
def test_changing_the_gamelogs_folder_repoints_the_tailer(tmp_path):
    """set_folder's gamelogs branch drives no watcher of its own, and the
    docstring above it records exactly what that costs: a folder that
    persisted while the window looked healthy and nothing ever polled."""
    ...

def test_turning_previews_off_stops_the_tailer(tmp_path):
    """Otherwise it keeps polling and winsound keeps firing with nothing
    on screen to explain it."""
    ...

def test_alerts_off_means_no_thread_even_with_previews_on(tmp_path):
    ...

def test_a_test_alert_is_never_persistent(tmp_path):
    """The user is looking at Wingman, so no preview is selected and
    nothing would acknowledge it -- it would pulse until they alt-tabbed
    to that client."""
    ...
```

`__main__.py` builds the service beside `build_preview_host` and passes
`config=lambda: state.settings["preview"]["alerts"]` — a callable, per the
stale-snapshot rule — and `on_alert=host.raise_alert`.

```bash
git commit -m "alerts: one reconciliation path, including the folder nobody watched"
```

---

### Task 13: The Alerts card

**Files:**
- Modify: `obs_youtube_uploader/web/index.html:382` (a third card inside `#section-previews`)
- Create: `obs_youtube_uploader/web/alerts.js`
- Modify: `obs_youtube_uploader/web/app.js:49-55` (`WM.HANDLERS`), `dev.js`
- Modify: `obs_youtube_uploader/web/style.css:766`
- Test: `tests/test_alerts_wiring.py`

Constraints the existing tests impose:

- The card goes **after** the second card, not inside the first.
  `test_the_position_checkbox_sits_with_the_preview_settings`
  (`test_preview_wiring.py:527-528`) splits the first card on `<section`, so
  inserting inside it breaks that test.
- A new push handler is a two-file edit: the name must be in `WM.HANDLERS`
  (`app.js:49-55`) **and** registered via `WM.handle`, or
  `tests/test_bridge_contract.py` fails. Prefer a read
  (`get_alert_state`) over a push, following `get_preview_hotkey_state`'s
  reasoning at `api.py:1758-1761` — the page asks on `wm:section`.
- `_settings_payload` is a shallow `dict(cfg)` (`api.py:1287`), so
  `preview.alerts` reaches the page through `wm:settings` for free. The three
  checkboxes can hydrate from that; the health line needs the read.
- `dev.js`'s `settingsPayload` has no `preview` key at all — add one with an
  `alerts` subtree so the card is eyeballable under `?dev=1`, and add a
  `get_alert_state` stub.

The card markup follows the existing `.check`/`.box` pattern (a bare checkbox
renders as a native white widget, `index.html:340-342`). The health line is a
`.hint` rendered from `get_alert_state`, and it never shows a character count
without the thread's liveness beside it.

Tests assert on source text, the way `test_preview_wiring.py` does — there is no
JS harness. Pin: the card is inside `#section-previews`; the three states are
each reachable in `alerts.js`; the count and the health flag are rendered
together; a failed write says the choice will not survive a restart, following
`test_the_position_toggle_says_when_the_choice_will_not_survive`
(`:534-543`).

```bash
git commit -m "alerts: a card that says when it is not watching anything"
```

---

### Task 14: Smoke checks for the half CI cannot reach

**Files:**
- Modify: `docs/smoke-checklist.md`

CI is `ubuntu-latest`, and `tests/test_preview_win32.py` skips wholesale off
Windows. Everything below is a hand pass.

- [ ] **Step 1: Add the checks**

Add an "EVE preview alerts" section:

1. With alerts off, no `wingman-alerts` thread exists (Task Manager or
   `threading.enumerate()` in a debug console).
2. Turn alerts on with no Gamelogs folder set: the card says so, and names the
   folder setting.
3. Set the folder: the card reports the characters it is watching, with the
   thread's liveness beside the count.
4. Change the Gamelogs folder while running: the count re-derives from the new
   folder without a restart.
5. Press Test on each event: the ring pulses on that character's preview, the
   sound plays, and the ring stops on its own — a test alert is never
   persistent.
6. Take fire from a player: the ring pulses red and keeps pulsing while you are
   in a browser.
7. Click the pulsing preview: the ring clears **even if the client does not come
   to the front**. This is the case `window.py:102-116` says will be the top
   field complaint.
8. Run a Sleeper site: no combat alerts fire. Turn the filter off: they do.
9. Alt-tab between two clients repeatedly: the ring follows the foreground and
   the switch does not feel slower than before.
10. Alt-tab to a browser: no preview has a ring.
11. Drag an alerting preview: no stutter, and the ring keeps pulsing.
12. Resize a preview past 640x480 while alerting: the pulse becomes a blink and
    nothing leaks.
13. Quit an EVE client mid-alert: no crash, and the alert timer stops.
14. Confirm in the **frozen build** that sounds play — this is the only place
    the packaging entry can be verified.
15. On a 150%/200% monitor, confirm the 2 px ring and the 6 px alert ring are
    both visible.

- [ ] **Step 2: Commit**

```bash
git add docs/smoke-checklist.md
git commit -m "docs: smoke checks for the alert paths CI cannot reach"
```

---

## Verification before claiming completion

1. `python -m pytest -q` — full suite green.
2. `python -m ruff check .` and `python -m ruff format --check .` — clean.
3. The smoke checklist above, on Windows, with at least two EVE clients.
4. The fixture corpus is committed and Task 3's assertions are real, not skipped.
5. `eve-preview-alerts-design.md` records Task 1's probe findings and Task 9's
   deviation.
6. No `tmp/` probe file is committed.
