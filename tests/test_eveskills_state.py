"""The roster document: one file holds identity, snapshot, queue, ETags,
and the DPAPI-wrapped refresh token for every character, so forgetting one
is a single atomic write with no window in which a token outlives the
character it belongs to.

Normalisation is tolerant rather than versioned, matching settings.py's
validated_*() functions and the rationale preview/layout.py:26-32 records:
a partially-written or hand-edited file should cost one character's row,
not the launch.
"""
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

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


def test_upsert_refuses_a_new_character_past_capacity():
    """TriffSkillsState.cs:212 throws at MaxCharacters. Updating an existing
    character is always allowed -- only a NEW row must be refused, since
    refusing an update would strand a character mid-refresh for no reason
    tied to capacity at all."""
    roster = state.SkillsState(characters=[
        state.Character(character_id=n) for n in range(1, state.MAX_CHARACTERS + 1)])
    with pytest.raises(ValueError):
        roster.upsert(state.Character(character_id=state.MAX_CHARACTERS + 1))
    # Updating one already present must still succeed at full capacity.
    roster.upsert(state.Character(character_id=1, character_name="Renamed"))
    assert roster.find(1).character_name == "Renamed"
    assert len(roster.characters) == state.MAX_CHARACTERS


def test_remove_reports_whether_it_removed_anything():
    """The bridge returns this boolean straight to the page, so forgetting a
    character that is already gone must be distinguishable from success."""
    roster = state.SkillsState(characters=[state.Character(character_id=1)])
    assert roster.remove(1) is True
    assert roster.remove(1) is False
    assert roster.characters == []


def test_find_returns_none_for_an_unknown_id():
    assert state.SkillsState().find(999) is None


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


def test_a_zero_skill_level_is_kept():
    """A resolved-but-untrained skill is level 0, which is a different fact
    from a skill whose name never resolved (absent entirely). Filtering
    zeros out would erase that distinction."""
    raw = {"characters": [{"character_id": 1,
                           "active_levels": {"3300": 0}}]}
    assert state.from_dict(raw).characters[0].active_levels == {3300: 0}


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


def test_selected_plan_name_beyond_120_chars_is_cleared():
    """TriffSkillsState.cs:198-199 clears rather than truncates: a silently
    truncated name would select a DIFFERENT plan (or none) on reload, which
    reads as a bug rather than the deliberate cap it is."""
    raw = {"selected_plan_name": "x" * 121}
    assert state.from_dict(raw).selected_plan_name == ""


def test_selected_plan_name_at_120_chars_is_kept():
    raw = {"selected_plan_name": "x" * 120}
    assert state.from_dict(raw).selected_plan_name == "x" * 120


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


def test_recovered_state_is_re_persisted_so_a_second_load_still_finds_it(
        tmp_path):
    """Mandatory correction 1 / TriffSkillsState.cs:118-119. _preserve_corrupt
    has already renamed the corrupt primary out of the way by the time
    recovery succeeds, so if load() does not immediately write the
    recovered state back to *path*, there is no primary file at all: a
    second load() (e.g. the process exiting before the next save()) takes
    the silent first-launch branch and the whole roster is gone with
    nothing shown explaining why."""
    target = tmp_path / "eve_skills.json"
    state.save(state.SkillsState(selected_plan_name="Good"), target)
    state.save(state.SkillsState(selected_plan_name="Newer"), target)
    target.write_text("{ this is not json", encoding="utf-8")

    first_loaded, first_warnings = state.load(target)
    assert first_loaded.selected_plan_name == "Good"
    assert any("Recovered" in w for w in first_warnings)

    # No save() in between -- load() itself must have re-persisted.
    second_loaded, second_warnings = state.load(target)
    assert second_loaded.selected_plan_name == "Good"
    assert second_warnings == []


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


def test_a_file_over_the_size_cap_is_treated_as_unreadable(tmp_path):
    """Mandatory correction 2 / TriffSkillsState.cs:79,102,118 via
    ReadBoundedText. An unbounded read of a multi-gigabyte state.json (or
    one grown that large by a bug or a hostile drop-in) would pull the
    whole thing into memory before any validation ever runs."""
    target = tmp_path / "eve_skills.json"
    oversized = json.dumps({"selected_plan_name": "x" * (
        state.MAX_STATE_FILE_BYTES + 1024)})
    target.write_text(oversized, encoding="utf-8")
    loaded, warnings = state.load(target)
    assert loaded.characters == []
    assert warnings and "could not be read" in warnings[0]


def test_two_corruptions_in_the_same_second_do_not_overwrite_each_other(
        tmp_path, monkeypatch):
    """Mandatory correction 5. The preserved filename uses millisecond
    resolution so two corruptions within the same wall-clock second get
    distinct names -- a second-resolution stamp would silently make the
    second corrupt-and-preserve overwrite the first preserved copy,
    destroying it before anyone could look at it."""
    target = tmp_path / "eve_skills.json"
    target.write_text("nope", encoding="utf-8")
    state.load(target)
    target.write_text("nope again", encoding="utf-8")
    state.load(target)
    preserved = sorted(p.name for p in tmp_path.iterdir()
                        if ".corrupt-" in p.name)
    assert len(preserved) == 2
    assert preserved[0] != preserved[1]


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
