# Fittings clipboard — implementation notes

Documentation checkpoint: implementation through `72050584`, based on `286596be`.
Tasks 2–4 have focused verification, scoped review and a fresh Chrome rerender;
whole-change polish/review and final full-suite rerun remain pending. This is not
Windows/WebView2 or live EVE/Pyfa acceptance.

## What changed and how it works

- `wingman/evefittings/eft.py` owns immutable parsed/resolved records, bounded
  single-fit parsing, line-specific warnings and strict rendering.
  `inventory.py` resolves only inventory names/IDs through the existing public
  `EsiClient`, validates association/category/rack metadata and retains bounded
  caches. Raw EFT and custom fit names are not sent to ESI. No new dependency,
  SDE, OAuth scope or fitting-legality simulation was added.
- `controller.py` remains the single library writer. The four thin `ui/api.py`
  facades are `fittings_review_eft`, `fittings_import_eft`,
  `fittings_export_eft` and `fittings_locate_entry`. One nonblocking clipboard
  gate serializes resolver use on borrowed bridge-call threads, not a new worker.
- Review runs parse → verified inventory snapshot → normalized candidate, then
  retains one immutable, opaque-ID ticket with items, names and warnings for
  15 monotonic minutes. Add accepts only that ID, never browser-supplied rows.
  It rechecks current content using the existing version-aware digest plus full
  canonical equality, then creates a local entry or retains an alias/no-op.
  `model.py` shares local construction, canonicalization and bounded alias logic
  without fabricating remote fitting IDs. Curation and existing exact templates
  survive duplicate imports; new descriptions are empty.
- Changed entries use the existing `_publish_locked`: save before replacing
  in-memory state, under the existing state lock. No schema, fingerprint,
  presence, snapshot, intent or remote character-copy semantics changed.
  Import works without an authorized character and never writes to ESI fittings.
- `names.py::merge_verified` hands the ticket's retained names to the cosmetic
  cache before notification/success, including duplicate/no-op and cold/full/
  stale-cache cases. Resolver eviction cannot remove these names; cosmetic file
  save failure is logged without undoing the committed library or in-memory labels.
- Export snapshots a saved entry, verifies inventory and renders outside the
  state lock, then refuses if the source changed or lifecycle admission closed.
  It uses the saved preferred name, not an unsaved metadata draft. The codec
  parses/resolves its own output against the same snapshot and compares complete
  canonical content, not only a hash, before returning actionable text.
- `locate_entry` computes the target page and workspace from one retained library
  snapshot; authority access stays outside the state lock. **Show fitting**
  renders that returned workspace directly, then reads the target detail — it
  never makes a second workspace read that could lose a page-boundary target.

## Approved compatibility boundary

[Format contract](reference/fittings-clipboard-format.md) and
[`tests/fixtures/evefittings/eft/`](../tests/fixtures/evefittings/eft/) retain
source pins, public ESI evidence and authored expected rows. These fixtures are
**source-derived, not live EVE/Pyfa clipboard captures**; parser self-round-trips
and public metadata do not prove installed-client interoperability.

Import is conventional, not lossless recovery of simulation state. Quantity
lines for drones/fighters use their dedicated bays regardless of blank-line
sections, preserving counts and warning per affected line. Other supported cargo
quantities remain exact. Inline loaded-ammo selection is validated then omitted
only with a visible warning because it has no quantity; offline state is omitted
only with a warning while retaining the module. Unknown inline charges, malformed
input, unsupported mutations and invalid metadata refuse the whole fit rather
than silently importing a subset.

Export is stricter: stored Cargo drones/fighters, fitted charge rows and other
unrepresentable templates refuse rather than move items or lose counts. Saved
canonical hull/type/location/quantity content must survive the internal round
trip. This asymmetry was explicitly approved, not inferred from permissive Pyfa
parsing. No new persisted interpretation or migration was introduced.

## Recovery, lifecycle and frontend ownership

`wingman/web/fittings.js`, `index.html` and `style.css` add a neutral inline
import/review panel and per-detail export, retaining **Copy selected** as the
sole accent action. A fresh opener reads only with no text, review or result;
reopening an existing draft/result preserves it. **Read clipboard** is explicit
replacement, route entry is clipboard-free, and denied/missing clipboard access
leaves manual paste usable. Successful Add retains warnings and offers Show,
without automatic selection or character writes.

The first controller implementation consumed tickets too early on save failure.
The correction retains the exact immutable ticket until successful commit/no-op;
same-ID retry needs no new lookup. Expiry, replacement or shutdown can invalidate
it, and failure never resurrects it. The UI additionally offers **Review again**
after any Add refusal, without parsing backend error prose or automatically
resolving again. If a sent Add loses page ownership, the preserved draft requests
re-review with uncertain-result guidance rather than claiming it was not saved.

Import draft/request ownership is independent of ordinary list generations, so
the import notification cannot erase its own receipt. Typing, navigation and
screenshot transitions fence late reads/reviews/results. Export owns the exact
mounted source/control; row changes, metadata Save, route changes and both copy
overlay entry paths (including **Last copy results**) revoke delivery. Success
feedback follows the clipboard write promise, not the backend reply. Already
admitted OS writes cannot be undone; cancellation prevents subsequent stale
feedback/focus, not rollback. Metadata drafts, disclosure, focus/caret and local
selection remain with their existing owners; async completions do not steal focus.

The callback correction releases lifecycle/state locks before page notification.
The actual Api `_push` delivery predicate rechecks controller/page closure before
each main-window/sig-bar evaluation. Shutdown closes admission before draining
the same gate within the existing shared deadline; an already-admitted blocked
evaluation can outlive the drain but cannot hold closure locked or admit the next
page stage. No second lifetime owner or shutdown budget was added.

`wingman/web/dev.js` and detached screenshot fixtures simulate clipboard and
bridge outcomes without falling through to the real OS/bridge. Staging revokes
pending owners and keeps the real draft separate for restoration. The final
`tests/fixtures/preview_dev_capture.cjs` correction adds only `navigator: {}` to
its VM browser double; it does not weaken production dev-safety guards.

## Rulings, in ledger order

The following transcribes every current `Ruling:` line from the ignored SDD
progress ledger, including its consequence if the interpretation is wrong.

1. Ruling: Treat “great, lets continue” as authorization to execute the revised plan, not permission to ignore its Task 1 compatibility gates — public interchange/persisted-content choices still require approval if evidence forces a scope change — wrong interpretation would cost rework, not remote writes.
2. Ruling: Interpret incoming quantity drones/fighters by category regardless of visual section; warn per affected line, preserve counts — source format lacks definitive cargo/bay authority and user accepted conventional interpretation — wrong interpretation costs a reviewed import correction, never automatic character writes. Stored Cargo drones/fighters still refuse export.
3. Ruling: Fresh opener reads clipboard only when text/review/result are absent; reopening a retained draft/result preserves it and Read clipboard remains explicit replacement — follows approved one-click first import without discarding drafts — wrong interpretation costs one explicit read when resuming, not lost user edits.
4. Ruling: Permit a minimal pure canonicalize_items helper with the existing canonicalize adapter unchanged if needed — avoids manufacturing remote fitting IDs merely to compare local content — wrong choice costs a small internal refactor, not stored schema/identity changes.

## Verification evidence and open gates

Results below are supplied parent evidence or recorded task results, not reruns
by this documentation checkpoint. Counts overlap; do not sum them.

| Gate / command or coverage | Recorded result | Remaining limitation |
| --- | --- | --- |
| Task 2: `uv run --no-sync python -m pytest tests/test_evefittings_eft.py tests/test_evefittings_inventory.py tests/test_evefittings_model.py tests/test_evefittings_names.py tests/test_evefittings_contracts.py -q` | 209 passed | Injected/public-source-backed evidence, not live clients |
| Task 3 initial controller/model/store/refresh/copy/lifecycle/API/bridge gate; adjacent codec/inventory/names/wiring gate | 438 passed; 194 passed | Predates fix; superseded on changed paths below |
| Task 3 fix: `uv run --no-sync python -m pytest tests/test_evefittings_clipboard.py tests/test_evefittings_lifecycle.py tests/test_api_fittings.py tests/test_bridge_contract.py -q` | 255 passed; targeted 7 RED → GREEN | Injected blocking window, not WebView2 |
| Task 4: `node --test scripts/test_fittings_runtime.js` | 151 passed; targeted fix 9 RED → GREEN | DOM/bridge doubles, not CSS rendering |
| Task 4: `uv run --no-sync python -m pytest tests/test_fittings_runtime.py tests/test_fittings_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py -q` | 481 passed | Includes Node harness; overlapping count |
| Parent Chrome script freshly rerun at `72050584`, widths 1280/840/839 | **PASS**: first-opener auto-read, server-invalidated ticket → Review again, failed-save same-ID retry, Add/Show/export, retained warnings, metadata draft/focus/caret, manual-paste refusal; no horizontal overflow/page errors; one accent action | Simulated dev clipboard only; scratch `browser-check-results.json` records results, not real clipboard/Windows acceptance |
| Global Ruff check / format check | Passed; 456 files already formatted | Parent evidence before final wrap-up |
| `node scripts/js_smoke.js` | PASS every page module loaded | Top-level execution only |
| Native prerequisites / Cargo regression | Release codec built and installed in checkout `packaging/bin`, availability confirmed; Cargo 1 test passed; Node on PATH | Not Windows runtime verification |
| Parent full pytest at `22d319f8` | **13223 passed, 1 failed, 13 expected Windows-only skips** | Missing `navigator` in preview dev VM; not a full pass |
| Harness-only fix `72050584`: isolated dev capture test; `tests/test_preview_savedlayouts_page.py` | 1 passed; 54 passed; JS smoke passed | Final full-suite rerun **pending** |
| Whole-change `polish-core --fix`, diff inspection and independent review | **Pending** | Scoped task reviews are not this final gate |
| Installed Windows/WebView2 clipboard, DPI and live EVE/Pyfa interchange smoke | **Not run / open** | Follow [smoke checklist](smoke-checklist.md); no manual acceptance claim |

Update these rows with fresh results before final integration. Task 5 remains
open until its automated, review and manual gates are accounted for separately.

## Reviewer focus

Prioritize the conventional-import/strict-export boundary, ticket retention
without resurrection, verified-name handoff ordering, single-snapshot locator,
and the real page-delivery lifecycle fence. Inspect UI cancellation at both copy
overlay openers, recovery without error-string parsing and dev/screenshot
isolation. The one-line preview harness fix belongs in the whole-change review.

## Knowledge check

1. Why may an incoming drone quantity use a warned bay convention while the equivalent stored Cargo drone row must refuse export?
2. What keeps Add tied to exactly the reviewed candidate across a failed save, and what can still invalidate a same-ID retry?
3. Why must verified names survive resolver eviction and reach the display cache before import notification, including a no-op import?
4. How do the single-snapshot locator and per-delivery lifecycle checks prevent different races without introducing another worker or state owner?
5. When may the opener read the clipboard, and how do retained drafts, late replies and dev/screenshot staging constrain delivery and focus?
