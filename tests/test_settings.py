import json

import pytest

from wingman import bookmarks, settings


def test_defaults_are_the_documented_values():
    assert settings.DEFAULTS == {
        "privacy": "unlisted",
        "category": "20",
        "notify_mode": "toast",
        "recording_dir": None,
        "discord_webhook": "",
        "gamelogs_dir": None,
        "channel_id": "",
        "channel_title": "",
        # TRUE, unlike the two feature flags below. Those decide whether
        # something RUNS and must be opted into; this decides only whether
        # the EVE screens are offered. In practice the people who install
        # this play EVE, so it is on for everyone and nothing asks -- and
        # an upgrading user's file predates the key, so defaulting it off
        # would silently remove four things they already use.
        "show_eve_tools": True,
        # FALSE, and it records a dismissal rather than a folder state.
        # __main__ shows the first-run screen whenever no folder RESOLVES,
        # so "never configured, and said so" has to be distinguishable from
        # "configured once, folder has since gone" -- only the first is a
        # skip, and the second still deserves the screen.
        "first_run_skipped": False,
        "eve_bookmarks": {
            "enabled": False,
            "keybinds": bookmarks.DEFAULT_BINDS,
            "windows": {},
        },
        "preview": {
            # Off by default for the same reason eve_bookmarks is:
            # enabling it starts a thread, a 700ms discovery sweep and a
            # foreground hook, none of which a non-EVE user should pay.
            "enabled": False,
            "width": 320,
            "height": 210,
            "opacity": 255,
            # 2, not 1: the opacity default moved from 235 once the key
            # became visible, and validated_preview's one-shot migration
            # is keyed off this marker.
            "defaults_version": 2,
            "layouts": {},
            "hotkeys": {"characters": {}, "cycle_next": "", "cycle_prev": ""},
            "seen": [],
            "restore_preview_positions": True,
            "alerts": {
                "enabled": False,
                "pve_filter": True,
                "persist_until_selected": True,
                "defaults_version": 1,
                "events": {
                    "combat": {
                        "enabled": True,
                        "duration_ms": 1200,
                        "pulses": 3,
                        "cooldown_s": 1,
                        "color": "#ff4d4d",
                        "sound": "alarm",
                    },
                    "warp_scramble": {
                        "enabled": True,
                        "duration_ms": 1200,
                        "pulses": 3,
                        "cooldown_s": 8,
                        "color": "#ffd24d",
                        "sound": "ring",
                    },
                    "decloak": {
                        "enabled": True,
                        "duration_ms": 1200,
                        "pulses": 3,
                        "cooldown_s": 8,
                        "color": "#4dd2ff",
                        "sound": "notify",
                    },
                },
            },
            "show_labels": True,
            "minimize_inactive_clients": False,
            # Off: previews leaving the screen is opt-in, and an upgrading
            # install has no such key.
            "hide_on_lost_focus": False,
            "never_minimize": [],
            "excluded": [],
            "locked": [],
            "lock_default": False,
            "snap": True,
            "lock_aspect": True,
            "selection_color": "#00c8dc",
        },
        "eve_settings": {
            "root": None,
            "server": None,
            "profile": None,
            "auto_keep": 10,
        },
        # Off by default like the other feature flags: it opens a second
        # WebView2 window, which must be asked for.
        "sig_bar": {
            "enabled": False,
            "x": None,
            "y": None,
        },
    }


def test_channel_identity_defaults_to_empty(tmp_path):
    """Empty, not None: it reaches a label, and "None" is not a channel."""
    data = settings.load(tmp_path / "missing.json")
    assert data["channel_id"] == ""
    assert data["channel_title"] == ""


def test_channel_identity_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save(
        {**settings.DEFAULTS, "channel_id": "UC123", "channel_title": "Zoolanders"}, p
    )
    loaded = settings.load(p)
    assert loaded["channel_id"] == "UC123"
    assert loaded["channel_title"] == "Zoolanders"


@pytest.mark.parametrize("bad", [{"nope": 1}, 7, None, ["a"]])
def test_non_string_channel_identity_is_discarded(tmp_path, bad):
    """This value is read back from a YouTube API response and then rendered
    into a label; a dict or an int arriving from a hand-edited file must not
    reach the UI."""
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"channel_title": bad, "channel_id": bad}))
    loaded = settings.load(p)
    assert loaded["channel_title"] == ""
    assert loaded["channel_id"] == ""


def test_discord_webhook_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    url = "https://discord.com/api/webhooks/123/tok"
    settings.save({**settings.DEFAULTS, "discord_webhook": url}, p)
    assert settings.load(p)["discord_webhook"] == url


def test_gamelogs_dir_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save({**settings.DEFAULTS, "gamelogs_dir": "C:/logs"}, p)
    assert settings.load(p)["gamelogs_dir"] == "C:/logs"


def test_non_string_discord_webhook_is_coerced(tmp_path):
    """settings.json is a plain file a user can edit; save-time UI validation
    does not protect the load path."""
    import json

    p = tmp_path / "s.json"
    p.write_text(json.dumps({"discord_webhook": 12345}))
    assert settings.load(p)["discord_webhook"] == ""


def test_non_string_gamelogs_dir_is_coerced(tmp_path):
    import json

    p = tmp_path / "s.json"
    p.write_text(json.dumps({"gamelogs_dir": ["a", "b"]}))
    assert settings.load(p)["gamelogs_dir"] is None


def test_recording_dir_roundtrips(tmp_path):
    """Regression guard: save() projects onto DEFAULTS keys, so a key not
    declared there is silently dropped and the folder is re-picked every
    launch."""
    p = tmp_path / "s.json"
    settings.save({**settings.DEFAULTS, "recording_dir": "C:/rec"}, p)
    assert settings.load(p)["recording_dir"] == "C:/rec"


def test_recording_dir_defaults_to_none(tmp_path):
    assert settings.load(tmp_path / "nope.json")["recording_dir"] is None


def test_load_returns_defaults_when_file_missing(tmp_path):
    assert settings.load(tmp_path / "nope.json") == settings.DEFAULTS


def test_load_merges_partial_file_over_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": "unlisted"}))
    loaded = settings.load(p)
    assert loaded["privacy"] == "unlisted"
    assert loaded["category"] == "20"
    assert loaded["notify_mode"] == "toast"


def test_load_survives_corrupt_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ not json")
    assert settings.load(p) == settings.DEFAULTS


def test_load_ignores_unknown_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": "public", "bogus": 1}))
    assert "bogus" not in settings.load(p)


def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save({"privacy": "public", "category": "22", "notify_mode": "popup"}, p)
    assert settings.load(p)["privacy"] == "public"
    assert settings.load(p)["notify_mode"] == "popup"
    assert settings.load(p)["category"] == "22"


def test_save_creates_parent_directory(tmp_path):
    p = tmp_path / "deep" / "s.json"
    settings.save(settings.DEFAULTS, p)
    assert p.exists()


@pytest.mark.parametrize("bad", ["", "sideways", None])
def test_load_rejects_invalid_privacy(tmp_path, bad):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": bad}))
    assert settings.load(p)["privacy"] == "unlisted"


@pytest.mark.parametrize("raw", ["[]", "42"])
def test_load_rejects_valid_json_of_the_wrong_shape(tmp_path, raw):
    """Valid JSON that isn't an object (a list, a bare number) must fall
    back to defaults rather than crashing on the `key in raw` checks."""
    p = tmp_path / "s.json"
    p.write_text(raw)
    assert settings.load(p) == settings.DEFAULTS


def test_load_rejects_category_supplied_as_an_int(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"category": 22}))
    assert settings.load(p)["category"] == settings.DEFAULTS["category"]


def test_load_rejects_recording_dir_supplied_as_a_non_string(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"recording_dir": 123}))
    assert settings.load(p)["recording_dir"] is None


def test_update_saves_on_clean_exit(tmp_path):
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    with settings.update(data, path) as doc:
        doc["privacy"] = "public"
    assert json.loads(path.read_text())["privacy"] == "public"


def test_update_rolls_back_and_does_not_write_on_failure(tmp_path):
    """A failed block must leave neither the file nor the live dict changed.

    ui/api.py bails before touching in-memory state precisely so state and
    disk cannot diverge; the primitive has to preserve that property or
    converting that caller would regress it.
    """
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    settings.save(data, path)
    with pytest.raises(RuntimeError), settings.update(data, path) as doc:
        doc["privacy"] = "public"
        raise RuntimeError("boom")
    assert data["privacy"] == settings.DEFAULTS["privacy"]
    assert json.loads(path.read_text())["privacy"] == settings.DEFAULTS["privacy"]


def test_update_rollback_restores_nested_sections(tmp_path):
    """Shallow restore would leave a mutated nested dict in place, which is
    exactly where preview state lives."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    with pytest.raises(RuntimeError), settings.update(data, path) as doc:
        doc["preview"]["opacity"] = 40
        raise RuntimeError("boom")
    assert data["preview"]["opacity"] == settings.DEFAULTS["preview"]["opacity"]


def test_concurrent_updates_serialise_without_corrupting_the_document(tmp_path):
    """Smoke coverage: concurrent writers interleave without corrupting the
    document or losing a key WITHIN this shape. It is NOT a regression guard
    for the lost-update race -- both threads share one dict and write
    disjoint keys, so it passes against an unlocked update() too (verified).
    The race needs a writer that serialises a SNAPSHOT read earlier, which
    arrives when ui/api.py is converted."""
    import threading

    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    settings.save(data, path)
    barrier = threading.Barrier(2)

    def writer(key, value):
        barrier.wait()
        for _ in range(50):
            with settings.update(data, path) as doc:
                doc[key] = value

    threads = [
        threading.Thread(target=writer, args=("privacy", "public")),
        threading.Thread(target=writer, args=("category", "22")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        # Bounded: if settings.update() ever deadlocks, this test must
        # fail loudly instead of hanging until the CI job times out.
        t.join(timeout=5.0)
        assert not t.is_alive()

    written = json.loads(path.read_text())
    assert written["privacy"] == "public"
    assert written["category"] == "22"


def test_preview_defaults_carry_an_empty_hotkey_table():
    section = settings._preview_defaults()
    assert section["hotkeys"] == {"characters": {}, "cycle_next": "", "cycle_prev": ""}
    assert section["seen"] == []


def test_preview_defaults_are_not_shared_between_calls():
    """The nested-dict trap the existing defaults were written to avoid."""
    a, b = settings._preview_defaults(), settings._preview_defaults()
    a["hotkeys"]["characters"]["Alice"] = "Ctrl+F1"
    assert b["hotkeys"]["characters"] == {}


def test_validated_preview_keeps_parseable_gestures():
    section = settings.validated_preview(
        {
            "hotkeys": {
                "characters": {"Alice": "Ctrl+F1"},
                "cycle_next": "Ctrl+Alt+Right",
                "cycle_prev": "",
            }
        }
    )
    assert section["hotkeys"]["characters"] == {"Alice": "Ctrl+F1"}
    assert section["hotkeys"]["cycle_next"] == "Ctrl+Alt+Right"


def test_validated_preview_drops_one_bad_gesture_not_the_section():
    """Same posture as the layout entries: a hand-edited file costs one
    binding, not the launch."""
    section = settings.validated_preview(
        {
            "enabled": True,
            "hotkeys": {
                "characters": {"Alice": "Ctrl+F1", "Bravo": "nonsense", "Carol": "F1"}
            },
        }
    )
    assert section["enabled"] is True
    assert section["hotkeys"]["characters"] == {"Alice": "Ctrl+F1"}


def test_validated_preview_canonicalises_gestures():
    """Stored in display form so the clash check compares strings."""
    section = settings.validated_preview(
        {"hotkeys": {"characters": {"Alice": "alt+ctrl+f2"}}}
    )
    assert section["hotkeys"]["characters"]["Alice"] == "Ctrl+Alt+F2"


def test_validated_preview_falls_back_on_a_malformed_hotkey_section():
    section = settings.validated_preview({"hotkeys": "nonsense"})
    assert section["hotkeys"] == {"characters": {}, "cycle_next": "", "cycle_prev": ""}


def test_validated_preview_cleans_the_roster():
    section = settings.validated_preview({"seen": ["Alice", "hwnd:0x1", 7]})
    assert section["seen"] == ["Alice"]


def test_a_pre_branch_file_is_migrated_off_the_dead_opacity_default():
    """235 in a file with no version marker is the old default, not a
    choice: opacity had no user interface before this branch, and
    _save_locked wrote the default into every install's file."""
    section = settings.validated_preview({"opacity": 235})
    assert section["opacity"] == 255
    assert section["defaults_version"] == 2


def test_the_opacity_migration_does_not_run_twice():
    """Someone who picks 235 from the slider AFTER the migration keeps it.
    The marker is the only thing separating that from the old default."""
    section = settings.validated_preview({"opacity": 235, "defaults_version": 2})
    assert section["opacity"] == 235
    assert section["defaults_version"] == 2


def test_the_opacity_migration_leaves_a_non_default_value_alone():
    """The whole point of keying off the previous default: anything else
    in a pre-branch file survives untouched."""
    section = settings.validated_preview({"opacity": 180})
    assert section["opacity"] == 180
    assert section["defaults_version"] == 2


def test_a_future_defaults_version_is_not_walked_backwards():
    section = settings.validated_preview({"opacity": 235, "defaults_version": 9})
    assert section["opacity"] == 235
    assert section["defaults_version"] == 9


# The two below are ported from the callable-style update(read, mutate)
# that the EVE Settings work added on main. That API is gone -- update() is
# a context manager here -- but the properties its tests pinned are real and
# were not otherwise covered, so they follow the surviving shape.
def test_update_holds_the_save_lock_across_the_body(tmp_path):
    """The whole point: the lock spans the caller's mutation, not just the
    write, or another writer completes in between and is reverted."""
    path = tmp_path / "settings.json"
    seen = []
    data = settings._fresh_defaults()

    with settings.update(data, path) as doc:
        seen.append(settings._SAVE_LOCK.locked())
        doc["privacy"] = "public"

    assert seen == [True]
    assert settings.load(path)["privacy"] == "public"


def test_update_releases_the_lock_when_the_body_raises(tmp_path):
    """A block that throws must not wedge every other writer forever."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()

    with pytest.raises(ValueError), settings.update(data, path):
        raise ValueError("nope")

    assert not settings._SAVE_LOCK.locked()


def test_preview_lock_aspect_defaults_on_and_survives_a_round_trip(tmp_path):
    """On by default because it is what shipped: the drag handle has always
    held the client's shape. A new key whose default matches current
    behaviour needs no defaults_version bump."""
    path = tmp_path / "settings.json"
    assert settings.load(path)["preview"]["lock_aspect"] is True

    doc = settings.load(path)
    with settings.update(doc, path) as live:
        live["preview"]["lock_aspect"] = False
    assert settings.load(path)["preview"]["lock_aspect"] is False


def test_preview_lock_aspect_ignores_a_non_bool(tmp_path):
    """Same guard every other preview bool gets: a junk value falls back to
    the default rather than reaching PreviewWindow as a truthy string."""
    section = settings.validated_preview({"lock_aspect": "yes"})
    assert section["lock_aspect"] is True


def test_preview_lock_default_is_off_and_needs_no_migration(tmp_path):
    """Off by default, and that is the whole reason this key could be added
    without a defaults_version bump.

    `preview.locked` keeps meaning "these differ from the default". With
    lock_default False the effective lock collapses to plain membership,
    which is exactly what every install that predates this key already
    does -- so a file written before it, and a file written after it,
    describe the same behaviour.
    """
    path = tmp_path / "settings.json"
    assert settings.load(path)["preview"]["lock_default"] is False

    doc = settings.load(path)
    with settings.update(doc, path) as live:
        live["preview"]["lock_default"] = True
    assert settings.load(path)["preview"]["lock_default"] is True


def test_preview_lock_default_ignores_a_non_bool(tmp_path):
    section = settings.validated_preview({"lock_default": "yes"})
    assert section["lock_default"] is False


def test_validated_preview_takes_a_good_selection_colour_and_drops_a_bad_one():
    """Same per-value posture as the rest of the section: a #rrggbb string
    is kept, anything else falls back to the shipped cyan alone."""
    good = settings.validated_preview({"selection_color": "#FF5A00"})
    assert good["selection_color"] == "#FF5A00"
    for bad in ("purple", "00c8dc", "#00c8d", 42, None):
        section = settings.validated_preview({"selection_color": bad})
        assert section["selection_color"] == "#00c8dc"
