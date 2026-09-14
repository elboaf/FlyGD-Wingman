# UX review follow-through — verification

## Scope and status

Implemented on `ux/review-followthrough`, based on
`7c871f424f19721dffffe9f1208b97b6f8f80a1c` (Hide previews for the active EVE
client (#231)). The `20260914T004958Z` Windows screenshot set from the main
checkout is baseline evidence, not acceptance of this changed UI.

The six approved passes were run in order: Clarify, Layout, Harden, Distill,
Audit, then Polish. Verification used local, uncommitted changes. The subsequent
user-driven `20260914T024454Z` set received complete Windows/WebView2 visual review:
61/61 screenshots inspected, no blank/partially initialized surface or new
blocking visual regression established. The three original priority refinements
are visibly present. This does not certify interaction or successful operations.

The user accepted the existing reveal-on-focus/Edit contract for Preview
conflicts; partial warning context during passive scrolling does not require
more sticky UI or auto-scroll. No further UI fixes are scheduled. Remaining
Windows interaction/accessibility, codec-equipped Profiles, native-operation,
persistence and DPI acceptance is explicitly deferred to release checks in
`docs/smoke-checklist.md`, not waived or marked passed.

During this work the primary checkout advanced independently to `76afd3dc`
(`test: share text-preserving page parser (#232)`). This worktree stayed on the
reviewed base; integration/rebase against that newer main was not performed.
No app/shooter CLI, native preview/picker/bar, real copy/save/connection Test,
or user-settings reset was run during implementation. Browser checks used
only local `index.html?dev=1`, synthetic fixtures and blocked HTTP(S).

## Changes and decisions

- Fittings states the additive-copy guarantee directly after the preflight
  summary, including ready and conflict cases. Resolution instructions keep
  their own accessible association. Uncertain-result guidance starts with
  verification before retry and precedes rate-limit guidance.
- Shared recovery occupies one sticky group **inside** the existing 55vh
  results body. It does not enlarge the dialog's surrounding height budget,
  repeat warnings per row, introduce a live-region owner, or retry anything.
- Preview bind/Edit focus reveals the existing warning and control using their
  actual boxes and preceding sticky headings. Rows remain `display: contents`;
  only the Characters & cycling subpage scrolls. Oversized warnings retain a
  reachable focused control and expose as much adjacent guidance as fits.
- Real mouse testing caught an important edge: scrolling on mouse-down focus
  could move the target before click. Focus while `:active` now defers reveal
  to click, preserving the existing capture/Edit action. Passive updates do
  not invoke reveal. Existing roster rebuilding behavior is unchanged.
- Bookmarks/crop readiness and shared recovery reuse the existing operational
  text role. Keeping `.hint` preserves `.hint.err`; existing status owners and
  inline/crop spacing remain intact. Manual management and character menus
  use neutral buttons. Scoped disclosure glyphs are more legible. Centering
  Keybind over its value control separates the narrow headings without
  narrowing the name track or changing grid columns.
- Offline geometry guidance advertises Copy only when another source exists
  and the target permits it. Minimize wording describes the next switch,
  not an immediate action. Formation edits are explicitly drafts until Save.
- The group-name label remains visible during typing and replacement renders.
  Alias filtering compares exact names with the **visible row title**, not
  an unsaved draft or independently refreshed detail. It changes no provenance,
  normalization, search or persisted data and retains a single real alternative.
- General removes repeated explanation while retaining feature independence.
  Fleet's no-verified-roster branch points to verification/boss controls below;
  it does not promise eligibility or tell users to enable local previews.
- The existing base Alerts capture resets its actual scroller and fails closed
  on wrong, missing, hidden, empty, clipped or covered master/readiness anchors.
  `SCREENS` keys/count are unchanged. Fittings capture verifiers were updated
  alongside the changed alias/reassurance/recovery presentation; they still
  reject wrong content, missing advice, reversed recovery and clipped content.

## Automated verification

Commands ran from the worktree. Python commands used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-ux-followthrough-venv` with the locked dev
extra. Node was available. The Linux release codec was built from this source
and installed at this worktree's `packaging/bin/wingman-settings-codec` before
the full suite; `codec_available()` was asserted true.

| Check | Result |
|---|---|
| Focused pre-change baseline | 592 passed |
| `uv run --no-sync python -m pytest tests/ -q -rs --durations=10 --junitxml=/tmp/wingman-ux-followthrough-pytest.xml` | **12,536 passed, 13 skipped**, 417.19s |
| Final focused pytest after review's test-only correction: `tests/test_preview_warning_grouping.py tests/test_shoot_screens.py tests/test_new_screenshots.py tests/test_ui_contrast.py -q -rs` | **331 passed**, no skips |
| `node --test --test-reporter=dot scripts/test_fittings_runtime.js` | **84 passed** |
| `node scripts/js_smoke.js` | Every module on all three pages loaded |
| `uv run --no-sync ruff check .` | Passed |
| `uv run --no-sync ruff format --check .` | Passed, 438 files formatted |
| `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-ux-codec-target` | **1 passed**, no failures/ignored tests |
| `git diff --check` | Passed |

All 13 full-suite skips are Windows-only: five junction cases, DPAPI/WinDLL,
message pump/window station, three user32/gdi32/dwmapi cases, Windows tray,
and Wanderer user-bound DPAPI. **No Node or native-codec coverage skipped.**
The full-suite run preceded one final correction to a test assertion only;
production code was unchanged, and the 331-test focused gate was rerun afterward.

Meaningful changed branches were exercised red before green: alias filtering,
visible group labels after repaint, conditional offline Copy, preflight
reassurance, shared result ordering/cleanup, direct conflict reveal, pointer
capture, oversized-warning positioning, and Alerts framing/failure propagation.
Broader shooter tests caught stale assumptions about aliases and recovery's old
parent/text; those were reconciled rather than removed or weakened.

## Browser and visual evidence — not Windows acceptance

Headless Chromium ran at 839×621, 840×625 and 1040×680 with local synthetic data,
no Python backend, blocked HTTP(S) and zero page errors:

- 42 Preview interaction cases and three lower-Fittings-result/focus-trap cases.
  At 840×625, recovery used 121px of the 343.75px body; the final result and Close
  remained reachable. Tab wrapped through the body/Close and Escape closed.
- Native browser Tab, actual mouse capture/Edit clicks, larger sticky headings,
  oversized warnings, bottom clamping, hidden/inactive/unrelated/passive states,
  menu keyboard focus, offline/excluded Copy and formation footer bounds.
- Header-ink separation changed from 3px to approximately 55px at the floor;
  the existing shared tracks and horizontal overflow checks remained intact.
- Production Alerts setup executed against actual rendered local DOM from an
  inherited `scrollTop=420`, restored zero, and passed its master/health checks.
- Fourteen targeted 840×625 fixture PNGs received isolated visual coverage,
  in batches of four, four, four and two. No worker received more than four
  images; the largest batch was 512,993 source bytes. No original Windows PNG
  suite was reattached. Two follow-up frames explicitly confirmed the new Fleet
  no-roster pointer and lower preflight Alternate name/Skip controls.

Measured token contrasts: operational text/panel 7.0463:1, neutral-button
text/control 10.3532:1, error/panel 5.3982:1 and focus ring/panel 8.3440:1.
The scoped technical audit scored 19/20, with accessibility provisional; this
is not a new Nielsen score or a WCAG/Windows certification.

The current deterministic detector (`npx impeccable --json <worktree>/wingman/web`)
returned 29 records (24 warnings, five advisories): disabled-state contrast,
font/progress heuristics, existing density/elevation patterns and an unchanged
page-wash match. No new actionable scoped defect was established. The raw
count is not a count of UI failures. No browser overlays or native app were
launched to satisfy the detector.

Local evidence lives under `/tmp/wingman-ux-followthrough-visual/`, the
`/tmp/wingman-ux-pass*.md` reports, `/tmp/wingman-ux-polish-*.md`, and
`/tmp/wingman-ux-followthrough-{pytest,cargo}.log`. These are review artifacts,
not dependencies or committed screenshot assets.

## Polish and independent review

`polish-core --fix` was applied to the uncommitted working-tree changes against
the named base, not an empty `BASE..HEAD` range. Existing ES5 conventions
superseded generic modern-JavaScript suggestions. Formatter edits were inspected;
the old CSS scroller comment was corrected without deleting its rationale.

Independent general, silent-failure and comment passes found no concrete new
production defect. The silent-failure pass found one misleading new test claim:
its passive repaint assertion could retain a detached `activeElement` in the
DOM double. Focus preservation is now asserted only for visible direct
interactions and includes attachment; passive checks remain no-scroll/no-bridge.
No unrelated production focus refactor was made. Final focused checks passed
after this correction. The visual polish batches found no blocking regression;
normal viewport continuation was kept distinct from inaccessible content.

## Remaining Windows evidence

Windows Python 3.12 reported `paths.codec_exe() is None` and
`codec_available() == False` in this source worktree. The usual per-user Windows
Cargo executable is absent. No system toolchain was installed and no capability
flag was overridden. This is a source-environment prerequisite gap, not an
installer defect; Linux codec coverage does not fill it.

The Windows CDP venv was prepared and imports `websocket-client`. Windows Git
resolves the intended linked worktree through its relative `.git` link. The
`20260914T024454Z` manifest matches this branch/base with dirty=true, all expected
stages present and no failures/skips. Image40 still shows the missing-codec
fallback; normal selective-copy presentation remains a deferred release check.
The capture used the real app with existing configuration, not persistence
isolation. No real operation should be performed merely to populate a capture.

The full visual critique, filename-keyed coverage and independent detector
assessment are recorded under `/tmp/wingman-windows-review-20260914T024454Z/`.
The follow-up user decisions close the passive-warning requirement question
and defer remaining native acceptance; they do not create new passing evidence.
