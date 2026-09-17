#!/usr/bin/env node
'use strict';

// Execute the real theme card in settings.js with the DOM/bridge boundaries
// replaced. Covers the picker contract that no lexical guard can see: the
// confirm gate on destructive preset switches, the receipt afterwards, the
// listbox keyboard/AT contract, and the fallback error copy.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../wingman/web/settings.js'), 'utf8');
const tests = [];
function test(name, run) { tests.push({name, run}); }
function turn() { return new Promise(resolve => setImmediate(resolve)); }

let uid = 0;
class Element {
  constructor(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.id = '';
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.className = '';
    this.hidden = false;
    this.listeners = {};
    this.style = {setProperty: (name, value) => { this.attrs['style:' + name] = value; }};
    // Real textContent semantics: writing replaces the children, reading
    // aggregates them. renderPicker's rebuilds depend on the write half.
    this._text = '';
    Object.defineProperty(this, 'textContent', {
      get: () => this.children.length
        ? this.children.map(child => child.textContent).join('')
        : this._text,
      set: value => { this._text = String(value); this.children = []; }
    });
  }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  removeChild(child) {
    const i = this.children.indexOf(child);
    if (i !== -1) { this.children.splice(i, 1); }
    child.parentNode = null;
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name); }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() {
    page.activeElement = this;
    if (page.doc) { page.doc.activeElement = this; }
  }
  contains(node) {
    for (let n = node; n; n = n.parentNode) { if (n === this) { return true; } }
    return false;
  }
  matches(selector) {
    return selector.split(',').every(part => {
      part = part.trim();
      return part.split(/(?=[.#])/).every(token => {
        if (token[0] === '.') { return this.className.split(/\s+/).includes(token.slice(1)); }
        if (token[0] === '#') { return this.id === token.slice(1); }
        return this.tagName === token.toUpperCase();
      });
    });
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const found = [];
    (function walk(node) {
      node.children.forEach(child => {
        if (child.matches(selector)) { found.push(child); }
        walk(child);
      });
    }(this));
    return found;
  }
  addEventListener(name, listener) { (this.listeners[name] = this.listeners[name] || []).push(listener); }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.preventDefault = event.preventDefault || function () {};
    (this.listeners[event.type] || []).forEach(listener => listener.call(this, event));
    // The menu handlers live on the list, the Escape handler on document;
    // both only work if keydown bubbles the way a real DOM bubbles it.
    if (this.parentNode) { this.parentNode.dispatchEvent(event); }
  }
}

const page = {};

function payload(extra) {
  return Object.assign({
    presets: [
      {id: 'wingman-dark', name: 'Wingman Dark'},
      {id: 'taco-bell', name: 'Taco Bell'},
      {id: 'zoolander', name: 'Zoolander'}
    ],
    // Same derivation contract as api._theme_payload: brand, danger, warn,
    // ok from the preset's own role table. Values here are inert hexes.
    preset_strips: {
      'wingman-dark': ['#7040ff', '#e04040', '#d4a017', '#40a040'],
      'taco-bell': ['#ff1f8d', '#ec4e57', '#ffd900', '#71c53e'],
      zoolander: ['#3366ff', '#cc3333', '#cccc33', '#33cc33']
    },
    preset: 'wingman-dark',
    families: {},
    effective: {},
    swatches: [
      {name: 'Midnight Blue', hex: '#0a0a1f', families: ['surface']},
      {name: 'Hot Magenta', hex: '#ff1f8d', families: ['surface', 'accent']}
    ],
    legal: {accent: ['#ff1f8d']},
    family_labels: {accent: 'Accent'},
    family_descriptions: {accent: 'The one call-to-action colour.'}
  }, extra || {});
}

function boot(theme) {
  const ids = ['theme-composer', 'theme-preset', 'btn-theme-customise', 'msg-theme'];
  const elements = {};
  ids.forEach(id => {
    const el = new Element('div');
    el.id = id;
    el.hidden = id === 'theme-composer' || id === 'msg-theme';
    elements[id] = el;
  });
  elements['btn-theme-customise'].tagName = 'BUTTON';

  const document = new Element('#document');
  document.querySelector = () => null;
  document.querySelectorAll = () => [];
  document.createElement = tag => new Element(tag);
  document.activeElement = new Element('body');
  page.activeElement = document;
  page.doc = document;
  const themeEvents = [];
  document.addEventListener('wm:theme', event => themeEvents.push(event.detail));

  const confirms = [];
  const calls = [];
  // The card's own roots are always returned; any other id is a stub the
  // real code creates on demand and expects to disappear once removed from
  // the document (renderReset's btn-theme-reset lifecycle), so a detached
  // stub reads back as null exactly like getElementById would.
  const ROOT_IDS = new Set(ids);
  const WM = {
    el: id => {
      if (ROOT_IDS.has(id)) { return elements[id]; }
      if (elements[id]) { return elements[id].parentNode ? elements[id] : null; }
      const made = new Element('div');
      made.id = id;
      document.appendChild(made);
      elements[id] = made;
      return made;
    },
    make: (tag, cls, text) => {
      const node = new Element(tag);
      if (cls) { node.className = cls; }
      if (text !== undefined && text !== null) { node.textContent = text; }
      return node;
    },
    confirm: (title, body, opts) => {
      confirms.push({title, body, opts});
      return new Promise(done => { confirms[confirms.length - 1].resolve = done; });
    },
    handle: () => {},
    setEnabled: () => {},
    send: (method, ...args) => {
      let resolve;
      const promise = new Promise(done => { resolve = done; });
      calls.push({method, args, resolve});
      return promise;
    }
  };
  page.WM = WM;
  page.calls = calls;
  page.confirms = confirms;
  page.elements = elements;
  page.themeEvents = themeEvents;
  page.document = document;
  page.msg = () => elements['msg-theme'];
  page.presetControl = () => elements['theme-preset'].children[0];

  vm.runInNewContext(source, {window: {WM}, WM, document, Promise}, {
    filename: 'wingman/web/settings.js'
  });

  WM.theme = theme === undefined ? payload() : theme;
  document.dispatchEvent({type: 'wm:theme', detail: WM.theme});
  return page;
}

function triggerOf(control) { return control.children[0]; }
function menuOf(control) { return control.querySelector('.theme-menu'); }
function optionsOf(control) { return menuOf(control).querySelectorAll('button'); }
function click(el) { el.dispatchEvent({type: 'click'}); }
function key(el, k) { el.dispatchEvent({type: 'keydown', key: k}); }
function familyControls(pageObj) { return pageObj.elements['theme-composer'].querySelectorAll('.theme-select'); }
// Sections outside the theme card also use the bridge at load; select the
// theme card's own calls by method so their traffic is invisible to these
// assertions.
function callTo(pageObj, method) {
  return pageObj.calls.filter(call => call.method === method).pop() || null;
}

test('preset rows carry their derived identity strip and the selected state', () => {
  const pageObj = boot();
  const options = optionsOf(pageObj.presetControl());
  assert.equal(options.length, 3);
  const taco = options[1];
  assert.equal(taco.getAttribute('aria-selected'), 'false');
  const dots = taco.querySelectorAll('.dot');
  assert.equal(dots.length, 4, 'one dot per derived strip colour');
  assert.deepEqual(
    dots.map(d => d.attrs['style:--swatch']),
    payload().preset_strips['taco-bell'],
    'strip dots come from the payload, not a page-side copy');
  assert.equal(options[0].getAttribute('aria-selected'), 'true');
  assert.equal(
    triggerOf(pageObj.presetControl()).getAttribute('aria-labelledby'),
    'lab-theme-preset theme-value-preset');
});

test('switching presets with no picks sends straight through, no confirm', () => {
  const pageObj = boot();
  const trigger = triggerOf(pageObj.presetControl());
  key(trigger, 'ArrowDown'); // keyboard entry opens onto the selected row
  assert.equal(pageObj.presetControl().hasAttribute('open'), true);
  assert.equal(pageObj.activeElement, optionsOf(pageObj.presetControl())[0],
    'ArrowDown opens onto the selected option');
  click(optionsOf(pageObj.presetControl())[1]);
  assert.equal(pageObj.confirms.length, 0, 'nothing to destroy, nothing to confirm');
  const call = callTo(pageObj, 'theme_set_preset');
  assert.ok(call, 'preset write went out');
  assert.deepEqual(call.args, ['taco-bell']);
  call.resolve({applied: true, persisted: true, error: null});
  return turn().then(() => {
    assert.equal(pageObj.msg().hidden, true, 'no receipt when nothing was cleared');
  });
});

test('switching presets with family picks confirms first and receipts after', () => {
  const pageObj = boot(payload({families: {accent: '#ff1f8d'}}));
  click(triggerOf(pageObj.presetControl()));
  click(optionsOf(pageObj.presetControl())[1]); // Taco Bell
  assert.equal(callTo(pageObj, 'theme_set_preset'), null, 'no write before the user answers');
  const confirm = pageObj.confirms[0];
  assert.equal(confirm.opts.destructive, true);
  assert.ok(confirm.body.indexOf('Taco Bell') !== -1);
  assert.ok(confirm.body.indexOf('1 saved colour pick') !== -1, confirm.body);
  confirm.resolve(false); // decline
  return turn().then(() => {
    assert.equal(callTo(pageObj, 'theme_set_preset'), null, 'decline writes nothing');
    assert.equal(pageObj.presetControl().querySelector('button').textContent,
                 'Wingman Dark', 'trigger repaints on the old preset');
    click(triggerOf(pageObj.presetControl()));
    click(optionsOf(pageObj.presetControl())[1]);
    pageObj.confirms[1].resolve(true); // accept
    return turn();
  }).then(() => {
    const call = callTo(pageObj, 'theme_set_preset');
    assert.ok(call, 'accept writes');
    assert.deepEqual(call.args, ['taco-bell']);
    call.resolve({applied: true, persisted: true, error: null});
    return turn();
  }).then(() => {
    assert.ok(pageObj.msg().textContent.indexOf('Switched to Taco Bell') === 0,
              pageObj.msg().textContent);
    assert.ok(pageObj.msg().textContent.indexOf('1 colour pick cleared') !== -1);
  });
});

test('family listboxes expose the picked option and the theme-default state', () => {
  const pageObj = boot(payload({families: {accent: '#ff1f8d'}}));
  pageObj.elements['btn-theme-customise'].dispatchEvent({type: 'click'});
  const control = familyControls(pageObj)[0];
  const options = optionsOf(control);
  assert.equal(options.length, 2, 'theme default + the one legal swatch');
  assert.equal(options[0].getAttribute('aria-selected'), 'false');
  assert.equal(options[1].getAttribute('aria-selected'), 'true');
  assert.equal(
    triggerOf(control).getAttribute('aria-labelledby'),
    'theme-label-accent theme-value-accent');
  assert.equal(triggerOf(control).getAttribute('aria-expanded'), 'false');
});

test('the listbox keyboard contract: arrows move, Escape closes back to the trigger', () => {
  const pageObj = boot();
  pageObj.elements['btn-theme-customise'].dispatchEvent({type: 'click'});
  const control = familyControls(pageObj)[0];
  const trigger = triggerOf(control);
  key(trigger, 'ArrowDown');
  const options = optionsOf(control);
  assert.equal(pageObj.activeElement, options[0], 'opens on the selected (default) row');
  key(pageObj.activeElement, 'ArrowDown');
  assert.equal(pageObj.activeElement, options[1]);
  key(pageObj.activeElement, 'ArrowUp');
  key(pageObj.activeElement, 'ArrowUp');
  assert.equal(pageObj.activeElement, options[options.length - 1], 'wraps backwards');
  key(pageObj.activeElement, 'Home');
  assert.equal(pageObj.activeElement, options[0]);
  key(pageObj.activeElement, 'End');
  assert.equal(pageObj.activeElement, options[options.length - 1]);
  key(pageObj.activeElement, 'Escape');
  assert.equal(control.hasAttribute('open'), false, 'Escape closes the menu');
  assert.equal(trigger.getAttribute('aria-expanded'), 'false');
  assert.equal(pageObj.activeElement, trigger, 'focus returns to the trigger');
});

test('a validation refusal keeps its own message; a bare failure names restart', () => {
  const pageObj = boot();
  pageObj.elements['btn-theme-customise'].dispatchEvent({type: 'click'});
  const control = familyControls(pageObj)[0];
  click(triggerOf(control));
  click(optionsOf(control)[1]);
  callTo(pageObj, 'theme_set_family').resolve({applied: false, persisted: false, error: 'That colour is not offered for this family.'});
  return turn().then(() => {
    assert.equal(pageObj.msg().textContent, 'That colour is not offered for this family.');
    click(triggerOf(control));
    click(optionsOf(control)[1]);
    callTo(pageObj, 'theme_set_family').resolve(null); // bridge resolved without a verdict
    return turn();
  }).then(() => {
    assert.ok(pageObj.msg().textContent.indexOf('restart Wingman') !== -1,
              pageObj.msg().textContent);
  });
});

test('Customise carries the ellipsis; Hide does not', () => {
  const pageObj = boot();
  const btn = pageObj.elements['btn-theme-customise'];
  click(btn);
  assert.equal(btn.textContent, 'Hide colours');
  assert.equal(btn.getAttribute('aria-expanded'), 'true');
  click(btn);
  assert.equal(btn.textContent, 'Customise colours…');
  assert.equal(btn.getAttribute('aria-expanded'), 'false');
});

(async () => {
  let failed = 0;
  for (const {name, run} of tests) {
    try {
      await run();
      console.log('ok - ' + name);
    } catch (err) {
      failed += 1;
      console.error('FAIL - ' + name);
      console.error(err && err.stack || err);
    }
  }
  if (failed) { process.exitCode = 1; }
  console.log(failed ? failed + ' failing' : 'all ' + tests.length + ' passed');
})();
