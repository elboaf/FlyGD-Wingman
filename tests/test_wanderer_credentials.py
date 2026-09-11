"""Bound secret storage; only the platform crypto boundary is substituted."""

import base64
import json
import traceback

import pytest
from cryptography.fernet import Fernet

BASE = "https://example.com/wanderer"
MAP = "My-Map"
TOKEN = "wmi_v1_fixture_SECRET_SENTINEL"


@pytest.fixture
def cipher():
    return Fernet(Fernet.generate_key())


def store_at(path, cipher):
    from wingman.wanderer.credentials import CredentialStore

    return CredentialStore(path, protect=cipher.encrypt, unprotect=cipher.decrypt)


def test_replace_round_trip_whole_protected_binding_and_remove(tmp_path, cipher):
    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    assert store.load(BASE, MAP) is None
    store.replace(BASE, MAP, TOKEN)
    encoded = path.read_bytes()
    for secret in (TOKEN, BASE, MAP):
        assert secret.encode() not in encoded
        assert secret not in repr(store)
    document = json.loads(encoded)
    assert set(document) == {"version", "protected"}
    protected = json.loads(cipher.decrypt(base64.b64decode(document["protected"])))
    assert protected == {
        "version": 1,
        "purpose": "wingman.wanderer.credentials",
        "base_url": BASE,
        "map_identifier": MAP,
        "token": TOKEN,
    }
    assert store_at(path, cipher).load(BASE, MAP) == TOKEN
    store.replace(BASE, MAP, "replacement-token")
    assert store.load(BASE, MAP) == "replacement-token"
    store.remove()
    assert not path.exists()
    assert store.load(BASE, MAP) is None
    store.remove()


def test_credential_default_path_is_separate_from_settings_and_eve_tokens(cipher):
    from wingman import paths
    from wingman.wanderer.credentials import CredentialStore

    store = CredentialStore(protect=cipher.encrypt, unprotect=cipher.decrypt)
    store.replace(BASE, MAP, TOKEN)
    assert (paths.state_dir() / "wanderer_credentials.json").is_file()
    assert not paths.settings_file().exists()
    assert not paths.eve_authority_file().exists()


@pytest.mark.parametrize(
    "base,map_id",
    [
        ("https://other.example/wanderer", MAP),
        ("https://example.com", MAP),
        ("https://example.com/Wanderer", MAP),
        ("https://example.com:444/wanderer", MAP),
        (BASE, "Other-Map"),
        (BASE, "my-map"),
    ],
)
def test_binding_edits_cannot_rebind_old_token(tmp_path, cipher, base, map_id):
    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    before = path.read_bytes()
    assert store.load(base, map_id) is None
    assert path.read_bytes() == before
    assert store.load(BASE, MAP) == TOKEN


def test_equivalent_url_and_uuid_bindings_round_trip(tmp_path, cipher):
    store = store_at(tmp_path / "credentials.json", cipher)
    store.replace(
        " HTTPS://EXAMPLE.com:443/wanderer/ ",
        "AABBCCDD-1234-5678-9ABC-123456789ABC",
        TOKEN,
    )
    assert store.load(BASE, "aabbccdd-1234-5678-9abc-123456789abc") == TOKEN


@pytest.mark.parametrize(
    "token",
    [None, "", "a b", "a\tb", "a\r\nb", "a,b", "a\x00b", "a\x7fb", "é", "x" * 506],
)
def test_token_header_bounds_and_no_plaintext_on_rejection(tmp_path, cipher, token):
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    before = path.read_bytes()
    with pytest.raises(CredentialError):
        store.replace(BASE, MAP, token)
    assert path.read_bytes() == before
    assert store.load(BASE, MAP) == TOKEN


def test_maximum_authorization_header_fits_512_bytes(tmp_path, cipher):
    store = store_at(tmp_path / "credentials.json", cipher)
    store.replace(BASE, MAP, "x" * 505)
    assert store.load(BASE, MAP) == "x" * 505


def failing_crypto(_):
    raise RuntimeError(TOKEN)


def assert_safe(caught):
    assert TOKEN not in "".join(traceback.format_exception(caught.value))
    assert TOKEN not in repr(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("operation", ["protect", "unprotect"])
def test_crypto_failures_are_safe_without_plaintext_fallback(
    tmp_path, cipher, operation, caplog
):
    from wingman.wanderer.credentials import CredentialError, CredentialStore

    path = tmp_path / "credentials.json"
    store_at(path, cipher).replace(BASE, MAP, TOKEN)
    before = path.read_bytes()
    store = CredentialStore(
        path,
        protect=failing_crypto if operation == "protect" else cipher.encrypt,
        unprotect=failing_crypto if operation == "unprotect" else cipher.decrypt,
    )
    with pytest.raises(CredentialError) as caught:
        if operation == "protect":
            store.replace(BASE, MAP, TOKEN)
        else:
            store.load(BASE, MAP)
    assert_safe(caught)
    assert path.read_bytes() == before
    assert TOKEN not in caplog.text


def test_failed_atomic_replace_preserves_previous_token(tmp_path, cipher, monkeypatch):
    from wingman import atomicio
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    before = path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise PermissionError(TOKEN)

    monkeypatch.setattr(atomicio, "replace_with_retry", fail_replace)
    with pytest.raises(CredentialError) as caught:
        store.replace(BASE, MAP, "new-token")
    assert_safe(caught)
    assert path.read_bytes() == before
    assert store.load(BASE, MAP) == TOKEN
    assert list(tmp_path.iterdir()) == [path]


def test_failed_remove_preserves_credential(tmp_path, cipher, monkeypatch):
    from pathlib import Path

    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)

    def fail_remove(*args, **kwargs):
        raise PermissionError(TOKEN)

    monkeypatch.setattr(Path, "unlink", fail_remove)
    with pytest.raises(CredentialError) as caught:
        store.remove()
    assert_safe(caught)
    assert store.load(BASE, MAP) == TOKEN


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[]",
        b"null",
        b"\xff",
        b"{",
        b'{"version":true,"protected":"abc"}',
        b'{"version":2,"protected":"abc"}',
        b'{"version":1,"version":1,"protected":"abc"}',
        b'{"version":1,"protected":"!!!"}',
        b'{"version":1,"protected":""}',
        b'{"version":1,"protected":"YWJj","base_url":"https://evil.example"}',
        b"x" * 16385,
    ],
)
def test_corrupt_or_oversized_document_fails_closed(tmp_path, cipher, body):
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    path.write_bytes(body)
    with pytest.raises(CredentialError) as caught:
        store_at(path, cipher).load(BASE, MAP)
    assert_safe(caught)
    assert path.read_bytes() == body


@pytest.mark.parametrize(
    "mutation", ["version", "purpose", "binding", "token", "extra", "oversized"]
)
def test_decrypted_payload_is_also_versioned_bounded_and_validated(
    tmp_path, cipher, mutation
):
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    outer = json.loads(path.read_bytes())
    inner = json.loads(cipher.decrypt(base64.b64decode(outer["protected"])))
    if mutation == "version":
        inner["version"] = True
    elif mutation == "purpose":
        inner["purpose"] = "other.secret.store"
    elif mutation == "binding":
        inner["base_url"] = "https://EXAMPLE.COM/wanderer/"
    elif mutation == "token":
        inner["token"] = "secret\r\nheader"
    elif mutation == "extra":
        inner["new"] = TOKEN
    else:
        inner["token"] = "x" * 5000
    outer["protected"] = base64.b64encode(
        cipher.encrypt(json.dumps(inner).encode())
    ).decode()
    path.write_text(json.dumps(outer))
    with pytest.raises(CredentialError) as caught:
        store.load(BASE, MAP)
    assert_safe(caught)


def test_duplicate_fields_in_otherwise_valid_protected_document(tmp_path, cipher):
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    path.write_bytes(
        path.read_bytes().replace(b'"version":1', b'"version":1,"version":1')
    )
    with pytest.raises(CredentialError):
        store.load(BASE, MAP)


def test_other_windows_user_or_tampered_blob_cannot_be_read(tmp_path, cipher):
    from wingman.wanderer.credentials import CredentialError

    path = tmp_path / "credentials.json"
    store_at(path, cipher).replace(BASE, MAP, TOKEN)
    different_user = Fernet(Fernet.generate_key())
    with pytest.raises(CredentialError):
        store_at(path, different_user).load(BASE, MAP)


def test_protected_snapshot_compensates_replacement_and_absence(tmp_path, cipher):
    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    assert store.snapshot() is None
    store.replace(BASE, MAP, TOKEN)
    before = path.read_bytes()
    snapshot = store.snapshot()
    assert snapshot == before and TOKEN.encode() not in snapshot
    store.replace("https://other.example", "other", "candidate")
    store.restore(snapshot)
    assert path.read_bytes() == before
    assert store.load(BASE, MAP) == TOKEN
    store.restore(None)
    assert not path.exists()


def test_snapshot_is_bounded_and_never_decrypts(tmp_path, cipher, monkeypatch):
    from wingman.wanderer.credentials import MAX_DOCUMENT_BYTES, CredentialError

    path = tmp_path / "credentials.json"
    store = store_at(path, cipher)
    store.replace(BASE, MAP, TOKEN)
    monkeypatch.setattr(store, "_unprotect", failing_crypto)
    snapshot = store.snapshot()
    store.remove()
    store.restore(snapshot)
    assert path.read_bytes() == snapshot
    path.write_bytes(b"x" * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(CredentialError) as caught:
        store.snapshot()
    assert_safe(caught)


def test_failed_snapshot_restore_keeps_safe_error_context(
    tmp_path, cipher, monkeypatch
):
    from wingman import atomicio
    from wingman.wanderer.credentials import CredentialError

    store = store_at(tmp_path / "credentials.json", cipher)
    store.replace(BASE, MAP, TOKEN)
    snapshot = store.snapshot()
    monkeypatch.setattr(
        atomicio, "write_bytes_atomic", lambda *args: failing_crypto(None)
    )
    with pytest.raises(CredentialError) as caught:
        store.restore(snapshot)
    assert_safe(caught)


def test_oversized_crypto_output_never_replaces_disk(tmp_path, cipher):
    from wingman.wanderer.credentials import CredentialError, CredentialStore

    path = tmp_path / "credentials.json"
    store = CredentialStore(
        path, protect=lambda _: b"x" * 8193, unprotect=cipher.decrypt
    )
    with pytest.raises(CredentialError):
        store.replace(BASE, MAP, TOKEN)
    assert not path.exists()
