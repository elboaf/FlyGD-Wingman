"""Pure fleet-sharing protocol boundary: projection, keys, and a signed client.

This package is the isolated tracer's Wingman-side transport contract for
authGD's fleet relay -- default-off, with no UI, no pairing flow, and no
real network call anywhere in `client`/`projection`/`crypto`/`state`
themselves (every one of those is pure or a local persistence seam). See
docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md and
`wingman.settings.validated_fleet_sharing` for the persisted, normalized
predicate that gates any of this from ever running.

- `model` -- frozen wire-safe dataclasses.
- `projection` -- pure local-FleetSnapshot -> PublishRow sparse projection.
- `crypto` -- Ed25519 keys, the `fleet-v1` canonical request contract, and
  the pairing completion preimage/signature.
- `state` -- persisted device identity/session document and its DPAPI seam.
- `client` -- signed HTTP transport primitives (pairing, catalogue, publish).
- `worker` -- the non-blocking coordinator-facing publisher: the one piece
  here that DOES perform real HTTP once a device is actually paired, kept
  off the coordinator's own dispatcher thread entirely (see its module
  docstring). No pairing flow writes a device identity anywhere in this
  tracer yet, so this stays inert -- `SharingStatus(state="stopped")` -- on
  every real install today.
"""

from .client import FleetRelayClient, FleetRelayError, PairingBegin, PairingComplete
from .crypto import sign_request
from .model import CatalogueCharacter, FleetCatalogue, PublishRow
from .projection import project_snapshot
from .state import DeviceIdentity, SharingState

__all__ = [
    "CatalogueCharacter",
    "DeviceIdentity",
    "FleetCatalogue",
    "FleetRelayClient",
    "FleetRelayError",
    "PairingBegin",
    "PairingComplete",
    "PublishRow",
    "SharingState",
    "project_snapshot",
    "sign_request",
]
