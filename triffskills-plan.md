# EVE skill plan readiness — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth top-level route to Wingman that shows, per EVE skill plan, which of your characters can fly it — backed by EVE SSO and read-only ESI.

**Architecture:** A self-contained `obs_youtube_uploader/eveskills/` package. Twelve of its thirteen modules are pure or filesystem-only and run in CI on Linux; only `dpapi.py` is Windows-only. A single `SkillsController` owns the roster in memory, is the only writer of the state document, and runs auth and refresh on worker threads. The bridge grows nine thin façade methods that delegate to it. The page is one vanilla-JS IIFE.

**Tech Stack:** Python 3.11+, stdlib `urllib` for HTTP, `cryptography` (already installed transitively via `google-auth`) for RS256, pywebview 6.2.1, vanilla ES5-flavoured JS, pytest.

**Spec:** `triffskills-design.md`

## Global Constraints

- **Python** `>=3.11`. **No new runtime dependency** may be added to `pyproject.toml`'s `dependencies` except `cryptography`, which is already installed transitively (`uv.lock:382-387`) and is declared explicitly by Task 1.
- **HTTP is stdlib `urllib.request`.** This repo has no `requests`. Follow `discord.py`'s injectable `transport=` seam (`discord.py:196-197,224`).
- **No linter, formatter, or type checker exists in this repo.** CI runs version consistency, a WebView2 predicate check, and `python -m pytest tests/ -v`. Style is enforced by convention and comment density.
- **Comment density is a real convention.** Document *why* at the exact line, including the failure mode observed and what it cost. This is the most visible house style in the repo.
- **Every collaborator is keyword-only injectable with a production default** — transports, clocks, sleeps, thread spawners, crypt callables. That is what keeps the suite headless.
- **Tests run headless on Linux.** No webview, no display, no network, no real sleeps. `tmp_path` for filesystem state.
- **Test docstrings carry the reasoning** and are the primary regression record.
- **ESI scopes are exactly** `esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`. Read-only. Nothing writes to ESI.
- **Status strings cross the bridge as names**, never integers: `Ready | Training | Locked | Missing | Unknown | Unscored` and `Active | TrainedInactive | Queued | Missing | Unknown`.
- **Bridge payload keys are `snake_case`**, matching `webhook_status` and `video_id`.
- **Bridge reads return; mutations return `True` and push** — including no-op paths, because `WM.send` resolves to `null` on a bridge failure and the page cannot otherwise tell the two apart.
- **`Api` exposes methods only.** Every non-method attribute is underscore-prefixed; `tests/test_api.py:114` asserts it.
- **All comparisons on skill names, plan names, and filenames are case-insensitive.**

---

## File structure

### New package `obs_youtube_uploader/eveskills/`

| Module | Responsibility | Task |
|---|---|---|
| `__init__.py` | Package docstring only | 1 |
| `application.py` | Client id, redirect, user agent, scopes, endpoints | 1 |
| `plans.py` | Plan `.txt` grammar → requirements + diagnostics | 2 |
| `evaluator.py` | Requirement states, plan readiness, ETA | 3 |
| `planstore.py` | Plans folder listing, reading, name validation | 4 |
| `state.py` | Roster model, tolerant normalise, load/save, `.bak` | 5 |
| `dpapi.py` | `CryptProtectData` / `CryptUnprotectData` (Windows) | 6 |
| `tokens.py` | Refresh-token wrap/unwrap | 6 |
| `esi.py` | Path hardening, retries, backoff, ETags | 7 |
| `skillids.py` | Skill name → type id cache and resolution | 8 |
| `jwt.py` | Claim validation + RS256 via `cryptography` | 9 |
| `loopback.py` | OAuth callback listener, strict parser | 10 |
| `sso.py` | PKCE, authorize URL, code exchange, refresh | 11 |
| `controller.py` | Orchestration, locking, worker threads, payloads | 12–14 |

### Modified

| File | Change | Task |
|---|---|---|
| `pyproject.toml` | `packages` entry; declare `cryptography` | 1 |
| `obs_youtube_uploader/paths.py` | Three zero-arg path helpers | 1 |
| `obs_youtube_uploader/ui/api.py` | Nine façade methods under a new banner | 15 |
| `obs_youtube_uploader/__main__.py` | `build_skills_controller`, wiring, shutdown | 15 |
| `obs_youtube_uploader/web/index.html` | Nav button, route div, script tag | 16 |
| `obs_youtube_uploader/web/app.js` | Route map, peer list, `WM.HANDLERS` | 16 |
| `obs_youtube_uploader/web/skills.js` | The whole page module (new) | 16–17 |
| `obs_youtube_uploader/web/style.css` | Two-pane workspace layout | 17 |
| `.github/workflows/build.yml` | `skills.js` bundled-asset assertion | 16 |
| `.github/workflows/release.yml` | Same assertion, mirrored | 16 |
| `docs/smoke-checklist.md` | Items the suite cannot cover | 18 |

---

## Interface contract

**This section is normative.** Every task implements against these exact
signatures. A task's implementer sees only their own task, so anything a
neighbouring task consumes appears here verbatim. Where a task's `Produces`
block repeats one of these, the two must agree exactly.

Dates are `datetime` objects with `tzinfo=timezone.utc` **inside** the
package. Conversion to ISO strings happens only in `controller.py`, at the
bridge boundary.

### `paths.py` — the three new helpers

Zero-arg, returning `Path`, never module constants — `paths.py`'s own rule.
Named after their file stems, which is the dominant convention there
(`settings.json` → `settings_file()`). The `engine_*` group is named after its
subsystem instead, because those four files have unrelated names; ours share a
stem, so stem-naming works cleanly here.

```python
def eve_skills_file() -> Path         # state_dir() / "eve_skills.json"
def eve_skills_cache_file() -> Path   # state_dir() / "eve_skills_cache.json"
def skill_plans_dir() -> Path         # state_dir() / "skill_plans"
```

### `application.py`
```python
CLIENT_ID: str          # the registered EVE application id
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 51779
REDIRECT_PATH = "/callback/"
REDIRECT_URI = "http://127.0.0.1:51779/callback/"
SCOPES: tuple[str, ...] = ("esi-skills.read_skills.v1",
                           "esi-skills.read_skillqueue.v1")
USER_AGENT: str         # f"FlyGD-Wingman/{__version__} (+{SOURCE_URL})"

SSO_AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize"
SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"
SSO_METADATA = "https://login.eveonline.com/.well-known/oauth-authorization-server"
SSO_HOST = "login.eveonline.com"
ACCEPTED_ISSUERS: frozenset[str]

ESI_BASE = "https://esi.evetech.net"
ESI_HOST = "esi.evetech.net"
ESI_COMPATIBILITY_DATE = "2026-08-12"

def is_configured() -> bool     # False when CLIENT_ID is the placeholder
```

### `plans.py`

```python
MAX_CONTENT_CHARS = 512 * 1024
MAX_LINES = 5_000
MAX_LINE_CHARS = 512
MAX_REQUIREMENTS = 2_000
MAX_SKILL_NAME_CHARS = 200

@dataclass(frozen=True)
class Requirement:
    skill_name: str
    level: int              # 1..5

@dataclass(frozen=True)
class Diagnostic:
    line: int               # 1-based; 0 for whole-file diagnostics
    message: str

@dataclass(frozen=True)
class ParseResult:
    requirements: tuple[Requirement, ...]   # () when not ok
    diagnostics: tuple[Diagnostic, ...]
    @property
    def ok(self) -> bool                    # not diagnostics

def parse(contents: str) -> ParseResult
```

**A file yielding no requirements is itself a diagnostic:**
`Diagnostic(0, "Plan contains no skill requirements.")`, emitted when there
are zero requirements AND no other diagnostic (`SkillPlanParser.cs:112-114`).
It catches an empty file and, less obviously, one of only blank lines and `#`
comments — which parses cleanly and produces nothing. Without it such a file
is a *valid* plan with zero requirements: `list_plans` lists it, the rail
shows a `0/N` ratio, and `compact_status([])` returns `Unknown`, so every
character reads Unknown with nothing explaining why.

**Consequence for the cap tests:** any test building content from comment
lines alone is a zero-requirement plan and must include at least one real
requirement line, or it asserts the wrong thing.

### `evaluator.py`

```python
# RequirementState values
ACTIVE = "Active"
TRAINED_INACTIVE = "TrainedInactive"
QUEUED = "Queued"
MISSING = "Missing"
UNKNOWN = "Unknown"

# PlanReadiness values
READY = "Ready"
TRAINING = "Training"
LOCKED = "Locked"
READINESS_MISSING = "Missing"
READINESS_UNKNOWN = "Unknown"
UNSCORED = "Unscored"

READINESS_ORDER: tuple[str, ...] = (
    READY, TRAINING, LOCKED, READINESS_MISSING, READINESS_UNKNOWN, UNSCORED)

@dataclass(frozen=True)
class QueueEntry:
    skill_id: int
    finished_level: int         # 1..5
    start_date: datetime | None
    finish_date: datetime | None
    queue_position: int

@dataclass(frozen=True)
class RequirementAnalysis:
    skill_name: str
    required_level: int
    active_level: int | None
    trained_level: int | None
    state: str
    queued_finish_utc: datetime | None
    queue_timing_unknown: bool

@dataclass(frozen=True)
class PlanAnalysis:
    readiness: str
    estimated_finish_utc: datetime | None
    queue_timing_unknown: bool
    requirements: tuple[RequirementAnalysis, ...]

    @property
    def active_count(self) -> int
    @property
    def trained_inactive_count(self) -> int
    @property
    def queued_count(self) -> int
    @property
    def missing_count(self) -> int
    @property
    def unknown_count(self) -> int

def compact_status(analyses: Sequence[RequirementAnalysis]) -> str
    # An EMPTY sequence returns READINESS_UNKNOWN, never READY
    # (SkillPlanEvaluator.cs:113). Without that guard a zero-requirement
    # plan reads as flyable -- the exact failure plans.py's own docstring
    # names: scoring a character Ready for a ship it cannot fly.

def evaluate(requirements: Sequence[Requirement],
             skill_ids: Mapping[str, int],      # case-insensitive lookup
             active_levels: Mapping[int, int],
             trained_levels: Mapping[int, int],
             queue: Sequence[QueueEntry],
             has_snapshot: bool) -> PlanAnalysis
```

### `planstore.py`

```python
MAX_PLAN_FILES = 200
MAX_PLAN_NAME_CHARS = 120

@dataclass(frozen=True)
class PlanFile:
    name: str                               # filename stem
    requirements: tuple[Requirement, ...]
    diagnostics: tuple[Diagnostic, ...]
    @property
    def ok(self) -> bool

def validate_plan_name(name: str) -> str    # "" when valid, else the reason
def list_plans(plans_dir: Path) -> tuple[list[PlanFile], list[str]]  # plans, warnings
def seed_starter_plan(plans_dir: Path) -> bool   # True if it wrote one
```

### `state.py`

```python
MAX_CHARACTERS = 50
STATE_VERSION = 1

@dataclass
class Character:
    character_id: int
    character_name: str = ""
    owner_hash: str = ""
    scopes: tuple[str, ...] = ()
    authenticated_utc: datetime | None = None
    fetched_utc: datetime | None = None
    active_levels: dict[int, int] = field(default_factory=dict)
    trained_levels: dict[int, int] = field(default_factory=dict)
    queue: tuple[QueueEntry, ...] = ()
    error: str = ""
    needs_reauth: bool = False
    refresh_token_blob: str = ""    # base64 DPAPI blob; "" when absent
    skills_etag: str = ""
    queue_etag: str = ""

    @property
    def has_snapshot(self) -> bool  # fetched_utc is not None
    @property
    def stale(self) -> bool         # has_snapshot and bool(error)

@dataclass
class SkillsState:
    characters: list[Character] = field(default_factory=list)
    selected_plan_name: str = ""

    def find(self, character_id: int) -> Character | None
    def upsert(self, character: Character) -> None
    def remove(self, character_id: int) -> bool

def to_dict(state: SkillsState) -> dict
def from_dict(raw: object) -> SkillsState          # tolerant; never raises
def load(path: Path) -> tuple[SkillsState, list[str]]   # state, warnings
def save(state: SkillsState, path: Path) -> None        # atomic, writes .bak
```

### `dpapi.py` / `tokens.py`

```python
# dpapi.py — Windows only
def protect(data: bytes) -> bytes
def unprotect(blob: bytes) -> bytes
def available() -> bool         # False off Windows

# tokens.py
def wrap(token: str, *, protect=dpapi.protect) -> str      # base64 text
def unwrap(blob: str, *, unprotect=dpapi.unprotect) -> str | None   # None if undecryptable
```

### `esi.py`

```python
MAX_ATTEMPTS = 3
MAX_ERROR_BODY_BYTES = 8192
MAX_SUCCESS_BODY_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = frozenset({408, 420, 429, 500, 502, 503, 504})
TIMEOUT_S = 20.0

@dataclass(frozen=True)
class EsiResponse:
    status: int
    data: object | None
    error: str
    etag: str
    method: str
    path: str

    @property
    def ok(self) -> bool            # 200 <= status < 300
    @property
    def not_modified(self) -> bool  # status == 304

def validate_path(path: str) -> str     # returns path, raises ValueError

class EsiClient:
    def __init__(self, *, user_agent: str,
                 transport=_default_transport,
                 sleep=time.sleep) -> None
    def get(self, path: str, *, token: str | None = None,
            etag: str | None = None) -> EsiResponse
    def post(self, path: str, body: object, *,
             token: str | None = None) -> EsiResponse
```

### `skillids.py`

```python
SKILL_CATEGORY_ID = 16
BATCH_SIZE = 500
MAX_ENTRIES = 20_000
CACHE_VERSION = 1
RESOLVE_WORKERS = 4

class SkillIdCache:
    def __init__(self, mapping: Mapping[str, int] | None = None) -> None
    def get(self, name: str) -> int | None      # case-insensitive
    def type_ids(self) -> dict[str, int]        # case-insensitive mapping
    def unresolved(self, names: Iterable[str]) -> list[str]
    def merge(self, entries: Mapping[str, int]) -> int   # count added

def load(path: Path) -> tuple[SkillIdCache, list[str]]
def save(cache: SkillIdCache, path: Path) -> None
def resolve(cache: SkillIdCache, names: Sequence[str], client: EsiClient, *,
            max_workers: int = RESOLVE_WORKERS) -> dict[str, str]
    # returns name -> failure reason for names that did NOT resolve
```

### `jwt.py`

```python
CLOCK_SKEW_S = 120
JWKS_TTL_S = 300

@dataclass(frozen=True)
class EveIdentity:
    character_id: int
    name: str
    owner_hash: str             # "" when the claim is absent
    scopes: frozenset[str]

class JwtError(Exception): ...

class SigningKeySource:
    def __init__(self, *, transport=..., now=..., ttl_s: int = JWKS_TTL_S)
    def keys(self, *, force: bool = False) -> dict[str, object]
        # kid -> cryptography RSAPublicKey; RSA signing keys only

def validate(token: str, *, client_id: str,
             required_scopes: Iterable[str],
             key_source: SigningKeySource,
             now: datetime | None = None,
             skew_s: int = CLOCK_SKEW_S) -> EveIdentity
```

### `loopback.py`

```python
CONNECTION_TIMEOUT_S = 10.0
AUTH_TIMEOUT_S = 300.0
MAX_LINE_BYTES = 8192
MAX_HEADER_BYTES = 32 * 1024

@dataclass(frozen=True)
class Callback:
    code: str
    error: str

class CallbackTimeout(Exception): ...
class CallbackCancelled(Exception): ...

def parse_request(raw: bytes, *, expected_host: str,
                  expected_path: str) -> dict[str, str]
    # returns the query mapping; raises ValueError on any violation

class LoopbackListener:
    def __init__(self, *, host: str, port: int, path: str) -> None
    def __enter__(self) -> "LoopbackListener"
    def __exit__(self, *exc) -> None
    def wait(self, expected_state: str, *,
             timeout_s: float = AUTH_TIMEOUT_S) -> Callback
    def cancel(self) -> None
```

### `sso.py`

```python
@dataclass(frozen=True)
class Pkce:
    state: str
    verifier: str
    challenge: str

@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int

class OAuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None
    status: int
    code: str
    @property
    def definitive(self) -> bool
        # code in {"invalid_grant", "identity_mismatch", "owner_changed"}

def generate_pkce(*, randbytes=os.urandom) -> Pkce
def authorize_url(pkce: Pkce) -> str
def exchange_code(code: str, verifier: str, *, transport=...) -> TokenSet
def refresh_token(token: str, *, transport=...) -> TokenSet
```

### `controller.py`

```python
class SkillsController:
    def __init__(self, *,
                 state_path: Path,
                 cache_path: Path,
                 plans_dir: Path,
                 push,                  # (handler: str, payload: dict) -> None
                 alert,                 # (kind, title, body) -> None
                 client: EsiClient | None = None,
                 key_source=None,
                 sso=None,               # the sso module; injected for tests
                 listener_factory=None,  # () -> LoopbackListener
                 validate_token=None,    # jwt.validate, injected for tests
                 spawn=threading.Thread,
                 open_folder=None,
                 launch_browser=webbrowser.open,
                 now=...) -> None

    # reads
    def state_payload(self) -> dict
    def character_detail(self, character_id: int, plan_name: str) -> dict

    # mutations
    def authenticate(self) -> None
    def cancel_auth(self) -> None
    def forget(self, character_id: int) -> bool
    def refresh_characters(self) -> None
    def reload_plans(self) -> None
    def open_plans_folder(self) -> None
    def select_plan(self, plan_name: str) -> bool

    def shutdown(self) -> None      # never raises
```

**`sso`, `listener_factory`, and `validate_token` are what make the auth tests
headless** — no network, no sockets, no browser. They are ordinary injectable
seams under the same rule as every other collaborator, not drift from this
contract.

**The controller is built from `Api`, not from `AppState`.** It needs `push`
and `alert`, which are bound methods of `Api`; `AppState` has neither. So
`build_skills_controller(api)` takes the `Api` object, and `api._skills` is
assigned afterwards — the same two-step shape `ui/window.py:create()` uses to
assign `api._window` after `create_window()`, and for the same reason: the
thing being assigned does not exist until the thing it is assigned to has been
constructed. It follows `build_preview_host`'s error posture exactly (lazy
imports inside the function, whole body wrapped in
`except Exception: logger.exception(...); return None`).

**`Api` gains a tenth public method, `shutdown_skills()`.** The nine façade
methods above are the page's surface; this one is `main()`-only lifecycle,
exactly as `shutdown_previews()` is, and like it must never raise.

`push` is called with `("onSkills", payload)` and
`("onSkillsProgress", payload)`. `state_payload()` shape:

```python
{
  "auth_configured": bool,
  "auth_in_progress": bool,
  "refresh_in_flight": bool,
  "selected_plan_name": str,
  "plans": [{"name": str, "requirement_count": int, "ready_count": int}],
  "characters": [{
      "character_id": int,
      "character_name": str,
      "fetched_utc": str,       # ISO 8601, "" when never fetched
      "error": str,
      "needs_reauth": bool,
      "stale": bool,
      "readiness": str,         # for selected_plan_name; "Unscored" if none
      "estimated_finish_utc": str,
      "queue_timing_unknown": bool,
      "active_count": int, "trained_inactive_count": int,
      "queued_count": int, "missing_count": int, "unknown_count": int,
  }],
  "plan_issues": [{"file_name": str, "message": str,
                   "diagnostics": [{"line": int, "message": str}]}],
  "warnings": [str],
  "plans_updated_utc": str,
}
```

**`ready_count` is computed in Python, for every plan, on every state build —
and it has to be.** The `characters[]` array carries `readiness` for the
**selected plan only**, so the page has no way to derive a numerator for any
other plan; without `ready_count` the rail could show a ratio for the selected
plan and nothing for the rest. The page supplies only the denominator, which
is `characters.length`, giving the rail its `5/40`.

This means every character is evaluated against every plan on every state
build, which is deliberate and bounded: forty characters by seven plans by
forty requirements is about eleven thousand dictionary lookups, well under a
millisecond. TriffView reached the same place by shipping a full
character-by-plan matrix to the page; aggregating to a count in Python sends
two orders of magnitude less over the bridge for the one number the rail
actually renders.

`character_detail()` shape:

```python
{
  "ok": bool, "message": str,
  "character_id": int, "plan_name": str,
  "readiness": str,
  "estimated_finish_utc": str,
  "queue_timing_unknown": bool,
  "requirements": [{"skill_name": str, "required_level": int,
                    "active_level": int, "trained_level": int,
                    "state": str, "queued_finish_utc": str,
                    "queue_timing_unknown": bool}],
}
```

`onSkillsProgress` shape:

```python
{"character_id": int, "character_name": str,
 "completed": int, "total": int, "error": str}
```

---
### Task 1: Package skeleton, application constants, paths, packaging

**Files:**
- Create: `obs_youtube_uploader/eveskills/__init__.py`
- Create: `obs_youtube_uploader/eveskills/application.py`
- Modify: `obs_youtube_uploader/paths.py:37-40` (insert three helpers after `durations_file()`)
- Modify: `pyproject.toml:26-40` (declare `cryptography`)
- Modify: `pyproject.toml:64-68` (add the subpackage)
- Test: `tests/test_eveskills_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces:

```python
# obs_youtube_uploader/eveskills/application.py
CLIENT_ID: str          # the registered EVE application id
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 51779
REDIRECT_PATH = "/callback/"
REDIRECT_URI = "http://127.0.0.1:51779/callback/"
SCOPES: tuple[str, ...] = ("esi-skills.read_skills.v1",
                           "esi-skills.read_skillqueue.v1")
USER_AGENT: str         # f"FlyGD-Wingman/{__version__} (+{SOURCE_URL})"

SSO_AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize"
SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"
SSO_METADATA = "https://login.eveonline.com/.well-known/oauth-authorization-server"
SSO_HOST = "login.eveonline.com"
ACCEPTED_ISSUERS: frozenset[str]

ESI_BASE = "https://esi.evetech.net"
ESI_HOST = "esi.evetech.net"
ESI_COMPATIBILITY_DATE = "2026-08-12"

def is_configured() -> bool     # False when CLIENT_ID is the placeholder

# obs_youtube_uploader/paths.py
def eve_skills_file() -> Path     # state_dir() / "eve_skills.json"
def eve_skills_cache_file() -> Path     # state_dir() / "eve_skills_cache.json"
def skill_plans_dir() -> Path       # state_dir() / "skill_plans"
```

---

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_paths.py`:

```python
"""The three new state paths, and the guard that stops an unregistered
build from opening a browser at CCP with a placeholder client id.

paths.py's rule is that every state location is a zero-arg function
returning a Path, never a module constant -- monkeypatching state_dir()
is how the whole suite redirects state into tmp_path, and a constant
computed at import time would defeat it.
"""
from obs_youtube_uploader import paths
from obs_youtube_uploader.eveskills import application


def test_skill_state_files_live_together(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.eve_skills_file() == tmp_path / "eve_skills.json"
    assert paths.eve_skills_cache_file() == tmp_path / "eve_skills_cache.json"
    assert paths.skill_plans_dir() == tmp_path / "skill_plans"


def test_the_state_document_and_its_backup_are_siblings(monkeypatch, tmp_path):
    """The .bak tier lives beside the primary, so both must sit under
    state_dir() and not, say, in tmp_dir() where a cleanup sweep would
    take the only copy of every character's refresh token with it."""
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.eve_skills_file().parent == tmp_path


def test_the_placeholder_client_id_is_not_configured():
    """Nobody has registered the EVE application yet. is_configured() is
    what the controller checks before offering `Add character`: without
    it the button launches a browser at login.eveonline.com with a
    literal placeholder in the query string, and CCP's error page is not
    a recognisable diagnosis for 'this build was never registered'."""
    assert application.CLIENT_ID == "REPLACE_WITH_REGISTERED_EVE_CLIENT_ID"
    assert application.is_configured() is False


def test_a_registered_client_id_is_configured(monkeypatch):
    monkeypatch.setattr(application, "CLIENT_ID", "abc123def456")
    assert application.is_configured() is True


def test_the_redirect_uri_is_assembled_from_its_own_parts():
    """The URI is registered with CCP and must match byte for byte. The
    loopback listener validates Host and path against these same three
    constants, so a hand-written URI that drifted from them would fail
    the listener's own check rather than at the redirect."""
    assert application.REDIRECT_URI == "http://127.0.0.1:51779/callback/"
    assert application.REDIRECT_HOST == "127.0.0.1"
    assert application.REDIRECT_PORT == 51779
    assert application.REDIRECT_PATH == "/callback/"


def test_the_scopes_are_read_only_and_exactly_two():
    """Widening this tuple widens the consent screen every user sees.
    Nothing in this subsystem writes to ESI."""
    assert application.SCOPES == ("esi-skills.read_skills.v1",
                                  "esi-skills.read_skillqueue.v1")


def test_the_user_agent_carries_the_app_version_and_a_contact_url():
    """CCP asks third-party clients to identify themselves; an anonymous
    agent is what gets an application rate-limited without warning."""
    from obs_youtube_uploader import __version__
    assert application.USER_AGENT.startswith(f"FlyGD-Wingman/{__version__} ")
    assert "github.com/elboaf/FlyGD-Wingman" in application.USER_AGENT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/__init__.py`:

```python
"""EVE skill plan readiness: SSO, ESI reads, plan parsing, and scoring.

Twelve of the thirteen modules here are pure or filesystem-only and run
in CI on Linux; only dpapi.py is Windows-only. That split is deliberate
and matches preview/ -- the logic worth testing must not be trapped
behind an API that only exists on the build machine.
"""
```

Create `obs_youtube_uploader/eveskills/application.py`:

```python
"""EVE application identity: client id, redirect, scopes, endpoints.

The client id is a plain source constant, not a build-time injected
value, matching TriffView's EveApplication.cs:12. EVE's flow is PKCE
public-client -- client_id only, no secret -- so there is no
confidentiality argument for injection the way there is for the Google
desktop secret that release.yml:78-90 injects.

What that costs is recorded rather than glossed: a source checkout and a
release share one identity in CCP's dashboard, a fork inherits Wingman's
name on its users' consent screens unless it edits one line, and a
revocation for abuse from any of them takes every release together. If
any of that becomes real, the fix is to move this one constant to
build-time injection alongside the Google one. This module exists to be
that single point.
"""
from .. import __version__ as _version

# Not yet registered at developers.eveonline.com. is_configured() is
# what keeps a placeholder build from launching a browser at CCP with
# this literal in the query string -- the resulting error page is not a
# recognisable diagnosis for "this build was never registered".
_PLACEHOLDER_CLIENT_ID = "REPLACE_WITH_REGISTERED_EVE_CLIENT_ID"

CLIENT_ID = _PLACEHOLDER_CLIENT_ID

# The redirect is registered with CCP and must match byte for byte, so
# the parts and the assembled URI are kept in one place: loopback.py
# validates the request's Host and path against these same constants,
# and a hand-written URI that drifted would fail our own listener rather
# than the redirect.
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 51779
REDIRECT_PATH = "/callback/"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

# 51779 sits clear of TriffView's 51777 so both applications can be
# installed together. There is deliberately no fallback port: the URI is
# registered, so binding elsewhere would produce a redirect CCP refuses.
# A bind failure is reported plainly instead.

# Read-only, and exactly two. Widening this tuple widens the consent
# screen every user sees; nothing in this subsystem writes to ESI.
SCOPES = (
    "esi-skills.read_skills.v1",
    "esi-skills.read_skillqueue.v1",
)

# CCP asks third-party clients to identify themselves. Matches the shape
# discord.py:169-170 already sends, for the same reason: an anonymous
# agent is what gets an application throttled without warning.
USER_AGENT = (f"FlyGD-Wingman/{_version} "
              "(+https://github.com/elboaf/FlyGD-Wingman)")

SSO_AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize"
SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"
SSO_METADATA = (
    "https://login.eveonline.com/.well-known/oauth-authorization-server")
SSO_HOST = "login.eveonline.com"

# All three spellings CCP has issued, matching the source's own set
# (EveJwtValidator.cs:12-15): the bare authority, the full origin, and
# the full origin with a trailing slash. OAuth issuer identifiers
# routinely appear with and without the slash, and jwt.py compares `iss`
# against this set by equality and nothing else -- so a missing spelling
# is not a near-miss, it is a rejected token and a character that can
# never authenticate.
ACCEPTED_ISSUERS = frozenset({
    "login.eveonline.com",
    "https://login.eveonline.com",
    "https://login.eveonline.com/",
})

ESI_BASE = "https://esi.evetech.net"
ESI_HOST = "esi.evetech.net"
# Pinned, as in the source. A stale value degrades to whatever ESI
# decides rather than failing loudly, which is why it is a named
# constant a reader can find rather than a literal in a header dict.
ESI_COMPATIBILITY_DATE = "2026-08-12"


def is_configured() -> bool:
    """True once a real client id has replaced the placeholder."""
    return bool(CLIENT_ID) and CLIENT_ID != _PLACEHOLDER_CLIENT_ID
```

- [ ] **Step 4: Add the three path helpers**

Insert into `obs_youtube_uploader/paths.py` after `durations_file()` (line 37), before `log_dir()`:

```python
def eve_skills_file() -> Path:
    """Roster, snapshots, skill queue, ETags, and DPAPI-wrapped tokens.

    One document holds all of it, which is what makes forgetting a
    character a single atomic write. TriffView splits tokens into
    Windows Credential Manager and cannot update the two together; its
    own error strings record the cost ("Forget was rolled back because
    state could not be saved"). A .bak sibling is kept beside this file
    by the controller, because merging the tokens in moved the one
    non-rebuildable thing into a file that had no backup tier.
    """
    return state_dir() / "eve_skills.json"


def eve_skills_cache_file() -> Path:
    """Skill name -> type id. Deleting it costs a re-resolve over ESI."""
    return state_dir() / "eve_skills_cache.json"


def skill_plans_dir() -> Path:
    """User-owned folder of plan .txt files, plus a seeded starter.

    A directory rather than a section of a state document on purpose:
    the user edits these in Notepad, and `Open plans folder` is the
    whole authoring workflow.
    """
    return state_dir() / "skill_plans"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_paths.py -v`

- [ ] **Step 6: Declare the package and the dependency**

`pyproject.toml` — add to `packages` (line 67, after `"obs_youtube_uploader.preview",`):

```toml
    "obs_youtube_uploader.preview",
    "obs_youtube_uploader.eveskills",
]
```

`pyproject.toml` — add to `dependencies` (line 39, after the `pywebview` entry):

```toml
    "pywebview==6.2.1",
    # Already installed, transitively: google-auth 2.56.3 depends on it
    # unconditionally (uv.lock:382-387) and it is bundled into every
    # release today. Declaring it changes no resolution -- it is here so
    # that dropping or replacing the Google client libraries cannot
    # silently take the EVE SSO token verifier's RS256 dependency with
    # them. That failure would surface at authentication, not at install.
    "cryptography",
]
```

- [ ] **Step 7: Run the packaging test to verify the manifest**

Run: `python -m pytest tests/test_packaging_completeness.py tests/test_eveskills_paths.py -v`
Expected: PASS. Before the `packages` edit this fails with
`AssertionError: undeclared packages: ['obs_youtube_uploader.eveskills']`.

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/eveskills/__init__.py \
        obs_youtube_uploader/eveskills/application.py \
        obs_youtube_uploader/paths.py \
        pyproject.toml \
        tests/test_eveskills_paths.py
git commit -m "feat(eveskills): package skeleton, EVE application constants, state paths"
```

---

### Task 2: plans.py — the plan text parser

**Files:**
- Create: `obs_youtube_uploader/eveskills/plans.py`
- Test: `tests/test_eveskills_plans.py`

**Interfaces:**
- Consumes: nothing.
- Produces:

```python
MAX_CONTENT_CHARS = 512 * 1024
MAX_LINES = 5_000
MAX_LINE_CHARS = 512
MAX_REQUIREMENTS = 2_000
MAX_SKILL_NAME_CHARS = 200

@dataclass(frozen=True)
class Requirement:
    skill_name: str
    level: int              # 1..5

@dataclass(frozen=True)
class Diagnostic:
    line: int               # 1-based; 0 for whole-file diagnostics
    message: str

@dataclass(frozen=True)
class ParseResult:
    requirements: tuple[Requirement, ...]   # () when not ok
    diagnostics: tuple[Diagnostic, ...]
    @property
    def ok(self) -> bool                    # not diagnostics

def parse(contents: str) -> ParseResult
```

---

#### Cycle A — the grammar

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_plans.py`:

```python
"""The plan .txt grammar. Pure text in, requirements out -- runs in CI
on Linux with no filesystem, no network, and no EVE client.

Any diagnostic rejects the whole file. There is no partial-success mode,
because a plan that silently dropped a line would score a character
"Ready" for a ship it cannot fly, and the user has no way to notice.
"""
import pytest

from obs_youtube_uploader.eveskills import plans


def parse_one(text):
    """Parse *text*, assert it was accepted, and return its requirements."""
    result = plans.parse(text)
    assert result.ok, [(d.line, d.message) for d in result.diagnostics]
    return result.requirements


def test_roman_numerals_one_through_five():
    got = parse_one("Navigation I\nNavigation2 II\nNavigation3 III\n"
                    "Navigation4 IV\nNavigation5 V\n")
    assert [r.level for r in got] == [1, 2, 3, 4, 5]


def test_roman_numerals_are_case_insensitive():
    """Plans are hand-typed and pasted from forums; "navigation iv" is a
    perfectly ordinary way to write a line."""
    assert parse_one("Navigation iv\n")[0].level == 4
    assert parse_one("Navigation Iv\n")[0].level == 4


def test_arabic_digits_one_through_five():
    got = parse_one("Navigation 1\nHull Upgrades 5\n")
    assert [r.level for r in got] == [1, 5]


def test_the_line_splits_at_the_last_whitespace():
    """Splitting at the FIRST whitespace would name this skill "Caldari"
    and score every character Unknown against a skill that exists."""
    got = parse_one("Caldari Battlecruiser V\n")
    assert got[0].skill_name == "Caldari Battlecruiser"
    assert got[0].level == 5


def test_interior_whitespace_runs_survive_in_the_name():
    got = parse_one("Small  Hybrid Turret III\n")
    assert got[0].skill_name == "Small  Hybrid Turret"


def test_blank_lines_and_comments_are_skipped():
    got = parse_one("# Core Ship Skills\n\nNavigation IV\n   \n# trailing\n")
    assert [r.skill_name for r in got] == ["Navigation"]


def test_a_comment_marker_must_start_the_line():
    """"#" mid-line is not a comment introducer; a skill named with one
    would otherwise be truncated into a name that resolves to nothing."""
    got = parse_one("Sharpshooter #1 III\n")
    assert got[0].skill_name == "Sharpshooter #1"


def test_a_line_with_no_level_is_a_diagnostic():
    result = plans.parse("Navigation\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_a_level_outside_one_to_five_is_a_diagnostic():
    """EVE skills top out at V. A "6" is a typo, and accepting it would
    make every character permanently Missing with no explanation."""
    assert not plans.parse("Navigation 6\n").ok
    assert not plans.parse("Navigation 0\n").ok


def test_diagnostic_line_numbers_are_one_based():
    """They are rendered straight into the plan-issues disclosure, next
    to a file the user opens in Notepad, which counts from 1."""
    result = plans.parse("Navigation IV\nHull Upgrades nope\n")
    assert [d.line for d in result.diagnostics] == [2]


def test_an_empty_plan_parses_to_nothing_without_complaint():
    """An empty file is a plan with no requirements, not a broken one --
    the roster shows it Ready for everyone, which is truthful."""
    result = plans.parse("")
    assert result.ok and result.requirements == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_plans.py -v`
Expected: FAIL with `ImportError: cannot import name 'plans' from 'obs_youtube_uploader.eveskills'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/plans.py`:

```python
"""Plan .txt grammar. Pure: text in, requirements and diagnostics out.

Ported from TriffView's SkillPlanParser. Each line is a skill name,
whitespace, then a level as I-V or 1-5. Blank lines and # comments are
skipped, and the split is at the LAST whitespace so interior spaces stay
in the name.

Any diagnostic rejects the whole file. There is deliberately no
partial-success mode: a plan that silently dropped a malformed line
would score a character Ready for a ship it cannot fly, and nothing in
the UI would say so.
"""
from dataclasses import dataclass

MAX_CONTENT_CHARS = 512 * 1024
MAX_LINES = 5_000
MAX_LINE_CHARS = 512
MAX_REQUIREMENTS = 2_000
MAX_SKILL_NAME_CHARS = 200

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


@dataclass(frozen=True)
class Requirement:
    skill_name: str
    level: int


@dataclass(frozen=True)
class Diagnostic:
    line: int       # 1-based, matching the editor the user opens the file in
    message: str


@dataclass(frozen=True)
class ParseResult:
    requirements: tuple
    diagnostics: tuple

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def _parse_level(token: str):
    """Return 1..5, or None when *token* is not a legal level.

    NAIVE PORT, deliberately: this mirrors what a direct translation of
    the C# does, and Cycle B replaces it. The source guards with
    int.TryParse(token, NumberStyles.None) and Python's int() has no
    equivalent, so this version accepts things it must not.
    """
    roman = _ROMAN.get(token.upper())
    if roman is not None:
        return roman
    try:
        value = int(token)
    except ValueError:
        return None
    return value if 1 <= value <= 5 else None


def parse(contents: str) -> ParseResult:
    """Parse plan text into requirements, or into diagnostics only."""
    diagnostics = []
    requirements = []
    for number, raw in enumerate(contents.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # rsplit(None, 1) splits on the LAST run of whitespace, which is
        # what keeps "Caldari Battlecruiser" whole. Splitting at the
        # first would name the skill "Caldari".
        parts = line.rsplit(None, 1)
        if len(parts) < 2:
            diagnostics.append(Diagnostic(
                number, "Expected a skill name followed by a level."))
            continue
        name, token = parts
        level = _parse_level(token)
        if level is None:
            diagnostics.append(Diagnostic(
                number, f"'{token}' is not a level. Use I-V or 1-5."))
            continue
        requirements.append(Requirement(name, level))
    if diagnostics:
        # All or nothing. Returning the good lines beside the complaints
        # is the partial-success mode this parser refuses to have.
        return ParseResult((), tuple(diagnostics))
    return ParseResult(tuple(requirements), ())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_plans.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/plans.py tests/test_eveskills_plans.py
git commit -m "feat(eveskills): plan grammar - roman and arabic levels, last-whitespace split"
```

---

#### Cycle B — the three Python traps

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_plans.py`:

```python
def test_a_signed_level_is_rejected():
    """Python trap 1, which does not exist in the C#. The source parses
    with int.TryParse(token, NumberStyles.None), and NumberStyles.None
    forbids a leading sign. Python's int("+5") returns 5 and int("-5")
    returns -5, so a naive port accepts `Navigation +5` as level 5 and
    would reject `Navigation -5` only by the 1..5 range check -- an
    accident, not a rule."""
    assert not plans.parse("Navigation +5\n").ok
    assert not plans.parse("Navigation -5\n").ok


def test_an_underscore_separated_level_is_rejected():
    """Python trap 2. int("1_0") is 10 -- PEP 515 digit separators are a
    number format C# has no notion of. The range check catches 1_0, but
    int("_5") raises and int("5_") raises while int("1_0") does not, so
    the behaviour is inconsistent unless the token is screened first.
    `Navigation 1_0` must be a diagnostic, not a silent 10."""
    assert not plans.parse("Navigation 1_0\n").ok


def test_a_unicode_digit_level_is_rejected():
    """Python trap 3. "٥" is ARABIC-INDIC DIGIT FIVE. Its .isdigit()
    is True and int("٥") returns 5, so a naive port silently accepts
    `Navigation ٥` as level V. The guard is
    `token.isascii() and token.isdigit()` -- isascii() is what makes
    isdigit() mean "ASCII 0-9" and nothing wider."""
    assert not plans.parse("Navigation ٥\n").ok


def test_a_whitespace_padded_level_is_rejected():
    """The same NumberStyles.None clause: int(" 1 ") succeeds in Python.
    The line splitter strips before this is reached, so the guard is
    what protects _parse_level() from any future caller that does not."""
    assert plans._parse_level(" 1 ") is None


@pytest.mark.parametrize("token", ["+1", "-1", "1_0", "٥", " 1 ", "١"])
def test_the_level_guard_rejects_every_trap_token(token):
    assert plans._parse_level(token) is None


@pytest.mark.parametrize("token", ["1", "5", "I", "v", "IV"])
def test_the_level_guard_still_accepts_real_levels(token):
    assert plans._parse_level(token) in (1, 4, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_plans.py -v`
Expected: FAIL — `test_a_signed_level_is_rejected` asserts `not plans.parse("Navigation +5\n").ok` and the naive `int()` returns 5, so `.ok` is True and the assertion fails. `test_a_unicode_digit_level_is_rejected` fails the same way.

- [ ] **Step 3: Write minimal implementation**

Replace `_parse_level` in `obs_youtube_uploader/eveskills/plans.py`:

```python
def _parse_level(token: str):
    """Return 1..5, or None when *token* is not a legal level.

    Three Python traps here, none of which exist in the C# source. It
    parses with int.TryParse(token, NumberStyles.None), which rejects
    signs, whitespace, and separators outright:

      * int("+1") and int("-1") both succeed in Python.
      * int(" 1 ") succeeds -- surrounding whitespace is ignored.
      * int("1_0") is 10 -- PEP 515 digit separators.

    And a fourth, from the obvious screen for them: str.isdigit() is
    True for Unicode digits, so "٥".isdigit() passes and
    int("٥") returns 5. `token.isascii()` is what makes the
    isdigit() check mean "ASCII 0-9" and nothing wider.

    A naive port silently accepts `Navigation +5`, `Navigation 1_0`, and
    `Navigation ٥`. Every one of those is a typo the user wants told
    about, not reinterpreted.
    """
    roman = _ROMAN.get(token.upper())
    if roman is not None:
        return roman
    if not (token.isascii() and token.isdigit()):
        return None
    value = int(token)
    return value if 1 <= value <= 5 else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_plans.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/plans.py tests/test_eveskills_plans.py
git commit -m "fix(eveskills): reject signed, separated, and non-ASCII level tokens"
```

---

#### Cycle C — normalisation, control characters, dedupe

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_plans.py`:

```python
def test_skill_names_are_nfc_normalised():
    """A name pasted from a browser can arrive decomposed -- "e" plus
    U+0301 rather than U+00E9. Those are different strings, so an
    un-normalised name would miss the skill-id cache and score Unknown
    against a skill that resolves perfectly well when composed."""
    got = parse_one("Café Handling V\n")
    assert got[0].skill_name == "Café Handling"


def test_normalisation_happens_before_the_length_cap():
    """Decomposed text is longer than its composed form, so capping
    first would reject a name that is legal once normalised."""
    decomposed = "é" * 150
    assert len(decomposed) == 300          # 150 once composed
    got = parse_one(f"{decomposed} V\n")   # 150 once composed
    assert len(got[0].skill_name) == 150


def test_a_control_character_in_a_name_is_rejected():
    """A stray \\x07 or \\x1b comes from a mangled paste or a binary file
    renamed .txt. It cannot be part of a real skill name, and letting it
    through puts an escape sequence into a log line and a bridge
    payload."""
    assert not plans.parse("Navi\x07gation V\n").ok
    assert not plans.parse("Navi\x1bgation V\n").ok


def test_a_tab_inside_a_name_is_rejected():
    """TAB is a control character too. It also cannot survive the
    round trip: rsplit(None, 1) treats it as the separator, so a name
    containing one is already ambiguous before it gets here."""
    assert not plans.parse("Navi\tgation V\n").ok


def test_duplicates_fold_case_insensitively_keeping_the_maximum_level():
    """Every name comparison in this subsystem is case-insensitive, and
    the stricter line governs: a plan asking for III and V wants V."""
    got = parse_one("Navigation III\nnavigation V\n")
    assert len(got) == 1
    assert got[0].level == 5


def test_a_lower_duplicate_does_not_lower_the_level():
    got = parse_one("Navigation V\nNAVIGATION I\n")
    assert [(r.skill_name, r.level) for r in got] == [("Navigation", 5)]


def test_the_first_spelling_of_a_duplicate_wins():
    """The name is what the user reads in the expanded row, so keep the
    one they wrote first rather than letting a shouty duplicate rename
    it. The skill-id lookup is case-insensitive either way."""
    got = parse_one("Navigation III\nNAVIGATION V\n")
    assert got[0].skill_name == "Navigation"


def test_requirement_order_follows_first_appearance():
    """The expanded row lists requirements in plan order; re-sorting
    them would scramble a plan the user grouped on purpose."""
    got = parse_one("Hull Upgrades IV\nNavigation III\nHull Upgrades V\n")
    assert [r.skill_name for r in got] == ["Hull Upgrades", "Navigation"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_plans.py -v`
Expected: FAIL — `test_skill_names_are_nfc_normalised` fails with
`AssertionError: assert 'Café Handling' == 'Café Handling'`, and
`test_duplicates_fold_case_insensitively_keeping_the_maximum_level` fails with
`assert 2 == 1`.

- [ ] **Step 3: Write minimal implementation**

Add the import at the top of `obs_youtube_uploader/eveskills/plans.py`:

```python
import unicodedata
from dataclasses import dataclass
```

Replace the body of `parse()`:

```python
def parse(contents: str) -> ParseResult:
    """Parse plan text into requirements, or into diagnostics only."""
    diagnostics = []
    # Insertion-ordered and keyed on the casefolded name: the first
    # spelling wins, later duplicates only ever raise the level, and
    # dict ordering keeps the user's own grouping intact.
    ordered = {}
    for number, raw in enumerate(contents.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # rsplit(None, 1) splits on the LAST run of whitespace, which is
        # what keeps "Caldari Battlecruiser" whole. Splitting at the
        # first would name the skill "Caldari".
        parts = line.rsplit(None, 1)
        if len(parts) < 2:
            diagnostics.append(Diagnostic(
                number, "Expected a skill name followed by a level."))
            continue
        name, token = parts
        level = _parse_level(token)
        if level is None:
            diagnostics.append(Diagnostic(
                number, f"'{token}' is not a level. Use I-V or 1-5."))
            continue
        # Normalise BEFORE the length cap: decomposed text is longer
        # than its composed form, so capping first rejects names that
        # are perfectly legal once composed.
        name = unicodedata.normalize("NFC", name)
        if len(name) > MAX_SKILL_NAME_CHARS:
            diagnostics.append(Diagnostic(
                number, "Skill name is longer than "
                        f"{MAX_SKILL_NAME_CHARS} characters."))
            continue
        if any(unicodedata.category(ch) == "Cc" for ch in name):
            # A stray \x07 or \x1b comes from a mangled paste. It cannot
            # be part of a real skill name and must not reach a log line
            # or a bridge payload as an escape sequence.
            diagnostics.append(Diagnostic(
                number, "Skill name contains a control character."))
            continue
        key = name.casefold()
        previous = ordered.get(key)
        if previous is None:
            ordered[key] = Requirement(name, level)
        elif level > previous.level:
            # Keep the first spelling, raise the level. Two lines for one
            # skill mean the stricter one governs.
            ordered[key] = Requirement(previous.skill_name, level)
    if diagnostics:
        # All or nothing. Returning the good lines beside the complaints
        # is the partial-success mode this parser refuses to have.
        return ParseResult((), tuple(diagnostics))
    return ParseResult(tuple(ordered.values()), ())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_plans.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/plans.py tests/test_eveskills_plans.py
git commit -m "feat(eveskills): NFC-normalise plan names, reject control chars, fold duplicates"
```

---

#### Cycle D — every cap, and all-or-nothing

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_plans.py`:

```python
def test_content_over_512_kib_is_a_whole_file_diagnostic():
    """The cap is checked before splitlines() so a hostile or corrupt
    file cannot make the parser materialise a multi-megabyte list first.
    Whole-file diagnostics carry line 0, which the UI renders without a
    line number."""
    result = plans.parse("A" * (plans.MAX_CONTENT_CHARS + 1))
    assert not result.ok
    assert result.diagnostics[0].line == 0
    assert len(result.diagnostics) == 1


def test_content_exactly_at_the_content_cap_is_accepted():
    """Off-by-one on a cap is the classic way a legal file starts being
    rejected after a refactor."""
    filler = "# " + "A" * (plans.MAX_CONTENT_CHARS - 2)
    assert len(filler) == plans.MAX_CONTENT_CHARS
    assert plans.parse(filler).ok


def test_more_than_5000_lines_is_a_whole_file_diagnostic():
    result = plans.parse("Navigation I\n" * (plans.MAX_LINES + 1))
    assert not result.ok
    assert result.diagnostics[0].line == 0


def test_a_line_over_512_characters_is_a_diagnostic():
    """Measured on the RAW line, before stripping: the cap exists to
    bound work per line, and a line padded to a megabyte of spaces is
    exactly the input it is bounding."""
    result = plans.parse("N" * plans.MAX_LINE_CHARS + " V\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_a_line_exactly_at_the_line_cap_is_accepted():
    line = "N" * (plans.MAX_LINE_CHARS - 2) + " V"
    assert len(line) == plans.MAX_LINE_CHARS
    assert plans.parse(line).ok


def test_more_than_2000_requirements_is_a_diagnostic():
    text = "".join(f"Skill{n} I\n" for n in range(plans.MAX_REQUIREMENTS + 1))
    result = plans.parse(text)
    assert not result.ok
    assert any("2000" in d.message for d in result.diagnostics)


def test_exactly_2000_requirements_is_accepted():
    text = "".join(f"Skill{n} I\n" for n in range(plans.MAX_REQUIREMENTS))
    assert len(parse_one(text)) == plans.MAX_REQUIREMENTS


def test_the_requirement_cap_counts_distinct_skills_not_lines():
    """Duplicates fold before the count, so a plan that repeats one
    skill 3000 times is one requirement, not an overflow."""
    assert len(parse_one("Navigation I\n" * 3000)) == 1


def test_a_skill_name_over_200_characters_is_a_diagnostic():
    result = plans.parse("N" * (plans.MAX_SKILL_NAME_CHARS + 1) + " V\n")
    assert not result.ok
    assert result.diagnostics[0].line == 1


def test_one_bad_line_rejects_every_good_line_with_it():
    """The all-or-nothing rule, stated as its own test because it is the
    single behaviour most likely to be "helpfully" relaxed later. A plan
    the user believes has ten requirements must never silently evaluate
    with nine."""
    result = plans.parse("Navigation IV\nHull Upgrades nope\nMechanics V\n")
    assert not result.ok
    assert result.requirements == ()


def test_every_bad_line_is_reported_not_just_the_first():
    """Fixing a plan one diagnostic per save-and-reload cycle is why
    parsing continues past the first complaint."""
    result = plans.parse("A nope\nB 9\nC ٥\n")
    assert [d.line for d in result.diagnostics] == [1, 2, 3]


def test_non_text_content_is_a_whole_file_diagnostic():
    """list_plans() reads bytes off disk and decodes them, so `contents`
    should always be str -- but parse() is also fed from the clipboard
    import path in a deferred slice, and returning a diagnostic beats
    raising AttributeError into the bridge thread."""
    result = plans.parse(None)
    assert not result.ok and result.diagnostics[0].line == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_plans.py -v`
Expected: FAIL — `test_content_over_512_kib_is_a_whole_file_diagnostic` fails with
`assert True is False` (the oversized content parses as one comment-free
non-line and is accepted), and `test_non_text_content_is_a_whole_file_diagnostic`
fails with `AttributeError: 'NoneType' object has no attribute 'splitlines'`.

- [ ] **Step 3: Write minimal implementation**

Insert the whole-file guards at the top of `parse()` in
`obs_youtube_uploader/eveskills/plans.py`, and add the two per-line caps:

```python
def parse(contents: str) -> ParseResult:
    """Parse plan text into requirements, or into diagnostics only."""
    # Whole-file guards carry line 0, which the UI renders without a
    # line number. They come first so a corrupt or hostile file never
    # gets as far as materialising a multi-million entry line list.
    if not isinstance(contents, str):
        return ParseResult((), (Diagnostic(0, "Plan content is not text."),))
    if len(contents) > MAX_CONTENT_CHARS:
        return ParseResult((), (Diagnostic(
            0, "Plan is larger than "
               f"{MAX_CONTENT_CHARS} characters."),))
    lines = contents.splitlines()
    if len(lines) > MAX_LINES:
        return ParseResult((), (Diagnostic(
            0, f"Plan has more than {MAX_LINES} lines."),))

    diagnostics = []
    # Insertion-ordered and keyed on the casefolded name: the first
    # spelling wins, later duplicates only ever raise the level, and
    # dict ordering keeps the user's own grouping intact.
    ordered = {}
    for number, raw in enumerate(lines, start=1):
        # Measured on the RAW line, before stripping. The cap bounds the
        # work done per line, and a line padded to a megabyte of spaces
        # is exactly the input it is there to bound.
        if len(raw) > MAX_LINE_CHARS:
            diagnostics.append(Diagnostic(
                number, f"Line is longer than {MAX_LINE_CHARS} characters."))
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # rsplit(None, 1) splits on the LAST run of whitespace, which is
        # what keeps "Caldari Battlecruiser" whole. Splitting at the
        # first would name the skill "Caldari".
        parts = line.rsplit(None, 1)
        if len(parts) < 2:
            diagnostics.append(Diagnostic(
                number, "Expected a skill name followed by a level."))
            continue
        name, token = parts
        level = _parse_level(token)
        if level is None:
            diagnostics.append(Diagnostic(
                number, f"'{token}' is not a level. Use I-V or 1-5."))
            continue
        # Normalise BEFORE the length cap: decomposed text is longer
        # than its composed form, so capping first rejects names that
        # are perfectly legal once composed.
        name = unicodedata.normalize("NFC", name)
        if len(name) > MAX_SKILL_NAME_CHARS:
            diagnostics.append(Diagnostic(
                number, "Skill name is longer than "
                        f"{MAX_SKILL_NAME_CHARS} characters."))
            continue
        if any(unicodedata.category(ch) == "Cc" for ch in name):
            # A stray \x07 or \x1b comes from a mangled paste. It cannot
            # be part of a real skill name and must not reach a log line
            # or a bridge payload as an escape sequence.
            diagnostics.append(Diagnostic(
                number, "Skill name contains a control character."))
            continue
        key = name.casefold()
        previous = ordered.get(key)
        if previous is None:
            ordered[key] = Requirement(name, level)
        elif level > previous.level:
            # Keep the first spelling, raise the level. Two lines for one
            # skill mean the stricter one governs.
            ordered[key] = Requirement(previous.skill_name, level)
        # Counted on distinct skills, after folding: a plan repeating one
        # skill three thousand times is one requirement, not an overflow.
        if len(ordered) > MAX_REQUIREMENTS:
            diagnostics.append(Diagnostic(
                number,
                f"Plan has more than {MAX_REQUIREMENTS} requirements."))
            break
    if diagnostics:
        # All or nothing. Returning the good lines beside the complaints
        # is the partial-success mode this parser refuses to have.
        return ParseResult((), tuple(diagnostics))
    return ParseResult(tuple(ordered.values()), ())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_plans.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/plans.py tests/test_eveskills_plans.py
git commit -m "feat(eveskills): enforce every plan parser cap, reject the whole file on any diagnostic"
```

---

### Task 3: evaluator.py — readiness scoring

**Files:**
- Create: `obs_youtube_uploader/eveskills/evaluator.py`
- Test: `tests/test_eveskills_evaluator.py`

**Interfaces:**
- Consumes: `obs_youtube_uploader.eveskills.plans.Requirement(skill_name: str, level: int)` (Task 2).
- Produces:

```python
ACTIVE = "Active"
TRAINED_INACTIVE = "TrainedInactive"
QUEUED = "Queued"
MISSING = "Missing"
UNKNOWN = "Unknown"

READY = "Ready"
TRAINING = "Training"
LOCKED = "Locked"
READINESS_MISSING = "Missing"
READINESS_UNKNOWN = "Unknown"
UNSCORED = "Unscored"

READINESS_ORDER: tuple[str, ...] = (
    READY, TRAINING, LOCKED, READINESS_MISSING, READINESS_UNKNOWN, UNSCORED)

@dataclass(frozen=True)
class QueueEntry:
    skill_id: int
    finished_level: int         # 1..5
    start_date: datetime | None
    finish_date: datetime | None
    queue_position: int

@dataclass(frozen=True)
class RequirementAnalysis:
    skill_name: str
    required_level: int
    active_level: int | None
    trained_level: int | None
    state: str
    queued_finish_utc: datetime | None
    queue_timing_unknown: bool

@dataclass(frozen=True)
class PlanAnalysis:
    readiness: str
    estimated_finish_utc: datetime | None
    queue_timing_unknown: bool
    requirements: tuple[RequirementAnalysis, ...]

    @property
    def active_count(self) -> int
    @property
    def trained_inactive_count(self) -> int
    @property
    def queued_count(self) -> int
    @property
    def missing_count(self) -> int
    @property
    def unknown_count(self) -> int

def lowest_sufficient_entry(queue: Sequence[QueueEntry], skill_id: int,
                            required_level: int) -> QueueEntry | None
def compact_status(analyses: Sequence[RequirementAnalysis]) -> str
def evaluate(requirements: Sequence[Requirement],
             skill_ids: Mapping[str, int],      # case-insensitive lookup
             active_levels: Mapping[int, int],
             trained_levels: Mapping[int, int],
             queue: Sequence[QueueEntry],
             has_snapshot: bool) -> PlanAnalysis
```

---

#### Cycle A — the queue entry selector

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_evaluator.py`:

```python
"""Readiness scoring. Ported from TriffView's SkillPlanEvaluator.cs.

This is the semantic core of the feature: every UI decision downstream
reads one of these strings, and TriffView has no automated coverage of
it at all. That is the one posture this port deliberately does not
inherit.
"""
from datetime import datetime, timedelta, timezone

import pytest

from obs_youtube_uploader.eveskills import evaluator as ev
from obs_youtube_uploader.eveskills.plans import Requirement

T0 = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def entry(skill_id, finished_level, position, finish=None):
    return ev.QueueEntry(skill_id=skill_id, finished_level=finished_level,
                         start_date=T0, finish_date=finish,
                         queue_position=position)


def test_no_sufficient_entry_returns_none():
    queue = [entry(100, 2, 0)]
    assert ev.lowest_sufficient_entry(queue, 100, 4) is None


def test_entries_for_other_skills_are_ignored():
    queue = [entry(999, 5, 0)]
    assert ev.lowest_sufficient_entry(queue, 100, 1) is None


def test_the_lowest_sufficient_level_wins():
    """A plan asking for III is satisfied by the entry that finishes at
    III, not by the one that eventually reaches V."""
    queue = [entry(100, 5, 0), entry(100, 3, 1), entry(100, 4, 2)]
    assert ev.lowest_sufficient_entry(queue, 100, 3).finished_level == 3


def test_queue_position_breaks_a_level_tie():
    queue = [entry(100, 4, 7), entry(100, 4, 2)]
    assert ev.lowest_sufficient_entry(queue, 100, 4).queue_position == 2


def test_the_finish_date_never_decides_which_entry_is_chosen():
    """The C# original is named EarliestSufficientEntry
    (SkillPlanEvaluator.cs:121) and the name misleads: it never looks at
    a date. Here the V entry finishes days BEFORE the III entry, and the
    III entry still wins because it is the lowest sufficient level. The
    port keeps that behaviour and renames the function to say so."""
    queue = [entry(100, 5, 0, finish=T0 + timedelta(days=1)),
             entry(100, 3, 1, finish=T0 + timedelta(days=9))]
    chosen = ev.lowest_sufficient_entry(queue, 100, 3)
    assert chosen.finished_level == 3
    assert chosen.finish_date == T0 + timedelta(days=9)


def test_an_entry_with_no_finish_date_is_still_selectable():
    """A paused queue reports entries with null dates. They still say
    "this skill is queued to a sufficient level", which is the whole
    question this function answers."""
    queue = [entry(100, 4, 0, finish=None)]
    assert ev.lowest_sufficient_entry(queue, 100, 4) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`
Expected: FAIL with `ImportError: cannot import name 'evaluator' from 'obs_youtube_uploader.eveskills'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/evaluator.py`:

```python
"""Readiness scoring. Pure: mappings in, an analysis out.

Ported from TriffView's SkillPlanEvaluator.cs. Dates are timezone-aware
UTC datetimes throughout; conversion to ISO strings happens only at the
bridge boundary in controller.py, so nothing here formats anything.
"""
from dataclasses import dataclass
from datetime import datetime

# --- RequirementState ---------------------------------------------------
ACTIVE = "Active"
TRAINED_INACTIVE = "TrainedInactive"
QUEUED = "Queued"
MISSING = "Missing"
UNKNOWN = "Unknown"

# --- PlanReadiness ------------------------------------------------------
READY = "Ready"
TRAINING = "Training"
LOCKED = "Locked"
READINESS_MISSING = "Missing"
READINESS_UNKNOWN = "Unknown"
UNSCORED = "Unscored"

# Best first. compact_status() takes the worst present, so a plan is only
# Ready when every one of its requirements is.
READINESS_ORDER = (READY, TRAINING, LOCKED, READINESS_MISSING,
                   READINESS_UNKNOWN, UNSCORED)


@dataclass(frozen=True)
class QueueEntry:
    skill_id: int
    finished_level: int
    start_date: datetime | None
    finish_date: datetime | None
    queue_position: int


def lowest_sufficient_entry(queue, skill_id: int, required_level: int):
    """The queued entry that satisfies *required_level* at the lowest level.

    Sorts by lowest sufficient finished level, tie-broken by queue
    position, and NEVER by date. The C# original is called
    EarliestSufficientEntry (SkillPlanEvaluator.cs:121), which misleads:
    "earliest" reads as a date and no date is consulted. A plan asking
    for Navigation III takes the entry finishing at III even when a
    later-positioned entry finishing at V has an earlier finish date.

    The behaviour is kept because the row's ETA must describe the entry
    that actually satisfies the requirement, not the deepest one that
    happens to cover it.
    """
    candidates = [e for e in queue
                  if e.skill_id == skill_id
                  and e.finished_level >= required_level]
    if not candidates:
        return None
    return min(candidates, key=lambda e: (e.finished_level, e.queue_position))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/evaluator.py tests/test_eveskills_evaluator.py
git commit -m "feat(eveskills): lowest_sufficient_entry - level then queue position, never date"
```

---

#### Cycle B — per-requirement precedence

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_evaluator.py`:

```python
def evaluate(reqs, *, ids=None, active=None, trained=None, queue=(),
             snapshot=True):
    """Call evaluate() with the four mappings defaulted to empty."""
    return ev.evaluate(reqs,
                       skill_ids={"Navigation": 100} if ids is None else ids,
                       active_levels=active or {},
                       trained_levels=trained or {},
                       queue=queue,
                       has_snapshot=snapshot)


NAV3 = (Requirement("Navigation", 3),)


def test_active_at_or_above_the_required_level_is_active():
    got = evaluate(NAV3, active={100: 3})
    assert got.requirements[0].state == ev.ACTIVE


def test_active_below_the_required_level_is_not_active():
    got = evaluate(NAV3, active={100: 2})
    assert got.requirements[0].state == ev.MISSING


def test_active_outranks_trained():
    """First match wins, in the order Unknown, Active, TrainedInactive,
    Queued, Missing. A skill that is both usable and trained is usable."""
    got = evaluate(NAV3, active={100: 5}, trained={100: 5})
    assert got.requirements[0].state == ev.ACTIVE


def test_trained_but_inactive_is_trained_inactive():
    """This is the inactive-clone / lapsed-Omega case: the level is
    trained, the active level is lower, so the character owns the skill
    and cannot currently use it."""
    got = evaluate(NAV3, active={100: 1}, trained={100: 4})
    assert got.requirements[0].state == ev.TRAINED_INACTIVE


def test_trained_outranks_queued():
    got = evaluate(NAV3, trained={100: 3}, queue=[entry(100, 5, 0)])
    assert got.requirements[0].state == ev.TRAINED_INACTIVE


def test_a_sufficient_queue_entry_is_queued():
    got = evaluate(NAV3, queue=[entry(100, 3, 0, finish=T0)])
    analysis = got.requirements[0]
    assert analysis.state == ev.QUEUED
    assert analysis.queued_finish_utc == T0


def test_an_insufficient_queue_entry_leaves_it_missing():
    got = evaluate(NAV3, queue=[entry(100, 2, 0, finish=T0)])
    assert got.requirements[0].state == ev.MISSING


def test_a_queued_entry_with_no_finish_date_flags_timing_unknown():
    """A paused queue reports null dates. The requirement is genuinely
    queued -- the row must say Training, and must not invent an ETA."""
    got = evaluate(NAV3, queue=[entry(100, 3, 0, finish=None)])
    analysis = got.requirements[0]
    assert analysis.state == ev.QUEUED
    assert analysis.queued_finish_utc is None
    assert analysis.queue_timing_unknown is True


def test_nothing_at_all_is_missing():
    assert evaluate(NAV3).requirements[0].state == ev.MISSING


def test_an_unresolved_skill_name_is_unknown():
    """Unknown is about the PLAN, not the character: the name never
    resolved to a validated category-16 type id, so no character can be
    scored against it."""
    got = evaluate((Requirement("Nvigation", 3),), ids={})
    assert got.requirements[0].state == ev.UNKNOWN


def test_the_skill_id_lookup_is_case_insensitive():
    """Every name comparison in this subsystem is case-insensitive, and
    the cache is keyed on whatever spelling ESI returned, which is not
    necessarily the spelling in the plan file."""
    got = evaluate((Requirement("navigation", 3),),
                   ids={"NAVIGATION": 100}, active={100: 5})
    assert got.requirements[0].state == ev.ACTIVE


def test_the_analysis_reports_the_levels_it_scored_against():
    """The expanded row renders these next to the requirement, so a user
    can see "you have III, this needs IV" without a second request."""
    got = evaluate(NAV3, active={100: 1}, trained={100: 2})
    analysis = got.requirements[0]
    assert (analysis.active_level, analysis.trained_level) == (1, 2)
    assert (analysis.skill_name, analysis.required_level) == ("Navigation", 3)


def test_an_unresolved_name_reports_no_levels():
    got = evaluate((Requirement("Nvigation", 3),), ids={}, active={100: 5})
    analysis = got.requirements[0]
    assert analysis.active_level is None and analysis.trained_level is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.evaluator' has no attribute 'evaluate'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/evaluator.py`:

```python
@dataclass(frozen=True)
class RequirementAnalysis:
    skill_name: str
    required_level: int
    active_level: int | None
    trained_level: int | None
    state: str
    queued_finish_utc: datetime | None
    queue_timing_unknown: bool


@dataclass(frozen=True)
class PlanAnalysis:
    readiness: str
    estimated_finish_utc: datetime | None
    queue_timing_unknown: bool
    requirements: tuple


def evaluate(requirements, skill_ids, active_levels, trained_levels,
             queue, has_snapshot: bool) -> PlanAnalysis:
    """Score *requirements* for one character against one snapshot."""
    # Case-insensitive on the name, because the cache is keyed on the
    # spelling ESI returned and the plan file carries whatever the user
    # typed. Built once per plan rather than per requirement.
    lookup = {str(name).casefold(): int(type_id)
              for name, type_id in skill_ids.items()}

    analyses = []
    for req in requirements:
        skill_id = lookup.get(req.skill_name.casefold())
        if skill_id is None:
            # Unknown is about the plan, not the character. No levels are
            # reported because there is no id to have looked them up by.
            analyses.append(RequirementAnalysis(
                skill_name=req.skill_name, required_level=req.level,
                active_level=None, trained_level=None, state=UNKNOWN,
                queued_finish_utc=None, queue_timing_unknown=False))
            continue
        active = active_levels.get(skill_id)
        trained = trained_levels.get(skill_id)
        chosen = None
        # First match wins, in exactly this order. Active before trained
        # because a skill that is usable is usable; trained before queued
        # because owning it beats being on the way to owning it.
        if active is not None and active >= req.level:
            state = ACTIVE
        elif trained is not None and trained >= req.level:
            state = TRAINED_INACTIVE
        else:
            chosen = lowest_sufficient_entry(queue, skill_id, req.level)
            state = QUEUED if chosen is not None else MISSING
        analyses.append(RequirementAnalysis(
            skill_name=req.skill_name,
            required_level=req.level,
            active_level=active,
            trained_level=trained,
            state=state,
            queued_finish_utc=chosen.finish_date if chosen else None,
            # A paused queue reports null dates. The requirement is still
            # queued; what is unknown is when it lands.
            queue_timing_unknown=bool(chosen is not None
                                      and chosen.finish_date is None),
        ))
    return PlanAnalysis(READY, None, False, tuple(analyses))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/evaluator.py tests/test_eveskills_evaluator.py
git commit -m "feat(eveskills): per-requirement state precedence"
```

---

#### Cycle C — plan readiness, ETA, and counts

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_evaluator.py`:

```python
def test_all_active_is_ready():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 5, 200: 5})
    assert got.readiness == ev.READY


def test_one_queued_requirement_makes_the_plan_training():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 5}, queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.TRAINING


def test_locked_outranks_training():
    """Stated as its own test because it is the counter-intuitive half of
    the table. A character who has TRAINED the skill but cannot use it --
    an inactive clone, a lapsed Omega -- is further from flying the plan
    than one actively training toward it: the second will get there on
    its own, the first needs the user to go do something. So Locked
    ranks WORSE than Training and the plan reads Locked."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5},
                   queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.LOCKED


def test_missing_outranks_locked():
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5})
    assert got.readiness == ev.READINESS_MISSING


def test_one_unknown_name_poisons_the_whole_plan():
    """Unknown outranks everything. One unresolved skill name makes the
    plan Unknown for EVERY character, because the plan cannot be scored
    -- not because any character is deficient."""
    reqs = (Requirement("Navigation", 3), Requirement("Nvigation", 1))
    got = evaluate(reqs, ids={"Navigation": 100}, active={100: 5})
    assert got.readiness == ev.READINESS_UNKNOWN


def test_no_snapshot_is_unscored_with_an_empty_requirement_list():
    """Unscored is the most common state a user sees: every newly
    authorised character is Unscored until its first refresh lands. The
    requirement list is EMPTY rather than every-requirement-Unknown,
    because there is no data to score against and the roster must not
    read as "this plan is broken"."""
    got = evaluate(NAV3, active={100: 5}, snapshot=False)
    assert got.readiness == ev.UNSCORED
    assert got.requirements == ()
    assert got.estimated_finish_utc is None


def test_an_empty_plan_is_ready():
    """A plan with no requirements is trivially satisfied. Unscored is
    reached by the snapshot gate, never by counting requirements."""
    assert evaluate(()).readiness == ev.READY


def test_the_eta_is_the_latest_finish_not_the_earliest():
    """The plan completes when the LAST queued requirement does. Taking
    the minimum would promise a date by which the character still cannot
    fly the ship."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    late = T0 + timedelta(days=9)
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   queue=[entry(100, 3, 0, finish=T0),
                          entry(200, 2, 1, finish=late)])
    assert got.readiness == ev.TRAINING
    assert got.estimated_finish_utc == late


def test_one_dateless_queue_entry_suppresses_the_eta_entirely():
    """The other half. With a null date in the set, the maximum of the
    rest is a lie -- the missing one could land later. The row reads
    "Training - timing unknown" instead of showing a date it cannot
    stand behind."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   queue=[entry(100, 3, 0, finish=T0),
                          entry(200, 2, 1, finish=None)])
    assert got.readiness == ev.TRAINING
    assert got.estimated_finish_utc is None
    assert got.queue_timing_unknown is True


def test_a_ready_plan_has_no_eta():
    """The ETA is populated only when readiness is exactly Training.
    Nothing is being waited for otherwise."""
    got = evaluate(NAV3, active={100: 5})
    assert got.readiness == ev.READY and got.estimated_finish_utc is None


def test_a_locked_plan_has_no_eta_even_with_a_dated_queue_entry():
    """Exactly Training, not "Training is present". A Locked plan has a
    queued requirement with a real date, and showing it would promise a
    completion the inactive clone will not deliver."""
    reqs = (Requirement("Navigation", 3), Requirement("Mechanics", 2))
    got = evaluate(reqs, ids={"Navigation": 100, "Mechanics": 200},
                   active={100: 1}, trained={100: 5},
                   queue=[entry(200, 2, 0, finish=T0)])
    assert got.readiness == ev.LOCKED
    assert got.estimated_finish_utc is None


def test_the_counts_partition_the_requirements():
    reqs = (Requirement("A", 1), Requirement("B", 1), Requirement("C", 1),
            Requirement("D", 1), Requirement("E", 1))
    got = evaluate(reqs, ids={"A": 1, "B": 2, "C": 3, "D": 4},
                   active={1: 5}, trained={2: 5},
                   queue=[entry(3, 1, 0, finish=T0)])
    assert (got.active_count, got.trained_inactive_count, got.queued_count,
            got.missing_count, got.unknown_count) == (1, 1, 1, 1, 1)
    assert sum([got.active_count, got.trained_inactive_count,
                got.queued_count, got.missing_count,
                got.unknown_count]) == len(got.requirements)


def test_compact_status_of_nothing_is_ready():
    assert ev.compact_status(()) == ev.READY


def test_compact_status_maps_an_unrecognised_state_to_unknown():
    """Defensive, and cheap: a state string added to this module without
    a contribution entry must not silently score as Ready. The roster's
    catch-all bucket is the same instinct on the page side."""
    rogue = ev.RequirementAnalysis("X", 1, None, None, "Sideways", None, False)
    assert ev.compact_status([rogue]) == ev.READINESS_UNKNOWN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`
Expected: FAIL — `test_one_queued_requirement_makes_the_plan_training` fails with
`assert 'Ready' == 'Training'` (evaluate() still returns a hardcoded READY), and
`test_no_snapshot_is_unscored_with_an_empty_requirement_list` fails with
`assert 'Ready' == 'Unscored'`.

- [ ] **Step 3: Write minimal implementation**

Add the contribution table below `READINESS_ORDER` in
`obs_youtube_uploader/eveskills/evaluator.py`:

```python
# Requirement state -> the plan readiness it contributes. Locked ranks
# WORSE than Training on purpose: a character who has trained a skill but
# cannot use it (inactive clone, lapsed Omega) needs the user to go do
# something, while one actively training will arrive on its own.
_CONTRIBUTION = {
    ACTIVE: READY,
    QUEUED: TRAINING,
    TRAINED_INACTIVE: LOCKED,
    MISSING: READINESS_MISSING,
    UNKNOWN: READINESS_UNKNOWN,
}
```

Add the count properties to `PlanAnalysis`:

```python
@dataclass(frozen=True)
class PlanAnalysis:
    readiness: str
    estimated_finish_utc: datetime | None
    queue_timing_unknown: bool
    requirements: tuple

    def _count(self, state: str) -> int:
        return sum(1 for a in self.requirements if a.state == state)

    @property
    def active_count(self) -> int:
        return self._count(ACTIVE)

    @property
    def trained_inactive_count(self) -> int:
        return self._count(TRAINED_INACTIVE)

    @property
    def queued_count(self) -> int:
        return self._count(QUEUED)

    @property
    def missing_count(self) -> int:
        return self._count(MISSING)

    @property
    def unknown_count(self) -> int:
        return self._count(UNKNOWN)
```

Add `compact_status()` above `evaluate()`:

```python
def compact_status(analyses) -> str:
    """The worst readiness any requirement contributes.

    Unknown > Missing > Locked > Training > Ready. An empty sequence is
    Ready: a plan with nothing in it is trivially satisfied, and Unscored
    is reached by evaluate()'s has_snapshot gate rather than by counting.

    An unrecognised state contributes Unknown rather than being skipped,
    so a state added to this module without a _CONTRIBUTION entry cannot
    silently score a plan Ready.
    """
    worst = READY
    for analysis in analyses:
        contribution = _CONTRIBUTION.get(analysis.state, READINESS_UNKNOWN)
        if READINESS_ORDER.index(contribution) > READINESS_ORDER.index(worst):
            worst = contribution
    return worst
```

Replace `evaluate()`'s opening guard and its return:

```python
def evaluate(requirements, skill_ids, active_levels, trained_levels,
             queue, has_snapshot: bool) -> PlanAnalysis:
    """Score *requirements* for one character against one snapshot."""
    if not has_snapshot:
        # Unscored, with an EMPTY requirement list. Every newly
        # authorised character is here until its first refresh lands, so
        # this is the most common state a user sees -- and marking every
        # requirement Unknown instead would make an ordinary new
        # character look like a broken plan.
        return PlanAnalysis(UNSCORED, None, False, ())

    # ... unchanged body building `analyses` ...

    readiness = compact_status(analyses)
    timing_unknown = any(a.queue_timing_unknown for a in analyses)
    finishes = [a.queued_finish_utc for a in analyses
                if a.state == QUEUED and a.queued_finish_utc is not None]
    # The MAXIMUM, not the minimum: the plan completes when the last
    # queued requirement does. And only when readiness is exactly
    # Training -- a Locked plan has a dated queue entry too, and showing
    # it would promise a completion the inactive clone will not deliver.
    # One dateless entry suppresses it entirely, because the maximum of
    # the rest could be beaten by the one with no date.
    estimated = None
    if readiness == TRAINING and finishes and not timing_unknown:
        estimated = max(finishes)
    return PlanAnalysis(readiness, estimated, timing_unknown, tuple(analyses))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_evaluator.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/evaluator.py tests/test_eveskills_evaluator.py
git commit -m "feat(eveskills): plan readiness precedence, latest-finish ETA, requirement counts"
```

---

### Task 4: planstore.py — the plans folder

**Files:**
- Create: `obs_youtube_uploader/eveskills/planstore.py`
- Test: `tests/test_eveskills_planstore.py`

**Interfaces:**
- Consumes: `obs_youtube_uploader.eveskills.plans.parse(contents: str) -> ParseResult`,
  `plans.Requirement`, `plans.Diagnostic` (Task 2).
- Produces:

```python
MAX_PLAN_FILES = 200
MAX_PLAN_NAME_CHARS = 120

@dataclass(frozen=True)
class PlanFile:
    name: str                               # filename stem
    requirements: tuple[Requirement, ...]
    diagnostics: tuple[Diagnostic, ...]
    @property
    def ok(self) -> bool

def validate_plan_name(name: str) -> str    # "" when valid, else the reason
def list_plans(plans_dir: Path) -> tuple[list[PlanFile], list[str]]  # plans, warnings
def seed_starter_plan(plans_dir: Path) -> bool   # True if it wrote one
```

---

#### Cycle A — name validation

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_planstore.py`:

```python
"""The plans folder: listing, reading, and the name rules.

Filesystem-only -- tmp_path, no network, no EVE client. The name rules
are Windows' rules even when the suite runs on Linux, because the
released application is Windows-only and a name accepted here would fail
at the write.
"""
import pytest

from obs_youtube_uploader.eveskills import planstore


def test_an_ordinary_name_is_valid():
    assert planstore.validate_plan_name("Core Ship Skills") == ""


def test_an_empty_or_blank_name_is_rejected():
    assert planstore.validate_plan_name("") != ""
    assert planstore.validate_plan_name("   ") != ""


def test_leading_or_trailing_whitespace_is_rejected():
    """Rejected rather than silently trimmed: the name is the identity
    the selected_plan_name field stores, and trimming here would make
    the stored name and the typed name differ."""
    assert planstore.validate_plan_name(" Core") != ""
    assert planstore.validate_plan_name("Core ") != ""


def test_a_name_over_120_characters_is_rejected():
    assert planstore.validate_plan_name("N" * 120) == ""
    assert planstore.validate_plan_name("N" * 121) != ""


@pytest.mark.parametrize("bad", ['a<b', 'a>b', 'a:b', 'a"b', 'a/b', 'a\\b',
                                 'a|b', 'a?b', 'a*b'])
def test_path_invalid_characters_are_rejected(bad):
    """Windows refuses all nine outright. `/` and `\\` are also the
    traversal primitives, so this check is doing two jobs."""
    assert planstore.validate_plan_name(bad) != ""


def test_a_control_character_is_rejected():
    assert planstore.validate_plan_name("Core\x00Ship") != ""
    assert planstore.validate_plan_name("Core\x1bShip") != ""


def test_dot_dot_is_rejected():
    """".." is not in the invalid-character set -- there is no dot in it
    -- and ".." is a perfectly legal filename fragment right up until it
    is joined to a path. `plans_dir / ".."` escapes the folder, and the
    plan name arrives from the bridge, which is to say from the page."""
    assert planstore.validate_plan_name("..") != ""
    assert planstore.validate_plan_name("Core..Ship") != ""
    assert planstore.validate_plan_name("../secrets") != ""


def test_a_single_dot_inside_a_name_is_allowed():
    """v1.2 is a name a user will reasonably type. Only the doubled dot
    is a traversal primitive."""
    assert planstore.validate_plan_name("Rifter v1.2") == ""


def test_a_trailing_dot_is_rejected():
    """Windows silently strips a trailing dot when creating the file, so
    "Core." becomes "Core" on disk and the name the user selected no
    longer matches any file. The failure is a plan that vanishes on
    reload, which reads as data loss."""
    assert planstore.validate_plan_name("Core.") != ""


@pytest.mark.parametrize("reserved", ["CON", "PRN", "AUX", "NUL", "COM1",
                                      "COM9", "LPT1", "LPT9"])
def test_reserved_windows_device_names_are_rejected(reserved):
    """These are device names, not files. CreateFile on CON.txt opens the
    console; the write appears to succeed and nothing lands on disk."""
    assert planstore.validate_plan_name(reserved) != ""
    assert planstore.validate_plan_name(reserved.lower()) != ""


def test_the_reserved_check_looks_at_the_stem_before_the_first_dot():
    """Windows applies the device rule to the base name, so "NUL.txt"
    and even "NUL.plan.txt" are the device -- the reserved-ness is not
    escaped by adding an extension."""
    assert planstore.validate_plan_name("NUL.plan") != ""


def test_a_name_merely_starting_with_a_device_name_is_fine():
    """"CONVOY" is not CON. Matching by prefix rather than by the whole
    stem would reject ordinary names."""
    assert planstore.validate_plan_name("CONVOY") == ""
    assert planstore.validate_plan_name("COM10") == ""


def test_a_non_string_name_is_rejected_rather_than_raising():
    """The name crosses the bridge from JavaScript, so its type is not
    guaranteed. A TypeError here would surface on the bridge thread."""
    assert planstore.validate_plan_name(None) != ""
    assert planstore.validate_plan_name(5) != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`
Expected: FAIL with `ImportError: cannot import name 'planstore' from 'obs_youtube_uploader.eveskills'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/planstore.py`:

```python
"""The plans folder: listing, reading, and the name rules.

The name rules are Windows' rules and are enforced even when this runs
on Linux, because the released application is Windows-only: a name this
module accepted on a developer's machine would fail at the write on a
user's. Plan names also arrive from the bridge, which is to say from the
page, so they are validated as untrusted input rather than as a typo
check.
"""
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import plans

MAX_PLAN_FILES = 200
MAX_PLAN_NAME_CHARS = 120

# The nine characters Windows refuses in a filename outright. `/` and `\`
# are also the traversal primitives, so this set does two jobs.
_INVALID_CHARS = frozenset('<>:"/\\|?*')

# Device names, not files: CreateFile on CON.txt opens the console, the
# write appears to succeed, and nothing lands on disk. Windows applies
# the rule to the base name, so an extension does not escape it.
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{n}" for n in range(1, 10)]
    + [f"LPT{n}" for n in range(1, 10)]
)


def validate_plan_name(name) -> str:
    """Return "" when *name* is a usable plan stem, else the reason why.

    A reason string rather than an exception because every caller wants
    to show it: the bridge returns it to the page verbatim.
    """
    if not isinstance(name, str):
        # The name crosses the bridge from JavaScript, so its type is
        # not guaranteed. A TypeError here lands on the bridge thread.
        return "Plan name is not text."
    normalised = unicodedata.normalize("NFC", name)
    if not normalised.strip():
        return "Plan name is empty."
    if normalised != normalised.strip():
        # Rejected rather than trimmed: the name is the identity stored
        # in selected_plan_name, and trimming would make the stored name
        # differ from the one the user typed.
        return "Plan name has leading or trailing whitespace."
    if len(normalised) > MAX_PLAN_NAME_CHARS:
        return ("Plan name is longer than "
                f"{MAX_PLAN_NAME_CHARS} characters.")
    if any(unicodedata.category(ch) == "Cc" for ch in normalised):
        return "Plan name contains a control character."
    if any(ch in _INVALID_CHARS for ch in normalised):
        return 'Plan name cannot contain < > : " / \\ | ? *'
    if ".." in normalised:
        # Not covered by _INVALID_CHARS, which has no dot in it. ".." is
        # a legal filename fragment right up until it is joined to a
        # path, and then it escapes the folder.
        return "Plan name cannot contain '..'."
    if normalised.endswith("."):
        # Windows strips a trailing dot when creating the file, so
        # "Core." becomes "Core" on disk and the selected name matches
        # nothing on reload -- which reads as data loss. A trailing
        # space is already rejected by the whitespace check above.
        return "Plan name cannot end with a dot."
    if normalised.split(".", 1)[0].upper() in _RESERVED:
        return "Plan name is a reserved Windows device name."
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/planstore.py tests/test_eveskills_planstore.py
git commit -m "feat(eveskills): plan name validation - Windows rules, traversal, device names"
```

---

#### Cycle B — listing the folder

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_planstore.py`:

```python
def write_plan(folder, stem, body="Navigation IV\n"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}.txt"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_missing_folder_lists_nothing_without_raising(tmp_path):
    """The folder is created on first launch, but a user can delete it
    while the app is running. That costs an empty roster, not a crash."""
    found, warnings = planstore.list_plans(tmp_path / "gone")
    assert found == [] and warnings == []


def test_each_txt_file_becomes_a_plan_named_by_its_stem(tmp_path):
    write_plan(tmp_path, "Core Ship Skills")
    found, warnings = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Core Ship Skills"]
    assert warnings == []


def test_the_contents_are_parsed(tmp_path):
    write_plan(tmp_path, "Rifter", "Navigation IV\nMechanics III\n")
    found, _ = planstore.list_plans(tmp_path)
    assert found[0].ok
    assert [(r.skill_name, r.level) for r in found[0].requirements] == [
        ("Navigation", 4), ("Mechanics", 3)]


def test_a_plan_with_diagnostics_is_listed_and_not_ok(tmp_path):
    """A broken plan must still appear -- it is the row that carries the
    diagnostics into the plan-issues disclosure. Dropping it would leave
    the user with a file on disk and no explanation anywhere."""
    write_plan(tmp_path, "Broken", "Navigation nope\n")
    found, _ = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Broken"]
    assert not found[0].ok
    assert found[0].requirements == ()
    assert found[0].diagnostics[0].line == 1


def test_non_txt_files_are_ignored(tmp_path):
    write_plan(tmp_path, "Real")
    (tmp_path / "notes.md").write_text("Navigation IV\n", encoding="utf-8")
    (tmp_path / "Old.txt.bak").write_text("Navigation IV\n", encoding="utf-8")
    found, _ = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Real"]


def test_a_directory_named_like_a_plan_is_ignored(tmp_path):
    """glob("*.txt") matches directories too, and read_text() on one
    raises IsADirectoryError -- which would become a warning about a
    file the user never created."""
    (tmp_path / "Folder.txt").mkdir(parents=True)
    write_plan(tmp_path, "Real")
    found, warnings = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Real"]
    assert warnings == []


def test_plans_are_sorted_case_insensitively(tmp_path):
    """Byte order puts every capitalised name before every lowercase
    one, which scatters "Rifter" and "rifter alt" across the rail."""
    for stem in ("zeta", "Alpha", "beta"):
        write_plan(tmp_path, stem)
    found, _ = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Alpha", "beta", "zeta"]


def test_an_undecodable_file_warns_and_does_not_stop_the_others(tmp_path):
    """A .txt saved as UTF-16 by Notepad, or a binary file renamed. One
    unreadable file costs its own row, not the folder -- the same
    per-entry tolerance preview/layout.py takes."""
    write_plan(tmp_path, "Good")
    (tmp_path / "Bad.txt").write_bytes(b"\xff\xfe\x00\x00Navigation")
    found, warnings = planstore.list_plans(tmp_path)
    assert [p.name for p in found] == ["Good"]
    assert len(warnings) == 1 and "Bad.txt" in warnings[0]


def test_at_most_200_files_are_read(tmp_path):
    """The cap bounds the work one `Reload plans` click can do. It warns
    rather than failing, because the plans the user can see still work."""
    for n in range(planstore.MAX_PLAN_FILES + 5):
        write_plan(tmp_path, f"Plan{n:04d}")
    found, warnings = planstore.list_plans(tmp_path)
    assert len(found) == planstore.MAX_PLAN_FILES
    assert len(warnings) == 1 and "200" in warnings[0]


def test_the_cap_keeps_the_first_files_in_sort_order(tmp_path):
    """Truncating after the sort rather than before means the same 200
    plans appear on every reload, instead of whichever 200 the
    filesystem happened to enumerate first."""
    for n in range(planstore.MAX_PLAN_FILES + 5):
        write_plan(tmp_path, f"Plan{n:04d}")
    found, _ = planstore.list_plans(tmp_path)
    assert found[0].name == "Plan0000"
    assert found[-1].name == f"Plan{planstore.MAX_PLAN_FILES - 1:04d}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.planstore' has no attribute 'list_plans'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/planstore.py`:

```python
@dataclass(frozen=True)
class PlanFile:
    name: str           # the filename stem; the plan's identity everywhere
    requirements: tuple
    diagnostics: tuple

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def list_plans(plans_dir: Path):
    """Read every *.txt in *plans_dir*. Returns (plans, warnings).

    Never raises. A broken plan is still listed -- it is the row that
    carries its diagnostics into the plan-issues disclosure, and
    dropping it would leave the user with a file on disk and no
    explanation anywhere in the UI.
    """
    warnings = []
    try:
        # is_file() because glob("*.txt") matches directories too, and
        # read_text() on one raises IsADirectoryError -- which would
        # become a warning about a file the user never created.
        entries = [p for p in plans_dir.glob("*.txt") if p.is_file()]
    except OSError as exc:
        # A deleted or permission-denied folder costs an empty roster,
        # not a crash. `Open plans folder` reports the real failure.
        return [], [f"The plans folder could not be read: {exc}"]

    # Sorted BEFORE the cap so the same 200 plans appear on every
    # reload, rather than whichever 200 the filesystem enumerated first.
    # Case-insensitive because byte order puts every capitalised name
    # ahead of every lowercase one and scatters related plans.
    entries.sort(key=lambda p: p.stem.casefold())
    if len(entries) > MAX_PLAN_FILES:
        warnings.append(
            f"Only the first {MAX_PLAN_FILES} of {len(entries)} plan files "
            "were read.")
        entries = entries[:MAX_PLAN_FILES]

    found = []
    for path in entries:
        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # A .txt Notepad saved as UTF-16, or a binary file renamed.
            # One unreadable file costs its own row, not the folder --
            # the same per-entry tolerance preview/layout.py takes.
            warnings.append(f"{path.name} could not be read: {exc}")
            continue
        result = plans.parse(contents)
        found.append(PlanFile(path.stem, result.requirements,
                              result.diagnostics))
    return found, warnings
```

Note: `Path.glob()` on a missing directory yields nothing rather than raising,
so `test_a_missing_folder_lists_nothing_without_raising` passes through the
normal path with an empty list; the `OSError` branch covers permission denied
and a path that exists but is not a directory.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/planstore.py tests/test_eveskills_planstore.py
git commit -m "feat(eveskills): list and parse the plans folder with per-file tolerance"
```

---

#### Cycle C — the starter plan

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_planstore.py`:

```python
def test_the_starter_plan_is_written_into_an_empty_folder(tmp_path):
    folder = tmp_path / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    assert (folder / "Core Ship Skills.txt").is_file()


def test_the_starter_plan_creates_the_folder(tmp_path):
    """First launch has no state directory tree at all, and seeding is
    what makes `Open plans folder` open something rather than fail."""
    folder = tmp_path / "deep" / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    assert folder.is_dir()


def test_the_starter_plan_parses_cleanly(tmp_path):
    """A seeded plan with a diagnostic would greet every new user with a
    plan-issues disclosure about a file they did not write."""
    folder = tmp_path / "skill_plans"
    planstore.seed_starter_plan(folder)
    found, warnings = planstore.list_plans(folder)
    assert warnings == []
    assert len(found) == 1 and found[0].ok
    assert found[0].requirements


def test_seeding_is_skipped_when_any_txt_is_present(tmp_path):
    """Keyed on "the folder has no plans", not on "this file is
    missing": a user who deletes the starter must not get it back on
    every launch."""
    folder = tmp_path / "skill_plans"
    write_plan(folder, "My Own Plan")
    assert planstore.seed_starter_plan(folder) is False
    assert not (folder / "Core Ship Skills.txt").exists()


def test_seeding_twice_writes_once(tmp_path):
    folder = tmp_path / "skill_plans"
    assert planstore.seed_starter_plan(folder) is True
    (folder / "Core Ship Skills.txt").write_text("Mechanics V\n",
                                                 encoding="utf-8")
    assert planstore.seed_starter_plan(folder) is False
    assert (folder / "Core Ship Skills.txt").read_text(
        encoding="utf-8") == "Mechanics V\n"


def test_seeding_into_an_unwritable_location_returns_false(tmp_path):
    """A read-only or occupied state directory costs the starter plan,
    not the launch -- the same policy resolve_binary() and
    configure_logging() take with a missing resource."""
    blocker = tmp_path / "skill_plans"
    blocker.write_text("not a directory", encoding="utf-8")
    assert planstore.seed_starter_plan(blocker) is False


def test_the_starter_plan_name_passes_validation():
    """It is written by us and selected by name like any other, so it
    has to satisfy the same rules a user-typed name does."""
    assert planstore.validate_plan_name(planstore.STARTER_PLAN_NAME) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.planstore' has no attribute 'seed_starter_plan'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/planstore.py`:

```python
STARTER_PLAN_NAME = "Core Ship Skills"

# Real skill names, at modest levels, and it must parse without a single
# diagnostic: a seeded plan that complained would greet every new user
# with a plan-issues disclosure about a file they did not write. The
# comment header doubles as the format documentation, because this file
# is the only instruction most users will ever read.
_STARTER_PLAN = """\
# Core Ship Skills - a starter plan, safe to edit or delete.
#
# One skill per line: the skill name, a space, then the level as
# I II III IV V or 1 2 3 4 5. Lines starting with # are ignored.
#
Spaceship Command III
Navigation IV
Evasive Maneuvering III
Warp Drive Operation III
Hull Upgrades IV
Mechanics IV
Shield Operation III
Power Grid Management IV
CPU Management IV
Capacitor Systems Operation III
Capacitor Management III
Targeting III
"""


def seed_starter_plan(plans_dir: Path) -> bool:
    """Write the starter plan when *plans_dir* holds no .txt at all.

    Keyed on "the folder has no plans" rather than "this file is
    missing", so a user who deletes the starter does not get it back on
    every launch.

    Returns False rather than raising on any filesystem failure: a
    read-only or occupied state directory costs the starter plan, not
    the launch, which is the same policy paths.resolve_binary() and
    configure_logging() take with a missing resource.
    """
    try:
        plans_dir.mkdir(parents=True, exist_ok=True)
        if any(plans_dir.glob("*.txt")):
            return False
        (plans_dir / f"{STARTER_PLAN_NAME}.txt").write_text(
            _STARTER_PLAN, encoding="utf-8")
    except OSError:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_planstore.py -v`

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: PASS, including `tests/test_packaging_completeness.py`.

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/eveskills/planstore.py tests/test_eveskills_planstore.py
git commit -m "feat(eveskills): seed a starter plan into an empty plans folder"
```
### Task 5: `state.py` — roster model and persistence

**Files:**
- Create: `obs_youtube_uploader/eveskills/state.py`
- Test: `tests/test_eveskills_state.py`

**Interfaces:**

- Consumes (from Task 3, `evaluator.py`):

```python
@dataclass(frozen=True)
class QueueEntry:
    skill_id: int
    finished_level: int         # 1..5
    start_date: datetime | None
    finish_date: datetime | None
    queue_position: int
```

- Consumes (existing repo module):

```python
# obs_youtube_uploader/atomicio.py
def write_atomic(path: Path, text: str, encoding: str = "utf-8", *,
                 attempts: int = 5, sleep=time.sleep) -> None
```

- Produces:

```python
MAX_CHARACTERS = 50
STATE_VERSION = 1

@dataclass
class Character:
    character_id: int
    character_name: str = ""
    owner_hash: str = ""
    scopes: tuple[str, ...] = ()
    authenticated_utc: datetime | None = None
    fetched_utc: datetime | None = None
    active_levels: dict[int, int] = field(default_factory=dict)
    trained_levels: dict[int, int] = field(default_factory=dict)
    queue: tuple[QueueEntry, ...] = ()
    error: str = ""
    needs_reauth: bool = False
    refresh_token_blob: str = ""    # base64 DPAPI blob; "" when absent
    skills_etag: str = ""
    queue_etag: str = ""

    @property
    def has_snapshot(self) -> bool  # fetched_utc is not None
    @property
    def stale(self) -> bool         # has_snapshot and bool(error)

@dataclass
class SkillsState:
    characters: list[Character] = field(default_factory=list)
    selected_plan_name: str = ""

    def find(self, character_id: int) -> Character | None
    def upsert(self, character: Character) -> None
    def remove(self, character_id: int) -> bool

def to_dict(state: SkillsState) -> dict
def from_dict(raw: object) -> SkillsState          # tolerant; never raises
def load(path: Path) -> tuple[SkillsState, list[str]]   # state, warnings
def save(state: SkillsState, path: Path) -> None        # atomic, writes .bak
```

---

#### Cycle A — the model

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_state.py`:

```python
"""The roster document: one file holds identity, snapshot, queue, ETags,
and the DPAPI-wrapped refresh token for every character, so forgetting one
is a single atomic write with no window in which a token outlives the
character it belongs to.

Normalisation is tolerant rather than versioned, matching settings.py's
validated_*() functions and the rationale preview/layout.py:26-32 records:
a partially-written or hand-edited file should cost one character's row,
not the launch.
"""
from datetime import datetime, timezone
from pathlib import Path

from obs_youtube_uploader.eveskills import state
from obs_youtube_uploader.eveskills.evaluator import QueueEntry


def test_a_new_character_has_no_snapshot_and_is_not_stale():
    """Every newly authorised character sits here until its first refresh
    lands. has_snapshot is what the evaluator reads to return Unscored, and
    stale must stay False -- there is no last-good data to be stale about."""
    character = state.Character(character_id=90000001)
    assert character.has_snapshot is False
    assert character.stale is False


def test_an_error_over_existing_data_is_stale():
    """stale means "you are looking at last-good data". It is exactly the
    conjunction: a fetch that failed leaves fetched_utc untouched and sets
    error, which is what makes the badge meaningful."""
    character = state.Character(
        character_id=90000001,
        fetched_utc=datetime(2026, 8, 24, tzinfo=timezone.utc),
        error="ESI timed out")
    assert character.stale is True


def test_an_error_with_no_data_is_not_stale():
    """A character whose *first* refresh failed has an error but nothing to
    show. Marking it stale would claim data that is not there."""
    character = state.Character(character_id=90000001, error="ESI timed out")
    assert character.stale is False


def test_upsert_replaces_by_id_and_keeps_position():
    """Merge by character id, never replace the roster wholesale -- the same
    rule preview/store.py carries. Position is kept so a refresh does not
    reshuffle rows under the user's cursor."""
    roster = state.SkillsState(characters=[
        state.Character(character_id=1, character_name="First"),
        state.Character(character_id=2, character_name="Second"),
    ])
    roster.upsert(state.Character(character_id=1, character_name="Renamed"))
    assert [c.character_id for c in roster.characters] == [1, 2]
    assert roster.find(1).character_name == "Renamed"


def test_upsert_appends_an_unknown_id():
    roster = state.SkillsState()
    roster.upsert(state.Character(character_id=7))
    assert [c.character_id for c in roster.characters] == [7]


def test_remove_reports_whether_it_removed_anything():
    """The bridge returns this boolean straight to the page, so forgetting a
    character that is already gone must be distinguishable from success."""
    roster = state.SkillsState(characters=[state.Character(character_id=1)])
    assert roster.remove(1) is True
    assert roster.remove(1) is False
    assert roster.characters == []


def test_find_returns_none_for_an_unknown_id():
    assert state.SkillsState().find(999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.state'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/state.py`:

```python
"""Roster, skill snapshots, ETags, and wrapped refresh tokens in one file.

One document holds everything about a character, which is what makes forget
a single atomic write: there is no window in which a token exists without
its character, and no reconciliation sweep to get wrong. TriffView splits
these across Credential Manager and state.json and pays for it in rollback
paths (TriffSkillsAuthentication.cs:103,108) and a RecoverOwnCredentials()
that exists only to resurrect orphans.

Only the refresh token is wrapped. The metadata beside it stays plaintext so
a blob that will not decrypt costs one character a re-authentication rather
than making the whole document unparseable.

Normalisation on load is deliberately tolerant rather than versioned, which
is the same posture settings.py's validated_*() functions take and the
reason preview/layout.py:26-32 gives: a partially-written or hand-edited
file should cost one row, not the launch.
"""
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import atomicio
from .evaluator import QueueEntry

MAX_CHARACTERS = 50
STATE_VERSION = 1

# Caps on the two unbounded per-character collections. A real character has
# a few hundred skills; 20,000 is far above anything EVE can produce and far
# below anything that would make the JSON load hurt.
MAX_LEVEL_ENTRIES = 20_000
# ESI's own skill queue tops out around 50 entries. 500 is headroom, not a
# guess at the real ceiling.
MAX_QUEUE_ENTRIES = 500


@dataclass
class Character:
    character_id: int
    character_name: str = ""
    owner_hash: str = ""
    scopes: tuple = ()
    authenticated_utc: "datetime | None" = None
    fetched_utc: "datetime | None" = None
    active_levels: dict = field(default_factory=dict)
    trained_levels: dict = field(default_factory=dict)
    queue: tuple = ()
    error: str = ""
    needs_reauth: bool = False
    # base64 text of the DPAPI blob; "" when the token is absent or was
    # deleted by a definitive auth failure.
    refresh_token_blob: str = ""
    # Per-endpoint ETags. These are request optimisation ONLY -- they are
    # not freshness state. fetched_utc is the single freshness fact, and it
    # means "both halves were confirmed current at this time".
    skills_etag: str = ""
    queue_etag: str = ""

    @property
    def has_snapshot(self) -> bool:
        return self.fetched_utc is not None

    @property
    def stale(self) -> bool:
        # The conjunction is the whole meaning: an error with no prior data
        # is a character that never loaded, not one showing stale data.
        return self.has_snapshot and bool(self.error)


@dataclass
class SkillsState:
    characters: list = field(default_factory=list)
    selected_plan_name: str = ""

    def find(self, character_id: int):
        for character in self.characters:
            if character.character_id == character_id:
                return character
        return None

    def upsert(self, character: Character) -> None:
        # Replace in place rather than remove-then-append: the roster order
        # is what the page renders inside each readiness group, and a
        # refresh must not reshuffle rows under the user's cursor.
        for index, existing in enumerate(self.characters):
            if existing.character_id == character.character_id:
                self.characters[index] = character
                return
        self.characters.append(character)

    def remove(self, character_id: int) -> bool:
        for index, existing in enumerate(self.characters):
            if existing.character_id == character_id:
                del self.characters[index]
                return True
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_state.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/state.py tests/test_eveskills_state.py
git commit -m "feat(eveskills): roster model with has_snapshot and stale"
```

---

#### Cycle B — tolerant normalisation

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_state.py`:

```python
def test_round_trips_a_full_character():
    """Datetimes are timezone-aware UTC inside the package and ISO 8601
    strings on disk. The conversion lives here so nothing downstream has to
    ask which form it is holding."""
    original = state.SkillsState(
        selected_plan_name="Interceptors",
        characters=[state.Character(
            character_id=90000001,
            character_name="Aiga Otsolen",
            owner_hash="abc123",
            scopes=("esi-skills.read_skills.v1",),
            authenticated_utc=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
            fetched_utc=datetime(2026, 8, 24, 10, 30, tzinfo=timezone.utc),
            active_levels={3300: 5},
            trained_levels={3300: 5, 3301: 4},
            queue=(QueueEntry(3301, 5,
                              datetime(2026, 8, 24, tzinfo=timezone.utc),
                              datetime(2026, 8, 26, tzinfo=timezone.utc), 0),),
            error="",
            needs_reauth=False,
            refresh_token_blob="QUJD",
            skills_etag='W/"abc"',
            queue_etag='W/"def"')])
    assert state.from_dict(state.to_dict(original)) == original


def test_from_dict_never_raises_on_junk():
    """This runs at launch. Anything that gets here -- a truncated write, a
    hand edit, a file from a future version -- must degrade to an empty
    roster rather than take the app down."""
    for raw in (None, [], "nope", 3, {"characters": "not-a-list"},
                {"characters": [None, 7, "x", []]}):
        assert isinstance(state.from_dict(raw), state.SkillsState)


def test_characters_are_capped_and_deduped():
    """MAX_CHARACTERS bounds a hand-edited or corrupted file; the dedupe is
    what keeps find()/upsert() single-valued, since both stop at the first
    match and a second row with the same id would be unreachable and
    unforgettable."""
    raw = {"characters": [{"character_id": 1} for _ in range(60)]
                         + [{"character_id": n} for n in range(2, 80)]}
    result = state.from_dict(raw)
    assert len(result.characters) == state.MAX_CHARACTERS
    ids = [c.character_id for c in result.characters]
    assert len(set(ids)) == len(ids)


def test_a_non_positive_character_id_is_dropped():
    """0 is what an absent id coerces to, and a negative id can never match
    a real EVE character. Either would produce a row that cannot be
    refreshed."""
    raw = {"characters": [{"character_id": 0}, {"character_id": -5},
                          {"character_id": 42}]}
    assert [c.character_id for c in state.from_dict(raw).characters] == [42]


def test_malformed_skill_levels_drop_individually():
    """Per-entry drops, not per-character. One unparseable skill id must
    not cost the whole snapshot -- that would silently turn a character
    Unscored and hide the fact behind an empty row."""
    raw = {"characters": [{"character_id": 1, "active_levels": {
        "3300": 5, "3301": 9, "bogus": 3, "3302": 4, "-1": 2}}]}
    levels = state.from_dict(raw).characters[0].active_levels
    assert levels == {3300: 5, 3302: 4}


def test_a_boolean_skill_level_is_dropped():
    """bool is an int subclass in Python, so a JSON `true` would sail
    through an isinstance(value, int) check and store level 1."""
    raw = {"characters": [{"character_id": 1,
                           "active_levels": {"3300": True}}]}
    assert state.from_dict(raw).characters[0].active_levels == {}


def test_queue_entries_are_validated_and_ordered_by_position():
    """queue_position is the tie-break the evaluator's
    lowest_sufficient_entry relies on, so the stored order must not be
    trusted -- a hand-edited file can list them any way at all."""
    raw = {"characters": [{"character_id": 1, "queue": [
        {"skill_id": 20, "finished_level": 3, "queue_position": 2},
        {"skill_id": 10, "finished_level": 1, "queue_position": 0},
        {"skill_id": 30, "finished_level": 9, "queue_position": 1},
        {"skill_id": 0, "finished_level": 2, "queue_position": 3},
        {"finished_level": 2, "queue_position": 4},
    ]}]}
    queue = state.from_dict(raw).characters[0].queue
    assert [(e.skill_id, e.queue_position) for e in queue] == [(10, 0), (20, 2)]


def test_queue_is_capped():
    raw = {"characters": [{"character_id": 1, "queue": [
        {"skill_id": n + 1, "finished_level": 1, "queue_position": n}
        for n in range(state.MAX_QUEUE_ENTRIES + 50)]}]}
    assert len(state.from_dict(raw).characters[0].queue) == \
        state.MAX_QUEUE_ENTRIES


def test_scopes_are_deduped_and_non_strings_dropped():
    raw = {"characters": [{"character_id": 1, "scopes": [
        "a", "a", 7, None, "b"]}]}
    assert state.from_dict(raw).characters[0].scopes == ("a", "b")


def test_an_unparseable_timestamp_becomes_none():
    """A bad fetched_utc must not raise. It degrades the character to
    Unscored, which is a state the UI already renders."""
    raw = {"characters": [{"character_id": 1, "fetched_utc": "not-a-date"}]}
    assert state.from_dict(raw).characters[0].fetched_utc is None


def test_a_naive_timestamp_is_read_as_utc():
    """Everything this package writes is UTC. A naive value can only come
    from a hand edit, and treating it as local time would shift an ETA by
    hours depending on the machine."""
    raw = {"characters": [{"character_id": 1,
                           "fetched_utc": "2026-08-24T10:30:00"}]}
    fetched = state.from_dict(raw).characters[0].fetched_utc
    assert fetched == datetime(2026, 8, 24, 10, 30, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_state.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.state' has no attribute 'to_dict'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/state.py`:

```python
def _iso(value) -> str:
    """UTC ISO 8601, or "" for absent. Never None, so the JSON has one
    shape for a field whether or not it is set."""
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(raw):
    """Parse an ISO 8601 string to an aware UTC datetime, or None.

    A naive value is read as UTC rather than local: everything this package
    writes is UTC, so a naive string can only be a hand edit, and reading it
    as local time would shift an ETA by the machine's offset. Python 3.11's
    fromisoformat accepts a trailing "Z"; the repo floor is 3.11, so no
    manual substitution is needed.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_int(raw):
    # bool is an int subclass, so JSON `true` would otherwise become 1 --
    # a skill id of 1 or a level of 1 that nothing in the file asked for.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _coerce_levels(raw) -> dict:
    """Skill id -> level, dropping malformed entries individually.

    Individually is the point: one unparseable id must cost that skill, not
    the character's whole snapshot. Dropping the snapshot would silently
    turn the character Unscored with no visible reason.
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if len(out) >= MAX_LEVEL_ENTRIES:
            break
        skill_id = _coerce_int(key)
        level = _coerce_int(value)
        if skill_id is None or level is None:
            continue
        if skill_id <= 0 or not 0 <= level <= 5:
            continue
        out[skill_id] = level
    return out


def _coerce_queue(raw) -> tuple:
    """Queue entries, validated per entry and re-sorted by position.

    The stored order is not trusted: queue_position is the tie-break
    lowest_sufficient_entry depends on, and a hand-edited file can list the
    entries in any order at all. The cap is applied to accepted entries as
    they are read, before the sort -- a truncated 5,000-entry file should
    stop costing time immediately, not after parsing all of it.
    """
    if not isinstance(raw, list):
        return ()
    entries = []
    for item in raw:
        if len(entries) >= MAX_QUEUE_ENTRIES:
            break
        if not isinstance(item, dict):
            continue
        skill_id = _coerce_int(item.get("skill_id"))
        finished_level = _coerce_int(item.get("finished_level"))
        if skill_id is None or finished_level is None:
            continue
        if skill_id <= 0 or not 1 <= finished_level <= 5:
            continue
        position = _coerce_int(item.get("queue_position"))
        entries.append(QueueEntry(
            skill_id=skill_id,
            finished_level=finished_level,
            start_date=_parse_utc(item.get("start_date")),
            finish_date=_parse_utc(item.get("finish_date")),
            queue_position=len(entries) if position is None else position))
    entries.sort(key=lambda entry: entry.queue_position)
    return tuple(entries)


def _coerce_scopes(raw) -> tuple:
    if not isinstance(raw, list):
        return ()
    out = []
    for item in raw:
        if isinstance(item, str) and item and item not in out:
            out.append(item)
    return tuple(out)


def _coerce_text(raw) -> str:
    return raw if isinstance(raw, str) else ""


def to_dict(state: SkillsState) -> dict:
    return {
        "version": STATE_VERSION,
        "selected_plan_name": state.selected_plan_name,
        "characters": [{
            "character_id": character.character_id,
            "character_name": character.character_name,
            "owner_hash": character.owner_hash,
            "scopes": list(character.scopes),
            "authenticated_utc": _iso(character.authenticated_utc),
            "fetched_utc": _iso(character.fetched_utc),
            # JSON object keys are strings; from_dict coerces them back.
            "active_levels": {str(k): v
                              for k, v in character.active_levels.items()},
            "trained_levels": {str(k): v
                               for k, v in character.trained_levels.items()},
            "queue": [{
                "skill_id": entry.skill_id,
                "finished_level": entry.finished_level,
                "start_date": _iso(entry.start_date),
                "finish_date": _iso(entry.finish_date),
                "queue_position": entry.queue_position,
            } for entry in character.queue],
            "error": character.error,
            "needs_reauth": character.needs_reauth,
            "refresh_token_blob": character.refresh_token_blob,
            "skills_etag": character.skills_etag,
            "queue_etag": character.queue_etag,
        } for character in state.characters],
    }


def from_dict(raw: object) -> SkillsState:
    """Rebuild a roster, dropping anything malformed. Never raises.

    This runs at launch, so the only acceptable failure is a smaller roster
    plus a warning. The version field is written but deliberately not
    checked: tolerant normalisation already handles a document from a
    different shape better than a hard version gate would, which is the
    same trade settings.py makes.
    """
    result = SkillsState()
    if not isinstance(raw, dict):
        return result
    result.selected_plan_name = _coerce_text(raw.get("selected_plan_name"))

    characters = raw.get("characters")
    if not isinstance(characters, list):
        return result

    seen = set()
    for item in characters:
        if len(result.characters) >= MAX_CHARACTERS:
            break
        if not isinstance(item, dict):
            continue
        character_id = _coerce_int(item.get("character_id"))
        # A second row for the same id would be unreachable: find() and
        # upsert() both stop at the first match, so the duplicate could
        # never be refreshed and never be forgotten.
        if character_id is None or character_id <= 0 or character_id in seen:
            continue
        seen.add(character_id)
        result.characters.append(Character(
            character_id=character_id,
            character_name=_coerce_text(item.get("character_name")),
            owner_hash=_coerce_text(item.get("owner_hash")),
            scopes=_coerce_scopes(item.get("scopes")),
            authenticated_utc=_parse_utc(item.get("authenticated_utc")),
            fetched_utc=_parse_utc(item.get("fetched_utc")),
            active_levels=_coerce_levels(item.get("active_levels")),
            trained_levels=_coerce_levels(item.get("trained_levels")),
            queue=_coerce_queue(item.get("queue")),
            error=_coerce_text(item.get("error")),
            needs_reauth=item.get("needs_reauth") is True,
            refresh_token_blob=_coerce_text(item.get("refresh_token_blob")),
            skills_etag=_coerce_text(item.get("skills_etag")),
            queue_etag=_coerce_text(item.get("queue_etag"))))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_state.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/state.py tests/test_eveskills_state.py
git commit -m "feat(eveskills): tolerant state normalisation with per-entry drops"
```

---

#### Cycle C — load, save, backup, corruption

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_state.py`:

```python
import json
import os
import stat
import sys

import pytest


def test_load_of_a_missing_file_is_empty_and_silent(tmp_path):
    """First launch is not an error condition and must not produce a
    warning the user has to dismiss."""
    loaded, warnings = state.load(tmp_path / "eve_skills.json")
    assert loaded.characters == []
    assert warnings == []


def test_save_then_load_round_trips(tmp_path):
    target = tmp_path / "eve_skills.json"
    original = state.SkillsState(
        selected_plan_name="Interceptors",
        characters=[state.Character(character_id=1, character_name="Aiga")])
    state.save(original, target)
    loaded, warnings = state.load(target)
    assert loaded == original
    assert warnings == []


def test_save_copies_the_previous_document_to_bak(tmp_path):
    """Merging the refresh tokens into this document moved the one
    non-rebuildable thing into the file that had no backup tier. Everything
    else in the subsystem rebuilds from a refresh; authorisations do not."""
    target = tmp_path / "eve_skills.json"
    state.save(state.SkillsState(selected_plan_name="First"), target)
    state.save(state.SkillsState(selected_plan_name="Second"), target)
    backup = json.loads((tmp_path / "eve_skills.json.bak").read_text())
    assert backup["selected_plan_name"] == "First"


def test_the_first_save_writes_no_bak(tmp_path):
    """There is nothing to back up yet, and an empty .bak would later be
    recovered from in preference to giving up honestly."""
    target = tmp_path / "eve_skills.json"
    state.save(state.SkillsState(), target)
    assert not (tmp_path / "eve_skills.json.bak").exists()


def test_a_corrupt_document_is_preserved_and_recovered_from_backup(tmp_path):
    """The alternative to this tier is a single bad write costing every
    character's authorisation."""
    target = tmp_path / "eve_skills.json"
    state.save(state.SkillsState(selected_plan_name="Good"), target)
    state.save(state.SkillsState(selected_plan_name="Newer"), target)
    target.write_text("{ this is not json", encoding="utf-8")

    loaded, warnings = state.load(target)
    assert loaded.selected_plan_name == "Good"
    assert any("Recovered" in w for w in warnings)
    preserved = [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert len(preserved) == 1


def test_a_corrupt_document_with_no_usable_backup_starts_empty(tmp_path):
    """Starting empty and saying so beats refusing to launch. The recovery
    is re-authorising, which is safe and needs no manual cleanup."""
    target = tmp_path / "eve_skills.json"
    target.write_text("{ this is not json", encoding="utf-8")
    loaded, warnings = state.load(target)
    assert loaded.characters == []
    assert warnings and "could not be read" in warnings[0]


def test_the_corrupt_file_is_moved_aside_not_left_in_place(tmp_path):
    """Left in place it would be re-read, re-preserved, and re-warned on
    every launch forever."""
    target = tmp_path / "eve_skills.json"
    target.write_text("nope", encoding="utf-8")
    state.load(target)
    assert not target.exists()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX mode bits; on Windows DPAPI does the work")
def test_the_document_is_owner_only_on_posix(tmp_path):
    """The file holds refresh tokens, so it wants owner-only permissions --
    but it must NOT be written with os.open(..., 0o600) the way
    uploader.py:286-293 writes the Google token, because write_atomic
    creates and owns its own temporary descriptor (atomicio.py:29-31).

    It does not need to be. tempfile.mkstemp creates its file at 0600
    regardless of umask, and os.replace carries the temporary file's mode to
    the destination -- verified, including over a pre-existing 0644 file. So
    an atomically-written file is owner-only on POSIX without any os.open
    dance, and the .bak copy inherits it because shutil.copy2 copies mode.
    """
    target = tmp_path / "eve_skills.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o644)
    state.save(state.SkillsState(), target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "eve_skills.json.bak").stat().st_mode) \
        == 0o600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_state.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.state' has no attribute 'load'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/state.py`:

```python
def _preserve_corrupt(path: Path) -> str:
    """Move an unreadable document aside, returning its new name or "".

    Moved, not copied: left in place it would be re-read, re-preserved and
    re-warned on every launch, and the user would accumulate one .corrupt-
    file per start with no way to tell which one mattered.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        os.replace(path, target)
    except OSError:
        return ""
    return target.name


def load(path: Path) -> tuple:
    """Read the roster. Returns (state, warnings) and never raises.

    A warning here reaches the UI notices strip, so it is written for the
    person reading it rather than for a log.
    """
    path = Path(path)
    warnings: list = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # First launch. Not an error, and not something to warn about.
        return SkillsState(), warnings
    except OSError as exc:
        warnings.append(f"{path.name} could not be read ({exc.strerror}); "
                        "starting with an empty roster.")
        return SkillsState(), warnings

    try:
        # json.JSONDecodeError and UnicodeDecodeError are both ValueError.
        return from_dict(json.loads(text)), warnings
    except ValueError:
        pass

    preserved = _preserve_corrupt(path)
    backup = path.with_name(path.name + ".bak")
    try:
        recovered = from_dict(json.loads(backup.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        warnings.append(
            f"{path.name} could not be read and was preserved as "
            f"{preserved or 'a copy'}; starting with an empty roster. "
            "Any characters you had added will need re-authorising.")
        return SkillsState(), warnings

    warnings.append(
        f"Recovered {path.name} from backup after the main file could not "
        f"be read; it was preserved as {preserved or 'a copy'}. Anything "
        "saved since the previous write is gone.")
    return recovered, warnings


def save(state: SkillsState, path: Path) -> None:
    """Write the roster atomically, keeping one previous copy.

    The .bak copy does NOT extend atomicio.py, deliberately. write_atomic
    makes no backup because it is shared with the Wingman/engine boundary,
    where a stray .bak sitting beside a polled INI would be its own problem
    -- the engine reads that directory. The copy is three lines and only
    this subsystem wants it, because this is the only file holding something
    (the refresh tokens) that a refresh cannot rebuild.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            # copy2 rather than copy: it carries the mode across, so the
            # backup of a 0600 document is not published at 0644.
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError:
            # A backup that cannot be made must not stop the save. Losing
            # the tier is strictly better than losing the write that the
            # tier exists to protect.
            pass
    atomicio.write_atomic(path, json.dumps(to_dict(state), indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_state.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/state.py tests/test_eveskills_state.py
git commit -m "feat(eveskills): state load/save with backup tier and corruption recovery"
```

---

### Task 6: `dpapi.py` and `tokens.py` — refresh-token wrapping

**Files:**
- Create: `obs_youtube_uploader/eveskills/dpapi.py`
- Create: `obs_youtube_uploader/eveskills/tokens.py`
- Test: `tests/test_eveskills_dpapi.py`
- Test: `tests/test_eveskills_tokens.py`

**Interfaces:**

- Consumes: nothing.
- Produces:

```python
# dpapi.py — Windows only
def protect(data: bytes) -> bytes
def unprotect(blob: bytes) -> bytes
def available() -> bool         # False off Windows

# tokens.py
def wrap(token: str, *, protect=dpapi.protect) -> str      # base64 text
def unwrap(blob: str, *, unprotect=dpapi.unprotect) -> str | None
```

---

#### Cycle A — `dpapi.py`

Write this first: `tokens.py` imports it for its production defaults, so
`tokens.py` cannot even import until this module exists.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_dpapi.py`:

```python
"""dpapi.py is the only Windows-only module in the package. Everything else
runs in CI on Linux, and this test exists to pin the one property that can
be checked off Windows: the module IMPORTS cleanly there.

That is not a formality. ctypes.WinDLL and ctypes.windll do not exist on
Linux, so a library binding built at module scope would raise at import --
and because state.py's neighbour tokens.py imports this module for its
production defaults, that import error would take the entire subsystem's
test suite with it. The bindings are therefore built lazily inside
functions, exactly as preview/win32.py:1-9 describes for the same reason.
"""
import sys

import pytest

from obs_youtube_uploader.eveskills import dpapi


def test_the_module_imports_off_windows():
    assert callable(dpapi.protect)
    assert callable(dpapi.unprotect)


def test_available_is_false_off_windows():
    """The controller reads this to decide whether it can store a token at
    all. A wrong answer here would mean silently discarding one."""
    assert dpapi.available() is (sys.platform == "win32")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has crypt32")
def test_protect_refuses_off_windows_rather_than_crashing():
    """Called by mistake off Windows this must be a clean, explanatory
    error, not an obscure ctypes AttributeError from three frames down."""
    with pytest.raises(OSError):
        dpapi.protect(b"x")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has crypt32")
def test_unprotect_refuses_off_windows_rather_than_crashing():
    with pytest.raises(OSError):
        dpapi.unprotect(b"x")


@pytest.mark.skipif(sys.platform != "win32", reason="requires real DPAPI")
def test_round_trips_on_windows():
    """The only place the real crypt32 path is exercised. The smoke
    checklist carries the same check for a release build."""
    assert dpapi.unprotect(dpapi.protect(b"secret")) == b"secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_dpapi.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.dpapi'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/dpapi.py`:

```python
"""CryptProtectData / CryptUnprotectData over ctypes. Windows only.

Imports cleanly on Linux, which is a hard requirement -- tokens.py imports
this module for its production defaults, so an import-time WinDLL would
take the whole subsystem's Linux test suite down. Structures and constants
live at module scope (ctypes.Structure is portable); every library binding
is built lazily inside a function, the layout preview/win32.py:1-9
establishes.

EVERY function below gets argtypes and restype. That is not decoration, and
preview/win32.py:10-16 records what it costs to omit: undeclared, ctypes
marshals a pointer-sized value as a 32-bit int, so a returned pbData would
be a truncated pointer and string_at would read from an address that is not
the buffer. Design probing hit that class of bug twice in the preview
subsystem, and both times the symptom appeared nowhere near the cause.

Why DPAPI rather than a plain JSON field: uploader.py:286-293 is explicit
that os.chmod on Windows only toggles the read-only attribute and that one
must "not assume the exposure is closed there". The real protection for a
plaintext file is the %LOCALAPPDATA% directory ACL, which gives nothing at
rest -- a stolen laptop, a disk image, a backup, or a %LOCALAPPDATA%
redirected into OneDrive all expose it. CryptProtectData is user-scoped and
closes that gap for about forty lines.
"""
import ctypes
import sys


class DATA_BLOB(ctypes.Structure):
    """crypt32's in/out buffer descriptor.

    c_uint32 rather than wintypes.DWORD so the definition is portable to
    the Linux import path; the two are the same width on every Windows ABI
    this ships to.
    """
    _fields_ = [("cbData", ctypes.c_uint32),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def available() -> bool:
    """Whether a token can be stored at all. Read by the controller before
    it tries, so a wrong answer here silently discards a refresh token."""
    return sys.platform == "win32"


def _require_windows() -> None:
    # A clean, explanatory error rather than an AttributeError raised from
    # inside ctypes three frames down.
    if not available():
        raise OSError("DPAPI is only available on Windows.")


def _crypt32():
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    # BOOL CryptProtectData(DATA_BLOB *in, LPCWSTR desc, DATA_BLOB *entropy,
    #                       PVOID reserved, PROMPTSTRUCT *prompt,
    #                       DWORD flags, DATA_BLOB *out)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p,
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    # CryptUnprotectData's second argument is LPWSTR* -- an OUT pointer to a
    # description string, not a string. Declared as c_void_p and passed
    # NULL, so crypt32 allocates nothing for it and there is nothing extra
    # to LocalFree.
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    return crypt32


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # HLOCAL LocalFree(HLOCAL) -- both pointer-sized. Undeclared, the
    # argument would be truncated to 32 bits and the free would either fail
    # or release an address that is not the one crypt32 allocated.
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return kernel32


def _call(func, name: str, data: bytes) -> bytes:
    # create_string_buffer with an explicit length gives a buffer of exactly
    # len(data) with no trailing NUL. It is bound to a local so it stays
    # alive for the duration of the call -- built inline it could be
    # collected while crypt32 still held the pointer.
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data),
                        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not func(ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
        raise OSError(ctypes.get_last_error(), f"{name} failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        # crypt32 allocates the output with LocalAlloc. Not freeing it leaks
        # for the process lifetime, once per token read.
        _kernel32().LocalFree(blob_out.pbData)


def protect(data: bytes) -> bytes:
    # The guard runs before _crypt32(), or the failure off Windows would be
    # an AttributeError on ctypes.WinDLL instead of the stated OSError.
    _require_windows()
    return _call(_crypt32().CryptProtectData, "CryptProtectData", data)


def unprotect(blob: bytes) -> bytes:
    _require_windows()
    return _call(_crypt32().CryptUnprotectData, "CryptUnprotectData", blob)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_dpapi.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/dpapi.py tests/test_eveskills_dpapi.py
git commit -m "feat(eveskills): DPAPI bindings with lazy WinDLL and full argtypes"
```

---

#### Cycle B — `tokens.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_tokens.py`:

```python
"""Wrap and unwrap, with the crypt callables injected.

Injection is what keeps this testable on Linux while only dpapi.py is
Windows-only, and it is the same keyword-only-with-a-production-default
seam discord.py:196-197 uses for its transport.
"""
from obs_youtube_uploader.eveskills import tokens


def _reverse_protect(data: bytes) -> bytes:
    """A stand-in cipher: reversible, and visibly not the plaintext."""
    return bytes(reversed(data))


def _reverse_unprotect(blob: bytes) -> bytes:
    return bytes(reversed(blob))


def test_wrap_then_unwrap_round_trips():
    blob = tokens.wrap("secret-refresh-token", protect=_reverse_protect)
    assert tokens.unwrap(blob, unprotect=_reverse_unprotect) == \
        "secret-refresh-token"


def test_the_wrapped_form_is_ascii_text():
    """It is stored as a JSON string field in the state document, so it must
    survive json.dumps/loads unchanged and must not carry raw bytes."""
    blob = tokens.wrap("secret-refresh-token", protect=_reverse_protect)
    assert blob.isascii()
    assert "secret" not in blob


def test_a_unicode_token_round_trips():
    """The token is opaque to us. Nothing may assume it is ASCII."""
    blob = tokens.wrap("tok-é中", protect=_reverse_protect)
    assert tokens.unwrap(blob, unprotect=_reverse_unprotect) == \
        "tok-é中"


def test_unwrap_of_an_empty_blob_is_none():
    """"" is how the state document spells "this character has no stored
    token", which is a normal state after a definitive auth failure."""
    assert tokens.unwrap("", unprotect=_reverse_unprotect) is None


def test_unwrap_returns_none_when_decryption_fails():
    """A blob that will not decrypt costs ONE character a re-authentication.
    Raising here would propagate out of the state load and make the whole
    document unloadable, taking every other character's authorisation with
    it -- which is exactly the failure that putting the tokens in the same
    document was meant to make impossible."""
    def boom(_blob):
        raise OSError(13, "The data is invalid")

    assert tokens.unwrap("QUJD", unprotect=boom) is None


def test_unwrap_returns_none_on_malformed_base64():
    """A truncated or hand-edited blob never reaches the crypt call."""
    assert tokens.unwrap("!!!not base64!!!",
                         unprotect=_reverse_unprotect) is None


def test_unwrap_returns_none_when_the_plaintext_is_not_utf8():
    """DPAPI can succeed on a blob written by something else entirely. Its
    output is then arbitrary bytes, not our token."""
    assert tokens.unwrap("QUJD", unprotect=lambda _b: b"\xff\xfe\x00") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.tokens'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/tokens.py`:

```python
"""Refresh-token wrapping for storage inside the state document.

Only the refresh token is wrapped; the roster metadata beside it stays
plaintext. That split is deliberate: a corrupt or undecryptable blob costs
one character a re-authentication rather than making the whole document
unparseable.

The crypt callables are injected with production defaults, so everything
here -- including the undecryptable-blob path -- is tested on Linux while
only dpapi.py is Windows-only.

What this does NOT buy, stated so nobody reads more into it: against
malware running as the same user, DPAPI, Credential Manager and a plain
file are equivalent. CryptUnprotectData succeeds for that user with no
prompt. This is a defence for data at rest -- a stolen laptop, a disk
image, a backup, a %LOCALAPPDATA% redirected into OneDrive -- not against
local code execution.
"""
import base64
import binascii

from . import dpapi


def wrap(token: str, *, protect=dpapi.protect) -> str:
    """Encrypt *token* and return it as base64 text.

    Text, not bytes, because the result is stored as a JSON string field in
    the state document.
    """
    return base64.b64encode(protect(token.encode("utf-8"))).decode("ascii")


def unwrap(blob: str, *, unprotect=dpapi.unprotect):
    """Decrypt *blob*, or return None if it cannot be read.

    None rather than an exception, and the except is deliberately broad.
    This is called while loading the state document, once per character. A
    blob fails to decrypt for reasons entirely outside our control -- the
    file was copied from another machine or another Windows account, the
    user's profile was recreated, a backup predates a key change, or the
    blob was hand-edited. Every one of those costs that character a
    re-authentication, which the UI already handles with a banner. Letting
    it propagate would take down the load and with it every OTHER
    character's authorisation, which is precisely the failure that putting
    the tokens in this document was meant to make impossible.
    """
    if not blob:
        return None
    try:
        # validate=True so stray characters are rejected here rather than
        # silently skipped, producing a shorter blob that then fails inside
        # crypt32 with a much less obvious message.
        raw = base64.b64decode(blob.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return None
    try:
        return unprotect(raw).decode("utf-8")
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_tokens.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/tokens.py tests/test_eveskills_tokens.py
git commit -m "feat(eveskills): wrap/unwrap refresh tokens with injected crypt"
```

---

### Task 7: `esi.py` — the ESI client

**Files:**
- Create: `obs_youtube_uploader/eveskills/esi.py`
- Test: `tests/test_eveskills_esi.py`

**Interfaces:**

- Consumes (from Task 1, `application.py`):

```python
ESI_BASE = "https://esi.evetech.net"
ESI_COMPATIBILITY_DATE = "2026-08-12"
USER_AGENT: str
```

- Produces:

```python
MAX_ATTEMPTS = 3
MAX_ERROR_BODY_BYTES = 8192
MAX_SUCCESS_BODY_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = frozenset({408, 420, 429, 500, 502, 503, 504})
TIMEOUT_S = 20.0

@dataclass(frozen=True)
class EsiResponse:
    status: int
    data: object | None
    error: str
    etag: str
    method: str
    path: str

    @property
    def ok(self) -> bool            # 200 <= status < 300
    @property
    def not_modified(self) -> bool  # status == 304

def validate_path(path: str) -> str     # returns path, raises ValueError

class EsiClient:
    def __init__(self, *, user_agent: str,
                 transport=_default_transport,
                 sleep=time.sleep) -> None
    def get(self, path: str, *, token: str | None = None,
            etag: str | None = None) -> EsiResponse
    def post(self, path: str, body: object, *,
             token: str | None = None) -> EsiResponse
```

---

#### Cycle A — path validation

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_esi.py`:

```python
"""Path hardening, retries, backoff order, redaction, and the synthetic 503.

Transport and sleep are injected, matching discord.py:196-197,224. HTTP is
stdlib urllib.request: this app has no requests dependency and discord.py is
the house pattern for doing without one.
"""
import pytest

from obs_youtube_uploader.eveskills import esi


def test_a_normal_path_is_returned_unchanged():
    assert esi.validate_path("/v3/universe/types/3300/") == \
        "/v3/universe/types/3300/"


def test_a_path_without_a_trailing_slash_is_accepted():
    assert esi.validate_path("/v3/universe/types/3300") == \
        "/v3/universe/types/3300"


@pytest.mark.parametrize("path", [
    "characters/1/skills/",          # no leading slash
    "//evil.example/skills/",        # protocol-relative: another authority
    "https://evil.example/skills/",  # absolute URL
    "/v3\\universe/",                # backslash
    "/v3/universe/?page=2",          # query
    "/v3/universe/#frag",            # fragment
    "/v3/universe/\x00/",            # NUL
    "/v3//universe/",                # empty interior segment
    "/v3/../admin/",                 # dot-dot traversal
    "/v3/./universe/",               # single dot
    "/v3/universe types/",           # space
    "/v3/universe%2Ftypes/",         # percent-encoding
    "/v3/universe/types//",          # empty trailing segment
    "/",                             # no segments
    "",
])
def test_hostile_paths_are_rejected(path):
    """These are all the ways a caller-built path could be steered off the
    intended endpoint. The Authorization header rides on every request, so a
    path that reaches another host hands a live access token to it."""
    with pytest.raises(ValueError):
        esi.validate_path(path)


def test_a_non_string_path_is_rejected():
    with pytest.raises(ValueError):
        esi.validate_path(None)


def test_query_strings_are_structurally_impossible():
    """Recorded as a test rather than only a comment: adding a paging
    parameter to any ESI call requires a deliberate change HERE first, and a
    future author will find this failing before they find the comment."""
    with pytest.raises(ValueError):
        esi.validate_path("/v3/universe/ids/?page=2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_esi.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.esi'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/esi.py`:

```python
"""Read-only ESI client: path hardening, bounded retries, ETags.

Transport and sleep are injected with production defaults, the seam
discord.py:196-197,224 establishes, which is what lets the whole retry and
backoff ladder be tested headless with no real sleeps.

Nothing here writes to ESI. The two scopes this application requests are
read-only, and the only POST is the unauthenticated universe/ids lookup.
"""
import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import application

MAX_ATTEMPTS = 3
MAX_ERROR_BODY_BYTES = 8192
MAX_SUCCESS_BODY_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = frozenset({408, 420, 429, 500, 502, 503, 504})
TIMEOUT_S = 20.0

# Server-suggested waits are honoured but capped: a misconfigured or hostile
# Retry-After of 86400 would otherwise hold a refresh worker for a day, and
# the user cannot tell that apart from a crash.
MAX_BACKOFF_S = 30.0
BASE_BACKOFF_S = 0.650
NETWORK_BACKOFF_S = 0.500

# Segments are restricted to this set, which is what makes a query string, a
# fragment, an encoded slash, and a traversal all structurally impossible
# rather than merely filtered. Adding a paging parameter to any ESI call in
# this package therefore requires a deliberate change here first.
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_VERSION_SEGMENT = re.compile(r"^v\d+$")


def validate_path(path: str) -> str:
    """Return *path* unchanged, or raise ValueError.

    Every authenticated request carries an Authorization header, so a path
    that can be steered to another host hands a live access token to that
    host. The checks are ported whole from TriffView and are load-bearing.
    """
    if not isinstance(path, str):
        raise ValueError("ESI path must be a string.")
    if not path.startswith("/"):
        raise ValueError("ESI path must start with '/'.")
    # "//host/x" is a protocol-relative URL: joined to a base it resolves to
    # a different authority while still looking like a path.
    if path.startswith("//"):
        raise ValueError("ESI path must not start with '//'.")
    if "://" in path:
        raise ValueError("ESI path must not be an absolute URL.")
    for forbidden, label in (("\\", "backslash"), ("?", "query"),
                             ("#", "fragment"), ("\x00", "NUL")):
        if forbidden in path:
            raise ValueError(f"ESI path must not contain a {label}.")

    body = path[1:]
    # Exactly one optional trailing slash: ESI's own routes carry it
    # ("/v3/universe/ids/"), but a second one is an empty segment.
    if body.endswith("/"):
        body = body[:-1]
    if not body:
        raise ValueError("ESI path must name at least one segment.")
    for segment in body.split("/"):
        if not segment:
            raise ValueError("ESI path segments must not be empty.")
        if segment in (".", ".."):
            raise ValueError("ESI path must not contain '.' or '..'.")
        if not _SEGMENT.match(segment):
            raise ValueError(
                f"ESI path segment {segment!r} has characters outside "
                "[A-Za-z0-9_-].")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_esi.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/esi.py tests/test_eveskills_esi.py
git commit -m "feat(eveskills): ESI path hardening"
```

---

#### Cycle B — requests, headers, and 304

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_esi.py`:

```python
import io
import json
import urllib.error
from email.message import Message


def _headers(**pairs) -> Message:
    """An email.message.Message is exactly what urllib hands back as
    `response.headers`, including its case-insensitive lookup."""
    message = Message()
    for key, value in pairs.items():
        message[key.replace("_", "-")] = str(value)
    return message


class _Response:
    """The minimal shape urllib returns: a context manager with status,
    headers, and read()."""

    def __init__(self, status, payload=b"", headers=None):
        self.status = status
        self.headers = headers if headers is not None else Message()
        self._stream = io.BytesIO(payload)

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(
        "https://esi.evetech.net/x", code, "err",
        headers if headers is not None else Message(), io.BytesIO(body))


class FakeTransport:
    """Records requests and replays a scripted list of outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSleep:
    """Records the delays asked for without spending any wall time."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def _client(outcomes, sleep=None):
    return esi.EsiClient(user_agent="TestAgent/1.0",
                         transport=FakeTransport(outcomes),
                         sleep=sleep or FakeSleep())


def test_a_successful_get_returns_parsed_json():
    client = _client([_Response(200, b'{"skills": []}')])
    response = client.get("/v6/characters/1/skills/")
    assert response.ok is True
    assert response.data == {"skills": []}
    assert response.error == ""


def test_every_request_carries_the_required_headers():
    """User-Agent identifies the app to CCP, X-Compatibility-Date pins the
    schema, and Accept stops a proxy negotiating something else."""
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="TestAgent/1.0", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/")
    headers = transport.requests[0].headers
    assert headers["User-agent"] == "TestAgent/1.0"
    assert headers["Accept"] == "application/json"
    assert headers["X-compatibility-date"] == \
        esi.application.ESI_COMPATIBILITY_DATE
    assert "Authorization" not in headers


def test_a_token_becomes_a_bearer_header():
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/", token="tok")
    assert transport.requests[0].headers["Authorization"] == "Bearer tok"


def test_an_etag_becomes_an_if_none_match_header():
    """The one place this port knowingly improves on TriffView, which sends
    no conditional requests at all: forty characters is eighty full
    refetches per click, charged against the error-limit budget to
    re-download data that mostly has not changed."""
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/", etag='W/"abc"')
    assert transport.requests[0].headers["If-none-match"] == 'W/"abc"'


def test_a_304_carries_no_data_and_keeps_the_sent_etag():
    """304 means "what you have is current". data must be None so a caller
    cannot mistake it for an empty skill list, and the etag must survive so
    the next refresh still sends it -- a 304 body carries no new validator
    to replace it with."""
    client = _client([_Response(304)])
    response = client.get("/v6/characters/1/skills/", etag='W/"abc"')
    assert response.not_modified is True
    assert response.ok is False
    assert response.data is None
    assert response.etag == 'W/"abc"'


def test_a_response_etag_is_captured():
    client = _client([_Response(200, b"{}", _headers(ETag='W/"new"'))])
    assert client.get("/v6/characters/1/skills/").etag == 'W/"new"'


def test_the_method_and_path_come_back_on_the_response():
    """The controller commits both halves of a snapshot together, so it has
    to be able to tell which half a response belongs to."""
    client = _client([_Response(200, b"{}")])
    response = client.get("/v6/characters/1/skills/")
    assert (response.method, response.path) == \
        ("GET", "/v6/characters/1/skills/")


def test_post_sends_a_json_body():
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.post("/v3/universe/ids/", ["Navigation"])
    request = transport.requests[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == ["Navigation"]
    assert request.headers["Content-type"] == "application/json"


def test_an_invalid_path_raises_before_any_request_is_made():
    """Path validation guards a programming error, not a runtime condition,
    so it raises rather than returning a response -- and it must fire before
    the transport sees anything."""
    transport = FakeTransport([])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    with pytest.raises(ValueError):
        client.get("/v3/universe/?page=2")
    assert transport.requests == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_esi.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.esi' has no attribute 'EsiClient'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/esi.py`:

```python
def _default_transport(request, timeout=None):
    return urllib.request.urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class EsiResponse:
    status: int
    data: object
    error: str
    etag: str
    method: str
    path: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class EsiClient:
    def __init__(self, *, user_agent: str, transport=_default_transport,
                 sleep=time.sleep) -> None:
        self._user_agent = user_agent
        self._transport = transport
        self._sleep = sleep

    def get(self, path: str, *, token=None, etag=None) -> EsiResponse:
        return self._request("GET", path, token=token, etag=etag)

    def post(self, path: str, body, *, token=None) -> EsiResponse:
        return self._request("POST", path, body=body, token=token)

    def _request(self, method: str, path: str, *, body=None, token=None,
                 etag=None) -> EsiResponse:
        # Raises, deliberately: a bad path is a bug in the caller, not a
        # runtime condition, and it must never reach the network.
        validate_path(path)
        url = application.ESI_BASE + path
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "X-Compatibility-Date": application.ESI_COMPATIBILITY_DATE,
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if etag:
            headers["If-None-Match"] = etag

        request = urllib.request.Request(url, data=payload, headers=headers,
                                         method=method)
        with self._transport(request, timeout=TIMEOUT_S) as response:
            return self._read(response, method, path, etag)

    @staticmethod
    def _read(response, method: str, path: str, sent_etag) -> EsiResponse:
        status = getattr(response, "status", 200)
        response_etag = response.headers.get("ETag", "") or ""
        if status == 304:
            # data stays None: an empty dict here would be indistinguishable
            # from a character who genuinely has no skills, and that reads
            # as data loss in the roster.
            return EsiResponse(304, None, "", sent_etag or response_etag,
                               method, path)
        # Read one byte past the cap so oversize is detectable without
        # buffering the whole thing first.
        raw = response.read(MAX_SUCCESS_BODY_BYTES + 1)
        if len(raw) > MAX_SUCCESS_BODY_BYTES:
            raise ValueError(
                f"ESI response for {path} exceeded "
                f"{MAX_SUCCESS_BODY_BYTES} bytes.")
        data = json.loads(raw.decode("utf-8")) if raw.strip() else None
        return EsiResponse(status, data, "", response_etag, method, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_esi.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/esi.py tests/test_eveskills_esi.py
git commit -m "feat(eveskills): ESI request construction, headers, and 304 handling"
```

---

#### Cycle C — retries, backoff order, redaction, synthetic 503

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_esi.py`:

```python
import socket


def test_a_retryable_status_is_retried_and_then_succeeds():
    sleep = FakeSleep()
    client = _client([_http_error(503), _Response(200, b'{"ok": 1}')], sleep)
    response = client.get("/v6/characters/1/skills/")
    assert response.data == {"ok": 1}
    assert sleep.delays == [pytest.approx(0.650)]


def test_a_non_retryable_status_returns_immediately():
    """401 and 403 are definitive -- they mean re-authenticate, and burning
    two more requests against the error-limit budget to confirm it costs the
    other characters queued behind this one in the refresh."""
    transport = FakeTransport([_http_error(403, b'{"error":"forbidden"}')])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.get("/v6/characters/1/skills/")
    assert response.status == 403
    assert len(transport.requests) == 1


def test_backoff_grows_with_the_attempt():
    sleep = FakeSleep()
    _client([_http_error(500), _http_error(500), _http_error(500)],
            sleep).get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650), pytest.approx(1.300)]


def test_retry_after_wins_over_the_default_backoff():
    sleep = FakeSleep()
    client = _client([_http_error(429, headers=_headers(Retry_After=7)),
                      _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(7.0)]


def test_the_error_limit_reset_is_used_when_retry_after_is_absent():
    """420 is ESI's error-limited status and carries the reset rather than
    Retry-After. Ignoring it is how a client gets its budget zeroed."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(420, headers=_headers(X_Esi_Error_Limit_Reset=12)),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(12.0)]


def test_retry_after_wins_over_the_error_limit_reset():
    """The order is asserted rather than assumed: Retry-After is a specific
    instruction about this request, the reset is the window before the error
    budget refills."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(429, headers=_headers(Retry_After=3,
                                           X_Esi_Error_Limit_Reset=25)),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(3.0)]


def test_a_server_suggested_wait_is_capped():
    """A hostile or misconfigured Retry-After would otherwise hold a refresh
    worker for a day, which the user cannot tell from a crash."""
    sleep = FakeSleep()
    client = _client([_http_error(429, headers=_headers(Retry_After=86400)),
                      _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(esi.MAX_BACKOFF_S)]


def test_a_non_numeric_retry_after_falls_through_to_the_default():
    """Retry-After may legally be an HTTP-date. That form is not parsed
    here, and the fallback must be the ladder rather than a crash."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(503,
                     headers=_headers(Retry_After="Wed, 21 Oct 2026 07:28:00 GMT")),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650)]


def test_exhausting_the_retries_returns_a_synthetic_503():
    """Returns, never raises: a refresh iterates characters sequentially,
    and one exhausted character must record an error and let the loop go on
    to the next.

    The caller must NOT read this 503 as "ESI said 503" -- it is synthesised
    here, and the upstream failure may have been any status in the retry set
    or no response at all."""
    transport = FakeTransport([_http_error(500)] * esi.MAX_ATTEMPTS)
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.get("/v6/characters/1/skills/")
    assert response.status == 503
    assert response.ok is False
    assert response.error
    assert len(transport.requests) == esi.MAX_ATTEMPTS


def test_network_errors_retry_on_their_own_ladder():
    """A connection that never opened produced no headers to read a
    server-suggested wait from, so the ladder is fixed and short."""
    sleep = FakeSleep()
    client = _client([urllib.error.URLError("no route"),
                      socket.timeout("timed out"),
                      _Response(200, b"{}")], sleep)
    assert client.get("/v6/characters/1/skills/").ok is True
    assert sleep.delays == [pytest.approx(0.5), pytest.approx(1.0)]


def test_an_oserror_from_the_transport_is_retried_not_raised():
    sleep = FakeSleep()
    client = _client([OSError("connection reset"), _Response(200, b"{}")],
                     sleep)
    assert client.get("/v6/characters/1/skills/").ok is True


def test_the_access_token_is_redacted_from_error_text():
    """The error string reaches a log and a per-character UI row. A bearer
    token echoed back by an ESI error page or a proxy would be written to
    both, in plain text, where it stays until log rotation."""
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"
    body = json.dumps({"error": f"invalid token {token}"}).encode("utf-8")
    client = _client([_http_error(400, body)])
    response = client.get("/v6/characters/1/skills/", token=token)
    assert token not in response.error
    assert "[redacted]" in response.error


def test_an_oversized_error_body_is_truncated():
    """An error page can be a full HTML document. 8 KiB is enough to see
    what happened and small enough not to fill the log."""
    body = b"x" * (esi.MAX_ERROR_BODY_BYTES * 2)
    response = _client([_http_error(400, body)]).get("/v6/characters/1/skills/")
    assert response.error.endswith("... [truncated]")
    assert len(response.error) < esi.MAX_ERROR_BODY_BYTES + 200


def test_an_oversized_success_body_raises():
    """Unlike an error body this is not truncated: half a JSON document is
    not parseable, and silently returning None would look to the caller like
    an empty skill list."""
    payload = b'{"pad": "' + b"y" * (esi.MAX_SUCCESS_BODY_BYTES + 10) + b'"}'
    with pytest.raises(ValueError):
        _client([_Response(200, payload)]).get("/v6/characters/1/skills/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_esi.py -v`
Expected: FAIL with `IndexError: pop from empty list` (the client makes exactly one attempt and never retries)

- [ ] **Step 3: Write minimal implementation**

In `obs_youtube_uploader/eveskills/esi.py`, add the three helpers below the
existing constants, then replace `EsiClient._request` with the retrying form:

```python
def _redact(text: str, token) -> str:
    """Strip an access token out of anything that could reach a log.

    Guarded on length because a very short token would be a common
    substring and redacting it would mangle unrelated text. Real EVE access
    tokens run to hundreds of characters, so the guard never fires in
    production -- it exists so a test fixture using "tok" cannot make this
    function destructive.
    """
    if token and len(token) >= 8:
        return text.replace(token, "[redacted]")
    return text


def _header_seconds(headers, name: str):
    """A header's value as seconds, or None.

    Retry-After may legally be an HTTP-date. That form is deliberately not
    parsed: the fallback ladder is a fine answer, and a date parser here
    would be more code than the case is worth. Returning None routes it
    there.
    """
    if headers is None:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def _is_ids_route(path: str) -> bool:
    """Whether *path* is the universe/ids batch lookup.

    The only POST this package retries. A retried non-idempotent request is
    the classic way to duplicate a write, so the allowance is a route check
    rather than a method check -- this package makes no writes today and the
    guard keeps that true if one is ever added. A leading version segment is
    tolerated so a bump from /v3/ to /v4/ does not silently lose the retry,
    which would surface as an intermittently failing first refresh that
    nobody connects back to this line.
    """
    segments = [s for s in path.split("/") if s]
    if segments and _VERSION_SEGMENT.match(segments[0]):
        segments = segments[1:]
    return tuple(segments) == ("universe", "ids")
```

```python
    def _request(self, method: str, path: str, *, body=None, token=None,
                 etag=None) -> EsiResponse:
        validate_path(path)
        url = application.ESI_BASE + path
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "X-Compatibility-Date": application.ESI_COMPATIBILITY_DATE,
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if etag:
            headers["If-None-Match"] = etag

        retryable_method = method == "GET" or _is_ids_route(path)
        last_error = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(url, data=payload,
                                             headers=headers, method=method)
            try:
                with self._transport(request, timeout=TIMEOUT_S) as response:
                    return self._read(response, method, path, etag)
            except urllib.error.HTTPError as exc:
                # HTTPError subclasses URLError subclasses OSError, so this
                # clause MUST come first. Below the network clause, a 404
                # would be treated as a connection failure and retried three
                # times against the error-limit budget.
                text = self._error_text(exc, token)
                if exc.code in RETRY_STATUSES and retryable_method:
                    last_error = text
                    if attempt < MAX_ATTEMPTS:
                        self._sleep(self._backoff(exc.headers, attempt))
                    continue
                return EsiResponse(exc.code, None, text, "", method, path)
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                # No response, so no headers to read a suggested wait from.
                # The ladder is fixed and short: a refresh is sequential, so
                # every second spent here delays every character behind it.
                last_error = _redact(f"Network error: {exc}", token)
                if attempt < MAX_ATTEMPTS:
                    self._sleep(NETWORK_BACKOFF_S * attempt)
                continue

        # Exhausted. Return rather than raise: a refresh iterates characters
        # sequentially and one exhausted character must record an error and
        # let the loop continue to the next.
        #
        # The 503 is SYNTHETIC -- it did not necessarily come from ESI. The
        # upstream failure may have been any status in RETRY_STATUSES, or no
        # response at all, and a caller reading it as an upstream outage
        # will be wrong about the cause.
        return EsiResponse(
            503, None,
            last_error or f"No response after {MAX_ATTEMPTS} attempts.",
            "", method, path)

    @staticmethod
    def _backoff(headers, attempt: int) -> float:
        """Retry-After, then X-Esi-Error-Limit-Reset, then the ladder.

        The order is not arbitrary. Retry-After is a specific instruction
        about this request; the reset is the window before the shared error
        budget refills. Preferring the budget window when a specific wait
        was given would sit on the worker thread longer than asked.
        """
        for name in ("Retry-After", "X-Esi-Error-Limit-Reset"):
            seconds = _header_seconds(headers, name)
            if seconds is not None:
                return min(seconds, MAX_BACKOFF_S)
        return BASE_BACKOFF_S * attempt

    @staticmethod
    def _error_text(exc, token) -> str:
        try:
            raw = exc.read(MAX_ERROR_BODY_BYTES + 1)
        except Exception:
            # HTTPError is not guaranteed to carry a readable body, and a
            # failure to read the explanation must not replace the status we
            # already have with a traceback.
            raw = b""
        text = raw.decode("utf-8", "replace")
        if len(raw) > MAX_ERROR_BODY_BYTES:
            # Truncated rather than dropped: the first 8 KiB of an error
            # page is where the reason is, and the rest is usually markup.
            text = text[:MAX_ERROR_BODY_BYTES] + "... [truncated]"
        return _redact(f"HTTP {exc.code}: {text}".strip(), token)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_esi.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/esi.py tests/test_eveskills_esi.py
git commit -m "feat(eveskills): ESI retries, backoff order, redaction, synthetic 503"
```

---

#### Cycle D — the POST retry restriction

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_esi.py`:

```python
def test_a_post_to_the_ids_route_is_retried():
    """The batch name lookup is idempotent and is the only POST this package
    makes. A first refresh over a large plan set depends on it."""
    transport = FakeTransport([_http_error(503), _Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    assert client.post("/v3/universe/ids/", ["Navigation"]).ok is True
    assert len(transport.requests) == 2


def test_a_version_bump_keeps_the_ids_route_retryable():
    """Matching the literal "/v3/universe/ids/" would silently lose the
    retry the day CCP ships v4, and the symptom would be an intermittent
    first refresh nobody connects back to the route check."""
    transport = FakeTransport([_http_error(503), _Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    assert client.post("/v4/universe/ids/", ["Navigation"]).ok is True
    assert len(transport.requests) == 2


def test_a_post_to_any_other_route_is_not_retried():
    """A retried non-idempotent POST is the classic way to duplicate a
    write. This package makes no writes today, and the guard is a route
    check rather than a method check so that stays true if one is added."""
    transport = FakeTransport([_http_error(503)])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.post("/v1/ui/openwindow/", {})
    assert response.status == 503
    assert len(transport.requests) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_esi.py -v`
Expected: with `_is_ids_route` written as a literal path comparison, FAIL
with `assert 1 == 2` on `test_a_version_bump_keeps_the_ids_route_retryable`.
Write it that way first if you want to see the red, then apply Step 3.

- [ ] **Step 3: Write minimal implementation**

The segment form in `obs_youtube_uploader/eveskills/esi.py`:

```python
def _is_ids_route(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    if segments and _VERSION_SEGMENT.match(segments[0]):
        segments = segments[1:]
    return tuple(segments) == ("universe", "ids")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_esi.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/esi.py tests/test_eveskills_esi.py
git commit -m "test(eveskills): pin the POST retry to the universe/ids route"
```

---

### Task 8: `skillids.py` — skill name to type id

**Files:**
- Create: `obs_youtube_uploader/eveskills/skillids.py`
- Test: `tests/test_eveskills_skillids.py`

**Interfaces:**

- Consumes (from Task 7, `esi.py`):

```python
@dataclass(frozen=True)
class EsiResponse:
    status: int
    data: object | None
    error: str
    etag: str
    method: str
    path: str
    @property
    def ok(self) -> bool

class EsiClient:
    def get(self, path: str, *, token=None, etag=None) -> EsiResponse
    def post(self, path: str, body, *, token=None) -> EsiResponse
```

- Consumes (existing repo module): `atomicio.write_atomic`.
- Produces:

```python
SKILL_CATEGORY_ID = 16
BATCH_SIZE = 500
MAX_ENTRIES = 20_000
CACHE_VERSION = 1
RESOLVE_WORKERS = 4

class SkillIdCache:
    def __init__(self, mapping: Mapping[str, int] | None = None) -> None
    def get(self, name: str) -> int | None      # case-insensitive
    def type_ids(self) -> dict[str, int]        # case-insensitive mapping
    def unresolved(self, names: Iterable[str]) -> list[str]
    def merge(self, entries: Mapping[str, int]) -> int   # count added

def load(path: Path) -> tuple[SkillIdCache, list[str]]
def save(cache: SkillIdCache, path: Path) -> None
def resolve(cache: SkillIdCache, names: Sequence[str], client: EsiClient, *,
            max_workers: int = RESOLVE_WORKERS) -> dict[str, str]
    # returns name -> failure reason for names that did NOT resolve
```

---

#### Cycle A — the cache

- [ ] **Step 1: Write the failing test**

Create `tests/test_eveskills_skillids.py`:

```python
"""There is no bundled SDE, so skill names become type ids over ESI.

The cache is keyed case-insensitively and NEVER invalidates -- a deliberate
inheritance from TriffView, because EVE type ids do not change and
re-checking would spend requests to learn nothing. The honest cost is that a
name resolved wrongly stays wrong until the cache file is deleted.
"""
from obs_youtube_uploader.eveskills import skillids


def test_lookup_is_case_insensitive():
    """All comparisons on skill names in this subsystem are
    case-insensitive, and a plan file is hand-typed."""
    cache = skillids.SkillIdCache({"Navigation": 3449})
    assert cache.get("navigation") == 3449
    assert cache.get("NAVIGATION") == 3449


def test_lookup_ignores_surrounding_whitespace():
    """The plan parser splits a line at its LAST whitespace, so a name
    arriving with a trailing tab would otherwise be a different key that
    never resolves."""
    assert skillids.SkillIdCache({" Navigation ": 3449}).get("Navigation") \
        == 3449


def test_an_unknown_name_is_none():
    """None is what makes the requirement score Unknown, which poisons the
    whole plan's readiness for every character -- so it must be a distinct
    answer, never 0."""
    assert skillids.SkillIdCache().get("Nope") is None


def test_type_ids_returns_a_case_insensitive_mapping():
    """The evaluator receives this directly as its skill_ids argument and
    lowercases its lookups against it, so the keys must already be folded."""
    ids = skillids.SkillIdCache({"Navigation": 3449}).type_ids()
    assert ids == {"navigation": 3449}


def test_unresolved_reports_names_the_cache_does_not_hold():
    cache = skillids.SkillIdCache({"Navigation": 3449})
    assert cache.unresolved(["Navigation", "Evasive Maneuvering"]) == \
        ["Evasive Maneuvering"]


def test_unresolved_dedupes_and_keeps_the_first_spelling():
    """Forty plans share most of their skills. A repeated name spends a slot
    out of the 500-name batch and can come back with two answers for one
    key."""
    cache = skillids.SkillIdCache()
    assert cache.unresolved(["Navigation", "navigation", "NAVIGATION"]) == \
        ["Navigation"]


def test_merge_reports_how_many_it_added():
    cache = skillids.SkillIdCache()
    assert cache.merge({"Navigation": 3449, "Acceleration Control": 3452}) == 2


def test_merge_refuses_to_overwrite_an_existing_key():
    """The cache never invalidates, so a second answer for a key already
    held is either identical or wrong. Neither is worth a write, and taking
    the newer one would let a single bad ESI response silently replace a
    good id that nothing will ever re-check."""
    cache = skillids.SkillIdCache({"Navigation": 3449})
    assert cache.merge({"navigation": 999}) == 0
    assert cache.get("Navigation") == 3449


def test_merge_rejects_non_positive_boolean_and_string_ids():
    """bool is an int subclass, so a JSON `true` would otherwise be stored
    as type id 1 -- a real inventory type, and not a skill."""
    cache = skillids.SkillIdCache()
    assert cache.merge({"A": 0, "B": -1, "C": True, "D": "3449"}) == 0


def test_the_cache_is_capped():
    """A hand-edited or corrupted file must not turn a launch into a
    multi-megabyte dict build."""
    cache = skillids.SkillIdCache()
    cache.merge({f"Skill {n}": n + 1
                 for n in range(skillids.MAX_ENTRIES + 100)})
    assert len(cache.type_ids()) == skillids.MAX_ENTRIES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.skillids'`

- [ ] **Step 3: Write minimal implementation**

Create `obs_youtube_uploader/eveskills/skillids.py`:

```python
"""Skill name -> type id, resolved over ESI and cached on disk.

There is no bundled SDE. Names become type ids in three steps -- a batch
POST to universe/ids, a per-type lookup for its group, and a per-group
lookup for its category -- and only category 16 (Skill) enters the cache.

The cache never invalidates. EVE type ids do not change, so re-checking
would spend requests to learn nothing; the honest cost is that a name
resolved wrongly stays wrong until the file is deleted.
"""
import concurrent.futures
import json
import os
import threading
import time
from pathlib import Path

from .. import atomicio

SKILL_CATEGORY_ID = 16
BATCH_SIZE = 500
MAX_ENTRIES = 20_000
CACHE_VERSION = 1
RESOLVE_WORKERS = 4

# Exact strings: the UI shows them verbatim next to the requirement they
# explain, and the tests pin them.
REASON_NOT_RESOLVED = "Name was not resolved by ESI."
REASON_NO_GROUP = "Resolved type had no valid group."
REASON_NOT_A_SKILL = "Resolved inventory type is not in EVE's skill category."


def _key(name) -> str:
    """The case-insensitive cache key.

    Stripped as well as folded: the plan parser splits a line at its LAST
    whitespace, so a name arriving with a trailing tab is otherwise a
    different key that never resolves.
    """
    if not isinstance(name, str):
        return ""
    return name.strip().lower()


class SkillIdCache:
    def __init__(self, mapping=None) -> None:
        self._by_key: dict = {}
        if mapping:
            self.merge(mapping)

    def get(self, name: str):
        return self._by_key.get(_key(name))

    def type_ids(self) -> dict:
        # Folded keys, which is what "case-insensitive mapping" means to the
        # evaluator: it lowercases its lookups against exactly this dict.
        return dict(self._by_key)

    def unresolved(self, names) -> list:
        """Names not yet cached, deduped, first spelling wins.

        Deduping matters: forty plans share most of their skills, and a
        repeated name spends a slot out of the 500-name batch and can come
        back with two answers for one key.
        """
        out, seen = [], set()
        for name in names:
            key = _key(name)
            if not key or key in self._by_key or key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    def merge(self, entries) -> int:
        """Add entries that pass validation, returning the count added.

        Never overwrites. The cache does not invalidate, so a second answer
        for a key already held is either identical or wrong -- and taking
        the newer one would let one bad ESI response silently replace a good
        id that nothing will ever re-check.
        """
        added = 0
        for name, type_id in entries.items():
            if len(self._by_key) >= MAX_ENTRIES:
                break
            key = _key(name)
            if not key or key in self._by_key:
                continue
            # bool first: it is an int subclass, so a JSON `true` would
            # otherwise be stored as type id 1, which is a real inventory
            # type and is not a skill.
            if isinstance(type_id, bool) or not isinstance(type_id, int):
                continue
            if type_id <= 0:
                continue
            self._by_key[key] = type_id
            added += 1
        return added
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/skillids.py tests/test_eveskills_skillids.py
git commit -m "feat(eveskills): case-insensitive skill id cache"
```

---

#### Cycle B — the disk format

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_skillids.py`:

```python
import json


def test_save_then_load_round_trips(tmp_path):
    target = tmp_path / "eve_skills_cache.json"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    loaded, warnings = skillids.load(target)
    assert loaded.get("navigation") == 3449
    assert warnings == []


def test_load_of_a_missing_file_is_empty_and_silent(tmp_path):
    loaded, warnings = skillids.load(tmp_path / "absent.json")
    assert loaded.type_ids() == {}
    assert warnings == []


def test_an_entry_omitting_category_id_is_rejected(tmp_path):
    """The one deliberate divergence from the source, and the reason it is a
    test rather than only a comment.

    TriffView's ValidatedSkillType carries `CategoryId = 16` as a CONSTRUCTOR
    DEFAULT (SkillIdCache.cs:110-121), so a cache entry that omits
    categoryId deserialises to 16 and passes its own validation -- the field
    that is supposed to prove the type is a skill is supplied by the code
    doing the checking. This port requires the field explicitly: an entry
    that does not say it is a skill is not treated as one.
    """
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({
        "version": skillids.CACHE_VERSION,
        "entries": [{"name": "Navigation", "type_id": 3449},
                    {"name": "Evasive Maneuvering", "type_id": 3453,
                     "category_id": skillids.SKILL_CATEGORY_ID}],
    }), encoding="utf-8")
    loaded, _warnings = skillids.load(target)
    assert loaded.get("Navigation") is None
    assert loaded.get("Evasive Maneuvering") == 3453


def test_an_entry_with_the_wrong_category_is_rejected(tmp_path):
    """Category 16 is the whole point of the three-step resolution. An entry
    claiming any other category is hand-edited or a bug, and letting it
    through would score a non-skill requirement as trainable."""
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({
        "version": skillids.CACHE_VERSION,
        "entries": [{"name": "Rifter", "type_id": 587, "category_id": 6}],
    }), encoding="utf-8")
    loaded, _warnings = skillids.load(target)
    assert loaded.type_ids() == {}


def test_a_wrong_version_starts_empty_with_a_warning(tmp_path):
    """This file rebuilds completely by re-resolving, so refusing a format
    we do not understand costs one slow refresh and nothing else."""
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({"version": 99, "entries": []}),
                      encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings


def test_a_corrupt_cache_is_preserved_and_starts_empty(tmp_path):
    """Same preserve-and-warn posture as state.py, but with NO .bak tier.

    The asymmetry is deliberate and is the whole reason state.py has one:
    this file holds nothing that cannot be rebuilt -- deleting it costs one
    slower refresh while the names re-resolve. eve_skills.json holds the
    DPAPI-wrapped refresh tokens, which no refresh can reconstruct, so a
    single bad write there would cost every character's authorisation.
    """
    target = tmp_path / "cache.json"
    target.write_text("{ not json", encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings
    assert not target.exists()
    assert [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]


def test_no_bak_file_is_ever_written(tmp_path):
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"A": 1}), target)
    skillids.save(skillids.SkillIdCache({"B": 2}), target)
    assert [p.name for p in tmp_path.iterdir()] == ["cache.json"]


def test_malformed_entries_drop_individually(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({
        "version": skillids.CACHE_VERSION,
        "entries": [
            None, 7, {"type_id": 1, "category_id": 16},
            {"name": "Good", "type_id": 3449, "category_id": 16},
            {"name": "Bad", "type_id": "3449", "category_id": 16},
        ],
    }), encoding="utf-8")
    loaded, _warnings = skillids.load(target)
    assert loaded.type_ids() == {"good": 3449}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.skillids' has no attribute 'save'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/skillids.py`:

```python
def save(cache: SkillIdCache, path: Path) -> None:
    """Write the cache atomically. No .bak tier, deliberately.

    Everything in this file rebuilds by re-resolving names against ESI, so
    a lost cache costs one slower refresh. state.py keeps a backup because
    it holds the wrapped refresh tokens, which nothing can reconstruct.
    """
    document = {
        "version": CACHE_VERSION,
        # category_id is written on every entry so the load-time check has
        # something real to require. It is constant today; writing it is
        # what makes the requirement honest rather than tautological.
        "entries": [{"name": name, "type_id": type_id,
                     "category_id": SKILL_CATEGORY_ID}
                    for name, type_id in sorted(cache.type_ids().items())],
    }
    atomicio.write_atomic(Path(path), json.dumps(document, indent=2))


def load(path: Path) -> tuple:
    """Read the cache. Returns (cache, warnings) and never raises."""
    path = Path(path)
    warnings: list = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return SkillIdCache(), warnings
    except OSError as exc:
        warnings.append(f"{path.name} could not be read ({exc.strerror}); "
                        "skill names will be resolved again.")
        return SkillIdCache(), warnings

    try:
        raw = json.loads(text)
    except ValueError:
        # Moved aside, not left in place: otherwise it is re-read,
        # re-preserved and re-warned on every launch.
        stamp = time.strftime("%Y%m%d-%H%M%S")
        preserved = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            os.replace(path, preserved)
        except OSError:
            preserved = None
        warnings.append(
            f"{path.name} could not be read"
            + (f" and was preserved as {preserved.name}" if preserved else "")
            + "; skill names will be resolved again.")
        return SkillIdCache(), warnings

    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        warnings.append(
            f"{path.name} is not a format this version understands; "
            "skill names will be resolved again.")
        return SkillIdCache(), warnings

    entries = raw.get("entries")
    if not isinstance(entries, list):
        return SkillIdCache(), warnings

    accepted: dict = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        # The key must be PRESENT and equal to 16. A .get with a default of
        # SKILL_CATEGORY_ID here would reproduce exactly the TriffView
        # constructor-default bug this port diverges from.
        if item.get("category_id") != SKILL_CATEGORY_ID:
            continue
        name = item.get("name")
        type_id = item.get("type_id")
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(type_id, bool) or not isinstance(type_id, int):
            continue
        if type_id <= 0:
            continue
        accepted[name] = type_id

    cache = SkillIdCache()
    cache.merge(accepted)
    return cache, warnings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/skillids.py tests/test_eveskills_skillids.py
git commit -m "feat(eveskills): skill id cache disk format requiring category_id"
```

---

#### Cycle C — resolution over ESI

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eveskills_skillids.py`:

```python
import pytest

from obs_youtube_uploader.eveskills import esi


@pytest.fixture(autouse=True)
def _clear_group_memo():
    """The group -> category memo is per PROCESS, so it has to be cleared
    between tests: otherwise the second test sees the first one's answers
    and its request-count assertions stop meaning anything."""
    skillids._GROUP_CATEGORIES.clear()
    yield
    skillids._GROUP_CATEGORIES.clear()


class FakeEsi:
    """Answers the three routes resolve() uses, recording every path."""

    def __init__(self, *, ids=None, types=None, groups=None):
        self.ids = ids or {}
        self.types = types or {}
        self.groups = groups or {}
        self.paths = []
        self.batches = []

    def post(self, path, body, *, token=None):
        self.paths.append(path)
        self.batches.append(list(body))
        found = [{"id": self.ids[n], "name": n} for n in body if n in self.ids]
        return esi.EsiResponse(200, {"inventory_types": found}, "", "",
                               "POST", path)

    def get(self, path, *, token=None, etag=None):
        self.paths.append(path)
        segments = [s for s in path.split("/") if s]
        table = self.types if segments[1] == "types" else self.groups
        key = int(segments[-1])
        if key not in table:
            return esi.EsiResponse(404, None, "not found", "", "GET", path)
        return esi.EsiResponse(200, table[key], "", "", "GET", path)


def test_a_skill_resolves_and_enters_the_cache():
    client = FakeEsi(ids={"Navigation": 3449},
                     types={3449: {"group_id": 257}},
                     groups={257: {"category_id": 16}})
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Navigation"], client, max_workers=1)
    assert failures == {}
    assert cache.get("Navigation") == 3449


def test_a_name_esi_does_not_know_reports_the_exact_reason():
    client = FakeEsi(ids={})
    failures = skillids.resolve(skillids.SkillIdCache(), ["Nope"], client,
                                max_workers=1)
    assert failures == {"Nope": "Name was not resolved by ESI."}


def test_a_type_with_no_group_reports_the_exact_reason():
    client = FakeEsi(ids={"Weird": 1}, types={1: {}})
    failures = skillids.resolve(skillids.SkillIdCache(), ["Weird"], client,
                                max_workers=1)
    assert failures == {"Weird": "Resolved type had no valid group."}


def test_a_non_skill_type_reports_the_exact_reason_and_is_not_cached():
    """A ship name in a plan file resolves to a real type id. Caching it
    would make that requirement look satisfiable forever, because the cache
    never invalidates."""
    client = FakeEsi(ids={"Rifter": 587}, types={587: {"group_id": 25}},
                     groups={25: {"category_id": 6}})
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Rifter"], client, max_workers=1)
    assert failures == {
        "Rifter": "Resolved inventory type is not in EVE's skill category."}
    assert cache.type_ids() == {}


def test_names_already_cached_cost_no_requests():
    client = FakeEsi()
    cache = skillids.SkillIdCache({"Navigation": 3449})
    assert skillids.resolve(cache, ["Navigation"], client) == {}
    assert client.paths == []


def test_names_are_batched_at_the_limit():
    """ESI rejects a universe/ids body over 500 names outright, so an
    unbatched first refresh over a large plan set fails entirely."""
    names = [f"Skill {n}" for n in range(skillids.BATCH_SIZE + 7)]
    client = FakeEsi(ids={})
    skillids.resolve(skillids.SkillIdCache(), names, client, max_workers=1)
    assert [len(b) for b in client.batches] == [skillids.BATCH_SIZE, 7]


def test_the_group_lookup_is_memoised():
    """Every skill in a plan set shares a handful of groups. Without the memo
    a 300-requirement resolve spends 300 identical group requests against the
    same error-limit budget the sequential refresh is protecting."""
    client = FakeEsi(ids={"A": 1, "B": 2},
                     types={1: {"group_id": 257}, 2: {"group_id": 257}},
                     groups={257: {"category_id": 16}})
    skillids.resolve(skillids.SkillIdCache(), ["A", "B"], client,
                     max_workers=1)
    assert client.paths.count("/v1/universe/groups/257/") == 1


def test_a_failed_batch_fails_every_name_in_it_without_poisoning_the_cache():
    """A 503 on the batch must not be recorded as "this name is not a skill"
    -- the cache never invalidates, so a transient outage recorded as a
    category verdict would strand those requirements at Unknown forever."""
    class Failing(FakeEsi):
        def post(self, path, body, *, token=None):
            self.batches.append(list(body))
            return esi.EsiResponse(503, None, "boom", "", "POST", path)

    client = Failing()
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["A", "B"], client, max_workers=1)
    assert failures == {"A": "Name was not resolved by ESI.",
                        "B": "Name was not resolved by ESI."}
    assert cache.type_ids() == {}


def test_resolution_fans_out():
    """Concurrency 4, matching TriffView's SemaphoreSlim(4, 4). Bounded on
    purpose: this is charged against the shared error-limit budget."""
    names = [f"Skill {n}" for n in range(8)]
    client = FakeEsi(
        ids={name: n + 1 for n, name in enumerate(names)},
        types={n + 1: {"group_id": 257} for n in range(8)},
        groups={257: {"category_id": 16}})
    cache = skillids.SkillIdCache()
    assert skillids.resolve(cache, names, client,
                            max_workers=skillids.RESOLVE_WORKERS) == {}
    assert len(cache.type_ids()) == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`
Expected: FAIL at collection with `AttributeError: module 'obs_youtube_uploader.eveskills.skillids' has no attribute '_GROUP_CATEGORIES'`

- [ ] **Step 3: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/skillids.py`:

```python
# group id -> category id, memoised for the PROCESS lifetime rather than per
# call. A group's category is immutable in EVE, and every skill in a plan set
# shares a handful of groups -- without this a 300-requirement resolve spends
# 300 identical requests against the same error-limit budget the sequential
# refresh loop is trying to protect. Not persisted: it is cheap to rebuild,
# and only the accepted name -> id result is worth a file.
_GROUP_CATEGORIES: dict = {}
_GROUP_LOCK = threading.Lock()


def _category_for_group(group_id: int, client):
    with _GROUP_LOCK:
        if group_id in _GROUP_CATEGORIES:
            return _GROUP_CATEGORIES[group_id]
    # The request happens OUTSIDE the lock: holding it across HTTP would
    # serialise the fan-out down to one worker, which is the opposite of
    # what the ThreadPoolExecutor is for. The cost is that two workers can
    # race the same group once; the setdefault below makes that harmless.
    response = client.get(f"/v1/universe/groups/{group_id}/")
    category = None
    if response.ok and isinstance(response.data, dict):
        value = response.data.get("category_id")
        if isinstance(value, int) and not isinstance(value, bool):
            category = value
    with _GROUP_LOCK:
        # A failed lookup is memoised as None too. Retrying it inside one
        # resolve would multiply a single outage by the number of skills in
        # that group, and the requirement scores Unknown either way.
        _GROUP_CATEGORIES.setdefault(group_id, category)
        return _GROUP_CATEGORIES[group_id]


def _classify(name: str, type_id: int, client) -> tuple:
    """Return (name, type_id or None, failure reason or "")."""
    response = client.get(f"/v3/universe/types/{type_id}/")
    if not response.ok or not isinstance(response.data, dict):
        return name, None, REASON_NO_GROUP
    group_id = response.data.get("group_id")
    if isinstance(group_id, bool) or not isinstance(group_id, int) \
            or group_id <= 0:
        return name, None, REASON_NO_GROUP
    if _category_for_group(group_id, client) != SKILL_CATEGORY_ID:
        # A ship or module name in a plan file resolves to a real type id.
        # Caching it would make that requirement look satisfiable forever,
        # because the cache never invalidates.
        return name, None, REASON_NOT_A_SKILL
    return name, type_id, ""


def resolve(cache: SkillIdCache, names, client, *,
            max_workers: int = RESOLVE_WORKERS) -> dict:
    """Resolve uncached names, returning name -> failure reason.

    Three steps, ported whole: a batch POST to universe/ids, a per-type
    lookup for its group, and a per-group lookup for its category. Only
    category 16 enters the cache; everything else is a failure with a
    specific reason and scores its requirement Unknown.
    """
    failures: dict = {}
    pending = cache.unresolved(names)
    if not pending:
        return failures

    candidates: dict = {}
    for start in range(0, len(pending), BATCH_SIZE):
        # ESI rejects a universe/ids body over 500 names outright, so an
        # unbatched first refresh over a large plan set fails entirely.
        batch = pending[start:start + BATCH_SIZE]
        response = client.post("/v3/universe/ids/", batch)
        by_key: dict = {}
        if response.ok and isinstance(response.data, dict):
            for item in response.data.get("inventory_types") or []:
                if isinstance(item, dict):
                    by_key[_key(item.get("name"))] = item.get("id")
        # A failed batch fails its names as "not resolved" rather than as
        # "not a skill". The distinction matters because the cache never
        # invalidates: recording a transient outage as a category verdict
        # would strand those requirements permanently.
        for name in batch:
            type_id = by_key.get(_key(name))
            if isinstance(type_id, int) and not isinstance(type_id, bool) \
                    and type_id > 0:
                candidates[name] = type_id
            else:
                failures[name] = REASON_NOT_RESOLVED

    if not candidates:
        return failures

    accepted: dict = {}
    # Concurrency 4, matching TriffView's SemaphoreSlim(4, 4). Bounded on
    # purpose: these requests are charged against the same error-limit budget
    # the refresh loop protects by staying sequential.
    workers = max(1, min(max_workers, len(candidates)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_classify, name, type_id, client)
                   for name, type_id in candidates.items()]
        for future in concurrent.futures.as_completed(futures):
            name, type_id, reason = future.result()
            if reason:
                failures[name] = reason
            else:
                accepted[name] = type_id

    cache.merge(accepted)
    return failures
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_skillids.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/skillids.py tests/test_eveskills_skillids.py
git commit -m "feat(eveskills): resolve skill names to category-16 type ids over ESI"
```
### Task 9: `jwt.py` — claim validation and RS256

**Files:**
- Create: `obs_youtube_uploader/eveskills/jwt.py`
- Test: `tests/test_eveskills_jwt.py`

**Interfaces:**
- Consumes (from Task 1, `obs_youtube_uploader/eveskills/application.py`):
  ```python
  CLIENT_ID: str
  USER_AGENT: str
  SSO_METADATA = "https://login.eveonline.com/.well-known/oauth-authorization-server"
  SSO_HOST = "login.eveonline.com"
  ACCEPTED_ISSUERS: frozenset[str]   # {"https://login.eveonline.com",
                                     #  "https://login.eveonline.com/",
                                     #  "login.eveonline.com"}
  ```
- Produces:
  ```python
  CLOCK_SKEW_S = 120
  JWKS_TTL_S = 300

  @dataclass(frozen=True)
  class EveIdentity:
      character_id: int
      name: str
      owner_hash: str             # "" when the claim is absent
      scopes: frozenset[str]

  class JwtError(Exception): ...

  class SigningKeySource:
      def __init__(self, *, transport=..., now=..., ttl_s: int = JWKS_TTL_S)
      def keys(self, *, force: bool = False) -> dict[str, object]
          # kid -> cryptography RSAPublicKey; RSA signing keys only

  def validate(token: str, *, client_id: str,
               required_scopes: Iterable[str],
               key_source: SigningKeySource,
               now: datetime | None = None,
               skew_s: int = CLOCK_SKEW_S) -> EveIdentity
  ```

---

#### Cycle 1 — token structure and algorithm pinning

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eveskills_jwt.py
"""EVE SSO access-token validation.

Every token in this file is signed for real, at test time, with an RSA
keypair generated in-process. That keeps the suite hermetic -- no network,
no checked-in private key, no fixture that quietly expires -- while still
exercising the same `cryptography` verify() call production uses. A test
that stubbed out signature verification would pass just as happily against
a module that never verified anything.
"""
import base64
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from obs_youtube_uploader.eveskills import jwt as evejwt

CLIENT_ID = "9a1f7d2c4b6e48f0a3d5c7e9b1f3a5d7"

REQUIRED = ("esi-skills.read_skills.v1", "esi-skills.read_skillqueue.v1")


@pytest.fixture(scope="module")
def keypair():
    """One 2048-bit keypair for the whole module.

    Generation costs ~100ms; per-test generation would add seconds to a
    suite that is otherwise instant, and nothing here depends on a fresh
    key except the wrong-key test, which makes its own.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign(private_key, payload: dict, *, header: dict | None = None) -> str:
    """Mint a real JWT. `header` overrides the default RS256/kid header."""
    head = dict(header if header is not None else {"alg": "RS256", "kid": "k1"})
    head_b64 = b64(json.dumps(head, separators=(",", ":")).encode("utf-8"))
    body_b64 = b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{head_b64}.{body_b64}.{b64(signature)}"


def claims(**overrides) -> dict:
    now = int(time.time())
    payload = {
        "iss": "login.eveonline.com",
        "aud": ["EVE Online", CLIENT_ID],
        "sub": "CHARACTER:EVE:95465499",
        "name": "Test Pilot",
        "owner": "abcdefgh12345678",
        "exp": now + 1200,
        "scp": "esi-skills.read_skills.v1 esi-skills.read_skillqueue.v1",
    }
    payload.update(overrides)
    return payload


class FakeKeys:
    """A SigningKeySource stand-in that counts forced refreshes."""

    def __init__(self, mapping):
        self._mapping = dict(mapping)
        self.forced = 0

    def keys(self, *, force=False):
        if force:
            self.forced += 1
        return dict(self._mapping)


class ExplodingKeys:
    """Fails the test if a key is ever requested."""

    def keys(self, *, force=False):
        raise AssertionError("a key was selected before `alg` was pinned")


def validate(token, key_source, **kwargs):
    kwargs.setdefault("client_id", CLIENT_ID)
    kwargs.setdefault("required_scopes", REQUIRED)
    return evejwt.validate(token, key_source=key_source, **kwargs)


def test_rejects_blank_and_oversized_tokens():
    """Neither shape can be a JWT, and both are cheap to reject up front.

    The size cap matters more than it looks: everything below splits and
    base64-decodes the token, so an unbounded string is unbounded work
    before the first real check.
    """
    for bad in ("", "   ", "x" * (32 * 1024 + 1)):
        with pytest.raises(evejwt.JwtError):
            validate(bad, ExplodingKeys())


def test_rejects_tokens_without_exactly_three_segments():
    """Two segments is an unsigned token; four is not a JWS at all."""
    for bad in ("only-one", "two.parts", "a.b.c.d"):
        with pytest.raises(evejwt.JwtError):
            validate(bad, ExplodingKeys())


def test_alg_none_is_rejected_before_any_key_is_selected(keypair):
    """Algorithm pinning happens on the unvalidated header, first.

    ExplodingKeys asserts if a key is ever requested, so this test fails
    loudly if a future refactor moves key selection ahead of the `alg`
    check -- which is exactly the ordering that lets alg:none through.
    """
    token = sign(keypair, claims(), header={"alg": "none", "kid": "k1"})
    with pytest.raises(evejwt.JwtError, match="signing algorithm"):
        validate(token, ExplodingKeys())


def test_hs256_is_rejected_before_any_key_is_selected(keypair):
    """The HMAC-confusion shape: a token asking to be verified with a
    symmetric algorithm is rejected outright, never routed to a different
    verifier."""
    token = sign(keypair, claims(), header={"alg": "HS256", "kid": "k1"})
    with pytest.raises(evejwt.JwtError, match="signing algorithm"):
        validate(token, ExplodingKeys())


def test_missing_kid_is_rejected(keypair):
    """A token that names no key cannot be verified against a key set, and
    guessing -- trying every key -- is how a rotated-out key stays usable
    long after CCP retired it."""
    token = sign(keypair, claims(), header={"alg": "RS256"})
    with pytest.raises(evejwt.JwtError, match="signing key"):
        validate(token, ExplodingKeys())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.jwt'` at collection.

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/eveskills/jwt.py
"""EVE SSO access-token validation: claim checks plus an RS256 signature.

Signature verification runs against `cryptography`, which this application
already ships. google-auth depends on it unconditionally (uv.lock:382-387)
and 50.0.0 is bundled into every release today, so verification here is ten
lines against an audited implementation.

An earlier draft of this design specified roughly sixty lines of
hand-written RSA in this module -- decoding the JWKS modulus and exponent to
ints, computing pow(sig, e, n), and checking the PKCS#1 v1.5 padding by hand
-- on the explicit grounds that it avoided adding a dependency. That premise
was false. The claim came from memory of older google-auth releases, which
pulled `rsa` rather than `cryptography`, instead of from the lock file. It
would have bought sixty lines of security-critical code -- encoded-message
length, minimum padding length, full-block equality, malformed key
parameters, none of which the draft specified -- in exchange for nothing at
all.

The lesson is cheap to apply and expensive to skip: check the lock file
before calling something a new dependency.
"""
import base64
import binascii
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

from . import application

CLOCK_SKEW_S = 120
JWKS_TTL_S = 300

MAX_TOKEN_CHARS = 32 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_JWKS_BYTES = 256 * 1024
TIMEOUT_S = 20.0

# The one algorithm this module will ever verify. See validate() for why the
# check sits where it does.
_ALGORITHM = "RS256"

_CHARACTER_SUBJECT = re.compile(r"^CHARACTER:EVE:([1-9][0-9]{0,18})$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]*$")


class JwtError(Exception):
    """Any reason an access token was not accepted."""


@dataclass(frozen=True)
class EveIdentity:
    character_id: int
    name: str
    owner_hash: str
    scopes: frozenset[str]


def _b64url_decode(segment: str) -> bytes:
    """Decode one base64url segment, rejecting anything outside the alphabet.

    base64.urlsafe_b64decode is lenient about characters it does not
    recognise -- it discards them -- so the alphabet is checked here first.
    A segment that decodes to different bytes than it reads as is exactly
    the ambiguity signature verification exists to remove.
    """
    if not _B64URL.match(segment):
        raise JwtError("EVE SSO returned an unreadable access token.")
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise JwtError("EVE SSO returned an unreadable access token.") from exc


def _decode_json_segment(segment: str) -> dict:
    try:
        parsed = json.loads(_b64url_decode(segment).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise JwtError("EVE SSO returned an unreadable access token.") from exc
    if not isinstance(parsed, dict):
        raise JwtError("EVE SSO returned an unreadable access token.")
    return parsed


def validate(token: str, *, client_id: str,
             required_scopes: Iterable[str],
             key_source,
             now: datetime | None = None,
             skew_s: int = CLOCK_SKEW_S) -> EveIdentity:
    """Validate an EVE SSO access token and return the identity it carries.

    Raises JwtError for every rejection; there is no partial success.
    """
    if not isinstance(token, str) or not token.strip():
        raise JwtError("EVE SSO returned an invalid access token.")
    if len(token) > MAX_TOKEN_CHARS:
        # Bounded before the split: everything below decodes segments, and
        # an unbounded string is unbounded work ahead of the first check.
        raise JwtError("EVE SSO returned an invalid access token.")
    pieces = token.split(".")
    if len(pieces) != 3:
        raise JwtError("EVE SSO returned an unreadable access token.")
    head_b64, body_b64, sig_b64 = pieces

    header = _decode_json_segment(head_b64)
    # Algorithm pinning, on the UNVALIDATED header, BEFORE a key is chosen.
    # The ordering is not incidental: reading `alg` after picking a key is
    # precisely what lets alg:none through, because by then something has
    # already decided how to verify.
    #
    # Pinning is not the whole HMAC-confusion defence either. The real
    # defence is structural: nothing below dispatches on the token's own
    # `alg` to select a verifier or a key type. There is ONE path, it is
    # RSA/PKCS#1v1.5/SHA-256, and a token asking for anything else is
    # rejected rather than routed.
    if header.get("alg") != _ALGORITHM:
        raise JwtError("EVE SSO access token used an unexpected signing algorithm.")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        # No kid means no key selection. Trying every key instead would keep
        # a rotated-out key usable long after CCP retired it.
        raise JwtError("EVE SSO access token did not name a signing key.")

    keys = key_source.keys()
    if kid not in keys:
        # Exactly one forced refresh on an unknown kid: CCP rotates, and the
        # cache may simply be stale. A refresh that itself fails is swallowed
        # so the previous keys stay in play and the rejection below reports
        # "unknown key" rather than surfacing a fetch failure -- the token is
        # unverifiable either way, and the accurate message is the useful one.
        try:
            keys = key_source.keys(force=True)
        except JwtError:
            pass
    public_key = keys.get(kid)
    if public_key is None:
        raise JwtError("EVE SSO access token was signed by an unknown key.")

    # PKCS#1 v1.5 with SHA-256 is what RS256 means. `cryptography` raises
    # InvalidSignature and nothing else for a bad signature, so the except
    # clause is deliberately narrow: any other error type here would mean a
    # malformed key object, which must not be swallowed as "bad signature".
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = _b64url_decode(sig_b64)
    try:
        public_key.verify(signature, signing_input,
                          padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise JwtError("EVE SSO access token failed signature verification.") from exc

    claims = _decode_json_segment(body_b64)
    return _read_claims(claims, client_id=client_id,
                        required_scopes=required_scopes,
                        now=now, skew_s=skew_s)


def _read_claims(claims: dict, *, client_id, required_scopes, now, skew_s) -> EveIdentity:
    """Placeholder until Cycle 3; Cycles 1-2 prove the signature path."""
    return EveIdentity(character_id=0, name="", owner_hash="",
                       scopes=frozenset())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/jwt.py tests/test_eveskills_jwt.py
git commit -m "feat(eveskills): pin JWT alg to RS256 before key selection"
```

---

#### Cycle 2 — RS256 signature verification

- [ ] **Step 6: Write the failing test**

```python
# tests/test_eveskills_jwt.py  (append)

def test_accepts_a_correctly_signed_token(keypair):
    """The happy path, verified against the real cryptography primitive."""
    token = sign(keypair, claims())
    identity = validate(token, FakeKeys({"k1": keypair.public_key()}))
    assert identity is not None


def test_rejects_a_token_signed_by_a_different_key(keypair):
    """A structurally perfect token signed by someone else's key.

    Every claim in this token is valid; only the signature is wrong. If
    verification were ever stubbed, weakened, or reordered behind the claim
    checks, this is the test that catches it.
    """
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign(impostor, claims())
    with pytest.raises(evejwt.JwtError, match="signature"):
        validate(token, FakeKeys({"k1": keypair.public_key()}))


def test_rejects_a_token_whose_payload_was_edited(keypair):
    """Tamper with the body after signing and the signature must fail.

    This is the check that makes every claim assertion below meaningful:
    without it, claim validation would be reading attacker-controlled JSON.
    """
    token = sign(keypair, claims())
    head_b64, _, sig_b64 = token.split(".")
    forged = b64(json.dumps(claims(sub="CHARACTER:EVE:1")).encode("utf-8"))
    with pytest.raises(evejwt.JwtError, match="signature"):
        validate(f"{head_b64}.{forged}.{sig_b64}",
                 FakeKeys({"k1": keypair.public_key()}))


def test_rejects_a_signature_outside_the_base64url_alphabet(keypair):
    """urlsafe_b64decode silently discards characters it does not know, so
    the alphabet is checked before decoding -- otherwise a signature would
    decode to different bytes than it reads as."""
    head_b64, body_b64, _ = sign(keypair, claims()).split(".")
    with pytest.raises(evejwt.JwtError, match="unreadable"):
        validate(f"{head_b64}.{body_b64}.not*a*signature",
                 FakeKeys({"k1": keypair.public_key()}))


def test_unknown_kid_forces_exactly_one_refresh(keypair):
    """An unknown kid triggers one forced refresh, then a rejection.

    One, not a loop: CCP rotates keys, so a stale cache is worth a single
    retry, but a kid that stays unknown must not turn every bad token into
    repeated fetches against login.eveonline.com.
    """
    source = FakeKeys({"k1": keypair.public_key()})
    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "rotated"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, source)
    assert source.forced == 1


def test_a_failed_forced_refresh_still_reports_an_unknown_key(keypair):
    """A network failure during the refresh must not replace the diagnosis.

    The token is unverifiable either way; reporting "unknown key" is
    accurate and actionable, while surfacing a fetch failure sends the user
    looking at their connection instead of at a rotated key.
    """

    class Flaky:
        def keys(self, *, force=False):
            if force:
                raise evejwt.JwtError("metadata fetch failed")
            return {"k1": keypair.public_key()}

    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "rotated"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, Flaky())
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`
Expected: PASS — Cycle 1 already wired `public_key.verify`. These tests exist
to pin that behaviour against future edits, and a failure here means the
Cycle 1 implementation is wrong. If `test_rejects_a_token_signed_by_a_different_key`
fails, verification is not actually running and Step 8 is not optional.

- [ ] **Step 8: Write minimal implementation**

No production change is expected. If any Cycle 2 test fails, the fault is in
Cycle 1's verification block; the correct form is exactly:

```python
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = _b64url_decode(sig_b64)
    try:
        public_key.verify(signature, signing_input,
                          padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise JwtError("EVE SSO access token failed signature verification.") from exc
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`

- [ ] **Step 10: Commit**

```bash
git add tests/test_eveskills_jwt.py
git commit -m "test(eveskills): prove RS256 verification rejects foreign keys"
```

---

#### Cycle 3 — claim validation

- [ ] **Step 11: Write the failing test**

```python
# tests/test_eveskills_jwt.py  (append)

@pytest.fixture
def keys(keypair):
    return FakeKeys({"k1": keypair.public_key()})


def test_accepts_every_form_of_the_issuer(keypair, keys):
    """CCP has emitted all three spellings; all three are the same issuer."""
    for issuer in ("https://login.eveonline.com",
                   "https://login.eveonline.com/",
                   "login.eveonline.com"):
        identity = validate(sign(keypair, claims(iss=issuer)), keys)
        assert identity.character_id == 95465499


def test_rejects_an_unexpected_issuer(keypair, keys):
    """Not a suffix match: "login.eveonline.com.evil.test" must not pass."""
    with pytest.raises(evejwt.JwtError, match="issuer"):
        validate(sign(keypair, claims(iss="https://login.eveonline.com.evil.test")), keys)


def test_audience_is_a_conjunction_not_a_choice(keypair, keys):
    """`aud` must contain BOTH "EVE Online" AND our client id.

    CCP stamps "EVE Online" into every token it mints, for every
    application, so that value alone proves nothing about who the token was
    for. The client id alone is likewise not enough to know it came from the
    EVE issuer at all. Accepting either half on its own would accept a token
    minted for somebody else's application.
    """
    assert validate(sign(keypair, claims()), keys).character_id == 95465499
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud=["EVE Online"])), keys)
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud=[CLIENT_ID])), keys)


def test_a_string_audience_is_read_as_a_single_value(keypair, keys):
    """RFC 7519 allows a bare string, and a bare string can never satisfy
    the conjunction -- which is the correct outcome, not a crash."""
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud="EVE Online")), keys)


def test_azp_must_match_when_present_and_is_optional_when_absent(keypair, keys):
    """An absent azp is normal; a present-and-wrong azp is a different app."""
    payload = claims()
    payload.pop("azp", None)
    assert validate(sign(keypair, payload), keys).character_id == 95465499
    assert validate(sign(keypair, claims(azp=CLIENT_ID)), keys).character_id == 95465499
    with pytest.raises(evejwt.JwtError, match="different client"):
        validate(sign(keypair, claims(azp="someone-else")), keys)


def test_expiry_allows_two_minutes_of_skew(keypair, keys):
    """Desktop clocks drift. Two minutes is the ported allowance.

    `now` is injected rather than slept for, so this asserts the boundary
    exactly instead of approximately.
    """
    moment = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    expiry = int(moment.timestamp()) - 60          # expired a minute ago
    assert validate(sign(keypair, claims(exp=expiry)), keys, now=moment)
    stale = int(moment.timestamp()) - 121          # past the 120s allowance
    with pytest.raises(evejwt.JwtError, match="expired"):
        validate(sign(keypair, claims(exp=stale)), keys, now=moment)


def test_rejects_a_missing_or_non_numeric_expiry(keypair, keys):
    """A token with no expiry never expires, which is not a token we accept.

    `True` is included because bool subclasses int, and `exp: true` reading
    as 1 second past the epoch would be an expiry check that always failed
    for the wrong reason.
    """
    payload = claims()
    del payload["exp"]
    with pytest.raises(evejwt.JwtError, match="expiry"):
        validate(sign(keypair, payload), keys)
    for bad in ("soon", None, True, [1]):
        with pytest.raises(evejwt.JwtError, match="expiry"):
            validate(sign(keypair, claims(exp=bad)), keys)


def test_subject_must_be_a_character_subject(keypair, keys):
    """CHARACTER:EVE:<id> and nothing else.

    EVE mints subjects for corporations and other entity kinds too. A
    corporation id parsed as a character id would key the whole roster on a
    number that never matches an ESI skills response. The leading-zero and
    trailing-space cases are the ones a looser regex lets through.
    """
    for bad in ("CORPORATION:EVE:98000001", "CHARACTER:EVE:0",
                "CHARACTER:EVE:0123", "CHARACTER:EVE:", "95465499",
                "CHARACTER:EVE:95465499 ", "character:eve:95465499"):
        with pytest.raises(evejwt.JwtError, match="character subject"):
            validate(sign(keypair, claims(sub=bad)), keys)


def test_name_is_trimmed_and_bounded(keypair, keys):
    payload = claims(name="  Test Pilot  ")
    assert validate(sign(keypair, payload), keys).name == "Test Pilot"
    for bad in ("", "   ", "x" * 101):
        with pytest.raises(evejwt.JwtError, match="character name"):
            validate(sign(keypair, claims(name=bad)), keys)


def test_name_rejects_control_characters(keypair, keys):
    """A newline in a character name would break every log line and every
    single-line label the roster renders it into."""
    for bad in ("Test\nPilot", "Test\x00Pilot", "Test\x7fPilot"):
        with pytest.raises(evejwt.JwtError, match="character name"):
            validate(sign(keypair, claims(name=bad)), keys)


def test_owner_is_optional_but_bounded_when_present(keypair, keys):
    """An absent owner hash reads as "", not as a failure.

    The owner hash is how a character transfer is detected later; a token
    without one simply cannot contribute to that check, which is different
    from the token being malformed.
    """
    payload = claims()
    del payload["owner"]
    assert validate(sign(keypair, payload), keys).owner_hash == ""
    assert validate(sign(keypair, claims()), keys).owner_hash == "abcdefgh12345678"
    for bad in ("short", "x" * 257, "abcdefg\nh"):
        with pytest.raises(evejwt.JwtError, match="owner"):
            validate(sign(keypair, claims(owner=bad)), keys)
```

- [ ] **Step 12: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`
Expected: FAIL with `AssertionError: assert 0 == 95465499` — the Cycle 1
placeholder `_read_claims` returns an empty identity and raises nothing.

- [ ] **Step 13: Write minimal implementation**

Replace the placeholder `_read_claims` in
`obs_youtube_uploader/eveskills/jwt.py`:

```python
def _is_control(character: str) -> bool:
    # Unicode category Cc is exactly C0 (0x00-0x1F) plus DEL and C1
    # (0x7F-0x9F) -- the same set the ported implementation rejected.
    return unicodedata.category(character) == "Cc"


def _read_claims(claims: dict, *, client_id, required_scopes, now, skew_s) -> EveIdentity:
    issuer = claims.get("iss")
    # Membership in a fixed set, deliberately not a suffix match:
    # "login.eveonline.com.evil.test" must not pass.
    if not isinstance(issuer, str) or issuer not in application.ACCEPTED_ISSUERS:
        raise JwtError("EVE SSO access token came from an unexpected issuer.")

    # The audience is a CONJUNCTION, not a choice. CCP stamps the literal
    # "EVE Online" into every token it mints for every application, so that
    # value alone says nothing about who the token was for; the client id is
    # what makes it OURS. Accepting either half alone accepts a token minted
    # for somebody else's application.
    audiences = claims.get("aud")
    if isinstance(audiences, str):
        # RFC 7519 allows a bare string. It can never satisfy the
        # conjunction, but reading it as a list of characters would be a
        # much stranger failure than reading it as one value.
        audiences = [audiences]
    if not isinstance(audiences, list):
        raise JwtError("EVE SSO access token was issued for a different audience.")
    present = {value for value in audiences if isinstance(value, str)}
    if "EVE Online" not in present or client_id not in present:
        raise JwtError("EVE SSO access token was issued for a different audience.")

    authorized_party = claims.get("azp")
    if authorized_party is not None and authorized_party != client_id:
        raise JwtError("EVE SSO access token was authorized to a different client.")

    expiry = claims.get("exp")
    # bool is an int subclass, and `exp: true` must not read as one second
    # past the epoch.
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        raise JwtError("EVE SSO access token had no usable expiry.")
    moment = now or datetime.now(timezone.utc)
    if expiry + skew_s <= moment.timestamp():
        raise JwtError("EVE SSO access token has expired.")

    subject = claims.get("sub")
    match = _CHARACTER_SUBJECT.match(subject) if isinstance(subject, str) else None
    if match is None:
        # EVE mints subjects for corporations and other entity kinds too. A
        # corporation id parsed as a character id would key the roster on a
        # number no ESI skills response will ever match.
        raise JwtError("EVE SSO access token had an invalid character subject.")
    character_id = int(match.group(1))

    raw_name = claims.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not 1 <= len(name) <= 100 or any(_is_control(ch) for ch in name):
        # A newline here would break every log line and every single-line
        # label the roster renders the name into.
        raise JwtError("EVE SSO access token had an invalid character name.")

    raw_owner = claims.get("owner")
    if raw_owner is None:
        # Absent is normal, not a failure: the owner hash only contributes
        # to the character-transfer check, and a token without one simply
        # cannot contribute to it.
        owner_hash = ""
    else:
        owner_hash = raw_owner.strip() if isinstance(raw_owner, str) else ""
        if not 8 <= len(owner_hash) <= 256 or any(_is_control(ch) for ch in owner_hash):
            raise JwtError("EVE SSO access token had an invalid owner claim.")

    granted = _read_scopes(claims.get("scp"))
    missing = sorted(scope for scope in required_scopes if scope not in granted)
    if missing:
        # Named, because the message is what the user acts on.
        raise JwtError("EVE SSO access token is missing required scopes: "
                       + ", ".join(missing) + ".")

    return EveIdentity(character_id=character_id, name=name,
                       owner_hash=owner_hash, scopes=frozenset(granted))


def _read_scopes(raw: object) -> frozenset[str]:
    """Placeholder until Cycle 4."""
    if isinstance(raw, str):
        return frozenset(raw.split())
    return frozenset()
```

- [ ] **Step 14: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`

- [ ] **Step 15: Commit**

```bash
git add obs_youtube_uploader/eveskills/jwt.py tests/test_eveskills_jwt.py
git commit -m "feat(eveskills): validate EVE access-token claims"
```

---

#### Cycle 4 — the three shapes of `scp`

- [ ] **Step 16: Write the failing test**

```python
# tests/test_eveskills_jwt.py  (append)

def test_scp_as_a_space_separated_string(keypair, keys):
    """The shape EVE emits for a multi-scope token today."""
    identity = validate(sign(keypair, claims(
        scp="esi-skills.read_skills.v1 esi-skills.read_skillqueue.v1")), keys)
    assert identity.scopes == frozenset(REQUIRED)


def test_scp_as_a_json_array(keypair, keys):
    """The other shape EVE emits, and the one that breaks a naive reader.

    Running a string reader's split() over a list, or a list reader over a
    string, yields one "scope" per character -- which then fails the subset
    check with a message naming scopes that look nothing like the ones the
    token actually granted.
    """
    identity = validate(sign(keypair, claims(scp=list(REQUIRED))), keys)
    assert identity.scopes == frozenset(REQUIRED)


def test_scp_as_a_bare_string_for_a_single_scope(keypair, keys):
    """A single-scope token carries a plain string with no separator."""
    identity = evejwt.validate(
        sign(keypair, claims(scp="esi-skills.read_skills.v1")),
        client_id=CLIENT_ID,
        required_scopes=("esi-skills.read_skills.v1",),
        key_source=keys)
    assert identity.scopes == frozenset({"esi-skills.read_skills.v1"})


def test_absent_scp_reads_as_no_scopes_not_as_an_error(keypair, keys):
    """A token minted with no scopes omits the claim entirely.

    Treating the absent case as malformed would reject a structurally valid
    token; it fails below on the subset check instead, which reports the
    actual problem -- missing scopes -- rather than "unreadable token".
    """
    payload = claims()
    del payload["scp"]
    with pytest.raises(evejwt.JwtError, match="missing required scopes"):
        validate(sign(keypair, payload), keys)


def test_required_scopes_are_a_subset_so_extras_are_fine(keypair, keys):
    """CCP may grant more than we asked for; that is not an error.

    Requiring equality would break the moment a user re-consents to a
    superset, or CCP widens what a scope implies.
    """
    granted = list(REQUIRED) + ["esi-characters.read_notifications.v1"]
    identity = validate(sign(keypair, claims(scp=granted)), keys)
    assert frozenset(REQUIRED) <= identity.scopes


def test_missing_scopes_are_named_in_the_message(keypair, keys):
    """The message is what the user acts on, so it names what is missing."""
    with pytest.raises(evejwt.JwtError,
                       match="esi-skills.read_skillqueue.v1"):
        validate(sign(keypair, claims(scp="esi-skills.read_skills.v1")), keys)


def test_a_scope_claim_of_an_unexpected_type_is_rejected(keypair, keys):
    """A number is neither of the two shapes EVE emits, and silently
    reading it as "no scopes" would hide a response nobody understands."""
    with pytest.raises(evejwt.JwtError, match="scope claim"):
        validate(sign(keypair, claims(scp=42)), keys)
```

- [ ] **Step 17: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`
Expected: FAIL on `test_scp_as_a_json_array` with
`JwtError: EVE SSO access token is missing required scopes: ...` — the
placeholder `_read_scopes` returns an empty set for list-shaped claims.

- [ ] **Step 18: Write minimal implementation**

Replace the placeholder `_read_scopes`:

```python
def _read_scopes(raw: object) -> frozenset[str]:
    """Read `scp` in all three shapes EVE emits.

    A single-scope token carries a bare string, a multi-scope token carries
    either a space-separated string or a JSON array, and a token minted with
    no scopes omits the claim. All three are valid responses, so none of
    them may raise.

    The failure this guards against is not hypothetical: reading a string
    with a list reader (or the reverse) yields one "scope" per character,
    and the resulting message names scopes that look nothing like what the
    token granted.
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        # split() with no argument collapses runs of whitespace and drops
        # empties, which covers both the single-scope and separated forms.
        return frozenset(raw.split())
    if isinstance(raw, list):
        return frozenset(item.strip() for item in raw
                         if isinstance(item, str) and item.strip())
    # Neither shape. Reading this as "no scopes" would hide a response
    # nobody understands behind a plausible-looking permissions error.
    raise JwtError("EVE SSO access token had an unreadable scope claim.")
```

- [ ] **Step 19: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`

- [ ] **Step 20: Commit**

```bash
git add obs_youtube_uploader/eveskills/jwt.py tests/test_eveskills_jwt.py
git commit -m "feat(eveskills): read scp in all three shapes EVE emits"
```

---

#### Cycle 5 — `SigningKeySource`

- [ ] **Step 21: Write the failing test**

```python
# tests/test_eveskills_jwt.py  (append)
import urllib.error


def jwks_entry(public_key, kid="k1", **overrides):
    """Serialise an RSA public key as a JWKS entry."""
    numbers = public_key.public_numbers()

    def encode(value: int) -> str:
        return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    entry = {"kty": "RSA", "use": "sig", "kid": kid,
             "n": encode(numbers.n), "e": encode(numbers.e)}
    entry.update(overrides)
    return entry


class FakeHttp:
    """Serves canned JSON per URL and records every fetch.

    A value that is an Exception instance is raised instead of served,
    which is how the failed-refresh test takes the transport offline
    mid-run.
    """

    def __init__(self, documents):
        self.documents = dict(documents)
        self.fetched = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.fetched.append(url)
        document = self.documents.get(url)
        if document is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if isinstance(document, Exception):
            raise document
        payload = json.dumps(document).encode("utf-8")

        class Response:
            def read(self, amount=None):
                return payload if amount is None else payload[:amount]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


METADATA_URL = "https://login.eveonline.com/.well-known/oauth-authorization-server"
JWKS_URL = "https://login.eveonline.com/oauth/jwks"


def metadata(**overrides):
    document = {"issuer": "https://login.eveonline.com", "jwks_uri": JWKS_URL}
    document.update(overrides)
    return document


class FakeClock:
    def __init__(self, start=None):
        self.moment = start or datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.moment

    def advance(self, seconds):
        self.moment = self.moment + timedelta(seconds=seconds)


def test_key_source_fetches_metadata_then_jwks(keypair):
    """Two hops, in order: the metadata document names the JWKS address."""
    http = FakeHttp({METADATA_URL: metadata(),
                     JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]
    assert http.fetched == [METADATA_URL, JWKS_URL]


def test_keys_are_cached_for_five_minutes(keypair):
    """One fetch pair per TTL window, not one per token validated."""
    clock = FakeClock()
    http = FakeHttp({METADATA_URL: metadata(),
                     JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]}})
    source = evejwt.SigningKeySource(transport=http, now=clock)
    source.keys()
    clock.advance(299)
    source.keys()
    assert len(http.fetched) == 2
    clock.advance(2)
    source.keys()
    assert len(http.fetched) == 4


def test_force_refetches_inside_the_ttl(keypair):
    """The unknown-kid path needs a way past a cache that is still fresh."""
    clock = FakeClock()
    http = FakeHttp({METADATA_URL: metadata(),
                     JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]}})
    source = evejwt.SigningKeySource(transport=http, now=clock)
    source.keys()
    source.keys(force=True)
    assert len(http.fetched) == 4


def test_a_failed_refresh_leaves_the_previous_keys_usable(keypair):
    """The cache is replaced only on a fully successful fetch.

    This is the difference between "one request failed" and "this process
    can no longer validate anything". The forced refresh below raises, and
    the next non-forced call must still hand back the keys already held.
    """
    clock = FakeClock()
    http = FakeHttp({METADATA_URL: metadata(),
                     JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]}})
    source = evejwt.SigningKeySource(transport=http, now=clock)
    assert list(source.keys()) == ["k1"]
    http.documents[METADATA_URL] = urllib.error.URLError("offline")
    with pytest.raises(evejwt.JwtError):
        source.keys(force=True)
    assert list(source.keys()) == ["k1"]


def test_rejects_metadata_with_an_unexpected_issuer(keypair):
    """And never fetches the JWKS the bad document named."""
    http = FakeHttp({METADATA_URL: metadata(issuer="https://evil.test"),
                     JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="issuer"):
        source.keys()
    assert http.fetched == [METADATA_URL]


def test_rejects_a_jwks_uri_that_is_not_absolute_https_on_the_sso_host():
    """The metadata document is the one input allowed to name a URL whose
    contents this process then trusts. A relative, plaintext, or off-host
    jwks_uri is precisely how that becomes key substitution -- and the
    third case below is why the host check is not a suffix match."""
    for bad in ("/oauth/jwks", "http://login.eveonline.com/oauth/jwks",
                "https://login.eveonline.com.evil.test/oauth/jwks",
                "https://evil.test/oauth/jwks", "not a url", ""):
        http = FakeHttp({METADATA_URL: metadata(jwks_uri=bad)})
        source = evejwt.SigningKeySource(transport=http, now=FakeClock())
        with pytest.raises(evejwt.JwtError, match="JWKS address"):
            source.keys()


def test_filters_jwks_to_rsa_signing_keys_with_a_kid(keypair):
    """Non-RSA keys, encryption keys, and keyless entries are dropped here.

    Dropping at load time rather than at lookup is what makes a kid naming a
    non-RSA key a REJECTION and never a fallback: the key is simply absent
    from the map, and validate() reports an unknown key.
    """
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": [
        {"kty": "EC", "use": "sig", "kid": "ec-key", "crv": "P-256",
         "x": "AAAA", "y": "AAAA"},
        jwks_entry(other.public_key(), kid="enc-key", use="enc"),
        jwks_entry(other.public_key(), kid="  "),
        "not-even-an-object",
        jwks_entry(keypair.public_key(), kid="k1"),
    ]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]


def test_a_kid_naming_a_non_rsa_key_is_rejected_never_a_fallback(keypair):
    """End to end: the token names the EC entry, and validation fails with
    "unknown key" rather than quietly verifying against the RSA one."""
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": [
        {"kty": "EC", "use": "sig", "kid": "ec-key", "crv": "P-256",
         "x": "AAAA", "y": "AAAA"},
        jwks_entry(keypair.public_key(), kid="k1"),
    ]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "ec-key"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, source)


def test_an_entry_without_use_is_still_accepted(keypair):
    """`use` is optional in a JWKS, and absent means unrestricted.
    Requiring it would reject a perfectly valid key set."""
    entry = jwks_entry(keypair.public_key())
    del entry["use"]
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": [entry]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]


def test_an_empty_key_set_is_a_failure_not_an_empty_cache():
    """Caching an empty set would fail every token for the next 5 minutes,
    long after whatever caused it had gone away."""
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": []}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="no usable signing keys"):
        source.keys()


def test_a_non_object_key_document_is_rejected():
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: ["k1"]})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="unreadable key set"):
        source.keys()


def test_an_http_failure_on_the_metadata_fetch_is_reported(keypair):
    http = FakeHttp({})           # every URL 404s
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="404"):
        source.keys()
```

- [ ] **Step 22: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.jwt' has no attribute 'SigningKeySource'`.

- [ ] **Step 23: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/jwt.py`:

```python
class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on the metadata and JWKS fetches.

    Both of these responses decide which keys this process will trust. A 3xx
    would let anything sitting in front of login.eveonline.com relocate that
    decision to a host the scheme and host checks below never got to see.
    Returning None tells urllib not to follow; the 3xx then surfaces as an
    ordinary HTTPError. Same seam and same reasoning as discord.py.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rsa_signing_key(entry: object):
    """Select one JWKS entry as (kid, RSAPublicKey), or None to drop it.

    Filtering here rather than at lookup time is what makes a kid naming a
    non-RSA key a rejection and never a fallback: an unusable entry is
    simply absent from the map, and validate() reports an unknown key.
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("kty") != "RSA":
        return None
    use = entry.get("use")
    # `use` is optional in a JWKS; absent means unrestricted. Only an
    # explicit non-"sig" value disqualifies an entry.
    if use is not None and use != "sig":
        return None
    kid = entry.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        return None
    modulus, exponent = entry.get("n"), entry.get("e")
    if not isinstance(modulus, str) or not isinstance(exponent, str):
        return None
    try:
        n = int.from_bytes(_b64url_decode(modulus), "big")
        e = int.from_bytes(_b64url_decode(exponent), "big")
    except JwtError:
        return None
    if n <= 0 or e <= 0:
        return None
    try:
        return kid, RSAPublicNumbers(e, n).public_key()
    except ValueError:
        # cryptography rejects malformed key parameters (an even exponent,
        # an implausible modulus). Dropping just this entry is right: the
        # rest of the key set is still perfectly usable.
        return None


class SigningKeySource:
    """Fetches and caches EVE's JWKS signing keys."""

    def __init__(self, *, transport=_default_transport, now=_utcnow,
                 ttl_s: int = JWKS_TTL_S) -> None:
        self._transport = transport
        self._now = now
        self._ttl_s = ttl_s
        # Refreshes happen on worker threads; the lock keeps a burst of
        # unknown-kid refreshes from becoming a burst of fetches.
        self._lock = threading.Lock()
        self._keys: dict[str, object] = {}
        self._expires: datetime | None = None

    def keys(self, *, force: bool = False) -> dict[str, object]:
        with self._lock:
            moment = self._now()
            fresh = bool(self._keys) and self._expires is not None and self._expires > moment
            if fresh and not force:
                return dict(self._keys)
            # The cache is replaced ONLY on a fully successful load. _load
            # raises before either assignment, so a metadata blip, a bad
            # issuer, or an empty JWKS all leave the previous keys in place
            # and usable -- the difference between "one request failed" and
            # "this process can no longer validate anything".
            loaded = self._load()
            self._keys = loaded
            self._expires = moment + timedelta(seconds=self._ttl_s)
            # A copy, so a caller mutating the result cannot poison the
            # cache for every later validation.
            return dict(self._keys)

    def _load(self) -> dict[str, object]:
        document = self._fetch_json(application.SSO_METADATA, MAX_METADATA_BYTES)
        if not isinstance(document, dict):
            raise JwtError("EVE SSO metadata was not a JSON object.")
        issuer = document.get("issuer")
        if not isinstance(issuer, str) or issuer not in application.ACCEPTED_ISSUERS:
            # Checked before the JWKS fetch, so a hostile metadata document
            # never gets to make a second request happen at all.
            raise JwtError("EVE SSO metadata returned an unexpected issuer.")
        jwks_uri = document.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise JwtError("EVE SSO metadata returned an unexpected JWKS address.")
        parsed = urlparse(jwks_uri)
        # Absolute HTTPS on the SSO host, and an equality check rather than
        # a suffix match: the metadata document is the one input allowed to
        # name a URL whose contents this process then trusts, and a
        # relative, plaintext, or off-host value is exactly how that becomes
        # key substitution.
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.hostname.lower() != application.SSO_HOST):
            raise JwtError("EVE SSO metadata returned an unexpected JWKS address.")

        key_set = self._fetch_json(jwks_uri, MAX_JWKS_BYTES)
        entries = key_set.get("keys") if isinstance(key_set, dict) else None
        if not isinstance(entries, list):
            raise JwtError("EVE SSO returned an unreadable key set.")
        keys: dict[str, object] = {}
        for entry in entries:
            selected = _rsa_signing_key(entry)
            if selected is not None:
                keys[selected[0]] = selected[1]
        if not keys:
            # Caching an empty set would fail every token for a full TTL.
            raise JwtError("EVE SSO returned no usable signing keys.")
        return keys

    def _fetch_json(self, url: str, limit: int) -> object:
        request = urllib.request.Request(
            url, headers={"User-agent": application.USER_AGENT,
                          "Accept": "application/json"},
            method="GET")
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                # limit + 1 so an oversized body is detected rather than
                # silently truncated into something that still parses.
                raw = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            raise JwtError(f"EVE SSO key fetch returned {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise JwtError("EVE SSO key fetch could not reach "
                           f"{application.SSO_HOST}.") from exc
        if len(raw) > limit:
            raise JwtError("EVE SSO response exceeded the configured limit.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise JwtError("EVE SSO returned an unreadable key document.") from exc
```

- [ ] **Step 24: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_jwt.py -v`

- [ ] **Step 25: Commit**

```bash
git add obs_youtube_uploader/eveskills/jwt.py tests/test_eveskills_jwt.py
git commit -m "feat(eveskills): cache EVE JWKS signing keys with a guarded fetch"
```

---

### Task 10: `loopback.py` — the OAuth callback listener

**Files:**
- Create: `obs_youtube_uploader/eveskills/loopback.py`
- Test: `tests/test_eveskills_loopback.py`

**Interfaces:**
- Consumes: nothing. This module imports only the stdlib, so the parser can
  be reasoned about on its own.
- Produces:
  ```python
  CONNECTION_TIMEOUT_S = 10.0
  AUTH_TIMEOUT_S = 300.0
  MAX_LINE_BYTES = 8192
  MAX_HEADER_BYTES = 32 * 1024

  @dataclass(frozen=True)
  class Callback:
      code: str
      error: str

  class CallbackTimeout(Exception): ...
  class CallbackCancelled(Exception): ...

  def safe_oauth_code(value: object) -> str
      # filtered to [A-Za-z0-9_-], truncated to 64, "oauth_error" when empty

  def parse_request(raw: bytes, *, expected_host: str,
                    expected_path: str) -> dict[str, str]
      # returns the query mapping; raises ValueError on any violation

  class LoopbackListener:
      def __init__(self, *, host: str, port: int, path: str) -> None
      def __enter__(self) -> "LoopbackListener"
      def __exit__(self, *exc) -> None
      def wait(self, expected_state: str, *,
               timeout_s: float = AUTH_TIMEOUT_S) -> Callback
      def cancel(self) -> None
  ```

---

#### Cycle 1 — `parse_request`: the request line

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eveskills_loopback.py
"""The OAuth loopback callback listener.

parse_request is a PURE function over bytes, which is the whole reason it
exists as a separate function: every rejection rule below is exercised on
Linux with no socket, no browser, and no timing. The listener tests further
down do open a real loopback socket, but the security surface is proved here.
"""
import pytest

from obs_youtube_uploader.eveskills import loopback

HOST = "127.0.0.1:51779"
PATH = "/callback/"


def request(target="/callback/?code=abc&state=xyz", *,
            host=HOST, method="GET", version="HTTP/1.1", extra=()):
    """Assemble a raw HTTP/1.1 request as bytes."""
    lines = [f"{method} {target} {version}"]
    if host is not None:
        lines.append(f"Host: {host}")
    lines.extend(extra)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def parse(raw):
    return loopback.parse_request(raw, expected_host=HOST, expected_path=PATH)


@pytest.mark.xfail(reason="query parsing arrives in Cycle 3", strict=True)
def test_parses_a_well_formed_callback():
    assert parse(request()) == {"code": "abc", "state": "xyz"}


def test_rejects_any_method_other_than_get():
    """The callback is a browser navigation. Anything else is a probe, and
    the lowercase spelling is included because HTTP methods are
    case-sensitive and a tolerant comparison is one more thing to get right.
    """
    for method in ("POST", "HEAD", "OPTIONS", "get"):
        with pytest.raises(ValueError):
            parse(request(method=method))


def test_rejects_any_version_other_than_http_1_1():
    for version in ("HTTP/1.0", "HTTP/2", "HTTP/1.1x", ""):
        with pytest.raises(ValueError):
            parse(request(version=version))


def test_rejects_a_request_line_with_the_wrong_number_of_fields():
    """Split on a single space, with no empty-entry collapsing.

    A tolerant split accepts "GET  /callback/  HTTP/1.1" and, worse,
    "GET /callback/ HTTP/1.1 extra" -- neither of which any browser sends.
    """
    for line in (b"GET /callback/\r\n", b"GET  /callback/ HTTP/1.1\r\n",
                 b"GET /callback/ HTTP/1.1 extra\r\n", b"\r\n"):
        with pytest.raises(ValueError):
            parse(line + b"Host: 127.0.0.1:51779\r\n\r\n")


def test_rejects_an_absolute_form_target():
    """Only origin-form. An absolute-form target is another way to name an
    authority that the Host check never gets to see."""
    with pytest.raises(ValueError):
        parse(request(target="http://127.0.0.1:51779/callback/?state=xyz"))


def test_rejects_a_request_that_ends_mid_line():
    """A truncated request must fail, not be parsed as far as it got.

    A half-arrived request could omit the Host line entirely, which is the
    one header the DNS-rebinding guard depends on.
    """
    with pytest.raises(ValueError):
        parse(b"GET /callback/?state=xyz HTTP/1.1\r\nHost: 127.0.0.1:51779")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.loopback'`.

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/eveskills/loopback.py
"""The OAuth callback listener: a raw socket and a deliberately strict parser.

This is a RAW SOCKET, not http.server, and the strict parser is the entire
reason. http.server would happily accept duplicate query keys (last wins),
non-ASCII request bytes, an arbitrary Host header, and a target that merely
normalises to the callback path. Every one of those is a rejection here:

- duplicate query keys are how a parameter is smuggled past a check that
  read the first copy while the consumer reads the last,
- the Host check is the DNS-rebinding guard, and a duplicate Host is how
  that guard gets bypassed by whichever copy the checker did not read,
- non-ASCII is not something a browser sends to a loopback callback, so
  accepting it only widens what has to be reasoned about.

parse_request is pure over bytes so that all of the above is testable with
no socket, no browser, and no timing.
"""
import hmac
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import unquote

CONNECTION_TIMEOUT_S = 10.0
AUTH_TIMEOUT_S = 300.0
MAX_LINE_BYTES = 8192
MAX_HEADER_BYTES = 32 * 1024
MAX_QUERY_KEY_CHARS = 128
MAX_QUERY_VALUE_CHARS = 8192
MAX_CODE_CHARS = 2048

# How long a blocking accept() waits before rechecking cancellation and the
# overall deadline. Short enough that cancel() feels immediate, long enough
# that a five-minute wait is not a busy loop.
_ACCEPT_POLL_S = 0.25

_CODE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
_HEX = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True)
class Callback:
    code: str
    error: str


class CallbackTimeout(Exception):
    """The browser never came back within the overall deadline."""


class CallbackCancelled(Exception):
    """The wait was cancelled from another thread."""


def _read_line(raw: bytes, offset: int) -> tuple[str, int]:
    """Read one CRLF-terminated ASCII line, returning it and the next offset."""
    end = raw.find(b"\n", offset)
    if end < 0:
        # A truncated request must fail rather than be parsed as far as it
        # got: a half-arrived header set could omit the Host line entirely,
        # and that line is the DNS-rebinding guard.
        raise ValueError("Local callback request ended without a complete line.")
    chunk = raw[offset:end]
    if chunk.endswith(b"\r"):
        chunk = chunk[:-1]
    if len(chunk) > MAX_LINE_BYTES:
        raise ValueError("Local callback line exceeded its configured limit.")
    for byte in chunk:
        # NUL and anything above 0x7F. A browser navigating to a loopback
        # callback sends neither, so accepting them only widens the surface
        # everything below has to be correct against.
        if byte == 0 or byte > 127:
            raise ValueError("Local callback contained non-ASCII request data.")
    return chunk.decode("ascii"), end + 1


def parse_request(raw: bytes, *, expected_host: str,
                  expected_path: str) -> dict[str, str]:
    """Parse a callback request, returning its query mapping.

    Raises ValueError on any violation. There is no tolerant mode.
    """
    request_line, offset = _read_line(raw, 0)
    # Split on a single space with no empty-entry collapsing: a tolerant
    # split accepts "GET  /callback/  HTTP/1.1" and "GET /x HTTP/1.1 extra",
    # neither of which any browser sends.
    pieces = request_line.split(" ")
    if (len(pieces) != 3 or pieces[0] != "GET" or pieces[2] != "HTTP/1.1"
            or not pieces[1].startswith("/")):
        # startswith("/") pins origin-form: an absolute-form target is
        # another way to name an authority the Host check never sees.
        raise ValueError("Local callback request line was not a plain GET.")
    return _parse_headers(pieces[1], raw, offset,
                          expected_host=expected_host,
                          expected_path=expected_path)


def _parse_headers(target: str, raw: bytes, offset: int, *,
                   expected_host: str, expected_path: str) -> dict[str, str]:
    """Placeholder until Cycle 2: headers and query come next."""
    return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: green, with `test_parses_a_well_formed_callback` reported as `xfail`.
That marker is removed in Step 11 once query parsing lands.

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/loopback.py tests/test_eveskills_loopback.py
git commit -m "feat(eveskills): strict request-line parsing for the OAuth callback"
```

---

#### Cycle 2 — headers, the Host guard, and the byte caps

- [ ] **Step 6: Write the failing test**

```python
# tests/test_eveskills_loopback.py  (append)

def test_rejects_a_duplicate_host_header():
    """The DNS-rebinding guard, bypassed.

    With two Host headers, whichever copy the checker reads is not
    necessarily the one anything downstream reads. Rejecting outright is
    the only answer that does not depend on agreeing about which one wins.
    """
    with pytest.raises(ValueError, match="duplicate Host"):
        parse(request(extra=["Host: evil.test"]))


def test_rejects_a_missing_host_header():
    with pytest.raises(ValueError, match="Host"):
        parse(request(host=None))


def test_rejects_a_host_that_is_not_the_redirect_authority():
    """This is the DNS-rebinding guard itself.

    A page on any origin can point a name at 127.0.0.1 and have the browser
    issue this exact request; what it cannot do is forge the Host header,
    which still carries the name the browser resolved. The bare "127.0.0.1"
    case matters because a port-less Host is a different authority.
    """
    for host in ("evil.test", "evil.test:51779", "127.0.0.1:51780",
                 "localhost:51779", "127.0.0.1"):
        with pytest.raises(ValueError, match="Host"):
            parse(request(host=host))


def test_host_comparison_is_case_insensitive():
    """Case carries no meaning in a hostname."""
    assert parse(request(target="/callback/", host="127.0.0.1:51779")) == {}


def test_rejects_a_header_line_without_a_colon():
    with pytest.raises(ValueError):
        parse(request(extra=["NotAHeader"]))


def test_rejects_a_header_line_that_starts_with_a_colon():
    """An empty header name is malformed, and ": Host: evil.test" is a way
    to smuggle one past a checker that splits on the first colon."""
    with pytest.raises(ValueError):
        parse(request(extra=[": Host: evil.test"]))


def test_rejects_a_line_over_the_line_cap():
    """8 KiB per line. Without a cap, a single header line is unbounded
    memory before any check runs."""
    with pytest.raises(ValueError, match="line exceeded"):
        parse(request(extra=["X-Pad: " + "a" * (loopback.MAX_LINE_BYTES + 1)]))


def test_rejects_headers_over_the_total_cap():
    """32 KiB of headers. Individually-legal lines still have to stop."""
    filler = ["X-Pad-%04d: %s" % (index, "a" * 200) for index in range(300)]
    with pytest.raises(ValueError, match="headers"):
        parse(request(extra=filler))


def test_rejects_non_ascii_request_bytes():
    """A browser sends none to a loopback callback."""
    raw = request().replace(b"code=abc", b"code=ab\xc3\xa9")
    with pytest.raises(ValueError, match="non-ASCII"):
        parse(raw)


def test_rejects_a_nul_byte():
    raw = request().replace(b"code=abc", b"code=ab\x00")
    with pytest.raises(ValueError, match="non-ASCII"):
        parse(raw)
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: FAIL — `test_rejects_a_duplicate_host_header` with
`Failed: DID NOT RAISE <class 'ValueError'>`, since the placeholder
`_parse_headers` never reads a header.

- [ ] **Step 8: Write minimal implementation**

Replace the placeholder `_parse_headers`:

```python
def _parse_headers(target: str, raw: bytes, offset: int, *,
                   expected_host: str, expected_path: str) -> dict[str, str]:
    host = None
    header_bytes = 0
    while True:
        line, offset = _read_line(raw, offset)
        if line == "":
            break
        # +2 for the CRLF the line reader stripped. Individually-legal lines
        # still have to stop somewhere.
        header_bytes += len(line) + 2
        if header_bytes > MAX_HEADER_BYTES:
            raise ValueError("Local callback headers exceeded their configured limit.")
        separator = line.find(":")
        if separator <= 0:
            # <= 0 rather than < 0: an empty header name is malformed, and
            # ": Host: evil.test" is a way to smuggle one past a checker
            # that splits on the first colon.
            raise ValueError("Local callback sent a malformed header.")
        if line[:separator].strip().lower() != "host":
            continue
        if host is not None:
            raise ValueError("Local callback contained duplicate Host headers.")
        host = line[separator + 1:].strip()

    # The DNS-rebinding guard. A page on any origin can point a name at
    # 127.0.0.1 and make the browser issue this exact request; what it
    # cannot do is forge the Host header, which still carries the name the
    # browser resolved. Compared case-insensitively because case carries no
    # meaning in a hostname, and by equality because a port-less or
    # differently-ported authority is a different authority.
    if host is None or host.lower() != expected_host.lower():
        raise ValueError("Local callback Host header did not match the redirect authority.")

    return _parse_target(target, expected_path=expected_path)


def _parse_target(target: str, *, expected_path: str) -> dict[str, str]:
    """Placeholder until Cycle 3."""
    return {}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`

- [ ] **Step 10: Commit**

```bash
git add obs_youtube_uploader/eveskills/loopback.py tests/test_eveskills_loopback.py
git commit -m "feat(eveskills): guard the callback Host header and byte caps"
```

---

#### Cycle 3 — the target path and the query

- [ ] **Step 11: Write the failing test**

```python
# tests/test_eveskills_loopback.py  (append)

def test_target_path_must_match_exactly():
    """No normalisation, no prefix match, no trailing-slash tolerance.

    EVE echoes the registered redirect_uri back verbatim, so an exact match
    is achievable -- and accepting an encoded or dot-segment spelling of the
    same path would mean re-deriving every normalisation rule correctly for
    no benefit at all.
    """
    for bad in ("/callback", "/callback//", "/Callback/", "/callback/x",
                "/other/", "/", "/%63allback/", "/callback/../callback/"):
        with pytest.raises(ValueError, match="path"):
            parse(request(target=bad + "?state=xyz"))


def test_target_with_no_query_parses_to_an_empty_mapping():
    """A bare callback hit is well-formed; it just carries nothing."""
    assert parse(request(target="/callback/")) == {}
    assert parse(request(target="/callback/?")) == {}


def test_rejects_a_fragment_in_the_target():
    """Browsers never send one to a server, so its presence means something
    other than a browser assembled this request."""
    with pytest.raises(ValueError, match="fragment"):
        parse(request(target="/callback/?state=xyz#frag"))


def test_rejects_duplicate_query_keys():
    """No last-wins parameter smuggling.

    Two `state` values is the shape where a checker reading the first copy
    and a consumer reading the last disagree about what the request said.
    Rejecting is the only answer that does not depend on agreeing which copy
    wins.
    """
    with pytest.raises(ValueError, match="duplicate"):
        parse(request(target="/callback/?state=xyz&state=abc"))
    with pytest.raises(ValueError, match="duplicate"):
        parse(request(target="/callback/?code=a&state=xyz&code=b"))


def test_rejects_invalid_percent_encoding():
    """Validated BEFORE unquoting, because unquote() is lenient: it leaves a
    malformed escape in place rather than failing, so "%zz" would survive
    into a value that later reads as three characters nobody wrote."""
    for bad in ("state=%zz", "state=%", "state=%A", "%zz=xyz"):
        with pytest.raises(ValueError, match="percent"):
            parse(request(target="/callback/?" + bad))


def test_percent_encoding_is_decoded():
    assert parse(request(target="/callback/?state=a%2Fb")) == {"state": "a/b"}


def test_plus_becomes_a_space():
    """Form encoding, which is what a browser produces here. Leaving '+'
    alone would make a state comparison fail for a state that matched."""
    assert parse(request(target="/callback/?state=a+b")) == {"state": "a b"}


def test_a_key_with_no_equals_reads_as_an_empty_value():
    assert parse(request(target="/callback/?state")) == {"state": ""}


def test_empty_segments_are_skipped():
    assert parse(request(target="/callback/?&state=xyz&")) == {"state": "xyz"}


def test_rejects_an_oversized_query_key_or_value():
    with pytest.raises(ValueError, match="query"):
        parse(request(target="/callback/?" + "k" * 129 + "=v"))
    with pytest.raises(ValueError, match="query"):
        parse(request(target="/callback/?state=" + "v" * 8193))
```

Remove the `@pytest.mark.xfail` decorator from
`test_parses_a_well_formed_callback` in the same edit.

- [ ] **Step 12: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: FAIL — `test_target_path_must_match_exactly` with
`Failed: DID NOT RAISE`, and `test_parses_a_well_formed_callback` with
`assert {} == {'code': 'abc', 'state': 'xyz'}`.

- [ ] **Step 13: Write minimal implementation**

Replace the placeholder `_parse_target`:

```python
def _parse_target(target: str, *, expected_path: str) -> dict[str, str]:
    if "#" in target:
        # Browsers never send a fragment to a server, so its presence here
        # means something other than a browser assembled this request.
        raise ValueError("Local callback target contained a fragment.")
    marker = target.find("?")
    path = target if marker < 0 else target[:marker]
    query = "" if marker < 0 else target[marker + 1:]
    # An EXACT literal match. EVE echoes the registered redirect_uri back
    # verbatim, so exactness is achievable -- and accepting "/%63allback/"
    # or "/callback/../callback/" as the same path would mean re-deriving
    # every normalisation rule correctly, for no benefit at all.
    if path != expected_path:
        raise ValueError("Local callback target did not match the redirect path.")
    return _parse_query(query)


def _ensure_percent_encoding(value: str) -> None:
    """Reject malformed escapes BEFORE unquoting.

    unquote() is lenient: it leaves a malformed escape in place rather than
    failing, so "%zz" would survive into a value that reads as three
    characters nobody wrote.
    """
    index = 0
    while index < len(value):
        if value[index] == "%":
            if (index + 2 >= len(value) or value[index + 1] not in _HEX
                    or value[index + 2] not in _HEX):
                raise ValueError("Local callback query contained invalid percent encoding.")
            index += 2
        index += 1


def _parse_query(query: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key_text, separator, value_text = part.partition("=")
        _ensure_percent_encoding(key_text)
        if separator:
            _ensure_percent_encoding(value_text)
        # '+' means space here: this is form encoding, and leaving it alone
        # would make a state comparison fail for a state that matched.
        # errors="strict" so an escape that is syntactically valid but not
        # valid UTF-8 raises (UnicodeDecodeError is a ValueError) rather
        # than producing replacement characters.
        key = unquote(key_text.replace("+", " "), errors="strict")
        value = (unquote(value_text.replace("+", " "), errors="strict")
                 if separator else "")
        if len(key) > MAX_QUERY_KEY_CHARS or len(value) > MAX_QUERY_VALUE_CHARS:
            raise ValueError("Local callback query exceeded its configured limit.")
        if key in result:
            # No last-wins smuggling: two `state` values is the shape where
            # the checker and the consumer disagree about what was sent.
            raise ValueError("Local callback query contained a duplicate key.")
        result[key] = value
    return result
```

- [ ] **Step 14: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`

- [ ] **Step 15: Commit**

```bash
git add obs_youtube_uploader/eveskills/loopback.py tests/test_eveskills_loopback.py
git commit -m "feat(eveskills): reject duplicate query keys and bad escapes"
```

---

#### Cycle 4 — `safe_oauth_code` and the listener's success path

- [ ] **Step 16: Write the failing test**

```python
# tests/test_eveskills_loopback.py  (append)
import socket as _socket
import threading


def test_safe_oauth_code_filters_and_truncates():
    """Anything outside [A-Za-z0-9_-] is dropped; anything past 64 is cut.

    This is the filter every value from the callback passes through before
    it can reach a log line or a user-visible message.
    """
    assert loopback.safe_oauth_code("access_denied") == "access_denied"
    assert loopback.safe_oauth_code("a b<script>c") == "abscriptc"
    assert len(loopback.safe_oauth_code("x" * 200)) == 64


def test_safe_oauth_code_never_returns_empty():
    """An empty string in a message reads as "no error", which is a lie
    when the callback carried one. Non-string inputs land here too, because
    this runs on the failure path where a TypeError would replace the real
    diagnosis with a type error.
    """
    for value in ("", "   ", "<<<>>>", None, 42, ["a"]):
        assert loopback.safe_oauth_code(value) == "oauth_error"


def free_port() -> int:
    """A port nothing is listening on right now.

    Tests take a fresh port each rather than sharing one: SO_REUSEADDR is
    deliberately OFF in the listener, so a TIME_WAIT connection left behind
    by an earlier test would make the next bind fail.
    """
    probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


def send(port: int, raw: bytes) -> bytes:
    """Send one raw request to the listener and read the whole reply."""
    client = _socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        client.sendall(raw)
        chunks = []
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        client.close()


def listener_request(port, target, host=None):
    host = host or f"127.0.0.1:{port}"
    return (f"GET {target} HTTP/1.1\r\nHost: {host}\r\n\r\n").encode("ascii")


def deliver(port, target, into=None):
    """Start a thread that sends one request; returns (thread, sink list)."""
    sink = into if into is not None else []
    worker = threading.Thread(
        target=lambda: sink.append(send(port, listener_request(port, target))))
    worker.start()
    return worker, sink


def test_listener_returns_the_callback_on_a_matching_state():
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=abc123&state=expected-state")
        callback = listener.wait("expected-state", timeout_s=5)
        worker.join(5)

    assert callback.code == "abc123"
    assert callback.error == ""
    assert sink[0].startswith(b"HTTP/1.1 200 OK")


def test_the_reply_is_a_page_not_a_redirect_and_is_never_cached():
    """A redirect would hand the whole query string -- authorization code
    included -- to whatever the Location header named. A cacheable page
    would leave the outcome in the browser's history store."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=abc123&state=s")
        listener.wait("s", timeout_s=5)
        worker.join(5)

    reply = sink[0]
    assert b"HTTP/1.1 200 OK" in reply
    assert b"Cache-Control: no-store" in reply
    assert b"Location:" not in reply


def test_the_authorization_code_is_never_echoed_into_the_page():
    """The served page ends up in a browser tab the user may screenshot,
    and the code is a live one-time credential until it is exchanged."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, sink = deliver(port, "/callback/?code=SUPERSECRETCODE&state=s")
        listener.wait("s", timeout_s=5)
        worker.join(5)

    assert b"SUPERSECRETCODE" not in sink[0]


def test_a_hostile_error_value_cannot_escape_the_filter():
    """The error string reaches a user-visible message, so it goes through
    the [A-Za-z0-9_-] filter first. Without it a hostile value carries
    markup, a newline that forges a second log record, or a URL, straight
    into the UI."""
    port = free_port()
    hostile = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, _ = deliver(port, f"/callback/?error={hostile}&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.error == "scriptalert1script"
    assert "<" not in callback.error and ">" not in callback.error


def test_a_code_outside_the_safe_alphabet_is_ignored():
    """The code is charset-CHECKED, not truncated.

    Truncating a real EVE code to 64 characters would corrupt it, so the
    64-char truncating filter is what protects the LOG and MESSAGE path
    (safe_oauth_code, applied to `error` above). The code itself must
    already be in that alphabet; a request carrying anything else did not
    come from EVE, so it is treated as a probe and the listener keeps
    waiting rather than returning a code that will fail at the token
    endpoint with no explanation.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        threading.Thread(target=lambda: send(port, listener_request(
            port, "/callback/?code=bad%20code&state=s")), daemon=True).start()
        with pytest.raises(loopback.CallbackTimeout):
            listener.wait("s", timeout_s=1.0)
```

- [ ] **Step 17: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.loopback' has no attribute 'safe_oauth_code'`.

- [ ] **Step 18: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/loopback.py`:

```python
def safe_oauth_code(value: object) -> str:
    """Filter a callback value down to something safe to log or display.

    Everything outside [A-Za-z0-9_-] is dropped and the result is truncated
    to 64 characters. This is the filter every value coming off the wire
    passes through before it can reach a log line or a user-visible message:
    without it, a hostile `error` carries markup, a newline that forges a
    second log record, or a URL, straight into the UI.

    Non-string input is coerced rather than rejected: this runs on the
    failure path, where a TypeError would replace the real diagnosis.

    It never returns "": an empty string in a message reads as "no error",
    which is a lie when the callback carried one.
    """
    text = value if isinstance(value, str) else ""
    safe = "".join(ch for ch in text if ch in _CODE_CHARS)[:64]
    return safe or "oauth_error"


def _safe_authorization_code(value: str) -> str:
    """Return the code if it is already in the safe alphabet, else "".

    Deliberately NOT safe_oauth_code(): truncating a real EVE authorization
    code to 64 characters would corrupt it, and silently filtering
    characters out of a credential produces a code that fails at the token
    endpoint with no explanation at all. A code carrying anything else did
    not come from EVE, so the request is ignored and the listener keeps
    waiting for the one that did.
    """
    if not value or len(value) > MAX_CODE_CHARS:
        return ""
    return value if all(ch in _CODE_CHARS for ch in value) else ""


_SUCCESS_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>FlyGD Wingman</title></head><body><p>Authentication complete. "
    "You can close this tab and return to Wingman.</p></body></html>")
_FAILURE_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>FlyGD Wingman</title></head><body><p>Authentication was not "
    "accepted. You can close this tab and return to Wingman.</p></body></html>")


def _reply(connection, success: bool) -> None:
    """Serve the tiny result page.

    Always 200 and never a redirect: a 3xx would hand the whole query string
    -- authorization code included -- to whatever the Location header named.
    The page never echoes the code either, because it ends up in a browser
    tab the user may well screenshot. no-store keeps the outcome out of the
    browser's history store.
    """
    body = (_SUCCESS_HTML if success else _FAILURE_HTML).encode("utf-8")
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n").encode("ascii")
    try:
        connection.sendall(headers + body)
    except OSError:
        # The browser closing first is normal and is not a failure of the
        # flow: the callback has already been read off the wire.
        pass


def _read_request(connection) -> bytes:
    """Read until the end of the header block, bounded."""
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = connection.recv(4096)
        if not chunk:
            break
        buffer += chunk
        if len(buffer) > MAX_HEADER_BYTES + MAX_LINE_BYTES:
            raise ValueError("Local callback request exceeded its configured limit.")
    return bytes(buffer)


class LoopbackListener:
    """A single-port loopback listener for one OAuth callback."""

    def __init__(self, *, host: str, port: int, path: str) -> None:
        self._host = host
        self._port = port
        self._path = path
        self._authority = f"{host}:{port}"
        self._socket = None
        self._cancelled = threading.Event()

    def __enter__(self) -> "LoopbackListener":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR is deliberately NOT set. The port is fixed because
        # the redirect URI is registered with CCP and must match exactly,
        # and a bind failure means something else already holds the port --
        # a plain, reportable condition, not something to paper over by
        # sharing the port with whatever that something is.
        try:
            sock.bind((self._host, self._port))
            sock.listen(4)
        except OSError:
            sock.close()
            raise
        self._socket = sock
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def cancel(self) -> None:
        """Make a pending wait() raise CallbackCancelled."""
        self._cancelled.set()

    def wait(self, expected_state: str, *,
             timeout_s: float = AUTH_TIMEOUT_S) -> Callback:
        """Placeholder until Cycle 5."""
        raise NotImplementedError
```

- [ ] **Step 19: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_loopback.py -k safe_oauth -v`
Expected: the two `safe_oauth_code` tests pass. The listener tests still fail
with `NotImplementedError` and are completed in Cycle 5.

- [ ] **Step 20: Commit**

```bash
git add obs_youtube_uploader/eveskills/loopback.py tests/test_eveskills_loopback.py
git commit -m "feat(eveskills): filter callback values before they reach a message"
```

---

#### Cycle 5 — `wait()`: state comparison, persistence, timeout, cancellation

- [ ] **Step 21: Write the failing test**

```python
# tests/test_eveskills_loopback.py  (append)

def test_a_wrong_state_does_not_end_the_wait():
    """The listener serves the failure page and KEEPS LISTENING.

    This is what makes the flow survive a stray hit on the callback port: an
    unrelated request -- a scanner, a stale tab, a forged navigation -- must
    not consume the one callback the user is about to deliver. The real
    browser tab may still be coming.
    """
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        replies = []

        def both():
            replies.append(send(port, listener_request(
                port, "/callback/?code=wrong&state=not-the-state")))
            replies.append(send(port, listener_request(
                port, "/callback/?code=right&state=expected-state")))

        worker = threading.Thread(target=both)
        worker.start()
        callback = listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    assert callback.code == "right"
    # Both requests were answered; only the second ended the wait.
    assert len(replies) == 2
    assert replies[0].startswith(b"HTTP/1.1 200 OK")
    assert b"not accepted" in replies[0]


def test_a_malformed_request_does_not_end_the_wait():
    """A parse rejection is a probe, not a failure of the flow."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        def both():
            send(port, b"GET /callback/?state=expected-state HTTP/1.1\r\n"
                       b"Host: evil.test\r\n\r\n")
            send(port, listener_request(
                port, "/callback/?code=right&state=expected-state"))

        worker = threading.Thread(target=both)
        worker.start()
        callback = listener.wait("expected-state", timeout_s=10)
        worker.join(10)

    assert callback.code == "right"


def test_state_is_compared_in_constant_time():
    """hmac.compare_digest, not ==.

    The state is a CSRF token the caller minted; comparing it with == leaks
    a prefix-length oracle to anything that can time the failure page. This
    is asserted on the source because the timing itself is not observable
    from a test, and the invariant is what matters.
    """
    import inspect
    source = inspect.getsource(loopback.LoopbackListener.wait)
    assert "compare_digest" in source
    assert "== expected_state" not in source


def test_wait_times_out_when_the_browser_never_returns():
    """The overall deadline. Without it the auth worker thread never ends
    and the callback port is held for the life of the process."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        with pytest.raises(loopback.CallbackTimeout):
            listener.wait("expected-state", timeout_s=0.5)


def test_cancel_makes_a_pending_wait_raise():
    """The user closing the auth dialog must not leave a thread parked for
    five minutes holding the callback port."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        canceller = threading.Timer(0.2, listener.cancel)
        canceller.start()
        try:
            with pytest.raises(loopback.CallbackCancelled):
                listener.wait("expected-state", timeout_s=10)
        finally:
            canceller.cancel()


def test_an_error_callback_with_a_matching_state_is_returned():
    """A user clicking "Deny" is a real outcome, not a timeout: it must come
    back promptly so the UI can say what happened."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        worker, _ = deliver(port, "/callback/?error=access_denied&state=s")
        callback = listener.wait("s", timeout_s=5)
        worker.join(5)

    assert callback.error == "access_denied"
    assert callback.code == ""


def test_a_matching_state_with_neither_code_nor_error_keeps_waiting():
    """Right state, nothing usable in it. Returning here would report an
    outcome that did not happen."""
    port = free_port()
    with loopback.LoopbackListener(host="127.0.0.1", port=port, path=PATH) as listener:
        threading.Thread(target=lambda: send(port, listener_request(
            port, "/callback/?state=s")), daemon=True).start()
        with pytest.raises(loopback.CallbackTimeout):
            listener.wait("s", timeout_s=1.0)
```

- [ ] **Step 22: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`
Expected: FAIL with `NotImplementedError` from the Cycle 4 placeholder.

- [ ] **Step 23: Write minimal implementation**

Replace the placeholder `wait`:

```python
    def wait(self, expected_state: str, *,
             timeout_s: float = AUTH_TIMEOUT_S) -> Callback:
        """Serve callback hits until one carries the expected state.

        Raises CallbackTimeout at the overall deadline and CallbackCancelled
        when cancel() is called from another thread.
        """
        if self._socket is None:
            raise RuntimeError("The loopback listener is not open.")
        deadline = time.monotonic() + timeout_s
        while True:
            if self._cancelled.is_set():
                raise CallbackCancelled("EVE authentication was cancelled.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CallbackTimeout("EVE authentication timed out.")
            # Poll rather than block for the whole remaining time, so that
            # cancel() takes effect promptly without another thread having
            # to tear the listening socket down underneath this one.
            self._socket.settimeout(min(remaining, _ACCEPT_POLL_S))
            try:
                connection, _ = self._socket.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                if self._cancelled.is_set():
                    raise CallbackCancelled("EVE authentication was cancelled.")
                raise
            try:
                # Per-connection timeout: a client that connects and then
                # says nothing must not hold the whole flow hostage.
                connection.settimeout(CONNECTION_TIMEOUT_S)
                try:
                    query = parse_request(_read_request(connection),
                                          expected_host=self._authority,
                                          expected_path=self._path)
                except (ValueError, OSError):
                    # A rejected request is a probe -- a scanner, a stale
                    # tab, a forged navigation. It is not a failure of the
                    # flow, and consuming the wait would mean the real
                    # browser tab arrives to a closed port.
                    continue

                # compare_digest, not ==: the state is a CSRF token, and ==
                # leaks a prefix-length oracle to anything that can time the
                # failure page below.
                returned = query.get("state", "")
                if not hmac.compare_digest(expected_state, returned):
                    _reply(connection, False)
                    continue

                error = safe_oauth_code(query["error"]) if query.get("error") else ""
                code = _safe_authorization_code(query.get("code", ""))
                if not error and not code:
                    # Right state, nothing usable in it. Keep waiting rather
                    # than reporting an outcome that did not happen.
                    _reply(connection, False)
                    continue
                _reply(connection, not error and bool(code))
                return Callback(code=code, error=error)
            finally:
                try:
                    connection.close()
                except OSError:
                    pass
```

- [ ] **Step 24: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_loopback.py -v`

- [ ] **Step 25: Commit**

```bash
git add obs_youtube_uploader/eveskills/loopback.py tests/test_eveskills_loopback.py
git commit -m "feat(eveskills): keep listening past a mismatched OAuth state"
```

---

### Task 11: `sso.py` — PKCE and the token endpoint

**Files:**
- Create: `obs_youtube_uploader/eveskills/sso.py`
- Test: `tests/test_eveskills_sso.py`

**Interfaces:**
- Consumes:
  ```python
  # application.py (Task 1)
  CLIENT_ID: str
  REDIRECT_URI = "http://127.0.0.1:51779/callback/"
  SCOPES: tuple[str, ...]
  USER_AGENT: str
  SSO_AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize"
  SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"

  # loopback.py (Task 10)
  def safe_oauth_code(value: object) -> str
  ```
- Produces:
  ```python
  @dataclass(frozen=True)
  class Pkce:
      state: str
      verifier: str
      challenge: str

  @dataclass(frozen=True)
  class TokenSet:
      access_token: str
      refresh_token: str
      expires_in: int

  class OAuthError(Exception):
      def __init__(self, status: int, code: str, message: str) -> None
      status: int
      code: str
      @property
      def definitive(self) -> bool
          # code in {"invalid_grant", "identity_mismatch", "owner_changed"}

  def generate_pkce(*, randbytes=os.urandom) -> Pkce
  def authorize_url(pkce: Pkce) -> str
  def exchange_code(code: str, verifier: str, *, transport=...) -> TokenSet
  def refresh_token(token: str, *, transport=...) -> TokenSet
  ```

---

#### Cycle 1 — PKCE and the authorize URL

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eveskills_sso.py
"""EVE SSO: PKCE, the authorize URL, and the token endpoint.

No network anywhere in this file. The token endpoint is exercised through
the injected transport seam, the same shape discord.py uses.
"""
import inspect
import io
import json
import urllib.error
import urllib.parse

import pytest

from obs_youtube_uploader.eveskills import application, sso

# RFC 7636 Appendix B, verbatim. These 32 octets encode to the verifier
# below, whose ASCII bytes hash to the challenge below. Any drift in the
# encoding, the hash input, or the padding shows up here immediately.
RFC7636_OCTETS = bytes([
    116, 24, 223, 180, 151, 153, 224, 37, 79, 250, 96, 125, 216, 173,
    187, 186, 22, 212, 37, 77, 105, 214, 191, 240, 91, 88, 5, 88, 83,
    132, 141, 121])
RFC7636_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC7636_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_pkce_matches_the_rfc_7636_s256_vector():
    """S256 hashes the ASCII bytes of the ENCODED verifier.

    Hashing the raw 32 random bytes instead produces a challenge the server
    cannot reproduce, and the only symptom is invalid_grant at the token
    endpoint -- a failure that reads as a bad code, not as a bad challenge.
    The published vector is the cheapest possible way to pin this.
    """
    pkce = sso.generate_pkce(randbytes=lambda count: RFC7636_OCTETS[:count])
    assert pkce.verifier == RFC7636_VERIFIER
    assert pkce.challenge == RFC7636_CHALLENGE


def test_pkce_draws_thirty_two_bytes_each_for_state_and_verifier():
    """Two independent draws, 32 bytes apiece."""
    drawn = []

    def randbytes(count):
        drawn.append(count)
        return bytes([len(drawn)]) * count

    pkce = sso.generate_pkce(randbytes=randbytes)
    assert drawn == [32, 32]
    assert pkce.state != pkce.verifier


def test_pkce_values_are_base64url_without_padding():
    """Padding would need escaping in the URL and is not part of S256."""
    pkce = sso.generate_pkce()
    for value in (pkce.state, pkce.verifier, pkce.challenge):
        assert "=" not in value and "+" not in value and "/" not in value
        assert len(value) == 43       # 32 bytes, unpadded


def test_generate_pkce_is_random_by_default():
    """The production default must actually draw fresh entropy."""
    assert sso.generate_pkce().state != sso.generate_pkce().state


def query_of(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    # strict_parsing so a malformed pair is an error rather than a silent
    # drop, plus an explicit duplicate check parse_qsl would hide.
    pairs = urllib.parse.parse_qsl(parsed.query, strict_parsing=True)
    assert len(pairs) == len(dict(pairs)), "authorize URL had a duplicate key"
    return dict(pairs)


def test_authorize_url_carries_every_required_parameter():
    pkce = sso.generate_pkce()
    url = sso.authorize_url(pkce)
    assert url.startswith(application.SSO_AUTHORIZE + "?")
    assert query_of(url) == {
        "response_type": "code",
        "redirect_uri": application.REDIRECT_URI,
        "client_id": application.CLIENT_ID,
        "scope": " ".join(sorted(application.SCOPES)),
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }


def test_authorize_url_encodes_every_key_and_value():
    """The redirect URI carries "://" and "/", and the scope list carries
    spaces. Left raw, the query would end at the first character CCP's
    parser disagreed about -- and a truncated redirect_uri is a rejected
    authorization, not a visible error."""
    url = sso.authorize_url(sso.generate_pkce())
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A51779%2Fcallback%2F" in url
    assert " " not in url


def test_authorize_url_sorts_the_scopes():
    """A stable order keeps the URL reproducible and the consent screen
    identical between runs."""
    scope = query_of(sso.authorize_url(sso.generate_pkce()))["scope"]
    assert scope == " ".join(sorted(scope.split(" ")))


def test_no_client_secret_appears_anywhere():
    """This is a PUBLIC client: it ships to end users, so any secret baked
    into the binary would be readable by everyone holding it and would
    protect nothing at all. PKCE is what stands in for one."""
    source = inspect.getsource(sso)
    assert "client_secret" not in source
    assert "Authorization" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_sso.py -v`
Expected: FAIL with `ImportError: cannot import name 'sso' from 'obs_youtube_uploader.eveskills'`.

- [ ] **Step 3: Write minimal implementation**

```python
# obs_youtube_uploader/eveskills/sso.py
"""EVE SSO: PKCE generation, the authorize URL, and the token endpoint.

There is no client secret in this module, and there must never be one. The
EVE application is registered as a PUBLIC client: it ships to end users, so
a secret compiled into it would be readable by everyone holding the binary
and would protect exactly nothing. PKCE is what stands in for it, which is
why the verifier checks below are not cosmetic.
"""
import base64
import hashlib
import json
import os
import string
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import application
from .loopback import safe_oauth_code

MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
MAX_ACCESS_TOKEN_CHARS = 32 * 1024
MAX_REFRESH_TOKEN_CHARS = 2048
MAX_CODE_CHARS = 2048
MAX_EXPIRES_IN_S = 86_400
TIMEOUT_S = 20.0

# Failures meaning the stored grant is gone for good. Anything else -- 5xx,
# a network drop, an unfamiliar OAuth code -- is transient, and the split is
# what decides whether the roster row shows a re-authenticate banner or just
# an error with last-good data still visible.
_DEFINITIVE = frozenset({"invalid_grant", "identity_mismatch", "owner_changed"})

# RFC 7636's unreserved set for the code verifier.
_VERIFIER_CHARS = frozenset(string.ascii_letters + string.digits + "-._~")


@dataclass(frozen=True)
class Pkce:
    state: str
    verifier: str
    challenge: str


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int


class OAuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def definitive(self) -> bool:
        """True when re-authenticating is the only way forward.

        Widening this set logs users out over a bad gateway; narrowing it
        leaves a dead token retrying forever.
        """
        return self.code in _DEFINITIVE


def _b64url(raw: bytes) -> str:
    # Unpadded: "=" would need escaping in the URL, and S256 is defined over
    # the unpadded form.
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pkce(*, randbytes=os.urandom) -> Pkce:
    """Mint a fresh state, verifier, and S256 challenge."""
    state = _b64url(randbytes(32))
    verifier = _b64url(randbytes(32))
    # RFC 7636 S256 hashes the ASCII bytes of the ENCODED verifier, not the
    # random bytes behind it. Hashing the raw entropy instead produces a
    # challenge the server cannot reproduce, and the only symptom is
    # invalid_grant at the token endpoint -- which reads as a bad code, not
    # as a bad challenge, and costs an afternoon to find.
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return Pkce(state=state, verifier=verifier, challenge=challenge)


def authorize_url(pkce: Pkce) -> str:
    """Build the URL the browser is sent to."""
    query = {
        "response_type": "code",
        "redirect_uri": application.REDIRECT_URI,
        "client_id": application.CLIENT_ID,
        # Sorted, for a reproducible URL and an identical consent screen
        # between runs.
        "scope": " ".join(sorted(application.SCOPES)),
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }
    # safe="" so that ":" and "/" in the redirect URI and the spaces in the
    # scope list are all escaped. Left raw, the query would end at the first
    # character CCP's parser disagreed about, and a truncated redirect_uri
    # is a rejected authorization rather than a visible error.
    encoded = "&".join(
        f"{urllib.parse.quote(key, safe='')}={urllib.parse.quote(value, safe='')}"
        for key, value in query.items())
    return f"{application.SSO_AUTHORIZE}?{encoded}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_sso.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/sso.py tests/test_eveskills_sso.py
git commit -m "feat(eveskills): PKCE S256 and the EVE authorize URL"
```

---

#### Cycle 2 — the token endpoint and response validation

- [ ] **Step 6: Write the failing test**

```python
# tests/test_eveskills_sso.py  (append)

VERIFIER = RFC7636_VERIFIER

GOOD = {"access_token": "at-value", "refresh_token": "rt-value",
        "expires_in": 1199, "token_type": "Bearer"}


class FakeTransport:
    """Records the request and serves a canned JSON body."""

    def __init__(self, payload, status=200):
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outer = self

        class Response:
            status = outer.status

            def read(self, amount=None):
                return outer.body if amount is None else outer.body[:amount]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


def error_transport(status, payload):
    """A transport that raises HTTPError, the way urllib does on a non-2xx."""
    body = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

    def transport(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, status, "Error", {},
                                     io.BytesIO(body))

    return transport


def form_of(request) -> dict:
    return dict(urllib.parse.parse_qsl(request.data.decode("ascii"),
                                       strict_parsing=True))


def test_exchange_code_posts_the_authorization_code_grant():
    transport = FakeTransport(GOOD)
    tokens = sso.exchange_code("thecode", VERIFIER, transport=transport)
    request = transport.requests[0]
    assert request.full_url == application.SSO_TOKEN
    assert request.get_method() == "POST"
    assert form_of(request) == {
        "grant_type": "authorization_code",
        "code": "thecode",
        "client_id": application.CLIENT_ID,
        "code_verifier": VERIFIER,
        "redirect_uri": application.REDIRECT_URI,
    }
    assert tokens == sso.TokenSet("at-value", "rt-value", 1199)


def test_refresh_token_posts_the_refresh_grant():
    transport = FakeTransport(GOOD)
    tokens = sso.refresh_token("rt-old", transport=transport)
    assert form_of(transport.requests[0]) == {
        "grant_type": "refresh_token",
        "refresh_token": "rt-old",
        "client_id": application.CLIENT_ID,
    }
    assert tokens.access_token == "at-value"


def test_the_request_is_form_encoded_and_carries_the_user_agent():
    """CCP asks every client to identify itself, and the token endpoint only
    accepts form encoding."""
    transport = FakeTransport(GOOD)
    sso.refresh_token("rt-old", transport=transport)
    headers = {key.lower(): value for key, value
               in transport.requests[0].header_items()}
    assert headers["content-type"] == "application/x-www-form-urlencoded"
    assert headers["user-agent"] == application.USER_AGENT


def test_refresh_token_may_omit_a_new_refresh_token():
    """EVE sometimes answers a refresh without reissuing one.

    Treating that as a failure would force a re-authentication out of a
    perfectly normal response. The caller keeps the token it already holds,
    which is why "" is a valid value here and not an error.
    """
    payload = dict(GOOD)
    del payload["refresh_token"]
    tokens = sso.refresh_token("rt-old", transport=FakeTransport(payload))
    assert tokens.refresh_token == ""


def test_exchange_code_requires_a_refresh_token():
    """A code exchange with no refresh token yields a session that dies in
    twenty minutes with nothing stored to recover it."""
    payload = dict(GOOD)
    del payload["refresh_token"]
    with pytest.raises(sso.OAuthError, match="no refresh token"):
        sso.exchange_code("thecode", VERIFIER, transport=FakeTransport(payload))


def test_rejects_a_blank_or_oversized_access_token():
    for value in ("", "   ", "x" * (32 * 1024 + 1)):
        payload = dict(GOOD, access_token=value)
        with pytest.raises(sso.OAuthError, match="access token"):
            sso.refresh_token("rt", transport=FakeTransport(payload))


def test_rejects_an_oversized_refresh_token():
    """The token is about to be encrypted and written to disk; an unbounded
    one is an unbounded state file."""
    payload = dict(GOOD, refresh_token="x" * 2049)
    with pytest.raises(sso.OAuthError, match="refresh token"):
        sso.refresh_token("rt", transport=FakeTransport(payload))


def test_rejects_an_out_of_range_lifetime():
    """0 means already expired and a day-plus means something is wrong with
    the response -- and either would be stored as a refresh deadline.

    `True` is in the list because bool subclasses int, and `expires_in: true`
    would otherwise read as one second.
    """
    for value in (0, -1, 86_401, "1199", True, None):
        payload = dict(GOOD, expires_in=value)
        with pytest.raises(sso.OAuthError, match="token lifetime"):
            sso.refresh_token("rt", transport=FakeTransport(payload))


def test_token_type_is_compared_case_insensitively():
    """CCP has spelled it both ways, and the header this produces is
    identical either way."""
    for value in ("Bearer", "bearer", "BEARER"):
        payload = dict(GOOD, token_type=value)
        assert sso.refresh_token("rt", transport=FakeTransport(payload))
    with pytest.raises(sso.OAuthError, match="token type"):
        sso.refresh_token("rt", transport=FakeTransport(dict(GOOD, token_type="MAC")))


def test_rejects_a_non_json_body():
    """A proxy's HTML error page arrives with a 200 often enough to matter."""

    def transport(request, timeout=None):
        class Response:
            status = 200

            def read(self, amount=None):
                return b"<html>gateway</html>"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()

    with pytest.raises(sso.OAuthError, match="invalid token response"):
        sso.refresh_token("rt", transport=transport)


def test_rejects_a_json_body_that_is_not_an_object():
    """Every hop below would raise AttributeError on a list, and this runs
    on the path where that would replace the real diagnosis."""
    with pytest.raises(sso.OAuthError, match="invalid token response"):
        sso.refresh_token("rt", transport=FakeTransport(["at-value"]))


def test_rejects_inputs_before_they_reach_the_wire():
    """A blank code or a malformed verifier is a local bug, and sending it
    would spend a round trip to be told so."""
    unused = FakeTransport(GOOD)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("", VERIFIER, transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("code", "short", transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("code", "!" * 50, transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.refresh_token("", transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.refresh_token("rt\0value", transport=unused)
    assert unused.requests == []
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_sso.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.eveskills.sso' has no attribute 'exchange_code'`.

- [ ] **Step 8: Write minimal implementation**

Append to `obs_youtube_uploader/eveskills/sso.py`:

```python
class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on the token endpoint.

    The POST body carries the authorization code or the refresh token. A 3xx
    would let anything sitting in front of login.eveonline.com have urllib
    resend that credential to wherever the Location header points. Same seam
    and same reasoning as discord.py.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def exchange_code(code: str, verifier: str, *,
                  transport=_default_transport) -> TokenSet:
    """Trade an authorization code for a token set."""
    # Checked locally: sending a blank code or a malformed verifier spends a
    # round trip to be told about a bug that is entirely on this side.
    if not code or len(code) > MAX_CODE_CHARS or "\0" in code:
        raise OAuthError(0, "invalid_request", "The authorization code was invalid.")
    if not 43 <= len(verifier) <= 128 or any(ch not in _VERIFIER_CHARS for ch in verifier):
        raise OAuthError(0, "invalid_request", "The PKCE verifier was invalid.")
    payload = _post_token({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": application.CLIENT_ID,
        "code_verifier": verifier,
        "redirect_uri": application.REDIRECT_URI,
    }, transport)
    return _read_token_set(payload, require_refresh_token=True)


def refresh_token(token: str, *, transport=_default_transport) -> TokenSet:
    """Trade a stored refresh token for a fresh token set."""
    if not token or len(token) > MAX_REFRESH_TOKEN_CHARS or "\0" in token:
        raise OAuthError(0, "invalid_request", "The stored refresh token was invalid.")
    payload = _post_token({
        "grant_type": "refresh_token",
        "refresh_token": token,
        "client_id": application.CLIENT_ID,
    }, transport)
    return _read_token_set(payload, require_refresh_token=False)


def _post_token(form: dict, transport) -> dict:
    body = urllib.parse.urlencode(form).encode("ascii")
    request = urllib.request.Request(
        application.SSO_TOKEN, data=body,
        headers={"Content-type": "application/x-www-form-urlencoded",
                 "Accept": "application/json",
                 "User-agent": application.USER_AGENT},
        method="POST")
    try:
        with transport(request, timeout=TIMEOUT_S) as response:
            # limit + 1 so an oversized body is detected rather than
            # silently truncated into something that still parses.
            raw = response.read(MAX_TOKEN_RESPONSE_BYTES + 1)
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        # Unlike discord.py, this path DOES read a non-2xx body: the OAuth
        # error code lives in it, and the definitive/transient split -- which
        # decides whether the user is told to re-authenticate -- has nowhere
        # else to come from. Everything read here goes through
        # safe_oauth_code before it can reach a message.
        detail = b""
        try:
            detail = exc.read(MAX_TOKEN_RESPONSE_BYTES + 1)
        except OSError:
            pass
        code = _read_error_code(detail)
        raise OAuthError(exc.code, code,
                         f"EVE SSO token request returned {exc.code} ({code}).") from exc
    except (urllib.error.URLError, OSError) as exc:
        # Transient by construction: the code is not in _DEFINITIVE, so a
        # flaky connection can never cost the user their stored token.
        raise OAuthError(0, "network", "EVE SSO could not be reached.") from exc

    if len(raw) > MAX_TOKEN_RESPONSE_BYTES:
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.") from exc
    if not isinstance(parsed, dict):
        # Every hop below would raise AttributeError on a list, and this is
        # the failure path, where that would replace the real diagnosis with
        # a type error.
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.")
    return parsed


def _read_error_code(detail: bytes) -> str:
    """Pull the OAuth error code out of a non-2xx body, safely.

    The body is written by whatever answered the request, so the value goes
    through the same [A-Za-z0-9_-] filter the callback error does before it
    can reach a message. A filtered value that no longer equals a literal in
    _DEFINITIVE is therefore transient, which is the safe direction: a
    hostile body cannot log the user out.
    """
    try:
        parsed = json.loads(detail.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "oauth_error"
    if not isinstance(parsed, dict):
        return "oauth_error"
    return safe_oauth_code(parsed.get("error"))


def _read_token_set(payload: dict, *, require_refresh_token: bool) -> TokenSet:
    access = payload.get("access_token")
    if (not isinstance(access, str) or not access.strip()
            or len(access) > MAX_ACCESS_TOKEN_CHARS):
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid access token.")

    refresh = payload.get("refresh_token", "")
    if refresh is None:
        refresh = ""
    if (not isinstance(refresh, str) or len(refresh) > MAX_REFRESH_TOKEN_CHARS
            or "\0" in refresh):
        # Bounded because this is about to be encrypted and written to disk.
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid refresh token.")
    # Required on a code exchange, OPTIONAL on a refresh. EVE sometimes
    # answers a refresh without reissuing one and expects the caller to keep
    # the token it already holds; demanding one here would turn a perfectly
    # normal response into a forced re-authentication.
    if require_refresh_token and not refresh.strip():
        raise OAuthError(200, "invalid_response", "EVE SSO returned no refresh token.")

    expires = payload.get("expires_in")
    # bool is an int subclass, and `expires_in: true` must not read as 1.
    if (isinstance(expires, bool) or not isinstance(expires, int)
            or not 0 < expires <= MAX_EXPIRES_IN_S):
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid token lifetime.")

    token_type = payload.get("token_type")
    # Case-insensitive: CCP has spelled it both ways, and the Authorization
    # header this produces is identical either way.
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an unexpected token type.")

    return TokenSet(access_token=access, refresh_token=refresh, expires_in=expires)
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_sso.py -v`

- [ ] **Step 10: Commit**

```bash
git add obs_youtube_uploader/eveskills/sso.py tests/test_eveskills_sso.py
git commit -m "feat(eveskills): exchange and refresh EVE SSO tokens"
```

---

#### Cycle 3 — failure classification

- [ ] **Step 11: Write the failing test**

```python
# tests/test_eveskills_sso.py  (append)

def test_definitive_codes_are_exactly_the_three():
    """The split drives the UI: a definitive failure clears the stored token
    and shows a re-authenticate banner, while a transient one leaves
    last-good data on screen. Widening this set logs users out over a bad
    gateway; narrowing it leaves a dead token retrying forever."""
    for code in ("invalid_grant", "identity_mismatch", "owner_changed"):
        assert sso.OAuthError(400, code, "x").definitive is True
    for code in ("invalid_request", "server_error", "temporarily_unavailable",
                 "network", "oauth_error", "invalid_response", ""):
        assert sso.OAuthError(500, code, "x").definitive is False


def test_an_invalid_grant_response_is_classified_definitive():
    """The revoked-refresh-token case, end to end."""
    transport = error_transport(400, {"error": "invalid_grant",
                                      "error_description": "token revoked"})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "invalid_grant"
    assert caught.value.status == 400
    assert caught.value.definitive is True


def test_a_server_error_is_transient():
    """CCP's 5xx must not cost the user their stored token."""
    transport = error_transport(503, {"error": "server_error"})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.definitive is False


def test_a_network_failure_is_transient_and_carries_no_status():
    def transport(request, timeout=None):
        raise urllib.error.URLError("offline")

    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "network"
    assert caught.value.status == 0
    assert caught.value.definitive is False


def test_an_unparseable_error_body_falls_back_to_oauth_error():
    """A gateway HTML page is still a failure, just not a classified one --
    and an unclassified failure is transient, which is the safe default."""
    transport = error_transport(502, b"<html>bad gateway</html>")
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "oauth_error"
    assert caught.value.definitive is False


def test_a_hostile_error_code_cannot_reach_the_message():
    """The error code goes into a user-visible message, so it passes through
    the same [A-Za-z0-9_-] filter the callback error does. A body controlled
    by whatever answered the request must not carry markup or a newline into
    the UI -- and because the filtered value no longer equals the literal,
    it is NOT definitive either: a hostile body cannot log the user out."""
    transport = error_transport(400, {"error": "<script>alert(1)</script>\ninvalid_grant"})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert "<" not in caught.value.code and "\n" not in caught.value.code
    assert "<" not in str(caught.value)
    assert caught.value.definitive is False


def test_an_error_code_of_the_wrong_json_type_is_neutered():
    """`{"error": {"code": "invalid_grant"}}` is not a string; every hop is
    type-checked rather than trusted, because this runs on the failure path
    where a TypeError would replace the real diagnosis."""
    transport = error_transport(400, {"error": {"code": "invalid_grant"}})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "oauth_error"


def test_an_oauth_error_message_is_readable():
    """The status and the code both appear, because the pair is what a bug
    report needs and neither alone identifies the failure."""
    transport = error_transport(400, {"error": "invalid_grant"})
    with pytest.raises(sso.OAuthError, match="400.*invalid_grant"):
        sso.refresh_token("rt-old", transport=transport)
```

- [ ] **Step 12: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_sso.py -v`
Expected: PASS — the Cycle 2 implementation already carries `definitive` and
routes error codes through `safe_oauth_code`. These tests pin that behaviour
against future edits. If `test_a_hostile_error_code_cannot_reach_the_message`
fails, `_read_error_code` is returning the raw body value and Step 13 is not
optional.

- [ ] **Step 13: Write minimal implementation**

No production change is expected. If a test fails, the two lines that carry
this behaviour are:

```python
_DEFINITIVE = frozenset({"invalid_grant", "identity_mismatch", "owner_changed"})
```

```python
    return safe_oauth_code(parsed.get("error"))
```

- [ ] **Step 14: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: green, including the pre-existing suite.

- [ ] **Step 15: Commit**

```bash
git add tests/test_eveskills_sso.py
git commit -m "test(eveskills): pin the definitive/transient OAuth split"
```
### Task 12: `controller.py` — construction, state payload, plans

**Files:**
- Create: `obs_youtube_uploader/eveskills/controller.py`
- Test: `tests/test_eveskills_controller.py`

**Interfaces:**
- Consumes:
  - `paths.eve_skills_file() -> Path`, `paths.eve_skills_cache_file() -> Path`, `paths.skill_plans_dir() -> Path` (Task 1)
  - `application.CLIENT_ID`, `application.USER_AGENT`, `application.SCOPES`, `application.REDIRECT_HOST`, `application.REDIRECT_PORT`, `application.REDIRECT_PATH`, `application.is_configured() -> bool` (Task 1)
  - `evaluator.evaluate(requirements, skill_ids, active_levels, trained_levels, queue, has_snapshot) -> PlanAnalysis`; `evaluator.READY`, `evaluator.UNSCORED` (Task 3)
  - `planstore.list_plans(plans_dir) -> tuple[list[PlanFile], list[str]]`, `planstore.seed_starter_plan(plans_dir) -> bool`, `PlanFile.name/.requirements/.diagnostics/.ok` (Task 4)
  - `state.load(path) -> tuple[SkillsState, list[str]]`, `state.save(state, path) -> None`, `state.SkillsState`, `state.Character`, `state.MAX_CHARACTERS` (Task 5)
  - `skillids.load(path) -> tuple[SkillIdCache, list[str]]`, `SkillIdCache.type_ids() -> dict[str, int]` (Task 8)
  - `esi.EsiClient(*, user_agent, transport=..., sleep=...)` (Task 7)
- Produces:
  ```python
  class SkillsController:
      def __init__(self, *, state_path: Path, cache_path: Path, plans_dir: Path,
                   push, alert, client=None, key_source=None,
                   spawn=threading.Thread, open_folder=None,
                   launch_browser=webbrowser.open, now=_utcnow,
                   sso=None, listener_factory=None, validate_token=None) -> None
      def state_payload(self) -> dict
      def reload_plans(self) -> None
      def select_plan(self, plan_name) -> bool
      def open_plans_folder(self) -> None
  ```

> **Note on the signature.** The interface contract in `triffskills-plan.md`
> lists the collaborators a *neighbouring task* consumes. `sso`,
> `listener_factory` and `validate_token` are three further keyword-only
> injectables with production defaults, added under the global constraint that
> every collaborator is injectable — they are what keeps Task 14's auth tests
> headless. Nothing outside this module and its tests passes them.

---

- [ ] **Step 1: Write the failing test — construction, and the lock that is not optional**

```python
"""SkillsController: the single writer of the skills state document.

Every test here is headless. No network (the ESI client is a fake), no
sockets, no browser, no real threads unless the test says so, and `tmp_path`
for the state file, the id cache, and the plans folder.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from obs_youtube_uploader.eveskills import state as state_mod
from obs_youtube_uploader.eveskills.controller import SkillsController

UTC = timezone.utc
T0 = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


class Clock:
    """A `now` that only moves when a test moves it."""

    def __init__(self, start=T0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value = self.value + timedelta(seconds=seconds)


class DeferredSpawn:
    """Captures worker targets instead of starting threads.

    Deliberately does NOT run the target on `.start()`: the single-flight
    latch can only be tested if the first worker is still notionally in
    flight when the second request arrives.
    """

    def __init__(self):
        self.targets = []

    def __call__(self, *, target, daemon=False):
        self.targets.append(target)
        return SimpleNamespace(start=lambda: None)

    def run_next(self):
        self.targets.pop(0)()


def build(tmp_path, *, plans=None, characters=(), selected="", **kwargs):
    """A controller over a fresh tmp state dir, with its pushes recorded."""
    plans_dir = tmp_path / "skill_plans"
    plans_dir.mkdir(exist_ok=True)          # Exists, so nothing is seeded.
    for name, body in (plans or {}).items():
        (plans_dir / f"{name}.txt").write_text(body, encoding="utf-8")

    if characters or selected:
        seed = state_mod.SkillsState(characters=list(characters),
                                     selected_plan_name=selected)
        state_mod.save(seed, tmp_path / "eve_skills.json")

    pushed = []
    alerts = []
    controller = SkillsController(
        state_path=tmp_path / "eve_skills.json",
        cache_path=tmp_path / "eve_skills_cache.json",
        plans_dir=plans_dir,
        push=lambda handler, payload: pushed.append((handler, payload)),
        alert=lambda kind, title, body: alerts.append((kind, title, body)),
        client=object(),
        now=kwargs.pop("now", Clock()),
        **kwargs)
    return controller, pushed, alerts


def test_the_state_lock_is_re_entrant(tmp_path):
    """A plain Lock would deadlock, not raise.

    Commit paths mutate the roster and then call helpers that save, and the
    save path takes the same lock. With `threading.Lock` the first such
    nesting hangs the worker forever with no traceback and no log line --
    the app simply never finishes a refresh. `RLock` is therefore a
    correctness requirement, not a convenience, and is asserted rather than
    trusted to survive a future edit.
    """
    controller, _, _ = build(tmp_path)

    with controller._lock:
        with controller._lock:          # Deadlocks here under threading.Lock.
            assert True


def test_a_missing_state_file_is_an_empty_roster_not_an_error(tmp_path):
    """First launch has no document at all. state.load is tolerant, and the
    controller must surface that as an empty roster rather than refusing to
    construct -- the route has to render before a character can be added."""
    controller, _, _ = build(tmp_path)

    payload = controller.state_payload()
    assert payload["characters"] == []
    assert payload["selected_plan_name"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.eveskills.controller'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Orchestration for the EVE skills route: state ownership, workers, pushes.

This module is the only writer of the skills state document. Nothing else
opens it for writing -- not the auth worker, not the refresh worker, not the
bridge. `atomicio.py:1-5` is explicit that atomic replacement addresses torn
*reads* and says nothing about lost *updates*: "single writer ownership
settles who may write." Without a stated owner a forget completing during a
refresh is silently undone by the refresh's save, and a character authorised
mid-refresh disappears.

Auth, refresh, forget and plan selection can all be in flight at once -- the
two latches below stop two refreshes and two authorisations, and nothing
else. So every read-modify-write of the roster happens under `self._lock`,
and the mutation and the save live in the same critical section. It is never
correct to read a snapshot, work from it, and save later: the document is
written whole, so a stale snapshot silently reverts everything committed
since it was taken.

Datetimes are timezone-aware `datetime` objects everywhere inside the
package. This module is the bridge boundary and the only place they become
ISO strings.
"""
import json
import logging
import os
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import application, evaluator, planstore, skillids
from . import esi as esi_mod
from . import state as state_mod

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Injectable in tests; production reads the real clock exactly here."""
    return datetime.now(timezone.utc)


def _iso(value) -> str:
    """A datetime as ISO 8601, or "" when it is absent.

    "" rather than None because the page renders these directly and a
    JSON null would print as "null" in a table cell. Every timestamp in
    both payload shapes goes through this.
    """
    return value.isoformat() if value is not None else ""


def _default_open_folder(path: Path) -> None:
    """Open a folder in the shell. Windows only; a no-op elsewhere.

    `os.startfile` does not exist off Windows, so it is looked up at call
    time behind the platform check rather than imported -- the same posture
    `__main__.set_dpi_awareness()` takes with its Win32 calls. Off Windows
    this is a deliberate no-op: development boxes have no shell to ask, and
    a raised NotImplementedError would turn a cosmetic button into an
    alert.
    """
    if sys.platform != "win32":
        return
    os.startfile(str(path))  # noqa: attribute exists only on Windows


class SkillsController:
    """Owns the roster in memory and the state document on disk."""

    def __init__(self, *, state_path, cache_path, plans_dir, push, alert,
                 client=None, key_source=None, spawn=threading.Thread,
                 open_folder=None, launch_browser=webbrowser.open,
                 now=_utcnow, sso=None, listener_factory=None,
                 validate_token=None) -> None:
        self._state_path = Path(state_path)
        self._cache_path = Path(cache_path)
        self._plans_dir = Path(plans_dir)
        self._push_cb = push
        self._alert = alert
        self._now = now
        self._spawn = spawn
        self._launch_browser = launch_browser
        self._open_folder = (open_folder if open_folder is not None
                             else _default_open_folder)
        self._client = client if client is not None else esi_mod.EsiClient(
            user_agent=application.USER_AGENT)
        # Built lazily on first use rather than here: constructing a
        # SigningKeySource is cheap but a JWKS fetch is not, and a user who
        # never signs in must never pay for one.
        self._key_source = key_source
        self._sso = sso
        self._listener_factory = listener_factory
        self._validate_token = validate_token

        # THE lock. Re-entrant because commit paths mutate the roster and
        # then call helpers that also save, and the save path takes this
        # same lock. A plain Lock would deadlock on the first such nesting,
        # and discovering that at runtime costs a hung worker rather than
        # an exception -- no traceback, no log line, just a refresh that
        # never finishes.
        self._lock = threading.RLock()

        self._state, warnings = state_mod.load(self._state_path)
        cache, cache_warnings = skillids.load(self._cache_path)
        self._cache = cache
        self._load_warnings = list(warnings) + list(cache_warnings)

        self._plans: list = []
        self._plan_warnings: list[str] = []
        self._plans_updated = None
        # The last payload actually sent, as JSON. `onSkills` carries the
        # whole world and is the largest payload in the app; mutation
        # handlers push it on both success and failure paths, so an
        # identical re-push is common and costs a full serialise plus a DOM
        # rebuild for nothing.
        self._last_push_json = ""

        # Seeded only when the folder is absent. Re-seeding on every launch
        # would resurrect a starter plan the user deliberately deleted.
        if not self._plans_dir.exists():
            try:
                planstore.seed_starter_plan(self._plans_dir)
            except OSError:
                logger.exception("Could not seed the starter skill plan")
        with self._lock:
            self._load_plans_locked()

    # ----- plans ----------------------------------------------------------

    def _load_plans_locked(self) -> None:
        try:
            plans, warnings = planstore.list_plans(self._plans_dir)
        except OSError as exc:
            # A plans folder that cannot be read is a warning in the
            # notices strip, not a dead route: the roster and every
            # character in it still render.
            plans, warnings = [], [f"Could not read the plans folder: {exc}"]
        self._plans = plans
        self._plan_warnings = list(warnings)
        self._plans_updated = self._now()

    def _find_plan_locked(self, name: str):
        """Case-insensitive, per the global rule for plan names."""
        target = str(name or "").casefold()
        if not target:
            return None
        for plan in self._plans:
            if plan.name.casefold() == target:
                return plan
        return None

    def _selected_plan_locked(self):
        return self._find_plan_locked(self._state.selected_plan_name)

    # ----- persistence ----------------------------------------------------

    def _save_locked(self) -> bool:
        """Write the document. Returns False rather than raising.

        A refresh that fetched good data and then failed to save has live
        data in memory and nothing on disk. That is a degraded state, not a
        failed one, and the caller flags the row accordingly -- so this
        reports the failure instead of unwinding a commit that is already
        correct in memory.
        """
        try:
            state_mod.save(self._state, self._state_path)
            return True
        except OSError:
            logger.exception("Could not save the EVE skills state document")
            return False

    # ----- payload --------------------------------------------------------

    def state_payload(self) -> dict:
        with self._lock:
            return self._state_payload_locked()

    def _state_payload_locked(self) -> dict:
        selected = self._selected_plan_locked()
        ids = self._cache.type_ids()
        return {
            "auth_configured": application.is_configured(),
            "auth_in_progress": False,      # Task 14 supplies the real flag.
            "refresh_in_flight": False,     # Task 13 supplies the real flag.
            "selected_plan_name": selected.name if selected else "",
            "plans": [self._plan_row_locked(plan, ids) for plan in self._plans],
            "characters": [self._character_row(ch, selected, ids)
                           for ch in self._state.characters],
            "plan_issues": [
                {"file_name": f"{plan.name}.txt",
                 # Any diagnostic rejects the whole file -- there is no
                 # partial-success mode -- so the summary says so once and
                 # the per-line detail hangs off it.
                 "message": "The file was rejected; no requirements were loaded.",
                 "diagnostics": [{"line": d.line, "message": d.message}
                                 for d in plan.diagnostics]}
                for plan in self._plans if not plan.ok],
            "warnings": list(self._load_warnings) + list(self._plan_warnings),
            "plans_updated_utc": _iso(self._plans_updated),
        }

    def _plan_row_locked(self, plan, ids) -> dict:
        """One left-rail row: the plan's size and how many can fly it.

        Every character is evaluated against every plan here, which is
        O(plans x characters) evaluations per payload. Seven plans against
        forty characters is under three hundred passes over a few dozen
        requirements, which is far cheaper than caching it would be to keep
        correct across a refresh that lands mid-render.
        """
        ready = 0
        if plan.ok:
            for ch in self._state.characters:
                if not ch.has_snapshot:
                    continue
                analysis = evaluator.evaluate(
                    plan.requirements, ids, ch.active_levels,
                    ch.trained_levels, ch.queue, True)
                if analysis.readiness == evaluator.READY:
                    ready += 1
        return {"name": plan.name,
                "requirement_count": len(plan.requirements),
                "ready_count": ready}

    def _character_row(self, ch, plan, ids) -> dict:
        """One roster row, scored against the selected plan.

        `analysis` is None when no plan is selected or the selected file was
        rejected. A character with no snapshot at all scores `Unscored` with
        empty requirements from the evaluator itself, so both cases land on
        the same row shape -- `Unscored` with zero counts, which is the most
        common state a user sees and is not padding.
        """
        analysis = None
        if plan is not None and plan.ok:
            analysis = evaluator.evaluate(
                plan.requirements, ids, ch.active_levels, ch.trained_levels,
                ch.queue, ch.has_snapshot)
        return {
            "character_id": ch.character_id,
            "character_name": ch.character_name,
            "fetched_utc": _iso(ch.fetched_utc),
            "error": ch.error,
            "needs_reauth": bool(ch.needs_reauth),
            "stale": ch.stale,
            "readiness": analysis.readiness if analysis else evaluator.UNSCORED,
            "estimated_finish_utc": (_iso(analysis.estimated_finish_utc)
                                     if analysis else ""),
            "queue_timing_unknown": (bool(analysis.queue_timing_unknown)
                                     if analysis else False),
            "active_count": analysis.active_count if analysis else 0,
            "trained_inactive_count": (analysis.trained_inactive_count
                                       if analysis else 0),
            "queued_count": analysis.queued_count if analysis else 0,
            "missing_count": analysis.missing_count if analysis else 0,
            "unknown_count": analysis.unknown_count if analysis else 0,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): SkillsController construction and state payload"
```

---

- [ ] **Step 6: Write the failing test — the payload scores every character**

```python
def test_a_character_with_no_snapshot_is_unscored_with_zero_counts(tmp_path):
    """Every newly authorised character is Unscored until its first refresh
    lands, and so is any character whose first refresh failed. The row must
    still render -- the expanded row is the ONLY surface for forgetting or
    re-authenticating, so a character with no row is a character that cannot
    be repaired."""
    character = state_mod.Character(character_id=95, character_name="Zuelo Parvi")
    controller, _, _ = build(tmp_path, characters=[character],
                             plans={"Interceptor": "Navigation V\n"},
                             selected="Interceptor")

    row = controller.state_payload()["characters"][0]

    assert row["readiness"] == "Unscored"
    assert row["fetched_utc"] == ""
    assert (row["active_count"], row["missing_count"],
            row["unknown_count"]) == (0, 0, 0)


def test_with_no_plan_selected_every_character_is_unscored(tmp_path):
    """Not an error state: the route opens with nothing selected, and forty
    rows reading Unscored is the correct first frame."""
    character = state_mod.Character(character_id=95, character_name="Aiga",
                                    fetched_utc=T0)
    controller, _, _ = build(tmp_path, characters=[character],
                             plans={"Interceptor": "Navigation V\n"})

    payload = controller.state_payload()

    assert payload["selected_plan_name"] == ""
    assert payload["characters"][0]["readiness"] == "Unscored"


def test_plan_rows_carry_their_size_and_their_ready_count(tmp_path):
    """The left rail shows a ready ratio per plan, so the payload has to
    score every character against every plan, not only the selected one."""
    controller, _, _ = build(tmp_path, plans={
        "Interceptor": "Navigation V\nSpaceship Command III\n",
        "Hauler": "Navigation I\n"})

    rows = {row["name"]: row for row in controller.state_payload()["plans"]}

    assert rows["Interceptor"]["requirement_count"] == 2
    assert rows["Hauler"]["requirement_count"] == 1
    assert rows["Interceptor"]["ready_count"] == 0   # No characters at all.


def test_a_rejected_plan_file_becomes_a_plan_issue(tmp_path):
    """Any diagnostic rejects the whole file. The row still appears in the
    rail with zero requirements, and the reason rolls up into plan_issues --
    a plan that silently vanished would look like a missing file."""
    controller, _, _ = build(tmp_path, plans={"Broken": "Navigation +5\n"})

    payload = controller.state_payload()

    assert payload["plan_issues"][0]["file_name"] == "Broken.txt"
    assert payload["plan_issues"][0]["diagnostics"][0]["line"] == 1
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: PASS — these pin the payload written in Step 3. If `plan_issues` or the
`Unscored` fallback were wrong they fail with a `KeyError` or a readiness mismatch.

- [ ] **Step 8: Commit**

```bash
git add tests/test_eveskills_controller.py
git commit -m "test(eveskills): pin Unscored rows and the plan-issues rollup"
```

---

- [ ] **Step 9: Write the failing test — plan selection and the push dedupe**

```python
def test_selecting_a_plan_is_case_insensitive_and_stores_the_file_spelling(tmp_path):
    """All comparisons on plan names are case-insensitive, but what is
    persisted is the file's own spelling -- the rail renders from the stored
    name, and echoing the caller's casing would make the selected row look
    different from the same row unselected."""
    controller, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})

    assert controller.select_plan("iNtErCePtOr") is True
    assert controller.state_payload()["selected_plan_name"] == "Interceptor"


def test_selecting_an_unknown_plan_reports_failure(tmp_path):
    """The page can hold a stale plan list across a reload that deleted the
    file. False is the honest answer; the forced push that does not happen
    is deliberate, because nothing changed."""
    controller, pushed, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})

    assert controller.select_plan("Gone") is False
    assert pushed == []


def test_selecting_persists_across_a_reconstruction(tmp_path):
    """The selection lives in the state document, not in the page. Reopening
    Wingman must land on the plan the user was last looking at."""
    controller, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})
    controller.select_plan("Interceptor")

    reopened, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})
    assert reopened.state_payload()["selected_plan_name"] == "Interceptor"


def test_an_identical_push_is_skipped_but_a_mutation_always_pushes(tmp_path):
    """onSkills carries the whole world and is the largest payload in the
    app. Mutation handlers push it on both success and failure paths, so an
    unchanged re-push is common -- and a full serialise plus a roster rebuild
    for an identical payload is pure cost.

    Mutations force the push regardless, because the dedupe is an
    optimisation and must never be the reason a committed change fails to
    reach the page."""
    controller, pushed, _ = build(tmp_path, plans={"A": "Navigation I\n"})

    controller._push_state()
    controller._push_state()                 # Identical: skipped.
    assert len(pushed) == 1

    controller.select_plan("A")              # Mutation: forced.
    controller.select_plan("A")              # Same value, still forced.
    assert len(pushed) == 3
```

- [ ] **Step 10: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute 'select_plan'`

- [ ] **Step 11: Write minimal implementation**

Append to `SkillsController`:

```python
    # ----- pushing --------------------------------------------------------

    def _push_state(self, *, force: bool = False) -> None:
        """Send the whole world to the page, deduped against the last send.

        `force` is not an optimisation switch: every mutation path sets it,
        because a committed change that the dedupe swallows is a page
        showing state the controller no longer holds. The dedupe exists for
        the *idle* re-pushes -- a refresh pass that returns all-304, a
        no-op toggle -- where the payload genuinely has not moved.
        """
        payload = self.state_payload()
        blob = json.dumps(payload, sort_keys=True, default=str)
        with self._lock:
            if not force and blob == self._last_push_json:
                return
            self._last_push_json = blob
        # Outside the lock: `push` reaches pywebview, and holding the state
        # lock across a bridge call would let a slow page block a refresh
        # worker's commit.
        self._push_cb("onSkills", payload)

    # ----- plan commands --------------------------------------------------

    def reload_plans(self) -> None:
        with self._lock:
            self._load_plans_locked()
        self._push_state(force=True)

    def select_plan(self, plan_name) -> bool:
        """Select a plan by name. False when it no longer exists.

        The empty string is a valid selection -- it clears the choice -- so
        it is handled before the lookup rather than falling into it.
        """
        name = str(plan_name or "")
        with self._lock:
            if name:
                plan = self._find_plan_locked(name)
                if plan is None:
                    # The page can hold a stale plan list across a reload
                    # that deleted the file. Reported rather than coerced to
                    # "no selection", which would silently discard a click.
                    return False
                # The file's own spelling, not the caller's: the rail
                # renders from the stored name.
                self._state.selected_plan_name = plan.name
            else:
                self._state.selected_plan_name = ""
            self._save_locked()
        self._push_state(force=True)
        return True

    def open_plans_folder(self) -> None:
        """Show the plans folder in the shell. Never raises.

        The folder is created first: on a machine where the starter plan
        could not be seeded it may not exist, and opening a path that is
        not there is an error dialog from the shell rather than from us.
        """
        with self._lock:
            plans_dir = self._plans_dir
        try:
            plans_dir.mkdir(parents=True, exist_ok=True)
            self._open_folder(plans_dir)
        except Exception:
            logger.exception("Could not open the skill plans folder")
            self._alert("warning", "Could not open the plans folder",
                        f"The folder is {plans_dir}.")
```

- [ ] **Step 12: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 13: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): plan selection, reload, and the onSkills dedupe"
```

---

- [ ] **Step 14: Write the failing test — reload picks up the folder, and open is injected**

```python
def test_reload_plans_sees_a_file_added_since_construction(tmp_path):
    """The whole point of the button: the user drops a .txt in the folder
    with Wingman already running."""
    controller, _, _ = build(tmp_path, plans={"A": "Navigation I\n"})
    (tmp_path / "skill_plans" / "B.txt").write_text("Navigation II\n",
                                                    encoding="utf-8")

    controller.reload_plans()

    assert [p["name"] for p in controller.state_payload()["plans"]] == ["A", "B"]


def test_open_plans_folder_uses_the_injected_opener(tmp_path):
    """os.startfile does not exist off Windows, so the shell call is
    injected and the suite asserts the path rather than the platform."""
    opened = []
    controller, _, _ = build(tmp_path, open_folder=opened.append)

    controller.open_plans_folder()

    assert opened == [tmp_path / "skill_plans"]


def test_a_failing_opener_warns_instead_of_raising(tmp_path):
    """This runs on the bridge thread. An exception here surfaces only as a
    rejected promise in a page nobody is debugging, so it becomes the alert
    channel that already exists."""
    def boom(path):
        raise OSError("no shell")

    controller, _, alerts = build(tmp_path, open_folder=boom)

    controller.open_plans_folder()

    assert alerts and alerts[0][0] == "warning"
```

- [ ] **Step 15: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: PASS — Step 11 implemented all three. If `open_plans_folder` had let the
`OSError` escape, the third test fails with `OSError: no shell`.

- [ ] **Step 16: Commit**

```bash
git add tests/test_eveskills_controller.py
git commit -m "test(eveskills): plan reload and the injected folder opener"
```

---

### Task 13: `controller.py` — the refresh worker

**Files:**
- Modify: `obs_youtube_uploader/eveskills/controller.py` (append; extend `__init__`)
- Test: `tests/test_eveskills_controller.py` (append)

**Interfaces:**
- Consumes:
  - `esi.EsiResponse` with `.status`, `.data`, `.error`, `.etag`, `.ok`, `.not_modified`; `EsiClient.get(path, *, token=None, etag=None) -> EsiResponse` (Task 7)
  - `skillids.resolve(cache, names, client, *, max_workers=4) -> dict[str, str]`, `skillids.save(cache, path) -> None`, `SkillIdCache.unresolved(names) -> list[str]` (Task 8)
  - `tokens.wrap(token, *, protect=...) -> str`, `tokens.unwrap(blob, *, unprotect=...) -> str | None` (Task 6)
  - `sso.refresh_token(token, *, transport=...) -> TokenSet`; `sso.TokenSet.access_token/.refresh_token/.expires_in`; `sso.OAuthError` with `.status`, `.code`, `.definitive` (Task 11)
  - `evaluator.QueueEntry(skill_id, finished_level, start_date, finish_date, queue_position)` (Task 3)
- Produces:
  ```python
  MSG_REAUTH: str
  MSG_NO_TOKEN: str
  MSG_TOKEN_UNREADABLE: str
  MSG_SAVE_FAILED: str
  TOKEN_EXPIRY_MARGIN_S = 30

  class SkillsController:
      def refresh_characters(self) -> None      # single-flight; spawns a worker
  ```

---

- [ ] **Step 1: Write the failing test — the single-flight latch**

```python
def test_two_concurrent_refreshes_produce_exactly_one_worker(tmp_path):
    """Ported from TriffSkillsController.cs:358. A second worker would send
    two ESI calls per character for the same data, doubling the pressure on
    the error-limit budget to compute the same answer twice -- and both
    workers would commit into the same roster."""
    spawn = DeferredSpawn()
    controller, _, _ = build(tmp_path, spawn=spawn)

    controller.refresh_characters()
    controller.refresh_characters()

    assert len(spawn.targets) == 1


def test_the_running_pass_re_enters_when_one_was_requested_during_it(tmp_path):
    """The latch drops the *worker*, never the *request*. A refresh clicked
    while one is running must still produce fresh data -- otherwise the
    button silently does nothing during the twenty seconds a forty-character
    pass takes, which reads as a broken button."""
    character = state_mod.Character(character_id=95, refresh_token_blob="blob")
    esi = FakeEsi()
    esi.on_get = lambda path: controller.refresh_characters()  # once; see below
    controller, _, _ = build(tmp_path, characters=[character], client=esi,
                             sso=FakeSso(), spawn=DirectSpawn())

    controller.refresh_characters()

    # Two passes over the one character: two skills calls, two queue calls.
    assert len([c for c in esi.calls if c[0].endswith("/skills/")]) == 2
```

Add the two fakes at the top of the test module:

```python
from obs_youtube_uploader.eveskills import esi as esi_mod
from obs_youtube_uploader.eveskills import sso as sso_mod


def esi_response(status, data=None, etag="", error="", path="/x/"):
    return esi_mod.EsiResponse(status=status, data=data, error=error,
                               etag=etag, method="GET", path=path)


SKILLS_BODY = {"skills": [{"skill_id": 3327, "active_skill_level": 4,
                           "trained_skill_level": 5}]}
QUEUE_BODY = [{"skill_id": 3327, "finished_level": 5, "queue_position": 0,
               "start_date": "2026-08-24T12:00:00Z",
               "finish_date": "2026-08-26T12:00:00Z"}]


class FakeEsi:
    """Replays scripted responses per path suffix, and records every call.

    Keyed on the suffix rather than the whole path so a test does not have
    to repeat the character id. A path with no script is an assertion
    failure, not a default -- an unexpected ESI call is exactly the bug
    these tests exist to catch.
    """

    def __init__(self, skills=None, queue=None):
        self.skills = list(skills or [esi_response(200, SKILLS_BODY, etag='"s1"')])
        self.queue = list(queue or [esi_response(200, QUEUE_BODY, etag='"q1"')])
        self.calls = []
        self.on_get = None
        self._hooked = False

    def get(self, path, *, token=None, etag=None):
        self.calls.append((path, token, etag))
        if self.on_get is not None and not self._hooked:
            self._hooked = True          # Fires once, or the test never ends.
            self.on_get(path)
        script = self.skills if path.endswith("/skills/") else self.queue
        assert script, f"unscripted ESI call: {path}"
        return script.pop(0) if len(script) > 1 else script[0]

    def post(self, path, body, *, token=None):
        raise AssertionError(f"unexpected POST {path}")


class FakeSso:
    """sso.refresh_token without a network.

    Only the functions the controller calls are defined. OAuthError itself
    is NOT faked: the controller's `except` clause names the real class from
    the real module, so a fake raising anything else would pass a test the
    production path would fail.
    """

    def __init__(self, expires_in=1200, raises=None):
        self.expires_in = expires_in
        self.raises = raises
        self.refreshes = []

    def refresh_token(self, token, **kwargs):
        self.refreshes.append(token)
        if self.raises is not None:
            raise self.raises
        return sso_mod.TokenSet(access_token=f"access-{len(self.refreshes)}",
                                refresh_token=f"refresh-{len(self.refreshes)}",
                                expires_in=self.expires_in)


class DirectSpawn:
    """Runs the worker inline on `.start()`, so no test waits on a thread."""

    def __init__(self):
        self.started = 0

    def __call__(self, *, target, daemon=False):
        self.started += 1
        return SimpleNamespace(start=target)
```

`build()` also needs to stop wrapping the refresh token, since tests store a
plain `"blob"`; add to the module:

```python
@pytest.fixture(autouse=True)
def plaintext_tokens(monkeypatch):
    """DPAPI is Windows-only, so the crypt seam is bypassed for the suite.

    tokens.py's own tests cover wrap/unwrap and the undecryptable blob.
    Here the token is a value the controller carries, and encrypting it
    would only make the assertions unreadable.
    """
    from obs_youtube_uploader.eveskills import tokens as tokens_mod
    monkeypatch.setattr(tokens_mod, "wrap", lambda token, **kw: token)
    monkeypatch.setattr(tokens_mod, "unwrap", lambda blob, **kw: blob or None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute 'refresh_characters'`

- [ ] **Step 3: Write minimal implementation**

Extend `__init__` (after `self._last_push_json = ""`):

```python
        # Single-flight latch. `_refresh_again` is the *request* that arrived
        # while a pass was running; the worker re-enters on it rather than
        # dropping it, so a click during a refresh is never silently lost.
        self._refresh_in_flight = False
        self._refresh_again = False
        # character_id -> (access_token, expires_at). Memory only, and
        # deliberately so: an access token lives twenty minutes and writing
        # one to disk would widen what a stolen state file is worth.
        self._access_tokens: dict[int, tuple[str, datetime]] = {}
        # Set on shutdown so a refresh pass stops between characters rather
        # than finishing eighty requests after the window has gone.
        self._stopping = threading.Event()
```

Append the module constants and the worker:

```python
# Exact user-facing text. These land in a roster row next to the data they
# describe, so they say what the user must DO, not what the transport
# returned -- "401" in a row is not an instruction.
MSG_REAUTH = "EVE rejected the stored authorisation. Re-authenticate this character."
MSG_NO_TOKEN = "No stored authorisation. Re-authenticate this character."
MSG_TOKEN_UNREADABLE = (
    "The stored authorisation could not be decrypted. Re-authenticate this character.")
MSG_SAVE_FAILED = "Fresh data is in memory but was not saved for offline use."
MSG_OWNER_CHANGED = "Character ownership changed; cached skill data was cleared."

# An access token is refreshed when it expires within this many seconds. The
# window has to cover the round trip that is about to use it, or a token that
# was valid when checked is rejected when sent.
TOKEN_EXPIRY_MARGIN_S = 30


def _skills_path(character_id: int) -> str:
    return f"/v4/characters/{character_id}/skills/"


def _queue_path(character_id: int) -> str:
    return f"/v2/characters/{character_id}/skillqueue/"
```

```python
    # ----- refresh --------------------------------------------------------

    def refresh_characters(self) -> None:
        """Start a refresh pass, or note that one is wanted.

        Returns immediately either way: this is called from the bridge
        thread, and a forty-character pass is eighty sequential HTTP
        requests.
        """
        with self._lock:
            if self._refresh_in_flight:
                self._refresh_again = True
                return
            self._refresh_in_flight = True
        self._push_state(force=True)     # The button becomes "Refreshing...".
        self._spawn(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            while True:
                self._refresh_pass()
                with self._lock:
                    if not self._refresh_again:
                        # Cleared inside the same critical section that
                        # reads the flag: clearing it after the check would
                        # drop a request that arrived in the gap, which is
                        # the exact bug the flag exists to prevent.
                        self._refresh_in_flight = False
                        break
                    self._refresh_again = False
        except Exception:
            logger.exception("EVE skills refresh failed")
            with self._lock:
                self._refresh_in_flight = False
                self._refresh_again = False
        finally:
            # Unconditional: the page's "Refreshing..." state is driven by
            # refresh_in_flight, and a pass that died without this push
            # leaves the button stuck forever.
            self._push_state(force=True)

    def _refresh_pass(self) -> None:
        with self._lock:
            targets = [(ch.character_id, ch.character_name)
                       for ch in self._state.characters]
        self._resolve_missing_skill_ids()
        total = len(targets)
        for index, (character_id, name) in enumerate(targets, start=1):
            if self._stopping.is_set():
                return
            error = self._refresh_one(character_id)
            self._push_cb("onSkillsProgress",
                          {"character_id": character_id,
                           "character_name": name,
                           "completed": index, "total": total,
                           "error": error})
            # Not forced: an all-304 pass changes only fetched_utc, and the
            # dedupe is what keeps a no-change refresh from rebuilding the
            # roster once per character.
            self._push_state()

    def _refresh_one(self, character_id: int) -> str:
        """Refresh one character. Returns "" on success, else the message."""
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return ""      # Forgotten between the snapshot and here.
            skills_etag, queue_etag = ch.skills_etag, ch.queue_etag

        skills, error, definitive = self._authorised_get(
            character_id, _skills_path(character_id), skills_etag)
        if skills is None:
            # Short-circuit, ported verbatim: the queue result could not be
            # committed on its own anyway, so spending the second request
            # would only burn error-limit budget to throw the answer away.
            self._commit_failure(character_id, error, definitive)
            return error

        queue, error, definitive = self._authorised_get(
            character_id, _queue_path(character_id), queue_etag)
        if queue is None:
            self._commit_failure(character_id, error, definitive)
            return error

        return self._commit_success(character_id, skills, queue)
```

- [ ] **Step 4: Run test to verify it fails differently**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: the latch test PASSES; the re-entry test FAILS with
`AttributeError: 'SkillsController' object has no attribute '_authorised_get'`

- [ ] **Step 5: Write the token and request path**

```python
    def _access_token(self, character_id: int, *, rejected=None):
        """(access_token, error, definitive) for one character.

        Refreshed when absent, when it expires within TOKEN_EXPIRY_MARGIN_S,
        or when a caller forces it AND the cached token is still the one ESI
        just rejected. That last clause is the stampede fix: N concurrent
        401s from one stale token produce exactly one refresh, because every
        caller after the first finds a cached token that no longer matches
        what it was handed.
        """
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return None, "", False
            blob = ch.refresh_token_blob
            cached = self._access_tokens.get(character_id)

        now = self._now()
        if cached is not None:
            token, expires_at = cached
            fresh = (expires_at - now).total_seconds() > TOKEN_EXPIRY_MARGIN_S
            if fresh and (rejected is None or token != rejected):
                return token, "", False

        if not blob:
            # Definitive: no amount of retrying invents a refresh token.
            return None, MSG_NO_TOKEN, True
        refresh = tokens.unwrap(blob)
        if refresh is None:
            # A DPAPI blob that will not decrypt costs this one character a
            # re-authentication, which is exactly why only the token is
            # wrapped and the roster metadata beside it is not.
            return None, MSG_TOKEN_UNREADABLE, True

        try:
            token_set = self._sso_module().refresh_token(refresh)
        except sso_mod.OAuthError as exc:
            # `definitive` is the OAuth error's own classification --
            # invalid_grant, identity_mismatch, owner_changed. Everything
            # else is transient and must not delete the stored token.
            return None, (MSG_REAUTH if exc.definitive
                          else f"EVE SSO refused the token refresh: {exc}"), \
                exc.definitive
        except Exception as exc:
            # Network, DNS, TLS. Transient by definition: last-good data
            # stays visible and the row is merely stale.
            logger.warning("Token refresh failed", exc_info=True)
            return None, f"Could not reach EVE SSO: {exc}", False

        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return None, "", False
            # EVE rotates the refresh token on every use, so the new one is
            # stored before it is used. Losing this write means the NEXT
            # launch cannot authenticate at all, with nothing on screen to
            # explain why.
            ch.refresh_token_blob = tokens.wrap(token_set.refresh_token)
            self._access_tokens[character_id] = (
                token_set.access_token,
                now + timedelta(seconds=max(0, int(token_set.expires_in))))
            self._save_locked()
        return token_set.access_token, "", False

    def _authorised_get(self, character_id: int, path: str, etag: str):
        """One authorised GET with exactly one 401 retry.

        Returns (response, error, definitive). `response` is None on
        failure; on success it is either a 200 or a 304, and the caller must
        treat both as "this half is current".
        """
        token, error, definitive = self._access_token(character_id)
        if token is None:
            return None, error, definitive

        response = self._client.get(path, token=token, etag=etag or None)
        if response.status == 401:
            # One retry, and only one. A token minted seconds ago and
            # rejected again is not a clock-skew problem, it is a revoked
            # grant, and retrying forever would spend the error-limit
            # budget discovering that repeatedly.
            token, error, definitive = self._access_token(character_id,
                                                          rejected=token)
            if token is None:
                return None, error, definitive
            response = self._client.get(path, token=token, etag=etag or None)
            if response.status == 401:
                return None, MSG_REAUTH, True

        if response.status == 403:
            # Definitive: the grant exists but no longer carries the scope,
            # which only a fresh consent screen can fix.
            return None, MSG_REAUTH, True
        if not (response.ok or response.not_modified):
            # Includes esi.py's synthetic 503 for retry exhaustion, which
            # did not necessarily come from ESI -- transient either way.
            return None, f"ESI request failed ({response.status}): {response.error}", False
        return response, "", False

    def _sso_module(self):
        """The SSO seam, resolved once. Injected whole in tests."""
        if self._sso is None:
            self._sso = sso_mod
        return self._sso
```

Extend the module imports:

```python
from datetime import datetime, timedelta, timezone

from . import application, evaluator, planstore, skillids, tokens
from . import esi as esi_mod
from . import sso as sso_mod
from . import state as state_mod
```

- [ ] **Step 6: Run test to verify it fails differently**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: ... '_commit_failure'`

- [ ] **Step 7: Commit the request path**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): refresh latch, token refresh, and the 401 retry"
```

---

- [ ] **Step 8: Write the failing test — ALL-OR-NOTHING, all five combinations**

```python
def with_snapshot(**kwargs):
    """A character that already has committed data, so a later refresh has
    something to preserve or overwrite."""
    defaults = dict(character_id=95, character_name="Aiga Otsolen",
                    refresh_token_blob="blob", fetched_utc=T0,
                    active_levels={3327: 3}, trained_levels={3327: 3},
                    skills_etag='"old-s"', queue_etag='"old-q"')
    defaults.update(kwargs)
    return state_mod.Character(**defaults)


def run_refresh(tmp_path, esi, character=None, clock=None, **kwargs):
    clock = clock or Clock()
    controller, pushed, alerts = build(
        tmp_path, characters=[character or with_snapshot()], client=esi,
        sso=FakeSso(), spawn=DirectSpawn(), now=clock, **kwargs)
    controller.refresh_characters()
    return controller, pushed, clock


def test_200_and_200_commits_both_halves(tmp_path):
    """The ordinary path. fetched_utc moves, both etags are stored, and any
    previous error is cleared."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi()
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    row = controller.state_payload()["characters"][0]
    ch = controller._state.characters[0]
    assert row["fetched_utc"] == clock.value.isoformat()
    assert ch.active_levels == {3327: 4} and ch.trained_levels == {3327: 5}
    assert (ch.skills_etag, ch.queue_etag) == ('"s1"', '"q1"')
    assert row["error"] == "" and row["stale"] is False


def test_304_and_304_keeps_the_data_and_still_advances_fetched_utc(tmp_path):
    """fetched_utc means "both halves were confirmed current at this time",
    not "both halves were re-downloaded". Nothing being modified is a
    successful confirmation, not a skipped one -- and if it did NOT advance,
    a character whose skills never change would drift toward looking stale
    forever."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(skills=[esi_response(304)], queue=[esi_response(304)])
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.fetched_utc == clock.value
    assert ch.active_levels == {3327: 3}          # Untouched.
    assert ch.skills_etag == '"old-s"'            # A 304 carries no new etag.


def test_200_and_304_commits_the_fresh_half_and_keeps_the_stored_one(tmp_path):
    """Per-endpoint freshness is the hazard conditional requests introduce.
    The rule that makes it safe: a 304 means the stored half is already
    current, so the pair is still one coherent snapshot."""
    esi = FakeEsi(queue=[esi_response(304)])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 4}          # Fresh skills committed.
    assert ch.queue_etag == '"old-q"'             # Stored queue kept.
    assert ch.error == ""


def test_a_failing_queue_call_commits_nothing_at_all(tmp_path):
    """THE critical rule. Current skills evaluated against a stale queue
    produce a Training verdict with an ETA drawn from a queue the character
    has since changed -- and the row shows no error, because the skills call
    succeeded. Quiet and wrong is worse than loud and stale."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(queue=[esi_response(500, error="upstream")])
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 3}, "the fresh skills must NOT be kept"
    assert ch.skills_etag == '"old-s"', "nor the etag that would hide it next time"
    assert ch.fetched_utc == T0, "fetched_utc must not move"
    assert ch.error and ch.needs_reauth is False
    assert controller.state_payload()["characters"][0]["stale"] is True


def test_a_failing_skills_call_skips_the_queue_call_entirely(tmp_path):
    """Ported short-circuit. The queue result could not be committed on its
    own, so spending the request only burns error-limit budget."""
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    assert [c[0] for c in esi.calls] == ["/v4/characters/95/skills/"]
    assert controller._state.characters[0].fetched_utc == T0


def test_cached_skill_data_survives_a_failure(tmp_path):
    """A transient ESI blip must not look like data loss. This is what makes
    `stale` mean "you are looking at last-good data" rather than "empty"."""
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    assert controller._state.characters[0].active_levels == {3327: 3}
```

- [ ] **Step 9: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute '_commit_success'`

- [ ] **Step 10: Write the commit**

```python
def _clamp_level(value) -> int:
    """0..5. ESI is trusted but not blindly: a level outside the range would
    make an out-of-range requirement score Active."""
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, level))


def _parse_skills(data):
    """(active_levels, trained_levels) from /characters/{id}/skills/.

    Malformed entries are dropped individually rather than failing the
    document, matching state.py's tolerant normalisation: one bad entry
    should cost one skill, not the refresh.
    """
    active: dict[int, int] = {}
    trained: dict[int, int] = {}
    rows = data.get("skills") if isinstance(data, dict) else None
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        try:
            skill_id = int(row["skill_id"])
        except (KeyError, TypeError, ValueError):
            continue
        active[skill_id] = _clamp_level(row.get("active_skill_level"))
        trained[skill_id] = _clamp_level(row.get("trained_skill_level"))
    return active, trained


def _parse_date(value):
    """An ESI timestamp, or None.

    None is a real, expected value: a paused queue entry has no dates, and
    that is exactly what drives "Training -- timing unknown".
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_queue(data):
    """A tuple of evaluator.QueueEntry, in the order ESI returned them."""
    entries = []
    for row in data if isinstance(data, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            skill_id = int(row["skill_id"])
            finished_level = int(row["finished_level"])
        except (KeyError, TypeError, ValueError):
            continue
        entries.append(evaluator.QueueEntry(
            skill_id=skill_id,
            finished_level=max(1, min(5, finished_level)),
            start_date=_parse_date(row.get("start_date")),
            finish_date=_parse_date(row.get("finish_date")),
            queue_position=_clamp_position(row.get("queue_position"))))
    return tuple(entries)


def _clamp_position(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
```

```python
    def _commit_success(self, character_id: int, skills, queue) -> str:
        """Commit both halves, or neither. Returns "" or a degraded message.

        Both responses have already resolved 200 or 304 by the time this is
        called -- that check is the caller's, and it is what makes this
        method a commit rather than a decision. Parsing happens OUTSIDE the
        lock; only the merge is inside it, one short critical section per
        character rather than one held across eighty HTTP requests.
        """
        parsed_skills = _parse_skills(skills.data) if skills.ok else None
        parsed_queue = _parse_queue(queue.data) if queue.ok else None

        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                # Forgotten while its refresh was in flight. The commit
                # re-checks presence and drops the result: merging by
                # character id rather than replacing the roster is what
                # makes that safe, and a forgotten character must STAY
                # forgotten or forget silently does nothing.
                return ""
            if parsed_skills is not None:
                ch.active_levels, ch.trained_levels = parsed_skills
                # A 200 with no ETag header leaves the stored one alone
                # rather than clearing it -- an empty etag just means the
                # next request is unconditional, which is merely wasteful.
                ch.skills_etag = skills.etag or ch.skills_etag
            if parsed_queue is not None:
                ch.queue = parsed_queue
                ch.queue_etag = queue.etag or ch.queue_etag
            ch.fetched_utc = self._now()
            ch.error = ""
            ch.needs_reauth = False
            if self._save_locked():
                return ""
            # The data is live in memory and correct; only the offline copy
            # is missing. Degraded, not failed, and the row says which.
            ch.error = MSG_SAVE_FAILED
            return MSG_SAVE_FAILED

    def _commit_failure(self, character_id: int, message: str,
                        definitive: bool) -> None:
        """Record the failure. The snapshot is deliberately left untouched.

        `fetched_utc` does not move here, which is the whole mechanism
        behind `stale`: last-good data plus an error. Discarding the
        snapshot would turn a transient ESI blip into apparent data loss.
        """
        with self._lock:
            ch = self._state.find(character_id)
            if ch is None:
                return
            ch.error = message
            if definitive:
                ch.needs_reauth = True
                # The stored grant cannot work again, so it is deleted
                # rather than retried on every future refresh -- and the row
                # shows a re-authenticate banner instead of an error that
                # never clears.
                ch.refresh_token_blob = ""
                self._access_tokens.pop(character_id, None)
            self._save_locked()
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 12: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): all-or-nothing snapshot commit across 200/304/error"
```

---

- [ ] **Step 13: Write the failing test — failure classification and the stampede fix**

```python
@pytest.mark.parametrize("status", [401, 403])
def test_a_definitive_failure_needs_reauth_and_deletes_the_token(tmp_path, status):
    """403, and 401 that survives one retry, are definitive: the grant is
    gone or no longer carries the scope, and only a fresh consent screen
    fixes either. Keeping the token would retry a dead grant on every
    refresh forever."""
    esi = FakeEsi(skills=[esi_response(status, error="denied")])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.needs_reauth is True
    assert ch.refresh_token_blob == ""
    assert ch.error == (
        "EVE rejected the stored authorisation. Re-authenticate this character.")
    assert ch.active_levels == {3327: 3}, "last-good data still stays visible"


def test_a_transient_failure_does_not_ask_for_re_authentication(tmp_path):
    """A 5xx is ESI having a bad minute. Showing a re-authenticate banner
    for it would send the user through a consent screen that fixes nothing
    and costs them their cached snapshot."""
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.needs_reauth is False
    assert ch.refresh_token_blob == "blob"


def test_a_definitive_oauth_error_is_definitive_here_too(tmp_path):
    """invalid_grant means the refresh token is revoked or already used.
    OAuthError.definitive is the classification; this asserts the controller
    honours it rather than inventing a second one."""
    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], client=esi,
        sso=FakeSso(raises=sso_mod.OAuthError(400, "invalid_grant", "revoked")),
        spawn=DirectSpawn())
    controller.refresh_characters()

    ch = controller._state.characters[0]
    assert ch.needs_reauth is True and ch.refresh_token_blob == ""
    assert esi.calls == [], "no ESI call is worth making without a token"


def test_a_transient_oauth_error_keeps_the_token(tmp_path):
    """An SSO 503 is not a revoked grant. Deleting the token here would cost
    the user a re-authentication for CCP's downtime."""
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], client=FakeEsi(),
        sso=FakeSso(raises=sso_mod.OAuthError(503, "server_error", "down")),
        spawn=DirectSpawn())
    controller.refresh_characters()

    ch = controller._state.characters[0]
    assert ch.needs_reauth is False and ch.refresh_token_blob == "blob"


def test_a_cached_token_is_reused_across_both_calls(tmp_path):
    """Two ESI calls per character must not mean two token refreshes. At
    forty characters that is forty wasted SSO round trips per click."""
    sso = FakeSso()
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    assert len(sso.refreshes) == 1


def test_a_401_forces_exactly_one_refresh_and_one_retry(tmp_path):
    """The stampede fix. A forced refresh only actually refreshes when the
    cached token is still the one ESI rejected -- so callers queued behind
    the first find a token that no longer matches and reuse it, and one
    stale token produces one refresh rather than N."""
    sso = FakeSso()
    esi = FakeEsi(skills=[esi_response(401, error="expired"),
                          esi_response(200, SKILLS_BODY, etag='"s1"')])
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=esi, sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    skills_calls = [c for c in esi.calls if c[0].endswith("/skills/")]
    assert len(skills_calls) == 2                     # One 401, one retry.
    assert skills_calls[0][1] != skills_calls[1][1]   # A different token.
    # Two refreshes total: the initial mint, and the one the 401 forced.
    # The queue call that follows reuses the second and adds none.
    assert len(sso.refreshes) == 2


def test_an_expiring_token_is_refreshed_before_it_is_used(tmp_path):
    """A token that is valid when checked and expired when it lands is a
    401 the user pays a retry for. The margin covers the round trip."""
    sso = FakeSso(expires_in=10)      # Inside TOKEN_EXPIRY_MARGIN_S.
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    assert len(sso.refreshes) == 2, "the second call must not reuse it"
```

- [ ] **Step 14: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: PASS against Steps 5 and 10. A `definitive` flag wired the wrong way round
fails `test_a_transient_failure_does_not_ask_for_re_authentication` with
`assert True is False`.

- [ ] **Step 15: Commit**

```bash
git add tests/test_eveskills_controller.py
git commit -m "test(eveskills): failure classification and the token stampede fix"
```

---

- [ ] **Step 16: Write the failing test — forgotten mid-refresh, progress, and id resolution**

```python
def test_a_character_forgotten_mid_refresh_stays_forgotten(tmp_path):
    """Auth, refresh, forget and plan selection can all be in flight at
    once. A forget completing during a refresh would be silently undone by
    the refresh's save -- the character reappears, with data, and the only
    way to remove it is to click forget again and hope."""
    esi = FakeEsi()
    controller = None

    def forget_during_the_fetch(path):
        controller.forget(95)

    esi.on_get = forget_during_the_fetch
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=esi, sso=FakeSso(), spawn=DirectSpawn())

    controller.refresh_characters()

    assert controller.state_payload()["characters"] == []


def test_progress_is_pushed_once_per_character(tmp_path):
    """A forty-character pass is eighty sequential requests. Without a
    per-character push the window looks hung for the duration."""
    characters = [with_snapshot(character_id=1, character_name="A"),
                  with_snapshot(character_id=2, character_name="B")]
    controller, pushed, _ = build(tmp_path, characters=characters,
                                  client=FakeEsi(), sso=FakeSso(),
                                  spawn=DirectSpawn())

    controller.refresh_characters()

    progress = [p for handler, p in pushed if handler == "onSkillsProgress"]
    assert [(p["completed"], p["total"]) for p in progress] == [(1, 2), (2, 2)]
    assert [p["character_name"] for p in progress] == ["A", "B"]
    assert all(p["error"] == "" for p in progress)


def test_a_refresh_resolves_plan_names_that_are_not_in_the_cache(tmp_path):
    """One unresolved name poisons a whole plan's readiness to Unknown for
    every character, so resolution has to happen somewhere -- and refresh is
    the only place with both a worker thread and an ESI client."""
    resolved = []

    def fake_resolve(cache, names, client, **kwargs):
        resolved.append(sorted(names))
        cache.merge({name: 3327 for name in names})
        return {}

    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=FakeSso(),
                             spawn=DirectSpawn(),
                             plans={"Interceptor": "Navigation V\n"})
    controller._resolve = fake_resolve

    controller.refresh_characters()

    assert resolved == [["Navigation"]]
    assert controller._cache.get("navigation") == 3327
```

- [ ] **Step 17: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute '_resolve_missing_skill_ids'`
(and `forget` arrives in Task 14; until then the first test fails on `forget` instead —
run it after Task 14's Step 9 if the order is followed strictly).

- [ ] **Step 18: Write minimal implementation**

Add to `__init__`:

```python
        # The resolver is an attribute rather than a direct call so a test
        # can replace it without a network: skillids.resolve fans out to
        # three ESI endpoints and its own tests already cover that.
        self._resolve = skillids.resolve
```

Append:

```python
    def _resolve_missing_skill_ids(self) -> None:
        """Resolve plan skill names that are not yet in the id cache.

        Runs once per refresh pass, before any character is fetched: one
        unresolved name scores `Unknown` for EVERY character, so resolving
        after the fetches would leave the whole roster wrong until the next
        click.

        Failures are recorded as cache misses and nothing more. A name that
        does not resolve is a plan-authoring problem -- a typo, or a
        non-skill type -- and it already shows as `Unknown` on the row.
        """
        with self._lock:
            names = sorted({req.skill_name for plan in self._plans if plan.ok
                            for req in plan.requirements})
            missing = self._cache.unresolved(names)
        if not missing:
            return
        try:
            failures = self._resolve(self._cache, missing, self._client)
        except Exception:
            logger.exception("Skill id resolution failed")
            return
        if failures:
            logger.info("Unresolved skill names: %s", sorted(failures))
        with self._lock:
            try:
                skillids.save(self._cache, self._cache_path)
            except OSError:
                # The cache rebuilds completely by re-resolving names, so a
                # failed write costs requests on the next refresh and
                # nothing else.
                logger.warning("Could not save the skill id cache", exc_info=True)
```

Also replace the two placeholder flags in `_state_payload_locked`:

```python
            "auth_in_progress": self._auth_in_progress,
            "refresh_in_flight": self._refresh_in_flight,
```

and add `self._auth_in_progress = False` to `__init__` (Task 14 drives it).

- [ ] **Step 19: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 20: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): per-character progress and pre-pass skill id resolution"
```

---

### Task 14: `controller.py` — auth, forget, character detail

**Files:**
- Modify: `obs_youtube_uploader/eveskills/controller.py` (append)
- Test: `tests/test_eveskills_controller.py` (append)

**Interfaces:**
- Consumes:
  - `sso.generate_pkce(*, randbytes=os.urandom) -> Pkce`, `sso.authorize_url(pkce) -> str`, `sso.exchange_code(code, verifier, *, transport=...) -> TokenSet` (Task 11)
  - `loopback.LoopbackListener(*, host, port, path)` as a context manager, `.wait(expected_state, *, timeout_s=AUTH_TIMEOUT_S) -> Callback`, `.cancel()`; `loopback.Callback.code/.error`; `loopback.CallbackTimeout`, `loopback.CallbackCancelled` (Task 10)
  - `jwt.validate(token, *, client_id, required_scopes, key_source, now=None, skew_s=...) -> EveIdentity`; `jwt.SigningKeySource()`; `EveIdentity.character_id/.name/.owner_hash/.scopes`; `jwt.JwtError` (Task 9)
- Produces:
  ```python
  class SkillsController:
      def authenticate(self) -> None
      def cancel_auth(self) -> None
      def forget(self, character_id) -> bool
      def character_detail(self, character_id, plan_name) -> dict
      def shutdown(self) -> None      # never raises
  ```

---

- [ ] **Step 1: Write the failing test — forget is one atomic write**

```python
def test_forget_removes_the_character_and_its_token_in_one_write(tmp_path):
    """They live in one document, which is the entire reason this decision
    exists: there is no window in which the character exists without its
    token or the token without its character, and no rollback to get wrong.

    TriffView splits them across Credential Manager and state.json and
    cannot update the two atomically -- its own error strings say so
    ("Forget was rolled back because state could not be saved"), and
    RecoverOwnCredentials() exists purely to resurrect the orphans."""
    controller, _, _ = build(tmp_path, characters=[with_snapshot()])

    assert controller.forget(95) is True

    reopened, _, _ = build(tmp_path)
    assert reopened._state.characters == []
    document = json.loads((tmp_path / "eve_skills.json").read_text("utf-8"))
    assert "blob" not in json.dumps(document), "the token went with the row"


def test_forgetting_a_character_that_is_not_there_is_an_idempotent_success(tmp_path):
    """The page can hold a roster across a refresh that already removed the
    row, and a two-step confirm makes a double click easy. False would make
    the page show a failure for a state the user already has."""
    controller, _, _ = build(tmp_path)

    assert controller.forget(999) is True


def test_forget_rejects_a_payload_that_is_not_an_id(tmp_path):
    """The argument crosses the bridge from JavaScript, where a missing
    dataset attribute arrives as undefined -> None."""
    controller, _, _ = build(tmp_path)

    assert controller.forget(None) is False
    assert controller.forget("not-a-number") is False


def test_forget_always_pushes(tmp_path):
    """A mutation that changed the roster must re-sync the page even when
    the payload is deduped against an identical earlier one."""
    controller, pushed, _ = build(tmp_path, characters=[with_snapshot()])

    controller.forget(95)

    assert [h for h, _ in pushed] == ["onSkills"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute 'forget'`

- [ ] **Step 3: Write minimal implementation**

```python
    # ----- forget ---------------------------------------------------------

    def forget(self, character_id) -> bool:
        """Remove a character and its stored token. One write, always.

        Because the roster row and the DPAPI-wrapped refresh token live in
        the same document, removing the row removes the token with it. That
        makes the entire orphan class impossible rather than recoverable --
        no rollback transaction, no reconciliation sweep, and no window in
        which a token outlives the character it belongs to.

        Idempotent: removing a character that is not there is a success.
        The page can hold a roster across a refresh that already dropped
        the row, and a two-step confirm makes a double click easy.
        """
        try:
            wanted = int(character_id)
        except (TypeError, ValueError):
            # Arrives from JavaScript, where a missing dataset attribute is
            # undefined -> None. Refused rather than coerced.
            logger.warning("Refusing a non-numeric character id: %r", character_id)
            return False
        with self._lock:
            self._state.remove(wanted)
            self._access_tokens.pop(wanted, None)
            self._save_locked()
        self._push_state(force=True)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): atomic forget"
```

---

- [ ] **Step 6: Write the failing test — interactive sign-in, with no network and no browser**

```python
from obs_youtube_uploader.eveskills import loopback as loopback_mod

IDENTITY = SimpleNamespace(character_id=95, name="Aiga Otsolen",
                           owner_hash="hash-a",
                           scopes=frozenset({"esi-skills.read_skills.v1"}))


class FakeListener:
    """The loopback listener, without a socket.

    Records the order of bind and wait so the browser-launch race can be
    asserted: `entered` flips in __enter__, and the launcher checks it.
    """

    def __init__(self, callback=None, raises=None):
        self.callback = callback or loopback_mod.Callback(code="the-code", error="")
        self.raises = raises
        self.entered = False
        self.cancelled = 0
        self.waited_state = None

    def __call__(self, *, host, port, path):
        self.host, self.port, self.path = host, port, path
        return self

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        return False

    def wait(self, expected_state, timeout_s=None):
        self.waited_state = expected_state
        if self.raises is not None:
            raise self.raises
        return self.callback

    def cancel(self):
        self.cancelled += 1


class FakeAuthSso(FakeSso):
    """Adds the three functions the interactive flow calls."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.exchanged = []

    def generate_pkce(self, **kwargs):
        return sso_mod.Pkce(state="the-state", verifier="v", challenge="c")

    def authorize_url(self, pkce):
        return f"https://login.eveonline.com/v2/oauth/authorize?state={pkce.state}"

    def exchange_code(self, code, verifier, **kwargs):
        self.exchanged.append((code, verifier))
        return sso_mod.TokenSet(access_token="jwt", refresh_token="refresh-1",
                                expires_in=1200)


def build_auth(tmp_path, *, listener=None, identity=IDENTITY, **kwargs):
    listener = listener or FakeListener()
    launched = []
    controller, pushed, alerts = build(
        tmp_path,
        sso=FakeAuthSso(),
        spawn=DirectSpawn(),
        listener_factory=listener,
        launch_browser=lambda url: launched.append((url, listener.entered)),
        validate_token=lambda token, **kwargs: identity,
        **kwargs)
    return controller, listener, launched, pushed, alerts


def test_a_successful_sign_in_adds_the_character(tmp_path):
    controller, listener, _, _, _ = build_auth(tmp_path)

    controller.authenticate()

    ch = controller._state.characters[0]
    assert (ch.character_id, ch.character_name) == (95, "Aiga Otsolen")
    assert ch.refresh_token_blob == "refresh-1"
    assert ch.needs_reauth is False
    assert listener.waited_state == "the-state"


def test_the_listener_is_bound_before_the_browser_launches(tmp_path):
    """A race, not a style point. The browser can complete the redirect
    before a listener bound afterwards exists, and the user then stares at a
    connection-refused page while Wingman waits five minutes for a callback
    that already happened."""
    controller, _, launched, _, _ = build_auth(tmp_path)

    controller.authenticate()

    assert launched and launched[0][1] is True, "bound before the launch"


def test_a_successful_sign_in_kicks_off_a_refresh(tmp_path):
    """A newly authorised character is Unscored until its first refresh
    lands. Making the user click Refresh to see anything at all would make
    a successful sign-in look like it did nothing."""
    controller, _, _, _, _ = build_auth(tmp_path, client=FakeEsi())

    controller.authenticate()

    assert controller._state.characters[0].fetched_utc is not None


def test_only_one_interactive_sign_in_at_a_time(tmp_path):
    """Two authorisations would fight over the same fixed loopback port, and
    the redirect URI is registered with CCP so there is no second port to
    fall back to."""
    class Blocking(FakeListener):
        def wait(self, expected_state, timeout_s=None):
            controller.authenticate()      # Re-entered from inside the flow.
            return self.callback

    controller, listener, _, _, alerts = build_auth(tmp_path,
                                                    listener=Blocking())
    controller.authenticate()

    assert len(controller._sso.exchanged) == 1
    assert alerts and "progress" in alerts[0][1].lower()


def test_cancel_auth_cancels_the_listener(tmp_path):
    """The add button becomes Cancel sign-in during the flow. Without this
    the only way out is to wait five minutes."""
    class Cancelling(FakeListener):
        def wait(self, expected_state, timeout_s=None):
            controller.cancel_auth()
            raise loopback_mod.CallbackCancelled()

    controller, listener, _, _, alerts = build_auth(tmp_path,
                                                    listener=Cancelling())
    controller.authenticate()

    assert listener.cancelled == 1
    assert controller._state.characters == []
    assert alerts == [], "a cancellation the user asked for is not an error"


def test_a_callback_carrying_an_error_adds_nothing(tmp_path):
    """The user can click Deny on the consent screen."""
    listener = FakeListener(
        callback=loopback_mod.Callback(code="", error="access_denied"))
    controller, _, _, _, alerts = build_auth(tmp_path, listener=listener)

    controller.authenticate()

    assert controller._state.characters == []
    assert alerts and alerts[0][0] == "warning"


def test_re_authenticating_the_same_character_keeps_its_data(tmp_path):
    """Re-auth is the repair path for needs_reauth. Clearing the snapshot
    would make repairing a character cost its cached data, which is the
    opposite of what the banner promises."""
    existing = with_snapshot(owner_hash="hash-a", needs_reauth=True,
                             error="EVE rejected the stored authorisation.")
    controller, _, _, _, _ = build_auth(tmp_path, characters=[existing])

    controller.authenticate()

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 3} and ch.fetched_utc == T0
    assert ch.needs_reauth is False and ch.error == ""


def test_an_ownership_change_clears_the_cached_snapshot(tmp_path):
    """The character id was transferred to a different account. Its skills,
    queue and etags now describe someone else's training, and scoring a plan
    against them would be confidently wrong."""
    existing = with_snapshot(owner_hash="hash-OLD")
    controller, _, _, _, _ = build_auth(tmp_path, characters=[existing])

    controller.authenticate()

    ch = controller._state.characters[0]
    assert ch.active_levels == {} and ch.trained_levels == {}
    assert ch.queue == () and ch.fetched_utc is None
    assert ch.skills_etag == "" and ch.queue_etag == ""
    assert ch.error == "Character ownership changed; cached skill data was cleared."
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute 'authenticate'`

- [ ] **Step 8: Write minimal implementation**

Add to `__init__`:

```python
        # A separate, non-re-entrant latch, acquired non-blocking. Not the
        # state lock: this one is held for the whole five-minute browser
        # round trip, and holding the state lock for that would block every
        # read the page makes while a consent screen is open.
        self._auth_latch = threading.Lock()
        self._listener = None
```

Extend the imports:

```python
from . import jwt as jwt_mod
from . import loopback as loopback_mod
```

Append:

```python
    # ----- interactive sign-in --------------------------------------------

    def authenticate(self) -> None:
        """Start an interactive EVE sign-in on a worker. Returns at once.

        This is called from the bridge thread, and the flow launches a
        browser and then blocks on the loopback accept loop for up to five
        minutes. Running that here would freeze the window for the
        duration.
        """
        if not application.is_configured():
            self._alert("warning", "EVE sign-in is not configured",
                        "This build has no EVE application client id compiled "
                        "in, so it cannot ask CCP for authorisation.")
            return
        if not self._auth_latch.acquire(blocking=False):
            # Non-blocking on purpose: two authorisations would fight over
            # the same fixed loopback port, and the redirect URI is
            # registered with CCP so there is no second port to use.
            self._alert("warning", "Sign-in already in progress",
                        "Finish or cancel the EVE sign-in already running.")
            return
        with self._lock:
            self._auth_in_progress = True
        self._push_state(force=True)
        self._spawn(target=self._auth_worker, daemon=True).start()

    def _auth_worker(self) -> None:
        added = False
        try:
            added = self._run_auth()
        except loopback_mod.CallbackCancelled:
            # The user pressed Cancel sign-in. Not an error, and alerting
            # on it would make the cancel button feel like a failure.
            logger.info("EVE sign-in cancelled")
        except loopback_mod.CallbackTimeout:
            self._alert("warning", "Sign-in timed out",
                        "No response from EVE SSO within five minutes.")
        except sso_mod.OAuthError as exc:
            self._alert("warning", "EVE refused the sign-in", str(exc))
        except jwt_mod.JwtError as exc:
            # A token that does not validate is never accepted as a
            # fallback: the whole point of validation is that a failure
            # rejects rather than degrades.
            self._alert("warning", "EVE returned a token we cannot trust",
                        str(exc))
        except Exception as exc:
            logger.exception("EVE sign-in failed")
            self._alert("warning", "Sign-in failed", str(exc))
        finally:
            with self._lock:
                self._auth_in_progress = False
                self._listener = None
            self._auth_latch.release()
            self._push_state(force=True)
        if added:
            # A newly authorised character is Unscored until its first
            # refresh lands, so a successful sign-in that stopped here would
            # look like it did nothing.
            self.refresh_characters()

    def _run_auth(self) -> bool:
        sso = self._sso_module()
        pkce = sso.generate_pkce()
        factory = (self._listener_factory if self._listener_factory is not None
                   else loopback_mod.LoopbackListener)
        with factory(host=application.REDIRECT_HOST,
                     port=application.REDIRECT_PORT,
                     path=application.REDIRECT_PATH) as listener:
            with self._lock:
                self._listener = listener
            # The browser launches only AFTER the bind. The reverse order
            # is a race: the redirect can arrive before anything is
            # listening, and the user then sees a connection-refused page
            # while Wingman waits five minutes for a callback that already
            # happened.
            self._launch_browser(sso.authorize_url(pkce))
            callback = listener.wait(pkce.state)

        if callback.error:
            self._alert("warning", "EVE refused the sign-in", callback.error)
            return False

        token_set = sso.exchange_code(callback.code, pkce.verifier)
        validate = (self._validate_token if self._validate_token is not None
                    else jwt_mod.validate)
        identity = validate(token_set.access_token,
                            client_id=application.CLIENT_ID,
                            required_scopes=application.SCOPES,
                            key_source=self._keys())
        return self._upsert_identity(identity, token_set)

    def _keys(self):
        """The JWKS source, built on first use.

        Lazy because constructing it is cheap but fetching JWKS is not, and
        a user who never signs in must never pay for one.
        """
        with self._lock:
            if self._key_source is None:
                self._key_source = jwt_mod.SigningKeySource()
            return self._key_source

    def _upsert_identity(self, identity, token_set) -> bool:
        blob = tokens.wrap(token_set.refresh_token)
        now = self._now()
        full = False
        with self._lock:
            existing = self._state.find(identity.character_id)
            if existing is None and len(self._state.characters) >= state_mod.MAX_CHARACTERS:
                full = True
            else:
                ch = existing or state_mod.Character(
                    character_id=identity.character_id)
                # Compared only when a hash was previously stored: an
                # absent claim on an older row is missing information, not
                # evidence of a transfer, and treating it as one would wipe
                # a good snapshot on the first re-auth after an upgrade.
                if existing is not None and existing.owner_hash and \
                        existing.owner_hash != identity.owner_hash:
                    # A different account owns this character now. Its
                    # skills, queue and etags describe someone else's
                    # training, and scoring a plan against them would be
                    # confidently wrong.
                    ch.active_levels = {}
                    ch.trained_levels = {}
                    ch.queue = ()
                    ch.fetched_utc = None
                    ch.skills_etag = ""
                    ch.queue_etag = ""
                    ch.error = MSG_OWNER_CHANGED
                else:
                    ch.error = ""
                ch.character_name = identity.name
                ch.owner_hash = identity.owner_hash
                ch.scopes = tuple(sorted(identity.scopes))
                ch.authenticated_utc = now
                ch.needs_reauth = False
                ch.refresh_token_blob = blob
                self._state.upsert(ch)
                self._access_tokens[ch.character_id] = (
                    token_set.access_token,
                    now + timedelta(seconds=max(0, int(token_set.expires_in))))
                self._save_locked()
        if full:
            # Alerted outside the lock: _alert reaches pywebview, and a slow
            # page must not hold the state lock.
            self._alert("warning", "Too many characters",
                        f"Wingman stores at most {state_mod.MAX_CHARACTERS} "
                        "characters. Forget one before adding another.")
            return False
        return True

    def cancel_auth(self) -> None:
        """Unblock the listener. Safe when no sign-in is running."""
        with self._lock:
            listener = self._listener
        if listener is None:
            return
        try:
            listener.cancel()
        except Exception:
            logger.exception("Could not cancel the EVE sign-in listener")

    def shutdown(self) -> None:
        """Stop cleanly on the way out. NEVER raises.

        Runs on every exit path from main(), after the window has gone, so
        like shutdown_engine() it must not be the thing that raises. The
        listener is what matters: a socket bound to the fixed redirect port
        with nothing left to accept on it would make the NEXT launch's
        sign-in fail to bind, with no fallback port to move to.
        """
        self._stopping.set()
        try:
            self.cancel_auth()
        except Exception:
            logger.exception("EVE skills shutdown was not clean")
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 10: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): interactive PKCE sign-in, cancellation, and shutdown"
```

---

- [ ] **Step 11: Write the failing test — character_detail**

```python
def test_character_detail_includes_active_requirements(tmp_path):
    """The page filters Active rows out for display; Python does not filter
    them out of the payload. Filtering here would make the payload lie about
    what the plan requires -- and the expanded row's counts, the "6 of 8"
    summary, and any future "show everything" toggle all read this list."""
    character = with_snapshot(active_levels={3327: 5, 3449: 1},
                              trained_levels={3327: 5, 3449: 1})
    controller, _, _ = build(tmp_path, characters=[character],
                             plans={"Interceptor": "Navigation V\nEvasive Maneuvering V\n"})
    controller._cache.merge({"Navigation": 3327, "Evasive Maneuvering": 3449})

    detail = controller.character_detail(95, "Interceptor")

    states = {r["skill_name"]: r["state"] for r in detail["requirements"]}
    assert states == {"Navigation": "Active", "Evasive Maneuvering": "Missing"}
    assert detail["ok"] is True and detail["readiness"] == "Missing"


def test_character_detail_matches_the_plan_name_case_insensitively(tmp_path):
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             plans={"Interceptor": "Navigation V\n"})

    assert controller.character_detail(95, "interceptor")["ok"] is True


def test_character_detail_for_a_forgotten_character_says_so(tmp_path):
    """The page can ask for a row a refresh has since removed. A structured
    ok/message beats an exception that surfaces as a rejected promise in a
    page nobody is debugging."""
    controller, _, _ = build(tmp_path)

    detail = controller.character_detail(95, "Interceptor")

    assert detail["ok"] is False and detail["message"]
    assert detail["requirements"] == []


def test_character_detail_for_a_rejected_plan_says_so(tmp_path):
    """Any diagnostic rejects the whole file, so its requirement list is
    empty -- and an empty list would otherwise render as "nothing left to
    train", which is the exact opposite of the truth."""
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             plans={"Broken": "Navigation +5\n"})

    detail = controller.character_detail(95, "Broken")

    assert detail["ok"] is False and "errors" in detail["message"]


def test_character_detail_reports_levels_as_integers(tmp_path):
    """active_level and trained_level are `int | None` inside the package
    and plain ints across the bridge: the page arithmetic-compares them, and
    `null > 3` is false in JavaScript rather than an error."""
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             plans={"Interceptor": "Nothing Known V\n"})

    row = controller.character_detail(95, "Interceptor")["requirements"][0]

    assert row["state"] == "Unknown"
    assert (row["active_level"], row["trained_level"]) == (0, 0)
    assert row["queued_finish_utc"] == ""
```

- [ ] **Step 12: Run test to verify it fails**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: FAIL with `AttributeError: 'SkillsController' object has no attribute 'character_detail'`

- [ ] **Step 13: Write minimal implementation**

```python
def _detail_error(character_id: int, plan_name: str, message: str) -> dict:
    """The failure shape, identical in every key to the success shape.

    Same keys either way so the page has one renderer: a payload that drops
    fields on failure means every access in skills.js needs a guard, and the
    one that gets forgotten throws inside a click handler.
    """
    return {"ok": False, "message": message,
            "character_id": character_id, "plan_name": plan_name,
            "readiness": evaluator.READINESS_UNKNOWN,
            "estimated_finish_utc": "", "queue_timing_unknown": False,
            "requirements": []}


    # ----- detail ---------------------------------------------------------

    def character_detail(self, character_id, plan_name) -> dict:
        """Re-evaluate one character against one plan, in full.

        Computed on demand rather than carried in the roster payload:
        forty characters times fifty requirements is two thousand rows the
        page would receive on every push to render at most one of.
        """
        name = str(plan_name or "")
        try:
            wanted = int(character_id)
        except (TypeError, ValueError):
            return _detail_error(0, name, "Unknown character.")

        with self._lock:
            ch = self._state.find(wanted)
            if ch is None:
                return _detail_error(
                    wanted, name, "That character is no longer in the roster.")
            plan = self._find_plan_locked(name)
            if plan is None:
                return _detail_error(
                    wanted, name, "That plan is no longer available. Reload plans.")
            if not plan.ok:
                return _detail_error(
                    wanted, plan.name,
                    "That plan file has errors and was not loaded.")
            analysis = evaluator.evaluate(
                plan.requirements, self._cache.type_ids(), ch.active_levels,
                ch.trained_levels, ch.queue, ch.has_snapshot)

        return {
            "ok": True, "message": "",
            "character_id": wanted, "plan_name": plan.name,
            "readiness": analysis.readiness,
            "estimated_finish_utc": _iso(analysis.estimated_finish_utc),
            "queue_timing_unknown": bool(analysis.queue_timing_unknown),
            # Active requirements are INCLUDED. The page filters them out of
            # the expanded row, which is a display decision; filtering here
            # would make the payload lie about what the plan requires.
            "requirements": [
                {"skill_name": req.skill_name,
                 "required_level": req.required_level,
                 # Plain ints across the bridge: the page compares these
                 # arithmetically, and `null > 3` is quietly false in
                 # JavaScript rather than an error.
                 "active_level": int(req.active_level or 0),
                 "trained_level": int(req.trained_level or 0),
                 "state": req.state,
                 "queued_finish_utc": _iso(req.queued_finish_utc),
                 "queue_timing_unknown": bool(req.queue_timing_unknown)}
                for req in analysis.requirements],
        }
```

- [ ] **Step 14: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`

- [ ] **Step 15: Commit**

```bash
git add obs_youtube_uploader/eveskills/controller.py tests/test_eveskills_controller.py
git commit -m "feat(eveskills): per-character requirement detail"
```

---

- [ ] **Step 16: Write the failing test — shutdown never raises**

```python
def test_shutdown_is_safe_with_no_sign_in_running(tmp_path):
    """Runs on every exit path from main(), after the window has gone. Like
    shutdown_engine() it must never be the thing that raises."""
    controller, _, _ = build(tmp_path)

    controller.shutdown()


def test_shutdown_swallows_a_failing_listener(tmp_path):
    """A socket teardown that throws during exit would leave main()
    returning non-zero on an otherwise clean quit."""
    class Exploding:
        def cancel(self):
            raise OSError("socket already closed")

    controller, _, _ = build(tmp_path)
    controller._listener = Exploding()

    controller.shutdown()


def test_shutdown_stops_a_refresh_pass_between_characters(tmp_path):
    """A forty-character pass is eighty sequential requests. Continuing them
    after the window is gone keeps the process alive in Task Manager with
    nothing on screen -- the same failure shutdown_previews() exists to
    prevent for HWNDs."""
    characters = [with_snapshot(character_id=1), with_snapshot(character_id=2)]
    controller, _, _ = build(tmp_path, characters=characters,
                             client=FakeEsi(), sso=FakeSso(),
                             spawn=DeferredSpawn())
    controller.refresh_characters()
    controller.shutdown()
    controller._spawn.run_next()          # The worker starts after shutdown.

    assert controller._client.calls == []
```

`build()` needs to keep the spawn reachable for that last test; add to the
controller's `__init__` nothing new — the test reads `controller._spawn`, which
already holds the injected object.

- [ ] **Step 17: Run test to verify it passes**

Run: `python -m pytest tests/test_eveskills_controller.py -v`
Expected: PASS against Step 8. Removing the `try/except` in `shutdown` fails the
second test with `OSError: socket already closed`.

- [ ] **Step 18: Commit**

```bash
git add tests/test_eveskills_controller.py
git commit -m "test(eveskills): shutdown never raises and stops a running pass"
```

---

### Task 15: `api.py` façade and `__main__` wiring

**Files:**
- Modify: `obs_youtube_uploader/ui/api.py:156-195` (add the `skills=` keyword and `self._skills`)
- Modify: `obs_youtube_uploader/ui/api.py:1516` (append the `# ---- EVE skills ---` banner at the end of the class)
- Modify: `obs_youtube_uploader/__main__.py:283-325` (add `build_skills_controller` after `build_preview_host`)
- Modify: `obs_youtube_uploader/__main__.py:382` (construct it), `:468` (tear it down)
- Test: `tests/test_api_skills.py`
- Test: `tests/test_skills_wiring.py`

**Interfaces:**
- Consumes: `SkillsController` (Tasks 12–14); `paths.eve_skills_file()`, `paths.eve_skills_cache_file()`, `paths.skill_plans_dir()` (Task 1)
- Produces:
  ```python
  class Api:
      def skills_state(self) -> dict
      def skills_character_detail(self, character_id, plan_name) -> dict
      def skills_add_character(self) -> bool
      def skills_cancel_auth(self) -> bool
      def skills_forget_character(self, character_id) -> bool
      def skills_refresh(self) -> bool
      def skills_reload_plans(self) -> bool
      def skills_open_plans_folder(self) -> bool
      def skills_select_plan(self, plan_name) -> bool
      def shutdown_skills(self) -> None       # main() only; never raises

  # __main__.py
  def build_skills_controller(api) -> SkillsController | None
  ```

> **Why `build_skills_controller(api)` and not `(state)`.** The controller
> needs `push` and `alert`, and both are bound methods of `Api`, not of
> `AppState` — the same reason `__main__` already reaches `api._watcher` and
> `api._on_recording_dir_ready`. `Api` is therefore constructed first and
> `api._skills` assigned after, exactly as `ui/window.py:create()` assigns
> `api._window` after `create_window()` for the identical chicken-and-egg
> reason.

---

- [ ] **Step 1: Write the failing test — the façade delegates, and tolerates no controller**

```python
"""The nine EVE skills façade methods. The controller is faked whole.

These are pure delegation, so what is worth testing is exactly the two
things delegation gets wrong: what a mutation returns, and what happens when
there is no controller at all.
"""
from tests.fakes import FakeWindow
from tests.test_api import make_api


class FakeSkills:
    """Records calls. The real controller has its own suite."""

    def __init__(self):
        self.calls = []
        self.forget_result = True

    def state_payload(self):
        self.calls.append(("state_payload",))
        return {"characters": [], "plans": []}

    def character_detail(self, character_id, plan_name):
        self.calls.append(("character_detail", character_id, plan_name))
        return {"ok": True, "requirements": []}

    def authenticate(self):
        self.calls.append(("authenticate",))

    def cancel_auth(self):
        self.calls.append(("cancel_auth",))

    def forget(self, character_id):
        self.calls.append(("forget", character_id))
        return self.forget_result

    def refresh_characters(self):
        self.calls.append(("refresh_characters",))

    def reload_plans(self):
        self.calls.append(("reload_plans",))

    def open_plans_folder(self):
        self.calls.append(("open_plans_folder",))

    def select_plan(self, plan_name):
        self.calls.append(("select_plan", plan_name))
        return True

    def shutdown(self):
        self.calls.append(("shutdown",))


def make(tmp_path, skills=None):
    api = make_api(tmp_path, window=FakeWindow(), skills=skills)
    return api, skills


def test_reads_return_the_controllers_payload(tmp_path):
    api, skills = make(tmp_path, FakeSkills())

    assert api.skills_state() == {"characters": [], "plans": []}
    assert api.skills_character_detail(95, "Interceptor")["ok"] is True
    assert skills.calls[1] == ("character_detail", 95, "Interceptor")


def test_every_mutation_returns_truthy(tmp_path):
    """WM.send resolves to null on a bridge failure, so the page cannot tell
    a method that returned None from a call that never landed. ui/api.py
    records that returning None from a no-op WAS the bug -- the redundant
    preview toggle read as a broken call and reverted the checkbox.

    Every mutation here therefore returns True, INCLUDING the paths that
    did nothing."""
    api, _ = make(tmp_path, FakeSkills())

    assert api.skills_add_character() is True
    assert api.skills_cancel_auth() is True
    assert api.skills_refresh() is True
    assert api.skills_reload_plans() is True
    assert api.skills_open_plans_folder() is True
    assert api.skills_select_plan("Interceptor") is True


def test_forget_reports_the_controllers_answer(tmp_path):
    """The one mutation with a real False: a payload that is not an id."""
    api, skills = make(tmp_path, FakeSkills())
    skills.forget_result = False

    assert api.skills_forget_character(None) is False


def test_every_method_tolerates_no_controller(tmp_path):
    """The controller is None when it failed to build. Every call site
    returns a safe value rather than platform-checking or raising -- the
    same posture build_preview_host()'s None takes, and the reason the page
    needs no capability probe."""
    api, _ = make(tmp_path, None)

    assert api.skills_state()["characters"] == []
    assert api.skills_character_detail(95, "x")["ok"] is False
    assert api.skills_add_character() is True
    assert api.skills_cancel_auth() is True
    assert api.skills_forget_character(95) is False
    assert api.skills_refresh() is True
    assert api.skills_reload_plans() is True
    assert api.skills_open_plans_folder() is True
    assert api.skills_select_plan("x") is True
    api.shutdown_skills()


def test_the_empty_state_has_the_same_shape_as_a_real_one(tmp_path):
    """One renderer, one shape. A payload missing keys when the subsystem is
    absent means every access in skills.js needs a guard, and the one that
    gets forgotten throws inside a click handler."""
    api, _ = make(tmp_path, None)

    payload = api.skills_state()

    for key in ("auth_configured", "auth_in_progress", "refresh_in_flight",
                "selected_plan_name", "plans", "characters", "plan_issues",
                "warnings", "plans_updated_utc"):
        assert key in payload
    assert payload["auth_configured"] is False


def test_shutdown_skills_never_raises(tmp_path):
    """Called last on every exit path, after the window has gone."""
    class Exploding(FakeSkills):
        def shutdown(self):
            raise RuntimeError("teardown")

    api, _ = make(tmp_path, Exploding())

    api.shutdown_skills()


def test_the_api_still_exposes_no_public_non_method_attributes(tmp_path):
    """test_api.py:114 asserts this globally; repeated here because adding a
    public `skills` attribute holding a controller is exactly the shape that
    sent pywebview's proxy walk into WinForms and killed the process eight
    seconds after launch."""
    api, _ = make(tmp_path, FakeSkills())

    for name in dir(api):
        if name.startswith("_"):
            continue
        assert callable(getattr(api, name)), f"{name} is not a method"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_skills.py -v`
Expected: FAIL with `TypeError: Api.__init__() got an unexpected keyword argument 'skills'`

- [ ] **Step 3: Write minimal implementation**

In `Api.__init__`, beside `preview_host`:

```python
                 timer=threading.Timer, preview_host=None, skills=None):
```

and beside the `_preview_host` assignment:

```python
        # None off the happy path -- when the subsystem failed to build, and
        # in most tests. Every call site below tolerates its absence and
        # returns a safe value, which is what lets the page render the route
        # without probing for a capability first.
        self._skills = skills
```

At the end of the class:

```python
    # ---- EVE skills ---

    def skills_state(self) -> dict:
        """Everything the Skills route renders, in one call."""
        if self._skills is None:
            return _empty_skills_state()
        return self._skills.state_payload()

    def skills_character_detail(self, character_id, plan_name) -> dict:
        if self._skills is None:
            return {"ok": False, "message": "The EVE skills subsystem is "
                    "unavailable.", "character_id": 0, "plan_name": "",
                    "readiness": "Unknown", "estimated_finish_utc": "",
                    "queue_timing_unknown": False, "requirements": []}
        return self._skills.character_detail(character_id, plan_name)

    def skills_add_character(self) -> bool:
        """Start an interactive EVE sign-in. Returns before it finishes.

        True even with no controller, and even though nothing happened.
        `WM.send` resolves to null on a bridge failure and the page cannot
        otherwise tell the two apart -- the comment on set_preview_enabled
        above records that returning None from a no-op WAS the bug, and that
        it cost a checkbox that reverted on every successful toggle.
        """
        if self._skills is not None:
            self._skills.authenticate()
        return True

    def skills_cancel_auth(self) -> bool:
        if self._skills is not None:
            self._skills.cancel_auth()
        return True

    def skills_forget_character(self, character_id) -> bool:
        """False is meaningful here: nothing was forgotten."""
        if self._skills is None:
            return False
        return self._skills.forget(character_id)

    def skills_refresh(self) -> bool:
        if self._skills is not None:
            self._skills.refresh_characters()
        return True

    def skills_reload_plans(self) -> bool:
        if self._skills is not None:
            self._skills.reload_plans()
        return True

    def skills_open_plans_folder(self) -> bool:
        if self._skills is not None:
            self._skills.open_plans_folder()
        return True

    def skills_select_plan(self, plan_name) -> bool:
        if self._skills is None:
            return True
        return self._skills.select_plan(plan_name)

    def shutdown_skills(self) -> None:
        """Tear the subsystem down on the way out. main() only.

        Not a façade -- the page never calls it, exactly as it never calls
        shutdown_previews(). Runs on every exit path, so like
        shutdown_engine() it must never be the thing that raises: a live
        loopback socket on the fixed redirect port would make the NEXT
        launch's sign-in fail to bind, and there is no fallback port.
        """
        if self._skills is None:
            return
        try:
            self._skills.shutdown()
        except Exception:
            logger.exception("EVE skills subsystem did not stop cleanly")
```

And beside the other module-level helpers near the top of `api.py`:

```python
def _empty_skills_state() -> dict:
    """The state payload when there is no controller at all.

    Same keys as the real one so skills.js has exactly one renderer. A
    payload that drops fields when the subsystem is absent means every
    access in the page needs a guard, and the one that gets forgotten
    throws inside a click handler with no console attached.
    """
    return {"auth_configured": False, "auth_in_progress": False,
            "refresh_in_flight": False, "selected_plan_name": "",
            "plans": [], "characters": [], "plan_issues": [],
            "warnings": ["The EVE skills subsystem is unavailable."],
            "plans_updated_utc": ""}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_skills.py tests/test_api.py -v`

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/ui/api.py tests/test_api_skills.py
git commit -m "feat(ui): nine EVE skills facade methods on the bridge"
```

---

- [ ] **Step 6: Write the failing test — construction and lifecycle in `__main__`**

```python
"""Wiring for the EVE skills subsystem, mirroring test_preview_wiring.py.

What must hold: the builder runs on every platform, a broken subsystem does
not stop Wingman launching, the callbacks it passes are resolved eagerly,
and main() both constructs it and tears it down.
"""
import inspect

import pytest

from obs_youtube_uploader import __main__ as main_mod


def test_build_skills_controller_is_not_windows_gated(monkeypatch, tmp_path):
    """Unlike build_preview_host, this one runs everywhere. Twelve of the
    thirteen modules are pure or filesystem-only; the Windows-only piece
    (dpapi) is reached through an injected seam, so gating the whole
    subsystem on sys.platform would take the entire Linux test surface with
    it -- and would make the route dead in development."""
    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)

    from tests.test_api import make_api
    controller = main_mod.build_skills_controller(make_api(tmp_path))

    assert controller is not None


def test_build_skills_controller_survives_a_broken_subsystem(monkeypatch):
    """Skills are secondary to the upload workflow. A failure to construct
    them must not stop Wingman launching -- the same posture
    build_preview_host takes, and the reason its whole body is wrapped."""
    assert main_mod.build_skills_controller(object()) is None


def test_the_builder_passes_bound_methods_not_lambdas(monkeypatch, tmp_path):
    """A name resolved lazily inside a lambda is not checked when the
    builder runs, so a wrong module alias ships green and fails on a user's
    machine the first time a push happens.
    tests/test_preview_wiring.py:96-108 records exactly what that cost --
    `save_settings=lambda data: settings.save(data)` with the wrong alias.
    """
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)

    from tests.test_api import make_api
    api = make_api(tmp_path)
    controller = main_mod.build_skills_controller(api)

    assert controller._push_cb == api._push
    assert controller._alert == api._alert


def test_main_builds_the_controller_and_hands_it_to_the_api():
    """The method existed, was tested directly, and nothing called it -- the
    exact failure test_preview_wiring.py records for previews. A unit test
    on the builder cannot catch that; only reading main() can."""
    src = inspect.getsource(main_mod.main)

    assert "build_skills_controller(api)" in src
    assert "api._skills =" in src


def test_main_tears_the_subsystem_down_last_and_unconditionally():
    """A live loopback socket on the fixed redirect port would make the next
    launch's sign-in fail to bind, and there is no fallback port."""
    lines = [line.strip() for line in
             inspect.getsource(main_mod.main).splitlines() if line.strip()]

    assert "api.shutdown_skills()" in lines
    at = lines.index("api.shutdown_skills()")
    assert lines[at + 1] == "return 0", "nothing may run after the teardown"
    # Not inside an `if`: the previous line is the other unconditional
    # teardown, not a guard.
    assert lines[at - 1] == "api.shutdown_previews()"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_skills_wiring.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.__main__' has no attribute 'build_skills_controller'`

- [ ] **Step 8: Write minimal implementation**

Add to `__main__.py` immediately after `build_preview_host`:

```python
def build_skills_controller(api):
    """The EVE skills controller, or None where it cannot be built.

    NOT Windows-gated, unlike build_preview_host: twelve of the thirteen
    modules in the subpackage are pure or filesystem-only, and the one
    Windows-only piece (dpapi) is reached through an injected seam inside
    tokens.py. Gating here would make the route dead in development and
    would take the entire Linux test surface with it.

    Takes the Api rather than the AppState because `push` and `_alert` are
    bound methods of the Api -- and it is constructed after it for the same
    chicken-and-egg reason ui/window.py assigns `api._window` after
    create_window().

    The imports are inside the function so a broken or missing subpackage
    costs the Skills route and nothing else; the whole body is wrapped for
    the same reason previews are.
    """
    try:
        from .eveskills.controller import SkillsController

        return SkillsController(
            state_path=paths.eve_skills_file(),
            cache_path=paths.eve_skills_cache_file(),
            plans_dir=paths.skill_plans_dir(),
            # Bound methods, never lambdas wrapping them: a name resolved
            # lazily inside a lambda is not checked when this function
            # runs, and tests/test_preview_wiring.py records what that cost
            # last time.
            push=api._push,
            alert=api._alert)
    except Exception:
        # Skills are secondary to the upload workflow. A failure to
        # construct them must not stop Wingman launching.
        logger.exception("EVE skills subsystem unavailable")
        return None
```

In `main()`, replace line 382 with:

```python
    api = api_mod.Api(state, preview_host=build_preview_host(state))
    # After construction, not through the constructor: the controller needs
    # the Api's own _push and _alert. Same shape, and same reason, as
    # ui/window.py assigning api._window after create_window().
    api._skills = build_skills_controller(api)
```

and after line 468:

```python
    api.shutdown_previews()
    # Last, and unconditional: a loopback socket still bound to the fixed
    # redirect port would make the next launch's sign-in fail to bind, and
    # the redirect URI is registered with CCP so there is no fallback port
    # to move to.
    api.shutdown_skills()
    return 0
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/test_skills_wiring.py tests/test_preview_wiring.py -v`

- [ ] **Step 10: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: all green, including `tests/test_packaging_completeness.py` (Task 1 added
`obs_youtube_uploader.eveskills` to `pyproject.toml`'s `packages`) and
`tests/test_api.py::test_api_exposes_no_public_non_method_attributes`.

- [ ] **Step 11: Commit**

```bash
git add obs_youtube_uploader/__main__.py tests/test_skills_wiring.py
git commit -m "feat(app): build and tear down the EVE skills controller in main()"
```
### Task 16: The fourth route and the skills page module

**Files:**
- Create: `obs_youtube_uploader/web/skills.js`
- Modify: `obs_youtube_uploader/web/index.html:18-22` (nav), `obs_youtube_uploader/web/index.html:260-280` (route divs), `obs_youtube_uploader/web/index.html:334-340` (script list)
- Modify: `obs_youtube_uploader/web/app.js:49-52` (`WM.HANDLERS`), `obs_youtube_uploader/web/app.js:90-116` (`WM.route`)
- Modify: `.github/workflows/build.yml:256-260`
- Modify: `.github/workflows/release.yml:228-229`
- Modify: `obs_youtube_uploader/web/dev.js:19-24` and `:116-170`
- Test: none. **There is no JS test harness in this repo** — no Playwright, no node, no browser toolchain, and `docs/smoke-checklist.md:7-12` says so plainly: *"This checklist is the only verification any of that gets."* Every step below verifies either by opening `obs_youtube_uploader/web/index.html?dev=1` in a browser or by running the app with `python -m obs_youtube_uploader`. Say that out loud rather than inventing a runner.

**Interfaces:**
- Consumes: `Api.skills_state()` → the `state_payload()` dict from the contract (`auth_configured`, `auth_in_progress`, `refresh_in_flight`, `selected_plan_name`, `plans[]`, `characters[]`, `plan_issues[]`, `warnings[]`, `plans_updated_utc`); the `onSkills` push carrying that same dict; the `onSkillsProgress` push `{character_id, character_name, completed, total, error}`. Mutations `skills_add_character()`, `skills_cancel_auth()`, `skills_refresh()`, `skills_reload_plans()`, `skills_open_plans_folder()`, `skills_select_plan(plan_name)` — every one returns truthy and pushes `onSkills`.
- Produces: the module-level `render(payload)` / `renderRoster()` seam and the `STATE`, `characters()`, `expanded`, `details`, `filterText` variables that Task 17 builds the roster on; the `#skills-roster`, `#skills-empty`, `#skills-filter`, `#skills-filter-clear` elements Task 17 fills; the `.skills` / `.skills-rail` / `.skills-main` class names Task 17 styles.

---

- [ ] **Step 1: The nav button — a sibling of the drag region, never a child.**

In `obs_youtube_uploader/web/index.html`, add a fourth `.navbtn` inside
`<nav id="routenav">`. The comment at `index.html:15-17` already states the
rule and is not repeated here — the button simply has to land inside the
`<nav>`, which is itself the sibling. A clickable child of
`.pywebview-drag-region` yields either dead buttons or an immovable window,
because `style.css:100-102` gives only that element the drag surface.

```html
    <nav class="routenav" id="routenav">
      <button class="navbtn active" id="nav-main" data-route="main">Uploader</button>
      <button class="navbtn" id="nav-bookmarks" data-route="bookmarks">Bookmarks</button>
      <button class="navbtn" id="nav-previews" data-route="previews">Previews</button>
      <button class="navbtn" id="nav-skills" data-route="skills">Skills</button>
    </nav>
```

Note for the reviewer: `style.css:120-123` warns that past about four
destinations the 44px title bar needs rethinking. Skills is the fourth. This
is the last one that fits.

- [ ] **Step 2: The route div.**

Add after the `route-previews` block in `index.html` (currently ends at
`:280`), before `route-firstrun`. Unlike `route-previews` this is **not** a
settings form, so it does **not** wrap in `<div class="settings"><section
class="card">` — it is a two-pane workspace and gets its own layout in
Task 17.

```html
  <!-- NOT the .settings/.card wrapper the previews and bookmarks routes
       use: this is a two-pane workspace, not a form. The rail is fixed at
       214px and the main pane takes the rest; see .skills in style.css. -->
  <div class="route" id="route-skills">
    <aside class="skills-rail">
      <div class="rail-block">
        <p class="rail-count" id="skills-counts">No characters yet</p>
        <button class="btn" id="skills-add">Add character</button>
        <button class="btn" id="skills-refresh">Refresh characters</button>
      </div>
      <div class="rail-block rail-plans-block">
        <h3 class="rail-head">Plans</h3>
        <div class="rail-plans" id="skills-plans"></div>
      </div>
      <div class="rail-block">
        <button class="btn" id="skills-open-folder">Open plans folder</button>
        <button class="btn" id="skills-reload-plans">Reload plans</button>
      </div>
    </aside>

    <section class="skills-main">
      <header class="skills-head">
        <h1 id="skills-plan-name">No plan selected</h1>
        <span class="skills-plan-count" id="skills-plan-count"></span>
      </header>

      <!-- Collapses entirely when empty rather than reserving a blank
           strip: on the common path there is nothing to say, and an empty
           box that never fills reads as something that failed to load. -->
      <div class="skills-notices" id="skills-notices" hidden></div>

      <details class="skills-issues" id="skills-issues" hidden>
        <summary id="skills-issues-summary"></summary>
        <div id="skills-issues-body"></div>
      </details>

      <div class="skills-filterbar">
        <input class="field" id="skills-filter" type="text" spellcheck="false"
               placeholder="Filter characters">
        <button class="linkbtn" id="skills-filter-clear" hidden>Clear filter</button>
      </div>

      <div class="skills-roster" id="skills-roster"></div>
      <div class="empty" id="skills-empty" hidden></div>
    </section>
  </div>
```

- [ ] **Step 3: The script tag.**

Add `skills.js` to the list at the bottom of `index.html`. Order matters only
in that `app.js` must come first — it creates `window.WM` and the
`WM.HANDLERS` stubs every other module registers against.

```html
  <script src="app.js"></script>
  <script src="bookmarks.js"></script>
  <script src="list.js"></script>
  <script src="panel.js"></script>
  <script src="settings.js"></script>
  <script src="skills.js"></script>
  <script src="firstrun.js"></script>
  <script src="dev.js"></script>
```

- [ ] **Step 4: The route map, the peer list, and the handler names in `app.js`.**

Three edits in one file. Replace `WM.HANDLERS` (`app.js:49-52`):

```js
  WM.HANDLERS = ['onRows', 'onDuration', 'onProgress', 'onStatus',
                 'onRetryAvailable', 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog', 'onFirstRun',
                 'onBookmarks', 'onEveStatus',
                 'onSkills', 'onSkillsProgress'];
```

An unlisted name throws at registration (`app.js:55-57`) — that is the
design, not an obstacle. Forgetting this edit makes `skills.js` throw on
load and take every registration below it with it.

Then the routes map and the peer-destination list inside `WM.route`
(`app.js:91-113`):

```js
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun',
                   bookmarks: 'route-bookmarks',
                   previews: 'route-previews',
                   skills: 'route-skills' };
```

```js
    if (name === 'main' || name === 'bookmarks' || name === 'previews'
        || name === 'skills') {
      // Peer destinations, unlike Settings: the gear returns to whichever
      // of these you came from.
      WM.last_destination = name;
    }
```

The peer edit is the quiet one. Omit it and the gear still opens Settings
from Skills, but pressing it again drops you on whatever route you visited
*before* Skills — a bug that looks like a stray click rather than a missing
list entry.

- [ ] **Step 5: The bundled-asset assertion in `build.yml`, and the stale count above it.**

`.github/workflows/build.yml:256-260`, inside "Verify the web page is
bundled". **Two edits, not one.** The array gains `skills.js`, and the
comment directly above it **stops carrying a count at all**.

It currently reads *"any of the four scripts"* while the array lists
**five** — it was already wrong before this change. Do not correct four to
six. A number in a comment that has to match an array directly beneath it is
a maintenance trap: it has drifted once already, this task would be the
second chance to get it wrong, and the pending `bookmarks.js` / `dev.js` fix
is the third. Phrase it so it stays true however many entries the array
holds.

```yaml
          # Every file the page loads by name. index.html is the entry point;
          # a missing style.css or any of the scripts renders an unstyled or
          # inert page rather than failing. Settings is a ROUTE inside
          # index.html, so there is no second document to check.
          #
          # Deliberately no count: this said "the four scripts" while
          # listing five, because the number is not checked against
          # anything and nobody updates it when a file is added. The array
          # below is the list; the comment says what the list is for.
          foreach ($asset in @("index.html", "style.css", "app.js", "list.js", "panel.js", "settings.js", "skills.js", "firstrun.js",
                               "fonts/InterVariable.woff2", "fonts/JetBrainsMono-Regular.woff2")) {
```

`release.yml`'s array carries no such preamble, so Step 6 is the array edit
alone.

Why this step is not optional, and why it is the one that gets forgotten:
**PyInstaller exits 0 when a `datas` entry resolves to nothing.** The step's
own comment (`build.yml:230-246`) spells out the consequence — a green build
of an app whose page is absent, with no exception anywhere, because pywebview
swallows load failures and `webview.start()` returns normally. For a *script*
the failure is narrower than a missing `web/` but just as silent: the route
renders its static markup, the nav button works, and nothing in it responds,
because the IIFE that wires every listener was never fetched.

- [ ] **Step 6: The same assertion in `release.yml`.**

`.github/workflows/release.yml:228-229`, identical edit:

```yaml
          foreach ($asset in @("index.html", "style.css", "app.js", "list.js", "panel.js", "settings.js", "skills.js", "firstrun.js",
                               "fonts/InterVariable.woff2", "fonts/JetBrainsMono-Regular.woff2")) {
```

**The two workflows are deliberately mirrored and say so.**
`release.yml:218-220` reads: *"Deliberately mirrors build.yml's step of the
same name. If you change one, change the other — they are the same assertion
on the same path, and the release path must not be the weaker of the two."*
`release.yml:209-216` records why the mirroring exists at all: release.yml
once carried no post-build assertion of any kind, so a release built straight
from a tag skipped every check build.yml had, and the first report would have
come from a user who downloaded a release and saw nothing happen. Editing
build.yml alone re-creates exactly that asymmetry.

Flag for the reviewer while you are in here, and do **not** fix it as part of
this task: `bookmarks.js` and `dev.js` are absent from both arrays today. It
is a pre-existing gap with the same failure shape, and it belongs in its own
change rather than riding along in this one. If that change lands first the
arrays will already hold entries this task does not mention — add `skills.js`
to what is there rather than replacing the line wholesale.

- [ ] **Step 7: `skills.js` — the module skeleton, the state, and the first-entry ask.**

Create `obs_youtube_uploader/web/skills.js`. Vanilla ES5-flavoured, `var`,
`Array.prototype.forEach.call`, one IIFE with `'use strict'` — matching
`bookmarks.js`. No framework, no build step, no ES modules; nothing in this
repo compiles JavaScript.

```js
/* FlyGD Wingman — the Skills route.
 *
 * Answers one question: who can fly this plan? Every judgement that
 * produces that answer -- readiness precedence, ETA, requirement state --
 * happens in Python's evaluator, because this repo has no way to test
 * JavaScript (webview-replatform-design.md:545). This file groups, sorts,
 * filters, and renders what Python already decided.
 *
 * The one derived value here is the plan rail's ready RATIO: Python sends
 * each plan's ready_count, and the denominator is characters.length, which
 * the page already holds.
 */
(function () {
  'use strict';
  var WM = window.WM;

  var STATE = null;       // last onSkills payload, whole
  var progress = null;    // last onSkillsProgress, cleared when a refresh ends
  var expanded = {};      // character_id -> true
  var details = {};       // character_id -> character_detail() payload
  var pendingDetail = {}; // character_id -> in-flight request id
  var detailSeq = 0;
  var confirming = 0;     // character_id whose Forget is awaiting confirmation
  var filterText = '';
  var asked = false;      // has the page asked Python for state yet

  function characters() { return (STATE && STATE.characters) || []; }
  function plans() { return (STATE && STATE.plans) || []; }

  function render(payload) {
    if (!payload) return;
    STATE = payload;
    // Progress lines describe a refresh in flight. onSkills is pushed on
    // BOTH the success and failure paths of every mutation, so the end of
    // a refresh always arrives here -- which is what stops "Refreshed 3 of
    // 7 characters" sitting on screen forever after a failure.
    if (!payload.refresh_in_flight) progress = null;
    renderRail();
    renderHead();
    renderNotices();
    renderIssues();
    renderRoster();
  }

  WM.handle('onSkills', render);

  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'skills') return;
    // The page asks; Python does not push unprompted at boot. Same rule
    // app.js:139-148 follows for rows and settings -- a subsystem that
    // costs nothing until you open it cannot be pushing state at launch.
    // Asked on FIRST entry only: after that every mutation pushes onSkills,
    // so re-asking on each entry would be a redundant round trip carrying
    // the largest payload in the app.
    if (asked) return;
    asked = true;
    WM.send('skills_state').then(render);
  });
}());
```

Verify: run the app, click Skills. The route shows its static markup and the
console carries no `unknown bridge handler` throw. Nothing renders yet —
`renderRail` and friends land in the next steps, so expect
`renderRail is not defined` in the console until Step 8. (Hoisted `function`
declarations mean the order they appear in the file does not matter, only
that they exist by the time `render` runs.)

- [ ] **Step 8: The left rail — counts, the plan list, and the ready ratios.**

```js
  // ---- left rail ------------------------------------------------------
  function renderRail() {
    var chars = characters();
    var ready = 0;
    chars.forEach(function (ch) { if (ch.readiness === 'Ready') ready += 1; });
    WM.el('skills-counts').textContent = chars.length
      ? chars.length + (chars.length === 1 ? ' character' : ' characters')
        + ' · ' + ready + ' ready'
      : 'No characters yet';

    renderRailButtons();
    renderPlans();
  }

  function renderPlans() {
    var host = WM.el('skills-plans');
    host.textContent = '';
    var list = plans();
    if (!list.length) {
      host.appendChild(WM.make('p', 'hint', 'No plans found.'));
      return;
    }
    var total = characters().length;
    var selected = (STATE.selected_plan_name || '').toLowerCase();
    list.forEach(function (plan) {
      var row = WM.make('button', 'rail-plan');
      if ((plan.name || '').toLowerCase() === selected) {
        row.classList.add('active');
      }
      row.appendChild(WM.make('span', 'rail-plan-name', plan.name));
      // The numerator is Python's ready_count for this plan; the
      // denominator is simply how many characters exist, which the page
      // already holds. Deriving the ratio here rather than sending a
      // formatted string keeps the payload keys plain numbers.
      row.appendChild(WM.make('span', 'rail-ratio',
                              plan.ready_count + '/' + total));
      row.addEventListener('click', function () { selectPlan(plan.name); });
      host.appendChild(row);
    });
  }
```

- [ ] **Step 9: Plan selection, and the detail cache it invalidates.**

```js
  function selectPlan(name) {
    if (!STATE || name === STATE.selected_plan_name) return;
    // Every cached detail was computed against the OLD plan and is now
    // answering a question nobody asked. Dropping pendingDetail as well is
    // what makes the in-flight replies land in requestDetail's mismatch
    // branch and be discarded rather than rendered under the new plan.
    details = {};
    pendingDetail = {};
    WM.send('skills_select_plan', name).then(function (ok) {
      // `!ok` rather than `=== false`: WM.send resolves to null on any
      // bridge failure (app.js:38-43), and select_plan returns True even
      // for a no-op precisely so the page can tell the two apart
      // (ui/api.py's convention). Either way the push re-syncs us, so
      // there is nothing to do but re-request the open rows.
      if (!ok) return;
      Object.keys(expanded).forEach(function (id) {
        requestDetail(parseInt(id, 10));
      });
    });
  }
```

- [ ] **Step 10: The rail's four action buttons.**

```js
  function renderRailButtons() {
    var add = WM.el('skills-add');
    var refresh = WM.el('skills-refresh');
    // Auth is unconfigured when application.py still holds the placeholder
    // client id -- a source checkout of a fork that has not registered its
    // own EVE application. Disabling with a reason beats a button that
    // opens a browser to an OAuth error.
    add.disabled = !STATE.auth_configured;
    add.title = STATE.auth_configured ? ''
      : 'This build has no EVE application id configured.';
    add.textContent = STATE.auth_in_progress
      ? 'Cancel sign-in' : 'Add character';
    refresh.textContent = STATE.refresh_in_flight
      ? 'Refreshing…' : 'Refresh characters';
    refresh.disabled = STATE.refresh_in_flight || !characters().length;
  }

  WM.el('skills-add').addEventListener('click', function () {
    if (!STATE) return;
    WM.send(STATE.auth_in_progress
            ? 'skills_cancel_auth' : 'skills_add_character');
  });

  WM.el('skills-refresh').addEventListener('click', function () {
    WM.send('skills_refresh');
  });

  WM.el('skills-open-folder').addEventListener('click', function () {
    WM.send('skills_open_plans_folder');
  });

  WM.el('skills-reload-plans').addEventListener('click', function () {
    // A reload can change which plan names exist, so the cached details
    // are no more trustworthy than after a plan switch.
    details = {};
    pendingDetail = {};
    WM.send('skills_reload_plans');
  });
```

None of these four inspect the return value. Every one is a mutation, and a
mutation pushes `onSkills` on both its success and failure paths — the push
is the answer, and acting on the return as well would render the same state
twice.

- [ ] **Step 11: The head, the notices strip, and the plan-issues disclosure.**

```js
  // ---- main pane header ------------------------------------------------
  function renderHead() {
    var name = STATE.selected_plan_name || '';
    WM.el('skills-plan-name').textContent = name || 'No plan selected';
    var count = 0;
    plans().forEach(function (plan) {
      if ((plan.name || '').toLowerCase() === name.toLowerCase()) {
        count = plan.requirement_count;
      }
    });
    WM.el('skills-plan-count').textContent = name
      ? count + (count === 1 ? ' requirement' : ' requirements') : '';
  }

  function renderNotices() {
    var host = WM.el('skills-notices');
    host.textContent = '';
    var lines = [];
    if (STATE.auth_in_progress) {
      lines.push('Waiting for EVE SSO…');
    }
    if (progress && progress.total) {
      lines.push('Refreshed ' + progress.completed + ' of '
                 + progress.total + ' characters');
    }
    (STATE.warnings || []).forEach(function (text) { lines.push(text); });
    host.hidden = !lines.length;
    lines.forEach(function (text) {
      host.appendChild(WM.make('p', 'notice', text));
    });
  }

  WM.handle('onSkillsProgress', function (payload) {
    progress = payload;
    // Only the strip moves. A progress tick during a forty-character
    // refresh must not rebuild forty rows and collapse the one the user is
    // reading -- and it carries nothing the roster renders anyway.
    renderNotices();
  });

  function renderIssues() {
    var host = WM.el('skills-issues');
    var issues = STATE.plan_issues || [];
    host.hidden = !issues.length;
    if (!issues.length) return;
    WM.el('skills-issues-summary').textContent =
      issues.length + (issues.length === 1
                       ? ' plan file has problems' : ' plan files have problems');
    var body = WM.el('skills-issues-body');
    body.textContent = '';
    issues.forEach(function (issue) {
      body.appendChild(WM.make('p', 'issue-file', issue.file_name));
      body.appendChild(WM.make('p', 'issue-message', issue.message));
      (issue.diagnostics || []).forEach(function (diag) {
        // Line 0 is the contract's whole-file diagnostic (plans.py's
        // Diagnostic docs it), so it must not print as "line 0".
        body.appendChild(WM.make(
          'p', 'issue-line',
          diag.line ? 'Line ' + diag.line + ': ' + diag.message
                    : diag.message));
      });
    });
  }
```

Collapsed by default because `<details>` is: a plan file with a typo is
worth surfacing, not worth pushing the roster down the page.

- [ ] **Step 12: The dev.js mock, so the page can be built in a browser.**

`obs_youtube_uploader/web/dev.js`. Add the six mutations to the generic stub
list at `:20-24` — they log and resolve to `null`, which is honest for
methods whose real answer arrives as a push:

```js
  var api = {};
  ['delete_selected', 'start_upload', 'retry',
   'open_path', 'copy_path', 'detect_folder',
   'connect_google', 'dialog_response', 'minimize', 'close',
   'set_recording_dir',
   'skills_add_character', 'skills_cancel_auth', 'skills_refresh',
   'skills_reload_plans', 'skills_open_plans_folder'
  ].forEach(function (name) { api[name] = log(name); });
```

`skills_select_plan` and `skills_forget_character` are **not** generic stubs,
for exactly the reason the file already records about `save_settings` at
`dev.js:26-29`: the page guards on `!ok`, so a `null` would make them silent
no-ops here while working in the product — a harness that lies about the
flows it exists to exercise. Add after the `api.save_settings` block:

```js
  // NOT generic stubs, for the same reason save_settings above is not: the
  // page guards on `!ok`, and the real bridge returns True even for a
  // no-op. A null here would make plan switching and forget dead in the
  // browser while working under Python.
  api.skills_select_plan = function (name) {
    console.log('DEV api.skills_select_plan(', name, ')');
    skills.selected_plan_name = name;
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_forget_character = function (id) {
    console.log('DEV api.skills_forget_character(', id, ')');
    skills.characters = skills.characters.filter(function (ch) {
      return ch.character_id !== id;
    });
    setTimeout(function () { window.onSkills(skills); }, 0);
    return Promise.resolve(true);
  };

  api.skills_state = function () {
    console.log('DEV api.skills_state()');
    return Promise.resolve(skills);
  };

  api.skills_character_detail = function (id, plan) {
    console.log('DEV api.skills_character_detail(', id, plan, ')');
    return Promise.resolve({
      ok: true, message: '', character_id: id, plan_name: plan,
      readiness: 'Missing', estimated_finish_utc: '',
      queue_timing_unknown: false,
      requirements: [
        { skill_name: 'Amarr Cruiser', required_level: 5, active_level: 4,
          trained_level: 4, state: 'Missing', queued_finish_utc: '',
          queue_timing_unknown: false },
        { skill_name: 'Heavy Assault Cruisers', required_level: 1,
          active_level: 0, trained_level: 1, state: 'TrainedInactive',
          queued_finish_utc: '', queue_timing_unknown: false },
        { skill_name: 'Energy Grid Upgrades', required_level: 4,
          active_level: 3, trained_level: 3, state: 'Queued',
          queued_finish_utc: '2026-08-27T04:00:00+00:00',
          queue_timing_unknown: false }
      ]
    });
  };
```

And the fixture the four above share, placed beside `settingsPayload`. It
covers every readiness group including one the page does **not** know, so the
catch-all bucket Task 17 builds can be seen working:

```js
  // One character per readiness group, plus a deliberately unrecognised
  // one so the roster's catch-all bucket is visible in the browser. The
  // Unscored row is the common case, not padding: every character is
  // Unscored between authorisation and its first refresh.
  var skills = {
    auth_configured: true, auth_in_progress: false, refresh_in_flight: false,
    selected_plan_name: 'Ishtar',
    plans: [
      { name: 'Ishtar', requirement_count: 14, ready_count: 1 },
      { name: 'Loki', requirement_count: 22, ready_count: 0 }
    ],
    characters: [
      { character_id: 1, character_name: 'Aiga Otsolen',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Ready',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 14, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0 },
      { character_id: 2, character_name: 'Zuelo Parvi',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '2026-08-26T12:00:00+00:00',
        queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 2,
        missing_count: 0, unknown_count: 0 },
      { character_id: 3, character_name: 'Kaska Rin',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Training',
        estimated_finish_utc: '', queue_timing_unknown: true,
        active_count: 13, trained_inactive_count: 0, queued_count: 1,
        missing_count: 0, unknown_count: 0 },
      { character_id: 4, character_name: 'Delen Vok',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Locked',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 11, trained_inactive_count: 3, queued_count: 0,
        missing_count: 0, unknown_count: 0 },
      { character_id: 5, character_name: 'Gustav Oswaldo',
        fetched_utc: '2026-08-23T20:00:00+00:00',
        error: 'ESI returned 503', needs_reauth: false, stale: true,
        readiness: 'Missing', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 8, trained_inactive_count: 0, queued_count: 0,
        missing_count: 6, unknown_count: 0 },
      { character_id: 6, character_name: 'Nera Tal',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Missing',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 12, trained_inactive_count: 0, queued_count: 0,
        missing_count: 2, unknown_count: 0 },
      { character_id: 7, character_name: 'Orin Kesh',
        fetched_utc: '2026-08-24T08:00:00+00:00', error: '',
        needs_reauth: false, stale: false, readiness: 'Unknown',
        estimated_finish_utc: '', queue_timing_unknown: false,
        active_count: 13, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 1 },
      { character_id: 8, character_name: 'Tavi Solen', fetched_utc: '',
        error: 'The refresh token was rejected', needs_reauth: true,
        stale: false, readiness: 'Unscored', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0 },
      { character_id: 9, character_name: 'Mira Halcyon', fetched_utc: '',
        error: '', needs_reauth: false, stale: false,
        readiness: 'Ascendant', estimated_finish_utc: '',
        queue_timing_unknown: false,
        active_count: 0, trained_inactive_count: 0, queued_count: 0,
        missing_count: 0, unknown_count: 0 }
    ],
    plan_issues: [
      { file_name: 'Broken.txt', message: 'The file was rejected.',
        diagnostics: [{ line: 4, message: 'Missing a level' },
                      { line: 0, message: 'No requirements were parsed' }] }
    ],
    warnings: [],
    plans_updated_utc: '2026-08-24T08:00:00+00:00'
  };
```

Finally add the manual drivers to `window.DEV`, for the pushes no click can
produce in a browser:

```js
    skillsProgress: function (completed, total) {
      window.onSkillsProgress({ character_id: 2, character_name: 'Zuelo Parvi',
                                completed: completed, total: total, error: '' });
    },
    skillsAuth: function (busy) {
      skills.auth_in_progress = !!busy;
      window.onSkills(skills);
    },
    skillsRefreshing: function (busy) {
      skills.refresh_in_flight = !!busy;
      window.onSkills(skills);
    },
    skillsEmpty: function () {
      skills.characters = [];
      skills.plans = [];
      skills.selected_plan_name = '';
      window.onSkills(skills);
    }
```

Verify: open `obs_youtube_uploader/web/index.html?dev=1` in a browser, click
Skills. The rail shows `9 characters · 1 ready`, two plans with `1/9` and
`0/9`, and the issues disclosure. `DEV.skillsAuth(true)` flips Add character
to Cancel sign-in and puts `Waiting for EVE SSO…` in the notices strip;
`DEV.skillsProgress(3, 9)` shows `Refreshed 3 of 9 characters`.

- [ ] **Step 13: Commit.**

```
git add obs_youtube_uploader/web/index.html obs_youtube_uploader/web/app.js \
        obs_youtube_uploader/web/skills.js obs_youtube_uploader/web/dev.js \
        .github/workflows/build.yml .github/workflows/release.yml
git commit -m "Add the Skills route, its rail, and the bundled-asset assertion"
```

---

### Task 17: The roster, in-row expansion, and CSS

**Files:**
- Modify: `obs_youtube_uploader/web/skills.js` (append; the module from Task 16)
- Modify: `obs_youtube_uploader/web/style.css` (append a `====== skills route ======` block at the end, after the first-run route)
- Test: none automated. See the note at the end of this task — the grouping function is the one piece here worth testing and the one piece nothing can test, which the design doc admits at `triffskills-design.md:817-821`.

**Interfaces:**
- Consumes: each `characters[]` entry from `state_payload()` — `character_id`, `character_name`, `fetched_utc`, `error`, `needs_reauth`, `stale`, `readiness`, `estimated_finish_utc`, `queue_timing_unknown`, `missing_count`; and `character_detail()` → `{ok, message, character_id, plan_name, readiness, estimated_finish_utc, queue_timing_unknown, requirements: [{skill_name, required_level, active_level, trained_level, state, queued_finish_utc, queue_timing_unknown}]}`. Calls `skills_character_detail(character_id, plan_name)` and `skills_forget_character(character_id)`.
- Produces: nothing further consumes this. It is the last surface in the chain.

---

- [ ] **Step 1: `buildRoster()` — the lockout guard.**

This is the piece most worth getting right in the whole page. Append to
`skills.js`:

```js
  // ---- the roster ------------------------------------------------------
  // Group order is fixed and matches evaluator.READINESS_ORDER, with a
  // trailing catch-all. OTHER is not in that list on purpose: it exists to
  // catch a readiness string this page has never heard of.
  var GROUPS = ['Ready', 'Training', 'Locked', 'Missing', 'Unknown',
                'Unscored'];
  var OTHER = 'Other';

  var GROUP_LABEL = {
    Ready: 'Ready', Training: 'Training', Locked: 'Locked',
    Missing: 'Missing requirements', Unknown: 'Unknown skills',
    Unscored: 'Not yet refreshed', Other: 'Unrecognised'
  };

  /* THE LOCKOUT GUARD.
   *
   * This iterates CHARACTERS and selects a group for each one. It must
   * NEVER enumerate the readiness groups and pull matching characters out
   * of them -- the trailing OTHER bucket exists so that a readiness string
   * this page does not recognise still produces a row.
   *
   * That is not tidiness. The expanded row is the ONLY surface in the
   * whole application for forgetting a character or re-authenticating it,
   * so a character with no row is a character that cannot be repaired --
   * not from here, not from Settings, not from anywhere but deleting
   * eve_skills.json by hand.
   *
   * And the group most likely to be affected is the most common one:
   * "Unscored" is the state of EVERY character between authorisation and
   * its first successful refresh, and of every character whose first
   * refresh failed. A roster driven by enumerating known groups would
   * strand exactly the characters most likely to need repair -- the ones
   * that just failed to authenticate.
   */
  function buildRoster(chars) {
    var buckets = {};
    GROUPS.forEach(function (name) { buckets[name] = []; });
    buckets[OTHER] = [];

    chars.forEach(function (ch) {
      var key = GROUPS.indexOf(ch.readiness) === -1 ? OTHER : ch.readiness;
      buckets[key].push(ch);
    });

    var order = GROUPS.concat([OTHER]);
    var groups = [];
    order.forEach(function (name) {
      var rows = buckets[name];
      if (!rows.length) return;          // empty groups are omitted
      rows.sort(name === 'Missing' ? byMissingThenName : byName);
      groups.push({ name: name, rows: rows });
    });
    return groups;
  }

  function byName(a, b) {
    return (a.character_name || '').toLowerCase()
      .localeCompare((b.character_name || '').toLowerCase());
  }

  // Fewest missing first. This is the whole surviving remnant of
  // TriffView's "Train next" tab: the tab never shipped, but the ordering
  // it existed to provide did, as the sort inside this one group.
  function byMissingThenName(a, b) {
    if (a.missing_count !== b.missing_count) {
      return a.missing_count - b.missing_count;
    }
    return byName(a, b);
  }
```

- [ ] **Step 2: The status line and the ETA formatter.**

```js
  // The exact strings the design specifies, and the only place they are
  // composed. "Training -- timing unknown" is a real state, not a fallback:
  // a queued requirement with no finish date means EVE reported a paused
  // queue, and claiming an ETA from the rest would be a guess.
  function statusLine(ch) {
    if (ch.readiness === 'Ready') return 'Ready';
    if (ch.readiness === 'Training') {
      var eta = formatEta(ch.estimated_finish_utc);
      return (ch.queue_timing_unknown || !eta)
        ? 'Training — timing unknown' : 'Training — ' + eta;
    }
    if (ch.readiness === 'Locked') return 'Locked';
    if (ch.readiness === 'Missing') return 'Missing ' + ch.missing_count;
    if (ch.readiness === 'Unknown') return 'Unknown';
    if (ch.readiness === 'Unscored') return 'Unscored';
    // The catch-all's row shows the raw string rather than inventing a
    // label for a state this page has never heard of.
    return ch.readiness || 'Unrecognised';
  }

  // "2d 4h", "4h 20m", "12m". Two units at most: a plan finishing in
  // eleven days does not want its minutes.
  function formatEta(iso) {
    if (!iso) return '';
    var finish = Date.parse(iso);
    if (isNaN(finish)) return '';
    var mins = Math.round((finish - Date.now()) / 60000);
    // A finish date already in the past means the queue completed since
    // the snapshot was taken. "Due" is honest; a negative duration is not.
    if (mins <= 0) return 'due';
    var days = Math.floor(mins / 1440);
    var hours = Math.floor((mins % 1440) / 60);
    if (days) return days + 'd ' + hours + 'h';
    if (hours) return hours + 'h ' + (mins % 60) + 'm';
    return mins + 'm';
  }

  function formatFetched(iso) {
    if (!iso) return 'Never fetched';
    var when = new Date(iso);
    if (isNaN(when.getTime())) return 'Never fetched';
    // Local time, deliberately: the ISO string crosses the bridge in UTC
    // because that is what the state document stores, but the person
    // reading the row is not in UTC.
    return 'Last fetched ' + when.toLocaleString();
  }
```

- [ ] **Step 3: `renderRoster()`, the filter, and the empty states.**

```js
  function matching() {
    var needle = filterText.trim().toLowerCase();
    if (!needle) return characters();
    return characters().filter(function (ch) {
      return (ch.character_name || '').toLowerCase().indexOf(needle) !== -1;
    });
  }

  function renderRoster() {
    var host = WM.el('skills-roster');
    var empty = WM.el('skills-empty');
    host.textContent = '';
    empty.textContent = '';
    WM.el('skills-filter-clear').hidden = !filterText.trim();

    if (!characters().length) {
      empty.hidden = false;
      empty.textContent =
        'No characters yet. Add one from the actions on the left.';
      return;
    }
    if (!plans().length) {
      empty.hidden = false;
      empty.textContent = 'No local plans yet. Drop a .txt plan in the '
        + 'plans folder, then reload.';
      return;
    }

    var rows = matching();
    if (!rows.length) {
      // The clear action is already visible (it is shown whenever a filter
      // is active), so this line does not repeat it as a button.
      empty.hidden = false;
      empty.textContent = 'No characters match “'
        + filterText.trim() + '”.';
      return;
    }
    empty.hidden = true;

    buildRoster(rows).forEach(function (group) {
      host.appendChild(groupNode(group));
    });
  }

  function groupNode(group) {
    var block = WM.make('div', 'skills-group');
    var head = WM.make('div', 'skills-group-head');
    head.appendChild(WM.make('span', 'skills-key key-' + group.name));
    head.appendChild(WM.make('span', 'skills-group-name',
                             GROUP_LABEL[group.name] || group.name));
    head.appendChild(WM.make('span', 'skills-group-count',
                             String(group.rows.length)));
    block.appendChild(head);
    group.rows.forEach(function (ch) { block.appendChild(rowNode(ch)); });
    return block;
  }

  WM.el('skills-filter').addEventListener('input', function () {
    filterText = WM.el('skills-filter').value;
    renderRoster();
  });

  WM.el('skills-filter-clear').addEventListener('click', function () {
    WM.el('skills-filter').value = '';
    filterText = '';
    renderRoster();
  });
```

Verify in the browser: typing `o` narrows to the names containing it; the
Clear filter action appears only while the box has content; `DEV.skillsEmpty()`
shows the no-characters line.

- [ ] **Step 4: The collapsed row.**

```js
  function rowNode(ch) {
    var row = WM.make('div', 'skills-row');
    if (expanded[ch.character_id]) row.classList.add('open');

    var top = WM.make('button', 'skills-row-top');
    top.appendChild(WM.make('span', 'chev',
                            expanded[ch.character_id] ? '▾' : '▸'));
    top.appendChild(WM.make('span', 'skills-name', ch.character_name
                                                   || String(ch.character_id)));
    // EXCEPTION-ONLY, and this is the considered half of it: an earlier
    // draft carried a per-row "Current" label beside this one. In the
    // common case every row had one, which is noise -- a badge that is
    // always present tells you nothing. Stale is worth a badge precisely
    // because it is rare.
    if (ch.stale) {
      var badge = WM.make('span', 'badge-stale', 'Stale');
      badge.title = 'You are looking at the last data that fetched '
        + 'successfully. The most recent refresh failed.';
      top.appendChild(badge);
    }
    top.appendChild(WM.make('span', 'skills-status status-' + ch.readiness,
                            statusLine(ch)));
    top.addEventListener('click', function () { toggle(ch.character_id); });
    row.appendChild(top);

    if (expanded[ch.character_id]) row.appendChild(detailNode(ch));
    return row;
  }

  function toggle(id) {
    if (expanded[id]) {
      delete expanded[id];
      // Collapsing abandons a half-typed confirmation. Leaving it armed
      // would mean re-opening the row a minute later shows a Forget button
      // already primed to fire on one click.
      if (confirming === id) confirming = 0;
    } else {
      expanded[id] = true;
      requestDetail(id);
    }
    renderRoster();
  }
```

- [ ] **Step 5: Lazy detail requests, one per expansion, with a request id.**

```js
  /* Details are requested lazily -- one call per expansion, never a
   * prefetch. A forty-character roster asking for forty requirement lists
   * on entry would evaluate thirty-nine plans nobody opened.
   *
   * The request id is what makes the reply safe to render. A plan switch
   * clears `details` and `pendingDetail` while a call is in flight, and
   * that reply describes the OLD plan -- rendering it would put the wrong
   * requirement list under an open row, with nothing on screen to say so.
   * A cleared or superseded entry no longer matches, so the reply is
   * dropped.
   */
  function requestDetail(id) {
    if (details[id]) return;
    detailSeq += 1;
    var token = detailSeq;
    pendingDetail[id] = token;
    var plan = (STATE && STATE.selected_plan_name) || '';
    WM.send('skills_character_detail', id, plan).then(function (payload) {
      if (pendingDetail[id] !== token) return;
      delete pendingDetail[id];
      // A null is a bridge failure, not an answer (app.js:38-43). The row
      // must say something rather than sit on "Loading requirements…"
      // forever.
      details[id] = payload || {
        ok: false, message: 'The requirement list could not be loaded.',
        requirements: []
      };
      renderRoster();
    });
  }
```

- [ ] **Step 6: The expanded row.**

```js
  function detailNode(ch) {
    var box = WM.make('div', 'skills-detail');

    // The re-authenticate banner comes FIRST: it is the only action that
    // makes any of the rest of this row work again.
    if (ch.needs_reauth) {
      var banner = WM.make('div', 'reauth');
      banner.appendChild(WM.make(
        'span', '',
        'This character needs to sign in to EVE again. Its stored token was '
        + 'rejected and has been removed.'));
      var again = WM.make('button', 'btn', 'Re-authenticate');
      // The same call Add character makes. EVE's own flow is what decides
      // which character comes back, and re-authorising an existing one
      // updates it in place rather than adding a second row.
      again.disabled = !STATE.auth_configured || STATE.auth_in_progress;
      again.addEventListener('click', function () {
        WM.send('skills_add_character');
      });
      banner.appendChild(again);
      box.appendChild(banner);
    }

    if (ch.error) box.appendChild(WM.make('p', 'row-error', ch.error));
    box.appendChild(WM.make('p', 'row-fetched', formatFetched(ch.fetched_utc)));

    var detail = details[ch.character_id];
    if (!detail) {
      box.appendChild(WM.make('p', 'hint', 'Loading requirements…'));
    } else if (!detail.ok) {
      box.appendChild(WM.make('p', 'row-error',
                              detail.message || 'No requirements available.'));
    } else {
      box.appendChild(requirementsNode(detail));
    }

    box.appendChild(forgetNode(ch));
    return box;
  }

  var STATE_LABEL = {
    TrainedInactive: 'Trained, inactive', Queued: 'Queued',
    Missing: 'Missing', Unknown: 'Unknown skill'
  };

  function requirementsNode(detail) {
    var list = WM.make('div', 'req-list');
    // Active requirements are FILTERED OUT. This list answers "what does
    // it still need"; a requirement already met at the active level is not
    // outstanding, and on a nearly-ready character the met ones would bury
    // the two that are not.
    var outstanding = (detail.requirements || []).filter(function (req) {
      return req.state !== 'Active';
    });
    if (!outstanding.length) {
      list.appendChild(WM.make('p', 'hint',
                               'Nothing outstanding — every '
                               + 'requirement is trained and active.'));
      return list;
    }
    outstanding.forEach(function (req) {
      var line = WM.make('div', 'req');
      line.appendChild(WM.make('span', 'req-name',
                               req.skill_name + ' ' + roman(req.required_level)));
      var note = STATE_LABEL[req.state] || req.state;
      if (req.state === 'Queued') {
        var eta = req.queue_timing_unknown ? '' : formatEta(req.queued_finish_utc);
        note = eta ? 'Queued — ' + eta : 'Queued — timing unknown';
      }
      line.appendChild(WM.make('span', 'req-state state-' + req.state, note));
      list.appendChild(line);
    });
    return list;
  }

  // Plans are written in roman numerals and EVE shows skills that way, so
  // the requirement reads back in the notation it was authored in.
  function roman(level) {
    return ['', 'I', 'II', 'III', 'IV', 'V'][level] || String(level);
  }
```

- [ ] **Step 7: Forget, behind a two-step inline confirm.**

```js
  /* Two-step, and inline rather than window.confirm. Forget deletes the
   * character's stored refresh token along with its snapshot -- the whole
   * point of one document is that this is a single atomic write -- so
   * recovering from a misclick means a full SSO round trip through a
   * browser.
   *
   * Only one row can be armed at a time, which is why `confirming` holds
   * an id rather than a flag: arming a second row disarms the first.
   */
  function forgetNode(ch) {
    var foot = WM.make('div', 'forget-row');
    if (confirming !== ch.character_id) {
      var start = WM.make('button', 'linkbtn danger', 'Forget character');
      start.addEventListener('click', function () {
        confirming = ch.character_id;
        renderRoster();
      });
      foot.appendChild(start);
      return foot;
    }
    foot.appendChild(WM.make(
      'span', 'forget-warn',
      'Forget ' + (ch.character_name || 'this character')
      + '? You will have to sign in to EVE again to add it back.'));
    var yes = WM.make('button', 'btn danger', 'Forget');
    yes.addEventListener('click', function () {
      confirming = 0;
      // False is a real answer here, unlike the other mutations: it means
      // the character was already gone (contract: `True` / `False`). Either
      // way the push re-syncs the roster, so the row is dropped by the
      // render that follows rather than by this callback.
      WM.send('skills_forget_character', ch.character_id);
      delete expanded[ch.character_id];
      delete details[ch.character_id];
      delete pendingDetail[ch.character_id];
    });
    var no = WM.make('button', 'btn', 'Cancel');
    no.addEventListener('click', function () {
      confirming = 0;
      renderRoster();
    });
    foot.appendChild(yes);
    foot.appendChild(no);
    return foot;
  }
```

Verify in the browser: expand `Gustav Oswaldo`, confirm the Stale badge and
the `ESI returned 503` line; expand `Tavi Solen` and confirm the
re-authenticate banner sits above `Never fetched`; click Forget character and
confirm the row arms, then Cancel, then Forget — under `?dev=1` the mock
removes it and pushes `onSkills`.

- [ ] **Step 8: The CSS — a two-pane workspace.**

Append to `obs_youtube_uploader/web/style.css`, after the first-run route.
Everything below is built from Wingman's **existing** tokens — `--panel`,
`--ok`, `--warn`, `--err`, `--text-dim`, `--fs-muted`. **TriffView's `--tv-*`
variables do not come across**; there is no shared stylesheet and nothing
defines them here.

```css
/* ====================== skills route ================================
   NOT the .settings form the previews and bookmarks routes use: a fixed
   rail beside a scrolling roster. The rail is 214px and the main pane
   takes the rest -- min_size is (840, 625) (ui/window.py:44-45), which
   leaves 626 CSS pixels beside the rail at 100% scaling, and less on the
   scaled displays .evestat's media query already accounts for. minmax(0,
   1fr) rather than 1fr: a bare 1fr floors at min-content, and one long
   character name would push the roster wider than the window. */
#route-skills {
  display: none;
  grid-template-columns: 214px minmax(0, 1fr);
  gap: 12px; padding: 12px; min-height: 0;
}
#route-skills.active { display: grid; }

.skills-rail {
  display: flex; flex-direction: column; gap: 14px; min-height: 0;
  background: var(--panel); border: 1px solid var(--panel-border);
  border-radius: var(--radius); padding: 12px;
}
.rail-block { display: flex; flex-direction: column; gap: 6px; }
/* Only the plan list scrolls. Seven plans fit; the buttons below it must
   not be pushed off the bottom by the eighth. */
.rail-plans-block { flex: 1; min-height: 0; }
.rail-plans { overflow-y: auto; min-height: 0; }
.rail-head {
  font-size: var(--fs-label); letter-spacing: .14em; text-transform: uppercase;
  color: #8b93a1; font-weight: 600; margin-bottom: 6px;
}
.rail-count { color: var(--text-dim); font-size: var(--fs-muted); }
.skills-rail button.btn { width: 100%; text-align: center; }

.rail-plan {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: none; border: 0; border-left: 2px solid transparent;
  border-radius: var(--radius-sm); padding: 6px 8px;
  color: var(--text-dim); font: inherit; font-size: var(--fs-mono);
  cursor: pointer; text-align: left;
}
.rail-plan:hover { background: #22252c; color: var(--text); }
.rail-plan.active {
  background: #191d24; border-left-color: var(--brand); color: var(--text);
}
.rail-plan-name { flex: 1; min-width: 0;
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-ratio {
  flex: none; color: var(--text-faint); font-variant-numeric: tabular-nums;
}

.skills-main {
  display: flex; flex-direction: column; gap: 10px; min-width: 0; min-height: 0;
}
.skills-head { display: flex; align-items: baseline; gap: 10px; flex: none; }
.skills-plan-count { color: var(--text-faint); font-size: var(--fs-muted); }

/* Collapses when empty, so the roster sits directly under the heading on
   the common path. Author rules beat the UA stylesheet's
   [hidden]{display:none} regardless of specificity -- same trap
   .routenav[hidden] and .evestat[hidden] already document. */
.skills-notices {
  flex: none; display: flex; flex-direction: column; gap: 4px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  background: #101216; border: 1px solid var(--field-border);
}
.skills-notices[hidden] { display: none; }
.notice { color: var(--text-dim); font-size: var(--fs-muted); }

.skills-issues {
  flex: none; padding: 8px 10px; border-radius: var(--radius-sm);
  background: #101216; border: 1px solid var(--field-border);
}
.skills-issues[hidden] { display: none; }
.skills-issues summary {
  cursor: pointer; color: var(--warn); font-size: var(--fs-muted);
}
.issue-file { margin-top: 8px; color: var(--text); font-size: var(--fs-muted); }
.issue-message { color: var(--text-dim); font-size: var(--fs-muted); }
.issue-line {
  color: var(--text-faint); font-size: var(--fs-muted);
  font-family: var(--mono); margin-left: 10px;
}

.skills-filterbar { flex: none; display: flex; align-items: center; gap: 8px; }
.skills-filterbar .field { flex: 1; }

.skills-roster { flex: 1; min-height: 0; overflow-y: auto; }
.skills-group { margin-bottom: 12px; }
.skills-group-head {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 2px 6px;
  font-size: var(--fs-muted); color: var(--text-dim);
}
.skills-group-count {
  color: var(--text-faint); font-variant-numeric: tabular-nums;
}
/* The colour key. Every value is an existing token; this route introduces
   no new colour literals. */
.skills-key {
  width: 8px; height: 8px; border-radius: 2px; flex: none;
  background: currentColor;
}
.key-Ready { color: var(--ok); }
.key-Training { color: #7aa2f7; }
.key-Locked { color: var(--warn); }
.key-Missing { color: var(--err); }
.key-Unknown { color: var(--text-dim); }
.key-Unscored { color: var(--text-faint); }
/* The catch-all bucket. Brand-coloured on purpose: a readiness this page
   has never heard of is worth looking at, not worth hiding. */
.key-Other { color: var(--brand); }

.skills-row {
  border-bottom: 1px solid #191c22;
  border-left: 2px solid transparent;
}
.skills-row.open { background: #171a20; border-left-color: #2f3540; }
.skills-row-top {
  display: flex; align-items: center; gap: 9px; width: 100%;
  background: none; border: 0; padding: 7px 10px;
  color: var(--text); font: inherit; font-size: var(--fs-body);
  cursor: pointer; text-align: left;
}
.skills-row-top:hover { background: #171a20; }
.chev { width: 10px; flex: none; color: var(--text-faint); font-size: 9px; }
.skills-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.skills-status { flex: none; font-size: var(--fs-muted); color: var(--text-dim); }
.status-Ready { color: var(--ok); }
.status-Training { color: #7aa2f7; }
.status-Locked { color: var(--warn); }
.status-Missing { color: var(--err); }
.badge-stale {
  flex: none; padding: 1px 7px; border-radius: 999px;
  background: #101216; border: 1px solid var(--warn);
  color: var(--warn); font-size: 10px; letter-spacing: .04em;
}

.skills-detail {
  padding: 4px 10px 12px 29px;
  display: flex; flex-direction: column; gap: 8px;
}
.reauth {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  background: #101216; border: 1px solid var(--err);
  color: var(--text-dim); font-size: var(--fs-muted);
}
.row-error { color: var(--err); font-size: var(--fs-muted); user-select: text; }
.row-fetched { color: var(--text-faint); font-size: var(--fs-muted); }

.req-list { display: flex; flex-direction: column; gap: 3px; }
.req { display: flex; align-items: baseline; gap: 10px; }
.req-name { flex: 1; min-width: 0; font-size: var(--fs-muted); }
.req-state { flex: none; font-size: var(--fs-muted); color: var(--text-dim); }
.state-Missing { color: var(--err); }
.state-TrainedInactive { color: var(--warn); }
.state-Queued { color: #7aa2f7; }
.state-Unknown { color: var(--text-faint); }

.forget-row { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.forget-warn { flex: 1; color: var(--warn); font-size: var(--fs-muted); }
.linkbtn.danger { color: var(--err); }
.linkbtn.danger:hover { color: #fff; background: #d9291c; }
button.btn.danger { border-color: var(--err); color: var(--err); }
button.btn.danger:hover:not(:disabled) { background: #d9291c; color: #fff; }
```

One thing not to trip over while styling: `.check` inputs are
`opacity: 0` with a styled `.box` span as the visible control
(`style.css:404-415`, and `index.html:211-213` records what happened without
it — a bare checkbox rendered as a native white widget against the dark
card). This route uses no checkboxes today, but the next person adding one
here needs the `<input><span class="box"></span>` pair, not a bare input.

- [ ] **Step 9: Verify by running the app, and record the coverage gap.**

Two passes, both manual, because there is nothing else:

1. `obs_youtube_uploader/web/index.html?dev=1` in a browser. Confirm seven
   groups render in the order Ready, Training, Locked, Missing, Unknown,
   Unscored, Unrecognised; that `Nera Tal` (missing 2) sorts above
   `Gustav Oswaldo` (missing 6); that `Mira Halcyon` — readiness
   `"Ascendant"`, a string this page has never heard of — **has a row** in
   the brand-keyed catch-all group, and that expanding it still offers
   Forget character. That last check is the lockout guard, and it is the
   only way to see it work.
2. `python -m obs_youtube_uploader`, click Skills, and confirm the layout
   holds at the 840×625 minimum by dragging the window down to it.

Then write down, in the commit message and in `implementation-notes.md`, what
has no coverage: **`buildRoster()` and its two comparators are the piece here
most worth testing and the piece nothing tests.** The design doc already
concedes this at `triffskills-design.md:817-821` — TriffView's own roster has
no automated coverage and its design doc says *"the logic most likely to
regress here is the least protected."* The port improves on that for the
Python evaluator, which is fully tested, but not for this function, because
this repo has no JavaScript test harness and adding one is not in scope. The
honest statement is that the readiness *decision* is covered and the
readiness *presentation* is not.

- [ ] **Step 10: Commit.**

```
git add obs_youtube_uploader/web/skills.js obs_youtube_uploader/web/style.css
git commit -m "Render the skills roster, its in-row detail, and the two-pane layout"
```

---

### Task 18: Smoke checklist and final verification

**Files:**
- Modify: `docs/smoke-checklist.md` (append a new `## EVE skill plan readiness` section at the end of the file, after `## EVE client previews`)
- Test: `tests/test_packaging_completeness.py`, `tests/test_api.py`, `tests/test_no_tk.py` — all existing, all run as part of the final gate below.

**Interfaces:**
- Consumes: nothing at runtime. This task documents what the automated suite structurally cannot reach.
- Produces: the release gate for the whole feature.

---

- [ ] **Step 1: The smoke-checklist section.**

Append to `docs/smoke-checklist.md`. The framing sentence matters as much as
the items: this file opens by saying it is *"the only verification any of
that gets"* (`:11-12`), and the section has to say which parts of this feature
fall into that category and why.

```markdown
## EVE skill plan readiness

Requires a Windows machine, a real EVE account, and a registered EVE
application. Most of this subsystem IS covered by pytest — the parser, the
evaluator, the JWT verifier, the loopback parser, the ESI client, the state
normaliser and the skill-id cache all run headless on Linux in CI. What
follows is only what the suite structurally cannot reach: a live third-party
authorisation server, a browser, a Windows-only crypto API, and a frozen
bundle.

**Register the EVE application first.** Until someone creates it at
developers.eveonline.com, sets the redirect URI to
`http://127.0.0.1:51779/callback/`, requests the two read-only scopes, and
puts the client id in `obs_youtube_uploader/eveskills/application.py`, none
of the SSO items below can run at all — `Add character` is disabled and says
so. Every module below the auth stack is testable with stubs before that
happens, which is why the rest of the feature can be built and merged
against a placeholder id; only these items are blocked on the registration.

### The SSO round trip

- [ ] **LOAD-BEARING: a real authorisation completes against CCP.** Click
      `Add character`. Expected: the default browser opens EVE's own login
      page, the consent screen names exactly the two scopes
      (`esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`) and
      no others, and after approving, **the browser tab shows Wingman's own
      completion page** rather than a connection error or a raw JSON blob.
      The character appears in the roster as `Unscored`. Nothing in the
      suite can reach login.eveonline.com, so this is the only proof the
      PKCE challenge, the state comparison, the loopback listener and the
      code exchange all agree with the live server.
- [ ] **The window stays responsive for the whole five minutes.** Start an
      authorisation and do not complete it. Drag the window, switch routes,
      scroll the recording list. If any of that freezes, the loopback wait
      is running on the bridge thread rather than a worker.
- [ ] **Cancel sign-in actually cancels.** Start an authorisation, click
      `Cancel sign-in`, then complete the login in the browser anyway. No
      character is added, and starting a second authorisation works — a
      listener that did not release port 51779 makes the second attempt
      fail to bind.
- [ ] **A second authorisation while one is in flight is refused, not
      queued.** Two would fight over the fixed port.

### DPAPI, on Windows only

- [ ] **LOAD-BEARING: the refresh token survives a restart.** Add a
      character, quit Wingman fully (tray Quit, not just closing the
      window), relaunch, and click `Refresh characters`. It refreshes
      without asking you to sign in again. This is the DPAPI round trip:
      `dpapi.py` is the one module CI never executes, because it is
      `CryptProtectData` and CI is Linux.
- [ ] **A token another user cannot read costs one character, not the
      file.** Open `%LOCALAPPDATA%\OBSYouTubeUploader\eve_skills.json`,
      corrupt one character's `refresh_token_blob` (change a few base64
      characters), and relaunch. Expected: that character shows
      `needs_reauth` with a re-authenticate banner; **every other character
      is untouched and still refreshes.** This is what keeping the roster
      metadata in plaintext beside the wrapped token buys.

### A live refresh

- [ ] **An account with more than one character refreshes all of them.**
      Add at least three, click `Refresh characters`, and watch the notices
      strip count `Refreshed 1 of 3`, `2 of 3`, `3 of 3` as it goes. A
      counter that jumps straight to the total means progress is being
      pushed after the loop rather than per character.
- [ ] **A failure isolates.** Disconnect the network mid-refresh. Expected:
      the characters already fetched keep their data and show no error; the
      rest carry a per-character error and a `Stale` badge if they had
      previous data. Nothing shows a `Stale` badge that never fetched
      successfully.
- [ ] **Last-good data survives.** Reconnect, refresh again, and confirm the
      errors clear and the badges disappear.
- [ ] **The readiness verdict matches the game.** Pick one character and one
      plan and check three requirements against the in-game skill sheet: one
      it has active, one it is training, one it lacks. The evaluator's
      precedence is unit-tested; that the *inputs* are the right ESI fields
      is not.

### Forget and re-add

- [ ] **Forget is one write and it sticks.** Expand a character, use
      `Forget character`, confirm. The row disappears. Quit and relaunch:
      it is still gone, and no orphaned token remains — grep the state file
      for its character id and find nothing.
- [ ] **A forgotten character can be added back.** Re-authorise the same
      character. It returns as a single row, `Unscored`, not a duplicate.
- [ ] **Forget during a refresh stays forgotten.** Start a refresh over
      several characters and forget one while it is in flight. It must not
      reappear when the refresh commits.

### Corruption recovery

- [ ] **A truncated state file recovers from `.bak`.** With at least two
      characters authorised and at least two refreshes done (so a `.bak`
      exists), quit Wingman, truncate `eve_skills.json` to a few bytes, and
      relaunch. Expected: the roster comes back from
      `eve_skills.json.bak`, a warning appears in the notices strip, the
      damaged file is preserved as `eve_skills.json.corrupt-<timestamp>`,
      and **the characters still refresh** — meaning the wrapped tokens came
      back with them. If they all need re-authenticating, the backup tier
      is not covering the tokens and the whole reason it exists is missing.
- [ ] **A corrupt skill-id cache costs a re-resolve, not a failure.** Delete
      `eve_skills_cache.json` and refresh. It rebuilds from ESI; readiness
      is unchanged afterwards.

### Frozen build

- [ ] **LOAD-BEARING: the installed build serves `skills.js`.** Install the
      built artifact, launch it, and click Skills. The rail renders, the
      buttons respond, and the roster fills. CI asserts the file exists at
      `_internal\web\skills.js`; only launching proves the page fetched and
      executed it. A route whose static markup renders and whose every
      control is inert is exactly what a missing script looks like —
      PyInstaller exits 0 when a `datas` entry resolves to nothing, and
      pywebview reports no error for a script that 404s.
- [ ] **The frozen build reaches only CCP.** With previews and the uploader
      idle, the only hosts this feature contacts are `login.eveonline.com`
      and `esi.evetech.net`.
```

- [ ] **Step 2: The final verification gate.**

Run these in order and paste the real output. Do not claim any of them
passed without having run it — `pyproject.toml` declares no linter,
formatter, or type checker, so the suite plus the structural tests is the
entire automated gate this repo has.

```bash
python -m pytest tests/ -v
```

That is the gate CI runs. Then the three structural tests, named explicitly
because each one guards a failure that a source checkout cannot reproduce:

```bash
python -m pytest tests/test_packaging_completeness.py -v
```

Reads `pyproject.toml`'s `packages` and asserts every directory holding an
`__init__.py` is listed. `obs_youtube_uploader.eveskills` is a new
subpackage, and subpackages are **not** implied by their parent — omit it and
the checkout passes every test while the frozen release dies at import.

```bash
python -m pytest tests/test_api.py::test_api_exposes_no_public_non_method_attributes -v
```

`Api` gained nine façade methods and, if the wiring was done carelessly, a
public attribute holding the controller. pywebview builds its JS proxy by
walking the public attributes of the `js_api` object; a public non-method
attribute sends that walk into a native object and recurses until
`RecursionError` kills the process about eight seconds after launch, with a
traceback pointing nowhere near the cause. `tests/test_api.py:114` is that
lesson as an assertion. The controller must be `self._skills`.

```bash
python -m pytest tests/test_no_tk.py -v
```

Nothing in this feature should import `tkinter`, but the guard is cheap and
the failure — Tcl/Tk silently dragged into the bundle — is invisible in a
checkout.

Finally, confirm by eye that both workflows carry the same asset list, since
no test asserts the mirror:

```bash
grep -n 'skills.js' .github/workflows/build.yml .github/workflows/release.yml
```

Two hits, one per file. One hit means the release path is the weaker of the
two, which is the exact asymmetry `release.yml:209-220` exists to prevent.

- [ ] **Step 3: Commit.**

```
git add docs/smoke-checklist.md
git commit -m "Add the skill-readiness smoke items the suite cannot cover"
```
