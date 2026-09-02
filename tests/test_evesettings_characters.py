import json
import threading

import pytest

from wingman.evesettings import characters


def test_only_the_exact_deleted_404_is_destructive():
    body = json.dumps({"status": 404, "error": "Character has been deleted!"})
    assert characters.classify(404, body) == (characters.DELETED, "")
    assert characters.classify(404, json.dumps({"error": "not found"})) == (
        characters.TRANSIENT,
        "",
    )


@pytest.mark.parametrize("status", [422, 429, 500, 503])
def test_other_failures_are_transient(status):
    assert characters.classify(status, "") == (characters.TRANSIENT, "")


def test_success_requires_a_nonempty_name():
    assert characters.classify(200, json.dumps({"name": " Pilot "})) == (
        characters.ACTIVE,
        "Pilot",
    )
    assert characters.classify(200, json.dumps({"name": ""})) == (
        characters.TRANSIENT,
        "",
    )


def test_fetch_character_uses_the_injected_transport_and_user_agent():
    seen = {}

    class FakeResponse:
        status = 200

        def read(self):
            return json.dumps({"name": "Pilot One"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def transport(request, timeout=None):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["headers"] = dict(request.headers)
        return FakeResponse()

    assert characters.fetch_character(123, transport=transport) == (
        characters.ACTIVE,
        "Pilot One",
    )
    assert seen["url"].endswith("/characters/123/?datasource=tranquility")
    assert seen["timeout"] == 8.0
    assert seen["headers"]["User-agent"].startswith("FlyGD-Wingman/")


@pytest.mark.parametrize("status", [404, 422, 429, 500, 503])
def test_fetch_character_classifies_http_error_bodies(status):
    import urllib.error

    class FakeError(urllib.error.HTTPError):
        def __init__(self, code, body):
            self.code = code
            self._body = body

        def read(self):
            return self._body.encode()

    def transport(request, timeout=None):
        raise FakeError(status, json.dumps({"error": "Character has been deleted!"}))

    expected = characters.DELETED if status == 404 else characters.TRANSIENT
    assert characters.fetch_character(123, transport=transport) == (expected, "")


def test_resolve_returns_active_names_and_deleted_ids():
    def fetch(ident):
        return (
            (characters.DELETED, "")
            if ident == 2
            else (
                characters.ACTIVE,
                f"Pilot {ident}",
            )
        )

    names, deleted = characters.resolve([1, 2, 1], fetch=fetch, max_workers=2)
    assert names == {1: "Pilot 1"}
    assert deleted == {2}


def test_resolve_deduplicates_and_drops_non_positive_ids():
    calls = []

    def fetch(ident):
        calls.append(ident)
        return characters.ACTIVE, f"Pilot {ident}"

    names, deleted = characters.resolve([1, 1, 0, -5, 2], fetch=fetch, max_workers=2)
    assert calls == [1, 2]
    assert names == {1: "Pilot 1", 2: "Pilot 2"}
    assert deleted == set()


def test_resolve_limits_parallel_fetches_to_the_requested_worker_count():
    active = 0
    peak = 0
    lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()
    over_limit = threading.Event()
    result = {}

    def fetch(ident):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active > 2:
                over_limit.set()
            if active == 2:
                started.set()
        release.wait(timeout=2)
        with lock:
            active -= 1
        return characters.ACTIVE, f"Pilot {ident}"

    def run():
        result["value"] = characters.resolve(
            [1, 2, 3, 4, 5], fetch=fetch, max_workers=2
        )

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(2)
    with lock:
        assert peak == 2
        assert not over_limit.is_set()
    release.set()
    thread.join(2)
    assert thread.is_alive() is False
    names, deleted = result["value"]
    assert names == {i: f"Pilot {i}" for i in range(1, 6)}
    assert deleted == set()
