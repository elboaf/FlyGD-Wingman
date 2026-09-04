"""EVE SSO's authorize URL, now owned by `wingman.eveauth.sso`.

The PKCE/token-endpoint behaviour this module shares with
`wingman.eveskills.sso` is still fully exercised through that
compatibility module (test_eveskills_sso.py) -- re-exported names are the
literal same function objects, not a fork, so testing them once there
covers both. This file is scoped to what changed with the extraction:
`authorize_url` now requires an explicit scope set, with no capability
implied and no "every scope" fallback.
"""

import urllib.parse

import pytest

from wingman.eveauth import application, sso


def query_of(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parsed.query, strict_parsing=True)
    assert len(pairs) == len(dict(pairs)), "authorize URL had a duplicate key"
    return dict(pairs)


def test_authorize_url_uses_only_explicit_scopes():
    """Skills' own scopes produce a URL naming exactly those scopes --
    and nothing from Fittings' scope set leaks in just because both
    capabilities share this one function."""
    pkce = sso.generate_pkce()
    url = sso.authorize_url(pkce, application.SKILLS_SCOPES)
    assert query_of(url)["scope"] == " ".join(sorted(application.SKILLS_SCOPES))
    assert "esi-fittings" not in url


def test_authorize_url_with_fittings_scopes_names_only_fittings_scopes():
    """The reverse of the read-only Skills case: a Fittings caller's
    consent screen must never carry a Skills scope either."""
    pkce = sso.generate_pkce()
    url = sso.authorize_url(pkce, application.FITTINGS_SCOPES)
    assert query_of(url)["scope"] == " ".join(sorted(application.FITTINGS_SCOPES))
    assert "esi-skills" not in url


def test_authorize_url_requires_at_least_one_scope():
    """There is no all-capabilities default to fall back to: an empty
    scope set is refused outright rather than silently producing a URL
    with an empty `scope=` parameter."""
    pkce = sso.generate_pkce()
    with pytest.raises(ValueError, match="scope"):
        sso.authorize_url(pkce, ())


def test_authorize_url_accepts_scopes_from_any_capability_together():
    """A caller MAY combine capabilities deliberately (a union it built
    itself), which is different from this function ever assuming one on
    the caller's behalf -- the guarantee is no implicit default, not that
    the parameter is capability-typed."""
    pkce = sso.generate_pkce()
    combined = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    url = sso.authorize_url(pkce, combined)
    assert query_of(url)["scope"] == " ".join(sorted(combined))
