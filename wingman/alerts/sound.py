"""In-memory volume scaling for the alert sounds.

Pure by design, and separate from service.py for the reason every pure
module here is separate: `winsound.PlaySound` cannot be exercised on
ubuntu-latest, and the arithmetic that decides how loud an alert is
must be.

Why scale samples at all: PlaySound has no volume parameter. The two
alternatives both reach past this feature -- `waveOutSetVolume` moves the
process's whole audio session (so it would also move anything else
Wingman ever plays), and the endpoint-volume COM interfaces move the
app's mixer slider behind the user's back. Scaling the buffer changes
exactly the sound being played and nothing else.
"""

import array
import io
import logging
import sys
import wave

logger = logging.getLogger(__name__)

# sound id -> (volume, scaled bytes). ONE entry per sound, not one per
# (sound, volume) pair: the volume slider is 101 positions and three
# sounds, so a pair-keyed cache would let a single drag across the
# control hold ~39MB of decoded audio for the life of the process. A
# volume change is rare and re-scaling is cheap; holding every position
# the pointer passed over is not.
_CACHE: dict[str, tuple[int, bytes]] = {}


def reset_cache() -> None:
    _CACHE.clear()


def scaled_for(sound_id: str, raw: bytes, volume: int) -> bytes:
    """`scaled_wav`, memoised per sound id."""
    cached = _CACHE.get(sound_id)
    if cached is not None and cached[0] == volume:
        return cached[1]
    out = scaled_wav(raw, volume)
    _CACHE[sound_id] = (volume, out)
    return out


def gain(volume: int) -> float:
    """Amplitude multiplier for a 0-100 setting.

    Squared, not linear. Loudness is perceived roughly logarithmically,
    so a linear multiplier puts 50% at half amplitude -- about 6dB down,
    which most people cannot pick out of the original. The whole top half
    of the slider then feels like it does nothing. Squaring spreads the
    audible range across the control instead: 50% lands ~12dB down, 25%
    ~24dB down.
    """
    return (max(0, min(100, int(volume))) / 100.0) ** 2


def scaled_wav(raw: bytes, volume: int) -> bytes:
    """*raw* WAV bytes at *volume* (0-100), as WAV bytes.

    Returns *raw* itself at 100, so the common case pays no decode and
    cannot differ by a rounding step from the file that ships.

    A sample width this cannot scale is returned unchanged rather than
    silenced: the sounds that ship are 16-bit PCM, and if a replacement
    ever is not, an alert that is too loud is recoverable and one that is
    silent is the failure mode this whole feature exists to avoid.
    """
    if volume >= 100:
        return raw
    try:
        with wave.open(io.BytesIO(raw), "rb") as src:
            params = src.getparams()
            frames = src.readframes(params.nframes)
    except (wave.Error, EOFError):
        # Not raised: this runs on the poll thread behind an alert. A
        # malformed file is already logged by nothing else, and playing
        # it unscaled is what the caller would have done anyway.
        logger.exception("Could not read an alert sound for scaling")
        return raw
    if params.sampwidth != 2:
        logger.warning(
            "Alert sound is %d-bit, which volume scaling does not handle; "
            "playing it at full volume",
            params.sampwidth * 8,
        )
        return raw

    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        # WAV is little-endian; array uses native order.
        samples.byteswap()
    factor = gain(volume)
    for i, value in enumerate(samples):
        samples[i] = int(value * factor)
    if sys.byteorder == "big":
        samples.byteswap()

    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setnchannels(params.nchannels)
        dst.setsampwidth(params.sampwidth)
        dst.setframerate(params.framerate)
        dst.writeframes(samples.tobytes())
    return out.getvalue()
