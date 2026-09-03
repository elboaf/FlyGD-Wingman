"""Skill name -> type id, resolved over ESI and cached on disk.

There is no bundled SDE. Names become type ids in three steps -- a batch
POST to universe/ids, a per-type lookup for its group, and a per-group
lookup for its category -- and only category 16 (Skill) enters the cache.

The cache never invalidates. EVE type ids do not change, so re-checking
would spend requests to learn nothing; the honest cost is that a name
resolved wrongly stays wrong until the file is deleted.

Ground truth: TriffSkills/SkillIdCache.cs and the resolve flow in
TriffSkillsController.cs (~503-615).
"""

import concurrent.futures
import contextlib
import json
import math
import os
import stat as stat_module
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .. import atomicio
from .training import ATTRIBUTE_NAMES, SkillTrainingMetadata

SKILL_CATEGORY_ID = 16
BATCH_SIZE = 500
MAX_ENTRIES = 20_000
CACHE_VERSION = 1
RESOLVE_WORKERS = 4

# A separate sub-version for the OPTIONAL training-metadata payload beside
# each id entry. CACHE_VERSION never changes for this feature -- an
# existing id-only file must keep loading exactly as before -- so an old
# file simply lacks (or fails to match) this key, and every id in it is
# still accepted; only the metadata half is treated as absent.
TRAINING_METADATA_VERSION = 1

# Metadata is not re-fetched forever: rank and the two trained attributes
# are effectively immutable ESI facts, but nothing else in this cache ever
# revisits an accepted answer, so a fixed staleness horizon is what makes a
# hand-edited or years-old value eventually get refreshed at all.
METADATA_MAX_AGE = timedelta(days=30)

# Documented ESI dogma attribute ids read off a type's own
# /v3/universe/types/{id}/ response. 275 is the skill's rank
# (skillTimeConstant). 180 and 181 are themselves REFERENCES to one of the
# five attribute ids below -- not that attribute's own dogma value -- which
# is why decoding them is a second lookup through ATTRIBUTE_ID_TO_NAME.
DOGMA_PRIMARY_ATTRIBUTE = 180
DOGMA_SECONDARY_ATTRIBUTE = 181
DOGMA_SKILL_TIME_CONSTANT = 275
ATTRIBUTE_ID_TO_NAME = {
    164: "charisma",
    165: "intelligence",
    166: "memory",
    167: "perception",
    168: "willpower",
}

# SkillIdCache.cs's MaxCacheFileBytes, read via ReadBoundedText before
# either the primary or the backup document is ever decoded. Same shape as
# state.py's MAX_STATE_FILE_BYTES / planstore.py's MAX_PLAN_FILE_BYTES: a
# size check against the file on disk, before its bytes are pulled into
# memory, so a multi-megabyte cache.json (bug or hand edit) cannot cost
# more than a stat() call.
MAX_CACHE_FILE_BYTES = 4 * 1024 * 1024

# Exact strings: the UI shows them verbatim next to the requirement they
# explain, and the tests pin them.
REASON_NOT_RESOLVED = "Name was not resolved by ESI."
REASON_NO_GROUP = "Resolved type had no valid group."
REASON_NOT_A_SKILL = "Resolved inventory type is not in EVE's skill category."
# Mandatory correction 3. The brief originally gave a request that FAILED
# (a plain outage while confirming a type's group or a group's category)
# the identical reason as a request that SUCCEEDED and definitively said
# "no group" / "not category 16". Both retry on the next resolve pass
# regardless -- nothing permanent happens either way -- but they are
# different facts, and a user reading the plan-issues rollup cannot tell
# "ESI was down just now" from "this genuinely is not a skill" unless the
# strings say so.
REASON_ESI_UNAVAILABLE = (
    "Could not confirm this skill with ESI; it will "
    "be retried on the next resolve pass."
)

# Distinct from the four reasons above: those explain why a NAME never
# became a type id. This explains why a type id the cache already trusts
# still has no rank/attribute metadata to estimate training time with --
# a different failure, on an id already known to be a real skill.
REASON_METADATA_UNAVAILABLE = "Could not load training metadata from ESI."


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
    def __init__(self, mapping: "Mapping[str, int] | None" = None) -> None:
        self._by_key: dict = {}
        # Type id -> SkillTrainingMetadata. Keyed by type id, not by the
        # folded name key _by_key uses: a fetch resolves one type id, and
        # two names sharing that id (a duplicate plan entry, differing
        # only in case) must share one metadata record, not each hold
        # their own copy that could later disagree.
        self._metadata: dict = {}
        if mapping:
            self.merge(mapping)

    def get(self, name: str) -> "int | None":
        return self._by_key.get(_key(name))

    def type_ids(self) -> dict:
        # Folded keys, which is what "case-insensitive mapping" means to the
        # evaluator: it lowercases its lookups against exactly this dict.
        return dict(self._by_key)

    def unresolved(self, names: Iterable[str]) -> list:
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

    def merge(self, entries: Mapping[str, int]) -> int:
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

    def training_metadata(self, now: datetime) -> dict:
        """Type id -> SkillTrainingMetadata for records still fresh at *now*.

        A record that has never been fetched is simply absent from here --
        the same shape as a stale one, from a caller's point of view. Both
        mean "nothing usable to estimate with right now"; metadata_due()
        below is what tells the two apart for the purpose of deciding what
        to fetch next.
        """
        return {
            type_id: meta
            for type_id, meta in self._metadata.items()
            if now - meta.fetched_utc < METADATA_MAX_AGE
        }

    def metadata_due(self, names: Iterable[str], now: datetime) -> tuple:
        """(name, type_id) pairs among *names* whose metadata is missing or
        at least METADATA_MAX_AGE old, deduplicated by type id.

        A name with no id yet is not "due" -- there is nothing to request
        metadata FOR until resolve() gives it one, and that is a separate
        pass. Deduplication matters for the identical reason unresolved()
        dedupes: two plan entries that differ only by case share one type
        id, and would otherwise spend two requests to learn the same
        answer twice.
        """
        fresh = self.training_metadata(now)
        seen: set = set()
        due: list = []
        for name in names:
            type_id = self.get(name)
            if type_id is None or type_id in seen:
                continue
            seen.add(type_id)
            if type_id not in fresh:
                due.append((name, type_id))
        return tuple(due)

    def merge_metadata(self, entries: Mapping) -> int:
        """Store *entries* (type id -> SkillTrainingMetadata), returning the
        count stored.

        Unlike merge() for ids, this OVERWRITES an existing record. The
        whole point of metadata_due()/METADATA_MAX_AGE is that a record can
        go stale and need replacing -- refusing to overwrite here would
        make expiry a dead letter, forever re-fetching the same stale
        answer.

        A type id the cache does not already hold an id for is refused: it
        is not this method's job to invent a skill the id-resolution half
        of the cache has never seen, and accepting one would let staged
        fetch results for an id that was since evicted (never happens
        today, since ids never invalidate, but the check costs nothing and
        keeps the invariant explicit) silently reappear.
        """
        valid_ids = set(self._by_key.values())
        added = 0
        for type_id, meta in entries.items():
            if isinstance(type_id, bool) or not isinstance(type_id, int):
                continue
            if type_id not in valid_ids:
                continue
            if not isinstance(meta, SkillTrainingMetadata):
                continue
            self._metadata[type_id] = meta
            added += 1
        return added


def _read_bounded(path: Path) -> str:
    """Read *path* as UTF-8 text, refusing anything over MAX_CACHE_FILE_BYTES.

    Sized BEFORE the bytes are read into memory -- mandatory correction 1,
    ported from SkillIdCache.cs's MaxCacheFileBytes check via
    ReadBoundedText, and the same shape state.py's own _read_bounded /
    planstore.py's size check already use in this package.
    """
    if path.stat().st_size > MAX_CACHE_FILE_BYTES:
        raise ValueError(
            f"{path.name} exceeds the "
            f"{MAX_CACHE_FILE_BYTES // (1024 * 1024)} MiB limit."
        )
    return path.read_text(encoding="utf-8")


def _preserve_corrupt(path: Path) -> str:
    """Move an unreadable document aside, returning its new name or "".

    Copied whole from state.py's _preserve_corrupt: moved, not left in
    place (else it is re-read, re-preserved and re-warned on every launch),
    millisecond-resolution stamp plus a numeric suffix fallback so two
    corruptions in the same wall-clock second cannot overwrite each other.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    suffix = 0
    while target.exists():
        suffix += 1
        target = path.with_name(f"{path.name}.corrupt-{stamp}-{suffix}")
    try:
        os.replace(path, target)
    except OSError:
        return ""
    return target.name


def _cache_from_raw(raw) -> "SkillIdCache | None":
    """Build a cache from a parsed JSON document, or None if the document
    itself is not a recognisable shape.

    None here means "route this through backup recovery", mirroring
    SkillIdCache.cs's FromJson(): it throws JsonException for a wrong
    top-level type, a version mismatch, OR an entries collection of the
    wrong type -- and Load() catches JsonException in the SAME clause that
    preserves the primary and tries `.bak`. A version mismatch is not a
    special "start empty" case in the source; it is just one more way
    FromJson can throw, so it gets the same recovery attempt as a JSON
    syntax error. Individual malformed ENTRIES inside an otherwise valid
    document are a different thing entirely -- FromJson's per-pair
    `continue` never throws, so those are dropped one at a time below,
    never treated as file-level corruption.
    """
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        return None
    entries = raw.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return None

    # A separate gate from CACHE_VERSION above: an id-only file from before
    # this feature existed simply lacks this key (or an old writer never
    # set it), and every id in it must still load exactly as it always
    # has. Metadata is the only thing this flag can discard -- it never
    # turns an otherwise-valid document into recovery-worthy corruption.
    metadata_ok = raw.get("training_metadata_version") == TRAINING_METADATA_VERSION

    accepted: dict = {}
    metadata: dict = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        # The key must be PRESENT and equal to 16. A .get with a default of
        # SKILL_CATEGORY_ID here would reproduce exactly the TriffView
        # constructor-default bug this port diverges from (ValidatedSkillType
        # defaults CategoryId to 16, so an entry omitting it deserialised to
        # 16 and passed its own validation).
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
        if metadata_ok:
            meta = _training_from_serialized(item.get("training"))
            if meta is not None:
                metadata[type_id] = meta

    cache = SkillIdCache()
    cache.merge(accepted)
    # merge_metadata(), not a direct _metadata update: it enforces the same
    # known-id invariant merge() enforces above. A duplicate case-folded
    # name (e.g. "Gunnery" and "gunnery" with different type ids) or a
    # MAX_ENTRIES cap rejection can leave *metadata* holding an entry for a
    # type id merge() never actually accepted into _by_key -- publishing
    # that entry unchecked would let this cache answer training_metadata()
    # for an id it does not otherwise know about.
    cache.merge_metadata(metadata)
    return cache


def _parse_fetched_utc(raw):
    """Parse a serialized "fetched_utc" string to an aware UTC datetime, or
    None if it is not one.

    Mirrors state.py's _parse_utc: a naive value can only be a hand edit --
    this cache never writes one -- and is read as UTC rather than local,
    matching everything else this package persists.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _training_from_serialized(data) -> "SkillTrainingMetadata | None":
    """Decode one entry's "training" sub-object from disk, or None if any
    field is malformed.

    Malformed metadata drops only that entry's metadata, never its type id
    -- matching _cache_from_raw's own per-entry handling of a bad id above.
    An entry with no "training" key at all (item.get returns None) takes
    the same None branch as a genuinely malformed one; both mean the same
    thing here, "nothing usable was persisted."
    """
    if not isinstance(data, dict):
        return None
    rank = data.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
        return None
    primary = data.get("primary_attribute")
    secondary = data.get("secondary_attribute")
    if (
        not isinstance(primary, str)
        or not isinstance(secondary, str)
        or primary not in ATTRIBUTE_NAMES
        or secondary not in ATTRIBUTE_NAMES
    ):
        return None
    fetched_utc = _parse_fetched_utc(data.get("fetched_utc"))
    if fetched_utc is None:
        return None
    return SkillTrainingMetadata(rank, primary, secondary, fetched_utc)


def _training_metadata_from_type(data, fetched_utc) -> "SkillTrainingMetadata | None":
    """Decode ESI's /v3/universe/types/{id}/ response into rank plus the
    two attributes it trains against, or None if anything here cannot be
    trusted.

    The three dogma attribute ids read (275/180/181) are documented ESI
    values: 275 is rank (skillTimeConstant). 180 and 181 are each
    themselves a REFERENCE to one of the five attribute ids -- not that
    attribute's own dogma value -- which is why ATTRIBUTE_ID_TO_NAME turns
    each into the name training.py's calculator validates against.

    Returns None rather than raising for anything malformed, INCLUDING a
    *fetched_utc* that is not an aware UTC datetime: fetch_training_metadata
    below calls this once per type inside a worker thread, and one type
    failing to decode must cost only that type's metadata, never the whole
    staged fetch.
    """
    if not isinstance(fetched_utc, datetime) or fetched_utc.tzinfo is None:
        return None
    if not isinstance(data, dict):
        return None
    attrs = data.get("dogma_attributes")
    if not isinstance(attrs, list):
        return None

    values: dict = {}
    for item in attrs:
        if not isinstance(item, dict):
            continue
        attribute_id = item.get("attribute_id")
        if isinstance(attribute_id, bool) or not isinstance(attribute_id, int):
            continue
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        # json.loads accepts NaN, Infinity and -Infinity by default, so a
        # malformed body really can put one here -- and every check below
        # converts with int(), which RAISES on those three (ValueError for
        # a NaN, OverflowError for an infinity) instead of comparing
        # False. That raise leaves _fetch, unwinds future.result(), and
        # costs the WHOLE staged pass its answers rather than this one
        # type its metadata. Dropping the value here is what keeps the
        # damage local: the id simply reads as absent below, so this
        # function returns None like any other malformed type.
        #
        # Only floats are screened. math.isfinite() converts its argument
        # to a float first, so passing a huge int would raise the very
        # OverflowError this is here to avoid, and an int is finite by
        # construction anyway.
        if isinstance(value, float) and not math.isfinite(value):
            continue
        values[attribute_id] = value

    rank_value = values.get(DOGMA_SKILL_TIME_CONSTANT)
    if (
        not isinstance(rank_value, (int, float))
        or rank_value <= 0
        or rank_value != int(rank_value)
    ):
        return None

    primary_ref = values.get(DOGMA_PRIMARY_ATTRIBUTE)
    secondary_ref = values.get(DOGMA_SECONDARY_ATTRIBUTE)
    if not isinstance(primary_ref, (int, float)) or not isinstance(
        secondary_ref, (int, float)
    ):
        return None
    if primary_ref != int(primary_ref) or secondary_ref != int(secondary_ref):
        return None

    primary_name = ATTRIBUTE_ID_TO_NAME.get(int(primary_ref))
    secondary_name = ATTRIBUTE_ID_TO_NAME.get(int(secondary_ref))
    if primary_name is None or secondary_name is None:
        return None

    return SkillTrainingMetadata(
        int(rank_value), primary_name, secondary_name, fetched_utc
    )


def fetch_training_metadata(
    requests: "Iterable[tuple[str, int]]",
    client,
    fetched_utc,
    *,
    max_workers: int = RESOLVE_WORKERS,
) -> tuple:
    """Fetch training metadata for *requests* ((name, type_id) pairs),
    returning (accepted, failures) -- staged results that never touch a
    SkillIdCache.

    Staged, not merged, on purpose: a caller merges the COMPLETE result
    under one lock hold once the whole staged fetch has finished, so a
    plan's readiness view never observes half a fetch's answers. One
    malformed or failed type affects only that type's entry in *failures*;
    the calculator suppresses just the estimate that needed it.

    Deduplicated by type id: two requests naming the same id (a duplicate
    plan entry differing only by case, or a caller that did not already
    dedupe via metadata_due()) cost one request, not two.
    """
    accepted: dict = {}
    failures: dict = {}

    pending: dict = {}
    for name, type_id in requests:
        if type_id in pending:
            continue
        pending[type_id] = name

    if not pending:
        return accepted, failures

    def _fetch(type_id: int, name: str) -> tuple:
        response = client.get(f"/v3/universe/types/{type_id}/")
        if not response.ok:
            return name, type_id, None
        return name, type_id, _training_metadata_from_type(response.data, fetched_utc)

    # Concurrency bound matches resolve()'s own ThreadPoolExecutor: charged
    # against the same shared ESI error-limit budget.
    workers = max(1, min(max_workers, len(pending)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_fetch, type_id, name) for type_id, name in pending.items()
        ]
        for future in concurrent.futures.as_completed(futures):
            name, type_id, meta = future.result()
            if meta is None:
                failures[name] = REASON_METADATA_UNAVAILABLE
            else:
                accepted[type_id] = meta

    return accepted, failures


def _serialize_entry(name: str, type_id: int, meta) -> dict:
    """One disk entry: the id fields always, a "training" sub-object only
    when *meta* is present. Freshness is not checked here -- training_
    metadata(now) filters by age at READ time, so even a record that has
    gone stale since it was fetched is still worth writing; discarding it
    here would turn a merely-stale record into a lost one on the very next
    save.
    """
    entry = {"name": name, "type_id": type_id, "category_id": SKILL_CATEGORY_ID}
    if meta is not None:
        entry["training"] = {
            "rank": meta.rank,
            "primary_attribute": meta.primary_attribute,
            "secondary_attribute": meta.secondary_attribute,
            "fetched_utc": meta.fetched_utc.astimezone(UTC).isoformat(),
        }
    return entry


def save(cache: SkillIdCache, path: Path) -> None:
    """Write the cache atomically, keeping one previous copy in `.bak`.

    Mandatory correction 2. The brief dropped this tier on the reasoning
    that the file "holds nothing that cannot be rebuilt" -- true, and
    beside the point: rebuilding a POPULATED cache means re-resolving every
    cached name through rate-limited ESI at up to three requests per name,
    so a real cache is hundreds of requests against the shared error-limit
    budget, spent to recover data that was sitting intact in a backup.

    Write-then-rotate, not rotate-then-write, matching state.py's save():
    the new content is written to a staging file and confirmed durable
    BEFORE anything happens to the existing primary or its .bak. The old
    shape copied the current primary to .bak first and only then wrote the
    new content -- so a primary that was itself corrupt (exactly the case
    _recover_from_backup calls this from) got copied over a good .bak an
    instant before the new write was known to succeed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_name(path.name + ".bak")
    staging = path.with_name(path.name + ".new")

    document = {
        "version": CACHE_VERSION,
        "training_metadata_version": TRAINING_METADATA_VERSION,
        # category_id is written on every entry so the load-time check has
        # something real to require. It is constant today; writing it is
        # what makes the requirement honest rather than tautological.
        "entries": [
            _serialize_entry(name, type_id, cache._metadata.get(type_id))
            for name, type_id in sorted(cache.type_ids().items())
        ],
    }
    # Written and confirmed durable first -- only once this succeeds is the
    # existing primary touched at all.
    atomicio.write_atomic(staging, json.dumps(document, indent=2))
    if path.exists():
        # Rename, not copy: os.replace carries the source file's own
        # mode across unchanged, matching what shutil.copy2 gave the
        # old copy-then-write shape -- and it only runs now, after the
        # new content is already safely on disk at *staging*, so a
        # primary that was itself corrupt never gets a chance to
        # overwrite a good .bak with more corruption.
        #
        # A backup that cannot be made must not stop the save. Losing
        # the tier is strictly better than losing the write it protects.
        with contextlib.suppress(OSError):
            os.replace(path, bak)
    # Bounded retry, mirroring atomicio.write_atomic's own retry on this
    # exact rename: a Windows MoveFileExW sharing violation from a reader
    # that does not grant FILE_SHARE_DELETE is transient, so a short wait
    # clears it. This is defence in depth, not a substitute for load()'s
    # own recovery above -- if every attempt here is exhausted, the primary
    # has already been rotated into *bak* and this raises, but the next
    # load() finds `.bak` and recovers from it instead of taking the
    # silent first-launch branch.
    for attempt in range(5):
        try:
            os.replace(staging, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))

    if bak.exists():
        # write_atomic's temp file is always created at 0600 and
        # carries that mode across on replace, so *path* is 0600
        # regardless of what mode the document it just replaced had.
        # Align .bak to match: without this, a document that predates
        # this cache ever touching it leaves a laxer-permission backup
        # sitting beside the hardened primary it just replaced.
        #
        # This chmod is a no-op on Windows -- os.chmod there only ever
        # toggles the read-only attribute, never real permission bits.
        # It costs nothing to still call it, but the actual protection
        # for files under %LOCALAPPDATA% on Windows is the directory's
        # own ACL, not these mode bits (this cache holds no secret, so
        # it needs nothing beyond that).
        with contextlib.suppress(OSError):
            os.chmod(bak, stat_module.S_IMODE(path.stat().st_mode))


def load(path: Path) -> tuple:
    """Read the cache. Returns (cache, warnings) and never raises."""
    path = Path(path)
    warnings: list = []
    try:
        text = _read_bounded(path)
    except FileNotFoundError:
        # No primary. Usually first launch -- but save()'s rotate-then-swap
        # can also leave exactly this on disk if the process dies or the
        # final os.replace(staging, path) fails between rotating the old
        # primary into *.bak* and installing the new one: a *.bak* with no
        # primary. A *.bak* on disk is the one thing that tells the two
        # apart -- first launch never has one -- so its absence is what
        # makes this branch safe to treat as silent.
        backup = path.with_name(path.name + ".bak")
        if not backup.exists():
            return SkillIdCache(), warnings
        return _recover_missing_primary(path, backup, warnings)
    except OSError as exc:
        # A genuine access failure rather than bad content. There is
        # nothing to preserve or recover here: if the file cannot even be
        # opened, neither can its .bak sibling for the same reason.
        warnings.append(
            f"{path.name} could not be read ({exc.strerror}); "
            "skill names will be resolved again."
        )
        return SkillIdCache(), warnings
    except ValueError:
        # _read_bounded's own size-cap check -- corrupt-content territory,
        # exactly like a JSON syntax error, so it gets the same recovery
        # attempt rather than a plain "unreadable" warning.
        return _recover_from_backup(path, warnings)

    try:
        raw = json.loads(text)
    except ValueError:
        return _recover_from_backup(path, warnings)

    cache = _cache_from_raw(raw)
    if cache is None:
        return _recover_from_backup(path, warnings)
    return cache, warnings


def _recover_missing_primary(path: Path, backup: Path, warnings: list) -> tuple:
    """The primary is gone but `.bak` is not: rebuild from it and restore
    the primary, then warn.

    Mirrors state.py's function of the same name. It exists because
    save()'s rotate-then-swap has no rollback: it renames the old primary
    to `.bak` and only then renames the new content into place, and a
    failure or a hard kill between those two renames leaves a `.bak` and a
    `.new` staging file but no primary. Without this, the next load() would
    take the FileNotFoundError branch, believe it is a first launch, and
    hand back an empty cache -- discarding every name this cache holds and
    paying for a full re-resolve (up to three rate-limited ESI requests per
    name) even though the `.bak` sitting right beside it is intact.
    """
    recovered = None
    for attempt in range(2):
        try:
            recovered = _cache_from_raw(json.loads(_read_bounded(backup)))
            break
        except ValueError:
            # Bad backup content -- permanent, retrying reads the same
            # bytes again.
            break
        except OSError:
            # A transient sharing violation on a GOOD backup, not a missing
            # or genuinely unreadable one -- matching _recover_from_backup's
            # own retry for the identical reason.
            if attempt == 0:
                time.sleep(0.05)

    if recovered is None:
        warnings.append(
            f"{path.name} was missing and its backup ({backup.name}) could "
            "not be read either; skill names will be resolved again."
        )
        return SkillIdCache(), warnings

    # Write the recovered document back to *path* immediately. save() sees
    # no existing primary (there isn't one) so it will not touch `.bak` --
    # it only rotates a primary that exists -- and the directory ends up
    # holding a real primary again, backed by the same `.bak` it came from.
    try:
        save(recovered, path)
    except OSError as exc:
        warnings.append(
            f"{path.name} was missing; recovered it from {backup.name}, but "
            f"the recovery could not be saved back to disk ({exc}). If the "
            "app closes before the next successful save, this recovery "
            "will be lost."
        )
        return recovered, warnings

    warnings.append(
        f"{path.name} was missing (likely an interrupted save) and was "
        f"recovered from its backup, {backup.name}."
    )
    return recovered, warnings


def _recover_from_backup(path: Path, warnings: list) -> tuple:
    """The corrupt-content path shared by every unreadable-CONTENT case in
    load(): move the bad primary aside, then try to rebuild from `.bak`.

    Mandatory correction 2, shape ported from state.py's
    _recover_from_backup. Split out because a JSON syntax error, a
    size-cap overflow, and an unrecognised document shape (wrong version,
    wrong top-level type) all mean exactly the same thing here: none of
    them is a document this cache can trust, and a good `.bak` is worth
    trying before giving up and paying for a full re-resolve.
    """
    preserved = _preserve_corrupt(path)
    backup = path.with_name(path.name + ".bak")
    recovered = None
    for attempt in range(2):
        try:
            recovered = _cache_from_raw(json.loads(_read_bounded(backup)))
            break
        except ValueError:
            # Bad backup content -- permanent, retrying reads the same
            # bytes again.
            break
        except OSError:
            # A transient sharing violation on a GOOD backup must not be
            # treated the same as a missing or genuinely unreadable one --
            # matching state.py's own retry for the identical reason.
            if attempt == 0:
                time.sleep(0.05)

    if recovered is None:
        warnings.append(
            f"{path.name} could not be read and was preserved as "
            f"{preserved or 'a copy'}; skill names will be resolved again."
        )
        return SkillIdCache(), warnings

    if not preserved:
        # _preserve_corrupt's own os.replace failed, so the corrupt content
        # is STILL sitting at *path*. Calling save() here regardless would
        # still see that corrupt file as the current primary and rotate it
        # into *backup* as save()'s own second step, overwriting the good
        # backup `recovered` just came from with the corrupt content it was
        # recovering FROM. The corrupt primary on disk is by definition
        # worse than the good backup, so the safest thing is to do nothing
        # to either file: hand back the recovered cache in memory.
        warnings.append(
            f"Recovered {path.name} from backup after the main file could "
            "not be read, but the corrupt file could not be moved aside "
            "and was left in place; the recovery could not be saved back "
            "to disk."
        )
        return recovered, warnings

    # Re-persisted immediately, mirroring state.py: _preserve_corrupt has
    # already moved the corrupt primary out of the way, so at this instant
    # there is no primary file at all. If the process exits before the
    # next save(), the next load() finds nothing at *path* and silently
    # starts empty with no explanation. Re-saving here closes that window.
    try:
        save(recovered, path)
    except OSError as exc:
        warnings.append(
            f"Recovered {path.name} from backup after the main file could "
            f"not be read, but the recovery could not be saved back to "
            f"disk ({exc}); it was preserved as {preserved or 'a copy'}."
        )
        return recovered, warnings

    warnings.append(
        f"Recovered {path.name} from backup after the main file could not "
        f"be read; it was preserved as {preserved or 'a copy'}."
    )
    return recovered, warnings


# group id -> (category id or None, request failed) memoised for the
# PROCESS lifetime rather than per call. A group's category is immutable
# in EVE, and every skill in a plan set shares a handful of groups --
# without this a 300-requirement resolve spends 300 identical requests
# against the same error-limit budget the sequential refresh loop is
# trying to protect. Not persisted: it is cheap to rebuild, and only the
# accepted name -> id result is worth a file. A failed lookup is memoised
# too (correction 3's request_failed flag survives the memo) -- retrying it
# inside one resolve would multiply a single outage by the number of
# skills sharing that group, and the requirement retries on the next pass
# regardless of which shape of failure this was.
_GROUP_CATEGORIES: dict = {}
_GROUP_LOCK = threading.Lock()


def _category_for_group(group_id: int, client) -> tuple:
    """(category_id or None, request_failed) for *group_id*."""
    with _GROUP_LOCK:
        if group_id in _GROUP_CATEGORIES:
            return _GROUP_CATEGORIES[group_id]
    # The request happens OUTSIDE the lock: holding it across HTTP would
    # serialise the fan-out down to one worker, which is the opposite of
    # what the ThreadPoolExecutor is for. The cost is that two workers can
    # race the same group once; the setdefault below makes that harmless.
    response = client.get(f"/v1/universe/groups/{group_id}/")
    if not response.ok:
        # Mandatory correction 3: the request itself failing (a 5xx, a
        # timeout) is a transient fact about ESI right now, not a
        # statement that this group has no category. Keeping it distinct
        # from the "responded, but no usable category_id" case below is
        # the whole point of the request_failed flag.
        result = (None, True)
    else:
        category = None
        if isinstance(response.data, dict):
            value = response.data.get("category_id")
            if isinstance(value, int) and not isinstance(value, bool):
                category = value
        result = (category, False)
    with _GROUP_LOCK:
        _GROUP_CATEGORIES.setdefault(group_id, result)
        return _GROUP_CATEGORIES[group_id]


def _classify(name: str, type_id: int, client) -> tuple:
    """Return (name, type_id or None, failure reason or "")."""
    response = client.get(f"/v3/universe/types/{type_id}/")
    if not response.ok:
        # Mandatory correction 3: distinct from REASON_NO_GROUP below.
        # ESI failing to answer this request is not the same fact as ESI
        # answering "this type has no group" -- the former is transient,
        # the latter is (as far as this pass can tell) a real property of
        # the resolved type. Both retry on the next resolve pass; only the
        # string a user reads differs.
        return name, None, REASON_ESI_UNAVAILABLE
    if not isinstance(response.data, dict):
        return name, None, REASON_NO_GROUP
    group_id = response.data.get("group_id")
    if isinstance(group_id, bool) or not isinstance(group_id, int) or group_id <= 0:
        return name, None, REASON_NO_GROUP
    category, request_failed = _category_for_group(group_id, client)
    if request_failed:
        return name, None, REASON_ESI_UNAVAILABLE
    if category != SKILL_CATEGORY_ID:
        # A ship or module name in a plan file resolves to a real type id.
        # Caching it would make that requirement look satisfiable forever,
        # because the cache never invalidates.
        return name, None, REASON_NOT_A_SKILL
    return name, type_id, ""


def resolve(
    cache: SkillIdCache,
    names: Sequence[str],
    client,
    *,
    max_workers: int = RESOLVE_WORKERS,
) -> dict:
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
        batch = pending[start : start + BATCH_SIZE]
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
            if (
                isinstance(type_id, int)
                and not isinstance(type_id, bool)
                and type_id > 0
            ):
                candidates[name] = type_id
            else:
                failures[name] = REASON_NOT_RESOLVED

    if not candidates:
        return failures

    accepted: dict = {}
    # Concurrency 4, matching TriffView's SemaphoreSlim(4, 4). Bounded on
    # purpose: these requests are charged against the same error-limit
    # budget the refresh loop protects by staying sequential.
    workers = max(1, min(max_workers, len(candidates)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_classify, name, type_id, client)
            for name, type_id in candidates.items()
        ]
        for future in concurrent.futures.as_completed(futures):
            name, type_id, reason = future.result()
            if reason:
                failures[name] = reason
            else:
                accepted[name] = type_id

    cache.merge(accepted)
    return failures
