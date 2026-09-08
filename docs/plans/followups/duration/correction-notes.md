# Captured-duration correction — implementation checkpoint

## Scope and contract

Approved by coordinator U-01/E-01; fixed base `ab06a6efde9ade0f40791d812d922356e8e6c16f`, worktree `.worktrees/followup-duration`, branch `test/followup-duration`. Integration against later main is coordinator-owned. Production changes are confined to `wingman/upload/controller.py`; RowSnapshot, durations cache schema, bridge, WorkGate and rename/link persistence implementation are unchanged.

- `_duration_verdict` selects an exact `(current path, size, mtime)` definitive answer from retained RAM or the cache; `probed and answered` and the cache hit flag distinguish final None from no verdict. All known exact representations converge at acceptance, so a later candidate cannot supersede an accepted definitive winner. Queue time does not establish precedence.
- `_reconcile_duration` runs under publication, after background run/generation admission or a foreground probe's return. It resolves detached captures directly but changes installed VideoInfos only through their current IDs and `RowSnapshot.set_duration`, preserving frozen cell text and definitive bookkeeping. It returns cache dirtiness separately from duration payloads; producers record that dirtiness before attempting publication and save once per drain/selection in `finally`.
- `_cache_duration` admits writes only for an eligible single path slot. A different installed owner blocks the old write even when unprobed. Without a current owner, an occupied conflicting slot is preserved. A same-identity slot or empty unowned slot can remember the winner. Nothing prunes.
- `_install_scan` shares winner lookup before installing new objects. If a retained RAM winner was previously refused caching, a newly accepted exact-identity scan hydrates it and can persist it once that scan establishes slot ownership. The scan still installs fresh objects and IDs; no strong historical registry or object reuse is introduced.
- `_listed_infos` is snapshotted briefly under its existing link-store protection. Publication remains outermost; link-store is released before any duration delivery. Cache helpers keep their existing internal locking. No ffprobe/scan runs under publication; cache batch saves remain independent of row liveness. Rename-adjusted capture paths remain authoritative; no historical aliases are created. URL durability still precedes waiting for UI publication.

## Test-first evidence

The original eight-case regression is preserved (shared real archive setup was extracted into a lane-local test helper without changing its joint assertions). Its historical red evidence remains local in `regression-output.txt`: 7 failed / 1 same-row control passed. Coordinator independently reproduced it before implementation.

Before source edits, added 13 parameterized cases all failed on the fixed-base controller: `implementation-red-output.txt`, **13 failed, 46 deselected in 5.78s**. They exercise:

- changed size and changed mtime with the replacement still unmeasured;
- both acceptance orders across refresh → rename → equal-metadata old-path reuse;
- detached folder-switch captures, with/without a conflicting cache slot, for duration/definitive None/no-verdict;
- retained uncached duration and definitive None surviving a fresh scan and reaching disk once admitted;
- the real full upload worker/log tail, a saved and hydrated URL, exact real ZIP window, WorkGate held during the log probe and released afterward.

All tests use real temporary filesystem scans, rows and disk serialization. Events/manual scheduling control races; no sleeps, synthetic desired-state assignments or shared fixture changes. External Google authentication/upload and Discord posting are stubbed; no live credentials/network writes or native EVE operations are performed.

## Initial green checkpoint verification

All commands run from the dedicated worktree with its own `.venv` and its own codec build/output. No borrowed editable installs or sidecars.

```bash
uv sync --locked --extra dev
node --version
# v26.5.0
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
uv run --no-sync python -m pytest tests/test_uploader_lifecycle_races.py tests/test_api_upload.py tests/test_rows.py tests/test_durations.py tests/test_combatlog.py tests/test_uploader.py tests/test_upload_media_close.py tests/test_uploader_http_errors.py tests/test_api_quick_actions.py tests/test_links.py tests/test_library.py tests/test_api.py tests/test_api_updates.py -q -rs
# 532 passed in 20.66s
uv run --no-sync python -m pytest tests/ -q -rs --junitxml=docs/plans/followups/duration/implementation-full.xml
# 8,532 passed, 11 skipped in 573.82s
uv run --no-sync ruff check .
# All checks passed
uv run --no-sync ruff format --check .
# 329 files already formatted
node scripts/js_smoke.js
# All index/fleetbar/sigbar modules passed
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored
git diff --check
# Passed
```

The 11 skips are exclusively Windows requirements: five real-junction cases, one DPAPI, one WinDLL, one real message-pump/window-station, and three Win32 binding cases. No Node or native-codec skips. Bulky full output/JUnit/red records stay local in this lane directory and are not implementation-commit contents.

This is the **pre-polish green candidate checkpoint**, not final coordinator acceptance. Committed-range polish and fresh post-polish verification follow. The earlier implementation-notes.md remains preserved locally as the historical RED-only packet, not current status.

## Limits and proposed native smoke additions

No native Windows/WebView2, hosted CI or real ffprobe concurrent replacement behavior is claimed. Native smoke should use disposable recordings/state and scripted network outcomes: upload/log probe overlapping list refresh; replacement snapshot rename followed by old-name reuse when uploads are not claimed; folder switch during retained-capture resolution; verify row length, reloaded cache, ZIP UTC window, URL durability and gate release together. Check duration pushes reach only current IDs and UI remains responsive while ffprobe is blocked. Do not mark central smoke records from these headless results.

The identity scheme still cannot distinguish an external replacement with identical path/size/mtime. No new retry policy for already-probed no-verdict objects is added. Detached winners whose cache slot remains ineligible survive only while a real owner retains their VideoInfo; that is intentional, not a durable history. Existing duration save failure remains best effort. These constraints do not justify a schema, strong registry or cache pruning change in this lane.
