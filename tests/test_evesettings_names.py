"""ESI universe/names. The transport is injected everywhere, so nothing here
touches the network."""
import json

import pytest

from obs_youtube_uploader.evesettings import names


def test_classify_reads_a_successful_body():
    body = json.dumps([{"id": 1, "name": "Pilot One"},
                       {"id": 2, "name": "Pilot Two"}])
    outcome, resolved = names.classify(200, body)
    assert outcome == names.RESOLVED
    assert resolved == {1: "Pilot One", 2: "Pilot Two"}


def test_classify_treats_a_json_error_404_as_invalid_ids():
    outcome, _ = names.classify(404, json.dumps({"error": "not found"}))
    assert outcome == names.INVALID


def test_classify_treats_a_plain_text_404_as_transient():
    """A route-level 404 says nothing about the ids. Bisecting on it would
    permanently blacklist every character the user has."""
    outcome, _ = names.classify(404, "page not found")
    assert outcome == names.TRANSIENT


def test_classify_treats_an_empty_error_404_as_transient():
    outcome, _ = names.classify(404, json.dumps({"error": "   "}))
    assert outcome == names.TRANSIENT


@pytest.mark.parametrize("status", [420, 429, 500, 502, 503])
def test_classify_treats_other_failures_as_transient(status):
    outcome, _ = names.classify(status, "")
    assert outcome == names.TRANSIENT


def test_classify_treats_unparseable_success_as_transient():
    outcome, _ = names.classify(200, "not json")
    assert outcome == names.TRANSIENT


def test_classify_drops_entries_with_no_usable_name():
    body = json.dumps([{"id": 1, "name": "  "}, {"id": 0, "name": "x"},
                       {"id": 3, "name": "Pilot"}])
    _, resolved = names.classify(200, body)
    assert resolved == {3: "Pilot"}


def test_resolve_returns_names_from_one_clean_batch():
    def fetch(ids):
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    assert names.resolve([1, 2], set(), fetch) == {1: "Pilot 1", 2: "Pilot 2"}


def test_resolve_bisects_to_isolate_a_bad_id():
    bad = 3

    def fetch(ids):
        if bad in ids:
            return names.INVALID, {}
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    invalid = set()
    resolved = names.resolve([1, 2, 3, 4], invalid, fetch)
    assert invalid == {bad}
    assert resolved == {1: "Pilot 1", 2: "Pilot 2", 4: "Pilot 4"}


def test_resolve_never_poisons_the_cache_on_a_transient_failure():
    def fetch(ids):
        return names.TRANSIENT, {}

    invalid = set()
    assert names.resolve([1, 2, 3], invalid, fetch) == {}
    assert invalid == set()


def test_resolve_does_not_bisect_a_transient_failure():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.TRANSIENT, {}

    names.resolve([1, 2, 3, 4], set(), fetch)
    assert calls == [[1, 2, 3, 4]]


def test_resolve_skips_ids_already_known_invalid():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    names.resolve([1, 2], {2}, fetch)
    assert calls == [[1]]


def test_resolve_deduplicates_and_drops_non_positive_ids():
    calls = []

    def fetch(ids):
        calls.append(list(ids))
        return names.RESOLVED, {}

    names.resolve([1, 1, 0, -5, 2], set(), fetch)
    assert calls == [[1, 2]]


def test_resolve_with_nothing_to_do_makes_no_call():
    def fetch(ids):  # pragma: no cover - must never run
        raise AssertionError("should not be called")

    assert names.resolve([], set(), fetch) == {}


def test_cache_reports_whether_it_learned_anything():
    cache = names.NameCache()

    def fetch(ids):
        return names.RESOLVED, {i: f"Pilot {i}" for i in ids}

    assert cache.resolve_missing([1], fetch=fetch) is True
    assert cache.names == {1: "Pilot 1"}
    # Second pass has nothing missing, so nothing was learned.
    assert cache.resolve_missing([1], fetch=fetch) is False


def test_cache_labels_unresolved_ids_with_a_fallback():
    cache = names.NameCache()
    assert cache.label(98123456) == "Character 98123456"
    cache.names[98123456] = "Pilot"
    assert cache.label(98123456) == "Pilot"


def test_fetch_batch_classifies_an_http_error(monkeypatch):
    import urllib.error

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            self.code = 404

        def read(self):
            return json.dumps({"error": "not found"}).encode()

    def transport(request, timeout=None):
        raise FakeError()

    outcome, _ = names.fetch_batch([1], transport=transport)
    assert outcome == names.INVALID


def test_fetch_batch_treats_a_network_error_as_transient():
    def transport(request, timeout=None):
        raise OSError("no route to host")

    outcome, _ = names.fetch_batch([1], transport=transport)
    assert outcome == names.TRANSIENT


def test_fetch_batch_posts_the_ids_as_json():
    seen = {}

    class FakeResponse:
        status = 200

        def read(self):
            return json.dumps([{"id": 1, "name": "Pilot"}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def transport(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        return FakeResponse()

    outcome, resolved = names.fetch_batch([1], transport=transport)
    assert outcome == names.RESOLVED and resolved == {1: "Pilot"}
    assert seen["body"] == [1]
    assert "universe/names" in seen["url"]


def test_a_non_serialisable_id_degrades_instead_of_raising(tmp_path):
    """json.dumps used to sit outside the try, so this raised.

    Every other failure in this module returns TRANSIENT, because names
    are cosmetic and the tool is fully usable offline. resolve() filters
    to positive ints before calling here, so nothing reaches it today --
    which is exactly why the contract must not depend on that filter.
    """
    def unreachable(*_args, **_kwargs):  # pragma: no cover - never called
        raise AssertionError("the request was built, so the id serialised")

    assert names.fetch_batch([object()], transport=unreachable) == (
        names.TRANSIENT, {})


def test_an_unbuildable_request_degrades_instead_of_raising(monkeypatch):
    """The other statement that used to sit outside the try."""
    def explode(*_args, **_kwargs):
        raise ValueError("unknown url type")

    monkeypatch.setattr(names.urllib.request, "Request", explode)
    assert names.fetch_batch([98123456]) == (names.TRANSIENT, {})
