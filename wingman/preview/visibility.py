"""The hide-on-lost-focus decision, as pure logic.

Same line switching.py draws, for the same reason: host.py keeps the Win32
calls and the ordering, and every decision of *whether* to hide lives here
where it can be tested on Linux.

Ported from TriffView's HideOnLostFocus (TriffViewSubsystem.cs:3516), which
inherited it from EVE-O Preview's HideThumbnailsOnLostFocus. TriffView's
condition is `clients.All(client => client.Handle != foreground)`; the
ownership clause below is ours and has no counterpart there. TriffView does
carry a `suppressLostFocusHide` parameter (:3456) that is never passed true,
but that is a blanket override of the whole hide rather than a test of who
owns the foreground -- a different thing that happens to be dead.
"""


def should_hide(*, enabled, foreground, client_hwnds, foreground_is_ours) -> bool:
    """Whether every preview should be hidden right now.

    True only when the feature is on AND the foreground window belongs to
    neither an EVE client nor to us.

    The user asked for "hide when all EVE windows are minimized" and this
    answers that too, without a separate IsIconic sweep: a minimized window
    cannot hold the foreground, so if every client is minimized the
    foreground is by definition something else.

    `foreground_is_ours` covers Wingman's own windows -- the main window, a
    WM.confirm dialog, the tray menu, and the previews themselves. It is
    resolved by process rather than by handle, because PreviewHost is built
    before the webview window exists and so can never be handed its HWND.
    Without it, opening Wingman to arrange previews would hide the very
    previews being arranged.

    A foreground of 0 -- the window is being destroyed, or a secure desktop
    (UAC, lock screen) holds it -- hides. Nothing of ours is on screen to
    mirror. Ownership is still checked first: it is the more specific
    claim, and a host that reported 0 as ours would otherwise flicker.
    """
    if not enabled:
        return False
    if foreground_is_ours:
        return False
    return foreground not in (client_hwnds or [])
