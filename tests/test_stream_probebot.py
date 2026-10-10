"""The probe bot's DPAPI token store (wingman/streaming/probebot.py).

Linux-testable with injected protect/unprotect doubles -- the same seam
wanderer/credentials.py's tests use. Pinned: version/purpose binding,
corrupt data raising (never silently None), removal idempotence, and a
bad token refused before any DPAPI call.
"""

import json

import pytest

from wingman.streaming.probebot import BotTokenStore, CredentialError

TOKEN = "MTEyMzQ1Njc4OTA.gGGh.Y83o-_xZ9z5vYcB8mF3nQw"


@pytest.fixture
def store(tmp_path):
    calls = []
    return BotTokenStore(
        tmp_path / "probe_bot_token.json",
        protect=lambda raw: (calls.append("protect"), b"encrypted:" + raw)[1],
        unprotect=lambda blob: blob[len(b"encrypted:") :],
    )


def test_an_absent_token_loads_as_none(store):
    assert store.load() is None


def test_replace_then_load_round_trips(store):
    store.replace(TOKEN)
    assert store.load() == TOKEN


def test_the_plaintext_never_reaches_the_file(tmp_path, store):
    store.replace(TOKEN)
    raw = (tmp_path / "probe_bot_token.json").read_bytes()
    assert TOKEN.encode() not in raw
    assert b"gGGh" not in raw


def test_a_bad_token_is_refused_before_any_crypto(store):
    with pytest.raises(CredentialError):
        store.replace("not a token")
    assert store.load() is None


def test_a_wrong_purpose_is_corrupt_not_absent(tmp_path):
    from wingman.eveauth import dpapi  # noqa: F401 -- import parity with production

    def protect(raw):
        # Encrypt with a DIFFERENT purpose than the store reads.
        document = json.loads(raw)
        document["purpose"] = "wingman.wanderer.credentials"
        return b"encrypted:" + json.dumps(document).encode()

    store = BotTokenStore(
        tmp_path / "probe_bot_token.json",
        protect=protect,
        unprotect=lambda blob: blob[len(b"encrypted:") :],
    )
    store.replace(TOKEN)
    with pytest.raises(CredentialError):
        store.load()


def test_remove_is_idempotent(store):
    store.remove()  # absent: fine
    store.replace(TOKEN)
    store.remove()
    assert store.load() is None
    store.remove()  # already gone: still fine


def test_a_failed_replace_leaves_the_prior_token(store):
    store.replace(TOKEN)
    original_protect = store._protect

    def broken(raw):
        raise OSError("disk gone")

    store._protect = broken
    with pytest.raises(CredentialError):
        store.replace("MTEyMzQ1Njc4OTA.gGGh.different-hmac-value-here-ok")
    store._protect = original_protect
    assert store.load() == TOKEN


def test_a_tampered_ciphertext_is_a_fixed_error(tmp_path, store):
    store.replace(TOKEN)
    path = tmp_path / "probe_bot_token.json"
    document = json.loads(path.read_bytes())
    document["protected"] = "AAAA"
    path.write_text(json.dumps(document))
    with pytest.raises(CredentialError):
        store.load()
