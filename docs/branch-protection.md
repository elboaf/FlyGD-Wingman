# Branch protection

These are repository settings, not files, so they cannot be committed and
must be applied by hand. Until they are, the CI in this repository
**reports but does not gate**: a pull request with a red Windows leg is
still mergeable.

Everything below is one ruleset. Three of the steps have a silent failure
mode — you end up with something that looks configured and enforces
nothing — so each is called out where it happens rather than in a note at
the end.

## 1. Create the ruleset

**Settings → Rules → Rulesets → New ruleset → New branch ruleset.**

(Not *Settings → Branches*. That is the older branch-protection-rules
page. It still works, but rulesets are where GitHub puts new development,
and the two are configured differently — following ruleset instructions on
the classic page will not line up.)

Name it something like `main protection`, and under **Target branches** add
the default branch.

## 2. Set Enforcement status to Active

**This is the step most likely to be missed, and missing it silently
undoes everything else.**

A new ruleset defaults to **Disabled**. A disabled ruleset appears in the
list, shows all your settings, and gates nothing. GitHub presents
switching it to Active as an optional step you have to go looking for.

Also leave the **Bypass list** empty. A solo maintainer's instinct is to
add themselves, and that reduces the ruleset to decoration — the whole
point is to stop *you* merging something red at 1am.

## 3. Require these status checks

Enable **Require status checks to pass**, and add these three by name.
Also enable **Require branches to be up to date before merging**.

```
checks
test (ubuntu-latest)
test (windows-latest)
```

You have to **type** each name and confirm it. GitHub cannot reliably
offer a pick-list for checks it has not seen recently, and hand-typing is
exactly where the next problem comes from:

> **A required check whose name does not match a job is never satisfied.**
> The job itself runs perfectly well — what never arrives is a status
> reported under the name you typed. So do not go looking at whether the
> workflow executed; it did. GitHub displays the unmatched requirement as
> *"Expected — Waiting for status to be reported"*, which reads like a
> check that is still running rather than one that will never report. A
> pull request can sit like that indefinitely, or the check can simply be
> absent and merging proceeds.

Copy the three names exactly, including the spaces and parentheses. They
come from `.github/workflows/ci.yml` — the `checks` job, and the `test`
job's matrix over `ubuntu-latest` and `windows-latest`. If that file's job
names or matrix ever change, these must change with it.

**`test (windows-latest)` is the one that matters most and the easiest to
omit.** It is the only place `tests/test_preview_win32.py` runs, and that
file is what catches a mistyped Win32 export before a user does. It is
also where `tests/test_eveskills_dpapi.py` exercises real DPAPI, the path
that encrypts EVE SSO tokens at rest.

## 4. Also enable

- **Require a pull request before merging.**
- **Block force pushes.**
- **Restrict deletions.**

## Deliberately not enabled

- **Auto-merge.** Runtime dependencies ship frozen into an installer, and
  the UI has no automated verification at all — see `smoke-checklist.md`
  beside this file. A green build says nothing about whether the app
  renders. `pyproject.toml` records that a `pywebview` upgrade needs a
  full smoke pass, not a routine bump.
- **Required approvals.** A solo-maintained repository; this would only
  block the maintainer.

## 5. Verify it actually works

Do **both** checks. The first one alone is not enough, for a reason worth
understanding.

### Confirm all three names are required

Open any pull request and read the merge box. All three names should be
listed under **Required**. A name you mistyped is not there — it sits
separately at *"Expected — Waiting for status to be reported"*. A name you
forgot is simply absent, with nothing to notice.

This is the check that catches a wrong or missing name. Do not skip it.

### Confirm a failing check actually blocks

Open a pull request with a deliberately failing test and confirm the merge
button is blocked.

Make the failure **Windows-only**, or this test proves less than it
appears to:

```python
def test_deliberate_failure_to_verify_branch_protection():
    import sys
    if sys.platform == "win32":
        raise AssertionError("intentional - delete this test")
```

A test that fails on both platforms is blocked by `test (ubuntu-latest)`
alone. You would see the merge button greyed out and conclude the
protection works — while `test (windows-latest)`, the requirement most
likely to have been omitted, was never enforced at all. A Windows-only
failure can only be blocked by the Windows requirement, so it tests the
thing you actually care about.

Delete the test afterwards.

## If you change CI

These names are a copy of `ci.yml`'s job names, kept in sync by hand.
Renaming a job, or adding a platform to the matrix, changes what CI
reports without changing what is required — and the new or renamed check
becomes optional, silently. Re-run the first verification above after any
change to `ci.yml`'s job or matrix names.
