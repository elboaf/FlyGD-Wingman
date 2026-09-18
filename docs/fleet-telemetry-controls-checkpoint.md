# Displayed fleet-control authority — verified local checkpoint

This completes the explicitly approved On/Stop continuation of
[the local integration checkpoint](fleet-telemetry-local-integration-checkpoint.md).
It does not complete every fleet-sharing UI workflow or authorize release/cutover.

Branch: `integrate/fleet-v2-runtime`. Base:
`bb7218fc8a6649a58904c58e215fc44936b990d0`. Final source/test checkpoint:
`8a9920c4996fca1c5fe7af3d532689981d66fc56`.

| Commit | Change |
| --- | --- |
| `5348dfca71da74e1773be2dd5a9cb95fbbe37b1d` | Original displayed authority for On/Stop, safe status projection and honest unresolved history |
| `4a038b4aa367829ee23015d2d367486f6c1dcf39` | Attempt/binding-owned refusal feedback survives unrelated repaint |
| `8a9920c4996fca1c5fe7af3d532689981d66fc56` | Static screenshot fixture follows the current authority projection; accidental scratch-report tracking removed without deleting its local evidence |

## Behavior and authority

`fleet_sharing_state()` now explicitly projects safe status and detached control
observations. Private saved command bodies, receipt bodies, history timestamps,
keys and sessions do not become page fields through recursive status serialization.
Automatic consent is summarized, not implicitly enabled or acknowledged.

The existing endpoints retain their names/leading arguments and accept the original
rendered control observation. Native types, closed keys and values must match one
captured immutable status. Current status can validate or reject the supplied CAS;
it cannot replace it with newer values. Participation checks both observed generation
and pending/queued choice identities, order and attempted state. Source Stop checks
its original source observation, automatic binding and pending identity.

The page captures detached authority at paint and again at click, before its existing
page-owned confirmation mechanism. Dialog continuations cannot adopt a later binding,
source generation, pending intent or automatic binding. Route/visibility/binding/
screenshot changes revoke obsolete dialogs. Rejected On feedback stays owned by its
attempt/binding across unrelated pushes, while a retry or binding change retires it.

Off never waits behind a dialog. If a bound Off cannot be admitted, the existing
unbound Off path still inhibits locally before preference persistence, without
inventing a CAS or superseding unseen durable history. Local Off is not a server
acknowledgement or automatic-consent Off.

An unresolved original Start may be cancelled at unknown-source generation zero only
when no source was displayed. A repeated pending Stop uses the existing worker reuse
path with its original request UUID, timestamp, CAS and automatic binding. No worker,
protocol, state schema, timing or producer semantics changed.

Expired unobserved Starts remain journaled and excluded from replay. The page says
**“Start saved; outcome unconfirmed.”** It does not invent an expired-success result.
A source acknowledgement can retire that exact command while invalidating the source
roster until the next real read; tests no longer confuse those separate facts.

The hidden-EVE-tools guard includes pending/enabled/unknown automatic authority and
unresolved participation/cutover work. Inert settled history alone is not a permanent
hide blocker. There is no new screen, automatic-On control, HTML or CSS change.

## Findings, correction and verification

Independent task/general review and the silent-failure pass found the same issue:
a stale-On refusal was written directly to a DOM node and erased by the next paint.
The correction has four genuine failing cases before the fix, plus an unchanged
positive control. Rereview closed the finding. Comment/contract review established
no additional concrete issue. The explicit JSON control interface was covered by
the task review; no new production class/type declaration required a separate
formal-type pass.

The first parent full run cleared all original 17 failures but found three screenshot
cleanup failures: the screenshot fixture doubled as a live read yet lacked current
control authority. The three failures reproduced independently. Production admission
and existing assertions remained unchanged; the fixture was migrated, and a new test
derives its expected controls from `Api._sharing_controls()` over typed data. The
follow-up review found no new issue. The fixture measures 2,611 UTF-16 code units,
below its unchanged 16,384-unit limit. Synthetic staging still cannot send actions.

**Fresh parent full run, final source/test checkpoint:**

```text
TMPDIR=/tmp uv run --no-sync python -m pytest tests/ -q -rs --tb=short \
  --junitxml=.superpowers/sdd/fleet-v2-integration/controls-parent-final.xml
16236 passed, 13 skipped in 662.88s
```

All original 17 failing node identities are still present and now pass. The 13 skips
are Windows junction, DPAPI/WinDLL, native message-pump/window-station and tray gates.
Node and the checkout native release codec were present; neither was skipped.
The preceding full result (3 failed / 16,232 passed / 13 skipped), focused REDs and
reports remain preserved, not replaced by the final green summary.

Fresh post-correction checks:

```text
uv run --no-sync ruff check .                       PASS
uv run --no-sync ruff format --check .              501 files formatted
node scripts/js_smoke.js                            all page modules PASS
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
                                                    1 passed, 0 failed
git diff --check bb7218fc                            PASS
```

A separate isolated headless Chrome check loaded actual `index.html?dev=1` at
840×625 and 839×625. It verified original Stop authority and stale refusal after
an intervening state change, readable unresolved-Start wording with Stop retained,
route cancellation of a pending On dialog, no horizontal overflow and no page errors.
No external requests were made. Screenshots were inspected. This is rendered-browser
evidence, **not Windows/WebView2 or real-backend evidence**. The initial browser
script targeted the intentionally hidden checkbox input; targeting its actual `.box`
wrapper corrected the harness, not production.

The expanded manual scenarios remain unchecked in `docs/smoke-checklist.md` for
separate installed/native verification. Full-suite and browser logs, screenshots,
original independent reports and implementation notes remain under the ignored
`.superpowers/sdd/fleet-v2-integration/` evidence directory.

## Important remaining boundary

Fresh setup with retained state4 automatic history still needs a separately approved
history-disposition UI. Pairing/browser tests explicitly acknowledge settled history
through the worker port to establish a permitted fixture transition; **production
Fresh setup does not perform that acknowledgement**. Test greenness must not be read
as completing that workflow. There is no silent discard of pending or automatic
history and no new automatic-consent grant.

Backend discovery/scheduling was separately accepted at the checkpoint documented in
[fleet-telemetry-discovery-scheduling-checkpoint.md](fleet-telemetry-discovery-scheduling-checkpoint.md).
No backend source was integrated here. Current-client cross-repository E2E, Windows/
WebView2/suspend behavior, original-target ingress normalization, the unchanged
maximum-GET performance failure, operational cutover and activation remain open.
No push, merge, deployment, live OAuth/EVE/relay call or power operation occurred.

## Reviewer focus and knowledge check

Review the distinction between validating original authority and silently replacing
it; immediate local Off versus server confirmation; pending Stop reuse; and refusal
ownership through asynchronous page transitions.

1. Which queued/pending participation fields prevent an old confirmation from overlooking a newer choice?
2. Why does repeated pending Stop use `supersedes=None` rather than replacing its saved command?
3. Why can stale bound Off inhibit locally without acknowledging or discarding conflicting history?
4. What prevents an unrelated status push from erasing a refusal or an old reply from overwriting newer Off?
5. Why do permitted fresh-pairing test fixtures not establish a production history-disposition workflow?
