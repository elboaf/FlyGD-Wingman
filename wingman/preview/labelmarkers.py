"""Manually assigned label markers; exact names, never native identities."""

MARKER_PALETTE = {
    "cyan": ("Cyan", (86, 180, 233)),
    "orange": ("Orange", (230, 159, 0)),
    "green": ("Green", (0, 158, 115)),
    "purple": ("Purple", (204, 121, 167)),
    "yellow": ("Yellow", (240, 228, 66)),
    "blue": ("Blue", (0, 114, 178)),
}


def valid_owner(name: object) -> bool:
    return (
        isinstance(name, str)
        and bool(name)
        and name == name.strip()
        and name.isprintable()
        and not name.startswith("hwnd:")
    )


def validated_markers(raw: object) -> dict[str, str]:
    """Drop malformed entries independently; configured owners have no roster cap."""
    if not isinstance(raw, dict):
        return {}
    return {
        name: key
        for name, key in raw.items()
        if valid_owner(name) and isinstance(key, str) and key in MARKER_PALETTE
    }


def marker_choices() -> list[dict[str, str]]:
    return [{"key": "", "label": "None"}] + [
        {"key": key, "label": value[0]} for key, value in MARKER_PALETTE.items()
    ]
