// Real Settings owners + markup. Only the external bridge and DOM mechanics
// are doubled; generated shooter expressions are the system under test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const readline = require('node:readline');
const vm = require('node:vm');
const {performance} = require('node:perf_hooks');
const {isNativeError} = require('node:util/types');
const {DOM_FACTORY_SOURCE} = require('./screenshot_dom.cjs');

if (process.argv.length !== 4) {
  process.stderr.write('Usage: current_screenshot_pages.cjs <markup-json> <web-root>\n');
  process.exit(2);
}
const startupPageJson = fs.readFileSync(process.argv[2], 'utf8');
const web = process.argv[3];

async function runScenario(request, cleanupProbe = null) {
  const data = {...(request.payload || {})};
  const outputLines = [];
  const requestConsole = {
    log: (...args) => outputLines.push(args.join(' ')),
    info: (...args) => outputLines.push(args.join(' ')),
    debug: (...args) => outputLines.push(args.join(' ')),
    warn: (...args) => outputLines.push(args.join(' ')),
    error: (...args) => { throw new Error(args.join(' ')); },
  };
  const console = requestConsole;
  const timers = new Map();
  const intervals = new Map();
  let nextTimer = 1;
  let nextInterval = 1;
  const requestSetTimeout = (callback, delay, ...args) => {
    const token = nextTimer++;
    const handle = setTimeout(() => {
      timers.delete(token);
      callback(...args);
    }, delay);
    timers.set(token, handle);
    return token;
  };
  const requestClearTimeout = token => {
    const handle = timers.get(token);
    if (handle !== undefined) clearTimeout(handle);
    timers.delete(token);
  };
  const requestSetInterval = (callback, delay, ...args) => {
    const token = nextInterval++;
    const handle = setInterval(callback, delay, ...args);
    intervals.set(token, handle);
    return token;
  };
  const requestClearInterval = token => {
    const handle = intervals.get(token);
    if (handle !== undefined) clearInterval(handle);
    intervals.delete(token);
  };
  const unhandledRejections = [];
  const captureRejection = reason => unhandledRejections.push(reason);
  process.on('unhandledRejection', captureRejection);
  try {
    // The adapter function is a hidden call-through into the host realm. Only
    // this primitive envelope may cross back into the request VM.
    const adapterEnvelope = operation => {
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
          result = args.length > 1 ? params.has(args[0], args[1]) : params.has(args[0]);
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
    const runtime = vm.createContext({
      __wingmanStartupPageJson: startupPageJson,
      __wingmanTextEncoderAdapter: textEncoderAdapter,
      __wingmanURLSearchParamsAdapter: urlSearchParamsAdapter,
      console: requestConsole,
      setTimeout: requestSetTimeout,
      clearTimeout: requestClearTimeout,
      setInterval: requestSetInterval,
      clearInterval: requestClearInterval,
    });
    const run = text => { if (text) return vm.runInContext(text, runtime); };
    run(`(() => {
      const createDOM = ${DOM_FACTORY_SOURCE};
      const page = JSON.parse(globalThis.__wingmanStartupPageJson);
      delete globalThis.__wingmanStartupPageJson;
      const {document, Element, scrolls} = createDOM(page);
      const windowState = new Element('window');
      Object.defineProperties(
        globalThis, Object.getOwnPropertyDescriptors(windowState));
      Object.setPrototypeOf(globalThis, Element.prototype);
      globalThis.window = globalThis;
      globalThis.document = document;
      globalThis.Element = Element;
      globalThis.__wingmanScrolls = scrolls;
    })()`);
    const window = run('globalThis');
    const document = window.document;
    const Element = window.Element;
    const scrolls = window.__wingmanScrolls;
    delete window.__wingmanScrolls;
    run(`(() => {
      const encode = globalThis.__wingmanTextEncoderAdapter;
      const searchParams = globalThis.__wingmanURLSearchParamsAdapter;
      delete globalThis.__wingmanTextEncoderAdapter;
      delete globalThis.__wingmanURLSearchParamsAdapter;

      const errorTypes = {Error, EvalError, RangeError, ReferenceError,
        SyntaxError, TypeError, URIError};
      function fromHost(envelope) {
        if (typeof envelope !== 'string') {
          throw new TypeError('Host adapter returned a non-primitive envelope');
        }
        const response = JSON.parse(envelope);
        if (!response || response.ok !== true) {
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
          } else if (init !== null && init !== undefined &&
              typeof init[Symbol.iterator] === 'function') {
            operation = 'construct-entries';
            const entries = [];
            for (const pair of init) {
              const values = Array.from(pair);
              if (values.length !== 2) {
                throw new TypeError('Each query pair must be an iterable [name, value] tuple');
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
        *keys() {
          for (const entry of this.entries()) yield entry[0];
        }
        *values() {
          for (const entry of this.entries()) yield entry[1];
        }
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
      globalThis.Event = class Event {
        constructor(type) { this.type = type; }
      };
      globalThis.CustomEvent = class CustomEvent {
        constructor(type, options) { this.type = type; this.detail = options.detail; }
      };
      globalThis.navigator = {clipboard: {
        readText() { throw new Error('clipboard read'); },
        writeText() { throw new Error('clipboard write'); }
      }};
      globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
      globalThis.matchMedia = () => ({matches: false});
      globalThis.getComputedStyle = () => ({visibility: 'visible'});
      globalThis.location = {search: ''};
    })()`);
    assert.equal(Object.hasOwn(window, '__wingmanTextEncoderAdapter'), false);
    assert.equal(Object.hasOwn(window, '__wingmanURLSearchParamsAdapter'), false);
    const vmGlobals = run('({Promise, Math, Date})');
    Object.assign(window, vmGlobals);
    const {Promise} = vmGlobals;
    const protocolProbe = request.payload?.protocol_probe;
    if (protocolProbe === 'vm-throw') {
      run(`(() => { function protocolVmThrow() { throw new Error('protocol VM throw'); }
        protocolVmThrow(); })()`);
    }
    if (protocolProbe === 'vm-reject') {
      run(`(() => { function protocolVmReject() {
        Promise.reject(new Error('protocol VM rejection')); }
        protocolVmReject(); })()`);
    }
    if (protocolProbe?.startsWith('pending-timer-')) {
      assert.ok(cleanupProbe, 'pending timer protocol requires a cleanup probe');
      const activeInterval = requestSetInterval(() => {
        cleanupProbe.events.push('active-interval');
        requestClearInterval(activeInterval);
      }, 0);
      const activeNativeInterval = intervals.get(activeInterval);
      cleanupProbe.cancelNativeIntervals = () => clearInterval(activeNativeInterval);
      await new Promise(resolve => setTimeout(() => {
        cleanupProbe.events.push('active-control');
        resolve();
      }, 0));
      await new Promise(resolve => setImmediate(resolve));
      assert.deepEqual(cleanupProbe.events, ['active-interval', 'active-control'],
        'request interval must run before its same-delay control');
      assert.equal(intervals.has(activeInterval), false,
        'requestClearInterval must release the active interval');
      requestSetTimeout(() => cleanupProbe.events.push('leaked-timeout'), 0);
      const pendingInterval = requestSetInterval(
        () => cleanupProbe.events.push('leaked-interval'), 0);
      const pendingNativeInterval = intervals.get(pendingInterval);
      cleanupProbe.cancelNativeIntervals = () => {
        clearInterval(activeNativeInterval);
        clearInterval(pendingNativeInterval);
      };
      cleanupProbe.pendingTimers = timers.size;
      cleanupProbe.pendingIntervals = intervals.size;
      cleanupProbe.timers = timers;
      cleanupProbe.intervals = intervals;
      if (protocolProbe === 'pending-timer-assertion-exit') {
        throw new Error('protocol cleanup probe failure');
      }
    }
    if (protocolProbe) {
      assert.equal(timers.size, 0, 'request left a live timer');
      await new Promise(resolve => setImmediate(resolve));
      if (unhandledRejections.length) throw unhandledRejections[0];
      assert.equal(timers.size, 0, 'request left a live timer');
      assert.fail('protocol probe did not fail');
    }
    const load = name => run(fs.readFileSync(web + '/' + name + '.js', 'utf8'));
    load('app');
    const WM = window.WM;
    const calls = [], waiting = [];
    let staging = false, hold = false, reply = () => null;
    const hostClone = value => JSON.parse(JSON.stringify(value));
    const clone = value => run('JSON.parse(' + JSON.stringify(JSON.stringify(value)) + ')');
    const webValue = value => {
      if (value === null || value === undefined || typeof value !== 'object'
          || value instanceof Promise) return value;
      return clone(value);
    };
    WM.send = (method, ...args) => {
      calls.push([method, ...args]);
      assert.equal(staging, false, 'synthetic stage reached bridge: ' + method);
      if (hold) return new Promise(resolve => waiting.push({method, resolve}));
      return Promise.resolve(webValue(reply(method, ...args)));
    };
    WM.endPreviewCapture = () => {};
    load('panel');
    const family = data.scenario === 'preview-subpage' ? 'previews'
      : data.section === 'previews' ? 'wanderer' : data.section;
    const methods = family === 'fleet' ? ['fleetScreenshot', 'fleetSharingScreenshot']
      : [family === 'wanderer' ? 'wandererScreenshot' : 'companionsScreenshot'];
    const tick = () => new Promise(resolve => requestSetTimeout(resolve, 5));
const live = data.fixture[family] ? clone(data.fixture[family]) : null;
if (data.companion_live_probe) {
  const probe = data.companion_live_probe;
  assert.equal(family, 'companions', 'companion live probe requires its owner family');
  assert.equal(live.state.revision, probe.expected_revision,
    'companion live revision leaked across requests');
  assert.equal(live.state.rows[0].label, probe.expected_label,
    'companion live label leaked across requests');
  assert.equal(live.state.rows[0].source.last_title, probe.expected_last_title,
    'companion nested live state leaked across requests');
  if (probe.poison) {
    live.state.revision = 9001;
    live.state.rows[0].label = 'Poisoned companion';
    live.state.rows[0].source.last_title = 'Poisoned nested source title';
  }
}
// Live revisions exceed the fixture: restoring authority must not depend on
// a guessed higher synthetic revision. Fleet controls are production-projected.
if (family === 'companions') {
  live.state.revision = 7; live.state.rows[0].label = 'Live companion'; live.state.rows[0].generation = 7;
} else if (family === 'wanderer') {
  live.state.revision = 7; live.state.generation = 7;
  live.state.base_url = 'https://live.example'; live.state.map_identifier = 'live-map';
} else if (family === 'fleet') {
  live.display.state.revision = 7; live.display.state.enabled = true; live.display.state.characters[0].name = 'Live pilot';
  live.sharing.state = clone(data.live_sharing);
  live.sharing.state.presentation_order = 7;
}
function pushLive() {
  if (family === 'companions') window.onCompanionPreviews(clone(live.state));
  else if (family === 'wanderer') window.onWandererState(clone(live.state));
  else { window.onFleetBarState(clone(live.display.state)); window.onFleetSharingState(clone(live.sharing.state)); }
}
function liveReply(method) {
  if (method === 'companion_previews_state' || method === 'wanderer_state') return live.state;
  if (method === 'fleet_bar_settings') return live.display.state;
  if (method === 'fleet_sharing_watch') return {state: live.sharing.state};
  return null;
}
function assertTab() {
  if (!data.tab) return;
  const panel = WM.el('settings-' + data.section + '-' + data.tab);
  assert.ok(panel, 'real markup has the expected subpage');
  assert.equal(panel.hidden, false, 'capture must select its tab before framing');
  const siblings = WM.el('section-' + data.section).querySelectorAll('.settings-subpage');
  assert.equal(siblings.filter(el => !el.hidden).length, 1);
}
function previousTab() {
  if (!data.tab) return;
  WM.settingsTab(data.section, data.tab === 'windows' || data.tab === 'youtube'
    ? (data.section === 'previews' ? 'characters' : 'combatlogs')
    : (data.section === 'previews' ? 'windows' : 'youtube'));
}
// Browser mechanics only: the shared DOM double has no layout engine. A hidden
// ancestor has no rendered boxes, and framing must use the selected panel.
Element.prototype.getClientRects = function () {
  for (let el = this; el; el = el.parentNode) if (el.hidden) return [];
  return [this.getBoundingClientRect()];
};
const click = Element.prototype.click;
Element.prototype.click = function () {
  if (staging && data.tab && this.closest('.settings-subpage')) {
    assertTab();
    assert.ok(this.getClientRects().length, 'cannot click a hidden screenshot control');
  }
  click.call(this);
};
const recordScroll = Element.prototype.scrollIntoView;
Element.prototype.scrollIntoView = function (options) {
  if (staging && data.tab) {
    assertTab();
    assert.ok(this.getClientRects().length, 'cannot frame a hidden descendant');
    assert.equal(this.closest('.settings-subpage')?.id, 'settings-' + data.section + '-' + data.tab);
  }
  recordScroll.call(this, options);
};
function assertContent() {
  assertTab();
  run(data.verify);
  assert.equal(WM.current_section, data.section);
  assert.ok(scrolls.length, 'semantic framing must run');
  if (family === 'companions') {
    assert.equal(document.querySelectorAll('.companion-row').length, 2);
    assert.match(WM.el('companion-list').textContent, /Mapper.*Whole window.*Fleet notes.*Selected region/);
    if (data.key.includes('detail')) assert.equal(document.querySelector('.companion-detail').open, true);
    if (data.key.endsWith('-add')) assert.equal(WM.el('companion-add-form').hidden, false);
    if (data.key.includes('source')) {
      assert.equal(WM.el('overlay').hidden, false);
      assert.ok(WM.el('dialog').classList.contains('compact-choice'));
      assert.match(WM.el('dlg-select').textContent, /Example map.*Example fleet notes/);
      assert.match(WM.el('dlg-select').options[0].textContent, /…$/);
      assert.match(WM.el('dlg-select-detail').textContent, /home chain and fleet route planning/);
    }
  } else if (family === 'wanderer') {
    assert.equal(WM.el('wanderer-url').value, 'https://wanderer.example/home-chain');
    assert.equal(WM.el('wanderer-token').value, '');
    assert.equal(WM.el('wanderer-url-draft').textContent, '');
    assert.equal(WM.el('wanderer-health-label').textContent, 'Connected · Names available for 2 of 3 previews');
    assert.match(WM.el('wanderer-coverage').textContent, /2 of 3/);
    if (data.key === 'settings-wanderer-narrow') {
      assert.equal(scrolls.at(-1).element.id, 'wanderer-health',
        'the floor status shot must frame readiness, not scroll past it to credentials');
    }
  } else {
    assert.equal(WM.fleet_bar_on, true, 'a local fixture cannot change the global live EVE gate');
    assert.match(WM.el('fleetbar-character-list').textContent, /Running.*Aiga Otsolen.*Offline.*Tanuki Solette/);
    assert.match(WM.el('sharing-connection').textContent, /Paired with https:\/\/authgd.example/);
    assert.equal(WM.el('sharing-history').hidden, false);
    assert.match(WM.el('sharing-history-sources').textContent, /ended — boss lost/);
  }
}
function mutations() {
  const fire = (id, type = 'click') => WM.el(id).dispatchEvent({type});
  if (family === 'companions') {
    for (const suffix of ['reset', 'region', 'remove', 'label-apply']) fire('companion-screenshot-map-' + suffix);
    fire('companion-enabled', 'change'); fire('companion-screenshot-map-enabled', 'change');
    if (data.key.includes('source')) fire('dlg-ok'); // Must never select a native source.
  } else if (family === 'wanderer') {
    fire('wanderer-test'); fire('wanderer-remove'); fire('wanderer-enabled', 'change');
    WM.el('wanderer-token').dispatchEvent({type: 'keydown', key: 'Enter'});
  } else {
    const confirm = WM.confirm;
    let confirmations = 0;
    WM.confirm = (...args) => { confirmations += 1; return confirm(...args); };
    try {
      for (const id of ['btn-fleetbar', 'fleetbar-reset', 'sharing-start', 'sharing-grant', 'sharing-connect', 'sharing-confirm-on',
        'sharing-combat', 'sharing-automatic-confirm', 'sharing-automatic-cancel', 'sharing-automatic-dismiss',
        'sharing-legacy-dismiss', 'sharing-legacy-remove']) fire(id);
      fire('fleetbar-enabled', 'change'); fire('sharing-enabled', 'change');
      for (const checked of [true, false]) {
        WM.el('sharing-automatic').checked = checked; fire('sharing-automatic', 'change');
      }
      document.querySelector('[data-fleet-character] input').dispatchEvent({type: 'change'});
      WM.el('sharing-refresh').click();
      // Replace pending Stop is the first (hidden) button; exercise real Stop.
      const stop = WM.el('sharing-sources').firstChild.lastChild;
      assert.equal(stop.textContent, 'Stop verification');
      assert.equal(stop.hidden, false);
      assert.equal(stop.disabled, false);
      stop.dispatchEvent({type: 'click'});
      assert.equal(confirmations, 0, 'fixture events must not even request confirmation');
    } finally { WM.confirm = confirm; }
  }
}
async function sharingLifecycle(scenario) {
  const A = clone(live.sharing.state), B = clone(data.live_sharing_newer);
  // Each pure projection starts at its first envelope. Sequence these two
  // deliveries without inventing or rewriting any control observation/hash.
  B.presentation_order = A.presentation_order + 1;
  const fire = (id, type = 'click') => WM.el(id).dispatchEvent({type});
  const groups = ['sharing-sources', 'sharing-pending-sources', 'sharing-history-sources'];
  const rowIds = () => groups.map(id => Array.from(
    WM.el(id).children, row => row.getAttribute('data-source')));
  const view = () => Array.from(document.querySelectorAll('[id]').filter(
    node => node.id.startsWith('sharing-')
      || ['fleet-overview-sharing', 'fleet-overview-auth',
        'fleet-overview-verification'].includes(node.id)),
  node => [node.id, node.textContent, node.hidden, node.disabled,
    node.checked, node.value, !!node.open]);
  const controls = ['sharing-combat', 'sharing-automatic-confirm', 'sharing-automatic-cancel',
    'sharing-automatic-dismiss', 'sharing-legacy-dismiss', 'sharing-legacy-remove', 'sharing-connect', 'sharing-confirm-on'];
  const confirm = WM.confirm;
  let confirmations = 0;
  WM.confirm = (...args) => { confirmations += 1; return confirm(...args); };
  function noAuthority() {
    const before = confirmations;
    for (const id of controls) fire(id);
    for (const id of ['sharing-enabled', 'sharing-automatic']) {
      WM.el(id).checked = true; fire(id, 'change');
      WM.el(id).checked = false; fire(id, 'change');
    }
    assert.equal(confirmations, before, 'unhydrated/fixture controls must not open a consent dialog');
    assert.equal(calls.length, 0, 'unhydrated/fixture controls must not send any observation');
  }
  function cold() {
    assert.equal(WM.el('fleet-overview-sharing').textContent, 'Unknown');
    assert.equal(WM.el('fleet-overview-auth').textContent, 'Unknown');
    assert.equal(WM.el('fleet-overview-verification').textContent, 'Unknown · unavailable');
    assert.match(WM.el('sharing-connection').textContent, /unavailable/);
    assert.match(WM.el('sharing-automatic-status').textContent, /has not been observed/);
    assert.doesNotMatch(WM.el('sharing-automatic-status').textContent, /Off for your account|On for your account|On;/);
    assert.equal(WM.el('sharing-automatic').checked, false);
    assert.equal(WM.el('sharing-combat').hidden, false);
    for (const id of ['sharing-confirm-on', 'sharing-automatic-confirm', 'sharing-automatic-cancel',
      'sharing-automatic-dismiss', 'sharing-legacy-history', 'sharing-legacy-dismiss', 'sharing-legacy-remove']) {
      assert.equal(WM.el(id).hidden, true, id + ' has no observed action after cold cleanup');
    }
    for (const id of ['sharing-setup-history', 'sharing-legacy-summary', 'sharing-consent', 'sharing-preference',
      'sharing-eligibility', 'sharing-action', 'sharing-browser-error', 'sharing-source-status']) {
      assert.equal(WM.el(id).textContent, '', id + ' retained synthetic feedback');
    }
    assert.equal(WM.el('sharing-legacy-history').open, false);
    assert.deepEqual(rowIds(), [[], [], []]);
    assert.equal(WM.el('sharing-eligible-list').children.length, 0);
    assert.equal(WM.el('sharing-history').hidden, true);
    assert.equal(WM.el('sharing-history-summary').textContent, 'Previous attempts (0)');
    for (const node of WM.el('fleet-sharing').querySelectorAll('button, input, select')) {
      assert.equal(node.disabled, true, node.id + ' must remain unavailable');
    }
    noAuthority();
  }
  function observed(expected) {
    assert.equal(WM.el('sharing-connection').textContent, 'Paired with ' + expected.metadata.paired_origin + '.');
    assert.equal(WM.el('sharing-automatic').checked, true);
    assert.equal(WM.el('sharing-automatic').disabled, false);
    assert.match(WM.el('sharing-automatic-status').textContent, /^On;/);
    assert.equal(WM.el('sharing-combat').hidden, true);
    assert.equal(WM.el('sharing-enabled').checked, expected.enabled);
    assert.equal(WM.el('fleet-overview-sharing').textContent, expected.enabled ? 'On' : 'Off');
    assert.match(WM.el('fleet-overview-auth').textContent, /Paired · last observed On/);
    assert.equal(WM.el('fleet-overview-verification').textContent,
      expected.pending_sources.length ? 'Eligible · local operation pending' : 'Eligible');
    assert.deepEqual(rowIds(), hostClone([
      expected.sources.sources.filter(row => row.state !== 'ended').map(row => row.source_id),
      expected.pending_sources.map(row => row.source_id),
      expected.sources.sources.filter(row => row.state === 'ended').map(row => row.source_id)
    ]));
    for (const control of expected.controls.sources) {
      const row = document.querySelector('[data-source="' + control.source_id + '"]');
      assert.deepEqual(hostClone(row.lastChild._sharingControl), hostClone(control));
    }
    assert.doesNotMatch(WM.el('fleet-sharing').textContent, /poisoned|authgd\.example/);
  }
  function poison(input) {
    input.metadata.paired_origin = 'https://poisoned.example';
    input.metadata.binding = 'poisoned-binding';
    input.sources.characters[0].character_name = 'poisoned character';
    input.sources.sources[0].reason = 'poisoned';
    input.controls.sources[0].binding = 'poisoned-control';
    input.setup_controls.automatic.observed.enabled = false;
    input.setup_controls.setup.combat_approved = false;
  }
  async function stage(generation) {
    calls.length = 0; staging = true;
    run(data.prepare);
    if (generation !== undefined) {
      const next = clone(data.fixture.fleet.sharing);
      next.state.presentation_order += generation;
      WM.fleetSharingScreenshot(next);
    }
    run(data.stage); await tick(); run(data.verify);
    assert.equal(WM.el('sharing-automatic-status').textContent, 'Off for your account.');
    assert.equal(WM.el('sharing-combat').hidden, false);
    mutations(); await tick(); assert.equal(calls.length, 0);
  }
  async function cleanup() {
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'fixture cleanup is entirely local');
    assert.equal(WM.el('sharing-history').open, false);
    assert.equal(WM.el('sharing-eligible').open, false);
  }
  async function automaticOff(expected) {
    staging = false; calls.length = 0;
    const before = confirmations;
    WM.el('sharing-automatic').checked = false; fire('sharing-automatic', 'change');
    await tick();
    assert.equal(confirmations, before, 'ordinary automatic Off does not wait on a dialog');
    assert.deepEqual(hostClone(calls), hostClone([
      ['fleet_sharing_automatic', 'off', expected.setup_controls.automatic]
    ]));
  }

  if (scenario === 'cold' || scenario === 'cold-then-live' || scenario === 'repeat') {
    const retired = [];
    for (let iteration = 0; iteration < (scenario === 'repeat' ? 3 : 1); iteration++) {
      await stage(scenario === 'repeat' ? iteration + 1 : undefined);
      retired.push(WM.el('sharing-sources').firstChild.lastChild);
      // Input interaction is still fixture-only; cleanup must clear the draft
      // checked state and disclosure even when no live observation ever arrived.
      WM.el('sharing-automatic').checked = true;
      fire('sharing-automatic', 'change');
      WM.el('sharing-legacy-history').open = true;
      await cleanup(); cold();
      for (const control of retired) {
        assert.equal(control._sharingControl, null, 'no prior fixture generation retains an observation');
        assert.equal(control.disabled, true);
      }
      const neutral = view();
      run(data.cleanup); await tick(); assert.deepEqual(view(), neutral);
    }
    if (scenario === 'cold-then-live') {
      staging = false; window.onFleetSharingState(clone(B)); observed(B);
      await automaticOff(B);
    }
  } else if (scenario === 'live-before') {
    const input = clone(A);
    window.onFleetSharingState(input);
    WM.el('sharing-boss').value = '1'; fire('sharing-boss', 'change');
    const before = view();
    await stage(); poison(input); await cleanup();
    assert.deepEqual(view(), before, 'stage must detach the preexisting live snapshot and roster');
    observed(A);
    await automaticOff(A);
  } else if (scenario === 'live-during') {
    window.onFleetSharingState(clone(A));
    await stage();
    const input = clone(B);
    window.onFleetSharingState(input); poison(input);
    window.onFleetSharingState(clone(A)); // Older delivery cannot replace buffered B.
    await cleanup(); observed(B);
    await automaticOff(B);
  } else if (scenario === 'authority') {
    window.onFleetSharingState(clone(A));
    // This dialog captured A, but no operation has been sent. Fixture epochs
    // must invalidate its answer rather than substitute B's newer authority.
    WM.el('sharing-automatic').checked = true; fire('sharing-automatic', 'change');
    assert.equal(confirmations, 1);
    assert.equal(WM.el('overlay').hidden, false);
    hold = true; WM.el('sharing-refresh').click(); await tick(); hold = false;
    assert.equal(waiting.length, 1);
    await stage();
    const fixtureStop = WM.el('sharing-sources').firstChild.lastChild;
    window.onFleetSharingState(clone(B));
    await cleanup(); observed(B);
    waiting.shift().resolve(webValue({state: clone(A)})); await tick(); observed(B);
    assert.equal(calls.length, 0, 'pre-fixture read completion cannot acquire live authority');
    WM.el('dlg-ok').click(); await tick();
    assert.equal(calls.length, 0, 'pre-fixture confirmation cannot survive the fixture epoch');
    const before = confirmations;
    fixtureStop.dispatchEvent({type: 'click'}); await tick();
    assert.equal(confirmations, before, 'a detached fixture Stop cannot open a live dialog');
    assert.equal(calls.length, 0);
    await automaticOff(B);
    calls.length = 0;
    const stop = WM.el('sharing-sources').firstChild.lastChild;
    stop.click(); assert.equal(WM.el('overlay').hidden, false);
    WM.el('dlg-ok').click(); await tick();
    assert.deepEqual(hostClone(calls), hostClone([
      ['fleet_sharing_stop_source', B.controls.sources[0].source_id,
        B.metadata.binding, B.controls.sources[0]]
    ]));
  } else if (scenario === 'focus') {
    window.onFleetSharingState(clone(A));
    WM.el('sharing-boss').value = '1'; fire('sharing-boss', 'change');
    WM.el('sharing-history').open = true; WM.el('sharing-eligible').open = true;
    const draft = WM.el('wanderer-url'); draft.value = 'https://private-draft.example/map';
    await stage();
    draft.focus();
    await cleanup();
    assert.equal(document.activeElement, draft, 'cleanup cannot steal newer outside focus');
    assert.equal(draft.value, 'https://private-draft.example/map');
    assert.equal(WM.el('sharing-boss').value, '1', 'same-binding boss draft survives capture');
    await stage();
    WM.confirm('Newer outside dialog', 'Retain this independently owned dialog.');
    WM.el('dlg-cancel').focus();
    await cleanup();
    assert.equal(WM.el('overlay').hidden, false);
    assert.equal(WM.el('dlg-title').textContent, 'Newer outside dialog');
    assert.equal(document.activeElement, WM.el('dlg-cancel'));
    WM.el('dlg-cancel').click(); await tick(); assert.equal(calls.length, 0);
  } else if (scenario === 'worklists') {
    window.onFleetSharingState(clone(A));
    const before = rowIds();
    await stage();
    assert.deepEqual(rowIds(), before);
    const fixtureRows = groups.flatMap(id => Array.from(WM.el(id).children));
    window.onFleetSharingState(clone(B));
    await cleanup(); observed(B);
    assert.deepEqual(rowIds(), hostClone([
      before[0], B.pending_sources.map(row => row.source_id), before[2]
    ]));
    assert.equal(WM.el('sharing-pending').hidden, false);
    assert.match(WM.el('sharing-pending-sources').textContent, /Start saved; outcome unconfirmed/);
    assert.equal(WM.el('sharing-history-summary').textContent, 'Previous attempts (1)');
    assert.match(WM.el('sharing-history-sources').textContent, /ended — boss lost/);
    const restored = groups.flatMap(id => Array.from(WM.el(id).children));
    assert.ok(restored.every(row => !fixtureRows.includes(row)), 'restored rows must not retain fixture control captures');
    const neutral = view();
    run(data.cleanup); assert.deepEqual(view(), neutral);
    restored[0].lastChild.focus();
    window.onFleetSharingState(clone(B));
    const reconciled = groups.flatMap(id => Array.from(WM.el(id).children));
    assert.equal(reconciled.length, restored.length);
    reconciled.forEach((row, index) => assert.equal(row, restored[index], 'ordinary live reconciliation keeps keyed rows'));
    assert.equal(document.activeElement, restored[0].lastChild);
    assert.equal(calls.length, 0);
  } else assert.fail('Unknown sharing lifecycle case: ' + scenario);
  WM.confirm = confirm;
}
async function executeScenario() {
  if (data.scenario === 'preview-subpage') {
    load('previews'); WM.openSettingsSection('previews'); await tick();
    const outer = document.querySelector('.settings-pane');
    outer.scrollTop = 57;
    const writes = [];
    for (const panel of WM.el('section-previews').querySelectorAll('.settings-subpage')) {
      let top = 73;
      panel.scrollHeight = 2000; panel.clientHeight = 400;
      Object.defineProperty(panel, 'scrollTop', {
        get: () => top,
        set: value => { assertTab(); assert.equal(panel.hidden, false); top = value; writes.push(panel.id); }
      });
    }
    // These navigation cases execute the real geometric stage/verifier too.
    // Supply boundary inputs here; exhaustive failures live in the dedicated
    // screenshot_pages and preview_warning_grouping harnesses.
    const pane = WM.el('settings-previews-characters');
    const rect = (left, top, width, height) => ({left, top, width, height, right: left + width, bottom: top + height});
    if (data.key === 'settings-previews-sticky-conflict') {
      const scroll = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (options) {
        scroll.call(this, options);
        pane.scrollTop = this.classList.contains('preview-bind-conflict') ? 400 : 444;
      };
      Element.prototype.getBoundingClientRect = function () {
        if (this === pane) return rect(200, 100, 600, 400);
        if (this.parentNode?.classList.contains('bind-head')) return rect(200, 100, 600, 22);
        const warning = this.classList.contains('preview-bind-conflict');
        return rect(220, (warning ? 400 : 444) - pane.scrollTop, 560, warning ? 40 : 28);
      };
    }
    function groupGeometry() {
      if (data.key !== 'settings-previews-groups') return;
      window.innerWidth = 840; window.innerHeight = 625;
      const manager = document.querySelector('.preview-group-manager');
      const boxes = new Map([[pane, rect(200, 140, 628, 435)], [manager, rect(220, 150, 560, 240)]]);
      manager.querySelectorAll('summary,.group-add-name,.group-add-btn,.group-rename-btn,.group-delete-btn')
        .forEach((node, i) => boxes.set(node, rect(220, 154 + i * 24, 560, 20)));
      for (const [node] of boxes) node.getBoundingClientRect = () => boxes.get(node);
      document.elementFromPoint = (x, y) => [...boxes].reverse().find(([node, r]) =>
        node.getClientRects().length && x > r.left && x < r.right && y > r.top && y < r.bottom)?.[0] || null;
    }
    calls.length = 0; staging = true;
    for (let iteration = 0; iteration < 2; iteration++) {
      writes.length = 0;
      scrolls.length = 0;
      previousTab();
      for (const name of ['appearance', 'placement', 'size', 'switching']) {
        WM.el('preview-group-' + name).open = iteration === 0;
      }
      run(data.prepare); run(data.stage); await tick(); assertTab(); groupGeometry(); run(data.verify);
      assert.equal(outer.scrollTop, 57, 'outer Settings pane must never own Preview scrolling');
      assert.ok(writes.length || scrolls.length, 'the selected panel must be framed');
      if (data.tab === 'windows') {
        const middle = data.key.endsWith('-middle');
        for (const name of ['appearance', 'placement']) assert.equal(WM.el('preview-group-' + name).open, !middle);
        for (const name of ['size', 'switching']) assert.equal(WM.el('preview-group-' + name).open, middle);
        if (middle) assert.equal(scrolls.at(-1).element.id, 'preview-group-size');
        else assert.equal(WM.el('settings-previews-windows').scrollTop, 0);
      }
      if (data.key === 'settings-previews-table') {
        assert.equal(WM.el('settings-previews-characters').scrollTop, 2000);
        assert.equal(document.querySelector('[data-preview-configure][aria-expanded="true"]'), null);
        // The next pass must close a detail inherited from an earlier capture.
        document.querySelector('[data-preview-configure]').click();
      }
      if (data.key === 'settings-previews-copy') WM.el('dlg-cancel').click();
      run(data.cleanup); await tick();
      assert.equal(calls.length, 0, 'tab selection and staging must not reach the bridge');
    }
    console.log('PASS current screenshot ' + data.key); return;
  }
  if (data.scenario === 'live-card') {
    const replies = {
      fightrecorder_status: {detected: false},
      get_bookmarks: {settings: {enabled: false, windows: {}, keybinds: {}},
        windows: [], order: ['sig'], labels: {sig: 'SIG'}, displays: {}, collisions: []},
      get_alert_state: {alerts: {enabled: false, events: {}}, previews_enabled: false},
      get_custom_alert_state: {revision: 1, rules: [], limit: 8, previews_enabled: false,
        alerts_enabled: false, reader: {running: false, last_error: null, characters: [], gamelogs_folder: null},
        matcher: {state: 'inactive', detail: null}}
    };
    reply = method => replies[method] || null;
    document.activeElement = document.body;
    load(data.section === 'uploading' ? 'settings' : data.section);
    WM.openSettingsSection(data.section);
    if (data.section === 'uploading') window.onSettings(clone({settings: {category: '20'}}));
    await tick();
    const expected = data.section === 'uploading' ? '#fr-status'
      : data.section === 'bookmarks' ? '#eve-windows' : '#custom-alert-health';
    assert.ok(document.querySelector(expected).textContent, 'real owner must hydrate the card');
    previousTab();
    calls.length = 0; staging = true;
    run(data.stage); assertTab(); run(data.verify);
    assert.equal(scrolls.at(-1).element.classList.contains('card'), true);
    assert.equal(scrolls.at(-1).options.block, 'start');
    assert.equal(calls.length, 0);
    const framed = scrolls.at(-1).element;
    framed.hidden = true;
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    framed.hidden = false;
    if (data.section === 'alerts') {
      // Add is legitimately disabled at capacity; populated controls are still
      // a settled card, not a hydration failure.
      replies.get_custom_alert_state.rules = Array.from({length: 8}, (_, index) => ({
        id: 'rule-' + index, name: 'Rule ' + index, search: '', enabled: false,
        color: '#ff8c42', sound: 'none', cooldown_s: 8
      }));
      staging = false; WM.openSettingsSection('alerts'); await tick(); staging = true;
      assert.equal(WM.el('custom-alert-add').disabled, true);
      run(data.verify);
    }
    // The stage cannot silently accept the startup/blank rendering.
    if (data.section === 'uploading') WM.el('f-category').value = '';
    else if (data.section === 'bookmarks') WM.el('eve-windows').textContent = '';
    else WM.el('custom-alert-health').textContent = 'Loading custom alert status…';
    assert.throws(() => run(data.verify), /Screenshot content did not settle/);
    console.log('PASS current screenshot ' + data.key); return;
  }
  hold = data.scenario === 'late-read';
  if (family === 'fleet') { load('fleet'); load('fleetsharing'); }
  else load(family);
  WM.openSettingsSection(data.section); await tick();
  if (data.scenario.startsWith('sharing-lifecycle-')) {
    await sharingLifecycle(data.scenario.slice('sharing-lifecycle-'.length));
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario === 'cold') {
    calls.length = 0; staging = true;
    run(data.prepare); WM.openSettingsSection(data.section); await tick(); run(data.stage); await tick(); run(data.verify);
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0);
    if (family === 'companions') {
      assert.equal(WM.el('companion-list').children.length, 0);
      assert.equal(WM.el('companion-count').textContent, '');
      assert.equal(WM.el('companion-status').textContent, 'Loading companions…');
    } else if (family === 'wanderer') {
      assert.equal(WM.el('wanderer-url').value, '');
      assert.equal(WM.el('wanderer-token').value, '');
      assert.equal(WM.el('wanderer-coverage').textContent, '');
      assert.notEqual(WM.el('wanderer-credential').textContent, 'Token stored for this connection.');
    } else {
      assert.equal(WM.el('fleetbar-character-list').children.length, 0);
      assert.doesNotMatch(WM.el('fleet-sharing').textContent, /Aiga Otsolen|Ariadne|authgd.example/);
      assert.equal(WM.el('sharing-consent').textContent, '');
    }
    staging = false; reply = liveReply; WM.openSettingsSection(data.section); await tick();
    if (family === 'companions') assert.match(WM.el('companion-list').textContent, /Live companion/);
    else if (family === 'wanderer') assert.equal(WM.el('wanderer-url').value, 'https://live.example/live-map');
    else assert.match(WM.el('sharing-connection').textContent, /https:\/\/live.example/);
    console.log('PASS current screenshot cold cleanup'); return;
  }
  pushLive();
  if (data.scenario.startsWith('sharing-read-')) {
    WM.el('sharing-boss').value = '1'; WM.el('sharing-boss').dispatchEvent({type: 'change'});
    assert.equal(WM.el('sharing-start').disabled, false);
    WM.el('sharing-refresh').click(); await tick();
    const failedAuthority = () => {
      assert.match(WM.el('sharing-connection').textContent, /Could not refresh current verification state/);
      assert.match(WM.el('sharing-eligibility').textContent, /Current eligibility unknown/);
      assert.equal(WM.el('sharing-eligible-list').children.length, 0);
      assert.equal(WM.el('sharing-start').disabled, true);
      assert.equal(WM.el('sharing-sources').querySelector('button').disabled, true);
    };
    failedAuthority(); calls.length = 0; staging = true;
    run(data.prepare);
    if (!data.scenario.endsWith('cached')) {
      if (data.scenario.endsWith('newer')) live.sharing.state.presentation_order += 1;
      window.onFleetSharingState(clone(live.sharing.state));
    }
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0);
    if (data.scenario.endsWith('newer')) {
      assert.doesNotMatch(WM.el('sharing-connection').textContent, /Could not refresh/);
      assert.equal(WM.el('sharing-start').disabled, false);
      assert.equal(WM.el('sharing-eligible-list').children.length, 2);
    } else failedAuthority();
    // A real successful Refresh at the same version still recovers authority.
    staging = false; reply = liveReply; WM.el('sharing-refresh').click(); await tick();
    assert.doesNotMatch(WM.el('sharing-connection').textContent, /Could not refresh/);
    assert.equal(WM.el('sharing-start').disabled, false);
    assert.equal(WM.el('sharing-sources').querySelector('button').disabled, false);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('wanderer-fence-')) {
    assert.equal(WM.el('wanderer-health-label').textContent, 'Connected · Names available for 2 of 3 previews');
    const buffered = data.scenario.endsWith('buffered');
    calls.length = 0; staging = true;
    if (buffered) run(data.prepare);
    // Settings changed before worker reconfiguration. The acknowledgement is
    // current, but this coverage still belongs to the previous binding.
    const rebound = clone({...live.state, revision: 8, generation: 7, map_identifier: 'new-binding'});
    window.onWandererState(rebound);
    if (buffered) {
      assert.equal(WM.el('wanderer-url').value, 'https://wanderer.example/home-chain');
      run(data.cleanup);
      assert.equal(WM.el('wanderer-url').value, 'https://live.example/new-binding');
    }
    assert.equal(WM.el('wanderer-health').textContent, 'Connecting…');
    assert.equal(WM.el('wanderer-coverage').textContent, '');
    window.onWandererState(clone({...rebound, generation: 8, available: 1}));
    assert.equal(WM.el('wanderer-health-label').textContent, 'Connected · Names available for 1 of 3 previews');
    assert.match(WM.el('wanderer-coverage').textContent, /^2 of 3 tracked/);
    assert.equal(calls.length, 0);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('fleet-pending-')) {
    const action = data.scenario.slice('fleet-pending-'.length);
    hold = true; calls.length = 0;
    if (action === 'character') document.querySelector('[data-fleet-character] input').dispatchEvent({type: 'change'});
    else if (action === 'toggle-check') WM.el('fleetbar-enabled').dispatchEvent({type: 'change'});
    else WM.el(action === 'reset' ? 'fleetbar-reset' : 'btn-fleetbar').click();
    if (action === 'overlap') WM.el('fleetbar-reset').click();
    assert.equal(waiting.length, action === 'overlap' ? 2 : 1);
    const refuse = () => {
      staging = true; calls.length = 0;
      assert.throws(() => run(data.prepare), /Fleet.*in progress/);
      run(data.cleanup); assert.equal(calls.length, 0); staging = false;
    };
    refuse();
    const error = {applied: false, persisted: false, error: 'Live write failed'};
    waiting.shift().resolve(webValue(error)); await tick();
    if (action === 'overlap') { refuse(); waiting.shift().resolve(webValue(error)); await tick(); }
    assert.match(WM.el(action === 'character' ? 'fleetbar-characters-status' : 'fleetbar-enabled-status').textContent, /Live write failed/);
    hold = false; staging = true;
    run(data.prepare); run(data.cleanup); // Admission resumes only after every reply.
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario.startsWith('sharing-pending-')) {
    const action = data.scenario.slice('sharing-pending-'.length);
    live.sharing.state.presentation_order += 1;
    live.sharing.state.configured_origin = 'https://live.example';
    live.sharing.state.detail = 'needs_upgrade';
    window.onFleetSharingState(clone(live.sharing.state));
    WM.el('sharing-boss').value = '1'; WM.el('sharing-boss').dispatchEvent({type: 'change'});
    hold = true; calls.length = 0;
    WM.el(action === 'pair' ? 'sharing-connect' : 'sharing-grant').click();
    if (action === 'overlap') WM.el('sharing-connect').click();
    assert.equal(waiting.length, action === 'overlap' ? 2 : 1);
    const refuse = () => {
      staging = true; calls.length = 0;
      assert.throws(() => run(data.prepare), /Fleet sharing action in progress/);
      run(data.cleanup); assert.equal(calls.length, 0); staging = false;
    };
    refuse();
    const error = {queued: false, error: 'Browser launch failed'};
    // Settle the newer owner first: the older pending call still blocks capture.
    waiting.pop().resolve(webValue(error)); await tick();
    if (action === 'overlap') { refuse(); waiting.pop().resolve(webValue(error)); await tick(); }
    assert.match(WM.el('sharing-action').textContent, /Browser launch failed/);
    hold = false; staging = true;
    run(data.prepare); run(data.cleanup);
    assert.match(WM.el('sharing-action').textContent, /Browser launch failed/);
    console.log('PASS current screenshot ' + data.scenario); return;
  }
  if (data.scenario === 'fleet-focused') {
    const check = WM.el('fleetbar-enabled'); check.focus();
    assert.equal(check.checked, true);
    calls.length = 0; staging = true;
    run(data.prepare); assert.equal(check.checked, false);
    run(data.cleanup);
    assert.equal(check.checked, true, 'cleanup restores the acknowledged live value even while focused');
    assert.equal(document.activeElement, check);
    // Ordinary pushes still leave a focused checkbox alone.
    live.display.state.revision += 1; live.display.state.enabled = false;
    window.onFleetBarState(clone(live.display.state));
    assert.equal(check.checked, true);
    document.activeElement = document.body;
    window.onFleetBarState(clone(live.display.state));
    assert.equal(check.checked, false);
    assert.equal(calls.length, 0);
    console.log('PASS current screenshot fleet-focused'); return;
  }
  if (family === 'wanderer') {
    for (const [name, value] of [['url', 'https://private-draft.example/private-map'], ['token', 'private-token']]) {
      WM.el('wanderer-' + name).value = value;
      WM.el('wanderer-' + name).dispatchEvent({type: 'input'});
    }
  }
  if (data.scenario === 'live-dialog') {
    WM.confirm('Live operation', 'Do not dismiss this to stage a screenshot.');
    calls.length = 0; staging = true;
    assert.throws(() => run(data.prepare), /dialog/);
    run(data.cleanup);
    assert.equal(WM.el('overlay').hidden, false);
    assert.equal(WM.el('dlg-title').textContent, 'Live operation');
    assert.equal(calls.length, 0);
    WM.el('dlg-cancel').click();
    console.log('PASS current screenshot live-dialog'); return;
  }
  calls.length = 0; staging = true;
  if (data.scenario === 'invalid') {
    for (const method of methods) assert.throws(() => WM[method]({kind: 'wrong'}), /Invalid .* screenshot fixture/);
  }
  for (let iteration = 0; iteration < 2; iteration++) {
    previousTab();
    run(data.prepare);
    WM.openSettingsSection(data.section);
    await tick(); run(data.stage); await tick();
    assertContent();
    if (data.scenario === 'late-read') {
      waiting.splice(0).forEach(item => item.resolve(webValue(liveReply(item.method))));
      await tick(); assertContent();
    }
    // A newer live delivery during capture must be retained, not merely
    // ignored until cleanup restores the old snapshot.
    if (family === 'companions') {
      live.state.revision += 1; live.state.rows[0].label = 'Live companion updated';
    } else if (family === 'wanderer') {
      live.state.revision += 1; live.state.generation += 1; live.state.map_identifier = 'live-map-updated';
    } else {
      live.display.state.revision += 1; live.display.state.characters[0].name = 'Live pilot updated';
      live.sharing.state.presentation_order += 1;
    }
    pushLive(); await tick(); assertContent();
    mutations(); await tick();
    run(data.cleanup); await tick();
    assert.equal(calls.length, 0, 'cleanup must stay local too');
    if (family === 'wanderer') {
      assert.equal(WM.el('wanderer-url').value, 'https://live.example/live-map-updated');
      assert.equal(WM.el('wanderer-token').value, '', 'never restore secret drafts');
    } else if (family === 'companions') {
      assert.match(WM.el('companion-list').textContent, /Live companion updated/);
      assert.equal(WM.el('companion-add-form').hidden, true);
      assert.equal(WM.el('companion-add-label').value, '');
      assert.equal(WM.el('overlay').hidden, true);
    } else {
      assert.match(WM.el('fleetbar-character-list').textContent, /Live pilot updated/);
      assert.match(WM.el('sharing-connection').textContent, /https:\/\/live.example/);
      assert.equal(WM.el('sharing-history').open, false);
    }
  }
  if (data.scenario === 'late-synthetic') {
    const NativePromise = window.Promise;
    let release;
    window.Promise = {resolve: value => new NativePromise(resolve => { release = () => resolve(value); })};
    run(data.prepare); WM.openSettingsSection(data.section); run(data.stage);
    run(data.cleanup); window.Promise = NativePromise;
    if (release) release(); await tick();
    assert.equal(calls.length, 0);
    assert.equal(WM.el('overlay').hidden, true);
  }
  // Verification rejects removed or half-initialized payloads.
  run(data.prepare); WM.openSettingsSection(data.section); await tick(); run(data.stage); await tick();
  if (family === 'companions') WM.el('companion-list').textContent = '';
  else if (family === 'wanderer') WM.el('wanderer-url').value = '';
  else WM.el('sharing-connection').textContent = '';
  assert.throws(() => run(data.verify), /Screenshot content did not settle/);
  run(data.cleanup); await tick();
  staging = false; hold = false; reply = liveReply;
  WM.openSettingsSection(data.section); await tick();
  if (family === 'fleet') WM.el('fleetbar-reset').click();
  else if (family === 'companions') WM.el('companion-screenshot-map-reset').click();
  else WM.el('wanderer-test').click();
  await tick(); assert.ok(calls.length, 'ordinary live behavior resumes');
  if (family === 'companions') {
    assert.deepEqual(calls.find(call => call[0] === 'companion_preview_reset_geometry'),
      ['companion_preview_reset_geometry', 'screenshot-map', 7]);
  } else if (family === 'wanderer') {
    assert.deepEqual(calls.find(call => call[0] === 'test_wanderer_connection'),
      ['test_wanderer_connection', 'https://live.example/live-map-updated', '']);
  }
  console.log('PASS current screenshot ' + data.key + ' ' + data.scenario);
}
    await executeScenario();
    assert.equal(timers.size, 0, 'request left a live timer');
    await new Promise(resolve => setImmediate(resolve));
    if (unhandledRejections.length) throw unhandledRejections[0];
    assert.equal(timers.size, 0, 'request left a live timer');
    const passLines = outputLines.filter(line => line.startsWith('PASS current screenshot'));
    assert.equal(passLines.length, 1, 'request must produce exactly one terminal PASS line');
    assert.equal(outputLines.at(-1), passLines[0], 'request PASS line must be terminal');
    return passLines[0];
  } finally {
    process.removeListener('unhandledRejection', captureRejection);
    for (const handle of timers.values()) clearTimeout(handle);
    for (const handle of intervals.values()) clearInterval(handle);
    timers.clear();
    intervals.clear();
  }
}

async function runCleanupProbe(request) {
  const probe = {events: []};
  let output, failure;
  try {
    output = await runScenario(request, probe);
  } catch (error) {
    failure = error;
  }
  try {
    if (failure && !probe.timers) throw failure;
    assert.equal(probe.pendingTimers, 1,
      'cleanup must start with one pending tracked timer');
    assert.equal(probe.pendingIntervals, 1,
      'cleanup must start with one pending tracked interval');
    await new Promise(resolve => setTimeout(() => {
      probe.events.push('cleanup-control');
      resolve();
    }, 0));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(probe.events,
      ['active-interval', 'active-control', 'cleanup-control'],
      'pending request callbacks must be cancelled before the same-delay control');
    assert.equal(probe.timers.size, 0, 'request timer tracking must be cleared');
    assert.equal(probe.intervals.size, 0, 'request interval tracking must be cleared');
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
      const cleanupProbe = request.payload?.protocol_probe?.startsWith('pending-timer-');
      const output = await (cleanupProbe ? runCleanupProbe(request) : runScenario(request));
      fields = {ok: true, output, error: '', stack: ''};
    } catch (error) {
      fields = failureFields(error);
    }
    try {
      assert.deepEqual(process.listeners('unhandledRejection'), listenerBaseline,
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
  process.stderr.write((isNativeError(error) ? String(error.stack || error.message) : String(error)) + '\n');
  process.exitCode = 1;
});
