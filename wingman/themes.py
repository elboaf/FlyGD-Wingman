"""Theme presets and the family-based customizer's colour engine.

Pure by design (no Windows APIs), like bookmarks.py: the CSS side cannot be
tested, so everything decidable lives here and is.

The model, in one paragraph: a preset owns a swatch pool and a default
mapping; the composer lets the user pick ONE swatch per element family
(surfaces, text, accent, danger, success, warning); the engine derives the
~45 CSS custom properties from those six picks. The derivation is the
technique style.css recorded from the vermilion-to-purple retheme: each
derived role keeps its REFERENCE LIGHTNESS and takes only hue and
saturation from the chosen swatch. That is what makes the customizer safe
without a per-pick contrast checker — WCAG contrast is a function of
luminance alone, so preserving every role's lightness preserves every
contrast ratio the preset was measured for, no matter which swatches the
user combines. Compatibility is therefore declarative (which families a
swatch MAY drive) rather than computed per combination.

--link stays fixed in every preset: it marks a link OUT of the app and
carries a legal obligation to be recognisable (see its note in style.css).
--training and --unmet stay fixed for the same kind of reason: they are
severity vocabulary, not decoration, and recolouring them from the accent
pool would let "Training" and "brand" collide.
"""

import colorsys

# The families the composer offers. Order is display order.
FAMILIES = ["surface", "base", "text", "accent", "danger", "success", "warning"]

FAMILY_LABELS = {
    "surface": "Panels & controls",
    "base": "App background",
    "text": "Text",
    "accent": "Accent",
    "danger": "Danger",
    "success": "Success",
    "warning": "Warning",
}

# What each family actually recolours, one sentence, rendered under its
# dropdown. "Accent" alone names a token role, not anything a user can
# picture; the sentence is the picture. Kept beside FAMILY_LABELS because
# the two answer the same question at different depths and must move
# together if a family's reach ever changes.
FAMILY_DESCRIPTIONS = {
    "surface": (
        "Cards, buttons, fields, scrollbars and the row highlights — "
        "most of the window's chrome."
    ),
    "base": (
        "The page behind everything: the app backdrop, text field wells, "
        "recessed bands and list rows."
    ),
    "text": (
        "Every piece of text — headings, body, labels and hints — at "
        "the preset's brightness steps, whatever hue you choose."
    ),
    "accent": (
        "The Upload button, focused fields, ticks and glows: the app's "
        "one call-to-action colour."
    ),
    "danger": (
        "Delete buttons and destructive hovers — the colour that must "
        "never be mistaken for the accent."
    ),
    "success": (
        "Green status marks, like the Ready rungs on the Skills roster."
    ),
    "warning": (
        "Amber status marks — plan problems and the Fleet Bar's "
        "incoming-threat tint."
    ),
}

# Roles derived from each family's swatch, as (role, reference-role) pairs.
# The reference role supplies the lightness that survives recolouring; the
# key is what the page receives. Keeping the reference IN THE PRESET (not
# hard-coded here) is what lets two presets shape the same family
# differently — Zoolander's navy ramp and Wingman's violet ramp do not
# share stops.
_SURFACE_ROLES = [
    ("--panel", "--panel"),
    ("--panel-border", "--panel-border"),
    ("--card-top", "--card-top"),
    ("--titlebar-top", "--titlebar-top"),
    ("--titlebar-bottom", "--titlebar-bottom"),
    ("--titlebar-inset", "--titlebar-inset"),
    ("--statusbar-top", "--statusbar-top"),
    ("--wash-top", "--wash-top"),
    ("--hover", "--hover"),
    ("--control", "--control"),
    ("--control-border", "--control-border"),
    ("--control-hover", "--control-hover"),
    ("--scrollbar", "--scrollbar"),
    ("--scrollbar-hover", "--scrollbar-hover"),
    ("--row-ring", "--row-ring"),
    ("--row-ring-focus", "--row-ring-focus"),
    ("--field-border", "--field-border"),
    ("--field-focus-border", "--field-focus-border"),
]

_BASE_ROLES = [
    ("--bg", "--bg"),
    ("--field", "--field"),
    ("--sunken", "--sunken"),
    ("--statusbar-bottom", "--statusbar-bottom"),
    ("--wash-bottom", "--wash-bottom"),
    ("--row-line", "--row-line"),
    ("--row-hover", "--row-hover"),
    ("--row-active", "--row-active"),
]

_TEXT_ROLES = [
    ("--text", "--text"),
    ("--text-dim", "--text-dim"),
    ("--text-faint", "--text-faint"),
    ("--text-label", "--text-label"),
    ("--text-btn", "--text-btn"),
    ("--control-edge", "--control-edge"),
]

_ACCENT_ROLES = [
    ("--brand", "--brand"),
    ("--brand-deep", "--brand-deep"),
    ("--brand-text", "--brand-text"),
    ("--acc-top", "--acc-top"),
    ("--acc-bottom", "--acc-bottom"),
    ("--brand-edge", "--brand-edge"),
    ("--focus-ring", "--focus-ring"),
]

_DANGER_ROLES = [
    ("--err", "--err"),
    ("--danger", "--danger"),
    ("--danger-solid", "--danger-solid"),
]

_SUCCESS_ROLES = [("--ok", "--ok")]

_WARNING_ROLES = [
    ("--warn", "--warn"),
    ("--fleet-incoming-threat", "--fleet-incoming-threat"),
]

_FAMILY_ROLES = {
    "surface": _SURFACE_ROLES,
    "base": _BASE_ROLES,
    "text": _TEXT_ROLES,
    "accent": _ACCENT_ROLES,
    "danger": _DANGER_ROLES,
    "success": _SUCCESS_ROLES,
    "warning": _WARNING_ROLES,
}


def _hls(hex_color):
    hue, light, sat = colorsys.rgb_to_hls(*_channels(hex_color))
    return hue, light, sat


def _channels(hex_color):
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def _hex(r, g, b):
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _recolor(reference, swatch):
    """The swatch's hue and saturation at the reference's lightness.

    A near-grey swatch (S below ~4%) carries no hue a user can see, so its
    saturation is taken literally: picking grey means the family goes grey,
    rather than silently keeping the reference's chroma.
    """
    _, ref_l, _ = _hls(reference)
    sw_h, _, sw_s = _hls(swatch)
    r, g, b = colorsys.hls_to_rgb(sw_h, ref_l, sw_s)
    return _hex(r, g, b)


def _relative_luminance(hex_color):
    def channel(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _channels(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a, b):
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _on_accent(preset, accent_bottom):
    """The label ON the accent fill: the preset's two candidates, picked by
    measured contrast against the darker gradient stop (the worst case).
    Neither candidate clearing 4.5:1 means the preset is broken, so the
    better of the two wins and the preset's own tests catch it."""
    dark = preset["_on_accent_dark"]
    light = preset["_on_accent_light"]
    if _contrast(dark, accent_bottom) >= 4.5:
        return dark
    if _contrast(light, accent_bottom) >= 4.5:
        return light
    return (
        dark
        if _contrast(dark, accent_bottom) > _contrast(light, accent_bottom)
        else light
    )


def resolve(preset, picks):
    """Effective role -> hex map for the preset after family picks.

    `picks` maps family -> swatch hex. Unknown families, roles and swatches
    a family may not drive are ignored rather than raised: the settings
    document outlives presets, and a fork that ships a smaller pool must
    not make an older document unreadable.
    """
    roles = dict(preset["roles"])
    for family, swatch in (picks or {}).items():
        if family not in _FAMILY_ROLES or not _family_allows(preset, family, swatch):
            continue
        for role, reference in _FAMILY_ROLES[family]:
            roles[role] = _recolor(roles[reference], swatch)
    # Computed roles land after the picks so they see recoloured inputs.
    roles["--on-accent"] = _on_accent(preset, roles["--acc-bottom"])
    roles["--brand-rgb"] = " ".join(
        str(round(c * 255)) for c in _channels(roles["--brand"])
    )
    roles["--wash-top-rgb"] = " ".join(
        str(round(c * 255)) for c in _channels(roles["--wash-top"])
    )
    roles["--wash-bottom-rgb"] = " ".join(
        str(round(c * 255)) for c in _channels(roles["--wash-bottom"])
    )
    roles["--fleet-threat-surface"] = "rgb({} / 0.12)".format(
        roles["--fleet-incoming-threat"].lstrip("#")
    )
    return roles


def _family_allows(preset, family, swatch):
    for entry in preset["swatches"]:
        if entry["hex"].lower() == str(swatch).lower():
            return family in entry["families"]
    return False


def legal_swatches(preset, family, picks):
    """Swatch hexes this family may drive, given the current picks.

    With lightness preserved by derivation, every allowed combination holds
    the preset's contrast, so legality here is purely the declarative
    family tags — the argument is in the module docstring.
    """
    return [entry["hex"] for entry in preset["swatches"] if family in entry["families"]]


def normalize(document):
    """Project a stored theme document onto what this module supports.

    Returns (preset_id, picks). Anything undeclared — an unknown preset,
    a family that no longer exists, a swatch the family may not drive --
    is dropped rather than trusted, the same way save() projects onto
    DEFAULTS keys.
    """
    preset_id = document.get("preset") if isinstance(document, dict) else None
    if preset_id not in PRESETS:
        preset_id = DEFAULT_PRESET
    picks = {}
    stored = document.get("families") if isinstance(document, dict) else None
    if isinstance(stored, dict):
        for family, swatch in stored.items():
            if family in _FAMILY_ROLES and _family_allows(
                PRESETS[preset_id], family, swatch
            ):
                picks[family] = str(swatch).lower()
    return preset_id, picks


def swatch_name(preset, hex_color):
    for entry in preset["swatches"]:
        if entry["hex"].lower() == str(hex_color).lower():
            return entry["name"]
    return None


def _swatches(entries):
    return [{"name": n, "hex": h, "families": list(f)} for n, h, f in entries]


def _preset(pid, name, roles, swatch_entries, on_dark, on_light):
    return {
        "id": pid,
        "name": name,
        "roles": roles,
        "swatches": _swatches(swatch_entries),
        "_on_accent_dark": on_dark,
        "_on_accent_light": on_light,
    }


WINGMAN_DARK_ROLES = {
    "--bg": "#0c0d10",
    "--panel": "#17151c",
    "--panel-border": "#231f2a",
    "--field": "#0c0a0f",
    "--field-border": "#282430",
    "--text": "#e8eaed",
    "--text-dim": "#9aa2b1",
    "--text-faint": "#7d8492",
    "--text-label": "#8b93a1",
    "--text-btn": "#c8cdd6",
    "--brand": "#8430d9",
    "--brand-deep": "#4a0083",
    "--brand-text": "#ad5aff",
    "--acc-top": "#9438e8",
    "--acc-bottom": "#7a1fc8",
    "--brand-edge": "#a95cf0",
    "--focus-ring": "#c99cff",
    "--ok": "#4ade80",
    "--warn": "#d29922",
    "--err": "#f85149",
    "--danger": "#f85149",
    "--danger-solid": "#d9291c",
    "--unmet": "#ff9668",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#191426",
    "--sunken": "#131117",
    "--titlebar-top": "#1b1528",
    "--titlebar-bottom": "#121016",
    "--titlebar-inset": "#292530",
    "--statusbar-top": "#14101c",
    "--statusbar-bottom": "#0f0c14",
    "--wash-top": "#1d1030",
    "--wash-bottom": "#170f26",
    "--hover": "#27232e",
    "--control": "#211d28",
    "--control-border": "#302c39",
    "--control-hover": "#2a2634",
    "--control-edge": "#787181",
    "--field-focus-border": "#433c52",
    "--scrollbar": "#2c2835",
    "--scrollbar-hover": "#3b3548",
    "--fleet-incoming-threat": "#be9550",
    "--row-line": "#1d1a24",
    "--row-hover": "#1b1822",
    "--row-active": "#1f1b27",
    "--row-ring": "#383244",
    "--row-ring-focus": "#554e65",
}

ZOOLANDER_ROLES = {
    "--bg": "#08080f",
    "--panel": "#0d0d1a",
    "--panel-border": "#1c1c34",
    "--field": "#06060e",
    "--field-border": "#282848",
    "--text": "#e8edf2",
    "--text-dim": "#a8b2bd",
    "--text-faint": "#7e8899",
    "--text-label": "#8a94a6",
    "--text-btn": "#c9d1dc",
    "--brand": "#7cb342",
    "--brand-deep": "#3e5c1f",
    "--brand-text": "#8fc654",
    "--acc-top": "#7cb342",
    "--acc-bottom": "#639532",
    "--brand-edge": "#97cc5d",
    "--focus-ring": "#97cc5d",
    "--ok": "#8bc34a",
    "--warn": "#d4a843",
    "--err": "#e91e8c",
    "--danger": "#e91e8c",
    "--danger-solid": "#c0156f",
    "--unmet": "#c67b4a",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#16162e",
    "--sunken": "#0a0a16",
    "--titlebar-top": "#14142e",
    "--titlebar-bottom": "#0c0c1c",
    "--titlebar-inset": "#26264a",
    "--statusbar-top": "#0f0f24",
    "--statusbar-bottom": "#0a0a18",
    "--wash-top": "#16163a",
    "--wash-bottom": "#10102e",
    "--hover": "#1f1f40",
    "--control": "#1a1a38",
    "--control-border": "#2c2c52",
    "--control-hover": "#242448",
    "--control-edge": "#7e88a8",
    "--field-focus-border": "#34345e",
    "--scrollbar": "#232348",
    "--scrollbar-hover": "#30305a",
    "--fleet-incoming-threat": "#d4a843",
    "--row-line": "#1a1a34",
    "--row-hover": "#16162c",
    "--row-active": "#1c1c38",
    "--row-ring": "#30305a",
    "--row-ring-focus": "#484878",
}

PRESETS = {
    "wingman-dark": _preset(
        "wingman-dark",
        "Wingman Dark",
        WINGMAN_DARK_ROLES,
        [
            # Surfaces: the preset's own ramps. Text pools carry only
            # swatches that clear 4.5:1 against every surface the preset
            # offers, so the declarative tags are the whole guard.
            ("Panel", "#17151c", ["surface"]),
            ("Card top", "#191426", ["surface"]),
            ("Hover", "#27232e", ["surface"]),
            ("Control", "#211d28", ["surface"]),
            ("Row", "#1d1a24", ["surface"]),
            ("Background", "#0c0d10", ["base"]),
            ("Sunken", "#131117", ["base"]),
            ("Field", "#0c0a0f", ["base"]),
            ("Ice", "#e8eaed", ["text"]),
            ("Bright", "#c8cdd6", ["text"]),
            ("Dim", "#9aa2b1", ["text"]),
            ("Label", "#8b93a1", ["text"]),
            ("Violet", "#8430d9", ["accent"]),
            ("Light violet", "#ad5aff", ["accent"]),
            ("Deep violet", "#7a1fc8", ["accent"]),
            ("Teal", "#45c8d4", ["accent"]),
            ("Gold", "#d29922", ["accent", "warning"]),
            ("Red", "#f85149", ["accent", "danger"]),
            ("Solid red", "#d9291c", ["danger"]),
            ("Green", "#4ade80", ["success"]),
        ],
        "#0c0d10",
        "#ffffff",
    ),
    "zoolander": _preset(
        "zoolander",
        "Zoolander",
        ZOOLANDER_ROLES,
        [
            ("Magnum", "#1a1a2e", ["surface"]),
            ("Steel blue", "#2c3e5c", ["surface"]),
            ("Cobalt", "#3d5a80", ["surface"]),
            ("Surface hover", "#2a2a4a", ["surface"]),
            ("Magnum deep", "#0d0d1a", ["base"]),
            ("Gasoline fight", "#08080f", ["base"]),
            ("Derelicte", "#2a1a1a", ["surface", "base"]),
            ("Ice", "#e8edf2", ["text"]),
            ("Bone", "#f5f0e8", ["text"]),
            ("Silver", "#a8b2bd", ["text"]),
            ("Lime", "#7cb342", ["accent", "success"]),
            ("Gold", "#d4a843", ["accent", "warning"]),
            ("Coral", "#e8574a", ["accent", "danger"]),
            ("Orange mocha", "#c67b4a", ["accent", "danger"]),
            ("Hot magenta", "#e91e8c", ["accent", "danger"]),
            ("Gasoline", "#6b3fa0", ["accent"]),
        ],
        "#0d0d1a",
        "#ffffff",
    ),
}

DEFAULT_PRESET = "wingman-dark"
