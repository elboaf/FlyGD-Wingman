"""PRODUCT.md's documented terms -- tests.

Fleet sharing is a deliberate, narrow exception to the "no telemetry" rule
(see docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md).
This test asserts PRODUCT.md states its bounds in exactly the words the
design's product-boundary prerequisite requires, once each, so a future
edit cannot loosen or duplicate the exception without this test noticing.
"""

from pathlib import Path

PRODUCT_MD = Path(__file__).resolve().parent.parent / "PRODUCT.md"


def test_product_md_states_the_fleet_sharing_exception_once_each():
    text = PRODUCT_MD.read_text(encoding="utf-8")
    required = (
        "Fleet sharing is optional and off by default",
        "authGD Member",
        "no raw combat logs",
        "does not automate gameplay",
    )
    assert all(text.count(phrase) == 1 for phrase in required)
