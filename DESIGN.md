# DESIGN.md

How the Wingman window is built, and why. Written after a review found the
same conventions broken in four places, in a codebase that documented every
one of them — in comments, inside the modules that already got them right.

This file is the reference a new screen is checked against.
`tests/test_page_conventions.py` enforces the mechanical half; everything
here that a regex cannot see is the reason this file exists as well.

The stack is plain HTML, CSS and ES5-flavoured JavaScript in a WebView2
window (pywebview), Windows only, dark only. No framework, no build step,
no bundler. Nothing in the test suite executes any of it.


## The one rule that explains most of the others

**Nothing renders this page except a real Windows machine.** There is no
JS test harness, no snapshot, no headless run. `pytest` proves the Python
side and reads the page's *source*; it never sees the result.

The failure mode that follows is specific and quiet. Handlers register at
the top of each module's IIFE, so one bad name throws mid-module and every
registration below it never runs. The screen loads as an inert copy of
itself — no data, no working buttons, and no error anywhere a user or a
test would look. `ui/api.py`'s `_push` renders as
`window.<handler> && window.<handler>(...)`, so the push is a no-op rather
than an error.

So: a broken screen looks like an empty screen. Assume any new screen is
broken until it has been opened by hand, and treat `docs/smoke-checklist.md`
as part of the change rather than as paperwork after it.


## Destinations vs. configuration

The title bar holds **destinations** — places you go to accomplish
something and stay. Settings holds **configuration** — screens you visit
twice ever, to switch a feature on and set it up.

The test is not how important a feature is. It is whether the screen
produces anything of its own. Bookmarks and Previews were top-level tabs
for four releases; neither shows anything on its own screen, because both
configure things that happen elsewhere — global keybinds that fire in EVE,
floating windows that appear on the desktop. They are Settings sections.

This matters because title-bar space is the scarcest thing in the app.

    unshrinkable content = nav + 3 window buttons + gaps + padding + 105px

That 105px is the drag region's floor: it is the only flexible child of
`.titlebar`, and with no `min-width` its automatic minimum resolves to the
wordmark's own width. Nothing else in the bar can compress at all — the nav
and the window buttons are both `flex: none`.

`MIN_WIDTH` is **840 logical pixels**, and the CSS viewport floor is
**840x625 at every display scaling**. `MIN_WIDTH` / `MIN_HEIGHT`
(`ui/window.py`) land in WinForms `MinimumSize` and `ptMinTrackSize`, both
of which Windows DPI-scales for a system-DPI-aware process, so the number
is already in the same units the page sees.

Measured, not derived: the floor capture is 1678x1242 physical on a
3840x2160 display at 200%, which is **839x621 CSS** against `MIN_WIDTH`
840 and `MIN_HEIGHT` 625. Were the floor 840 *physical*, that capture
would be ~840px across; it is twice that. The maintainer's standing
observation that the app cannot be resized to the CSS floors is this fact,
observed before it was explained.

> **This corrects a bold claim that stood here through four releases.**
> This file previously said `MIN_WIDTH` is "**840 physical pixels**, not
> logical … the CSS viewport floor is `840 / scale`: 672px at 125%, 560px
> at 150%". That arithmetic is wrong, and `docs/ui-critique.md` and
> `docs/smoke-checklist.md` were both written against it. **Do not size
> anything against a 560px or 672px viewport. Neither can occur.**

**Unresolved — the observation that produced the rule above.** This file
also reported that "five destinations needed 686px and clipped the close
button off the right edge at 125%". Both statements cannot be true as
written: at a floor of 840 CSS, 686px of unshrinkable content fits with
154px to spare and nothing should have clipped.

| | claimed | measured |
|---|---|---|
| viewport at 125% | 672px | 840px |
| unshrinkable content | 686px | unchanged |
| result | close button clipped | fits, with 154px spare |

This is **not** a claim that `#38` was wrong. Three destinations stand on
`PRODUCT.md`'s destination-vs-configuration test, which needs no pixel
argument, and something was evidently observed. What is suspect is the
recorded *reason* — and the reason is the tool the next contributor will
reach for. Reproduce the clip or establish that it cannot be reproduced
before relying on either number. Deliberately left open rather than
guessed at.

**What this means for `style.css`.** Of its eight width media queries,
seven can never fire:

| Query | Fires at the floor |
|---|---|
| `max-width: 839px` (the `.panel` 248px step) | **only at some scalings** — see below |
| `max-width: 767px`, `max-width: 607px` (the list's column-dropping steps) | no |
| `max-width: 720px` x5 (status strip, two Settings blocks, the settings row, Skills) | no |

Six are simply unreachable. The seventh is worse than unreachable, and it
is the one that decides how wide the Uploader's panel is:

**`max-width: 839px` fires at 200% scaling and not at 100%.** At 100% the
floor viewport is 840 CSS and the query does not match. At 200% the floor
measures 839 CSS — the 840 logical minimum lands a client area of 1678
physical, and 1678 / 2 is 839 — so it matches, at the floor and nowhere
else. The Uploader's panel is therefore 248px wide on one machine and
320px on another, at the same window size, with nothing in the stylesheet
that predicts which. That is a rounding artefact holding a layout
decision, not a breakpoint. **R1 owns this**; it is recorded here because
the reason is a DPI fact rather than a CSS one and would otherwise have to
be rediscovered at the stylesheet.

None of the six dead blocks is load-bearing today, and each owning lane
decides whether its block is a decision worth keeping or dead weight — a
rule the window cannot currently reach is not thereby wrong. Note that
`docs/ui-critique.md` credited one of these queries with doing the
scaling arithmetic "correctly": it is the `839px` one, and the credit was
earned against the wrong model. It is the least correct of the eight.

**Before adding a destination, do the arithmetic.** `style.css` warned at
four; four features added one each without revisiting it, the last
describing the change as "seven edits, all mechanical". If it is mechanical
you are not deciding anything, which is the problem.


## Controls

**Checkboxes and radios must use the wrapper.** Nothing in `style.css`
targets `input[type=checkbox]` or `input[type=radio]`; the dark appearance
comes entirely from `.check > input + .box` and `.radio > input + .ring` —
the input is `opacity: 0` and the styled span beside it is what you see. A
bare input is a white Win32 widget on a dark card. This applies to controls
built in JavaScript too, which is where the worst instance shipped: one per
character, forty of them.

**Field labels go through the shared column.** `.settings .row > .lab` is
118px, right-aligned, `--text-dim`, for the whole screen. A label outside
it renders brighter than every other label and at its own width. Prefer
`<label class="lab" for="...">` over a `<span>`: it keeps the control
association.

**One accent per screen, or none.** `.btn.acc` is the single brand-accent
control. Zero is fine — a screen that applies immediately has no commit
action to accent. Two is two things claiming to be primary. Its label is
near-black on the brand, not white: white measures 3.08:1 on the gradient's
top stop.

**Accent marks what is selected and what will happen. A card heading is
neither.** The rule above is written about *controls*, so the Uploader's
`UPLOAD` and `PUBLISH` heading bars never breached its letter — they were
a third and fourth claim on a signal that carries exactly two meanings.
The signal is diluted by every use that is neither. On the Uploader that
is five accent uses down to three: the checked row's checkbox and its
left-edge marker (what is selected), and the `Upload` button (what will
happen); the two `.card > h2` bars lose it. This is about `.card > h2`
generally and not about one screen — the heading-bar treatment is not
confined to the Uploader, and whichever screen owns a card heading
inherits the rule.

**Never use `window.confirm`, `window.prompt` or `window.alert`.** WebView2
renders them as browser chrome captioned with the page origin — a grey box
mentioning localhost, in a frameless dark app. Use `WM.confirm` /
`WM.prompt`, which raise the app's own overlay. Python's `_confirm` cannot
serve a page-initiated dialog: it blocks the calling thread until
`dialog_response` arrives, so calling it from a bridge method deadlocks the
thread that has to deliver the answer.

**`hidden` needs an author rule.** An author rule beats the UA
stylesheet's `[hidden] { display: none }` regardless of specificity, so any
selector that sets a display needs its own `[hidden]` override or the
element stays visible. Six rules in `style.css` carry a note about this and
one shipped without it anyway.


## Saving

Settings has no Save button. Every field commits on its own through a
per-field endpoint returning `{applied, persisted, error}`.

Three outcomes, not two, because the page says something different for
each: **refused** (revert the control, explain inline), **applied but not
persisted** (leave the control, warn it will not survive a restart),
**done**.

**A refusal reverts the control. A failed write does not.** The setting
really did take effect for the session; snapping the control back would
misreport it.

**Discrete controls commit on change. Free text does not commit on blur.**
Folders and the webhook commit on Enter, or via an explicit affordance
(Browse, Detect, Remove). This is not fussiness:

- Committing a half-typed path that happens to name a real directory
  rebinds the watcher, and `Watcher.rebind` marks every file already in
  that folder as seen — silently suppressing the announcement for every
  recording that arrived this session, then doing it again to the right
  folder on the corrective commit. Not undoable from the UI.
- An empty webhook used to mean "clear it", so select-all, Delete and look
  away destroyed a credential. There is no Cancel and no pre-edit snapshot
  anywhere on the page.

**Nothing commits before the first payload has rendered.** `get_settings`
resolves asynchronously and every field is blank until it does; a commit
fired in that window writes blanks over a configured install. There is a
test recording that this once happened.

**An endpoint whose effect reaches outside its own control must apply that
effect locally.** There is no whole-document push to ride on any more —
that push is exactly what used to rewrite the field you were still typing
in. The EVE gate learned this twice: once by persisting without repainting,
once by clearing the current route but not the route the gear returns to.
**Hiding a screen means cutting every route into it, not just the one the
user is standing on.**


## Routes and sections

`WM.route` switches destinations; `WM.section` switches groups inside
Settings. Both dispatch an event, and both provide the same **enter and
leave** contract. Leaving Settings dispatches a section change too, so a
module folded into Settings learns about both.

Route and section entry is how screens **fetch**. There is no polling and
nothing is pushed at boot; a subsystem that costs nothing until you open it
must not push state at launch.

Leaving is load-bearing, not bookkeeping. `bookmarks.js` and `previews.js`
each install a document-level `keydown` listener while capturing a keybind,
and each disarms it on being left. `stopPropagation()` does not stop a
sibling listener already attached to the same node, so an armed capture
consumes the next keystroke typed anywhere and persists it into the wrong
bind, off-screen. The capture handler `preventDefault()`s every key
including Tab — an escaped capture inside Settings would swallow a folder
path or a webhook mid-type.


## Words

One name per concept, across every screen.

A key combination is a **keybind**. It was a keybind, a hotkey and a chord
on two adjacent screens that build the same widget. Identifiers may keep
older spellings where they cross the Python bridge — consistency with the
API outranks consistency with the label — but user-visible text may not.

A screen may not repeat its own tab name as its first card heading.

Say what a control does, not what it configures. A tab named "EVE
Settings" beside a gear named "Settings" describes the implementation and
confuses the reader; "Profiles" is what the thing is called.


## State that must not be retyped

Four places carried a count of the bookmark keybinds. `bookmarks.py`
defines eighteen; a confirmation said twenty-one, two comments said
nineteen, and the smoke checklist said twenty-one. The user-visible one
guarded the only irreversible action on that screen.

`tests/fakes.py` hand-listed the settings keys, so every new setting was
absent from the fake until someone remembered.

Derive it, or assert it in a test. A number that has to be kept in step by
hand will drift, and the copy that drifts is usually the one a user reads.


## Colour and type

Tokens live in `:root` and are the only place a colour is decided. Reducing
a token fixes every rule that uses it: `--text-faint` was below AA against
every surface it appeared on, and one edit fixed twenty-two rules.

Contrast floors: **4.5:1** for text (everything here is under 18px, so
nothing qualifies as large), **3:1** for a focus ring or a state border.

`color-scheme: dark` is declared, or WebView2 resolves UA-drawn chrome for
a light scheme against a near-black page.

Every interactive element needs a visible `:focus-visible`. One rule covers
them all. `:focus-visible` and not `:focus`, so a mouse click does not
leave a ring behind.

Column headers sit *below* body size deliberately: they label the data and
are not the data. Do not "fix" this.

**A header row is laid out by the same padding as the rows beneath it,
with no separate inset.** Two screens broke this in opposite directions —
the Uploader's headers sit ~16px right of their data, and on Skills
`PLANS` sits ~22px left of its column while `READY` sits ~14px right of
its own. The Skills instance has no scrollbar, which rules out a
scrollbar gutter as the explanation for the Uploader's. A header that
does not share its column's inset is not labelling that column. This
licenses no change to header *size* — see the paragraph above.

**The one blue is a declared exemption.** `--link` is the single colour in
the app outside the palette, and it stays that way on purpose: an outbound
link keeps link-blue *because* it leaves the app, and a link recoloured
into the palette stops reading as a link. It is a token like any other —
7.4:1 on `--panel`, 7.7:1 on `--bg` — so "tokens are the only place a
colour is decided" holds. Do not unify it into the brand.

Both infinite animations are stopped under `prefers-reduced-motion`. An
indeterminate bar still has to say "working" without claiming a percentage.


## What this file cannot tell you

Whether a screen is worth adding. Whether a control belongs where you put
it. Whether the words are right. Whether the thing is any good.

The conventions here are floors, not a design. Clearing them is what stops
a screen being obviously wrong; it is not what makes it right.
