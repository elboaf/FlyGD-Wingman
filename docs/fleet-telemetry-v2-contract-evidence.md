# Fleet telemetry v2 — contract evidence

**Status: contract reviewed; implementation/lane/platform/deployment gates remain.**

## Canonical publication and source history

This documentation-only publication uses Wingman coordination source HEAD
`419660bc` (`docs: track accepted fleet contract corrections`). Independent
[contract re-review](fleet-telemetry-v2-contract-review.md) returned **READY** with
all six accepted findings **ADDRESSED** and no new Important/Critical finding.
Its sole minor response-reader wording correction is already present in the
publication inputs (coordinator correction reference `0085572a`). The review is
copied verbatim: its original scratch filenames, line references and minor finding
are historical evidence, not references to renamed files or an outstanding change.

Canonical documents and their original input names:

| Canonical document | Original scratch artifact |
| --- | --- |
| [Common API](fleet-telemetry-v2-api-contract.md) | `common-api-contract.md` |
| [Combat contract](fleet-telemetry-v2-contract.md) | `combat-contract-draft.md` |
| [Automatic/control contract](fleet-telemetry-v2-automatic-contract.md) | `automatic-control-contract.md` |
| [Cutover contract](fleet-telemetry-v2-cutover-contract.md) | `cutover-migration-contract.md` |
| [Automatic plan](fleet-telemetry-automatic-plan.md) | `automatic-plan-draft.md` |
| [Combat model plan](fleet-telemetry-combat-model-plan.md) | `model-plan-draft.md` |
| [Frozen profile](fleet-combat-v2-profile.json) | `fleet-combat-v2-profile.json` |
| [Verbatim independent review](fleet-telemetry-v2-contract-review.md) | `contract-re-review.md` |

The canonical documents/profile above live in W `docs/`. Original artifacts,
proof scripts and historical pass reports remain local under W
`.superpowers/sdd/fleet-telemetry-coordination/`; they are not installed application
resources or portable repository/CI tests. References to adjacent/sibling scratch
proofs, vectors, proposals and reports in the copied bodies refer to that original
scratch directory, not files shipped alongside these documents. Root-qualified W/A
source and future implementation paths retain their original meaning. The six
bodies change only publication filename references and review-status wording;
completed model core Tasks 1 and 4 remain complete and outside redispatch scope.
Published status headers supersede historical draft/review-pending wording retained
in the copied bodies; implementation and acceptance gates remain unchanged.

## Six closures and recorded offline evidence

The final local `contract-reconciliation-report.md` supersedes earlier pass counts
and provisional conclusions; `contract-re-review.md` supplies independent approval.
The publication owner initially reused that evidence. The coordinator subsequently
reran all four proofs after publication: the same results below passed again.
These models are not converted into application tests.

| Finding | Reviewed closure | Actual recorded offline result |
| --- | --- | --- |
| 1 — clock/order continuity | Immutable isotonic origins; origin-scoped receiver intervals, not a permanent global minimum | **1,944** ordering/safety vectors; 120-second recovery and 200 mixed-delay steps; 71-record bound |
| 2 — measurement freshness | Original measurement pins and final pre-send age gate | Cached replay/replacement and 4,999/5,000ms admission plus 2,999/3,000/9,999/10,000ms transport boundaries passed |
| 3 — byte/Unicode budgets | 512-KiB PUT; 64-MiB canonical decoded GET; frozen table-only Unicode consumers | Actual W `_json` PUT **419,900 bytes**; full Python/Node GET **47,022,137 bytes**, row widths 4,833/5,739 bytes |
| 4 — durable quota-safe Off | Reserved terminal receipt capacity; durable same-CAS Off; exact-receipt cancellation and nondestructive browser Off | Eight automatic groups passed; **7,778** transition/race sequences, saturation, purge and seven-day queued Off |
| 5 — closed control/discovery handoff | Exact DTOs/bindings and source-free claim/bind/commit; actual provenance, no invented initiating-session field | Correlation, source mapping and discovery-fence probes passed; no compiled adapter/transaction claim |
| 6 — cutover and state4 | Close/drain/fence/schema/verify/separately authorize reopen; one bounded archive/journal | **780** migration checks, including actual legacy in-memory parsers and 11 route resources × 7 modeled methods; state4 cancellation, selected validators, terminal reserve and Unicode-consumption checks passed |

Frozen profile: **94,220 bytes**, SHA-256
`036582f29ec5b427cd50397a5504fa4c9a3145e35d15118a64c4eb2f26700868`.
The published profile is byte-identical to the original, not regenerated.
Maximum GET SHA-256:
`684eab27b0487bcd59a11a6c3ea55e952b97c91fc79c35907745ce8b2fb40fa4`.

Generation/exhaustive audit used system Python **3.14.3 / Unicode 16.0.0**.
Actual application-interpreter consumption was checked under W Python
**3.11.15 / Unicode 14.0.0**, using frozen tables rather than host Unicode fallback.
The generation runtime is not an application prerequisite. Node serialization
agreement is not implementation of a TypeScript Unicode validator.

## Recorded commands — local evidence only

These exact commands were executed in the earlier final reconciliation, as recorded
in its local report. They require that original scratch workspace and its tools;
they are **not portable checkout commands or application/CI test targets**. No
Python proof files or historical pass reports are copied into `docs/`.

```sh
python3 -B /mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.superpowers/sdd/fleet-telemetry-coordination/combat-resolution-proof.py
/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.venv/bin/python -B /mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.superpowers/sdd/fleet-telemetry-coordination/automatic-control-proof.py
/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.venv/bin/python -B /mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.superpowers/sdd/fleet-telemetry-coordination/cutover-migration-proof.py
/mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.venv/bin/python -B /mnt/c/dev/flygd-wingman/.worktrees/fleet-telemetry-coordination/.superpowers/sdd/fleet-telemetry-coordination/contract-state4-proof.py
```

All four proof processes passed. Scoped scratch Ruff checks also passed (two files
already formatted), as did the recorded tracked `git diff --check`. Independent
re-review reran the bounded state4 proof, including real Unicode-14 consumption,
and independently checked serialization widths; it did not rerun the large suites.
The coordinator's later publication checks also confirmed six unchanged code-fence
sets, byte-identical profile/review, 28 valid document links and unchanged production
source. Ruff lint and format passed (462 files). Strict diff checks pass outside
the verbatim review, whose 20 original two-space Markdown hard breaks are retained
intentionally rather than rewriting the review.

## Limits and remaining gates

Finite models, lexical pins and serialization arithmetic do not establish actual
DB drain/atomicity, security enforcement, compiled interfaces, pg-boss fairness,
shutdown ownership or complete state4 persistence. Real transaction/race and
atomic-write tests, browser Origin/session enforcement and convergence,
cross-language helpers and packaged resources, 64-MiB allocation/latency,
100ms/95s DB/elapsed-clock assumptions and Windows suspend fencing remain gates.
Generated migrations, isolated held-reader/writer cutover/interruption tests,
current-client/two-account integration, application suites, rendered browser and
Windows/WebView2 acceptance are still required. Deployment/activation/live two-PC
checks require separate authorization. No new implementation, test suite, DB/live
call or rollout is claimed by this publication.
