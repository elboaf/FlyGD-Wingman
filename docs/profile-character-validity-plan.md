# Profile Character Validity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide ESI-confirmed deleted Tranquility characters from Profiles, automatically remove their Wingman account links, and preserve EVE files, backups, and offline behavior.

**Architecture:** Keep filesystem discovery pure. Add a focused ESI character-status module, then coordinate its bounded background checks from `Api`; remote status is cached by datasource/ID while application to the selected profile is guarded by a canonical context. Persist cleanup under the existing Profiles mutation lock, publish settings atomically, and carry identification generations across the bridge so stale promises cannot resurrect deleted candidates.

**Tech Stack:** Python 3.11, stdlib `urllib` and `concurrent.futures`, pywebview bridge, ES5 JavaScript, pytest, Ruff.

**Spec:** `docs/profile-character-validity-design.md`

## Global Constraints

- Only the exact ESI 404 JSON error `Character has been deleted!` authorizes hiding or cleanup.
- Timeouts, 422, 429, other 404s, 5xx, malformed responses, and missing results are transient and non-destructive.
- Deletion checks and account identity management are limited to trusted Tranquility server directories.
- Never delete, move, rename, or rewrite `core_char_*.dat` files or backups.
- Existing account identity metadata is interpreted as Tranquility-only.
- Persisted account-link cleanup is automatic; account names are retained.
- Active characters are rechecked on later resolver passes; deleted verdicts are process-lifetime facts.
- ESI work never runs on the bridge thread, and no network call holds `_eve_mutation`.
- Every non-method `Api` attribute remains underscore-prefixed.
- No new dependency or package is required.
- Any web-layer change receives a Windows Profiles smoke pass.

---

### Task 1: Atomic settings publication

**Files:**
- Modify: `wingman/settings.py:1-15, 819-823`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `wingman.atomicio.write_atomic(path: Path, text: str, encoding="utf-8")`.
- Produces: unchanged `settings.save`, `settings.update`, and `settings.update_section` interfaces with replace-based disk publication.

- [ ] **Step 1: Write failing publication tests**

Add tests that monkeypatch `settings.atomicio.write_atomic` rather than `Path.write_text`:

```python
def test_save_publishes_the_complete_document_through_atomic_io(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    seen = []
    monkeypatch.setattr(
        settings.atomicio,
        "write_atomic",
        lambda path, text, encoding="utf-8": seen.append((path, text, encoding)),
    )
    data = settings.load(target)

    settings.save(data, target)

    assert seen[0][0] == target
    assert json.loads(seen[0][1])["privacy"] == data["privacy"]
    assert seen[0][2] == "utf-8"


def test_update_restores_memory_and_keeps_old_file_when_atomic_publish_fails(
    tmp_path, monkeypatch
):
    target = tmp_path / "settings.json"
    target.write_text('{"sentinel": "old"}', encoding="utf-8")
    data = settings.load()
    before = copy.deepcopy(data)
    monkeypatch.setattr(
        settings.atomicio,
        "write_atomic",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("locked")),
    )

    with pytest.raises(OSError, match="locked"):
        settings.update_section(data, "eve_settings", {"auto_keep": 7}, target)

    assert data == before
    assert target.read_text(encoding="utf-8") == '{"sentinel": "old"}'
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
uv run --no-sync python -m pytest tests/test_settings.py -k "atomic_io or atomic_publish" -v
```

Expected: failure because `_save_locked()` still calls `Path.write_text()` and `settings.atomicio` is not imported.

- [ ] **Step 3: Route `_save_locked()` through atomic I/O**

Import `atomicio` from the package and replace direct publication:

```python
from . import atomicio


def _save_locked(data: dict, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    atomicio.write_atomic(path, json.dumps(payload, indent=2), encoding="utf-8")
```

Do not add a second retry loop; `write_atomic()` owns Windows replacement retries.

- [ ] **Step 4: Run focused settings and atomic-I/O tests**

```bash
uv run --no-sync python -m pytest tests/test_settings.py tests/test_atomicio.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wingman/settings.py tests/test_settings.py
git commit -m "fix: publish settings atomically"
```

---

### Task 2: Authoritative ESI character status

**Files:**
- Create: `wingman/evesettings/characters.py`
- Create: `tests/test_evesettings_characters.py`

**Interfaces:**
- Produces: `ACTIVE`, `DELETED`, `TRANSIENT`; `classify(status: int, body: str) -> tuple[str, str]`; `fetch_character(character_id: int, *, transport=..., timeout=8.0) -> tuple[str, str]`; `resolve(ids, fetch=fetch_character, max_workers=4) -> tuple[dict[int, str], set[int]]`.
- Consumed later by: `Api.eve_settings_resolve_names()` coordinator.

- [ ] **Step 1: Write classifier and resolver tests**

Cover exact deletion, successful name extraction, all conservative outcomes, deduplication, and bounded parallelism. Core cases:

```python
def test_only_the_exact_deleted_404_is_destructive():
    body = json.dumps({"status": 404, "error": "Character has been deleted!"})
    assert characters.classify(404, body) == (characters.DELETED, "")
    assert characters.classify(404, json.dumps({"error": "not found"})) == (
        characters.TRANSIENT,
        "",
    )


@pytest.mark.parametrize("status", [422, 429, 500, 503])
def test_other_failures_are_transient(status):
    assert characters.classify(status, "") == (characters.TRANSIENT, "")


def test_success_requires_a_nonempty_name():
    assert characters.classify(200, json.dumps({"name": " Pilot "})) == (
        characters.ACTIVE,
        "Pilot",
    )
    assert characters.classify(200, json.dumps({"name": ""})) == (
        characters.TRANSIENT,
        "",
    )


def test_resolve_returns_active_names_and_deleted_ids():
    def fetch(ident):
        return (characters.DELETED, "") if ident == 2 else (
            characters.ACTIVE,
            f"Pilot {ident}",
        )

    names, deleted = characters.resolve([1, 2, 1], fetch=fetch, max_workers=2)
    assert names == {1: "Pilot 1"}
    assert deleted == {2}
```

Use a guarded fake fetch with counters/events to assert simultaneous calls never exceed `max_workers`.

- [ ] **Step 2: Run and confirm module-not-found failure**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_characters.py -v
```

Expected: import failure because `characters.py` does not exist.

- [ ] **Step 3: Implement strict transport and bounded resolver**

Use `urllib.request.Request` with the existing Wingman user agent convention, GET
`https://esi.evetech.net/latest/characters/{id}/?datasource=tranquility`, classify `HTTPError` bodies, and degrade every other exception to `TRANSIENT`. Resolve unique positive integer IDs through `ThreadPoolExecutor(max_workers=max_workers)`; a future exception becomes transient for that ID and never escapes.

Representative classifier:

```python
def classify(status: int, body: str) -> tuple[str, str]:
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return TRANSIENT, ""
    if status == 404 and isinstance(parsed, dict):
        if parsed.get("error") == "Character has been deleted!":
            return DELETED, ""
    if not 200 <= status < 300 or not isinstance(parsed, dict):
        return TRANSIENT, ""
    name = parsed.get("name")
    if not isinstance(name, str) or not name.strip():
        return TRANSIENT, ""
    return ACTIVE, name.strip()
```

Validate `max_workers >= 1`. Keep logging at debug for transport failures because offline operation is normal.

- [ ] **Step 4: Run module tests and Ruff**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_characters.py -q
uv run --extra dev ruff check wingman/evesettings/characters.py tests/test_evesettings_characters.py
uv run --extra dev ruff format --check wingman/evesettings/characters.py tests/test_evesettings_characters.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wingman/evesettings/characters.py tests/test_evesettings_characters.py
git commit -m "feat: classify deleted EVE characters"
```

---

### Task 3: Trusted Tranquility boundary

**Files:**
- Modify: `wingman/evesettings/tree.py`
- Test: `tests/test_evesettings_tree.py`

**Interfaces:**
- Produces: `is_tranquility_server(path) -> bool`, independent from display-oriented `_shard()`.
- Consumed later by: Profiles API state, resolver, and account identity endpoints.

- [ ] **Step 1: Write strict predicate tests**

```python
@pytest.mark.parametrize(
    "name",
    ["tranquility", "c_ccp_eve_tq_tranquility", "c_eve_sharedcache_tq_tranquility"],
)
def test_trusted_tranquility_server_names(name):
    assert tree.is_tranquility_server(Path("C:/EVE") / name) is True


@pytest.mark.parametrize(
    "name",
    [
        "fake_tranquility_other",
        "tranquility_backup",
        "mytranquilfolder",
        "server_singularity",
        "server_serenity",
    ],
)
def test_display_heuristics_do_not_authorize_tranquility_cleanup(name):
    assert tree.is_tranquility_server(Path("C:/EVE") / name) is False
```

Include mixed-case accepted examples because Windows paths are case-insensitive.

- [ ] **Step 2: Run and confirm missing-symbol failure**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_tree.py -k "trusted_tranquility or authorize_tranquility" -v
```

Expected: `AttributeError` for `is_tranquility_server`.

- [ ] **Step 3: Implement the conservative predicate**

```python
def is_tranquility_server(path) -> bool:
    name = os.path.normcase(Path(path).name).casefold()
    return name == "tranquility" or name.endswith("_tq_tranquility")
```

Keep `_shard()` unchanged; its substring matching still serves display/discovery compatibility.

- [ ] **Step 4: Run tree tests**

```bash
uv run --no-sync python -m pytest tests/test_evesettings_tree.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wingman/evesettings/tree.py tests/test_evesettings_tree.py
git commit -m "feat: add trusted Tranquility predicate"
```

---

### Task 4: Resolver coordination, filtering, and automatic cleanup

**Files:**
- Modify: `wingman/ui/api.py:20-45, 400-450, 4660-4815, 5060-5385`
- Test: `tests/test_api_evesettings.py`

**Interfaces:**
- Consumes: `evesettings_characters.resolve(ids)`, `tree.is_tranquility_server(path)`, `settings.update_section()`.
- Produces: process caches `_eve_deleted: set[tuple[str, int]]`, `_eve_identity_generation`, trusted-context filtering, automatic cleanup, and coalesced resolver behavior; `eve_settings_state()["account_identity_available"]`.

- [ ] **Step 1: Add state/filtering regression tests**

Create fixture helpers that mark IDs deleted without network calls. Assert:

```python
def test_confirmed_deleted_character_is_hidden_but_its_file_and_backup_remain(...):
    # Build trusted tq profile with core_char_20.dat and core_char_21.dat.
    api._eve_deleted.add(("tranquility", 21))
    state = api.eve_settings_state()
    assert [row["id"] for row in state["characters"]] == ["20"]
    assert (profile / "core_char_21.dat").exists()
    assert any(row["stem"] == "core_char_21" for row in state["backups"])


def test_unresolved_character_remains_visible(...):
    assert {row["id"] for row in api.eve_settings_state()["characters"]} == {
        "20",
        "21",
    }
```

Add tests that non-trusted or Singularity profiles expose
`account_identity_available=False`, retain character files, perform no cleanup,
and do not apply Tranquility account names.

- [ ] **Step 2: Add cleanup and failure tests**

Cover removal from every account list, dropping empty mappings, preserving
`account_names`, disk reload, write rollback, filtered pending payloads, and refusing a normal account edit when pending cleanup cannot save. Assert the EVE file and backup remain.

Use the existing blocking `update_section` test pattern around
`tests/test_api_evesettings.py:1094-1130` to prove a concurrent manual edit cannot be overwritten: the resolver must reread associations only after acquiring `_eve_mutation`.

- [ ] **Step 3: Add coordinator tests**

With controllable fake threads/events, prove:

- one worker runs at once;
- a second request sets one trailing pass;
- switching A→B while A runs eventually resolves B;
- stale A results cache remote facts but cannot clean/push B;
- B publishes cached facts newly applicable to B;
- active IDs are passed to `resolve()` again on a later route pass;
- deleted IDs are not fetched again;
- worker spawn/exception clears running state.

- [ ] **Step 4: Run tests and confirm failures**

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py -k "deleted or tranquility or resolver or cleanup" -v
```

Expected: failures because the cache, payload flag, filtering, cleanup, and coordinator do not exist.

- [ ] **Step 5: Implement trusted context and filtered state**

Add an API-local immutable context carrying canonical root/server/profile plus datasource. Derive `trusted` only when the selected server is in `found.servers` with display key `tranquility` **and** `tree.is_tranquility_server(found.server)`.

Add helpers:

```python
def _eve_deleted_ids(self, found) -> set[str]: ...
def _eve_account_identity_available(self, found) -> bool: ...
def _eve_prune_deleted_links_locked(self, deleted_ids: set[str]) -> bool: ...
```

Filter only payload construction and authorization; do not mutate `found.characters`. In non-trusted contexts, account identities use raw account IDs and the page payload disables identity management.

- [ ] **Step 6: Implement automatic cleanup under `_eve_mutation`**

The background resolver performs network checks first, then waits for `_eve_mutation`, re-discovers/revalidates context, rereads the current mapping, and calls `update_section` only when pruning changes it. Persist pending cleanup IDs after a write failure and retry them before later manual link edits. Log IDs only.

- [ ] **Step 7: Implement single-flight and trailing coalescing**

Add a short coordinator lock plus `_eve_resolve_running` and `_eve_resolve_pending`. `eve_settings_resolve_names()` claims running or sets pending. The worker's `finally` clears running atomically and starts at most one latest-context pass. Never recurse while holding the coordinator lock; decide `restart`, release, then spawn.

Merge active names into `_eve_names.names`; add confirmed deletions to `_eve_deleted`. Continue `/universe/names` for non-Tranquility and association-only IDs. Push once when facts newly affect the current context.

- [ ] **Step 8: Run focused API tests**

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py tests/test_evesettings_characters.py tests/test_evesettings_tree.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add wingman/ui/api.py tests/test_api_evesettings.py
git commit -m "feat: hide and clean deleted profile characters"
```

---

### Task 5: Race-safe identification generations

**Files:**
- Modify: `wingman/ui/api.py:420-430, 4667-4671, 5198-5353`
- Test: `tests/test_api_evesettings.py:1300-1670`

**Interfaces:**
- Produces: `_eve_identification_lock`, monotonic `_eve_identification_generation`, generation-bearing identification responses and deletion events.
- Consumed later by: `wingman/web/evesettings.js` stale-response guard.

- [ ] **Step 1: Write Python race tests**

Add deterministic event/barrier tests for:

- cancel between start/check work and publication;
- deletion invalidation during candidate publication;
- confirmation with a stale candidate generation;
- cancel while `_eve_mutation` is held;
- `onEveSettingsNames` carrying `identification_generation` and matching `deleted_candidate_ids`.

Expected response shape example:

```python
assert result == {
    "status": "candidate",
    "error": None,
    "account": result["account"],
    "characters": result["characters"],
    "identification_generation": 4,
}
```

- [ ] **Step 2: Run and confirm generation failures**

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py -k "generation or cancel.*mutation or deleted_candidate" -v
```

Expected: missing generation fields and stale state publication.

- [ ] **Step 3: Implement atomic generation state**

Add a dedicated `_eve_identification_lock`. Store candidate authorization with its generation. Start increments/claims a generation; start/check do I/O outside the state lock and compare-and-publish under it. Cancel increments and clears under only the state lock. Confirmation validates generation while reading candidate authorization. Resolver invalidation increments and clears under the state lock while cleanup owns `_eve_mutation`.

Never acquire `_eve_mutation` while holding `_eve_identification_lock`; this fixed ordering avoids deadlock. Return the generation on every identification response that the page processes.

- [ ] **Step 4: Run identification tests**

```bash
uv run --no-sync python -m pytest tests/test_api_evesettings.py -k "identification or deleted_candidate" -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wingman/ui/api.py tests/test_api_evesettings.py
git commit -m "fix: serialize profile identification state"
```

---

### Task 6: Page gating and stale-promise rejection

**Files:**
- Modify: `wingman/web/evesettings.js:20-40, 280-470, 960-1135, 1195-1240`
- Test: `tests/test_page_conventions.py` or a focused new lexical section in `tests/test_api_evesettings.py`
- Test/manual: `docs/smoke-checklist.md` only if the checklist lacks Profiles deletion/generation coverage

**Interfaces:**
- Consumes: `account_identity_available`, `identification_generation`, and `deleted_candidate_ids` from Python.
- Produces: hidden/disabled non-Tranquility identity management and stale identification-response rejection.

- [ ] **Step 1: Add lexical bridge/page tests**

Assert source contains:

- a retained `identificationGeneration` initialized to zero;
- generation update before deleted-candidate inspection in `onEveSettingsNames`;
- generation comparison before every `renderCandidate(result)` path;
- `account_identity_available` gating identity controls;
- no new bridge handler name.

Add a test that the existing handler remains in `WM.HANDLERS` and is registered once.

- [ ] **Step 2: Run and confirm lexical failures**

```bash
uv run --no-sync python -m pytest tests/test_bridge_contract.py tests/test_page_conventions.py -k "Eve or identification or handler" -v
```

Expected: new lexical assertions fail.

- [ ] **Step 3: Implement generation observation helper**

Use one helper from every identification promise callback:

```javascript
var identificationGeneration = 0;

function acceptIdentification(result) {
  var generation = result && result.identification_generation;
  if (typeof generation !== 'number') return false;
  if (generation < identificationGeneration) return false;
  identificationGeneration = generation;
  return true;
}
```

Call it before mutating local identity state. In `onEveSettingsNames(payload)`, update the retained generation first, then inspect `deleted_candidate_ids`; if they intersect the current candidate, clear local state, return to idle with the specified inline message, and refresh. Otherwise refresh normally.

Gate account identity controls from `state.account_identity_available`, not from path text in JavaScript.

- [ ] **Step 4: Run lexical and API tests**

```bash
uv run --no-sync python -m pytest tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_api_evesettings.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wingman/web/evesettings.js tests/test_page_conventions.py tests/test_api_evesettings.py docs/smoke-checklist.md
git commit -m "fix: reject stale profile identity responses"
```

---

### Task 7: Polish and full verification

**Files:**
- Review all changed files
- Update: `docs/profile-character-validity-design.md` or `docs/profile-character-validity-plan.md` only for implementation deviations discovered during execution

**Interfaces:** None; this task verifies the integrated behavior.

- [ ] **Step 1: Run `polish-core --fix` workflow**

Load the `polish-core` skill, review changes since `492b825`, apply only high-confidence fixes, and inspect every resulting diff. Do not accept scope expansion.

- [ ] **Step 2: Run the full automated gates**

```bash
uv run --no-sync python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Expected: all tests pass and both Ruff commands exit zero.

- [ ] **Step 3: Inspect final diff and invariants**

```bash
git diff 492b825 --check
git diff 492b825 --stat
git status --short
rg -n "DEBUG-" wingman tests
```

Confirm no EVE file deletion path was added, backups remain unfiltered, all new `Api` attributes are underscore-prefixed, no real OAuth credentials exist, and no debug instrumentation remains.

- [ ] **Step 4: Run the Windows Profiles smoke pass**

Follow the design's nine smoke cases using the two known deleted local IDs. Record actual results in the completion report; do not claim the UI is verified if this pass cannot be run.

- [ ] **Step 5: Explain the completed change**

Load `change-explainer` and produce a reviewer-facing summary covering authoritative ESI evidence, trusted Tranquility boundary, automatic metadata cleanup, atomic settings publication, race handling, exact verification, and remaining operational risk.

- [ ] **Step 6: Commit final documentation or polish changes**

```bash
git add -A
git commit -m "docs: record profile validity implementation"  # only if files remain
```
