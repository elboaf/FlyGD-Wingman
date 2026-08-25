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
