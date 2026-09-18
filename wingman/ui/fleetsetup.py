"""Detached setup observations, never saved command bodies or permission grants."""

import hashlib
import json
from dataclasses import asdict

from ..fleetsharing.protocol import COMBAT_CAPABILITY


def _fingerprint(value):
    # Equality witness for private history. No registry, secret, or authority is
    # minted here: the bridge must still compare against its current typed owner.
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def controls(status, *, configured_origin=None):
    automatic = status.automatic
    pending = automatic.pending
    observed = status.automatic_status
    consent = observed.consent if observed else None
    automatic_view = {
        "binding": status.metadata.binding,
        "observed": {
            "generation": consent.generation,
            "revision": consent.revision,
            "enabled": consent.enabled,
            "approver": observed.approver,
        }
        if consent
        else None,
        "pending": {
            "enabled": pending.command.enabled,
            "attempted": pending.attempted,
            "cancellation_pending": pending.cancel_after_on is not None,
        }
        if pending
        else None,
        "stage": status.automatic_stage,
        "choice": status.automatic_choice
        if status.automatic_stage == "queued"
        else pending.command.enabled
        if pending
        else None,
        "request": _fingerprint(status.automatic_request_id),
        "history": _fingerprint(asdict(automatic)),
    }
    pairing = status.pending_pairing
    recovery = status.pending_recovery
    return {
        "automatic": automatic_view,
        "setup": {
            "binding": status.metadata.binding,
            "configured_origin": configured_origin,
            "combat_approved": COMBAT_CAPABILITY
            in (status.metadata.approved_capabilities or ()),
            "history": _fingerprint(
                {
                    "automatic": asdict(automatic),
                    "queued_automatic": (
                        status.automatic_stage,
                        status.automatic_choice,
                        status.automatic_request_id,
                    ),
                    "queued_participation": (
                        status.participation,
                        status.participation_intent_id,
                        status.participation_order,
                    ),
                    "queued_pairing": (status.pairing, status.pairing_action_id),
                    "pairing": asdict(pairing) if pairing else None,
                    "recovery": asdict(recovery) if recovery else None,
                    "participation": asdict(status.pending_participation)
                    if status.pending_participation
                    else None,
                    "sources": [asdict(item) for item in status.pending_sources],
                    "cutover": [asdict(item) for item in status.cutover_outcomes],
                }
            ),
            "pairing_pending": pairing is not None or status.pairing == "queued",
            "recovery_pending": recovery is not None,
            "automatic_enabled": automatic.observed_consent.enabled
            if automatic.observed_consent
            else None,
            "automatic_pending": pending is not None
            or (
                status.automatic_stage == "queued"
                and status.automatic_choice is not None
            ),
            "participation_pending": status.pending_participation is not None
            or status.participation == "queued",
            "source_requests": len(status.pending_sources),
            "cutover": [asdict(item) for item in status.cutover_outcomes],
        },
    }
