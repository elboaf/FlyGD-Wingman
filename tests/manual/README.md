# Windows updater native integration harness

This checkout-only harness exercises the same download, handoff-marker,
Attachment Services, protected-file, ShellExecute, and process-handle seams as
`wingman.updates`. It is not included by `packaging/uploader.spec`, adds no app
bridge or environment-variable route, and performs no network request in
`serve` mode. Importing `update_harness.py` is inert on Linux and Windows.

The provided installer source is `update_fixture.iss`: a no-payload,
non-uninstallable, lowest-privilege Inno fixture. It uses only
`Local\FlyGDWingmanUpdateHarness`. Native file commands verify the exact
basename `Wingman-Update-Harness-Setup.exe` and refuse symlinks; those guards
do not identify the file's contents. The operator must compile and use the
provided fixture for every native command below. Each invocation creates one
temporary staging root and removes only that root. `attachment` may add
Attachment Services metadata to the explicitly supplied path, and
`shell-launch` starts that path after the guard. `lock-race` copies the fixture
into the temporary root before attempting replacement, so its source is never
changed.

Run these commands from the repository root in PowerShell on Windows. Install
the locked development dependencies first (`uv sync --locked --extra dev`) and
make sure Inno Setup's `iscc` is on `PATH`.

## Compile the provided no-payload fixture

```powershell
iscc /O"$PWD\dist" tests\manual\update_fixture.iss
$Fixture = Join-Path $PWD "dist\Wingman-Update-Harness-Setup.exe"
$SourceUrl = "https://github.com/elboaf/FlyGD-Wingman/releases/download/v0.0.0/test.exe"
```

Expected: `dist\Wingman-Update-Harness-Setup.exe` is created. The setup has no
application payload, no uninstall entry, no privileged operation, and only a
temporary default destination.

## Injected download and fault modes

These modes run on Linux too. The response object is passed directly through
`download_release(..., opener=...)`; the release URL remains an allowed HTTPS
GitHub origin and production host validation is not changed or bypassed.

```powershell
uv run python tests\manual\update_harness.py serve --mode complete
uv run python tests\manual\update_harness.py serve --mode truncated
uv run python tests\manual\update_harness.py serve --mode checksum-mismatch
```

Expected:

- `complete` prints a `.ready.exe` identity, exact size and SHA-256, then
  `handoff marker created`, `handoff marker removed: True`, and
  `temporary staging root removed: yes`.
- `truncated` prints `expected failure: stage=download code=size` and
  `partial retention: none`.
- `checksum-mismatch` prints
  `expected failure: stage=download code=checksum` and
  `partial retention: none`.
- Every mode ends with `temporary staging root removed: yes`; no response
  fixture is fetched from the network.

## Attachment Services metadata

The long acknowledgement is intentionally required even though this command
does not launch the file: Attachment Services may add metadata, replace,
quarantine, or reject the explicitly named fixture according to local policy.

```powershell
uv run python tests\manual\update_harness.py attachment `
  --i-understand-this-launches-a-test-exe `
  $Fixture `
  $SourceUrl
Get-Item -LiteralPath $Fixture -Stream *
```

Expected on a filesystem and local policy that support Mark-of-the-Web: the
harness prints file identity, size, SHA-256, and `Zone.Identifier: present`;
`Zone.Identifier` is present and listed by `Get-Item` beside the ordinary data
stream. Where they do not support it, the zone stream may be absent. A policy
rejection or quarantine must remain a typed updater failure and must not be
worked around by weakening host or Attachment Services validation. Recompile
the fixture if local policy quarantines it.

## Protected-handle replacement race

```powershell
uv run python tests\manual\update_harness.py lock-race `
  --i-understand-this-launches-a-test-exe `
  $Fixture
```

Expected (the harness prints the actual Windows error code):

```text
safe retention: replacement denied (winerror=5)
identity unchanged: yes (...)
size unchanged: yes (...)
sha256 unchanged: yes (...)
```

Windows may instead print `winerror=32`; only access denied (5) and sharing
violation (32) are accepted replacement denials. The production protected
handle is held while a barrier releases the replacement thread. Any successful
replacement, any other error code, a timeout, or changed identity, size, or
digest makes the harness exit non-zero. The race uses a staged copy; the
compiled source fixture remains untouched.

## Deterministic fixture-mutex behavior

Hold the fixture's mutex in one PowerShell terminal:

```powershell
uv run python tests\manual\update_harness.py mutex-holder
```

In another terminal, open the fixture directly:

```powershell
# Expect Inno's close/OK prompt; it must not continue while the holder waits.
& .\dist\Wingman-Update-Harness-Setup.exe
```

Expected: Inno reports that the **FlyGD Wingman Update Harness** must be closed
and exits/returns to the prompt. Press Enter in the first terminal only after
observing that result.

For the no-mutex run, first press Enter in the holder terminal, then run:

```powershell
& .\dist\Wingman-Update-Harness-Setup.exe
```

Expected: no app-close prompt. The ordinary fixture setup may be cancelled or
completed; it installs no files and creates no uninstall entry.

## Verified ShellExecute and process-handle ownership

With the fixture mutex either held or released according to the case being
checked:

```powershell
uv run python tests\manual\update_harness.py shell-launch `
  --i-understand-this-launches-a-test-exe `
  dist\Wingman-Update-Harness-Setup.exe `
  https://github.com/elboaf/FlyGD-Wingman/releases/download/v0.0.0/test.exe
```

Expected: `launch_verified` runs real Attachment Services, verifies the file
through the protected handle, and ShellExecute starts the supplied path. The
harness guard proves only its exact basename and that it is not a symlink, so
the operator must compile and supply the provided no-payload fixture above.
The harness prints a non-zero `returned process handle`, then `process handle
closed: yes`. With `mutex-holder` active, the launched fixture shows the
close/OK prompt. Without it, no close prompt appears. Windows may show a
reputation warning depending on local policy and the fixture's reputation; do
not disable zone checks to suppress it.

For a deterministic missing-file launch failure, use a deleted path with the
required fixture basename:

```powershell
$Missing = Join-Path $env:TEMP "Wingman-Update-Harness-Setup.exe"
Copy-Item -LiteralPath $Fixture -Destination $Missing -Force
Remove-Item -LiteralPath $Missing
uv run python tests\manual\update_harness.py shell-launch `
  --i-understand-this-launches-a-test-exe `
  $Missing `
  $SourceUrl
$LASTEXITCODE
```

Expected: no process opens, the harness prints an `updater failure` from the
real attachment/protected-open path, and `$LASTEXITCODE` is `1`. Windows policy
may detect the absent file in Attachment Services (`code=attachment`) or at
the protected open (`code=file`); either is a safe launch refusal.

## Release gate

Run all sections on a real Windows host before release. The automated Linux
suite verifies import safety, parser/opt-in behavior, packaging exclusion, and
the injected production seams, but it cannot prove live COM, sharing, mutex,
or ShellExecute behavior.

# Windows preview crop probe harness

`preview_crop_harness.py` is the Phase 0 engineering probe for cropped preview
regions (`docs/preview-evolution-crops-design.md`). It subclasses the real
`PreviewHost`, so discovery, the message pump, activation and teardown are the
shipped ones; only the crop windows and the crop picker are prototype code.
Like `update_harness.py` it is checkout-only: no module in `wingman/` imports
it, `packaging/uploader.spec` excludes `tests/manual`, and importing it is
inert on Linux and Windows.

## Safety boundaries

- **It saves nothing.** No settings write, no layout write, no restart
  restoration. Its `on_layout_changed` discards the geometry you drag.
- **It reads no settings either.** The CLI constructs the host with the
  character to wait for and nothing else: no `locked`/`lock_default` roster,
  no `hide_on_lost_focus` provider and no alert service. The inherited code
  paths for all three are still the shipped ones, but nothing in the probe
  can switch them on, so locking a crop, hide-on-lost-focus and the
  alert-pulse-while-dragging check are Phase 1 pre-release gates rather than
  probe steps (see `docs/smoke-checklist.md`).
- **It moves no EVE window.** Crops are DWM mirrors; the probe never sizes,
  positions or restores a real client. Clicking a crop activates its client
  through the inherited coordinator, exactly as a primary preview does.
- **At most eight ephemeral crops.** Eight is the probe guard the design doc
  names, not a production cap; the production cap is whatever the measured
  stages support.
- **It must not run beside installed Wingman.** Both commands acquire
  Wingman's own single-instance mutex and refuse when the app (or its 3.x
  predecessor) already holds it. While the probe runs, Wingman will not start.
- **Everything disappears when the process exits.** Every crop, the picker and
  the pump die with it; nothing survives to the next launch.

Both commands also refuse to run anywhere but Windows, and both need an
interactive console: each pause waits for Enter so an operator can look at, or
measure, what is on screen.

## Commands

Run from the repository root in PowerShell on Windows, with at least one EVE
client logged in to a named character.

```powershell
# Close the installed Wingman first.
$env:WINGMAN_LOG_LEVEL = "DEBUG"
$env:WINGMAN_PREVIEW_PERF = "1"
uv run --no-sync python tests/manual/preview_crop_harness.py pick `
  --character "Alice" `
  --i-understand-this-is-an-ephemeral-windows-probe

uv run --no-sync python tests/manual/preview_crop_harness.py load `
  --i-understand-this-is-an-ephemeral-windows-probe
```

`WINGMAN_LOG_LEVEL=DEBUG` is what makes the DWM registration and update
HRESULTs readable in `uploader_debug.log`; `WINGMAN_PREVIEW_PERF=1` adds the
per-drag timing lines. The acknowledgement flag is spelled out in full on
purpose: every parser sets `allow_abbrev=False`, so no prefix of it is
accepted.

### `pick`

Opens one picker for the named character as soon as that client is discovered,
and one crop when you confirm. One picker per process, ever: cancelling is a
decision, not a transient failure, so it does not reopen on the next sweep.

- Picker: left drag selects, Enter confirms, Escape cancels.
- Crop: left click activates, left drag moves, right drag resizes (the source
  aspect is preserved; a locked crop only activates, but nothing in the probe
  can lock one).

Press Enter in the console to print a final status line and shut everything
down. Ctrl+C ends the run the same way: the host is stopped, the probe prints
`crop probe interrupted` and exits `130` rather than printing a traceback.

### `load`

Walks the staged simultaneous counts 1, 2, 4 and 8, printing the probe status
at each stage and waiting for Enter so the performance-gate metrics can be
recorded before the next stage opens. It refuses to start with no named client
running, stops before a stage the machine has fewer clients than, and stops at
the first stage that records a crop failure rather than continuing past it.

## Release gate

The Linux suite covers parsing, the long opt-in, import inertness, the
platform and single-instance refusals, the packaging exclusion and the whole
reconciliation loop against fake clients. It cannot render a DWM pixel, map a
selection on a scaled monitor, or measure compositor cost -- those are the
Phase 0 gates in `docs/preview-evolution-crops-design.md`, and they are proved
only by running the two commands above on real Windows hardware. The
settings- and alert-dependent behaviors listed under "Safety boundaries" are
not Phase 0 gates at all: they are named pre-release gates in
`docs/smoke-checklist.md` and `docs/preview-crop-prototype-results.md`.
