"""The theme engine (themes.py): derivation, safety, and the settings seam.

The page cannot be rendered by pytest, so — like bookmarks.py — everything
decidable about the feature lives in this module and is asserted here. The
load-bearing property is the one the module docstring argues: derivation
preserves each role's lightness, so the presets' measured contrast ratios
hold under EVERY combination the composer can produce. These tests pin
that property over the whole swatch pools, not spot values, because the
pools are exactly what a future palette edit will change.
"""

import colorsys

import pytest

from wingman import settings, themes


def _lightness(hex_color):
    _, light, _ = colorsys.rgb_to_hls(
        *[int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    )
    return light


def _all_picks(preset, families):
    """Every legal combination over the given families' pools."""
    pools = [
        [(f, hex_color) for hex_color in themes.legal_swatches(preset, f, {})]
        for f in families
    ]
    if not pools:
        return [{}]
    rest = _all_picks(preset, families[1:])
    combinations = []
    for family, hex_color in pools[0]:
        for tail in rest:
            combination = dict(tail)
            combination[family] = hex_color
            combinations.append(combination)
    return combinations


def test_every_preset_role_clears_aa_against_its_surfaces():
    """The whole point of lightness-preserving derivation: text stays
    legible on every surface the user can assemble, and the accent fill
    carries its own label. Asserted over the FULL cross product of the
    surface/base/text pools so a palette edit cannot quietly shrink a
    pool below safety."""
    for preset in themes.PRESETS.values():
        for picks in _all_picks(preset, ["surface", "base", "text"]):
            effective = themes.resolve(preset, picks)
            for role in ("--text", "--text-dim", "--text-faint", "--text-label"):
                for surface in ("--panel", "--bg"):
                    ratio = themes._contrast(effective[role], effective[surface])
                    assert ratio >= 4.5, (
                        f"{preset['id']}: {role} on {surface} at {picks} "
                        f"is {ratio:.2f}:1"
                    )


def test_on_accent_clears_aa_for_every_accent_choice():
    for preset in themes.PRESETS.values():
        for hex_color in themes.legal_swatches(preset, "accent", {}):
            effective = themes.resolve(preset, {"accent": hex_color})
            ratio = themes._contrast(
                effective["--on-accent"], effective["--acc-bottom"]
            )
            assert ratio >= 4.5, (
                f"{preset['id']}: on-accent on {hex_color} is {ratio:.2f}:1"
            )


def test_derivation_preserves_lightness():
    """The mechanism the safety rests on, pinned directly: a derived role
    keeps its reference lightness and takes only hue/saturation."""
    preset = themes.PRESETS["zoolander"]
    default = themes.resolve(preset, {})
    recolored = themes.resolve(preset, {"surface": "#2c3e5c"})
    for role in ("--panel", "--card-top", "--control", "--row-ring"):
        assert abs(_lightness(default[role]) - _lightness(recolored[role])) < 1e-6


def test_default_resolve_is_the_preset_mapping():
    """The default mapping resolves to itself: every declared role passes
    through untouched, the computed channels (--brand-rgb, the wash fades,
    --on-accent, the fleet threat tint) are derived rather than stored
    twice, and resolving is idempotent. Some preset tables carry the
    computed keys baked in (their default mapping WAS a resolve over
    picks), some do not; both must land in the same place."""
    computed = {
        "--on-accent",
        "--brand-rgb",
        "--wash-top-rgb",
        "--wash-bottom-rgb",
        "--fleet-threat-surface",
    }
    for preset in themes.PRESETS.values():
        effective = themes.resolve(preset, {})
        for role, value in preset["roles"].items():
            assert effective[role] == value
        assert computed <= set(effective)
        assert themes.resolve(preset, {}) == effective


def test_resolve_ignores_unknown_families_and_disallowed_swatches():
    preset = themes.PRESETS["wingman-dark"]
    untouched = themes.resolve(preset, {})
    tampered = themes.resolve(preset, {"accent": "#e8eaed", "bogus": "#ff0000"})
    assert tampered == untouched


def test_link_stays_fixed_under_any_pick():
    """style.css's --link note: the outbound-link blue carries a legal
    obligation. No family may drive it, in either preset."""
    for preset in themes.PRESETS.values():
        everything = {f: "#123456" for f in themes.FAMILIES}
        effective = themes.resolve(preset, everything)
        assert effective["--link"] == preset["roles"]["--link"]
        assert effective["--training"] == preset["roles"]["--training"]
        assert effective["--unmet"] == preset["roles"]["--unmet"]


def test_normalize_drops_undeclared_state():
    assert themes.normalize(None) == ("wingman-dark", {})
    assert themes.normalize({"preset": "nope"}) == ("wingman-dark", {})
    picks = themes.normalize(
        {
            "preset": "zoolander",
            "families": {"accent": "#D4A843", "text": "#000000", "wat": "#111111"},
        }
    )
    assert picks == ("zoolander", {"accent": "#d4a843"})


def test_legal_swatches_respect_family_tags():
    wingman = themes.PRESETS["wingman-dark"]
    assert "#8430d9" in themes.legal_swatches(wingman, "accent", {})
    assert "#8430d9" not in themes.legal_swatches(wingman, "text", {})


def test_every_family_has_a_label_and_a_description():
    """The dropdown is named by the label and explained by the description;
    one without the other is either a mystery noun or an orphan sentence.
    Both travel to the page in the theme payload."""
    for family in themes.FAMILIES:
        assert themes.FAMILY_LABELS[family]
        assert themes.FAMILY_DESCRIPTIONS[family]


def test_settings_ship_the_theme_section():
    fresh = settings._fresh_defaults()
    assert fresh["theme"] == {"preset": "wingman-dark", "families": {}}


def test_validated_theme_projects_onto_shipped_presets():
    validated = settings.validated_theme(
        {"preset": "zoolander", "families": {"accent": "#7cb342"}}
    )
    assert validated == {
        "preset": "zoolander",
        "families": {"accent": "#7cb342"},
    }
    # A hand-edited file naming an unknown preset lands on the default
    # rather than being preserved.
    assert settings.validated_theme({"preset": "nope"})["preset"] == "wingman-dark"


def test_zoolander_default_mapping_is_the_field_approved_look():
    """The shipping default for Zoolander is the 'extreme' mapping the
    maintainer approved in the palette walkthrough: lime accent, hot
    magenta danger, magnum-deep surfaces. Hand-tuned, so pinned."""
    roles = themes.PRESETS["zoolander"]["roles"]
    assert roles["--brand"] == "#7cb342"
    assert roles["--err"] == "#e91e8c"
    assert roles["--panel"] == "#0d0d1a"


@pytest.mark.parametrize("preset_id", list(themes.PRESETS))
def test_every_preset_ships_a_pool_for_every_family(preset_id):
    """A family with an empty pool renders as a labelled row with no
    control in it -- silently, the way an empty container always fails."""
    preset = themes.PRESETS[preset_id]
    for family in themes.FAMILIES:
        assert themes.legal_swatches(preset, family, {}), (
            f"{preset_id}: family {family} has an empty pool"
        )


def test_preset_strip_is_derived_from_the_default_mapping():
    """The picker's identity strip must never be a hand-kept copy: it is
    four roles read straight out of each preset's own default mapping, so
    a preset edit reflows its strip without a second place to change."""
    for preset in themes.PRESETS.values():
        strip = themes.preset_strip(preset)
        assert len(strip) == len(themes._STRIP_ROLES)
        assert strip == [themes.resolve(preset, {})[role] for role in themes._STRIP_ROLES]
        assert all(color.startswith("#") for color in strip)
