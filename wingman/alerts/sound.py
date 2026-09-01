"""In-memory volume scaling for the alert sounds.

Pure by design, and separate from service.py for the reason every pure
module here is separate: `winsound.PlaySound` cannot be exercised on
ubuntu-latest, and the arithmetic that decides how loud an alert is
must be.

Why scale samples at all: PlaySound has no volume parameter. The two
alternatives both reach past this feature -- `waveOutSetVolume` sets the
volume of a waveform-output device, so it moves everything playing
through it rather than this sound, and the audio-session APIs
(ISimpleAudioVolume) move Wingman's own slider in the Windows volume
mixer behind the user's back. Scaling the buffer changes exactly the
sound being played and nothing else.

Why the result lands on DISK rather than being played from memory:
`winsound` refuses `SND_MEMORY | SND_ASYNC` outright -- CPython's own
documentation says the module "does not support playing from a memory
image asynchronously" and raises RuntimeError for that combination. The
only synchronous alternative would block the alert poll thread for up to
the length of the sound (1.5s for `ring`, against a 1s poll), so the
scaled bytes are written once to a cache file and played by name, which
is exactly what shipped before volume existed.
"""

import array
import io
import logging
import sys
import wave
from pathlib import Path

from .. import paths

logger = logging.getLogger(__name__)

# sound id -> (volume, path of the scaled file). ONE entry per sound, not
# one per (sound, volume) pair: a pair-keyed cache would keep every level
# the user ever set, and every level is a whole copy of the audio. Only
# the current volume can ever be played, so only the current volume is
# worth keeping.
_CACHE: dict[str, tuple[int, Path]] = {}


def reset_cache() -> None:
    _CACHE.clear()


def playable_path(sound_id: str, source: Path, volume: int) -> Path:
    """The file to hand to PlaySound for *sound_id* at *volume*.

    *source* itself at full volume -- there is nothing to change, and the
    file that ships is the one that plays.

    Below that, a scaled copy under the state directory, written once per
    volume change and reused for every alert until the setting moves
    again. If it cannot be written, *source* is returned: the alert plays
    LOUDER than asked rather than not at all, which is the trade
    PRODUCT.md makes everywhere in this feature -- a missed alert is the
    failure mode, and the one volume that must never be wrong this way
    (0) never reaches here, because play_sound returns before it.
    """
    if volume >= 100:
        return source
    cached = _CACHE.get(sound_id)
    if cached is not None and cached[0] == volume and cached[1].is_file():
        return cached[1]
    try:
        target = paths.tmp_dir() / f"alert-{sound_id}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(scaled_wav(source.read_bytes(), volume))
    except OSError:
        logger.exception(
            "Could not write a volume-scaled copy of %s; "
            "playing it at full volume instead",
            source,
        )
        return source
    _CACHE[sound_id] = (volume, target)
    return target


def gain(volume: int) -> float:
    """Amplitude multiplier for a 0-100 setting.

    Squared, not linear. Loudness rises roughly with the logarithm of
    amplitude, so a linear multiplier spends most of the slider's travel
    in a range that sounds close to full: halving the amplitude is 6dB,
    which is a real but modest step, and the whole top half of the
    control then covers less than that. Squaring spreads the range out --
    50% lands 12dB down, 25% 24dB down -- so the positions people
    actually drag to differ audibly from each other.
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
