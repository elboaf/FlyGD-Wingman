"""Alert volume: the pure PCM scaling, and what play_sound does with it.

winsound.PlaySound has no volume parameter, so the only way to make an
alert quieter without moving the whole process's audio session is to
scale the samples before handing them over. That scaling is pure, so it
is covered here on ubuntu-latest; the PlaySound call itself is not.
"""

import io
import struct
import wave

import pytest

from wingman.alerts import sound


def _wav(samples, *, width=2, channels=1, rate=44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def _samples(raw: bytes) -> list:
    with wave.open(io.BytesIO(raw), "rb") as w:
        frames = w.readframes(w.getnframes())
    return list(struct.unpack(f"<{len(frames) // 2}h", frames))


def test_full_volume_returns_the_bytes_unchanged():
    """The common case must not pay a decode and re-encode, and must not
    risk a rounding difference against the file that ships."""
    raw = _wav([0, 1000, -1000, 32767])
    assert sound.scaled_wav(raw, 100) is raw


def test_scaling_is_quieter_but_keeps_the_shape():
    raw = _wav([0, 10000, -10000])
    out = _samples(sound.scaled_wav(raw, 50))
    assert out[0] == 0
    assert 0 < out[1] < 10000
    assert out[2] == -out[1]


def test_quieter_settings_are_monotonically_quieter():
    """The slider has to mean something across its whole range: every
    step down must actually reduce the amplitude."""
    raw = _wav([20000])
    peaks = [_samples(sound.scaled_wav(raw, v))[0] for v in (100, 75, 50, 25, 10)]
    assert peaks == sorted(peaks, reverse=True)


def test_zero_is_silence():
    assert _samples(sound.scaled_wav(_wav([20000, -20000]), 0)) == [0, 0]


def test_the_curve_is_not_linear():
    """Halving the amplitude is barely audible as "half as loud", so the
    slider is scaled on a squared curve. A linear implementation would
    put 50% at ~50% amplitude and the control would feel dead over its
    top half."""
    raw = _wav([20000])
    assert _samples(sound.scaled_wav(raw, 50))[0] == pytest.approx(5000, abs=2)


def test_a_sample_width_it_cannot_scale_is_left_alone():
    """8-bit or 24-bit audio is not something this ships, but a future
    replacement sound must not become silence -- unscaled and audible is
    the safe failure."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(44100)
        w.writeframes(b"\x80\xff\x00")
    raw = buf.getvalue()
    assert sound.scaled_wav(raw, 40) is raw


# ---- the file handed to PlaySound ------------------------------------------
# winsound refuses SND_MEMORY together with SND_ASYNC, and the synchronous
# form would block the alert poll thread for the length of the sound. So
# the scaled audio has to reach the device as a FILE.


def test_full_volume_plays_the_file_that_ships(tmp_path):
    sound.reset_cache()
    source = tmp_path / "alarm.wav"
    source.write_bytes(_wav([20000]))
    assert sound.playable_path("alarm", source, 100) == source


def test_a_quieter_volume_plays_a_scaled_copy(tmp_path):
    sound.reset_cache()
    source = tmp_path / "alarm.wav"
    source.write_bytes(_wav([20000]))

    out = sound.playable_path("alarm", source, 50)

    assert out != source
    assert _samples(out.read_bytes())[0] < 20000


def test_the_scaled_copy_is_written_once_per_volume(tmp_path):
    """An alert must not re-encode 66k frames every time it fires, and a
    volume change must not leave the old level playing."""
    sound.reset_cache()
    source = tmp_path / "alarm.wav"
    source.write_bytes(_wav([20000]))

    first = sound.playable_path("alarm", source, 50)
    stamp = first.stat().st_mtime_ns
    quiet_peak = _samples(first.read_bytes())[0]
    assert sound.playable_path("alarm", source, 50) == first
    assert first.stat().st_mtime_ns == stamp

    louder = sound.playable_path("alarm", source, 90)
    # The SAME file, rewritten: one entry per sound means one file per
    # sound, so the old level cannot be left behind for something to play.
    assert louder == first
    assert _samples(louder.read_bytes())[0] > quiet_peak
    # One entry per sound, not one per level the slider passed through.
    assert len(sound._CACHE) == 1


def test_a_deleted_cache_file_is_rewritten(tmp_path):
    """The state directory is a place users and cleaners delete things
    from. A cache entry pointing at a file that is gone would hand
    PlaySound a missing path, and PlaySound's failure is a silent one."""
    sound.reset_cache()
    source = tmp_path / "alarm.wav"
    source.write_bytes(_wav([20000]))
    first = sound.playable_path("alarm", source, 50)
    first.unlink()

    again = sound.playable_path("alarm", source, 50)

    assert again.is_file()


def test_a_cache_that_cannot_be_written_falls_back_to_the_original(
    tmp_path, monkeypatch
):
    """Louder than asked, never silent: PRODUCT.md's rule for this whole
    feature is that a missed alert is the failure mode. Volume 0 cannot
    reach here -- play_sound returns before it."""
    sound.reset_cache()
    source = tmp_path / "alarm.wav"
    source.write_bytes(_wav([20000]))

    def boom(*a, **kw):
        raise OSError("read-only")

    monkeypatch.setattr(sound.Path, "write_bytes", boom)

    assert sound.playable_path("alarm", source, 50) == source


# ---- play_sound ------------------------------------------------------------


def test_a_volume_of_zero_never_reaches_the_audio_api(monkeypatch):
    """Nothing is played rather than a silent buffer being played: the
    quiet path must cost nothing and must not hold the device."""
    from wingman.alerts import service

    monkeypatch.setattr(
        service, "sound_path", lambda _id: pytest.fail("resolved a muted sound")
    )
    service.play_sound("alarm", 0)


def test_the_volume_reaches_the_scaler(monkeypatch):
    from wingman.alerts import service

    seen = {}

    def fake_playable_path(sound_id, source, volume):
        seen["args"] = (sound_id, volume)
        return "scaled.wav"

    monkeypatch.setattr(service.sound, "playable_path", fake_playable_path)
    monkeypatch.setattr(service, "_play_file", lambda p: seen.setdefault("played", p))

    service.play_sound("alarm", 40)

    assert seen["args"] == ("alarm", 40)
    assert seen["played"] == "scaled.wav"


def test_the_async_flag_pair_winsound_refuses_is_not_used():
    """winsound raises RuntimeError on SND_MEMORY | SND_ASYNC ("this
    module does not support playing from a memory image asynchronously").
    Nothing on Linux can catch that, and the failure is a swallowed
    exception and total silence -- so the flags are asserted lexically,
    which is the same trade the web-page guards make.
    """
    import inspect

    from wingman.alerts import service

    call = [
        line
        for line in inspect.getsource(service._play_file).splitlines()
        if "PlaySound(" in line
    ]
    assert len(call) == 1, "_play_file no longer has exactly one PlaySound call"
    # The docstring names SND_MEMORY to say why it is not used, so this
    # reads the CALL rather than the function's whole source.
    assert "SND_FILENAME" in call[0] and "SND_ASYNC" in call[0]
    assert "SND_MEMORY" not in call[0]
