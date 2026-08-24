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
import os
import stat as stat_module
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .. import atomicio

SKILL_CATEGORY_ID = 16
BATCH_SIZE = 500
MAX_ENTRIES = 20_000
CACHE_VERSION = 1
RESOLVE_WORKERS = 4

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
REASON_ESI_UNAVAILABLE = ("Could not confirm this skill with ESI; it will "
                          "be retried on the next resolve pass.")


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
            f"{MAX_CACHE_FILE_BYTES // (1024 * 1024)} MiB limit.")
    return path.read_text(encoding="utf-8")


def _preserve_corrupt(path: Path) -> str:
    """Move an unreadable document aside, returning its new name or "".

    Copied whole from state.py's _preserve_corrupt: moved, not left in
    place (else it is re-read, re-preserved and re-warned on every launch),
    millisecond-resolution stamp plus a numeric suffix fallback so two
    corruptions in the same wall-clock second cannot overwrite each other.
    """
    stamp = (time.strftime("%Y%m%d-%H%M%S")
             + f"{int(time.time() * 1000) % 1000:03d}")
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

    accepted: dict = {}
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

    cache = SkillIdCache()
    cache.merge(accepted)
    return cache


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
        # category_id is written on every entry so the load-time check has
        # something real to require. It is constant today; writing it is
        # what makes the requirement honest rather than tautological.
        "entries": [{"name": name, "type_id": type_id,
                     "category_id": SKILL_CATEGORY_ID}
                    for name, type_id in sorted(cache.type_ids().items())],
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
        warnings.append(f"{path.name} could not be read ({exc.strerror}); "
                        "skill names will be resolved again.")
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
            "not be read either; skill names will be resolved again.")
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
            "will be lost.")
        return recovered, warnings

    warnings.append(
        f"{path.name} was missing (likely an interrupted save) and was "
        f"recovered from its backup, {backup.name}.")
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
            f"{preserved or 'a copy'}; skill names will be resolved again.")
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
            "to disk.")
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
            f"disk ({exc}); it was preserved as {preserved or 'a copy'}.")
        return recovered, warnings

    warnings.append(
        f"Recovered {path.name} from backup after the main file could not "
        f"be read; it was preserved as {preserved or 'a copy'}.")
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
    if isinstance(group_id, bool) or not isinstance(group_id, int) \
            or group_id <= 0:
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


def resolve(cache: SkillIdCache, names: Sequence[str], client, *,
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
    # purpose: these requests are charged against the same error-limit
    # budget the refresh loop protects by staying sequential.
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
