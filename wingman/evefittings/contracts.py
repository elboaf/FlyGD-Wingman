"""Pinned ESI fitting contracts: scopes, paths, remote limits, and the
accepted-flag inventory, plus this application's own local refusal
boundaries.

Two different kinds of constant live here, and the distinction matters
enough to call out once rather than per-constant:

- Values pinned to CCP's compatibility-dated schema (scopes, paths, the
  50/500/512 character/item limits, the accepted flag enum). These are
  facts about ESI, not choices Wingman makes, and a compatibility-date
  bump that changes any of them must change this file deliberately rather
  than have the app discover a drift at runtime.
- Local bounds this application enforces on its own state and UI (library
  size, page size, operation record count, state file size). These are
  explicit refusal boundaries, not CCP limits: crossing one means Wingman
  declines to keep growing rather than silently degrading.
"""

from datetime import timedelta

# EVE SSO scopes. Fittings requests these as their own capability, never
# folded into Skills' scope set -- see eveauth's CAPABILITY_SCOPES (task
# 2), which keeps a missing fitting grant from ever looking like a missing
# skills grant or vice versa.
READ_SCOPE = "esi-fittings.read_fittings.v1"
WRITE_SCOPE = "esi-fittings.write_fittings.v1"

# Unversioned path templates, resolved through the X-Compatibility-Date
# header every request in this app already sends (see eveesi.py), not
# through a /vN/ path segment. `{character_id}` is a caller-filled
# placeholder, never handed to validate_path() until it is filled in with
# the real integer -- a literal "{character_id}" would fail path
# validation's [A-Za-z0-9_-]+ segment check, which is the point: nothing
# can reach the network with the placeholder still in it.
GET_PATH = "/characters/{character_id}/fittings"
POST_PATH = "/characters/{character_id}/fittings"

# ESI's create/read limits for a single fitting.
MAX_NAME_CHARS = 50
MAX_DESCRIPTION_CHARS = 500
MAX_CREATE_ITEMS = 512

# How long a successful GET's snapshot may be treated as current before a
# refresh is considered due. This is the same "prior five-minute cache
# horizon" the design doc's reconciliation rules refer to when deciding
# whether a 304 or a surviving in_flight intent can be resolved.
READ_CACHE_SECONDS = 300

# One fitting-copy operation is refused above this many creates rather
# than silently queued -- see the design doc's preflight section: "A
# larger selection is refused with instructions to split it into
# additional explicit batches; work is not queued invisibly."
MAX_COPY_WRITES = 20
PREFLIGHT_TICKET_SECONDS = 15 * 60
MAX_PREFLIGHT_TICKETS = 20

# --- Local refusal boundaries -------------------------------------------
# Not ESI limits: these bound what Wingman itself will hold in memory and
# on disk before it declines to grow further, independent of whatever CCP
# allows a character to store.
MAX_REMOTE_FITTINGS = 500
MAX_LIBRARY_ENTRIES = 10_000
MAX_COLLECTIONS = 200
MAX_COLLECTION_NAME_CHARS = 80
MAX_ALIASES_PER_ENTRY = 100
PAGE_SIZE = 100
MAX_OPERATION_RECORDS = 200
# Terminal copy results are diagnostic history, not safety state. Ninety
# days keeps recent support context while preventing the count cap from
# becoming the only retention policy on quiet installations. Unresolved
# intents are exempt from both limits.
COMPLETED_OPERATION_MAX_AGE = timedelta(days=90)
MAX_STATE_BYTES = 64 * 1024 * 1024

# --- Rack classes --------------------------------------------------------
# Numbered slots canonicalize to one of these; see the design doc's
# "Numbered slots normalize to rack classes" list. Bay-style locations
# (Cargo, DroneBay, FighterBay) and the schema-defined Invalid flag are
# deliberately NOT rack classes -- they stay exact, non-rack canonical
# content instead (see NON_RACK_FLAGS below).
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
RIG = "rig"
SUBSYSTEM = "subsystem"
SERVICE = "service"


def _numbered(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(f"{prefix}{i}" for i in range(count))


# Pinned from ESI's compatibility-dated OpenAPI schema for
# GET /characters/{character_id}/fittings/ items[].flag. Declared as a
# flat literal set first -- not derived from the rack groups below -- so
# that the exhaustiveness assertion at the bottom of this module is a real
# cross-check between "what ESI can send" and "how this app classifies
# it," rather than a tautology that would pass no matter which flags were
# forgotten from the rack groups.
ACCEPTED_FLAGS = frozenset(
    {
        "Cargo",
        "DroneBay",
        "FighterBay",
        *_numbered("HiSlot", 8),
        "Invalid",
        *_numbered("LoSlot", 8),
        *_numbered("MedSlot", 8),
        *_numbered("RigSlot", 3),
        *_numbered("ServiceSlot", 8),
        *_numbered("SubSystemSlot", 4),
    }
)

# Derived FROM the pinned inventory above, not hand-duplicated: each rack
# group is the exact numbered-slot span ESI defines for it, and
# RACK_BY_FLAG is built by inverting those groups rather than retyped
# per flag.
_RACK_GROUPS = {
    HIGH: _numbered("HiSlot", 8),
    MEDIUM: _numbered("MedSlot", 8),
    LOW: _numbered("LoSlot", 8),
    RIG: _numbered("RigSlot", 3),
    SUBSYSTEM: _numbered("SubSystemSlot", 4),
    SERVICE: _numbered("ServiceSlot", 8),
}

RACK_BY_FLAG: dict[str, str] = {
    flag: rack for rack, flags in _RACK_GROUPS.items() for flag in flags
}

# Flags that are accepted but never rack-mapped: bay-style locations that
# canonicalize exactly (see the design doc: "Cargo, DroneBay, and
# FighterBay remain distinct and quantity-sensitive"), and the
# schema-defined Invalid flag, which the design doc says is "retained as
# distinct canonical content rather than silently dropped."
NON_RACK_FLAGS = frozenset({"Cargo", "DroneBay", "FighterBay", "Invalid"})

_classified = set(RACK_BY_FLAG) | NON_RACK_FLAGS
# A pinned inventory is only as good as its own consistency. If a flag is
# ever added to ACCEPTED_FLAGS without a matching rack group or an entry
# in NON_RACK_FLAGS, canonicalization (task 7) would have nothing to do
# with it -- worse than rejecting an unknown flag outright, because it
# would look like an oversight rather than a schema-unknown remote flag.
# Asserted at import time, not only under a test runner, so a broken
# inventory fails the first import anywhere in the app.
assert _classified == ACCEPTED_FLAGS, (
    "ACCEPTED_FLAGS and the rack/non-rack classification have drifted: "
    f"unclassified={sorted(ACCEPTED_FLAGS - _classified)} "
    f"classified_but_not_accepted={sorted(_classified - ACCEPTED_FLAGS)}"
)
