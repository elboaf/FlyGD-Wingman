# Windows updater native integration harness

This checkout-only harness exercises the same download, handoff-marker,
Attachment Services, protected-file, ShellExecute, and process-handle seams as
`wingman.updates`. It is not included by `packaging/uploader.spec`, adds no app
bridge or environment-variable route, and performs no network request in
`serve` mode. Importing `update_harness.py` is inert on Linux and Windows.

The only installer is `update_fixture.iss`: a no-payload, non-uninstallable,
lowest-privilege Inno fixture. It uses only
`Local\FlyGDWingmanUpdateHarness`. Native file commands accept only the
compiled filename `Wingman-Update-Harness-Setup.exe`; symlinks are refused.
Each invocation creates one temporary staging root and removes only that root.
`attachment` may add Attachment Services metadata to the explicitly supplied
fixture, and `shell-launch` explicitly starts that fixture. `lock-race` copies
the fixture into the temporary root before attempting replacement, so its
source is never changed.

Run these commands from the repository root in PowerShell on Windows. Install
the locked development dependencies first (`uv sync --locked --extra dev`) and
make sure Inno Setup's `iscc` is on `PATH`.

## Compile the harmless fixture

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

Expected on the harmless fixture: the harness prints file identity, size,
SHA-256, and `Zone.Identifier: present`; `Get-Item` lists both the ordinary
data stream and `Zone.Identifier`. A policy rejection or quarantine must
remain a typed updater failure and must not be worked around by weakening host
or Attachment Services validation. Recompile the fixture if local policy
quarantines it.

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
through the protected handle, and ShellExecute starts only the harmless Inno
fixture. The harness prints a non-zero `returned process handle`, then
`process handle closed: yes`. With `mutex-holder` active, the launched fixture
shows the close/OK prompt. Without it, no close prompt appears. An unsigned
local fixture may also show the normal Windows reputation warning; do not
disable zone checks to suppress it.

For a deterministic missing-file launch failure, use a deleted path with the
required harmless fixture filename:

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
