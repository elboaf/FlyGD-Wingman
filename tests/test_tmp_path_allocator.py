"""Exercise the suite's tmp_path override through real, isolated pytest sessions.

Children load the actual conftest, not a second implementation of its fixtures.
Only the vanilla differential arm unregisters the override. Observation files
live outside basetemp so pytest's real cleanup cannot erase the evidence.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFTEST = Path(__file__).with_name("conftest.py")

_OBSERVE = """
import json
from pathlib import Path

OBS = {"paths": {}, "reports": []}

@pytest.fixture(autouse=True)
def allocator_observe(tmp_path, request):
    OBS["paths"][request.node.name] = str(tmp_path)
    (tmp_path / "allocated").write_text(request.node.name, encoding="utf-8")

@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    OBS["reports"].append([item.name, report.when, report.outcome])
    return report

@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    OBS["base"] = str(session.config._tmp_path_factory.getbasetemp())
    Path(__file__).with_name("observed.json").write_text(
        json.dumps(OBS), encoding="utf-8"
    )
"""


def _child(
    root,
    source,
    *,
    plugin="",
    adapted=True,
    policy="all",
    count=3,
    temproot=None,
):
    root.mkdir(parents=True)
    conftest = CONFTEST.read_text(encoding="utf-8")
    if not adapted:
        conftest += '\nglobals().pop("tmp_path", None)\n'
    (root / "conftest.py").write_text(conftest + _OBSERVE + plugin, encoding="utf-8")
    (root / "test_cases.py").write_text(source, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-ra",
        "-c",
        str(root / "pytest.ini"),
        "--confcutdir",
        str(root),
        "-o",
        f"tmp_path_retention_policy={policy}",
        "-o",
        f"tmp_path_retention_count={count}",
    ]
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_ADDOPTS": "",
    }
    if temproot is None:
        command += ["--basetemp", str(root / "temp")]
    else:
        temproot.mkdir(parents=True, exist_ok=True)
        environment["PYTEST_DEBUG_TEMPROOT"] = str(temproot)
    result = subprocess.run(
        command, cwd=root, env=environment, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    (root / "pytest.log").write_text(output, encoding="utf-8")
    assert (root / "observed.json").is_file(), output
    observed = json.loads((root / "observed.json").read_text(encoding="utf-8"))
    return result.returncode, observed, output


_IDENTITY_AND_SCANS = """
import os

SCANS = []
BUILTIN_PATHS = []
FACTORY = None
ORIGINAL = None

@pytest.fixture(scope="session", autouse=True)
def early_factory(tmp_path_factory, request):
    global FACTORY, ORIGINAL
    FACTORY = tmp_path_factory
    ORIGINAL = FACTORY.mktemp
    assert "mktemp" not in vars(FACTORY)
    assert FACTORY is request.config._tmp_path_factory
    assert FACTORY.mktemp("ordinary").name == "ordinary0"
    assert FACTORY.mktemp("ordinary").name == "ordinary1"
    assert FACTORY.mktemp("early-exact", numbered=False).name == "early-exact"
    real_scandir = os.scandir
    base = FACTORY.getbasetemp()

    def observe_scandir(path):
        if path == base:
            SCANS.append(str(path))
        return real_scandir(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "scandir", observe_scandir)
        yield
    assert "mktemp" not in vars(FACTORY)
    assert FACTORY.mktemp == ORIGINAL

@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef, request):
    builtin = (fixturedef.argname == "tmp_path"
               and fixturedef.func.__module__ == "_pytest.tmpdir")
    if builtin:
        # This call occurs inside the adapter window, not just after restoration.
        name = "exact-" + str(len(BUILTIN_PATHS))
        exact = FACTORY.mktemp(name, numbered=False)
        assert exact.name == name
        with pytest.raises(FileExistsError):
            FACTORY.mktemp(name, numbered=False)
    value = yield
    if builtin:
        BUILTIN_PATHS.append(value)
    return value
"""

_ISOLATION = """
import os
import re
from pathlib import Path
import pytest
import conftest as c
from wingman import paths

SEEN = set()

@pytest.mark.parametrize("value", ["same/a", "same?a", "same" * 30, "é" * 30])
def test_é_colliding_long_prefix_cases(tmp_path, request, tmp_path_factory, value):
    assert c.SCANS == [], "per-case numbered scan returned"
    assert tmp_path is c.BUILTIN_PATHS[-1]
    assert request.getfixturevalue("tmp_path") is tmp_path
    assert request.getfixturevalue("tmp_path") is tmp_path
    assert tmp_path not in SEEN
    SEEN.add(tmp_path)
    assert re.fullmatch(r"[A-Za-z0-9_]{1,14}-[0-9a-f]{16}", tmp_path.name)
    assert len(tmp_path.name) <= 31
    assert Path(os.environ["LOCALAPPDATA"]) == tmp_path / "state"
    assert paths.state_dir() == tmp_path / "state" / "FlyGD Wingman"
    paths.ensure_dirs()
    assert not paths.settings_file().exists()
    paths.settings_file().write_text(value, encoding="utf-8")
    deep = paths.tmp_dir() / "EVE" / "c_program_files_ccp_eve_tranquility" / "settings_Default"
    deep.mkdir(parents=True)
    target = deep / "core_char_123456789.dat"
    target.write_bytes(b"private case state")
    assert target.read_bytes() == b"private case state"
    c.OBS["deep_path_length"] = len(str(target))
    assert tmp_path_factory is c.FACTORY is request.config._tmp_path_factory
    assert "mktemp" not in vars(tmp_path_factory), "adapter left a shadowing instance method"
    assert tmp_path_factory.mktemp == c.ORIGINAL
    assert tmp_path_factory.mktemp("ordinary").name == "ordinary" + str(len(SEEN) + 1)
    assert len(c.SCANS) == 1, "spy must see ordinary numbered factory scans"
    c.SCANS.clear()
    paths._use_legacy = True


def test_without_explicit_tmp_path():
    assert c.SCANS == []
    state = Path(os.environ["LOCALAPPDATA"])
    assert state.parent not in SEEN
    assert state == c.BUILTIN_PATHS[-1] / "state"
    assert not paths._use_legacy
    assert not paths.settings_file().exists()
    assert len(SEEN) == 4


def test_direct_factory_guards(tmp_path_factory):
    assert c.SCANS == []
    assert "mktemp" not in vars(tmp_path_factory)
    assert tmp_path_factory.mktemp == c.ORIGINAL
    with pytest.raises(FileExistsError):
        tmp_path_factory.mktemp("early-exact", numbered=False)
    assert tmp_path_factory.mktemp("after-exact", numbered=False).name == "after-exact"
    base = tmp_path_factory.getbasetemp()
    outside = base.parent / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("untouched", encoding="utf-8")
    for name in ("../escaped", str(outside / "absolute")):
        for numbered in (False, True):
            with pytest.raises(ValueError, match="relative path"):
                tmp_path_factory.mktemp(name, numbered=numbered)
    link = base / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        # Stock Windows may lack symlink privilege; still exercise its real
        # reparse-point containment via a junction, without skipping the case.
        assert os.name == "nt" and error.winerror == 1314
        import subprocess
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        c.OBS["link_kind"] = "junction (symlink privilege unavailable)"
    else:
        c.OBS["link_kind"] = "symlink"
    try:
        for numbered in (False, True):
            with pytest.raises(ValueError, match="relative path"):
                tmp_path_factory.mktemp("link", numbered=numbered)
    finally:
        if link.is_symlink():
            link.unlink()
        else:
            link.rmdir()
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert list(outside.iterdir()) == [sentinel]
    assert c.SCANS == []
"""


def test_case_allocation_avoids_scans_without_changing_factory_or_isolation(tmp_path):
    code, observed, output = _child(
        tmp_path / "child", _ISOLATION, plugin=_IDENTITY_AND_SCANS
    )
    assert code == 0, output
    assert len(set(observed["paths"].values())) == 6
    print("direct factory containment:", observed["link_kind"])
    print("deep state file path length:", observed["deep_path_length"])


_FAILURES = """
import secrets

@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    factory = item.config._tmp_path_factory
    assert "mktemp" not in vars(factory)
    original = factory.mktemp
    base = factory.getbasetemp()
    name = item.name
    attempts, tokens, mkdirs = [], [], []
    permission = PermissionError("allocator permission boundary")
    real_mkdir = Path.mkdir

    def token_hex(size):
        assert size == 8
        tokens.append(size)
        assert len(tokens) <= 10, "unbounded collision retry"
        if name == "test_escape":
            return "/../../escape"
        if name == "test_collision" and len(tokens) > 1:
            return "1" * 16
        return "0" * 16

    def mktemp(basename, numbered=True):
        attempts.append([basename, numbered])
        return original(basename, numbered=numbered)

    def mkdir(path, mode=0o777, parents=False, exist_ok=False):
        if path.parent == base:
            mkdirs.append(path.name)
            assert mode == 0o700 and not parents and not exist_ok
            if name == "test_denied":
                raise permission
            if name in ("test_collision", "test_full") and len(mkdirs) == 1:
                # Occupy the candidate at the actual exclusive mkdir boundary.
                real_mkdir(path, mode=mode)
                (path / "sentinel").write_text("do not overwrite", encoding="utf-8")
        return real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(secrets, "token_hex", token_hex)
        patch.setitem(vars(factory), "mktemp", mktemp)
        patch.setattr(Path, "mkdir", mkdir)
        try:
            yield
        except (FileExistsError, PermissionError, ValueError) as error:
            OBS.setdefault("errors", {})[name] = [type(error).__name__, str(error)]
            if name == "test_denied":
                assert error is permission
            raise
        finally:
            assert vars(factory)["mktemp"] is mktemp, "prior instance override not restored"
            OBS.setdefault("attempts", {})[name] = attempts
            OBS.setdefault("tokens", {})[name] = len(tokens)
            OBS.setdefault("mkdirs", {})[name] = mkdirs
    assert "mktemp" not in vars(factory)
    assert factory.mktemp == original
"""


def test_collisions_are_exclusive_bounded_and_other_errors_propagate(tmp_path):
    source = """
import pytest

def test_collision(tmp_path):
    assert tmp_path.name == "test_collision-" + "1" * 16

def test_full():
    pytest.fail("exhaustion must fail fixture setup")

def test_denied():
    pytest.fail("permission failure must fail fixture setup")

def test_escape():
    pytest.fail("containment failure must fail fixture setup")

def test_recovered(tmp_path):
    assert tmp_path.is_dir()
"""
    code, observed, output = _child(tmp_path / "child", source, plugin=_FAILURES)
    assert code == 1, output
    assert "2 passed, 3 errors" in output, output
    assert observed["tokens"] == {
        "test_collision": 2,
        "test_full": 10,
        "test_denied": 1,
        "test_escape": 1,
        "test_recovered": 1,
    }
    errors = observed["errors"]
    assert errors["test_full"][0] == "FileExistsError"
    assert errors["test_denied"] == ["PermissionError", "allocator permission boundary"]
    assert errors["test_escape"][0] == "ValueError"
    assert "relative path" in errors["test_escape"][1]
    assert observed["mkdirs"]["test_escape"] == []
    for name, attempts in observed["attempts"].items():
        assert len(attempts) == observed["tokens"][name]
        assert all(numbered is False for _, numbered in attempts)
    base = Path(observed["base"])
    for name in ("test_collision", "test_full"):
        occupied = base / (name + "-" + "0" * 16)
        assert (occupied / "sentinel").read_text(encoding="utf-8") == "do not overwrite"
    assert not (base.parent / "escape").exists()


_OUTCOMES = """
import pytest

@pytest.fixture
def setup_fail(tmp_path):
    raise RuntimeError("after allocation in setup")

@pytest.fixture
def teardown_fail(tmp_path):
    yield
    raise RuntimeError("after allocation in teardown")

def test_pass(tmp_path):
    assert tmp_path.is_dir()

def test_call_fail(tmp_path):
    assert False, "intentional call failure"

def test_setup_fail(setup_fail):
    pass

def test_teardown_fail(teardown_fail):
    pass

def test_skip(tmp_path):
    pytest.skip("intentional post-allocation skip")
"""


def _retained(observed):
    return {
        name: (Path(path) / "allocated").exists()
        for name, path in observed["paths"].items()
    }


@pytest.mark.parametrize("policy", ["all", "failed", "none"])
def test_builtin_case_retention_matches_vanilla_for_every_outcome(tmp_path, policy):
    observations = []
    for adapted in (False, True):
        code, observed, output = _child(
            tmp_path / str(adapted), _OUTCOMES, adapted=adapted, policy=policy
        )
        assert code == 1, output
        assert "1 failed, 2 passed, 1 skipped, 2 errors" in output, output
        assert len(observed["paths"]) == 5
        observations.append(observed)
    vanilla, adapted = observations
    assert adapted["reports"] == vanilla["reports"]
    assert _retained(adapted) == _retained(vanilla)
    # pytest 9.1.1's failed policy uses call status, not overall test success.
    # Explicit basetemp bypasses session-root removal even for policy=none.
    expected = dict.fromkeys(vanilla["paths"], True)
    if policy == "failed":
        expected.update(
            test_pass=False, test_setup_fail=False, test_teardown_fail=False
        )
    assert _retained(adapted) == expected
    print("explicit basetemp", policy, expected)


@pytest.mark.parametrize(
    ("policy", "count", "expected"),
    [
        ("all", 2, [1, 2, 2]),
        ("all", 0, [0, 0, 0]),
        ("failed", 2, [0]),
        ("none", 2, [0]),
    ],
)
def test_builtin_session_retention_matches_vanilla(tmp_path, policy, count, expected):
    arms = []
    for adapted in (False, True):
        temproot = tmp_path / str(adapted) / "roots"
        history = []
        for index in range(len(expected)):
            code, observed, output = _child(
                tmp_path / str(adapted) / str(index),
                "def test_pass(tmp_path):\n    assert tmp_path.is_dir()\n",
                adapted=adapted,
                policy=policy,
                count=count,
                temproot=temproot,
            )
            assert code == 0, output
            # Ignore pytest-current links; count only actual retained sessions.
            roots = list(temproot.glob("pytest-of-*/pytest-*"))
            retained = sorted(
                path.name
                for path in roots
                if path.name.removeprefix("pytest-").isdigit() and path.is_dir()
            )
            history.append(retained)
            assert len(retained) == expected[index]
            if retained:
                assert Path(observed["base"]).name == retained[-1]
        arms.append(history)
    assert arms[0] == arms[1]
    print("default session root", policy, count, arms[1])
