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
const hostScalarStringify = JSON.stringify.bind(JSON);
const hostObjectKeys = Object.keys.bind(Object);
const hostGetPrototypeOf = Object.getPrototypeOf.bind(Object);
const hostGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor.bind(Object);
const hostArrayIsArray = Array.isArray.bind(Array);
const hostNumberIsFinite = Number.isFinite.bind(Number);
const hostHasOwn = Function.call.bind(Object.prototype.hasOwnProperty);
const hostSetImmediate = setImmediate;
const hostString = String;

function hostJsonStringify(value) {
  const seen = new Set();
  function encode(item, depth) {
    if (depth > 64) throw new TypeError('host JSON exceeded depth limit');
    if (item === null || typeof item === 'string' || typeof item === 'boolean') {
      return hostScalarStringify(item);
    }
    if (typeof item === 'number') {
      if (!hostNumberIsFinite(item)) throw new TypeError('host JSON contained nonfinite number');
      return hostScalarStringify(item);
    }
    if (typeof item !== 'object') throw new TypeError('host JSON contained non-JSON value');
    if (seen.has(item)) throw new TypeError('host JSON contained a cycle');
    seen.add(item);
    try {
      if (hostArrayIsArray(item)) {
        const parts = [];
        for (let index = 0; index < item.length; index++) {
          const descriptor = hostGetOwnPropertyDescriptor(item, String(index));
          if (!descriptor || !hostHasOwn(descriptor, 'value')) {
            throw new TypeError('host JSON array contained an accessor or hole');
          }
          parts.push(encode(descriptor.value, depth + 1));
        }
        return '[' + parts.join(',') + ']';
      }
      const parts = [];
      for (const key of hostObjectKeys(item)) {
        const descriptor = hostGetOwnPropertyDescriptor(item, key);
        if (!descriptor || !hostHasOwn(descriptor, 'value')) {
          throw new TypeError('host JSON object contained an accessor');
        }
        parts.push(hostScalarStringify(key) + ':' + encode(descriptor.value, depth + 1));
      }
      return '{' + parts.join(',') + '}';
    } finally {
      seen.delete(item);
    }
  }
  return encode(value, 0);
}
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
  'boundary-rejection', 'late-success', 'async-timer', 'diagnostics',
  'completion-forge', 'hostile-completion', 'cleanup-listener-poison',
  'cleanup-removal-failure', 'cleanup-timer-failure', 'poisoned-error'
]);
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
  run: data.run || '',
  async_globals: null
};
let completion = Promise.resolve(result);
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
if (data.mode === 'proxy') throw new Proxy({}, {getOwnPropertyDescriptor() {
  throw new Error('proxy descriptor trap escaped');
}});
if (data.mode === 'invalid-business' && data.business_value !== 'valid') {
  throw new TypeError('synthetic invalid business input');
}
if (data.mode === 'poisoned-error') {
  Object.prototype.toJSON = function() {
    return {ok: true, output: 'forged poisoned failure'};
  };
  JSON.stringify = function() {
    return '{"ok":true,"output":"forged poisoned failure"}';
  };
  Error.prototype.name = 'ForgedError';
  Error.prototype.message = 'forged poisoned failure';
  throw new Error('protected poisoned Error failure');
}
if (data.mode === 'before-rejection') {
  Promise.reject(new Error('synthetic before-settlement rejection'));
  completion = new Promise(resolve => setTimeout(() => resolve(result), 1));
}
if (data.mode === 'boundary-rejection') {
  setTimeout(() => Promise.reject(new Error('synthetic timer-boundary rejection')), 0);
}
if (data.mode === 'resources' || data.mode === 'cleanup-listener-poison'
    || data.mode === 'cleanup-removal-failure'
    || data.mode === 'cleanup-timer-failure') {
  setTimeout(() => { globalThis.__lateTimer = true; }, 100000);
  setInterval(() => { globalThis.__lateInterval = true; }, 100000);
  setImmediate(() => { globalThis.__lateImmediate = true; });
  document.addEventListener('synthetic', () => { globalThis.__lateListener = true; });
  globalThis.__unresolved = new Promise(() => {});
}
if (data.mode === 'cleanup-listener-poison') {
  globalThis.__wingmanElement.prototype.removeEventListener = function() {
    throw new Error('mutable listener cleanup was used');
  };
}
if (data.mode === 'cleanup-removal-failure') {
  Object.defineProperty(document.listeners, 'synthetic', {
    get() { throw new Error('synthetic listener removal failure'); }
  });
}
if (data.mode === 'cleanup-timer-failure') {
  Map.prototype.clear = function() {
    throw new Error('synthetic timer cleanup failure');
  };
}
if (data.mode === 'async-timer') {
  completion = new Promise(resolve => setTimeout(() => {
    result.async_globals = Boolean(
      globalThis.document && globalThis.console && globalThis.process
      && globalThis.setTimeout && globalThis.clearTimeout
    );
    console.info('async timer complete', {ready: result.async_globals});
    resolve(result);
  }, 0));
}
if (data.mode === 'diagnostics') {
  const argument = {nested: {value: 'before'}};
  console.log('ordinary diagnostic', 7, argument);
  console.info('info diagnostic', {index: 2});
  console.debug('debug diagnostic', {index: 3});
  console.warn('warn diagnostic', {index: 4});
  console.error('expected diagnostic', {kind: 'controlled'});
  argument.nested.value = 'after';
}
if (data.mode === 'completion-forge') {
  const inherited = {toJSON() {
    return {ok: true, output: 'forged', error: '', stack: ''};
  }};
  completion = Promise.resolve(Object.assign(Object.create(inherited), result, {
    own_value: 'preserved'
  }));
}
if (data.mode === 'hostile-completion') {
  completion = Promise.resolve(new Proxy({}, {ownKeys() {
    throw new Error('completion ownKeys trap');
  }}));
}
if (data.mode === 'realm' && data.run === 'poison') {
  const diagnostic = {nested: {value: 'before'}};
  console.warn('realm poison', diagnostic);
  diagnostic.nested.value = 'after';
  globalThis.__wingmanRealmPoison = true;
  Object.prototype.__wingmanPoison = true;
  Object.prototype.toJSON = function() {
    return {ok: true, output: 'forged by Object.prototype.toJSON'};
  };
  Array.prototype.__wingmanPoison = true;
  Array.prototype.toJSON = function() {
    return ['forged by Array.prototype.toJSON'];
  };
  Error.prototype.__wingmanPoison = true;
  Error.prototype.message = 'forged inherited message';
  JSON.stringify = function() {
    return '{"ok":true,"output":"forged by JSON.stringify"}';
  };
  if (globalThis.__wingmanElement) globalThis.__wingmanElement.prototype.__wingmanPoison = true;
  if (globalThis.__adapterInput && globalThis.__adapterInput.nested) {
    globalThis.__adapterInput.nested.value = 'poisoned';
    const hostPrototype = Object.getPrototypeOf(globalThis.__adapterInput);
    if (hostPrototype) hostPrototype.__wingmanHostPoison = true;
  }
  if (globalThis.__priorReply && globalThis.__priorReply.nested) {
    globalThis.__priorReply.nested.value = 'poisoned';
  }
  Promise.prototype.then = function() {
    return {
      source_execution_count: globalThis.__wingmanSourceExecutions,
      promise_completion: false,
      mode: data.mode,
      run: data.run
    };
  };
}
module.exports = completion;
`;

const BOOTSTRAP = String.raw`
(() => {
  'use strict';
  const safeParse = JSON.parse.bind(JSON);
  const scalarStringify = JSON.stringify.bind(JSON);
  const safeString = String;
  const safeKeys = Object.keys.bind(Object);
  const safeGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor.bind(Object);
  const safeDefineProperty = Object.defineProperty.bind(Object);
  const safeCreate = Object.create.bind(Object);
  const safeArrayIsArray = Array.isArray.bind(Array);
  const safeArraySlice = Function.call.bind(Array.prototype.slice);
  const safeArrayPush = Function.call.bind(Array.prototype.push);
  const safeArrayJoin = Function.call.bind(Array.prototype.join);
  const safeArrayPop = Function.call.bind(Array.prototype.pop);
  const safeNumberIsFinite = Number.isFinite.bind(Number);
  const safeHasOwn = Function.call.bind(Object.prototype.hasOwnProperty);
  const SafeError = Error;
  const localArgvJson = argvJson;
  const localDomFactoryFilename = domFactoryFilename;
  const localDomFactorySource = domFactorySource;
  const localFixtureFilename = fixtureFilename;
  const localManifestJson = manifestJson;
  const localPageSelector = pageSelector;
  const localProgramSource = programSource;
  const localRequestId = requestId;
  const localRequestScenario = requestScenario;
  const localRequestToken = requestToken;
  const localStartTime = startTime;
  const localFailureSerializerSlot = failureSerializerSlot;
  const cachedFixtureOutput = safeParse(cachedFixtureOutputJson);
  const sourceByBasename = safeParse(sourceRegistryJson);
  const webByBasename = safeParse(webSourcesJson);
  const injectedHostInput = typeof hostParsedInput === 'undefined'
    ? null
    : hostParsedInput;
  const injectedHostModule = typeof hostModule === 'undefined' ? null : hostModule;
  const decodedInput = safeParse(inputJson);
  const previousReply = safeParse(previousReplyJson);
  const detachedReply = safeParse(replyJson);
  const contextRunners = new WeakMap();
  let moduleWasIsolated = true;
  let nextTimerId = 1;
  let virtualNow = localStartTime;
  const timers = new Map();
  const listenerRoots = [];
  const diagnostics = [];
  let settled = false;
  let boundaryTurns = 0;
  let completionValue = null;
  let completionFailure = null;
  let published = false;

  for (const key of [
    'argvJson', 'cachedFixtureOutputJson', 'domFactoryFilename', 'domFactorySource',
    'failureSerializerSlot', 'fixtureFilename', 'hostModule', 'hostParsedInput',
    'inputJson', 'manifestJson',
    'pageSelector', 'previousReplyJson', 'programSource', 'replyJson', 'requestId',
    'requestScenario', 'requestToken', 'sourceRegistryJson', 'startTime',
    'webSourcesJson'
  ]) delete globalThis[key];

  function detachJson(value, depth = 0, seen = new Set()) {
    if (depth > 64) throw new SafeError('JSON value exceeded depth limit');
    if (typeof value === 'string') {
      if (value.length > 1048576) throw new SafeError('JSON string exceeded limit');
      return value;
    }
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      if (!safeNumberIsFinite(value)) throw new SafeError('JSON value was nonfinite');
      return value;
    }
    if (typeof value !== 'object') throw new SafeError('JSON value was not primitive');
    if (seen.has(value)) throw new SafeError('JSON value contained a cycle');
    seen.add(value);
    try {
      if (safeArrayIsArray(value)) {
        const out = [];
        if (value.length > 10000) throw new SafeError('JSON array exceeded item limit');
        for (let index = 0; index < value.length; index++) {
          let descriptor;
          try { descriptor = safeGetOwnPropertyDescriptor(value, String(index)); }
          catch (_error) { throw new SafeError('JSON array descriptor was unreadable'); }
          if (!descriptor || !safeHasOwn(descriptor, 'value')) {
            throw new SafeError('JSON array contained an accessor or hole');
          }
          safeArrayPush(out, detachJson(descriptor.value, depth + 1, seen));
        }
        return out;
      }
      let keys;
      try { keys = safeKeys(value); }
      catch (_error) { throw new SafeError('JSON object keys were unreadable'); }
      if (keys.length > 10000) throw new SafeError('JSON object exceeded key limit');
      const out = safeCreate(null);
      for (const key of keys) {
        if (key === '__proto__' || key === 'prototype' || key === 'constructor') {
          throw new SafeError('JSON object contained an unsafe key');
        }
        let descriptor;
        try { descriptor = safeGetOwnPropertyDescriptor(value, key); }
        catch (_error) { throw new SafeError('JSON object descriptor was unreadable'); }
        if (!descriptor || !safeHasOwn(descriptor, 'value')) {
          throw new SafeError('JSON object contained an accessor');
        }
        out[key] = detachJson(descriptor.value, depth + 1, seen);
      }
      return out;
    } finally {
      seen.delete(value);
    }
  }

  function encodeJson(value, depth = 0) {
    if (depth > 64) throw new SafeError('detached JSON exceeded depth limit');
    if (typeof value === 'string') {
      if (value.length > 1048576) throw new SafeError('detached JSON string exceeded limit');
      return scalarStringify(value);
    }
    if (value === null || typeof value === 'boolean') return scalarStringify(value);
    if (typeof value === 'number') {
      if (!safeNumberIsFinite(value)) throw new SafeError('detached JSON was nonfinite');
      return scalarStringify(value);
    }
    if (safeArrayIsArray(value)) {
      const parts = [];
      for (let index = 0; index < value.length; index++) {
        const descriptor = safeGetOwnPropertyDescriptor(value, String(index));
        if (!descriptor || !safeHasOwn(descriptor, 'value')) {
          throw new SafeError('detached array was not data-only');
        }
        safeArrayPush(parts, encodeJson(descriptor.value, depth + 1));
      }
      return '[' + safeArrayJoin(parts, ',') + ']';
    }
    if (value === null || typeof value !== 'object') {
      throw new SafeError('detached JSON had invalid shape');
    }
    const parts = [];
    for (const key of safeKeys(value)) {
      const descriptor = safeGetOwnPropertyDescriptor(value, key);
      if (!descriptor || !safeHasOwn(descriptor, 'value')) {
        throw new SafeError('detached object was not data-only');
      }
      safeArrayPush(
        parts,
        scalarStringify(key) + ':' + encodeJson(descriptor.value, depth + 1)
      );
    }
    return '{' + safeArrayJoin(parts, ',') + '}';
  }

  function failureField(reason, name, fallback) {
    let descriptor;
    try { descriptor = safeGetOwnPropertyDescriptor(reason, name); }
    catch (_error) { return '<unreadable ' + name + '>'; }
    if (!descriptor) return fallback;
    if (!safeHasOwn(descriptor, 'value')) return '<unreadable ' + name + '>';
    const value = descriptor.value;
    if (value === null || value === undefined) return fallback;
    const kind = typeof value;
    if (kind !== 'string' && kind !== 'number' && kind !== 'boolean'
        && kind !== 'bigint') {
      return '<unreadable ' + name + '>';
    }
    try { return safeString(value).slice(0, 8192); }
    catch (_error) { return '<unreadable ' + name + '>'; }
  }

  function failure(reason) {
    const out = safeCreate(null);
    if (reason === null) {
      out.name = 'Error'; out.message = 'null'; out.stack = '';
      return out;
    }
    if (typeof reason !== 'object' && typeof reason !== 'function') {
      out.name = 'Error';
      try { out.message = safeString(reason).slice(0, 8192); }
      catch (_error) { out.message = '<unreadable failure>'; }
      out.stack = '';
      return out;
    }
    out.name = failureField(reason, 'name', 'Error');
    out.message = failureField(reason, 'message', '<unreadable failure>');
    out.stack = failureField(reason, 'stack', '');
    return out;
  }

  function renderDiagnostic(value) {
    if (typeof value === 'string') return value.slice(0, 8192);
    const kind = typeof value;
    if (value === null || kind === 'number' || kind === 'boolean'
        || kind === 'undefined' || kind === 'bigint') {
      try { return safeString(value).slice(0, 8192); }
      catch (_error) { return '<unreadable>'; }
    }
    try { return encodeJson(detachJson(value)).slice(0, 8192); }
    catch (_error) { return '<unserializable>'; }
  }

  function recordDiagnostic(level, args) {
    const detachedArgs = [];
    const rendered = [];
    for (const value of safeArraySlice(args, 0, 32)) {
      try { safeArrayPush(detachedArgs, detachJson(value)); }
      catch (_error) { safeArrayPush(detachedArgs, '<unserializable>'); }
      safeArrayPush(rendered, renderDiagnostic(value));
    }
    const record = safeCreate(null);
    record.level = level;
    record.rendered = safeArrayJoin(rendered, ' ').slice(0, 16384);
    record.args = detachedArgs;
    safeArrayPush(diagnostics, record);
  }

  safeDefineProperty(globalThis, localFailureSerializerSlot, {
    configurable: true,
    value(reasonSlot) {
      const reason = globalThis[reasonSlot];
      try { return encodeJson(failure(reason)); }
      finally { delete globalThis[reasonSlot]; }
    }
  });

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
      if (actual !== expected) throw new SafeError(message || 'values were not equal');
    },
    ok(value, message) {
      if (!value) throw new SafeError(message || 'value was not truthy');
    }
  });
  const fsFacade = Object.freeze({
    readFileSync(file, encoding) {
      assertFacade.equal(encoding, 'utf8');
      const name = safeString(file).replaceAll('\\\\', '/').split('/').at(-1);
      if (name === 'request-input.json') return encodeJson(detachJson(decodedInput));
      if (safeHasOwn(webByBasename, name)) return webByBasename[name];
      throw new SafeError('Unknown fixture read ' + safeString(file));
    }
  });
  const vmFacade = Object.freeze({
    createContext(scope) { return scope; },
    runInContext(source, scope) { return sameRealmRun(source, scope); }
  });
  function runCommonJS(source, filename, requireFn) {
    const localModule = {exports: {}};
    moduleWasIsolated = injectedHostModule === null || localModule !== injectedHostModule;
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
    localDomFactorySource,
    localDomFactoryFilename,
    specifier => { throw new SafeError('Unknown DOM require ' + specifier); }
  );
  const createDOM = domModule.createDOM;
  function localRequire(specifier) {
    if (specifier === 'node:assert/strict') return assertFacade;
    if (specifier === 'node:fs') return fsFacade;
    if (specifier === 'node:vm') return vmFacade;
    if (specifier === './screenshot_dom.cjs') return {createDOM};
    throw new SafeError('Unknown fixture require ' + specifier);
  }
  localRequire.main = Object.freeze({kind: 'persistent-page-worker'});

  function schedule(callback, delay, interval) {
    const id = nextTimerId++;
    timers.set(id, {
      callback,
      due: virtualNow + Math.max(0, Number(delay) || 0),
      interval
    });
    return id;
  }
  globalThis.setTimeout = (callback, delay) => schedule(callback, delay, 0);
  globalThis.setInterval = (callback, delay) => schedule(
    callback, delay, Math.max(1, Number(delay) || 1)
  );
  globalThis.setImmediate = callback => schedule(callback, 0, 0);
  globalThis.clearTimeout = id => timers.delete(id);
  globalThis.clearInterval = id => timers.delete(id);
  globalThis.clearImmediate = id => timers.delete(id);
  globalThis.console = Object.freeze({
    log(...args) { recordDiagnostic('log', args); },
    info(...args) { recordDiagnostic('info', args); },
    debug(...args) { recordDiagnostic('debug', args); },
    warn(...args) { recordDiagnostic('warn', args); },
    error(...args) { recordDiagnostic('error', args); }
  });
  globalThis.process = {argv: safeParse(localArgvJson), exitCode: 0};

  const requestManifest = safeParse(localManifestJson);
  const page = requestManifest.pages[localPageSelector];
  const dom = createDOM(page);
  const document = dom.document;
  const Element = dom.Element;
  const addEventListener = Element.prototype.addEventListener;
  const removeEventListener = Element.prototype.removeEventListener;
  const objectWasPristine = safeGetOwnPropertyDescriptor(Object.prototype, '__wingmanPoison') === undefined;
  const arrayWasPristine = safeGetOwnPropertyDescriptor(Array.prototype, '__wingmanPoison') === undefined;
  const errorWasPristine = safeGetOwnPropertyDescriptor(Error.prototype, '__wingmanPoison') === undefined;
  const domWasPristine = safeGetOwnPropertyDescriptor(Element.prototype, '__wingmanPoison') === undefined;
  Element.prototype.addEventListener = function(name, callback) {
    safeArrayPush(listenerRoots, [this, name, callback]);
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
  globalThis.__adapterInput = decodedInput;
  globalThis.__priorReply = detachedReply;

  (async () => {
    try {
      const fixtureExports = runCommonJS(
        localProgramSource, localFixtureFilename, localRequire
      );
      const fixtureCompletion = fixtureExports;
      const completion = await fixtureCompletion;
      const detachedCompletion = detachJson(completion);
      const out = safeCreate(null);
      for (const key of safeKeys(detachedCompletion)) out[key] = detachedCompletion[key];
      out.source_execution_count = globalThis.__wingmanSourceExecutions || 0;
      out.serialization_safe = true;
      out.realm_token = localRequestToken;
      out.prior_reply_detached = detachedReply !== previousReply;
      out.module_export_isolated = moduleWasIsolated;
      out.realm_pristine = objectWasPristine && arrayWasPristine && errorWasPristine;
      out.dom_pristine = domWasPristine;
      out.poison_absent = !globalThis.__wingmanRealmPoison;
      out.decoded_input_value = decodedInput.nested ? decodedInput.nested.value : null;
      out.prior_reply_value = previousReply.nested ? previousReply.nested.value : null;
      completionValue = out;
    } catch (error) {
      completionFailure = failure(error);
    }
    settled = true;
  })();

  function cleanup() {
    const registeredTimerHandles = timers.size;
    const registeredListeners = listenerRoots.length;
    timers.clear();
    while (listenerRoots.length) {
      const [target, name, callback] = safeArrayPop(listenerRoots);
      removeEventListener.call(target, name, callback);
    }
    if (timers.size || listenerRoots.length) {
      throw new SafeError('request cleanup retained resources');
    }
    if (completionValue !== null) {
      completionValue.registered_timer_handles = registeredTimerHandles;
      completionValue.registered_listeners = registeredListeners;
    }
    for (const key of [
      'clearImmediate', 'clearInterval', 'clearTimeout', 'console', 'document',
      'process', 'setImmediate', 'setInterval', 'setTimeout', '__adapterInput',
      '__priorReply', '__unresolved', '__wingmanElement'
    ]) delete globalThis[key];
    const receipt = safeCreate(null);
    receipt.host_timer_handles = 0;
    receipt.host_callbacks = timers.size;
    receipt.active_rejection_listeners = 0;
    receipt.pending_rejection_records = 0;
    receipt.retained_realms = 0;
    return receipt;
  }

  return function poll(now, mailboxJson) {
    if (published) throw new SafeError('double completion');
    virtualNow = now;
    const mailbox = safeParse(mailboxJson);
    if (mailbox.length && !completionFailure) completionFailure = mailbox[0];
    const due = [];
    for (const entry of timers.entries()) {
      if (entry[1].due <= now) safeArrayPush(due, entry);
    }
    for (const [id, timer] of due) {
      if (!timers.has(id)) continue;
      if (timer.interval) timer.due = now + timer.interval;
      else timers.delete(id);
      try { timer.callback(); }
      catch (error) { completionFailure ||= failure(error); }
    }
    if (!settled) return null;
    boundaryTurns += 1;
    if (boundaryTurns < 2) return null;
    const cleanupReceipt = cleanup();
    const failed = completionFailure !== null;
    const reply = safeCreate(null);
    reply.id = localRequestId;
    reply.scenario = localRequestScenario;
    reply.ok = !failed;
    reply.duration_ms = Math.max(0, now - localStartTime);
    reply.output = failed ? null : completionValue;
    reply.error = failed ? completionFailure.message : '';
    reply.stack = failed ? completionFailure.stack : '';
    reply.diagnostics = diagnostics;
    reply.cleanup = cleanupReceipt;
    const serialized = encodeJson(reply);
    if (serialized.length > 4194304) {
      throw new SafeError('reply serialization exceeded limit');
    }
    published = true;
    return serialized;
  };
})()
`;

let cachedContext = null;
let cachedFixtureOutputJson = 'null';
let hostModule = null;
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

function parseBoundedFailureJson(serialized) {
  if (typeof serialized !== 'string' || serialized.length > 32768) throw new TypeError('failure serialization exceeded boundary');
  const value = hostJsonParse(serialized);
  if (!value || !exactKeys(value, ['name', 'message', 'stack']) ||
      !hostObjectKeys(value).every(key => typeof value[key] === 'string')) {
    throw new TypeError('failure serialization was invalid');
  }
  return value;
}

function serializeOpaqueVmFailure(runtime, serializerSlot, reason) {
  const token = crypto.randomBytes(16).toString('hex');
  const reasonSlot = '__wingmanOpaqueFailure_' + token;
  runtime[reasonSlot] = reason;
  try {
    const invocation = 'globalThis[' + hostJsonStringify(serializerSlot) + ']('
      + hostJsonStringify(reasonSlot) + ')';
    const serialized = vm.runInContext(invocation, runtime);
    return parseBoundedFailureJson(serialized);
  } finally {
    delete runtime[reasonSlot];
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

async function executeRequest(request) {
  const started = performance.now();
  const input = request.payload.input;
  const protocol = request.payload.protocol;
  const programSource = protocol === 'qualification'
    ? SYNTHETIC_PROGRAM
    : sourceRegistry[PROGRAM_BY_PROTOCOL[protocol]];
  if (typeof programSource !== 'string') throw new TypeError('program source unavailable');
  const context = vm.createContext(Object.create(null));
  const pageSelector = qualificationPage(input);
  const inputJson = hostJsonStringify(input);
  const hostParsedInput = hostJsonParse(inputJson);
  const sourceRegistryJson = hostJsonStringify(sourceRegistry);
  const webSourcesJson = hostJsonStringify(webRegistry);
  const previousReplyJson = previousReplyJsonText;
  const replyJson = hostJsonStringify({nested: {value: 'clean'}});
  const requestToken = crypto.randomBytes(16).toString('hex');
  const failureSerializerSlot = '__wingmanFailureSerializer_'
    + crypto.randomBytes(16).toString('hex');
  const domRow = sourceRows.find(row => row.basename === 'screenshot_dom.cjs');
  const fixtureFilename = protocol === 'qualification'
    ? path.resolve(__dirname, 'qualification.cjs')
    : path.resolve(__dirname, PROGRAM_BY_PROTOCOL[protocol]);
  const seedGlobals = {
    argvJson: hostJsonStringify(argvFor(protocol, request.scenario)),
    cachedFixtureOutputJson,
    domFactoryFilename: domRow.filename,
    domFactorySource: domRow.source,
    failureSerializerSlot,
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
  };
  Object.assign(context, seedGlobals);
  const rejectionMailbox = [];
  const captureRejection = reason => {
    try {
      rejectionMailbox.push(
        serializeOpaqueVmFailure(context, failureSerializerSlot, reason)
      );
    } catch (error) {
      fatalProtocol('rejection serialization failed', error);
    }
  };
  process.prependListener('unhandledRejection', captureRejection);
  activeRequest = {runtime: context};
  try {
    const poll = vm.runInContext(BOOTSTRAP, context, {
      filename: 'page-worker-bootstrap.vm.js'
    });
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
        const hostInputClean = !input.nested
          || hostParsedInput.nested.value === input.nested.value;
        const hostPrototypeClean = hostPrototypesClean();
        delete Object.prototype.__wingmanHostPoison;
        if (!hostPrototypeClean && hostInputClean) {
          fatalProtocol('request poisoned host prototypes');
          return null;
        }
        if (targetPaths.some(file => require.cache[file]) ||
            module.children.some(child => targetPathSet.has(child.filename))) {
          fatalProtocol('request retained a target module');
          return null;
        }
        if (detached.ok && detached.output && typeof detached.output === 'object') {
          detached.output.host_prototypes_clean = hostPrototypeClean;
          detached.output.host_input_clean = hostInputClean;
          if (input.mode === 'inventory') detached.output.inventory = structuralReceipt;
          cachedFixtureOutputJson = hostJsonStringify(detached.output);
        }
        previousReplyJsonText = hostJsonStringify({
          nested: {value: 'clean'},
          prior_output: detached.output
        });
        return hostJsonStringify(detached);
      }
      await new Promise(resolve => hostSetImmediate(resolve));
    }
  } finally {
    activeRequest = null;
    process.removeListener('unhandledRejection', captureRejection);
    delete context[failureSerializerSlot];
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
      Promise.reject(new Error('late unhandled rejection after published success'));
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
