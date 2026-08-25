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


# --- the legacy Startup-folder shortcut -------------------------------------
#
# packaging/installer.iss shipped a run-at-login task long before the app had
# a setting for it, implemented as a shortcut with no arguments. The
# installer now writes the same Run value this module does, but the shortcut
# exists on every machine that ever ticked that box.


def startup_dir(monkeypatch, tmp_path):
    """Point _startup_dir at a real directory, on any platform."""
    d = tmp_path / "Startup"
    d.mkdir()
    monkeypatch.setattr(autostart, "_startup_dir", lambda: d)
    return d


def test_a_legacy_shortcut_alone_reads_as_on(monkeypatch, tmp_path):
    """It starts the app at login just as effectively as the Run value. A
    checkbox that ignored it would read "off" on a machine that
    demonstrably does start Wingman at login."""
    use(monkeypatch, FakeRegistry())
    (startup_dir(monkeypatch, tmp_path) / "FlyGD Wingman.lnk").write_text("shortcut")

    assert autostart.is_enabled() is True


def test_the_pre_rename_shortcut_name_counts_too(monkeypatch, tmp_path):
    """AppId is pinned across the rename, so pre-rename installs upgrade in
    place and can still be carrying the old spelling."""
    use(monkeypatch, FakeRegistry())
    (startup_dir(monkeypatch, tmp_path) / "OBS YouTube Uploader.lnk").write_text("x")

    assert autostart.is_enabled() is True


def test_enabling_migrates_a_legacy_shortcut_onto_the_run_value(monkeypatch, tmp_path):
    """One mechanism after the first toggle. Two login entries at once is
    what the collision produced, and one of them raised the window."""
    reg = use(monkeypatch, FakeRegistry())
    d = startup_dir(monkeypatch, tmp_path)
    legacy = d / "FlyGD Wingman.lnk"
    legacy.write_text("shortcut")

    autostart.enable()

    assert reg.values[RUN][autostart.VALUE_NAME] == autostart.command()
    assert not legacy.exists()
    assert autostart.legacy_shortcuts() == []


def test_disabling_removes_the_shortcut_as_well_as_the_value(monkeypatch, tmp_path):
    """ "Off" has to mean the app does not start at login. Leaving the
    shortcut while reporting success is the same lie in the other
    direction."""
    use(monkeypatch, FakeRegistry({RUN: {autostart.VALUE_NAME: "whatever"}}))
    d = startup_dir(monkeypatch, tmp_path)
    legacy = d / "FlyGD Wingman.lnk"
    legacy.write_text("shortcut")

    autostart.disable()

    assert not legacy.exists()
    assert autostart.is_enabled() is False


def test_a_refused_registry_write_leaves_the_legacy_shortcut_alone(
    monkeypatch, tmp_path
):
    """The migration rides along with what the user asked for. If the write
    is refused they must keep the login entry they already had -- ticking an
    already-ticked box must not be able to turn start-on-login OFF."""
    use(monkeypatch, FakeRegistry(denied=True))
    d = startup_dir(monkeypatch, tmp_path)
    legacy = d / "FlyGD Wingman.lnk"
    legacy.write_text("shortcut")

    with pytest.raises(OSError, match="policy"):
        autostart.enable()

    assert legacy.exists()
    assert autostart.is_enabled() is True


def test_a_locked_shortcut_does_not_fail_the_toggle(monkeypatch, tmp_path):
    """Failing the user's toggle because a stale .lnk is locked would report
    the wrong thing about the wrong action."""
    reg = use(monkeypatch, FakeRegistry())
    startup_dir(monkeypatch, tmp_path)

    def locked():
        class Stubborn:
            def unlink(self):
                raise OSError("in use")

        return [Stubborn()]

    monkeypatch.setattr(autostart, "legacy_shortcuts", locked)

    autostart.enable()  # must not raise

    assert reg.values[RUN][autostart.VALUE_NAME] == autostart.command()


def test_no_startup_folder_falls_back_to_the_registry_alone(monkeypatch):
    """A redirected or unreadable Startup folder means the legacy shortcut
    is not found, which is the pre-existing behaviour rather than a new
    failure."""
    use(monkeypatch, FakeRegistry())
    monkeypatch.setattr(autostart, "_startup_dir", lambda: None)

    assert autostart.legacy_shortcuts() == []
    assert autostart.is_enabled() is False
    autostart.enable()
    assert autostart.is_enabled() is True


# --- the installer and this module must write the same entry ----------------
#
# The same class of coupling ci.yml guards for the WebView2 predicate: two
# files in two languages that cannot share code and must ask one question.
# Here they must WRITE one value -- if they disagree, the install-time
# checkbox and the Settings checkbox describe different login entries and
# the user can end up with both.

import pathlib  # noqa: E402 - grouped with the section that uses it

_ISS = (
    pathlib.Path(__file__).resolve().parents[1] / "packaging" / "installer.iss"
).read_text(encoding="utf-8")


def _directives(text: str = _ISS) -> str:
    """installer.iss with its `;` comment lines removed.

    Necessary, not tidiness: the comments in that file explain the mechanism
    they replaced, so they legitimately contain the strings "{userstartup}"
    and "Tasks:". A test grepping the raw text cannot tell prose about a
    removed shortcut from a line that recreates one -- which is the same
    trap installer.iss's own note about braced comments and "[Run]" records
    against Inno's parser.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(";")
    )


def test_the_installer_writes_the_value_name_this_module_reads():
    """installer.iss uses {#AppName}, so the define has to match VALUE_NAME.
    An orphaned name keeps launching the app while the checkbox reads
    "off" -- which is the bug this whole section exists to close."""
    assert f'#define AppName "{autostart.VALUE_NAME}"' in _ISS
    assert 'ValueName: "{#AppName}"' in _ISS


def test_the_installer_writes_to_the_same_run_key():
    assert (
        r"Subkey: \"Software\Microsoft\Windows\CurrentVersion\Run\"".replace(r"\"", '"')
        in _ISS
    )
    assert "Root: HKCU" in _ISS, "HKLM would need elevation and affect other users"


def test_the_installers_login_entry_starts_hidden():
    """The whole reason the shortcut had to go: it carried no arguments, so
    the login launch raised the window at every boot on a tray app."""
    assert 'ValueData: """{app}\\{#AppExe}"" --hidden"' in _ISS


def test_the_installer_no_longer_writes_a_startup_shortcut():
    """One mechanism. Two is what produced a checkbox that disagreed with
    what Windows actually did at login."""
    icons = _directives().split("[Icons]")[1].split("[Registry]")[0]
    assert "{userstartup}" not in icons, (
        "a {userstartup} entry in [Icons] means the second mechanism is back"
    )


def test_the_installer_deletes_both_legacy_shortcut_names():
    """Unconditionally, not gated on the startup task: an upgrade that
    leaves it unticked must still remove the old shortcut, or the app keeps
    starting at login through something no UI can see or turn off."""
    delete_section = _directives().split("[InstallDelete]")[1].split("[Run]")[0]
    for name in autostart._LEGACY_SHORTCUT_NAMES:
        assert name in delete_section, f"{name} survives an upgrade"
    assert "Tasks:" not in delete_section, "the deletion must be unconditional"
