"""Character id -> name, against ESI's universe/names.

Unauthenticated: no SSO, no token, no scopes. Names are cosmetic and every
failure degrades to "Character 98123456", so the tool is fully usable offline.

The endpoint rejects an ENTIRE batch with 404 when one id in it is
unresolvable, so a rejection identifies no particular id -- hence the bisect.
The trap is that ESI also 404s a moved or renamed route, and treating that as
invalid-ids would blacklist every character the user has. The two are
separated by response shape, not wording, so CCP can reword the message.
"""
import json
import logging
import urllib.error
import urllib.request

from .. import __version__ as _version

logger = logging.getLogger(__name__)

ESI_URL = ("https://esi.evetech.net/latest/universe/names/"
           "?datasource=tranquility")
_USER_AGENT = f"FlyGD-Wingman/{_version} (+https://wingman.zoolanders.vip/)"
_TIMEOUT_SECONDS = 8.0
# ESI's documented cap for this endpoint.
MAX_BATCH = 1000

RESOLVED = "resolved"
INVALID = "invalid"
TRANSIENT = "transient"


def _is_invalid_ids_body(body: str) -> bool:
    """A JSON object carrying a non-empty "error" string.

    Matched on shape rather than exact wording: the alternative is a
    plain-text gateway body, and a reworded message must not start
    blacklisting ids.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return False
    error = parsed.get("error") if isinstance(parsed, dict) else None
    return isinstance(error, str) and bool(error.strip())


def classify(status: int, body: str) -> tuple[str, dict]:
    if status == 404:
        return (INVALID if _is_invalid_ids_body(body) else TRANSIENT), {}
    if not 200 <= status < 300:
        return TRANSIENT, {}
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return TRANSIENT, {}
    if not isinstance(parsed, list):
        return TRANSIENT, {}
    resolved = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        ident, name = item.get("id"), item.get("name")
        if (isinstance(ident, int) and not isinstance(ident, bool)
                and ident > 0 and isinstance(name, str) and name.strip()):
            resolved[ident] = name.strip()
    return RESOLVED, resolved


def fetch_batch(ids, *, transport=urllib.request.urlopen,
                timeout: float = _TIMEOUT_SECONDS) -> tuple[str, dict]:
    # Building the request sits INSIDE the try with the send. Everything
    # else here degrades -- names are cosmetic and every failure returns
    # TRANSIENT -- and json.dumps on a non-serialisable id, or Request()
    # on a malformed URL, would be the one path that raises instead,
    # taking down the caller for a decoration. resolve() filters to
    # positive ints first, so nothing reaches this today; the contract
    # should not rest on a caller upstream continuing to be careful.
    try:
        payload = json.dumps(list(ids)).encode("utf-8")
        request = urllib.request.Request(
            ESI_URL, data=payload,
            headers={"Content-type": "application/json",
                     "User-agent": _USER_AGENT},
            method="POST")
        with transport(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a body we cannot read is not a verdict
            body = ""
        return classify(exc.code, body)
    except Exception:
        # Logged because TRANSIENT means "retry next pass", and a caller
        # bug -- a non-serialisable id, a malformed URL -- retries forever
        # while every row shows its fallback label. Before these two
        # statements moved inside the try, such a bug escaped to
        # eve_settings_resolve_names, which logs it. Debug, not warning:
        # an offline machine takes this arm on every pass and that is not
        # a fault.
        logger.debug("ESI name batch could not be sent", exc_info=True)
        return TRANSIENT, {}
    return classify(status, body)


def resolve(ids, known_invalid: set, fetch) -> dict:
    """Names for *ids*, bisecting around any the endpoint rejects."""
    candidates = [i for i in dict.fromkeys(ids)
                  if isinstance(i, int) and i > 0 and i not in known_invalid]
    resolved: dict = {}
    for start in range(0, len(candidates), MAX_BATCH):
        _resolve_batch(candidates[start:start + MAX_BATCH],
                       known_invalid, fetch, resolved)
    return resolved


def _resolve_batch(ids, known_invalid: set, fetch, resolved: dict) -> None:
    if not ids:
        return
    outcome, names = fetch(ids)
    if outcome == RESOLVED:
        resolved.update(names)
        return
    if outcome == TRANSIENT:
        # Says nothing about validity: leave them unresolved and try again
        # on the next pass. Never bisect, never remember.
        return
    if len(ids) == 1:
        known_invalid.add(ids[0])
        return
    half = len(ids) // 2
    _resolve_batch(ids[:half], known_invalid, fetch, resolved)
    _resolve_batch(ids[half:], known_invalid, fetch, resolved)


class NameCache:
    """Process-lifetime memo. Names are free to re-fetch on the next launch."""

    def __init__(self):
        self.names: dict = {}
        self.invalid: set = set()

    def resolve_missing(self, ids, fetch=fetch_batch) -> bool:
        """Resolve what is not cached. True when at least one name was new."""
        missing = [i for i in ids
                   if i not in self.names and i not in self.invalid]
        if not missing:
            return False
        found = resolve(missing, self.invalid, fetch)
        self.names.update(found)
        return bool(found)

    def label(self, character_id: int) -> str:
        return self.names.get(character_id, f"Character {character_id}")
