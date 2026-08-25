"""Sound ids, resolution, and the packaging entry.

The frozen build is where this breaks and nowhere else, so the tests
assert on paths and the spec file rather than on playback.
"""

from obs_youtube_uploader import settings
from obs_youtube_uploader.alerts import service


def test_every_valid_sound_has_a_file():
    """An id in the dropdown with no file behind it plays nothing, which
    is indistinguishable from a broken alert."""
    for name in settings.VALID_SOUNDS - {"none"}:
        assert service.sound_path(name).is_file(), name


def test_an_unknown_id_resolves_to_none():
    assert service.sound_path("airhorn") is None


def test_the_spec_collects_the_sounds_folder():
    """chrome.py's font is collected to a destination that does not match
    where it looks (assets/fonts vs obs_youtube_uploader/assets/fonts), so
    it is not the precedent to copy. These go through paths.bundle_dir()."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert "assets/sounds" in spec or "assets\\\\sounds" in spec
