"""Fleet hierarchy retains independent controls and their status owners."""

import re
from pathlib import Path

from tests.html_tree import TextPageTree

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"


def walk(node):
    yield node
    for child in node["children"]:
        yield from walk(child)


def page():
    tree = TextPageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return tree.root


def by_id(root, name):
    return next((n for n in walk(root) if n["attrs"].get("id") == name), None)


def has(root, name):
    return by_id(root, name) is not None


def test_overview_precedes_independent_display_and_sharing_controls():
    root = page()
    fleet = by_id(root, "section-fleet")
    sections = [n for n in fleet["children"] if n["tag"] == "section"]
    assert [n["attrs"].get("id") for n in sections] == [
        "fleet-overview",
        "preview-fleet-options",
        "fleet-sharing",
    ]
    overview, local, sharing = sections
    for name in ("local", "sharing", "auth", "verification"):
        fact = by_id(overview, "fleet-overview-" + name)
        assert fact is not None
        assert "Unknown" in fact["text"], "unhydrated facts must not fabricate Off"
        assert "role" not in fact["attrs"], "overview must not duplicate live owners"
    assert not any(n["tag"] in ("input", "button", "select") for n in walk(overview))
    assert has(local, "fleetbar-enabled") and not has(local, "sharing-enabled")
    assert has(sharing, "sharing-enabled") and not has(sharing, "fleetbar-enabled")
    headings = [n["text"].strip() for n in walk(fleet) if n["tag"] == "h2"]
    assert headings == ["Fleet overview", "Local display", "External sharing"]


def test_sharing_refresh_and_attempt_actions_keep_their_owners():
    fleet = by_id(page(), "section-fleet")
    header = next(
        (n for n in walk(fleet) if n["tag"] == "header" and has(n, "sharing-refresh")),
        None,
    )
    assert header is not None
    assert any(
        n["tag"] == "h3" and n["text"].strip() == "Connection" for n in walk(header)
    )
    assert (
        by_id(header, "sharing-refresh")["attrs"]["aria-label"]
        == "Refresh sharing connection and verification"
    )
    current = by_id(fleet, "sharing-current")
    pending = by_id(fleet, "sharing-pending")
    assert current is not None and pending is not None
    assert has(current, "sharing-sources") and has(pending, "sharing-pending-sources")
    assert not has(pending, "sharing-action"), (
        "the action live owner must not be hidden with an empty pending group"
    )
    assert not has(by_id(fleet, "sharing-eligible"), "sharing-eligibility")
    sharing = by_id(fleet, "fleet-sharing")
    ids = [n["attrs"].get("id") for n in walk(sharing)]
    assert ids.index("sharing-sources") < ids.index("sharing-boss")
    assert ids.index("sharing-pending-sources") < ids.index("sharing-boss")
    for name in (
        "sharing-connection",
        "sharing-browser-error",
        "sharing-consent",
        "sharing-eligibility",
        "sharing-preference",
        "sharing-action",
    ):
        node = by_id(sharing, name)
        assert node["attrs"].get("role") == "status"
        assert "hidden" not in node["attrs"]
    assert "never raw logs or history" in by_id(sharing, "sharing-scope")["text"]


def test_fleet_subsections_keep_text_on_an_opaque_surface():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"#section-fleet \.fleet-subsection\s*\{([^}]+)\}", css)
    assert rule and "background: var(--panel)" in rule[1], (
        "flat subsections must not expose the shell watermark behind status text"
    )
    assert "#section-fleet h2::before { display: none; }" in css


def test_local_display_state_and_recovery_stay_together():
    local = by_id(page(), "preview-fleet-options")
    runtime = next(
        (
            n
            for n in walk(local)
            if "fleet-local-control" in n["attrs"].get("class", "").split()
        ),
        None,
    )
    assert runtime is not None
    assert has(runtime, "fleetbar-enabled") and has(runtime, "fleetbar-enabled-status")
    assert has(runtime, "fleetbar-state")
    assert not any(
        n["tag"] == "button" and n["text"].strip() == "Refresh" for n in walk(local)
    )
    assert by_id(local, "fleetbar-characters")["tag"] == "details"
