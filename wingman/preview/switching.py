"""The minimize-inactive-clients decision, as pure logic.

The preview subsystem's Win32 calls cannot be exercised in CI (ubuntu and
windows both run, but no Win32 call in the preview path has ever run
against a real EVE client in any automated test). preview/bookmarks.py
already draws this line for the AutoHotkey-supervising engine; this module
draws the same line for switching: host.py keeps only the Win32 calls and
the ordering, and every decision of *whether* to minimize lives here where
it can be tested on Linux.
"""


def should_minimize(*, enabled, activated, previous_key, next_key, never) -> bool:
    """Whether to minimize the previously-active client after a switch.

    False in every one of these cases, True otherwise:

    - the feature is off (`enabled` is falsy)
    - `activated` is falsy -- the activation of the next client failed.
      Ported deliberately from TriffView, whose switch sequence returns
      early when activation fails. Without this guard, a failed switch
      would minimize the client the user was just looking at and leave
      them staring at an empty desktop with nothing focused -- worse than
      doing nothing.
    - there is no previous client (`previous_key` is None or empty)
    - the previous and next client are the same (nothing to switch away
      from)
    - the previous character is in `never` (the preview.never_minimize
      roster)
    """
    if not enabled:
        return False
    if not activated:
        return False
    if not previous_key:
        return False
    if previous_key == next_key:
        return False
    return previous_key not in (never or [])
