# Setup Controller Fixture Construction Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace only the four brand-new initial DAT publications performed by the repeated setup-controller fixture with an exclusive fresh-file publisher, preserving codec verification, all 188 existing controller identities, every controller-body atomic persistence boundary, and all non-controller callers' atomic defaults.

**Architecture:** Add one private test-only `(Path, bytes) -> None` publisher in `tests/setup_fixtures.py` and expose it only through a keyword-only `seed_profile(..., initial_dat_publish=None)` seam whose `None` branch omits the codec `publish` override. Qualify parity, isolation, syscall shape, failure cleanup, separate direct/atomic fsync channels, and controller-body persistence in exactly two appended non-parameterized witnesses; only then opt the existing two-argument controller `setup` fixture into the fresh publisher for its source and recipient profiles.

**Tech Stack:** Python 3.11, pytest, stdlib `os`/`pathlib`/`stat`/`xml.etree.ElementTree`, the existing lossless and native settings codec paths, Node.js setup-page harness, Cargo settings codec, uv, Git, and GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`

## Global Constraints

- Source baseline is merged `main` commit `c23788e3` (`Consolidate generated verifier and Alerts tests (#287)`).
- Preserve all 188 existing `tests/test_ui_setup_controller.py` testcase identities byte-for-text and in their existing order.
- Add exactly two non-parameterized witness identities, appended after the existing collection so the ordered 188-ID baseline remains the exact prefix.
- The exact witness suffix, in order, is:
  1. `tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures`
  2. `tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence`
- Exactly the original 136 controller cases continue to consume the pytest `setup` fixture; neither new witness requests it.
- The structural claim is only `136 × 2 profiles × 2 DATs = 544` fixture-construction fsync calls removed.
- Make no Windows, Linux, suite, job, runner-efficiency, critical-path, or wall-clock speedup claim.
- `seed_profile()` remains atomic by default. `initial_dat_publish=None` means omit `publish=` and retain `codec.write_document()`'s existing definition-time default.
- Only the existing controller `setup(tmp_path, monkeypatch)` fixture opts reusable construction into the fresh publisher. Its signature and positional order do not change because `tests/fixtures/ui_setup_page.cjs` calls `setup.__wrapped__(Path(temp), patch)`.
- The two qualification witnesses may call the private helper, `seed_profile()`, or `setup.__wrapped__()` directly; no other existing reusable fixture or caller opts in.
- The fresh helper makes exactly one destination creation call: `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)`.
- The helper performs no existence/stat/access preflight, fsync, tempfile creation, replace, retry, hardlink, reflink, symlink, shared template, or session cache.
- The helper loops through legal partial writes, rejects zero progress, closes before success, removes a partial destination after write/close failure where possible, and re-raises the original failure object.
- Codec encode, signature validation, verifying decode, envelope equality, `had_crc`, and revision computation remain real for fast construction.
- Controller-body staging, rewritten DAT publication, final directory publication, and selection persistence remain production-strength and atomic.
- Temporary mutants are uncommitted, match-once, fail only at their intended witness assertion, and are restored exactly after every probe.
- Node and the built release settings codec are mandatory for full verification; availability skips are not acceptable evidence.
- Exact committed tranche scope is limited to:
  - `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`
  - `docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md`
  - `docs/ci-setup-controller-fixture-construction-results.md`
  - `tests/setup_fixtures.py`
  - `tests/test_ui_setup_controller.py`
- No file under `wingman/`, other test module, Node fixture, workflow, dependency, lockfile, packaging path, pytest configuration, marker, selector, budget, or shard manifest may be committed.
- Stop and return to design review if production changes, replacement support, a reusable opt-in outside the controller fixture, another test module, more than two identities, fixture signature changes, shared templates, or weakened controller persistence become necessary.

## File Structure and Ownership

- Create `docs/ci-setup-controller-fixture-construction-results.md` as the sole evidence ledger for baseline identities, structural fixture-use inventory, PR #287 artifact provenance, mutation outcomes, local verification, hosted comparison, scope, concerns, and self-review.
- Modify `tests/setup_fixtures.py` to own `_publish_fresh_file(path, data)` and the optional `seed_profile(..., initial_dat_publish=None)` seam. This file does not know about controllers or instrumentation.
- Modify `tests/test_ui_setup_controller.py` to import the fixture module itself, opt only `setup` into `_publish_fresh_file`, add test-local proxies/normalizers, and append the exact two witness tests.
- Read but do not commit changes to `wingman/evesettings/codec.py`, `setup_profile.py`, `profilecopy.py`, `controller.py`, `wingman/atomicio.py`, and `wingman/settings.py`; temporary mutation probes against `setup_profile.py` are restored before any commit.
- Keep `tests/test_ui_setup_schema.py`, `tests/test_ui_setup_profile.py`, `tests/test_ui_setup_integration.py`, `tests/test_evesettings_codec.py`, `tests/test_evesettings_profilecopy.py`, `tests/test_atomicio.py`, `tests/test_ui_setup_page.py`, and `tests/fixtures/ui_setup_page.cjs` unchanged; their default paths and direct wrapped-fixture call are acceptance evidence.

## Task Right-Sizing

1. Task 1 freezes source/artifact truth and creates the results ledger without accepting a helper or executable change.
2. Task 2 adds and independently qualifies the private publisher, optional seed seam, and comprehensive witness while every existing caller remains atomic.
3. Task 3 opts only the controller fixture into the helper and adds the independently reviewable controller-body persistence witness.
4. Task 4 proves the complete local endpoint, exact 188-prefix/2-suffix identity transformation, full-suite projection, skips, gates, scope, and mutation restoration.
5. Task 5 performs polish, whole-branch review, change explanation, an explicit publication stop, and—only after authorization—the hosted Windows/Ubuntu comparison against PR #287.

## Plan-Author Baseline Check

The plan author independently collected the current baseline and reparsed `/tmp/wingman-stage3-{windows,ubuntu}`. The observed authorities match the approved design: 188 controller identities, 136 structural users of fixture `setup`, 16,605 complete identities, 14 Ubuntu skips, 67 Windows skips, controller testcase sums 3.185s/42.301s, setup-user sums 2.964s/40.384s, and other-controller sums 0.221s/1.917s. Per the spec, this plan publishes no projected controller or full-suite node hash; implementation computes hashes from actual newline-terminated inventories.

---

## Reproducibility Blocks

### Block A — exact baseline identities, structural fixture users, and PR #287 artifacts

This block extracts `c23788e3` into a disposable checkout, uses a pytest collection plugin to identify `setup` consumers structurally through `item.fixturenames`, writes one complete node ID per line with a final newline, and reparses both hosted artifacts. It writes only under `/tmp`.

```bash
cat > /tmp/setup_fixture_inventory_plugin.py <<'PY'
from __future__ import annotations
import json, os
from pathlib import Path


def pytest_collection_finish(session):
    rows = [
        {"nodeid": item.nodeid, "uses_setup": "setup" in item.fixturenames}
        for item in session.items
    ]
    Path(os.environ["WINGMAN_COLLECTION_OUT"]).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
PY
cat > /tmp/setup_fixture_baseline.py <<'PY'
from __future__ import annotations
import hashlib, io, json, os, re, subprocess, tarfile, tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
P = W / '.venv/bin/python'
O = Path('/tmp/wingman-setup-fixture-baseline')
ARTIFACTS = {
    'ubuntu': Path('/tmp/wingman-stage3-ubuntu'),
    'windows': Path('/tmp/wingman-stage3-windows'),
}
CONTROLLER = 'tests/test_ui_setup_controller.py'


def sha(nodes):
    return hashlib.sha256(('\n'.join(nodes) + '\n').encode()).hexdigest()


def extract(commit, root):
    raw = subprocess.check_output(['git', '-C', str(W), 'archive', commit])
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        archive.extractall(root, filter='data')


def collect(root, args, name):
    output = O / name
    env = dict(os.environ, PYTHONPATH=f"{root}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [str(P), '-m', 'pytest', *args, '--collect-only', '-q',
         '-p', 'no:cacheprovider', '-p', 'setup_fixture_inventory_plugin'],
        cwd=root, env=env, text=True, capture_output=True, timeout=240,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    rows = json.loads(output.read_text(encoding='utf-8'))
    nodes = [row['nodeid'] for row in rows]
    assert len(nodes) == len(set(nodes))
    return rows


def identity(case):
    parts = case.get('classname').split('.')
    assert len(parts) >= 2 and parts[0] == 'tests', parts
    return '::'.join(('/'.join(parts[:2]) + '.py', *parts[2:], case.get('name')))


def normalized_skip(text):
    return re.sub(
        r'pytest-of-[^/\s]+/pytest-\d+/[^\s:\"\']+',
        'pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>',
        text.replace('\\', '/'),
    )


def artifact(root):
    cases = list(ET.parse(root / 'pytest-result.xml').getroot().iter('testcase'))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids))
    seconds = {node: float(case.get('time', '0') or 0)
               for node, case in zip(ids, cases, strict=True)}
    skips = []
    failures = errors = 0
    counts = defaultdict(int)
    sums = defaultdict(float)
    for node, case in zip(ids, cases, strict=True):
        file = node.split('::', 1)[0]
        counts[file] += 1
        sums[file] += seconds[node]
        skipped = case.find('skipped')
        if skipped is not None:
            skips.append((node, normalized_skip(skipped.get('message') or skipped.text or '')))
        failures += len(case.findall('failure'))
        errors += len(case.findall('error'))
    timing = json.loads((root / 'pytest-timing.json').read_text(encoding='utf-8'))
    assert timing['case_count'] == len(ids)
    for file, row in timing['files'].items():
        assert row['cases'] == counts[file]
        assert abs(row['seconds'] - sums[file]) < 1e-9
    return ids, seconds, skips, failures, errors

O.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='wingman-setup-baseline-') as directory:
    root = Path(directory)
    extract('c23788e3', root)
    controller_rows = collect(root, [CONTROLLER], 'controller-collection.json')
    complete_rows = collect(root, ['tests'], 'complete-collection.json')
controller = [row['nodeid'] for row in controller_rows]
setup_users = [row['nodeid'] for row in controller_rows if row['uses_setup']]
complete = [row['nodeid'] for row in complete_rows]
assert len(controller) == 188
assert len(setup_users) == 136
assert len(complete) == 16605
parsed = {platform: artifact(path) for platform, path in ARTIFACTS.items()}
ubuntu_ids, ubuntu_time, ubuntu_skips, uf, ue = parsed['ubuntu']
windows_ids, windows_time, windows_skips, wf, we = parsed['windows']
assert ubuntu_ids == complete
assert set(windows_ids) == set(complete)
assert uf == ue == wf == we == 0
assert len(ubuntu_skips) == 14 and len(windows_skips) == 67
assert [node for node in ubuntu_ids if node.startswith(CONTROLLER + '::')] == controller
assert [node for node in windows_ids if node.startswith(CONTROLLER + '::')] == controller
setup_set = set(setup_users)
for name, nodes in {
    'controller-188.txt': controller,
    'setup-users-136.txt': setup_users,
    'complete-16605.txt': complete,
}.items():
    (O / name).write_text('\n'.join(nodes) + '\n', encoding='utf-8')
for platform, skips in {'ubuntu': ubuntu_skips, 'windows': windows_skips}.items():
    (O / f'{platform}-skips.json').write_text(
        json.dumps(skips, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {
    'controller_count': len(controller),
    'controller_sha256': sha(controller),
    'setup_user_count': len(setup_users),
    'setup_user_sha256': sha(setup_users),
    'complete_count': len(complete),
    'complete_sha256': sha(complete),
    'ubuntu_controller_seconds': sum(ubuntu_time[node] for node in controller),
    'windows_controller_seconds': sum(windows_time[node] for node in controller),
    'ubuntu_setup_seconds': sum(ubuntu_time[node] for node in setup_users),
    'windows_setup_seconds': sum(windows_time[node] for node in setup_users),
    'ubuntu_other_seconds': sum(ubuntu_time[node] for node in controller if node not in setup_set),
    'windows_other_seconds': sum(windows_time[node] for node in controller if node not in setup_set),
    'ubuntu_skips': len(ubuntu_skips),
    'windows_skips': len(windows_skips),
}
(O / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/setup_fixture_inventory_plugin.py /tmp/setup_fixture_baseline.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
uv run --no-sync python /tmp/setup_fixture_baseline.py
```

Expected: exact counts 188, 136, and 16,605; Ubuntu/Windows complete identity sets equal; no controller skips; 14/67 platform skips; zero failures/errors; the timing observations in the approved spec; actual hashes written to `summary.json`, not predicted in this plan.

### Block B — exact mutants with byte/diff/status restoration

Every mutation is an exact unique replacement in this catalog. Before applying it, the runner captures the target bytes and SHA-256, the complete `git diff --binary HEAD -- .`, and NUL-delimited porcelain-v2 status. It runs pytest with `check=False`, validates an intended red assertion, and restores inside `finally`; shell `set -e` therefore cannot strand a mutation. Restoration requires byte equality, hash equality, binary-diff equality, and status equality with the pre-probe state. This is valid while implementation changes are uncommitted; `git diff --exit-code HEAD` is deliberately not used as the mutation oracle.

```bash
cat > /tmp/setup_fixture_mutation_probe.py <<'PY'
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
PYTEST = [str(W / '.venv/bin/python'), '-m', 'pytest']
COMPREHENSIVE = 'tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures'
BODY = 'tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence'
HELPER = '''def _publish_fresh_file(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Fresh fixture write made no progress.")
            remaining = remaining[written:]
        os.close(descriptor)
        descriptor = None
    except BaseException:
        if descriptor is not None:
            with contextlib.suppress(BaseException):
                os.close(descriptor)
        with contextlib.suppress(BaseException):
            os.unlink(path)
        raise
'''
MUTATIONS = {
    'remove-o-excl': {
        'target': 'tests/setup_fixtures.py',
        'before': '    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)\n',
        'after': '    flags = os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)\n',
        'node': COMPREHENSIVE,
        'expect': ('fresh open flags changed',),
    },
    'path-preflight': {
        'target': 'tests/setup_fixtures.py',
        'before': '    descriptor = os.open(path, flags, 0o600)\n',
        'after': '    if path.name == "success.dat":\n        path.exists()\n        path.stat()\n    descriptor = os.open(path, flags, 0o600)\n',
        'node': COMPREHENSIVE,
        'expect': ('fresh publisher called Path.exists',),
    },
    'direct-fsync': {
        'target': 'tests/setup_fixtures.py',
        'before': '            remaining = remaining[written:]\n        os.close(descriptor)\n',
        'after': '            remaining = remaining[written:]\n        os.fsync(descriptor)\n        os.close(descriptor)\n',
        'node': COMPREHENSIVE,
        'expect': ('fast direct fsync count changed',),
    },
    'atomic-delegation': {
        'target': 'tests/setup_fixtures.py',
        'before': HELPER,
        'after': '''def _publish_fresh_file(path: Path, data: bytes) -> None:
    codec.atomicio.write_bytes_atomic(path, data)
''',
        'node': COMPREHENSIVE,
        'expect': ('fast atomic fsync count changed',),
    },
    'extra-byte': {
        'target': 'tests/setup_fixtures.py',
        'before': '        remaining = memoryview(data)\n',
        'after': '        remaining = memoryview(data + b" ")\n',
        'node': COMPREHENSIVE,
        'expect': ('source byte inventory differs',),
    },
    'mapping-order': {
        'target': 'tests/setup_fixtures.py',
        'before': '    account, character = documents(case)\n    root = tmp_path / "EVE"\n',
        'after': '''    account, character = documents(case)
    if initial_dat_publish is not None:
        rows = account.doc["bytes:overview"]["bytes:tabsettings_new"]["tuple"][1]
        account.doc["bytes:overview"]["bytes:tabsettings_new"]["tuple"][1] = dict(
            reversed(tuple(rows.items()))
        )
    root = tmp_path / "EVE"
''',
        'node': COMPREHENSIVE,
        'expect': ('source byte inventory differs',),
    },
    'line-endings': {
        'target': 'tests/setup_fixtures.py',
        'before': '''    else:
        yaml_bytes = b"# synthetic recipient local preferences\\r\\nuiScale: 1.25\\r\\n"
        ini_bytes = b"; synthetic recipient local preferences\\r\\nmonitor=2\\r\\n"
    (profile / "core_public__.yaml").write_bytes(yaml_bytes)
''',
        'after': '''    else:
        yaml_bytes = b"# synthetic recipient local preferences\\r\\nuiScale: 1.25\\r\\n"
        ini_bytes = b"; synthetic recipient local preferences\\r\\nmonitor=2\\r\\n"
        if initial_dat_publish is not None:
            yaml_bytes = yaml_bytes.replace(b"\\r\\n", b"\\n")
            ini_bytes = ini_bytes.replace(b"\\r\\n", b"\\n")
    (profile / "core_public__.yaml").write_bytes(yaml_bytes)
''',
        'node': COMPREHENSIVE,
        'expect': ('recipient byte inventory differs',),
    },
    'hardlink-template': {
        'target': 'tests/setup_fixtures.py',
        'before': HELPER,
        'after': '''_FRESH_FILE_TEMPLATES = {}


def _publish_fresh_file(path: Path, data: bytes) -> None:
    template = _FRESH_FILE_TEMPLATES.get(data)
    if template is not None:
        os.link(template, path)
        return
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Fresh fixture write made no progress.")
            remaining = remaining[written:]
        os.close(descriptor)
        descriptor = None
    except BaseException:
        if descriptor is not None:
            with contextlib.suppress(BaseException):
                os.close(descriptor)
        with contextlib.suppress(BaseException):
            os.unlink(path)
        raise
    _FRESH_FILE_TEMPLATES[data] = path
''',
        'node': COMPREHENSIVE,
        'expect': ('fast-a link count changed',),
    },
    'direct-body-write': {
        'target': 'wingman/evesettings/setup_profile.py',
        'before': '''        written_account_revision = codec.write_document(
            staged_account_path,
            updated_account,
            backup=lambda _path: None,
            expected_content_revision=account_revision,
        )
''',
        'after': '''        written_account_revision = codec.write_document(
            staged_account_path,
            updated_account,
            backup=lambda _path: None,
            publish=lambda path, data: Path(path).write_bytes(data),
            expected_content_revision=account_revision,
        )
''',
        'node': BODY,
        'expect': ('body fsync categories changed',),
    },
}


def git_bytes(*args):
    return subprocess.check_output(['git', '-C', str(W), *args])


def run(name):
    row = MUTATIONS[name]
    target = W / row['target']
    original = target.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    before_diff = git_bytes('diff', '--binary', 'HEAD', '--', '.')
    before_status = git_bytes('status', '--porcelain=v2', '--untracked-files=all', '-z')
    before = row['before'].encode()
    after = row['after'].encode()
    assert original.count(before) == 1, (name, 'before_count', original.count(before))
    assert original.count(after) == 0, (name, 'after_already_present')
    output = b''
    problem = None
    try:
        target.write_bytes(original.replace(before, after, 1))
        changed = target.read_bytes()
        assert changed.count(after) == 1, (name, 'after_count', changed.count(after))
        result = subprocess.run(
            [*PYTEST, row['node'], '-q', '-p', 'no:cacheprovider'],
            cwd=W, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        output = result.stdout
        if result.returncode == 0:
            problem = AssertionError(f'{name}: mutant unexpectedly passed')
        else:
            text = output.decode('utf-8', 'replace')
            missing = [fragment for fragment in row['expect'] if fragment not in text]
            if missing:
                problem = AssertionError(
                    f'{name}: wrong red; missing {missing}; output follows\n{text}'
                )
    except BaseException as error:
        problem = error
    finally:
        target.write_bytes(original)
        restored = target.read_bytes()
        assert restored == original
        assert hashlib.sha256(restored).hexdigest() == original_hash
        assert git_bytes('diff', '--binary', 'HEAD', '--', '.') == before_diff
        assert git_bytes('status', '--porcelain=v2', '--untracked-files=all', '-z') == before_status
        out = Path('/tmp/wingman-setup-fixture-mutants')
        out.mkdir(exist_ok=True)
        (out / f'{name}.log').write_bytes(output)
        (out / f'{name}.json').write_text(json.dumps({
            'target': row['target'],
            'original_sha256': original_hash,
            'restored_sha256': hashlib.sha256(restored).hexdigest(),
            'expected': row['expect'],
        }, sort_keys=True, indent=2) + '\n')
    if problem is not None:
        raise problem
    print(json.dumps({'mutant': name, 'result': 'intended-red', 'restored_sha256': original_hash}))


parser = argparse.ArgumentParser()
parser.add_argument('mutant', choices=tuple(MUTATIONS))
args = parser.parse_args()
run(args.mutant)
PY
python -m py_compile /tmp/setup_fixture_mutation_probe.py
```

The `path-preflight` mutant deliberately retains `O_EXCL`; it adds both `Path.exists()` and `Path.stat()` only for the dedicated direct success path so the intended failure is the witness's no-preflight guard, not a missing file or open-flag assertion. `mapping-order` is expected to fail at the earlier exact source byte-inventory assertion because reordering changes verified encoded bytes before the later JSON-order assertion.

### Block C — final identity and scope audit

After Task 3, collect actual controller and full-suite identities and compare them to Block A. The script refuses any baseline removal, rename, reorder, additional suffix, structural setup-fixture-user change, or unapproved path.

```bash
cat > /tmp/setup_fixture_endpoint_audit.py <<'PY'
from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
P = W / '.venv/bin/python'
B = Path('/tmp/wingman-setup-fixture-baseline')
O = Path('/tmp/wingman-setup-fixture-endpoint')
O.mkdir(exist_ok=True)
CONTROLLER = 'tests/test_ui_setup_controller.py'
SUFFIX = [
    CONTROLLER + '::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures',
    CONTROLLER + '::test_fast_fixture_construction_preserves_controller_body_atomic_persistence',
]


def sha(nodes):
    return hashlib.sha256(('\n'.join(nodes) + '\n').encode()).hexdigest()


def collect(args, output):
    env = dict(os.environ, PYTHONPATH=f"{W}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [str(P), '-m', 'pytest', *args, '--collect-only', '-q',
         '-p', 'no:cacheprovider', '-p', 'setup_fixture_inventory_plugin'],
        cwd=W, env=env, text=True, capture_output=True, timeout=240,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(output.read_text(encoding='utf-8'))

baseline_controller = (B / 'controller-188.txt').read_text().splitlines()
baseline_setup = (B / 'setup-users-136.txt').read_text().splitlines()
baseline_complete = (B / 'complete-16605.txt').read_text().splitlines()
controller_rows = collect([CONTROLLER], O / 'controller-collection.json')
complete_rows = collect(['tests'], O / 'complete-collection.json')
controller = [row['nodeid'] for row in controller_rows]
setup_users = [row['nodeid'] for row in controller_rows if row['uses_setup']]
complete = [row['nodeid'] for row in complete_rows]
assert len(controller) == len(set(controller)) == 190
assert controller[:188] == baseline_controller
assert controller[188:] == SUFFIX
assert setup_users == baseline_setup
assert len(complete) == len(set(complete)) == 16607
assert set(baseline_complete) <= set(complete)
assert [node for node in complete if node not in set(baseline_complete)] == SUFFIX
assert not (set(baseline_complete) - set(complete))
for name, nodes in {
    'controller-190.txt': controller,
    'setup-users-136.txt': setup_users,
    'complete-16607.txt': complete,
    'added-2.txt': SUFFIX,
}.items():
    (O / name).write_text('\n'.join(nodes) + '\n', encoding='utf-8')
allowed = {
    'docs/ci-setup-controller-fixture-construction-results.md',
    'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
    'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
    'tests/setup_fixtures.py',
    'tests/test_ui_setup_controller.py',
}
changed = set(subprocess.check_output(
    ['git', '-C', str(W), 'diff', '--name-only', 'c23788e3..HEAD'], text=True
).splitlines())
assert changed <= allowed, sorted(changed - allowed)
assert {'tests/setup_fixtures.py', 'tests/test_ui_setup_controller.py'} <= changed
summary = {
    'controller_count': len(controller),
    'controller_sha256': sha(controller),
    'setup_user_count': len(setup_users),
    'setup_user_sha256': sha(setup_users),
    'complete_count': len(complete),
    'complete_sha256': sha(complete),
    'added': SUFFIX,
    'removed': [],
    'changed_paths': sorted(changed),
}
(O / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/setup_fixture_endpoint_audit.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
uv run --no-sync python /tmp/setup_fixture_endpoint_audit.py
```

Expected: 190 controller IDs with exact 188 prefix and exact two-ID suffix, unchanged 136 structural setup users, 16,607 complete IDs, two additions, zero removals, and only the five approved paths.

### Block D — authorized hosted run collection and complete audit

Run this block only after Task 5's explicit publication authorization. `NEW_RUN` is mandatory and is the stable workflow-run ID; the collector reads `run_attempt` from the API, calls `gh run view --attempt`, stores every attempt's run/jobs metadata, and selects jobs/artifacts only from the current successful attempt. Earlier failed attempts remain documented but cannot enter passing evidence. GitHub's run `head_sha` is treated as the PR branch head and must equal `run.pull_requests[0].head.sha`; the exact base is `run.pull_requests[0].base.sha`. The synthetic merge is derived independently from each selected job's checkout log using the `HEAD is now at <short> Merge <full-head> into <full-base>` line and the full SHA immediately following `[command]...log -1 --format=%H`, matching the Linux and quoted-Windows formats observed in run `36001306188`. Artifact IDs are selected by exact name and current-attempt job time window, then downloaded by ID so duplicate names from reruns cannot silently select attempt 1.

```bash
cat > /tmp/setup_fixture_hosted_collect.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
: "${NEW_RUN:?Set NEW_RUN to the authorized GitHub Actions workflow run ID}"
R="elboaf/FlyGD-Wingman"
W="/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit"
O="/tmp/wingman-setup-hosted-${NEW_RUN}"
rm -rf "$O"
mkdir -p "$O/logs" "$O/artifacts"
cd "$W"

gh api "repos/$R/actions/runs/$NEW_RUN" > "$O/run.json"
ATTEMPT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_attempt"])' "$O/run.json")
PR=$(python -c 'import json,sys; r=json.load(open(sys.argv[1])); p=r["pull_requests"]; assert len(p)==1,p; assert r["head_sha"]==p[0]["head"]["sha"],(r["head_sha"],p[0]["head"]["sha"]); print(p[0]["number"])' "$O/run.json")
gh run view "$NEW_RUN" -R "$R" --attempt "$ATTEMPT" --json databaseId,headSha,status,conclusion,url,jobs > "$O/run-view.json"
gh pr view "$PR" -R "$R" --json number,url,headRefName,headRefOid,baseRefName,baseRefOid > "$O/pr.json"
for attempt in $(seq 1 "$ATTEMPT"); do
  gh api "repos/$R/actions/runs/$NEW_RUN/attempts/$attempt" > "$O/run-attempt-$attempt.json"
  gh api "repos/$R/actions/runs/$NEW_RUN/attempts/$attempt/jobs?per_page=100" > "$O/jobs-attempt-$attempt.json"
done
cp "$O/jobs-attempt-$ATTEMPT.json" "$O/jobs.json"
gh api --paginate "repos/$R/actions/runs/$NEW_RUN/artifacts?per_page=100" --slurp > "$O/artifact-pages.json"

python - "$O" <<'PY'
from __future__ import annotations
import json, sys
from datetime import datetime
from pathlib import Path

out = Path(sys.argv[1])
run = json.loads((out / 'run.json').read_text())
view = json.loads((out / 'run-view.json').read_text())
pr = json.loads((out / 'pr.json').read_text())
jobs = json.loads((out / 'jobs.json').read_text())['jobs']
pages = json.loads((out / 'artifact-pages.json').read_text())
artifacts = [row for page in pages for row in page['artifacts']]
assert run['conclusion'] == view['conclusion'] == 'success'
assert run['event'] == 'pull_request', run['event']
run_prs = run['pull_requests']
assert len(run_prs) == 1, run_prs
run_pr = run_prs[0]
run_head = run_pr['head']['sha']
run_base = run_pr['base']['sha']
assert run['head_sha'] == view['headSha'] == run_head
assert pr['number'] == run_pr['number']
assert pr['headRefOid'] == run_head, ('run is not for current final PR head', run_head, pr['headRefOid'])
roles = {
    'checks': 'checks',
    'ubuntu': 'test (ubuntu-latest)',
    'windows': 'test (windows-latest)',
}
selected = {}
for role, name in roles.items():
    rows = [job for job in jobs if job['name'] == name]
    assert len(rows) == 1, (role, rows)
    job = rows[0]
    assert job['run_attempt'] == run['run_attempt']
    assert job['conclusion'] == 'success', (role, job['conclusion'])
    selected[role] = job

def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

selected_artifacts = {}
for role, artifact_name in {
    'ubuntu': 'pytest-evidence-ubuntu-latest',
    'windows': 'pytest-evidence-windows-latest',
}.items():
    job = selected[role]
    rows = [
        artifact for artifact in artifacts
        if artifact['name'] == artifact_name
        and not artifact['expired']
        and stamp(job['started_at']) <= stamp(artifact['created_at']) <= stamp(job['completed_at'])
    ]
    assert len(rows) == 1, (role, [(row['id'], row['created_at']) for row in rows])
    selected_artifacts[role] = rows[0]
metadata = {
    'run_id': run['id'],
    'run_attempt': run['run_attempt'],
    'run_head': run_head,
    'run_base': run_base,
    'pr_number': run_pr['number'],
    'run_head_ref': run_pr['head']['ref'],
    'run_base_ref': run_pr['base']['ref'],
    'current_pr_head': pr['headRefOid'],
    'current_pr_base': pr['baseRefOid'],
    'jobs': selected,
    'artifacts': selected_artifacts,
}
(out / 'selection.json').write_text(json.dumps(metadata, sort_keys=True, indent=2) + '\n')
for role, job in selected.items():
    (out / f'{role}-job-id').write_text(str(job['id']))
for role, artifact in selected_artifacts.items():
    (out / f'{role}-artifact-id').write_text(str(artifact['id']))
PY

for role in checks ubuntu windows; do
  JOB_ID=$(cat "$O/$role-job-id")
  gh api --allow-escape-sequences "repos/$R/actions/jobs/$JOB_ID/logs" > "$O/logs/$role.log"
done
for role in ubuntu windows; do
  ARTIFACT_ID=$(cat "$O/$role-artifact-id")
  gh api "repos/$R/actions/artifacts/$ARTIFACT_ID/zip" > "$O/artifacts/$role.zip"
  mkdir -p "$O/artifacts/$role"
  unzip -q "$O/artifacts/$role.zip" -d "$O/artifacts/$role"
  test -f "$O/artifacts/$role/pytest-result.xml"
  test -f "$O/artifacts/$role/pytest-timing.json"
done

python - "$O" <<'PY'
from __future__ import annotations
import json, re, sys
from pathlib import Path

out = Path(sys.argv[1])
metadata = json.loads((out / 'selection.json').read_text())
merge_pattern = re.compile(
    r'HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge '
    r'(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})'
)
full_pattern = re.compile(r'(?P<sha>[0-9a-f]{40})\s*$')

def checkout_evidence(path):
    lines = path.read_text(errors='replace').splitlines()
    merges = [merge_pattern.search(line) for line in lines]
    merges = [match for match in merges if match]
    commands = [
        index for index, line in enumerate(lines)
        if '[command]' in line and 'log -1 --format=%H' in line
    ]
    assert len(merges) == len(commands) == 1, (path, len(merges), commands)
    command = commands[0]
    assert command + 1 < len(lines), path
    full = full_pattern.search(lines[command + 1])
    assert full, (path, lines[command + 1])
    merge = merges[0]
    synthetic = full.group('sha')
    assert synthetic.startswith(merge.group('short')), (path, synthetic, merge.group('short'))
    return {
        'synthetic_merge': synthetic,
        'short': merge.group('short'),
        'merge_head': merge.group('head'),
        'merge_base': merge.group('base'),
    }

checkout = {
    role: checkout_evidence(out / f'logs/{role}.log')
    for role in ('checks', 'ubuntu', 'windows')
}
synthetics = {row['synthetic_merge'] for row in checkout.values()}
assert len(synthetics) == 1, checkout
for role, row in checkout.items():
    assert row['merge_head'] == metadata['run_head'], (role, row)
    assert row['merge_base'] == metadata['run_base'], (role, row)
metadata['synthetic_merge'] = synthetics.pop()
metadata['checkout'] = checkout
(out / 'selected.json').write_text(json.dumps(metadata, sort_keys=True, indent=2) + '\n')
PY

SYNTHETIC=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["synthetic_merge"])' "$O/selected.json")
HEAD_SHA=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_head"])' "$O/selected.json")
BASE_SHA=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_base"])' "$O/selected.json")
git fetch --quiet --no-tags origin "$SYNTHETIC" "$HEAD_SHA" "$BASE_SHA"
git cat-file -e "$SYNTHETIC^{commit}"
git cat-file -e "$HEAD_SHA^{commit}"
git cat-file -e "$BASE_SHA^{commit}"
read -r COMMIT PARENT_BASE PARENT_HEAD EXTRA <<< "$(git rev-list --parents -n 1 "$SYNTHETIC")"
test "$COMMIT" = "$SYNTHETIC"
test "$PARENT_BASE" = "$BASE_SHA"
test "$PARENT_HEAD" = "$HEAD_SHA"
test -z "${EXTRA:-}"
git fetch --quiet origin "+refs/pull/$PR/merge:refs/remotes/pull/$PR/merge"
test "$(git rev-parse refs/remotes/pull/$PR/merge)" = "$SYNTHETIC"
git cat-file -e "ab2028f55f080e6067d7cc62002451f96171fa68^{commit}"
HOSTED_ROOT="$O" python /tmp/setup_fixture_hosted_audit.py
printf 'HOSTED_ROOT=%s\nNEW_RUN=%s\nATTEMPT=%s\nPR=%s\nSYNTHETIC=%s\n' "$O" "$NEW_RUN" "$ATTEMPT" "$PR" "$SYNTHETIC"
SH
bash -n /tmp/setup_fixture_hosted_collect.sh
```

Create the audit parser before running the collector:

```bash
cat > /tmp/setup_fixture_hosted_audit.py <<'PY'
from __future__ import annotations
import hashlib, json, os, re, subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
O = Path(os.environ['HOSTED_ROOT'])
BASELINE_ROOTS = {
    'ubuntu': Path('/tmp/wingman-stage3-ubuntu'),
    'windows': Path('/tmp/wingman-stage3-windows'),
}
CANDIDATE_ROOTS = {
    'ubuntu': O / 'artifacts/ubuntu',
    'windows': O / 'artifacts/windows',
}
B = Path('/tmp/wingman-setup-fixture-baseline')
E = Path('/tmp/wingman-setup-fixture-endpoint')
CONTROLLER = 'tests/test_ui_setup_controller.py'
ADDED = [
    CONTROLLER + '::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures',
    CONTROLLER + '::test_fast_fixture_construction_preserves_controller_body_atomic_persistence',
]
COMPARATOR_SYNTHETIC = 'ab2028f55f080e6067d7cc62002451f96171fa68'
MERGED_BASELINE = 'c23788e392bcd586dfc95b7390eaee18cb4ec224'
KNOWN_POST_COMPARATOR = {'docs/ci-generated-verifier-alerts-consolidation-results.md'}
AUTHORED = {
    'docs/ci-setup-controller-fixture-construction-results.md',
    'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
    'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
    'tests/setup_fixtures.py',
    'tests/test_ui_setup_controller.py',
}
FULL_ALLOWED = KNOWN_POST_COMPARATOR | AUTHORED


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_nodes(nodes):
    return sha_bytes(('\n'.join(nodes) + '\n').encode())


def identity(case):
    parts = case.get('classname', '').split('.')
    assert len(parts) >= 2 and parts[0] == 'tests', parts
    return '::'.join(('/'.join(parts[:2]) + '.py', *parts[2:], case.get('name', '')))


def normalized_skip(text):
    return re.sub(
        r'pytest-of-[^/\s]+/pytest-\d+/[^\s:\"\']+',
        'pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>',
        text.replace('\\', '/'),
    )


def parse_artifact(root):
    cases = list(ET.parse(root / 'pytest-result.xml').getroot().iter('testcase'))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids))
    times = {}
    skips = []
    failures = errors = 0
    file_counts = defaultdict(int)
    file_seconds = defaultdict(float)
    for node, case in zip(ids, cases, strict=True):
        seconds = float(case.get('time', '0') or 0)
        times[node] = seconds
        file = node.split('::', 1)[0]
        file_counts[file] += 1
        file_seconds[file] += seconds
        skipped = case.find('skipped')
        if skipped is not None:
            skips.append((node, normalized_skip(skipped.get('message') or skipped.text or '')))
        failures += len(case.findall('failure'))
        errors += len(case.findall('error'))
    timing = json.loads((root / 'pytest-timing.json').read_text())
    assert timing['case_count'] == len(ids)
    for file, row in timing['files'].items():
        assert row['cases'] == file_counts[file]
        assert abs(row['seconds'] - file_seconds[file]) < 1e-9
    return {
        'ids': ids,
        'set': set(ids),
        'times': times,
        'skips': skips,
        'failures': failures,
        'errors': errors,
        'file_counts': dict(file_counts),
        'file_seconds': dict(file_seconds),
    }


def changed(left, right):
    return set(subprocess.check_output(
        ['git', '-C', str(W), 'diff', '--name-only', f'{left}..{right}'], text=True
    ).splitlines())


def parents(commit):
    return subprocess.check_output(
        ['git', '-C', str(W), 'rev-list', '--parents', '-n', '1', commit], text=True
    ).split()


def seconds(start, end):
    a = datetime.fromisoformat(start.replace('Z', '+00:00'))
    b = datetime.fromisoformat(end.replace('Z', '+00:00'))
    return (b - a).total_seconds()


def checkout_evidence(path):
    lines = path.read_text(errors='replace').splitlines()
    merge_pattern = re.compile(
        r'HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge '
        r'(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})'
    )
    full_pattern = re.compile(r'(?P<sha>[0-9a-f]{40})\s*$')
    merges = [merge_pattern.search(line) for line in lines]
    merges = [match for match in merges if match]
    commands = [
        index for index, line in enumerate(lines)
        if '[command]' in line and 'log -1 --format=%H' in line
    ]
    assert len(merges) == len(commands) == 1, (path, len(merges), commands)
    command = commands[0]
    assert command + 1 < len(lines), path
    full = full_pattern.search(lines[command + 1])
    assert full, (path, lines[command + 1])
    merge = merges[0]
    synthetic = full.group('sha')
    assert synthetic.startswith(merge.group('short')), (path, synthetic, merge.group('short'))
    return {
        'synthetic_merge': synthetic,
        'short': merge.group('short'),
        'merge_head': merge.group('head'),
        'merge_base': merge.group('base'),
    }


metadata = json.loads((O / 'selected.json').read_text())
run = json.loads((O / 'run.json').read_text())
pr = json.loads((O / 'pr.json').read_text())
run_prs = run['pull_requests']
assert len(run_prs) == 1, run_prs
run_pr = run_prs[0]
synthetic = metadata['synthetic_merge']
head = metadata['run_head']
base = metadata['run_base']
assert run['head_sha'] == run_pr['head']['sha'] == head
assert run_pr['base']['sha'] == base
assert run_pr['number'] == metadata['pr_number'] == pr['number']
assert pr['headRefOid'] == metadata['current_pr_head'] == head
assert metadata['current_pr_base'] == pr['baseRefOid']
assert parents(synthetic) == [synthetic, base, head], parents(synthetic)
merge_ref = subprocess.check_output(
    ['git', '-C', str(W), 'rev-parse', f"refs/remotes/pull/{metadata['pr_number']}/merge"],
    text=True,
).strip()
assert merge_ref == synthetic, (merge_ref, synthetic)
assert changed(COMPARATOR_SYNTHETIC, MERGED_BASELINE) == KNOWN_POST_COMPARATOR
assert changed(MERGED_BASELINE, head) == AUTHORED
assert changed(COMPARATOR_SYNTHETIC, synthetic) == FULL_ALLOWED
full = changed(COMPARATOR_SYNTHETIC, synthetic)
assert not any(path.startswith(('.github/', 'wingman/', 'scripts/', 'tests/fixtures/', 'packaging/')) for path in full)
assert not (full & {'pyproject.toml', 'uv.lock'})
assert not {
    path for path in full
    if path.startswith('tests/')
    and path not in {'tests/setup_fixtures.py', 'tests/test_ui_setup_controller.py'}
}

checkout = {
    role: checkout_evidence(O / f'logs/{role}.log')
    for role in ('checks', 'ubuntu', 'windows')
}
assert {row['synthetic_merge'] for row in checkout.values()} == {synthetic}
for role, row in checkout.items():
    assert row == metadata['checkout'][role], (role, row, metadata['checkout'][role])
    assert row['merge_head'] == head, (role, row)
    assert row['merge_base'] == base, (role, row)

baseline = {platform: parse_artifact(root) for platform, root in BASELINE_ROOTS.items()}
candidate = {platform: parse_artifact(root) for platform, root in CANDIDATE_ROOTS.items()}
assert baseline['ubuntu']['set'] == baseline['windows']['set']
assert candidate['ubuntu']['set'] == candidate['windows']['set']
baseline_ids = (B / 'complete-16605.txt').read_text().splitlines()
baseline_controller = (B / 'controller-188.txt').read_text().splitlines()
setup_users = (B / 'setup-users-136.txt').read_text().splitlines()
assert len(baseline_ids) == 16605 and set(baseline_ids) == baseline['ubuntu']['set']
assert len(baseline_controller) == 188
assert len(setup_users) == 136
expected_after = set(baseline_ids) | set(ADDED)
report = {'provenance': metadata, 'platforms': {}, 'synthetic_paths': sorted(full)}
for platform in ('ubuntu', 'windows'):
    old = baseline[platform]
    new = candidate[platform]
    assert len(new['ids']) == len(new['set']) == 16607
    assert new['set'] == expected_after
    assert new['set'] - old['set'] == set(ADDED)
    assert old['set'] - new['set'] == set()
    controller = [node for node in new['ids'] if node.startswith(CONTROLLER + '::')]
    assert controller == baseline_controller + ADDED
    assert len(controller) == 190
    assert not [row for row in new['skips'] if row[0].startswith(CONTROLLER + '::')]
    assert new['skips'] == old['skips']
    assert len(new['skips']) == {'ubuntu': 14, 'windows': 67}[platform]
    assert new['failures'] == new['errors'] == 0
    for node, reason in new['skips']:
        lowered = reason.casefold()
        assert not any(fragment in lowered for fragment in (
            'node is not installed',
            'settings codec not built',
            'codec is not available',
            'resource unavailable',
            'resource module',
        )), (node, reason)
    expected_passed = {'ubuntu': 16593, 'windows': 16540}[platform]
    assert len(new['ids']) - len(new['skips']) == expected_passed
    controller_seconds = sum(new['times'][node] for node in controller)
    setup_seconds = sum(new['times'][node] for node in setup_users)
    other_seconds = sum(new['times'][node] for node in controller if node not in set(setup_users))
    slowest_retained = sorted(
        ((new['times'][node], node) for node in baseline_controller), reverse=True
    )[:10]
    artifact = metadata['artifacts'][platform]
    archive = O / f'artifacts/{platform}.zip'
    xml = CANDIDATE_ROOTS[platform] / 'pytest-result.xml'
    timing = CANDIDATE_ROOTS[platform] / 'pytest-timing.json'
    report['platforms'][platform] = {
        'cases': len(new['ids']),
        'passed': expected_passed,
        'skips': len(new['skips']),
        'controller_cases': len(controller),
        'controller_seconds': controller_seconds,
        'setup_user_cases': len(setup_users),
        'setup_user_seconds': setup_seconds,
        'other_controller_seconds': other_seconds,
        'controller_sha256': sha_nodes(controller),
        'complete_sha256': sha_nodes(new['ids']),
        'added': ADDED,
        'removed': [],
        'slowest_retained_controller': slowest_retained,
        'artifact_id': artifact['id'],
        'artifact_archive_sha256': sha_bytes(archive.read_bytes()),
        'xml_sha256': sha_bytes(xml.read_bytes()),
        'timing_sha256': sha_bytes(timing.read_bytes()),
    }
    (O / f'{platform}-complete-16607.txt').write_text('\n'.join(new['ids']) + '\n')
    (O / f'{platform}-controller-190.txt').write_text('\n'.join(controller) + '\n')
    (O / f'{platform}-skips.json').write_text(json.dumps(new['skips'], indent=2) + '\n')

assert [node for node in candidate['ubuntu']['ids'] if node.startswith(CONTROLLER + '::')] == [
    node for node in candidate['windows']['ids'] if node.startswith(CONTROLLER + '::')
]
if (E / 'complete-16607.txt').is_file():
    local_ids = (E / 'complete-16607.txt').read_text().splitlines()
    assert set(local_ids) == candidate['ubuntu']['set']
if (E / 'controller-190.txt').is_file():
    local_controller = (E / 'controller-190.txt').read_text().splitlines()
    assert local_controller == baseline_controller + ADDED

job_observations = {}
for role, job in metadata['jobs'].items():
    test_steps = [step for step in job['steps'] if step['name'] == 'Test']
    job_observations[role] = {
        'job_id': job['id'],
        'job_seconds': seconds(job['started_at'], job['completed_at']),
        'test_step_seconds': (
            seconds(test_steps[0]['started_at'], test_steps[0]['completed_at'])
            if test_steps else None
        ),
    }
report['job_observations'] = job_observations
report['claim'] = 'structural only: 136 setup users x 4 fresh DATs = 544 fixture fsyncs removed'
(O / 'hosted-audit.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
print(json.dumps(report, sort_keys=True))
PY
python -m py_compile /tmp/setup_fixture_hosted_audit.py
```

The parser defines every helper it uses (`changed`, `parents`, `checkout_evidence`, identity/skip normalization, artifact parsing, duration and hash functions). It proves the run payload head equals the payload/current final PR head, takes the exact base from the run payload, independently re-extracts one identical synthetic merge from each of the three checkout logs, verifies each merge message names that run head/base, verifies parents `[base, head]`, and treats the current PR merge ref only as matching final-head corroboration. It then proves the exact six-path comparator-synthetic diff and protected paths, artifact hashes/IDs, timing-JSON agreement, full cross-platform identity equality, comparator+two exact additions and zero removals, 190 ordered controller IDs with 188 prefix/two suffix, platform-local skip equality, no controller/resource/Node/codec availability skip, pass/failure/error counts, retained setup/controller timing observations, and slowest retained Windows identities.

---

### Task 1: Freeze the c23788e3 Baseline and Create the Evidence Ledger

**Files:**
- Create: `docs/ci-setup-controller-fixture-construction-results.md`
- Read: `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`
- Read: `tests/setup_fixtures.py`
- Read/collect: `tests/test_ui_setup_controller.py`
- Read artifacts: `/tmp/wingman-stage3-ubuntu/{pytest-result.xml,pytest-timing.json}`
- Read artifacts: `/tmp/wingman-stage3-windows/{pytest-result.xml,pytest-timing.json}`

**Interfaces:**
- Consumes: source commit `c23788e3`, fixture name `setup`, PR #287 run `35994945673` attempt 2, Ubuntu job `107621270623`, Windows job `107621270652`, synthetic merge `ab2028f55f080e6067d7cc62002451f96171fa68`, PR head `db2185768b919331c54370d3532215e53d5583bd`, and base `8d5b93058d9de3def9c17d222ba2d665eb0ba87b`.
- Produces: exact ordered 188-controller, 136-setup-user, and 16,605-complete inventories; actual hashes; complete normalized skip tuples; artifact provenance/integrity; timing observations; and the results-document structure consumed by Tasks 2–5.

**Independent deliverable:** A reviewer can accept baseline truth and artifact attribution without accepting any helper, witness, or optimization.

- [ ] **Step 1: Verify checkout identity and artifact presence**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
git status --short --branch
git merge-base --is-ancestor c23788e3 HEAD
for platform in ubuntu windows; do
  test -f "/tmp/wingman-stage3-$platform/pytest-result.xml"
  test -f "/tmp/wingman-stage3-$platform/pytest-timing.json"
done
node --version
uv sync --locked --extra dev
```

Expected: branch `ci-setup-fixture-construction`, clean except approved planning history, `c23788e3` is an ancestor, both artifact roots contain exactly the required evidence files, Node is available, and dependency sync succeeds.

- [ ] **Step 2: Run Block A and freeze all ordered inventories**

Run Block A exactly.

Expected:

- exactly 188 unique controller IDs;
- exactly 136 IDs whose collected `item.fixturenames` contains `setup`;
- exactly 16,605 unique complete-suite IDs;
- controller IDs in both artifact sets equal the source collection in order;
- Ubuntu and Windows complete identity sets equal;
- zero failures/errors;
- 14 Ubuntu and 67 Windows normalized skip tuples;
- actual newline-normalized SHA-256 values recorded from generated files, never copied from this plan.

- [ ] **Step 3: Record exact artifact identity and provenance**

Record these approved attempt-2 authorities and verify extracted file hashes directly:

| Platform | Job | Artifact ID | Archive digest | XML SHA-256 | Timing SHA-256 |
|---|---:|---:|---|---|---|
| Ubuntu | `107621270623` | `10806746306` | `sha256:ae44499ef75418f94fc220351e30cd8bbba35709d89d8f76737cc0a7fef6a17f` | `40e3c887f72c1332cf0ebbcd31716c5bce63d60e776d6c8e0437a3b8ecb690ff` | `ece3c88211a0e00bc29fbcfa0d052c1a5e02296386984c75e65d9a4c5519157c` |
| Windows | `107621270652` | `10807115906` | `sha256:0249528a74786639791c9386c1dafe41cd93abb667682efd25b25de7e885606b` | `24875479dcd8d146251b605a44733d9afaf0656e64d16273aade3c56da31c8be` | `b8a929884c1550a92464124eabe0ade06f33202a0e00a117577acb12945b63ae` |

```bash
sha256sum /tmp/wingman-stage3-ubuntu/pytest-result.xml \
  /tmp/wingman-stage3-ubuntu/pytest-timing.json \
  /tmp/wingman-stage3-windows/pytest-result.xml \
  /tmp/wingman-stage3-windows/pytest-timing.json
```

Expected: extracted hashes match the table. Record that attempt 1 is excluded and attempt 2 is passing comparator evidence.

- [ ] **Step 4: Record exact timing and skip controls without making a speed claim**

Publish the complete ordered normalized skip tuples from Block A and these JUnit observations:

| Scope | Ubuntu | Windows |
|---|---:|---:|
| Complete identities | 16,605 | 16,605 |
| Passed | 16,591 | 16,538 |
| Intentional platform skips | 14 | 67 |
| Controller identities | 188 | 188 |
| Controller skips | 0 | 0 |
| Controller testcase sum | 3.185s | 42.301s |
| Structural `setup` users | 136 | 136 |
| Setup-user testcase sum | 2.964s | 40.384s |
| Other-controller testcase sum | 0.221s | 1.917s |

State that these observations motivate structural filesystem analysis but prove no expected duration change.

- [ ] **Step 5: Create the results document with exact sections**

Create these top-level sections and populate Task 1 evidence completely:

1. `Scope and authority`
2. `Task status`
3. `Exact 188-ID controller baseline`
4. `Exact 136-ID structural setup-fixture inventory`
5. `Exact 16,605-ID complete baseline`
6. `PR #287 attempt-2 provenance and artifact integrity`
7. `Complete normalized comparator skip tuples`
8. `Comparator testcase observations`
9. `Fresh publisher and parity evidence`
10. `Controller-body persistence evidence`
11. `Mutation ledger and restoration`
12. `Local endpoint verification`
13. `Hosted comparison`
14. `Deviations and concerns`
15. `Required self-review`

For later sections use explicit status text such as `NOT STARTED — Task 2 owns this evidence`; do not use an unfinished-body marker or imply evidence already exists.

- [ ] **Step 6: Audit and commit Task 1**

```bash
git diff --check
git diff --name-only
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: freeze setup fixture construction baseline"
```

Expected: only the results document is committed in this task.

**Implementer report:** Commit SHA; exact counts and actual hashes; complete artifact provenance and extracted hashes; 14/67 skips; timing table; changed paths; and discrepancies. State explicitly that no executable file or test identity changed.

**Fresh reviewer gate:** Independently rerun Block A, compare every inventory byte-for-byte, recompute hashes, reparse both artifact sets and timing JSON, verify structural fixture use rather than name-pattern inference, and approve the Task 1 commit.

**Fix loop:** Any identity, fixture-use, artifact, skip, timing, or provenance mismatch stops the tranche. Correct the evidence or attribution, rerun all Task 1 checks, commit a documentation correction, and repeat fresh review before Task 2.

---

### Task 2: Add and Qualify the Fresh Publisher, Optional Seed Seam, and Comprehensive Witness

**Files:**
- Modify: `tests/setup_fixtures.py` import block, immediately before `seed_profile`, and the exact `seed_profile` signature/DAT-write loop
- Modify: `tests/test_ui_setup_controller.py` import block and append after `test_file_save_rejects_non_json_destination_without_writing`
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Test only: `tests/test_ui_setup_schema.py`, unchanged default-path caller

**Interfaces:**
- Consumes: existing `codec.write_document(path, document, *, backup, publish=atomicio.write_bytes_atomic, ...)` and the current `ProfileFixture`/fixture document factories.
- Produces:
  - `_publish_fresh_file(path: Path, data: bytes) -> None` in `tests.setup_fixtures`;
  - `seed_profile(tmp_path, *, case="recipient", name="Base", initial_dat_publish=None) -> ProfileFixture`;
  - exact appended witness `test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures`;
  - test-local `_OSProxy`, normalization, metadata, and seed-pair helpers in `tests/test_ui_setup_controller.py`.

**Independent deliverable:** The helper and first witness are fully qualified while the reusable controller fixture and every existing caller remain on the default atomic path.

- [ ] **Step 1: Add the witness name first and verify RED**

Append a minimal first version of the exact witness with signature `(tmp_path, monkeypatch)`—not `setup`—that imports `tests.setup_fixtures` and calls `_publish_fresh_file`.

```python
def test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures(
    tmp_path, monkeypatch
):
    target = tmp_path / "fresh.dat"
    setup_fixtures._publish_fresh_file(target, b"payload")
    assert target.read_bytes() == b"payload"
```

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures -q
```

Expected: FAIL with `AttributeError` because `_publish_fresh_file` does not exist.

- [ ] **Step 2: Implement the minimal helper with original-exception cleanup**

Use this complete stdlib import block in `tests/setup_fixtures.py`, preserving the existing `yaml` and codec imports below it:

```python
import contextlib
import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
```

Then add this helper immediately before `seed_profile`:

```python
def _publish_fresh_file(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Fresh fixture write made no progress.")
            remaining = remaining[written:]
        os.close(descriptor)
        descriptor = None
    except BaseException:
        if descriptor is not None:
            with contextlib.suppress(BaseException):
                os.close(descriptor)
        with contextlib.suppress(BaseException):
            os.unlink(path)
        raise
```

This shape is load-bearing:

- `os.open` is outside the cleanup `try`, so an existing destination is refused without unlinking it;
- the one syscall owns exclusivity;
- a close failure leaves `descriptor` non-`None`, so cleanup retries close and then unlinks;
- cleanup suppresses its own failure and the bare `raise` preserves the original exception object;
- no fsync, temporary neighbor, replace, retry, or preflight exists.

Run the focused witness. Expected: PASS for the initial success check.

- [ ] **Step 3: Add the optional seed seam while keeping omission observable**

Change the signature exactly to:

```python
def seed_profile(
    tmp_path,
    *,
    case="recipient",
    name="Base",
    initial_dat_publish=None,
) -> ProfileFixture:
```

Replace only the DAT write loop with an explicit branch that omits `publish` when `None`:

```python
    for path, document in ((account_path, account), (character_path, character)):
        # These files do not exist yet; there is no previous content to back up.
        if initial_dat_publish is None:
            codec.write_document(path, document, backup=lambda path: None)
        else:
            codec.write_document(
                path,
                document,
                backup=lambda path: None,
                publish=initial_dat_publish,
            )
```

Do not bind an atomic function or `_publish_fresh_file` as the default argument. Do not move YAML/INI writes through this publisher.

- [ ] **Step 4: Add the complete shared witness support**

Replace the complete import block with this executable Ruff-ordered block:

```python
import contextlib
import copy
import errno
import io
import json
import logging
import os
import stat
from collections import Counter
from dataclasses import asdict, fields, replace
from pathlib import Path
from uuid import UUID

import pytest

from tests import fakes, setup_fixtures, test_setup_catalog
from tests.setup_fixtures import (
    ProfileFixture,
    install_lossless_codec,
    seed_profile,
    wire,
)
from tests.test_evesettings_controller import QueuedThreads, build_controller
from tests.test_ui_setup_documents import value
from wingman import atomicio
from wingman.evesettings import (
    codec,
    profilecopy,
    setup_catalog,
    setup_documents,
    setup_model,
    setup_profile,
    setup_sharing,
    tree,
)
from wingman.evesettings import controller as controller_mod
from wingman.evesettings.controller import _SetupReview
from wingman.ui import api as api_mod
```

Append these complete helpers immediately before the first witness. They are shared only by the two approved witness tests and create no identities:

```python
class _OSProxy:
    def __init__(
        self,
        real,
        *,
        assert_fresh_open=False,
        write_steps=(),
        close_errors=(),
        unlink_errors=(),
    ):
        self._real = real
        self._assert_fresh_open = assert_fresh_open
        self._write_steps = list(write_steps)
        self._close_errors = list(close_errors)
        self._unlink_errors = list(unlink_errors)
        self.open_calls = []
        self.open_descriptors = set()
        self.write_calls = []
        self.close_calls = []
        self.unlink_calls = []
        self.fsync_calls = []
        self.fsync_categories = []
        self.current_category = None
        self.category_events = None

    def __getattr__(self, name):
        return getattr(self._real, name)

    def open(self, path, flags, mode=0o777):
        call = (Path(path), flags, mode)
        self.open_calls.append(call)
        if self._assert_fresh_open:
            expected = (
                self._real.O_CREAT
                | self._real.O_EXCL
                | self._real.O_WRONLY
                | getattr(self._real, "O_BINARY", 0)
            )
            assert flags == expected, (
                f"fresh open flags changed: {flags:#x} != {expected:#x}"
            )
            assert mode == 0o600, f"fresh open mode changed: {mode:o}"
        descriptor = self._real.open(path, flags, mode)
        self.open_descriptors.add(descriptor)
        return descriptor

    def write(self, descriptor, data):
        self.write_calls.append((descriptor, bytes(data)))
        if self._write_steps:
            step = self._write_steps.pop(0)
            if isinstance(step, BaseException):
                raise step
            if step == 0:
                return 0
            return self._real.write(descriptor, data[:step])
        return self._real.write(descriptor, data)

    def close(self, descriptor):
        self.close_calls.append(descriptor)
        result = self._real.close(descriptor)
        self.open_descriptors.discard(descriptor)
        if self._close_errors:
            raise self._close_errors.pop(0)
        return result

    def release_tracked(self):
        failures = []
        for descriptor in tuple(self.open_descriptors):
            try:
                self._real.close(descriptor)
            except OSError as error:
                failures.append((descriptor, error))
            else:
                self.open_descriptors.discard(descriptor)
        return failures

    def unlink(self, path):
        self.unlink_calls.append(Path(path))
        if self._unlink_errors:
            raise self._unlink_errors.pop(0)
        return self._real.unlink(path)

    def fsync(self, descriptor):
        self.fsync_calls.append(descriptor)
        if self.current_category is not None:
            self.fsync_categories.append(self.current_category)
            if self.category_events is not None:
                self.category_events.append(self.current_category)
        return self._real.fsync(descriptor)

    @contextlib.contextmanager
    def category(self, name):
        previous = self.current_category
        self.current_category = name
        try:
            yield
        finally:
            self.current_category = previous


class _PathProxy:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name in {"exists", "lexists", "isfile", "isdir", "islink"}:
            raise AssertionError(f"fresh publisher called os.path.{name}")
        return getattr(self._real, name)


class _ClockProxy:
    def __init__(self, real, now):
        self._real = real
        self._now = now

    def __getattr__(self, name):
        return getattr(self._real, name)

    def time(self):
        return self._now


def _normalized_paths(value, root):
    if isinstance(value, Path):
        return value.relative_to(root).as_posix()
    if isinstance(value, dict):
        return {key: _normalized_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized_paths(item, root) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalized_paths(item, root) for item in value)
    return value


def _normalized_discovery(profile):
    value = asdict(tree.discover(profile.root, profile.server, profile.profile))
    for row in value["profiles"]:
        row.pop("modified")
    return _normalized_paths(value, profile.root)


def _profile_manifest(profile):
    found = tree.discover(profile.root, profile.server, profile.profile)
    plan = profilecopy.prepare_copy(found, profile.profile, "new", "ManifestTarget")
    return setup_profile.capture_manifest(plan)


def _normalized_manifest(profile):
    return _normalized_paths(asdict(_profile_manifest(profile)), profile.root)


def _fixture_inventory(profile):
    return {
        path.relative_to(profile.profile).as_posix(): path.read_bytes()
        for path in sorted(profile.profile.rglob("*"))
        if path.is_file()
    }


def _fixture_files(profile):
    return {
        path.relative_to(profile.profile).as_posix(): path
        for path in sorted(profile.profile.rglob("*"))
        if path.is_file()
    }


def _stable_metadata(path):
    info = path.stat()
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_nlink,
    )


def _seed_pair(root, publisher=None):
    kwargs = {} if publisher is None else {"initial_dat_publish": publisher}
    return (
        seed_profile(root, case="source", name="Source", **kwargs),
        seed_profile(root, **kwargs),
    )


def _snapshots(profile):
    return (
        codec.read_snapshot(profile.account_path),
        codec.read_snapshot(profile.character_path),
    )
```

`_OSProxy` records each real descriptor after `os.open`. Its `close` delegates to the real close first, removes the descriptor only after physical close succeeds, and only then raises an injected sentinel. A real close failure therefore leaves the descriptor tracked for teardown. `release_tracked()` retries only still-tracked real descriptors. Each owning module receives a distinct proxy. `_ClockProxy` replaces only `controller_mod.time` and delegates every member other than `time()`; it never mutates the shared stdlib `time` module.

- [ ] **Step 5: Replace the temporary RED body with the complete comprehensive witness**

Append this exact, non-parameterized test. The code executes parity bytes/documents/order/revisions/discovery/manifests, source/recipient distinctions, metadata/isolation/link/template/duplicate checks, exact open flags/mode/count, no-preflight guards, partial/zero writes, write and close failures, cleanup failures, and original-exception identity:

```python
def test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures(
    tmp_path, monkeypatch, request
):
    install_lossless_codec(monkeypatch)
    real_os = os
    expected_flags = (
        real_os.O_CREAT
        | real_os.O_EXCL
        | real_os.O_WRONLY
        | getattr(real_os, "O_BINARY", 0)
    )
    direct = _OSProxy(real_os, assert_fresh_open=True)
    direct.path = _PathProxy(real_os.path)
    atomic = _OSProxy(real_os)
    proxies = [direct, atomic]
    direct_root = tmp_path / "direct"

    def make_proxy(**kwargs):
        proxy = _OSProxy(real_os, assert_fresh_open=True, **kwargs)
        proxies.append(proxy)
        return proxy

    def release_descriptors_and_files():
        release_failures = []
        for proxy in proxies:
            release_failures.extend(proxy.release_tracked())
        cleanup_failures = []
        if direct_root.exists():
            for path in direct_root.iterdir():
                try:
                    path.unlink()
                except OSError as error:
                    cleanup_failures.append((path, error))
        assert release_failures == [], release_failures
        assert cleanup_failures == [], cleanup_failures
        assert all(not proxy.open_descriptors for proxy in proxies)

    request.addfinalizer(release_descriptors_and_files)
    monkeypatch.setattr(setup_fixtures, "os", direct)
    monkeypatch.setattr(atomicio, "os", atomic)

    atomic_source, atomic_recipient = _seed_pair(tmp_path / "atomic")
    assert len(atomic.fsync_calls) == 4, "default construction fsync count changed"
    assert direct.fsync_calls == [], "default construction used direct fsync channel"
    assert direct.open_calls == [], "default construction used fresh publisher"

    atomic.fsync_calls.clear()
    fast_source, fast_recipient = _seed_pair(
        tmp_path / "fast-a", setup_fixtures._publish_fresh_file
    )
    assert atomic.fsync_calls == [], "fast atomic fsync count changed"
    assert direct.fsync_calls == [], "fast direct fsync count changed"
    assert len(direct.open_calls) == 4, "fast destination open count changed"
    assert direct.open_descriptors == set()
    assert atomic.open_descriptors == set()
    assert all(
        flags == expected_flags and mode == 0o600
        for _path, flags, mode in direct.open_calls
    ), direct.open_calls

    roles = (
        ("source", atomic_source, fast_source),
        ("recipient", atomic_recipient, fast_recipient),
    )
    for role, atomic_profile, fast_profile in roles:
        assert _fixture_inventory(atomic_profile) == _fixture_inventory(fast_profile), (
            f"{role} byte inventory differs"
        )
        atomic_snapshots = _snapshots(atomic_profile)
        fast_snapshots = _snapshots(fast_profile)
        assert atomic_snapshots == fast_snapshots, f"{role} snapshots differ"
        assert [row.document.had_crc for row in atomic_snapshots] == [
            row.document.had_crc for row in fast_snapshots
        ]
        assert [row.content_revision for row in atomic_snapshots] == [
            row.content_revision for row in fast_snapshots
        ]
        assert [
            json.dumps(row.document.doc, ensure_ascii=False)
            for row in atomic_snapshots
        ] == [
            json.dumps(row.document.doc, ensure_ascii=False)
            for row in fast_snapshots
        ], f"{role} JSON type/order differs"
        assert _normalized_discovery(atomic_profile) == _normalized_discovery(
            fast_profile
        ), f"{role} discovery differs"
        assert _normalized_manifest(atomic_profile) == _normalized_manifest(
            fast_profile
        ), f"{role} manifest differs"

    assert (fast_source.account_path.name, fast_source.character_path.name) == (
        "core_user_10.dat",
        "core_char_11.dat",
    )
    assert (fast_recipient.account_path.name, fast_recipient.character_path.name) == (
        "core_user_20.dat",
        "core_char_30.dat",
    )
    source_snapshots = _snapshots(fast_source)
    recipient_snapshots = _snapshots(fast_recipient)
    assert [row.document.had_crc for row in source_snapshots] == [True, True]
    assert [row.document.had_crc for row in recipient_snapshots] == [False, False]
    assert source_snapshots[0].document.doc["bytes:syntheticPrivate"] == {
        "bytes:accountID": 10,
        "bytes:marker": "utf8:Synthetic private source account",
    }
    assert recipient_snapshots[0].document.doc["bytes:syntheticPrivate"] == {
        "bytes:accountID": 20,
        "bytes:marker": "utf8:Synthetic private recipient account",
    }
    expected_preferences = {
        "source": {
            "core_public__.yaml": b"# synthetic source local preferences\nuiScale: 1.0\n",
            "prefs.ini": b"; synthetic source local preferences\nmonitor=1\n",
        },
        "recipient": {
            "core_public__.yaml": b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n",
            "prefs.ini": b"; synthetic recipient local preferences\r\nmonitor=2\r\n",
        },
    }
    for role, profile in (("source", fast_source), ("recipient", fast_recipient)):
        assert {
            name: (profile.profile / name).read_bytes()
            for name in expected_preferences[role]
        } == expected_preferences[role]

    second_source, second_recipient = _seed_pair(
        tmp_path / "fast-b", setup_fixtures._publish_fresh_file
    )
    assert fast_source.profile != fast_recipient.profile
    assert not fast_source.profile.samefile(fast_recipient.profile)
    first_files = _fixture_files(fast_source)
    second_files = _fixture_files(second_source)
    assert set(first_files) == set(second_files)
    for name in first_files:
        first = first_files[name]
        second = second_files[name]
        assert stat.S_ISREG(first.stat().st_mode) and stat.S_ISREG(second.stat().st_mode)
        assert real_os.access(first, real_os.W_OK) and real_os.access(second, real_os.W_OK)
        assert first.stat().st_nlink == 1, "fast-a link count changed"
        assert second.stat().st_nlink == 1, "fast-b link count changed"
        assert not first.samefile(second), "fast fixtures share inode"

    metadata_before = {
        name: _stable_metadata(path) for name, path in _fixture_files(fast_recipient).items()
    }
    _snapshots(fast_recipient)
    _normalized_discovery(fast_recipient)
    _normalized_manifest(fast_recipient)
    assert {
        name: _stable_metadata(path) for name, path in _fixture_files(fast_recipient).items()
    } == metadata_before, "stable metadata changed during observation"

    second_before = _fixture_inventory(second_source)
    fast_source.account_path.write_bytes(fast_source.account_path.read_bytes() + b" ")
    assert _fixture_inventory(second_source) == second_before, "fast fixtures share data"
    assert not [path for path in tmp_path.rglob("*") if "template" in path.name.lower()]
    before_duplicate = _fixture_inventory(fast_recipient)
    with pytest.raises(FileExistsError):
        seed_profile(
            tmp_path / "fast-a",
            initial_dat_publish=setup_fixtures._publish_fresh_file,
        )
    assert _fixture_inventory(fast_recipient) == before_duplicate
    assert second_recipient.profile != fast_recipient.profile

    def forbidden_path(name):
        def forbidden(*_args, **_kwargs):
            raise AssertionError(f"fresh publisher called Path.{name}")

        return forbidden

    def direct_call(path, payload, proxy, *, forbid_preflight=False):
        proxy.path = _PathProxy(real_os.path)
        error = None
        with monkeypatch.context() as patch:
            patch.setattr(setup_fixtures, "os", proxy)
            if forbid_preflight:
                for name in ("exists", "stat", "lstat", "is_file", "is_dir", "is_symlink"):
                    patch.setattr(Path, name, forbidden_path(name))
            try:
                setup_fixtures._publish_fresh_file(path, payload)
            except (AssertionError, OSError, RuntimeError) as caught:
                error = caught
        return error

    direct_root.mkdir()
    success = direct_root / "success.dat"
    proxy = make_proxy()
    assert direct_call(success, b"payload", proxy, forbid_preflight=True) is None
    assert success.read_bytes() == b"payload"
    assert proxy.open_calls == [(success, expected_flags, 0o600)]
    assert len(proxy.close_calls) == 1 and proxy.fsync_calls == []

    existing = direct_root / "existing.dat"
    existing.write_bytes(b"keep")
    proxy = make_proxy()
    error = direct_call(existing, b"replace", proxy, forbid_preflight=True)
    assert isinstance(error, FileExistsError)
    assert proxy.open_calls == [(existing, expected_flags, 0o600)]
    assert existing.read_bytes() == b"keep"

    partial = direct_root / "partial.dat"
    proxy = make_proxy(write_steps=(2, 1, 1))
    assert direct_call(partial, b"abcdef", proxy) is None
    assert partial.read_bytes() == b"abcdef"
    assert len(proxy.write_calls) >= 4 and len(proxy.close_calls) == 1

    write_failure = RuntimeError("write sentinel")
    close_failure = RuntimeError("close sentinel")
    cleanup_close_original = RuntimeError("original cleanup-close write failure")
    cleanup_close = RuntimeError("cleanup close failure")
    cleanup_unlink_original = RuntimeError("original cleanup-unlink write failure")
    cleanup_unlink = RuntimeError("cleanup unlink failure")
    failure_cases = [
        {
            "name": "zero-progress",
            "path": direct_root / "zero.dat",
            "proxy": make_proxy(write_steps=(2, 0)),
            "original": None,
            "fragment": "no progress",
            "close_count": 1,
            "remaining": None,
        },
        {
            "name": "write-failure",
            "path": direct_root / "write-failure.dat",
            "proxy": make_proxy(write_steps=(2, write_failure)),
            "original": write_failure,
            "fragment": "",
            "close_count": 1,
            "remaining": None,
        },
        {
            "name": "close-failure",
            "path": direct_root / "close-failure.dat",
            "proxy": make_proxy(close_errors=(close_failure,)),
            "original": close_failure,
            "fragment": "",
            "close_count": 2,
            "remaining": None,
        },
        {
            "name": "cleanup-close-failure",
            "path": direct_root / "cleanup-close.dat",
            "proxy": make_proxy(
                write_steps=(2, cleanup_close_original),
                close_errors=(cleanup_close,),
            ),
            "original": cleanup_close_original,
            "fragment": "",
            "close_count": 1,
            "remaining": None,
        },
        {
            "name": "cleanup-unlink-failure",
            "path": direct_root / "cleanup-unlink.dat",
            "proxy": make_proxy(
                write_steps=(2, cleanup_unlink_original),
                unlink_errors=(cleanup_unlink,),
            ),
            "original": cleanup_unlink_original,
            "fragment": "",
            "close_count": 1,
            "remaining": b"ab",
        },
    ]
    for case in failure_cases:
        error = direct_call(case["path"], b"abcdef", case["proxy"])
        if case["original"] is None:
            assert type(error) is OSError, case["name"]
            assert case["fragment"] in str(error), case["name"]
        else:
            assert error is case["original"], f"{case['name']} masked original failure"
        assert len(case["proxy"].close_calls) == case["close_count"], case["name"]
        assert case["proxy"].unlink_calls == [case["path"]], case["name"]
        if case["remaining"] is None:
            assert not case["path"].exists(), case["name"]
        else:
            assert case["path"].read_bytes() == case["remaining"], case["name"]
        assert case["proxy"].open_descriptors == set(), case["name"]
```

The earliest parity assertion is exact byte inventory. Therefore both `extra-byte` and `mapping-order` intentionally fail there; the later snapshot/JSON assertions remain executable independent evidence when bytes agree. All failure branches execute inside one named-case loop with per-case messages rather than pytest parametrization. Injected close failure occurs only after the real descriptor has been physically closed and untracked; the helper's retry therefore sees an already-closed descriptor without leaking a Windows handle. The cleanup-close row proves the original write exception survives an injected cleanup-close report after physical close. The cleanup-unlink row separately proves the exact partial-file contract. The registered finalizer retries any genuinely still-tracked real descriptors first, then removes direct-test files, and requires zero release, cleanup, or descriptor residue.

- [ ] **Step 8: Run focused GREEN and unchanged default callers**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_schema.py::test_seed_profile_exercises_real_discovery_and_preserves_local_bytes \
  tests/test_ui_setup_schema.py::test_source_seed_has_distinct_documents_ids_and_local_preferences \
  tests/test_ui_setup_schema.py::test_lossless_transport_keeps_real_revision_and_publication_guards \
  tests/test_ui_setup_schema.py::test_lossless_transport_does_not_bypass_verification_before_publish -q
```

Expected: five passed. The four unchanged schema tests prove ordinary calls still use the atomic default.

Collect controller IDs now and compare with Task 1. Expected: 189 IDs; the baseline 188 are the exact prefix; the comprehensive witness is the only suffix; exactly the original 136 IDs use fixture `setup`.

- [ ] **Step 9: Run every exact Task 2 mutant through the restoration-safe catalog**

Run the committed witness green, then execute each Block B row independently:

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures -q
for mutant in \
  remove-o-excl path-preflight direct-fsync atomic-delegation \
  extra-byte mapping-order line-endings hardlink-template
do
  python /tmp/setup_fixture_mutation_probe.py "$mutant"
done
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures -q
```

Expected exact mapping:

| Catalog key | Intended red assertion |
|---|---|
| `remove-o-excl` | `fresh open flags changed` before delegation |
| `path-preflight` | `fresh publisher called Path.exists`; `O_EXCL` remains present |
| `direct-fsync` | `fast direct fsync count changed`; atomic channel remains zero |
| `atomic-delegation` | `fast atomic fsync count changed`; direct channel is not the detector |
| `extra-byte` | earliest `source byte inventory differs` |
| `mapping-order` | earliest `source byte inventory differs` because encoded order changes bytes |
| `line-endings` | `recipient byte inventory differs` |
| `hardlink-template` | `fast-a link count changed` before byte equality can hide aliasing |

Each command writes its captured red output and restoration hash under `/tmp/wingman-setup-fixture-mutants`. The runner itself proves restored bytes/hash and complete pre/post binary diff/status equality. A codec error, missing-file preflight error, collection error, or later controller failure is rejected as the wrong red.

- [ ] **Step 10: Update results, review, and commit Task 2**

Record parity, source/recipient distinctions, metadata/isolation, all direct contracts, exact fsync/open counts, every mutation result and restoration hash, 189-ID interim collection, unchanged 136 fixture users, and default-caller evidence.

```bash
git diff --check
git diff --exit-code -- wingman tests/test_ui_setup_schema.py \
  tests/test_ui_setup_profile.py tests/test_ui_setup_integration.py \
  tests/fixtures/ui_setup_page.cjs
git add tests/setup_fixtures.py tests/test_ui_setup_controller.py \
  docs/ci-setup-controller-fixture-construction-results.md
git commit -m "test: qualify fresh setup fixture publisher"
```

**Implementer report:** Commit SHA; exact helper/signature; 189-ID and 136-user evidence; direct open flags/mode/count; descriptor tracking/release proof including reported-close and cleanup-close cases; 4-vs-0 construction fsyncs; parity/isolation/failure results; mutation ledger; restoration proof; changed paths; concerns.

**Fresh reviewer gate:** Review helper cleanup line-by-line, prove no preflight or shared backing, verify injected close errors occur after physical close, force-review the finalizer's real-close-before-unlink order and zero tracked descriptors, re-run the witness and every mutant, inspect exact failure locations, confirm default calls omit `publish`, compare 188-prefix/one-suffix identities, and approve before Task 3.

**Fix loop:** Restore all mutants first. Any helper, parity, direct-contract, mutation, identity, or default-path issue returns to RED/GREEN in this task. Add only the smallest correction in the two authorized test files/results, rerun every affected mutant and unchanged schema checks, commit a fix, and repeat fresh review.

---

### Task 3: Opt Only the Controller Fixture In and Prove Controller-Body Persistence

**Files:**
- Modify: the exact two `seed_profile(...)` calls inside `tests/test_ui_setup_controller.py::setup`, then append the second witness after the Task 2 witness
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Temporarily modify and restore: the exact `written_account_revision = codec.write_document(...)` block in `wingman/evesettings/setup_profile.py::stage_setup`
- Verify unchanged: the `setup.__wrapped__(Path(temp), patch)` boundary in `tests/fixtures/ui_setup_page.cjs`

**Interfaces:**
- Consumes: Task 2's `_publish_fresh_file`, optional `seed_profile` seam, `_OSProxy`, and existing `setup.__wrapped__`, `review`, `queue_create`, `assert_create_done` helpers.
- Produces: the unchanged fixture signature `setup(tmp_path, monkeypatch)` using the fresh publisher for exactly four DATs, plus exact second suffix witness `test_fast_fixture_construction_preserves_controller_body_atomic_persistence`.

**Independent deliverable:** The actual hotspot is optimized and the representative create flow proves six pre-publication atomic fsync categories plus one post-publication selection fsync.

- [ ] **Step 1: Append the second witness before changing `setup` and verify RED**

Append this exact non-parameterized RED body after Task 2's witness. It directly calls the wrapped fixture and never requests pytest fixture `setup`:

```python
def test_fast_fixture_construction_preserves_controller_body_atomic_persistence(
    tmp_path, monkeypatch
):
    real_os = os
    direct = _OSProxy(real_os, assert_fresh_open=True)
    direct.path = _PathProxy(real_os.path)
    atomic = _OSProxy(real_os)
    monkeypatch.setattr(setup_fixtures, "os", direct)
    monkeypatch.setattr(atomicio, "os", atomic)
    setup.__wrapped__(tmp_path, monkeypatch)
    assert len(direct.open_calls) == 4, "fast destination open count changed"
    assert direct.fsync_calls == [], "fast direct fsync count changed"
    assert atomic.fsync_calls == [], "fast atomic fsync count changed"
```

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
```

Expected before fixture opt-in: FAIL because construction records zero direct opens and four atomic-channel fsyncs.

- [ ] **Step 2: Opt only the controller fixture into the fresh publisher**

Preserve the fixture definition exactly:

```python
@pytest.fixture
def setup(tmp_path, monkeypatch):
```

Change only its two seed calls:

```python
    source = seed_profile(
        tmp_path,
        case="source",
        name="Source",
        initial_dat_publish=setup_fixtures._publish_fresh_file,
    )
    base = seed_profile(
        tmp_path,
        initial_dat_publish=setup_fixtures._publish_fresh_file,
    )
```

Do not add a fixture argument, wrapper fixture, autouse patch, or module-wide publisher substitution.

Rerun the second witness's construction assertions. Expected: four exact direct opens, zero fsync on both channels.

- [ ] **Step 3: Replace the RED stub with the complete construction/body witness**

Use this exact final test. It phase-separates construction, delegates every wrapped write, accounts for the codec's definition-time publisher default, replaces only the controller module's `time` binding with a delegating clock proxy, completes a real create, and asserts exact output bytes and category order:

```python
def test_fast_fixture_construction_preserves_controller_body_atomic_persistence(
    tmp_path, monkeypatch
):
    real_os = os
    direct = _OSProxy(real_os, assert_fresh_open=True)
    direct.path = _PathProxy(real_os.path)
    atomic = _OSProxy(real_os)
    monkeypatch.setattr(setup_fixtures, "os", direct)
    monkeypatch.setattr(atomicio, "os", atomic)

    controller, source, base = setup.__wrapped__(tmp_path, monkeypatch)
    construction = {
        "opens": list(direct.open_calls),
        "direct_fsyncs": len(direct.fsync_calls),
        "atomic_fsyncs": len(atomic.fsync_calls),
    }
    assert construction["opens"] and len(construction["opens"]) == 4
    assert construction["direct_fsyncs"] == 0
    assert construction["atomic_fsyncs"] == 0
    assert direct.open_descriptors == set()
    assert atomic.open_descriptors == set()
    assert controller._settings["eve_settings"]["profile"] == str(source.profile)

    direct.open_calls.clear()
    direct.fsync_calls.clear()
    atomic.fsync_calls.clear()
    atomic.fsync_categories.clear()
    events = []
    atomic.category_events = events

    real_copy_atomic = atomicio.copy_atomic
    real_write_bytes_atomic = atomicio.write_bytes_atomic
    real_write_atomic = atomicio.write_atomic
    real_write_document = codec.write_document
    real_publish_new = profilecopy.publish_new
    real_clock = controller_mod.time
    monkeypatch.setattr(controller_mod, "time", _ClockProxy(real_clock, 1000.0))

    parsed = setup_sharing.parse_text(setup_sharing.export_text(wire()))
    expected_account, expected_character = setup_documents.apply_setup(
        codec.read_document(base.account_path),
        codec.read_document(base.character_path),
        parsed,
        keep_ship_labels=False,
        now=1000.0,
    )

    def expected_lossless(document):
        envelope = {"had_crc": document.had_crc, "doc": document.doc}
        return b"\x7d" + json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    def copy_atomic(source_path, target_path, *args, **kwargs):
        category = (
            "stage_dat_copy"
            if Path(target_path).suffix == ".dat"
            else "stage_local_copy"
        )
        with atomic.category(category):
            return real_copy_atomic(source_path, target_path, *args, **kwargs)

    def write_document(path, document, **kwargs):
        target = Path(path)
        if (
            "publish" not in kwargs
            and target.parent.name.startswith(profilecopy.STAGE_PREFIX)
            and target.parent.name.endswith(profilecopy.STAGE_SUFFIX)
        ):

            def publish(rewrite_path, data):
                with atomic.category("rewrite_dat"):
                    return real_write_bytes_atomic(rewrite_path, data)

            kwargs["publish"] = publish
        return real_write_document(target, document, **kwargs)

    def write_atomic(path, text, *args, **kwargs):
        with atomic.category("selection"):
            return real_write_atomic(path, text, *args, **kwargs)

    publications = []

    def publish_new(staged):
        result = real_publish_new(staged)
        publications.append(result)
        events.append("directory_publish")
        return result

    monkeypatch.setattr(atomicio, "copy_atomic", copy_atomic)
    monkeypatch.setattr(codec, "write_document", write_document)
    monkeypatch.setattr(atomicio, "write_atomic", write_atomic)
    monkeypatch.setattr(profilecopy, "publish_new", publish_new)

    offer, queued = queue_create(controller, base)
    queued.run_next()
    done = assert_create_done(controller, offer, published=True)
    assert done["selection_persisted"] is True and done["warning"] == ""
    destination = offer.plan.destination
    assert publications == [destination]

    counts = Counter(atomic.fsync_categories)
    expected_counts = Counter(
        {
            "stage_dat_copy": 2,
            "stage_local_copy": 2,
            "rewrite_dat": 2,
            "selection": 1,
        }
    )
    assert counts == expected_counts, f"body fsync categories changed: {counts}"
    assert len(atomic.fsync_calls) == 7, "body fsync total changed"
    assert events == [
        "stage_dat_copy",
        "stage_dat_copy",
        "stage_local_copy",
        "stage_local_copy",
        "rewrite_dat",
        "rewrite_dat",
        "directory_publish",
        "selection",
    ], events
    assert direct.open_calls == [] and direct.fsync_calls == []
    assert direct.open_descriptors == set()
    assert atomic.open_descriptors == set()

    assert {path.name for path in destination.iterdir()} == {
        base.account_path.name,
        base.character_path.name,
        "core_public__.yaml",
        "prefs.ini",
    }
    assert (destination / base.account_path.name).read_bytes() == expected_lossless(
        expected_account
    )
    assert (destination / base.character_path.name).read_bytes() == expected_lossless(
        expected_character
    )
    assert (destination / "core_public__.yaml").read_bytes() == (
        b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n"
    )
    assert (destination / "prefs.ini").read_bytes() == (
        b"; synthetic recipient local preferences\r\nmonitor=2\r\n"
    )
    assert controller._settings["eve_settings"]["profile"] == str(destination)
    assert not list(
        base.server.glob(f"{profilecopy.STAGE_PREFIX}*{profilecopy.STAGE_SUFFIX}")
    )
```

The clock substitution is a module-binding proxy: `controller_mod.time` changes, but the shared `time` module object is never mutated. The body assertion occurs only after `assert_create_done(..., published=True)`, so the direct-body mutant qualifies only if creation and directory publication complete first.

- [ ] **Step 4: Run the completed witness GREEN**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
```

Expected: one pass; construction records four opens and zero fsyncs, body records exact categories `2 + 2 + 2 + 1 = 7`, directory publication precedes selection, and complete destination bytes match.

- [ ] **Step 5: Run existing controller failure/race gates and the three direct Node scenarios**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_create_codec_failure_never_publishes_partial_profile \
  tests/test_ui_setup_controller.py::test_create_external_writer_during_staging_or_final_publish_is_not_overwritten \
  tests/test_ui_setup_controller.py::test_create_preserves_boundary_error_codes_and_failure_context \
  tests/test_ui_setup_controller.py::test_create_publication_survives_housekeeping_failures \
  tests/test_ui_setup_controller.py::test_create_revalidates_authority_and_complete_base \
  tests/test_ui_setup_controller.py::test_create_does_not_trust_authority_from_before_slow_closed_probe -q
uv run --no-sync python -m pytest \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[eve-unknown]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[malformed-text]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[stale-manifest]' -q
```

Expected: all selected controller cases pass; all three Node scenarios pass through the unchanged direct `setup.__wrapped__(Path(temp), patch)` boundary.

- [ ] **Step 6: Qualify independent construction and body mutants with exact restoration**

The Block B catalog already contains unique before/after anchors and exact commands. Run:

```bash
python /tmp/setup_fixture_mutation_probe.py direct-fsync
python /tmp/setup_fixture_mutation_probe.py atomic-delegation
python /tmp/setup_fixture_mutation_probe.py direct-body-write
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
```

Expected:

- direct fsync fails only `fast direct fsync count changed`;
- atomic delegation fails only `fast atomic fsync count changed`;
- direct body write uses the exact `written_account_revision = codec.write_document(...)` block in `stage_setup`, preserves codec encode/signature/readback/revision work, completes `assert_create_done(..., published=True)`, then fails `body fsync categories changed` with rewrite `2 → 1` and total `7 → 6`;
- every target's restored bytes/hash and complete binary diff/status equal its pre-probe snapshot;
- final two-witness command passes.

- [ ] **Step 7: Verify exact 190-ID endpoint and fixture-user count**

Run Block C.

Expected: 190 IDs, baseline 188 exact prefix, exact two-name suffix in order, 136 structural setup users unchanged, and 16,607 projected complete identities.

- [ ] **Step 8: Update results, review, and commit Task 3**

Record actual construction/body counters, exact category/order events, final-byte assertions, Node direct-call evidence, body-mutant completion/count failure, exact 190 collection and hashes, 136 fixture users, and restoration proof.

```bash
git diff --check
git diff --exit-code -- wingman tests/fixtures/ui_setup_page.cjs \
  tests/test_ui_setup_page.py
git add tests/test_ui_setup_controller.py \
  docs/ci-setup-controller-fixture-construction-results.md
git commit -m "test: optimize setup controller fixture construction"
```

**Implementer report:** Commit SHA; exact fixture call changes and unchanged signature; construction counts; seven body categories/order; complete bytes and operation result; Node three-scenario result; 190/136 identity evidence; independent mutant results; restoration; changed paths; concerns.

**Fresh reviewer gate:** Independently inspect fixture scope, run the second witness, verify every wrapper delegates, check definition-time codec default handling, reproduce 7→6 body mutant after successful publication, run the Node scenarios, and approve the Task 3 commit.

**Fix loop:** Any construction leak, body count/category/order error, Node break, extra fixture user, identity drift, or mutant masking returns to this task. Restore production first, apply the smallest test-only correction, rerun both witnesses and affected controller/Node gates, commit a fix, and repeat fresh review.

---

### Task 4: Prove the Complete Local Endpoint and Record Final Local Evidence

**Files:**
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Verify only: all repository paths

**Interfaces:**
- Consumes: Tasks 1–3 baseline files, two witnesses, mutation ledger, exact 190 collection, and unchanged default callers.
- Produces: actual 190-controller and 16,607-complete inventories/hashes, full local pass/skip evidence, all setup/native/codec/profilecopy/atomicio/Node gates, exact scope, and clean mutation restoration.

**Independent deliverable:** A complete locally reviewable endpoint with no publication or hosted claim.

- [ ] **Step 1: Build and install the required release codec**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os,pathlib,shutil; from wingman.evesettings import codec; name='wingman-settings-codec'+('.exe' if os.name=='nt' else ''); source=pathlib.Path('packaging/settings-codec/target/release')/name; target=pathlib.Path('packaging/bin')/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target); assert codec.codec_available()"
node --version
```

Expected: codec built/installed and `codec.codec_available()` true; Node available.

- [ ] **Step 2: Re-run both focused witnesses and exact identity audit**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
uv run --no-sync python /tmp/setup_fixture_endpoint_audit.py
```

Expected: two passed; exact 188-prefix/two-suffix order; 190 unique controller IDs; 136 structural setup users; 16,607 unique complete IDs; exactly two additions and zero removals.

- [ ] **Step 3: Run the complete setup/controller/default/native gate**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py \
  tests/test_ui_setup_schema.py \
  tests/test_ui_setup_profile.py \
  tests/test_ui_setup_integration.py \
  tests/test_evesettings_codec.py \
  tests/test_evesettings_profilecopy.py \
  tests/test_atomicio.py -q -rs --durations=50 \
  --junitxml=/tmp/wingman-setup-fixture-focused.xml
```

Expected: all selected tests pass; zero skip caused by missing Node/codec; native setup integration and native codec rows execute; controller file has 190 passes and zero skips.

- [ ] **Step 4: Run the executable setup-page boundary**

```bash
uv run --no-sync python -m pytest \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[eve-unknown]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[malformed-text]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[stale-manifest]' \
  tests/test_ui_setup_page.py::test_setup_page_worker_protocol_reuses_process_and_correlates_unknown_scenario \
  tests/test_ui_setup_page.py::test_setup_page_worker_isolation_sentinel -q
```

Expected: five passed; direct wrapped-fixture invocation and worker reuse/isolation remain executable.

- [ ] **Step 5: Run complete pytest and audit exact counts/skips**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-setup-fixture-full.xml
```

Expected projection for the unchanged Linux environment: 16,593 passed plus 14 intentional skips = 16,607 identities. Parse the actual JUnit rather than substituting the projection. Reject any failure/error, Node skip, settings-codec skip, controller skip, new platform skip, or identity beyond the exact two witnesses.

- [ ] **Step 6: Run independent Cargo, JS, and Ruff gates**

```bash
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
node scripts/js_smoke.js
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Expected: Cargo passes; JS smoke passes; Ruff check/format pass; diff check is clean.

- [ ] **Step 7: Re-run all exact temporary mutations and prove restoration**

```bash
for mutant in \
  remove-o-excl path-preflight direct-fsync atomic-delegation \
  extra-byte mapping-order line-endings hardlink-template direct-body-write
do
  python /tmp/setup_fixture_mutation_probe.py "$mutant"
done
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
```

Every catalog run independently compares restored bytes/hash and the entire binary diff/status to its own pre-probe snapshot, so uncommitted implementation changes are preserved rather than mistaken for mutation residue. Audit protected paths and temporary symbols separately:

```bash
git diff --exit-code -- wingman .github tests/fixtures \
  tests/test_ui_setup_schema.py tests/test_ui_setup_profile.py \
  tests/test_ui_setup_integration.py tests/test_evesettings_codec.py \
  tests/test_evesettings_profilecopy.py tests/test_atomicio.py \
  pyproject.toml uv.lock packaging
grep -RInE 'MUTATION|_FRESH_FILE_TEMPLATES' \
  tests/setup_fixtures.py tests/test_ui_setup_controller.py || true
```

Expected: every intended red and restoration check passes, both witnesses return green, protected-path diff is empty, and no temporary symbol remains.

- [ ] **Step 8: Audit exact scope and arithmetic**

Run Block C again and additionally:

```bash
python - <<'PY'
import subprocess
allowed = {
 'docs/ci-setup-controller-fixture-construction-results.md',
 'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
 'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
 'tests/setup_fixtures.py',
 'tests/test_ui_setup_controller.py',
}
changed = set(subprocess.check_output(
 ['git','diff','--name-only','c23788e3..HEAD'], text=True).splitlines())
assert changed == allowed, {'missing': sorted(allowed-changed), 'unexpected': sorted(changed-allowed)}
assert 136 * 2 * 2 == 544
assert 188 + 2 == 190
assert 16605 + 2 == 16607
print('\n'.join(sorted(changed)))
PY
```

Expected: exact five-path scope and arithmetic.

- [ ] **Step 9: Complete local results and commit Task 4**

Record actual inventory hashes, exact two-ID addition, zero removals/renames/reorders, 136 unchanged fixture users, focused/full counts, all 14 normalized Linux skips, controller zero skips, native/Node/Cargo/JS/Ruff results, full mutation restoration, exact scope, and claim discipline.

```bash
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: record setup fixture construction verification"
git diff --exit-code HEAD -- .
git diff --cached --exit-code
git status --short --branch
```

Expected: clean branch after a documentation-only Task 4 commit. This is the final post-commit clean-diff check; mutation probes use their pre-probe snapshots instead.

**Implementer report:** Commit SHA; actual 190/16,607 hashes and inventories; two additions/zero removals; 136 structural users; focused/full pass/skip counts; exact commands; native/Node/Cargo/JS/Ruff results; mutation restoration; scope; remaining risks. Do not state a speedup.

**Fresh reviewer gate:** Re-run Block C, inspect JUnit/skip tuples, run both witnesses and a representative native/Node gate, verify arithmetic and five-path scope, inspect mutation restore records, and approve Task 4.

**Fix loop:** Route failures to the owning task: helper/parity/direct contracts to Task 2, fixture/body/Node to Task 3, environment/count/scope/results to Task 4. Apply the smallest authorized correction, rerun all affected and endpoint checks, commit a fix, and repeat fresh review.

---

### Task 5: Polish, Whole Review, Publication Stop, and Hosted Windows/Ubuntu Comparison

**Files:**
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Review: approved spec, this plan, complete `c23788e3..HEAD` diff, local JUnit/inventories, and PR #287 comparator artifacts
- Do not push until explicit maintainer authorization

**Interfaces:**
- Consumes: clean locally verified Task 4 endpoint.
- Produces: polished/reviewed branch, reviewer-facing change explanation, explicit publication checkpoint, and—only after authorization—hosted provenance/artifact comparison proving the exact two-ID addition and structural 544-fsync reduction claim.

**Independent deliverable:** Review and publication readiness are complete before any remote mutation; hosted evidence is a separate authorized phase.

- [ ] **Step 1: Run `polish-core --fix` over the whole tranche**

Load `polish-core` and run its fix workflow against `c23788e3..HEAD`. Inspect every edit. Reject any edit outside the five-path allowlist or any weakening of exact assertions. Rerun affected tests, Block C, Ruff, and `git diff --check`; commit only high-confidence corrections in a separate fix commit.

Expected: no unreviewed polish edit remains and executable identities remain 190/16,607 with exact suffix.

- [ ] **Step 2: Obtain an independent whole-branch review**

A fresh reviewer examines:

- spec-to-plan-to-results coverage;
- helper exclusivity and original-exception cleanup;
- no-preflight and exact flag/mode evidence;
- atomic/fast parity, order/types/CRC/revisions/discovery/manifests;
- isolation, metadata, links, duplicate behavior;
- separate direct/atomic fsync channels;
- exact seven body categories and publication/selection order;
- every mutation's intended assertion and restoration;
- identity/fixture-use/skip/scope/claim discipline;
- unchanged Node wrapped-fixture signature.

Resolve every Critical or Important finding, rerun affected tests and final gates, and obtain fresh approval after each fix wave.

- [ ] **Step 3: Run fresh final local verification on the reviewed executable head**

At minimum rerun:

- both focused witnesses;
- Block C;
- complete controller/setup/default/native gate;
- three direct Node scenarios;
- full pytest with skip audit;
- Cargo, JS smoke, Ruff check/format;
- scope/protected-path/diff checks.

Record the exact reviewed executable head SHA in the results document.

- [ ] **Step 4: Run `change-explainer`**

Load `change-explainer` and produce the reviewer-facing summary from the final diff, tests, results, and verification. It must explain the four fresh DAT publications, why default callers remain atomic, how original exceptions survive cleanup, how controller-body atomic work is phase-separated, the exact two test IDs, the mutation evidence, actual verification, reviewer focus, and remaining risks. It must make only the structural 544-fsync claim.

- [ ] **Step 5: Stop for explicit publication authorization**

Present:

- reviewed head SHA and clean status;
- exact 190 controller and 16,607 complete inventories/hashes;
- exact two-ID suffix and zero removals;
- 136 unchanged setup users;
- local pass/skip/gate results;
- whole-review outcome;
- proposed PR title `Optimize setup controller fixture construction`;
- proposed body stating four exclusive fresh DAT publications per setup fixture, preserved codec/body persistence, exact identity delta, and no speedup claim.

Do not push, open a PR, rerun GitHub workflows, or call a GitHub mutation API before explicit authorization.

- [ ] **Step 6: After authorization, identify the exact successful run**

The maintainer supplies the workflow run ID explicitly; do not infer “latest”:

```bash
read -r -p 'Authorized GitHub Actions run ID: ' NEW_RUN
test -n "$NEW_RUN"
export NEW_RUN
```

Before running the collector, inspect it explicitly:

```bash
gh run view "$NEW_RUN" -R elboaf/FlyGD-Wingman --json databaseId,headSha,status,conclusion,url
```

Expected: pull-request run for this branch. If the run was rerun, keep the same `NEW_RUN`; Block D reads the current `run_attempt`, records every prior attempt, and selects current-attempt jobs/artifacts by job ID and time window. A failed earlier attempt is provenance only and never passing evidence.

- [ ] **Step 7: Execute the self-contained hosted collector and audit**

Create both Block D files exactly, syntax-check them, then run:

```bash
python -m py_compile /tmp/setup_fixture_hosted_audit.py
bash -n /tmp/setup_fixture_hosted_collect.sh
NEW_RUN="$NEW_RUN" bash /tmp/setup_fixture_hosted_collect.sh
```

Expected: the collector proves `run.head_sha == run.pull_requests[0].head.sha == current final PR head`, takes the base only from `run.pull_requests[0].base.sha`, extracts one identical synthetic merge SHA from checks/Ubuntu/Windows checkout logs, verifies each merge message names that head/base, fetches the exact synthetic/head/base objects, validates merge parents `[synthetic, base, head]`, and only then corroborates that the current final-head PR merge ref equals the extracted synthetic. It downloads logs by exact current-attempt job IDs and artifacts by exact IDs, records archive/XML/timing hashes, and writes `hosted-audit.json` beneath `/tmp/wingman-setup-hosted-$NEW_RUN`.

- [ ] **Step 8: Inspect every hosted acceptance output**

Read `selected.json`, all `run-attempt-*.json`/`jobs-attempt-*.json`, `hosted-audit.json`, both complete/controller inventories, normalized skip files, artifact hashes, and job logs. Require the parser's executable assertions to have proved:

- exact six-path comparator-synthetic-to-candidate-synthetic allowlist and protected paths;
- exact per-job checkout-log synthetic SHA immediately after the logged `git log -1 --format=%H` command, identical across checks/Ubuntu/Windows, with each `HEAD is now at` merge subject naming the run payload head/base;
- 16,607 complete identities on each platform with equal cross-platform sets;
- exact two named additions and zero removals across the complete suite;
- exact ordered 190 controller IDs with the 188 baseline prefix and two-name suffix;
- zero controller skips/failures/errors and platform-local skip tuples equal to PR #287 (14 Ubuntu, 67 Windows);
- no resource, Node, or codec availability skip;
- JUnit/timing case/per-file agreement, actual inventory hashes, artifact IDs/digests, controller/setup-user/other-controller sums, slowest retained controller IDs, and Test/job observations.

Any assertion failure is a stop or `INCONCLUSIVE`; do not edit the parser to normalize away evidence drift.

- [ ] **Step 9: Record hosted evidence with claim discipline**

Record provenance, artifact identity, synthetic diff, identity/skip comparison, exact two additions/zero removals, controller order, testcase sums, slowest retained IDs, and Test/job observations. State explicitly:

- verified structural reduction: 136 existing setup users × 4 initial DATs = 544 fixture-only fsync calls removed;
- two new witnesses add qualification work but do not consume fixture `setup` and do not change 544;
- one hosted run supports no speedup, regression attribution, runner-efficiency, critical-path, or wall-clock conclusion.

Any extra identity, removed/reordered baseline ID, platform identity divergence, skip change, availability skip, failure/error, protected path, or unexplained synthetic diff is a stop.

- [ ] **Step 10: Commit hosted evidence and verify the evidence head**

After hosted comparison succeeds, commit only the results document:

```bash
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: record hosted setup fixture construction evidence"
```

Push this evidence commit only if separately authorized, then wait for required checks on that exact documentation head. Record those checks separately from executable timing evidence.

**Implementer report:** Polish edits; whole-review verdict/fixes; reviewed and evidence SHAs; exact hosted run/jobs/artifacts/provenance; six-path synthetic diff; 16,607/190 identities and hashes; two additions/zero removals/reorders; 14/67 skips; testcase/Test/job observations; structural 544 claim; evidence-head checks; unresolved concerns.

**Fresh reviewer gate:** Independently verify merge parents/logs, six-path synthetic diff, artifact IDs/digests, complete identity and skip sets, controller prefix/suffix, timing-json agreement, scope, and no speedup wording before accepting hosted evidence.

**Fix loop:** Local review findings return to the owning task. Hosted provenance/artifact incomparability yields `INCONCLUSIVE` and a repeat run, not inference. Contract failure yields `STOP / repair`; apply no workflow, selector, dependency, production, or broader fixture change under this plan.

---

## Required Plan Self-Review

- **Spec coverage:** Task 1 owns exact baseline/provenance/timing/skips/results ledger; Task 2 owns helper/default seam/parity/isolation/direct failures and all helper mutants; Task 3 owns sole fixture opt-in, unchanged signature, body categories/order and direct body mutant; Task 4 owns complete local endpoint and scope; Task 5 owns polish/review/change explanation/publication stop/hosted comparison.
- **Names and ordering:** The exact two witness names are defined once in Global Constraints, Block C, Tasks 2–3, and hosted acceptance; Task 2 appends the first, Task 3 appends the second, preserving the 188 prefix.
- **Counts and arithmetic:** `136 × 4 = 544`, `188 + 2 = 190`, `16,605 + 2 = 16,607`, Ubuntu projection `16,593 + 14`, Windows projection `16,540 + 67`.
- **Signature consistency:** `_publish_fresh_file(path: Path, data: bytes) -> None`; `seed_profile(..., initial_dat_publish=None)`; fixture remains `setup(tmp_path, monkeypatch)`; the comprehensive witness uses `(tmp_path, monkeypatch, request)` only for descriptor/file finalization, the body witness uses `(tmp_path, monkeypatch)`, and neither requests `setup`.
- **OS proxy safety:** both module bindings are replaced separately; no attribute on the shared real `os` module is mutated; exact flags include platform `O_BINARY`; exact mode is `0o600`; every opened real descriptor is tracked, injected close failures occur only after real close, real close failures remain tracked, and finalization requires no descriptor/file residue.
- **Original exception implementability:** helper retries/suppresses cleanup while a bare `raise` preserves the original write or reported-close sentinel object; cleanup-close reporting occurs after deterministic physical close and cannot mask the original write exception; existing-file open failure occurs before cleanup and cannot unlink the predecessor.
- **Mutation exactness:** Block B requires one exact source match; snapshots/restores exact bytes, hash, binary diff, and status; and defines independent O_EXCL-removal, O_EXCL-retaining `Path.exists`/`Path.stat` preflight, direct fsync, atomic delegation, bytes, order, line-ending, hardlink, and body direct-write mutants with intended assertions.
- **Identity hashes:** scripts compute actual hashes; the plan contains no projected node hash target.
- **Hosted comparison:** run `head_sha` is branch head, never synthetic; the synthetic is independently extracted from all three checkout logs, checked against run-payload head/base and parents `[base, head]`, then used for the exact six-path comparator diff and platform-local skip comparison. Failed/incomparable evidence cannot be normalized away.
- **No placeholders or scope expansion:** every task contains exact files, interfaces, commands, code, expected outcomes, commit, implementer report, reviewer gate, and fix loop; no production or workflow implementation is authorized.
