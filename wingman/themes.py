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


# The four dots that identify a preset at a glance in the picker's open
# list. Derived from the preset's own default mapping — never hand-typed —
# so a preset edit reflows its strip the same way it reflows the window.
_STRIP_ROLES = ["--brand", "--danger", "--warn", "--ok"]


def preset_strip(preset):
    """Identity colours for the preset picker's preview strip."""
    roles = resolve(preset, {})
    return [roles[role] for role in _STRIP_ROLES]


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

TACO_BELL_ROLES = {
    "--bg": "#050510",
    "--panel": "#0a0a1f",
    "--panel-border": "#151543",
    "--field": "#030309",
    "--field-border": "#1b1b53",
    "--text": "#f6f5fa",
    "--text-dim": "#c1b7db",
    "--text-faint": "#a99bce",
    "--text-label": "#b5a9d4",
    "--text-btn": "#d7d0e8",
    "--brand": "#ff1f8d",
    "--brand-deep": "#750039",
    "--brand-text": "#ff5aab",
    "--acc-top": "#ff1f8d",
    "--acc-bottom": "#e90072",
    "--brand-edge": "#ff5aab",
    "--focus-ring": "#ff5aab",
    "--ok": "#71c53e",
    "--warn": "#ffd900",
    "--err": "#ec4e57",
    "--danger": "#ec4e57",
    "--danger-solid": "#b7131c",
    "--unmet": "#f0a263",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#131339",
    "--sunken": "#04040e",
    "--titlebar-top": "#131339",
    "--titlebar-bottom": "#0a0a20",
    "--titlebar-inset": "#1e1e5c",
    "--statusbar-top": "#0e0e2c",
    "--statusbar-bottom": "#080818",
    "--wash-top": "#0e0e2a",
    "--wash-bottom": "#0e0e2c",
    "--hover": "#1b1b55",
    "--control": "#131339",
    "--control-border": "#1f1f61",
    "--control-hover": "#1b1b55",
    "--control-edge": "#8d7abd",
    "--field-focus-border": "#24246e",
    "--scrollbar": "#161646",
    "--scrollbar-hover": "#202064",
    "--fleet-incoming-threat": "#d4b400",
    "--row-line": "#0f0f31",
    "--row-hover": "#0d0d28",
    "--row-active": "#121238",
    "--row-ring": "#1c1c56",
    "--row-ring-focus": "#28287e",
    "--on-accent": "#050510",
    "--brand-rgb": "255 31 141",
    "--wash-top-rgb": "14 14 42",
    "--wash-bottom-rgb": "14 14 44",
    "--fleet-threat-surface": "rgb(d4b400 / 0.12)",
}

CARLS_JR_ROLES = {
    "--bg": "#0a0a0a",
    "--panel": "#1a1a1a",
    "--panel-border": "#2e2e2e",
    "--field": "#050505",
    "--field-border": "#303030",
    "--text": "#f0eeeb",
    "--text-dim": "#c9c4b8",
    "--text-faint": "#a09782",
    "--text-label": "#aba390",
    "--text-btn": "#d7d3ca",
    "--brand": "#f7a800",
    "--brand-deep": "#6b4900",
    "--brand-text": "#ffbe33",
    "--acc-top": "#f7a800",
    "--acc-bottom": "#d18e00",
    "--brand-edge": "#ffbe33",
    "--focus-ring": "#ffbe33",
    "--ok": "#71c53e",
    "--warn": "#f7ac00",
    "--err": "#ec4861",
    "--danger": "#ec4861",
    "--danger-solid": "#b7132c",
    "--unmet": "#f0a263",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#202020",
    "--sunken": "#0b0b0b",
    "--titlebar-top": "#1f1f1f",
    "--titlebar-bottom": "#121212",
    "--titlebar-inset": "#303030",
    "--statusbar-top": "#171717",
    "--statusbar-bottom": "#0e0e0e",
    "--wash-top": "#121212",
    "--wash-bottom": "#121212",
    "--hover": "#3a3a3a",
    "--control": "#242424",
    "--control-border": "#383838",
    "--control-hover": "#303030",
    "--control-edge": "#9e9580",
    "--field-focus-border": "#3e3e3e",
    "--scrollbar": "#2b2b2b",
    "--scrollbar-hover": "#3b3b3b",
    "--fleet-incoming-threat": "#d19100",
    "--row-line": "#202020",
    "--row-hover": "#1c1c1c",
    "--row-active": "#232323",
    "--row-ring": "#343434",
    "--row-ring-focus": "#4b4b4b",
    "--on-accent": "#0a0a0a",
    "--brand-rgb": "247 168 0",
    "--wash-top-rgb": "18 18 18",
    "--wash-bottom-rgb": "18 18 18",
    "--fleet-threat-surface": "rgb(d19100 / 0.12)",
}

BRAWNDO_ROLES = {
    "--bg": "#050505",
    "--panel": "#001528",
    "--panel-border": "#002548",
    "--field": "#030303",
    "--field-border": "#002d58",
    "--text": "#ffffff",
    "--text-dim": "#fff59c",
    "--text-faint": "#ffeb35",
    "--text-label": "#ffee4f",
    "--text-btn": "#fff8b5",
    "--brand": "#39ff14",
    "--brand-deep": "#127500",
    "--brand-text": "#6dff52",
    "--acc-top": "#39ff14",
    "--acc-bottom": "#21d200",
    "--brand-edge": "#6dff52",
    "--focus-ring": "#6dff52",
    "--ok": "#3dff14",
    "--warn": "#fff000",
    "--err": "#eb4a3f",
    "--danger": "#eb4a3f",
    "--danger-solid": "#b91d13",
    "--unmet": "#f0975c",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#001a32",
    "--sunken": "#040404",
    "--titlebar-top": "#001c36",
    "--titlebar-bottom": "#000f1e",
    "--titlebar-inset": "#002a52",
    "--statusbar-top": "#001528",
    "--statusbar-bottom": "#0c0c0c",
    "--wash-top": "#001020",
    "--wash-bottom": "#0d0d0d",
    "--hover": "#002b54",
    "--control": "#00203e",
    "--control-border": "#00305e",
    "--control-hover": "#002950",
    "--control-edge": "#ffea28",
    "--field-focus-border": "#003a70",
    "--scrollbar": "#002446",
    "--scrollbar-hover": "#003464",
    "--fleet-incoming-threat": "#d4c700",
    "--row-line": "#181818",
    "--row-hover": "#151515",
    "--row-active": "#1b1b1b",
    "--row-ring": "#002e5a",
    "--row-ring-focus": "#004688",
    "--on-accent": "#000000",
    "--brand-rgb": "57 255 20",
    "--wash-top-rgb": "0 16 32",
    "--wash-bottom-rgb": "13 13 13",
    "--fleet-threat-surface": "rgb(d4c700 / 0.12)",
}

PURPLE_COBRAS_ROLES = {
    "--bg": "#060307",
    "--panel": "#180a27",
    "--panel-border": "#271040",
    "--field": "#040204",
    "--field-border": "#2f134c",
    "--text": "#eeffe6",
    "--text-dim": "#a7ff7d",
    "--text-faint": "#73ff2f",
    "--text-label": "#83ff47",
    "--text-btn": "#ccffb4",
    "--brand": "#4ae400",
    "--brand-deep": "#1d5900",
    "--brand-text": "#7dff3e",
    "--acc-top": "#4ae400",
    "--acc-bottom": "#3dbc00",
    "--brand-edge": "#61ff15",
    "--focus-ring": "#61ff15",
    "--ok": "#84e15b",
    "--warn": "#f5c518",
    "--err": "#ec4b51",
    "--danger": "#ec4b51",
    "--danger-solid": "#ab1217",
    "--unmet": "#d87ba8",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#250f3b",
    "--sunken": "#0e0611",
    "--titlebar-top": "#260f3e",
    "--titlebar-bottom": "#140820",
    "--titlebar-inset": "#341555",
    "--statusbar-top": "#1c0b2e",
    "--statusbar-bottom": "#150a1a",
    "--wash-top": "#240e3a",
    "--wash-bottom": "#190b1f",
    "--hover": "#2f134c",
    "--control": "#250f3b",
    "--control-border": "#331553",
    "--control-hover": "#2f134c",
    "--control-edge": "#73ff30",
    "--field-focus-border": "#3c1861",
    "--scrollbar": "#260f3d",
    "--scrollbar-hover": "#351556",
    "--fleet-incoming-threat": "#f3c10b",
    "--row-line": "#25112e",
    "--row-hover": "#210f28",
    "--row-active": "#2c1436",
    "--row-ring": "#39175d",
    "--row-ring-focus": "#502082",
    "--on-accent": "#050208",
    "--brand-rgb": "74 228 0",
    "--wash-top-rgb": "36 14 58",
    "--wash-bottom-rgb": "25 11 31",
    "--fleet-threat-surface": "rgb(f3c10b / 0.12)",
}

MERICA_ROLES = {
    "--bg": "#050f22",
    "--panel": "#3d0c12",
    "--panel-border": "#4f0f17",
    "--field": "#020710",
    "--field-border": "#61121c",
    "--text": "#ffffff",
    "--text-dim": "#cecece",
    "--text-faint": "#a6a6a6",
    "--text-label": "#aeaeae",
    "--text-btn": "#d9d9d9",
    "--brand": "#8c8c8c",
    "--brand-deep": "#3e3e3e",
    "--brand-text": "#9b9b9b",
    "--acc-top": "#8c8c8c",
    "--acc-bottom": "#737373",
    "--brand-edge": "#a8a8a8",
    "--focus-ring": "#a8a8a8",
    "--ok": "#69ad46",
    "--warn": "#ffd23f",
    "--err": "#dd4d5f",
    "--danger": "#dd4d5f",
    "--danger-solid": "#8b1a28",
    "--unmet": "#e08a5a",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#480d15",
    "--sunken": "#040b18",
    "--titlebar-top": "#4c0e16",
    "--titlebar-bottom": "#28080c",
    "--titlebar-inset": "#5e111b",
    "--statusbar-top": "#3d0b11",
    "--statusbar-bottom": "#050f21",
    "--wash-top": "#530f18",
    "--wash-bottom": "#071633",
    "--hover": "#5e121b",
    "--control": "#480d15",
    "--control-border": "#6a141f",
    "--control-hover": "#62121c",
    "--control-edge": "#9a9a9a",
    "--field-focus-border": "#781622",
    "--scrollbar": "#5f121b",
    "--scrollbar-hover": "#761622",
    "--fleet-incoming-threat": "#ffc919",
    "--row-line": "#0a1f47",
    "--row-hover": "#091b3e",
    "--row-active": "#0c234e",
    "--row-ring": "#68141e",
    "--row-ring-focus": "#8a1a28",
    "--on-accent": "#ffffff",
    "--brand-rgb": "140 140 140",
    "--wash-top-rgb": "83 15 24",
    "--wash-bottom-rgb": "7 22 51",
    "--fleet-threat-surface": "rgb(ffc919 / 0.12)",
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
    "--brand": "#e9362a",
    "--brand-deep": "#6a110b",
    "--brand-text": "#ef6b62",
    "--acc-top": "#e9362a",
    "--acc-bottom": "#bf1e13",
    "--brand-edge": "#ef6b62",
    "--focus-ring": "#ef6b62",
    "--ok": "#26f200",
    "--warn": "#ffe600",
    "--err": "#ff2ba5",
    "--danger": "#ff2ba5",
    "--danger-solid": "#cc0075",
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
    "--wash-top": "#111111",
    "--wash-bottom": "#0e0e0e",
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
    "--on-accent": "#ffffff",
    "--brand-rgb": "233 54 42",
    "--wash-top-rgb": "17 17 17",
    "--wash-bottom-rgb": "14 14 14",
    "--fleet-threat-surface": "rgb(d4bf00 / 0.12)",
}

RON_BURGUNDY_ROLES = {
    "--bg": "#1d100a",
    "--panel": "#3b1f0f",
    "--panel-border": "#4b2713",
    "--field": "#0a0503",
    "--field-border": "#4e2914",
    "--text": "#ebe7dd",
    "--text-dim": "#c4b89c",
    "--text-faint": "#a8976e",
    "--text-label": "#b1a17b",
    "--text-btn": "#dad3c1",
    "--brand": "#d4881f",
    "--brand-deep": "#5d3c0e",
    "--brand-text": "#e39e3f",
    "--acc-top": "#d4881f",
    "--acc-bottom": "#b5741b",
    "--brand-edge": "#e4a144",
    "--focus-ring": "#e4a144",
    "--ok": "#72ab8d",
    "--warn": "#c9a227",
    "--err": "#e34560",
    "--danger": "#e34560",
    "--danger-solid": "#9c182e",
    "--unmet": "#d89060",
    "--training": "#45c8d4",
    "--link": "#7aa2f7",
    "--card-top": "#442411",
    "--sunken": "#140a06",
    "--titlebar-top": "#452411",
    "--titlebar-bottom": "#29150a",
    "--titlebar-inset": "#5d3118",
    "--statusbar-top": "#2f190c",
    "--statusbar-bottom": "#1a0e09",
    "--wash-top": "#341b0d",
    "--wash-bottom": "#20110a",
    "--hover": "#522b15",
    "--control": "#412210",
    "--control-border": "#5c3118",
    "--control-hover": "#522b15",
    "--control-edge": "#a49166",
    "--field-focus-border": "#5c3017",
    "--scrollbar": "#422311",
    "--scrollbar-hover": "#5a2f17",
    "--fleet-incoming-threat": "#c9a227",
    "--row-line": "#331b11",
    "--row-hover": "#2d180f",
    "--row-active": "#391e13",
    "--row-ring": "#562d16",
    "--row-ring-focus": "#7a401f",
    "--on-accent": "#1f0f08",
    "--brand-rgb": "212 136 31",
    "--wash-top-rgb": "52 27 13",
    "--wash-bottom-rgb": "32 17 10",
    "--fleet-threat-surface": "rgb(c9a227 / 0.12)",
}

DODGEBALL_ROLES = {
    "--bg": "#0d0d0d",
    "--panel": "#1a1a1a",
    "--panel-border": "#262626",
    "--field": "#050505",
    "--field-border": "#2e2e2e",
    "--text": "#fdf4d9",
    "--text-dim": "#f7d469",
    "--text-faint": "#f5c942",
    "--text-label": "#f6cd4f",
    "--text-btn": "#fae4a1",
    "--brand": "#dd4747",
    "--brand-deep": "#681313",
    "--brand-text": "#dd4747",
    "--acc-top": "#dd4747",
    "--acc-bottom": "#d02727",
    "--brand-edge": "#e77e7e",
    "--focus-ring": "#e77e7e",
    "--ok": "#30b2a2",
    "--warn": "#ffc925",
    "--err": "#e85688",
    "--danger": "#e85688",
    "--danger-solid": "#a91749",
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
    "--wash-top": "#1f1f1f",
    "--wash-bottom": "#141414",
    "--hover": "#2e2e2e",
    "--control": "#242424",
    "--control-border": "#343434",
    "--control-hover": "#383838",
    "--control-edge": "#f3be1a",
    "--field-focus-border": "#3a3a3a",
    "--scrollbar": "#2a2a2a",
    "--scrollbar-hover": "#3a3a3a",
    "--fleet-incoming-threat": "#f7ba00",
    "--row-line": "#1e1e1e",
    "--row-hover": "#1b1b1b",
    "--row-active": "#222222",
    "--row-ring": "#333333",
    "--row-ring-focus": "#4a4a4a",
    "--on-accent": "#ffffff",
    "--brand-rgb": "221 71 71",
    "--wash-top-rgb": "31 31 31",
    "--wash-bottom-rgb": "20 20 20",
    "--fleet-threat-surface": "rgb(f7ba00 / 0.12)",
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
    "taco-bell": _preset(
        "taco-bell",
        "Taco Bell",
        TACO_BELL_ROLES,
        [
            # Midnight drive-thru surfaces; Bell Purple and Bell Bright
            # tint the whole lot toward the bell, Drive-Thru Cyan toward
            # the neon. Fire Pink takes the accent slot faithfully -- its
            # danger (Sauce Red) is a distinct hue, so unlike Dodgeball
            # and friends the collision rule does not fire.
            ("Midnight Blue", "#0a0a1f", ["surface"]),
            ("Bell Purple", "#702082", ["surface"]),
            ("Bell Bright", "#9b2fa8", ["surface"]),
            ("Drive-Thru Cyan", "#00e5ff", ["surface", "accent"]),
            ("Midnight Deep", "#050510", ["base"]),
            ("Bell Deep", "#2e0a38", ["base", "surface"]),
            ("Neon White", "#f5f0ff", ["text"]),
            ("Neon White Dim", "#c9c0e0", ["text"]),
            ("Shell Tan", "#e8c88a", ["text"]),
            ("Fire Pink", "#ff1f8f", ["text", "accent"]),
            ("Fire Pink Bright", "#ff5aab", ["accent"]),
            ("Cheese Yellow", "#ffd400", ["text", "accent", "warning"]),
            ("Cheese Bright", "#ffe44a", ["accent", "warning"]),
            ("Lava Orange", "#ff6b1a", ["accent", "danger"]),
            ("Sauce Red", "#e8242f", ["danger"]),
            ("Lettuce Green", "#5fa832", ["success"]),
        ],
        "#050510",
        "#ffffff",
    ),
    "carls-jr": _preset(
        "carls-jr",
        "Carl's Jr",
        CARLS_JR_ROLES,
        [
            # Char-black grill surfaces; Patty Brown and Charbroil Red
            # Dark let a user tint the kitchen warmer. Star Yellow owns
            # the accent slot -- the star logo, the focus ring, the
            # Order Now flame -- because Charbroil Red is cast as BOTH
            # primary and danger. Warning stays faithful Star Yellow,
            # the Brawndo-style deliberate hue-share.
            ("Char Black", "#1a1a1a", ["surface"]),
            ("Char Gray", "#2e2e2e", ["surface"]),
            ("Patty Brown", "#6b3a1f", ["surface"]),
            ("Charbroil Red Dark", "#b8122c", ["surface", "danger"]),
            ("Char Black Deep", "#0a0a0a", ["base"]),
            ("Cola Caramel", "#3d1f0a", ["base", "surface"]),
            ("Diner White", "#f5f0e6", ["text"]),
            ("Diner White Dim", "#c9c4b8", ["text"]),
            ("Bun Tan", "#e8c99b", ["text"]),
            ("Milkshake Cream", "#fff4dc", ["text"]),
            ("Star Yellow", "#f7a800", ["text", "accent", "warning"]),
            ("Star Bright", "#ffc133", ["accent", "warning"]),
            ("Cheese Orange", "#ff8a1f", ["accent", "warning"]),
            ("Chrome Silver", "#c8c8d0", ["text", "accent"]),
            ("Lettuce Green", "#5fa832", ["success"]),
            ("Charbroil Red", "#e31837", ["accent", "danger"]),
            ("Charbroil Deep", "#8a0d20", ["danger"]),
        ],
        "#0a0a0a",
        "#ffffff",
    ),
    "brawndo": _preset(
        "brawndo",
        "Brawndo: Thirst Mutilator",
        BRAWNDO_ROLES,
        [
            # Metal-black neutrals; Mocha-style brand tints come from
            # Flavor Purple, Power Blue and Can Aluminum Dark.
            # Success stays Brawndo Green DELIBERATELY -- unlike
            # Idiocracy, where Mountain Dew took the slot -- because this
            # template's whole identity is that everything is Brawndo;
            # the accent/success hue-sharing is the joke, and the
            # composer can split them for anyone it bothers.
            ("Metal Dark", "#141414", ["surface"]),
            ("Flavor Purple", "#7b2fbe", ["surface"]),
            ("Power Blue", "#0055a5", ["surface"]),
            ("Can Aluminum Dark", "#8a8a96", ["surface"]),
            ("Metal Black", "#0a0a0a", ["base", "surface"]),
            ("Metal Deep", "#050505", ["base"]),
            ("Lightning White", "#ffffff", ["text"]),
            ("Lightning White Dim", "#e0e0e8", ["text"]),
            ("Can Aluminum", "#c8c8d0", ["text"]),
            ("Chrome Bright", "#e8e8f0", ["text"]),
            ("Brawndo Green", "#39ff14", ["text", "accent", "success"]),
            ("Green Bright", "#5fff3d", ["accent", "success"]),
            ("Electrolyte Yellow", "#ffe600", ["text", "accent", "warning"]),
            ("Electrolyte Yellow Bright", "#fff44a", ["accent", "warning"]),
            ("Electric Cyan", "#00e5ff", ["accent"]),
            ("Flavor Purple Bright", "#9b4fde", ["accent"]),
            ("Power Blue", "#0055a5", ["accent"]),
            ("Caution Orange", "#ff6b1a", ["accent", "danger"]),
            ("Thirst Mutilator Red", "#e8291c", ["accent", "danger"]),
            ("Thirst Mutilator Red Dark", "#b81e14", ["danger"]),
        ],
        "#000000",
        "#ffffff",
    ),
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
            ("Star White", "#ffffff", ["text", "accent"]),
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
