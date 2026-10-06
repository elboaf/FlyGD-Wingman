"""Launch wiring for the mirror supervisor (#317): the mirror follows the
engine's opt-in and shutdown discipline.

- restore at launch only when the user left mirror_on on (sticky
  on-demand; shipped default off must never start anything on upgrade);
- orphan reclaim runs regardless of the setting (a mirror nobody can
  address is the failure the job object only partly covers);
- shutdown stops it on every exit path and must never be the raiser.
"""

from wingman import __main__ as main_mod


class Recorder:
    def __init__(self, enabled):
        self.enabled = enabled
        self.started = 0
        self.stopped = 0
        self.recovered = 0

    def start(self):
        self.started += 1
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1

    def is_running(self):
        return self.started > self.stopped

    def recover_orphan(self):
        self.recovered += 1


def test_mirror_restores_at_launch_when_mirror_on():
    sup = Recorder(True)
    main_mod.start_mirror_if_enabled(sup, {"mirror_on": True})
    assert sup.started == 1


def test_mirror_does_not_restore_when_off():
    """Shipped default is off: an upgrading install must not acquire a
    background process (or a capture window) by upgrading."""
    sup = Recorder(True)
    main_mod.start_mirror_if_enabled(sup, {"mirror_on": False})
    assert sup.started == 0


def test_mirror_restore_is_safe_with_no_supervisor():
    main_mod.start_mirror_if_enabled(None, {"mirror_on": True})


def test_mirror_orphan_reclaim_runs_even_when_off():
    sup = Recorder(False)
    main_mod.reclaim_orphaned_mirror(sup)
    assert sup.recovered == 1


def test_mirror_orphan_reclaim_is_safe_with_none_and_never_raises():
    main_mod.reclaim_orphaned_mirror(None)

    class Boom:
        def recover_orphan(self):
            raise OSError("no kernel32")

    main_mod.reclaim_orphaned_mirror(Boom())


def test_shutdown_stops_the_mirror():
    sup = Recorder(True)
    main_mod.shutdown_mirror(sup)
    assert sup.stopped == 1


def test_shutdown_is_safe_with_no_mirror_and_never_raises():
    main_mod.shutdown_mirror(None)

    class Boom:
        def stop(self, timeout=5.0):
            raise OSError("gone")

    main_mod.shutdown_mirror(Boom())


def test_mirror_exe_locates_the_bundled_binary(tmp_path, monkeypatch):
    """Same shape as engine_exe(): bundle_dir/bin first, packaging/bin in
    a dev checkout, and deliberately NO PATH fallback -- a wingman-mirror
    .exe of unknown provenance on PATH must never become the thing Discord
    pins. Absent means the Streaming card says so."""
    import wingman.paths as paths

    calls = []

    def fake_bundle_dir():
        calls.append(1)
        return tmp_path

    monkeypatch.setattr(paths, "bundle_dir", fake_bundle_dir)
    monkeypatch.setattr(paths.sys, "_MEIPASS", "frozen", raising=False)
    assert paths.mirror_exe() is None  # not bundled -> None, not a guess
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "wingman-mirror.exe").write_text("")
    found = paths.mirror_exe()
    assert found and found.endswith("wingman-mirror.exe")
