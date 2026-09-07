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
| Preview configuration options (#87, #88) | `preview-config-design.md`, `preview-config-plan.md` |
| Preview sizing, ring colour, EVE-O gestures (#127) | `preview-sizing-plan.md` (the design stays in `docs/`; `ui/api.py` cites it) |
| Preview switch performance (#121, #141) | `preview-switch-performance-design.md` |
| Preview direct activation | `preview-direct-activation-design.md` |
| Named preview cycle groups (#145) | `preview-cycle-groups-design.md`, `preview-cycle-groups-plan.md` |
| Previews character table | `previews-character-table-design.md`, `previews-character-table-plan.md` |
| Preview placement continuity and geometry copy | `preview-layout-continuity-copy-plan.md` |
| Preview smoke walk | `preview-smoke-walk-findings.md` |
| Profiles identity and backups (#128, #129) | `profiles-identity-backups-design.md` |
| Profile character validity | `profile-character-validity-design.md`, `profile-character-validity-plan.md` |
| Probe formation sharing (#173) | `probe-formation-sharing-plan.md`, `probe-formation-sharing-verification.md` (the umbrella `settings-sharing-design.md` stays in `docs/`; its later phases are open) |
| Uploader quick actions (#139) | `uploader-quick-actions-design.md` |
| UI critique rounds and work lanes | `ui-critique-6.md`, `ui-work-lanes.md`, `ui-work-lanes-2.md` |
| UI lane handoffs | `r1-handoffs.md`, `r4-handoffs.md`, `s1-handoffs.md`, `s3-handoffs.md` (`r2-handoffs.md` stays in `docs/`; `style.css` cites it by path) |

Live documentation stays in `docs/`: the smoke checklist, the UI walkthrough
and critique, branch protection, the bookmarks reference, the preview roadmap,
and any design whose later phases are still open or that code, tests or the
manual harness cite by path. The second wholesale move (September 2026) used
exactly that test: a record moved only if nothing outside `docs/` named it, or
if every citing line could be repointed in place without shifting a line
number. Relative links *inside* a moved record that pointed at a document that
stayed (two of them) were left dangling on purpose, per the rule above.

One record is still read as a roadmap: `eve-preview-design.md` carries a
"Deferred, in rough priority order" list, and previews are the one effort here
that is not finished. Six of its statements have since gone stale — two of the
features it lists as shipped were removed again in #31, and one it lists as
deferred shipped in #65. **`docs/preview-roadmap.md` is the live list**; the
record stays as written, per the rule above.
