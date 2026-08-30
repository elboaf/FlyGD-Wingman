# EVE settings: reading the .dat

Design. Base: `main` (074a0c6), 2026-08-29.

**Destination:** drop this into FlyGD-Wingman as `docs/eve-settings-decode-design.md`
alongside `docs/preview-config-design.md`. (`eve-settings-design.md` itself
now lives in `docs/history/`; references below use that path.) It is a *live* design, not a
`docs/history/` record — move it there once the work lands.

## Outcome

Wingman gains the ability to read and rewrite the *contents* of a
`core_user_*.dat`, and spends it on two features it cannot build today:

1. **A probe formation editor.** Read, edit and write the account's custom
   probe formations, with presets and a 3D preview.
2. **Selective copy.** Copy the overview and window layout onto ten characters
   without clobbering each one's hand-arranged module slots.

This reverses `docs/history/eve-settings-design.md:503` — *"Explicitly excluded: parsing or
rewriting the contents of a `.dat`"* — and the reversal has to be argued, not
assumed. See **Why the exclusion no longer holds**.

## Provenance and licence

The approach and the format knowledge come from
[eve-wrench](https://github.com/eve-wrench/eve-wrench-app) (Tim Kunze), a Tauri
settings manager that ships all of this today. **Tim gave his consent on Discord
for his code to be used in Wingman.**

`blue-marshal` itself is **MIT**, published on crates.io by TrueBrain
(<https://crates.io/crates/blue-marshal>, repo
<https://github.com/TrueBrain/blue-marshal-rs>). Same treatment in
`THIRD-PARTY-NOTICES.md` — but for the whole static link, not for
`blue-marshal` alone: the sidecar compiles about twenty MIT/Apache-2.0
crates into one executable, and MIT's condition is that the notice travels
with the binary. `packaging/settings-codec/collect_licenses.py` reads
`Cargo.lock`, finds each crate's vendored source, and concatenates every
licence text it ships into a single `settings-codec-COPYING.txt` installed
beside the application. It fails the build rather than skipping a crate it
cannot account for.

## Why the exclusion no longer holds

The original exclusion rested on three claims. Two have changed:

| Original claim | Status |
|---|---|
| "the format is undocumented" | **No longer true.** `blue.Marshal` has a maintained, MIT, lossless Rust implementation built on CCP's own published code. |
| "version-specific" | **Still true**, and it is why the decode dependency is a *third-party* one that gets updated rather than a format we maintain ourselves. |
| "corrupting it costs a user their entire UI layout" | **Still true**, and it is why the architecture below never lets the decoder near the filesystem. |

The exclusion was right when written. What it was protecting against was
*Wingman writing its own parser*. That is still refused. Taking a dependency on
someone else's tested one is a different question, and this design answers only
that one.

## What was verified, and how

Run against `blue-marshal` 1.0.1 with cargo 1.94.1, plus a close read of
eve-wrench at `12e2359`.

| # | Question | Result |
|---|---|---|
| 1 | Is the decode → encode round trip byte-identical for an untouched document? | **Yes.** A settings-shaped document (nested dicts, FILETIME longs, floats, bools, utf8, bytes keys, negative ints, tuples, lists) survived `decode → to_json → from_json → encode` byte-for-byte, at 280 and 285 bytes. |
| 2 | Does the CRC survive? | **Yes, in both directions.** `decode()` reports `had_crc`; feeding it back as `EncodeOptions.checksum` reproduces the original exactly whether or not a checksum was present. A file that had no CRC does not grow one. |
| 3 | Does the JSON bridge lose int-vs-float? | **No.** An int stays an int and an integral float stays `250000.0`. This matters: eve-wrench writes probe coordinates as `f64` unconditionally, so if EVE stores them as ints, its writes silently widen the type. Whether the client cares is question 2 in **Open questions**. |
| 4 | Is splitting the `utf8:` type prefix on the first colon safe for a formation name containing colons? | **Yes.** `"utf8:has:colon:in:name"` round-trips, and splitting once from the left recovers the name exactly. |
| 5 | Is there a Python implementation that could avoid a native dependency? | **None found.** [reverence](https://github.com/ntt/reverence) is Python 2 and read-oriented for cache/bulkdata, not a lossless round trip you would write a settings file with. Searched PyPI and GitHub; treat as "none found", not "none exists". |
| 6 | Does eve-wrench gate writes on EVE not running? | **No.** No process check anywhere in its tree. Wingman already has `Api._eve_client_running()` and the *"The file is in use. Close EVE and retry."* message in `ops._describe`. |

Results 1-4 used documents produced by the library itself. **Slice 0 then ran
the same round trip against real CCP-written files** (2026-08-29, twelve
`core_user_*.dat` from a live Tranquility install, copies only):

| # | Question | Result |
|---|---|---|
| 7 | Does a real `core_user_*.dat` re-encode byte-identically? | **No — semantically identical, and the difference is understood.** The client writes marshal **version 0** (`TY_SIGNATURE`, `0x7e`) with a shared-object table (290 entries, 1,160 trailing bytes). The library always writes **version 1** (`TY_SIGNATURE2`, `0x7d`) and, by documented design, never emits shared references. Output is 179,110 bytes against 154,550 (+16%). Decoding the re-encoded bytes gives JSON identical to the original for all twelve files. `had_crc=false` on every file and the re-encode correctly adds none. |
| 8 | Are probe coordinates ints or doubles? | **Doubles.** Every position and range is `f64` (`184913199104.0`, range `1196782965600.0`). eve-wrench's unconditional `f64` is correct; nothing widens. |
| 9 | What is the formation name's string type? | **Both, by origin.** The client's scratch entry is `"bytes:tempFormation"`; a user-created formation (made in-game 2026-08-29, read back from `settings_Default/core_user_19298063.dat`) is `"utf8:Test"` with id `int:0`, 8 probes, all `f64`, and `selectedFormationID` pointing at `0` with the same FILETIME stamp as `customFormations`. Read both prefixes; write user names as `utf8:`. |
| 10 | Does the EVE client load a version-1 stream? | **Yes** (2026-08-29). With every client closed, `settings_Default/core_user_19298063.dat` was re-encoded untouched (163,145 → 187,338 bytes, `0x7d`, decode-back identical) and published over the live file, backup beside it. The client was launched on that account and closed; it rewrote the file as version 0 (170,409 bytes) with all 353 `ui` keys preserved (320 byte-identical including stamps, the rest restamped by ordinary session churn), the "Test" formation identical (8 probes, same coordinates) and `selectedFormationID` still `0`. A client that failed to read the file would have reset to defaults and the key count would have collapsed. |

`blue-marshal` states `Marshal.cpp` reads both versions natively and eve-wrench
ships on that basis; finding 10 is Wingman's own proof against a real install.
The smoke checklist keeps the line so a client update that changes the answer
is caught by a walk, not by a user.

Corpus caveat: the eleven numbered files were byte-identical to each other —
that profile is itself the output of Wingman's copy — so this is a fair corpus,
not a diverse one.

## Architecture

### The seam

One new module, `wingman/evesettings/marshal.py`, is **the only thing in Wingman
that knows a `.dat` has structure**:

```text
read_document(path) -> dict          # decoded JSON document
write_document(path, doc, *, backup) # re-encode and publish
```

Everything above it works on plain dicts. Everything below it is the sidecar.

### The decoder never touches the filesystem

This is the load-bearing decision and it is where this design diverges from
eve-wrench, which lets its encoder `fs::write` the target directly.

The sidecar is **a pure filter**: bytes on stdin, JSON on stdout, and back. It
opens no files, so it has no path handling to get wrong and nothing to sandbox.
Python keeps everything it already owns:

- `tree.require_under()` for containment, unchanged.
- `backup.create_file_backup()` before the write, unchanged.
- `atomicio` publishes the new bytes — temp in the destination directory,
  fsync, `os.replace` with `replace_with_retry` for the Windows sharing
  violation. `copy_atomic` streams from a file; this needs a bytes sibling
  (`write_bytes_atomic`), which is the same shape as finding 5 in
  `eve-settings-design.md`.
- `Api._eve_mutation` + `_eve_begin`/`_eve_done` for the worker wiring.

So every guarantee the settings layer has today survives the new feature
untouched. The decode dependency buys structure and nothing else.

### Why a bundled sidecar

`blue-marshal` is Rust; Wingman is pure Python with no build step, an explicit
`[tool.setuptools] packages` list, and CI green on ubuntu *and* windows. A
compiled extension breaks several of those at once. A bundled binary does not,
and **the precedent is already in the tree three times**:
`packaging/fetch_autohotkey.py`, `fetch_ffmpeg.py`, `fetch_webview2.py`.

Follow the AutoHotkey pattern exactly, including the part in `CLAUDE.md` about
`hotkeys.py` supervising AHK *"with AHK named nowhere in its public interface"*:

- `packaging/fetch_bluemarshal.py` fetches or builds the CLI, matching its
  siblings' shape and their installer-version coupling.
- `marshal.py` takes an injected runner seam, so the whole module is
  unit-testable on Linux with a fake that returns canned JSON — the same way
  every other Windows-facing subsystem here is tested.
- `test_packaging_completeness.py` today holds one test (subpackage
  declaration) and checks no bundles — `packaging/bin/` carries only FFmpeg in
  the tree, and AutoHotkey is fetched, never committed. A bundle-presence test
  is therefore **new**; put it in that file, skipped when the bundle is absent,
  as the FFmpeg integration tests are.
- The fetcher must decide **build vs download**: a downloaded release artifact
  needs a pinned checksum like `fetch_ffmpeg.py`; a local build needs a Rust
  toolchain step in `release.yml`. An unsigned binary is also a
  SmartScreen/Defender question FFmpeg has already answered once; follow it.
- Modules: `wingman/evesettings/marshal.py` and
  `wingman/evesettings/formations.py` — inside the existing package, so
  `[tool.setuptools] packages` is unchanged.
- Neither "Rust" nor "blue-marshal" appears in `marshal.py`'s public surface.
  A future pure-Python implementation should be a drop-in replacement.

### Where it lands in the UI

**A sub-screen of the Profiles destination, reached from an account row** — not
a fourth EVE destination.

By `PRODUCT.md`'s destination-vs-configuration rule the formation editor is
clearly a destination: you sit and do it, it produces something on its own
screen. But `DESIGN.md` is equally clear that title-bar space is the scarce
resource, and `WM.EVE_ROUTES` already holds two entries. A sub-screen keeps the
rule satisfied without spending the scarce thing, and it matches how a user
reaches it in eve-wrench anyway (the ⋯ menu on an account). Do the
`MIN_WIDTH`/`MIN_HEIGHT` arithmetic before committing to the layout — the CSS
viewport floor is 840x625 at every scaling.

Formations are an **account** (`core_user_*.dat`) concept, so the entry point
belongs on account rows only, and is absent on character rows.

Two things the shell does not have yet, and which should be prototyped with
fake data in `?dev=1` before the layout is committed: account rows carry no
⋯ menu today, and a sub-screen inside a `WM.route` (with its own enter/leave
contract) exists nowhere — sections exist only under Settings. Whether the
editor is a section-style sub-view of the Profiles route or a route of its own
that the title bar never shows is the real decision here.

The 3D preview ports cleanly: eve-wrench's is hand-rolled SVG with a ~40-line
yaw/pitch projection and no library, which is already the shape `wingman/web/`
wants. No framework, no build step, no new dependency.

### As built

Slice 1 shipped with four deviations from the plan above, all deliberate:

- The Python module is `wingman/evesettings/codec.py`, not `marshal.py` —
  `marshal` is a stdlib module name and same-named files have shadowed the
  stdlib in this repo's tooling before.
- The sidecar is not a fetched `blue-marshal` binary but Wingman's own
  ~60-line crate at `packaging/settings-codec/`, over `blue-marshal =1.0.1`,
  built by cargo in `.github/actions/build-installer/action.yml`. Upstream's
  own `marshal-tool` CLI is file-path based and always appends a checksum,
  which does not fit the pure-filter, `had_crc`-preserving seam this design
  needs; wrapping the library directly does. It is a pure stdin/stdout filter
  with `decode`/`encode` subcommands and an `{had_crc, doc}` envelope, and it
  never opens a file. `write_document` verifies its own output by decoding it
  back before any backup or publish.
- The state key is `formations_available`, not `decode_available` — the page
  is hiding a *feature*, and a mechanism name (naming the codec) would
  outlive a future pure-Python codec replacing the sidecar.
- The editor is its own route id, `#route-formations`, reached from a fourth
  Profiles card ("Probe formations", an account `<select>` plus "Edit
  formations…"), added to `WM.EVE_ROUTES` but never shown in the title bar —
  not a hidden face of `#route-evesettings`. `test_page_conventions.py`
  allows only one `.btn.acc` per route, and the account roster has no
  per-row controls to hang a second entry point off.

Two format-note rules landed stricter than drafted above: `read_formations`
refuses (raises) any file it does not fully understand, including a
present-but-malformed formations container, rather than skipping the parts
it cannot read; and `from_payload` rejects negative ids outright rather than
treating them as valid input, since negative ids are reserved client scratch
state (see the FILETIME/scratch note above).

## The format

Formations live in the **account** file under
`ui → probescanning.customFormations`:

```text
"bytes:probescanning.customFormations": {"tuple": [<FILETIME>, {
    "int:0": {"tuple": ["utf8:Pinpoint", [        // utf8: for user names; the -4 scratch entry is bytes:
        {"tuple": [{"tuple": [x, y, z]}, range]},   // one per probe, max 8
        ...
    ]]}
}]}
```

Notes that cost a debugging session each if missed:

- **Positions and ranges are `f64` meters** (verified, finding 8). The editor should work in km and AU and
  convert only at the boundary. Valid scan ranges are powers of two from
  0.25 to 32 AU; keep an out-of-range value from an existing file selectable
  rather than silently rewriting it.
- **Every leaf is a `(FILETIME, value)` tuple.** FILETIME is 100ns intervals
  since 1601-01-01: `(unix_secs + 11_644_473_600) * 10_000_000`. Re-stamp the
  key you change.
- **Negative ids are client scratch state.** `-4` is `tempFormation`, holding
  your currently launched probe positions. Hide them from the user and write
  them back untouched — eve-wrench does this and has a regression test for it.
- **`probescanning.selectedFormationID` is a sibling pointer that must be
  remapped, not validity-checked.** This is a live bug in eve-wrench: it
  renumbers formation ids by array index on save, then only checks the pointer
  still names *an* id that exists. After renumbering the ids are always
  `0..n-1`, so any pointer below `n` passes while now naming a different
  formation — reorder your formations and the client's selection silently moves.
  Carry the original ids through the editor, mint new ids only for new
  formations, and map old→new.
- **Preserve `had_crc`.** Verified above; do not add a checksum to a file that
  lacked one.
- **EVE re-centres a launched formation on its centroid**, so only zero-centroid
  formations launch as drawn. eve-wrench's counterweight-probe handling is
  correct and worth porting wholesale, including the presets that bake it in.
- **The launcher holds 8 probes.** Cap new probes at 8, and say something about
  a file that already holds more rather than silently truncating.
- **A file the parser does not fully understand is refused, not trimmed.** The
  write rebuilds the whole formations key from what the read returned, so an
  entry skipped on read would be deleted on the next save. Refuse to open the
  editor and say why; the file is left untouched.
- **Formation names must be unique (case-insensitive).** Not a file-format
  rule — the client keys on id — but the editor's list is by name, so two
  identical names are indistinguishable to the user. Editor-side validation.

## Scope

**Slice 0 — the gating probe. Done 2026-08-29**, findings 7-9 above:
semantically identical, version 0 → version 1, doubles, `bytes:` names. Two
small gates remain before a write path ships:

- **The client reads a version-1 file.** With EVE closed, re-encode one
  account's file untouched, publish it through the normal backup path, launch
  the client, confirm the UI layout and formations survive, then restore the
  backup. Manual; goes in `docs/smoke-checklist.md`.
- ~~The shape of a real custom formation.~~ Done (finding 9): first user
  formation is id `0`, name `utf8:`, and the client stamps `customFormations`
  and `selectedFormationID` with the same FILETIME — re-stamp both together.

**Slice 1 — `marshal.py`, the sidecar, and the probe formation editor.**
Formations first, revising the order I would have guessed: the formation write
replaces **one key in an otherwise untouched document**, while selective copy
merges two documents wholesale. The smaller write surface should be the one that
proves the seam. It is also the more reversible failure — a wrong formation is
visibly wrong and one restore away, where a wrong merge quietly ships wrong
settings to ten characters at once — and eve-wrench ships a round-trip test for
exactly this path that ports directly.

**Slice 2 — selective copy.** Groups of keys, each a checkbox, unchecked groups
keeping the target's own values. Port eve-wrench's group table
(`evesettings.rs:955`) and its defaults (module slot layout and typed search
history off).

One non-obvious detail is worth copying exactly: **clone the source document
whole, then restore only the excluded groups from the target.** That way a key
no group knows about still travels, so an unmapped setting behaves like a normal
copy rather than silently not copying. It is easy to build backwards and the
backwards version fails silently.

**`eve_settings_state` gains a boolean** so Profiles can hide the formation
entry point when the sidecar is missing (open question 4). Name it now:
`test_bridge_contract.py` and `dev.js` both need it. The plan names it
`formations_available` rather than `decode_available`: the page hides a
feature, and a payload key naming the mechanism would outlive a pure-Python
codec replacing the sidecar.

**Deferred:** account aliases keyed on the numeric id (this is `eve-settings-design.md`'s
deferred #6, and the id is the "stabler than the full path" key that
design asked for — it needs no decode and could ship before any of this);
export/import with a pre-write conflict analysis; ESI portraits on roster rows.

## Testing

| Module | Coverage |
|---|---|
| `marshal.py` | Round trip through a fake runner; a sidecar that exits non-zero, writes garbage to stdout, or hangs, each surfacing as `MarshalError` and leaving the file untouched; the real binary exercised in one integration test skipped when the bundle is absent. |
| `atomicio.write_bytes_atomic` | Beside the existing `copy_atomic` tests: temp created in the destination directory, no debris on failure, `replace_with_retry` on a locked destination. |
| `formations.py` | Parse/serialise round trip; negative ids hidden but preserved; `selectedFormationID` remapped across a reorder (the eve-wrench bug, as a regression test); centroid and counterweight maths; km/AU conversion at the boundary. |
| `ui/api.py` | Thin delegation, mutation lock, and the running-EVE confirm — following `test_api_bookmarks.py`. |
| `test_bridge_contract.py` | Every new `_push` name in `WM.HANDLERS`. Extend, do not duplicate. |

**What cannot be tested here**, and belongs in `docs/smoke-checklist.md`:

- Edit a formation with EVE closed → the client shows it on next launch.
- Edit with EVE **running** → refused with the *close EVE and retry* message,
  file intact. eve-wrench claims no restart is needed; Wingman should not repeat
  that claim until this line has been walked, because EVE holds `core_*.dat`
  open for a session and rewrites it on exit.
- Restore the pre-edit backup → the old formations come back.
- A formation saved by Wingman, then edited in the client, then read again.

## Open questions

1. ~~Does a real `core_user_*.dat` re-encode byte-identically?~~ **Answered**
   (finding 7): no, semantically identical; version 0 with shared refs in,
   version 1 flat out, +16%. Remaining gate: the client reads version 1.
2. ~~Are probe coordinates ints or doubles?~~ **Answered** (finding 8):
   doubles. Nothing widens.
2b. ~~What does the client write for a user-created formation?~~ **Answered**
   (finding 9): `utf8:` name, ids from `0`, both keys stamped together.
3. **Does the sidecar survive the frozen build and the installer?** The
   precedent is strong but unproven for this binary. Fails loudly at
   `test_packaging_completeness.py` rather than at a user, which is the right
   failure.
4. **What happens if the sidecar is missing at runtime?** Proposed: the
   formation entry point is hidden and the rest of Profiles works exactly as it
   does today. The decode dependency must never be able to take the existing
   copy/backup features down with it.
