# Task 1 implementation report

## RED recorded before production code

Started at Wingman `146313b6` in the assigned linked worktree only. Read the task,
global constraints, AGENTS, approved sibling design and the exact deployed
Wanderer `2ddff24516c27ecde7b175991fcd74d608a35932` documentation, serializer,
controller, schema, confirmation store and fixture tests using `git show`.

Command:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py tests/test_wanderer_credentials.py --basetemp=/tmp/wanderer-task1 -q --tb=line
```

Result: **234 failed in 3.23s**, exit 1. Expected missing-feature failures:
`ModuleNotFoundError: No module named 'wingman.wanderer'` and the explicit
setuptools package assertion. No implementation existed when run. Full raw
session output: `/tmp/pi-bash-d501b146045ab23d.log` (ephemeral, not committed).

## Discovery / blind spots

- Deployed unavailable records have `online` false/null and *all* location/map
  fields null; `tracked` is always true. Hidden/unmapped fields cannot carry map
  names or map timestamps. Visible records carry a map timestamp. Enforce these
  jointly, not ten independent permissive field validators.
- Server revision is opaque; sorted records and confirmation-based age are part
  of the executing contract. Fixtures are synthetic reproductions, not live
  captures. The worker, not this task, owns 304 and immediate auth clearing.
- DPAPI must protect the binding and document identity/version together with
  the token. Reusing token-only EVE wrapping would leave editable plaintext
  binding metadata; reuse the lower-level `eveauth.dpapi` primitives instead.
- `atomicio.write_atomic` supplies same-directory replacement and cleanup, but
  not parent-directory fsync. Do not claim multi-document or power-loss atomicity.
- Strict local input policy: HTTPS with ASCII DNS/IP authority and conservative
  unescaped deployment path segments; one ASCII slug/UUID. Prefix and slug case
  remain significant; UUID/host case and default HTTPS port normalize. Ambiguous
  paths, controls and encoded separators are rejected rather than guessed.
- Exact names use NFC, outer trim and casefold only; no substring, accent folding
  or internal-whitespace collapse. Reject ambiguous normalized duplicates and
  unsafe single-line Unicode. No high-impact unresolved decision blocks Task 1.

## Implemented interfaces

`wingman.wanderer.model`:

```python
normalize_base_url(value: str) -> str
normalize_map_identifier(value: str) -> str
normalize_character_name(value: str) -> str
parse_snapshot(body: bytes, receipt_monotonic: float) -> Snapshot

@dataclass(frozen=True)
class LocationRecord:
    character_id: int
    character_name: str
    tracked: bool
    online: bool | None
    solar_system_id: int | None
    solar_system_name: str | None
    display_name: str | None
    map_system_visible: bool
    location_observed_at: datetime | None
    map_system_updated_at: datetime | None
    deadline_monotonic: float | None

    def display_at(self, now_monotonic: float) -> str | None: ...

@dataclass(frozen=True)
class Snapshot:
    records: tuple[LocationRecord, ...]
    observed_at: datetime
    revision: str
    receipt_monotonic: float
    by_name: Mapping[str, LocationRecord]  # derived, init=False, read-only proxy

    def record_for(self, character_name: str) -> LocationRecord | None: ...

class SnapshotError(ValueError):
    def __init__(self) -> None: ...
```

The three normalizers raise fixed `ValueError` text. Parsing raises only a fixed
`SnapshotError` for rejected candidates, with neither `__cause__` nor
`__context__` retaining external errors. Record/envelope timestamps are aware UTC
`datetime` values (strict calendar timestamps, Z or +00:00, at most six fractional
digits). Future location/map times are rejected; old locations expire immediately.
Unavailable records have `deadline_monotonic=None`. Display returns `None` to clear,
otherwise trimmed effective visible name or trimmed raw name. Callers should use
`parse_snapshot`, not construct unvalidated records from wire input themselves.

`Snapshot.by_name` is keyed by `normalize_character_name`; `record_for` accepts the
original local character name. No-match returns `None`; malformed lookup names
raise a fixed `ValueError`. IDs must be positive exact integers at most
9,007,199,254,740,991. Records must arrive sorted without duplicate IDs or normalized
names. Exact envelope keys and the exact deployed ten record keys are enforced;
JSON duplicate fields, non-integer numbers and non-finite numbers are rejected.

Model constants available for the next task:
`MAX_RESPONSE_BYTES=1_048_576`, `MAX_RECORDS=2000`,
`MAX_NAME_CODEPOINTS=255`, `MAX_NAME_BYTES=1024`, `MAX_BASE_URL_BYTES=2048`,
`MAX_MAP_BYTES=255`, `MAX_CONDITIONAL_BYTES=1024`, `FRESHNESS_SECONDS=15.0`,
`MAX_ID=9_007_199_254_740_991`. Revision text is bounded ASCII unreserved text, at
most 1,020 bytes to leave four bytes for the weak ETag wrapper. Treat revision as
opaque; the client should prefer the actual validated response ETag.

`wingman.wanderer.credentials`:

```python
class CredentialError(OSError): ...

validate_token(value: str) -> str

class CredentialStore:
    def __init__(
        self, path: Path | None = None, *,
        protect: Callable[[bytes], bytes] = dpapi.protect,
        unprotect: Callable[[bytes], bytes] = dpapi.unprotect,
    ) -> None: ...
    def load(self, base: str, map: str) -> str | None: ...
    def replace(self, base: str, map: str, token: str) -> None: ...
    def remove(self) -> None: ...
```

Default path: `paths.state_dir() / "wanderer_credentials.json"`. No `paths.py`,
ordinary settings, EVE token store, bridge or runtime wiring changes. The package
is registered in setuptools' explicit package list and imports cleanly on Linux.

The only plaintext outer document fields are `version: 1` and `protected` (base64
DPAPI ciphertext). The protected JSON contains exactly `version: 1`,
`purpose: "wingman.wanderer.credentials"`, canonical `base_url`, canonical
`map_identifier`, and `token`. Both documents reject additional/duplicate keys.
The file read is capped at 16 KiB plus one overflow-detection byte; ciphertext is
capped at 8 KiB, decrypted JSON at 4 KiB. `MAX_AUTHORIZATION_BYTES=512` includes
`Bearer `, so `validate_token` accepts 1–505 printable ASCII bytes excluding comma
and all whitespace/controls. Tokens are neither stripped nor interpreted.

`load` returns `None` only for a missing file or valid credential bound to another
base/map. Corruption, unsupported document version, decryption/read failure or
invalid arguments raise a fixed operation-specific `CredentialError`. `replace`
protects before atomic publication; failure does not replace the prior file or
retain an in-memory token. `remove` is idempotent for absence and reports failure
without changing acknowledged state. Underlying exception details are discarded
outside the exception handler, including hidden chaining context; no logging is
performed. The controller must serialize these methods and maintain any cached
token under its own connection-generation lock. `load` is Python-only: **never
return its token to the page**.

## GREEN and focused verification

Initial implementation, same command as RED: **234 passed in 3.16s**, exit 0.

Self-review strengthened duplicate-field coverage with otherwise-valid envelopes
and protected documents. Mutation exercise (in memory only, no source mutation):

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -c 'from wingman.wanderer import model, credentials; model._unique_object = dict; credentials._object = dict; import pytest; raise SystemExit(pytest.main(["tests/test_wanderer_model.py", "tests/test_wanderer_credentials.py", "-k", "duplicate_fields", "--basetemp=/tmp/wanderer-task1", "-q", "--tb=short"]))'
```

Expected RED: **3 failed, 234 deselected in 1.89s**, all `DID NOT RAISE`. With the
production duplicate guards unchanged, focused GREEN was **237 passed in 3.15s**:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py tests/test_wanderer_credentials.py --basetemp=/tmp/wanderer-task1 -q -rs
```

Final verification after all Python/test edits:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff check wingman/wanderer tests/test_wanderer_model.py tests/test_wanderer_credentials.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff format --check wingman/wanderer tests/test_wanderer_model.py tests/test_wanderer_credentials.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py tests/test_wanderer_credentials.py tests/test_packaging_completeness.py tests/test_eveskills_tokens.py tests/test_atomicio.py --basetemp=/tmp/wanderer-task1 -q -rs
git diff --check
```

Results: Ruff **all checks passed**, **5 files already formatted**;
pytest **360 passed in 7.72s**, no skips; diff whitespace check exit 0.
The extra 123 tests cover existing packaging completeness and the reused crypto /
atomic-I/O neighborhood. Full suite remains parent-owned at the final gate.

## Scoped self-review / decisions / remaining concerns

Reviewed the complete task diff, including fixtures and tests. Local scoped polish
applied Ruff formatting, documented the deliberately non-logging broad exception
boundary, and strengthened duplicate-key tests; no subagents or broad review loop.
Only Task 1 files and this report changed. No plan/progress edits, dependencies,
version bump, HTTP requests, worker/controller/preview/page changes or location
persistence. No placeholders remain in the implementation.

No known blocking Task 1 findings. Conservative URL/path/slug and safe-label
validation can reject unusual deployment prefixes or source names; this is
intentional fail-closed behavior and is documented above, not an unverified claim
of compatibility with every theoretical server input. Atomic replace uses the
existing repository durability guarantees, not cross-document atomicity. Binding
changes leave the old protected credential unusable for the new binding; only
explicit replacement binds a new credential.

Windows DPAPI itself, a frozen build and live Wanderer/EVE behavior were **NOT
RUN** here. Tests replace only the platform crypto seam with authenticated Fernet
operations and exercise real filesystem/atomic I/O; they do not prove Windows
account behavior. No deployed URL/token was supplied. The later worker task must
retain original deadlines on 304 and clear cached records immediately on auth
errors. No historical companion-preview dependency was introduced.

Reviewer focus: strict state coherence, immutable monotonic deadlines, exact-name
matching, and protecting every credential-binding field together. Integration
checks for the next tasks:

1. Why must a 304 retain the same `LocationRecord.deadline_monotonic`?
2. Which record fields distinguish a hidden location from an unavailable one?
3. Which canonicalization changes preserve a binding, and which require a new token?
4. How does the controller distinguish missing credentials from unreadable storage?
5. Which credential-store result must never be passed through a bridge response?
