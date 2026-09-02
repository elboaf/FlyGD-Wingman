"""Sound ids, resolution, and the packaging entry.

The frozen build is where this breaks and nowhere else, so the tests
assert on paths and the spec file rather than on playback.
"""

from wingman import settings
from wingman.alerts import service


def test_every_valid_sound_has_a_file():
    """An id in the dropdown with no file behind it plays nothing, which
    is indistinguishable from a broken alert."""
    for name in settings.VALID_SOUNDS - {"none"}:
        assert service.sound_path(name).is_file(), name


def test_an_unknown_id_resolves_to_none():
    assert service.sound_path("airhorn") is None


def test_sound_path_prefers_the_frozen_bundle(tmp_path, monkeypatch):
    """The frozen layout: bundle_dir()/assets/sounds/<id>.wav.

    Nothing else exercises this branch -- CI is unfrozen ubuntu-latest, so
    without this test a destination string that drifted out of sync
    between uploader.spec and sound_path's frozen candidate (chrome.py's
    exact failure mode) would pass every other test in this file.
    """
    sounds = tmp_path / "assets" / "sounds"
    sounds.mkdir(parents=True)
    (sounds / "system-fault.wav").write_bytes(b"")
    monkeypatch.setattr(service.paths, "bundle_dir", lambda: tmp_path)

    assert service.sound_path("system-fault") == sounds / "system-fault.wav"


def test_the_spec_collects_the_sounds_folder():
    """chrome.py's font is collected to a destination that does not match
    where it looks (assets/fonts vs wingman/assets/fonts), so
    it is not the precedent to copy. These go through paths.bundle_dir()."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert "assets/sounds" in spec or "assets\\\\sounds" in spec


def test_no_orphaned_sound_files_ship():
    """The mirror of test_every_valid_sound_has_a_file.

    That one catches an id with no file. This catches a file with no id --
    dead weight in the installer, and the specific way it arises is a
    sound being replaced: the new file lands, the id changes, and the old
    .wav sits there forever because nothing looks for it.
    """
    folder = service.sound_path(min(settings.VALID_SOUNDS - {"none"})).parent
    shipped = {p.stem for p in folder.glob("*.wav")}
    orphans = shipped - (settings.VALID_SOUNDS - {"none"})
    assert not orphans, (
        f"{sorted(orphans)} ship in assets/sounds but no VALID_SOUNDS id "
        f"names them, so nothing can ever play them"
    )


def test_every_shipped_sound_is_credited():
    """The sounds are CC BY 4.0, so shipping one without a credit is a
    licence violation rather than an untidiness.

    Attribution lives in THIRD-PARTY-NOTICES.md, which the installer
    ships, and CC BY 4.0 also requires that modifications be disclosed --
    every one of these was decoded from MP3, and one was truncated.
    Derived from VALID_SOUNDS rather than listed here, so adding a fourth
    sound fails until it is credited too.
    """
    import pathlib

    notices = (
        pathlib.Path(__file__).resolve().parents[1] / "THIRD-PARTY-NOTICES.md"
    ).read_text(encoding="utf-8")

    assert "notificationsounds.com" in notices, (
        "the alert sounds' source is not credited at all"
    )
    assert "CC BY 4.0" in notices or "Attribution 4.0" in notices

    for name in sorted(settings.VALID_SOUNDS - {"none"}):
        assert f"`{name}.wav`" in notices, (
            f"{name}.wav ships but THIRD-PARTY-NOTICES.md does not credit it"
        )
