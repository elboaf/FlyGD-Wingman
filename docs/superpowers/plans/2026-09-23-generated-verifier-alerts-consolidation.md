# Generated-Verifier and Alerts Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the generated gap-verifier product from 35 identities to a mutation-qualified set of at least 22 and the Alerts top-anchor product from 31 identities to a mutation-qualified set of at least 24, with exact identity, skip, scope, and hosted evidence.

**Architecture:** Freeze the merged PR #286 baseline first, then qualify the generated and Alerts candidates independently with temporary production/helper mutants and supplemental fixture inputs that never survive a probe. Only after both mutation gates pass may `tests/test_shoot_screens.py` derive the retained parameter sequences; all other executable files remain byte-identical.

**Tech Stack:** Python 3.12, pytest, Node.js/CommonJS VM harnesses, generated ES5 screenshot verifier scripts, Cargo settings codec, uv, Git, GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-23-generated-verifier-alerts-consolidation-design.md`

## Global Constraints

- Source baseline is merged PR #286 at `8d5b9305` (`Consolidate current-owner lifecycle tests (#286)`).
- Design authority is `docs/ci-test-budget-redesign.md`; Stage 3 authorization and comparator evidence are in `docs/ci-current-owner-lifecycle-consolidation-results.md`.
- Committed executable changes are limited to parameter derivation in `tests/test_shoot_screens.py`.
- The only other committed paths are this plan, the approved Stage 3 spec, and `docs/ci-generated-verifier-alerts-consolidation-results.md`.
- `scripts/shoot_screens.py`, `tests/fixtures/screenshot_pages.cjs`, and `tests/fixtures/screenshot_alerts.cjs` may be mutated only as temporary, uncommitted probes and must be restored after every probe.
- Fixture-only mutants prove dispatch wiring only. They never qualify a production/helper branch and never justify an identity removal.
- Every mutant must fail at the intended assertion. A TypeError, timeout, worker crash, cleanup failure, protocol failure, or unrelated later assertion is not evidence.
- Retain all five generated settled cases, all five same-owner missing cases, all five same-owner wrong-text cases, one same-owner geometry witness per owner, all 15 Alerts base states, both Alerts missing short circuits, all three Alerts visibility mechanisms, both Alerts anchors, and all four Alerts edge comparisons unless the design is revised before implementation.
- The approved unexpanded candidate is `22 + 24 = 46` retained product identities, `220 / 90 / 91 / 101 = 502` four-file identities, 20 removals, and zero additions.
- The 46 and 502 counts are consequences, not deletion targets. A surviving or masked mutant expands the retained set; it never permits a compensating deletion.
- Node and the built release settings codec are required. A Node, codec, native-contract, or unexplained platform skip invalidates the relevant verification.
- No production behavior, screenshot scenario semantics, workflow, dependency, lockfile, packaging, marker, budget, shard, cadence, or overall-runtime claim is in scope.
- Stage 4 lower Fittings consolidation remains stopped.
- If an exact source anchor below differs, refuse the replacement, record the mismatch, and return to design review. Do not use a broader textual replacement.

## File Structure and Ownership

- Create `docs/ci-generated-verifier-alerts-consolidation-results.md` as the single evidence ledger: baseline inventories, comparator provenance, mutation rows, mappings, verification, hosted observations, deviations, and the bounded next decision.
- Modify `tests/test_shoot_screens.py` only in Task 4: named derived constants and the two target parametrization decorators.
- Temporarily modify and restore `scripts/shoot_screens.py` in Tasks 2–3: exact owner predicates, owner-to-helper wiring, shared visibility/geometry/hit-test branches, and Alerts guards.
- Temporarily modify and restore `tests/fixtures/screenshot_pages.cjs` in Task 2 only to isolate masked hidden, zero-height, point-specific, null-hit, and descendant-hit inputs alongside production/helper mutants.
- Temporarily modify and restore `tests/fixtures/screenshot_alerts.cjs` in Task 3 only when a narrow input is needed to isolate `parent.hidden`; this fixture is supplemental evidence only.
- Do not create a mutation runner, witness test module, helper script in the repository, or committed fixture scenario.

## Task Right-Sizing

1. Task 1 is a documentation-only baseline freeze that can be accepted without accepting any candidate deletion.
2. Task 2 qualifies the generated product and shared helper independently; a reviewer can reject its branch attribution without blocking review of the baseline.
3. Task 3 qualifies Alerts independently and consumes only the already-recorded shared-helper evidence.
4. Task 4 is the sole executable change and is forbidden until Tasks 2–3 are approved.
5. Task 5 proves the complete local endpoint without publication.
6. Task 6 performs final polish/review and, only after explicit authorization, publication and hosted comparison.

## Plan-Author Preflight — Completed Without Source Deletion

The plan author collected the exact current worktree and built the candidate in an untracked `/tmp` archive. No repository source or test identity was deleted or edited.

Baseline formula:

```python
all_nodes = collect(
    "tests/test_shoot_screens.py",
    "tests/test_new_screenshots.py",
    "tests/test_current_screenshots.py",
    "tests/test_fittings_page.py",
)
normalized_hash = sha256(("\n".join(all_nodes) + "\n").encode()).hexdigest()
```

Candidate generated formula:

```python
_GAP_CAPTURE_CASES = tuple(
    (scenario, key)
    for scenario in ("settled", "missing", "wrong-text")
    for key in GAP_CAPTURES
) + (
    ("hidden", "profiles-copy-scope"),
    ("clipped", "profiles-copy-scope"),
    ("clipped", "fittings-metadata-narrow"),
    ("clipped", "fittings-copy-preflight-bottom-narrow"),
    ("clipped", "fittings-copy-result-bottom-narrow"),
    ("covered", "fittings-copy-result-bottom-narrow"),
    ("zero-area", "settings-wanderer-controls-narrow"),
)
```

Candidate Alerts formula:

```python
_ALERTS_CAPTURE_SCENARIOS = (
    _ALERTS_BASE_SCENARIOS
    + _ALERTS_ANCHOR_SCENARIOS
    + _ALERTS_CLIPPED_SCENARIOS
)
```

Preflight results:

- Baseline counts: `240 / 90 / 91 / 101 = 522`, all unique.
- Baseline four-file hash: `07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6`.
- Baseline target products: 35 generated + 31 Alerts = 66 unique identities.
- Candidate generated count: 22.
- Candidate Alerts count: 24.
- Candidate retained-product hash: `359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9`.
- Candidate four-file counts: `220 / 90 / 91 / 101 = 502`.
- Candidate four-file hash from actual temporary collection: `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`.
- Exact projected diff: 20 removals, zero additions.
- The generated derived order intentionally moves the retained `wrong-text` block before the retained shared `hidden` witness; therefore the candidate four-file hash must come from actual candidate collection, not a naive set-filter of the 522-ID baseline.

---

## Reproducibility Blocks

Every block writes only under `/tmp` unless a mutation is explicitly applied through Block B. Execute hosted blocks in the documented order **F then E** so a clean `/tmp` contains the parser before the collector invokes it. The plan author syntax-checked every Python/Bash block, ran Block A against an actually edited disposable archive, dry-ran Block D against those actual 502 IDs, parsed the PR #286 artifacts with Block F, checked comparator parents/path deltas, and ran all Block C control/mutant sequences in disposable archives.

### Reproducibility Block A — actual disposable candidate collection and report archive

This block always collects the frozen baseline from `8d5b9305`. It separately builds a projected list, then archives `HEAD` into a disposable checkout. If `tests/test_shoot_screens.py` is still pre-implementation, it applies the exact Task 4 constants/decorators with match-once guards; if Task 4 is already present, it requires the exact post-edit anchors. Any third source state is refused. Pytest runs from the disposable checkout with the current venv and `PYTHONPATH` set to that checkout. Actual collection must equal the separate projection byte-for-normalized-byte.

```bash
cat > /tmp/stage3_inventory_audit.py <<'PY'
from __future__ import annotations
import hashlib,io,json,os,shutil,subprocess,tarfile,tempfile
from pathlib import Path
W=Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation'); P=W/'.venv/bin/python'; O=Path('/tmp/wingman-stage3-inventory'); A=Path('/tmp/wingman-stage3-inventory.tar.gz')
FILES=('tests/test_shoot_screens.py','tests/test_new_screenshots.py','tests/test_current_screenshots.py','tests/test_fittings_page.py'); PRODUCTS=(FILES[0]+'::test_gap_capture_requires_semantic_content_after_framing',FILES[0]+'::test_alerts_base_capture_requires_top_anchors_without_actions'); G=PRODUCTS[0]+'['; L=PRODUCTS[1]+'['
GAP='''GAP_CAPTURES = {
    "settings-wanderer-controls-narrow": ("settings", "previews", True),
    "profiles-copy-scope": ("evesettings", None, False),
    "fittings-metadata-narrow": ("fittings", None, True),
    "fittings-copy-preflight-bottom-narrow": ("fittings", None, True),
    "fittings-copy-result-bottom-narrow": ("fittings", None, True),
}
'''
GAP_CASES='''

_GAP_CAPTURE_CASES = tuple(
    (scenario, key)
    for scenario in ("settled", "missing", "wrong-text")
    for key in GAP_CAPTURES
) + (
    ("hidden", "profiles-copy-scope"),
    ("clipped", "profiles-copy-scope"),
    ("clipped", "fittings-metadata-narrow"),
    ("clipped", "fittings-copy-preflight-bottom-narrow"),
    ("clipped", "fittings-copy-result-bottom-narrow"),
    ("covered", "fittings-copy-result-bottom-narrow"),
    ("zero-area", "settings-wanderer-controls-narrow"),
)
'''
GAP_OLD='''@pytest.mark.parametrize("key", GAP_CAPTURES)
@pytest.mark.parametrize(
    "scenario",
    ["settled", "missing", "hidden", "wrong-text", "clipped", "covered", "zero-area"],
)
'''; GAP_NEW='''@pytest.mark.parametrize(("scenario", "key"), _GAP_CAPTURE_CASES)
'''
ALERT_OLD='''@pytest.mark.parametrize(
    "scenario",
    [
        "settled-disabled",
        "settled-enabled",
        "wrong-route",
        "wrong-section",
        "inactive-route",
        "inactive-section",
        "missing-section",
        "missing-pane",
        "hidden-section",
        "hidden-pane",
        "hidden-card",
        "wrong-owner",
        "empty-health",
        "zero-health",
        "outside-viewport",
        *[
            f"{kind}-{anchor}"
            for kind in ("missing", "hidden", "invisible", "display-none")
            for anchor in ("master", "health")
        ],
        *[
            f"clipped-{anchor}-{edge}"
            for anchor in ("master", "health")
            for edge in ("top", "bottom", "left", "right")
        ],
    ],
)
'''
ALERT_NEW='''_ALERTS_BASE_SCENARIOS = (
    "settled-disabled",
    "settled-enabled",
    "wrong-route",
    "wrong-section",
    "inactive-route",
    "inactive-section",
    "missing-section",
    "missing-pane",
    "hidden-section",
    "hidden-pane",
    "hidden-card",
    "wrong-owner",
    "empty-health",
    "zero-health",
    "outside-viewport",
)
_ALERTS_ANCHOR_SCENARIOS = (
    "missing-master",
    "missing-health",
    "hidden-master",
    "invisible-health",
    "display-none-master",
)
_ALERTS_CLIPPED_SCENARIOS = (
    "clipped-master-top",
    "clipped-master-right",
    "clipped-health-bottom",
    "clipped-health-left",
)
_ALERTS_CAPTURE_SCENARIOS = (
    _ALERTS_BASE_SCENARIOS
    + _ALERTS_ANCHOR_SCENARIOS
    + _ALERTS_CLIPPED_SCENARIOS
)


@pytest.mark.parametrize("scenario", _ALERTS_CAPTURE_SCENARIOS)
'''
def h(v): return hashlib.sha256(('\n'.join(v)+'\n').encode()).hexdigest()
def extract(commit,root):
 raw=subprocess.check_output(['git','-C',str(W),'archive',commit])
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as t: t.extractall(root,filter='data')
def collect(root,args,name):
 env=dict(os.environ,PYTHONPATH=str(root)); r=subprocess.run([str(P),'-m','pytest',*args,'--collect-only','-q','-p','no:cacheprovider'],cwd=root,env=env,text=True,capture_output=True,check=True,timeout=180); (O/name).write_text(r.stdout); v=[x for x in r.stdout.splitlines() if x.startswith('tests/')]; assert len(v)==len(set(v)); return v
def once(text,before,after): assert text.count(before)==1,('before_count',text.count(before)); assert text.count(after)==0,('after_pre_count',text.count(after)); out=text.replace(before,after,1); assert out.count(after)==1,('after_count',out.count(after)); return out
if O.exists(): shutil.rmtree(O)
O.mkdir()
with tempfile.TemporaryDirectory(prefix='wingman-stage3-base-') as d:
 B=Path(d); extract('8d5b9305',B); baseline=collect(B,FILES,'baseline-collection.txt'); products=collect(B,PRODUCTS,'baseline-products-collection.txt')
keys=('settings-wanderer-controls-narrow','profiles-copy-scope','fittings-metadata-narrow','fittings-copy-preflight-bottom-narrow','fittings-copy-result-bottom-narrow'); gen=[f'{G}{s}-{k}]' for s in ('settled','missing','wrong-text') for k in keys]+[f'{G}{x}]' for x in ('hidden-profiles-copy-scope','clipped-profiles-copy-scope','clipped-fittings-metadata-narrow','clipped-fittings-copy-preflight-bottom-narrow','clipped-fittings-copy-result-bottom-narrow','covered-fittings-copy-result-bottom-narrow','zero-area-settings-wanderer-controls-narrow')]; alerts=[f'{L}{x}]' for x in ('settled-disabled','settled-enabled','wrong-route','wrong-section','inactive-route','inactive-section','missing-section','missing-pane','hidden-section','hidden-pane','hidden-card','wrong-owner','empty-health','zero-health','outside-viewport','missing-master','missing-health','hidden-master','invisible-health','display-none-master','clipped-master-top','clipped-master-right','clipped-health-bottom','clipped-health-left')]
projection=[]; eg=el=False
for n in baseline:
 if n.startswith(G):
  if not eg: projection+=gen; eg=True
 elif n.startswith(L):
  if not el: projection+=alerts; el=True
 else: projection.append(n)
with tempfile.TemporaryDirectory(prefix='wingman-stage3-candidate-') as d:
 C=Path(d); extract('HEAD',C); path=C/FILES[0]; text=path.read_text(); old=(text.count(GAP_CASES)==0 and text.count(GAP_OLD)==1 and text.count(ALERT_OLD)==1); new=(text.count(GAP_CASES)==1 and text.count(GAP_NEW)==1 and text.count(ALERT_NEW)==1); assert old ^ new,('source_state_refused',old,new)
 if old:
  text=once(text,GAP,GAP+GAP_CASES); text=once(text,GAP_OLD,GAP_NEW); text=once(text,ALERT_OLD,ALERT_NEW); path.write_text(text)
 actual=collect(C,FILES,'candidate-collection.txt'); retained=collect(C,PRODUCTS,'candidate-products-collection.txt')
assert actual==projection,('actual_candidate_differs_from_projection',[(i,a,b) for i,(a,b) in enumerate(zip(actual,projection)) if a!=b][:3]); counts=lambda v:[sum(n.startswith(f+'::') for n in v) for f in FILES]; removed=[n for n in baseline if n not in set(actual)]; added=[n for n in actual if n not in set(baseline)]
assert counts(baseline)==[240,90,91,101] and len(baseline)==522 and len(products)==66 and h(baseline)=='07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6'; assert counts(actual)==[220,90,91,101] and len(actual)==502 and len(retained)==46 and len(removed)==20 and added==[] and h(actual)=='592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a' and h(retained)=='359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9'
for name,v in {'baseline-522.txt':baseline,'baseline-products-66.txt':products,'projection-502.txt':projection,'candidate-actual-502.txt':actual,'candidate-products-46.txt':retained,'removed-20.txt':removed,'added-0.txt':added}.items(): (O/name).write_text('\n'.join(v)+('\n' if v else ''))
summary={'baseline_counts':counts(baseline),'baseline_total':len(baseline),'baseline_product_total':len(products),'baseline_hash':h(baseline),'actual_candidate_counts':counts(actual),'actual_candidate_total':len(actual),'actual_candidate_hash':h(actual),'actual_equals_projection':actual==projection,'candidate_product_total':len(retained),'candidate_product_hash':h(retained),'removed':len(removed),'added':len(added)}; (O/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
if A.exists(): A.unlink()
with tarfile.open(A,'w:gz') as t:
 for p in sorted(O.iterdir()): t.add(p,arcname=p.name)
print(json.dumps(summary,sort_keys=True)); print('temporary_checkouts_cleaned=true'); print(f'report_archive={A}')
PY
python -m py_compile /tmp/stage3_inventory_audit.py
python /tmp/stage3_inventory_audit.py
```

### Reproducibility Block B — guarded mutation apply/restore

Every worktree mutation in Tasks 2–3 uses this driver. Put the exact multiline before and after blocks named by the step in `/tmp/stage3-before.txt` and `/tmp/stage3-after.txt`; use a mutation-specific backup path. `check`, `apply`, and `restore` each enforce count one. A command that reports any other count stops the probe.

```bash
cat > /tmp/stage3_guarded_replace.py <<'PY'
from pathlib import Path
import argparse, hashlib, json
p=argparse.ArgumentParser(); p.add_argument('mode',choices=('check','apply','restore')); p.add_argument('target',type=Path); p.add_argument('before',type=Path); p.add_argument('after',type=Path); p.add_argument('backup',type=Path); a=p.parse_args()
b=a.before.read_text(); n=a.after.read_text(); assert b and n and b!=n
if a.mode in ('check','apply'):
 t=a.target.read_text(); assert t.count(b)==1,('before_count',t.count(b)); u=t.replace(b,n,1); assert u.count(n)==1,('after_count',u.count(n))
 if a.mode=='check': print(json.dumps({'before_count':1,'after_count':1,'target':str(a.target)}))
 else:
  assert not a.backup.exists(); a.backup.write_bytes(a.target.read_bytes()); a.target.write_text(u); assert a.target.read_text().count(n)==1; print(json.dumps({'before_count':1,'after_count':1,'original_sha256':hashlib.sha256(a.backup.read_bytes()).hexdigest()}))
else:
 assert a.backup.is_file(); t=a.target.read_text(); assert t.count(n)==1,('after_count',t.count(n)); raw=a.backup.read_bytes(); original=raw.decode(); assert original.count(b)==1,('backup_before_count',original.count(b)); a.target.write_bytes(raw); assert a.target.read_text().count(b)==1; a.backup.unlink(); print(json.dumps({'restored_before_count':1,'restored_sha256':hashlib.sha256(a.target.read_bytes()).hexdigest()}))
PY
python -m py_compile /tmp/stage3_guarded_replace.py
```

For each exact mutation row, run `check`, then `apply`, then that row's fully spelled witness command, then `restore`, and finally the row's exact `git diff --exit-code` path audit. The target path and mutation-specific backup path are concrete in each row; never reuse a live backup across probes.

```bash
python /tmp/stage3_guarded_replace.py check scripts/shoot_screens.py /tmp/stage3-before.txt /tmp/stage3-after.txt /tmp/stage3-mutation.backup
python /tmp/stage3_guarded_replace.py apply scripts/shoot_screens.py /tmp/stage3-before.txt /tmp/stage3-after.txt /tmp/stage3-mutation.backup
```

After the named witness command:

```bash
python /tmp/stage3_guarded_replace.py restore scripts/shoot_screens.py /tmp/stage3-before.txt /tmp/stage3-after.txt /tmp/stage3-mutation.backup
git diff --exit-code -- scripts/shoot_screens.py
```

### Reproducibility Block C — unique framed-helper and target-coordinate probes

This complete script uses disposable `git archive` copies. Its `H` anchor contains the tolerance comments, tolerance value, dimensions, all edges, all five points, and full hit body, so it occurs once only in `_framed_content_script`. `rep()` asserts `before_count == 1` and `after_count == 1` for every source and fixture mutation.

```bash
cat > /tmp/stage3-helper-probe.py <<'PY'
from pathlib import Path
import io,subprocess,tarfile,tempfile
W=Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation'); P=W/'.venv/bin/python'
G='tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing['; X='tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests['
COVER=G+'covered-fittings-copy-result-bottom-narrow]'; SETTLED=G+'settled-fittings-copy-result-bottom-narrow]'; ZERO=G+'zero-area-settings-wanderer-controls-narrow]'
H='''  // Scroll offsets can round while DOMRects retain fractions (measured 0.109375px).
  // Allow at most one CSS pixel at an edge, never a covered hit-test point.
  var tolerance = 1;
  if (r.width <= 0 || r.height <= 0
      || r.left < Math.max(0, p.left) - tolerance || r.right > Math.min(innerWidth, p.right) + tolerance
      || r.top < Math.max(0, p.top) - tolerance || r.bottom > Math.min(innerHeight, p.bottom) + tolerance) return false;
  var inset = Math.min(4, r.width / 4, r.height / 4);
  return [[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {
      var hit = document.elementFromPoint(point[0], point[1]);
      return hit && (hit === node || node.contains(hit));
    });
'''
F='''    // Each hit-test point belongs to the last measured node unless another
    // surface covers it. This isolates the generated guard, not CSS hit testing.
    let measured;
    const box = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () { measured = this; return box.call(this); };
    document.elementFromPoint = () => covered && (scenario !== 'covered-summary' || measured === target)
      ? document.body : measured;
'''
Z='''      const r = rect(120, 130, zero && this === target ? 120 : 760, 330);'''; ZH='''      const r = zero && this === target
        ? rect(120, 130, 760, 130)
        : rect(120, 130, 760, 330);'''
POINTS=((124,134),(756,134),(124,326),(756,326),(440,230))
ARRAY='''  return [[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {'''
REMOVED=(
'''  return [[r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {''',
'''  return [[r.left + inset, r.top + inset],
    [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {''',
'''  return [[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
    [r.right - inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {''',
'''  return [[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset],
    [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {''',
'''  return [[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
    [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset]].every(function (point) {''')
def rep(path,b,a):
 t=path.read_text(); assert t.count(b)==1,('before_count',t.count(b)); u=t.replace(b,a,1); assert u.count(a)==1,('after_count',u.count(a)); path.write_text(u)
def fixture(kind,index=0):
 x,y=POINTS[index]; value={'body':'document.body','null':'null','descendant':'descendantHit'}[kind]; gate='covered && measured === target'; extra=''
 if kind=='descendant': extra="    const descendantHit = WM.make('span');\n    target.appendChild(descendantHit);\n"; gate='measured === target'
 return f'''    // Each hit-test point belongs to the last measured node unless another
    // surface covers it. This isolates the generated guard, not CSS hit testing.
    let measured;
    const box = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {{ measured = this; return box.call(this); }};
    const expectedTargetRect = rect(120, 130, 760, 330), expectedTargetInset = 4;
    const expectedTargetPoints = [[124,134],[756,134],[124,326],[756,326],[440,230]];
    const coveredTargetPoint = expectedTargetPoints[{index}]; assert.deepEqual(coveredTargetPoint,[{x},{y}]);
{extra}    document.elementFromPoint = (x,y) => {{ if ({gate}) assert.deepEqual(box.call(target),expectedTargetRect); return {gate} && x === coveredTargetPoint[0] && y === coveredTargetPoint[1] ? {value} : measured; }};
'''
def run(name,helper,node,fix=None,ea='AssertionError:',eb='at Object.throws'):
 with tempfile.TemporaryDirectory(prefix='stage3-'+name+'-') as d:
  R=Path(d)
  with tarfile.open(fileobj=io.BytesIO(ARCH),mode='r:') as t: t.extractall(R,filter='data')
  s=R/'scripts/shoot_screens.py'; f=R/'tests/fixtures/screenshot_pages.cjs'; assert s.read_text().count(H)==1
  if fix=='zero-height': rep(f,Z,ZH)
  elif fix: rep(f,F,fix)
  q=lambda:subprocess.run([str(P),'-m','pytest',node,'-q','-p','no:cacheprovider'],cwd=R,text=True,capture_output=True,timeout=60)
  green=q(); assert green.returncode==0,green.stdout+green.stderr; rep(s,H,helper); red=q(); out=red.stdout+red.stderr; assert red.returncode!=0 and ea in out and eb in out,out; print(name+': control PASS; mutant FAIL at '+eb+' / '+ea)
ARCH=subprocess.check_output(['git','-C',str(W),'archive','HEAD'])
for i in range(5): run('point-'+str(i),H.replace(ARRAY,REMOVED[i]),COVER,fixture('body',i),'AssertionError: covered')
mut={
'width':(H.replace('  if (r.width <= 0 || r.height <= 0\n','  if (r.height <= 0\n'),ZERO,None,'AssertionError: zero-area','at Object.throws'),
'height':(H.replace('  if (r.width <= 0 || r.height <= 0\n','  if (r.width <= 0\n'),ZERO,'zero-height','AssertionError: zero-area','at Object.throws'),
'every':(H.replace(']].every(function (point) {',']].some(function (point) {'),COVER,fixture('body'),'AssertionError: covered','at Object.throws'),
'null':(H.replace('      return hit && (hit === node || node.contains(hit));','      return !hit || hit === node || node.contains(hit);'),COVER,fixture('null'),'AssertionError: covered','at Object.throws'),
'unrelated':(H.replace('      return hit && (hit === node || node.contains(hit));','      return Boolean(hit);'),COVER,fixture('body'),'AssertionError: covered','at Object.throws'),
'direct':(H.replace('      return hit && (hit === node || node.contains(hit));','      return hit && hit !== node && node.contains(hit);'),SETTLED,None,'Screenshot content did not settle: fittings-copy-result-bottom-narrow','at check'),
'descendant':(H.replace('      return hit && (hit === node || node.contains(hit));','      return hit && hit === node;'),SETTLED,fixture('descendant'),'Screenshot content did not settle: fittings-copy-result-bottom-narrow','at check')}
for edge,old,new in (('left','      || r.left < Math.max(0, p.left) - tolerance || r.right > Math.min(innerWidth, p.right) + tolerance\n','      || r.right > Math.min(innerWidth, p.right) + tolerance\n'),('right','      || r.left < Math.max(0, p.left) - tolerance || r.right > Math.min(innerWidth, p.right) + tolerance\n','      || r.left < Math.max(0, p.left) - tolerance\n'),('top','      || r.top < Math.max(0, p.top) - tolerance || r.bottom > Math.min(innerHeight, p.bottom) + tolerance) return false;\n','      || r.bottom > Math.min(innerHeight, p.bottom) + tolerance) return false;\n'),('bottom','      || r.top < Math.max(0, p.top) - tolerance || r.bottom > Math.min(innerHeight, p.bottom) + tolerance) return false;\n','      || r.top < Math.max(0, p.top) - tolerance) return false;\n')): mut['edge-'+edge]=(H.replace(old,new),X+'overflow-'+edge+']',None,'AssertionError: overflow-'+edge,'at Object.throws')
for edge in ('top','right','bottom','left'): mut['tolerance-'+edge]=(H.replace('  var tolerance = 1;\n','  var tolerance = 1.01;\n'),X+'overflow-'+edge+']',None,'AssertionError: overflow-'+edge,'at Object.throws')
for name,args in mut.items(): run(name,*args)
PY
python -m py_compile /tmp/stage3-helper-probe.py
python /tmp/stage3-helper-probe.py
```

Expected output is five `point-N` PASS/FAIL-at-intended-assert lines plus width, height, four edges, four tolerance probes, every, null, unrelated, direct, and descendant lines. No disposable mutation survives.

### Reproducibility Block D — five execution orders

```bash
cat > /tmp/stage3_five_orders.py <<'PY'
from pathlib import Path
import hashlib,json,random,subprocess,sys
W=Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation'); P=W/'.venv/bin/python'; O=Path('/tmp/wingman-stage3-five-orders'); dry='--dry-run' in sys.argv
F=('tests/test_shoot_screens.py','tests/test_new_screenshots.py','tests/test_current_screenshots.py','tests/test_fittings_page.py')
def h(n): return hashlib.sha256(('\n'.join(n)+'\n').encode()).hexdigest()
if dry: nodes=[x for x in Path('/tmp/wingman-stage3-inventory/candidate-actual-502.txt').read_text().splitlines() if x.startswith('tests/')]
else:
 r=subprocess.run([str(P),'-m','pytest',*F,'--collect-only','-q','-p','no:cacheprovider'],cwd=W,text=True,capture_output=True,check=True,timeout=180); nodes=[x for x in r.stdout.splitlines() if x.startswith('tests/')]
assert len(nodes)==len(set(nodes))==502 and h(nodes)=='592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a'
by={f:[n for n in nodes if n.startswith(f+'::')] for f in F}; assert [len(by[f]) for f in F]==[220,90,91,101]
shuffle=list(nodes); random.Random(0x8D5B9305).shuffle(shuffle)
orders={'normal-file':(list(F),[n for f in F for n in by[f]]),'reverse-file':(list(reversed(F)),[n for f in reversed(F) for n in by[f]]),'forward-node':(list(nodes),list(nodes)),'reverse-node':(list(reversed(nodes)),list(reversed(nodes))),'shuffled-node-seed-8d5b9305':(shuffle,shuffle)}
expected={'normal-file':'592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a','reverse-file':'ac515f4df98d8036bf5248d64a5a3645491cfe1c596f133f965056b5d6e24e79','forward-node':'592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a','reverse-node':'411ca8b2d5b3bae72340dcbdd672ae473af53123fd924dcfdc8e0268d88ef14f','shuffled-node-seed-8d5b9305':'ba282ea09921c2f6edb13c0e7b2946b858a584bd2593360d6d7f919a037a23ee'}
O.mkdir(exist_ok=True); summary={}
for name,(args,ordered) in orders.items():
 assert h(ordered)==expected[name]; (O/f'{name}.nodes.txt').write_text('\n'.join(ordered)+'\n')
 if dry: output='DRY-RUN'
 else:
  q=subprocess.run([str(P),'-m','pytest',*args,'-q','-p','no:cacheprovider'],cwd=W,text=True,capture_output=True,timeout=300); output=q.stdout+q.stderr; (O/f'{name}.pytest.txt').write_text(output); assert q.returncode==0 and '502 passed' in output,output
 summary[name]={'count':len(ordered),'sha256':h(ordered),'result':output.splitlines()[-1]}
(O/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n'); print(json.dumps(summary,sort_keys=True))
PY
python -m py_compile /tmp/stage3_five_orders.py
python /tmp/stage3_five_orders.py
```

### Reproducibility Block E — per-job provenance, artifacts, merge parents, and complete synthetic diff

Block F must run first on a clean `/tmp`; E refuses to start without the syntax-checked artifact parser.

```bash
cat > /tmp/stage3_hosted_collect.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation
R=elboaf/FlyGD-Wingman; C=35882408360; D=/tmp/wingman-stage3-hosted; test -f /tmp/stage3_hosted_artifacts.py; python -m py_compile /tmp/stage3_hosted_artifacts.py; mkdir -p "$D"
gh pr view -R "$R" --json number,headRefName,headRefOid,baseRefOid,url > "$D/pr.json"
gh run list -R "$R" --workflow ci.yml --event pull_request --limit 100 --json databaseId,headSha,conclusion > "$D/runs.json"
python - <<'PY'
import json
from pathlib import Path
d=Path('/tmp/wingman-stage3-hosted'); p=json.loads((d/'pr.json').read_text()); runs=json.loads((d/'runs.json').read_text()); m=[r for r in runs if r['headSha']==p['headRefOid'] and r['conclusion']=='success']; assert len(m)==1,m; (d/'run-id').write_text(str(m[0]['databaseId']))
PY
S=$(cat "$D/run-id"); gh api "repos/$R/actions/runs/$S" > "$D/run.json"; gh api --paginate --slurp "repos/$R/actions/runs/$S/jobs?per_page=100" > "$D/jobs.json"
python - <<'PY'
import json
from pathlib import Path
d=Path('/tmp/wingman-stage3-hosted'); pages=json.loads((d/'jobs.json').read_text()); jobs=[j for page in pages for j in page['jobs']]; names={'checks':'checks','ubuntu':'test (ubuntu-latest)','windows':'test (windows-latest)'}; selected={}
for role,name in names.items():
 m=[j for j in jobs if j['name']==name]; assert len(m)==1,(role,m); assert m[0]['conclusion']=='success',m[0]; selected[role]=m[0]
(d/'selected-jobs.json').write_text(json.dumps(selected,sort_keys=True,indent=2)+'\n')
for role,j in selected.items(): (d/f'stage3-{role}-job-id').write_text(str(j['id']))
PY
for role in checks ubuntu windows; do gh run view "$S" -R "$R" --job "$(cat "$D/stage3-$role-job-id")" --log > "$D/stage3-$role.log"; done
gh run view "$C" -R "$R" --job 107253913132 --log > "$D/comparator-checks.log"
gh run view "$C" -R "$R" --job 107253913433 --log > "$D/comparator-ubuntu.log"
gh run view "$C" -R "$R" --job 107253913529 --log > "$D/comparator-windows.log"
python - <<'PY'
import json,re
from datetime import datetime
from pathlib import Path
d=Path('/tmp/wingman-stage3-hosted'); pr=json.loads((d/'pr.json').read_text()); run=json.loads((d/'run.json').read_text()); selected=json.loads((d/'selected-jobs.json').read_text()); assert run['head_sha']==pr['headRefOid']
def checkout(path,number,head,base,merge=None):
 t=path.read_text(errors='replace'); fetch=set(re.findall(r'\+([0-9a-f]{40}):refs/remotes/pull/'+str(number)+r'/merge',t)); subjects=set(re.findall(r'HEAD is now at [0-9a-f]+ Merge ([0-9a-f]{40}) into ([0-9a-f]{40})',t)); exact=set(re.findall(r'(?:^|\s)([0-9a-f]{40})$',t,re.M)); assert len(fetch)==1,fetch; found=next(iter(fetch)); assert merge is None or found==merge,(found,merge); assert subjects=={(head,base)},subjects; assert found in exact,(found,exact); return found
stage={role:checkout(d/f'stage3-{role}.log',pr['number'],pr['headRefOid'],pr['baseRefOid']) for role in ('checks','ubuntu','windows')}; assert len(set(stage.values()))==1,stage; merge=stage['checks']
for role in ('checks','ubuntu','windows'): checkout(d/f'comparator-{role}.log',286,'0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e','459c5d6b57f5f35c97d3076bee25a6f65ba515be','c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26')
seconds=lambda a,b:(datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds(); observations={}
for role,j in selected.items():
 test=[s for s in j['steps'] if s['name']=='Test']; observations[role]={'job_id':j['id'],'job_seconds':seconds(j['started_at'],j['completed_at']),'test_step_seconds':seconds(test[0]['started_at'],test[0]['completed_at']) if test else None}
out={'pr':pr['number'],'run':run['id'],'branch_head':pr['headRefOid'],'synthetic_merge':merge,'base':pr['baseRefOid'],'observations':observations}; (d/'provenance.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
PY
python - <<'PY'
import shutil
from pathlib import Path
for p in map(Path,('/tmp/wingman-pr286-ubuntu','/tmp/wingman-pr286-windows','/tmp/wingman-stage3-ubuntu','/tmp/wingman-stage3-windows')):
 if p.exists(): shutil.rmtree(p)
PY
gh run download "$C" -R "$R" -n pytest-evidence-ubuntu-latest -D /tmp/wingman-pr286-ubuntu
gh run download "$C" -R "$R" -n pytest-evidence-windows-latest -D /tmp/wingman-pr286-windows
gh run download "$S" -R "$R" -n pytest-evidence-ubuntu-latest -D /tmp/wingman-stage3-ubuntu
gh run download "$S" -R "$R" -n pytest-evidence-windows-latest -D /tmp/wingman-stage3-windows
python - <<'PY'
import json,subprocess
from pathlib import Path
d=Path('/tmp/wingman-stage3-hosted'); p=json.loads((d/'provenance.json').read_text()); c='c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26'; s=p['synthetic_merge']; head=p['branch_head']; base=p['base']
for x in (c,s,head,base,'8d5b9305','0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e'): subprocess.run(['git','fetch','--quiet','origin',x],check=True)
def parents(commit): return subprocess.check_output(['git','rev-list','--parents','-n','1',commit],text=True).split()
assert parents(c)==[c,'459c5d6b57f5f35c97d3076bee25a6f65ba515be','0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e']; assert parents(s)==[s,base,head],parents(s)
def changed(a,b): return set(subprocess.check_output(['git','diff','--name-only',a+'..'+b],text=True).splitlines())
known_post={'docs/ci-current-owner-lifecycle-consolidation-results.md'}; assert changed(c,'8d5b9305')==known_post; assert changed(c,base)==known_post
allowed_authored={'docs/ci-generated-verifier-alerts-consolidation-results.md','docs/superpowers/plans/2026-09-23-generated-verifier-alerts-consolidation.md','docs/superpowers/specs/2026-09-23-generated-verifier-alerts-consolidation-design.md','tests/test_shoot_screens.py'}; authored=changed('8d5b9305',head); assert authored==allowed_authored,authored
full=changed(c,s); expected=known_post|allowed_authored; assert full==expected,{'missing':sorted(expected-full),'unexpected':sorted(full-expected)}
protected=('.github/','wingman/','scripts/','tests/fixtures/','packaging/'); configs={'pyproject.toml','uv.lock'}; other_tests={x for x in full if x.startswith('tests/') and x!='tests/test_shoot_screens.py'}; assert not any(x.startswith(protected) for x in full); assert not(full&configs); assert not other_tests
(d/'complete-diff.json').write_text(json.dumps({'comparator_synthetic':c,'stage3_synthetic':s,'comparator_parents':parents(c)[1:],'stage3_parents':parents(s)[1:],'known_post_comparator':sorted(known_post),'authored':sorted(authored),'full_synthetic_diff':sorted(full)},sort_keys=True,indent=2)+'\n')
PY
python /tmp/stage3_hosted_artifacts.py
SH
bash -n /tmp/stage3_hosted_collect.sh
python - <<'PY'
import subprocess
c='c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26'
assert subprocess.check_output(['git','rev-list','--parents','-n','1',c],text=True).split()==[c,'459c5d6b57f5f35c97d3076bee25a6f65ba515be','0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e']
assert set(subprocess.check_output(['git','diff','--name-only',c+'..8d5b9305'],text=True).splitlines())=={'docs/ci-current-owner-lifecycle-consolidation-results.md'}
print('comparator parents and post-comparator path set: PASS')
PY
bash /tmp/stage3_hosted_collect.sh
```

### Reproducibility Block F — JUnit identities/skips/timing sums

```bash
cat > /tmp/stage3_hosted_artifacts.py <<'PY'
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,sys,xml.etree.ElementTree as ET
C={p:Path('/tmp/wingman-pr286-'+p) for p in ('ubuntu','windows')}; S={p:Path('/tmp/wingman-stage3-'+p) for p in ('ubuntu','windows')}; FILES=('tests/test_shoot_screens.py','tests/test_new_screenshots.py','tests/test_current_screenshots.py','tests/test_fittings_page.py'); G='tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing['; A='tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions['
R={G+x+']' for x in ('hidden-settings-wanderer-controls-narrow','hidden-fittings-metadata-narrow','hidden-fittings-copy-preflight-bottom-narrow','hidden-fittings-copy-result-bottom-narrow','clipped-settings-wanderer-controls-narrow','covered-settings-wanderer-controls-narrow','covered-profiles-copy-scope','covered-fittings-metadata-narrow','covered-fittings-copy-preflight-bottom-narrow','zero-area-profiles-copy-scope','zero-area-fittings-metadata-narrow','zero-area-fittings-copy-preflight-bottom-narrow','zero-area-fittings-copy-result-bottom-narrow')}|{A+x+']' for x in ('hidden-health','invisible-master','display-none-health','clipped-master-bottom','clipped-master-left','clipped-health-top','clipped-health-right')}
def ident(c):
 p=c.get('classname').split('.'); assert len(p)>=2 and p[0]=='tests'; return '::'.join(('/'.join(p[:2])+'.py',*p[2:],c.get('name')))
def skip(s): return re.sub(r'pytest-of-[^/\s]+/pytest-\d+/[^\s:\"\']+','pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>',s.replace('\\','/'))
def parse(d):
 cases=list(ET.parse(d/'pytest-result.xml').getroot().iter('testcase')); ids=[ident(c) for c in cases]; assert len(ids)==len(set(ids)); count=defaultdict(int); sec=defaultdict(float); times={}; skips=[]; fail=err=0
 for c,n in zip(cases,ids,strict=True):
  f=n.split('::',1)[0]; t=float(c.get('time','0') or 0); count[f]+=1; sec[f]+=t; times[n]=t; z=c.find('skipped'); skips.append((n,skip((z.get('message') or z.text or '')))) if z is not None else None; fail+=len(c.findall('failure')); err+=len(c.findall('error'))
 timing=json.loads((d/'pytest-timing.json').read_text()); assert timing['case_count']==len(ids)
 for f,v in timing['files'].items(): assert v['cases']==count[f] and abs(v['seconds']-sec[f])<1e-9
 target=[n for n in ids if n.split('::',1)[0] in FILES]; return {'ids':ids,'set':set(ids),'target':target,'target_set':set(target),'count':count,'sec':sec,'times':times,'skips':skips,'fail':fail,'err':err,'g':[n for n in ids if n.startswith(G)],'a':[n for n in ids if n.startswith(A)]}
def h(n): return hashlib.sha256(('\n'.join(n)+'\n').encode()).hexdigest()
c={p:parse(d) for p,d in C.items()}; assert c['ubuntu']['set']==c['windows']['set']
assert len(c['ubuntu']['target_set'])==522 and [c['ubuntu']['count'][f] for f in FILES]==[240,90,91,101] and len(c['ubuntu']['g'])==35 and len(c['ubuntu']['a'])==31 and len(c['ubuntu']['skips'])==14 and len(c['windows']['skips'])==67
if '--comparator-self-test' in sys.argv: print('comparator-self-test: PASS'); raise SystemExit(0)
s={p:parse(d) for p,d in S.items()}; assert s['ubuntu']['set']==s['windows']['set'] and s['ubuntu']['target_set']==s['windows']['target_set']
report={}
for p in ('ubuntu','windows'):
 b=c[p]; q=s[p]; assert q['fail']==q['err']==b['fail']==b['err']==0; assert q['skips']==b['skips']; assert [q['count'][f] for f in FILES]==[220,90,91,101] and len(q['g'])==22 and len(q['a'])==24 and h(q['target'])=='592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a'; assert b['target_set']-q['target_set']==R and q['target_set']-b['target_set']==set(); common=b['target_set']&q['target_set']; report[p]={'cases':[len(b['ids']),len(q['ids'])],'skips':len(q['skips']),'generated_seconds':sum(q['times'][n] for n in q['g']),'alerts_seconds':sum(q['times'][n] for n in q['a']),'combined_product_seconds':sum(q['times'][n] for n in q['g']+q['a']),'per_file':{f:[q['count'][f],q['sec'][f]] for f in FILES},'four_file_seconds':sum(q['sec'][f] for f in FILES),'all_case_seconds':sum(q['sec'].values()),'removed_seconds':sum(b['times'][n] for n in R),'common_seconds':[sum(b['times'][n] for n in common),sum(q['times'][n] for n in common)]}
Path('/tmp/wingman-stage3-hosted-audit.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n'); print(json.dumps(report,sort_keys=True))
PY
python -m py_compile /tmp/stage3_hosted_artifacts.py
if test -f /tmp/wingman-pr286-ubuntu/pytest-result.xml && test -f /tmp/wingman-pr286-windows/pytest-result.xml; then
  python /tmp/stage3_hosted_artifacts.py --comparator-self-test
else
  echo 'artifact parser created; Block E will download comparator artifacts before invoking it'
fi
```

### Task 1: Freeze the Exact PR #286 Baseline and Comparator Controls

**Files:**
- Create: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Read: `docs/ci-current-owner-lifecycle-consolidation-results.md`
- Read artifacts: `/tmp/wingman-pr286-windows/{pytest-result.xml,pytest-timing.json}`
- Read artifacts: `/tmp/wingman-pr286-ubuntu/{pytest-result.xml,pytest-timing.json}`
- Test/collect: the four screenshot test files and the two target products in `tests/test_shoot_screens.py`

**Interfaces:**
- Consumes: baseline commit `8d5b9305`, complete PR #286 artifacts, current `GAP_CAPTURES` insertion order, and existing Alerts parametrization order.
- Produces: an authoritative 522-ID baseline, 66-ID product baseline, normalized hashes, exact hosted skip tuples, comparator provenance, and timing controls used by Tasks 2–6.

**Independent deliverable:** A reviewer can verify the source and hosted baseline without accepting any mutation result or executable change.

- [ ] **Step 1: Verify checkout identity and prerequisites**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation
git status --short --branch
git merge-base --is-ancestor 8d5b9305 HEAD
node --version
uv sync --locked --extra dev
```

Expected: the branch contains `8d5b9305`, has only the approved Stage 3 design/plan history before Task 1, Node is available, and dependency sync succeeds.

- [ ] **Step 2: Collect and archive the complete baseline without deleting cases**

Run **Reproducibility Block A** exactly. It collects the four-file baseline and both products, writes complete ordered ID reports under `/tmp/wingman-stage3-inventory`, and creates `/tmp/wingman-stage3-inventory.tar.gz`.

Expected exact output fields: baseline counts `[240, 90, 91, 101]`, baseline total `522`, product total `66`, and baseline hash `07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6`.

- [ ] **Step 3: Recompute and archive the candidate in a disposable checkout**

The same Block A keeps the projected formula separate, archives `HEAD` into a temporary checkout, and then either applies the exact Task 4 constants/decorators with match-once guards or validates that the exact post-edit anchors are already present. It runs actual pytest collection from that checkout and requires the actual ordered IDs to equal the projection. This makes the same command valid before Task 4 and as its post-edit audit.

Expected exact output fields: `actual_candidate_counts` `[220, 90, 91, 101]`, `actual_candidate_total` `502`, `candidate_product_total` `46`, `actual_equals_projection` true, candidate hash `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`, retained-product hash `359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9`, 20 removals, and zero additions. The worktree remains unmodified.

- [ ] **Step 4: Freeze exact PR #286 provenance and artifact integrity**

Record:

- PR #286 run `35882408360`.
- Branch head `0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e`.
- Synthetic merge `c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26`.
- Base `459c5d6b57f5f35c97d3076bee25a6f65ba515be`.
- Checks job `107253913132`.
- Ubuntu job `107253913433`.
- Windows job `107253913529`.
- Artifact roots `/tmp/wingman-pr286-ubuntu` and `/tmp/wingman-pr286-windows`.
- Each root contains `pytest-result.xml` and `pytest-timing.json`.

Recheck the GitHub job API and checkout logs if the artifacts or provenance differ. Expected: all three jobs concluded successfully and checked out the exact synthetic merge above.

- [ ] **Step 5: Publish the full comparator skip tuples**

Parse every `<testcase>` with `<skipped>` from both PR #286 JUnit files. Normalize only path separators and generated `pytest-of-*/pytest-N/<temporary-leaf>` fragments to `<PYTEST_TMP>`. Store every ordered `(test identity, normalized skip reason)` tuple in the results document.

Expected:

- Windows: 67 exact tuples.
- Ubuntu: 14 exact tuples.
- No failure or error.
- No Node or settings-codec availability skip.
- The 14 Ubuntu tuples include exactly the platform-only cases already listed in `docs/ci-current-owner-lifecycle-consolidation-results.md`.

- [ ] **Step 6: Freeze target timing controls without making a timing claim**

Parse JUnit testcase sums and timing JSON, and record these PR #286 observations:

| Platform | Generated 35 | Alerts 31 | Combined 66 | `test_shoot_screens.py` | Four-file target | All cases | Test step / job |
|---|---:|---:|---:|---:|---:|---:|---:|
| Windows | 6.155s | 3.552s | 9.707s | 30.799s / 240 | 90.316s / 522 | 656.277s | 11m38s / 12m34s |
| Ubuntu | 4.923s | 2.454s | 7.377s | 23.304s / 240 | 71.268s / 522 | 341.717s | 6m15s / 6m54s |

Also record the structural process control: generated cases use the persistent screenshot worker, while each Alerts case launches `screenshot_alerts.cjs`; the approved candidate projects 35 to 28 structural starts solely because seven Alerts identities are removed. State explicitly that these are controls and observations, not speedup claims.

- [ ] **Step 7: Create the results document with complete, reviewable sections**

Create these exact top-level sections and populate Task 1 evidence now:

1. `Scope and authority`
2. `Task status`
3. `Exact 522-ID baseline inventory`
4. `Exact 66-ID product baseline`
5. `Approved candidate projection`
6. `PR #286 comparator provenance and artifacts`
7. `Complete normalized comparator skip tuples`
8. `Comparator timing controls`
9. `Generated mutation ledger`
10. `Alerts mutation ledger`
11. `Parameter derivation and 20-row mapping`
12. `Local verification`
13. `Hosted evidence`
14. `Deviations, expansions, and concerns`
15. `Required self-review`

Later-task rows use explicit status such as `NOT STARTED — Task 2 owns this evidence`; do not use unresolved placeholder markers or abbreviated future-work text.

- [ ] **Step 8: Audit scope and commit**

```bash
git diff --check
git diff --name-only
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: freeze generated verifier alerts baseline"
```

Expected: only the new results document is committed in Task 1.

**Implementer report:** Provide the commit SHA; exact 522/66 counts and hashes; artifact paths; 67/14 skip counts; timing-control table; changed paths; and any discrepancy. State that no case was deleted and no executable file changed.

**Fresh reviewer gate:** A fresh reviewer independently reparses the two collection files and both comparator artifact sets, confirms all IDs/hashes/skip tuples/provenance, checks the timing table arithmetic, and approves the Task 1 commit before Task 2 begins.

**Fix loop:** For any mismatch, stop. Correct collection normalization or artifact attribution, rerun the complete Task 1 audit, add a follow-up documentation fix commit, and repeat fresh review. Do not reinterpret a mismatch as harmless drift.

---

### Task 2: Qualify the Generated 22-Case Candidate and Shared Helper

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Temporarily modify and restore: `scripts/shoot_screens.py:1161-1192,1196-1353`
- Temporarily modify and restore: `tests/fixtures/screenshot_pages.cjs:576-780`
- Test: generated 35-case product, the unchanged 13-case geometry matrix, dedicated owner tests, gap walk tests, persistent-worker protocol, and isolation tests in `tests/test_shoot_screens.py`

**Interfaces:**
- Consumes: Task 1's exact baseline and candidate IDs.
- Produces: a branch-level mutation ledger proving every retained generated semantic/wiring/shared-helper witness, or an explicit expansion/redesign decision before any deletion.

**Independent deliverable:** Documentation-only qualification evidence; no production, helper, fixture, or test witness survives.

#### Exact probe discipline

For every row below:

1. Run the named witness green with unmodified source.
2. Apply only the exact candidate replacement.
3. Run the named witness and require the intended assertion/location.
4. Save stdout/stderr and the exact diff in the results document.
5. Restore by exact inverse replacement.
6. Require `git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_pages.cjs` before the next row.

If the before text does not match exactly once, refuse the mutant. If the test fails by TypeError, timeout, protocol error, worker crash, or a different assertion, mark it unqualified.

- [ ] **Step 1: Run the complete future-retained generated set and unchanged geometry matrix green**

Use the exact 22 retained node arguments plus the independent 13-case geometry function; no `-k` approximation is permitted:

```bash
uv run --no-sync python -m pytest \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-settings-wanderer-controls-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-profiles-copy-scope]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-metadata-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-preflight-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[settled-fittings-copy-result-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-settings-wanderer-controls-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-profiles-copy-scope]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-metadata-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-preflight-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[missing-fittings-copy-result-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-settings-wanderer-controls-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-profiles-copy-scope]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-metadata-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-preflight-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[wrong-text-fittings-copy-result-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[hidden-profiles-copy-scope]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-profiles-copy-scope]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-metadata-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-preflight-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[clipped-fittings-copy-result-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[covered-fittings-copy-result-bottom-narrow]' \
  'tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing[zero-area-settings-wanderer-controls-narrow]' \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests -q
```

Expected: exactly 35 selected cases pass before mutation: retained 22 plus independent geometry 13.

- [ ] **Step 2: Qualify every owner anchor's absence and exact text**

Use these exact candidate source anchors. Each absence mutant may change multiple clauses only when every clause is part of the same named anchor-existence chain; it must leave route, owner, unrelated semantics, and shared helper behavior intact.

| Owner | Temporary absence-chain replacements | Temporary wrong-text replacement | Required retained witness |
|---|---|---|---|
| Wanderer | `&& text(remove, 'Remove connection') && !remove.disabled` → `&& (!remove || (text(remove, 'Remove connection') && !remove.disabled))`; `[note, test, remove]` → `[note, test].concat(remove ? [remove] : [])` | `text(remove, 'Remove connection')` → `remove && remove.textContent.length > 0` | same-owner `missing-settings-wanderer-controls-narrow`; `wrong-text-settings-wanderer-controls-narrow` |
| Profiles | Apply the four exact healthy-branch replacements immediately below this table | `text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')` → `note && note.textContent.length > 0` | same-owner `missing-profiles-copy-scope`; `wrong-text-profiles-copy-scope` |
| Metadata | `&& text(save, 'Save') && save.disabled && discard` → `&& (!save || (text(save, 'Save') && save.disabled)) && discard`; final exposed list `[summary, nameLabel, name, descriptionLabel, description, save]` → `[summary, nameLabel, name, descriptionLabel, description].concat(save ? [save] : [])` | `text(save, 'Save')` → `save && save.textContent.length > 0` | same-owner `missing-fittings-metadata-narrow`; `wrong-text-fittings-metadata-narrow` |
| Preflight | `&& text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.')` → `&& (!note || text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.'))`; `review.getAttribute('aria-describedby') === note.id` → `(!note || review.getAttribute('aria-describedby') === note.id)`; `note.scrollIntoView({block: 'end', behavior: 'instant'});` → `if (note) note.scrollIntoView({block: 'end', behavior: 'instant'});`; `check(exposed(note, pane) &&` → `check((!note || exposed(note, pane)) &&` | the exact `text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.')` call → `note && note.textContent.length > 0` | same-owner `missing-fittings-copy-preflight-bottom-narrow`; `wrong-text-fittings-copy-preflight-bottom-narrow` |
| Result | `&& text(status, 'Not attempted: rate limit') && status.classList.contains(expected.status)` → `&& (!status || (text(status, 'Not attempted: rate limit') && status.classList.contains(expected.status)))`; `var requiredNodes = [name, character, status, disclosure];` → `var requiredNodes = [name, character, disclosure]; if (status) requiredNodes.splice(2, 0, status);` | `text(status, 'Not attempted: rate limit')` → `status && status.textContent.length > 0` | same-owner `missing-fittings-copy-result-bottom-narrow`; `wrong-text-fittings-copy-result-bottom-narrow` |

For the Profiles absence probe, apply these exact four replacements together; they weaken only the healthy `es-copy-scope-note` existence chain:

```javascript
// 1
&& visible(WM.el('es-copy-options')) && visible(note) && scope && commit);
// becomes
&& visible(WM.el('es-copy-options')) && (!note || visible(note)) && scope && commit);

// 2
check(text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')
  && !note.classList.contains('warn') && commit.hidden && WM.el('es-copy-scope-summary').textContent);
// becomes
check(!note || (text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')
  && !note.classList.contains('warn') && commit.hidden && WM.el('es-copy-scope-summary').textContent));

// 3
note.scrollIntoView({block: 'center', behavior: 'instant'});
// becomes
if (note) note.scrollIntoView({block: 'center', behavior: 'instant'});

// 4
check(exposed(note, pane));
// becomes
check(!note || exposed(note, pane));
```

Expected intended failure for each negative witness: the fixture reaches `assert.throws(verify, /Screenshot content did not settle/, scenario)` and reports that the expected screenshot-settle exception was not thrown. The witness must not fail from a null dereference.

Record ten rows: exact mutation, exact retained ID, assertion, exit status, restoration command/result. Settled cases are green controls only and do not count as sensitivity evidence.

- [ ] **Step 3: Qualify owner-to-`exposed()` wiring independently**

Apply one exact mutation at a time:

| Owner | Exact before | Temporary replacement | Required same-owner geometry witness |
|---|---|---|---|
| Wanderer | `[note, test, remove]` | `[note, test]` | `zero-area-settings-wanderer-controls-narrow` |
| Profiles | `check(exposed(note, pane));` | `check(true);` | `clipped-profiles-copy-scope` |
| Metadata | `[summary, nameLabel, name, descriptionLabel, description, save]` | `[summary, nameLabel, name, descriptionLabel, description]` | `clipped-fittings-metadata-narrow` |
| Preflight | `check(exposed(note, pane) &&` | `check(` | `clipped-fittings-copy-preflight-bottom-narrow` |
| Result | `var requiredNodes = [name, character, status, disclosure];` | `var requiredNodes = [name, character, disclosure];` | `clipped-fittings-copy-result-bottom-narrow` |

Expected: each retained geometry witness fails at the fixture's `assert.throws` because the mutated generated verifier wrongly accepts the damaged exact anchor. For Result, confirm the clipped target is `status`, not the broad covered target or disclosure.

- [ ] **Step 4: Qualify hidden and positive-area branches**

For hidden, use **Reproducibility Block B** with exact before/after snippet files. The production before snippet includes the complete `for (var parent = node; ...)` loop; the fixture before snippet includes the complete `getClientRects` loop. The guard must report `before_count: 1` and `after_count: 1` for each file before applying. Run `hidden-profiles-copy-scope`: fixture-only control PASS, paired production mutant FAIL at `Object.throws` with `AssertionError: hidden`. Restore fixture and source through Block B and require their original SHA-256 values.

For width and height, run Block C. Its unique production before block starts with the `0.109375px` comment, includes `var tolerance = 1`, all four comparisons, all five points, and the complete hit-return body. It cannot match `_fidelity_verify_script`. Width uses the existing zero-width target; height uses the exact guarded zero-height fixture replacement. Expected for each: control PASS; mutant FAIL at `Object.throws` with `AssertionError: zero-area`.

The shared no-client-rect branch is qualified separately by Task 3's retained `display-none-master` production witness.

- [ ] **Step 5: Qualify all four containment edges and one-pixel tolerance**

Run the four edge-removal and four tolerance probes in Block C. Every probe replaces the same unique full helper block, with exactly one named comparison removed or `var tolerance = 1` changed to `1.01`. Each before/after pair is checked for count one before execution.

Expected independent failures:

- left → `overflow-left` / `AssertionError: overflow-left` at `Object.throws`;
- right → `overflow-right` / `AssertionError: overflow-right`;
- top → `overflow-top` / `AssertionError: overflow-top`;
- bottom → `overflow-bottom` / `AssertionError: overflow-bottom`;
- tolerance `1.01` → each of `overflow-top`, `overflow-right`, `overflow-bottom`, and `overflow-left` fails in its own disposable sequence.

All `rounding-*` and `edge-*` controls remain green with original production. The retained clipped preflight case is the product-level witness; the independent 13-case matrix owns exact edge/tolerance attribution.

- [ ] **Step 6: Qualify all five target-specific hit-test points and `.every()`**

Run **Reproducibility Block C** exactly. For the retained covered Result target, the fixture's framed rectangle is `(120, 130, 760, 330)`, the helper-derived inset is `4`, and the five exact coordinates are `(124,134)`, `(756,134)`, `(124,326)`, `(756,326)`, and `(440,230)`.

The temporary fixture callback accepts `(x, y)`, requires `measured === target`, rechecks `box.call(target)` against the exact target rectangle, and covers only the selected coordinate. It has no global counter and cannot consume calls made for another required node. For each coordinate, Block C removes exactly that coordinate from the unique `_framed_content_script` helper block in a disposable archive.

Expected for each of the five probes: fixture-only control PASS; production point-removal mutant FAIL in `screenshot_scenario_worker.cjs` at `Object.throws` with `AssertionError: covered`. Each full before block and each distinct after block has count exactly one.

Block C separately changes the same unique full helper block from `.every` to `.some` while only one exact target coordinate is covered. Expected: control PASS; mutant FAIL at `Object.throws` with `AssertionError: covered`.

- [ ] **Step 7: Qualify width, height, null, unrelated, direct-node, and descendant branches independently**

Continue **Reproducibility Block C**. Every production mutant replaces the unique multiline `_framed_content_script` fragment beginning with the `0.109375px` tolerance comment and ending after the hit-test return; no single-line global replacement is permitted.

Expected independent results:

- width removal: retained zero-area Wanderer control PASS; mutant FAIL at `Object.throws` with `AssertionError: zero-area`;
- height removal with exact zero-height supplemental fixture: control PASS; mutant FAIL at the same intended assertion;
- null acceptance with one exact target coordinate returning null: control PASS; mutant FAIL at `Object.throws` with `AssertionError: covered`;
- unrelated-hit acceptance with one exact target coordinate returning `document.body`: control PASS; mutant FAIL at that same negative assertion;
- direct-node rejection using the unchanged direct-hit fixture: settled Result control PASS; mutant FAIL at generated `check` with `Screenshot content did not settle: fittings-copy-result-bottom-narrow`;
- descendant rejection using an actual child only at one exact target coordinate: settled Result control PASS; mutant FAIL at the same generated `check`.

These are six separate control/mutant sequences. Null, unrelated, direct-node, and descendant evidence may not share a mutated fixture or be inferred from another row.

- [ ] **Step 8: Build the complete 13-removal generated ledger**

For each removed generated ID, record:

1. same-owner semantic evidence: exact missing and wrong-text retained IDs and their owner predicate mutants;
2. same-owner geometry/wiring evidence: exact retained geometry ID and wiring mutant;
3. shared branch evidence: hidden, edge/tolerance, covered/hit-test, or width/height mutant and witness;
4. intended assertion text/location;
5. exact restoration proof.

Use the approved 13-row mapping from the spec without abbreviating owner labels to family-level claims.

- [ ] **Step 9: Apply the expansion/redesign protocol before any implementation**

If a mutant survives or is masked:

- stop Task 2;
- leave `tests/test_shoot_screens.py` unchanged;
- restore every temporary file and prove empty diffs;
- add the smallest existing generated identity that kills the exact branch if one exists;
- otherwise revise the spec, this plan, and the results document before implementation;
- recalculate the actual retained product inventory, four-file inventory, mappings, counts, and hashes;
- never delete a different case to preserve 22 or 502;
- if persistent fixture/test-support/production change is required, return to design review rather than expanding scope.

- [ ] **Step 10: Re-run green generated/protocol/isolation coverage and commit documentation only**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes \
  tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover \
  tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent \
  tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture -q
git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_pages.cjs
git diff --check
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: qualify generated verifier alert mutations"
```

Expected before reduction: complete 35-case generated product and 13-case geometry matrix pass; no witness code remains; only the results document is committed.

**Implementer report:** Provide the commit SHA; every mutation row and intended assertion; restoration proof count; generated candidate status (`QUALIFIED`, `EXPANDED`, or `REDESIGN REQUIRED`); actual retained IDs/hashes if expanded; and exact changed paths.

**Fresh reviewer gate:** A fresh reviewer checks every exact before/replacement pair against source, verifies failures are at intended assertions, confirms fixture inputs are supplemental, audits all 13 mappings, and proves no temporary diff remains.

**Fix loop:** Any rejected row is unqualified. Restore source, narrow or replace the probe without broadening scope, rerun the row and all affected green controls, commit corrected documentation as a follow-up, and repeat fresh review. Do not proceed to Task 3 with an unresolved shared-helper dimension.

---

### Task 3: Qualify the Alerts 24-Case Candidate

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Temporarily modify and restore: `scripts/shoot_screens.py:1161-1192,2004-2028`
- Temporarily modify and restore: `tests/fixtures/screenshot_alerts.cjs:1-130`
- Test: Alerts 31-case product, Alerts walk test, and Task 2's unchanged shared geometry matrix

**Interfaces:**
- Consumes: Task 2's qualified shared-helper ledger for positive area, clipping tolerance, and hit testing.
- Produces: independent master/health guards, both missing short circuits, all three visibility mechanisms, all four edge comparisons, exact seven-row mapping, or an explicit expansion/redesign stop.

**Independent deliverable:** Documentation-only Alerts qualification; no fixture or generated script change survives.

- [ ] **Step 1: Run all 24 future-retained Alerts cases and shared controls green**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests -q
```

Expected before reduction: 31 Alerts product cases, two walk cases, and 13 geometry cases pass.

- [ ] **Step 2: Qualify the independent master and health missing guards**

Master exact mutation:

```javascript
if (!visible(master) || !exposed(master.closest('label.check'), pane)) {
// becomes
if (master && (!visible(master) || !exposed(master.closest('label.check'), pane))) {
```

Run `missing-master`. Expected: the mutated setup no longer throws the master-specific framing error, so `assert.throws(run, /Screenshot.*settings-alerts/, scenario + ' must refuse a misleading capture')` fails. It must not fail with `master.closest` TypeError.

Health exact mutation:

```javascript
if (!health || !health.textContent.trim() || !exposed(health, pane)) {
// becomes
if (health && (!health.textContent.trim() || !exposed(health, pane))) {
```

Run `missing-health`. Expected: the same fixture assertion fails because the missing health short circuit was independently weakened.

Restore and diff-audit after each probe.

- [ ] **Step 3: Qualify all three Alerts visibility mechanisms**

Use exact production/helper mutations:

| Mechanism | Exact temporary mutation | Retained ID | Supplemental fixture rule |
|---|---|---|---|
| `hidden` ancestry | remove only `parent.hidden ||` from the shared `visible()` loop | `hidden-master` | Temporarily change `if (node.hidden || node.style.display === 'none') return [];` to `if ((node.hidden && scenario !== 'hidden-master') || node.style.display === 'none') return [];`. Original production must still reject via `parent.hidden`; the mutant must be accepted and fail at `assert.throws`. |
| computed visibility | `if (parent.hidden || window.getComputedStyle(parent).visibility === 'hidden')` → `if (parent.hidden)` | `invisible-health` | None; computed visibility is the only intended rejecting branch. |
| no client rect/display none | `if (!node || !node.getClientRects().length)` → `if (!node)` | `display-none-master` | None; fixture display-none wiring is supplemental, and production `getClientRects` rejection must be the killed branch. |

A fixture-only failure or a later generic error does not qualify the branch. Restore both files after hidden-master before continuing.

- [ ] **Step 4: Qualify all four exact Alerts edge comparisons**

Remove one shared-helper comparison at a time and run its pairwise retained ID:

- top clause → `clipped-master-top`;
- right clause → `clipped-master-right`;
- bottom clause → `clipped-health-bottom`;
- left clause → `clipped-health-left`.

Expected: each mutated setup accepts its clipped anchor, so the fixture's exact negative `assert.throws` fails. A different edge case or the other owner cannot substitute for the named branch.

- [ ] **Step 5: Confirm positive-area and hit-test attribution without adding Alerts cases**

Record that:

- `zero-health` remains among the 15 unshrunk base states and exercises an Alerts owner with zero width;
- Task 2's width and temporary zero-height production mutants are killed by retained/shared generated witnesses;
- Task 2's five-point, `.every`, null, unrelated, direct-node, and descendant production mutants are killed by the retained covered Result/shared geometry evidence;
- `document.elementFromPoint = () => measured` in the Alerts fixture is wiring context only and is not counted as production hit-test sensitivity.

If an Alerts-specific production path bypasses the shared helper or any shared branch evidence does not execute the same `_framed_content_script()`, stop and redesign. Do not add a fixture-only claim.

- [ ] **Step 6: Preserve and audit all 15 base invariants**

Run the complete 15-state base sequence and the two walk cases. Confirm the unchanged fixture assertions still own:

- action-free staging;
- route, section, pane, and card ownership;
- outer Settings scroll reset and section-scroll preservation;
- master preference and Advanced disclosure preservation;
- no anchor `scrollIntoView`;
- setup-before-capture order and fail-closed walk behavior.

No base state may be removed or remapped to an anchor-product case.

- [ ] **Step 7: Build the complete seven-removal Alerts ledger**

Record these exact rows:

| Removed | Owner witness | Mechanism/edge witness |
|---|---|---|
| `hidden-health` | `invisible-health`, `missing-health` | `hidden-master` |
| `invisible-master` | `hidden-master`, `display-none-master` | `invisible-health` |
| `display-none-health` | `invisible-health`, `missing-health` | `display-none-master` |
| `clipped-master-bottom` | `clipped-master-top`, `clipped-master-right` | `clipped-health-bottom` |
| `clipped-master-left` | `clipped-master-top`, `clipped-master-right` | `clipped-health-left` |
| `clipped-health-top` | `clipped-health-bottom`, `clipped-health-left` | `clipped-master-top` |
| `clipped-health-right` | `clipped-health-bottom`, `clipped-health-left` | `clipped-master-right` |

Each row also names the exact production mutant, intended fixture assertion, and restoration proof.

- [ ] **Step 8: Apply the stop/redesign protocol for any masked Alerts branch**

If either guard, any visibility mechanism, or any edge mutant survives or fails for the wrong reason:

- stop before Task 4;
- restore all temporary files;
- expand the retained Alerts set only with the smallest existing case that kills the exact branch;
- revise the spec, this plan, and results before implementation;
- recalculate product/four-file inventories, hashes, mappings, and structural start count;
- do not preserve 24 or 502 by deleting another case;
- if persistent fixture/helper/test-support change is required, return to design review.

- [ ] **Step 9: Re-run complete Alerts/shared green coverage and commit documentation only**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests -q
git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_alerts.cjs
git diff --check
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: qualify Alerts anchor mutations"
```

Expected before reduction: 31 Alerts cases, two walk cases, and 13 geometry cases pass; no temporary change remains.

**Implementer report:** Provide the commit SHA; guard, visibility, edge, base-invariant, and shared-helper evidence; seven-row mapping; restoration proof; candidate status; and any expansion with recalculated identities/hashes.

**Fresh reviewer gate:** A fresh reviewer verifies independent short circuits, production rather than fixture sensitivity, exact edge ownership, all base-state invariants, the seven mappings, and empty temporary diffs.

**Fix loop:** Any masked or misattributed branch returns to the Task 3 stop protocol. Correct/revise, rerun all affected controls, add a follow-up documentation fix commit, and repeat fresh review. Task 4 cannot begin until both Task 2 and Task 3 are approved.

---

### Task 4: Derive and Apply the Qualified Parameter Selection

**Files:**
- Modify: `tests/test_shoot_screens.py:154-160,773-781,2568-2600`
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Do not modify: `scripts/shoot_screens.py`, either screenshot fixture, or any other test module

**Interfaces:**
- Consumes: approved Task 2 and Task 3 mutation ledgers and their actual qualified retained sets.
- Produces: named, derived generated and Alerts parameter sequences; exactly 20 removals and zero additions for the unexpanded candidate; complete 13+7 mapping.

**Independent deliverable:** The only executable commit, reviewable as parameter derivation after prior mutation qualification.

- [ ] **Step 1: Enforce the prior-gate precondition**

Read the results document and assert both product statuses are `QUALIFIED` or an approved documented `EXPANDED` set exists. Require empty diffs for scripts and fixtures.

```bash
git diff --exit-code -- scripts/shoot_screens.py \
  tests/fixtures/screenshot_pages.cjs tests/fixtures/screenshot_alerts.cjs
```

Expected: no temporary mutation remains. Refuse implementation if either ledger is incomplete.

- [ ] **Step 2: Write collection-level red assertions before changing decorators**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-products-before-reduction.txt
python - <<'PY'
from pathlib import Path
nodes = [line for line in Path('/tmp/wingman-stage3-products-before-reduction.txt').read_text().splitlines()
         if line.startswith('tests/')]
assert len(nodes) == 46, f'expected qualified 46, still collected {len(nodes)}'
PY
```

Expected for the unexpanded approved candidate: FAIL with 66 collected. If qualification expanded the set, substitute the documented actual expected count; do not use 46.

- [ ] **Step 3: Add the exact generated derived constant**

Immediately after `GAP_CAPTURES`, add:

```python
_GAP_CAPTURE_CASES = tuple(
    (scenario, key)
    for scenario in ("settled", "missing", "wrong-text")
    for key in GAP_CAPTURES
) + (
    ("hidden", "profiles-copy-scope"),
    ("clipped", "profiles-copy-scope"),
    ("clipped", "fittings-metadata-narrow"),
    ("clipped", "fittings-copy-preflight-bottom-narrow"),
    ("clipped", "fittings-copy-result-bottom-narrow"),
    ("covered", "fittings-copy-result-bottom-narrow"),
    ("zero-area", "settings-wanderer-controls-narrow"),
)
```

Replace the two stacked decorators with:

```python
@pytest.mark.parametrize(("scenario", "key"), _GAP_CAPTURE_CASES)
```

Do not hand-copy the five settled/missing/wrong-text keys. Preserve IDs as `scenario-key`.

If qualification expanded the generated set, add only the approved extra tuples after the seven witnesses and document their order.

- [ ] **Step 4: Add the exact Alerts named groups**

Immediately before the Alerts test, add:

```python
_ALERTS_BASE_SCENARIOS = (
    "settled-disabled",
    "settled-enabled",
    "wrong-route",
    "wrong-section",
    "inactive-route",
    "inactive-section",
    "missing-section",
    "missing-pane",
    "hidden-section",
    "hidden-pane",
    "hidden-card",
    "wrong-owner",
    "empty-health",
    "zero-health",
    "outside-viewport",
)
_ALERTS_ANCHOR_SCENARIOS = (
    "missing-master",
    "missing-health",
    "hidden-master",
    "invisible-health",
    "display-none-master",
)
_ALERTS_CLIPPED_SCENARIOS = (
    "clipped-master-top",
    "clipped-master-right",
    "clipped-health-bottom",
    "clipped-health-left",
)
_ALERTS_CAPTURE_SCENARIOS = (
    _ALERTS_BASE_SCENARIOS
    + _ALERTS_ANCHOR_SCENARIOS
    + _ALERTS_CLIPPED_SCENARIOS
)
```

Replace the inline list-comprehension decorator with:

```python
@pytest.mark.parametrize("scenario", _ALERTS_CAPTURE_SCENARIOS)
```

If qualification expanded Alerts, add only the approved identities to the corresponding named group and recalculate all evidence.

- [ ] **Step 5: Prove exact product order, IDs, and hashes green**

Collect the two products and assert the exact ordered generated and Alerts ID lists from the spec. For the unexpanded candidate assert:

```python
assert len(generated) == len(set(generated)) == 22
assert len(alerts) == len(set(alerts)) == 24
assert sha256(("\n".join(generated + alerts) + "\n").encode()).hexdigest() == (
    "359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9"
)
```

Then run both products:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions -q
```

Expected: 46 passed if unexpanded.

- [ ] **Step 6: Prove exact four-file collection and set diff**

Rerun Block A first. In post-edit mode it must recognize only the exact Task 4 anchors, collect the actual edited archive without applying another patch, and report `actual_equals_projection: true`. Then collect the worktree directly:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-after-all.txt
```

Audit against Task 1's baseline. For the unexpanded candidate require:

```python
assert counts == (220, 90, 91, 101)
assert len(after) == len(set(after)) == 502
assert len(set(before) - set(after)) == 20
assert not (set(after) - set(before))
assert after_hash == "592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a"
```

Expected removals are exactly the 13 generated and seven Alerts IDs in the approved mapping tables. No script or fixture identity is added.

- [ ] **Step 7: Publish the complete 20-row mapping and after inventories**

In the results document add:

- complete ordered 502-ID after inventory;
- complete ordered 46-ID retained product inventory;
- normalized hashes;
- exact set diff;
- all 13 generated mapping rows with semantic + wiring + shared branch evidence;
- all seven Alerts mapping rows with owner + mechanism/edge evidence;
- explicit zero-addition proof;
- actual expansion explanation if applicable.

- [ ] **Step 8: Run the affected file and commit**

```bash
uv run --no-sync python -m pytest tests/test_shoot_screens.py -q
git diff --check
git diff --name-only
git add tests/test_shoot_screens.py \
  docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "test: consolidate generated verifier alerts matrix"
```

Expected unexpanded result: `tests/test_shoot_screens.py` collects and passes 220 tests; only the target test file and results document are committed.

**Implementer report:** Provide the commit SHA; exact constants and order; product/four-file counts and hashes; 20 removals/zero additions; whole-file result; changed paths; and confirmation that mutation qualification preceded deletion.

**Fresh reviewer gate:** A fresh reviewer compares the diff to the approved candidate, derives all IDs from constants, verifies complete mappings and hashes, and confirms no test body, scenario semantics, script, fixture, or other module changed.

**Fix loop:** Any ID/order/hash/mapping/scope mismatch blocks Task 5. Correct only parameter derivation or the results evidence, rerun all Task 4 collection/execution checks, add a follow-up fix commit, and repeat fresh review. A mutation-related correction returns to Tasks 2–3 rather than being patched here.

---

### Task 5: Prove the Complete Local Endpoint

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Verify only: all repository paths

**Interfaces:**
- Consumes: Task 4's executable endpoint and all frozen before/after inventories.
- Produces: five-order execution evidence, focused 502-case JUnit/timing, complete pytest/skip audit, independent gates, exact scope proof, and a clean locally reviewable branch.

**Independent deliverable:** Complete local evidence with no publication or hosted claim.

- [ ] **Step 1: Re-audit exact inventories and hashes from fresh collection**

Repeat Task 4's collection from scratch. Expected unexpanded endpoint:

- generated 22;
- Alerts 24;
- retained product 46 with hash `359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9`;
- `220 / 90 / 91 / 101 = 502`;
- four-file hash `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`;
- exactly 20 mapped removals and zero additions.

If the candidate expanded, use the published actual values and prove them instead.

- [ ] **Step 2: Run the exact focused mutation-owned families**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes \
  tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover \
  tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent \
  tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests \
  tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts \
  tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides \
  tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes \
  tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer \
  tests/test_shoot_screens.py::test_lower_result_capture_keeps_recovery_before_pairs_not_sticky \
  tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure -q
```

Expected: all focused generated, shared-geometry, Alerts, walk, worker-protocol, and isolation tests pass.

- [ ] **Step 3: Run the four files in five exact orders**

Run **Reproducibility Block D** exactly. It uses Python argument arrays, passes every explicit node separately, fixes integer seed `0x8d5b9305`, saves every ordered list and pytest output, and refuses any collection other than the published 502 IDs.

Expected 502 passes in each executed order and these exact order hashes:

- normal file: `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`;
- reverse file: `ac515f4df98d8036bf5248d64a5a3645491cfe1c596f133f965056b5d6e24e79`;
- forward node: `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`;
- reverse node: `411ca8b2d5b3bae72340dcbdd672ae473af53123fd924dcfdc8e0268d88ef14f`;
- shuffled node: `ba282ea09921c2f6edb13c0e7b2946b858a584bd2593360d6d7f919a037a23ee`.

- [ ] **Step 4: Build/install the release codec and run focused four-file JUnit**

```bash
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  -q -rs --durations=50 \
  --junitxml=/tmp/wingman-stage3-focused.xml
```

Expected unexpanded endpoint: 502 passed, zero skipped/failures/errors. Record per-file, generated-product, Alerts-product, retained-product, removed-ID projection, and four-file testcase sums as observations.

- [ ] **Step 5: Run complete pytest with strict skip audit**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-stage3-full.xml
```

Projection for the unchanged local environment and unexpanded candidate: baseline `16,611 - 20 = 16,591` passed, the same 14 intentional platform-only skips, and 16,605 JUnit cases. Treat this as an identity projection to audit, not a substitute for actual collection. If environment collection changes, explain and audit it before accepting; do not hardcode the projection over actual evidence.

Reject any Node, codec, native-contract, or unexplained new skip. Publish every actual `(identity, reason)` tuple and compare it with Task 1's local baseline list.

- [ ] **Step 6: Run independent gates**

```bash
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Expected:

- JS smoke passes;
- Node DOM: 35 passed, zero failed/skipped/cancelled/todo;
- Cargo: one passed;
- Ruff check and format pass;
- diff check is empty.

- [ ] **Step 7: Audit whole-branch scope and temporary-mutant restoration**

```bash
python - <<'PY'
import subprocess
allowed = {
    'docs/ci-generated-verifier-alerts-consolidation-results.md',
    'docs/superpowers/plans/2026-09-23-generated-verifier-alerts-consolidation.md',
    'docs/superpowers/specs/2026-09-23-generated-verifier-alerts-consolidation-design.md',
    'tests/test_shoot_screens.py',
}
changed = set(subprocess.check_output(
    ['git', 'diff', '--name-only', '8d5b9305..HEAD'], text=True
).splitlines())
assert changed <= allowed, sorted(changed - allowed)
assert 'tests/test_shoot_screens.py' in changed
print('\n'.join(sorted(changed)))
PY
git diff --name-only 8d5b9305..HEAD -- \
  wingman .github scripts tests/fixtures packaging pyproject.toml uv.lock
```

Expected: changed paths are within the four-path allowlist; protected-path output is empty. Explicitly search changed paths for mutation markers, witness comments, debug output, and unresolved placeholder markers.

- [ ] **Step 8: Complete local results, self-review, and commit**

Record exact inventories/hashes, five order runs, focused/full counts and skips, independent gates, scope audit, structural process counts, and no timing claim. Complete the spec's self-review categories: placeholder, arithmetic, identity, mutation, scope, protected paths, claim discipline, and staged boundary.

```bash
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: record generated verifier alerts verification"
git status --short --branch
```

Expected: clean branch after a documentation-only Task 5 commit.

**Implementer report:** Provide commit SHA; exact local commands/results; actual full count and complete skip audit; all five order hashes; focused/product/four-file sums; scope output; and remaining risks. Do not state a speedup.

**Fresh reviewer gate:** A fresh reviewer reruns inventory/hash/scope scripts, inspects JUnit and skip tuples, checks all arithmetic and mappings, and verifies the branch contains no temporary witness or protected-path change.

**Fix loop:** Any failure returns to its owning task. Mutation evidence returns to Tasks 2–3; identity derivation to Task 4; environment/gate/scope evidence to Task 5. Apply the smallest correction, rerun all affected and endpoint checks, add a follow-up commit, and repeat fresh review.

---

### Task 6: Final Polish, Independent Review, Authorized Publication, and Hosted Evidence

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Review: approved spec, this plan, complete `8d5b9305..HEAD` diff, Task 5 JUnit/timing evidence, and PR #286 comparator artifacts

**Interfaces:**
- Consumes: the clean locally verified endpoint.
- Produces: polished/reviewed branch; only with explicit authorization, a PR and hosted Windows/Ubuntu artifact comparison to PR #286; bounded next decision.

**Independent deliverable:** Final review is separable from publication. No push or PR occurs without explicit authorization.

- [ ] **Step 1: Run `polish-core --fix` over the whole Stage 3 branch**

Load the `polish-core` skill and run its fix workflow for `8d5b9305..HEAD`. Inspect every edit. Reject any change outside the approved four-path allowlist or any edit that weakens evidence. Rerun every affected test/gate and commit only high-confidence corrections as a separate fix commit.

Expected: no unreviewed polish change remains.

- [ ] **Step 2: Obtain an independent whole-branch review**

A fresh reviewer examines:

- spec-to-plan-to-results coverage;
- exact mutation branch attribution and intended assertions;
- fixture-only evidence labels;
- expansion/stopping protocol;
- complete 20-row mapping;
- parameter derivation and ID order;
- full inventories/hashes/skips;
- protected-path and claim discipline;
- no lower Fittings/workflow/budget/shard scope.

Resolve every Critical or Important finding. Re-run affected tests and obtain fresh approval after each fix wave.

- [ ] **Step 3: Run fresh final local verification on the reviewed executable head**

At minimum rerun:

- fresh 502-ID collection and both hashes;
- the focused mutation-owned command;
- the complete four-file JUnit run;
- full pytest with skip audit;
- JS smoke;
- Node DOM 35;
- Cargo;
- Ruff check and format;
- diff/scope/protected-path audits;
- `git diff --check`.

Expected unexpanded endpoint remains `220 / 90 / 91 / 101 = 502`, 20 removals, zero additions, and the qualified hashes. Record the exact reviewed executable head SHA.

- [ ] **Step 4: Run `change-explainer` before publication**

Load the `change-explainer` skill and produce the reviewer-facing summary from the final diff, results, tests, and verification. The explanation must cover what changed, mutation gates, exact identity transformation, deviations/expansions, edge cases, verification actually run, reviewer focus, and remaining risks. It must state no Stage 3 or overall timing claim.

- [ ] **Step 5: Stop for explicit publication authorization**

Present the reviewed head SHA, clean status, exact counts/hashes, local gates, independent review outcome, and proposed PR title/body. Do not push, open a PR, or call GitHub mutation APIs until the maintainer explicitly authorizes publication.

- [ ] **Step 6: After authorization, publish the exact reviewed head**

Push the Stage 3 branch to `fork` and open a PR against `elboaf/FlyGD-Wingman:main` using `-R elboaf/FlyGD-Wingman`. Suggested title:

```text
Consolidate generated verifier and Alerts tests
```

The PR body states:

- qualified generated `35 → 22` and Alerts `31 → 24`, or actual expanded values;
- `522 → 502`, 20 removals, zero additions, or actual expanded values;
- mutation qualification and restoration boundaries;
- complete local evidence;
- structural process-start observation only;
- no workflow, budget, shard, overall-runtime, speedup, or lower Fittings claim.

- [ ] **Step 7: Derive exact Stage 3 hosted provenance from API and checkout logs**

On a clean `/tmp`, run **Reproducibility Block F first** to create and syntax-check `/tmp/stage3_hosted_artifacts.py`; its comparator self-test runs immediately when comparator artifacts already exist, otherwise Block E downloads them before the final invocation. Then run **Reproducibility Block E** after authorization and a successful executable-head run. E refuses a missing parser, derives the current PR/run from the reviewed branch head, selects exact job IDs, fetches each log independently, downloads artifacts, and finally invokes the already-created parser.

The collector refuses duplicate/missing required jobs, fetches checks/Ubuntu/Windows logs by their exact API job IDs, and validates each log independently. Every log must contain the exact pull-merge fetch ref, exact 40-character checkout SHA, and exact `Merge head into base` subject. It then reads the merge objects directly: GitHub’s tested pull-ref merge is constructed by checking out the base and merging the PR head, so parent 1 must equal the API base and parent 2 must equal the API head. Comparator parents must be `459c5d6b...` then `0c785ce...`; Stage 3 parents must be its recorded API base then head. Any reversal or mismatch is refused rather than normalized away.

Expected: all required jobs have `success`; Stage 3 provenance is written to `/tmp/wingman-stage3-hosted/provenance.json`; Windows and Ubuntu artifacts are downloaded with both evidence files present.

- [ ] **Step 8: Compare the complete synthetic diff and hosted artifacts**

Block E computes the **complete** `git diff --name-only c1ab289e..stage3Synthetic`. It derives the expected union from two independently checked sets: comparator synthetic to final merged Stage 2 baseline `8d5b9305` must be exactly `docs/ci-current-owner-lifecycle-consolidation-results.md`; `8d5b9305` to the Stage 3 branch head must be exactly the Stage 3 spec, plan, results, and `tests/test_shoot_screens.py`. The full synthetic diff must equal that union exactly—no hand-picked executable subset.

The same script explicitly refuses any full-diff path under `.github/`, `wingman/`, `scripts/`, `tests/fixtures/`, or `packaging/`; refuses `pyproject.toml`/`uv.lock`; and refuses every other test path. Branch-head authored accounting remains separate from synthetic-merge comparison. Unexpected base movement or any other file makes the comparison inconclusive.

The parser created by Block F and invoked at the end of Block E directly parses Windows/Ubuntu JUnit and timing JSON, normalizes complete identities including class owners, normalizes skip path fragments, cross-checks JSON/JUnit counts and per-file sums, and requires:

- equal Stage 3 platform identity and target sets;
- `220 / 90 / 91 / 101 = 502`, generated 22, Alerts 24;
- exact after hash `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`;
- the explicit 20-ID removed set and zero additions relative to PR #286;
- exact comparator skip tuples: Ubuntu 14 and Windows 67;
- zero failures/errors;
- generated, Alerts, combined-product, per-file, four-file, all-case, removed-ID, and common-retained-ID sums.

Block E records Test-step/job observations from the API; Block F records testcase sums. Hosted pass projections remain conditional: Ubuntu 16,591 passed/14 skipped and Windows 16,538 passed/67 skipped only if actual identities and normalized skips match. No observation is a speedup claim.

- [ ] **Step 9: Make the bounded next decision**

Decision rules:

- **GO for review of a separate later tranche only** if required jobs pass, platform identities/skips agree, exact removals/zero additions hold, mutation/scope contracts remain intact, and there is no unexplained material target regression.
- **INCONCLUSIVE** if provenance, blobs, artifacts, platform identities, or observations are not comparable; repeat measurement rather than infer.
- **STOP / repair** for contract failure, identity/skip divergence, residual mutation, protected-path drift, or unexplained material target regression.

No outcome authorizes workflow selection, budget enforcement, sharding, cadence changes, dependency changes, an overall/Stage 3 speedup claim, or lower Fittings work.

- [ ] **Step 10: Commit hosted evidence and verify the evidence head**

Commit only the results document:

```bash
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: record hosted generated verifier alerts evidence"
```

After authorization, push the evidence commit, update the PR body with bounded conclusions, and wait for required checks on the exact documentation head. Finish only when those checks pass or the results document records an explicit unresolved status.

**Implementer report:** Provide polish edits, independent review outcome, final executable/evidence SHAs, publication authorization, PR/run/job provenance, artifact paths, identity/skip comparisons, all testcase sums, Test-step/job observations, decision, and remaining risks.

**Fresh reviewer gate:** A fresh reviewer validates the final diff and every hosted claim directly from APIs/logs/artifacts, confirms the comparator is PR #286 executable run `35882408360`, and checks the decision language for prohibited claims.

**Fix loop:** For code/test findings, return to the owning earlier task, rerun local verification, repolish, rereview, and obtain a new executable run. For evidence-only errors, correct the results document, reparse artifacts, commit a follow-up documentation fix, and re-run evidence-head checks. Never conceal an incomparable run with a timing conclusion.

---

## Plan Completion Self-Review

Before treating this plan as executable, the plan author performs these checks:

- [x] **Spec coverage:** Every authority, candidate ID, mutation family, mapping, stopping rule, verification gate, hosted comparator requirement, claim restriction, and Stage 4 stop has an owning task.
- [x] **Placeholder scan:** The plan contains no unresolved placeholder marker or abbreviated future-work text.
- [x] **Type/name consistency:** `_GAP_CAPTURE_CASES`, `_ALERTS_BASE_SCENARIOS`, `_ALERTS_ANCHOR_SCENARIOS`, `_ALERTS_CLIPPED_SCENARIOS`, and `_ALERTS_CAPTURE_SCENARIOS` are spelled identically in all tasks and match their parametrization decorators.
- [x] **Arithmetic consistency:** `35 + 31 = 66`, `22 + 24 = 46`, `13 + 7 = 20`, `240 - 20 = 220`, `220 + 90 + 91 + 101 = 502`, and local baseline `16,611 - 20 = 16,591` are consistent as projections for the unexpanded candidate.
- [x] **Mutation consistency:** Every temporary production/helper mutant has an intended retained witness, exact assertion, and restoration gate; supplemental fixture input is never credited alone.
- [x] **Scope consistency:** The only planned executable diff is `tests/test_shoot_screens.py`; scripts, fixtures, production, workflows, configuration, dependencies, packaging, markers, budgets, and shards remain protected.
- [x] **Claim discipline:** Structural process counts and durations are observations only; no Stage 3, whole-suite, job, runner-efficiency, or critical-path speedup is claimed.
- [x] **Probe isolation:** All five hit probes require the exact Result target and exact derived `(x, y)` coordinate; no global counter or cross-node state determines coverage.
- [x] **Unique anchors:** Width, height, edge, tolerance, every, null, unrelated, direct, descendant, and point-removal mutants replace one full `_framed_content_script` helper block whose source count is exactly one.
- [x] **Script syntax:** All six embedded temporary scripts were extracted from this Markdown and passed `python -m py_compile` or `bash -n`; Block A applied the exact Task 4 edit in a disposable archive and actual collection equaled projection, Block C ran every disposable probe, Block D dry-run reproduced all five hashes, and Block F comparator self-test parsed PR #286 artifacts.
- [x] **Hosted ordering:** A clean `/tmp` execution creates and checks Block F’s parser before Block E invokes it.
- [x] **Per-job provenance:** Required job names must each resolve to exactly one API job; each job log independently proves fetch SHA, checkout SHA, and merge subject; merge-object parents prove base/head order.
- [x] **Complete synthetic accounting:** Full comparator-to-Stage3 synthetic diff must equal the explicit one-file post-comparator Stage 2 set union the exact four-file Stage 3 authored set. Protected paths are also refused explicitly; branch-head accounting remains separate.

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-09-23-generated-verifier-alerts-consolidation.md`.

Recommended execution: **Subagent-Driven Development** with a fresh implementer and fresh reviewer gate per task, using `superpowers:subagent-driven-development`. Inline execution is acceptable only with `superpowers:executing-plans` and the same task/commit/review boundaries.
