"""Lexical bridge/convention guards; real browser evidence is recorded separately."""

from pathlib import Path

WEB = Path(__file__).parents[1] / "wingman" / "web"


def test_sharing_module_loaded_after_allowlist_before_dev_first_use():
    html = (WEB / "index.html").read_text()
    assert (
        html.index('src="app.js"')
        < html.index('src="fleetsharing.js"')
        < html.index('src="dev.js"')
    )
    assert "'onFleetSharingState'" in (WEB / "app.js").read_text()
    js = (WEB / "fleetsharing.js").read_text()
    assert "WM.handle('onFleetSharingState', render)" in js


def test_sharing_controls_have_own_card_and_never_publish_alts_checklist():
    html = (WEB / "index.html").read_text()
    card = html.split('id="fleet-sharing"', 1)[1].split("</section>", 1)[0]
    assert "<h2>Fleet sharing</h2>" in card
    assert '<label class="check">' in card
    assert 'id="sharing-enabled" disabled' in card
    assert 'class="lab" for="sharing-boss"' in card
    assert 'id="sharing-boss"' in card
    assert 'id="sharing-sources"' in card
    js = (WEB / "fleetsharing.js").read_text()
    assert "wm:section" in js
    assert "visibilitychange" in js
    assert "innerHTML" not in js
    assert "source_control === 'acknowledged'" not in js
