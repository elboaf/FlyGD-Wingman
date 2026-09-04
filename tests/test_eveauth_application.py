"""EVE application identity, now owned by `wingman.eveauth.application`.

Skills' own identity tests (CLIENT_ID, redirect assembly, issuer set,
placeholder guard) still live in test_eveskills_paths.py, unchanged in
substance, because `wingman.eveskills.application` re-exports (and, for
`CLIENT_ID`/`is_configured`, re-declares) every one of those names and
production code keeps reaching them that way. This file covers what did
NOT exist before this extraction: the capability scope registry, and the
guarantee that no capability's scopes are ever implied by another's.
"""

from wingman.eveauth import application


def test_capabilities_have_separate_scope_sets():
    """Skills' two read-only scopes and Fittings' read/write pair are
    pinned exactly, and by capability name -- not by position, order, or
    any other accident of how the dict happens to iterate."""
    assert application.CAPABILITY_SCOPES[application.SKILLS] == frozenset(
        {"esi-skills.read_skills.v1", "esi-skills.read_skillqueue.v1"}
    )
    assert application.CAPABILITY_SCOPES[application.FITTINGS] == frozenset(
        {"esi-fittings.read_fittings.v1", "esi-fittings.write_fittings.v1"}
    )


def test_capability_scope_sets_are_disjoint():
    """A user granting one capability's scopes must never be read as
    having granted the other's. If these ever shared a scope, a Skills
    sign-in would silently double as partial Fittings authorisation with
    no consent screen ever asking for it."""
    assert application.SKILLS_SCOPES.isdisjoint(application.FITTINGS_SCOPES)


def test_the_capability_scope_registry_has_exactly_the_two_known_capabilities():
    """Every capability this app knows about is registered, and nothing
    else is -- a stray third entry would mean some caller can request
    scopes with no name pinned to them anywhere."""
    assert set(application.CAPABILITY_SCOPES) == {
        application.SKILLS,
        application.FITTINGS,
    }


def test_skills_and_fittings_are_distinct_capability_names():
    assert application.SKILLS != application.FITTINGS


def test_full_authorization_names_exactly_the_current_product_capabilities():
    assert application.FULL_AUTH_CAPABILITIES == (
        application.SKILLS,
        application.FITTINGS,
    )


def test_full_authorization_scopes_are_derived_from_the_explicit_capabilities():
    expected = application.SKILLS_SCOPES | application.FITTINGS_SCOPES
    assert application.FULL_AUTH_SCOPES == expected
    assert application.FULL_AUTH_SCOPES == frozenset(
        {
            "esi-skills.read_skills.v1",
            "esi-skills.read_skillqueue.v1",
            "esi-fittings.read_fittings.v1",
            "esi-fittings.write_fittings.v1",
        }
    )


def test_a_future_capability_does_not_widen_full_authorization(monkeypatch):
    monkeypatch.setitem(application.CAPABILITY_SCOPES, "future", frozenset({"future.scope"}))
    assert "future.scope" not in application.FULL_AUTH_SCOPES
