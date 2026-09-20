"""Exercise package-relative loading without source cwd or editable imports."""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "wingman/data/fleet-combat-v2-profile.json"


def _git(repository, *arguments):
    # cwd alone cannot contain Git when inherited routing/config overrides it.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=environment,
        capture_output=True,
        check=True,
        timeout=15,
    )


def test_git_runner_ignores_inherited_repository_and_config(monkeypatch, tmp_path):
    # Setup must be independent of the runner under test. All poison targets a
    # disposable caller, never this worktree or an inherited Git directory.
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }

    def setup_git(repository, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            env=clean_env,
            capture_output=True,
            check=True,
            timeout=15,
        )

    caller, target = tmp_path / "caller", tmp_path / "target"
    for repository in (caller, target):
        repository.mkdir()
        setup_git(repository, "init", "--quiet")
        (repository / "probe.txt").write_bytes(b"original\n")
        setup_git(repository, "add", "--", "probe.txt")
    saved = {
        name: (caller / ".git" / name).read_bytes() for name in ("config", "index")
    }
    (caller / "probe.txt").write_bytes(b"caller change\n")
    (target / "probe.txt").write_bytes(b"target change\n")
    poisoned = {
        "GIT_DIR": str(caller / ".git"),
        "GIT_COMMON_DIR": str(caller / ".git"),
        "GIT_WORK_TREE": str(caller),
        "GIT_INDEX_FILE": str(caller / ".git/index"),
        "GIT_OBJECT_DIRECTORY": str(caller / ".git/objects"),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "polish.injected",
        "GIT_CONFIG_VALUE_0": "poison",
    }
    with monkeypatch.context() as patch:
        for key in list(os.environ):
            if key.upper().startswith("GIT_"):
                patch.delenv(key)
        for key, value in poisoned.items():
            patch.setenv(key, value)
        _git(target, "config", "--local", "polish.marker", "target")
        _git(target, "add", "--", "probe.txt")
        configuration = _git(target, "config", "--list").stdout
    # Restore the ordinary test environment before assertions/failure reporting.
    assert {name: (caller / ".git" / name).read_bytes() for name in saved} == saved
    assert b"polish.injected=poison" not in configuration
    assert (
        setup_git(target, "config", "--local", "--get", "polish.marker").stdout.strip()
        == b"target"
    )
    assert setup_git(target, "show", ":probe.txt").stdout == b"target change\n"


@pytest.mark.parametrize(
    "relative",
    [
        "docs/fleet-combat-v2-profile.json",
        "wingman/data/fleet-combat-v2-profile.json",
        "tests/fixtures/fleet-combat-v2.json",
    ],
)
def test_combat_bytes_survive_autocrlf_checkout(tmp_path, relative):
    # Never change the developer's checkout/index/config. No commit is needed
    # to exercise Git's real index-to-working-tree conversion in this repo.
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "--local", "core.autocrlf", "true")
    shutil.copyfile(ROOT / ".gitattributes", tmp_path / ".gitattributes")
    original = (ROOT / relative).read_bytes()
    destination = tmp_path / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(original)
    control = tmp_path / "unprotected.json"
    control.write_bytes(b'{"control":true}\n')
    _git(tmp_path, "add", "--", ".gitattributes", relative, control.name)
    destination.unlink()
    control.unlink()
    _git(tmp_path, "checkout-index", "--all", "--force")
    # Prove conversion was actually enabled, and protection is not all JSON.
    assert control.read_bytes() == b'{"control":true}\r\n'
    assert (
        hashlib.sha256(destination.read_bytes()).hexdigest()
        == hashlib.sha256(original).hexdigest()
    )


def _frozen_datas():
    tree = ast.parse((ROOT / "packaging/uploader.spec").read_text(encoding="utf-8"))
    analysis = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Analysis"
    )
    datas = next(item.value for item in analysis.keywords if item.arg == "datas")
    # Evaluate the spec's real data expression, without building Windows binaries.
    return eval(
        compile(ast.Expression(datas), "uploader.spec:datas", "eval"),
        {
            "ROOT": ROOT,
            "BIN": ROOT / "packaging/bin",
            "WEB": ROOT / "wingman/web",
            "ICON": ROOT / "wingman/assets/app.ico",
        },
    )


def test_wheel_manifest_collects_the_exact_profile():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = config["tool"]["setuptools"]["package-data"]["wingman"]
    collected = {
        path for pattern in patterns for path in (ROOT / "wingman").glob(pattern)
    }
    assert RESOURCE in collected


def test_frozen_spec_collects_the_profile_at_its_package_relative_path():
    assert (str(RESOURCE), "wingman/data") in _frozen_datas()


@pytest.mark.parametrize("frozen", [False, True], ids=["installed", "frozen-layout"])
def test_profile_loads_outside_the_source_tree(tmp_path, frozen):
    library = tmp_path / ("_internal" if frozen else "site-packages")
    package = library / "wingman"
    package.mkdir(parents=True)
    for filename in ("__init__.py", "combatprofile.py"):
        shutil.copyfile(ROOT / "wingman" / filename, package / filename)
    if frozen:
        # Copy through the actual spec destination, so a path mismatch fails.
        destinations = [dest for src, dest in _frozen_datas() if Path(src) == RESOURCE]
        assert len(destinations) == 1
        destination = library / destinations[0]
    else:
        destination = package / "data"
    destination.mkdir(parents=True)
    shutil.copyfile(RESOURCE, destination / RESOURCE.name)
    code = "\n".join(
        [
            "import json, sys",
            f"sys.path.insert(0, {str(library)!r})",
            f"sys.frozen = {frozen!r}",
            f"sys._MEIPASS = {str(library)!r}",
            "from wingman.combatprofile import normalize_observed_name, observed_name_key",
            r"print(json.dumps([normalize_observed_name(' e\u0301 '), observed_name_key('Stra\u00dfe')]))",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) == ["\u00e9", "strasse"]
    # A broken installation must fail with its missing resource path, not fall
    # back to docs/, a different checkout or a host Unicode implementation.
    (destination / RESOURCE.name).unlink()
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr
    assert repr(str(destination / RESOURCE.name)) in result.stderr
