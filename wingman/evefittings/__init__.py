"""EVE Online Personal Fittings: consolidate, curate, and copy loadouts.

Fittings shares its secure ESI transport with Skills (see
`wingman.eveesi`) rather than duplicating retry, redaction, and
redirect-refusal logic a second time. This package owns the pinned
fitting contracts (`contracts.py`) plus, in later tasks, the fitting
model, authority integration, and controller.
"""
