"""Wrap and unwrap, with the crypt callables injected.

Injection is what keeps this testable on Linux while only dpapi.py is
Windows-only, and it is the same keyword-only-with-a-production-default
seam discord.py:196-197 uses for its transport.
"""
from obs_youtube_uploader.eveskills import tokens


def _reverse_protect(data: bytes) -> bytes:
    """A stand-in cipher: reversible, and visibly not the plaintext."""
    return bytes(reversed(data))


def _reverse_unprotect(blob: bytes) -> bytes:
    return bytes(reversed(blob))


def test_wrap_then_unwrap_round_trips():
    blob = tokens.wrap("secret-refresh-token", protect=_reverse_protect)
    assert tokens.unwrap(blob, unprotect=_reverse_unprotect) == \
        "secret-refresh-token"


def test_the_wrapped_form_is_ascii_text():
    """It is stored as a JSON string field in the state document, so it must
    survive json.dumps/loads unchanged and must not carry raw bytes."""
    blob = tokens.wrap("secret-refresh-token", protect=_reverse_protect)
    assert blob.isascii()
    assert "secret" not in blob


def test_a_unicode_token_round_trips():
    """The token is opaque to us. Nothing may assume it is ASCII."""
    blob = tokens.wrap("tok-é中", protect=_reverse_protect)
    assert tokens.unwrap(blob, unprotect=_reverse_unprotect) == \
        "tok-é中"


def test_unwrap_of_an_empty_blob_is_none():
    """"" is how the state document spells "this character has no stored
    token", which is a normal state after a definitive auth failure."""
    assert tokens.unwrap("", unprotect=_reverse_unprotect) is None


def test_unwrap_returns_none_when_decryption_fails():
    """A blob that will not decrypt costs ONE character a re-authentication.
    Raising here would propagate out of the state load and make the whole
    document unloadable, taking every other character's authorisation with
    it -- which is exactly the failure that putting the tokens in the same
    document was meant to make impossible."""
    def boom(_blob):
        raise OSError(13, "The data is invalid")

    assert tokens.unwrap("QUJD", unprotect=boom) is None


def test_unwrap_returns_none_on_malformed_base64():
    """A truncated or hand-edited blob never reaches the crypt call."""
    assert tokens.unwrap("!!!not base64!!!",
                         unprotect=_reverse_unprotect) is None


def test_unwrap_returns_none_when_the_plaintext_is_not_utf8():
    """DPAPI can succeed on a blob written by something else entirely. Its
    output is then arbitrary bytes, not our token."""
    assert tokens.unwrap("QUJD", unprotect=lambda _b: b"\xff\xfe\x00") is None
