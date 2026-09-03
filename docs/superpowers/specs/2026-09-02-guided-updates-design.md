# Guided application updates

## Summary

FlyGD Wingman will check GitHub once per process for a newer stable release,
show availability on the Settings gear and in Settings > General, download the
release installer without sending the user to GitHub, verify the download, and
hand it to the existing visible Inno Setup installer after the user confirms.
Wingman will never install an update silently or interrupt an active upload.

The first version deliberately uses the SHA-256 digest published with the
GitHub release asset. This proves that the downloaded bytes match GitHub's
release metadata; it does not independently prove publisher identity because
the asset and digest share the same trust boundary. Wingman and its installer
remain unsigned.

## Goals

- Let users discover stable Wingman releases without visiting GitHub.
- Make update availability visible but unobtrusive.
- Download and integrity-check the installer in Wingman.
- Preserve the normal visible installer and Windows security prompts.
- Reuse the existing installer, upgrade identity, and orderly application
  shutdown rather than replacing installed files directly.
- Fail safely and leave the current Wingman process usable when checking,
  downloading, or launching fails.

## Non-goals

- Silent or unattended installation.
- Automatic download or installation.
- Periodic polling within a process.
- Prerelease channels, skipped versions, deferrals, or update preferences.
- Rendering release notes in Wingman.
- Rollback beyond what the existing Inno Setup installer provides.
- Independently authenticating the publisher. A signed manifest or
  Authenticode signing can strengthen this in a later change.
- Updating a source checkout or replacing an installed Wingman tree directly.

## Product behavior

### Discovery

Wingman starts one update check in a background worker after the page is ready.
This happens whether the app starts visible or hidden at login. The check runs
once per process and is not repeated on a timer.

This is a deliberate exception to the normal rule that a subsystem fetches only
when its route or Settings section is entered. Availability must be known before
General is opened so the Settings gear can carry the indicator. The request
must not delay application startup, page hydration, or any existing feature.

Entering Settings > General reads the cached state. It does not create a second
request when a check is already running or a completed automatic result is
available. A **Check again** action explicitly starts a fresh check. All callers
share one in-flight request, so repeated clicks and section entry cannot create
concurrent GitHub requests.

Only GitHub's latest stable release is considered. Drafts, prereleases,
malformed releases, the installed version, and older versions do not produce an
availability indicator.

### Visibility

The existing Settings gear receives a small badge when a newer release is
available. The badge is not color-only: the gear's accessible name and tooltip
also state that an update is available. There is no banner, destination, or
Windows notification.

The existing **About Wingman** card in Settings > General gains update status
and actions beneath the installed version. Its states are:

| State | Presentation and available action |
| --- | --- |
| Not checked | Installed version and **Check again** |
| Checking | Brief inline “Checking for updates…” status; duplicate actions disabled |
| Current | “Wingman is up to date.” and **Check again** |
| Available | “Version X.Y.Z is available.”, **Download update**, and **Check again** |
| Downloading | Determinate progress based on the validated asset size |
| Ready | “Version X.Y.Z is ready to install.” and **Install update** |
| Manual failure | A specific inline error and the appropriate retry action |

An automatic-check network failure does not create a badge, dialog, banner, or
error elsewhere in the app. When General is opened it may present a neutral
“Update status unavailable” state and **Check again**. A failed manual check or
download names the failed stage and gives the user a retry.

### Download and install

**Download update** is always explicit. It starts a background, streamed
download and does not close Wingman. When verification succeeds, Wingman asks
**Install now?** through `WM.confirm`.

- If the user declines, the verified installer remains available for the
  current process and the card shows **Install update**.
- If the user accepts, Wingman atomically claims update handoff, freshly
  revalidates the staged installer, launches the normal visible installer, and
  begins orderly shutdown.
- If an upload is claimed or active, installation is refused with “Finish the
  active upload before installing the update.” Setup is not launched.
- Once update handoff is claimed, both new uploads and upload retries are
  refused so neither can race shell launch or shutdown.
- If revalidation or Setup launch fails, handoff state is cleared, Wingman
  remains running, and the card offers the appropriate retry.

Inno Setup's existing `AppMutex` is the final safety boundary, not a passive
waiter. Official Inno behavior is to detect the running mutex at startup and ask
the user to close Wingman, then click OK to continue or Cancel to exit. Wingman
launches Setup before beginning orderly shutdown so a process-creation failure
cannot strand the user in a closed app. Depending on timing, Setup may either
start after the mutex is gone or briefly show that standard close/continue
prompt while Wingman finishes cleanup. That prompt is acceptable in the first
version and is part of the Windows smoke test. The updater never weakens the
mutex or directly writes to the installation directory.

The normal Inno UI remains visible. Wingman does not pass silent-install flags,
suppress installer messages, or attempt to restart itself after installation.
The existing installer remains responsible for files, shortcuts, registry
entries, optional components, WebView2 handling, and upgrade behavior.

## Architecture

### `wingman/updates.py`

A new platform-light module owns release and download mechanics. UI wording and
application lifecycle do not belong here. Its responsibilities are:

- fetch and validate latest-release metadata;
- strictly parse numeric `vMAJOR.MINOR.PATCH` release tags and compare them with
  `wingman.__version__`;
- select exactly one expected installer asset;
- stream the asset to a uniquely named staging file;
- report bounded progress;
- validate response size and SHA-256;
- apply Windows attachment security metadata before an executable can be
  launched; and
- clean incomplete, invalid, and stale updater files.

It returns structured immutable results or typed/stage-specific failures so the
API layer can choose user-facing copy without parsing exception strings.
Network access, filesystem operations, hashing, and Windows attachment handling
are injected or isolated behind narrow functions so behavior remains testable
on Linux.

### Release validation

The metadata request targets:

`https://api.github.com/repos/elboaf/FlyGD-Wingman/releases/latest`

It uses a Wingman versioned User-Agent, GitHub's JSON media type, finite connect
and read timeouts, and no credentials. Release validation requires all of the
following:

- the release is neither a draft nor prerelease;
- the tag is strict `vMAJOR.MINOR.PATCH` and is newer than the running version;
- the expected asset name is exactly
  `FlyGD-Wingman-Setup-MAJOR.MINOR.PATCH.exe`;
- exactly one asset has that name;
- the asset reports an HTTPS browser download URL;
- the asset reports a positive byte size below a documented defensive maximum;
- the asset reports a valid `sha256:<64 lowercase-or-uppercase hex digits>`
  digest; and
- release tag, parsed version, and asset filename agree.

The initial `browser_download_url` and every redirect hop must satisfy one
explicit origin policy: HTTPS, an exact normalized hostname from the narrow
GitHub release-download host set, and the default HTTPS port. A custom redirect
handler validates each target before following it; checking only the final URL
is insufficient. The implementation records the host set beside the validation
and covers the currently observed GitHub redirect path in a Windows smoke
check. It never infers trust from a broad suffix such as
`*.githubusercontent.com`, and it rejects userinfo, misleading suffixes,
nonstandard ports, and HTTPS downgrades.

The streamed byte count must never exceed the advertised size or defensive
maximum. Success requires the final byte count to equal the advertised size and
the computed digest to equal the advertised digest. Any mismatch removes the
partial file.

### Staging and attachment security

Updater files live in a dedicated subdirectory under Wingman's existing
application temporary/state area, never beside the executable and never under
a user-selected path. Downloads use unpredictable exclusive filenames. The
filename presented to Setup retains the validated `.exe` extension.

Before an installer becomes `ready`, Wingman uses Windows Attachment Services'
`IAttachmentExecute`: set the validated source URL and local path, then call
`Save` so Windows applies its normal attachment policy and scanning. Attachment
processing happens before the final ready-state integrity check because policy
or scanning may quarantine, replace, or otherwise change the file. After `Save`,
Wingman opens the resulting path, verifies its identity, exact size, and SHA-256
through that handle, and only then reports `ready`. An attachment or post-save
verification failure is launch-blocking; the app must not quietly fall back to
an unmarked executable or claim that the file is ready. This preserves the
Windows/SmartScreen path users expect from a browser download while keeping the
normal installer visible.

A retained `ready` file is not trusted indefinitely. After update handoff is
atomically claimed and immediately before launch, a worker repeats the
`IAttachmentExecute` source/local-path/`Save` sequence *before* trusting the
bytes. It then opens the resulting path with a Windows file handle that permits
Setup to read but denies write and delete sharing, verifies file identity,
exact size, and SHA-256 through that held handle, and retains the handle through
shell launch. The order is attachment processing, protected open, verification,
then launch; hashing before attachment processing or releasing the handle before
launch is forbidden. A missing, truncated, replaced, unverifiable, unmarkable,
post-attachment-changed, or identity-changed file returns to a download-failed
state and is never passed to Setup.

The installer is opened only through `ShellExecuteExW` using the normal `open`
verb. The call uses `SEE_MASK_NOASYNC | SEE_MASK_NOCLOSEPROCESS`, never
`SEE_MASK_NOZONECHECKS`, and runs on a worker whose COM apartment is initialized
as required by the Shell API. Success requires a non-null returned process
handle; Wingman closes that handle after recording the handoff in an on-disk
marker and does not wait for Setup to finish. Direct `CreateProcess` or
`subprocess.Popen` execution is forbidden because it does not guarantee the
Windows shell's attachment-zone checks. The existing injectable
`ShellExecuteExW` shape in `wingman/fightrecorder.py` is the repository pattern,
adapted to the non-elevated
`open` verb.

Partial or invalid files are removed immediately when possible. A verified file
is removed when an ordinary process exit can safely remove it or by bounded
stale-file cleanup on a later launch. A successful handoff is classified by an
on-disk sidecar written before Wingman exits; cleanup must not infer handoff
solely from process memory. The sidecar is atomically published and its file
contents are fsynced, but its parent directory is not, so the classification is
persistent across ordinary process restarts without claiming power-loss
durability.

A handed-off installer is not removed during Wingman's shutdown because Setup
may still need it. The marker's mtime starts the `UPDATE_STALE_AFTER` seven-day
retention period: a fresh marker protects even an old matching installer. Once
the marker is stale, cleanup attempts the installer and, if that succeeds, its
marker; stale orphan markers are cleaned independently. Every deletion is
best-effort, so a sharing violation or other failure safely retains that path,
and a partial pair
deletion leaves the remainder for a later cleanup. Stale cleanup only touches
files created inside the dedicated updater staging directory and never
traverses or deletes arbitrary temporary files.

### `wingman/ui/api.py`

The API layer owns orchestration and user-facing state. New updater state stored
on `Api` is underscore-prefixed, preserving pywebview's public-attribute
constraint. Public bridge methods are limited to semantic actions such as:

- read current update status;
- explicitly check again;
- download the available update; and
- install the verified update.

The exact method names are implementation details, but each page-called method
must have a dev-harness double. Any Python-to-page status push must be a literal
handler in `WM.HANDLERS` and registered by the owning web module.

One lock protects the updater state machine and one in-flight operation per
stage. The updater lock and upload/handoff boundary are never nested; each is
held only for a short state transition, never across confirmation, network or
file I/O, attachment handling, shell launch, or `_push`. Workers perform all
slow work and communicate with the page only through `_push`. A read method
repairs a push that was missed while the window was hidden or the page was not
ready.

The state exposed to JavaScript contains only presentation-safe fields:
operation state, installed version, available version, progress byte counts,
whether each action is currently allowed, and a user-facing error where
appropriate. It does not expose arbitrary release URLs or filesystem paths.

### Startup and shutdown ownership

The post-readiness automatic check is scheduled from the application lifecycle,
not from `get_settings()`. `get_settings()` currently hydrates the page at bridge
startup; adding network access there would delay unrelated settings and turn an
optional check into a startup dependency.

The existing orderly-quit behavior becomes one shared lifecycle operation used
by tray Quit and update handoff. This refactoring must preserve existing close-
hides behavior and upload protection. Update handoff differs from ordinary Quit
only where the product decisions differ: it refuses an active or claimed upload
rather than offering a force-quit confirmation.

One shared synchronization boundary owns the mutually exclusive claims for
upload work and update handoff. Under that boundary, installation verifies that
no upload is claimed or running and claims handoff *before* revalidation or
Setup launch. Both `start_upload()` and `retry()` verify that handoff is clear
and claim the upload slot before releasing the same boundary. The upload claim
lives from dispatch through worker completion and is released in `finally`; it
is not inferred only from a thread reference between separate checks. A
revalidation or shell-launch failure clears handoff under that boundary.
Checking separate flags without this atomic claim is not sufficient because
pywebview can run bridge methods on different threads.

Tray Quit is also arbitrated by that boundary. Before handoff is claimed,
ordinary Quit keeps its existing behavior. While handoff is `handing_off`,
`revalidating`, or `launching`, a tray Quit request is refused with a short
“Update installation is being prepared” message and does not destroy windows or
services. If preparation fails, the claim clears and Quit works again. After a
successful shell launch, only the updater requests the shared orderly shutdown.
That shutdown operation is idempotent, so a duplicate or late shutdown request
cannot destroy resources twice. No updater worker may remain able to mutate
handoff state after shutdown cleanup begins.

Setup is shell-launched before orderly shutdown begins. Failure to obtain its
process handle therefore leaves Wingman alive and able to clear handoff state.
After a successful launch and persistent on-disk handoff classification, the
updater calls the idempotent shutdown operation. `AppMutex` prevents replacement
while Wingman remains alive; if it detects the mutex, Setup presents its standard
close/OK-or-Cancel prompt rather than silently waiting.

### Web UI

`wingman/web/settings.js` owns General-section update rendering and actions.
`wingman/web/app.js` owns only the cross-route Settings-gear badge and bridge
handler plumbing needed to update it. The page never fabricates release state;
`dev.js` is the sole fake-data source.

The About card uses existing card, button, progress, field-message, disabled,
and focus conventions where they fit. Update status is a polite live region,
and download progress exposes semantic current and maximum byte values in
addition to its visual fill. No second accent action is introduced. All new
display-setting selectors receive explicit `[hidden]` handling, and all states
remain understandable without color. Manual confirmation uses `WM.confirm`,
never browser chrome.

## State model and concurrency

The logical states are:

`idle -> checking -> current | available | check_failed`

`available -> downloading -> ready | download_failed`

`ready -> handing_off -> revalidating -> launching -> exiting`

Recoverable process-creation failure returns to `ready`; failed pre-launch file
or attachment revalidation returns to `download_failed`. A fresh explicit check
may supersede `current`, `available`, `check_failed`, or `download_failed`.
While a verified installer is `ready`, **Check again** is unavailable because
there is already a concrete update to install. An in-flight check, download,
revalidation, or launch cannot be duplicated.

All transitions that mutate cached metadata, staged paths, upload claims, or
handoff state happen under the appropriate shared boundary; page pushes happen
after releasing it. Since operations are single-flight and cannot be
superseded while running, no generation-token mechanism is required.

The upload/handoff boundary is acquired immediately before pre-launch
revalidation, not only when the confirmation first opens. Installation claims
handoff only if no upload slot is claimed or active. `start_upload()` and
`retry()` claim that same upload slot only if handoff is clear. This closes the
cross-thread race between verification, confirmation, upload dispatch, retry,
and shell launch.

## Errors and recovery

Errors are stage-specific and actionable:

- metadata/network failure: “Could not check for updates — check your internet.”
- invalid or incomplete release metadata: “The latest release cannot be
  verified.”
- interrupted transfer: “Could not download the update — check your internet.”
- size/digest mismatch: “The download did not match the release checksum — not
  installed.”
- attachment-security failure: “Windows could not mark the installer as an
  internet download — not installed.”
- Setup launch failure: “Could not open the installer.”
- active upload: “Finish the active upload before installing the update.”

Exact final copy may be adjusted to existing UI vocabulary, but it must preserve
the stage and next action. Automatic-check failure remains non-interrupting.
No failure may turn into an implicit browser fallback, arbitrary URL launch,
silent install, or direct modification of the installed app.

## Release workflow

The tag-triggered release workflow gains a gate before build or publication.
It reads `wingman.__version__`, requires the triggering ref to equal
`v<__version__>`, and fails with both values in the diagnostic when they differ.
The generated installer filename remains derived from the same source version.
A workflow/source test asserts that the gate exists so a future workflow edit
cannot silently remove tag/version agreement.

No signed manifest is added in this version. The GitHub release asset digest is
mandatory; a release without it is visible through GitHub but not installable
through Wingman.

## Security and privacy

The automatic check sends GitHub the normal connection metadata and Wingman's
versioned User-Agent once per process, including hidden login-start processes.
It sends no Wingman settings, EVE information, account data, file names, or
telemetry. `README.md` must disclose this GitHub request and correct the existing
network-destination description.

The SHA-256 requirement protects against corruption and bytes that differ from
the release record. It does not protect against repository takeover, release
credential compromise, or malicious replacement of both an asset and its
metadata. User-facing copy and documentation must not call the digest a
publisher signature.

The updater accepts no caller-provided URL or path. It never executes an
unverified or unmarked download. Installation requires a fresh user action and
confirmation. Source checkouts can inspect status for development, but install
and launch actions are disabled unless the process is a frozen Wingman build.

## Testing

### Pure updater tests

A new `tests/test_updates.py` covers:

- strict current/newer/older/malformed version handling;
- stable release requirements;
- exact asset selection and tag/name agreement;
- missing, malformed, and mismatched digest behavior;
- missing, zero, inconsistent, and excessive sizes;
- origin policy for the initial URL and every redirect hop, including a
  disallowed initial host, a disallowed intermediate host, HTTPS downgrade,
  misleading suffix, userinfo, and nonstandard port;
- chunked transfer, progress, byte-count limits, and successful verification;
- interrupted reads and cleanup of partial files;
- checksum mismatch and cleanup;
- attachment-security success/failure through an injected seam;
- an attachment call that reports success but changes, replaces, or quarantines
  the file, proving post-attachment verification rejects changed bytes;
- deletion, truncation, replacement, and attachment failure after a file has
  entered `ready`, with fresh pre-launch verification refusing each case;
- a barrier-controlled replacement attempt after final hashing and before shell
  launch, proving the held file identity cannot change;
- `ShellExecuteExW` flags, normal `open` verb, required process handle, COM
  initialization, shell-launch failure, and prohibition of zone-check bypass;
- ordinary-exit cleanup versus process-restart-persistent handed-off-file
  classification;
- marker-age-based seven-day cleanup constrained to the dedicated updater
  directory, including a fresh marker protecting an old installer, stale orphan
  marker cleanup, and best-effort partial deletion; and
- structured failure categories without real network access.

### API and lifecycle tests

A new `tests/test_api_updates.py` and focused existing-test updates cover:

- one automatic check per process after readiness;
- no network call from `get_settings()`;
- cached status reads and missed-push repair;
- manual retry after automatic failure;
- single-flight checks and downloads;
- refusal of overlapping checks, downloads, revalidation, and launches;
- progress payloads and action enablement;
- source-checkout launch refusal;
- install confirmation decline and later install;
- active-upload refusal immediately before launch;
- barrier-controlled races proving install is mutually exclusive with both
  `start_upload()` and `retry()` claims;
- upload claims remaining held through worker completion and clearing in every
  worker exit path;
- no lock nesting or lock held across confirmation, I/O, shell launch, or
  `_push`;
- new-upload and retry refusal during handoff;
- barrier-controlled tray Quit races against `handing_off`, `revalidating`, and
  `launching`, proving Quit is refused until failure clears the claim or the
  updater owns shutdown;
- idempotent orderly shutdown and no updater mutation after cleanup begins;
- Setup shell-launch failure returning to `ready`;
- successful shell launch entering orderly shutdown;
- all updater `Api` attributes remaining underscore-prefixed; and
- preservation of ordinary tray Quit and close-hides behavior.

### Web and workflow tests

Lexical page tests cover:

- `WM.HANDLERS`, `_push`, and registration agreement;
- General-section cached-state fetch and manual actions;
- a `dev.js` double for every page-called bridge method;
- accessible badge naming and non-color status;
- explicit `[hidden]` overrides where display rules are introduced; and
- existing button, focus, progress, and confirmation conventions.

Release workflow tests assert that tag/source version agreement gates the build
and publication jobs and that the installer asset naming remains derived from
the source version.

### Verification and Windows smoke pass

Run the full Linux test suite, Ruff lint, and Ruff format check. Add a test-only
Windows update integration harness under `tests/manual/`; it is excluded from
the frozen package, requires an explicit command-line opt-in, uses an isolated
temporary staging root and test mutex name, and calls the same native attachment,
file-locking, and shell-launch seams as production. It must not add a production
environment variable or bridge method that weakens the fixed endpoint, origin
policy, frozen-build guard, or verification checks.

The harness provides reproducible fixtures and fault switches for a complete,
truncated, and checksum-mismatched stream; post-attachment file replacement;
attachment failure; held-file replacement attempts; and shell-launch failure.
A harmless test-only Inno fixture using the test mutex reproduces both mutex
outcomes without installing or replacing Wingman. Pure injected tests remain the
CI gate; the harness is the repeatable Windows-native pre-release exercise for
behavior Linux cannot execute.

The Windows smoke checklist gains explicit commands for the harness and checks
for:

- current, checking, available, offline, downloading, failed, and ready states;
- gear badge visibility, tooltip, keyboard behavior, and accessible name;
- hidden login start performing one non-blocking check;
- manual retry after an automatic failure;
- declined immediate install followed by **Install update**;
- active-upload refusal and normal upload behavior after refusal;
- checksum and truncated-download failure;
- attachment security and the expected SmartScreen/unsigned warning;
- normal visible Inno upgrade with settings preserved;
- both observed Inno mutex outcomes: Setup starting after cleanup, and Setup's
  standard close-Wingman/click-OK prompt when it observes the live mutex;
- Setup launch failure recovery; and
- source-checkout install controls remaining unavailable.

Because no automated test renders the page, the new UI states must also be
exercised in the `?dev=1` harness and in the real Windows WebView2 app.

## Documentation changes

- `README.md`: describe automatic checks, manual retry, guided installation,
  the GitHub request, checksum scope, and unsigned warning.
- `DESIGN.md`: record the post-readiness check as a narrow exception to
  section-entry fetching because its output appears in global Settings chrome.
- `docs/smoke-checklist.md`: add the Windows checks listed above.
- Historical documents under `docs/history/` remain unchanged.

## Likely implementation surface

- New: `wingman/updates.py`, `tests/test_updates.py`,
  `tests/test_api_updates.py`, and a non-packaged Windows integration harness
  plus harmless test Inno fixture under `tests/manual/`.
- Orchestration/lifecycle: `wingman/ui/api.py`, `wingman/__main__.py`, and
  focused existing lifecycle/API tests.
- Web: `wingman/web/index.html`, `settings.js`, `app.js`, `dev.js`, and only the
  necessary `style.css` rules.
- Release: `.github/workflows/release.yml` and packaging/workflow tests.
- Docs: `README.md`, `DESIGN.md`, and `docs/smoke-checklist.md`.

The implementation plan may refine exact private function and bridge method
names, but it must preserve the boundaries, states, safety checks, and user
behavior specified here.
