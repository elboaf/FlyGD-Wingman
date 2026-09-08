from types import SimpleNamespace

import pytest

from wingman import eveesi
from wingman.eveskills import esi as skills_esi

PATH = "/v4/characters/95/skills/"
CAPABILITY = "skills"
FIRST_TOKEN = "first-secret-token"
SECOND_TOKEN = "second-secret-token"


def response(status: int, *, etag: str = "", error: str = "") -> eveesi.EsiResponse:
    return eveesi.EsiResponse(status, None, error, etag, "GET", PATH)


def token_result(token, error="", invalidated=False, reason=""):
    return SimpleNamespace(
        token=token,
        error=error,
        grant_invalidated=invalidated,
        reason=reason,
    )


class Authority:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def access_token(self, character_id, capability, *, rejected_token=None):
        self.calls.append((character_id, capability, rejected_token))
        return self.results.pop(0)


class Client:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, path, *, token=None, etag=None):
        self.calls.append((path, token, etag))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def authenticated_get(authority, client, **kwargs):
    adapter = getattr(eveesi, "authenticated_get", None)
    assert adapter is not None, "shared authenticated GET adapter is missing"
    return adapter(authority, client, **kwargs)


@pytest.mark.parametrize("status", [200, 304])
def test_success_returns_the_exact_response_and_preserves_the_caller_etag(status):
    expected = response(status, etag='"response"')
    authority = Authority(token_result(FIRST_TOKEN))
    client = Client(expected)

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
        etag='"caller"',
    )

    assert result.response is expected
    assert result.error == ""
    assert result.authority_invalidated is False
    assert result.authority_reason == ""
    assert result.endpoint_denied is False
    assert result.authority_error is False
    assert client.calls == [(PATH, FIRST_TOKEN, '"caller"')]


def test_one_401_refreshes_with_the_rejected_token_and_retries_once():
    expected = response(200, etag='"fresh"')
    authority = Authority(
        token_result(FIRST_TOKEN),
        token_result(SECOND_TOKEN),
    )
    client = Client(response(401, error="expired"), expected)

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is expected
    assert result.authority_error is False
    assert authority.calls == [
        (95, CAPABILITY, None),
        (95, CAPABILITY, FIRST_TOKEN),
    ]
    assert client.calls == [
        (PATH, FIRST_TOKEN, None),
        (PATH, SECOND_TOKEN, None),
    ]


@pytest.mark.parametrize("statuses", [(401, 401), (403,), (401, 403)])
def test_endpoint_denial_does_not_claim_authority_invalidation(statuses):
    authority_results = [token_result(FIRST_TOKEN)]
    if len(statuses) == 2:
        authority_results.append(token_result(SECOND_TOKEN))
    authority = Authority(*authority_results)
    client = Client(*(response(status, error="denied") for status in statuses))

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is None
    assert result.endpoint_denied is True
    assert result.authority_invalidated is False
    assert result.authority_reason == ""
    assert result.authority_error is False
    assert len(client.calls) == len(statuses)


def test_token_acquisition_failure_is_classified_as_an_authority_error():
    authority = Authority(
        token_result(None, "Re-authenticate through shared EVE authority.")
    )
    client = Client()

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is None
    assert result.error == "Re-authenticate through shared EVE authority."
    assert result.authority_error is True
    assert result.authority_invalidated is False
    assert result.endpoint_denied is False
    assert client.calls == []


def test_authority_invalidation_after_401_remains_distinct_bounded_and_redacted():
    authority = Authority(
        token_result(FIRST_TOKEN),
        token_result(
            None,
            f"authority rejected {FIRST_TOKEN}: " + ("x" * 5000),
            invalidated=True,
            reason="owner_changed",
        ),
    )
    client = Client(response(401, error="expired"))

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is None
    assert 0 < len(result.error) <= 4096
    assert FIRST_TOKEN not in result.error
    assert result.authority_invalidated is True
    assert result.authority_reason == "owner_changed"
    assert result.endpoint_denied is False
    assert result.authority_error is True
    assert len(client.calls) == 1


@pytest.mark.parametrize("phase", ["initial", "retry"])
@pytest.mark.parametrize("exception_type", [OSError, ValueError, RecursionError])
def test_expected_get_exceptions_are_bounded_and_redact_every_used_token(
    phase, exception_type
):
    secret_error = f"failed with {FIRST_TOKEN} and {SECOND_TOKEN}: " + ("x" * 5000)
    authority_results = [token_result(FIRST_TOKEN)]
    outcomes = []
    if phase == "retry":
        authority_results.append(token_result(SECOND_TOKEN))
        outcomes.append(response(401, error="expired"))
    outcomes.append(exception_type(secret_error))
    authority = Authority(*authority_results)
    client = Client(*outcomes)

    result = authenticated_get(
        authority,
        client,
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is None
    assert 0 < len(result.error) <= 4096
    assert FIRST_TOKEN not in result.error
    if phase == "retry":
        assert SECOND_TOKEN not in result.error
    assert result.authority_invalidated is False
    assert result.endpoint_denied is False
    assert result.authority_error is False


def test_empty_expected_exception_uses_its_class_name():
    result = authenticated_get(
        Authority(token_result(FIRST_TOKEN)),
        Client(OSError()),
        character_id=95,
        capability=CAPABILITY,
        path=PATH,
    )

    assert result.response is None
    assert result.error == "OSError"
    assert result.authority_error is False


def test_type_error_from_get_escapes_instead_of_hiding_a_programmer_error():
    authority = Authority(token_result(FIRST_TOKEN))
    client = Client(TypeError("broken client contract"))

    with pytest.raises(TypeError, match="broken client contract"):
        authenticated_get(
            authority,
            client,
            character_id=95,
            capability=CAPABILITY,
            path=PATH,
        )


def test_skills_compatibility_module_re_exports_the_adapter_contract():
    result_type = getattr(eveesi, "AuthenticatedGetResult", None)
    adapter = getattr(eveesi, "authenticated_get", None)

    assert result_type is not None
    assert skills_esi.AuthenticatedGetResult is result_type
    assert skills_esi.authenticated_get is adapter
