"""Contrast regressions for informative UI roles, not decorative panel edges.

Evaluate the shipped CSS declarations/tokens numerically. The separate browser
probe verifies cascade, hover, focus rendering and SVG geometry in Chromium.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
CSS = re.sub(
    r"/\*.*?\*/", "", (WEB / "style.css").read_text(encoding="utf-8"), flags=re.DOTALL
)


def declarations(selector):
    result = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        if selector in [part.strip() for part in selectors.split(",")]:
            for prop, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body):
                result[prop] = value.strip()
    return result


def color(value):
    tokens = declarations(":root")
    while value.startswith("var("):
        value = tokens[value[4:-1]]
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), value
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def contrast(foreground, background):
    def luminance(rgb):
        channels = [channel / 255 for channel in rgb]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return sum(
            value * weight
            for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
        )

    low, high = sorted((luminance(color(foreground)), luminance(color(background))))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("hover", [False, True], ids=["rest", "hover"])
def test_enabled_dim_keybind_clears_text_contrast_on_its_actual_control_fill(hover):
    # This role is an enabled latent collision, not a disabled-control exemption.
    rule = declarations(".bindbtn")
    rule.update(declarations(".bindbtn.dim"))
    rule.update(declarations(".bindbtn.dim:not(:disabled):not(.capturing)"))
    if hover:
        rule.update(declarations(".bindbtn:hover:not(:disabled)"))
    assert contrast(rule["color"], rule["background"]) >= 4.5


@pytest.mark.parametrize("capturing", [False, True], ids=["idle", "capturing"])
@pytest.mark.parametrize("hover", [False, True], ids=["rest", "hover"])
def test_enabled_collision_text_clears_contrast_without_losing_capture(
    capturing, hover
):
    # Browser coverage separately verifies specificity; this pins the numerical
    # contract of the actual state declarations, including capture under hover.
    rule = declarations(".bindbtn")
    if capturing:
        rule.update(declarations(".bindbtn.capturing"))
    rule.update(declarations(".bindbtn.clash"))
    if capturing:
        rule.update(declarations(".bindbtn.clash.capturing"))
    if hover:
        rule.update(declarations(".bindbtn:hover:not(:disabled)"))
        rule.update(declarations(".bindbtn.clash:hover:not(:disabled)"))
    assert contrast(rule["color"], rule["background"]) >= 4.5
    assert rule["color"] == "var(--err)"
    assert rule["border-color"] == ("var(--brand-text)" if capturing else "var(--err)")


def test_disabled_dim_keybind_retains_its_existing_quiet_role():
    assert declarations(".bindbtn.dim")["color"] == "var(--text-faint)"
    assert declarations(".bindbtn:disabled")["opacity"] == ".45"


@pytest.mark.parametrize("selector", [".fm-ring", ".fm-tether"])
def test_informative_formation_guides_clear_nontext_contrast(selector):
    # Reusing --panel-border here made distance/height information nearly vanish.
    stroke = declarations(selector)["stroke"]
    assert contrast(stroke, declarations("#fm-preview")["background"]) >= 3
    assert stroke != "var(--panel-border)"


@pytest.mark.parametrize("selector", ["#fittings-copy-body", "#fittings-copy-dialog"])
def test_copy_keyboard_scroll_and_fallback_targets_have_visible_focus(selector):
    focus = declarations(selector + ":focus-visible")
    assert re.match(
        r"[1-9][\d.]*px solid var\(--focus-ring\)", focus.get("outline", "")
    )
    assert contrast("var(--focus-ring)", "var(--panel)") >= 3
