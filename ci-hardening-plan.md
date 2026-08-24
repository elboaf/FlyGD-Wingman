# CI hardening implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the release path run the tests, run those tests on the platform the app ships to, lint the code, enforce the lockfile, and remove the duplication that has already caused the two Windows workflows to drift.

**Architecture:** No application code changes except lint cleanup. The work is in `.github/`, `pyproject.toml`, and Windows-compatibility fixes to the test suite. The shared Windows build sequence becomes a composite action so `build.yml` and `release.yml` cannot drift again.

**Tech Stack:** GitHub Actions, pytest, ruff, uv, PyInstaller, Inno Setup.

**Spec:** `ci-hardening-design.md`

## Global Constraints

- **Python 3.11** everywhere. `requires-python = ">=3.11"`. Do not add other versions to any matrix — this app ships one frozen interpreter, so testing others tests something nobody runs.
- **`pywebview==6.2.1` stays exactly pinned.** `pyproject.toml` documents why. Do not relax it, do not let a lockfile refresh move it.
- **Do not widen what the credential check prints.** It currently prints lengths plus `client_id[-30:]` and `client_secret[:7]` (`build.yml`'s `Verify the injected credentials are well-formed`). That is mostly constant material — the ID's trailing `.apps.googleusercontent.com` is 27 of those 30 characters, and `GOCSPX-` is the secret's fixed prefix — so the real exposure is about three characters of client ID. Preserve exactly that, and never print a fuller value when moving the step.
- **Do not run `ruff format` before Task 5.** Tasks 1–4 must stay reviewable; a reformat mixed into them would bury the real change.
- **`packages = [...]` in `pyproject.toml` is explicit on purpose.** A missing subpackage installs cleanly and fails at import time inside the frozen build. Never replace it with auto-discovery.
- **The `AppId` in `packaging/installer.iss` must not change.** It is what makes the rename upgrade in place instead of installing a second copy.
- Baseline before any change: **1839 passed, 6 skipped** via `python -m pytest tests/ -q`.

## PR boundaries

Tasks map to pull requests as follows. Each PR is independently landable and revertable.

| PR | Tasks | Deliverable |
|----|-------|-------------|
| 1 | 1, 2 | Release path runs tests; build chain deduplicated |
| 2 | 3 | Tests run on Windows, green and blocking |
| 3 | 4, 5 | Ruff check and format adopted |
| 4 | 6 | Lockfile enforced; concurrency group |
| 5 | 7 | Dependabot, SHA-pinned actions, branch-protection checklist |

---

### Task 1: Gate the release path on the test suite

The hole this closes: `ci.yml` triggers on `push: branches: ["**"]` and `pull_request`. A tag push matches neither, and neither `release.yml` nor `build.yml` runs pytest. Pushing a tag today publishes a release having run zero tests.

**Files:**
- Modify: `.github/workflows/release.yml` (add a `test` job before `build`, add `needs:` to `build`)
- Modify: `.github/workflows/build.yml` (same)

**Interfaces:**
- Consumes: nothing.
- Produces: a job named `test` in both workflows. Task 7's branch-protection checklist refers to these job names.

- [ ] **Step 1: Read the current job headers so the edit lands in the right place**

Run: `sed -n '/^jobs:/,/steps:/p' .github/workflows/release.yml`

Expected: `jobs:`, then `build:` with `runs-on: windows-latest` and a `permissions: contents: write` block. Note the workflow-level `permissions: {}` above it — that grants the job token **no** permissions at all, not a read-only default. The new `test` job needs none (`actions/checkout` on a public repo works without a token scope), so give it no `permissions` block and let it inherit the empty set. If checkout ever fails there for want of a scope, add `permissions: {contents: read}` to that job alone rather than loosening the workflow-level default.

- [ ] **Step 2: Add the `test` job to `release.yml`**

Insert immediately after the `jobs:` line, *before* `build:`:

```yaml
  # The release path ran no tests at all before this job existed. ci.yml
  # triggers on `push: branches` and `pull_request`; a tag push matches
  # neither, so `git tag v3.2.2 && git push --tags` built an installer and
  # published a release without a single test having run.
  #
  # ubuntu-latest for now, DELIBERATELY, even though this ships a Windows
  # app. The suite has never run on Windows and is not yet green there;
  # putting windows-latest here would red both workflows immediately and
  # block Task 2 from proving the composite action. Task 3 fixes Windows
  # compatibility and then switches this job over. Closing the
  # zero-tests-on-release hole is worth having a platform-imperfect gate
  # in the meantime.
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: python -m pip install -e ".[dev]"
      - name: Test
        run: python -m pytest tests/ -v

```

- [ ] **Step 3: Make `build` depend on it**

In `release.yml`, change the `build:` job header from:

```yaml
  build:
    runs-on: windows-latest
    permissions:
      contents: write
```

to:

```yaml
  build:
    needs: test
    runs-on: windows-latest
    permissions:
      contents: write
```

- [ ] **Step 4: Do the same in `build.yml`**

Insert after `jobs:`, before `build:`:

```yaml
  test:
    # ubuntu-latest deliberately; see the note in release.yml. Task 3
    # switches both over once the suite is green on Windows.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: python -m pip install -e ".[dev]"
      - name: Test
        run: python -m pytest tests/ -v

```

Then change `build:`'s header from `  build:\n    runs-on: windows-latest` to:

```yaml
  build:
    needs: test
    runs-on: windows-latest
```

- [ ] **Step 5: Verify the YAML parses**

Run: `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/release.yml','.github/workflows/build.yml']]; print('both parse')"`

Expected: `both parse`

If `yaml` is not installed, run `python -m pip install pyyaml` first.

- [ ] **Step 6: Verify the dependency is actually declared**

Run: `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/release.yml')); print(d['jobs']['build']['needs']); print(list(d['jobs']))"`

Expected: `test` then `['test', 'build']`

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/build.yml
git commit -m "Run the tests before building or publishing

ci.yml triggers on branches and pull requests. A tag push matches
neither, so release.yml built an installer and published a GitHub
release having run zero tests. build.yml did not run them either.

Both now have a test job that build depends on, so Publish is
unreachable on red.

The job runs on ubuntu for now, deliberately, even though this ships a
Windows app: the suite has never run on Windows and is not green there
yet. A windows-latest job here would red both workflows immediately.
Closing the zero-tests-on-release hole is worth having a
platform-imperfect gate until the Windows work lands and switches it."
```

- [ ] **Step 8: Add the follow-up note so the ubuntu choice is not forgotten**

The `ubuntu-latest` above is a deliberate temporary state, and a temporary state with no reminder becomes permanent. Task 3 Step 7 switches it. Confirm that task exists and says so before moving on — if you are executing tasks out of order, this is the dependency to respect.

---

### Task 2: Extract the shared build chain into a composite action

`build.yml` (364 lines) and `release.yml` (311 lines) duplicate roughly 500 lines. They have already drifted: `build.yml` has eight `Verify` steps, `release.yml` has seven, and `Verify the app icon is bundled` exists only in `build.yml`. The credential-injection block has also lost its explanatory comment in `release.yml`.

**This task deliberately identifies steps by name, never by line number.** This repository is developed by parallel sessions and the line numbers in an earlier draft of this plan went stale within a day. If a step named below no longer exists, stop and report it rather than guessing at position.

**Files:**
- Create: `.github/actions/build-installer/action.yml`
- Modify: `.github/workflows/build.yml` (replace everything from `Install Inno Setup` through `Build installer` with one `uses:`)
- Modify: `.github/workflows/release.yml` (same range)

**Interfaces:**
- Consumes: the `test` job from Task 1 (unchanged by this task).
- Produces: `.github/actions/build-installer` with inputs `inject-credentials` (string `"true"`/`"false"`, default `"false"`), `oauth-client-id`, `oauth-client-secret`. Callers pass secrets explicitly — **a composite action cannot read `secrets.*` itself.**

- [ ] **Step 1: Confirm the two credential blocks differ only as expected**

Run:
```bash
sed -n '/- name: Inject OAuth credentials/,/Set-Content/p' .github/workflows/build.yml > /tmp/b.txt
sed -n '/- name: Inject OAuth credentials/,/Set-Content/p' .github/workflows/release.yml > /tmp/r.txt
diff /tmp/b.txt /tmp/r.txt
```

Expected: differences confined to the `if:` guard, the error-message wording, and a comment present only in `build.yml`. If you see a behavioral difference, stop and report it — the extraction assumes these are equivalent.

- [ ] **Step 2: Create the composite action scaffold**

Create `.github/actions/build-installer/action.yml` with this header, then fill the steps in Step 3:

```yaml
# Shared Windows build chain for build.yml and release.yml.
#
# These two workflows previously carried ~500 duplicated lines and had
# already drifted apart: the app-icon verification existed only in
# build.yml, so the workflow producing throwaway artifacts was STRICTER
# than the one that ships to users. One definition makes that class of
# bug impossible rather than merely unlikely.
#
# Secrets are inputs, not `secrets.*`. A composite action has no access
# to the calling repository's secrets; the caller must pass them.
name: Build installer
description: Fetch dependencies, freeze with PyInstaller, verify the bundle, and build the Inno Setup installer.

inputs:
  inject-credentials:
    description: 'Replace the OAuth placeholders in credentials.py. String "true" or "false", not a boolean — composite action inputs are always strings.'
    required: false
    default: "false"
  oauth-client-id:
    description: "OAuth client ID. Required when inject-credentials is true."
    required: false
    default: ""
  oauth-client-secret:
    description: "OAuth client secret. Required when inject-credentials is true."
    required: false
    default: ""

runs:
  using: composite
  steps:
```

- [ ] **Step 3: Move the steps in, in this exact order**

Copy each step **verbatim** from `build.yml` — it is the stricter and better-commented of the two — into the `steps:` list, in this order. Locate each by its `- name:` value.

| Order | Step name in `build.yml` |
|-------|--------------------------|
| 1 | `Install Inno Setup` |
| 2 | `Install dependencies` |
| 3 | `Verify the app's dependencies are importable` |
| 4 | `Inject OAuth credentials` |
| 5 | `Verify the injected credentials are well-formed` |
| 6 | `Warn that credentials are placeholders` |
| 7 | `Fetch ffmpeg` |
| 8 | `Fetch the AutoHotkey interpreter` |
| 9 | `Fetch the WebView2 bootstrapper` |
| 10 | `Verify the WebView2 bootstrapper is signed by Microsoft` |
| 11 | `Build executable` |
| 12 | `Show what PyInstaller produced` |
| 13 | `Verify the preview label font is bundled` |
| 14 | `Verify the web page is bundled` |
| 15 | `Verify the bookmark engine was collected` |
| 16 | `Verify the app icon is bundled` |
| 17 | `Verify the GPL notices are bundled` |
| 18 | `Build installer` |

Dump them in order to check nothing is missed:

```bash
grep -n '      - name:' .github/workflows/build.yml
```

**Before copying, diff the two files' versions of steps 2 and 3.** `release.yml`'s `Install dependencies` and `Verify the app's dependencies are importable` have their own wording and their own comments, and both files recently gained an `eveskills` importability check independently. Take the union of what the two check, not just `build.yml`'s copy — dropping a check that exists only in `release.yml` would weaken the release path, which is the exact failure this task exists to prevent.

Transformations, applied to every step as you move it:

1. **Add `shell:` to every `run:` step.** Composite actions have no default shell; a `run:` without one is a hard error. These are all PowerShell — use `shell: pwsh`. Steps that already declare `shell: pwsh` need no change.
2. **Rewrite the credential conditionals.** Inputs are strings here, so `if: ${{ inputs.inject_credentials }}` becomes `if: ${{ inputs.inject-credentials == 'true' }}`. Note the hyphen: the input is `inject-credentials`, not `inject_credentials`. Step 6 ("Warn that credentials are placeholders") inverts it: `if: ${{ inputs.inject-credentials != 'true' }}`.
3. **Rewrite the secret references.** `${{ secrets.OAUTH_CLIENT_ID }}` becomes `${{ inputs.oauth-client-id }}`, and `${{ secrets.OAUTH_CLIENT_SECRET }}` becomes `${{ inputs.oauth-client-secret }}`. Leave the `env:` block structure alone — passing them through `env:` is what keeps the values out of the command line and the logs.
4. **Do not move** `actions/checkout`, `actions/setup-python`, `Show what PyInstaller produced`'s dependence on anything outside the workspace, or the two `upload-artifact` steps. Checkout and setup-python stay in the calling workflow; the uploads are `build.yml`-only.

- [ ] **Step 4: Replace `build.yml`'s steps with a call**

`build.yml`'s `build` job steps become exactly this:

```yaml
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - uses: ./.github/actions/build-installer
        with:
          # Optional here, unlike release.yml: without secrets the
          # installer still builds and installs, and everything except
          # "Connect Google Account" is testable.
          inject-credentials: ${{ inputs.inject_credentials }}
          oauth-client-id: ${{ secrets.OAUTH_CLIENT_ID }}
          oauth-client-secret: ${{ secrets.OAUTH_CLIENT_SECRET }}

      - name: Upload installer
        uses: actions/upload-artifact@v4
        with:
          name: FlyGD-Wingman-installer
          path: packaging/Output/*.exe

      - name: Upload unpacked build
        uses: actions/upload-artifact@v4
        with:
          name: FlyGD-Wingman-unpacked
          path: dist/
```

Keep the existing `Upload installer` and `Upload unpacked build` steps' `with:` blocks exactly as they are in the current file rather than trusting the snippet above — read them and preserve their real values.

- [ ] **Step 5: Replace `release.yml`'s steps with a call**

`release.yml`'s `build` job steps become:

```yaml
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - uses: ./.github/actions/build-installer
        with:
          # Always true for a release: shipping an installer that cannot
          # sign in is worse than not shipping. The action throws if the
          # secrets are absent.
          inject-credentials: "true"
          oauth-client-id: ${{ secrets.OAUTH_CLIENT_ID }}
          oauth-client-secret: ${{ secrets.OAUTH_CLIENT_SECRET }}

      - name: Publish
        uses: softprops/action-gh-release@v2
```

Preserve the existing `Publish` step's `with:` block verbatim from the current file.

- [ ] **Step 6: Verify all three files still parse**

Run: `python -c "import yaml; [print(f, 'ok') for f in ['.github/workflows/build.yml','.github/workflows/release.yml','.github/actions/build-installer/action.yml'] if yaml.safe_load(open(f))]"`

Expected: three `ok` lines.

- [ ] **Step 7: Verify every `run:` in the composite action declares a shell**

Run: `python -c "
import yaml
d = yaml.safe_load(open('.github/actions/build-installer/action.yml'))
bad = [s.get('name','<unnamed>') for s in d['runs']['steps'] if 'run' in s and 'shell' not in s]
print('missing shell:', bad or 'none')
"`

Expected: `missing shell: none`

A `run:` step without `shell:` fails at runtime, not at parse time, so this check is the only thing standing between you and a red Windows run.

- [ ] **Step 8: Verify the icon check now applies to both workflows**

Run: `grep -c 'Verify the app icon is bundled' .github/actions/build-installer/action.yml .github/workflows/build.yml .github/workflows/release.yml`

Expected: `1`, `0`, `0` — the check now lives in exactly one place and both callers inherit it.

- [ ] **Step 9: Verify no secret is referenced from inside the action**

Run: `grep -nE '\$\{\{ *secrets\.' .github/actions/build-installer/action.yml || echo "no secrets expression - correct"`

Expected: `no secrets expression - correct`. A composite action silently resolves `secrets.*` to an empty string rather than erroring, which would produce an installer with placeholder credentials that builds green.

Match the **expression** `${{ secrets.` rather than the bare word `secrets.` — otherwise the check fires on the action's own header comment explaining that secrets are passed as inputs, and forces prose to be reworded to satisfy a grep.

- [ ] **Step 10: Commit**

```bash
git add .github/actions/build-installer/action.yml .github/workflows/build.yml .github/workflows/release.yml
git commit -m "Extract the shared Windows build chain into a composite action

build.yml and release.yml carried ~500 duplicated lines and had already
drifted: build.yml had eight Verify steps to release.yml's seven, and
'Verify the app icon is bundled' existed only in build.yml. The workflow
producing throwaway artifacts was stricter than the one that ships.
release.yml's copy of the credential injection had also lost the comment
explaining why replacement order matters.

The only real difference between the two was credential strictness, so
that becomes an inject-credentials input rather than two divergent
copies. Secrets are passed as inputs because a composite action cannot
read secrets.* -- and resolves them to empty strings rather than
failing, which would ship placeholder credentials in a green build."
```

- [ ] **Step 11: Prove it on the runner before trusting it**

`build.yml` is `workflow_dispatch` and exists precisely to exercise the Windows chain without publishing. Push the branch and trigger it:

```bash
git push -u origin HEAD
gh -R elboaf/FlyGD-Wingman workflow run build.yml --ref "$(git branch --show-current)" -f inject_credentials=false
```

Note `-R elboaf/FlyGD-Wingman` — this repository's PRs and workflows live on `elboaf`, not the `guarzo` fork you may be pushing from.

Watch it: `gh -R elboaf/FlyGD-Wingman run watch`

Expected: green, with an installer artifact attached. **Do not open the PR for this task until that run is green.** The composite action cannot be verified locally, and `release.yml` will depend on it.

---

### Task 3: Run the tests on Windows

The app is Windows-only and seven modules bind `windll` or `winreg`, but tests run on `ubuntu-latest` only. Six tests are gated off every non-Windows platform and have never executed anywhere, including the developer's WSL machine:

```
tests/test_eveskills_dpapi.py:44   requires real DPAPI
tests/test_eveskills_dpapi.py:51   requires real WinDLL
tests/test_preview_host.py:145     needs a real message pump and window station
tests/test_preview_win32.py:67     binds user32/gdi32/dwmapi
tests/test_preview_win32.py:81     binds user32/gdi32/dwmapi
tests/test_preview_win32.py:102    binds user32/gdi32/dwmapi
```

`test_preview_win32.py` asserts that every `user32`, `gdi32`, and `dwmapi` symbol the app binds actually resolves — the exact check for "did we typo a Win32 export that only fails on a user's machine". `test_eveskills_dpapi.py` covers DPAPI, which is how EVE SSO tokens are encrypted at rest. Both are currently dead code.

**Files:**
- Modify: `.github/workflows/ci.yml` (matrix the `test` job, split the text-assertion checks into their own job)
- Modify: various under `tests/` — determined empirically in Step 3

**Interfaces:**
- Consumes: nothing.
- Produces: CI job names `test (ubuntu-latest)`, `test (windows-latest)`, and `checks`. Task 7's branch-protection checklist names these exactly.

- [ ] **Step 1: Restructure `ci.yml` into two jobs**

Replace the entire `jobs:` block. The version-consistency and WebView2-predicate checks are text assertions over files, so they run once on ubuntu rather than twice.

```yaml
jobs:
  # Text assertions over files. No reason to pay for these twice.
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      # PASTE the existing "Check version consistency" step here verbatim
      # from the current ci.yml lines 17-38.
      # PASTE the existing "Check the WebView2 detection predicate agrees"
      # step here verbatim from the current ci.yml lines 39-77.

  test:
    # windows-latest is not redundant with ubuntu. Seven modules bind
    # windll/winreg, and tests/test_preview_win32.py -- which asserts every
    # user32/gdi32/dwmapi symbol the app binds actually resolves -- is
    # skipif'd off every other platform. Before this matrix it had never
    # executed anywhere, including the WSL dev machine.
    runs-on: ${{ matrix.os }}
    strategy:
      # One platform's failure must not cancel the other's run. Knowing
      # whether a failure is Windows-specific or universal is the whole
      # point of the matrix.
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"
      - name: Test
        run: python -m pytest tests/ -v
```

Copy the two check steps from the current file rather than retyping them — they contain a heredoc'd Python block and a set of exact GUID/registry tokens that must not be altered.

- [ ] **Step 2: Verify the workflow parses and has the shape you intended**

Run: `python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print('jobs:', list(d['jobs']))
print('matrix:', d['jobs']['test']['strategy']['matrix']['os'])
print('fail-fast:', d['jobs']['test']['strategy']['fail-fast'])
print('check steps:', [s.get('name') for s in d['jobs']['checks']['steps']])
"`

Expected:
```
jobs: ['checks', 'test']
matrix: ['ubuntu-latest', 'windows-latest']
fail-fast: False
check steps: [None, None, 'Check version consistency', 'Check the WebView2 detection predicate agrees']
```

If either check step is missing, you dropped it during the restructure. Recover it from `git show HEAD:.github/workflows/ci.yml`.

- [ ] **Step 3: Find out what actually breaks on Windows**

You cannot fix these locally — the dev machine is WSL. Push and read the run:

```bash
git add .github/workflows/ci.yml
git commit -m "wip: run the test suite on Windows too"
git push -u origin HEAD
gh -R elboaf/FlyGD-Wingman run watch
```

Then capture the failures:

```bash
gh -R elboaf/FlyGD-Wingman run view --log-failed > /tmp/win-failures.txt
grep -E '^(FAILED|ERROR)' /tmp/win-failures.txt | sort | uniq
```

Expected: some number of failures. 1839 tests have only ever seen POSIX.

- [ ] **Step 4: Fix each failure by category**

Do not add `skipif` markers to make failures disappear. A skipped test on the shipping platform is the exact problem this task exists to solve. Fix the cause. The likely categories, with the actual fix for each:

**Encoding.** Windows defaults `open()` to the ANSI code page, not UTF-8, so a file written with non-ASCII content reads back mangled or raises `UnicodeDecodeError`. The app's own text is full of `…` and `--`.

```python
# Before
path.write_text(content)
data = path.read_text()

# After
path.write_text(content, encoding="utf-8")
data = path.read_text(encoding="utf-8")
```

**Line endings.** `write_text` on Windows translates `\n` to `\r\n`, so a test asserting on exact bytes or line counts fails.

```python
# Before
assert path.read_text() == "a\nb\n"

# After — newline="" disables translation in both directions
assert path.read_text(encoding="utf-8", newline="") == "a\nb\n"
```

**Open file handles.** Windows refuses to delete or rename a file that is still open. `tmp_path` teardown then fails with `PermissionError` even though the test body passed.

```python
# Before
f = open(path, "w"); f.write(data)

# After
with open(path, "w", encoding="utf-8") as f:
    f.write(data)
```

**Path separators.** An assertion comparing against a hardcoded `/` string.

```python
# Before
assert str(result) == "/tmp/thing/file.mkv"

# After — compare Path objects, which normalise per platform
assert result == tmp_path / "thing" / "file.mkv"
```

**Case-insensitive filesystem.** A test asserting that `Foo.mkv` and `foo.mkv` are distinct files will fail. If this appears in `tests/test_evesettings_*.py` or `tests/test_library.py`, the *application* behaviour on Windows is what matters — treat a failure here as a possible real bug and report it rather than editing the assertion.

- [ ] **Step 5: Confirm the Linux suite did not regress**

Every fix above must be platform-neutral. Run locally:

Run: `python -m pytest tests/ -q`
Expected: `1839 passed, 6 skipped` — the same numbers as the baseline. A changed count means a fix altered behaviour rather than portability.

- [ ] **Step 6: Push and confirm Windows is green**

```bash
git push
gh -R elboaf/FlyGD-Wingman run watch
```

Expected: both matrix legs green.

Read the Windows leg's skip list:

```bash
gh -R elboaf/FlyGD-Wingman run view --log | grep -E 'SKIPPED|passed|skipped' | tail -20
```

**The skip set on Windows is different from the skip set on Linux, and it is not smaller.** Markers point both ways:

| Test | Marker | Runs on |
|------|--------|---------|
| `test_preview_win32.py` (3 tests) | `skipif(sys.platform != "win32")` | Windows only |
| `test_preview_host.py:145` | `skipif(sys.platform != "win32")` | Windows only |
| `test_eveskills_dpapi.py:44`, `:51` | `skipif(sys.platform != "win32")` | Windows only |
| `test_eveskills_dpapi.py:30`, `:38` | `skipif(sys.platform == "win32")` | Linux only |
| `test_evesettings_tree.py:121` | `skipif(os.name == "nt")` | Linux only |

So the acceptance criterion is: on the Windows leg, **the six Windows-only tests all run**, and exactly **three tests skip** (`dpapi:30`, `dpapi:38`, `evesettings_tree:121`). Any Windows-only test still skipping means the matrix is not doing its job.

Note that `test_preview_host.py:145` will now **execute** rather than skip. Its reason string — "needs a real message pump and window station" — describes what it requires, not a prediction that a runner lacks it. If it fails on GitHub's Windows runner because the service context provides no window station, that is a real finding: report it and decide whether to narrow the marker, rather than silently widening the skip.

- [ ] **Step 7: Switch the `test` jobs in `release.yml` and `build.yml` to Windows**

Task 1 deliberately left those on `ubuntu-latest` because Windows was not green. It is now. Change `runs-on: ubuntu-latest` to `runs-on: windows-latest` in the `test` job of **both** files, and update the comment Task 1 left there to say the switch has happened.

This is the step that makes the release gate test the platform it ships to. Do not skip it — Task 1's comment is written on the assumption that this step exists.

Run: `grep -A1 '^  test:' .github/workflows/release.yml .github/workflows/build.yml`
Expected: `runs-on: windows-latest` under both.

- [ ] **Step 8: Squash the WIP commit and write the real message**

```bash
git reset --soft "$(git merge-base HEAD origin/main)"
git add -A
git commit -m "Run the test suite on Windows

The app is Windows-only and seven modules bind windll or winreg, but
tests ran on ubuntu alone. Four tests marked skipif(sys.platform !=
'win32') had never executed anywhere -- not in CI, not on the WSL dev
machine. Among them, test_preview_win32.py asserts that every
user32/gdi32/dwmapi symbol the app binds actually resolves, which is
exactly the check for a typo that would only fail on a user's machine.
It was dead code.

Task 1's test jobs in release.yml and build.yml were deliberately left
on ubuntu until the suite was green here; this switches both to Windows,
so the release gate now tests the platform being shipped.

Also splits the version-consistency and WebView2-predicate checks into
their own ubuntu-only job. They are text assertions over files and there
is no reason to run them twice.

fail-fast is off so a Windows failure does not cancel the Linux leg;
knowing whether a break is platform-specific is the point of a matrix.

The test-suite fixes here are portability only -- encoding, newline
translation, and file-handle lifetime. The Linux run is unchanged at
1839 passed, 6 skipped."
```

---

### Task 4: Adopt `ruff check`

Nothing lints anything today: no ruff, black, flake8, mypy, pre-commit, or `.editorconfig`, across 16,160 lines of application Python and 21,590 lines of tests. With the rule selection below, ruff 0.16.4 finds 219 issues, 111 auto-fixable. The tree already contains fourteen `# noqa: BLE001` comments with explanations attached, so the convention exists.

Ruff also reports a **malformed `# noqa` directive at `obs_youtube_uploader/eveskills/controller.py:204`** — it is not valid syntax, so it currently suppresses nothing while looking like it does. Fixing that is part of this task.

**Ruff is pinned, and the version matters.** Rule sets and fix behaviour change between releases, so an unpinned ruff gives every contributor a different finding count and makes the numbers in this plan unreproducible. All counts here are ruff **0.16.4**. Do not run `uvx ruff@latest` — use the pinned version added in Step 1.

**Files:**
- Modify: `pyproject.toml` (add `[tool.ruff]`)
- Modify: `.github/workflows/ci.yml` (add a lint step to the `checks` job)
- Modify: various source files (the cleanup)

**Interfaces:**
- Consumes: the `checks` job from Task 3.
- Produces: `ruff check` passing clean. Task 5 depends on this being committed first.

- [ ] **Step 1: Add the ruff configuration**

Append to `pyproject.toml`, after the existing `[tool.pytest.ini_options]` section:

```toml
[tool.ruff]
target-version = "py311"
# 88 is ruff's default and already this codebase's shape: the longest
# line in the tree is 104 characters. Raising the limit to 100 does not
# reduce the reformat at all -- 149 files change either way -- and it
# would rejoin deliberately wrapped user-facing message strings into
# 97-character lines.
line-length = 88

[tool.ruff.lint]
select = [
    "I",      # import sorting
    "F",      # pyflakes
    "E", "W", # pycodestyle
    "UP",     # pyupgrade
    "SIM",    # flake8-simplify
    "RET",    # flake8-return
    "PIE",
    "FURB",
    "RUF",
    "BLE",    # blind except -- see below
    "DTZ",    # naive datetimes
    "S110",   # try-except-pass
    "S112",   # try-except-continue
]
ignore = [
    # The formatter owns line length. Selecting "E" pulls in E501, which
    # flags 84 lines here -- and `ruff format` CANNOT fix them, because it
    # will not split a long string or a comment. Leaving E501 enabled makes
    # the lint gate unsatisfiable without hand-rewrapping 84 sites for no
    # benefit the formatter does not already provide.
    "E501",
]
# Not selected, deliberately:
#   D    -- the docstrings here are unusually good and carry real
#           reasoning. A formal style gate would produce noise, not signal.
#   ANN  -- annotating 16k lines is its own project.
#   PL, C901 -- complexity thresholds would flag ui/api.py without
#           telling anyone something they do not already know.
#
# BLE001 is selected even though fifteen sites currently trip it,
# because fourteen OTHER sites already carry `# noqa: BLE001` with a
# reason attached. The convention exists; this makes it enforced. Every
# new suppression must state why the exception is swallowed.

[tool.ruff.lint.per-file-ignores]
# Tests legitimately bind values purely to assert on them later, and
# fixtures shadow imports by design.
"tests/*" = ["S110", "S112"]
```

Also pin ruff as a dev dependency in the same file, so the version is one thing rather than whatever each contributor's `uvx` resolves:

```toml
[project.optional-dependencies]
dev = ["pytest", "ruff==0.16.4"]
```

Then refresh the lockfile so the pin is real: `uvx uv lock` — and confirm `pywebview` is still exactly `6.2.1` in the diff before continuing.

- [ ] **Step 2: See the damage before touching anything**

Run: `uv run --extra dev ruff check --statistics .`

Expected: 219 findings, the largest groups being `I001` (30), `UP017` (25), `F401` (22), `SIM105` (20), and `BLE001` (15). You will also see a warning about the malformed `# noqa` in `eveskills/controller.py`.

If you get a materially different count, check which ruff you invoked. `uvx ruff@latest` is not the pinned version and will not reproduce these numbers.

- [ ] **Step 3: Apply the safe automatic fixes**

Run: `uv run --extra dev ruff check --fix .`

Expected: about 111 findings resolved. Do **not** pass `--unsafe-fixes`; the 40 fixes behind that flag change behaviour and each needs an individual decision.

- [ ] **Step 4: Confirm the auto-fixes broke nothing**

Run: `python -m pytest tests/ -q`
Expected: `1839 passed, 6 skipped`

This is the entire safety argument for an automated fix pass across 149 files. If the count changed, run `git diff` and find out which fix did it before going further.

- [ ] **Step 5: Commit the automatic pass separately**

Keeping it alone makes the hand-written pass in Step 6 reviewable.

```bash
git add -A
git commit -m "Apply ruff's automatic fixes

Mechanical: import sorting, unused imports, unused noqa directives,
datetime.timezone.utc over the deprecated alias, f-strings over
printf-style formatting. No behaviour change; the suite is unchanged at
1839 passed, 6 skipped.

Kept separate from the hand-written fixes so those stay reviewable."
```

- [ ] **Step 6: Fix the remaining findings by hand**

Run: `uv run --extra dev ruff check --output-format concise .` and work the list. The categories and their fixes:

**`F821` at `obs_youtube_uploader/ui/window.py:158`** — not a live bug. The signature is `def create(api) -> "webview.Window"`; the annotation is a string and is never evaluated, and `webview` is imported lazily inside the function for documented reasons. Make the intent explicit:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - the import is real only to type checkers
    import webview
```

Place this after the existing `from pathlib import Path` import and before the `obs_youtube_uploader.ui` import. Do **not** move the runtime import out of the function body — the module docstring explains that importing pywebview at module scope runs its import-time setup on machines where that is wrong.

**`BLE001`, 15 sites** — each gets a `# noqa: BLE001` with a reason, matching the existing house style. Read what the handler actually does and describe it:

```python
# Existing examples in the tree, for tone:
except Exception as exc:  # noqa: BLE001 - reported, never raised
except Exception:  # noqa: BLE001 - a pill, never a failure
except Exception:  # noqa: BLE001 - names are cosmetic
```

If a site turns out to swallow an error that should propagate, **stop and report it** rather than suppressing. That is a real bug and does not belong in a lint commit.

**`DTZ`, 9 sites** — naive datetimes. These feed the upload flow, so read each one. Where a timestamp is compared or serialised, make it timezone-aware:

```python
# Before
datetime.now()
datetime.utcfromtimestamp(ts)

# After
datetime.now(tz=timezone.utc)
datetime.fromtimestamp(ts, tz=timezone.utc)
```

Where a naive local time is genuinely intended — a filename stamp a user reads — suppress with a reason: `# noqa: DTZ005 - local wall-clock, shown to the user`.

**`S110` / `S112`, 4 sites** — `try/except/pass` and `try/except/continue`. Same rule as `BLE001`: add a reason, or fix it if the silence is wrong.

**`F841`, 4 sites** — including `WNDPROC` in `preview/win32.py`. Careful: a ctypes callback assigned to a local and never referenced is a **use-after-free waiting to happen**, because the callback must outlive the window. If that is what this is, the fix is to keep a module-level reference, not to delete the line. Read the surrounding code before touching it.

**The malformed `# noqa` at `eveskills/controller.py:204`** — ruff warns that it is not a comma-separated list of codes, which means it suppresses nothing today. Read what the line actually trips and write the directive properly: `# noqa: <CODE> - <reason>`. If it turns out to suppress nothing because there is nothing to suppress, delete it.

- [ ] **Step 7: Verify clean and green**

Run: `uv run --extra dev ruff check .`
Expected: `All checks passed!`

Run: `python -m pytest tests/ -q`
Expected: `1839 passed, 6 skipped`

- [ ] **Step 8: Add the lint step to CI**

In `.github/workflows/ci.yml`, append to the `checks` job's steps. Use the pinned ruff from the dev extra rather than `ruff-action`'s bundled copy, so CI and local runs cannot disagree about what is a finding:

```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Lint
        # The pinned ruff from [project.optional-dependencies] dev, not
        # ruff-action's own copy: a version skew between CI and a
        # contributor's machine turns "lint is green locally" into a
        # coin flip.
        run: |
          uv sync --locked --extra dev
          uv run --extra dev ruff check --output-format github
```

`--output-format github` makes findings appear as inline annotations on the pull request rather than only in the log.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Fix the remaining ruff findings by hand, and lint in CI

Blind excepts get a reason comment each, matching the ten sites that
already carried one. Naive datetimes feeding the upload flow become
timezone-aware; the ones deliberately showing local wall-clock time to
the user are suppressed with that stated.

The F821 on ui/window.py was never a live bug -- the annotation is a
string and pywebview is imported lazily on purpose -- so it becomes a
TYPE_CHECKING import that says so rather than a behaviour change.

1839 passed, 6 skipped, unchanged."
```

---

### Task 5: Adopt `ruff format`

149 of 176 files reformat. Ruff does not reflow docstrings or comment prose, so the long explanatory blocks throughout this codebase survive untouched; what changes is code style, chiefly hand-aligned call continuations becoming one argument per line.

**Files:**
- Create: `.git-blame-ignore-revs`
- Modify: `README.md` (document the blame config)
- Modify: `.github/workflows/ci.yml` (add the format check)
- Modify: 149 source files (mechanical)

**Interfaces:**
- Consumes: Task 4's committed lint fixes. Running format first would make Task 4's diff unreadable.
- Produces: a formatted tree and a `.git-blame-ignore-revs` containing the format commit's SHA.

- [ ] **Step 1: Confirm Task 4 is committed and the tree is clean**

Run: `git status --porcelain`
Expected: empty output. A reformat on top of uncommitted work is unreviewable and unrevertable.

- [ ] **Step 2: Fix the over-length trailing comments first**

A long trailing comment pushes a short statement past 88, and the formatter responds by parenthesising the value — which is worse than what it replaced:

```python
# What the formatter would produce, left alone:
CHUNK_SIZE = (
    4 * 1024 * 1024
)  # Consumed by app._upload_one when building MediaFileUpload.
```

Find them:

```bash
find obs_youtube_uploader tests -name '*.py' | xargs awk 'length>88 && /  #/ {print FILENAME":"FNR": "$0}'
```

Expected: about **two** sites. Most over-length lines in this tree are long because the *code* is long, and the formatter handles those correctly — only the trailing-comment ones misbehave.

For each, move the comment above the statement:

```python
# Consumed by app._upload_one when building MediaFileUpload.
CHUNK_SIZE = 4 * 1024 * 1024
```

The line is then short and the formatter leaves it alone permanently.

- [ ] **Step 3: Commit the comment moves separately**

```bash
git add -A
git commit -m "Move over-length trailing comments above their statements

ruff format would otherwise parenthesise the value to fit the comment,
which reads worse than the original. Moving the comment up makes the
line short and the formatter leaves it alone permanently."
```

- [ ] **Step 4: Run the formatter**

Run: `uv run --extra dev ruff format .`
Expected: `149 files reformatted, 27 files left unchanged` (approximately — Steps 2–3 may shift this slightly).

- [ ] **Step 5: Verify nothing broke**

Run: `python -m pytest tests/ -q`
Expected: `1839 passed, 6 skipped`

That the suite is unchanged is the whole safety argument for a 149-file mechanical rewrite. Anything else, stop.

Run: `uv run --extra dev ruff check .`
Expected: `All checks passed!` — the formatter must not have reintroduced lint findings.

- [ ] **Step 6: Commit the format pass alone, touching nothing else**

This commit must contain *only* mechanical reformatting, because its SHA is about to be permanently ignored by `git blame`. Anything hidden here becomes invisible to future archaeology.

```bash
git add -A
git commit -m "Apply ruff format

Mechanical reformat of 149 of 176 files, no behaviour change: 1839
passed, 6 skipped, unchanged. Docstrings and comment prose are untouched
-- ruff does not reflow them -- so the explanatory blocks throughout the
codebase survive as written. What changes is code style, chiefly
hand-aligned call continuations becoming one argument per line.

This commit is recorded in .git-blame-ignore-revs and contains nothing
but formatting."
```

- [ ] **Step 7: Record the SHA so `git blame` stays useful**

**Read this before running it: the SHA you record must be the one that ends up on `main`.**

A squash merge rewrites the format commit into a brand-new SHA, and the entry you write here then points at a commit that exists nowhere in `main`'s history. `git blame` ignores it silently — no error, no warning — and every one of the 149 files is attributed to the reformat anyway. A rebase merge rewrites the SHA too.

Two ways to get this right; pick one and be deliberate:

**A — merge commit (simplest).** Merge this PR with a true merge commit, not squash and not rebase. The format commit's SHA survives, so recording it now works:

```bash
FORMAT_SHA=$(git rev-parse HEAD)
printf '# Mechanical reformats. Configure once with:\n#   git config blame.ignoreRevsFile .git-blame-ignore-revs\n\n# Adopt ruff format across the tree (149 of 176 files, no behaviour change)\n%s\n' "$FORMAT_SHA" > .git-blame-ignore-revs
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

**B — squash or rebase merge.** Write the file with a placeholder now, merge, then push one follow-up commit to `main` replacing it with the post-merge SHA read from `git log`. This is two steps and easy to forget, which is why A is preferred.

Whichever you choose, say so explicitly in the PR description. A reviewer clicking the default merge button is exactly how this breaks.

- [ ] **Step 8: Verify blame actually skips it**

Run: `git blame -L 1,5 obs_youtube_uploader/uploader.py | cut -c1-40`

Expected: the commits shown are the ones that wrote those lines, **not** the format commit. If the format SHA appears, the config or the file is wrong.

**Re-run this same check after the PR merges.** Passing locally proves only that the pre-merge SHA is correct; it says nothing about whether the SHA survived the merge. This is the check that catches a squash.

- [ ] **Step 9: Document the config in the README**

The `blame.ignoreRevsFile` setting is per-clone; it does not travel with the repository. Every contributor must run it once or their blame output is useless. Add to `README.md` under whatever development or contributing section exists (create one if there is none):

```markdown
### After cloning

```
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Without this, `git blame` attributes 149 files to the ruff-format commit
rather than to whoever wrote the code. The setting is per-clone and
cannot be committed.
```

- [ ] **Step 10: Add the format check to CI**

In `.github/workflows/ci.yml`, add to the `checks` job after the `Lint` step. Same pinned ruff, same reason:

```yaml
      - name: Format
        run: uv run --extra dev ruff format --check --diff
```

`--diff` prints what differs, so a failure tells the contributor exactly what to run rather than only that something is wrong.

- [ ] **Step 11: Commit**

```bash
git add .git-blame-ignore-revs README.md .github/workflows/ci.yml
git commit -m "Ignore the format commit in blame, and check format in CI

blame.ignoreRevsFile is per-clone and cannot be committed, so the README
documents the one-time command. Without it, blame attributes 149 files
to a mechanical reformat instead of to their authors."
```

---

### Task 6: Enforce the lockfile

`uv.lock` is committed at 162KB and no workflow uses it — every one runs `pip install -e .` and resolves fresh. Dependencies are unpinned except `pywebview==6.2.1`, whose pin carries a comment explaining exactly why pinning matters here.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/actions/build-installer/action.yml`
- Modify: `.github/workflows/release.yml`, `.github/workflows/build.yml` (the Task 1 `test` jobs)

**Interfaces:**
- Consumes: the composite action from Task 2, the matrix from Task 3.
- Produces: `uv sync --locked` as the install path everywhere. Task 7's Dependabot config depends on this.

- [ ] **Step 1: Confirm the lockfile matches `pyproject.toml` before relying on it**

Run: `uvx uv lock --check`

Expected: confirmation that the lockfile is up to date. If it reports drift, run `uvx uv lock`, inspect the diff, and **verify `pywebview` is still exactly `6.2.1`** before committing — the pin is load-bearing and a refresh must not move it.

- [ ] **Step 2: Confirm the dev dependency group resolves**

Run: `uvx uv sync --locked --extra dev --dry-run`
Expected: a resolution including `pytest`, with no error.

- [ ] **Step 3: Switch `ci.yml` to uv**

In both the `checks` and `test` jobs, replace the `actions/setup-python` and `Install` steps with:

```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install
        # --locked, not --frozen: --locked fails if uv.lock disagrees with
        # pyproject.toml, which is the whole point. --frozen would install
        # a stale lockfile silently.
        run: uv sync --locked --extra dev
```

Then prefix the test invocation so it runs inside the synced environment:

```yaml
      - name: Test
        run: uv run --no-sync pytest tests/ -v
```

`--no-sync` because the previous step already synced; without it uv re-resolves on every invocation.

- [ ] **Step 4: Switch the `test` jobs in `release.yml` and `build.yml`**

Apply the identical three-step replacement from Step 3 to the `test` job Task 1 added to each file.

- [ ] **Step 5: Switch the composite action's install step**

**This is the step most likely to be got wrong.** `uv sync` installs into a
`.venv`, which a bare `python` — the one `actions/setup-python` put on `PATH` —
does not see. Every subsequent command in the action that runs Python must go
through `uv run`, or it will execute against an interpreter with none of the
app's dependencies installed. That failure does not stop the build: the import
checks fail confusingly, or PyInstaller freezes an application missing its
dependencies. `build.yml`'s own comments record that exact outcome happening
once before.

In `.github/actions/build-installer/action.yml`, add the uv installation as a
new step immediately before `Install dependencies`:

```yaml
    - name: Install uv
      uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
```

Then replace the `Install dependencies` step's body. Preserve the existing
`$LASTEXITCODE` checking — its comment records that a failed install previously
produced a green step and a frozen app with no pystray in it:

```yaml
    - name: Install dependencies
      shell: pwsh
      run: |
        # $ErrorActionPreference alone does NOT catch a native command's
        # non-zero exit, and a multi-line run: block keeps going after one.
        # That is how a failed install previously produced a green step, no
        # pystray in the environment, and a frozen app that crashed on
        # launch. Check every exit code explicitly.
        uv sync --locked
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed - the app's dependencies are missing" }
        # PyInstaller goes INTO the synced environment, not alongside it.
        # `uv pip install` without --active would target a different prefix.
        uv pip install --python .venv "pyinstaller>=6,<7"
        if ($LASTEXITCODE -ne 0) { throw "pyinstaller install failed" }
```

- [ ] **Step 5b: Route every remaining Python invocation through `uv run`**

This is the other half of Step 5 and must not be skipped. Rewrite each of these
steps in the composite action:

- `Verify the app's dependencies are importable` — every `python -c "..."` becomes `uv run python -c "..."`.
- `Verify the injected credentials are well-formed` — this uses `shell: python`, which runs the *runner's* interpreter and imports `obs_youtube_uploader.credentials`. Change it to `shell: pwsh` invoking `uv run python - <<'PY' ... PY`, or move the script to a file and call `uv run python packaging/verify_credentials.py`. Preserve every check it performs.
- `Build executable` — `pyinstaller ...` becomes `uv run pyinstaller ...`.

Find any you missed:

```bash
grep -nE '^\s+(python|pyinstaller)\b|shell: python' .github/actions/build-installer/action.yml
```

Expected: no output. Every hit is a command about to run against the wrong interpreter.

- [ ] **Step 5c: Prove the interpreter is the synced one**

Add a step to the composite action immediately after `Install dependencies`:

```yaml
    - name: Verify uv run reaches the synced environment
      # Guards the whole class of bug in Step 5b: if any later step drops the
      # `uv run` prefix it silently uses the setup-python interpreter, which
      # has none of the app's dependencies. Fail here, where it is obvious.
      shell: pwsh
      run: |
        uv run python -c "import sys, pystray, webview; print(sys.executable)"
        if ($LASTEXITCODE -ne 0) { throw "uv run cannot import the app's dependencies - the sync did not take" }
```

- [ ] **Step 6: Verify no `pip install` survives anywhere**

Run: `grep -rn 'pip install' .github/ || echo "none remaining"`

Expected: either `none remaining`, or only the `uv pip install` for PyInstaller — which is correct, since PyInstaller is a build tool and deliberately not a project dependency.

- [ ] **Step 7: Add the concurrency group**

At the top of `.github/workflows/ci.yml`, after the `on:` block:

```yaml
# A push to a busy branch cancels its own superseded runs. Scoped by ref
# so unrelated branches never cancel each other.
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Do **not** add this to `release.yml`. Cancelling a half-finished publish is a genuinely bad idea.

- [ ] **Step 8: Verify everything parses**

Run: `python -c "
import yaml, glob
for f in glob.glob('.github/workflows/*.yml') + glob.glob('.github/actions/*/action.yml'):
    yaml.safe_load(open(f)); print(f, 'ok')
"`

Expected: four `ok` lines.

- [ ] **Step 9: Commit and confirm on the runner**

```bash
git add -A
git commit -m "Install from the lockfile instead of resolving fresh

uv.lock was committed at 162KB and every workflow ignored it, running
pip install -e . and resolving whatever it found that day. Dependencies
are unpinned apart from pywebview, so a transitive break would have
arrived as mysteriously red CI on an unrelated change -- or as a bad
installer.

--locked rather than --frozen: --locked fails when uv.lock and
pyproject.toml disagree, which is the property worth having.

ci.yml also gains a concurrency group. release.yml deliberately does
not: cancelling a half-finished publish is worse than paying for it."
git push
gh -R elboaf/FlyGD-Wingman run watch
```

Expected: green on both matrix legs. Trigger `build.yml` as in Task 2 Step 11 to confirm the Windows build chain still installs correctly.

---

### Task 7: Dependabot, SHA-pinned actions, and the branch-protection checklist

Only useful now that the lockfile is enforced — that is what gives Dependabot something to bump. No auto-merge, either ecosystem.

**Files:**
- Create: `.github/dependabot.yml`
- Create: `docs/branch-protection.md`
- Modify: all four workflow/action files (SHA pinning)

**Interfaces:**
- Consumes: Task 6's enforced lockfile; the job names `checks`, `test (ubuntu-latest)`, `test (windows-latest)` from Task 3.
- Produces: nothing downstream.

- [ ] **Step 1: Create the Dependabot configuration**

Create `.github/dependabot.yml`:

```yaml
# Useful only because uv.lock is enforced (see ci-hardening-design.md);
# before that there was no pinned version for anything to bump.
#
# No auto-merge, either ecosystem. For runtime dependencies this is not a
# close call: they are frozen into an installer and shipped, and the
# automated gate cannot validate them. docs/smoke-checklist.md states that
# the UI is untested by pytest and the checklist is the only verification
# it gets, so green CI on a pywebview bump means the headless bridge tests
# passed -- not that the application renders. pyproject.toml already
# records the rule: an upgrade is "a change requiring a full smoke pass,
# not a routine bump."
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      # One pull request a week, not five.
      actions:
        patterns: ["*"]
    commit-message:
      prefix: "ci"

  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      python:
        patterns: ["*"]
    commit-message:
      prefix: "deps"
    # pywebview is NOT ignored, deliberately. The pin is exact and an
    # upgrade needs a full smoke pass, but a security fix nobody hears
    # about is worse than a pull request nobody merges.
```

- [ ] **Step 2: Verify the ecosystem identifier is actually `uv`**

The spec flags this as unverified. Confirm before relying on it:

Run: `gh -R elboaf/FlyGD-Wingman api repos/elboaf/FlyGD-Wingman/dependabot/alerts --silent 2>&1 | head -2` — this only checks access, not the schema.

The reliable check is the file itself. Push the branch and look at the repository's Insights → Dependency graph → Dependabot tab. An invalid `package-ecosystem` surfaces there as a config error rather than failing any workflow.

If `uv` is rejected, fall back to `package-ecosystem: "pip"`, which covers the Python ecosystem broadly, and note in the file's comment that uv-native support was unavailable.

- [ ] **Step 3: Pin every action to a commit SHA**

Dependabot maintains these with a readable version comment, so pinning costs nothing ongoing. Collect the current SHAs:

```bash
for spec in actions/checkout@v4 actions/setup-python@v5 actions/upload-artifact@v4 astral-sh/setup-uv@v5 softprops/action-gh-release@v2; do
  repo="${spec%@*}"; ref="${spec#*@}"
  sha=$(gh api "repos/$repo/commits/$ref" --jq .sha)
  echo "$repo@$sha # $ref"
done
```

Replace each `uses:` across all four files with the pinned form, keeping the version as a trailing comment:

```yaml
      - uses: actions/checkout@<sha>  # v4
```

Leave `uses: ./.github/actions/build-installer` unpinned — it is a local path, not a third-party action.

- [ ] **Step 4: Verify no unpinned third-party action remains**

Run: `grep -rn 'uses:' .github/ | grep -v '@[0-9a-f]\{40\}' | grep -v './.github/'`

Expected: no output.

- [ ] **Step 5: Write the branch-protection checklist**

This cannot be committed as configuration — it is a repository setting. Create `docs/branch-protection.md`:

```markdown
# Branch protection

These are repository settings, not files, so they cannot be committed and
must be applied by hand. Without them the CI added in `ci-hardening-plan.md`
reports but does not gate: a pull request with a red Windows leg is still
mergeable.

Apply at **Settings → Branches → Add branch ruleset**, targeting `main`.

## Required status checks

Require these to pass before merging, with "Require branches to be up to
date before merging" enabled:

- `checks`
- `test (ubuntu-latest)`
- `test (windows-latest)`

**`test (windows-latest)` is the one that matters most and the easiest to
omit.** It is the only place `tests/test_preview_win32.py` executes, and
that file is what catches a mistyped Win32 export before a user does.

## Also enable

- Require a pull request before merging.
- Block force pushes.
- Restrict deletions.

## Deliberately not enabled

- **Auto-merge.** See `ci-hardening-design.md` §6. Runtime dependencies
  ship frozen into an installer and the UI has no automated verification
  at all, so a green build says nothing about whether the app renders.
- **Required approvals.** A solo-maintained repository; this would only
  block the maintainer.

## Verify it works

Open a pull request with a deliberately failing test and confirm the merge
button is blocked. A required check whose name does not exactly match a
job name silently never runs, and GitHub shows this as "waiting for status
to be reported" — which looks like a pending check rather than a
misconfiguration.
```

- [ ] **Step 6: Verify the job names in the checklist match reality**

The names must match exactly or the protection silently never applies.

Run: `python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
for name, job in d['jobs'].items():
    m = job.get('strategy', {}).get('matrix', {}).get('os')
    print('\n'.join(f'{name} ({o})' for o in m) if m else name)
"`

Expected:
```
checks
test (ubuntu-latest)
test (windows-latest)
```

These three strings must appear verbatim in `docs/branch-protection.md`. Fix either side if they disagree.

- [ ] **Step 7: Commit**

```bash
git add .github/dependabot.yml docs/branch-protection.md .github/workflows/ .github/actions/
git commit -m "Add Dependabot, pin actions by SHA, document branch protection

Dependabot is useful only now that uv.lock is enforced. Updates are
grouped so the result is one pull request per ecosystem per week.

No auto-merge, either ecosystem. Runtime dependencies are frozen into an
installer and shipped, and docs/smoke-checklist.md states plainly that
the UI is untested by pytest -- green CI on a pywebview bump means the
headless bridge tests passed, not that the app renders. pywebview is
still not ignored: a security fix nobody hears about is worse than a
pull request nobody merges.

Actions are pinned by SHA, which Dependabot now maintains with a version
comment, so the supply-chain pin costs no readability.

Branch protection is a repository setting and cannot be committed, so it
ships as a checklist. The required checks must include the Windows leg
or the gate is decorative."
```

- [ ] **Step 8: Hand off the manual step**

Tell the maintainer explicitly that `docs/branch-protection.md` needs applying by hand, and that until it is, every check added by this plan reports without gating.

---

## Verification summary

| What | How | Expected |
|------|-----|----------|
| Suite unchanged throughout | `python -m pytest tests/ -q` | `1839 passed, 6 skipped` |
| Lint clean | `uv run --extra dev ruff check .` | `All checks passed!` |
| Format clean | `uv run --extra dev ruff format --check .` | `176 files already formatted` |
| Ruff is the pinned version | `uv run --extra dev ruff --version` | `ruff 0.16.4` |
| Lockfile agrees | `uvx uv lock --check` | up to date |
| Workflows parse | the `yaml.safe_load` loop in Task 6 Step 8 | four `ok` lines |
| Composite action uses the synced interpreter | `grep -nE '^\s+(python\|pyinstaller)\b\|shell: python' .github/actions/build-installer/action.yml` | no output |
| Windows chain works | `gh -R elboaf/FlyGD-Wingman workflow run build.yml` | green, installer artifact |
| Win32 tests execute | Windows leg's skip list | six Windows-only tests run; exactly three skip |
| Blame ignores the reformat | `git blame` after merge, not just before | format SHA absent |

Tasks 1, 2, 6, and 7 change CI itself and cannot be fully verified without pushing. `build.yml` is `workflow_dispatch` and exists to exercise the Windows chain without publishing — use it as the proving ground before `release.yml` depends on anything.

The manual smoke checklist in `docs/smoke-checklist.md` is unaffected by all of this and remains the only verification the UI gets.
