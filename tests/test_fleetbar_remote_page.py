"""Execute standalone dev fixtures and production handler bodies, not CSS/native."""

import re
import shutil
import subprocess
from pathlib import Path


def test_fleet_table_keyboard_focus_uses_an_inset_theme_ring():
    """The tab stop needs its own ring inside the overflow-clipped widget.

    This guards the CSS convention only; keyboard scrolling and the rendered
    focus indicator still require a browser/WebView2 check.
    """
    web = Path(__file__).resolve().parents[1] / "wingman" / "web"
    html = (web / "fleetbar.html").read_text(encoding="utf-8")
    assert re.search(r'<div\b[^>]*class="fleet-table"[^>]*tabindex="0"', html)
    focus = re.search(r"\.fleet-table:focus-visible\s*\{([^}]*)\}", html)
    assert focus, "the Fleet table has no authored keyboard focus indicator"
    assert re.search(r"outline:\s*2px solid var\(--focus-ring\)\s*;", focus[1])
    assert re.search(r"outline-offset:\s*-2px\s*;", focus[1]), (
        "the focus ring must stay inside the overflow-clipped shell"
    )


def test_damage_tracks_keep_complete_remote_markers_and_header_only_drag():
    web = Path(__file__).resolve().parents[1] / "wingman" / "web"
    html = (web / "fleetbar.html").read_text(encoding="utf-8")
    grid = re.search(r"\.fleet-grid\s*\{([^}]*)\}", html)
    assert "minmax(0, 1fr) 160px 148px" in grid[1]
    marker = re.search(r"\.fleet-remote\s*\{([^}]*)\}", html)
    assert "white-space: normal" in marker[1]
    assert "text-overflow" not in marker[1]
    assert html.count("pywebview-drag-region") == 1
    assert '<div class="fleet-drag pywebview-drag-region" id="fleet-drag">' in html
    assert 'id="fleet-reset-width"' in html and 'id="fleet-hide"' in html
    assert "opacity: 0" in html and "visibility: hidden" in html
    assert 'aria-label="Character damage and incoming EWAR"' in html


def test_standalone_remote_handler_fixtures_and_stale_hydration():
    node = shutil.which("node")
    assert node, "Node is a required verification prerequisite"
    web = Path(__file__).resolve().parents[1] / "wingman" / "web"
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.children=[]; this._text=''; this.className=''; this.style={}; this.hidden=false; this.offsetWidth=420; this.offsetHeight=95;
    this.attributes={};
    this.classList={toggle:()=>{},add:name=>{this.className+=' '+name;}}; }
  set textContent(value) { this._text=value; this.children=[]; }
  get textContent() { return this._text + this.children.map(c=>c.textContent).join(''); }
  appendChild(child) { this.children.push(child); }
  setAttribute(name,value) { this.attributes[name]=String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
}
const nodes = Object.fromEntries(['fleet-rows','fleet-empty','fleet-health','fleet-note'].map(id=>[id,new Element()]));
const shell=new Element(), table=new Element();
const document={createElement:()=>new Element(),getElementById:id=>nodes[id],
  querySelector:s=>s==='.fleet-shell'?shell:s==='.fleet-table'?table:null,
  addEventListener:()=>{},fonts:{ready:Promise.resolve()}};
const window={location:{search:'?dev=1'},addEventListener:()=>{},screenX:0,screenY:0};
const context=vm.createContext({window,document,console,Promise,URLSearchParams,screen:{availWidth:1920,availHeight:1080},setTimeout:()=>{}});
vm.runInContext(fs.readFileSync(process.argv[1]+'/dev.js','utf8'),context);
vm.runInContext(fs.readFileSync(process.argv[1]+'/fleetbar.js','utf8'),context);
async function main() {
  await new Promise(setImmediate);
  assert.equal(typeof window.DEV.fleetBar,'function');
  assert.match(window.location.hash,/^#fleet-page=[0-9a-f]{64}$/);
  const valueOf=half=>half.children.find(c=>c.className==='fleet-damage-value').textContent;
  const fillOf=half=>half.children.find(c=>c.className==='fleet-damage-track').children[0];
  for (const kind of ['local','remote','mixed','stale','empty','hidden','long','max','maxlocal','defensive','zero','roster','nolog']) {
    await window.DEV.fleetBar(kind);
    const rows=nodes['fleet-rows'].children;
    assert(nodes['fleet-health'].textContent.startsWith('LOCAL '));
    if (kind==='empty') { assert.equal(rows.length,0); assert.equal(nodes['fleet-empty'].hidden,false); continue; }
    assert(rows.every(row=>row.children.length===3));
    if (kind==='local') { assert.equal(rows[0].children[0].children.length,1); assert.equal(nodes['fleet-health'].textContent,'LOCAL LIVE'); }
    if (kind==='remote') assert.equal(rows[0].children[0].children[1].textContent,'REMOTE');
    if (kind==='stale') {
      assert.equal(rows[0].children[0].children[1].textContent,'REMOTE · STALE');
      assert(!rows[0].children[1].children[0].className.includes('live'));
      assert(!rows[0].children[2].className.includes('active'));
    }
    if (kind==='hidden') assert.equal(rows[0].children[0].children[0].title,'Other remote');
    if (kind==='long') assert(rows[0].children[0].children[0].title.length>=100);
    if (kind==='max') { assert.equal(valueOf(rows[0].children[1].children[0]),'10000000'); assert.equal(rows[0].children[2].textContent,'SCRAM/POINT'); }
    if (kind==='maxlocal' || kind==='defensive' || kind==='zero') {
      const expected=kind==='maxlocal'?'10000000':kind==='defensive'?'>10m':'0';
      assert.equal(valueOf(rows[0].children[1].children[0]),expected);
      assert.equal(valueOf(rows[0].children[1].children[2]),expected);
    }
    if (kind==='nolog') {
      assert.equal(rows[0].children[1].textContent,'NO LOG');
      assert.equal(rows[0].children[2].textContent,'—');
    }
    for (const row of rows.filter(r=>r.children[0].children.length===2)) {
      const damage=row.children[1], incoming=damage.children[2];
      assert.equal(valueOf(incoming),'—');
      assert.equal(fillOf(incoming).style.transform,'scaleX(0)');
      assert(!incoming.className.includes('warn'));
      assert(damage.getAttribute('aria-label').endsWith('incoming unavailable'));
      assert(!damage.textContent.includes('NO LOG'));
    }
    if (kind==='roster') assert.equal(rows.length,128);
  }
  await window.DEV.fleetBar('stale');
  const before=nodes['fleet-rows'].textContent;
  for (const revision of [0,-1,null,NaN]) {
    await window.onFleetSnapshot({revision,rows:[]});
    assert.equal(nodes['fleet-rows'].textContent,before);
  }
  const noDev={location:{search:''}};
  vm.runInNewContext(fs.readFileSync(process.argv[1]+'/dev.js','utf8'),{window:noDev});
  assert.equal(noDev.pywebview,undefined);
  assert.equal(noDev.location.hash,undefined);
  const native={location:{search:'?dev=1'},pywebview:{api:{owned:true}}};
  vm.runInNewContext(fs.readFileSync(process.argv[1]+'/dev.js','utf8'),{window:native});
  assert.equal(native.pywebview.api.owned,true);
  assert.equal(native.DEV,undefined);
  assert.equal(native.location.hash,undefined);
  console.log('PASS standalone Fleet fixtures and handlers');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script, str(web)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS standalone Fleet fixtures and handlers" in result.stdout
