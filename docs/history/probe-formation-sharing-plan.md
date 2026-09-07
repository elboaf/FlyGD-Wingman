# Probe Formation Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Players copy one or several probe formations, review pasted formations in another Wingman installation, and explicitly save an additive draft without overwriting externally changed account settings.

**Architecture:** Extend the existing codec with same-byte content snapshots and opt-in guarded publication, then migrate the formation editor's read/save contract as one vertical change. A pure formation-sharing module owns the versioned JSON format and Unicode-aware import validation; the existing page owns selection, clipboard work, review, and unsaved edits. Persistence stays in the existing formation save worker.

**Tech Stack:** Python 3.11+, pytest/Ruff, plain HTML/CSS/ES5, pywebview 6.2.1/WebView2, existing bundled settings codec. Node subprocess tests use the repository's existing optional simulated-DOM testing pattern; no new runtime dependency, framework, bundler, or JavaScript package manager.

**Spec:** [Settings sharing design](settings-sharing-design.md), approved in conversation after independent-review revisions at `418ff64`. Scope is phase 1 only. Source baseline: `57ce91d`.

## Global Constraints

- Only the existing explicit Save action writes the account file.
- One destination account per editing session. No multi-account import in this release.
- No automatic replacement, skipping, or renaming.
- No new title-bar destination. Save remains the route's sole accent action; sharing controls are secondary.
- At most 64 KiB of UTF-8 text, checked before parsing.
- Between 1 and 32 formations per artifact; this is not a cap on the target account's existing list.
- Between 1 and 8 probes per formation, reusing the existing domain maximum.
- Names are trimmed, nonempty, at most 128 Unicode code points, and contain no control characters.
- Coordinates and range are finite JSON numbers, not booleans. Bound each coordinate's absolute value to `10^16` meters.
- Shared ranges must be between `10^-6` AU and `65536` AU, inclusive, expressed in meters in the artifact. Derive both meter limits from the existing AU constant (`149597870700` meters).
- Never export local IDs, paths, account/character metadata, content revisions, scratch entries, or selection state. Formation names remain user-authored text, not anonymized text.
- Preserve root containment, mutation locking, EVE-closed checks, backup-first publication, codec round-trip verification, and atomic replacement. Refuse stale files; no force-save or automatic merge.
- Content revision, local edit revision, and account/load generation are distinct. A successful commit advances its own baseline even if newer edits prevent reload.
- Conflict detection is optimistic: external writes after the final check remain a race. EVE must stay closed and the file must not be edited elsewhere during Save.
- Keep `.check` wrappers, accessible labels, text-only rendering of names, explicit hidden/display rules, focus restoration, and the 840x625 CSS floor. Real Windows/WebView2 and EVE checks remain required.
- Every non-method `Api` attribute is underscore-prefixed. `evesettings.js` remains the sole owner of `onEveSettingsDone` and forwards to `WM.formationsDone`.
- No changes to selective-copy semantics, arbitrary `.dat` import, overview sharing, complete UI setups, libraries, network access, or persisted Wingman settings.

---

## Evidence and decisions for review

| Decision | Repository evidence and consequence |
| --- | --- |
| Guard the entire formation save, not just paste | `api.py:8079–8146` reads an account again at save time but `formations.py:184–219` replaces the user list from the draft. External additions/selection can otherwise be lost. |
| Hash exactly the decoded bytes | `codec.py:78–87` currently has one `read_bytes()` before decode. Add a snapshot sibling, not a second independent read or fields on editable `Document`. |
| Optional writer guard; required editor revision | `ops.py:142–179` uses the same codec for selective copy. It must retain unguarded legacy behavior; the formation API must not retain a revision-free fallback. |
| Publication decides success | `api.py:8142–8152` currently publishes, prunes, reports status, then sets `ok=True`. Move success/revision capture immediately after publication, isolate subsequent housekeeping, and retain the existing single completion channel (`api.py:7497–7508`). |
| Inline import workspace, not a new modal framework | `index.html:1938–1987` and `style.css:4354–4456` already separate a scrolling work area from pinned commit controls. Temporarily show a paste/review work area in that pane; preserve the draft separately. |
| Python decides Unicode conflicts | `formations.py:148` uses `casefold()`; `formations.js:630–637` uses lowercase. Check import conflicts in Python both at review and at Add, not by copying the browser's approximation. |
| Preserve imported range validity | `formations.js:163–173,282,333` normalizes ordinary reloads to six decimal AU places. Keep that behavior, use an unrounded sharing conversion, and enforce the spec's representable range bounds. |
| Runtime tests without a new framework | `tests/test_fittings_page.py:568–902` and `tests/test_characters_page.py:354–687` execute real JS with Node and a small DOM simulation. This is narrower than browser rendering and contradicts older blanket statements that no tests execute JS. Use this precedent, not source extraction or a second implementation of production state logic. |
| Preserve editable long imported names | `index.html:1961` caps the normal name input at 40 UTF-16 units, while the approved format accepts 128 Unicode code points. Remove that HTML cap so imported names remain editable; enforce sharing limits in Python and import review, not as a new local-file restriction. |

Alternatives rejected: whole-file export leaks unknown data; restoring unchecked groups is not allowlisted extraction; automatic stale-file merge lacks an agreed conflict policy; native clipboard reads add permission failure modes without helping ordinary paste; globally disabling the editor during Save discards its established live-edit behavior; a generic preset registry or shared dialog overhaul is unnecessary for one type.

## File map and dependency order

| File | Responsibility/change |
| --- | --- |
| `wingman/evesettings/codec.py` | Same-byte snapshot, digest validation/conflict error, opt-in pre/post-backup checks, committed digest return. |
| `wingman/evesettings/formation_sharing.py` **new** | Strict version-1 JSON, limits, explicit export projection, import preparation and conflict indexes. |
| `wingman/ui/api.py` | Correlated guarded formation saves and pure sharing bridge methods. No public state attributes. |
| `wingman/web/formations.js` | Content baseline/generation tracking, reload recovery, copy selection, inline paste/review, preview reuse. |
| `wingman/web/index.html`, `style.css` | Secondary sharing/reload controls and inline review layout. No new production JS file. |
| `wingman/web/dev.js` | Migrate save/read fake together; add delayed conflict/import/clipboard scenarios. Fakes remain here only. |
| `tests/test_evesettings_codec.py`, `test_api_evesettings.py` | Extend existing seams and assertions; migrate old formation save callers. |
| `tests/test_evesettings_formation_sharing.py` **new** | Strict transport and pure conflict tests. |
| `tests/test_formations_page.py`, `tests/fixtures/formations_page.cjs` **new** | Execute the production editor with controllable bridge promises/events and a simulated DOM. |
| `tests/test_page_conventions.py`, `test_profiles_page.py`, `test_dev_harness.py` | Maintain existing guards and extend sharing-specific structural assertions. |
| `docs/smoke-checklist.md` | Add real-browser, WebView2, codec and cross-account acceptance checks. |

Task order is 1 → 2 → 3 → 4 → 5 → 6. Task 3's pure module could be implemented independently, but do not parallelize shared API/JS edits. Each task is a separately testable commit. No package-list or bundled-web-assets changes are needed: the new Python module is inside the existing `wingman.evesettings` package and the page adds no script.

## Task 1: Same-byte snapshots and guarded codec publication

**Files:** modify `wingman/evesettings/codec.py:45–142`; extend `tests/test_evesettings_codec.py`. Verify unchanged callers with `tests/test_evesettings_ops.py` and `tests/test_evesettings_selective.py`.

**Interfaces (new unless marked existing):**

```text
DocumentSnapshot(document: Document, content_revision: str)  # frozen dataclass
ContentChangedError(CodecError)
read_snapshot(path: Path, *, runner=subprocess.run, exe=paths.codec_exe) -> DocumentSnapshot
require_content_revision(path: Path, expected: str) -> None
read_document(path: Path, *, runner, exe) -> Document         # existing contract unchanged
write_document(path, document, *, backup, runner, exe, publish,
               expected_content_revision: str | None = None) -> str
```

Keep all existing keyword defaults on `write_document`. It returns the SHA-256 hex digest of the verified encoded bytes after successful publication, including for unguarded callers; inspected existing callers ignore its former `None` return. `None` means unguarded only at the codec layer. Empty or malformed non-`None` revisions are errors. `require_content_revision` accepts exactly 64 lowercase hex characters and raises `ContentChangedError` for mismatching, missing, or unreadable target content, preserving an underlying I/O cause without logging file contents.

- [ ] **Write snapshot and publication-order failing tests using existing `dat`, `FakeRun`, `TwoStepRun`, and `ENVELOPE`.** Add `hashlib` to the test imports. Start with:

```python
def test_snapshot_hashes_the_bytes_it_decoded(tmp_path):
    target = dat(tmp_path, b"ORIGINAL")
    def run(cmd, **kwargs):
        assert kwargs["input"] == b"ORIGINAL"
        target.write_bytes(b"EXTERNAL")
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(ENVELOPE).encode(), stderr=b""
        )
    snapshot = codec.read_snapshot(target, runner=run, exe=lambda: "/x/codec")
    assert snapshot.content_revision == hashlib.sha256(b"ORIGINAL").hexdigest()
    assert snapshot.document == codec.Document(ENVELOPE["doc"], False)


def test_backup_time_change_refuses_publication(tmp_path):
    target = dat(tmp_path, b"OLD")
    published = []
    def backup(path):
        path.write_bytes(b"EXTERNAL")
    with pytest.raises(codec.ContentChangedError):
        codec.write_document(
            target, codec.Document(ENVELOPE["doc"], False), backup=backup,
            runner=TwoStepRun(b"\x7dNEW", json.dumps(ENVELOPE).encode()),
            exe=lambda: "/x/codec",
            publish=lambda p, data: published.append(data),
            expected_content_revision=hashlib.sha256(b"OLD").hexdigest(),
        )
    assert published == []
    assert target.read_bytes() == b"EXTERNAL"
```

- [ ] **Run red:** `uv run --no-sync python -m pytest tests/test_evesettings_codec.py -q`. Confirm failures are the missing snapshot/guard behavior, not setup errors.
- [ ] **Implement the narrow seam.** Factor decode-of-bytes into a private helper shared by `read_document` and `read_snapshot`; do not change the `Document` fields or sidecar envelope. In the writer, retain all existing encode/signature/decode-back checks, then use this sequence:

```python
committed_revision = hashlib.sha256(data).hexdigest()
if expected_content_revision is not None:
    require_content_revision(Path(path), expected_content_revision)
backup(Path(path))
if expected_content_revision is not None:
    require_content_revision(Path(path), expected_content_revision)
publish(Path(path), data)
return committed_revision
```

  Validate expected-revision syntax before invoking the codec. Do not hash a reread after publication or claim an atomic compare-and-swap. Keep the existing publisher/retry implementation unchanged; the spec documents the remaining race after the last check.
- [ ] **Complete the focused test matrix:** mismatch before backup (including same-size bytes/restored mtime), mutation during encode/verification, post-backup conflict, missing/unreadable file, malformed digest, backup failure, publish failure, no backup on failed verification, exact returned digest, and unguarded behavior. A failed publisher returns no digest.
- [ ] **Run green:** `uv run --no-sync python -m pytest tests/test_evesettings_codec.py tests/test_evesettings_ops.py tests/test_evesettings_selective.py -q`; run Ruff on modified Python files.
- [ ] **Commit:** `git add wingman/evesettings/codec.py tests/test_evesettings_codec.py && git commit -m "feat: guard settings codec publication with content revisions"`.

## Task 2: Guard every formation-editor save and correlate completion

**Files:** modify `wingman/ui/api.py:8079–8162`, `wingman/web/formations.js:48–60,211–335,659–815`, `wingman/web/index.html`'s formation commit controls, `wingman/web/style.css`, `wingman/web/dev.js:2993–3039`, `tests/test_api_evesettings.py:2914–3109`, `tests/test_profiles_page.py`, `tests/test_page_conventions.py`, and `tests/test_dev_harness.py`. Create `tests/test_formations_page.py` and `tests/fixtures/formations_page.cjs`.

**Consumes:** Task 1 snapshot/guard/digest interfaces.

**Produces:**

```text
eve_settings_formations(path) -> existing payload plus content_revision on success
eve_settings_save_formations(path, formations, expected_content_revision="",
                             request_id="") -> bool
_eve_save_formations_worker(path, items, expected_content_revision, request_id)

onEveSettingsDone formation payload:
{ok, operation: "formations_save", path, request_id,
 content_revision, error_code, error, warning}
```

`content_revision` is the committed digest on success and `""` on refusal. `error_code` is `"stale_file"`, `"invalid_request"`, or `"save_failed"` on failure, `""` on success. Other string fields default to `""`; `warning` reports post-publication housekeeping trouble. Require a nonempty string request ID of at most 128 characters, echoed unchanged only for correlation. Existing callers missing a revision/request ID receive a refusal, never an unguarded write. Keep the asynchronous bool-started contract, including exactly one completion for each started worker.

- [ ] **Write failing API and page regressions.** Use existing `account_setup`, `_fake_codec`, `QueuedThreads`, `fakes.record_pushes`, and `fakes.payloads`; update `_fake_codec` to model snapshots/digests for ordinary tests. Build the executable harness and scenarios detailed later in this task before changing production JS, and record their expected failures against the old completion behavior. Start the API coverage with a missing-revision refusal:

```python
def test_formation_save_without_revision_is_refused(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "_eve_client_running_strict", lambda: False)
    before = account.read_bytes()
    sent = fakes.record_pushes(api)
    assert api.eve_settings_save_formations(str(account), [], "", "1:1")
    done = fakes.payloads(sent, "onEveSettingsDone")
    assert len(done) == 1
    assert done[0]["ok"] is False
    assert done[0]["error_code"] == "invalid_request"
    assert done[0]["content_revision"] == ""
    assert account.read_bytes() == before
```

  For stale-byte and publish/prune tests, use the **real** codec snapshot/writer with an injected subprocess, not a static `_fake_codec` that cannot prove hashing or publication. Add queued-worker mutation, encode-time mutation, backup-time mutation, existing-ID/scratch/selection retention, and a real publication followed by injected `_eve_prune` failure. Assert no prune on refused publication and exactly one completion/lock release on all paths.
- [ ] **Run red:** `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_formations_page.py -q`.
- [ ] **Implement the API and migrate callers in the same task.** Read snapshots under `_eve_hold`; under the save mutation lock, validate request/revision, enforce `_eve_client_running_strict`, read/compare one snapshot, transform its document, and pass its expected revision into `write_document`. Capture `ok=True` and the returned digest immediately on writer return. Isolate prune/status failures as warnings with logging; never issue “Formations not saved” for committed data. `_eve_done` already accepts extra details, so do not add another push handler. Classify `ContentChangedError` before general `CodecError`. Until Task 5 completes both Copy and Paste, use “This account's settings changed. Nothing was saved. Your edits are still here.” Task 5 replaces this interim text with the full copy-before-reload recovery guidance, so no intermediate commit points at a nonexistent action.

  The publication boundary is explicit:

```python
committed_revision = evesettings_codec.write_document(
    target, updated_document, backup=self._eve_auto_backup,
    expected_content_revision=expected_content_revision,
)
ok = True
# Retention/status are attempted separately after this commit boundary.
# Their failure must not reset ok or erase committed_revision.
```

  `updated_document` is `Document(updated, snapshot.document.had_crc)`; build `updated` with the existing `write_formations`. Keep `_eve_done` in `finally`, including on validation refusal. Use the existing profile-copy housekeeping separation at `api.py:7943–7963` as the local pattern.
- [ ] **Implement page correlation and explicit reload recovery.** Add `state.contentRevision`, a monotonically increasing load generation, a read-attempt counter, a save sequence, and one `pendingSave` snapshot. Generate request IDs from page-session identity plus generation/sequence; these are not authorization tokens. Retain the distinction between `selectedAccountPath` (choice identity) and `state.path` (resolved save target).

  Use a page-session prefix created once as `String(Date.now()) + '-' + Math.random().toString(36).slice(2)`, then append generation and incremented save sequence. Initialize failure/completion fields before the worker's try block so validation errors still complete safely.

  Before a completion touches busy/dirty state, require the operation, request ID, resolved path, originating load generation, and current route to match `pendingSave`. On successful completion, set `state.contentRevision` **before** the existing `revision !== savingAt` early return. Clear the pending save exactly once. Do not clear newer edits. Adopt a read response's document and revision together only if route/generation/attempt and existing edit guards accept it. A refused/ignored response advances neither one. A delayed bool-started reply must also check its request before clearing busy state.

  Add secondary `fm-reload` and a persistent text-only `fm-save-status`. Reload uses `WM.confirm` if dirty, then an explicit same-account read; failure/cancellation retains the old draft and revision. Stale-file errors leave ordinary editing available. Copy-based recovery becomes available in Task 4; no automatic reload or force save. Preserve Back/account-switch dirty protection and never let another Profiles operation's completion clear the editor's busy state.
- [ ] **Bring the initially failing executable harness green and migrate dev fakes.** The harness written in the red step follows `test_fittings_page.py`'s `_PageTree` + Node `vm` pattern, loading the real formation markup and unmodified production `formations.js`. New harness simulates only DOM/SVG mechanics, `WM` bridge promises, clipboard and completion delivery; do not port load/save logic into tests. Provide controlled read/start promises and invoke the real `WM.formationsDone`. Add scenarios for successful baseline advancement with newer edits, ignored read revisions, stale route/account callbacks, start-reply-after-completion, failed switch, and second save from retained post-commit edits.

  A Python wrapper in `test_formations_page.py` should follow this subprocess contract (`_PageTree` is defined locally using `HTMLParser`, as in the existing Fittings test):

```python
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("scenario", [
    "commit-keeps-newer-edit", "ignored-read-keeps-baseline",
    "old-completion-ignored", "second-save-retained-draft",
])
def test_formation_editor_runtime(tmp_path, scenario):
    page = _PageTree()
    page.feed((WEB / "index.html").read_text(encoding="utf-8"))
    markup = tmp_path / "page.json"
    markup.write_text(json.dumps(page.root), encoding="utf-8")
    result = subprocess.run(
        ["node", str(ROOT / "tests/fixtures/formations_page.cjs"),
         str(markup), scenario, str(WEB / "formations.js")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
```

  Define `ROOT`, `WEB`, imports and `_PageTree` in that new test file. The harness reads arguments in the same order and prints `PASS <scenario>` only after its actual production event-flow assertions. No JS package installation. Preserve dev's delayed reads, minted IDs, and single completion channel; fake revisions may be monotonically generated 64-character strings, never presented as real hashing evidence.
- [ ] **Run green and commit together:** `uv run --no-sync python -m pytest tests/test_evesettings_codec.py tests/test_api_evesettings.py tests/test_formations_page.py tests/test_profiles_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_bridge_contract.py -q`. Node scenarios must execute locally, not all skip. Stage only this task's listed files and commit `feat: refuse stale formation saves and preserve committed revisions`.

## Task 3: Strict portable formation format and import preparation

**Files:** create `wingman/evesettings/formation_sharing.py`, `tests/test_evesettings_formation_sharing.py`. No bridge/UI change yet.

**Consumes:** existing `formations.Formation`, `Probe`, `MAX_PROBES`, `from_payload`, `validate`, `to_payload`. Existing `from_payload` coerces strings/booleans to float, so it is not sufficient at this trust boundary.

**Produces:**

```text
export_text(items: list[dict]) -> str
parse_text(text: str) -> list[Formation]                         # all IDs None
prepare_import(items: list[dict], existing_names: list[str])
    -> tuple[list[Formation], list[int]]                        # conflict indexes
limits_payload() -> dict                                       # authoritative UI limits
```

`export_text` consumes selected internal meter-valued payloads with `id`, `name`, `probes`, explicitly projects only names/geometry, then validates that projection. `parse_text` accepts only the spec's exact external keys: root `format/version/type/formations`, formation `name/probes`, probe `x/y/z/range`. `prepare_import` consumes canonical internal payloads with `id: None` after review renames and returns validated candidates plus indexes colliding with existing names. Duplicate incoming names are a validation error, not a target conflict. Existing draft names are compared as stored using `casefold()`; do not validate unrelated draft geometry or turn its pre-existing errors into import errors. All failures raise a contextual `ValueError`; no state changes or I/O.

- [ ] **Write failing format tests.** Define a reusable `item()` helper and verify identity omission and Unicode conflict behavior:

```python
import json
import pytest
from wingman.evesettings import formation_sharing as sharing
from wingman.evesettings.formations import to_payload


def item(name="Pinpoint", ident=7, scan_range=149597870700):
    return {"id": ident, "name": name, "probes": [
        {"x": -1250.5, "y": 0, "z": 2500.25, "range": scan_range}
    ]}


def test_share_round_trip_omits_local_identity():
    text = sharing.export_text([item()])
    wire = json.loads(text)
    assert set(wire) == {"format", "version", "type", "formations"}
    assert set(wire["formations"][0]) == {"name", "probes"}
    parsed = sharing.parse_text(text)
    assert parsed[0].id is None
    assert to_payload(parsed)[0] == item(ident=None)


def test_target_conflicts_use_python_casefold():
    prepared, conflicts = sharing.prepare_import(
        [item(name="Straße", ident=None)], ["STRASSE"]
    )
    assert prepared[0].name == "Straße"
    assert conflicts == [0]
```

- [ ] **Run red:** `uv run --no-sync python -m pytest tests/test_evesettings_formation_sharing.py -q`.
- [ ] **Implement bounded strict decoding and explicit projection.** Check string type, character count as an early byte-limit bound, then UTF-8 encoded size before `json.loads`. Reject unpaired surrogates, unknown fields, duplicate object keys, non-integer/bool version, unsupported type/version, non-list collections, and non-object entries. Catch decode errors and recursion/overflow errors as contextual `ValueError`; do not swallow exceptions broadly. Use `object_pairs_hook` and `parse_constant` rejection:

```python
def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"Repeated JSON field: {key}.")
        out[key] = value
    return out


def _constant(value):
    raise ValueError(f"Invalid JSON number: {value}.")


def _number(value, low, high, label):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f"{label}: value is outside the sharing limits.")
    return float(value)
```

  Define `AU_METERS = 149_597_870_700`, meter range bounds derived from it, byte/count/name constants, and coordinate bound in this module. Import `MAX_PROBES`. `limits_payload()` returns `max_bytes`, `max_formations`, `max_name_codepoints`, `max_probes`, `au_meters`, `min_range_meters`, `max_range_meters`, `max_coordinate_meters`. Assert AU equality with the existing JS literal in tests rather than leaving an unchecked copy.

  Trim names; count Python Unicode code points; reject `unicodedata.category(ch) == "Cc"` and strings not UTF-8 encodable. Validate incoming case-fold uniqueness and probe counts; reject booleans/numeric strings before domain conversion. Build new domain objects with no IDs. Emit compact JSON with `ensure_ascii=False`, `allow_nan=False`; bound output bytes too. Never clamp, truncate, include metadata, parse Markdown fences, or fetch a URL.
- [ ] **Complete boundary tests:** 0/1/32/33 formations; 0/1/8/9 probes; 128/129 code-point and supplementary-plane names; empty/control/surrogate names; duplicate incoming names; UTF-8 byte boundary with multibyte names; unknown keys at each level; duplicate root/nested keys; numeric string/bool/NaN/infinity/huge integer; deeply nested JSON; whitespace-only/malformed/truncated input; exact and adjacent range bounds; 1 meter and `1e-320`; coordinate bounds; oversized export; valid selected items alongside an unselected invalid draft. Assert input lists/dicts are unchanged on success and failure.
- [ ] **Run green:** `uv run --no-sync python -m pytest tests/test_evesettings_formation_sharing.py tests/test_evesettings_formations.py -q`; run Ruff on both new files.
- [ ] **Commit:** `git add wingman/evesettings/formation_sharing.py tests/test_evesettings_formation_sharing.py && git commit -m "feat: define strict portable probe formation presets"`.

## Task 4: Copy selected draft formations through the bridge

**Files:** modify `wingman/ui/api.py`, `wingman/web/formations.js`, `wingman/web/index.html`, `wingman/web/style.css`, `wingman/web/dev.js`, `tests/test_api_evesettings.py`, `tests/test_formations_page.py`, `tests/fixtures/formations_page.cjs`, `tests/test_profiles_page.py`, `tests/test_page_conventions.py`, and `tests/test_dev_harness.py`.

**Consumes:** `formation_sharing.export_text`, `limits_payload`, existing `toMeters(f)`, Task 2 account/load generation.

**Produces:**

```text
eve_settings_export_formations(items: list) -> {ok: True, text: str}
                                               | {ok: False, error: str}
eve_settings_formations(path) success additionally includes sharing_limits
```

- [ ] **Write failing API and runtime tests.** A pure export request succeeds without configuring an EVE folder or codec and performs no file writes; malformed payload returns a serializable failure, not an exception. Runtime scenarios select two rows independently of the current editor row, modify a valid selected draft, copy, and inspect the exact meter-valued bridge request. Include an unselected invalid formation, clipboard denial/throw, repeated attempts, account/route change before bridge response, and route change before clipboard completion.

  Example API test uses existing `build` and an explicit payload:

```python
def test_export_formations_does_not_need_an_account(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    reply = api.eve_settings_export_formations([
        {"id": 99, "name": "Pair", "probes": [
            {"x": 1000, "y": 0, "z": 0, "range": 149597870700}
        ]}
    ])
    assert reply["ok"] is True
    shared = json.loads(reply["text"])
    assert "id" not in shared["formations"][0]
```

- [ ] **Run red:** `uv run --no-sync python -m pytest tests/test_api_evesettings.py::test_export_formations_does_not_need_an_account tests/test_formations_page.py -q`.
- [ ] **Implement the thin endpoint and page controls.** Import the pure module with an underscored/non-public API reference pattern matching existing imports. The endpoint delegates and catches `ValueError`; it does not report clipboard success. Add `.check` checkboxes as siblings of the existing `.fm-item` buttons, not nested interactive controls. Accessible names say `Select <formation name> for sharing`; selection tracks formation object identity, not array indexes that move after deletion. Clear it on accepted document replacement; removing an item removes that selection.

  Add secondary `fm-copy` (`Copy selected`) in the rail with a derived selected count and persistent text-only `fm-share-status`. Keep Task 2's interim stale-file text until Paste also exists in Task 5. Keep copy enabled for valid selected drafts during stale-file recovery, but disabled during account loading/saving. Snapshot selected values with `toMeters` at invocation; use generation/attempt guards before clipboard invocation and completion status. Follow `skills.js:450–499` for promise rejection and synchronous clipboard failure handling:

```javascript
var attempt = ++copyAttempt;
var generation = loadGeneration;
var items = state.formations.filter(function (f) {
  return copySelection.indexOf(f) !== -1;
}).map(toMeters);
WM.send('eve_settings_export_formations', items).then(function (reply) {
  if (generation !== loadGeneration || attempt !== copyAttempt
      || WM.current_route !== 'formations') { return; }
  if (!reply || !reply.ok) {
    setShareStatus((reply && reply.error) || 'Could not prepare formations.', true);
    return;
  }
  function stillCurrent() {
    return generation === loadGeneration && attempt === copyAttempt
      && WM.current_route === 'formations';
  }
  try {
    navigator.clipboard.writeText(reply.text).then(function () {
      if (stillCurrent()) { setShareStatus('Formations copied.', false); }
    }, function () {
      if (stillCurrent()) {
        setShareStatus('Could not copy formations to the clipboard.', true);
      }
    });
  } catch (error) {
    if (stillCurrent()) {
      setShareStatus('Could not copy formations to the clipboard.', true);
    }
  }
}, function () {
  if (generation === loadGeneration && attempt === copyAttempt
      && WM.current_route === 'formations') {
    setShareStatus('Could not prepare formations.', true);
  }
});
```

  Define `copyAttempt`, `copySelection`, and `setShareStatus(text, isError)` in this task. No automatic clipboard reads. Once the OS clipboard call begins it cannot be revoked; stale outcomes are ignored and cannot change another account's UI. Use authoritative limits from the read payload for UI guidance, not duplicate hardcoded limits. Ensure an empty account still loads limits and can paste in Task 5.
- [ ] **Migrate the dev export stub and add scenarios.** It may fabricate responses for its scenario data, but must not claim to prove Python's strict parser or Unicode case-fold policy. Run actual contract tests against the Python module. Assert the read fake includes limits and the copy code never sends a destination path or calls Save.
- [ ] **Run green:** `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_formation_sharing.py tests/test_formations_page.py tests/test_profiles_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_bridge_contract.py -q`. Inspect copy and recovery controls in `?dev=1` at the floor before committing.
- [ ] **Commit listed task files:** `feat: copy selected probe formations from the editor`.

## Task 5: Inline paste review, conflict resolution and atomic draft addition

**Files:** modify `wingman/ui/api.py`, `wingman/web/formations.js`, `wingman/web/index.html`, `wingman/web/style.css`, `wingman/web/dev.js`, `tests/test_api_evesettings.py`, `tests/test_formations_page.py`, `tests/fixtures/formations_page.cjs`, `tests/test_profiles_page.py`, `tests/test_page_conventions.py`, and `tests/test_dev_harness.py`. Extend `tests/test_evesettings_formation_sharing.py` if an uncovered strict-input case is found. No new production module.

**Consumes:** `parse_text`, `prepare_import`, `formations.to_payload`, sharing limits, Task 2 generation/edit guards.

**Produces:**

```text
eve_settings_parse_formations(text: str, existing_names: list)
eve_settings_validate_formation_import(items: list, existing_names: list)
Both return {ok: True, formations: list, conflicts: list[int]}
         or {ok: False, error: str}

fromSharedMeters(f) -> editor-unit formation with id: null, unrounded range
renderFormationPreview(svg, formation) -> draws geometry without changing state
```

Parsing calls `parse_text`, then `prepare_import` on its canonical payload. Validation calls `prepare_import` on the renamed candidates. Both are pure bridge calls with no paths, persistence, or pending Python session. Existing draft names cross only because Python computes conflicts. Python compares their actual values with `casefold()`; it must not reject an import merely because another existing draft formation has invalid probes.

- [ ] **Write failing API/runtime tests.** Verify parse/validate are side-effect-free, normalize IDs to `None`, return target-conflict indexes, reject malformed/duplicate incoming names, and treat `Straße` versus `STRASSE` consistently. Runtime scenarios cover paste/edit/review, malformed/deep input, cancel with existing unsaved edits, rename conflict resolution, whole-batch addition, empty destination, current-row independence, changed draft during validation, stale route/account replies, and Add double-click. Feed real Python-generated responses into Node scenarios for Unicode/strict-boundary cases rather than reproducing Python validation inside the harness.
- [ ] **Run red:** `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_formations_page.py -q`.
- [ ] **Add an inline review workspace.** Give the existing ordinary `.fm-work` an ID (`fm-editor-work`). Add sibling `fm-import-work` with class `.fm-work`, initially hidden, and pinned sibling `fm-import-commit`. Normal work/commit hide while review is open; cancel restores them and focuses `fm-paste`. No global modal, focus trap, or new route is needed.

```html
<section class="fm-work" id="fm-import-work" aria-labelledby="fm-import-heading" hidden>
  <h2 id="fm-import-heading">Paste formations</h2>
  <label class="lab" for="fm-import-text">Shared formation text</label>
  <textarea class="field" id="fm-import-text" rows="6"
            aria-describedby="fm-import-status"></textarea>
  <div id="fm-import-list"></div>
  <svg id="fm-import-preview" viewBox="0 0 100 100"
       role="img" aria-label="Imported formation preview"></svg>
</section>
<div class="row" id="fm-import-commit" hidden>
  <button class="btn" id="fm-import-review" type="button">Review</button>
  <button class="btn" id="fm-import-add" type="button" disabled>Add formations</button>
  <button class="btn" id="fm-import-cancel" type="button">Cancel</button>
  <span class="hint" id="fm-import-status" role="status"></span>
</div>
```

  Add `fm-paste` (`Paste formations…`) as a secondary rail control. Both recovery actions now exist; replace the API's interim stale-file text with the spec's full guidance: “This account's settings changed since you opened them. Nothing was saved. Copy the formations you want to keep, then reload the account before pasting them back.” Avoid `maxlength` on the textarea: silently clipping an oversized paste would conceal the reason validation failed. Use the byte limit for immediate error feedback and backend rejection. Remove the normal `fm-name` input's `maxlength="40"`; review names are fully editable and validated on explicit Add, including Python code-point length. No change to ordinary local-file name validation.

  Add scoped `[hidden]` overrides for every new/changed display-setting selector, including `fm-editor-work`, `fm-commit`, `fm-import-work`, and `fm-import-commit`. Keep pinned actions outside scrollable content and use existing tokens/classes. While import review is open, disable normal New/Save actions rather than allowing an invisible edit; Cancel, Back and ordinary text editing remain usable. Account/route changes still invalidate the review even when triggered outside these controls.
- [ ] **Implement review state and reuse the preview without swapping drafts.** Keep one page-local import state with text, canonical meter-valued candidates, selected preview index, captured resolved path/load generation/edit revision, and monotonically increasing attempt ID. Changing pasted text or candidate names invalidates the prior validated result. Review is explicit; do not continually send names or clipboard data on keystrokes. Target collisions display next to their named incoming rows; no default replacement or automatic rename.

  Factor the existing drawing body into `renderFormationPreview(svg, f)` while retaining yaw/pitch/projection helpers. `renderPreview()` calls it with `current()`; review calls it with a separate `fromSharedMeters(candidate)`. Do not temporarily assign `state.formations` or `state.selected`. Centralize conversions so sharing uses unrounded AU division while ordinary `fromMeters` retains normalization; update the old “two places” comment and boundary guard to describe all actual callers.

  On explicit Add, snapshot renamed candidates and current existing names, call the validation endpoint again, and permit insertion only if **all** captured context and review-attempt values still match. Do not trust a previous conflict-free response after a name edit. Create the converted batch before mutation; insertion is one concatenation:

```javascript
var firstAdded = state.formations.length;
var additions = reply.formations.map(fromSharedMeters);
state.formations = state.formations.concat(additions);
state.selected = firstAdded;
markDirty();
closeImportReview(false);
renderAll();
```

  This runs only after checking `reply.ok`, no conflicts, unchanged route/path/load generation/edit revision/review attempt, and an outstanding Add request. Define `closeImportReview(restoreInvokerFocus)` to invalidate attempts, clear candidates and restore the normal pane; call with `true` on Cancel and `false` on successful Add, then focus the first added row. No ID allocation, file write, or account reread occurs here. Duplicate Add replies become stale after the first insertion advances the edit revision/closes review.
- [ ] **Complete lifecycle tests.** Run numeric bounds through the **production** sharing conversion, Save payload and ordinary reload for at least two full cycles. Include min/max neighbors, supported fractional ranges and a multi-formation batch with existing IDs/selection. Inspect outgoing requests to prove Add/Cancel never call Save and renamed responses cannot add after route exit. Test text-only rendering with markup-shaped names, 128 supplementary-character names, focus restoration, keyboard-only operation, and visible error/Cancel controls at the floor. Dev fixtures include invalid JSON, conflicts, slow validation, stale file, empty account and copied unsaved edits.
- [ ] **Run green:** `uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_formation_sharing.py tests/test_evesettings_formations.py tests/test_formations_page.py tests/test_profiles_page.py tests/test_page_conventions.py tests/test_dev_harness.py tests/test_bridge_contract.py -q`. Execute the new Node scenarios, then a real-browser `?dev=1` pass. Stage the listed files and commit `feat: review and paste shared probe formations into drafts`.

## Task 6: Cross-boundary verification, smoke coverage and polish

**Files:** extend `docs/smoke-checklist.md` in the existing Probe formations section and `tests/test_api_evesettings.py` for the cross-account test. Extend `tests/test_evesettings_codec.py`, `tests/test_evesettings_formation_sharing.py`, `tests/test_formations_page.py`, and `tests/fixtures/formations_page.cjs` only for uncovered contract cases. Create `docs/probe-formation-sharing-verification.md` recording actual results and unverified platform gates. No unrelated cleanup.

**Consumes:** all Task 1–5 contracts. **Produces:** a tested release candidate and an honest verification record, not an automatic release or merge.

- [ ] **Add a complete cross-account test** that exports from account A, parses/reviews with account B's names, saves into B with its loaded revision, and decodes the committed document. Assert A is unchanged; B retains its existing IDs, scratch entries, unrelated keys and valid selection; new IDs are allocated above B's existing nonnegative IDs without reusing A's IDs as authority; B's new revision matches its actual published bytes. Choose source/target fixture IDs that make accidental source-ID reuse visible. Numeric equality across unrelated accounts can be coincidental and is not itself a failure. Use the real codec APIs with a lossless fake subprocess for Linux portability, plus the bundled-codec integration when available. Add the stale B mutation variant and a publish-success/prune-failure variant.
  Add the integration test in `tests/test_api_evesettings.py`, using its existing fixtures and the production APIs. This lossless fake filter models only the sidecar transport, not application logic:

```python
def test_shared_formation_lifecycle_between_accounts(tmp_path, monkeypatch):
    import hashlib
    from wingman.evesettings import codec, formations

    def filter_bytes(mode, payload, **kwargs):
        if mode == "encode":
            return b"\x7d" + payload
        assert payload.startswith(b"\x7d")
        return payload[1:]

    def entry(ident, name):
        return {"id": ident, "name": name, "probes": [
            {"x": 1000, "y": 0, "z": 0, "range": 149597870700}
        ]}

    def document(items):
        return formations.write_formations(
            {}, formations.from_payload(items), now=1
        )

    def encoded(doc):
        return b"\x7d" + json.dumps({"had_crc": False, "doc": doc}).encode()

    api, source = account_setup(tmp_path, monkeypatch)
    fake_status(api, monkeypatch)
    monkeypatch.setattr(codec, "_run", filter_bytes)
    monkeypatch.setattr(api, "_eve_client_running_strict", lambda: False)
    target = source.with_name("core_user_2.dat")
    source.write_bytes(encoded(document([entry(900, "Incoming")])))
    target_doc = document([entry(2, "Existing")])
    target_doc["bytes:unrelated"] = "utf8:keep"
    scratch = {"tuple": ["bytes:tempFormation", []]}
    target_doc[formations.UI_KEY][formations.FORMATIONS_KEY]["tuple"][1]["int:-4"] = scratch
    target.write_bytes(encoded(target_doc))
    source_before = source.read_bytes()

    sender = api.eve_settings_formations(str(source))
    recipient = api.eve_settings_formations(str(target))
    exported = api.eve_settings_export_formations(sender["formations"])
    review = api.eve_settings_parse_formations(
        exported["text"], [f["name"] for f in recipient["formations"]]
    )
    assert review["ok"] and review["conflicts"] == []
    assert all(f["id"] is None for f in review["formations"])
    sent = fakes.record_pushes(api)
    assert api.eve_settings_save_formations(
        str(target), recipient["formations"] + review["formations"],
        recipient["content_revision"], "lifecycle:1",
    )
    done, = fakes.payloads(sent, "onEveSettingsDone")
    assert done["ok"] and done["request_id"] == "lifecycle:1"
    assert done["content_revision"] == hashlib.sha256(target.read_bytes()).hexdigest()
    saved = codec.read_document(target).doc
    assert [(f.id, f.name) for f in formations.read_formations(saved)] == [
        (2, "Existing"), (3, "Incoming")
    ]
    assert saved[formations.UI_KEY][formations.SELECTED_KEY]["tuple"][1] == 2
    assert saved[formations.UI_KEY][formations.FORMATIONS_KEY]["tuple"][1]["int:-4"] == scratch
    assert saved["bytes:unrelated"] == "utf8:keep"
    assert source.read_bytes() == source_before
```

  Run this test red before correcting an integration failure, then green. If it passes immediately, record it as added coverage rather than claiming a red phase. Parameterize the external-mutation and housekeeping-failure variants with assertions from Task 2.
- [ ] **Extend smoke checks explicitly:** clipboard denial; invalid/oversized/deep text; batch/name limits and Unicode conflicts; rename/cancel; empty destination; Copy preserving unsaved edits; paste adding only on Add; save only on Save; stale-file recovery with copy-before-reload; edits during save/reload; repeated saves; EVE-running refusal; backup restoration; 840x625 and 839x621 layouts; keyboard and screen-reader labels. A developer's browser pass is not a Windows/WebView2 or live-EVE pass.
- [ ] **Run `polish-core --fix` against the implementation base**, inspect every edit, and keep only safe in-scope changes. This is a skill invocation, not an assumed shell executable. Re-run the affected tests after any edits and then the full gates below. Use `change-explainer` for the completion write-up.
- [ ] **Run fresh full verification:**

```bash
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/ -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node --check wingman/web/formations.js
node --check wingman/web/dev.js
git diff --check
```

  Ensure the Node runtime tests actually ran in this environment; follow existing skip-if-Node-unavailable behavior for other environments and report skips. Keep existing CI's Ubuntu/Windows matrix; do not add a new JS package/build pipeline. If CI skips Node scenarios, record that gap rather than claim automated runtime coverage there.
- [ ] **Perform real Windows/WebView2 and two-account EVE smoke checks**, with all clients closed for saves and unrelated account copies/backups prepared first. Verify actual probe geometry/ranges and selected formation after launch, then restore the backup. If the environment is unavailable, record these gates as unverified and do not call the feature release-ready.
- [ ] **Inspect the final diff against the approved scope**, update the verification record with exact commands/results, and commit only the task's docs/tests/polish corrections: `test: verify probe sharing lifecycle and recovery`.

## Spec coverage and adaptation points

| Approved requirement | Implementing task |
| --- | --- |
| Same-byte snapshots, guarded publication, explicit stale-file recovery | 1–2 |
| Committed baseline despite newer edits; stale callbacks ignored | 2, 5–6 |
| Strict allowlisted/versioned format, size/name/numeric bounds | 3 |
| Export selected current draft values; clipboard success/failure | 4 |
| Paste/review/rename; authoritative case-fold conflicts; all-or-nothing Add | 3, 5 |
| No writes until Save; local IDs and existing selection retained | 2, 5–6 |
| Valid ranges through conversion/save/reload/export | 3, 5–6 |
| Page ownership, accessible controls, no new destination | 2, 4–5 |
| Real-browser/WebView2/EVE evidence and restore | 6 |
| Later overview/UI/library phases remain deferred | All tasks |

Revisit the plan rather than guess if the bundled codec's actual return/verification behavior differs from the tested seam, the guarded writer cannot preserve another caller's existing behavior, or live EVE rejects an otherwise valid shared formation. A parser or UI gap discovered while implementing phase 1 does not authorize raw account-file import, general settings schemas, automatic merges, new cloud services, or a redesigned Profiles screen.

## Planning verification actually performed

- Inspected the approved design, product/design guidance, formation code/UI and existing tests. One structured read-only subagent pass verified codec callers, API fixtures and publication boundaries.
- Ran `uv run --no-sync python -m pytest tests/test_evesettings_formations.py tests/test_evesettings_codec.py tests/test_evesettings_ops.py tests/test_api_evesettings.py tests/test_page_conventions.py tests/test_profiles_page.py tests/test_dev_harness.py tests/test_bridge_contract.py -q`: **698 passed, 1 skipped**. The skipped test requires the absent bundled codec.
- Self-review mapped every spec section to the six tasks, checked cross-task names/signatures and intermediate behavior, and checked for placeholders. Document checks parsed all nine Python snippets, syntax-checked both JavaScript snippets with Node, and verified relative links and existing file references. Proposed new files were checked against the creation list, not treated as missing repository files.
- These results are baseline/planning evidence only. New symbols, tests, UI states, content-revision guards and sharing endpoints described here have not been implemented. Browser, Windows/WebView2 and live-EVE verification remain future execution gates.
