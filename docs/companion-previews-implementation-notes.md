# Companion previews — implementation

## Current direction

Implement the actual user-facing feature now: Settings > Previews, explicitly
selected auxiliary windows, whole-window and selected-region modes, persisted
definitions, independent family toggles, movement/resizing/activation, reselection
and removal. Default off, at most eight enabled companions. No build-time flag,
Phase 0 blocker, capacity qualification matrix or staged-release program.

The user redirected work away from the standalone Phase 1 manual check to this
feature. This worktree stacks on the reviewed/rebased runtime at `df28297e` rather
than blocking implementation on a separate merge. It does not authorize a merge
or release. The earlier native prototype worked; that is not a claim that this
production implementation has been manually exercised.

## Discovery constraints

- `preview/runtime.py`: one runtime owns host startup/shutdown; independent EVE
  and companion demand and selection leases already exist.
- `preview/host.py`: Phase 1 acknowledges companion activity without native
  resources. Feature integration must replace those acknowledgments with actual
  family ownership/cleanup, not introduce another owner.
- `preview/croppicker.py`: character crop policy must remain an adapter over any
  extracted generic picker. Source dimensions and identity remain authoritative.
- `settings.update()` rolls back failed writes. Native candidates stay hidden
  until complete definitions persist; old committed views survive reselection.
- `PRODUCT.md` forbids source geometry/input automation. Sources and owned
  destination/picker handles must be distinct in tests.
- `DESIGN.md` requires hydrated field commits, literal bridge handlers, page-owned
  dialogs and preserved drafts. Native callbacks cannot evaluate JavaScript.
- Packaging already includes `wingman.preview`; new modules remain within it.
  New page scripts still require index loading and executable/lexical guards.

Remaining implementation risks are cross-boundary ordering, source identity
reverification, shared picker admission and incomplete native cleanup. These
follow the approved contracts; no unresolved product decision blocks work.

UI preflight: context=pass, product=pass, command_reference=product,
shape=approved user brief, image_gate=skipped (existing utility controls, no image
assets), mutation=open. Repository tokens, typography, wrappers and em-dash house
style take precedence over generic design advice.

## Work checklist

- [ ] Validated immutable definitions, source descriptors and normalized regions.
- [ ] Safe source catalog, owned companion windows and generic region picker.
- [ ] Transaction controller, shared runtime integration and bridge facades.
- [ ] Companion card and focused JavaScript response-ordering tests.
- [ ] Integrated tests, polish/fixes and fresh normal repository gates.
- [ ] Rendered page check and practical Windows companion smoke, recorded honestly.
- [ ] Final diff explanation and reviewable PR; no automatic merge or release.

## Verification environment

Linux uses `/tmp/wingman-companions-venv` with locked dev dependencies and the
release settings codec built/installed in this worktree. Windows uses
`%TEMP%\wingman-companions-dev\venv`; its codec is copied from the runtime checkout
with unchanged Rust sources. Node 26.5.0 is available. Tests use isolated state;
no live source windows are manipulated during automated verification.
