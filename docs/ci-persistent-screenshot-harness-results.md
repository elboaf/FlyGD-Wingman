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
| Hosted comparator checkout | `2ed88f372edba7f94cd815d484595960236b984b` |
| Windows comparator job | [`106607316881`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316881), successful |
| Ubuntu job recorded with the run | [`106607316829`](https://github.com/elboaf/FlyGD-Wingman/actions/runs/35684157184/job/106607316829), successful |

The artifact executed PR head `2ed88f372edba7f94cd815d484595960236b984b`; it did **not** execute the later squash merge `c4a2b2060de8f8317e61a732708a9b5bd88beb98`. The four target test files are unchanged from `c4a2b206` to the Task 0 start, and the artifact checkout and `c4a2b206` share all 572 normalized target node IDs. The comparator is accepted because that node set is byte-for-byte identical, not because the two SHAs are treated as interchangeable.

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

Task 6 must compare the completed tranche against this exact allowlist:

```text
docs/ci-persistent-screenshot-harness-results.md
docs/superpowers/plans/2026-09-22-persistent-screenshot-harness.md
tests/conftest.py
tests/fittings_scenario_worker.py
tests/fixtures/current_screenshot_pages.cjs
tests/fixtures/fittings_page.cjs
tests/fixtures/persistent_screenshot_harness_base_nodes.txt
tests/fixtures/screenshot_pages.cjs
tests/test_current_screenshots.py
tests/test_fittings_page.py
tests/test_new_screenshots.py
tests/test_shoot_screens.py
```

No production, workflow, packaging, configuration, marker-policy, persisted-data, screenshot-key, generated-expression, or pywebview path is authorized by this plan.
