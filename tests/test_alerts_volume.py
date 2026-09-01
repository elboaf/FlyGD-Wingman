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


def test_scaling_is_cached_per_sound_id():
    """A drag across the slider must not grow memory, and an alert must
    not re-encode 66k frames on every pulse. One buffer per sound id, so
    the cache is bounded by the number of sounds that ship."""
    sound.reset_cache()
    raw = _wav([20000])
    first = sound.scaled_for("alarm", raw, 40)
    again = sound.scaled_for("alarm", raw, 40)
    assert again is first
    changed = sound.scaled_for("alarm", raw, 80)
    assert changed is not first
    assert len(sound._CACHE) == 1


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

    def fake_scaled_for(sound_id, raw, volume):
        seen["args"] = (sound_id, volume)
        return b"scaled"

    monkeypatch.setattr(service.sound, "scaled_for", fake_scaled_for)
    monkeypatch.setattr(
        service, "_play_bytes", lambda data: seen.setdefault("data", data)
    )

    service.play_sound("alarm", 40)

    assert seen["args"] == ("alarm", 40)
    assert seen["data"] == b"scaled"
