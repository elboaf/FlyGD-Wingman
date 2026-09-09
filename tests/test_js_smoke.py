"""The web layer's executable gate, run from pytest.

`scripts/js_smoke.js` loads app.js and every `<script src>` of each page
under node with a permissive DOM stub and reports any module whose IIFE
throws at top level. Its header comment carries the full account of what
it can and cannot catch; the short version is that it catches everything
`test_bridge_contract.py`'s regexes catch plus the throws they cannot see
(a misspelled identifier, a missing `WM.*` member, a wrong script order),
and it cannot catch a handler body failing on a real payload, a missing
element id, or anything in CSS.

Two things live here and both matter:

- The gate itself, so a local `pytest tests/` run sees the same failure
  CI's `checks` job does, rather than the contributor learning about it
  from a red workflow after the push.
- A SELF-TEST that injects a fault into a copy of the page and asserts the
  gate reports it. Without it the gate is an assertion that "node printed
  ok" -- and a stub permissive enough to load every module is also
  permissive enough to swallow a real error if the harness regresses
  (say, a `try` that catches and logs instead of counting). The self-test
  is what proves the gate is not a no-op.

Skipped where node is absent for focused local runs; that is not acceptable
full-suite coverage. CI requires node before pytest on both platforms and
also runs this gate directly in `checks`. `test_ci_runs_the_gate_directly`
below keeps that independent page-loading gate in place.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "js_smoke.js"
WEB = ROOT / "wingman" / "web"
PAGES = ("index.html", "fleetbar.html", "sigbar.html")

needs_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not on PATH; CI runs scripts/js_smoke.js on ubuntu-latest",
)


def run_gate(web_dir: Path, *pages: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(SCRIPT), str(web_dir), *pages],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def page_modules(page: str) -> list:
    """The `<script src>` names of a page, in order, from the page itself.

    Derived rather than retyped so a module added to index.html is expected
    from the gate's output the moment it is added, not when someone
    remembers to extend a list here.
    """
    html = (WEB / page).read_text(encoding="utf-8")
    return re.findall(r'<script src="([^"]+)"></script>', html)


def copy_web(tmp_path: Path) -> Path:
    """The pages and modules only. Fonts and assets are dead weight to a
    harness that paints nothing."""
    target = tmp_path / "web"
    target.mkdir()
    for path in WEB.iterdir():
        if path.suffix in (".html", ".js"):
            shutil.copy(path, target / path.name)
    return target


@needs_node
def test_every_page_module_loads_under_node():
    """The gate, as CI runs it. Every module of all three pages must load,
    and every module must be REPORTED -- a gate that exited 0 having found
    no `<script src>` tags would be checking air, which is why the script
    refuses an empty page and this test checks the report against the
    pages' own tags rather than trusting the exit status alone."""
    result = run_gate(WEB)
    assert result.returncode == 0, result.stdout + result.stderr
    for page in PAGES:
        modules = page_modules(page)
        assert modules, f"{page} has no <script src> tags to load"
        for name in modules:
            assert f"ok    {name}" in result.stdout, (name, result.stdout)
    assert "THROW" not in result.stdout


@needs_node
@pytest.mark.parametrize(
    "module, page, fault, expect",
    [
        # A misspelled identifier at IIFE top level: a ReferenceError the
        # moment the line runs, and every registration below it never runs.
        # This is the shape no regex in the suite can see.
        ("bookmarks.js", "index.html", "  refrsh();\n", "refrsh"),
        # The incident that produced test_bridge_contract.py, reproduced as
        # a throw rather than as a regex: WM.handle refuses a name absent
        # from WM.HANDLERS, and app.js's real WM is what refuses it here.
        (
            "evesettings.js",
            "index.html",
            "  WM.handle('onNoSuchHandler', function () {});\n",
            "onNoSuchHandler",
        ),
        # The standalone bars have no WM and no lexical guard at all, so the
        # gate is their only check. Prove it sees a fault in one of them.
        ("sigbar.js", "sigbar.html", "  refrsh();\n", "refrsh"),
    ],
)
def test_the_gate_reports_an_injected_fault(tmp_path, module, page, fault, expect):
    """Proves the gate is not a no-op: a fault injected just inside a
    module's IIFE must be reported against THAT module, and the exit status
    must be non-zero. Injected after 'use strict' so the fault sits at the
    same depth as the registrations it stands in for."""
    web = copy_web(tmp_path)
    target = web / module
    source = target.read_text(encoding="utf-8")
    marker = "'use strict';\n"
    assert marker in source, f"{module} does not open with 'use strict'"
    target.write_text(source.replace(marker, marker + fault, 1), encoding="utf-8")

    result = run_gate(web, page)
    assert result.returncode != 0, result.stdout + result.stderr
    line = next(
        (ln for ln in result.stdout.splitlines() if ln.startswith(f"THROW {module}")),
        None,
    )
    assert line is not None, result.stdout
    assert expect in line, line


@needs_node
def test_the_gate_keeps_reporting_past_the_first_throw(tmp_path):
    """The failure mode this gate exists for is positional: a throw in one
    module leaves every LATER module still loading, so the report must
    name the faulty module AND keep going, or the one line that matters is
    lost behind the first. Kill app.js and every module after it must still
    appear in the report -- some as THROW, because WM is gone (that cascade
    is the real shape of the incident), and some as ok, because
    characters.js and dev.js guard their WM use and legitimately survive."""
    web = copy_web(tmp_path)
    target = web / "app.js"
    source = target.read_text(encoding="utf-8")
    target.write_text(
        source.replace("'use strict';\n", "'use strict';\n  refrsh();\n", 1),
        encoding="utf-8",
    )
    result = run_gate(web, "index.html")
    assert result.returncode != 0
    assert "THROW app.js -> refrsh is not defined" in result.stdout
    later = page_modules("index.html")[1:]
    assert later
    reported = {
        ln.split()[1]: ln.split()[0] for ln in result.stdout.splitlines() if " " in ln
    }
    for name in later:
        assert reported.get(name) in ("ok", "THROW"), (name, result.stdout)
    assert "WM is not defined" in result.stdout


@needs_node
def test_fleetbar_runtime_executes_split_damage_rendering():
    """Runs the real fleetbar.js render path against representative rows --
    proves handler-body behavior neither the lexical assertions above nor
    the top-level-load gate can see. See scripts/test_fleetbar_runtime.js
    for the payloads and the exact OUT/IN/NO LOG/aria-label assertions.
    Independent of scripts/js_smoke.js, which stays the top-level module
    gate for all three pages.
    """
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "test_fleetbar_runtime.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_runs_the_gate_directly():
    """CI's `checks` job calls the script directly, independently of pytest.
    Deleting that step must fail here rather than silently leaving page
    loading entirely to the full-suite job."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node scripts/js_smoke.js" in workflow


def test_the_gate_loads_every_page_that_reaches_a_window():
    """The script's page list is hand-kept, and this pins it to the three
    pages that actually open a WebView2 window. A fourth page added to
    wingman/web without joining the list would load unchecked."""
    script = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"const PAGES = \[(.*?)\];", script)
    assert match
    listed = re.findall(r"'([^']+)'", match.group(1))
    assert sorted(listed) == sorted(PAGES)
    assert sorted(listed) == sorted(p.name for p in WEB.glob("*.html"))
