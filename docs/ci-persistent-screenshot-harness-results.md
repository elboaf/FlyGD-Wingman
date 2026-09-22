# Persistent screenshot harness results

## Task 0 baseline and scope freeze

Task 0 records evidence only. It changes no production or test behavior and does not delete, pairwise-reduce, rename, or reparameterize any existing screenshot business scenario. No matrix deletion occurs in this tranche.

### Source and hosted identities

| Identity | Evidence |
|---|---|
| Authoritative merged source base | [`c4a2b2060de8f8317e61a732708a9b5bd88beb98`](https://github.com/elboaf/FlyGD-Wingman/commit/c4a2b2060de8f8317e61a732708a9b5bd88beb98), `Cut Fleet test runtime without dropping contracts (#277)` |
| Task 0 implementation start | `e8c636344fa9701c533a7f96436de8ee53f02557`, `docs: plan persistent screenshot harness` |
| `git merge-base HEAD main` at collection | `c4a2b2060de8f8317e61a732708a9b5bd88beb98` |
| Hosted comparator PR | [PR #277](https://github.com/elboaf/FlyGD-Wingman/pull/277) |
| Hosted comparator run | [`35684157184`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184) |
| Hosted comparator PR head | `2ed88f372edba7f94cd815d484595960236b984b` |
| Hosted comparator Actions checkout | synthetic merge `94e0cd8f0fb84cb8dd4451ba84121674194c8787` (`Merge 2ed88f372edba7f94cd815d484595960236b984b into cfa1aca256c2aadf7082bbb5061275c749e345c6`) |
| Windows comparator job | [`106607316881`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316881), successful |
| Ubuntu job recorded with the run | [`106607316829`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316829), successful |

The Actions checkout log shows that all three jobs fetched and checked out synthetic merge `94e0cd8f0fb84cb8dd4451ba84121674194c8787`, not the PR head directly and not the later squash merge `c4a2b2060de8f8317e61a732708a9b5bd88beb98`. The log records `HEAD is now at 94e0cd8 Merge 2ed88f37... into cfa1aca2...` for checks, Ubuntu, and Windows.

Reconstructing that checkout with:

```bash
git merge-tree --write-tree cfa1aca2 2ed88f37
# eb93f6f02270af7a49251f2998e8ef047b374002
```

produces exactly the tree recorded by GitHub's commit API for `94e0cd8`. The six workload-defining blobs below are byte-identical between that reconstructed synthetic merge and squash `c4a2b206`:

| Path | Synthetic-merge blob | `c4a2b206` blob |
|---|---|---|
| `tests/test_shoot_screens.py` | `8ac28c6911c0474624b15be4def2d647b326fd88` | `8ac28c6911c0474624b15be4def2d647b326fd88` |
| `tests/test_new_screenshots.py` | `dc6ac94873923b0a7f53d6ffa1047fab77c4fd7d` | `dc6ac94873923b0a7f53d6ffa1047fab77c4fd7d` |
| `tests/test_current_screenshots.py` | `62db1fa43386c615c312b8bfd78015424cb76c77` | `62db1fa43386c615c312b8bfd78015424cb76c77` |
| `tests/test_fittings_page.py` | `e7e87cd4b4474495140154db01a1254e24fb7d2c` | `e7e87cd4b4474495140154db01a1254e24fb7d2c` |
| `tests/fixtures/screenshot_pages.cjs` | `ef60e44b95e4f11ec75ff769fe1d1b2c2bb3747c` | `ef60e44b95e4f11ec75ff769fe1d1b2c2bb3747c` |
| `tests/fixtures/current_screenshot_pages.cjs` | `910acc4f211dd0e6c8a54b05ebec0a5ac7cec0b4` | `910acc4f211dd0e6c8a54b05ebec0a5ac7cec0b4` |

The shared normalized 572-node set remains supporting evidence. Exact blob equality is the primary proof that the hosted comparator measured the same four target tests and both pre-worker screenshot fixtures; the SHAs themselves are not treated as interchangeable.

### Exact 572-node inventory

The tracked base inventory is:

```text
tests/fixtures/persistent_screenshot_harness_base_nodes.txt
```

It was produced before screenshot-harness source changes with:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  | python -c "import sys; print(''.join(sorted(line for line in sys.stdin if line.startswith('tests/') and '::' in line)), end='')" \
  > tests/fixtures/persistent_screenshot_harness_base_nodes.txt
```

| File | Exact base nodes | PR #277 Windows testcase sum |
|---|---:|---:|
| `tests/test_shoot_screens.py` | 240 | 38.610s |
| `tests/test_new_screenshots.py` | 89 | 26.005s |
| `tests/test_current_screenshots.py` | 156 | 25.852s |
| `tests/test_fittings_page.py` | 87 | 23.838s |
| **Total** | **572** | **114.305s** |

The tracked file contains 572 sorted, unique lines, is 61,106 bytes, and has SHA-256 `222ba095dfdfb010a62d10e8ae2209ac2840b3bb985bc0c02f345b8fc9e7a4eb`.

### PR #277 Windows artifact normalization

The Windows evidence was downloaded with:

```bash
rm -rf /tmp/wingman-pr277-screenshot-baseline
mkdir -p /tmp/wingman-pr277-screenshot-baseline
gh run download 35684157184 -R elboaf/FlyGD-Wingman \
  -n pytest-evidence-windows-latest \
  -D /tmp/wingman-pr277-screenshot-baseline
```

Artifact inputs and normalized output:

```text
/tmp/wingman-pr277-screenshot-baseline/pytest-result.xml
/tmp/wingman-pr277-screenshot-baseline/pytest-timing.json
/tmp/wingman-pr277-screenshot-baseline/persistent_screenshot_harness_target_nodes.txt
```

The exact normalization command was:

```bash
python -c "import xml.etree.ElementTree as ET; from pathlib import Path; source=Path('/tmp/wingman-pr277-screenshot-baseline/pytest-result.xml'); target=Path('/tmp/wingman-pr277-screenshot-baseline/persistent_screenshot_harness_target_nodes.txt'); modules={'tests.test_shoot_screens','tests.test_new_screenshots','tests.test_current_screenshots','tests.test_fittings_page'}; root=ET.parse(source).getroot(); rows=sorted(tc.attrib['classname'].replace('.', '/') + '.py::' + tc.attrib['name'] for tc in root.iter('testcase') if tc.attrib.get('classname') in modules); target.write_text(''.join(x+'\\n' for x in rows), encoding='utf-8'); print(target); print(len(rows)); print(target.stat().st_size)"
cmp /tmp/wingman-pr277-screenshot-baseline/persistent_screenshot_harness_target_nodes.txt \
  tests/fixtures/persistent_screenshot_harness_base_nodes.txt
```

All 572 target testcases use one of four module-only classnames:

```text
tests.test_shoot_screens
tests.test_new_screenshots
tests.test_current_screenshots
tests.test_fittings_page
```

There are no class-method testcase classnames in this four-file artifact set, so the required reversible mapping is exactly `classname.replace('.', '/') + '.py::' + name`; no class suffix needs to be split or reconstructed. The normalized artifact file is also 61,106 bytes with SHA-256 `222ba095dfdfb010a62d10e8ae2209ac2840b3bb985bc0c02f345b8fc9e7a4eb`. `cmp` returned exit 0. The 572 target artifact cases contain zero failures, zero errors, and zero skips.

### One-shot Node launch inventory

The call-site inventory command was:

```bash
rg -n "subprocess\.run|screenshot_pages\.cjs|current_screenshot_pages\.cjs|_run_fittings_node" \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py
```

The launch-bearing call sites at the base are:

| Owner | Call site | Harness |
|---|---|---|
| Generated screenshot gap captures | `tests/test_shoot_screens.py:217` and `:220` | `tests/fixtures/screenshot_pages.cjs` |
| Alerts capture framing, explicitly out of scope | `tests/test_shoot_screens.py:2068` | `tests/fixtures/screenshot_alerts.cjs` |
| New screenshots | `tests/test_new_screenshots.py:65` and `:68` | `tests/fixtures/screenshot_pages.cjs` |
| New-screenshot Fittings pending-confirmation cases | `tests/test_new_screenshots.py:134` via imported `_run_fittings_node` | embedded Fittings harness |
| Current-owner screenshots | `tests/test_current_screenshots.py:437` and `:440` | `tests/fixtures/current_screenshot_pages.cjs` |
| Fittings harness launch | `tests/test_fittings_page.py:1971`, called at `:2016` and `:2037` | embedded Fittings harness |

The exact family derivation is:

| Family | Derivation | Current child launches | Worker scope |
|---|---|---:|---:|
| Migrated generated gap screenshots | `35` semantic framing + `13` geometry + `7` metadata + `4` profile scope + `10` lower outcomes + `18` retained context/footer + `1` recovery ordering + `26` progress/result/limit corruption | 114 | 114 |
| Alerts | `15` base-state cases + `8` anchor omission/visibility cases + `8` clipped-edge cases | 31 | 0 |
| New screenshots | `11` fidelity/writer-exit + `2` identity collisions + `2` Fittings pending-confirmation + `17` Groups geometry + `5` staging + `13` detail + `17` live-control + `6` dialog-started + `2` parser-started + `3` terminal-operation cases | 78 | 78 |
| Current-owner screenshots | `9` Preview subpages + `40` synthetic-owner cases + `7` live cards + `3` cold cleanup + `1` live dialog + `8` sharing lifecycle + `3` refresh authority + `2` Wanderer fence + `5` Fleet pending + `3` Sharing pending + `1` focus restoration | 82 | 82 |
| Fittings | `29` accessibility/dialog/interleaving cases + `11` state-machine scenarios run from the aggregate state node | 40 | 40 |
| **Total** |  | **345** | **314** |

The persistent-worker scope therefore migrates 314 current Node child launches. The 31 `screenshot_alerts.cjs` launches remain one-shot and unchanged because Alerts geometry ownership is outside this tranche. The hosted Windows file sums above are recorded as measured evidence only; no Windows seconds-per-launch value is inferred.

### Allowed changed paths

Final scope compares the completed tranche against this exact 15-path allowlist. The final polish explicitly justifies the added shared DOM factory and worker lifecycle source/tests; it does not authorize any production, workflow, or configuration path.

```text
docs/ci-persistent-screenshot-harness-results.md
docs/superpowers/plans/2026-09-22-persistent-screenshot-harness.md
tests/conftest.py
tests/fittings_scenario_worker.py
tests/fixtures/current_screenshot_pages.cjs
tests/fixtures/fittings_page.cjs
tests/fixtures/persistent_screenshot_harness_base_nodes.txt
tests/fixtures/screenshot_dom.cjs
tests/fixtures/screenshot_pages.cjs
tests/node_scenario_worker.py
tests/test_current_screenshots.py
tests/test_fittings_page.py
tests/test_new_screenshots.py
tests/test_node_scenario_worker.py
tests/test_shoot_screens.py
```

No production, workflow, packaging, configuration, marker-policy, persisted-data, screenshot-key, generated-expression, or pywebview path is authorized by this plan.

## Task 6 local inventory and verification

### Local identity and decision boundary

The local evidence run started from clean worktree HEAD
`71545c5605f8fa86e2df164b5f4be368840c20c8` (`test: isolate Fittings timer
callback this`) on branch `ci-ui-harness-consolidation`. The source comparison
base remains `c4a2b2060de8f8317e61a732708a9b5bd88beb98`.

The local host was WSL2 Linux
`6.6.87.2-microsoft-standard-WSL2`, x86-64, with Python 3.11.15, pytest 9.1.1,
Node v26.5.0, Cargo 1.91.0, rustc 1.91.0, and Ruff 0.16.7. These Linux results
prove local correctness and isolation only. They are not projected into Windows
runtime savings.

No branch was pushed, no pull request was created, and no hosted workflow was
dispatched. The only hosted data in this document remains the PR #277 reference
artifact described above, with its exact checkout caveat. A comparable hosted
Windows/Ubuntu measurement for this tranche is **pending**. Therefore the local
decision is **LOCAL PASS / HOSTED PENDING**; it is not a hosted GO, and Plan B
(matrix consolidation) remains unauthorized.

### Exact 572 to 597 node-set proof

Final collection used the required command:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider \
  > /tmp/wingman-screenshot-harness-final-nodes.txt
```

Filtering lines beginning with `tests/` and containing `::`, then comparing sets
against `tests/fixtures/persistent_screenshot_harness_base_nodes.txt`, produced:

```text
base count/unique: 572 / 572
final count/unique: 597 / 597
removed: 1
added: 26
net: +25
all base IDs retained except the authorized aggregate: yes
```

Final per-file counts are exact:

| File | Base | Final | Change |
|---|---:|---:|---:|
| `tests/test_shoot_screens.py` | 240 | 246 | +6 protocol/isolation |
| `tests/test_new_screenshots.py` | 89 | 90 | +1 protocol/isolation |
| `tests/test_current_screenshots.py` | 156 | 160 | +4 protocol/isolation |
| `tests/test_fittings_page.py` | 87 | 101 | -1 aggregate, +11 split identities, +4 protocol/isolation |
| **Total** | **572** | **597** | **+25** |

The only removed ID is:

```text
tests/test_fittings_page.py::test_fittings_state_machine_in_node
```

Its eleven replacement IDs are:

```text
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-copy-lifecycle]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-detail-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-rejected-mutation]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-request-sequence]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-route-lifecycle]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-screenshot-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-selection-scope]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-preflight]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-progress]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-stale-start-result]
tests/test_fittings_page.py::test_fittings_state_machine_in_node[state-ticket-progress]
```

The fifteen added protocol/isolation IDs are:

```text
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_current_screenshots.py::test_current_screenshot_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_current_screenshots.py::test_current_screenshot_worker_isolates_owner_families
tests/test_current_screenshots.py::test_current_screenshot_worker_vm_failures_preserve_stack_and_recover
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_fittings_page.py::test_fittings_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_fittings_page.py::test_fittings_worker_reuses_process_and_preserves_business_outcomes
tests/test_fittings_page.py::test_fittings_worker_vm_failures_preserve_stack_and_recover
tests/test_new_screenshots.py::test_new_screenshot_worker_reuses_process_and_preserves_negative_contracts
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-assertion-exit]
tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer[pending-timer-normal-exit]
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[covered-settled-hidden]
tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent[settled-missing-settled]
tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes
tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover
```

There are no other additions or removals. Thus every pre-existing business node
remains, except that the one aggregate Fittings node is represented by its same
eleven scenarios as eleven independently reportable nodes. The raw collection
artifact path, 63,564-byte size, and SHA-256
`9ed430e815799c37b5bba9f815e933e98543df1543c058da016e8d852a60a5f6` are
run-specific metadata because pytest appends an elapsed-time footer. Reproducible
identity evidence is the filtered 597-line forward node list described below:
597 unique IDs with SHA-256
`4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7`.

### Process topology and reuse

The frozen pre-change inventory is 345 Node child launches: 314 in scope and 31
unchanged Alerts launches. The 314 business launches remain the same scenario
inventory after conversion: 114 generated-gap requests, 76 ordinary new-
screenshot requests, 82 current-owner requests, and 42 Fittings requests (40
from the Fittings file plus the two pending-confirmation requests owned by the
new-screenshot file).

A temporary `/tmp` `node` wrapper logged every Node process start during the
normal four-file run and then `exec`'d the real Node binary. The test command was:

```bash
PATH=/tmp/wingman-node-wrapper:/home/tng/.local/bin:/home/tng/.local/share/mise/installs/node/26.5.0/bin:/home/tng/.cargo/bin:/usr/local/bin:/usr/bin:/bin \
  uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  -q -rs --durations=50
```

The trace contained exactly 35 distinct process starts/PIDs:

| Node entry point | Starts | Topology |
|---|---:|---|
| `tests/fixtures/screenshot_pages.cjs` | 2 | one session worker for generated-gap markup and one for standard new-screenshot markup |
| `tests/fixtures/current_screenshot_pages.cjs` | 1 | one current-owner session worker |
| `tests/fixtures/fittings_page.cjs` | 1 | one root-session worker shared by `test_new_screenshots.py` and `test_fittings_page.py` |
| `tests/fixtures/screenshot_alerts.cjs` | 31 | deliberately unchanged one-shot Alerts harness |
| **Total** | **35** | **4 persistent workers + 31 unchanged Alerts launches** |

There were no persistent-worker restarts in that target run, despite assertion,
rejection, and pending-timer probes. The two `screenshot_pages.cjs` processes are
intentional separate harness families with different immutable markup. The
single Fittings process is shared across its two Python modules regardless of
which file is requested first.

### Order-isolation evidence

The four files passed in normal and reverse file order:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  -q -rs --durations=50
# 597 passed in 75.43s

uv run --no-sync python -m pytest \
  tests/test_fittings_page.py \
  tests/test_current_screenshots.py \
  tests/test_new_screenshots.py \
  tests/test_shoot_screens.py \
  -q -rs --durations=50
# 597 passed in 75.47s
```

Three explicit 597-node argument lists were generated from final collection and
executed directly, without an ordering plugin, by passing every line as a pytest
argument:

| Order | Construction | SHA-256 | Result |
|---|---|---|---|
| Forward | collection order | `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7` | 597 passed in 73.57s |
| Reverse | exact reversed list | `22855de6df815148424d1f81c35232cacd3a63bf4b8180230fec752b6d66d695` | 597 passed in 74.39s |
| Shuffled | `random.Random(20260922).shuffle(...)` | `a02deeda92e9853e747e85281676164c62517d365a7f7ab60f0b70717b2577ab` | 597 passed in 75.58s |

Each list contains 597 unique IDs and the same exact set. The files are:

```text
/tmp/wingman-screenshot-harness-forward-nodes.txt
/tmp/wingman-screenshot-harness-reverse-nodes.txt
/tmp/wingman-screenshot-harness-shuffle-seed-20260922-nodes.txt
```

The fifteen new protocol/isolation nodes were also executed alone from an
explicit list:

```text
15 passed in 9.72s
JUnit: /tmp/wingman-persistent-screenshot-protocol.xml
SHA-256: d8ee7347616b778963522b03679977118d1014e5fff831b54117e849cfb5ad05
```

Together the tests prove:

- existing negative business scenarios (`missing`, `covered`, `hidden`,
  `invalid`, and geometry corruption) still return their exact `PASS` labels;
- A to B to A generated-screenshot sequences, current owner-family switches,
  and Fittings ordinary/dialog/screenshot switches retain no request state;
- VM throws and unhandled rejections produce `NodeScenarioFailure` with the
  named JavaScript function in the preserved stack;
- assertion-style and pending-timer failures complete listener/timer cleanup,
  recover on the next business request, and keep the same process;
- every request receives a fresh VM, DOM, bridge queues, mutable fixture clone,
  timers/intervals, rejection listener, console, focus, scroll, and owner state;
- timeout, crash, malformed reply, schema mismatch, and reply-ID mismatch paths
  discard the process and restart through `NodeScenarioWorker`.

The independent worker protocol suite confirms the final item and diagnostic
rendering:

```bash
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py \
  -q -rs --durations=20 \
  --junitxml=/tmp/wingman-node-scenario-worker.xml
# 9 passed in 3.93s
```

Its JUnit SHA-256 is
`eccde7cbca029b29e1881b2b34b95bf7761c21d35beddd87be52b2309a5b8629`.

Node-absence behavior remains intentionally asymmetric and unchanged:
`test_shoot_screens.py`, `test_new_screenshots.py`, and
`test_current_screenshots.py` assert `node is not installed` from their worker
fixtures; `create_fittings_worker()` also asserts rather than skips; and the
existing Fittings-owned tests retain their explicit `skipif` markers. No shared
factory calls `pytest.skip()`.

### Prerequisites and focused JUnit

The prerequisite commands produced:

```bash
node --version
# v26.5.0

cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
# Finished release profile in 4.70s

uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
# source: packaging/settings-codec/target/release/wingman-settings-codec
# target: packaging/bin/wingman-settings-codec
# codec.codec_available(): True
```

The required focused run was:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  -q -rs --durations=50 \
  --junitxml=/tmp/wingman-persistent-screenshot-focused.xml
```

Result: **597 passed in 77.65s**, with zero failures, errors, or skips. The JUnit
file is 87,671 bytes with SHA-256
`a54bc20474b8350aa6f625e84538ed29ef3ef34c6bc428fe20ef71fcf6ce700d`.
Local Linux testcase sums were 29.739s for `test_shoot_screens.py`, 13.705s for
`test_new_screenshots.py`, 16.464s for `test_current_screenshots.py`, and
10.829s for `test_fittings_page.py`. These are local evidence only and are not
compared numerically with Windows.

### Full local verification and skip inventory

The required full-suite command was:

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-persistent-screenshot-full.xml
```

Result: **16,683 passed, 14 skipped in 552.45s (9m12s)**; zero failures and zero
errors across 16,697 JUnit cases. The JUnit testcase-time sum is 492.123s. The
file is 2,507,255 bytes with SHA-256
`1f82d7e6ea4912c1c89a15cb7495b0425b05092bd1e276a29a1ff63bec2a0053`.

Exact skip inventory:

| Test | Reason |
|---|---|
| `tests.test_clipserve.test_a_live_reader_does_not_block_deletion` | delete-while-open is a Windows sharing rule |
| `tests.test_evesettings_profilecopy.test_prepare_copy_rejects_a_real_windows_server_junction_outside_the_root` | requires a real Windows junction |
| `tests.test_evesettings_profilecopy.test_prepare_copy_rejects_a_real_windows_profile_junction_outside_the_server` | requires a real Windows junction |
| `tests.test_evesettings_profilecopy.test_cleanup_refuses_a_stage_shaped_windows_junction_rather_than_following_it` | requires a real Windows junction |
| `tests.test_eveskills_dpapi.test_round_trips_on_windows` | requires real DPAPI |
| `tests.test_eveskills_dpapi.test_crypt32_binding_is_cached` | requires real WinDLL |
| `tests.test_preview_host.test_stop_from_another_thread_really_exits_the_pump` | needs a real message pump and window station |
| `tests.test_preview_win32.test_every_used_function_is_declared` | binds user32/gdi32/dwmapi |
| `tests.test_preview_win32.test_pointer_sized_returns_are_not_left_at_the_c_int_default` | binds user32/gdi32/dwmapi |
| `tests.test_preview_win32.test_bind_is_cached_so_declarations_are_applied_once` | binds user32/gdi32/dwmapi |
| `tests.test_tray.test_adapter_loads_against_the_pinned_pystray_windows_backend` | pystray Windows backend |
| `tests.test_ui_setup_profile.test_recognized_file_shaped_junction_refuses[core_char_31.dat]` | requires real Windows junction |
| `tests.test_ui_setup_profile.test_recognized_file_shaped_junction_refuses[prefs.ini]` | requires real Windows junction |
| `tests.test_wanderer_integration.test_real_windows_credential_document_roundtrip_replace_binding_and_remove` | real Windows user-bound DPAPI required |

There are no Node-availability skips and no codec-availability skips.

The independent gates all passed:

```text
node scripts/js_smoke.js
  PASS every page module loaded

node --test tests/fixtures/screenshot_dom.test.cjs
  35 passed, 0 failed, 0 skipped, duration 124.452439ms

cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
  1 passed, 0 failed

uv run --no-sync ruff check .
  All checks passed!

uv run --no-sync ruff format --check .
  520 files already formatted

git diff --check
  no output, exit 0
```

### Final polish fix wave

The final polish implementation is commit `02556db14ea7991a5ac4e5c0ec426f4d6ab4c98a` (`test: seal screenshot DOM worker lifecycle`). It fixes two shared isolation/lifecycle defects without adding a screenshot/current protocol identity:

- `screenshot_dom.cjs` now exports both its existing CommonJS `createDOM` and one closure-free `DOM_FACTORY_SOURCE`. `screenshot_pages.cjs` and `current_screenshot_pages.cjs` retain only startup JSON text in the host, parse that text inside each request VM, evaluate the DOM factory there, and expose VM-owned document, `Element`, methods, arrays, style objects, and prototype/function chains before production or generated source runs. Host `assert`, host error instances, and host page objects do not enter the DOM construction path.
- The existing generated/current worker identities now use `document.constructor.constructor('return globalThis')`, mutate document/`Element`/method/object prototype chains, and prove the following request is pristine and still in the request VM.
- `NodeScenarioWorker` records its last successful scenario/request. A retained process that exits after an `ok` reply is now reported as `NodeScenarioCrash` on the next request instead of being silently restarted. `close()` uses a bounded 100ms close-only grace to catch an immediate late exit and reports status, last successful scenario/request, and stderr. Request-detected timeout/crash/protocol failures still discard state and permit the following request to restart.
- The accepted minor request-console attachment enhancement was deliberately not implemented.

TDD RED was observed before implementation:

```text
generated screenshot DOM escape
  failed: DOM callable escaped the request VM: document

current-owner DOM escape
  failed: DOM callable escaped the request VM: document

late exit after ok, next request
  failed: DID NOT RAISE NodeScenarioCrash

late exit after ok, close
  failed: DID NOT RAISE NodeScenarioCrash
```

Fresh GREEN evidence after the compatibility correction:

```text
all worker protocol/isolation identities
  15 passed, 582 deselected in 15.24s
  JUnit: /tmp/wingman-final-polish-protocol.xml
  SHA-256: aac2c57908550aea6dbdd38070c13a1d7834a053bd883bd38f57356a0ca622aa

NodeScenarioWorker lifecycle/protocol suite
  11 passed in 5.01s
  JUnit: /tmp/wingman-final-polish-node-worker.xml
  SHA-256: fc374625fedfba7a8957c263536736e0f4c3a58f7668af3f6ad99560a79d4146

four target files
  597 passed in 87.01s
  597 cases, zero failures/errors/skips, testcase sum 78.917s
  JUnit: /tmp/wingman-final-polish-focused.xml
  SHA-256: 280753467712ab90a1c5e18d8583664be14b09468fb9cf72362f579c2e831132

full suite
  16,685 passed, 14 skipped in 628.81s (10m28s)
  16,699 cases, zero failures/errors, testcase sum 580.109s
  JUnit: /tmp/wingman-final-polish-full.xml
  SHA-256: a5389c7c3104948db7d2c2059b12c5e980018202a373f7997de85ebc54a98eb4
```

The fourteen full-suite skips are the same platform-only Windows integration cases listed above; there are zero Node-availability or codec-availability skips. Node v26.5.0 and `codec.codec_available() == True` were verified before the run.

Final target collection is still exactly **597 unique IDs**, with unchanged per-file counts `246 / 90 / 160 / 101` and the same reproducible filtered-node SHA-256 `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7`. No screenshot/current protocol ID was added.

Fresh independent gates also passed: 35 direct Node DOM tests, JS smoke, Cargo test, Ruff check, Ruff format check, Node syntax checks for all four worker/DOM fixtures, and `git diff --check`.

### Final polish scoped fix round 2

Round 2 closes the remaining race in the late-exit diagnostic. A process may still be alive when `_ensure_started()` polls it, then close stdin or stdout immediately afterward. The resulting broken write or queued EOF previously discarded the process and emitted a generic crash before collecting its real status and prior successful request context.

The write-failure and EOF branches now perform a bounded broken-process reap/poll before discard. The bound is 250ms and is reached only after the request path has already observed a broken write or EOF; healthy requests receive no sleep, grace, or additional poll. When the process exits within that bound and the state has a prior successful reply, `NodeScenarioCrash` uses the real status plus the last successful scenario/request ID and retained stderr. The current request still fails, state is discarded, and a later request may restart. Generic write/EOF diagnostics remain the fallback when no late-exit context is available.

The tests deterministically control both race branches:

- the real synthetic Node worker stays alive after the successful reply and exits only after reading the immediate next request, forcing the queued-EOF branch without a pre-wait;
- a scripted process double accepts one successful request, breaks the next stdin write, and returns status 28 only when the broken-process reap runs. It records the exact bounded wait and supplies deterministic stderr without timers.

Neither next-request test waits for process exit. The existing close/last-request case now also asserts the prior scenario and request ID.

TDD RED on the prior implementation:

```text
queued EOF
  expected status 27 and prior request context
  got: worker crash before reply

broken write
  expected status 28 and prior request context
  got: worker crash while sending request: [Errno 32] Broken pipe
```

Fresh round-2 GREEN evidence:

```text
NodeScenarioWorker lifecycle/protocol suite
  12 passed in 3.74s
  12 cases, zero failures/errors/skips
  JUnit: /tmp/wingman-final-polish-round2-worker.xml
  SHA-256: 61c22727a5aec152d195e76cdedd7b6e99cb612198eb09f16e3a444ef18761d2

immediate race stability probe
  both immediate cases passed in five consecutive invocations

screenshot protocol/isolation identities
  15 passed, 582 deselected in 11.41s
  JUnit: /tmp/wingman-final-polish-round2-protocol.xml
  SHA-256: 4debe78b52b2509e0c8ea3aade6f3628eb10706159137cbb788da46da980bf58

four target files
  597 passed in 74.61s
  597 cases, zero failures/errors/skips
  JUnit: /tmp/wingman-final-polish-round2-target.xml
  SHA-256: b127dd32b9faa81f8e883fef728be639d226ec79378839e77085b5a2b50f17a9

other shared-worker consumers
  tests/test_ui_setup_page.py + tests/test_formations_page.py
  448 passed in 45.69s
  448 cases, zero failures/errors/skips
  JUnit: /tmp/wingman-final-polish-round2-other-consumers.xml
  SHA-256: 3fa2ff58eef9162d2bb4db9f9f70b481f9dd4ee85a3628375b4c37bd5f58cadd
```

Final collection remains exactly **597 unique target IDs**, with counts `246 / 90 / 160 / 101` and filtered-node SHA-256 `4ff87df92ef58977cd8e5b99b85ca52dddd330f4fc86b037d5f6d209e99de6e7`.

A full suite was deliberately not rerun for round 2. Executable changes are limited to `tests/node_scenario_worker.py` and its direct protocol test. Repository search identified the four screenshot/Fittings targets plus UI Setup and Formations as shared-worker consumers; all six consumer files were run in full, alongside the dedicated protocol suite. The results/report edits only record evidence and do not expand executable scope. The clean round-1 full-suite result remains historical evidence, not a claimed round-2 run.

Round-2 syntax and static gates passed for the changed Python files and all four worker/DOM CJS fixtures, together with repository-wide Ruff check/format and `git diff --check`.

### Changed-path and cleanup proof

The final prohibited-scope command returned no output:

```bash
git diff --name-only \
  c4a2b206..02556db14ea7991a5ac4e5c0ec426f4d6ab4c98a -- \
  wingman .github scripts packaging pyproject.toml uv.lock
```

The final implementation scope is pinned to `02556db14ea7991a5ac4e5c0ec426f4d6ab4c98a`. The documentation commit that records this endpoint changes only the already-allowed plan/results paths and is intentionally outside the pinned implementation range, avoiding a self-referential commit SHA. The complete changed-path set from `c4a2b206` through the pinned endpoint is exactly the final 15-path allowlist:

```text
docs/ci-persistent-screenshot-harness-results.md
docs/superpowers/plans/2026-09-22-persistent-screenshot-harness.md
tests/conftest.py
tests/fittings_scenario_worker.py
tests/fixtures/current_screenshot_pages.cjs
tests/fixtures/fittings_page.cjs
tests/fixtures/persistent_screenshot_harness_base_nodes.txt
tests/fixtures/screenshot_dom.cjs
tests/fixtures/screenshot_pages.cjs
tests/node_scenario_worker.py
tests/test_current_screenshots.py
tests/test_fittings_page.py
tests/test_new_screenshots.py
tests/test_node_scenario_worker.py
tests/test_shoot_screens.py
```

The exact dead-symbol search was scoped to executable test sources:

```bash
rg -n "_COPY_ACCESSIBILITY_HARNESS|_run_fittings_node|fittings-harness\.cjs" tests/
# no matches, exit 1
```

Plans and results may retain those names as historical evidence; no matching
symbol remains under `tests/`. The only Python launches of
`screenshot_pages.cjs` are the two `NodeScenarioWorker` startup argument lists;
the only launch of `current_screenshot_pages.cjs` is its worker startup. The one
preserved `screenshot_alerts.cjs` `subprocess.run` call site still produces the
31 explicitly out-of-scope Alerts one-shot launches. No temporary compatibility
entry point, debug statement, dead one-shot symbol, product file, workflow,
configuration, packaging source, dependency lock, marker policy, persisted-data
contract, screenshot key, generated expression, or pywebview behavior changed.

### Hosted comparison and Plan B

PR #277 Windows reference sums remain, without Linux projection:

```text
test_shoot_screens.py     38.610s
test_new_screenshots.py   26.005s
test_current_screenshots.py 25.852s
test_fittings_page.py     23.838s
total                    114.305s
```

Comparable hosted evidence for this branch has not been collected because
publication and workflow dispatch are external side effects that are not yet
authorized. After explicit authorization, the next step is to push, run hosted
CI, download Windows and Ubuntu JUnit/timing artifacts, and compare common
business nodes separately from the fifteen new protocol nodes, including the
four target-file sums, pytest step, complete job, required critical path, and
total testcase sum.

Until that comparison is conclusive, hosted status is **PENDING**, no hosted GO
is claimed, and Plan B remains unauthorized. An anomalous or incomparable run
would remain inconclusive rather than authorizing matrix consolidation.
