"""There is no bundled SDE, so skill names become type ids over ESI.

The cache is keyed case-insensitively and NEVER invalidates -- a deliberate
inheritance from TriffView, because EVE type ids do not change and
re-checking would spend requests to learn nothing. The honest cost is that a
name resolved wrongly stays wrong until the cache file is deleted.
"""

import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta

import pytest

from wingman.eveskills import esi, skillids, training


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
    assert skillids.SkillIdCache({" Navigation ": 3449}).get("Navigation") == 3449


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
    assert cache.unresolved(["Navigation", "Evasive Maneuvering"]) == [
        "Evasive Maneuvering"
    ]


def test_unresolved_dedupes_and_keeps_the_first_spelling():
    """Forty plans share most of their skills. A repeated name spends a slot
    out of the 500-name batch and can come back with two answers for one
    key."""
    cache = skillids.SkillIdCache()
    assert cache.unresolved(["Navigation", "navigation", "NAVIGATION"]) == [
        "Navigation"
    ]


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
    cache.merge({f"Skill {n}": n + 1 for n in range(skillids.MAX_ENTRIES + 100)})
    assert len(cache.type_ids()) == skillids.MAX_ENTRIES


# --- Cycle B: the disk format --------------------------------------------


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


def test_a_missing_primary_with_a_good_bak_is_recovered_not_first_launch(tmp_path):
    """This is what save()'s rotate-then-swap leaves behind if the final
    os.replace(staging, path) fails or the process is killed between it and
    the rotate: a *.bak* with no primary. Without the FileNotFoundError
    branch consulting *.bak*, this looks identical to first launch and the
    whole cache is discarded, costing hundreds of rate-limited ESI requests
    to re-resolve names a good *.bak* still had."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(
        skillids.SkillIdCache({"Navigation": 3449, "Acceleration Control": 3452}),
        target,
    )
    target.unlink()

    loaded, warnings = skillids.load(target)
    assert loaded.get("navigation") == 3449
    assert any("was missing" in w and "recovered" in w.lower() for w in warnings)
    assert target.exists()


def test_a_missing_primary_with_no_bak_is_still_a_silent_first_launch(tmp_path):
    target = tmp_path / "cache.json"
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings == []
    assert not target.exists()


def test_a_missing_primary_with_an_unreadable_bak_starts_empty_with_a_warning(tmp_path):
    target = tmp_path / "cache.json"
    bak = tmp_path / "cache.json.bak"
    bak.write_text("{ not json", encoding="utf-8")

    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings and "will be resolved again" in warnings[0]


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
    target.write_text(
        json.dumps(
            {
                "version": skillids.CACHE_VERSION,
                "entries": [
                    {"name": "Navigation", "type_id": 3449},
                    {
                        "name": "Evasive Maneuvering",
                        "type_id": 3453,
                        "category_id": skillids.SKILL_CATEGORY_ID,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded, _warnings = skillids.load(target)
    assert loaded.get("Navigation") is None
    assert loaded.get("Evasive Maneuvering") == 3453


def test_an_entry_with_the_wrong_category_is_rejected(tmp_path):
    """Category 16 is the whole point of the three-step resolution. An entry
    claiming any other category is hand-edited or a bug, and letting it
    through would score a non-skill requirement as trainable."""
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            {
                "version": skillids.CACHE_VERSION,
                "entries": [{"name": "Rifter", "type_id": 587, "category_id": 6}],
            }
        ),
        encoding="utf-8",
    )
    loaded, _warnings = skillids.load(target)
    assert loaded.type_ids() == {}


def test_malformed_entries_drop_individually(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            {
                "version": skillids.CACHE_VERSION,
                "entries": [
                    None,
                    7,
                    {"type_id": 1, "category_id": 16},
                    {"name": "Good", "type_id": 3449, "category_id": 16},
                    {"name": "Bad", "type_id": "3449", "category_id": 16},
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded, _warnings = skillids.load(target)
    assert loaded.type_ids() == {"good": 3449}


# --- Mandatory correction 1: bound the read by size ----------------------


def test_a_file_over_the_size_cap_is_treated_as_unreadable(tmp_path):
    """SkillIdCache.cs's MaxCacheFileBytes via ReadBoundedText, applied
    BEFORE any content is decoded. Without this a multi-megabyte cache.json
    (a bug or a hand-edited drop-in) would be pulled entirely into memory
    before json.loads ever got a chance to reject it."""
    target = tmp_path / "cache.json"
    oversized = json.dumps(
        {
            "version": skillids.CACHE_VERSION,
            "entries": [],
            "padding": "x" * (skillids.MAX_CACHE_FILE_BYTES + 1024),
        }
    )
    target.write_text(oversized, encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings and "could not be read" in warnings[0]


def test_an_oversized_primary_is_recovered_from_a_good_backup(tmp_path):
    """An oversized file is exactly as recoverable-from-.bak as a
    syntactically broken one: SkillIdCache.cs's Load() catches the size-cap
    overflow in the same clause as a JSON syntax error, and that clause is
    what preserves the primary and tries the backup."""
    target = tmp_path / "cache.json"
    # save() only writes .bak from a SECOND call.
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    oversized = json.dumps(
        {
            "version": skillids.CACHE_VERSION,
            "entries": [],
            "padding": "x" * (skillids.MAX_CACHE_FILE_BYTES + 1024),
        }
    )
    target.write_text(oversized, encoding="utf-8")

    loaded, warnings = skillids.load(target)
    assert loaded.get("Navigation") == 3449
    assert any("Recovered" in w for w in warnings)
    preserved = [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert len(preserved) == 1


# --- Mandatory correction 2: restore the .bak recovery tier --------------


def test_save_copies_the_previous_document_to_bak(tmp_path):
    """A populated cache rebuilds by re-resolving every name through
    rate-limited ESI at up to three requests per name -- hundreds of
    requests against the shared error-limit budget, to recover data that
    was sitting intact in a backup."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"A": 1}), target)
    skillids.save(skillids.SkillIdCache({"B": 2}), target)
    backup = json.loads((tmp_path / "cache.json.bak").read_text())
    assert backup["entries"] == [
        {"name": "a", "type_id": 1, "category_id": skillids.SKILL_CATEGORY_ID}
    ]


def test_the_first_save_writes_no_bak(tmp_path):
    """There is nothing to back up yet, and an empty .bak would later be
    recovered from in preference to giving up honestly."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"A": 1}), target)
    assert not (tmp_path / "cache.json.bak").exists()


def test_a_corrupt_cache_is_recovered_from_backup(tmp_path):
    """The whole point of mandatory correction 2: this is the scenario the
    brief's dropped tier would have failed."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    target.write_text("{ not json", encoding="utf-8")

    loaded, warnings = skillids.load(target)
    assert loaded.get("Navigation") == 3449
    assert any("Recovered" in w for w in warnings)
    preserved = [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert len(preserved) == 1


def test_recovered_cache_is_re_persisted_so_a_second_load_still_finds_it(tmp_path):
    """_preserve_corrupt has already renamed the corrupt primary out of the
    way by the time recovery succeeds, so if load() does not immediately
    write the recovered cache back to *path*, a second load() (e.g. the
    process exiting before the next save()) takes the silent
    empty-cache branch with no explanation."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    target.write_text("{ not json", encoding="utf-8")

    first_loaded, first_warnings = skillids.load(target)
    assert first_loaded.get("Navigation") == 3449
    assert any("Recovered" in w for w in first_warnings)

    second_loaded, second_warnings = skillids.load(target)
    assert second_loaded.get("Navigation") == 3449
    assert second_warnings == []


def test_a_corrupt_cache_with_no_usable_backup_starts_empty(tmp_path):
    """Same preserve-and-warn posture as state.py, but the recovery here is
    a slower resolve pass rather than re-authorising every character."""
    target = tmp_path / "cache.json"
    target.write_text("{ not json", encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings and "could not be read" in warnings[0]
    assert not target.exists()
    assert [p.name for p in tmp_path.iterdir() if ".corrupt-" in p.name]


def test_a_wrong_version_is_recovered_from_backup_when_one_exists(tmp_path):
    """Ground-truth divergence found while implementing correction 2:
    SkillIdCache.cs's FromJson() throws JsonException for a version
    mismatch exactly the same way it does for broken JSON, and Load()
    catches both in the SAME clause that tries `.bak` -- a wrong version is
    not a distinct "start empty" case in the source, it is just one more
    way FromJson can throw. Restoring the .bak tier without also routing
    version mismatches through it would leave a real ground-truth path
    untested."""
    target = tmp_path / "cache.json"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    target.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")

    loaded, warnings = skillids.load(target)
    assert loaded.get("Navigation") == 3449
    assert any("Recovered" in w for w in warnings)


def test_a_wrong_version_starts_empty_with_a_warning(tmp_path):
    """This file rebuilds completely by re-resolving, so refusing a format
    we do not understand -- with no backup to fall back on -- costs one
    slow refresh and nothing else."""
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert loaded.type_ids() == {}
    assert warnings


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX mode bits; on Windows DPAPI does the work"
)
def test_bak_mode_is_hardened_on_the_recovery_write_back_path_too(tmp_path):
    """The chmod in save() that aligns .bak to the primary's mode must also
    fire on _recover_from_backup()'s write-back, where save() never takes
    its own copy branch (the primary was just moved aside by
    _preserve_corrupt) but a laxer-permission .bak from before this cache
    ever touched it can still be sitting there."""
    target = tmp_path / "cache.json"
    bak = tmp_path / "cache.json.bak"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    os.chmod(bak, 0o644)

    target.write_text("{ not json", encoding="utf-8")
    loaded, _warnings = skillids.load(target)

    assert loaded.get("Navigation") == 3449
    assert stat.S_IMODE(bak.stat().st_mode) == 0o600


def test_preservation_failure_does_not_overwrite_a_good_backup(tmp_path, monkeypatch):
    """Same Critical fix as state.py's identically-named test: if
    _preserve_corrupt's own os.replace fails, the corrupt content is still
    sitting at *path*. save() must never be called in that case -- its
    rotate step would otherwise overwrite the good .bak with the still-
    corrupt primary an instant after reading a good cache out of it."""
    target = tmp_path / "cache.json"
    bak = tmp_path / "cache.json.bak"
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    skillids.save(skillids.SkillIdCache({"Navigation": 3449}), target)
    target.write_text("{ not json", encoding="utf-8")

    real_replace = os.replace

    def _flaky_replace(src, dst, *a, **kw):
        if ".corrupt-" in str(dst):
            raise OSError("simulated: concurrent handle on the target")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(skillids.os, "replace", _flaky_replace)

    loaded, warnings = skillids.load(target)

    assert loaded.get("Navigation") == 3449
    assert any("could not be saved back" in w for w in warnings)
    assert target.read_text(encoding="utf-8") == "{ not json"
    backup_cache = skillids._cache_from_raw(json.loads(bak.read_text(encoding="utf-8")))
    assert backup_cache.get("Navigation") == 3449


# --- Cycle C: resolution over ESI ----------------------------------------


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
        return esi.EsiResponse(200, {"inventory_types": found}, "", "", "POST", path)

    def get(self, path, *, token=None, etag=None):
        self.paths.append(path)
        segments = [s for s in path.split("/") if s]
        # segments[0] is the version ("v3"/"v1"), segments[1] is always
        # "universe" for both routes -- the route noun this helper needs
        # to distinguish "/types/" from "/groups/" on is segments[2].
        table = self.types if segments[2] == "types" else self.groups
        key = int(segments[-1])
        if key not in table:
            return esi.EsiResponse(404, None, "not found", "", "GET", path)
        return esi.EsiResponse(200, table[key], "", "", "GET", path)


def test_a_skill_resolves_and_enters_the_cache():
    client = FakeEsi(
        ids={"Navigation": 3449},
        types={3449: {"group_id": 257}},
        groups={257: {"category_id": 16}},
    )
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Navigation"], client, max_workers=1)
    assert failures == {}
    assert cache.get("Navigation") == 3449


def test_a_name_esi_does_not_know_reports_the_exact_reason():
    client = FakeEsi(ids={})
    failures = skillids.resolve(
        skillids.SkillIdCache(), ["Nope"], client, max_workers=1
    )
    assert failures == {"Nope": "Name was not resolved by ESI."}


def test_a_type_with_no_group_reports_the_exact_reason():
    client = FakeEsi(ids={"Weird": 1}, types={1: {}})
    failures = skillids.resolve(
        skillids.SkillIdCache(), ["Weird"], client, max_workers=1
    )
    assert failures == {"Weird": "Resolved type had no valid group."}


def test_a_non_skill_type_reports_the_exact_reason_and_is_not_cached():
    """A ship name in a plan file resolves to a real type id. Caching it
    would make that requirement look satisfiable forever, because the cache
    never invalidates."""
    client = FakeEsi(
        ids={"Rifter": 587},
        types={587: {"group_id": 25}},
        groups={25: {"category_id": 6}},
    )
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Rifter"], client, max_workers=1)
    assert failures == {
        "Rifter": "Resolved inventory type is not in EVE's skill category."
    }
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
    client = FakeEsi(
        ids={"A": 1, "B": 2},
        types={1: {"group_id": 257}, 2: {"group_id": 257}},
        groups={257: {"category_id": 16}},
    )
    skillids.resolve(skillids.SkillIdCache(), ["A", "B"], client, max_workers=1)
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
    assert failures == {
        "A": "Name was not resolved by ESI.",
        "B": "Name was not resolved by ESI.",
    }
    assert cache.type_ids() == {}


def test_resolution_fans_out():
    """Concurrency 4, matching TriffView's SemaphoreSlim(4, 4). Bounded on
    purpose: this is charged against the shared error-limit budget."""
    names = [f"Skill {n}" for n in range(8)]
    client = FakeEsi(
        ids={name: n + 1 for n, name in enumerate(names)},
        types={n + 1: {"group_id": 257} for n in range(8)},
        groups={257: {"category_id": 16}},
    )
    cache = skillids.SkillIdCache()
    assert (
        skillids.resolve(cache, names, client, max_workers=skillids.RESOLVE_WORKERS)
        == {}
    )
    assert len(cache.type_ids()) == 8


# --- Mandatory correction 3: transient failure vs. genuinely missing -----


def test_a_transient_failure_confirming_the_type_is_distinct_from_no_group():
    """The brief originally gave both cases the identical reason. A user
    reading the plan-issues rollup cannot tell "ESI was down just now" from
    "this genuinely is not a skill" unless the strings differ."""

    class Flaky(FakeEsi):
        def get(self, path, *, token=None, etag=None):
            if "/types/" in path:
                self.paths.append(path)
                return esi.EsiResponse(503, None, "boom", "", "GET", path)
            return super().get(path)

    client = Flaky(ids={"Navigation": 3449})
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Navigation"], client, max_workers=1)
    assert failures == {"Navigation": skillids.REASON_ESI_UNAVAILABLE}
    assert failures["Navigation"] != skillids.REASON_NO_GROUP
    assert cache.type_ids() == {}


def test_a_transient_failure_confirming_the_category_is_also_distinct():
    """The same distinction applies one step later: the group lookup
    failing outright is not the same fact as it succeeding with a category
    that is not 16."""
    client = FakeEsi(ids={"Navigation": 3449}, types={3449: {"group_id": 257}})
    # No entry for group 257 -- FakeEsi.get() answers that with a 404.
    cache = skillids.SkillIdCache()
    failures = skillids.resolve(cache, ["Navigation"], client, max_workers=1)
    assert failures == {"Navigation": skillids.REASON_ESI_UNAVAILABLE}
    assert failures["Navigation"] != skillids.REASON_NOT_A_SKILL
    assert cache.type_ids() == {}


# --- Task 2: expiring skill training metadata -----------------------------

NOW = datetime(2026, 9, 2, tzinfo=UTC)
GUNNERY_META = training.SkillTrainingMetadata(1, "perception", "willpower", NOW)

# Documented ESI dogma attributes for Gunnery (type 3300): 275 is rank
# (skillTimeConstant) = 1, 180/181 are references to attribute ids 167
# (perception) and 168 (willpower).
TYPE_BODY = {
    "group_id": 255,
    "dogma_attributes": [
        {"attribute_id": 275, "value": 1.0},
        {"attribute_id": 180, "value": 167.0},
        {"attribute_id": 181, "value": 168.0},
    ],
}


def test_training_metadata_round_trips_without_changing_type_id_lookup(tmp_path):
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    assert cache.merge_metadata({3300: GUNNERY_META}) == 1
    target = tmp_path / "cache.json"
    skillids.save(cache, target)
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("gunnery") == 3300
    assert loaded.training_metadata(NOW) == {3300: GUNNERY_META}


def test_version_one_id_only_cache_loads_and_requests_metadata(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [{"name": "Gunnery", "type_id": 3300, "category_id": 16}],
            }
        ),
        encoding="utf-8",
    )
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("gunnery") == 3300
    assert loaded.metadata_due(["Gunnery"], NOW) == (("Gunnery", 3300),)


def test_merge_metadata_rejects_a_type_id_the_cache_does_not_hold():
    """merge_metadata is not the id-resolution path: it must never let a
    staged fetch result invent a skill this cache has no id for."""
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    assert cache.merge_metadata({9999: GUNNERY_META}) == 0
    assert cache.training_metadata(NOW) == {}


def test_merge_metadata_overwrites_a_stale_record():
    """Unlike merge() for ids, metadata merge must overwrite: expiry is
    only useful if a fresh fetch can replace a record already on file."""
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    stale = training.SkillTrainingMetadata(
        1, "perception", "willpower", NOW - timedelta(days=40)
    )
    cache.merge_metadata({3300: stale})
    assert cache.training_metadata(NOW) == {}
    cache.merge_metadata({3300: GUNNERY_META})
    assert cache.training_metadata(NOW) == {3300: GUNNERY_META}


def test_metadata_at_29_days_is_fresh_and_at_30_days_is_due():
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    fresh = training.SkillTrainingMetadata(
        1, "perception", "willpower", NOW - timedelta(days=29)
    )
    cache.merge_metadata({3300: fresh})
    assert cache.training_metadata(NOW) == {3300: fresh}
    assert cache.metadata_due(["Gunnery"], NOW) == ()

    stale = training.SkillTrainingMetadata(
        1, "perception", "willpower", NOW - timedelta(days=30)
    )
    cache.merge_metadata({3300: stale})
    assert cache.training_metadata(NOW) == {}
    assert cache.metadata_due(["Gunnery"], NOW) == (("Gunnery", 3300),)


def test_metadata_due_dedupes_names_sharing_one_type_id():
    """Two plan entries differing only by case share one type id, and must
    not spend two requests to learn the same answer twice."""
    cache = skillids.SkillIdCache({"Gunnery": 3300})
    assert cache.metadata_due(["Gunnery", "gunnery", "GUNNERY"], NOW) == (
        ("Gunnery", 3300),
    )


def test_metadata_due_skips_a_name_with_no_type_id_yet():
    cache = skillids.SkillIdCache()
    assert cache.metadata_due(["Gunnery"], NOW) == ()


def test_a_wrong_training_metadata_sub_version_preserves_ids_and_drops_metadata(
    tmp_path,
):
    """training_metadata_version is a gate independent of CACHE_VERSION: a
    mismatch discards only the metadata half, never the id it sits beside."""
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            {
                "version": skillids.CACHE_VERSION,
                "training_metadata_version": 99,
                "entries": [
                    {
                        "name": "Gunnery",
                        "type_id": 3300,
                        "category_id": 16,
                        "training": {
                            "rank": 1,
                            "primary_attribute": "perception",
                            "secondary_attribute": "willpower",
                            "fetched_utc": "2026-09-02T00:00:00+00:00",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("Gunnery") == 3300
    assert loaded.training_metadata(NOW) == {}


def test_a_second_case_folded_name_with_a_different_type_id_does_not_leak_its_metadata(
    tmp_path,
):
    """Fix round 1: _cache_from_raw() built *metadata* from every entry that
    passed the per-entry id checks, keyed by that entry's OWN type_id, and
    then applied it with a direct cache._metadata.update() -- bypassing
    merge_metadata()'s known-id invariant entirely. "Gunnery" and "gunnery"
    fold to the same _by_key key, so merge() (first spelling wins, never
    overwrites) accepts only 3300 into _by_key; but the update() bypass
    still stored training metadata for 9999, an id this cache does not
    actually hold. Only 3300 must ever be visible, in both type_ids() and
    training_metadata().
    """
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            {
                "version": skillids.CACHE_VERSION,
                "training_metadata_version": skillids.TRAINING_METADATA_VERSION,
                "entries": [
                    {
                        "name": "Gunnery",
                        "type_id": 3300,
                        "category_id": 16,
                        "training": {
                            "rank": 1,
                            "primary_attribute": "perception",
                            "secondary_attribute": "willpower",
                            "fetched_utc": "2026-09-02T00:00:00+00:00",
                        },
                    },
                    {
                        "name": "gunnery",
                        "type_id": 9999,
                        "category_id": 16,
                        "training": {
                            "rank": 1,
                            "primary_attribute": "perception",
                            "secondary_attribute": "willpower",
                            "fetched_utc": "2026-09-02T00:00:00+00:00",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.type_ids() == {"gunnery": 3300}
    assert loaded.training_metadata(NOW) == {3300: GUNNERY_META}


def _entry_with_training(training_obj) -> dict:
    return {
        "version": skillids.CACHE_VERSION,
        "training_metadata_version": skillids.TRAINING_METADATA_VERSION,
        "entries": [
            {
                "name": "Gunnery",
                "type_id": 3300,
                "category_id": 16,
                "training": training_obj,
            }
        ],
    }


@pytest.mark.parametrize(
    "training_obj",
    [
        {
            "rank": 0,
            "primary_attribute": "perception",
            "secondary_attribute": "willpower",
            "fetched_utc": "2026-09-02T00:00:00+00:00",
        },
        {
            "rank": True,
            "primary_attribute": "perception",
            "secondary_attribute": "willpower",
            "fetched_utc": "2026-09-02T00:00:00+00:00",
        },
        {
            "rank": 1,
            "primary_attribute": "warlock",
            "secondary_attribute": "willpower",
            "fetched_utc": "2026-09-02T00:00:00+00:00",
        },
        {
            "rank": 1,
            "primary_attribute": "perception",
            "secondary_attribute": "willpower",
            "fetched_utc": "not a timestamp",
        },
        {
            "rank": 1,
            "primary_attribute": "perception",
            "secondary_attribute": "willpower",
        },
    ],
    ids=[
        "non_positive_rank",
        "boolean_rank",
        "unknown_attribute_name",
        "malformed_timestamp",
        "missing_timestamp",
    ],
)
def test_malformed_training_metadata_drops_only_that_entrys_metadata(
    tmp_path, training_obj
):
    target = tmp_path / "cache.json"
    target.write_text(json.dumps(_entry_with_training(training_obj)), encoding="utf-8")
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.get("Gunnery") == 3300
    assert loaded.training_metadata(NOW) == {}


def test_unknown_fields_in_training_metadata_are_ignored(tmp_path):
    target = tmp_path / "cache.json"
    target.write_text(
        json.dumps(
            _entry_with_training(
                {
                    "rank": 1,
                    "primary_attribute": "perception",
                    "secondary_attribute": "willpower",
                    "fetched_utc": "2026-09-02T00:00:00+00:00",
                    "unexpected_field": "ignored",
                }
            )
        ),
        encoding="utf-8",
    )
    loaded, warnings = skillids.load(target)
    assert warnings == []
    assert loaded.training_metadata(NOW) == {3300: GUNNERY_META}


def test_a_corrupt_cache_recovers_both_ids_and_metadata_from_backup(tmp_path):
    """Every existing corruption/backup invariant must keep holding with
    metadata in the picture: recovery must not silently drop it."""
    target = tmp_path / "cache.json"
    cache = skillids.SkillIdCache({"Navigation": 3449})
    cache.merge_metadata(
        {3449: training.SkillTrainingMetadata(1, "perception", "willpower", NOW)}
    )
    skillids.save(cache, target)
    skillids.save(cache, target)
    target.write_text("{ not json", encoding="utf-8")

    loaded, warnings = skillids.load(target)
    assert loaded.get("Navigation") == 3449
    assert loaded.training_metadata(NOW) == {
        3449: training.SkillTrainingMetadata(1, "perception", "willpower", NOW)
    }
    assert any("Recovered" in w for w in warnings)


def test_fetch_training_metadata_decodes_rank_and_attribute_names():
    client = FakeEsi(types={3300: TYPE_BODY})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300),), client, NOW, max_workers=1
    )
    assert accepted == {3300: GUNNERY_META}
    assert failures == {}


def test_fetch_failure_returns_no_partial_cache_mutation():
    class OneFailure(FakeEsi):
        def get(self, path, *, token=None, etag=None):
            if path.endswith("/3449/"):
                self.paths.append(path)
                return esi.EsiResponse(503, None, "boom", "", "GET", path)
            return super().get(path, token=token, etag=etag)

    cache = skillids.SkillIdCache({"Gunnery": 3300, "Navigation": 3449})
    client = OneFailure(types={3300: TYPE_BODY})
    accepted, failures = skillids.fetch_training_metadata(
        cache.metadata_due(["Gunnery", "Navigation"], NOW),
        client,
        NOW,
        max_workers=1,
    )
    assert 3300 in accepted and "Navigation" in failures
    assert cache.training_metadata(NOW) == {}, "fetch must stage, not mutate"
    assert failures["Navigation"] == skillids.REASON_METADATA_UNAVAILABLE


def test_fetch_training_metadata_dedupes_requests_by_type_id():
    """Duplicate names sharing one type id must cost one request."""
    client = FakeEsi(types={3300: TYPE_BODY})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300), ("gunnery", 3300)), client, NOW, max_workers=1
    )
    assert accepted == {3300: GUNNERY_META}
    assert failures == {}
    assert client.paths.count("/v3/universe/types/3300/") == 1


def test_fetch_training_metadata_rejects_a_type_with_no_dogma_attributes():
    client = FakeEsi(types={3300: {"group_id": 255}})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300),), client, NOW, max_workers=1
    )
    assert accepted == {}
    assert failures == {"Gunnery": skillids.REASON_METADATA_UNAVAILABLE}


def test_fetch_training_metadata_rejects_an_unknown_attribute_reference():
    body = {
        "group_id": 255,
        "dogma_attributes": [
            {"attribute_id": 275, "value": 1.0},
            {"attribute_id": 180, "value": 999.0},
            {"attribute_id": 181, "value": 168.0},
        ],
    }
    client = FakeEsi(types={3300: body})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300),), client, NOW, max_workers=1
    )
    assert accepted == {}
    assert failures == {"Gunnery": skillids.REASON_METADATA_UNAVAILABLE}


def test_fetch_training_metadata_rejects_a_non_integer_rank():
    body = {
        "group_id": 255,
        "dogma_attributes": [
            {"attribute_id": 275, "value": 1.5},
            {"attribute_id": 180, "value": 167.0},
            {"attribute_id": 181, "value": 168.0},
        ],
    }
    client = FakeEsi(types={3300: body})
    accepted, failures = skillids.fetch_training_metadata(
        (("Gunnery", 3300),), client, NOW, max_workers=1
    )
    assert accepted == {}
    assert failures == {"Gunnery": skillids.REASON_METADATA_UNAVAILABLE}
