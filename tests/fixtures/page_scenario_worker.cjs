'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const vm = require('node:vm');
const {performance} = require('node:perf_hooks');
const {isNativeError} = require('node:util/types');

const hostJsonParse = JSON.parse.bind(JSON);
const hostJsonStringify = JSON.stringify.bind(JSON);
const hostObjectKeys = Object.keys.bind(Object);
const hostGetPrototypeOf = Object.getPrototypeOf.bind(Object);
const hostHasOwn = Function.call.bind(Object.prototype.hasOwnProperty);
const hostSetImmediate = setImmediate;
const hostString = String;
const cleanObjectPrototype = hostObjectKeys(Object.prototype).sort().join('\0');
const cleanArrayPrototype = hostObjectKeys(Array.prototype).sort().join('\0');
const cleanPromisePrototype = hostObjectKeys(Promise.prototype).sort().join('\0');
const cleanErrorPrototype = hostObjectKeys(Error.prototype).sort().join('\0');

const FAMILY_PROTOCOLS = Object.freeze({
  'saved-layouts': Object.freeze(['saved-main', 'saved-owner', 'saved-capture', 'saved-dev']),
  'fleet-sharing': Object.freeze(['fleet-sharing']),
  'group-backward': Object.freeze(['group-backward']),
  'label-markers': Object.freeze(['label-markers'])
});
const FAMILY_PAGE_KEYS = Object.freeze({
  'saved-layouts': Object.freeze(['structural', 'text']),
  'fleet-sharing': Object.freeze(['sharing']),
  'group-backward': Object.freeze(['structural']),
  'label-markers': Object.freeze(['structural'])
});
const PROGRAM_BY_PROTOCOL = Object.freeze({
  'saved-main': 'preview_savedlayouts.cjs',
  'saved-owner': 'preview_savedlayouts.cjs',
  'saved-capture': 'preview_capture_sessions.cjs',
  'saved-dev': 'preview_dev_capture.cjs',
  'fleet-sharing': 'fleetsharing_page.cjs',
  'group-backward': 'preview_group_backward.cjs',
  'label-markers': 'preview_labelmarkers.cjs'
});
const WEB_BY_FAMILY = Object.freeze({
  'saved-layouts': Object.freeze(['app.js', 'previews.js', 'fleetsharing.js', 'panel.js', 'dev.js']),
  'fleet-sharing': Object.freeze(['app.js', 'fleetsharing.js', 'dev.js']),
  'group-backward': Object.freeze(['app.js', 'previews.js', 'panel.js', 'dev.js']),
  'label-markers': Object.freeze(['app.js', 'previews.js', 'panel.js'])
});
const BUSINESS_LABELS = Object.freeze({
  'saved-layouts': Object.freeze([
    'preview-saved-layouts/page/',
    'preview-saved-layouts/owners/',
    'preview-saved-layouts/capture/',
    'preview-saved-layouts/dev/'
  ]),
  'fleet-sharing': Object.freeze(['fleet-sharing/page/']),
  'group-backward': Object.freeze(['preview-group-backward/page/']),
  'label-markers': Object.freeze(['preview-label-markers/page/'])
});
const SCENARIOS_BY_PROTOCOL = Object.freeze({
  'saved-main': new Set([
    'reversed', 'bulk', 'keybind', 'retry', 'draft', 'early', 'named', 'staging',
    'staging-roundtrip', 'copy-dialog-navigation', 'copy-dialog-subpage',
    'copy-dialog-staging', 'copy-dialog-configure', 'copy-dialog-attempt',
    'copy-dialog-capture', 'copy-admitted-subpage', 'copy-detail-fit',
    'copy-detail-truncated', 'copy-detail-clipped', 'copy-detail-legacy',
    'copy-detail-unmeasurable', 'copy-detail-resize', 'copy-detail-typography',
    'copy-detail-default', 'dialog-focus-history', 'dialog-owned-cancel',
    'geometry-detail-focus', 'geometry-detail-dialog', 'geometry-ack',
    'geometry-getter', 'geometry-keybind', 'geometry-staging',
    'geometry-dialog-navigation', 'geometry-dialog-capture', 'controls-empty',
    'controls-select', 'controls-save', 'controls-apply', 'controls-update',
    'controls-rename', 'controls-remove', 'controls-cancel', 'controls-errors',
    'controls-pending', 'controls-staging', 'controls-capture', 'controls-busy',
    'row-feedback', 'row-rejected', 'controls-unhydrated',
    'controls-unavailable', 'controls-failed-save', 'controls-incomplete',
    'controls-reopen', 'controls-staged-receipt'
  ]),
  'saved-owner': new Set(['saved', 'retained', 'excluded']),
  'saved-capture': new Set(['reversed', 'local', 'boundary']),
  'saved-dev': new Set(['dev']),
  'fleet-sharing': new Set([
    'missing-worker', 'null', 'error-no-state', 'reject', 'leave', 'reenter',
    'newer-push', 'stale-state', 'failed-refresh-during-on',
    'rejected-admission', 'scope-copy', 'overview-unknown', 'overview-pairing',
    'overview-preference', 'overview-verification', 'overview-read-fences',
    'pending-worklists', 'eligibility-readiness', 'verification-scope',
    'mixed-history', 'ended-only', 'ended-prerequisites', 'pending-precedence',
    'local-results', 'retained-unknown', 'failed-refresh-history',
    'binding-invalidation', 'inflight-stop', 'bridge-source-rejection',
    'inflight-start-leave', 'inflight-binding-reply', 'stable-history-focus',
    'visibility-ownership', 'retained-local-result', 'concurrent-stop-replies',
    'inflight-reenter', 'stale-preference-after-failed-refresh',
    'equal-preference-after-failed-refresh', 'boss-selection-across-unknown',
    'replace-stop-original', 'replace-stop-route', 'control-capture-on-generation',
    'control-capture-on-queued', 'control-capture-stop-generation',
    'control-capture-stop-automatic', 'control-capture-stop-pending',
    'control-dialog-binding', 'control-dialog-route', 'control-dialog-screenshot',
    'control-dialog-off', 'control-dialog-on-route', 'control-dialog-on-binding',
    'control-missing-authority', 'dev-control-authority', 'control-setup-combat',
    'control-setup-automatic', 'control-setup-stale', 'control-setup-route',
    'control-setup-off-overtakes', 'control-legacy-empty',
    'control-preference-feedback-pushes', 'control-preference-feedback-retry',
    'control-preference-feedback-off', 'control-preference-feedback-binding',
    'control-preference-feedback-screenshot'
  ]),
  'group-backward': new Set([
    'dev', 'rows', 'conflicts', 'writes', 'stale', 'cancel', 'marker',
    'focus-clearance', 'focus-draft', 'focus-lifecycle', 'focus-ownership',
    'focus-stable', 'focus-own-dialog', 'focus-dialog-owners',
    'focus-fixture-draft', 'focus-fixture-unhydrated', 'focus-crop-direction'
  ]),
  'label-markers': new Set([
    'hydration', 'receipts', 'owners', 'retention', 'exclusions', 'refresh',
    'navigation', 'screenshot', 'copy', 'reset-copy', 'reset-draft',
    'reset-headings', 'reset-headings-off', 'reset-capture',
    'reset-owner-capture', 'capture-entry-pointer', 'capture-entry-focus',
    'capture-entry-pointer-deferred', 'capture-entry-focus-deferred',
    'capture-entry-before-arm', 'screenshot-deferred'
  ])
});
const QUALIFICATION_MODES = new Set([
  'realm', 'clean', 'resources', 'inventory', 'error', 'primitive', 'null',
  'hostile', 'proxy', 'invalid-business', 'before-rejection',
  'boundary-rejection', 'late-success'
]);
const ZERO_CLEANUP = Object.freeze({
  host_timer_handles: 0,
  host_callbacks: 0,
  active_rejection_listeners: 0,
  pending_rejection_records: 0,
  retained_realms: 0
});
const TARGET_NAMES = Object.freeze([
  'preview_savedlayouts.cjs',
  'preview_capture_sessions.cjs',
  'preview_dev_capture.cjs',
  'fleetsharing_page.cjs',
  'preview_group_backward.cjs',
  'preview_labelmarkers.cjs',
  'screenshot_dom.cjs'
]);

function fatalProtocol(message, error = null) {
  const detail = error && isNativeError(error)
    ? message + ': ' + hostString(error.stack || error.message)
    : message;
  process.stderr.write(detail.slice(0, 65536) + '\n', () => process.exit(70));
}

function startupFailure(message, error = null) {
  const detail = error && isNativeError(error)
    ? message + ': ' + hostString(error.stack || error.message)
    : message;
  fs.writeSync(process.stderr.fd, detail.slice(0, 65536) + '\n');
  process.exit(64);
}

function exactKeys(value, expected) {
  const actual = hostObjectKeys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function assertFiniteJson(value, seen = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('nonfinite JSON number');
    return;
  }
  if (typeof value !== 'object') throw new TypeError('non-JSON value');
  if (seen.has(value)) throw new TypeError('cyclic JSON value');
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      for (const item of value) assertFiniteJson(item, seen);
      return;
    }
    if (hostGetPrototypeOf(value) !== Object.prototype && hostGetPrototypeOf(value) !== null) {
      throw new TypeError('non-plain JSON object');
    }
    for (const key of hostObjectKeys(value)) {
      if (key === '__proto__' || key === 'prototype' || key === 'constructor') {
        throw new TypeError('prototype-pollution key');
      }
      assertFiniteJson(value[key], seen);
    }
  } finally {
    seen.delete(value);
  }
}

function sha256(source) {
  return crypto.createHash('sha256').update(source, 'utf8').digest('hex');
}

let family;
let webRoot;
let manifestPath;
let manifestText;
let manifest;
let sourceRows;
let webRows;
let targetPaths;
let targetPathSet;
try {
  if (process.argv.length !== 6 || process.argv[2] !== '--worker') {
    throw new Error('usage: page_scenario_worker.cjs --worker FAMILY WEB_ROOT MANIFEST_PATH');
  }
  family = process.argv[3];
  webRoot = path.resolve(process.argv[4]);
  manifestPath = path.resolve(process.argv[5]);
  if (!hostHasOwn(FAMILY_PROTOCOLS, family)) throw new Error('unknown worker family ' + family);
  targetPaths = TARGET_NAMES.map(name => path.resolve(__dirname, name));
  targetPathSet = new Set(targetPaths);
  sourceRows = targetPaths.map((file, index) => {
    const source = fs.readFileSync(file, 'utf8');
    return Object.freeze({
      relative: 'tests/fixtures/' + TARGET_NAMES[index],
      filename: file,
      basename: TARGET_NAMES[index],
      source,
      sha256: sha256(source)
    });
  });
  webRows = WEB_BY_FAMILY[family].map(name => {
    const filename = path.resolve(webRoot, name);
    const source = fs.readFileSync(filename, 'utf8');
    return Object.freeze({basename: name, filename, source, sha256: sha256(source)});
  });
  manifestText = fs.readFileSync(manifestPath, 'utf8');
  manifest = hostJsonParse(manifestText);
  assertFiniteJson(manifest);
  if (!exactKeys(manifest, ['version', 'pages']) || manifest.version !== 1) {
    throw new Error('manifest must contain version 1 and pages');
  }
  if (!manifest.pages || hostGetPrototypeOf(manifest.pages) !== Object.prototype) {
    throw new Error('manifest pages must be an object');
  }
  const pageKeys = hostObjectKeys(manifest.pages).sort();
  const expectedPageKeys = [...FAMILY_PAGE_KEYS[family]].sort();
  if (pageKeys.length !== expectedPageKeys.length ||
      !pageKeys.every((key, index) => key === expectedPageKeys[index])) {
    throw new Error('manifest page keys did not match family');
  }
  if (targetPaths.some(file => require.cache[file])) throw new Error('target entered require.cache');
  if (module.children.some(child => targetPathSet.has(child.filename))) {
    throw new Error('target entered module.children');
  }
  manifest = null;
  Object.freeze(sourceRows);
  Object.freeze(webRows);
} catch (error) {
  startupFailure('page worker startup failed', error);
}

const sourceRegistry = Object.freeze(Object.fromEntries(
  sourceRows.map(row => [row.basename, row.source])
));
const webRegistry = Object.freeze(Object.fromEntries(
  webRows.map(row => [row.basename, row.source])
));
const structuralReceipt = Object.freeze({
  source_manifest: sourceRows.map(({relative, source, sha256: digest}) => Object.freeze({
    path: relative,
    bytes: Buffer.byteLength(source, 'utf8'),
    sha256: digest
  })),
  require_cache_targets: targetPaths.filter(file => require.cache[file]),
  module_child_targets: module.children
    .map(child => child.filename)
    .filter(file => targetPathSet.has(file)),
  retained_target_functions: 0
});
Object.freeze(structuralReceipt.source_manifest);

const SYNTHETIC_PROGRAM = String.raw`
'use strict';
const fs = require('node:fs');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
globalThis.__wingmanSourceExecutions = (globalThis.__wingmanSourceExecutions || 0) + 1;
const result = {
  source_execution_count: globalThis.__wingmanSourceExecutions,
  promise_completion: true,
  mode: data.mode,
  run: data.run || ''
};
if (data.mode === 'error') throw new Error('synthetic Error failure');
if (data.mode === 'primitive') throw 'synthetic primitive failure';
if (data.mode === 'null') throw null;
if (data.mode === 'hostile') {
  const hostile = {};
  Object.defineProperties(hostile, {
    name: {get() { throw new Error('name getter escaped'); }},
    message: {get() { throw new Error('message getter escaped'); }},
    stack: {get() { throw new Error('stack getter escaped'); }}
  });
  throw hostile;
}
if (data.mode === 'proxy') throw new Proxy({}, {get() { throw new Error('proxy trap escaped'); }});
if (data.mode === 'invalid-business' && data.business_value !== 'valid') {
  throw new TypeError('synthetic invalid business input');
}
if (data.mode === 'before-rejection') throw new Error('synthetic before-settlement rejection');
if (data.mode === 'boundary-rejection') throw new Error('synthetic timer-boundary rejection');
if (data.mode === 'resources') {
  setTimeout(() => { globalThis.__lateTimer = true; }, 100000);
  setInterval(() => { globalThis.__lateInterval = true; }, 100000);
  setImmediate(() => { globalThis.__lateImmediate = true; });
  document.addEventListener('synthetic', () => { globalThis.__lateListener = true; });
  globalThis.__unresolved = new Promise(() => {});
}
if (data.mode === 'realm' && data.run === 'poison') {
  globalThis.__wingmanRealmPoison = true;
  Object.prototype.__wingmanPoison = true;
  Array.prototype.__wingmanPoison = true;
  Error.prototype.__wingmanPoison = true;
  if (globalThis.__wingmanElement) globalThis.__wingmanElement.prototype.__wingmanPoison = true;
  if (data.nested) data.nested.value = 'poisoned';
  module.exports = {poisoned: true};
  Promise.prototype.then = function() {
    return {
      source_execution_count: globalThis.__wingmanSourceExecutions,
      promise_completion: false,
      mode: data.mode,
      run: data.run
    };
  };
}
module.exports = Promise.resolve(result);
`;

const BOOTSTRAP = String.raw`
(() => {
  'use strict';
  const safeParse = JSON.parse.bind(JSON);
  const safeStringify = JSON.stringify.bind(JSON);
  const safeString = String;
  const safeKeys = Object.keys.bind(Object);
  const localRequestId = requestId;
  const localRequestScenario = requestScenario;
  const localRequestToken = requestToken;
  const localStartTime = startTime;
  const localProgramSource = programSource;
  const localFixtureFilename = fixtureFilename;
  const sourceByBasename = JSON.parse(sourceRegistryJson);
  const webByBasename = JSON.parse(webSourcesJson);
  globalThis.hostParsedInput = safeParse(inputJson);
  const inputAliasWitness = globalThis.hostParsedInput;
  const decodedInput = safeParse(inputJson);
  delete globalThis.hostParsedInput;
  const previousReply = safeParse(previousReplyJson);
  const detachedReply = safeParse(replyJson);
  const hostModule = {exports: {host: true}};
  const cachedFixtureExports = Object.freeze({
    source_execution_count: 0,
    promise_completion: true,
    mode: decodedInput.mode,
    run: decodedInput.run || ''
  });
  const contextRunners = new WeakMap();
  let moduleWasIsolated = true;
  let nextTimerId = 1;
  const timers = new Map();
  const listenerRoots = [];
  let settled = false;
  let boundaryObserved = false;
  let completionValue = null;
  let completionFailure = null;
  let published = false;

  function sameRealmRun(source, scope) {
    let runner = contextRunners.get(scope);
    if (!runner) {
      const factory = Function('scope', 'return (function* () {'
        + 'with (scope) { while (true) { const source = yield; eval(source); } }'
        + '})()');
      runner = factory(scope);
      runner.next();
      contextRunners.set(scope, runner);
    }
    return runner.next(source).value;
  }

  const assertFacade = Object.freeze({
    equal(actual, expected, message) {
      if (actual !== expected) throw new Error(message || 'values were not equal');
    },
    ok(value, message) {
      if (!value) throw new Error(message || 'value was not truthy');
    }
  });
  const fsFacade = Object.freeze({
    readFileSync(file, encoding) {
      assertFacade.equal(encoding, 'utf8');
      const name = String(file).replaceAll('\\\\', '/').split('/').at(-1);
      if (name === 'request-input.json') return safeStringify(decodedInput);
      if (Object.hasOwn(webByBasename, name)) return webByBasename[name];
      throw new Error('Unknown fixture read ' + String(file));
    }
  });
  const vmFacade = Object.freeze({
    createContext(scope) { return scope; },
    runInContext(source, scope) { return sameRealmRun(source, scope); }
  });
  function runCommonJS(source, filename, requireFn) {
    const localModule = {exports: {}};
    moduleWasIsolated = localModule !== hostModule;
    const wrapper = Function(
      'require', 'module', 'exports', '__filename', '__dirname', source
    );
    wrapper(
      requireFn,
      localModule,
      localModule.exports,
      filename,
      filename.replace(/[/\\\\][^/\\\\]+$/, '')
    );
    return localModule.exports;
  }
  const domModule = runCommonJS(
    domFactorySource,
    domFactoryFilename,
    specifier => { throw new Error('Unknown DOM require ' + specifier); }
  );
  const createDOM = domModule.createDOM;
  function localRequire(specifier) {
    if (specifier === 'node:assert/strict') return assertFacade;
    if (specifier === 'node:fs') return fsFacade;
    if (specifier === 'node:vm') return vmFacade;
    if (specifier === './screenshot_dom.cjs') return {createDOM};
    throw new Error('Unknown fixture require ' + specifier);
  }
  localRequire.main = Object.freeze({kind: 'persistent-page-worker'});

  function schedule(callback, delay, interval) {
    const id = nextTimerId++;
    timers.set(id, {callback, due: localStartTime + Math.max(0, Number(delay) || 0), interval});
    return id;
  }
  globalThis.setTimeout = (callback, delay) => schedule(callback, delay, 0);
  globalThis.setInterval = (callback, delay) => schedule(callback, delay, Math.max(1, Number(delay) || 1));
  globalThis.setImmediate = callback => schedule(callback, 0, 0);
  globalThis.clearTimeout = id => timers.delete(id);
  globalThis.clearInterval = id => timers.delete(id);
  globalThis.clearImmediate = id => timers.delete(id);
  globalThis.console = Object.freeze({log() {}, info() {}, debug() {}, warn() {}, error() {}});
  globalThis.process = {argv: safeParse(argvJson), exitCode: 0};

  const requestManifest = safeParse(manifestJson);
  const page = requestManifest.pages[pageSelector];
  const dom = createDOM(page);
  const document = dom.document;
  const Element = dom.Element;
  const addEventListener = Element.prototype.addEventListener;
  const removeEventListener = Element.prototype.removeEventListener;
  Element.prototype.addEventListener = function(name, callback) {
    listenerRoots.push([this, name, callback]);
    return addEventListener.call(this, name, callback);
  };
  Element.prototype.removeEventListener = function(name, callback) {
    for (let index = listenerRoots.length - 1; index >= 0; index--) {
      const row = listenerRoots[index];
      if (row[0] === this && row[1] === name && row[2] === callback) listenerRoots.splice(index, 1);
    }
    return removeEventListener.call(this, name, callback);
  };
  globalThis.document = document;
  globalThis.__wingmanElement = Element;

  function safeField(reason, name, fallback) {
    try {
      const value = reason == null ? undefined : reason[name];
      return value == null ? fallback : safeString(value).slice(0, 8192);
    } catch (_error) {
      return '<unreadable ' + name + '>';
    }
  }
  function failure(reason) {
    if (reason === null) return {name: 'Error', message: 'null', stack: ''};
    if (typeof reason !== 'object' && typeof reason !== 'function') {
      return {name: 'Error', message: safeString(reason).slice(0, 8192), stack: ''};
    }
    return {
      name: safeField(reason, 'name', 'Error'),
      message: safeField(reason, 'message', '<unreadable failure>'),
      stack: safeField(reason, 'stack', '')
    };
  }

  (async () => {
    try {
      const fixtureExports = runCommonJS(programSource, fixtureFilename, localRequire);
      const fixtureCompletion = fixtureExports;
      const completion = await fixtureCompletion;
      completionValue = {
        ...completion,
        fresh_execution: true,
        process_retainable: true,
        realm_token: localRequestToken,
        input_detached: decodedInput !== inputAliasWitness,
        prior_reply_detached: detachedReply !== previousReply,
        module_export_isolated: moduleWasIsolated,
        dom_pristine: !Element.prototype.__wingmanPoison,
        poison_absent: !globalThis.__wingmanRealmPoison,
        cached_output_absent: !globalThis.__wingmanCachedOutput,
        decoded_input_value: decodedInput.nested ? decodedInput.nested.value : null,
        prior_reply_value: detachedReply.nested ? detachedReply.nested.value : null
      };
    } catch (error) {
      completionFailure = failure(error);
    }
    settled = true;
  })();

  function cleanup() {
    timers.clear();
    while (listenerRoots.length) {
      const [target, name, callback] = listenerRoots.pop();
      try { removeEventListener.call(target, name, callback); } catch (_error) {}
    }
    delete globalThis.document;
    delete globalThis.__wingmanElement;
    delete globalThis.__unresolved;
  }

  return function poll(now, mailboxJson) {
    if (published) throw new Error('double completion');
    const mailbox = safeParse(mailboxJson);
    if (mailbox.length && !completionFailure) completionFailure = mailbox[0];
    const due = [...timers.entries()].filter(([, timer]) => timer.due <= now);
    for (const [id, timer] of due) {
      if (!timers.has(id)) continue;
      if (timer.interval) timer.due = now + timer.interval;
      else timers.delete(id);
      try { timer.callback(); } catch (error) { completionFailure ||= failure(error); }
    }
    if (!settled) return null;
    if (!boundaryObserved) {
      boundaryObserved = true;
      return null;
    }
    cleanup();
    const failed = completionFailure !== null;
    const reply = {
      id: localRequestId,
      scenario: localRequestScenario,
      ok: !failed,
      duration_ms: Math.max(0, now - localStartTime),
      output: failed ? null : completionValue,
      error: failed ? completionFailure.message : '',
      stack: failed ? completionFailure.stack : '',
      diagnostics: [],
      cleanup: {
        host_timer_handles: 0,
        host_callbacks: 0,
        active_rejection_listeners: 0,
        pending_rejection_records: 0,
        retained_realms: 0
      }
    };
    published = true;
    return safeStringify(reply);
  };
})()
`;

const sharedContext = Object.freeze({kind: 'unsafe-shared-context-mutation'});
const cachedFixtureExports = Object.freeze({
  source_execution_count: 0,
  promise_completion: true,
  mode: 'realm',
  run: ''
});
let previousReplyJsonText = hostJsonStringify({nested: {value: 'clean'}});
let activeRequest = null;

function familyProtocolForScenario(scenario) {
  const qualificationPrefix = 'qualification/' + family + '/';
  if (scenario.startsWith(qualificationPrefix)) {
    const mode = scenario.slice(qualificationPrefix.length);
    return QUALIFICATION_MODES.has(mode) ? 'qualification' : null;
  }
  const prefix = BUSINESS_LABELS[family].find(candidate => scenario.startsWith(candidate));
  if (!prefix || scenario.length === prefix.length) return null;
  let protocol;
  if (family === 'saved-layouts') {
    if (prefix.endsWith('/page/')) protocol = 'saved-main';
    else if (prefix.endsWith('/owners/')) protocol = 'saved-owner';
    else if (prefix.endsWith('/capture/')) protocol = 'saved-capture';
    else protocol = 'saved-dev';
  } else {
    protocol = FAMILY_PROTOCOLS[family][0];
  }
  return SCENARIOS_BY_PROTOCOL[protocol].has(scenario.slice(prefix.length))
    ? protocol
    : null;
}

function validateRequest(request) {
  if (!request || hostGetPrototypeOf(request) !== Object.prototype ||
      !exactKeys(request, ['id', 'scenario', 'payload'])) {
    throw new TypeError('request envelope must contain id, scenario, payload');
  }
  if (!Number.isSafeInteger(request.id) || request.id <= 0) throw new TypeError('request id must be a positive safe integer');
  if (typeof request.scenario !== 'string' || !request.scenario) throw new TypeError('request scenario must be nonempty');
  if (!request.payload || hostGetPrototypeOf(request.payload) !== Object.prototype ||
      !exactKeys(request.payload, ['protocol', 'input'])) {
    throw new TypeError('request payload must contain protocol and input');
  }
  const expected = familyProtocolForScenario(request.scenario);
  if (expected === null) throw new TypeError('unknown or wrong-family scenario');
  if (request.payload.protocol !== expected) throw new TypeError('protocol did not match scenario');
  if (!request.payload.input || hostGetPrototypeOf(request.payload.input) !== Object.prototype) {
    throw new TypeError('request input must be an object');
  }
  assertFiniteJson(request.payload.input);
  if (expected === 'qualification') {
    const mode = request.payload.input.mode;
    if (!QUALIFICATION_MODES.has(mode)) throw new TypeError('unknown qualification scenario');
  }
  return request;
}

function buildFailureSerializer(slot) {
  return `(() => {
    const safeString = String;
    const reason = globalThis[${hostJsonStringify(slot)}];
    const field = (name, fallback) => {
      try {
        const value = reason == null ? undefined : reason[name];
        return value == null ? fallback : safeString(value).slice(0, 8192);
      } catch (_error) { return '<unreadable ' + name + '>'; }
    };
    try {
      if (reason === null) return JSON.stringify({name: 'Error', message: 'null', stack: ''});
      if (typeof reason !== 'object' && typeof reason !== 'function') {
        return JSON.stringify({name: 'Error', message: safeString(reason).slice(0, 8192), stack: ''});
      }
      return JSON.stringify({name: field('name', 'Error'), message: field('message', '<unreadable failure>'), stack: field('stack', '')});
    } finally {
      delete globalThis[${hostJsonStringify(slot)}];
    }
  })()`;
}

function parseBoundedFailureJson(serialized) {
  if (typeof serialized !== 'string' || serialized.length > 32768) throw new TypeError('failure serialization exceeded boundary');
  const value = hostJsonParse(serialized);
  if (!value || !exactKeys(value, ['name', 'message', 'stack']) ||
      !hostObjectKeys(value).every(key => typeof value[key] === 'string')) {
    throw new TypeError('failure serialization was invalid');
  }
  return value;
}

function serializeOpaqueVmFailure(runtime, reason) {
  const token = crypto.randomBytes(16).toString('hex');
  const slot = '__wingmanOpaqueFailure_' + token;
  runtime[slot] = reason;
  try {
    const serialized = vm.runInContext(buildFailureSerializer(slot), runtime);
    return parseBoundedFailureJson(serialized);
  } finally {
    delete runtime[slot];
  }
}

process.on('unhandledRejection', () => {
  if (activeRequest !== null) return;
  fatalProtocol('late unhandled rejection after published success');
});

function hostPrototypesClean() {
  return hostObjectKeys(Object.prototype).sort().join('\0') === cleanObjectPrototype &&
    hostObjectKeys(Array.prototype).sort().join('\0') === cleanArrayPrototype &&
    hostObjectKeys(Promise.prototype).sort().join('\0') === cleanPromisePrototype &&
    hostObjectKeys(Error.prototype).sort().join('\0') === cleanErrorPrototype;
}

function qualificationPage(input) {
  const requested = typeof input.page === 'string' ? input.page : FAMILY_PAGE_KEYS[family][0];
  const parsedManifest = hostJsonParse(manifestText);
  if (!hostHasOwn(parsedManifest.pages, requested)) throw new TypeError('unknown manifest page selector');
  return requested;
}

function argvFor(protocol, scenario) {
  const fixture = path.resolve(__dirname, PROGRAM_BY_PROTOCOL[protocol] || 'qualification.cjs');
  if (protocol === 'fleet-sharing') return [process.execPath, fixture, 'request-input.json', scenario.split('/').at(-1), webRoot];
  return [process.execPath, fixture, 'request-input.json', webRoot];
}

function directMutantReply(request, started, changes) {
  return hostJsonStringify({
    id: request.id,
    scenario: request.scenario,
    ok: true,
    duration_ms: Math.max(0, performance.now() - started),
    output: Object.assign({
      fresh_execution: true,
      process_retainable: true,
      realm_token: 'shared-context',
      source_execution_count: 0,
      promise_completion: true,
      input_detached: true,
      prior_reply_detached: true,
      module_export_isolated: true,
      dom_pristine: true,
      poison_absent: true,
      cached_output_absent: true,
      decoded_input_value: 'clean',
      prior_reply_value: 'clean'
    }, changes),
    error: '',
    stack: '',
    diagnostics: [],
    cleanup: ZERO_CLEANUP
  });
}

async function executeRequest(request) {
  const started = performance.now();
  const input = request.payload.input;
  const protocol = request.payload.protocol;
  const programSource = protocol === 'qualification'
    ? SYNTHETIC_PROGRAM
    : sourceRegistry[PROGRAM_BY_PROTOCOL[protocol]];
  if (typeof programSource !== 'string') throw new TypeError('program source unavailable');
  const context = vm.createContext(Object.create(null));
  if (!vm.isContext(context)) {
    return directMutantReply(request, started, {fresh_context: false});
  }
  const pageSelector = qualificationPage(input);
  const inputJson = hostJsonStringify(input);
  const sourceRegistryJson = hostJsonStringify(sourceRegistry);
  const webSourcesJson = hostJsonStringify(webRegistry);
  const previousReplyJson = previousReplyJsonText;
  const replyJson = hostJsonStringify({nested: {value: 'clean'}});
  const requestToken = crypto.randomBytes(16).toString('hex');
  const domRow = sourceRows.find(row => row.basename === 'screenshot_dom.cjs');
  const fixtureFilename = protocol === 'qualification'
    ? path.resolve(__dirname, 'qualification.cjs')
    : path.resolve(__dirname, PROGRAM_BY_PROTOCOL[protocol]);
  Object.assign(context, {
    argvJson: hostJsonStringify(argvFor(protocol, request.scenario)),
    domFactoryFilename: domRow.filename,
    domFactorySource: domRow.source,
    fixtureFilename,
    inputJson,
    manifestJson: manifestText,
    pageSelector,
    previousReplyJson,
    programSource,
    replyJson,
    requestId: request.id,
    requestScenario: request.scenario,
    requestToken,
    sourceRegistryJson,
    startTime: started,
    webSourcesJson
  });
  const poll = vm.runInContext(BOOTSTRAP, context, {filename: 'page-worker-bootstrap.vm.js'});
  for (const key of hostObjectKeys(context)) delete context[key];
  const rejectionMailbox = [];
  const captureRejection = reason => {
    rejectionMailbox.push(serializeOpaqueVmFailure(context, reason));
  };
  process.prependListener('unhandledRejection', captureRejection);
  activeRequest = {runtime: context};
  try {
    while (true) {
      let serialized;
      try {
        serialized = poll(
          performance.now(), hostJsonStringify(rejectionMailbox.splice(0))
        );
      } catch (error) {
        activeRequest = null;
        fatalProtocol('request poll failed', error);
        return null;
      }
      if (serialized !== null) {
        activeRequest = null;
        process.removeListener('unhandledRejection', captureRejection);
        if (typeof serialized !== 'string') {
          fatalProtocol('request poll returned a non-string');
          return null;
        }
        const detached = hostJsonParse(serialized);
        assertFiniteJson(detached);
        if (!hostPrototypesClean()) {
          fatalProtocol('request poisoned host prototypes');
          return null;
        }
        if (targetPaths.some(file => require.cache[file]) ||
            module.children.some(child => targetPathSet.has(child.filename))) {
          fatalProtocol('request retained a target module');
          return null;
        }
        if (detached.ok && detached.output && typeof detached.output === 'object') {
          detached.output.host_prototypes_clean = true;
          detached.output.fresh_context = true;
          if (input.mode === 'inventory') detached.output.inventory = structuralReceipt;
        }
        previousReplyJsonText = hostJsonStringify(detached);
        return previousReplyJsonText;
      }
      await new Promise(resolve => hostSetImmediate(resolve));
    }
  } finally {
    activeRequest = null;
    process.removeListener('unhandledRejection', captureRejection);
  }
}

async function serveLine(line) {
  let request;
  try {
    request = hostJsonParse(line);
  } catch (error) {
    fatalProtocol('malformed request JSON', error);
    return;
  }
  try {
    validateRequest(request);
  } catch (error) {
    fatalProtocol('invalid request', error);
    return;
  }
  const serialized = await executeRequest(request);
  if (serialized === null) return;
  process.stdout.write(serialized + '\n', () => {
    if (request.payload.input.mode === 'late-success') {
      setTimeout(() => {
        process.stderr.write('late unhandled rejection after published success\n', () => process.exit(71));
      }, 10);
    }
  });
  await new Promise(resolve => hostSetImmediate(resolve));
}

const inputLines = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
(async () => {
  for await (const line of inputLines) {
    await serveLine(line);
  }
})().catch(error => fatalProtocol('worker read loop failed', error));
