"""Pure policy for minimizing an inactive EVE client after a successful switch.

The preview subsystem's Win32 calls cannot be exercised against a real EVE
client in CI. Keep the decision of whether an outgoing client qualifies here,
where Linux tests can cover it; host.py owns only Win32 calls and their order.
"""


def should_minimize(*, enabled, previous_key, next_key, never) -> bool:
    """Whether a successful switch should minimize its outgoing client.

    The host evaluates this before activation so it preserves the exact outgoing
    stable key/HWND, but performs the asynchronous request only after the target
    is observed foreground.
    """
    if not enabled or not previous_key or previous_key == next_key:
        return False
    return previous_key not in (never or [])
