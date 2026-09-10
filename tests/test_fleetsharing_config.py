"""Origin selection never sends an existing identity to a newly configured relay."""

import pytest

BRACKETED_INVALID_ORIGINS = (
    "https://[v1.relay.example.test]",
    "https://[v1.relay.example.test]:443",
    "https://prefix[2001:db8::1]",
    "https://[2001:db8::1]suffix",
    "https://[2001:db8::1]suffix:443",
    "https://[[2001:db8::1]]",
)


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("HTTPS://Relay.Example.test:443/", "https://relay.example.test"),
        ("https://relay.example.test:8443", "https://relay.example.test:8443"),
        ("https://[2001:db8::1]:443/", "https://[2001:db8::1]"),
        ("HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/", "https://[2001:db8::1]"),
        ("https://[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
    ],
)
def test_canonical_https_origin(raw, want):
    from wingman.fleetsharing.config import canonical_origin

    assert canonical_origin(raw) == want


@pytest.mark.parametrize(
    "raw",
    [
        "http://relay.test",
        "https://user:pass@relay.test",
        "https://relay.test/path",
        "https://relay.test?",
        "https://relay.test#",
        "https://relay.test/?x=1",
        " https://relay.test",
        "https://relay.test\n",
        "https://re\tlay.test",
        "https://relay.test\\@evil.test",
        "https://relay.test:99999",
        "https://relay.test:",
        "https://relay.test/%2e",
        "https://relay.test%2f.evil",
        "https://",
        "https://a..test",
        "https://[2001:db8::1]evil.test",
    ],
)
def test_hostile_origin_is_rejected(raw):
    from wingman.fleetsharing.config import canonical_origin

    with pytest.raises(ValueError):
        canonical_origin(raw)


@pytest.mark.parametrize("raw", BRACKETED_INVALID_ORIGINS)
def test_bracketed_authority_is_ipv6_only_never_rewritten_to_another_host(raw):
    from wingman.fleetsharing.config import canonical_origin

    with pytest.raises(ValueError):
        canonical_origin(raw)


def test_paired_origin_wins_over_distribution_default():
    from wingman.fleetsharing.config import resolve_relay_origin

    assert resolve_relay_origin() == "https://authgd.zoolanders.space"
    assert (
        resolve_relay_origin(paired_origin="https://old.example.test/")
        == "https://old.example.test"
    )
    assert (
        resolve_relay_origin(
            paired_origin="https://old.example.test",
            configured_origin="HTTPS://OLD.EXAMPLE.TEST:443",
        )
        == "https://old.example.test"
    )


def test_explicit_origin_change_refuses_existing_credentials():
    from wingman.fleetsharing.config import resolve_relay_origin

    with pytest.raises(ValueError, match="pairing"):
        resolve_relay_origin(
            paired_origin="https://old.example.test",
            configured_origin="https://new.example.test",
        )
    assert (
        resolve_relay_origin(configured_origin="https://new.example.test")
        == "https://new.example.test"
    )
