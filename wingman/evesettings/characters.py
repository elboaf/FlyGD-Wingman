"""Authoritative ESI character status.

This seam is intentionally isolated from the rest of evesettings so later
profile-resolution logic can consume a single conservative contract: active
names are usable, deleted ids are permanent, and everything else stays
transient.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import __version__ as _version

logger = logging.getLogger(__name__)

ESI_URL = (
    "https://esi.evetech.net/latest/characters/{character_id}/?datasource=tranquility"
)
_USER_AGENT = f"FlyGD-Wingman/{_version} (+https://wingman.zoolanders.vip/)"
_TIMEOUT_SECONDS = 8.0

ACTIVE = "active"
DELETED = "deleted"
TRANSIENT = "transient"


def classify(status: int, body: str) -> tuple[str, str]:
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return TRANSIENT, ""
    if (
        status == 404
        and isinstance(parsed, dict)
        and parsed.get("error") == "Character has been deleted!"
    ):
        return DELETED, ""
    if not 200 <= status < 300 or not isinstance(parsed, dict):
        return TRANSIENT, ""
    name = parsed.get("name")
    if not isinstance(name, str) or not name.strip():
        return TRANSIENT, ""
    return ACTIVE, name.strip()


def fetch_character(
    character_id: int,
    *,
    transport=urllib.request.urlopen,
    timeout: float = _TIMEOUT_SECONDS,
) -> tuple[str, str]:
    try:
        request = urllib.request.Request(
            ESI_URL.format(character_id=character_id),
            headers={"User-agent": _USER_AGENT},
            method="GET",
        )
        with transport(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - unreadable error bodies are still transient
            body = ""
        return classify(exc.code, body)
    except Exception:
        # Offline machines are normal; transport failures are expected to
        # resolve as transient so the later profile resolver can keep moving.
        logger.debug("ESI character fetch failed", exc_info=True)
        return TRANSIENT, ""
    return classify(status, body)


def _positive_unique_ids(ids) -> list[int]:
    return [
        ident
        for ident in dict.fromkeys(ids)
        if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0
    ]


def resolve(
    ids,
    fetch=fetch_character,
    max_workers: int = 4,
) -> tuple[dict[int, str], set[int]]:
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    names: dict[int, str] = {}
    deleted: set[int] = set()
    candidates = _positive_unique_ids(ids)
    if not candidates:
        return names, deleted

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {pool.submit(fetch, ident): ident for ident in candidates}
        for future in as_completed(future_to_id):
            ident = future_to_id[future]
            try:
                status, name = future.result()
            except Exception:
                logger.debug(
                    "ESI character resolution failed for %s", ident, exc_info=True
                )
                continue
            if status == ACTIVE:
                names[ident] = name
            elif status == DELETED:
                deleted.add(ident)
    return names, deleted
