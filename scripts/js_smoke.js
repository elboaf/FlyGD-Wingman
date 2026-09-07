// FlyGD Wingman -- the web layer's first EXECUTABLE gate.
//
//   node scripts/js_smoke.js                      # every page, repo layout
//   node scripts/js_smoke.js path/to/web          # every page under that dir
//   node scripts/js_smoke.js path/to/web sigbar.html   # one page
//
// Exit status is 0 when every module of every page loads and non-zero
// otherwise; the report is one line per module, `ok` or `THROW`.
//
// Why this exists. Nothing in pytest executes web/*.js -- the suite reads
// the page's SOURCE, lexically, and never sees the result (DESIGN.md, "The
// one rule that explains most of the others"). Handlers register at the top
// of each module's IIFE, so one bad name throws mid-module and every
// registration below it silently never runs: the screen loads as an inert,
// empty copy of itself, with no error anywhere a user or a test would look.
// `WM.handle('onEveSettingsRunning')` once did exactly that to the whole EVE
// Settings route while every test stayed green. tests/test_bridge_contract.py
// guards the handler-name half of that with regexes; this script runs the
// modules for real, so the OTHER ways an IIFE can throw are covered too.
//
// What it does: builds a `vm` context whose `window`/`document` are
// permissive Proxy stubs -- every element lookup returns an element that
// accepts any property, call or listener -- then evaluates app.js and every
// `<script src>` of each page IN PAGE ORDER, each page in a fresh context.
// Anything thrown while a module's top level runs is reported against that
// module's name. Because app.js's real `WM` is loaded first, an unknown
// `WM.handle` name throws the same way it does in WebView2.
//
// What it CATCHES: anything that throws while an IIFE runs to completion --
//   * a `WM.handle('name')` absent from WM.HANDLERS (the incident above);
//   * a misspelled identifier at module top level (`refrsh()` for
//     `refresh()`, a ReferenceError the moment the line is reached);
//   * a `WM.*` member a module uses at load that app.js does not define;
//   * a wrong `<script src>` order, where a module reads a global that the
//     module defining it has not yet run;
//   * a syntax error, which throws before the first line executes.
//
// What it CANNOT catch, and must not be mistaken for catching:
//   * a handler BODY that fails on a real payload -- handlers are registered
//     here, never invoked, and nothing pushes into them;
//   * a missing element id -- the stub answers every `getElementById` with a
//     live-looking element, so `WM.el('typo').addEventListener(...)` passes
//     here and does nothing in the app;
//   * anything in CSS, layout, or rendering -- nothing is painted;
//   * code that runs LATER: timers, `pywebviewready`, DOMContentLoaded,
//     promise callbacks and event listeners are registered and then
//     abandoned when the process exits. Only synchronous top level runs.
//
// Stdlib only, on purpose: the repo has no package.json and no bundler,
// and a gate that needs an `npm install` first is one that stops being run.
// ubuntu-latest ships node preinstalled, which is what CI relies on; the
// pytest wrapper (tests/test_js_smoke.py) skips where node is absent.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// The three pages that reach a WebView2 window. index.html is the app;
// the two bars are standalone windows that do NOT load app.js (their
// header comments explain why), so their one module is the whole page and
// the WM.HANDLERS allowlist is irrelevant to them -- which is exactly why
// they need an executable check, having no lexical one.
const PAGES = ['index.html', 'fleetbar.html', 'sigbar.html'];

function scriptsOf(html) {
  // Only bare `<script src="x.js"></script>` tags, which is the only shape
  // the pages use. A page whose tags stopped matching would report zero
  // modules; main() refuses that rather than passing on an empty list.
  return [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]);
}

// An element stub that accepts anything. Reads of well-known scalar
// properties return a plausible empty value (so `el.value.trim()` and
// `el.textContent === ''` behave); every other read returns another stub;
// every write is accepted; calling it returns a stub. `then` is undefined
// so a stub handed to Promise.resolve/Promise.all is a plain value and not
// a thenable that never settles. `overrides` wins over every rule below:
// the Proxy's `set` trap accepts writes and DROPS them, so a real API
// (document.fonts) cannot be assigned onto a stub after the fact -- it
// has to be built in.
function stubEl(overrides) {
  const el = new Proxy(function () {}, {
    get(_target, key) {
      if (overrides && Object.prototype.hasOwnProperty.call(overrides, key)) {
        return overrides[key];
      }
      if (key === 'then') return undefined;
      if (key === Symbol.toPrimitive) return () => '';
      if (key === 'classList') {
        return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
      }
      if (key === 'style' || key === 'dataset') {
        return new Proxy({}, { get: () => '', set: () => true });
      }
      if (key === 'children' || key === 'childNodes' || key === 'options') return [];
      if (key === 'querySelectorAll') return () => [];
      if (key === 'getAttribute') return () => null;
      if (key === 'getBoundingClientRect') {
        return () => ({ width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 });
      }
      if (key === 'contains' || key === 'matches') return () => false;
      if (key === 'hidden' || key === 'disabled' || key === 'checked') return false;
      if (key === 'value' || key === 'textContent' || key === 'id' ||
          key === 'className' || key === 'innerHTML') return '';
      if (key === 'offsetWidth' || key === 'offsetHeight' ||
          key === 'scrollWidth' || key === 'scrollHeight') return 0;
      return stubEl();
    },
    set() { return true; },
    apply() { return stubEl(); },
  });
  return el;
}

function makeWindow() {
  // sigbar.js calls `document.fonts.ready.then(fit)` unguarded, and
  // fleetbar.js hands the same promise to Promise.all. A plain stub would
  // make `.then` undefined and the page would THROW here for a line that
  // is correct in WebView2, so the stub carries a real, settled thenable
  // at that one address. Extend the stub for a real API; never bend the
  // page to fit the harness.
  const document = stubEl({
    fonts: { ready: Promise.resolve(), addEventListener() {} },
  });
  const window = {
    document,
    location: { search: '', href: 'file:///index.html', hash: '', pathname: '/index.html' },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    setTimeout, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: clearTimeout,
    matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
    getComputedStyle: () => new Proxy({}, { get: () => '' }),
    innerWidth: 1000, innerHeight: 700, devicePixelRatio: 1, screenX: 0, screenY: 0,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    navigator: { clipboard: { writeText: () => Promise.resolve() }, userAgent: 'node' },
    console, Promise, JSON, Math, Date, Object, Array, Number, String, RegExp,
    Error, TypeError, RangeError, isFinite, isNaN, parseInt, parseFloat, Boolean,
    Symbol, Map, Set, WeakMap, Intl, encodeURIComponent, decodeURIComponent,
    CustomEvent: class { constructor(type, opts) { this.type = type; this.detail = opts && opts.detail; } },
    Event: class { constructor(type) { this.type = type; } },
    KeyboardEvent: class {}, MouseEvent: class {}, HTMLElement: class {}, Node: class {},
    performance: { now: () => 0 },
    screen: { availLeft: 0, availTop: 0, availWidth: 1000, availHeight: 700 },
    // Absent, as it is before pywebview injects it: every module waits for
    // `pywebviewready` rather than assuming the bridge, and a module that
    // touched `pywebview.api` at top level would throw here as it would in
    // the real window before injection.
    pywebview: undefined,
  };
  window.window = window;
  window.self = window;
  window.globalThis = window;
  return window;
}

function loadPage(webDir, page) {
  const html = fs.readFileSync(path.join(webDir, page), 'utf8');
  const scripts = scriptsOf(html);
  if (scripts.length === 0) {
    console.log(`THROW ${page} -> no <script src> tags matched; the gate would be checking air`);
    return 1;
  }
  const window = makeWindow();
  const context = vm.createContext(window);
  let bad = 0;
  for (const name of scripts) {
    const source = fs.readFileSync(path.join(webDir, name), 'utf8');
    try {
      vm.runInContext(source, context, { filename: name });
      console.log(`ok    ${name}`);
    } catch (err) {
      bad += 1;
      const message = String(err && err.message !== undefined ? err.message : err);
      console.log(`THROW ${name} -> ${message.split('\n')[0]}`);
    }
  }
  return bad;
}

function main(argv) {
  const webDir = argv[0] || path.join(__dirname, '..', 'wingman', 'web');
  const pages = argv.length > 1 ? argv.slice(1) : PAGES;
  let bad = 0;
  for (const page of pages) {
    console.log(`== ${page}`);
    bad += loadPage(webDir, page);
  }
  if (bad) {
    console.log(`FAIL ${bad} module(s) threw at top level; every registration below the throw never ran`);
  } else {
    console.log('PASS every page module loaded');
  }
  // Exit explicitly: the modules have armed setTimeout(fit, 500) and other
  // timers that would otherwise keep the process alive and run stubbed
  // code this gate makes no claims about.
  process.exit(bad ? 1 : 0);
}

main(process.argv.slice(2));
