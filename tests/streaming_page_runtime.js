// Focused DOM/bridge boundary for the Streaming card.
//
// Exists because of #321's build test: the mirror toggle rendered and
// re-labelled but had NO click handler attached -- a dead control no
// lexical guard can see (test_bridge_contract asserts sends exist on Api,
// not that anything sends them; js_smoke executes only top level). This
// harness executes the real production module against DOM/bridge doubles
// and CLICKS it. No CSS or WebView2: events are delivered explicitly.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '..', 'wingman', 'web');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const markup = new Map(Array.from(
  html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g),
  match => [match[2], match[1]]));
const elements = {};
const handlers = {};
const calls = [];
const replies = {};
let mirrorState = null;
let couplingState = null;

// The scenario's expected literals are created in the vm realm; the
// recorded calls are created here. assert/strict's deepEqual is
// deepStrictEqual, which rejects any cross-realm object on prototype
// identity -- two identical arrays from different realms compare unequal,
// so every deepEqual would fail (observed, not hypothetical). These
// scenarios only ever assert JSON data, so compare by JSON.
const baseAssert = require('node:assert/strict');
const assert = Object.assign(() => {}, baseAssert, {
  deepEqual(actual, expected, message) {
    try {
      baseAssert.deepStrictEqual(JSON.stringify(actual ?? null),
                                 JSON.stringify(expected ?? null));
    } catch {
      baseAssert.fail((message ?? '') + '\n  actual:   ' +
        JSON.stringify(actual) + '\n  expected: ' + JSON.stringify(expected));
    }
  },
});

function eventTarget(node) {
  node.listeners = {};
  node.addEventListener = function (name, callback) {
    (this.listeners[name] || (this.listeners[name] = [])).push(callback);
  };
  node.fire = function (name, fields = {}) {
    const event = {target: this, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...fields};
    (this.listeners[name] || []).forEach(callback => callback(event));
    return event;
  };
  return node;
}

function element(tag) {
  return eventTarget({
    tagName: tag.toUpperCase(), children: [], parentNode: null,
    value: '', hidden: false, disabled: false, checked: false,
    className: '', _text: '',
    set textContent(value) { this._text = value; },
    get textContent() { return this._text; },
    classList: {add() {}, remove() {}, contains() { return false; }},
  });
}

// Unlike the profiles runtime, an unknown id FAILS here: the card's
// ceremony wiring (#321) added seven ids the module must find in the real
// markup, and silently creating a div would hide exactly the typo this
// harness exists to catch.
function el(id) {
  if (elements[id]) return elements[id];
  assert.ok(markup.has(id), 'no element id="' + id + '" in index.html');
  return (elements[id] = element(markup.get(id)));
}

const WM = {
  el,
  handle(name, callback) { handlers[name] = callback; },
  setEnabled(node, enabled) { node.disabled = !enabled; },
  positionWarn(warn) { return warn || ''; },
  send(...args) {
    calls.push(args);
    const method = args[0];
    if (method === 'stream_mirror_state') return Promise.resolve(mirrorState);
    if (method === 'stream_coupling_state') return Promise.resolve(couplingState);
    if (method === 'capture_bind') return Promise.resolve(null);
    assert.ok(method in replies, 'unexpected bridge call: ' + method);
    return Promise.resolve(replies[method]);
  },
};

const document = eventTarget({activeElement: null});
const tick = () => new Promise(resolve => setImmediate(resolve));

let finish;
const done = new Promise(resolve => { finish = resolve; });

const scenario = fs.readFileSync(0, 'utf8');
const source = fs.readFileSync(path.join(web, 'streaming.js'), 'utf8');
const closure = source.match(/}\(\)\);\r?\n$/);
assert.ok(closure, 'streaming.js must end with its IIFE close');
const exercise = `
  el('coupling-quiet').parentNode = element('div');
  el('coupling-state').parentNode = element('div');
  (async () => {
    ${scenario}
  })().then(result => finish(result), err => finish('ERR: ' + (err && err.stack || err)));
`;
vm.runInNewContext(source.slice(0, closure.index) + exercise + '\n}());\n', {
  WM, document, element, el, assert, calls, tick, console,
  handlers, setImmediate, finish,
  setMirror(payload) { mirrorState = payload; },
  setCoupling(payload) { couplingState = payload; },
  setReply(method, reply) { replies[method] = reply; },
}, {filename: 'streaming.js'});

done.then(code => {
  if (typeof code === 'string') {
    // A failed scenario reports through the harness, not the vm: the vm
    // realm has no console of its own beyond the one passed in, and an
    // error thrown in the .then handler itself would vanish silently.
    console.error(code);
    code = 1;
  }
  process.exit(code);
});
// A scenario that never resolves would otherwise drain the loop and exit
// 0 -- a hang passing as a pass. The watchdog is what makes a stuck
// scenario fail loudly instead.
setTimeout(() => { console.error('scenario timed out'); process.exit(1); }, 5000);
