"""Direct ProfilesController tests.

Tests in this module exercise the controller's private state, locks, and
worker machinery using a ProfilesController fixture with deterministic named
ports.  They do not go through the Api facade.

Facade/integration tests (return payloads, settings persistence, JSON transport)
stay in tests/test_api_evesettings.py.
"""

import dataclasses
import hashlib
import json
import threading
import zipfile
from functools import partial
from pathlib import Path

import pytest

from wingman import paths, settings
from wingman.evesettings import backup as backup_mod
from wingman.evesettings import codec as codec_mod
from wingman.evesettings import controller as ctrl_mod
from wingman.evesettings import formations as formations_mod
from wingman.evesettings import identity as evesettings_identity
from wingman.evesettings import profilecopy as profilecopy_mod
from wingman.evesettings import tree
from wingman.evesettings.controller import (
    ProfilesController,
    ProfilesPorts,
    _EveCandidate,
)
from wingman.ui import copy as copy_mod

# ---------------------------------------------------------------------------
# Thread doubles
# ---------------------------------------------------------------------------


class ImmediateThread:
    """Runs the worker inline, so a test never races a real thread."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


class QueuedThreads:
    """A spawn seam a test drives by hand, to observe the coordinator."""

    def __init__(self):
        self.queued = []

    def spawn(self, *, target, args=(), daemon=True):
        queued = self.queued

        class Handle:
            def start(self):
                queued.append(lambda: target(*args))

        return Handle()

    def run_next(self):
        self.queued.pop(0)()


# ---------------------------------------------------------------------------
# Controller fixture
# ---------------------------------------------------------------------------

TRUSTED_SERVER = "c_ccp_eve_tq_tranquility"


def eve_tree(
    tmp_path, files=("core_char_1.dat", "core_char_2.dat"), server=TRUSTED_SERVER
):
    profile = tmp_path / "EVE" / server / "settings_Default"
    profile.mkdir(parents=True)
    for name in files:
        (profile / name).write_bytes(b"payload-" + name.encode())
    return profile


def build_controller(tmp_path, *, answer=True, spawn=None):
    """Construct a ProfilesController with deterministic ports.

    Named ports use call-time resolution so tests can swap them after
    construction with dataclasses.replace(controller._ports, ...).
    """
    cfg = settings.load(tmp_path / "settings.json")
    running_pushes = []
    names_pushes = []
    done_pushes = []
    alerts = []
    statuses = []

    if spawn is None:

        def spawn_port(*, target, args=(), daemon=True):
            return ImmediateThread(target=target, args=args, daemon=daemon)

    else:
        spawn_port = spawn

    ports = ProfilesPorts(
        publish_running=running_pushes.append,
        publish_names=names_pushes.append,
        publish_done=done_pushes.append,
        alert=lambda kind, title, body: alerts.append((kind, title, body)),
        status=lambda text: statuses.append(text),
        confirm=lambda title, body, **kw: answer,
        choose_root=lambda initial: "",
        spawn=spawn_port,
        advisory_client_running=lambda: False,
        strict_client_running=lambda: False,
        profile_copy_refusal=lambda: None,
        backup_root=paths.eve_settings_backup_dir,
        update_settings=lambda values: settings.update_section(
            cfg, "eve_settings", values
        ),
        format_copy_confirm=copy_mod.format_eve_copy_confirm,
        format_copy_done=copy_mod.format_eve_copy_done,
    )
    controller = ProfilesController(cfg, ports=ports)
    controller._running_pushes = running_pushes
    controller._names_pushes = names_pushes
    controller._done_pushes = done_pushes
    controller._alerts = alerts
    controller._statuses = statuses
    return controller


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def fake_status(controller, monkeypatch, names=None, deleted=(), seen=None, error=None):
    """Answer both ESI paths from memory without hitting the network."""

    def resolve(ids, *args, **kwargs):
        if seen is not None:
            seen.append(list(ids))
        if error is not None:
            raise error
        return dict(names or {}), {int(i) for i in deleted}

    monkeypatch.setattr(ctrl_mod.evesettings_characters, "resolve", resolve)
    controller._eve_names.resolve_missing = lambda ids, **kwargs: False


def _pending_identification(
    controller, account_id="10", character_ids=("20",), generation=None
):
    """An observation and the offer it authorized, as a check leaves them."""
    controller._eve_identification = evesettings_identity.Snapshot(
        Path("root"), Path("server"), Path("profile"), {}
    )
    _offer_candidate(controller, account_id, character_ids, generation)


def _offer_candidate(
    controller, account_id="10", character_ids=("20",), generation=None
):
    """Publish an offer, authorized by the current generation by default."""
    controller._eve_identification_candidate = _EveCandidate(
        controller._eve_identification_generation if generation is None else generation,
        account_id,
        tuple(character_ids),
    )


def offered(controller):
    """The offered pair without its generation, for comparison."""
    candidate = controller._eve_identification_candidate
    if candidate is None:
        return None
    return (candidate.account_id, candidate.character_ids)


def mark_deleted(controller, *character_ids, datasource="tranquility"):
    """Record ESI deletion verdicts the way a resolver pass would."""
    for character_id in character_ids:
        controller._eve_deleted.add((datasource, int(character_id)))


# ---------------------------------------------------------------------------
# Selective copy confirmation safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("groups", [["windows"], []])
@pytest.mark.parametrize("after_confirm", ["running", "probe_error", "declined"])
def test_selective_copy_refuses_without_filesystem_work_after_confirmation(
    tmp_path, monkeypatch, groups, after_confirm
):
    profile = eve_tree(tmp_path)
    source = profile / "core_char_1.dat"
    target = profile / "core_char_2.dat"
    workers = QueuedThreads()
    controller = build_controller(tmp_path, spawn=workers.spawn)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    confirmed = False

    def probe():
        if not confirmed:
            return False
        if after_confirm == "probe_error":
            raise OSError("window station unavailable")
        return True

    def confirm(title, body, **kwargs):
        nonlocal confirmed
        confirmed = True
        return after_confirm != "declined"

    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=probe, confirm=confirm
    )
    monkeypatch.setattr(
        ctrl_mod.evesettings_ops,
        "copy_selected_to_targets",
        lambda *args, **kwargs: pytest.fail("selective filesystem work must not start"),
    )

    assert controller.copy(str(source), [str(target)], groups) is True
    workers.run_next()

    assert confirmed
    assert target.read_bytes() == b"payload-core_char_2.dat"
    assert source.read_bytes() == b"payload-core_char_1.dat"
    assert not paths.eve_settings_backup_dir().exists()
    assert controller._done_pushes == [{"ok": False}]
    assert controller._statuses == []
    if after_confirm == "declined":
        assert controller._alerts == []
    else:
        [(kind, title, body)] = controller._alerts
        assert (kind, title) == ("error", "Copy not started")
        assert "Close EVE" in body
        assert ("could not verify" in body) is (after_confirm == "probe_error")

    # A refusal must release the gate, and legacy copy must still be advisory
    # even when the strict probe can no longer prove EVE is closed.
    controller._ports = dataclasses.replace(
        controller._ports,
        confirm=lambda *args, **kwargs: True,
        advisory_client_running=lambda: True,
    )
    assert controller.copy(str(source), [str(target)]) is True
    workers.run_next()
    assert target.read_bytes() == b"payload-core_char_1.dat"
    assert controller._done_pushes == [{"ok": False}, {"ok": True}]
    [archive] = paths.eve_settings_backup_dir().rglob("*.zip")
    with zipfile.ZipFile(archive) as saved:
        assert b"payload-core_char_2.dat" in (
            saved.read(name) for name in saved.namelist()
        )


@pytest.mark.parametrize(
    ("groups", "expected_windows"), [(["windows"], "source"), ([], "target")]
)
def test_selective_copy_rechecks_closed_before_real_copy_and_backup(
    tmp_path, monkeypatch, groups, expected_windows
):
    profile = eve_tree(tmp_path)
    source = profile / "core_char_1.dat"
    target = profile / "core_char_2.dat"
    for path, label in ((source, "source"), (target, "target")):
        path.write_bytes(
            b"\x7d"
            + json.dumps(
                {
                    "had_crc": False,
                    "doc": {"bytes:windows": {"tuple": [label]}, "bytes:ui": {}},
                }
            ).encode()
        )
    original = target.read_bytes()
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    order = []

    def probe():
        order.append("probe")
        return False

    def confirm(*args, **kwargs):
        order.append("confirm")
        return True

    def codec_filter(mode, payload, **kwargs):
        # Only the sidecar filter is substituted: real ops, codec verification,
        # backup creation, and atomic publication still operate on temp files.
        order.append(mode)
        return b"\x7d" + payload if mode == "encode" else payload[1:]

    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=probe, confirm=confirm
    )
    monkeypatch.setattr(codec_mod, "_run", codec_filter)

    assert controller.copy(str(source), [str(target)], groups) is True

    assert controller._alerts == []
    assert controller._done_pushes == [{"ok": True}]
    assert controller._statuses
    assert order[:4] == ["probe", "confirm", "probe", "decode"]
    assert json.loads(target.read_bytes()[1:])["doc"]["bytes:windows"] == {
        "tuple": [expected_windows]
    }
    [archive] = paths.eve_settings_backup_dir().rglob("*.zip")
    with zipfile.ZipFile(archive) as saved:
        assert original in (saved.read(name) for name in saved.namelist())
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


# ---------------------------------------------------------------------------
# Mutation lock
# ---------------------------------------------------------------------------


def test_a_second_mutation_is_refused_while_one_holds_the_lock(tmp_path, monkeypatch):
    """_confirm parks each worker independently, so without a lock two
    approved operations can interleave over the same files."""
    profile = eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._eve_mutation.acquire()
    try:
        accepted = controller.copy(
            str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
        )
    finally:
        controller._eve_mutation.release()
    assert accepted is False
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_the_lock_is_released_even_when_the_worker_raises(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ctrl_mod.evesettings_ops, "copy_to_targets", explode)
    controller.copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert controller._eve_mutation.acquire(blocking=False) is True
    controller._eve_mutation.release()


def test_a_failed_spawn_does_not_strand_the_mutation_lock(tmp_path, monkeypatch):
    """Only the worker releases the lock, and a worker that never started
    never will -- every later operation would be refused for good."""
    profile = eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")

    class Refuses:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    controller._ports = dataclasses.replace(
        controller._ports,
        spawn=lambda *, target, args=(), daemon=True: Refuses(),
    )
    assert (
        controller.copy(
            str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
        )
        is False
    )
    assert controller._eve_mutation.acquire(blocking=False) is True
    controller._eve_mutation.release()


def test_selecting_is_refused_while_a_mutation_holds_the_lock(tmp_path, monkeypatch):
    """`root` is an input to every containment check, so changing it under
    an in-flight restore has that operation validate against a different
    root than the one in effect when the user approved it."""
    profile = eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._eve_mutation.acquire()
    try:
        assert controller.select(str(profile.parent), str(profile)) is False
        assert controller._eve_section()["server"] is None
    finally:
        controller._eve_mutation.release()
    assert controller.select(str(profile.parent), str(profile)) is True


def test_picking_a_root_is_refused_while_a_mutation_holds_the_lock(tmp_path):
    eve_tree(tmp_path)
    opened = []

    def dialog(initial):
        opened.append(initial)
        return str(tmp_path / "EVE")

    controller = build_controller(tmp_path)
    controller._ports = dataclasses.replace(controller._ports, choose_root=dialog)
    controller._eve_mutation.acquire()
    try:
        assert controller.pick_root() == ""
        assert opened == []
    finally:
        controller._eve_mutation.release()
    assert controller.pick_root() == str(tmp_path / "EVE")
    assert controller._settings["eve_settings"]["root"] == str(tmp_path / "EVE")


def test_selecting_releases_the_lock_for_the_next_mutation(tmp_path, monkeypatch):
    """A hold that leaked would refuse every later copy, backup, restore
    and delete until the app restarted."""
    eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    controller.select("s", "p")
    assert controller._eve_mutation.acquire(blocking=False) is True
    controller._eve_mutation.release()


def test_a_pick_root_that_raises_still_releases_the_lock(tmp_path, monkeypatch):
    eve_tree(tmp_path)

    def boom(initial):
        raise RuntimeError("no dialog here")

    controller = build_controller(tmp_path)
    controller._ports = dataclasses.replace(controller._ports, choose_root=boom)
    with pytest.raises(RuntimeError):
        controller.pick_root()
    assert controller._eve_mutation.acquire(blocking=False) is True
    controller._eve_mutation.release()


def test_save_holds_and_releases_the_mutation_lock(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_1.dat",))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    store = _fake_codec(monkeypatch, {})
    queued = QueuedThreads()
    controller._ports = dataclasses.replace(controller._ports, spawn=queued.spawn)
    assert controller.save_formations(
        str(profile / "core_user_1.dat"), [], "a" * 64, "lock:1"
    )
    assert not controller._eve_mutation.acquire(blocking=False)
    assert store["written"] == [] and controller._done_pushes == []
    queued.run_next()
    assert len(store["written"]) == 1
    (done,) = controller._done_pushes
    assert done["ok"] is True
    assert done["request_id"] == "lock:1" and done["content_revision"] == "b" * 64
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


# ---------------------------------------------------------------------------
# Advisory running probe
# ---------------------------------------------------------------------------


def test_state_reads_the_running_pill_from_cache_not_a_fresh_probe(
    tmp_path, monkeypatch
):
    """eve_settings_state is costed in the design as scandir over a few
    dozen files. list_clients() enumerates every top-level window and
    resolves PIDs to executables, which is not that -- so it runs on a
    background thread and state reads the last known answer."""
    eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    calls = []
    controller._eve_refresh_running = lambda: calls.append(1)
    controller._eve_running = True

    controller._eve_section()["root"] = str(tmp_path / "EVE")
    assert controller.state()["eve_running"] is True
    assert calls == [1]


def test_the_running_probe_pushes_only_when_the_answer_changes(tmp_path, monkeypatch):
    """One push per change, not per refresh."""
    eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    pushed = controller._running_pushes

    controller._ports = dataclasses.replace(
        controller._ports, advisory_client_running=lambda: False
    )
    controller._eve_refresh_running()
    assert pushed == [{"running": False}]

    controller._eve_refresh_running()
    assert len(pushed) == 1, "no change, so nothing to push"

    controller._ports = dataclasses.replace(
        controller._ports, advisory_client_running=lambda: True
    )
    controller._eve_refresh_running()
    assert pushed[-1] == {"running": True}
    assert len(pushed) == 2 and controller._eve_running is True

    controller._eve_refresh_running()
    assert len(pushed) == 2, "no change, so nothing to push"


def test_a_probe_that_raises_leaves_the_pill_alone(tmp_path, monkeypatch):
    """Advisory only. A failed probe must never surface as an error."""
    eve_tree(tmp_path)
    controller = build_controller(tmp_path)
    pushed = controller._running_pushes

    def boom():
        raise OSError("no window station")

    controller._ports = dataclasses.replace(
        controller._ports, advisory_client_running=boom
    )
    controller._eve_refresh_running()
    assert pushed == [] and controller._eve_running is None


def test_a_second_probe_is_skipped_while_one_is_in_flight(tmp_path, monkeypatch):
    """Without single-flight a slow probe finishing after a fast one publishes
    the OLDER observation and leaves it cached."""
    eve_tree(tmp_path)
    threads = QueuedThreads()
    controller = build_controller(tmp_path, spawn=threads.spawn)
    controller._eve_refresh_running()
    controller._eve_refresh_running()
    assert len(threads.queued) == 1, "a second probe was spawned over the first"


def test_a_probe_that_cannot_be_spawned_does_not_wedge_the_lock(tmp_path, monkeypatch):
    """Only the worker releases, and a worker that never started never
    will -- that would freeze the pill for the process's lifetime."""
    eve_tree(tmp_path)

    def no_thread(*, target, args=(), daemon=True):
        raise RuntimeError("can't start new thread")

    controller = build_controller(tmp_path)
    controller._ports = dataclasses.replace(controller._ports, spawn=no_thread)
    controller._eve_refresh_running()
    assert controller._eve_probe.acquire(blocking=False) is True
    controller._eve_probe.release()


def test_the_probe_releases_its_lock_even_when_it_raises(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    controller = build_controller(tmp_path)

    def boom():
        raise OSError("no window station")

    controller._ports = dataclasses.replace(
        controller._ports, advisory_client_running=boom
    )
    controller._eve_refresh_running()
    assert controller._eve_probe.acquire(blocking=False) is True
    controller._eve_probe.release()


# ---------------------------------------------------------------------------
# Identification transitions and generations
# ---------------------------------------------------------------------------


def test_identification_starts_with_no_snapshot_or_candidate(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    assert controller._eve_identification is None
    assert controller._eve_identification_candidate is None


def test_identification_start_replaces_an_old_candidate_and_check_records_latest_pair(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    _offer_candidate(controller, "old", ("candidate",))

    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    assert controller.identification_start()["status"] == "watching"
    assert controller._eve_identification_candidate is None
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_20.dat").write_bytes(b"changed character")

    assert controller.identification_check()["status"] == "candidate"
    assert offered(controller) == ("10", ("20",))


def test_identification_check_clears_obsolete_candidate_on_no_change(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    assert controller.identification_start()["status"] == "watching"
    _offer_candidate(controller)

    result = controller.identification_check()

    assert result == {
        "status": "none",
        "error": "No account and character changes were found. Make a small settings change in the client, then close it completely and check again.",
        "identification_generation": 1,
    }
    assert controller._eve_identification is not None
    assert controller._eve_identification_candidate is None


def test_identification_check_clears_candidate_on_ambiguity_and_invalidation(
    tmp_path, monkeypatch
):
    profile = eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    assert controller.identification_start()["status"] == "watching"
    _offer_candidate(controller)
    for name in ("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"):
        (profile / name).write_bytes(b"changed with a different size " + name.encode())

    assert controller.identification_check()["status"] == "ambiguous"
    assert controller._eve_identification_candidate is None
    _offer_candidate(controller)
    (profile / "core_char_20.dat").unlink()

    invalidated = controller.identification_check()

    assert invalidated["status"] == "invalidated"
    assert invalidated["identification_generation"] == 2
    assert controller._eve_identification is None
    assert controller._eve_identification_candidate is None


def test_identification_check_preserves_snapshot_but_clears_candidate_while_eve_runs(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    assert controller.identification_start()["status"] == "watching"
    snapshot = controller._eve_identification
    _offer_candidate(controller)
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: True
    )

    assert controller.identification_check()["status"] == "watching"
    assert controller._eve_identification is snapshot
    assert controller._eve_identification_candidate is None


def test_identification_responses_carry_a_monotonic_generation(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    controller._eve_names.names[20] = "Aiga Otsolen"

    started = controller.identification_start()
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_20.dat").write_bytes(b"changed character")
    checked = controller.identification_check()
    cancelled = controller.identification_cancel()
    restarted = controller.identification_start()

    assert started == {
        "status": "watching",
        "error": None,
        "identification_generation": 1,
    }
    assert checked == {
        "status": "candidate",
        "error": None,
        "account": checked["account"],
        "characters": [{"id": "20", "name": "Aiga Otsolen"}],
        "identification_generation": 1,
    }
    assert cancelled == {
        "status": "idle",
        "error": None,
        "identification_generation": 2,
    }
    assert restarted["identification_generation"] == 3


def test_a_cancel_racing_start_publication_discards_the_observation(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    real_snapshot = ctrl_mod.evesettings_identity.take_snapshot
    taking = threading.Event()

    def cancel_during_snapshot(found):
        taking.set()
        canceller = threading.Thread(target=controller.identification_cancel)
        canceller.start()
        canceller.join(5)
        assert not canceller.is_alive(), "cancellation waited for the mutation lock"
        return real_snapshot(found)

    monkeypatch.setattr(
        ctrl_mod.evesettings_identity, "take_snapshot", cancel_during_snapshot
    )

    result = controller.identification_start()

    assert taking.is_set()
    assert result == {
        "status": "cancelled",
        "error": None,
        "identification_generation": 2,
    }
    assert controller._eve_identification is None


def test_a_cancel_racing_a_candidate_discards_the_offer(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    assert controller.identification_start()["status"] == "watching"
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_20.dat").write_bytes(b"changed character")

    def cancel_while_probing():
        canceller = threading.Thread(target=controller.identification_cancel)
        canceller.start()
        canceller.join(5)
        assert not canceller.is_alive(), "cancellation waited for the mutation lock"
        return False

    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=cancel_while_probing
    )

    result = controller.identification_check()

    assert result == {
        "status": "cancelled",
        "error": None,
        "identification_generation": 2,
    }
    assert controller._eve_identification is None
    assert controller._eve_identification_candidate is None


def test_cancellation_is_never_blocked_by_the_mutation_lock(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    _pending_identification(controller)
    controller._eve_mutation.acquire()
    try:
        canceller = threading.Thread(target=controller.identification_cancel)
        canceller.start()
        canceller.join(5)

        assert not canceller.is_alive(), "cancellation waited for the mutation lock"
        assert controller._eve_identification is None
        assert controller._eve_identification_candidate is None
        assert controller._eve_identification_generation == 1
    finally:
        controller._eve_mutation.release()


def test_confirmation_refuses_an_offer_from_an_older_generation(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    _pending_identification(
        controller, generation=controller._eve_identification_generation - 1
    )

    result = controller.identification_confirm("10", "20", "Login")

    assert result["applied"] is False
    assert result["error"] == "Start account identification again."
    assert controller._eve_section()["account_names"] == {}
    assert controller._eve_section()["account_characters"] == {}


# ---------------------------------------------------------------------------
# Resolver coordination and cache
# ---------------------------------------------------------------------------


def test_a_second_request_coalesces_into_one_trailing_pass(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_char_20.dat",))
    threads = QueuedThreads()
    controller = build_controller(tmp_path, spawn=threads.spawn)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._eve_refresh_running = lambda: None
    seen = []
    fake_status(controller, monkeypatch, seen=seen)

    controller.resolve_names()
    controller.resolve_names()
    controller.resolve_names()

    assert len(threads.queued) == 1
    threads.run_next()
    assert len(threads.queued) == 1, "the two later requests coalesced into one"
    threads.run_next()

    assert threads.queued == []
    assert seen == [[20], [20]]
    assert controller._eve_resolve_running is False
    assert controller._eve_resolve_pending is False


def test_switching_profiles_during_a_pass_resolves_the_new_one(tmp_path, monkeypatch):
    first = eve_tree(tmp_path, files=("core_char_20.dat",))
    second = first.parent / "settings_Other"
    second.mkdir()
    (second / "core_char_30.dat").write_bytes(b"payload")
    threads = QueuedThreads()
    controller = build_controller(tmp_path, spawn=threads.spawn)
    section = controller._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["profile"] = str(first)
    controller._eve_refresh_running = lambda: None
    controller._eve_names.resolve_missing = lambda ids, **kwargs: False
    seen = []

    def switch_while_resolving(ids, *args, **kwargs):
        seen.append(list(ids))
        if section["profile"] == str(first):
            section["profile"] = str(second)
            controller.resolve_names()
        return {}, set()

    monkeypatch.setattr(
        ctrl_mod.evesettings_characters, "resolve", switch_while_resolving
    )

    controller.resolve_names()
    threads.run_next()

    assert len(threads.queued) == 1, "the request made mid-pass owes one more"
    threads.run_next()

    assert seen == [[20], [30]]
    assert threads.queued == []


def test_a_stale_pass_caches_facts_but_cannot_clean_or_push_another_profile(
    tmp_path, monkeypatch
):
    first = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_21.dat"))
    second = first.parent / "settings_Other"
    second.mkdir()
    (second / "core_char_30.dat").write_bytes(b"payload")
    controller = build_controller(tmp_path)
    section = controller._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["profile"] = str(first)
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["21"]}
    controller._eve_names.resolve_missing = lambda ids, **kwargs: False

    def switch_then_report(ids, *args, **kwargs):
        section["profile"] = str(second)
        return {}, {21}

    monkeypatch.setattr(ctrl_mod.evesettings_characters, "resolve", switch_then_report)

    controller.resolve_names()

    assert ("tranquility", 21) in controller._eve_deleted
    assert controller._eve_section()["account_characters"] == {"10": ["21"]}
    assert controller._names_pushes == []


def test_a_pass_publishes_cached_facts_newly_applicable_to_its_profile(
    tmp_path, monkeypatch
):
    """What a stale pass learned still has to reach the selected profile,
    and only once: application is tracked apart from the remote cache."""
    eve_tree(tmp_path, files=("core_char_20.dat",))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    controller._eve_names.names[20] = "Alpha"
    fake_status(controller, monkeypatch)

    controller.resolve_names()
    assert len(controller._names_pushes) == 1

    controller.resolve_names()
    assert len(controller._names_pushes) == 1


def test_active_ids_are_rechecked_while_deleted_ids_are_never_fetched_again(
    tmp_path, monkeypatch
):
    """Active is not a cacheable verdict -- a character deleted during a long
    session must still be found -- while deleted is monotonic."""
    eve_tree(tmp_path, files=("core_char_20.dat", "core_char_21.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    seen = []
    fake_status(controller, monkeypatch, names={20: "Alpha"}, deleted={21}, seen=seen)

    controller.resolve_names()
    controller.resolve_names()

    assert seen == [[20, 21], [20]]


def test_a_resolver_that_cannot_spawn_clears_its_running_state(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_char_20.dat",))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")

    def refuses(*, target, args=(), daemon=True):
        raise RuntimeError("can't start new thread")

    controller._ports = dataclasses.replace(controller._ports, spawn=refuses)

    controller.resolve_names()

    assert controller._eve_resolve_running is False
    assert controller._eve_resolve_pending is False


def test_a_resolver_that_raises_clears_its_running_state(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_char_20.dat",))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    fake_status(controller, monkeypatch, error=RuntimeError("ESI exploded"))

    controller.resolve_names()

    assert controller._eve_resolve_running is False
    assert controller._eve_resolve_pending is False


def test_cleanup_clears_an_identification_candidate_it_invalidates(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_21.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    fake_status(controller, monkeypatch, deleted={21})
    _pending_identification(controller, "10", ("21",))

    controller.resolve_names()

    assert controller._eve_identification is None
    assert controller._eve_identification_candidate is None
    assert controller._names_pushes != []


def test_an_unrelated_identification_candidate_survives_a_deletion(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_21.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    fake_status(controller, monkeypatch, deleted={21})
    _pending_identification(controller, "10", ("20",))

    controller.resolve_names()

    assert offered(controller) == ("10", ("20",))
    assert controller._names_pushes == [
        {"identification_generation": 0, "deleted_candidate_ids": []}
    ]


# ---------------------------------------------------------------------------
# Account identity static helpers
# ---------------------------------------------------------------------------


def test_account_identity_helpers_preserve_shared_validation_and_relinking_rules(
    tmp_path, monkeypatch
):
    controller = build_controller(tmp_path)

    assert controller._eve_validate_account_name("10", " Login ", {"11": "Other"}) == (
        "Login",
        None,
    )
    assert controller._eve_validate_account_name("10", "other", {"11": "Other"}) == (
        None,
        "That EVE Online username is already assigned to another account.",
    )
    assert controller._eve_relink_account_characters(
        {"10": ["21"], "11": ["20"]}, "10", ["20"], ["21", "20"]
    ) == ({"10": ["21", "20"]}, None)
    assert controller._eve_relink_account_characters(
        {"10": ["21", "22", "23"]}, "10", ["20"], ["21", "22", "23", "20"]
    ) == (None, "An EVE account can have up to three characters.")


# ---------------------------------------------------------------------------
# Manual identity work under mutation lock (direct)
# ---------------------------------------------------------------------------


def test_manual_identity_name_and_roster_work_stays_under_the_mutation_lock(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    original_discover = controller._eve_discover
    original_update = ctrl_mod.settings_mod.update_section

    def checked_discover():
        assert controller._eve_mutation.locked()
        return original_discover()

    def checked_update(*args, **kwargs):
        assert controller._eve_mutation.locked()
        return original_update(*args, **kwargs)

    monkeypatch.setattr(controller, "_eve_discover", checked_discover)
    monkeypatch.setattr(ctrl_mod.settings_mod, "update_section", checked_update)

    assert controller.set_account_name("10", "LoginName")["applied"] is True
    assert controller.set_account_characters("10", ["20"])["applied"] is True


# ---------------------------------------------------------------------------
# Formations helpers and direct orchestration
# ---------------------------------------------------------------------------


def controller_account_setup(tmp_path, name="core_user_1.dat"):
    profile = eve_tree(tmp_path, files=(name,))
    controller = build_controller(tmp_path)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    return controller, profile / name


FORMATION_DOC = {
    "bytes:ui": {
        "bytes:probescanning.customFormations": {
            "tuple": [
                "long:1",
                {
                    "int:0": {
                        "tuple": [
                            "utf8:Test",
                            [{"tuple": [{"tuple": [1.0, 2.0, 3.0]}, 4.0]}],
                        ]
                    },
                    "int:-4": {"tuple": ["bytes:tempFormation", []]},
                },
            ]
        },
        "bytes:probescanning.selectedFormationID": {"tuple": ["long:1", 0]},
    }
}


def _fake_codec(monkeypatch, doc, *, available=True):
    """In-memory snapshots for orchestration tests, not publication evidence."""
    store = {"doc": doc, "written": []}

    def read_document(path, **kw):
        return codec_mod.Document(doc=store["doc"], had_crc=False)

    def read_snapshot(path, **kw):
        return codec_mod.DocumentSnapshot(read_document(path), "a" * 64)

    def write_document(path, document, *, backup, expected_content_revision, **kw):
        assert expected_content_revision == "a" * 64
        backup(path)
        store["written"].append((path, document))
        return "b" * 64

    monkeypatch.setattr(codec_mod, "read_snapshot", read_snapshot)
    monkeypatch.setattr(codec_mod, "read_document", read_document)
    monkeypatch.setattr(codec_mod, "write_document", write_document)
    monkeypatch.setattr(codec_mod, "codec_available", lambda **kw: available)
    return store


def test_formations_read_refuses_a_path_outside_the_root(tmp_path, monkeypatch):
    controller, _account = controller_account_setup(tmp_path)
    _fake_codec(monkeypatch, FORMATION_DOC)
    outside = tmp_path / "elsewhere" / "core_user_9.dat"
    outside.parent.mkdir()
    outside.write_bytes(b"")
    got = controller.formations(str(outside))
    assert got["ok"] is False and "outside" in got["error"]


def test_formations_read_refuses_a_character_file(tmp_path, monkeypatch):
    controller, char = controller_account_setup(tmp_path, name="core_char_1.dat")
    _fake_codec(monkeypatch, FORMATION_DOC)
    got = controller.formations(str(char))
    assert got["ok"] is False and "account" in got["error"]


def test_formations_read_reports_a_codec_failure_as_an_error_not_an_exception(
    tmp_path, monkeypatch
):
    controller, account = controller_account_setup(tmp_path)

    def boom(path, **kw):
        raise codec_mod.CodecError("bad header")

    monkeypatch.setattr(codec_mod, "read_snapshot", boom)
    got = controller.formations(str(account))
    assert got == {"ok": False, "error": "bad header"}

    # A document that decodes cleanly but is not something read_formations
    # understands must not open the editor on a partial parse either --
    # write_formations would rebuild the key from whatever was returned and
    # silently drop the part it could not read.
    _fake_codec(monkeypatch, FORMATION_DOC)

    def refuse(doc):
        raise ValueError("This file has a formation entry Wingman does not understand.")

    monkeypatch.setattr(formations_mod, "read_formations", refuse)
    got = controller.formations(str(account))
    assert got == {
        "ok": False,
        "error": "This file has a formation entry Wingman does not understand.",
    }


def test_save_is_refused_when_the_strict_running_probe_fails(tmp_path, monkeypatch):
    controller, account = controller_account_setup(tmp_path)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    backups = []
    controller._eve_auto_backup = lambda path: backups.append(path)

    def boom():
        raise OSError("window station unavailable")

    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=boom
    )
    controller.save_formations(str(account), [], "a" * 64, "probe:1")

    assert store["written"] == [] and backups == []
    assert len(controller._alerts) == 1
    assert "Close EVE" in controller._alerts[0][2]


def test_save_is_refused_while_an_eve_client_is_running(tmp_path, monkeypatch):
    controller, account = controller_account_setup(tmp_path)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: True
    )
    controller.save_formations(str(account), [], "a" * 64, "running:1")
    assert store["written"] == []
    assert len(controller._alerts) == 1 and "Close EVE" in controller._alerts[0][2]
    assert controller._done_pushes == [
        {
            "ok": False,
            "operation": "formations_save",
            "path": str(account),
            "request_id": "running:1",
            "content_revision": "",
            "error_code": "save_failed",
            "error": "The file is in use. Close EVE and retry.",
            "warning": "",
        }
    ]
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


def test_save_rejects_an_invalid_formation_before_touching_the_file(
    tmp_path, monkeypatch
):
    controller, account = controller_account_setup(tmp_path)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    controller._ports = dataclasses.replace(
        controller._ports, strict_client_running=lambda: False
    )
    backups = []
    controller._eve_auto_backup = lambda path: backups.append(path)
    controller.save_formations(
        str(account), [{"id": None, "name": "", "probes": []}], "a" * 64, "invalid:1"
    )
    assert store["written"] == [] and backups == []
    assert "needs a name" in controller._alerts[0][2]


@pytest.mark.parametrize("refusal", ["busy", "identification", "spawn"])
def test_formation_save_admission_refusal_never_publishes_done(
    tmp_path, monkeypatch, refusal
):
    controller, account = controller_account_setup(tmp_path)
    before = account.read_bytes()

    def no_read(*args, **kwargs):
        pytest.fail("a refused save never starts account work")

    monkeypatch.setattr(codec_mod, "read_snapshot", no_read)
    if refusal == "busy":
        controller._eve_mutation.acquire()
    elif refusal == "identification":
        controller._eve_identification = object()
    else:

        def refuse_spawn(**kwargs):
            raise RuntimeError("worker unavailable")

        controller._ports = dataclasses.replace(controller._ports, spawn=refuse_spawn)
    try:
        assert (
            controller.save_formations(str(account), [], "a" * 64, "refused:1") is False
        )
        assert controller._done_pushes == []
        assert len(controller._alerts) == 1
        assert account.read_bytes() == before
        assert not list(paths.eve_settings_backup_dir().glob("*.zip"))
        assert controller._eve_mutation.locked() is (refusal == "busy")
    finally:
        if refusal == "busy":
            controller._eve_mutation.release()
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


@pytest.mark.parametrize("outcome", ["saved", "stale", "publish-failure"])
def test_formation_save_direct_boundary_preserves_bytes_correlation_and_completion(
    tmp_path, monkeypatch, outcome
):
    """Real snapshots, guarded publication and backups, without an Api instance."""
    controller, account = controller_account_setup(tmp_path)
    before = b"\x7d" + json.dumps({"doc": FORMATION_DOC, "had_crc": True}).encode()
    account.write_bytes(before)

    # Only replace the external filter: verifying decode consumes encoded bytes.
    def filter_bytes(mode, payload, **kwargs):
        if mode == "encode":
            return b"\x7d" + payload
        assert mode == "decode" and payload.startswith(b"\x7d")
        return payload[1:]

    monkeypatch.setattr(codec_mod, "_run", filter_bytes)
    loaded = controller.formations(str(account))
    assert loaded["ok"]
    assert loaded["content_revision"] == hashlib.sha256(before).hexdigest()
    wanted = [
        {"id": None, "name": "New", "probes": [{"x": 1, "y": 2, "z": 3, "range": 4}]}
    ]
    queued = QueuedThreads()
    lock_at_done = []

    def done(payload):
        lock_at_done.append(controller._eve_mutation.locked())
        controller._done_pushes.append(payload)

    controller._ports = dataclasses.replace(
        controller._ports, spawn=queued.spawn, publish_done=done
    )
    prunes = []
    real_prune = controller._eve_prune

    def prune(keep):
        prunes.append(keep)
        return real_prune(keep)

    controller._eve_prune = prune
    if outcome == "publish-failure":

        def refuse_publish(*args, **kwargs):
            raise OSError("publication unavailable")

        monkeypatch.setattr(
            codec_mod,
            "write_document",
            partial(codec_mod.write_document, publish=refuse_publish),
        )
    assert controller.save_formations(
        str(account), wanted, loaded["content_revision"], "direct:1"
    )
    assert controller._eve_mutation.locked()
    assert controller._done_pushes == []
    assert not controller.formations(str(account))["ok"]
    if outcome == "stale":
        changed = before + b" "
        account.write_bytes(changed)

        def no_write(*args, **kwargs):
            pytest.fail(
                "a stale snapshot must be refused before encoding or backing up"
            )

        monkeypatch.setattr(codec_mod, "write_document", no_write)
    queued.run_next()
    (payload,) = controller._done_pushes
    assert lock_at_done == [False]
    assert payload["operation"] == "formations_save"
    assert payload["path"] == str(account) and payload["request_id"] == "direct:1"
    assert payload["warning"] == ""
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()
    archives = list(paths.eve_settings_backup_dir().glob("*.zip"))
    if outcome == "stale":
        assert payload["ok"] is False and payload["error_code"] == "stale_file"
        assert payload["content_revision"] == ""
        assert "Nothing was saved" in payload["error"]
        assert account.read_bytes() == changed
        assert archives == [] and prunes == []
    else:
        (archive,) = archives
        with zipfile.ZipFile(archive) as backup:
            assert backup.read(account.name) == before
        if outcome == "publish-failure":
            assert payload["ok"] is False and payload["error_code"] == "save_failed"
            assert payload["content_revision"] == ""
            assert "publication unavailable" in payload["error"]
            assert account.read_bytes() == before and prunes == []
        else:
            assert payload["ok"] is True
            assert payload["error"] == payload["error_code"] == ""
            assert (
                payload["content_revision"]
                == hashlib.sha256(account.read_bytes()).hexdigest()
            )
            assert payload["content_revision"] != loaded["content_revision"]
            assert prunes == [10]
            saved = formations_mod.to_payload(
                formations_mod.read_formations(codec_mod.read_document(account).doc)
            )
            assert saved == [{"id": 1, "name": "New", "probes": wanted[0]["probes"]}]


def test_formation_import_direct_boundary_needs_no_runtime_state():
    # Accessing settings, ports or an account fails: none exist on this instance.
    controller = ProfilesController.__new__(ProfilesController)
    items = [
        {
            "id": None,
            "name": " Straße ",
            "probes": [{"x": 1, "y": 0, "z": 0, "range": 149597870700}],
        }
    ]
    existing = ["STRASSE"]
    before = json.dumps([items, existing])
    exported = controller.export_formations(items)
    assert exported["ok"] is True
    parsed = controller.parse_formations(exported["text"], existing)
    validated = controller.validate_formation_import(items, existing)
    expected = {
        "ok": True,
        "formations": [
            {
                "id": None,
                "name": "Straße",
                "probes": [{"x": 1, "y": 0, "z": 0, "range": 149597870700}],
            }
        ],
        "conflicts": [0],
    }
    assert parsed == expected and validated == expected
    assert json.dumps([items, existing]) == before
    items[0]["id"] = 7
    rejected = controller.validate_formation_import(items, existing)
    assert set(rejected) == {"ok", "error"}
    assert rejected["ok"] is False and rejected["error"]
    assert json.loads(json.dumps(rejected)) == rejected


# ---------------------------------------------------------------------------
# Whole-profile copy helpers and direct orchestration
# ---------------------------------------------------------------------------


def copy_profile_setup(tmp_path, others=(), *, answer=True, spawn=None):
    source = eve_tree(tmp_path)
    for name in others:
        other = source.parent / f"{tree.PROFILE_PREFIX}{name}"
        other.mkdir()
        (other / "core_char_9.dat").write_bytes(b"old-9")
    controller = build_controller(tmp_path, answer=answer, spawn=spawn)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    return controller, source


def watch(order, label, func):
    def wrapper(*args, **kwargs):
        order.append(label)
        return func(*args, **kwargs)

    return wrapper


def order_spies(controller, monkeypatch):
    """Record the whole orchestration sequence, real behaviour intact."""
    order = []
    controller._eve_discover = watch(order, "discover", controller._eve_discover)
    controller._eve_persist_selection = watch(
        order, "persist", controller._eve_persist_selection
    )
    controller._ports = dataclasses.replace(
        controller._ports,
        confirm=watch(order, "confirm", controller._ports.confirm),
        profile_copy_refusal=watch(
            order, "probe", controller._ports.profile_copy_refusal
        ),
    )
    controller._eve_prune = watch(order, "prune", controller._eve_prune)
    controller._eve_done = watch(order, "done", controller._eve_done)
    for module, name, label in (
        (profilecopy_mod, "prepare_copy", "prepare"),
        (profilecopy_mod, "stage_copy", "stage"),
        (profilecopy_mod, "publish_new", "publish"),
        (profilecopy_mod, "publish_replacement", "publish"),
        (backup_mod, "create_profile_backup", "backup"),
    ):
        monkeypatch.setattr(module, name, watch(order, label, getattr(module, name)))
    return order


def stages_left(server):
    return [
        entry.name
        for entry in server.iterdir()
        if entry.name.startswith(profilecopy_mod.STAGE_PREFIX)
    ]


def failing_publication(monkeypatch, destination):
    """Break the second per-file replacement, so publication fails after it
    has already changed the destination."""
    real_copy = profilecopy_mod.atomicio.copy_atomic

    def flaky(source, target, **kwargs):
        if Path(target).parent == destination and Path(target).name.endswith("2.dat"):
            raise OSError("the destination went away")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr(profilecopy_mod.atomicio, "copy_atomic", flaky)


def test_profile_copy_releases_the_lock_when_the_worker_cannot_start(
    tmp_path, monkeypatch
):
    """Only the worker releases the lock, so a worker that never started
    would refuse every later Profiles operation for good."""
    source = eve_tree(tmp_path)

    class Refuses:
        def __init__(self, *, target=None, args=(), daemon=None):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    controller = build_controller(tmp_path, spawn=Refuses)
    controller._eve_section()["root"] = str(tmp_path / "EVE")
    result = controller.copy_profile(str(source), "new", "Fleet")
    assert result == {
        "accepted": False,
        "error": "Profile copy could not be started.",
    }
    assert controller._eve_mutation.acquire(blocking=False) is True
    controller._eve_mutation.release()


def test_profile_copy_runs_its_steps_in_the_documented_order(tmp_path, monkeypatch):
    controller, source = copy_profile_setup(tmp_path, others=("Backup",))
    order = order_spies(controller, monkeypatch)

    result = controller.copy_profile(
        str(source), "replace", str(source.parent / "settings_Backup")
    )

    assert result == {"accepted": True, "error": None}
    assert order == [
        "discover",
        "prepare",
        "persist",
        "probe",
        "stage",
        "confirm",
        "probe",
        "backup",
        "publish",
        "prune",
        "done",
    ]


def test_a_failed_publication_rolls_back_from_the_backup_it_just_took(
    tmp_path, monkeypatch
):
    controller, source = copy_profile_setup(tmp_path, others=("Backup",))
    destination = source.parent / "settings_Backup"
    archives = []
    real_backup = backup_mod.create_profile_backup

    def record(*args, **kwargs):
        archives.append(real_backup(*args, **kwargs))
        return archives[-1]

    restores = []
    real_restore = backup_mod.restore

    def watched_restore(store, archive, root, **kwargs):
        restores.append((Path(archive), kwargs))
        return real_restore(store, archive, root, **kwargs)

    monkeypatch.setattr(backup_mod, "create_profile_backup", record)
    monkeypatch.setattr(backup_mod, "restore", watched_restore)
    failing_publication(monkeypatch, destination)
    prunes = []
    controller._eve_prune = lambda *args, **kwargs: prunes.append(args)

    controller.copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert (destination / "core_char_9.dat").read_bytes() == b"old-9"
    assert restores == [(archives[0], {"backup_current": False})]
    assert stages_left(source.parent) == []
    assert len(prunes) == 1
    assert controller._alerts[0][1] == "Replacement failed"
    assert "restored" in controller._alerts[0][2]
    (payload,) = controller._done_pushes
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    assert "restored" in payload["error"]
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


def test_a_failed_rollback_names_the_backup_and_prunes_nothing(tmp_path, monkeypatch):
    """The durable archive is the only way back, so it is named in the
    message and retention does not get to consider deleting anything."""
    controller, source = copy_profile_setup(tmp_path, others=("Backup",))
    destination = source.parent / "settings_Backup"
    archives = []
    real_backup = backup_mod.create_profile_backup

    def record(*args, **kwargs):
        archives.append(real_backup(*args, **kwargs))
        return archives[-1]

    def refuse_restore(*args, **kwargs):
        raise OSError("the archive could not be read")

    monkeypatch.setattr(backup_mod, "create_profile_backup", record)
    monkeypatch.setattr(backup_mod, "restore", refuse_restore)
    failing_publication(monkeypatch, destination)
    prunes = []
    controller._eve_prune = lambda *args, **kwargs: prunes.append(args)

    controller.copy_profile(str(source), "replace", str(destination))

    assert prunes == []
    assert archives[0].exists()
    kind, _title, body = controller._alerts[0]
    assert kind == "error"
    assert archives[0].name in body
    assert "Backups" in body
    (payload,) = controller._done_pushes
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    assert archives[0].name in payload["error"]
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


def test_an_unexpected_worker_failure_still_releases_and_completes_once(
    tmp_path, monkeypatch
):
    controller, source = copy_profile_setup(tmp_path)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(profilecopy_mod, "stage_copy", explode)

    controller.copy_profile(str(source), "new", "Fleet")

    (payload,) = controller._done_pushes
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is False
    assert payload["error"]
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()
