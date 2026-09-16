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
    "success": ("Green status marks, like the Ready rungs on the Skills roster."),
    "warning": (
        "Amber status marks — plan problems and the Fleet Bar's incoming-threat tint."
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

PURPLE_COBRAS_ROLES = {
    "--bg": "#050208",
    "--panel": "#1a0d24",
    "--panel-border": "#2a1838",
    "--field": "#030105",
    "--field-border": "#2e1a45",
    "--text": "#f0f0f5",
    "--text-dim": "#b8b8c4",
    "--text-faint": "#90909e",
    "--text-label": "#9c9caa",
    "--text-btn": "#d5d5de",
    "--brand": "#6b2fb5",
    "--brand-deep": "#2e1148",
    "--brand-text": "#9d55e8",
    "--acc-top": "#6b2fb5",
    "--acc-bottom": "#55229a",
    "--brand-edge": "#8a45cf",
    "--focus-ring": "#8a45cf",
    "--ok": "#7cff3d",
    "--warn": "#f5c518",
    "--err": "#f0474e",
    "--danger": "#f0474e",
    "--danger-solid": "#a51820",
    "--unmet": "#d87ba8",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#241436",
    "--sunken": "#0b0512",
    "--titlebar-top": "#261538",
    "--titlebar-bottom": "#150a1e",
    "--titlebar-inset": "#33204a",
    "--statusbar-top": "#1d1029",
    "--statusbar-bottom": "#120a1a",
    "--wash-top": "#221038",
    "--wash-bottom": "#150a20",
    "--hover": "#2e1a45",
    "--control": "#241436",
    "--control-border": "#352048",
    "--control-hover": "#2e1a45",
    "--control-edge": "#8f8fa0",
    "--field-focus-border": "#3a2554",
    "--scrollbar": "#271636",
    "--scrollbar-hover": "#35214a",
    "--fleet-incoming-threat": "#d4b62a",
    "--row-line": "#200f30",
    "--row-hover": "#1c0d2a",
    "--row-active": "#241238",
    "--row-ring": "#382252",
    "--row-ring-focus": "#4e3270",
}

MERICA_ROLES = {
    "--bg": "#050f22",
    "--panel": "#0a1e3f",
    "--panel-border": "#14264a",
    "--field": "#03080f",
    "--field-border": "#1e3055",
    "--text": "#ffffff",
    "--text-dim": "#c9c9d4",
    "--text-faint": "#a0a0ac",
    "--text-label": "#a8a8b4",
    "--text-btn": "#d4d4de",
    "--brand": "#c5a253",
    "--brand-deep": "#5c4a20",
    "--brand-text": "#d4b062",
    "--acc-top": "#c5a253",
    "--acc-bottom": "#a8873e",
    "--brand-edge": "#e0bc70",
    "--focus-ring": "#e0bc70",
    "--ok": "#6f9e55",
    "--warn": "#ffd23f",
    "--err": "#e04a55",
    "--danger": "#e04a55",
    "--danger-solid": "#8b1a28",
    "--unmet": "#e08a5a",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#0d2348",
    "--sunken": "#040a18",
    "--titlebar-top": "#10234a",
    "--titlebar-bottom": "#081228",
    "--titlebar-inset": "#1a3055",
    "--statusbar-top": "#0c1d3c",
    "--statusbar-bottom": "#060f20",
    "--wash-top": "#122050",
    "--wash-bottom": "#0a1230",
    "--hover": "#16295a",
    "--control": "#112244",
    "--control-border": "#1e3260",
    "--control-hover": "#182c5c",
    "--control-edge": "#8c90a8",
    "--field-focus-border": "#24386a",
    "--scrollbar": "#17275a",
    "--scrollbar-hover": "#22336a",
    "--fleet-incoming-threat": "#c5a253",
    "--row-line": "#0d2044",
    "--row-hover": "#0b1c3c",
    "--row-active": "#10244a",
    "--row-ring": "#1c3260",
    "--row-ring-focus": "#2c4478",
}

IDIOCRACY_ROLES = {
    "--bg": "#0a0a0a",
    "--panel": "#141414",
    "--panel-border": "#262626",
    "--field": "#050505",
    "--field-border": "#2a2a2a",
    "--text": "#f5f5f5",
    "--text-dim": "#b8b8b8",
    "--text-faint": "#8f8f8f",
    "--text-label": "#9c9c9c",
    "--text-btn": "#d9d9d9",
    "--brand": "#39ff14",
    "--brand-deep": "#1a6b0a",
    "--brand-text": "#7dff52",
    "--acc-top": "#39ff14",
    "--acc-bottom": "#2bc40e",
    "--brand-edge": "#7dff52",
    "--focus-ring": "#7dff52",
    "--ok": "#b8d41e",
    "--warn": "#ffe600",
    "--err": "#f0443a",
    "--danger": "#f0443a",
    "--danger-solid": "#b81e14",
    "--unmet": "#f0975c",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#1a1a1a",
    "--sunken": "#060606",
    "--titlebar-top": "#1c1c1c",
    "--titlebar-bottom": "#101010",
    "--titlebar-inset": "#2a2a2a",
    "--statusbar-top": "#151515",
    "--statusbar-bottom": "#0d0d0d",
    "--wash-top": "#0e1a08",
    "--wash-bottom": "#16060f",
    "--hover": "#2a2a2a",
    "--control": "#1f1f1f",
    "--control-border": "#303030",
    "--control-hover": "#282828",
    "--control-edge": "#8f8f8f",
    "--field-focus-border": "#383838",
    "--scrollbar": "#242424",
    "--scrollbar-hover": "#333333",
    "--fleet-incoming-threat": "#d4bf00",
    "--row-line": "#181818",
    "--row-hover": "#151515",
    "--row-active": "#1b1b1b",
    "--row-ring": "#2e2e2e",
    "--row-ring-focus": "#454545",
}

RON_BURGUNDY_ROLES = {
    "--bg": "#1f0f08",
    "--panel": "#3b1f0f",
    "--panel-border": "#4a2a14",
    "--field": "#0a0503",
    "--field-border": "#4a3018",
    "--text": "#f0e8d8",
    "--text-dim": "#c4b89c",
    "--text-faint": "#9c917a",
    "--text-label": "#a89d84",
    "--text-btn": "#ded3bd",
    "--brand": "#d4881f",
    "--brand-deep": "#5f3a0c",
    "--brand-text": "#e89a3a",
    "--acc-top": "#d4881f",
    "--acc-bottom": "#b87418",
    "--brand-edge": "#f0a838",
    "--focus-ring": "#f0a838",
    "--ok": "#6fae8c",
    "--warn": "#c9a227",
    "--err": "#de4a5f",
    "--danger": "#de4a5f",
    "--danger-solid": "#9c1834",
    "--unmet": "#d89060",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#432412",
    "--sunken": "#150a05",
    "--titlebar-top": "#47260f",
    "--titlebar-bottom": "#2a1509",
    "--titlebar-inset": "#553520",
    "--statusbar-top": "#2f1a0c",
    "--statusbar-bottom": "#1d0f06",
    "--wash-top": "#33200e",
    "--wash-bottom": "#221408",
    "--hover": "#4f2f18",
    "--control": "#42230f",
    "--control-border": "#58371c",
    "--control-hover": "#4f2f18",
    "--control-edge": "#9a8a70",
    "--field-focus-border": "#553a1e",
    "--scrollbar": "#44260f",
    "--scrollbar-hover": "#57351a",
    "--fleet-incoming-threat": "#c9a227",
    "--row-line": "#35200f",
    "--row-hover": "#2f1c0d",
    "--row-active": "#3a2412",
    "--row-ring": "#50331c",
    "--row-ring-focus": "#6b4a2e",
}

DODGEBALL_ROLES = {
    "--bg": "#0d0d0d",
    "--panel": "#1a1a1a",
    "--panel-border": "#262626",
    "--field": "#050505",
    "--field-border": "#2e2e2e",
    "--text": "#f5f0e1",
    "--text-dim": "#bcb4a4",
    "--text-faint": "#a49f93",
    "--text-label": "#ada698",
    "--text-btn": "#d9d2c2",
    "--brand": "#f4c430",
    "--brand-deep": "#6b5210",
    "--brand-text": "#f4c430",
    "--acc-top": "#f4c430",
    "--acc-bottom": "#d9a91e",
    "--brand-edge": "#ffd966",
    "--focus-ring": "#ffd966",
    "--ok": "#2fb3a3",
    "--warn": "#f4c430",
    "--err": "#f0554e",
    "--danger": "#f0554e",
    "--danger-solid": "#a31d1d",
    "--unmet": "#f0996b",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#202020",
    "--sunken": "#0a0a0a",
    "--titlebar-top": "#222222",
    "--titlebar-bottom": "#141414",
    "--titlebar-inset": "#303030",
    "--statusbar-top": "#181818",
    "--statusbar-bottom": "#101010",
    "--wash-top": "#201826",
    "--wash-bottom": "#141017",
    "--hover": "#2e2e2e",
    "--control": "#242424",
    "--control-border": "#343434",
    "--control-hover": "#383838",
    "--control-edge": "#8f8a7e",
    "--field-focus-border": "#3a3a3a",
    "--scrollbar": "#2a2a2a",
    "--scrollbar-hover": "#3a3a3a",
    "--fleet-incoming-threat": "#d9a91e",
    "--row-line": "#1e1e1e",
    "--row-hover": "#1b1b1b",
    "--row-active": "#222222",
    "--row-ring": "#333333",
    "--row-ring-focus": "#4a4a4a",
}

TROPIC_THUNDER_ROLES = {
    "--bg": "#1a2410",
    "--panel": "#2e2719",
    "--panel-border": "#3d3423",
    "--field": "#141b0c",
    "--field-border": "#3d3826",
    "--text": "#d9d2c1",
    "--text-dim": "#aba596",
    "--text-faint": "#97907a",
    "--text-label": "#9d9681",
    "--text-btn": "#c6bfae",
    "--brand": "#ff6b1a",
    "--brand-deep": "#6b2a08",
    "--brand-text": "#ff8b47",
    "--acc-top": "#ff6b1a",
    "--acc-bottom": "#e85d04",
    "--brand-edge": "#ff9557",
    "--focus-ring": "#ffab63",
    "--ok": "#96a94e",
    "--warn": "#ffd23f",
    "--err": "#e05246",
    "--danger": "#e05246",
    "--danger-solid": "#8b1e1e",
    "--unmet": "#e09a6a",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#342c1d",
    "--sunken": "#171c0e",
    "--titlebar-top": "#37301f",
    "--titlebar-bottom": "#201b12",
    "--titlebar-inset": "#463d28",
    "--statusbar-top": "#241f14",
    "--statusbar-bottom": "#171308",
    "--wash-top": "#2d2a16",
    "--wash-bottom": "#1c1a0e",
    "--hover": "#3a3222",
    "--control": "#332c1e",
    "--control-border": "#46402c",
    "--control-hover": "#413a28",
    "--control-edge": "#9a8f72",
    "--field-focus-border": "#4a4330",
    "--scrollbar": "#38311f",
    "--scrollbar-hover": "#48402a",
    "--fleet-incoming-threat": "#c9a93c",
    "--row-line": "#262015",
    "--row-hover": "#221d13",
    "--row-active": "#2a2417",
    "--row-ring": "#3f3826",
    "--row-ring-focus": "#574e36",
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
    "purple-cobras": _preset(
        "purple-cobras",
        "Purple Cobras",
        PURPLE_COBRAS_ROLES,
        [
            # Scale-black and purple den surfaces; Blood Purple lets the
            # whole den go magenta. The template's primary (Cobra Purple
            # Bright) and danger (Cobra Eye Red) are already distinct, so
            # the accent slot takes the faithful purple -- no collision
            # rule needed for once.
            ("Cobra Purple", "#4b1e7a", ["surface"]),
            ("Scale Dark", "#1a0d24", ["surface"]),
            ("Blood Purple", "#8b1e5c", ["surface", "danger"]),
            ("Cobra Deep", "#1f0a35", ["base"]),
            ("Scale Black", "#0d0610", ["base", "surface"]),
            ("Scale Black Deep", "#050208", ["base"]),
            ("Venom White", "#f0f0f5", ["text"]),
            ("Fang Silver", "#c4c4d0", ["text"]),
            ("Court Line", "#e8e0d0", ["text"]),
            ("Venom Green", "#7cff3d", ["text", "accent", "success"]),
            ("Venom Dark", "#4fb821", ["success"]),
            ("Cobra Gold", "#f5c518", ["accent", "warning"]),
            ("Cobra Gold Bright", "#ffe04a", ["accent", "warning"]),
            ("Cobra Purple Bright", "#6b2fb5", ["accent"]),
            ("Cobra Eye Red", "#e8232a", ["danger"]),
        ],
        "#050208",
        "#f0f0f5",
    ),
    "merica": _preset(
        "merica",
        "Merica",
        MERICA_ROLES,
        [
            # Navy field surfaces; Old Glory Red Dark, Liberty Teal and
            # Field Green let a user tint the flag toward one stripe.
            # Eagle Gold owns the accent slot -- the template's own
            # "Launch Freedom" CTA and focus colour -- because Old Glory
            # Red is cast as BOTH primary and danger, and this app cannot
            # have Upload and Delete in one colour.
            ("Navy", "#0a1e3f", ["surface"]),
            ("Old Glory Blue Dark", "#2a2950", ["surface"]),
            ("Liberty Teal", "#1f6f6b", ["surface", "accent"]),
            ("Field Green", "#2d4a1e", ["surface", "success"]),
            ("Asphalt", "#1a1a1e", ["surface", "base"]),
            ("Navy Deep", "#050f22", ["base"]),
            ("Asphalt Deep", "#0a0a0d", ["base"]),
            ("Star White", "#ffffff", ["text"]),
            ("Star White Dim", "#e8e8ec", ["text"]),
            ("Eagle Gold", "#c5a253", ["text", "accent"]),
            ("Eagle Gold Bright", "#e0bc70", ["accent"]),
            ("Old Glory Red", "#b22234", ["accent", "danger"]),
            ("Old Glory Red Dark", "#8b1a28", ["surface", "danger"]),
            ("Caution Yellow", "#ffd23f", ["accent", "warning"]),
        ],
        "#050f22",
        "#ffffff",
    ),
    "idiocracy": _preset(
        "idiocracy",
        "Idiocracy",
        IDIOCRACY_ROLES,
        [
            # CRT-black neutrals; Mocha, Jacked Purple and Costco Blue let
            # a user tint the static toward one brand. Brawndo Green takes
            # the accent slot -- it IS the theme's identity -- so success
            # defaults to Mountain Dew rather than wearing the accent.
            ("CRT Dark", "#141414", ["surface"]),
            ("Starbucks Mocha", "#6b4226", ["surface"]),
            ("Jacked Purple", "#7b2fbe", ["surface"]),
            ("Costco Blue", "#0055a5", ["surface"]),
            ("CRT Black", "#0a0a0a", ["base", "surface"]),
            ("TV Static", "#f5f5f5", ["text"]),
            ("TV Static Dim", "#b8b8b8", ["text"]),
            ("Starbucks Cream", "#e8d5b7", ["text"]),
            ("Brawndo Green", "#39ff14", ["text", "accent", "success"]),
            ("Mountain Dew", "#ccff00", ["text", "accent", "success"]),
            ("Electrolyte Yellow", "#ffe600", ["accent", "warning", "text"]),
            ("Nacho Cheese", "#f5a623", ["accent", "warning"]),
            ("Carl's Jr Star", "#f7941d", ["accent", "warning"]),
            ("Gatorade Orange", "#ff6b1a", ["accent"]),
            ("MTV Pink", "#ff1fa0", ["accent", "danger"]),
            ("Costco Red", "#e8291c", ["accent", "danger"]),
            ("Fudd Burgundy", "#8b1e1e", ["danger"]),
        ],
        # Pure black, not CRT Black: Gatorade Orange as the accent leaves
        # the dark label at 4.45:1 against the gradient's bottom stop --
        # the only pool pick CRT Black cannot carry.
        "#000000",
        "#ffffff",
    ),
    "ron-burgundy": _preset(
        "ron-burgundy",
        "Ron Burgundy",
        RON_BURGUNDY_ROLES,
        [
            # Wood-panel surfaces; Broadcast Blue and Velvet Green let a
            # user tint the newsroom to the channel's other sets. Scotch
            # Amber owns the accent slot -- the template's own "Stay
            # Classy" CTA and focus colour -- because the template casts
            # burgundy as primary AND red as danger, and this app cannot
            # have Upload and Delete within a hue-step of each other.
            ("Mahogany", "#3b1f0f", ["surface"]),
            ("Wood Panel", "#4a2a14", ["surface"]),
            ("Walnut", "#5c3418", ["surface"]),
            ("Broadcast Blue", "#1e3a8a", ["surface", "accent"]),
            ("Velvet Green", "#2f4f3e", ["surface", "success"]),
            ("Mahogany Deep", "#1f0f08", ["base"]),
            ("Studio Black", "#0f0805", ["base"]),
            ("Newsprint", "#f0e8d8", ["text"]),
            ("Newsprint Dim", "#c4b89c", ["text"]),
            ("Tan", "#c9a876", ["text"]),
            ("Scotch Amber", "#d4881f", ["text", "accent", "warning"]),
            ("Gold Mic", "#c9a227", ["accent", "warning"]),
            ("Cravat Burgundy", "#8b1e3f", ["accent", "danger"]),
            ("Cravat Burgundy Dark", "#5f1329", ["danger"]),
            ("Sex Panther Red", "#c41e3a", ["accent", "danger"]),
        ],
        "#1f0f08",
        "#ffffff",
    ),
    "dodgeball": _preset(
        "dodgeball",
        "Dodgeball",
        DODGEBALL_ROLES,
        [
            # Gym-wall greys take the surface slots; Bruise and Gym Floor
            # let a user tint the whole gym purple or wood-orange at dark
            # reference lightness. Gold takes the accent slot by default --
            # the template casts red as BOTH primary and danger, and this
            # app cannot have Upload and Delete in one colour.
            ("Gym Wall", "#1a1a1a", ["surface"]),
            ("Bruise", "#4a2a5a", ["surface"]),
            ("Gym Floor", "#c8642a", ["surface"]),
            ("Tape Black", "#2b2b2b", ["surface", "base"]),
            ("Gym Wall Deep", "#0d0d0d", ["base"]),
            ("Court Line", "#f5f0e1", ["text"]),
            ("Court Line Dim", "#b8b0a0", ["text"]),
            ("Globo Gold", "#f4c430", ["text", "accent", "warning"]),
            ("Globo Gold Bright", "#ffd966", ["accent", "warning"]),
            ("Dodgeball Pink", "#e85a8a", ["text", "accent", "danger"]),
            ("Average Joe Red", "#d62828", ["accent", "danger"]),
            ("Average Joe Red Dark", "#a31d1d", ["danger"]),
            ("Globo Blue", "#1e5faa", ["accent"]),
            ("Wrench Purple", "#7b3fa0", ["accent"]),
            ("Sweat Teal", "#2a9d8f", ["accent", "success"]),
            ("Trophy Bronze", "#b87333", ["accent"]),
        ],
        "#0d0d0d",
        "#ffffff",
    ),
    "tropic-thunder": _preset(
        "tropic-thunder",
        "Tropic Thunder",
        TROPIC_THUNDER_ROLES,
        [
            # The template's own surfaces: mud and jungle. Pool tags keep
            # Dog Tag and its ramp as the only text drivers, so the AA
            # cross-product below stays about bright-on-dark.
            ("River Mud", "#5c4a2e", ["surface"]),
            ("River Mud Dark", "#2e2719", ["surface"]),
            ("River Mud Light", "#3d3423", ["surface"]),
            ("Jungle Rot", "#2d4a1e", ["surface", "base"]),
            ("Flare-lit mud", "#38301f", ["surface"]),
            ("Jungle Rot Deep", "#1a2410", ["base"]),
            ("Blackface Blunder", "#1a1613", ["base"]),
            ("Sunken green", "#141b0c", ["base"]),
            ("Dog Tag", "#d9d2c1", ["text"]),
            ("Elephant Grass", "#7a8b3c", ["text", "success"]),
            ("Napalm Dawn", "#ff6b1a", ["accent"]),
            ("Agent Orange", "#e85d04", ["accent"]),
            ("Flare Gun", "#ffd23f", ["accent", "warning"]),
            ("Hollywood Teal", "#1f6f6b", ["accent"]),
            ("Blood Diamond", "#8b1e1e", ["danger"]),
        ],
        "#1a1613",
        "#ffffff",
    ),
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
