"""The minimize-inactive-clients decisions, as pure logic.

The preview subsystem's Win32 calls cannot be exercised in CI (ubuntu and
windows both run, but no Win32 call in the preview path has ever run
against a real EVE client in any automated test). preview/bookmarks.py
already draws this line for the AutoHotkey-supervising engine; this module
draws the same line for switching: host.py keeps only the Win32 calls and
the ordering, and every decision of *whether* to minimize -- and whether
to undo one -- lives here where it can be tested on Linux.
"""


def should_minimize(*, enabled, previous_key, next_key, never) -> bool:
    """Whether to minimize the previously-active client, BEFORE the switch.

    False in every one of these cases, True otherwise:

    - the feature is off (`enabled` is falsy)
    - there is no previous client (`previous_key` is None or empty)
    - the previous and next client are the same (nothing to switch away
      from -- and with minimize-first this runs before the activation's
      own early-return, so it is the only thing stopping a click on the
      foreground client from minimizing it)
    - the previous character is in `never` (the preview.never_minimize
      roster)

    There is no `activated` input any more: the minimize happens first,
    as in EVE-O Preview's SwitchActiveClient, so the activation's verdict
    is not known yet. should_restore is where that verdict lands.
    """
    if not enabled:
        return False
    if not previous_key:
        return False
    if previous_key == next_key:
        return False
    return previous_key not in (never or [])


def should_restore(*, activated, attempted) -> bool:
    """Whether a refused switch must bring the outgoing client back.

    TriffView's safety property was "a failed switch minimizes nothing",
    kept by activating first. With minimize-first the outgoing client is
    already down when the refusal is learned, so this policy requests its
    restoration. Windows can refuse that request too; without the attempt,
    however, a refused activation necessarily leaves the old client down and
    the new one absent, strictly worse than the switch simply not working.

    `attempted`, not "minimized": the send's verdict is not trusted here.
    A send that timed out is still delivered and processed later, so a
    client the host believes is "still where it was" can go down 50ms
    after a refused switch. Restoring on every attempt covers that, and
    costs nothing when the send really did fail -- activate() on a window
    that still holds the foreground is its own early return.
    """
    return attempted and not activated
