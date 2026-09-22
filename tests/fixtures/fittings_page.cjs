
const hostAssert = require('node:assert/strict');
const fs = require('node:fs');
const readline = require('node:readline');
const vm = require('node:vm');
const {performance} = require('node:perf_hooks');
const {isNativeError} = require('node:util/types');

function freezeJson(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) freezeJson(child);
  return value;
}

if (process.argv.length !== 5) {
  process.stderr.write(
    'Usage: fittings_page.cjs <markup-json> <fittings-js> <panel-js>\n');
  process.exit(2);
}
const startupPage = freezeJson(
  JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
const startupPageJson = JSON.stringify(startupPage);
const fittingsSource = fs.readFileSync(process.argv[3], 'utf8');
const panelSource = fs.readFileSync(process.argv[4], 'utf8');

async function scenarioProgram() {
  const startupJson = globalThis.__wingmanStartupPageJson;
  const payloadJson = globalThis.__wingmanPayloadJson;
  const scenario = globalThis.__wingmanScenario;
  const fittingsScript = globalThis.__wingmanFittingsSource;
  const panelScript = globalThis.__wingmanPanelSource;
  const encode = globalThis.__wingmanTextEncoderAdapter;
  const searchParams = globalThis.__wingmanURLSearchParamsAdapter;
  const reportProtocolEvent = globalThis.__wingmanProtocolEvent;
  const unhandledRejections = globalThis.__wingmanUnhandledRejections;
  delete globalThis.__wingmanStartupPageJson;
  delete globalThis.__wingmanPayloadJson;
  delete globalThis.__wingmanScenario;
  delete globalThis.__wingmanFittingsSource;
  delete globalThis.__wingmanPanelSource;
  delete globalThis.__wingmanTextEncoderAdapter;
  delete globalThis.__wingmanURLSearchParamsAdapter;
  delete globalThis.__wingmanProtocolEvent;
  delete globalThis.__wingmanUnhandledRejections;

  class AssertionError extends Error {
    constructor(message) {
      super(message || 'Assertion failed');
      this.name = 'AssertionError';
    }
  }
  const render = value => {
    try { return JSON.stringify(value); } catch { return String(value); }
  };
  const deeplyEqual = (actual, expected) => {
    if (Object.is(actual, expected)) return true;
    if (!actual || !expected || typeof actual !== 'object'
        || typeof expected !== 'object') return false;
    if (Array.isArray(actual) !== Array.isArray(expected)) return false;
    const actualKeys = Object.keys(actual);
    const expectedKeys = Object.keys(expected);
    if (actualKeys.length !== expectedKeys.length) return false;
    return actualKeys.every((key, index) => key === expectedKeys[index]
      && deeplyEqual(actual[key], expected[key]));
  };
  const assert = {
    ok(value, message) {
      if (!value) throw new AssertionError(message || 'Expected value to be truthy');
    },
    equal(actual, expected, message) {
      if (!Object.is(actual, expected)) {
        throw new AssertionError(message
          || `Expected ${render(actual)} to equal ${render(expected)}`);
      }
    },
    notEqual(actual, expected, message) {
      if (Object.is(actual, expected)) {
        throw new AssertionError(message
          || `Expected ${render(actual)} not to equal ${render(expected)}`);
      }
    },
    deepEqual(actual, expected, message) {
      if (!deeplyEqual(actual, expected)) {
        throw new AssertionError(message
          || `Expected ${render(actual)} to deep-equal ${render(expected)}`);
      }
    },
    match(actual, pattern, message) {
      if (!pattern.test(String(actual))) {
        throw new AssertionError(message
          || `Expected ${render(actual)} to match ${String(pattern)}`);
      }
    },
    throws(callback, pattern, message) {
      let thrown;
      try { callback(); } catch (error) { thrown = error; }
      if (!thrown) throw new AssertionError(message || 'Expected function to throw');
      if (pattern && !pattern.test(String(thrown.message || thrown))) {
        throw new AssertionError(message
          || `Expected ${String(thrown.message || thrown)} to match ${String(pattern)}`);
      }
      return thrown;
    },
    fail(message) { throw new AssertionError(message); },
  };

  function fromHost(envelope) {
    if (typeof envelope !== 'string') {
      throw new TypeError('Host adapter returned a non-primitive envelope');
    }
    const response = JSON.parse(envelope);
    if (!response || response.ok !== true) {
      const errorTypes = {Error, EvalError, RangeError, ReferenceError,
        SyntaxError, TypeError, URIError};
      const ErrorType = errorTypes[response && response.errorName] || Error;
      throw new ErrorType(response && response.errorMessage || 'Host adapter failed');
    }
    return response.value;
  }
  function encoderInput(value) {
    return typeof value === 'symbol' ? value : String(value);
  }
  const encoders = new WeakSet();
  function encoder(instance) {
    if (!encoders.has(instance)) throw new TypeError('Illegal invocation');
  }
  class TextEncoder {
    constructor() { encoders.add(this); }
    get encoding() { encoder(this); return 'utf-8'; }
    encode(input = '') {
      encoder(this);
      const encoded = fromHost(encode('encode', encoderInput(input), 0));
      const result = new Uint8Array(encoded.bytes.length);
      for (let index = 0; index < encoded.bytes.length; index++) {
        result[index] = encoded.bytes[index];
      }
      return result;
    }
    encodeInto(input, destination) {
      encoder(this);
      if (!(destination instanceof Uint8Array)) {
        throw new TypeError('The destination must be a Uint8Array');
      }
      const encoded = fromHost(encode(
        'encodeInto', encoderInput(input), destination.length));
      for (let index = 0; index < encoded.written; index++) {
        destination[index] = encoded.bytes[index];
      }
      return {read: encoded.read, written: encoded.written};
    }
  }
  Object.defineProperty(TextEncoder.prototype, Symbol.toStringTag,
    {value: 'TextEncoder', configurable: true});

  const parameterStates = new WeakMap();
  function stateFor(instance) {
    if (!parameterStates.has(instance)) throw new TypeError('Illegal invocation');
    return parameterStates.get(instance);
  }
  function webString(value) {
    if (typeof value === 'symbol') {
      throw new TypeError('Cannot convert a Symbol value to a string');
    }
    return String(value);
  }
  function urlOperation(operation, serializedState, args) {
    const response = fromHost(searchParams(
      operation, serializedState, JSON.stringify(args)));
    if (!response || typeof response.state !== 'string') {
      throw new TypeError('Host URLSearchParams adapter returned invalid state');
    }
    return response;
  }
  function invoke(instance, operation, args) {
    const response = urlOperation(operation, stateFor(instance), args);
    parameterStates.set(instance, response.state);
    return response.result;
  }
  class URLSearchParams {
    constructor(init = '') {
      let operation = 'construct-string';
      let args;
      if (init instanceof URLSearchParams) {
        args = [stateFor(init)];
      } else if (typeof init === 'string') {
        args = [init];
      } else if (init !== null && init !== undefined
          && typeof init[Symbol.iterator] === 'function') {
        operation = 'construct-entries';
        const entries = [];
        for (const pair of init) {
          const values = Array.from(pair);
          if (values.length !== 2) {
            throw new TypeError(
              'Each query pair must be an iterable [name, value] tuple');
          }
          entries.push([webString(values[0]), webString(values[1])]);
        }
        args = [entries];
      } else if (init !== null && typeof init === 'object') {
        operation = 'construct-entries';
        const entries = [];
        for (const name of Object.keys(init)) {
          entries.push([webString(name), webString(init[name])]);
        }
        args = [entries];
      } else {
        args = [webString(init)];
      }
      const response = urlOperation(operation, '', args);
      parameterStates.set(this, response.state);
    }
    get size() { return invoke(this, 'size', []); }
    append(name, value) {
      invoke(this, 'append', [webString(name), webString(value)]);
    }
    delete(name, value) {
      const args = [webString(name)];
      if (arguments.length > 1) args.push(webString(value));
      invoke(this, 'delete', args);
    }
    get(name) { return invoke(this, 'get', [webString(name)]); }
    getAll(name) { return invoke(this, 'getAll', [webString(name)]); }
    has(name, value) {
      const args = [webString(name)];
      if (arguments.length > 1) args.push(webString(value));
      return invoke(this, 'has', args);
    }
    set(name, value) {
      invoke(this, 'set', [webString(name), webString(value)]);
    }
    sort() { invoke(this, 'sort', []); }
    toString() { return invoke(this, 'toString', []); }
    *entries() {
      for (let index = 0; ; index++) {
        const entries = invoke(this, 'entries', []);
        if (index >= entries.length) return;
        yield [entries[index][0], entries[index][1]];
      }
    }
    *keys() { for (const entry of this.entries()) yield entry[0]; }
    *values() { for (const entry of this.entries()) yield entry[1]; }
    forEach(callback, thisArg = undefined) {
      for (let index = 0; ; index++) {
        const entries = invoke(this, 'entries', []);
        if (index >= entries.length) return;
        callback.call(thisArg, entries[index][1], entries[index][0], this);
      }
    }
    [Symbol.iterator]() { return this.entries(); }
  }
  Object.defineProperty(URLSearchParams.prototype, Symbol.toStringTag,
    {value: 'URLSearchParams', configurable: true});
  globalThis.TextEncoder = TextEncoder;
  globalThis.URLSearchParams = URLSearchParams;

  const data = {page: JSON.parse(startupJson), ...(JSON.parse(payloadJson) || {})};
  const page = data.page;
  const stateMachineScenario = scenario.startsWith('state-');
  const interleavingScenario = scenario.startsWith('interleaving-');
  const outputLines = [];
  globalThis.console = {
    log: (...args) => outputLines.push(args.join(' ')),
    info: (...args) => outputLines.push(args.join(' ')),
    debug: (...args) => outputLines.push(args.join(' ')),
    warn: (...args) => outputLines.push(args.join(' ')),
    error: (...args) => { throw new Error(args.join(' ')); },
  };

// Only DOM mechanics live here. Fittings rendering, listeners, selection and
// phase changes all run from the unmodified production module below.
class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.attrs = {...attrs};
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
    this.hidden = 'hidden' in attrs;
    this.disabled = 'disabled' in attrs;
    this.className = attrs.class || '';
    this.id = attrs.id || '';
    this.type = attrs.type || '';
    this.value = '';
    this.style = {
      setProperty(name, value) { this[name] = value; },
      removeProperty(name) { delete this[name]; }
    };
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { this.className += ' ' + name; },
      remove: name => {
        this.className = this.className.split(/\s+/).filter(x => x !== name).join(' ');
      },
      toggle: (name, force) => {
        const present = force === undefined ? !this.classList.contains(name) : force;
        this.classList.remove(name);
        if (present) this.classList.add(name);
        return present;
      }
    };
  }
  set id(value) { this.attrs.id = String(value); }
  get id() { return this.attrs.id || ''; }
  appendChild(child) {
    if (child.parentNode) child.remove();
    this.children.push(child);
    child.parentNode = this;
    return child;
  }
  remove() {
    this.parentNode.children = this.parentNode.children.filter(x => x !== this);
    this.parentNode = null;
  }
  set textContent(value) {
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
    this.text = value;
  }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  contains(node) {
    return node === this || this.children.some(child => child.contains(node));
  }
  matches(selector) {
    return selector.split(',').some(part => {
      part = part.trim();
      const exclusions = [...part.matchAll(/:not\(([^)]+)\)/g)];
      if (exclusions.some(match => this.matches(match[1]))) return false;
      part = part.replace(/:not\([^)]+\)/g, '');
      const tag = part.match(/^[a-z]+/i);
      if (tag && tag[0].toUpperCase() !== this.tagName) return false;
      if (part.includes(':disabled') && !this.disabled) return false;
      if ([...part.matchAll(/\.([\w-]+)/g)].some(match =>
          !this.classList.contains(match[1]))) return false;
      return [...part.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)].every(match => {
        const value = match[1] === 'hidden' ? (this.hidden ? '' : null)
          : this.getAttribute(match[1]);
        return value !== null && (match[2] === undefined || value === match[2]);
      });
    });
  }
  querySelectorAll(selector) {
    const found = [];
    const walk = node => node.children.forEach(child => {
      if (child.matches(selector)) found.push(child);
      walk(child);
    });
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getBoundingClientRect() { return {height: 36, width: 600, top: 0, bottom: 36, left: 0, right: 600}; }
  getClientRects() {
    for (let node = this; node; node = node.parentNode) {
      if (node.hidden || node.style.display === 'none'
          || (node.classList.contains('route') && !node.classList.contains('active'))) {
        return [];
      }
    }
    return document.contains(this) ? [{}] : [];
  }
  focus() {
    if (!this.disabled && this.getClientRects().length
        && getComputedStyle(this).visibility === 'visible' && document.activeElement !== this) {
      document.activeElement = this;
      document.dispatchEvent({type: 'focusin', target: this});
    }
  }
  blur() { if (document.activeElement === this) document.activeElement = document.body; }
  select() { this.selectionStart = 0; this.selectionEnd = this.value.length; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  dispatchEvent(event) {
    event.target ||= this;
    event.currentTarget = this;
    (this.listeners[event.type] || []).forEach(callback => callback(event));
  }
  click() {
    if (!this.disabled) this.dispatchEvent({type: 'click'});
  }
}
function fromTree(tree) {
  const node = new Element(tree.tag, tree.attrs);
  tree.children.forEach(child => node.appendChild(fromTree(child)));
  return node;
}
const document = fromTree(page);
globalThis.document = document;
document.body = document.querySelector('body');
document.activeElement = document.body;
document.createElement = tag => new Element(tag);
document.getElementById = id => document.querySelectorAll('[id]').find(x => x.id === id) || null;
const getComputedStyle = node => {
  let visibility = 'visible';
  for (let current = node; current; current = current.parentNode) {
    if (current.style.visibility) { visibility = current.style.visibility; break; }
  }
  return {visibility};
};
const el = id => {
  const node = document.getElementById(id);
  assert.ok(node, 'missing real markup: ' + id);
  return node;
};
const route = el('route-fittings');
document.querySelectorAll('.route').forEach(node => node.classList.remove('active'));
route.classList.add('active');
const handlers = {};
const calls = [];
const pending = {};
let copyTicketSequence = 0;
function deferred(name, args) {
  let resolve;
  let reject;
  const promise = new Promise((accept, refuse) => { resolve = accept; reject = refuse; });
  const request = {args, promise, resolve, reject};
  (pending[name] ||= []).push(request);
  return promise;
}
function takePending(name) {
  const queue = pending[name] || [];
  assert.ok(queue.length, 'no pending ' + name + ' request');
  return queue.shift();
}
const fitA = {id: 'fit-1', name: 'Sabre tackle', ship_name: 'Sabre', ship_type_id: 22456,
  presence_count: 1, collection_ids: [], deployable: true, superseded_by: null};
const fitB = {id: 'fit-2', name: 'Flycatcher tackle', ship_name: 'Flycatcher', ship_type_id: 22464,
  presence_count: 1, collection_ids: [], deployable: true, superseded_by: null};
const state = {
  available: true, warnings: [], refreshing: false,
  collections: [
    {id: 'all', name: 'All fittings', count: 2},
    {id: 'doctrine', name: 'Doctrine', count: 2}
  ],
  ships: [],
  characters: [
    {character_id: 1, character_name: 'Pilot', status: 'enabled', fetched_utc: '2026-09-01', stale: false},
    {character_id: 2, character_name: 'Unavailable', status: 'disabled', fetched_utc: '', stale: false}
  ],
  rows: [fitA], total: 1, page: 1, page_size: 100
};
function workspace(label, overrides = {}) {
  const payload = {...state, ...overrides};
  payload.collections = (overrides.collections || state.collections).map(collection => ({
    ...collection,
    name: collection.id === 'all' ? label : collection.name
  }));
  return payload;
}
function detailFor(row, description) {
  return {id: row.id, name: row.name, description, ship_type_id: row.ship_type_id,
    items: [], aliases: [], presences: [], collection_ids: [], superseded_by: null};
}
function screenshotPayload() {
  const entries = [];
  for (let index = 1; index <= 21; index += 1) {
    entries.push({...fitA, id: 'screenshot-' + index, name: 'Screenshot fitting ' + index,
      presence_count: 0, is_unfiled: true});
  }
  return {
    kind: 'fittings-screenshot-v1', characters: [state.characters[0]],
    collections: state.collections, entries, details: {},
    mixed_preflight: {pairs: []}, copy_result: {results: []}
  };
}
const WM = {
  current_route: 'fittings', el: id => document.getElementById(id),
  route(name) {
    WM.current_route = name;
    if (name === 'fittings') route.classList.add('active');
    else route.classList.remove('active');
    document.dispatchEvent({type: 'wm:route', detail: name});
  },
  make(tag, cls, text) {
    const node = new Element(tag, {class: cls || ''});
    if (text !== undefined) node.textContent = text;
    return node;
  },
  handle(name, callback) { handlers[name] = callback; },
  send(name, ...args) {
    calls.push([name, ...args]);
    if (name === 'fittings_state') {
      return stateMachineScenario ? deferred(name, args) : Promise.resolve(state);
    }
    if (name === 'fittings_detail' &&
        (scenario === 'state-detail-sequence' || scenario === 'state-rejected-mutation')) {
      return deferred(name, args);
    }
    if (name === 'fittings_update_metadata' && scenario === 'state-rejected-mutation') {
      return Promise.resolve(false);
    }
    if (name === 'fittings_preflight_copy' && scenario === 'state-stale-preflight') {
      return deferred(name, args);
    }
    if (name === 'fittings_preflight_copy') {
      copyTicketSequence += 1;
      const ticketId = scenario === 'state-ticket-progress'
          || scenario === 'state-stale-start-result'
        ? 'ticket-' + (copyTicketSequence === 1 ? 'a' : 'b') : 'ticket';
      return Promise.resolve({
        accepted: true, ticket_id: ticketId, write_count: 1, requires_resolution: false,
        counts: {ready: 1}, pairs: [{entry_id: 'fit-1', character_id: 1,
          fitting_name: 'Sabre tackle', character_name: 'Pilot', status: 'ready', chosen_name: 'Sabre tackle'}]
      });
    }
    if (name === 'fittings_start_copy' && (scenario === 'state-stale-start-result' || interleavingScenario)) {
      return deferred(name, args);
    }
    if (name === 'fittings_start_copy' || name === 'fittings_cancel_copy') return Promise.resolve(true);
    throw new Error('Unexpected bridge call: ' + name);
  },
  confirm() { return Promise.resolve(true); }
};
globalThis.getComputedStyle = getComputedStyle;
globalThis.window = {
  WM,
  getComputedStyle,
  addEventListener() {},
  setTimeout,
  clearTimeout,
  setImmediate,
  setInterval,
  clearInterval,
  TextEncoder,
  URLSearchParams,
  Promise,
  Math,
  Date,
};
globalThis.window.window = globalThis.window;
globalThis.WM = WM;

function loadSource(source, filename) {
  (0, eval)(source + '\n//# sourceURL=' + filename);
}
const loadOrder = [];
if (scenario === 'dialog-description' || scenario.startsWith('interleaving-')) {
  loadSource(panelScript, 'panel.js');
  loadOrder.push('panel.js');
}
loadSource(fittingsScript, 'fittings.js');
loadOrder.push('fittings.js');
assert.deepEqual(loadOrder,
  scenario === 'dialog-description' || scenario.startsWith('interleaving-')
    ? ['panel.js', 'fittings.js'] : ['fittings.js'],
  'production script load order changed');

function mutateIsolation() {
  const marker = '__wingmanFittingsRequestProbe';
  for (const [name, intrinsic] of Object.entries(
    {Promise, Math, Date, TextEncoder, URLSearchParams}
  )) {
    const targets = [
      ['constructor', intrinsic],
      ['prototype', intrinsic.prototype],
      ['constructor-base', Object.getPrototypeOf(intrinsic)],
      ['instance-base', intrinsic.prototype
        && Object.getPrototypeOf(intrinsic.prototype)],
    ];
    for (const [level, target] of targets) {
      if (target) target[marker] = name + '.' + level;
    }
  }
  const returnedMarker = '__wingmanFittingsReturnedPrototypeProbe';
  const params = new URLSearchParams('a=1&a=2');
  const iterator = params.entries();
  for (const value of [
    new TextEncoder().encode('probe'),
    params.getAll('a'),
    iterator,
    iterator.next().value,
  ]) {
    for (let target = Object.getPrototypeOf(value); target;
        target = Object.getPrototypeOf(target)) {
      target[returnedMarker] = 'mutated';
    }
  }
  let errorRealm;
  try {
    new TextEncoder().encode(Symbol('host-realm-probe'));
  } catch (error) {
    errorRealm = error.constructor.constructor('return globalThis')();
  }
  assert.ok(errorRealm, 'TextEncoder Symbol did not fail');
  errorRealm.__wingmanFittingsHostRealmProbe = 'mutated';
  document.__wingmanFittingsDocumentProbe = 'mutated';
  const timeoutId = setTimeout(() => {}, 60000);
  const intervalId = setInterval(() => {}, 60000);
  try {
    assert.equal(Number.isInteger(timeoutId), true,
      'timeout ID exposed a host object');
    assert.equal(Number.isInteger(intervalId), true,
      'interval ID exposed a host object');
    assert.equal(timeoutId, 1, 'first timeout ID was not request-local');
    assert.equal(intervalId, 1, 'first interval ID was not request-local');
    const timerMarker = '__wingmanFittingsTimerTokenProbe';
    for (const value of [timeoutId, intervalId]) {
      const wrapper = Object(value);
      wrapper[timerMarker] = 'wrapper';
      for (let target = Object.getPrototypeOf(wrapper); target;
          target = Object.getPrototypeOf(target)) {
        target[timerMarker] = 'prototype';
      }
    }
  } finally {
    clearTimeout(timeoutId);
    clearInterval(intervalId);
  }
}

function assertPristineIsolation() {
  const marker = '__wingmanFittingsRequestProbe';
  for (const [name, intrinsic] of Object.entries(
    {Promise, Math, Date, TextEncoder, URLSearchParams}
  )) {
    const targets = [
      ['constructor', intrinsic],
      ['prototype', intrinsic.prototype],
      ['constructor-base', Object.getPrototypeOf(intrinsic)],
      ['instance-base', intrinsic.prototype
        && Object.getPrototypeOf(intrinsic.prototype)],
    ];
    for (const [level, target] of targets) {
      if (target && Object.prototype.hasOwnProperty.call(target, marker)) {
        throw new Error('request intrinsic leaked: ' + name + '.' + level);
      }
    }
  }
  assert.equal('__wingmanTextEncoderAdapter' in globalThis, false,
    'TextEncoder host adapter remained globally reachable');
  assert.equal('__wingmanURLSearchParamsAdapter' in globalThis, false,
    'URLSearchParams host adapter remained globally reachable');
  assert.equal(Object.prototype.hasOwnProperty.call(
    document, '__wingmanFittingsDocumentProbe'), false,
  'request DOM leaked between requests');
  assert.equal(data.screenshot, null,
    'request screenshot payload leaked into an ordinary scenario');

  const timerMarker = '__wingmanFittingsTimerTokenProbe';
  const timeoutIds = [setTimeout(() => {}, 60000), setTimeout(() => {}, 60000)];
  const intervalIds = [setInterval(() => {}, 60000), setInterval(() => {}, 60000)];
  try {
    for (const value of [...timeoutIds, ...intervalIds]) {
      const wrapper = Object(value);
      for (let target = wrapper; target; target = Object.getPrototypeOf(target)) {
        if (Object.prototype.hasOwnProperty.call(target, timerMarker)) {
          throw new Error('timer token prototype leaked between requests');
        }
      }
      assert.equal(Number.isInteger(value), true,
        'timer ID exposed a host object');
    }
    assert.deepEqual(timeoutIds, [1, 2],
      'timeout IDs were not numeric and request-local');
    assert.deepEqual(intervalIds, [1, 2],
      'interval IDs were not numeric and request-local');
  } finally {
    timeoutIds.forEach(clearTimeout);
    intervalIds.forEach(clearInterval);
  }

  let adapterError;
  let errorRealm;
  try {
    new TextEncoder().encode(Symbol('host-realm-probe'));
  } catch (error) {
    adapterError = error;
    errorRealm = error.constructor.constructor('return globalThis')();
  }
  assert.ok(errorRealm, 'TextEncoder Symbol did not fail');
  assert.equal(adapterError instanceof TypeError, true,
    'TextEncoder host error was not reconstructed as TypeError');
  assert.equal(Boolean(errorRealm.__wingmanFittingsHostRealmProbe), false,
    'host realm marker leaked between requests');
  assert.equal(errorRealm, globalThis,
    'TextEncoder error escaped the request VM');

  const returnedMarker = '__wingmanFittingsReturnedPrototypeProbe';
  const isolationParams = new URLSearchParams('a=1&a=2');
  const isolationIterator = isolationParams.entries();
  const returned = [
    new TextEncoder().encode('probe'),
    isolationParams.getAll('a'),
    isolationIterator,
    isolationIterator.next().value,
  ];
  assert.equal(returned[0] instanceof Uint8Array, true,
    'TextEncoder result was not VM-owned');
  assert.equal(Array.isArray(returned[1]), true,
    'URLSearchParams array was not VM-owned');
  assert.equal(Array.isArray(returned[3]), true,
    'URLSearchParams entry was not VM-owned');
  assert.equal(isolationIterator[Symbol.iterator](), isolationIterator,
    'URLSearchParams iterator was not VM-owned');
  for (const value of returned) {
    for (let target = Object.getPrototypeOf(value); target;
        target = Object.getPrototypeOf(target)) {
      if (Object.prototype.hasOwnProperty.call(target, returnedMarker)) {
        throw new Error('returned value prototype leaked between requests');
      }
    }
  }
  const encoder = new TextEncoder();
  assert.equal(encoder.encoding, 'utf-8');
  assert.equal(Array.from(encoder.encode('Aé𐐀')).join(','),
    '65,195,169,240,144,144,128');
  const destination = new Uint8Array(2);
  assert.deepEqual(encoder.encodeInto('éA', destination), {read: 1, written: 2});
  assert.equal(Array.from(destination).join(','), '195,169');
  const params = new URLSearchParams('?a=1&a=2&space=hello+world');
  assert.equal(params.get('a'), '1');
  assert.deepEqual(params.getAll('a'), ['1', '2']);
  assert.equal(params.get('space'), 'hello world');
  assert.equal(params.has('a', '2'), true);
  params.delete('a', '1');
  params.set('a', '3');
  params.append('b', 'two words');
  params.sort();
  const serialized = 'a=3&b=two+words&space=hello+world';
  assert.equal(params.size, 3);
  assert.equal(params.toString(), serialized);
  assert.equal(new URLSearchParams(params).toString(), serialized);
  assert.deepEqual(Array.from(params.keys()), ['a', 'b', 'space']);
  assert.deepEqual(Array.from(params.values()), ['3', 'two words', 'hello world']);
  const visited = [];
  params.forEach((value, name, owner) => {
    assert.equal(owner, params, 'URLSearchParams owner changed');
    visited.push(name + '=' + value);
  });
  assert.equal(visited.join('&'), 'a=3&b=two words&space=hello world');
}

if (data.isolation_probe === 'mutate') mutateIsolation();
if (data.isolation_probe === 'pristine') assertPristineIsolation();
if (!scenario.startsWith('interleaving-screenshot-')) {
  assert.equal(data.screenshot, null,
    'ordinary scenario received a screenshot payload');
}

const protocolProbe = data.protocol_probe;
if (protocolProbe === 'vm-throw') {
  function protocolVmThrow() { throw new Error('protocol VM throw'); }
  protocolVmThrow();
}
if (protocolProbe === 'vm-reject') {
  function protocolVmReject() {
    Promise.reject(new Error('protocol VM rejection'));
  }
  protocolVmReject();
  await new Promise(resolve => setTimeout(resolve, 0));
  if (unhandledRejections.length) throw unhandledRejections[0];
  assert.fail('protocol VM rejection was not captured');
}
if (protocolProbe && protocolProbe.startsWith('pending-timer-')) {
  const events = [];
  const event = name => {
    events.push(name);
    reportProtocolEvent(name);
  };
  const activeInterval = setInterval(() => {
    event('active-interval');
    clearInterval(activeInterval);
  }, 0);
  await new Promise(resolve => setTimeout(() => {
    event('active-control');
    resolve();
  }, 0));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(events, ['active-interval', 'active-control'],
    'request interval must run before its same-delay control');
  setTimeout(() => event('leaked-timeout'), 0);
  setInterval(() => event('leaked-interval'), 0);
  if (protocolProbe === 'pending-timer-assertion-exit') {
    throw new Error('protocol cleanup probe failure');
  }
  throw new AssertionError('request left a live timer');
}

function key(name, shift = false, handled = false) {
  const event = {type: 'keydown', key: name, shiftKey: shift, defaultPrevented: handled,
    preventDefault() { this.defaultPrevented = true; }};
  document.dispatchEvent(event);
  return event;
}
function tick(node) { node.checked = true; node.dispatchEvent({type: 'change'}); }
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
async function enterWith(payload) {
  document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
  const request = takePending('fittings_state');
  request.resolve(payload);
  await flush();
}
function selectedCheckbox() {
  const checkbox = el('fittings-list').querySelector('input');
  assert.ok(checkbox, 'rendered fitting has a selection checkbox');
  return checkbox;
}
async function beginCopy() {
  tick(selectedCheckbox());
  const invoker = el('fittings-copy-selected');
  invoker.focus();
  invoker.click();
  const target = el('fittings-copy-body').querySelector('input');
  tick(target);
  el('fittings-copy-review').click();
  await flush();
  el('fittings-copy-start').click();
  await flush();
}
async function runStateMachineScenario() {
  if (scenario === 'state-route-lifecycle') {
    document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
    const departed = takePending('fittings_state');
    WM.current_route = 'skills';
    route.classList.remove('active');
    el('route-skills').classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'skills'});
    departed.resolve(workspace('Departed response'));
    await flush();
    assert.equal(el('fittings-collection-name').textContent, '',
      'a response resolving after route leave cannot repaint the departed route');
    WM.current_route = 'fittings';
    el('route-skills').classList.remove('active');
    route.classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
    const current = takePending('fittings_state');
    current.resolve(workspace('Current response'));
    await flush();
    assert.equal(el('fittings-collection-name').textContent, 'Current response');
    assert.equal(calls.filter(call => call[0] === 'fittings_state').length, 2,
      'reentry requests fresh state');
    return;
  }

  const initial = scenario === 'state-detail-sequence'
    ? workspace('Two fittings', {rows: [fitA, fitB], total: 2})
    : scenario === 'state-stale-preflight' || scenario === 'state-stale-progress'
        || scenario === 'state-ticket-progress' || scenario === 'state-stale-start-result'
      ? workspace('Two targets', {characters: [
          state.characters[0],
          {character_id: 2, character_name: 'Second Pilot', status: 'enabled',
            fetched_utc: '2026-09-01', stale: false}
        ]})
      : workspace('Initial response');
  await enterWith(initial);
  if (scenario === 'state-request-sequence') {
    handlers.onFittingsChanged();
    handlers.onFittingsChanged();
    const older = takePending('fittings_state');
    const newer = takePending('fittings_state');
    newer.resolve(workspace('Newest response'));
    await flush();
    assert.equal(el('fittings-collection-name').textContent, 'Newest response');
    older.resolve(workspace('Older response'));
    await flush();
    assert.equal(el('fittings-collection-name').textContent, 'Newest response',
      'an older state response cannot overwrite the newest response');
    return;
  }

  if (scenario === 'state-selection-scope') {
    tick(selectedCheckbox());
    assert.equal(el('fittings-copy-selected').disabled, false);
    el('fittings-collections').querySelectorAll('button')[1].click();
    assert.equal(el('fittings-copy-selected').disabled, true,
      'collection change clears selection before its request resolves');
    assert.equal(calls.filter(call => call[0] === 'fittings_state').at(-1)[1].collection_id,
      'doctrine');
    el('fittings-copy-selected').click();
    assert.equal(calls.some(call => call[0] === 'fittings_preflight_copy'), false,
      'cleared collection selection cannot reach preflight');
    takePending('fittings_state').resolve(workspace('Scoped response', {
      rows: [fitA], total: 2, page: 1, page_size: 1
    }));
    await flush();

    tick(selectedCheckbox());
    el('fittings-page-next').click();
    assert.equal(el('fittings-copy-selected').disabled, true,
      'page change clears selection before its request resolves');
    el('fittings-copy-selected').click();
    assert.equal(calls.some(call => call[0] === 'fittings_preflight_copy'), false,
      'cleared page selection cannot reach preflight');
    assert.equal(calls.filter(call => call[0] === 'fittings_state').at(-1)[1].page, 2);
    takePending('fittings_state').resolve(workspace('Second page', {
      rows: [fitB], total: 2, page: 2, page_size: 1
    }));
    await flush();

    tick(selectedCheckbox());
    el('fittings-search').value = 'needle';
    el('fittings-search').dispatchEvent({type: 'input'});
    assert.equal(el('fittings-copy-selected').disabled, true,
      'search clears selection before its debounced request');
    el('fittings-copy-selected').click();
    await wait(250);
    assert.equal(calls.filter(call => call[0] === 'fittings_state').at(-1)[1].search,
      'needle');
    assert.equal(calls.some(call => call[0] === 'fittings_preflight_copy'), false,
      'scope, page, and search transitions never send stale IDs');
    takePending('fittings_state').resolve(workspace('Search response', {
      rows: [], total: 0, page: 1, page_size: 1
    }));
    await flush();
    return;
  }

  if (scenario === 'state-detail-sequence') {
    const toggles = el('fittings-list').querySelectorAll('.fit-row-toggle');
    toggles[0].click();
    const detailA = takePending('fittings_detail');
    el('fittings-list').querySelectorAll('.fit-row-toggle')[1].click();
    const detailB = takePending('fittings_detail');
    detailA.resolve(detailFor(fitA, 'Late detail A'));
    await flush();
    assert.equal(el('fittings-list').querySelector('.fit-description'), null,
      'late detail for the collapsed fitting is ignored');
    detailB.resolve(detailFor(fitB, 'Current detail B'));
    await flush();
    assert.equal(el('fittings-list').querySelector('.fit-description').textContent,
      'Current detail B');
    assert.equal(el('fittings-list').querySelectorAll('.fit-row.open').length, 1);
    return;
  }

  if (scenario === 'state-rejected-mutation') {
    tick(selectedCheckbox());
    el('fittings-list').querySelector('.fit-row-toggle').click();
    takePending('fittings_detail').resolve(detailFor(fitA, 'Persisted detail'));
    await flush();
    const save = el('fittings-list').querySelectorAll('button')
      .find(button => button.textContent === 'Save');
    assert.ok(save, 'expanded real module renders its Save mutation control');
    el('fittings-list').querySelector('.fit-metadata-disclosure').open = true;
    const name = el('fit-name-fit-1');
    name.value = 'Edited name';
    name.dispatchEvent({type: 'input'});
    save.click();
    await flush();
    assert.equal((pending.fittings_state || []).length, 1,
      'rejected mutation follows the existing state requery path');
    assert.equal(el('fittings-copy-selected').disabled, false,
      'rejection does not optimistically clear selection');
    assert.equal(el('fittings-list').querySelectorAll('.fit-row.open').length, 1,
      'rejection does not optimistically collapse detail');
    assert.equal(el('fittings-list').querySelector('.fit-description').textContent,
      'Persisted detail');
    takePending('fittings_state').resolve(workspace('Requeried response'));
    await flush();
    assert.equal(el('fittings-collection-name').textContent, 'Requeried response');
    assert.equal(el('fittings-copy-selected').disabled, false);
    takePending('fittings_detail').resolve(detailFor(fitA, 'Requeried detail'));
    await flush();
    assert.equal(el('fittings-list').querySelector('.fit-description').textContent,
      'Requeried detail');
    return;
  }

  if (scenario === 'state-screenshot-progress') {
    const fixture = screenshotPayload();
    fixture.copy_stage = 'progress';
    fixture.copy_progress_completed = 1;
    fixture.copy_result = {operation_id: 'screenshot-copy', status: 'complete', write_count: 1,
      results: [{entry_id: 'screenshot-1', fitting_name: 'Screenshot fitting 1',
        character_id: 1, character_name: 'Pilot', status: 'success', attempted: true}]};
    const before = calls.length;
    handlers.onFittingsScreenshotState(fixture);
    assert.equal(el('fittings-list').querySelectorAll('.fit-row').length, 21,
      'the bounded screenshot fixture is active');
    assert.equal(el('fittings-copy-title').textContent, 'Copying fittings');
    assert.equal(el('fittings-copy-review').hidden, true);
    assert.equal(el('fittings-copy-start').hidden, true);
    assert.equal(el('fittings-copy-cancel').hidden, false);
    assert.equal(el('fittings-copy-close').disabled, true);
    assert.equal(el('fittings-copy-summary').textContent,
      '1 of 1 fitting/character check complete');
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'unrelated'});
    assert.equal(el('fittings-copy-title').textContent, 'Copying fittings');
    el('fittings-copy-cancel').click();
    fixture.copy_stage = 'results';
    handlers.onFittingsScreenshotState(fixture);
    assert.equal(el('fittings-copy-title').textContent, 'Copy results');
    assert.equal(el('fittings-copy-body').querySelector('.fit-copy-pair-name').textContent,
      'Screenshot fitting 1 (Sabre)');
    handlers.onFittingsScreenshotState({kind: 'fittings-screenshot-v1', clear: true});
    assert.equal(el('fittings-copy-overlay').hidden, true);
    assert.equal(calls.length, before, 'presentation and cleanup never reach a writer');
    return;
  }

  if (scenario === 'state-stale-preflight') {
    tick(selectedCheckbox());
    const invoker = el('fittings-copy-selected');
    invoker.click();
    const firstTargets = el('fittings-copy-body').querySelectorAll('input');
    tick(firstTargets[0]);
    el('fittings-copy-review').click();
    const first = takePending('fittings_preflight_copy');
    assert.deepEqual(first.args[1], [1]);
    el('fittings-copy-close').click();

    invoker.click();
    const secondTargets = el('fittings-copy-body').querySelectorAll('input');
    tick(secondTargets[1]);
    el('fittings-copy-review').click();
    const second = takePending('fittings_preflight_copy');
    assert.deepEqual(second.args[1], [2]);

    first.resolve({accepted: true, ticket_id: 'ticket-a', write_count: 1,
      requires_resolution: false, counts: {ready: 1}, pairs: [{
        entry_id: 'fit-1', character_id: 1, fitting_name: 'Stale fitting A',
        character_name: 'Pilot', status: 'ready', chosen_name: 'Stale fitting A'
      }]});
    await flush();
    assert.equal(el('fittings-copy-review').hidden, false,
      'stale reply cannot move the reopened dialog out of targets phase');
    assert.equal(el('fittings-copy-start').hidden, true);
    assert.equal(el('fittings-copy-summary').textContent, 'Choose target characters.');
    assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Second Pilot');
    assert.equal(el('fittings-copy-body').querySelector('.fit-copy-pair-name'), null,
      'the stale pair is not rendered in the current targets phase');

    second.resolve({accepted: true, ticket_id: 'ticket-b', write_count: 1,
      requires_resolution: false, counts: {ready: 1}, pairs: [{
        entry_id: 'fit-1', character_id: 2, fitting_name: 'Current fitting B',
        character_name: 'Second Pilot', status: 'ready', chosen_name: 'Current fitting B'
      }]});
    await flush();
    assert.equal(el('fittings-copy-review').hidden, true);
    assert.equal(el('fittings-copy-start').hidden, false,
      'only the current dialog reply enters preflight');
    assert.match(el('fittings-copy-summary').textContent, /^1 addition planned/);
    assert.equal(el('fittings-copy-body').querySelector('.fit-copy-pair-name').textContent,
      'Current fitting B (Sabre)');
    el('fittings-copy-start').click();
    await flush();
    const starts = calls.filter(call => call[0] === 'fittings_start_copy');
    assert.equal(starts.length, 1);
    assert.equal(starts[0][1], 'ticket-b', 'the stale ticket is never used');
    return;
  }

  if (scenario === 'state-ticket-progress') {
    await beginCopy();
    assert.equal(calls.filter(call => call[0] === 'fittings_start_copy')[0][1],
      'ticket-a');
    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-a',
      operation_id: 'copy-a', completed: 1, total: 1, result: {status: 'success'}});
    const cancellations = calls.filter(call => call[0] === 'fittings_cancel_copy').length;
    WM.current_route = 'skills';
    route.classList.remove('active');
    el('route-skills').classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'skills'});
    assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length,
      cancellations + 1, 'route leave cancels copy A');
    assert.deepEqual(calls.filter(call => call[0] === 'fittings_cancel_copy').pop(),
      ['fittings_cancel_copy', 'ticket-a'], 'the cancel names the ticket it stops');

    WM.current_route = 'fittings';
    el('route-skills').classList.remove('active');
    route.classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
    takePending('fittings_state').resolve(workspace('Reentered response', {
      characters: initial.characters
    }));
    await flush();
    await beginCopy();
    const starts = calls.filter(call => call[0] === 'fittings_start_copy');
    assert.equal(starts[1][1], 'ticket-b');
    const cancelB = el('fittings-copy-cancel');
    cancelB.focus();

    function assertCopyBActive(eventName) {
      assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot',
        eventName + ' cannot replace copy B');
      assert.equal(el('fittings-copy-summary').textContent,
        '0 of 1 fitting/character check complete');
      assert.equal(el('fittings-copy-selected').textContent, 'Copy selected (1)',
        eventName + ' cannot clear copy B selection');
      assert.equal(el('fittings-copy-cancel').hidden, false);
      assert.equal(document.activeElement, cancelB,
        eventName + ' cannot redirect focus from copy B');
    }

    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-a',
      operation_id: 'copy-a', completed: 1, total: 1, result: {status: 'success'}});
    assertCopyBActive('late copy A progress');
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket-a',
      operation_id: 'copy-a', completed: 1, total: 1, result: {
        operation_id: 'copy-a', status: 'complete', write_count: 1, results: [{
          fitting_name: 'Copy A result', character_name: 'Pilot', status: 'success'
        }]
      }});
    assertCopyBActive('late copy A completion');

    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket-b',
      operation_id: 'copy-b', completed: 1, total: 1, result: {status: 'success'}});
    assert.equal(el('fittings-copy-summary').textContent,
      '1 of 1 fitting/character check complete');
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket-b',
      operation_id: 'copy-b', completed: 1, total: 1, result: {
        operation_id: 'copy-b', status: 'complete', write_count: 1, results: [{
          fitting_name: 'Copy B result', character_name: 'Pilot', status: 'success'
        }]
      }});
    assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
    assert.equal(el('fittings-copy-body').querySelector('.fit-copy-pair-name').textContent,
      'Copy B result', 'matching copy B completion renders normally');
    return;
  }

  if (scenario === 'state-stale-start-result') {
    await beginCopy();
    const startA = takePending('fittings_start_copy');
    assert.deepEqual(startA.args, ['ticket-a']);
    WM.current_route = 'skills';
    route.classList.remove('active');
    el('route-skills').classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'skills'});

    WM.current_route = 'fittings';
    el('route-skills').classList.remove('active');
    route.classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
    takePending('fittings_state').resolve(workspace('Reentered response', {
      characters: initial.characters
    }));
    await flush();
    tick(selectedCheckbox());
    el('fittings-copy-selected').click();
    const targetsB = el('fittings-copy-body').querySelectorAll('input');
    const targetB = targetsB[1];
    tick(targetB);
    targetB.focus();

    startA.resolve(false);
    await flush();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(unhandledRejections.length, 0,
      'stale false start result cannot render a cleared preflight');
    assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Second Pilot');
    assert.equal(el('fittings-copy-review').hidden, false,
      'dialog B remains in targets phase');
    assert.equal(el('fittings-copy-start').hidden, true);
    assert.equal(el('fittings-copy-summary').textContent, 'Choose target characters.');
    assert.equal(document.contains(targetB), true);
    assert.equal(targetB.checked, true);
    assert.equal(document.activeElement, targetB);
    return;
  }

  if (scenario === 'state-stale-progress') {
    await beginCopy();
    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket',
      operation_id: 'copy-a', completed: 1, total: 1, result: {status: 'success'}});
    assert.equal(el('fittings-copy-summary').textContent,
      '1 of 1 fitting/character check complete');
    const cancellations = calls.filter(call => call[0] === 'fittings_cancel_copy').length;
    WM.current_route = 'skills';
    route.classList.remove('active');
    el('route-skills').classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'skills'});
    assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length,
      cancellations + 1, 'route leave cancels copy A');
    assert.equal(el('fittings-copy-overlay').hidden, true,
      'route leave force-closes copy A');

    WM.current_route = 'fittings';
    el('route-skills').classList.remove('active');
    route.classList.add('active');
    document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
    takePending('fittings_state').resolve(workspace('Reentered response', {
      characters: initial.characters
    }));
    await flush();
    tick(selectedCheckbox());
    el('fittings-copy-selected').click();
    const targetsB = el('fittings-copy-body').querySelectorAll('input');
    const targetB = targetsB[1];
    tick(targetB);
    targetB.focus();
    assert.equal(targetsB[0].checked, false);
    assert.equal(document.activeElement, targetB);

    function assertTargetsDialogB(eventName) {
      assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Second Pilot',
        eventName + ' cannot turn dialog B into copy A results');
      assert.equal(el('fittings-copy-review').hidden, false,
        eventName + ' leaves dialog B in targets phase');
      assert.equal(el('fittings-copy-start').hidden, true);
      assert.equal(el('fittings-copy-summary').textContent,
        'Choose target characters.', 'copy A summary is not rendered');
      assert.equal(el('fittings-copy-body').querySelector('.fit-copy-result'), null,
        'copy A result is not rendered');
      assert.equal(document.contains(targetB), true,
        eventName + ' does not replace dialog B controls');
      assert.equal(targetsB[0].checked, false);
      assert.equal(targetB.checked, true, 'dialog B target selection remains present');
      assert.equal(document.activeElement, targetB,
        eventName + ' does not redirect focus from dialog B');
      assert.equal(el('fittings-copy-selected').disabled, false,
        eventName + ' does not clear dialog B fitting selection');
    }

    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket',
      operation_id: 'copy-a', completed: 1, total: 1, result: {status: 'success'}});
    assertTargetsDialogB('late progress');
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
      completed: 1, total: 1, result: {
        operation_id: 'copy-a', status: 'complete', write_count: 1, results: [{
          fitting_name: 'Copy A result', character_name: 'Pilot', status: 'success'
        }]
      }});
    assertTargetsDialogB('late completion');
    return;
  }

  if (scenario === 'state-copy-lifecycle') {
    await beginCopy();
    assert.ok(calls.some(call => call[0] === 'fittings_preflight_copy'));
    assert.ok(calls.some(call => call[0] === 'fittings_start_copy'));
    handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket',
      completed: 1, total: 1, result: {status: 'success'}});
    assert.equal(el('fittings-copy-status').textContent, '1 of 1 fitting/character check complete · Copied');
    assert.equal(el('fittings-copy-close').disabled, true);
    key('Escape');
    el('fittings-copy-close').click();
    assert.equal(el('fittings-copy-overlay').hidden, false,
      'progress cannot be dismissed by Escape or Close');
    el('fittings-copy-cancel').click();
    assert.ok(calls.some(call => call[0] === 'fittings_cancel_copy'));
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
      result: {operation_id: 'op-1', status: 'cancelled', write_count: 1,
        results: []}});
    assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
    assert.equal(el('fittings-copy-selected').disabled, true,
      'completion clears selection');
    assert.equal(el('fittings-copy-close').disabled, false,
      'completion restores the close guard');
    el('fittings-copy-close').click();

    await beginCopy();
    const cancellations = calls.filter(call => call[0] === 'fittings_cancel_copy').length;
    WM.current_route = 'skills';
    route.classList.remove('active');
    el('route-skills').classList.add('active');
    el('nav-skills').focus();
    document.dispatchEvent({type: 'wm:route', detail: 'skills'});
    assert.equal(el('fittings-copy-overlay').hidden, true);
    assert.equal(document.activeElement, el('nav-skills'),
      'route-leave cancellation does not steal focus');
    assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length,
      cancellations + 1, 'route leave cancels an active copy');
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
      result: {operation_id: 'late', status: 'success', write_count: 1, results: []}});
    assert.equal(el('fittings-copy-overlay').hidden, true,
      'late completion cannot reopen a copy workflow after route leave');
    assert.equal(el('fittings-copy-selected').disabled, true,
      'late completion cannot restore departed selection');
    assert.equal(document.activeElement, el('nav-skills'),
      'late completion cannot steal focus from the current route');
    return;
  }

  throw new Error('Unknown state-machine scenario: ' + scenario);
}
async function runInterleavingScenario() {
  document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
  await flush();
  tick(selectedCheckbox());
  el('fittings-copy-selected').focus();
  el('fittings-copy-selected').click();
  tick(el('fittings-copy-body').querySelector('input'));
  el('fittings-copy-review').click();
  await flush();
  el('fittings-copy-start').focus();
  el('fittings-copy-start').click();
  assert.equal(el('overlay').hidden, false, 'real panel confirmation opens for Start');
  if (scenario.startsWith('interleaving-screenshot-')) {
    const confirmationFocus = document.activeElement.id;
    const confirmationBody = el('dlg-body').textContent;
    assert.equal(confirmationFocus, 'dlg-ok');
    assert.deepEqual(calls.map(call => call[0]), ['fittings_state', 'fittings_preflight_copy']);
    handlers.onFittingsScreenshotState(data.screenshot.payload);
    const isProgress = data.screenshot.payload.copy_stage === 'progress';
    assert.equal(el('fittings-copy-overlay').hidden, false, 'fixture still enters presentation');
    assert.equal(el('fittings-copy-title').textContent, isProgress ? 'Copying fittings' : 'Copy results');
    assert.equal(document.activeElement.id, confirmationFocus,
      'screenshot presentation must not steal the real pending confirmation focus');
    // Execute the production guard too — visibility alone cannot prove exposure.
    assert.throws(() => (0, eval)(data.screenshot.verify), /Screenshot content did not settle/);
    assert.equal(el('overlay').hidden, false, 'capture verification never dismisses the question');
    assert.equal(el('dlg-title').textContent, 'Copy fittings');
    assert.equal(el('dlg-body').textContent, confirmationBody);
    assert.equal(document.activeElement.id, confirmationFocus);
    handlers.onFittingsScreenshotState({kind: 'fittings-screenshot-v1', clear: true});
    await flush();
    assert.equal(WM.current_route, 'main');
    assert.equal(el('fittings-copy-overlay').hidden, true);
    assert.equal(el('overlay').hidden, false, 'teardown leaves the unanswered question alone');
    assert.equal(document.activeElement.id, confirmationFocus);
    assert.deepEqual(calls.map(call => call[0]), ['fittings_state', 'fittings_preflight_copy'],
      'presentation, verification and teardown never submit or cancel a real copy');
    return;
  }
  el('dlg-ok').click();
  await flush();
  const start = takePending('fittings_start_copy');
  const copy = el('fittings-copy-dialog');
  const cancel = el('fittings-copy-cancel');
  assert.equal(document.activeElement.id, cancel.id);
  if (scenario.includes('complete')) {
    start.resolve(true);
    await flush();
    const first = WM.confirm('Synthetic notice', 'No action follows this answer.');
    const queued = scenario.includes('queued') ? WM.confirm('Queued notice', 'Still no action.') : null;
    assert.equal(el('overlay').hidden, false);
    handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
      result: {results: [], write_count: 0, status: 'cancelled'}});
    assert.equal(el('fittings-copy-title').textContent, 'Copy 1 fitting to Pilot');
    assert.equal(cancel.hidden, true, 'completion invalidated generic dialog return focus');
    assert.equal(document.activeElement.id, 'dlg-ok', 'completion leaves generic dialog in charge');
    assert.equal(key('Escape').defaultPrevented, true);
    assert.equal(await first, false);
    if (queued) {
      assert.equal(el('overlay').hidden, false, 'first dismissal keeps queued generic dialog in charge');
      assert.equal(document.activeElement.id, 'dlg-ok');
      key('Escape');
      assert.equal(await queued, false);
    }
    assert.equal(el('overlay').hidden, true);
    assert.equal(el('fittings-copy-overlay').hidden, false, 'same Escape must not dismiss copy results');
    assert.ok(copy.contains(document.activeElement), 'real panel dismissal must immediately return inside copy modal');
    assert.ok(!document.activeElement.disabled && document.activeElement.getClientRects().length);
    for (const reverse of [true, false]) {
      key('Tab', reverse);
      assert.ok(copy.contains(document.activeElement));
    }
    assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length, 0);
  } else {
    const didCancel = !scenario.endsWith('uncancelled');
    if (didCancel) cancel.click();
    const reply = scenario.includes('null') ? null : false;
    start.resolve(reply);
    await flush();
    assert.equal(el('fittings-copy-status').textContent, 'The copy could not start.');
    assert.equal(el('fittings-copy-start').hidden, false);
    assert.equal(el('fittings-copy-body').getAttribute('tabindex'), '0');
    if (scenario.endsWith('root-tab') || scenario.endsWith('descendant-tab')) {
      const fallback = scenario.endsWith('root-tab') ? copy : el('fittings-copy-title');
      fallback.setAttribute('tabindex', '-1');
      fallback.focus();
      assert.equal(key('Tab', true).defaultPrevented, true, 'non-tab stop must not leak reverse Tab');
      assert.equal(document.activeElement.id, 'fittings-copy-start');
    } else {
      assert.equal(document.activeElement.id, 'fittings-copy-body', 'rollback must reconcile hidden Cancel or fallback-root focus');
      assert.equal(key('Tab', true).defaultPrevented, true);
      assert.equal(document.activeElement.id, 'fittings-copy-start');
    }
    key('Tab');
    assert.equal(document.activeElement.id, 'fittings-copy-body');
    assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length, didCancel ? 1 : 0);
    assert.equal(calls.filter(call => call[0] === 'fittings_start_copy').length, 1);
    key('Escape');
    assert.equal(el('fittings-copy-overlay').hidden, true);
    assert.equal(document.activeElement.id, 'fittings-copy-selected');
  }
}
await (async () => {
  if (scenario === 'dialog-description') {
    const dialog = el('dialog'), body = el('dlg-body');
    const invoker = el('fittings-refresh-all'); invoker.focus();
    function description(expected, focus) {
      const ids = (dialog.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      assert.ok(ids.length, 'generic dialog must describe its consequence/scope body');
      assert.ok(ids.map(el).includes(body), 'description references the existing message node');
      assert.equal(body.textContent, expected, 'messages are neither parsed nor reformatted');
      assert.ok(dialog.contains(body) && body.getClientRects().length,
        'the complete message remains independently present and readable');
      assert.notEqual(body.getAttribute('aria-hidden'), 'true');
      assert.equal(body.children.length, 0, 'message markup remains literal text');
      assert.equal(dialog.getAttribute('aria-labelledby'), 'dlg-title', 'title remains the name');
      assert.equal(document.activeElement.id, focus, 'existing initial focus is unchanged');
    }
    const consequence = 'Delete “Map & <notes>”?\n\nThis cannot be undone.\nThe source stays open.';
    const confirm = WM.confirm('Remove companion', consequence, {destructive: true});
    const warning = 'Could not read the file:\n  C:\\clips\\<recording>.mp4\n\nRetry after closing it.';
    handlers.onDialog({kind: 'warning', title: 'File unavailable', body: warning, request_id: null});
    description(consequence, 'dlg-cancel');
    el('dlg-cancel').click(); assert.equal(await confirm, false);
    description(warning, 'dlg-ok');
    el('dlg-ok').click();
    assert.equal(document.activeElement, invoker, 'queue completion restores the invoker');
    const prompt = WM.prompt('Rename collection', 'A new name for this collection.', 'Draft');
    description('A new name for this collection.', 'dlg-input');
    assert.equal(el('dlg-input').value, 'Draft');
    el('dlg-cancel').click(); assert.equal(await prompt, null);
    const choose = WM.choose('Copy preview geometry', 'Copy saved size and position to “Pilot”.',
      [{label: 'Current previews', options: [{value: 'source-1', label: 'Mapper'}]}], 'Copy');
    description('Copy saved size and position to “Pilot”.', 'dlg-select');
    el('dlg-cancel').click(); assert.equal(await choose, null);
    for (const kind of ['info', 'error']) {
      handlers.onDialog({kind, title: 'Message', body: '', request_id: null});
      description('', 'dlg-ok'); // a reused dialog must not retain prior consequences
      el('dlg-ok').click();
    }
    assert.equal(document.activeElement, invoker);
    assert.deepEqual(calls, [], 'local dialogs and worker notices do not send answers to unrelated requests');
    return;
  }
  if (interleavingScenario) {
    await runInterleavingScenario();
    return;
  }
  if (stateMachineScenario) {
    await runStateMachineScenario();
    return;
  }
  document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
  await flush();
  const checkbox = el('fittings-list').querySelector('input');
  if (scenario === 'checkbox-name') {
    assert.equal(checkbox.getAttribute('aria-label'), 'Select Sabre tackle — Sabre, row 1 on this page');
    return;
  }
  tick(checkbox);
  const invoker = el('fittings-copy-selected');
  invoker.focus();
  invoker.click();
  const overlay = el('fittings-copy-overlay');
  const close = el('fittings-copy-close');
  const target = el('fittings-copy-body').querySelector('input');
  const review = el('fittings-copy-review');
  assert.equal(overlay.hidden, false, 'Copy selected opens overlay');
  assert.equal(document.activeElement, close, 'opening moves focus into dialog');

  if (scenario === 'tab-wrap') {
    // Review is initially disabled; unavailable target and Start/Cancel are excluded.
    close.focus();
    assert.equal(key('Tab').defaultPrevented, true);
    assert.equal(document.activeElement, target, 'last wraps to first enabled target');
    assert.equal(key('Tab', true).defaultPrevented, true);
    assert.equal(document.activeElement, close, 'first wraps to last');
    tick(target);
    review.focus();
    key('Tab');
    assert.equal(document.activeElement, target, 'newly enabled review is now last');
    target.focus();
    key('Tab', true);
    assert.equal(document.activeElement, review);
    close.focus();
    assert.equal(key('Tab').defaultPrevented, false, 'ordinary interior Tab stays native');
  } else if (scenario === 'tab-outside') {
    invoker.focus();
    assert.equal(document.activeElement, target, 'outside focus is reconciled before another key');
    assert.equal(key('Tab', true).defaultPrevented, true);
    assert.equal(document.activeElement, close);
  } else if (scenario === 'hidden-controls') {
    target.parentNode.style.display = 'none';
    close.focus();
    key('Tab');
    assert.equal(document.activeElement, close, 'hidden ancestor excludes target');
    close.disabled = true;
    assert.equal(key('Tab').defaultPrevented, true, 'empty focus list cannot leak Tab');
  } else if (scenario === 'close' || scenario === 'escape') {
    if (scenario === 'close') close.click(); else key('Escape');
    assert.equal(overlay.hidden, true);
    assert.equal(document.activeElement, invoker, 'dismissal restores the saved invoker');
  } else if (scenario.startsWith('fallback-')) {
    if (scenario === 'fallback-detached') {
      const replacement = new Element('button', {id: invoker.id});
      invoker.parentNode.appendChild(replacement);
      invoker.remove();
    } else if (scenario === 'fallback-hidden') invoker.parentNode.style.display = 'none';
    else if (scenario === 'fallback-invisible') invoker.style.visibility = 'hidden';
    else {
      // Real completion clears selection and disables the original invoker.
      tick(target);
      review.click();
      await flush();
      el('fittings-copy-start').click();
      await flush();
      handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
        result: {results: [], write_count: 0, status: 'cancelled'}});
    }
    // Fallback must skip both a disabled first control and a hidden ancestor.
    el('fittings-manage-characters').disabled = true;
    el('fittings-refresh-all').parentNode.style.display = 'none';
    close.click();
    assert.equal(overlay.hidden, true);
    assert.equal(document.activeElement, el('fittings-collections').querySelector('button'),
      'fallback finds an available control on active Fittings route');
  } else if (scenario === 'shared-dialog') {
    el('overlay').hidden = false;
    el('dlg-ok').focus();
    key('Tab');
    assert.equal(document.activeElement, el('dlg-ok'), 'shared dialog keeps keyboard ownership');
    // panel.js handles Escape in capture phase, hiding itself before this listener.
    el('overlay').hidden = true;
    key('Escape', false, true);
    assert.equal(overlay.hidden, false, 'shared confirmation Escape does not close copy overlay');
  } else if (['progress-focus', 'progress-tab', 'cancel-focus', 'cancel-tab',
              'progress-shared-dialog', 'review-scroller', 'results-scroller'].includes(scenario)) {
    tick(target);
    review.click();
    await flush();
    const body = el('fittings-copy-body');
    const dialog = el('fittings-copy-dialog');
    const start = el('fittings-copy-start');
    const cancel = el('fittings-copy-cancel');
    function assertScroller() {
      assert.equal(body.getAttribute('tabindex'), '0', 'copy content must be a keyboard stop');
      assert.equal(body.getAttribute('role'), 'region');
      assert.equal(body.getAttribute('aria-labelledby'), 'fittings-copy-title');
      assert.ok(el(body.getAttribute('aria-labelledby')).textContent, 'region has a current accessible name');
      const last = scenario === 'review-scroller' ? start : close;
      last.focus();
      assert.equal(key('Tab').defaultPrevented, true);
      assert.equal(document.activeElement, body, 'forward wrap admits scrollable content');
      assert.equal(key('Tab', true).defaultPrevented, true);
      assert.equal(document.activeElement, last, 'reverse wrap leaves content for last control');
    }
    if (scenario === 'review-scroller') {
      assertScroller();
      key('Escape');
      assert.equal(document.activeElement, invoker);
      return;
    }
    start.focus();
    start.click();
    await flush();
    if (scenario === 'progress-focus') {
      assert.equal(document.activeElement, cancel, 'progress entry focuses its only enabled control');
      const note = el('fittings-copy-cancel-note');
      assert.equal(note.hidden, false, 'cancellation consequences appear before clicking Cancel');
      assert.equal(cancel.getAttribute('aria-describedby'), note.id);
      assert.equal(el('fittings-copy-body').contains(note), false, 'progress replacement does not own the note');
      handlers.onFittingsProgress({kind: 'copy', phase: 'progress', ticket_id: 'ticket',
        completed: 1, total: 2, result: {status: 'success'}});
      assert.ok(note.getClientRects().length, 'consequences stay visible after progress updates');
      handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
        result: {results: [], write_count: 1, status: 'complete'}});
      assert.equal(note.hidden, true, 'completed results replace active-copy guidance');
    } else if (scenario === 'progress-tab') {
      cancel.focus();
      for (const reverse of [false, true]) {
        assert.equal(key('Tab', reverse).defaultPrevented, true, 'progress must contain Tab');
        assert.equal(document.activeElement, cancel);
      }
      key('Escape');
      assert.equal(overlay.hidden, false);
      assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length, 0);
    } else if (scenario === 'cancel-focus' || scenario === 'cancel-tab') {
      cancel.focus();
      cancel.click();
      assert.equal(cancel.disabled, true);
      assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length, 1);
      if (scenario === 'cancel-focus') {
        assert.equal(dialog.getAttribute('tabindex'), '-1', 'empty modal needs a programmatic focus target');
        assert.equal(document.activeElement, dialog, 'Cancel must not leave focus on a disabled control');
      } else {
        invoker.focus();
        for (const reverse of [false, true]) {
          assert.equal(key('Tab', reverse).defaultPrevented, true, 'cancellation wait contains Tab');
          assert.equal(document.activeElement, dialog, 'zero-control fallback recovers modal focus');
        }
      }
      key('Escape');
      assert.equal(overlay.hidden, false, 'cancellation wait cannot close the operation');
      assert.equal(calls.filter(call => call[0] === 'fittings_cancel_copy').length, 1);
    } else if (scenario === 'progress-shared-dialog') {
      el('overlay').hidden = false;
      el('dlg-ok').focus();
      assert.equal(key('Tab').defaultPrevented, false, 'generic overlay has priority during progress');
      assert.equal(document.activeElement, el('dlg-ok'));
      cancel.click();
      assert.equal(document.activeElement, el('dlg-ok'), 'Cancel fallback must not steal topmost focus');
      handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
        result: {results: [], write_count: 0, status: 'cancelled'}});
      assert.equal(document.activeElement, el('dlg-ok'), 'completion must not steal topmost focus');
      el('overlay').hidden = true;
      key('Escape', false, true);
      assert.equal(overlay.hidden, false, 'already-handled Escape must not dismiss copy results');
    } else {
      handlers.onFittingsProgress({kind: 'copy', phase: 'complete', ticket_id: 'ticket',
        result: {results: [], write_count: 0, status: 'cancelled'}});
      assert.equal(document.activeElement, close, 'completion replaces hidden Cancel focus');
      assertScroller();
      key('Escape');
      assert.equal(overlay.hidden, true);
      assert.equal(document.activeElement, el('fittings-manage-characters'));
    }
  } else if (scenario === 'progress' || scenario === 'route-leave') {
    tick(target);
    review.click();
    await flush();
    const start = el('fittings-copy-start');
    start.focus();
    key('Tab');
    assert.equal(document.activeElement.id, 'fittings-copy-body', 'preflight includes its content scroller first');
    el('fittings-copy-body').focus();
    key('Tab', true);
    assert.equal(document.activeElement, start, 'preflight recalculates last control');
    start.click();
    await flush();
    assert.equal(close.disabled, true, 'Close stays disabled during progress');
    key('Escape');
    close.click();
    assert.equal(overlay.hidden, false, 'progress cannot be dismissed');
    if (scenario === 'route-leave') {
      WM.current_route = 'skills';
      route.classList.remove('active');
      el('route-skills').classList.add('active');
      el('nav-skills').focus();
      document.dispatchEvent({type: 'wm:route', detail: 'skills'});
      assert.equal(overlay.hidden, true, 'route leave force-closes progress');
      assert.equal(document.activeElement, el('nav-skills'), 'cleanup does not steal new route focus');
      assert.ok(calls.some(call => call[0] === 'fittings_cancel_copy'));
      WM.current_route = 'fittings';
      route.classList.add('active');
      document.dispatchEvent({type: 'wm:route', detail: 'fittings'});
      await flush();
      tick(el('fittings-list').querySelector('input'));
      invoker.focus();
      invoker.click();
      assert.equal(close.disabled, false, 'reentry resets progress guard');
      close.click();
      assert.equal(document.activeElement, invoker);
    }
  } else throw new Error('Unknown scenario: ' + scenario);
})();
const output = 'PASS ' + scenario;
outputLines.push(output);
assert.equal(outputLines.at(-1), output, 'request PASS line must be terminal');
return output;
}

function adapterEnvelope(operation) {
  try {
    return JSON.stringify({ok: true, value: operation()});
  } catch (error) {
    let errorName = 'Error';
    let errorMessage = 'Host adapter failed';
    try {
      if (error && typeof error.name === 'string') errorName = error.name;
    } catch {}
    try {
      if (error && typeof error.message === 'string') errorMessage = error.message;
      else errorMessage = String(error);
    } catch {}
    try {
      return JSON.stringify({ok: false, errorName, errorMessage});
    } catch {
      return '{"ok":false,"errorName":"Error","errorMessage":"Host adapter failed"}';
    }
  }
}

async function runScenario(request, cleanupProbe = null) {
  const timers = new Map();
  const intervals = new Map();
  const allNativeTimers = new Set();
  const allNativeIntervals = new Set();
  let nextTimer = 1;
  let nextInterval = 1;
  const requestSetTimeout = (callback, delay, ...args) => {
    const token = nextTimer++;
    const handle = setTimeout(() => {
      timers.delete(token);
      callback(...args);
    }, delay);
    timers.set(token, handle);
    allNativeTimers.add(handle);
    return token;
  };
  const requestClearTimeout = token => {
    const handle = timers.get(token);
    if (handle !== undefined) clearTimeout(handle);
    timers.delete(token);
  };
  const requestSetImmediate = (callback, ...args) =>
    requestSetTimeout(callback, 0, ...args);
  const requestSetInterval = (callback, delay, ...args) => {
    const token = nextInterval++;
    const handle = setInterval(callback, delay, ...args);
    intervals.set(token, handle);
    allNativeIntervals.add(handle);
    return token;
  };
  const requestClearInterval = token => {
    const handle = intervals.get(token);
    if (handle !== undefined) clearInterval(handle);
    intervals.delete(token);
  };
  const hostTextEncoder = new globalThis.TextEncoder();
  const textEncoderAdapter = (operation, input, capacity) => adapterEnvelope(() => {
    if (operation === 'encode') {
      return {bytes: Array.from(hostTextEncoder.encode(input))};
    }
    if (operation === 'encodeInto') {
      const destination = new Uint8Array(capacity);
      const result = hostTextEncoder.encodeInto(input, destination);
      return {read: result.read, written: result.written,
        bytes: Array.from(destination.subarray(0, result.written))};
    }
    throw new Error('Unknown TextEncoder adapter operation: ' + operation);
  });
  const urlSearchParamsAdapter = (operation, serializedState, argumentsJson) =>
    adapterEnvelope(() => {
      const args = JSON.parse(argumentsJson);
      let params;
      if (operation === 'construct-string') {
        params = new globalThis.URLSearchParams(args[0]);
      } else if (operation === 'construct-entries') {
        params = new globalThis.URLSearchParams(args[0]);
      } else {
        params = new globalThis.URLSearchParams(serializedState);
      }
      let result = null;
      if (operation === 'append') params.append(args[0], args[1]);
      else if (operation === 'delete') {
        if (args.length > 1) params.delete(args[0], args[1]);
        else params.delete(args[0]);
      } else if (operation === 'get') result = params.get(args[0]);
      else if (operation === 'getAll') result = params.getAll(args[0]);
      else if (operation === 'has') {
        result = args.length > 1
          ? params.has(args[0], args[1]) : params.has(args[0]);
      } else if (operation === 'set') params.set(args[0], args[1]);
      else if (operation === 'sort') params.sort();
      else if (operation === 'size') result = params.size;
      else if (operation === 'toString') result = params.toString();
      else if (operation === 'entries') result = Array.from(params.entries());
      else if (!['construct-string', 'construct-entries'].includes(operation)) {
        throw new Error('Unknown URLSearchParams adapter operation: ' + operation);
      }
      return {state: params.toString(), result};
    });
  const protocolEvent = name => {
    hostAssert.equal(typeof name, 'string', 'protocol event must be primitive');
    if (cleanupProbe) cleanupProbe.events.push(name);
  };
  const runtime = vm.createContext({
    __wingmanStartupPageJson: startupPageJson,
    __wingmanPayloadJson: JSON.stringify(request.payload || {}),
    __wingmanScenario: request.scenario,
    __wingmanFittingsSource: fittingsSource,
    __wingmanPanelSource: panelSource,
    __wingmanTextEncoderAdapter: textEncoderAdapter,
    __wingmanURLSearchParamsAdapter: urlSearchParamsAdapter,
    __wingmanProtocolEvent: protocolEvent,
    setTimeout: requestSetTimeout,
    clearTimeout: requestClearTimeout,
    setImmediate: requestSetImmediate,
    setInterval: requestSetInterval,
    clearInterval: requestClearInterval,
  });
  const unhandledRejections = vm.runInContext('[]', runtime);
  runtime.__wingmanUnhandledRejections = unhandledRejections;
  const captureRejection = reason => unhandledRejections.push(reason);
  process.on('unhandledRejection', captureRejection);
  try {
    const output = await vm.runInContext(
      '(' + scenarioProgram.toString() + ')()',
      runtime,
      {filename: 'fittings_scenario_worker.cjs'},
    );
    hostAssert.equal(timers.size, 0, 'request left a live timer');
    hostAssert.equal(intervals.size, 0, 'request left a live interval');
    await new Promise(resolve => setImmediate(resolve));
    if (unhandledRejections.length) throw unhandledRejections[0];
    hostAssert.equal(timers.size, 0, 'request left a live timer');
    hostAssert.equal(intervals.size, 0, 'request left a live interval');
    hostAssert.equal(typeof output, 'string', 'request did not return a PASS label');
    return output;
  } finally {
    process.removeListener('unhandledRejection', captureRejection);
    if (cleanupProbe) {
      cleanupProbe.pendingTimers = timers.size;
      cleanupProbe.pendingIntervals = intervals.size;
      cleanupProbe.timers = timers;
      cleanupProbe.intervals = intervals;
      const nativeIntervals = [...allNativeIntervals];
      cleanupProbe.cancelNativeIntervals = () => {
        for (const handle of nativeIntervals) clearInterval(handle);
      };
    }
    for (const handle of allNativeTimers) clearTimeout(handle);
    for (const handle of allNativeIntervals) clearInterval(handle);
    timers.clear();
    intervals.clear();
    allNativeTimers.clear();
    allNativeIntervals.clear();
  }
}

async function runCleanupProbe(request) {
  const probe = {events: []};
  let output;
  let failure;
  try {
    output = await runScenario(request, probe);
  } catch (error) {
    failure = error;
  }
  try {
    if (failure && !probe.timers) throw failure;
    hostAssert.equal(probe.pendingTimers, 1,
      'cleanup must start with one pending tracked timer');
    hostAssert.equal(probe.pendingIntervals, 1,
      'cleanup must start with one pending tracked interval');
    await new Promise(resolve => setTimeout(() => {
      probe.events.push('cleanup-control');
      resolve();
    }, 0));
    await new Promise(resolve => setImmediate(resolve));
    hostAssert.deepEqual(probe.events,
      ['active-interval', 'active-control', 'cleanup-control'],
      'pending request callbacks must be cancelled before the same-delay control');
    hostAssert.equal(probe.timers.size, 0,
      'request timer tracking must be cleared');
    hostAssert.equal(probe.intervals.size, 0,
      'request interval tracking must be cleared');
    if (failure) throw failure;
    return output;
  } finally {
    if (probe.cancelNativeIntervals) probe.cancelNativeIntervals();
  }
}

function failureFields(error) {
  return {
    ok: false,
    error: isNativeError(error) ? error.message : String(error),
    stack: isNativeError(error) ? String(error.stack || '') : '',
  };
}

async function serveRequest(request) {
  const started = performance.now();
  const listenerSentinel = () => {};
  process.on('unhandledRejection', listenerSentinel);
  try {
    const listenerBaseline = process.listeners('unhandledRejection');
    let fields;
    try {
      const cleanupProbe = request.payload?.protocol_probe?.startsWith(
        'pending-timer-');
      const output = await (cleanupProbe
        ? runCleanupProbe(request) : runScenario(request));
      fields = {ok: true, output, error: '', stack: ''};
    } catch (error) {
      fields = failureFields(error);
    }
    try {
      hostAssert.deepEqual(process.listeners('unhandledRejection'), listenerBaseline,
        'unhandledRejection listener baseline changed');
    } catch (error) {
      fields = failureFields(error);
    }
    return {
      id: request.id,
      scenario: request.scenario,
      duration_ms: performance.now() - started,
      ...fields,
    };
  } finally {
    process.removeListener('unhandledRejection', listenerSentinel);
  }
}

async function serveWorker() {
  const rl = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
  for await (const line of rl) {
    const request = JSON.parse(line);
    const reply = await serveRequest(request);
    process.stdout.write(JSON.stringify(reply) + '\n');
  }
}

serveWorker().catch(error => {
  process.stderr.write(
    (isNativeError(error) ? String(error.stack || error.message) : String(error))
    + '\n');
  process.exitCode = 1;
});
