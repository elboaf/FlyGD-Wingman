"""The Uploader's three row-and-folder actions, across the bridge.

Post the last hour, Play, and Rename. None of them involves a video
upload, and two of them touch the user's files, so the failure modes here
are about state that must move with a file and about work that must not
overlap -- not about YouTube.
"""

import datetime
import threading
from pathlib import Path

from tests import fakes
from wingman import combatlog, durations, library
from wingman import links as links_mod
from wingman.ui import api as api_mod

HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def api_with(tmp_path, names=("a.mkv", "b.mkv"), watcher=None, **kw):
    rows = {}
    for index, name in enumerate(names):
        path = tmp_path / name
        path.write_bytes(b"\0" * 1024)
        rows[f"r{index}"] = fakes.info(path, size=1024, mtime=1_700_000_000.0)
    api, window = fakes.build_api(
        tmp_path, rows=fakes.FakeRows(rows), watcher=watcher, **kw
    )
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    api.list_rows = lambda preselect=None: None
    return api, window, rows


def logs_api(tmp_path, monkeypatch, settings=None, selection=None, dropped=0):
    """An api whose gamelogs folder and webhook are both usable."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    cfg = {"discord_webhook": HOOK, "gamelogs_dir": str(logs_dir)}
    cfg.update(settings or {})
    api, _window, _rows = api_with(tmp_path, settings=cfg)

    windows_asked = []
    stamp = datetime.datetime(2026, 8, 21, 19, 0, tzinfo=datetime.UTC)
    logs = (
        selection
        if selection is not None
        else [
            combatlog.SelectedLog(
                path=logs_dir / "x.txt",
                listener="Pilot",
                span_start=stamp,
                span_end=stamp + datetime.timedelta(minutes=5),
            )
        ]
    )

    def fake_select(directory, start, end):
        windows_asked.append((directory, start, end))
        return combatlog.Selection(logs=list(logs), dropped=dropped)

    monkeypatch.setattr(api_mod.combatlog, "select_logs", fake_select)
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(
        api_mod.combatlog,
        "build_archive",
        lambda sel, out, s, e: combatlog.ArchiveResult(
            path=archive_path,
            file_count=1,
            characters=["Pilot"],
            raw_bytes=10,
            zip_bytes=3,
            dropped=dropped,
        ),
    )
    return api, windows_asked


def join_logs(api):
    thread = api._logs_thread
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive()


def posts(monkeypatch, ok=True, message="Posted combatlogs.zip (3 B)."):
    posted = []

    def fake_post(hook, path, content):
        posted.append((path, content))
        return api_mod.discord.PostResult(ok, message)

    monkeypatch.setattr(api_mod.discord, "post_archive", fake_post)
    return posted


# ---- post the last hour ---------------------------------------------------


def test_the_window_is_the_hour_ending_now(tmp_path, monkeypatch):
    """The whole specification of the feature, and the one thing no other
    test would catch: combatlog._require_utc rejects a naive datetime, so
    "it did not raise" proves only that the bounds are tz-aware, not that
    they are the right hour."""
    api, asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)

    before = datetime.datetime.now(datetime.UTC)
    api.post_recent_logs()
    join_logs(api)
    after = datetime.datetime.now(datetime.UTC)

    ((_directory, start, end),) = asked
    assert before <= end <= after
    assert end - start == datetime.timedelta(hours=1)


def test_the_window_is_timezone_aware_utc(tmp_path, monkeypatch):
    """EVE writes gamelog timestamps in UTC and VideoInfo.mtime is local;
    combatlog's module docstring records that comparing the two naively
    selects the wrong hour with no error raised."""
    api, asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)

    api.post_recent_logs()
    join_logs(api)

    ((_directory, start, end),) = asked
    for bound in (start, end):
        assert bound.tzinfo is not None
        assert bound.utcoffset() == datetime.timedelta(0)


def test_a_successful_post_says_only_what_it_did(tmp_path, monkeypatch):
    """Round 3's finding 13 requires the PRIMARY action to be said first.
    After an upload that is the upload, and the log line trails it. Here
    the post IS the primary action, so the line stands alone -- it must
    not lead with a sentence about an upload that never happened."""
    api, _asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["text"] == "Posted combatlogs.zip (3 B)."
    assert final["kind"] == "SUCCESS"
    assert final["busy"] is False
    assert "None" not in final["text"]
    assert "Uploaded" not in final["text"]


def test_no_logs_in_the_window_is_reported_without_an_upload_sentence(
    tmp_path, monkeypatch
):
    api, _asked = logs_api(tmp_path, monkeypatch, selection=[])
    posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["text"] == "No combat logs found."
    assert final["busy"] is False


def test_a_missing_webhook_is_named_rather_than_silent(tmp_path, monkeypatch):
    """The upload tail stays SILENT here on purpose -- a strip per upload
    forever is the recurring-failure pattern, and the panel states the fact
    instead. A standalone post must say it: the user asked for exactly this
    and nothing else answers them."""
    api, _asked = logs_api(tmp_path, monkeypatch, settings={"discord_webhook": ""})
    posted = posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    assert posted == []
    (status,) = fakes.payloads(sent, "onStatus")
    assert status["kind"] == "WARNING"
    assert "webhook" in status["text"]
    assert "Settings" in status["text"]


def test_a_broken_webhook_is_reported_as_its_own_case(tmp_path, monkeypatch):
    api, _asked = logs_api(
        tmp_path, monkeypatch, settings={"discord_webhook": "http://example.com/x"}
    )
    posted = posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    assert posted == []
    (status,) = fakes.payloads(sent, "onStatus")
    assert status["kind"] == "WARNING"


def test_a_missing_gamelogs_folder_is_named(tmp_path, monkeypatch):
    api, _asked = logs_api(
        tmp_path, monkeypatch, settings={"gamelogs_dir": str(tmp_path / "nope")}
    )
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)
    posted = posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    assert posted == []
    (status,) = fakes.payloads(sent, "onStatus")
    assert "Gamelogs" in status["text"]


def test_the_post_is_refused_while_an_upload_runs(tmp_path, monkeypatch):
    api, _asked = logs_api(tmp_path, monkeypatch)
    posted = posts(monkeypatch)
    sent = fakes.record_pushes(api)
    gate = threading.Event()
    assert api._work_gate.claim_upload()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.post_recent_logs()
        assert posted == []
        assert api._logs_thread is None
        (status,) = fakes.payloads(sent, "onStatus")
        assert status["kind"] == "WARNING"
        # Its OWN sentence. "An upload is already in progress" belongs to
        # start_upload and would be answering a question nobody asked.
        assert "upload" in status["text"].lower()
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)
        api._work_gate.release_upload()


def test_an_upload_is_refused_while_a_post_runs_with_its_own_sentence(
    tmp_path, monkeypatch
):
    """Widening _busy() would have made this say "An upload is already in
    progress", which is false: nothing is uploading."""
    api, _asked = logs_api(tmp_path, monkeypatch)
    gate = threading.Event()
    api._logs_running = True
    api._logs_thread = threading.Thread(target=gate.wait, daemon=True)
    api._logs_thread.start()
    try:
        api.start_upload("t", "d", False, ["r0"])
        assert api._upload_thread is None
        ((kind, _title, body),) = api._alert.raised
        assert kind == "warning"
        assert "already in progress" not in body
        assert "combat log" in body.lower()
    finally:
        gate.set()
        api._logs_thread.join(timeout=5)
        api._logs_running = False


def test_a_second_post_is_refused_while_one_runs(tmp_path, monkeypatch):
    api, _asked = logs_api(tmp_path, monkeypatch)
    posted = posts(monkeypatch)
    gate = threading.Event()
    api._logs_running = True
    api._logs_thread = threading.Thread(target=gate.wait, daemon=True)
    api._logs_thread.start()
    try:
        api.post_recent_logs()
        assert posted == []
    finally:
        gate.set()
        api._logs_thread.join(timeout=5)
        api._logs_running = False


def test_the_post_is_claimed_before_the_worker_starts(tmp_path, monkeypatch):
    """A click one millisecond after another must not slip past the guard.

    pywebview serves each bridge call on its own thread, and a guard
    written against thread.is_alive() answers False for a handle that has
    been assigned and not yet started -- so the claim has to be a flag
    taken under a lock, not the thread's own liveness.

    The spy reads _logs_busy(), which is the predicate every caller
    actually consults; it says nothing about when _logs_thread is
    assigned, which is bookkeeping for the tests' own join()."""
    api, _asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)
    started = []
    real_start = threading.Thread.start

    def spy(self):
        started.append(api._logs_busy())
        real_start(self)

    monkeypatch.setattr(threading.Thread, "start", spy)
    api.post_recent_logs()
    monkeypatch.undo()
    join_logs(api)

    assert started == [True]


def test_the_page_is_told_the_post_started_and_finished(tmp_path, monkeypatch):
    api, _asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    assert fakes.payloads(sent, "onLogPostRunning") == [
        {"running": True},
        {"running": False},
    ]


def test_the_running_flag_is_cleared_even_when_the_worker_explodes(
    tmp_path, monkeypatch
):
    """_combat_log_worker reports its own failures and returns, so this
    covers the disarm after a REPORTED failure rather than an escaping
    exception. That is the case that actually occurs; the finally is there
    for the one that does not, since a lost claim can never be retaken."""
    api, _asked = logs_api(tmp_path, monkeypatch)

    def explode(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api_mod.combatlog, "select_logs", explode)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()
    join_logs(api)

    assert fakes.payloads(sent, "onLogPostRunning")[-1] == {"running": False}


def test_a_refused_post_repairs_the_pages_idea_of_the_flag(tmp_path, monkeypatch):
    """Every call re-states the flag, refusals included.

    This is one half of the defence against a disarm lost into a hidden
    window; it cannot be the whole of it, because a button the page has
    drawn as disabled takes neither a click nor a keypress and so cannot
    ask for its own repair. The other half is list_rows, below."""
    api, _asked = logs_api(tmp_path, monkeypatch, settings={"discord_webhook": ""})
    posts(monkeypatch)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()

    assert fakes.payloads(sent, "onLogPostRunning") == [{"running": False}]


def test_the_post_does_not_defer_the_recording_list(tmp_path, monkeypatch):
    """poll_tick reads _busy() to decide whether a rebuild would destroy an
    upload's links and progress. A log post touches no rows, so it must not
    make the list go stale."""
    api, _asked = logs_api(tmp_path, monkeypatch)
    gate = threading.Event()
    api._logs_running = True
    api._logs_thread = threading.Thread(target=gate.wait, daemon=True)
    api._logs_thread.start()
    try:
        assert api._busy() is False
    finally:
        gate.set()
        api._logs_thread.join(timeout=5)
        api._logs_running = False


# ---- play -----------------------------------------------------------------


def test_play_asks_the_shell_for_the_recording(tmp_path, monkeypatch):
    api, _window, rows = api_with(tmp_path)
    monkeypatch.setattr(api_mod.sys, "platform", "win32")
    opened = []
    monkeypatch.setattr(api_mod.os, "startfile", opened.append, raising=False)

    api.play_recording("r0")
    api._play_thread.join(timeout=5)

    assert opened == [str(rows["r0"].path)]


def test_play_off_windows_is_a_deliberate_no_op(tmp_path, monkeypatch):
    """A dev box has no shell to ask, and the file is there, so nothing is
    reported -- the posture open_recording_dir already takes."""
    api, _window, _rows = api_with(tmp_path)
    monkeypatch.setattr(api_mod.sys, "platform", "linux")
    sent = fakes.record_pushes(api)

    api.play_recording("r0")
    api._play_thread.join(timeout=5)

    assert fakes.payloads(sent, "onStatus") == []


def test_play_reports_a_recording_that_has_gone(tmp_path, monkeypatch):
    api, _window, rows = api_with(tmp_path)
    rows["r0"].path.unlink()
    sent = fakes.record_pushes(api)

    api.play_recording("r0")
    api._play_thread.join(timeout=5)

    (status,) = fakes.payloads(sent, "onStatus")
    assert status["kind"] == "WARNING"
    assert "no longer" in status["text"]


def test_play_reports_a_shell_that_refuses(tmp_path, monkeypatch):
    api, _window, _rows = api_with(tmp_path)
    monkeypatch.setattr(api_mod.sys, "platform", "win32")

    def boom(_path):
        raise OSError("no association")

    monkeypatch.setattr(api_mod.os, "startfile", boom, raising=False)
    sent = fakes.record_pushes(api)

    api.play_recording("r0")
    api._play_thread.join(timeout=5)

    assert fakes.payloads(sent, "onStatus")[0]["kind"] == "WARNING"


def test_play_on_a_stale_id_does_nothing_loudly(tmp_path, monkeypatch):
    """Every id-taking method treats a stale id as "do nothing"; here it
    also has to say so, because the row is still on the user's screen."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)

    api.play_recording("r404")

    assert api._play_thread is None
    (status,) = fakes.payloads(sent, "onStatus")
    assert status["kind"] == "WARNING"


# ---- rename ---------------------------------------------------------------


def rename_api(tmp_path, **kw):
    watcher = fakes.FakeWatcher(tmp_path)
    api, window, rows = api_with(tmp_path, watcher=watcher, **kw)
    return api, window, rows, watcher


def test_rename_moves_the_file_and_keeps_the_extension(tmp_path):
    api, _window, rows, _watcher = rename_api(tmp_path)
    old = rows["r0"].path

    assert api.rename_recording("r0", "Fight 12") == {"ok": True, "error": ""}

    assert not old.exists()
    assert (tmp_path / "Fight 12.mkv").exists()


def test_rename_reports_the_new_name_to_the_page_without_rebuilding(tmp_path):
    """A rebuild mints fresh ids, and web/list.js drops every selection and
    focus id it no longer recognises -- so a rebuild costs the user's ticks
    and keyboard position. (The sort key lives in the page and survives.)

    What this asserts is the backend half: no rebuild, one targeted push.
    Nothing in this suite executes the page."""
    api, _window, _rows, _watcher = rename_api(tmp_path)
    rebuilt = []
    api.list_rows = lambda preselect=None: rebuilt.append(True)
    sent = fakes.record_pushes(api)

    api.rename_recording("r0", "Fight 12")

    assert rebuilt == []
    assert fakes.payloads(sent, "onRowRenamed") == [
        {"id": "r0", "name": "Fight 12.mkv"}
    ]


def test_rename_carries_the_watcher_entry_so_it_is_not_announced(tmp_path):
    """THE regression. The seen-set is keyed by path, so without this the
    next completed settle cycle announces the renamed file as a finished
    recording, preselected and ready to upload -- which reads as a bug
    about OBS rather than about the rename.

    This pins the delegation; tests/test_watcher.py owns the announcement
    itself, including the control test that proves an unmigrated rename IS
    announced."""
    api, _window, rows, watcher = rename_api(tmp_path)
    old = rows["r0"].path

    api.rename_recording("r0", "Fight 12")

    assert watcher.renamed == [(old, tmp_path / "Fight 12.mkv")]


def test_rename_carries_the_link_and_the_duration(tmp_path):
    """links is the one that cannot be rebuilt: nothing prunes that file
    and nothing recomputes it, so a lost key is the Link column's answer
    gone for good."""
    api, _window, rows, _watcher = rename_api(tmp_path)
    info = rows["r0"]
    links_mod.remember(
        api._link_store, info.path, info.size, info.mtime, "https://youtu.be/abc"
    )
    durations.remember(api._cache, info.path, info.size, info.mtime, 61.0)

    api.rename_recording("r0", "Fight 12")

    new = tmp_path / "Fight 12.mkv"
    assert links_mod.lookup(api._link_store, new, info.size, info.mtime) == (
        "https://youtu.be/abc"
    )
    assert durations.lookup(api._cache, new, info.size, info.mtime) == (True, 61.0)


def test_a_renamed_link_survives_a_restart(tmp_path):
    """The migration is only worth anything if it reaches disk: the whole
    point of the persisted store is the next launch."""
    api, _window, rows, _watcher = rename_api(tmp_path)
    info = rows["r0"]
    links_mod.remember(
        api._link_store, info.path, info.size, info.mtime, "https://youtu.be/abc"
    )

    api.rename_recording("r0", "Fight 12")

    reloaded = links_mod.load(api._links_file)
    assert str(tmp_path / "Fight 12.mkv") in reloaded


def test_rename_is_refused_while_an_upload_runs(tmp_path):
    """Refused whenever an upload thread is alive, which is all this test
    exercises -- it fakes the thread rather than running an upload.

    The reason for the rule is the race it forecloses: the uploader reads
    a source path when it opens it, and on the stitched path the open
    handle is on the merged temporary rather than on the sources, so
    Windows would allow the rename outright. Verifying THAT needs a real
    stitched upload on Windows, which is why it is also a smoke item."""
    api, _window, rows, _watcher = rename_api(tmp_path)
    old = rows["r0"].path
    gate = threading.Event()
    assert api._work_gate.claim_upload()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        result = api.rename_recording("r0", "Fight 12")
        assert result["ok"] is False
        assert "upload" in result["error"].lower()
        assert old.exists()
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)
        api._work_gate.release_upload()


def test_rename_refuses_a_name_already_on_disk(tmp_path):
    """Never overwrite: the target is another recording, and a silent
    clobber here destroys a fight nothing can bring back."""
    api, _window, rows, _watcher = rename_api(tmp_path)
    victim = rows["r1"].path
    victim.write_bytes(b"the other recording")

    result = api.rename_recording("r0", "b")

    assert result["ok"] is False
    assert "b.mkv" in result["error"]
    # The file it would have destroyed is untouched, byte for byte.
    assert victim.read_bytes() == b"the other recording"
    assert rows["r0"].path.exists()


def test_rename_leaves_every_store_untouched_when_it_fails(tmp_path):
    api, _window, rows, watcher = rename_api(tmp_path)
    info = rows["r0"]
    links_mod.remember(
        api._link_store, info.path, info.size, info.mtime, "https://youtu.be/abc"
    )
    (tmp_path / "b.mkv").write_bytes(b"x")

    api.rename_recording("r0", "b")

    assert watcher.renamed == []
    assert links_mod.lookup(api._link_store, info.path, info.size, info.mtime) == (
        "https://youtu.be/abc"
    )


def test_a_case_only_rename_is_not_a_collision(tmp_path):
    """fight.mkv -> Fight.mkv is the rename a user is most likely to want,
    and on a case-insensitive filesystem the file IS its own destination.
    Refusing it as a clash would be the validator arguing with itself.

    What it proves depends on where it runs, and CI runs it in both
    places. On Linux, Fight.mkv simply does not exist, so this pins only
    that the normcase check does not refuse the rename as a self-collision.
    On the windows-latest job it goes further and exercises Path.rename
    against a real NTFS volume, which is the half that could not be
    reasoned out from here."""
    api, _window, _rows, _watcher = rename_api(tmp_path, names=("fight.mkv",))

    result = api.rename_recording("r0", "Fight")

    assert result == {"ok": True, "error": ""}


def test_renaming_to_the_same_name_is_a_no_op(tmp_path):
    api, _window, _rows, watcher = rename_api(tmp_path, names=("fight.mkv",))
    sent = fakes.record_pushes(api)

    assert api.rename_recording("r0", "fight") == {"ok": True, "error": ""}

    assert watcher.renamed == []
    assert fakes.payloads(sent, "onRowRenamed") == []


def test_rename_tells_a_stale_list_apart_from_a_missing_file(tmp_path):
    """WM.prompt resolves seconds later, and a watcher poll landing in that
    window re-mints every id. The file is right there on screen, so "that
    recording is no longer there" would be a wrong sentence about a state
    the user can see."""
    api, _window, _rows, _watcher = rename_api(tmp_path)

    stale = api.rename_recording("r404", "Fight 12")

    assert stale["ok"] is False
    assert "refreshed" in stale["error"].lower()


def test_rename_reports_a_recording_that_has_gone(tmp_path):
    api, _window, rows, _watcher = rename_api(tmp_path)
    rows["r0"].path.unlink()

    result = api.rename_recording("r0", "Fight 12")

    assert result["ok"] is False
    assert "no longer" in result["error"].lower()


def test_rename_reports_a_refusing_filesystem_rather_than_raising(
    tmp_path, monkeypatch
):
    """It crosses the bridge, so an escaping OSError is a dead dialog and a
    traceback nobody reads."""
    api, _window, _rows, _watcher = rename_api(tmp_path)

    def boom(self, target):
        raise OSError("in use")

    monkeypatch.setattr(Path, "rename", boom)

    result = api.rename_recording("r0", "Fight 12")

    assert result["ok"] is False
    assert result["error"]


def test_every_refused_name_is_refused_before_anything_moves(tmp_path):
    api, _window, rows, _watcher = rename_api(tmp_path)
    for stem in (
        "",
        "   ",
        "a/b",
        "a\\b",
        "a:b",
        "a?b",
        'a"b',
        "a|b",
        "a*b",
        "a<b",
        "a>b",
        "fight.",
        "CON",
        "nul",
        "..",
        "a\x00b",
    ):
        result = api.rename_recording("r0", stem)
        assert result["ok"] is False, f"{stem!r} should be refused"
        assert result["error"], f"{stem!r} needs a sentence"
    assert rows["r0"].path.exists()
    assert sorted(p.name for p in tmp_path.glob("*.mkv")) == ["a.mkv", "b.mkv"]


def test_surrounding_whitespace_is_trimmed_rather_than_refused(tmp_path):
    """A name cannot end in a space on Windows, and typing one is an
    accident rather than a decision."""
    api, _window, _rows, _watcher = rename_api(tmp_path)

    assert api.rename_recording("r0", "  Fight 12  ")["ok"] is True

    assert (tmp_path / "Fight 12.mkv").exists()


def test_the_stem_is_what_is_renamed_so_the_extension_cannot_change(tmp_path):
    """Typing "fight.mp4" must not claim a remux happened."""
    api, _window, _rows, _watcher = rename_api(tmp_path)

    api.rename_recording("r0", "fight.mp4")

    assert (tmp_path / "fight.mp4.mkv").exists()


def test_the_name_validator_is_pure_and_shared(tmp_path):
    """The rules are Windows' and belong with the other file logic, where
    they can be exercised without a filesystem."""
    assert library.rename_problem("Fight 12") is None
    assert library.rename_problem("") is not None
    assert library.rename_problem("CON") is not None


def test_a_post_that_cannot_start_does_not_latch_the_button(tmp_path, monkeypatch):
    """The claim is taken before the worker exists, so a thread that never
    starts would leave it taken -- and nothing else clears it. The button
    would then refuse for the rest of the process, which is the one failure
    worse than the post not happening."""
    api, _asked = logs_api(tmp_path, monkeypatch)
    posts(monkeypatch)

    def refuse(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(api, "_spawn", refuse)
    sent = fakes.record_pushes(api)

    api.post_recent_logs()

    assert api._logs_busy() is False
    assert fakes.payloads(sent, "onLogPostRunning")[-1] == {"running": False}
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "WARNING"


def test_a_list_rebuild_restates_the_flag(tmp_path, monkeypatch):
    """The only repair available for a disarm lost into a hidden window.
    _push swallows those, and a button the page has drawn as disabled takes
    neither a click nor a keypress, so it cannot ask for its own repair. A
    rebuild is what a watcher announcement, a delete and a folder change
    all produce."""
    api, _window, _rows = api_with(tmp_path)
    del api.list_rows  # the fixture stubs it out; here it is the subject
    api._state.settings["recording_dir"] = str(tmp_path)
    sent = fakes.record_pushes(api)

    api.list_rows()

    assert fakes.payloads(sent, "onLogPostRunning") == [{"running": False}]


def test_a_reserved_device_name_is_refused_whatever_follows_it(tmp_path):
    """Windows reserves the device name before the first dot, so CON.foo
    is refused as surely as CON -- and the whole point of validating here
    rather than letting the filesystem answer is that the filesystem says
    "the system cannot find the path specified"."""
    assert library.rename_problem("CON.foo") is not None
    assert library.rename_problem("lpt1.backup") is not None
    # Not a device name, and must not be caught by the same rule.
    assert library.rename_problem("CONVOY.2") is None

    api, _window, rows = api_with(tmp_path)
    assert api.rename_recording("r0", "CON.foo")["ok"] is False
    assert rows["r0"].path.exists()
