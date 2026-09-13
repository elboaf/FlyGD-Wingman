# Hide the active EVE client's previews — design for #212

**Status:** design approved in chat; independent second opinion SHIP with no
findings. Implementation and worker Linux/native-double/browser gates are complete,
including the authorized fresh full suite after correcting its defaults consumer.
Coordinator review/polish/final verification remain separate. Windows /
WebView2 / live-EVE acceptance has not been performed. See
[implementation notes](preview-hide-active-implementation-notes.md).

**Repository baseline:** `d6fbd776a36481dc2d02db6204d4f2973a471592` (`main`), after
shared preview-runtime work and merged backward cycling (#228).
**Workspace:** `.worktrees/preview-hide-active`, branch `feature/preview-hide-active`.
**Issue:** https://github.com/elboaf/FlyGD-Wingman/issues/212

## 1. Intended outcome and approved behavior

A default-off preference hides the primary thumbnail, its label, and the owned
cropped preview of the EVE client currently holding foreground focus. Inactive
clients remain visible **if their existing settings/lifecycle allow it**. This is
presentation suppression, not exclusion, disablement or removal of a client.

- Match the current discovered client's exact source HWND against the resolved
  foreground HWND. Use actual observed foreground, not the sticky selection ring,
  remembered cycle cursor or a pending activation target.
- A matching anonymous character-select client hides its own primary thumbnail
  too. Its HWND fallback key is not permission to hide unrelated characters.
  Named crops retire normally when their character session disappears.
- Crops remain independently configurable when their primary is excluded. If
  that owner is foreground, its crop still hides; no primary is recreated.
- Switching A → B restores A's otherwise-eligible windows and hides B's.
- Foreground on Wingman or an unrelated application suppresses no client under
  this new rule. If foreground remains zero/unknown after the existing fallback,
  it likewise supplies no active-client match.
- Existing hide-on-lost-focus may independently hide **all** EVE previews/crops
  for unrelated/unknown foreground. Wingman's process exemption remains intact.
- Turning the new preference off restores windows except where another rule still
  suppresses them. EVE Off/shutdown and crop candidate authority always dominate.
- Companions remain independent. Temporary hiding must not change cycle members,
  alert ownership, Wanderer primary-session eligibility or crop capacity/status.
- No EVE window is moved, resized, hidden or otherwise changed by this option.
  Existing explicitly authorized activation/minimize behavior remains unchanged.

### Composition table

Assume the new option is on, sources still exist and ordinary eligibility holds:

| Resolved foreground | Hide-on-lost-focus off | Hide-on-lost-focus on |
|---|---|---|
| Named EVE client A | Only A's primary/label/crop hidden | Same |
| Anonymous EVE character-select window | Only that anonymous primary hidden | Same |
| Excluded EVE client A | No A primary to show; its independent crop hidden | Same |
| Wingman window/dialog/tray | All otherwise-eligible EVE previews shown | Same |
| Other process, or unresolved zero/unknown | All otherwise-eligible EVE previews shown | All hidden by the existing rule |

No rule restores an excluded primary, an unavailable session, an uncommitted
candidate or an owner whose runtime admission has closed.

## 2. Evidence and existing boundaries

Line references below describe the baseline, not future line positions.

- `wingman/preview/host.py:2808–2906`: `_apply_selection` separates actual focus
  from sticky selection and invokes `_apply_visibility`. The current visibility
  loop and `_previews_hidden` shortcut assume one global answer for every window.
- `wingman/preview/visibility.py:16–48`: `should_hide` is the existing pure global
  lost-focus predicate; Wingman ownership and zero foreground behavior are explicit.
- `wingman/preview/host.py:2363–2393,1453`: foreground hooks feed existing shared
  discovery/selection work. Do not introduce another timer or use the legacy
  `_sweep` testing seam as the production delivery owner.
- `wingman/preview/host.py:2617–2679,2908–2916`: current clients include anonymous
  and excluded sources. Primary inclusion and the named Settings roster differ.
- `tests/test_preview_cropcontroller.py:1482–1507`: an excluded primary does not
  exclude its crop. A primary-window lookup alone cannot determine crop hiding.
- `wingman/preview/cropcontroller.py:221,680–682,743–780`: ordinary crop creation
  and candidate promotion currently consume global `_hidden`; candidates remain
  hidden until committed/authorized and stopping prevents later reveal.
- `wingman/preview/window.py:453` currently shows a new primary before the final
  host visibility pass. An eventual hidden flag does not prove hidden-at-birth.
- `wingman/settings.py:1180–1194` and `wingman/__main__.py:397,474–479`: persistence
  publishes the committed Preview reader only after successful save. Native
  visibility decisions must not read a tentative settings transaction.
- `wingman/preview/host.py:813–899,2304–2331,4293–4300`: EVE authority, stale
  restyle epochs and retained-window stop handling are separate from pump liveness.
- `wingman/web/settings.js:938–984` is an ordered checkbox reference;
  `wingman/ui/api.py:5387–5393` is a commit-gated effect reference. The nearby
  lost-focus field has older behavior and must not be copied indiscriminately.

## 3. Architecture and visibility ownership

Keep foreground resolution and application on the existing preview pump. Extend
`visibility.py` with a pure per-source composition: existing global hide **OR**
active hiding enabled with a nonzero, matching current source HWND. Exact helper
names are internal; do not duplicate the global lost-focus truth table.

### Primaries and labels

The host computes and applies an answer per primary, using its source HWND. A → B
must update both windows even when the global lost-focus result stays false. The
old global-only early return cannot skip active hiding or its transition back to
Off. Retain cheap idempotent `set_hidden` operations and avoid probing foreground
PID ownership when hide-on-lost-focus is disabled.

Add a defaulted hidden-at-birth capability to the existing primary factory/window
path. Host-owned creation must not issue an initial show for a known-suppressed
primary or label. Prefer hidden native preparation followed by a current-policy
show decision at host publication, rather than show-then-hide. The default-off
fast path must still reveal newly prepared eligible windows. Keep geometry,
thumbnail registration and label ownership in their existing objects.

Restyle, alert/label paint and metadata updates must respect the hidden state;
they must not become alternate routes that show an active client's preview.

### Crops, including asynchronous creation/promotion

Extend the host-to-crop visibility handoff to support a **current per-source**
decision, not only the global `_hidden` boolean. The proposed mechanism is an
injected pump-local decision supplier using the host's existing foreground and
committed settings readers. Preserve existing behavior when the supplier is absent
in standalone constructions. It performs no disk, network, UI bridge or worker wait.

Use it for existing live crops, ordinary creation and committed candidate
promotion. Reevaluate at reveal-capable boundaries after native preparation; a
mask cached when the request began must not reveal a newly active source when
saving finishes. The supplier's presentation answer does not authorize a session
or transaction. Existing session/generation/epoch checks remain necessary, and
stopping always forces hidden. A saved crop can correctly be live but hidden:
do not cancel its successful persistence, free its capacity or report it offline.

Foreground and configuration updates still arrive through existing pump/host
work. Ensure the context is current before reveal-capable paths, not only after
roster reconciliation. An equivalent small existing handoff may be preferable
if inspection demonstrates the same freshness and authority guarantees; do not
introduce a second lifecycle owner or a general visibility framework.

### Lifecycle invariants

- Hidden windows remain tracked; never emulate hiding through exclusion or close.
- Failed/pending activation cannot hide the intended target before observed focus.
- Logout, named-to-anonymous transitions and source replacement use current
  session identity, not a stale name/HWND association retained by this feature.
- EVE Off/on may share a surviving pump with companions or a selection lease.
  A preference change, stale callback or completion cannot reopen EVE admission.
- Preserve admitted operation draining, final saves and retained timed-out owners.

## 4. Settings and UI contract

Add `preview.hide_active_preview = false` to defaults and boolean normalization.
Missing, malformed or non-boolean persisted values normalize to the off default.
No settings-version bump or migration is needed. Older binaries may discard the
unknown field; this design does not promise downgrade retention.

Add `Api.set_preview_hide_active_preview(enabled)` with strict boolean validation
and the standard `{applied, persisted, error}` receipt. Use `_write_preview_setting`
and the committed reader; request restyle only after an accepted persistent write.
No new runtime start/stop, whole-document push or page handler is needed. Include
`preview_hide_active_preview` in ordinary settings hydration. A missing host is
not a reason to refuse saving a future preference.

Place one `.check` control in **Settings → Previews → Windows → When you switch
away**, beside the existing focus-hiding option without separating minimize from
its exceptions:

- Label: **Hide the active EVE client's previews**
- Hint: **Hides its thumbnail and cropped preview while that EVE client is active.**

Use existing tokens, spacing and field-local feedback. No new card, route, theme,
roster column or disclosure rename. The checkbox remains editable with Previews
Off, but cannot commit before initial hydration. Serialize rapid writes, preserve
newer queued choices, and restore the last acknowledged value after refusal.
Do not retrofit unrelated Settings fields as part of this feature.

## 5. Verification strategy — planned, not yet performed

1. **Pure policy:** both toggles, A/B, Wingman/other/zero/unknown foreground,
   anonymous/excluded sources and option-Off restoration.
2. **Native seams/host:** use production selection/restyle delivery; test changing
   active identity with unchanged global hide, source disappearance/replacement,
   failed/pending activation, hidden members remaining cycleable, and hidden labels
   surviving metadata/alert/restyle. Assert initial native show calls, not only a
   final `hidden` property, for primary/label creation.
3. **Production crops:** hidden creation and committed promotion, source focus
   changing while persistence waits, excluded-primary owners, unchanged live/cap
   accounting, logout and session replacement, stale completion/stop dominance.
4. **Persistence/bridge:** defaults, malformed inputs, round-trip, blocked save,
   rollback/no dependent effect, no-host and Off configuration, committed reads.
5. **UI:** initial hydration, rapid toggles, accepted/refused/null replies, section
   and subpage return, real module registration and field-local feedback. Render
   the Windows panel at840×625 and839×621; do not claim unrelated roster fixes.
6. **Final gates:** focused tests, full pytest with Node and THIS checkout's built
   release codec, Ruff lint/format, all-page Node smoke and independent Cargo.
   All pytest data goes under case-sensitive Linux `/tmp`, bytecode/cache disabled;
   use a dedicated environment, never a sibling's. Inspect skips and retain failures.

Existing relevant tests include `test_preview_visibility.py`, `test_preview_host.py`,
`test_preview_window.py`, **production** `test_preview_cropcontroller.py` and
`test_preview_cropwindow.py`, `test_settings_preview.py`,
`test_settings_committed_preview.py`, `test_preview_wiring.py`,
`test_preview_runtime*.py`, `test_settings_runtime.py`/`scripts/test_settings_runtime.js`,
`test_settings_page.py`, `test_page_conventions.py` and `test_bridge_contract.py`.
The similarly named crop prototype harness is not production-controller coverage.

Append a real Windows smoke procedure covering A/B activation, Alt-Tab to Wingman
and other apps, character selection/logout/restart, both hide settings,
minimize-inactive, labels/crops without initial flashes or focus theft, independent
companions, Off/on and Quit. Confirm EVE source bounds are unchanged. Browser and
Linux/native-double tests do **not** satisfy that operator acceptance item; leave
it visibly unverified until actually run.

## 6. Alternatives, limits and adaptation points

Rejected: sticky-selection hiding (wrong after leaving EVE), exclusion/deletion
(changes eligibility/resources), named-only matching (reveals anonymous active
thumbnails), and primary-dependent crop masking (breaks independent crops).
A new polling timer, runtime owner, or cached request-time visibility mask is not
needed and would add stale-state/lifecycle risks.

This is not an implementation plan or a claim that the injected supplier already
exists. If the existing reveal boundaries cannot evaluate current policy without
blocking or weakening authority, revisit this mechanism before implementation.
Likewise, stop if avoiding initial shows requires moving/resizing an EVE source.

Out of scope: companion hiding, per-character preferences, layout profiles,
external controls, changing alert/cycle semantics, broad Settings cleanup, the
pre-existing deferred-crop caret/focus limitation recorded during #211, and unrelated
Previews grid work. Preserve current behavior with the preference Off.

Implementation, polish and actual CodeRabbit remain later gates. This document's
second opinion comes first; findings are presented to the user before incorporation.
