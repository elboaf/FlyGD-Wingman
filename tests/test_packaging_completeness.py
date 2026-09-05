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
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL_UPDATE_FIXTURE = ROOT / "tests" / "manual" / "update_fixture.iss"
MANUAL_UPDATE_HARNESS = ROOT / "tests" / "manual" / "update_harness.py"


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
    assert "only the Skills interaction" in flat


def test_readme_eve_authorization_docs_point_to_settings_characters_and_current_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    flat = " ".join(readme.split())
    assert (
        "Settings → Characters is the only place to authorize, reconnect, or "
        "forget EVE characters." in flat
    )
    for scope in (
        "esi-characters.read_skills.v1",
        "esi-skills.read_skillqueue.v1",
        "esi-fittings.read_fittings.v1",
        "esi-fittings.write_fittings.v1",
    ):
        assert scope in readme
    for phrase in (
        "Existing Skills-only consent remains valid for Skills.",
        "Wingman matches the character EVE returns against the sign-in that started the flow, not against a specific scope combination.",
        "If Wingman already knows that character's owner and EVE returns a different one, the sign-in is refused.",
        "If no owner is saved yet, the returned owner is accepted for compatibility with older Skills-only records.",
        "If you cancel before EVE replies, the cancellation wins.",
        "If EVE replies first, that reply wins and the later cancel is ignored.",
        "If cleanup is only partly saved, Wingman keeps the character blocked from being added again until reconciliation proves what survived.",
    ):
        assert phrase in flat
    for removed in (
        "Enable fittings",
        "Whether pressed from Skills or Fittings",
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
        "partial cleanup removes the row but leaves the add blocked until reconciliation proves what survived"
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

    path = ROOT / "scripts" / "shoot_screens.py"
    spec = importlib.util.spec_from_file_location("shoot_screens", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    prompt = (ROOT / ".pi" / "prompts" / "screenshots.md").read_text(encoding="utf-8")
    flat_prompt = " ".join(prompt.split())
    assert f"walks **{len(module.SCREENS)} screens**" in flat_prompt
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
