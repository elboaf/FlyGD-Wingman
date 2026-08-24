# CI hardening design

Verification in this repository is thorough where someone got burned and
absent everywhere else. Every check in `ci.yml` is a scar: the
version-consistency check exists because three files declare the version
independently, the WebView2-predicate check exists because the installer
and the app must ask the same question in two languages that cannot share
code. Both are good checks.

The gaps are the places nobody has been bitten yet. This document covers
six of them, in the order their absence costs the most.

## 1. The release path runs no tests

`ci.yml` triggers on `push: branches: ["**"]` and `pull_request`. A tag
push matches neither. `release.yml` triggers on `push: tags: ["v*"]` and
contains no `pytest` invocation; neither does `build.yml`.

The consequence: `git tag v3.2.2 && git push --tags` builds an installer
and publishes a GitHub release having run zero tests. The suite gates
branches. It does not gate what users download.

**Change.** Both `release.yml` and `build.yml` gain a `test` job; their
`build` job declares `needs: test`. `Publish` becomes unreachable on red.

This is the only change here that would have prevented a shipped
regression, so it lands first regardless of what else slips.

## 2. The two Windows workflows have already drifted

`build.yml` and `release.yml` share roughly 500 lines of copy-pasted
sequence: dependency install, importability verification, ffmpeg /
AutoHotkey / WebView2 fetches, signature check, PyInstaller invocation,
bundle verification, Inno Setup build.

They are no longer identical. `build.yml` has eight `Verify` steps;
`release.yml` has seven. `Verify the app icon is bundled` exists only in
`build.yml` — the workflow producing throwaway artifacts is stricter than
the one that ships. This is the predictable failure mode of duplication,
and it is not hypothetical.

**Change.** Extract the shared sequence into
`.github/actions/build-installer/action.yml`. Both workflows call it.

The only genuine difference between them is credential strictness:
`build.yml` treats a missing OAuth secret as a warning, `release.yml` as a
hard failure. That becomes an `inject-credentials` input rather than two
divergent copies. The drifted icon check comes along for free and applies
to both.

## 3. Tests never run on the platform that ships

The app is Windows-only. Seven modules bind `windll` or `winreg`. Tests
run on `ubuntu-latest` only.

Six tests are gated off every non-Windows platform and have never executed
anywhere — not in CI, not on the development machine, which is WSL:

    tests/test_eveskills_dpapi.py:44   requires real DPAPI
    tests/test_eveskills_dpapi.py:51   requires real WinDLL
    tests/test_preview_host.py:145     needs a real message pump and window station
    tests/test_preview_win32.py:67     binds user32/gdi32/dwmapi
    tests/test_preview_win32.py:81     binds user32/gdi32/dwmapi
    tests/test_preview_win32.py:102    binds user32/gdi32/dwmapi

`test_preview_win32.py` asserts that every `user32`, `gdi32`, and `dwmapi`
symbol the app binds actually resolves. That is precisely the "did we typo
a Win32 export that only fails on a user's machine" check, and it is
currently dead code. `test_eveskills_dpapi.py` covers DPAPI, which is how
EVE SSO tokens are encrypted at rest — a path where a silent failure has
real consequences.

`test_preview_wiring.py:103` states the gap directly:

> The `sys.platform` guard means this function's body never runs in CI, so
> a NameError or a wrong import inside it would ship silently and only fail
> on a user's Windows machine.

Someone identified this and worked around it with a monkeypatch. A Windows
runner closes it for real.

**Change.** `ci.yml`'s `test` job becomes a matrix over `ubuntu-latest`
and `windows-latest`, both on Python 3.11. The version-consistency and
WebView2-predicate checks stay in a separate ubuntu-only job — they are
text assertions over files and there is no reason to pay for them twice.

**Known cost.** The first Windows run will likely be red: 1839 tests have
only ever seen POSIX. Spot-checking suggests this is better than average
(`Path("/x") / name` behaves on Windows, `/usr/bin/ffmpeg` is only ever an
opaque string, and `test_evesettings_tree.py:121` already carries a
`skipif(os.name == "nt")` for symlink semantics), but expect work on
tempfile handling and `open()` calls without an explicit encoding. That
cleanup lands in the same change, so the job arrives green and blocking
rather than as a non-blocking check that stays non-blocking forever.

Note that the skip set on Windows is different, not smaller: three tests
skip there (`test_eveskills_dpapi.py:30` and `:38`, which cover the
non-Windows fallback, and `test_evesettings_tree.py:121`, which asserts
POSIX symlink semantics). `test_preview_host.py:145` will **execute**
rather than skip — its stated need for a real message pump and window
station describes a requirement, not a prediction that the runner lacks
one. Whether GitHub's service-context runners satisfy it is an open
question this change answers empirically.

## 4. Nothing lints anything

No ruff, black, flake8, mypy, pre-commit, or `.editorconfig`. 16,160 lines
of application Python, 21,590 lines of tests, and 4,410 lines of web assets
with no automated checking. `ui/api.py` alone is over 2,000 lines.

With the rule selection below, ruff **0.16.4** finds 219 issues, 111 of
them auto-fixable. The version is stated because it matters: rule sets and
fix behaviour move between releases, so ruff is pinned as a dev dependency
rather than invoked as `ruff@latest`. An unpinned linter gives every
contributor a different answer and makes any number recorded here a
fiction.

The tree already contains fourteen `# noqa: BLE001` comments with real
explanations attached — someone has run ruff here before and reasoned
about its output. Adoption is much cheaper than a cold start.

Ruff also reports a malformed `# noqa` directive in
`eveskills/controller.py` that is not valid syntax, and therefore suppresses
nothing while appearing to.

**Change.** A `[tool.ruff]` section in `pyproject.toml` targeting `py311`,
with rules selected against what is actually present:

- **Enable and auto-fix:** `I`, `F`, `E`, `W`, `UP`, `SIM`, `RET`, `PIE`,
  `FURB`, `RUF`. The large majority of the 219 findings.
- **Enabled by `E` but ignored:** `E501`, line-too-long. Selecting `E`
  pulls it in and it flags 84 lines — and `ruff format` cannot fix a single
  one, because it will not split a long string or a comment. Leaving it on
  would make the lint gate unsatisfiable without hand-rewrapping 84 sites
  for a benefit the formatter already provides. The formatter owns line
  length; the linter should not also have an opinion about it.
- **Enable, convention already exists:** `BLE001`. Thirteen unsuppressed
  sites, ten already carrying explained `noqa`s. Each new suppression gets
  a reason comment, matching the existing house style rather than
  inventing one.
- **Enable, fix by hand:** `DTZ` (nine naive-datetime sites, worth real
  attention since timestamps feed the upload flow) and `S110`/`S112`
  (four silent-swallow sites).
- **Do not enable:** `D`, `ANN`, `PL`, `C901`. The docstrings in this
  codebase are unusually good and a formal style gate would produce noise,
  not signal.

`ruff format` is adopted, at the default line length of 88.

The width is not arbitrary: the longest line in the tree is 104
characters, so the code already sits close to this shape. Raising the
limit to 100 does not reduce the blast radius at all — 149 files reformat
either way — and it would rejoin deliberately wrapped user-facing message
strings into 97-character lines.

The cost is real and worth stating plainly: 149 of 176 files are
reformatted. Ruff does **not** reflow docstrings or comment prose, so the
long explanatory blocks throughout this codebase survive untouched — what
changes is code style, chiefly hand-aligned call continuations becoming
one-argument-per-line.

One pattern does get worse. A long *trailing* comment can push a short
statement past the limit, and the formatter responds by parenthesising the
value:

    CHUNK_SIZE = (
        4 * 1024 * 1024
    )  # Consumed by app._upload_one when building MediaFileUpload.

Only two sites in the tree are over-length because of a trailing comment;
the rest are long because the code is long, which the formatter handles
correctly. The fix for those two is to move the comment above the
statement, after which the line is short and the formatter leaves it alone
permanently.

Three commits, in this order: the `ruff check` fixes (automatic, then
hand-written) land first so they stay reviewable, then the over-length
trailing comments move above their statements, and only then the
mechanical `ruff format` pass. Format runs last because a reformat mixed
into a lint diff makes both unreadable, and because moving those comments
first stops the formatter parenthesising the values under them.

The format commit's SHA is recorded in a new `.git-blame-ignore-revs`
file, with `blame.ignoreRevsFile` documented in the README, so a
whole-tree mechanical reformat does not bury authorship of every line in
the project. That SHA only survives a true merge commit — a squash or
rebase merge rewrites it and silently makes the entry inert, so the
merge strategy for that pull request is a deliberate choice, not a
default.

One cleanup commit, then `ruff check` and `ruff format --check` join the
ubuntu CI job.

**Note on `F821`.** Ruff reports an undefined name `webview` at
`ui/window.py:158`. This is **not** a live bug: the signature is
`def create(api) -> "webview.Window"`, the annotation is a string, and it
is never evaluated. `webview` is imported lazily inside the function for
documented reasons. The fix is a `TYPE_CHECKING` import to make the intent
explicit, not a behavior change.

## 5. `uv.lock` is decorative

A 162KB `uv.lock` is committed. Every workflow runs `pip install -e .` and
resolves fresh. Dependencies are unpinned except `pywebview==6.2.1`, whose
pin carries a comment explaining exactly why pinning matters here.

A `google-api-python-client` transitive break would arrive as mysteriously
red CI on an unrelated change, or as a bad installer.

**Change.** All workflows switch to `astral-sh/setup-uv` plus
`uv sync --locked`. The editable install stays for the app itself. The
lockfile becomes enforced rather than aspirational, so a dependency break
arrives as a deliberate lockfile bump instead of a surprise.

`ci.yml` also gains a `concurrency` group so a push to a busy branch
cancels its own superseded runs.

## 6. Dependabot

Valuable only once the lockfile is enforced, since that is what gives it
something to bump. Two ecosystems: `github-actions` and `uv`.

This also retires the separate question of SHA-pinning actions. Pin them
by commit SHA and Dependabot maintains them with a readable version
comment, which buys supply-chain pinning without the usual unreadability
cost.

Updates are grouped so the result is one pull request per ecosystem per
week rather than five.

**No auto-merge, either ecosystem.** For runtime dependencies this is not
a close call:

1. They are frozen into an installer and shipped. The automated gate
   cannot validate them. `docs/smoke-checklist.md` says so directly: *"The
   UI itself is likewise untested by pytest... This checklist is the only
   verification any of that gets."* Green CI on a `pywebview` bump means
   the headless bridge tests passed, not that the application renders.
2. `pyproject.toml` already records the rule: *"Treat an upgrade as a
   change requiring a full smoke pass, not a routine bump."* Auto-merging
   would systematically bypass a constraint the codebase deliberately
   wrote down.
3. The failure mode is silent. Per the same checklist, a WebView2 failure
   exits **0** with no window and no error dialog.

For `github-actions` the risk is genuinely low and auto-merge would be
defensible, but it is omitted for consistency and to avoid a dependency on
branch-protection configuration.

`pywebview` gets a PR like anything else rather than an `ignore` rule. A
security fix that nobody hears about is worse than a PR nobody merges.

## Deliberately out of scope

- **Coverage gates.** 1,839 tests over 16,160 lines of application code. A
  percentage threshold would be ceremony, not signal.
- **mypy.** Real value at the `ui/api.py` bridge seam, but it carries its
  own annotation cost and belongs in its own change.
- **JS/CSS linting.** 3,416 lines with no checks is a real gap, and
  `test_bridge_contract.py` only covers the boundary. Deserves a separate
  round.
- **Branch protection.** A repository setting, not a committable file.
  Delivered as a written checklist rather than configured automatically.
- **Linting `packaging/`.** Task 4 sets `extend-exclude = ["packaging"]`,
  because the automatic pass touched two files there and that task's scope
  forbade it. This exclusion is **temporary by intent and must not become
  permanent by default** — an exemption with no owner is one nobody
  revisits. The measured backlog is exactly two findings, both auto-fixable
  `F401` unused imports, so lifting it costs almost nothing. The reason to
  lift it is not those two imports: `fetch_autohotkey.py`,
  `fetch_ffmpeg.py`, and `fetch_webview2.py` decide which third-party
  binaries ship inside the installer, no test executes them, and the
  exclusion makes `packaging/` the one place in the tree where an `F821`
  undefined name can never be caught. Lift it in its own small change,
  where a break in the release-build path is attributable to that change
  rather than buried in a 219-finding cleanup.

## Sequencing

Each step is independently landable and independently revertable.

1. **Release gate + composite action.** Highest value, touches no test
   code, so nothing here can be blamed on test churn.
2. **Windows matrix + compatibility fixes.** Isolated, so a red first
   Windows run blocks nothing else.
3. **Ruff configuration, format pass, cleanup commit, and CI step.**
4. **Lockfile enforcement + concurrency group.**
5. **Dependabot + SHA-pinned actions**, plus a written branch-protection
   checklist covering the required status checks, which must include the
   Windows job from step 2.

## Verification

Steps 1, 2, 4, and 5 change CI itself, which cannot be fully verified
without pushing. `build.yml` is `workflow_dispatch` and exists precisely
to exercise the Windows chain without publishing, so it is the proving
ground for the composite action before `release.yml` depends on it.

Step 3 is verified locally: `ruff check` and `ruff format --check` clean,
and the full suite still at 1,839 passing. That the suite still passes is
the whole safety argument for a 108-file mechanical reformat.

The manual smoke checklist is unaffected by all of this and remains the
only verification the UI gets.
