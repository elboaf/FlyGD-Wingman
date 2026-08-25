"""The three new state paths, and the guard that stops an unregistered
build from opening a browser at CCP with a placeholder client id.

paths.py's rule is that every state location is a zero-arg function
returning a Path, never a module constant -- monkeypatching state_dir()
is how the whole suite redirects state into tmp_path, and a constant
computed at import time would defeat it.
"""

from obs_youtube_uploader import paths
from obs_youtube_uploader.eveskills import application


def test_skill_state_files_live_together(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.eve_skills_file() == tmp_path / "eve_skills.json"
    assert paths.eve_skills_cache_file() == tmp_path / "eve_skills_cache.json"
    assert paths.skill_plans_dir() == tmp_path / "skill_plans"


def test_the_state_document_and_its_backup_are_siblings(monkeypatch, tmp_path):
    """The .bak tier lives beside the primary, so both must sit under
    state_dir() and not, say, in tmp_dir() where a cleanup sweep would
    take the only copy of every character's refresh token with it."""
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.eve_skills_file().parent == tmp_path


def test_the_placeholder_client_id_is_not_configured(monkeypatch):
    """The guard outlives our own registration: a fork that re-points
    this at its own application starts from the placeholder, and
    is_configured() is what the controller checks before offering `Add
    character`. Without it the button launches a browser at
    login.eveonline.com with a literal placeholder in the query string,
    and CCP's error page is not a recognisable diagnosis for 'this build
    was never registered'."""
    monkeypatch.setattr(
        application, "CLIENT_ID", "REPLACE_WITH_REGISTERED_EVE_CLIENT_ID"
    )
    assert application.is_configured() is False


def test_the_empty_client_id_is_not_configured(monkeypatch):
    """A fork that blanks the constant rather than replacing it gets the
    same disabled button, not an authorize URL with `client_id=`."""
    monkeypatch.setattr(application, "CLIENT_ID", "")
    assert application.is_configured() is False


def test_the_shipped_client_id_is_configured():
    """This build is registered, so the Skills tab offers `Add
    character` rather than the not-configured notice."""
    assert application.CLIENT_ID == "c2ea757d14a04283980be1fa6aa084ee"
    assert application.is_configured() is True


def test_the_redirect_uri_is_assembled_from_its_own_parts():
    """The URI is registered with CCP and must match byte for byte. The
    loopback listener validates Host and path against these same three
    constants, so a hand-written URI that drifted from them would fail
    the listener's own check rather than at the redirect."""
    assert application.REDIRECT_URI == "http://127.0.0.1:51779/callback/"
    assert application.REDIRECT_HOST == "127.0.0.1"
    assert application.REDIRECT_PORT == 51779
    assert application.REDIRECT_PATH == "/callback/"


def test_the_scopes_are_read_only_and_exactly_two():
    """Widening this tuple widens the consent screen every user sees.
    Nothing in this subsystem writes to ESI."""
    assert application.SCOPES == (
        "esi-skills.read_skills.v1",
        "esi-skills.read_skillqueue.v1",
    )


def test_the_user_agent_carries_the_app_version_and_a_contact_url():
    """CCP asks third-party clients to identify themselves; an anonymous
    agent is what gets an application rate-limited without warning."""
    from obs_youtube_uploader import __version__

    assert application.USER_AGENT.startswith(f"FlyGD-Wingman/{__version__} ")
    assert "github.com/elboaf/FlyGD-Wingman" in application.USER_AGENT


def test_all_three_issuer_spellings_are_accepted():
    """jwt.py compares the `iss` claim against ACCEPTED_ISSUERS by
    equality and nothing else, so a missing spelling is not a near-miss:
    it is a rejected token and a character that can never authenticate.
    TriffView's own validator (EveJwtValidator.cs:12-15) accepts all
    three -- the bare authority, the full origin, and the full origin
    with a trailing slash, since OAuth issuers appear both ways."""
    assert application.ACCEPTED_ISSUERS == frozenset(  # noqa: SIM300
        {
            "login.eveonline.com",
            "https://login.eveonline.com",
            "https://login.eveonline.com/",
        }
    )
