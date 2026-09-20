# Fleet v2 integration: review readiness

## Scope

The integrated desktop implementation includes the frozen combat profile and v2
wire codecs; ten-second directional DPS and independent thirty-second activity,
effect and tackle-name lifetimes; original producer/source admission and retained
timing fences; durable state4 controls and recovery; and the existing Fleet UI's
separate combat approval, account automatic verification and local participation.
The optional inactive-row preference changes display only, not collection.

Fresh setup compares its displayed command sequence atomically at worker
admission. Cancelling a queued On does not retarget older durable history. Retry
preserves unregistered initial pairing and its requested capabilities. Legacy
archives, including empty archives, require explicit removal. These are the
review corrections, not new automatic enrollment or implicit acknowledgements.

The backend companion is the `integrate/fleet-v2-runtime` branch in
`guarzo/authGD`. Both changes are for coordinated review, not independent
activation. Updated clients only; no v1 runtime fallback.

## Agreed local acceptance boundary

The separately configured real-clock current-client journey remains **opt-in and
environment-blocked on this WSL host**. It is not part of either regular suite.
The user explicitly approved retaining that test without requiring this host's
clock repair or a green run here before opening draft PRs. This is a scope
choice, **not a passing end-to-end result** or a silent skip added to the test.

A read-only probe reproduced clock disagreement without Wingman: the shared WSL
kernel's disciplined clock ran several percent slower than raw time, and its
wall clock stepped by roughly 1.4 seconds. Windows precise clocks stayed aligned,
and all 2,400 sampled database timestamp conversions agreed. The attempted
system-level repair did not remain stable. Further WSL diagnosis is outside this
change. Application timing protections remain unchanged.

## Verification and its limits

Recorded source/test verification before this documentation-only PR preparation:

- Desktop full suite: **16,267 passed, 13 Windows-only skips**; no Node/native-codec
  skips. Ruff check/format, all-page executable JS smoke and Cargo regression pass.
- Native Windows Python targeted setup/display/normalization tests: **25 passed**.
- Actual Chromium controls at 840×625 and 839×625: no page errors or horizontal
  overflow; separate automatic consent, activity filtering and empty-archive
  removal exercised. This was not Windows/WebView2 acceptance.
- Backend regular suite: **4,936 passed in 190 files**, no skips; full lint,
  typecheck and an offline-font Next production build pass. Its explicitly pinned
  historical desktop fixtures are not substitutes for the current-client journey.
- Maximum legal 47,022,137-byte reader/codec measurement: **3.894s Linux** and
  **4.207s Windows**. Neither includes network/TLS/database time or proves the
  unchanged five-second full-call budget.

Fresh publication run on unchanged source/test head `3363da55`: **16,267 passed,
13 Windows-only skips, 790.39s**. Ruff check/format (507 files), all-page executable
JS smoke and the Cargo regression passed again.

### Bounded Windows/WebView2 smoke

Current source was exercised through the real main/Fleet Bar window factories,
Api bridge, page scripts and presentation owner on Windows 11, Python 3.12.10,
pywebview 6.2.1 and WebView2 **153.0.4234.32**. Two separate processes used one
isolated settings/state directory and an explicitly synthetic, stateful relay;
non-loopback networking was blocked and browser approval was a fixture callback.
No EVE enumeration, real DPAPI, live relay or OAuth was exercised.

Both processes exited successfully. Observed results included:

- Explicit combat approval, then automatic consent On while local participation
  remained Off; local On/Off did not disable account automatic consent.
- Native Fleet Bar rendered **32 outgoing / 14 incoming DPS** and
  **SCRAM/POINT · NEUT** from a synthetic local presentation snapshot.
- Tackle-source name expiry left the other effect visible; activity expiry removed
  the row without deleting its character from the retained display roster.
- A fresh process restored the inactive-row preference and separately observed
  account consent; automatic Off then settled against the offline peer.
- Sharing and presentation owners reported stopped before native window teardown.

The real factory requested 840×625 outer geometry; this machine reported an
**828×613 CSS viewport at DPR 1**, without horizontal overflow. This is not proof
of every minimum-size/DPI configuration. The driver had to reproduce the normal
page-ready/floating-window startup hooks and await actual bridge settlement;
fixture setup failures are not counted as passing runs. This source-runtime smoke
is not an installed/frozen build or a substitute for the real-backend journey.

The original partial checkpoints retain their historical failures and acceptance
scope; do not read those old counts as the current suite result.

## Published-review corrections

Ordinary Stop still retries the exact original request. A separate **Replace
pending Stop…** confirmation acknowledges a durable expired/conflicted Stop and
uses the displayed live source's original generation/binding. It refuses stale
observations and cannot replace a request that is only queued; that would lose
the queued request's link to its durable predecessor. Unknown/ended sources do
not authorize a new replacement. No automatic consent is enabled by this action.

Historical approval-URL text validation is now frozen to Unicode 14 rather than
following the host Python Unicode tables. The generator requires Unicode 14;
exhaustive equivalence covers all 1,114,112 code points. Combat-v2's immutable
Unicode 16 profile and shared fixtures are unchanged.

Post-polish desktop verification: **16,280 passed, 13 Windows-only skips,
970.61s**, with no Node/native-codec skips. Ruff check/format (510 files), all-page
JS smoke and the Cargo regression pass. Windows Python 3.12 additionally passed
**70 migration/recovery tests**. A fresh actual WebView2 **153.0.4234.32** process
exercised the new confirmation through the real page/Api/worker against an
offline peer, settled the expired/conflicted Stop, retained the no-overflow
840×625 outer-window check, and stopped sharing/presentation before teardown.
The same native/live/installed limitations above still apply.

The companion correction exposes own-account browser automatic Off without
revocation, retains original request identity across response loss/refresh and
binds actions to the rendered account. Maintenance failures are isolated by row
and phase without new owners or cadence. Its ordinary browser suite passed
**451 tests** and the complete maintained integration profile passed **25 tests**
with zero retries/skips. The latter now verifies API2 source/combat traffic and
actual rejection of pinned pre-v2 clients, not obsolete v1 success. See the
companion's current verification document for its separately recorded regular
suite results; none of these checks replaces the opt-in current-client journey.

## Still separate from draft-PR readiness

- A complete current-client restart → future fleet → automatic Off journey on
  stable clocks.
- Maximum-body full transport budget and original-target ingress normalization.
- Installed/frozen Windows build, native WebView2 lifecycle, DPI/mixed-monitor,
  suspend/resume and two-PC acceptance beyond any specifically recorded smoke.
- Hosted CI results and the explicitly authorized operational cutover.

Opening these PRs authorizes neither merge nor deployment. Activation must follow
the existing closed-ingress, drained-owner, schema and generation-fencing cutover
contract; do not apply migrations or enable the relay against an operational
installation as part of review preparation.
