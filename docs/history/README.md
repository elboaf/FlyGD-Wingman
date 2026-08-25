# docs/history

Design documents and implementation plans for work that has already shipped.
They lived in the repo root until they outnumbered the four documents that
actually orient a reader (`README.md`, `CLAUDE.md`, `PRODUCT.md`,
`DESIGN.md`), so they were moved here wholesale.

**These are records, not instructions.** They describe what was decided at the
time and why, including options that were rejected and constraints that have
since changed. Where one of them disagrees with `PRODUCT.md`, `DESIGN.md`, or
the code, the code wins — do not "fix" a document here to match. Comments and
tests cite them by path and line (e.g. `webview-replatform-design.md:545`), so
editing one silently invalidates a citation somewhere else.

Paired `-design` / `-plan` files belong to the same effort: the design states
the decisions, the plan is the ordered task list that implemented them.

| Effort | Documents |
| --- | --- |
| WebView2 replatform (Tk → pywebview) | `webview-replatform-design.md`, `webview-replatform-plan.md` |
| Window resize / Win32 split | `window-resize-plan.md` |
| UI refresh | `ui-refresh-design.md`, `ui-refresh-plan.md` |
| UI layout | `ui-layout-design.md`, `ui-layout-plan.md`, `ui-layout-observations.md` |
| EVE bookmarks keybinds | `eve-bookmarks-design.md`, `eve-bookmarks-plan.md`, `eve-bookmarks-fidelity-plan.md` |
| Client previews | `eve-preview-design.md`, `eve-preview-plan.md` |
| Preview hotkeys | `eve-preview-hotkeys-design.md`, `eve-preview-hotkeys-plan.md` |
| Preview alerts | `eve-preview-alerts-design.md`, `eve-preview-alerts-plan.md` |
| EVE settings copier | `eve-settings-design.md`, `eve-settings-plan.md` |
| Skill plans (TriffSkills port) | `triffskills-design.md`, `triffskills-plan.md` |
| CI hardening | `ci-hardening-design.md`, `ci-hardening-plan.md` |

Live documentation — the smoke checklist, UI walkthroughs, work lanes, branch
protection — stays in `docs/`.

One record is still read as a roadmap: `eve-preview-design.md` carries a
"Deferred, in rough priority order" list, and previews are the one effort here
that is not finished. Six of its statements have since gone stale — two of the
features it lists as shipped were removed again in #31, and one it lists as
deferred shipped in #65. **`docs/preview-roadmap.md` is the live list**; the
record stays as written, per the rule above.
