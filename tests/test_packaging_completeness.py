"""Every importable subpackage must be listed in pyproject's `packages`.

pyproject.toml:38-49 records why this is not paranoia: discovery is
enumerated by hand, subpackages are NOT implied by their parent, and a
missing entry "installs cleanly and fails at import time in the built
artifact, not in the checkout where the source tree makes it work anyway."
A source checkout passes every test while the frozen release dies on
launch, so only a test that reads the manifest can catch it here.
"""

import ast
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib

import pytest
import yaml

from tests import test_setup_catalog
from wingman import paths
from wingman.eveauth import application as eveauth_application

# Reuse the temporary synthetic catalog, never mutate shipped assets for faults.
catalog_fixture = test_setup_catalog.catalog_fixture

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL_UPDATE_FIXTURE = ROOT / "tests" / "manual" / "update_fixture.iss"
MANUAL_UPDATE_HARNESS = ROOT / "tests" / "manual" / "update_harness.py"
MANUAL_PREVIEW_CROP_HARNESS = ROOT / "tests" / "manual" / "preview_crop_harness.py"
MANUAL_PREVIEW_CROP_MODEL = ROOT / "tests" / "manual" / "preview_crop_model.py"
MANUAL_PREVIEW_CROP_WINDOWS = ROOT / "tests" / "manual" / "preview_crop_windows.py"


def test_readme_discloses_automatic_github_update_checks():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "GitHub release API" in readme
    assert "once each time Wingman starts" in readme
    assert "SHA-256" in readme
    assert "does not prove publisher identity" in readme


def test_readme_google_token_note_is_only_the_boundary_and_table_link():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    previous = readme.index("- **Your Google credentials")
    start = readme.index("\n- **", previous) + 1
    end = readme.index("\n- **Video data", start)
    note = " ".join(readme[start:end].split())

    assert note == (
        "- **No FlyGD-operated backend receives Google OAuth tokens or other "
        "application data.** See the [Privacy section](#privacy) network table "
        "for the external services each feature contacts and what it sends."
    )


def test_readme_network_table_covers_eve_and_current_user_triggers():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ccp_row = next(
        line for line in readme.splitlines() if line.startswith("| CCP EVE SSO and ESI")
    )
    assert "login.eveonline.com" in ccp_row
    assert "esi.evetech.net" in ccp_row
    assert "skills, queue, and attributes" in ccp_row
    assert "Authenticated ESI skills, queue, and attributes requests" in ccp_row
    assert "skill plans through unauthenticated" in ccp_row
    assert "`/universe/ids`" in ccp_row
    assert "type metadata" in ccp_row
    assert "group metadata" in ccp_row
    assert ccp_row.index("`/characters/{id}/`") < ccp_row.index("`/universe/names`")
    assert "remaining display names" in ccp_row
    assert "FightRecorder" in readme
    assert not re.search(
        r"makes network connections to (?:exactly )?"
        r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten) places",
        readme,
        re.IGNORECASE,
    )
    for removed_copy in (
        "Also post combat logs to Discord",
        "combat logs go with it only while that box is ticked",
        "Untick the box to upload the video alone",
    ):
        assert removed_copy not in readme


def test_smoke_network_checks_scope_ccp_after_the_startup_update_check():
    smoke = (ROOT / "docs" / "smoke-checklist.md").read_text(encoding="utf-8")
    flat = " ".join(smoke.split())
    assert "Clear the capture after the automatic GitHub startup check finishes" in flat
    assert "Settings > Characters authorization or Skills refresh interaction" in flat
    assert "only that EVE interaction contacts the network" in flat
    assert "only the Skills interaction" not in flat


def test_readme_eve_authorization_docs_point_to_settings_characters_and_current_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    flat = " ".join(readme.split())
    assert (
        "Settings → Characters is the only place to authorize, reconnect, or "
        "forget EVE characters." in flat
    )
    assert len(eveauth_application.FULL_AUTH_SCOPES) == 4
    for scope in sorted(eveauth_application.FULL_AUTH_SCOPES):
        assert scope in readme
    for phrase in (
        "Every new EVE sign-in from Settings → Characters requests the full Skills-and-Fittings set",
        "If EVE returns a character Wingman does not know yet, Wingman adds it only after Skills and Fittings cleanup both verify no orphan state blocks that ID.",
        "If Wingman already has that character with a known owner and EVE returns a different known owner, the sign-in is refused and the existing grant stays in place.",
        "Older grants that contain only the two Skills scopes keep working for Skills.",
        "Reconnecting any character now uses the same full four-scope request; there is no per-feature authorization button.",
        "If cleanup is only partly saved, Wingman keeps the character blocked from being added again until reconciliation proves what survived.",
    ):
        assert phrase in flat
    for removed in (
        "esi-characters.read_skills.v1",
        "Existing Skills-only consent remains valid for Skills.",
        "**Skills only**",
        "Enable fittings",
        "Choosing a different character on EVE's consent screen is refused",
        "wrong character is refused",
        "Whether pressed from Skills or Fittings",
        "eve_skills.json` holds Skills-only snapshots",
    ):
        assert removed not in readme


def test_smoke_and_screenshot_prompt_cover_current_characters_and_fittings_checks():
    smoke = (ROOT / "docs" / "smoke-checklist.md").read_text(encoding="utf-8")
    flat_smoke = " ".join(smoke.split())
    assert "Settings > Characters" in smoke
    assert "50-row keyboard/menu checks" in flat_smoke
    assert "Fittings spacing at 100%, 125%, 150%, and 200% scaling" in flat_smoke
    assert "Open Settings on Uploading, Characters, or General" in flat_smoke
    assert "Uploading, Characters, Bookmarks, Previews, Alerts, General" in flat_smoke
    assert "Forget from Settings > Characters" in flat_smoke
    assert (
        "complete cleanup removes the shared credential, Skills snapshot, fitting snapshot and that character's presence"
        in flat_smoke
    )
    assert (
        "partial cleanup removes the row but leaves re-add blocked until reconciliation proves what survived"
        in flat_smoke
    )
    assert "refused cleanup leaves the row" in flat_smoke
    assert "keeps the shared credential" in flat_smoke
    assert "leaves both feature snapshots intact" in flat_smoke
    assert (
        "Forget one character from Fittings, then repeat from Skills after re-adding it."
        not in flat_smoke
    )
    assert "Open Settings on Account, Discord or General" not in flat_smoke
    for scope in sorted(eveauth_application.FULL_AUTH_SCOPES):
        assert scope in smoke
    for removed in (
        "esi-characters.read_skills.v1",
        "Skills-only remains Skills-only",
        "row still reads **Skills only**",
        "Reconnect a Skills-only character",
        "as appropriate for that character's enabled capabilities",
        "Complete it with THE SAME character",
        "Completing it with the wrong character is refused",
        "requests the two read-only scopes",
        "wingman/eveskills/application.py",
        "`Add character` is disabled",
        "Click `Add character`",
        "consent screen names exactly the two scopes",
        "Open `%LOCALAPPDATA%\\FlyGD Wingman\\eve_skills.json`, corrupt one character's `refresh_token_blob`",
        "capability enable",
        "only the Skills interaction",
        "leaves the add blocked",
    ):
        assert removed not in smoke

    path = ROOT / "scripts" / "shoot_screens.py"
    spec = importlib.util.spec_from_file_location("shoot_screens", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    prompt = (ROOT / ".pi" / "prompts" / "screenshots.md").read_text(encoding="utf-8")
    flat_prompt = " ".join(prompt.split())
    assert (
        "walks the screen inventory in that checkout's `scripts/shoot_screens.py`"
        in flat_prompt
    )
    assert "walks **" not in flat_prompt
    for phrase in (
        "Settings — Characters",
        "Settings — Characters (waiting)",
        "Settings — Characters (partial cleanup)",
        "Settings — Characters (narrow 840x625)",
        "Fittings — Narrow (840x625)",
    ):
        assert phrase in flat_prompt
    assert "Fittings — Characters" not in flat_prompt


def test_external_privacy_policy_is_not_a_repository_release_gate():
    documents = {
        "plan": ROOT
        / "docs"
        / "superpowers"
        / "plans"
        / "2026-09-02-guided-updates.md",
        "spec": ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-09-02-guided-updates-design.md",
        "smoke": ROOT / "docs" / "smoke-checklist.md",
    }
    forbidden = {
        "plan": (
            "External release action:",
            "Update and deploy the published privacy statement",
            "external privacy-policy deployment",
        ),
        "spec": (
            "Before release, the externally published",
            "shipping is blocked until the public statement",
            "Published privacy policy:",
        ),
        "smoke": ("The published privacy policy matches before release",),
    }

    for name, path in documents.items():
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden[name]:
            assert phrase not in text


def test_updater_docs_do_not_claim_power_loss_durability():
    documents = (
        ROOT / "docs" / "superpowers" / "plans" / "2026-09-02-guided-updates.md",
        ROOT / "docs" / "superpowers" / "specs" / "2026-09-02-guided-updates-design.md",
    )
    forbidden = (
        "durable handoff",
        "durable classification",
        "durably classified",
        "durably classifies",
        "durable handed-off",
    )

    for path in documents:
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert all(phrase not in text for phrase in forbidden)
        assert "power-loss durability" in text
        assert "marker's mtime" in text
        assert "stale orphan marker" in text
        assert "best-effort" in text


def test_updater_manual_docs_keep_fixture_and_windows_policy_claims_narrow():
    manual = (ROOT / "tests" / "manual" / "README.md").read_text(encoding="utf-8")
    smoke = (ROOT / "docs" / "smoke-checklist.md").read_text(encoding="utf-8")
    flat_manual = " ".join(manual.split())
    flat_smoke = " ".join(smoke.split())

    assert "verify the exact basename" in flat_manual
    assert "guards do not identify the file's contents" in flat_manual
    assert "must compile and use the provided fixture" in flat_manual
    assert "ShellExecute starts only" not in flat_manual
    assert "filesystem and local policy that support Mark-of-the-Web" in flat_manual
    assert "`Zone.Identifier` is present and listed" in flat_manual
    assert (
        "must not be worked around by weakening host or Attachment Services validation"
        in flat_manual
    )
    assert "reputation warning depending on local policy" in flat_smoke
    assert "must leave zone checks enabled" in flat_smoke
    assert "normal visible installer" in flat_smoke
    assert "reputation UI is mandatory" not in flat_smoke


def test_pyinstaller_is_exactly_pinned_in_an_opt_in_build_group():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        project = tomllib.load(fh)

    assert project.get("dependency-groups", {}).get("build") == [
        "pyinstaller==6.22.2"
    ], "PyInstaller must be exactly pinned in the build-only group"
    runtime = project["project"]["dependencies"]
    dev = project["project"]["optional-dependencies"]["dev"]
    assert not any("pyinstaller" in dep.lower() for dep in runtime + dev)
    defaults = project.get("tool", {}).get("uv", {}).get("default-groups", ["dev"])
    assert defaults != "all" and "build" not in defaults


def test_pyinstaller_build_action_uses_the_lock_not_an_ad_hoc_install():
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    commands = "\n".join(
        line for line in action.splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(
        r"\buv\s+pip\s+install\b[^\n]*pyinstaller", commands, re.IGNORECASE
    ), "PyInstaller must not be installed outside uv.lock"
    sync = "uv sync --locked --group build"
    assert sync in commands
    assert commands.index(sync) < commands.index("python -m PyInstaller")
    after_sync = commands.split(sync, 1)[1].lstrip()
    assert after_sync.startswith('if ($LASTEXITCODE -ne 0) { throw "uv sync failed')
    comments = " ".join(
        line.strip().removeprefix("#").strip()
        for line in action.splitlines()
        if line.lstrip().startswith("#")
    )
    for explanation in ("6.x", "one-folder layout", "load-bearing", "installer.iss"):
        assert explanation in comments


def _workflow_steps(path, job=None):
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return workflow["jobs"][job]["steps"] if job else workflow["runs"]["steps"]


def _python_body(step):
    assert step["shell"] == "bash", "Python heredocs need bash on both runners"
    return re.search(r"python - <<'(\w+)'\n([\s\S]+)\n\1", step["run"])[2]


# Each pytest job owns its prerequisites; a codec built by a later installer
# job cannot help it. Derive the inventory so new workflows/jobs join both guards.
PYTEST_JOBS = [
    pytest.param(path, name, id=f"{path.name}:{name}")
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    for name, job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].items()
    if any(
        re.search(r"\bpytest(?:\s|$)", step.get("run", ""))
        for step in job.get("steps", [])
    )
]


@pytest.mark.parametrize(("workflow", "job"), PYTEST_JOBS)
def test_workflow_setup_prerequisites_precede_pytest_without_optional_gates(
    workflow, job
):
    steps = _workflow_steps(workflow, job)
    names = [step.get("name") for step in steps]
    required = [
        "Check Node",
        "Build the settings codec for tests",
        "Install the settings codec for tests",
    ]
    for name in required:
        assert name in names, f"{workflow.name}:{job} is missing {name}"
        step = steps[names.index(name)]
        assert names.index("Install") < names.index(name) < names.index("Test")
        assert not step.get("continue-on-error") and "if" not in step
        assert step["shell"] == "bash"
    assert steps[names.index("Check Node")]["run"] == "node --version"
    assert steps[names.index(required[1])]["run"] == (
        "cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml "
        "--target-dir packaging/settings-codec/target"
    )
    assert (
        names.index(required[0]) < names.index(required[1]) < names.index(required[2])
    )
    for index, step in enumerate(steps):
        if re.search(r"\bpytest(?:\s|$)", step.get("run", "")):
            assert index > names.index(required[2])
            assert "-rs" in step["run"].split()


def test_ci_keeps_the_independent_codec_regression():
    steps = _workflow_steps(ROOT / ".github/workflows/ci.yml", "test")
    step = next(s for s in steps if s.get("name") == "Test settings codec")
    assert step["run"] == (
        "cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml"
    )


@pytest.mark.parametrize(("workflow", "job"), PYTEST_JOBS)
def test_workflow_codec_install_fails_missing_build_then_copies_to_runtime_location(
    workflow, job, tmp_path, monkeypatch
):
    from wingman import paths
    from wingman.evesettings import codec

    steps = _workflow_steps(workflow, job)
    step = next(
        (s for s in steps if s.get("name") == "Install the settings codec for tests"),
        None,
    )
    assert step is not None, f"{workflow.name}:{job} must install the codec"
    assert step["run"].startswith("uv run --no-sync python")
    body = compile(_python_body(step), f"{workflow.name}:{job}:codec-install", "exec")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        exec(body, {})
    source = tmp_path / "packaging/settings-codec/target/release" / CODEC.name
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic release artifact")
    exec(body, {})
    target = tmp_path / "packaging/bin" / CODEC.name
    assert target.read_bytes() == b"synthetic release artifact"
    assert paths.codec_exe() == str(target) and codec.codec_available()
    monkeypatch.setattr(codec, "codec_available", lambda: False)
    with pytest.raises(
        AssertionError, match="Native integration tests require the built codec"
    ):
        exec(body, {})


@pytest.mark.parametrize("has_junit", [False, True])
def test_ci_failure_annotations_preserve_prerequisite_failure_without_junit(
    tmp_path, has_junit
):
    steps = _workflow_steps(ROOT / ".github/workflows/ci.yml", "test")
    step = next(s for s in steps if s.get("name") == "Surface failures")
    assert step["if"] == "failure()"
    body = _python_body(step)
    if has_junit:
        (tmp_path / "pytest-result.xml").write_text(
            '<testsuites><testsuite><testcase classname="tests.synthetic" name="broken">'
            '<failure message="failure"/></testcase></testsuite></testsuites>',
            encoding="utf-8",
        )
    result = subprocess.run(
        [sys.executable, "-c", body], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert (
        "::error::tests.synthetic.broken"
        if has_junit
        else "::notice::pytest-result.xml is absent; inspect the failed prerequisite step"
    ) in result.stdout


def test_windows_build_checks_frozen_yaml_not_only_development_imports():
    steps = _workflow_steps(ROOT / ".github/actions/build-installer/action.yml")
    names = [step.get("name") for step in steps]
    name = "Verify setup YAML is bundled"
    assert (
        names.index("Build executable")
        < names.index(name)
        < names.index("Build installer")
    )
    step = steps[names.index(name)]
    assert not step.get("continue-on-error") and "if" not in step
    body = _python_body(step)
    compile(body, "verify-frozen-yaml", "exec")
    for token in (
        'CArchiveReader("dist/Wingman/Wingman.exe")',
        'open_embedded_archive("PYZ.pyz")',
        '"wingman.evesettings.overview_yaml"',
        '"yaml"',
        '"yaml.loader"',
        '"yaml.events"',
        '"yaml.constructor"',
        '"yaml.cyaml"',
        "import yaml._yaml",
        'Path("dist/Wingman/_internal/yaml")',
        "Path(yaml._yaml.__file__).name",
        "extension.is_file()",
        '"THIRD-PARTY-NOTICES.md"',
        '"## PyYAML\\n"',
        'f"Version: {yaml.__version__}"',
        'distribution("PyYAML")',
        "license_text in section",
    ):
        assert token in body, token


def test_setup_presets_are_explicit_package_data_and_frozen_assets():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)["tool"]["setuptools"]
    patterns = config.get("package-data", {}).get("wingman", [])
    assert "assets/setup-presets/*.json" in patterns
    assert "assets/setup-presets/*.txt" in patterns
    source = ROOT / "wingman/assets/setup-presets"
    expected = {path for path in source.iterdir() if path.is_file()}
    collected = {
        path for pattern in patterns for path in (ROOT / "wingman").glob(pattern)
    }
    assert expected and expected <= collected
    spec = (ROOT / "packaging/uploader.spec").read_text(encoding="utf-8")
    assert (
        '(str(ROOT / "wingman" / "assets" / "setup-presets"), "assets/setup-presets")'
        in spec
    )


def test_setup_presets_disable_checkout_newline_conversion():
    assets = sorted((ROOT / "wingman/assets/setup-presets").iterdir())
    names = [path.relative_to(ROOT).as_posix() for path in assets]
    result = subprocess.run(
        ["git", "check-attr", "-z", "text", "--stdin"],
        input="\0".join(names) + "\0",
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    records = result.stdout.rstrip("\0").split("\0")
    assert records[::3] == names
    assert records[2::3] == ["unset"] * len(names), (
        "Hash-bound setup and exact licence bytes must not depend on core.autocrlf"
    )


def test_setup_presets_inventory_gate_runs_after_freeze_before_installer():
    steps = _workflow_steps(ROOT / ".github/actions/build-installer/action.yml")
    names = [step.get("name") for step in steps]
    name = "Verify setup presets are bundled"
    assert name in names
    assert (
        names.index("Build executable")
        < names.index(name)
        < names.index("Build installer")
    )
    step = steps[names.index(name)]
    assert not step.get("continue-on-error") and "if" not in step
    assert step["run"].startswith("uv run --no-sync python")


@pytest.mark.parametrize("fault", ["none", "missing", "changed", "extra"])
@pytest.mark.parametrize("asset", ["manifest", "artifact", "license"])
def test_frozen_setup_inventory_executes_on_actual_bundle_bytes(
    catalog_fixture, tmp_path, monkeypatch, fault, asset
):
    entry, _text, directory = catalog_fixture
    steps = _workflow_steps(ROOT / ".github/actions/build-installer/action.yml")
    step = next(
        (s for s in steps if s.get("name") == "Verify setup presets are bundled"), None
    )
    assert step is not None, "Frozen preset inventory must be an executable build gate"
    body = compile(_python_body(step), "verify-frozen-setup-presets", "exec")
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "wingman/assets/setup-presets"
    shutil.copytree(directory, source)
    monkeypatch.setattr(paths, "setup_presets_dir", lambda: source)
    frozen = tmp_path / "dist/Wingman/_internal/assets/setup-presets"
    shutil.copytree(source, frozen)
    filename = {
        "manifest": "catalog.json",
        "artifact": f"{entry['id']}-r{entry['revision']}.json",
        "license": entry["overview_sources"][0]["license_file"],
    }[asset]
    if fault == "missing":
        (frozen / filename).unlink()
    elif fault == "changed":
        with (frozen / filename).open("ab") as handle:
            handle.write(b" ")
    elif fault == "extra":
        (frozen / "orphan-r1.json").write_bytes(b"invented unlisted content")
    if fault == "none":
        exec(body, {})
    else:
        with pytest.raises(
            AssertionError, match=r"[Ii]nventory|[Bb]ytes|[Mm]issing|[Dd]iffer"
        ):
            exec(body, {})


def test_every_subpackage_is_declared():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    on_disk = {
        ".".join(p.parent.relative_to(ROOT).parts)
        for p in (ROOT / "wingman").rglob("__init__.py")
    }
    assert on_disk <= declared, f"undeclared packages: {sorted(on_disk - declared)}"


def test_profilecopy_module_ships_under_the_already_declared_evesettings_package():
    """Whole-profile copy (wingman/evesettings/profilecopy.py) added no new
    subpackage -- it is a module inside wingman.evesettings, which
    pyproject.toml already lists. `test_every_subpackage_is_declared` above
    only ever sees __init__.py directories, so it would stay silent if this
    file were ever hoisted into its own undeclared subpackage (e.g.
    wingman.evesettings.profilecopy as a package). This pins both halves of
    that assumption directly, without touching pyproject.toml."""
    module = ROOT / "wingman" / "evesettings" / "profilecopy.py"
    assert module.is_file(), "profilecopy.py must live inside wingman/evesettings/"
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    assert "wingman.evesettings" in declared


CODEC = (
    ROOT
    / "packaging"
    / "bin"
    / (
        "wingman-settings-codec.exe"
        if sys.platform == "win32"
        else "wingman-settings-codec"
    )
)


def test_fleet_runtime_and_pages_are_in_declared_package_and_frozen_web_tree():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = set(tomllib.load(fh)["tool"]["setuptools"]["packages"])
    assert "wingman.telemetry" in declared
    assert (ROOT / "wingman" / "ui" / "fleetbar.py").is_file()
    assert (ROOT / "wingman" / "web" / "fleetbar.html").is_file()
    assert (ROOT / "wingman" / "web" / "fleetbar.js").is_file()
    spec = (ROOT / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert '(str(WEB), "web")' in spec


def test_the_spec_bundles_the_settings_codec_and_its_licence():
    spec = (ROOT / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert 'BIN / "wingman-settings-codec.exe"' in spec
    # One combined licence file for the whole static link, not one per
    # crate. Named here and in the action's licence assertion; both have to
    # move together or the build throws on a file the spec never shipped.
    assert 'BIN / "settings-codec-COPYING.txt"' in spec
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "settings-codec-COPYING.txt" in action
    assert "blue-marshal-COPYING.txt" not in action + spec, (
        "the per-crate licence file was replaced by the combined one; a "
        "surviving reference names a file nothing generates any more"
    )


def test_the_notices_name_the_pinned_codec_dependency():
    cargo = (ROOT / "packaging" / "settings-codec" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert 'blue-marshal = "=1.0.1"' in cargo
    assert "blue-marshal and its dependencies" in notices
    assert "Version: 1.0.1" in notices


def test_the_notices_list_every_crate_the_codec_links():
    """The codec is statically linked, so MIT's notice condition covers the
    whole dependency closure and not just blue-marshal. The list is derived
    from Cargo.lock rather than retyped: a `cargo update` that adds or drops
    a crate would otherwise leave the notices quietly wrong, which is the
    one failure mode here that nothing at runtime can reveal.
    """
    lock = (ROOT / "packaging" / "settings-codec" / "Cargo.lock").read_text(
        encoding="utf-8"
    )
    linked = set(re.findall(r'^name = "([^"]+)"', lock, re.MULTILINE))
    linked.discard("wingman-settings-codec")  # our own crate, GPL with the app
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    named = set(re.findall(r"[A-Za-z0-9_-]+", notices))
    assert linked <= named, (
        "THIRD-PARTY-NOTICES.md does not name every crate linked into "
        f"wingman-settings-codec.exe: {sorted(linked - named)}"
    )


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
def test_the_built_codec_round_trips_large_floats_exactly():
    doc = {
        "had_crc": False,
        "doc": {
            "bytes:ui": {
                "bytes:plex_value": {
                    "tuple": ["long:134251880277573607", 93668995514.40001]
                }
            }
        },
    }
    encoded = subprocess.run(
        [str(CODEC), "encode"], input=json.dumps(doc).encode(), capture_output=True
    )
    assert encoded.returncode == 0, encoded.stderr
    assert encoded.stdout[:1] == b"\x7d"
    decoded = subprocess.run(
        [str(CODEC), "decode"], input=encoded.stdout, capture_output=True
    )
    assert decoded.returncode == 0, decoded.stderr
    assert json.loads(decoded.stdout) == doc


def test_the_installer_fightrecorder_feature_is_wired():
    """The FightRecorder task, its bundled DLL and its install-time code
    must all be present in installer.iss. Any one going missing has a
    specific symptom: no task (feature gone), no [Files] entry (iscc
    fails at compile), no code (a checkbox that does nothing)."""
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert 'Name: "fightrecorder"' in iss
    assert r'Source: "bin\obs-fightrecorder.dll"; Flags: dontcopy noencryption' in iss
    assert "procedure InstallFightRecorder();" in iss
    assert "WizardIsTaskSelected('fightrecorder')" in iss


def _load_manual_update_harness():
    spec = importlib.util.spec_from_file_location(
        "manual_update_harness", MANUAL_UPDATE_HARNESS
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_update_harness_is_not_packaged():
    spec = (ROOT / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert "tests/manual" not in spec
    assert MANUAL_UPDATE_HARNESS.is_file() and MANUAL_UPDATE_FIXTURE.is_file()


def test_manual_preview_crop_harness_is_not_packaged():
    """The crop probe is three checkout-only files, not one: the harness
    loads the model and the window controllers as siblings by path, so a
    build that shipped any of them would ship a prototype that opens
    always-on-top windows against live EVE clients. The lexical guard is
    kept for the same reason the updater harness keeps it -- `tests/manual`
    appearing anywhere in the spec is the only way any of them could be
    collected.
    """
    spec = (ROOT / "packaging" / "uploader.spec").read_text(encoding="utf-8")
    assert "tests/manual" not in spec
    assert MANUAL_PREVIEW_CROP_HARNESS.is_file()
    assert MANUAL_PREVIEW_CROP_MODEL.is_file()
    assert MANUAL_PREVIEW_CROP_WINDOWS.is_file()


@pytest.mark.parametrize(
    "name", ["crops", "cropstore", "cropwindow", "croppicker", "cropcontroller"]
)
def test_production_crops_import_as_modules_of_the_declared_preview_package(name):
    with (ROOT / "pyproject.toml").open("rb") as fh:
        packages = tomllib.load(fh)["tool"]["setuptools"]["packages"]
    assert "wingman.preview" in packages
    fullname = "wingman.preview." + name
    module = importlib.import_module(fullname)
    assert pathlib.Path(module.__file__).resolve() == ROOT / "wingman" / "preview" / (
        name + ".py"
    )
    assert fullname not in packages  # Modules, not a new subpackage.


def test_no_shipped_module_imports_the_crop_probe():
    """Packaging exclusion is only half of it: a `wingman/` module that
    imported the probe would drag it into the frozen build through
    PyInstaller's own dependency analysis, spec exclusion or not."""
    # Match the actual probe modules, not semantic bridge endpoints such as
    # get_preview_crop_state, which share the feature's vocabulary.
    probes = "|".join(
        re.escape(path.stem)
        for path in (
            MANUAL_PREVIEW_CROP_HARNESS,
            MANUAL_PREVIEW_CROP_MODEL,
            MANUAL_PREVIEW_CROP_WINDOWS,
        )
    )
    offenders = [
        path.relative_to(ROOT)
        for path in (ROOT / "wingman").rglob("*.py")
        if re.search(probes, path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    ("mode", "failure_code"),
    [
        ("complete", None),
        ("truncated", "size"),
        ("checksum-mismatch", "checksum"),
    ],
)
def test_manual_update_harness_serve_modes_run_without_native_dependencies(
    mode, failure_code
):
    result = subprocess.run(
        [sys.executable, str(MANUAL_UPDATE_HARNESS), "serve", "--mode", mode],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "temporary staging root removed: yes" in result.stdout
    staging_line = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("temporary staging root: ")
    )
    assert not pathlib.Path(
        staging_line.removeprefix("temporary staging root: ")
    ).exists()

    if failure_code is None:
        assert "size: 36" in result.stdout
        assert (
            "sha256: 00bf96a604486a01f524855947924d49b14deced0ca87bc90143e0034bf91434"
            in result.stdout
        )
        assert "handoff marker created: update-" in result.stdout
        assert "handoff marker removed: True" in result.stdout
        assert "expected failure:" not in result.stdout
        assert "partial retention:" not in result.stdout
    else:
        assert f"expected failure: stage=download code={failure_code}" in result.stdout
        assert "partial retention: none" in result.stdout
        assert "downloaded:" not in result.stdout


def test_manual_update_harness_rejects_non_fixture_basenames():
    harness = _load_manual_update_harness()
    with pytest.raises(RuntimeError, match="must name the harmless"):
        harness._require_fixture(ROOT / "FlyGD-Wingman-Setup-4.9.0.exe")


def test_manual_update_harness_rejects_fixture_named_symlinks(tmp_path):
    harness = _load_manual_update_harness()
    target = tmp_path / "harmless-target.exe"
    target.write_bytes(b"not an installer")
    link = tmp_path / "Wingman-Update-Harness-Setup.exe"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(RuntimeError, match="symlinks are refused"):
        harness._require_fixture(link)


def test_manual_update_fixture_is_inert_and_separate_from_production():
    text = MANUAL_UPDATE_FIXTURE.read_text(encoding="utf-8")
    sections = re.findall(r"^\[([^]]+)]$", text, re.MULTILINE)
    setup_text = text.split("[Setup]\n", 1)[1].split("\n[", 1)[0]
    setup = dict(
        line.split("=", 1)
        for line in setup_text.splitlines()
        if line and not line.startswith(";")
    )

    assert sections == ["Setup"]
    assert setup == {
        "AppId": "FlyGD Wingman Update Harness",
        "AppName": "FlyGD Wingman Update Harness",
        "AppVersion": "1.0.0",
        "DefaultDirName": r"{tmp}\FlyGD-Wingman-Update-Harness",
        "PrivilegesRequired": "lowest",
        "Uninstallable": "no",
        "AppMutex": r"Local\FlyGDWingmanUpdateHarness",
        "OutputBaseFilename": "Wingman-Update-Harness-Setup",
    }
    for production_identity in (
        "Wingman.exe",
        r"{autopf}\FlyGD Wingman",
        r"Global\OBSYouTubeUploader",
        r"Global\FlyGDWingman",
        "FlyGD-Wingman-Setup-{#AppVersion}",
    ):
        assert production_identity not in text


def _os_error_with_winerror(code):
    error = OSError(code, f"Windows error {code}")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32])
def test_manual_update_harness_accepts_only_known_replacement_denials(code):
    harness = _load_manual_update_harness()

    assert (
        harness._replacement_denial_code({"error": _os_error_with_winerror(code)})
        == code
    )


def test_manual_update_harness_rejects_other_replacement_errors():
    harness = _load_manual_update_harness()

    with pytest.raises(RuntimeError, match=r"unexpected error code 87"):
        harness._replacement_denial_code({"error": _os_error_with_winerror(87)})


def test_manual_update_harness_rejects_successful_replacement():
    harness = _load_manual_update_harness()

    with pytest.raises(RuntimeError, match="replacement unexpectedly succeeded"):
        harness._replacement_denial_code({"replaced": True})


def test_manual_update_harness_reports_replacement_barrier_timeout():
    harness = _load_manual_update_harness()

    with pytest.raises(RuntimeError, match="timed out waiting for the barrier"):
        harness._replacement_denial_code({"timed_out": True})


@pytest.mark.parametrize(
    ("during", "after"),
    [
        (("changed-identity", 10), ("original-identity", 10, "original-digest")),
        (("original-identity", 11), ("original-identity", 10, "original-digest")),
        (("original-identity", 10), ("original-identity", 10, "changed-digest")),
    ],
)
def test_manual_update_harness_rejects_mutated_lock_race_facts(during, after):
    harness = _load_manual_update_harness()
    before = ("original-identity", 10, "original-digest")

    with pytest.raises(RuntimeError, match="identity, size, or digest changed"):
        harness._require_unchanged_file_facts(before, during, after)


def test_manual_update_harness_pins_its_deliberate_production_seams():
    tree = ast.parse(MANUAL_UPDATE_HARNESS.read_text(encoding="utf-8"))
    referenced = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "updates"
    }

    # _open_locked is deliberately included: the harness must exercise the
    # same protected-handle implementation as launch verification, not a
    # friendlier test-only file reader.
    assert referenced == {
        "ReleaseInfo",
        "UpdateFailure",
        "_open_locked",
        "close_process_handle",
        "download_release",
        "launch_verified",
        "remove_handoff_marker",
        "save_attachment",
        "validate_download_origin",
        "write_handoff_marker",
    }


@pytest.mark.parametrize(
    ("argv", "command"),
    [
        (["serve", "--mode", "complete"], "serve"),
        (
            [
                "attachment",
                "--i-understand-this-launches-a-test-exe",
                "fixture.exe",
                "https://example.test/fixture.exe",
            ],
            "attachment",
        ),
        (
            [
                "lock-race",
                "--i-understand-this-launches-a-test-exe",
                "fixture.exe",
            ],
            "lock-race",
        ),
        (
            [
                "shell-launch",
                "--i-understand-this-launches-a-test-exe",
                "fixture.exe",
                "https://example.test/fixture.exe",
            ],
            "shell-launch",
        ),
        (["mutex-holder"], "mutex-holder"),
    ],
)
def test_manual_update_harness_parser_exposes_every_command(argv, command):
    harness = _load_manual_update_harness()
    assert harness.build_parser().parse_args(argv).command == command


@pytest.mark.parametrize(
    "argv",
    [
        ["attachment", "fixture.exe", "https://example.test/fixture.exe"],
        ["lock-race", "fixture.exe"],
        ["shell-launch", "fixture.exe", "https://example.test/fixture.exe"],
    ],
)
def test_manual_update_harness_dangerous_commands_require_opt_in(argv):
    harness = _load_manual_update_harness()
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(argv)


def test_manual_update_harness_rejects_an_abbreviated_opt_in():
    harness = _load_manual_update_harness()
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(
            [
                "attachment",
                "--i-understand-this-launches",
                "fixture.exe",
                "https://example.test/fixture.exe",
            ]
        )


def test_the_fightrecorder_fetcher_is_on_the_ci_allowlist():
    """ci.yml refuses bare `python` invocations in the build action
    except for the stdlib-only fetch scripts. A new fetcher not on the
    list turns every push red with a bypass error; this pins the
    allowlist entry so removing the fetcher from the action is a
    deliberate act."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fetch_fightrecorder" in ci
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "packaging/fetch_fightrecorder.py" in action


def test_shared_eve_authority_and_fittings_are_explicit_packages():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        declared = set(tomllib.load(handle)["tool"]["setuptools"]["packages"])
    assert {"wingman.eveauth", "wingman.evefittings"} <= declared


def test_fleetsharing_is_an_explicit_package():
    """wingman.fleetsharing added no web tree or frozen-build wiring of its
    own (it is pure protocol boundary code, imported by no coordinator or
    UI yet), so it needs only the same declared-package guarantee every
    other subpackage gets from test_every_subpackage_is_declared -- pinned
    explicitly here the same way eveauth/evefittings are above, rather than
    relying solely on that generic scan.
    """
    with (ROOT / "pyproject.toml").open("rb") as handle:
        declared = set(tomllib.load(handle)["tool"]["setuptools"]["packages"])
    assert "wingman.fleetsharing" in declared
    assert (ROOT / "wingman" / "fleetsharing" / "__init__.py").is_file()


def test_the_build_verifies_every_eve_capability_controller_is_importable():
    """Mirrors the existing SkillsController assertion below it in the
    action, for the two packages the character-fittings feature added.

    `wingman.eveauth` and `wingman.evefittings` are plain package imports
    with no `hiddenimports` entry, exactly like `wingman.eveskills` --
    PyInstaller does not fail the build over a missing one, and a broken
    import would otherwise surface only once the affected route opens in
    the frozen app, not here where the failure is actionable.
    """
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "from wingman.eveauth.controller import AuthorityController" in action
    assert "from wingman.evefittings.controller import FittingsController" in action
    assert "from wingman.eveskills.controller import SkillsController" in action


def test_the_build_verifies_fittings_and_characters_js_are_bundled():
    """Same silent-`datas`-failure shape as the other named web assets:
    the action already lists every script the page loads by name so a
    wrong path in uploader.spec cannot ship a build missing one of them
    silently. `fittings.js` and `characters.js` must be on that list
    alongside the scripts that were there before those sections existed.
    """
    action = (
        ROOT / ".github" / "actions" / "build-installer" / "action.yml"
    ).read_text(encoding="utf-8")
    web_check = action[action.index('$web = "dist\\Wingman\\_internal\\web"') :]
    web_check = web_check[: web_check.index("# The fonts fail QUIETLY")]
    assert "fittings.js" in web_check, (
        "the action's bundled-web-assets check does not name fittings.js -- "
        "a missing datas entry for it would ship a build with a blank "
        "Fittings route and no CI signal at all"
    )
    assert "characters.js" in web_check, (
        "the action's bundled-web-assets check does not name characters.js -- "
        "a missing datas entry for it would ship a build with an inert "
        "Characters Settings section and no CI signal at all"
    )
    for name in ("index.html", "style.css", "app.js", "skills.js"):
        assert name in web_check, name
    assert "Test-Path $path -PathType Leaf" in web_check, (
        "the bundled-web-assets check must prove each expected path is a file, "
        "not merely an existing directory"
    )
