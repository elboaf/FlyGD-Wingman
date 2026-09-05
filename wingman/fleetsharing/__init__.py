"""Pure fleet-sharing protocol boundary: projection, keys, and a signed client.

This package is the isolated tracer's Wingman-side transport contract for
authGD's fleet relay -- default-off, with no UI, no coordinator wiring, and
no real network call anywhere in it. See
docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md and
`wingman.settings.validated_fleet_sharing` for the persisted, normalized
predicate that gates any of this from ever running.

- `model` -- frozen wire-safe dataclasses.
- `projection` -- pure local-FleetSnapshot -> PublishRow sparse projection.
- `crypto` -- Ed25519 keys, the `fleet-v1` canonical request contract, and
  the pairing completion preimage/signature.
- `state` -- persisted device identity/session document and its DPAPI seam.
- `client` -- signed HTTP transport primitives (pairing, catalogue, publish).
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
