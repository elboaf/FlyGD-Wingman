"""The Windows login entry (M3).

winreg does not exist off Windows and the suite runs on Linux in CI, so
every test here drives autostart._winreg's seam with a fake hive. That is
the same shape the rest of the repo uses for Windows APIs -- an injected
seam rather than a mock of the whole module -- and it means the branch
logic is covered on both CI platforms rather than skipped on one.
"""

import sys

import pytest

from obs_youtube_uploader import autostart


class FakeKey:
    def __init__(self, hive, path):
        self.hive = hive
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRegistry:
    """Just enough winreg to exercise every branch.

    `denied` makes each entry point raise OSError, which is what a managed
    machine's policy looks like from here.
    """

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self, values=None, denied=False):
        self.values = dict(values or {})
        self.denied = denied
        self.created = []

    def OpenKey(self, hive, path, reserved=0, access=0):  # winreg spells it this way
        if self.denied:
            raise OSError("access is denied by policy")
        if path not in self.values:
            raise FileNotFoundError(path)
        return FakeKey(hive, path)

    def CreateKey(self, hive, path):  # winreg spells it this way
        if self.denied:
            raise OSError("access is denied by policy")
        self.values.setdefault(path, {})
        self.created.append(path)
        return FakeKey(hive, path)

    def QueryValueEx(self, key, name):  # winreg spells it this way
        try:
            return self.values[key.path][name], self.REG_SZ
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def SetValueEx(self, key, name, reserved, kind, value):  # winreg's spelling
        self.values.setdefault(key.path, {})[name] = value

    def DeleteValue(self, key, name):  # winreg spells it this way
        try:
            del self.values[key.path][name]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc


RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def use(monkeypatch, registry):
    monkeypatch.setattr(autostart, "_winreg", lambda: registry)
    return registry


def test_off_when_no_entry_exists(monkeypatch):
    use(monkeypatch, FakeRegistry())
    assert autostart.is_enabled() is False


def test_enabling_writes_the_entry_under_the_product_name(monkeypatch):
    """The value name is what a user sees in Task Manager's Startup tab, so
    it is the product name and not the package name."""
    reg = use(monkeypatch, FakeRegistry())

    autostart.enable()

    assert reg.values[RUN][autostart.VALUE_NAME] == autostart.command()
    assert autostart.VALUE_NAME == "FlyGD Wingman"
    assert autostart.is_enabled() is True


def test_the_registered_command_starts_hidden(monkeypatch):
    """A login that raises a window at every boot is worse than no setting.
    The flag has to be IN the registered command -- nothing else about the
    boot launch distinguishes it from a launch off the Start menu."""
    use(monkeypatch, FakeRegistry())

    autostart.enable()

    assert "--hidden" in autostart.installed_command()


def test_the_command_is_quoted_for_a_path_containing_spaces(monkeypatch):
    """C:\\Program Files\\... is the normal install location. Unquoted, the
    shell reads it as a command plus arguments and launches "C:\\Program" at
    every login, forever, with nothing on screen to say so."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Wingman\Wingman.exe")

    assert autostart.command().startswith('"C:\\Program Files\\')
    assert autostart.command().endswith('" --hidden')


def test_a_source_checkout_registers_the_module_not_the_interpreter(monkeypatch):
    """sys.executable is python.exe there, and python.exe alone knows
    nothing about this package."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = autostart.command()

    assert "-m obs_youtube_uploader" in command
    assert command.endswith("--hidden")


def test_disabling_removes_the_entry(monkeypatch):
    reg = use(monkeypatch, FakeRegistry({RUN: {autostart.VALUE_NAME: "whatever"}}))

    autostart.disable()

    assert autostart.VALUE_NAME not in reg.values[RUN]
    assert autostart.is_enabled() is False


def test_disabling_something_already_gone_is_success(monkeypatch):
    """The user can delete this from Task Manager's Startup tab. Unticking a
    box that is already off must not report a failure for having nothing to
    do -- and it is the case the walkthrough asked for an answer to."""
    use(monkeypatch, FakeRegistry({RUN: {}}))

    autostart.disable()  # must not raise

    assert autostart.is_enabled() is False


def test_a_hand_removed_entry_reads_as_off_with_no_stored_copy_to_disagree(
    monkeypatch,
):
    """The registry is the state. There is no settings.json key, so there is
    nothing that can still claim "on" after the user deletes the entry."""
    reg = use(monkeypatch, FakeRegistry())
    autostart.enable()
    assert autostart.is_enabled() is True

    del reg.values[RUN][autostart.VALUE_NAME]  # the user, via Task Manager

    assert autostart.is_enabled() is False


def test_enabling_overwrites_a_stale_command(monkeypatch):
    """Re-ticking the box is the repair for a path left behind by a
    reinstall into a different folder."""
    reg = use(
        monkeypatch,
        FakeRegistry({RUN: {autostart.VALUE_NAME: r'"D:\old\Wingman.exe" --hidden'}}),
    )

    autostart.enable()

    assert reg.values[RUN][autostart.VALUE_NAME] == autostart.command()


def test_a_stale_path_still_reads_as_on(monkeypatch):
    """Presence, not equality. The value that exists is what Windows will
    run, so reporting "on" is true even when the path is stale -- comparing
    commands would tell a user their app does not start at login while it
    demonstrably still does."""
    use(
        monkeypatch,
        FakeRegistry({RUN: {autostart.VALUE_NAME: r'"D:\somewhere\else.exe"'}}),
    )

    assert autostart.is_enabled() is True


def test_a_denied_read_reads_as_off_rather_than_throwing(monkeypatch):
    """This feeds a checkbox rendered at load. A settings screen that fails
    to open because a registry read threw is a worse failure than a checkbox
    that starts unticked."""
    use(monkeypatch, FakeRegistry(denied=True))

    assert autostart.is_enabled() is False


def test_a_denied_write_raises_so_the_caller_can_say_so(monkeypatch):
    """The opposite rule to the read, and deliberately. A checkbox that
    silently fails to take is exactly what the commit contract exists to
    prevent, so this must not be swallowed here."""
    use(monkeypatch, FakeRegistry(denied=True))

    with pytest.raises(OSError, match="policy"):
        autostart.enable()
    with pytest.raises(OSError, match="policy"):
        autostart.disable()


def test_off_windows_every_read_is_off_and_every_write_refuses(monkeypatch):
    """The module imports on Linux -- the whole suite does -- so the
    non-Windows path has to be a defined answer rather than an ImportError."""
    monkeypatch.setattr(autostart, "_winreg", lambda: None)

    assert autostart.is_enabled() is False
    assert autostart.installed_command() == ""
    with pytest.raises(OSError, match="only available on Windows"):
        autostart.enable()
    with pytest.raises(OSError, match="only available on Windows"):
        autostart.disable()
