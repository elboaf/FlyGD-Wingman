// Capture framing only: real markup ancestry, bounded scroll/geometry inputs.
// This is not a CSS renderer or evidence of a Windows/WebView2 capture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createDOM} = require('./screenshot_dom.cjs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const {document, Element, scrolls} = createDOM(data.page);
const el = id => document.getElementById(id);
const route = el('route-settings'), section = el('section-alerts');
const pane = section.closest('.settings-pane');
const master = el('alert-enabled'), label = master.closest('label.check');
const health = el('alerts-health'), advanced = el('alert-advanced');
route.classList.add('active');
for (const node of pane.querySelectorAll('.settings')) node.classList.toggle('active', node === section);
health.textContent = 'Not watching gamelogs.';
pane.scrollTop = 420;
section.scrollTop = 17;
const actions = [];
const forbidden = name => (...args) => { actions.push([name, ...args]); throw Error('Unexpected action: ' + name); };
const WM = {
  current_route: 'settings', current_section: 'alerts', el,
  send: forbidden('bridge'), route: forbidden('route'), section: forbidden('section'),
  openSettingsSection: forbidden('openSettingsSection'), notify_section: forbidden('notify_section'),
  settingsTab: forbidden('settingsTab')
};
Element.prototype.click = forbidden('click');
Element.prototype.dispatchEvent = forbidden('dispatchEvent');
const rect = (left, top, right, bottom) => ({left, top, right, bottom, width: right-left, height: bottom-top});
const bounds = rect(190, 70, 820, 580);
let clipped = null, measured;
Object.defineProperty(Element.prototype, 'parentElement', {get() { return this.parentNode; }});
Element.prototype.getBoundingClientRect = function () {
  measured = this;
  if (this === pane) return bounds;
  // The native checkbox is intentionally invisible; its .check label paints it.
  if (this === master) return rect(210, 150 - pane.scrollTop, 210, 150 - pane.scrollTop);
  if (this === label || this === health) {
    const top = (this === label ? 150 : 200) - pane.scrollTop;
    const r = rect(210, top, 730, top + 25);
    if (clipped && clipped.node === this) {
      r[clipped.edge] = clipped.limit;
      r.width = r.right - r.left; r.height = r.bottom - r.top;
    }
    return r;
  }
  return bounds;
};
Element.prototype.getClientRects = function () {
  for (let node = this; node; node = node.parentNode) {
    if (node.hidden || node.style.display === 'none') return [];
    if ((node.classList.contains('route') || node.classList.contains('settings'))
        && !node.classList.contains('active')) return [];
  }
  return [this.getBoundingClientRect()];
};
const window = {
  document, WM, innerWidth: 840, innerHeight: 625,
  getComputedStyle: node => ({visibility: node.style.visibility || 'visible'}),
  pywebview: {api: new Proxy({}, {get: (_, name) => forbidden('api.' + name)})}
};
window.window = window;
document.elementFromPoint = () => measured;
const runtime = vm.createContext(window);
const run = () => vm.runInContext(data.stage || '', runtime);

const scenario = data.scenario;
if (scenario === 'wrong-route') WM.current_route = 'main';
else if (scenario === 'wrong-section') WM.current_section = 'fleet';
else if (scenario === 'inactive-route') route.classList.remove('active');
else if (scenario === 'inactive-section') section.classList.remove('active');
else if (scenario === 'missing-section') section.remove();
else if (scenario === 'missing-pane') pane.classList.remove('settings-pane');
else if (scenario === 'hidden-section') section.hidden = true;
else if (scenario === 'hidden-pane') pane.style.visibility = 'hidden';
else if (scenario === 'empty-health') health.textContent = '  ';
else if (scenario === 'zero-health') health.getBoundingClientRect = () => rect(210, 200, 210, 225);
else if (scenario === 'hidden-card') label.closest('.card').hidden = true;
else if (scenario === 'wrong-owner') el('section-fleet').appendChild(health);
else if (scenario.startsWith('missing-')) (scenario.endsWith('master') ? master : health).remove();
else if (scenario.startsWith('hidden-')) (scenario.endsWith('master') ? label : health).hidden = true;
else if (scenario.startsWith('invisible-')) (scenario.endsWith('master') ? label : health).style.visibility = 'hidden';
else if (scenario.startsWith('display-none-')) (scenario.endsWith('master') ? label : health).style.display = 'none';
else if (scenario.startsWith('clipped-')) {
  const [, anchor, edge] = scenario.split('-');
  clipped = {node: anchor === 'master' ? label : health, edge,
    limit: bounds[edge] + (['left', 'top'].includes(edge) ? -2 : 2)};
} else if (scenario === 'outside-viewport') {
  bounds.bottom = 700; bounds.height = 630;
  clipped = {node: health, edge: 'bottom', limit: 650};
}

// Preserve preferences, disclosure state, and ownership even when staging fails.
master.checked = scenario === 'settled-enabled';
advanced.open = scenario === 'settled-enabled';
const controls = document.querySelectorAll('input, select, textarea, details');
const snapshot = () => controls.map(node => [node.value, node.checked, node.disabled, node.open]);
const before = snapshot(), owner = [WM.current_route, WM.current_section, route.className, section.className];
if (scenario.startsWith('settled')) {
  run();
  assert.equal(pane.scrollTop, 0, 'base Alerts capture must reset stale outer Settings scroll');
  for (const node of [label, health]) {
    const r = node.getBoundingClientRect();
    assert.ok(r.top >= bounds.top && r.bottom <= bounds.bottom && r.left >= bounds.left && r.right <= bounds.right);
  }
  // Repeat from another inherited offset without toggling Advanced or the master.
  pane.scrollTop = 300;
  run();
  assert.equal(pane.scrollTop, 0);
} else {
  assert.throws(run, /Screenshot.*settings-alerts/, scenario + ' must refuse a misleading capture');
}
assert.equal(section.scrollTop, 17, 'the section itself is not the scroll owner');
assert.deepEqual(snapshot(), before, 'framing must not change preferences or disclosures');
assert.deepEqual([WM.current_route, WM.current_section, route.className, section.className], owner);
assert.deepEqual(actions, [], 'no bridge, section entry, click, or dispatched write');
assert.deepEqual(scrolls, [], 'do not scroll an anchor into a different framing');
console.log('PASS Alerts capture framing ' + scenario);
