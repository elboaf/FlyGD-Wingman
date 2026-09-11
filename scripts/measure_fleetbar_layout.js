#!/usr/bin/env node
'use strict';

const childProcess = require('node:child_process');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, 'wingman', 'web');
const WIDTHS = [420, 500, 720];
const VIEWPORT_HEIGHT = 900;
const READY_TIMEOUT_MS = 15000;
const EPSILON = 1;

function parseArgs(argv) {
  const args = { chrome: null, proof: null };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--chrome') {
      if (!argv[i + 1]) throw new Error('--chrome needs a path');
      args.chrome = argv[i + 1];
      i += 1;
      continue;
    }
    if (argv[i] === '--prove') {
      if (!argv[i + 1]) throw new Error('--prove needs overflow or emphasis');
      args.proof = argv[i + 1];
      i += 1;
      continue;
    }
    throw new Error('Unknown argument: ' + argv[i]);
  }
  if (args.proof && args.proof !== 'overflow' && args.proof !== 'emphasis') {
    throw new Error('--prove must be overflow or emphasis');
  }
  return args;
}

function pathExists(target) {
  try {
    fs.accessSync(target, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function discoverChrome(explicitPath) {
  const candidates = [];
  if (explicitPath) candidates.push(explicitPath);
  candidates.push(
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/opt/google/chrome/chrome'
  );
  const which = name => {
    try {
      const found = childProcess.spawnSync('which', [name], {
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'],
      });
      if (found.status === 0) {
        return found.stdout.trim().split(/\r?\n/)[0] || null;
      }
    } catch {
      return null;
    }
    return null;
  };
  for (const name of ['google-chrome', 'chromium', 'chromium-browser']) {
    const found = which(name);
    if (found) candidates.push(found);
  }
  for (const candidate of candidates) {
    if (candidate && pathExists(candidate)) return path.resolve(candidate);
  }
  throw new Error('Could not find a Chrome/Chromium executable');
}

function httpJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => { body += chunk; });
      response.on('end', () => {
        if (response.statusCode !== 200) {
          reject(new Error('HTTP ' + response.statusCode + ' from ' + url + ': ' + body));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(new Error('Bad JSON from ' + url + ': ' + error.message));
        }
      });
    });
    req.on('error', reject);
  });
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function startServer(rootDir) {
  const server = http.createServer(async (request, response) => {
    try {
      const rawUrl = new URL(request.url || '/', 'http://127.0.0.1');
      let pathname = decodeURIComponent(rawUrl.pathname);
      if (pathname === '/') pathname = '/fleetbar.html';
      const resolved = path.resolve(rootDir, '.' + pathname);
      if (resolved !== rootDir && !resolved.startsWith(rootDir + path.sep)) {
        response.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('Forbidden');
        return;
      }
      let stat;
      try {
        stat = await fsp.stat(resolved);
      } catch {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('Not found');
        return;
      }
      if (!stat.isFile()) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('Not found');
        return;
      }
      const contentType = {
        '.css': 'text/css; charset=utf-8',
        '.gif': 'image/gif',
        '.html': 'text/html; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8',
        '.png': 'image/png',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.woff2': 'font/woff2',
      }[path.extname(resolved)] || 'application/octet-stream';
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Length': stat.size,
        'Content-Type': contentType,
      });
      fs.createReadStream(resolved).pipe(response);
    } catch (error) {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end(String(error && error.stack || error));
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Could not read loopback server address');
  }
  return {
    server,
    baseUrl: 'http://127.0.0.1:' + address.port,
  };
}

async function stopServer(server) {
  if (!server) return;
  await new Promise(resolve => server.close(() => resolve()));
}

function spawnChrome(chromePath, profileDir) {
  const stderr = [];
  const stdout = [];
  const browser = childProcess.spawn(chromePath, [
    '--headless=new',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-sync',
    '--metrics-recording-only',
    '--mute-audio',
    '--no-default-browser-check',
    '--no-first-run',
    '--remote-debugging-port=0',
    '--user-data-dir=' + profileDir,
    'about:blank',
  ], {
    cwd: ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const capture = bucket => chunk => {
    bucket.push(String(chunk));
    if (bucket.length > 40) bucket.shift();
  };
  if (browser.stdout) browser.stdout.on('data', capture(stdout));
  if (browser.stderr) browser.stderr.on('data', capture(stderr));
  return { browser, stdout, stderr };
}

async function waitForDevTools(profileDir, browser, stderrLines) {
  const marker = path.join(profileDir, 'DevToolsActivePort');
  const start = Date.now();
  while (Date.now() - start < READY_TIMEOUT_MS) {
    if (browser.exitCode !== null) {
      throw new Error('Chrome exited before DevTools opened\n' + stderrLines.join(''));
    }
    try {
      const text = await fsp.readFile(marker, 'utf8');
      const lines = text.trim().split(/\r?\n/);
      if (lines.length >= 2) {
        const port = Number(lines[0]);
        if (Number.isFinite(port) && port > 0) {
          return {
            port,
            browserPath: lines[1],
          };
        }
      }
    } catch {
      // Keep polling.
    }
    await delay(50);
  }
  throw new Error('Timed out waiting for DevToolsActivePort\n' + stderrLines.join(''));
}

async function waitForPageTarget(port) {
  const start = Date.now();
  while (Date.now() - start < READY_TIMEOUT_MS) {
    const targets = await httpJson('http://127.0.0.1:' + port + '/json/list');
    const page = Array.isArray(targets)
      ? targets.find(target => target && target.type === 'page' && target.webSocketDebuggerUrl)
      : null;
    if (page) return page;
    await delay(50);
  }
  throw new Error('Timed out waiting for a page target');
}

class CdpClient {
  constructor(url) {
    this._url = url;
    this._nextId = 1;
    this._pending = new Map();
    this._waiters = [];
    this._closed = false;
    this._socket = null;
    this._requestOrigin = null;
  }

  async connect() {
    await new Promise((resolve, reject) => {
      const socket = new WebSocket(this._url);
      this._socket = socket;
      const fail = error => reject(error instanceof Error ? error : new Error(String(error)));
      socket.addEventListener('open', () => resolve(), { once: true });
      socket.addEventListener('error', event => {
        if (socket.readyState !== WebSocket.OPEN) {
          fail(event.error || new Error('WebSocket open failed'));
        }
      });
      socket.addEventListener('close', () => {
        this._closed = true;
        const error = new Error('CDP socket closed');
        for (const pending of this._pending.values()) pending.reject(error);
        this._pending.clear();
        while (this._waiters.length) {
          const waiter = this._waiters.shift();
          clearTimeout(waiter.timer);
          waiter.reject(error);
        }
      });
      socket.addEventListener('message', event => this._onMessage(event));
    });
  }

  _onMessage(event) {
    const raw = typeof event.data === 'string'
      ? event.data
      : Buffer.from(event.data).toString('utf8');
    const message = JSON.parse(raw);
    if (message.method === 'Fetch.requestPaused') {
      const request = message.params;
      const allowed = new URL(request.request.url).origin === this._requestOrigin;
      this.send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest',
        allowed ? { requestId: request.requestId }
          : { requestId: request.requestId, errorReason: 'BlockedByClient' }
      ).catch(error => { console.error(error); process.exitCode = 1; });
      return;
    }
    if (Object.prototype.hasOwnProperty.call(message, 'id')) {
      const pending = this._pending.get(message.id);
      if (!pending) return;
      this._pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message || 'CDP error'));
      else pending.resolve(message.result || {});
      return;
    }
    const keep = [];
    for (const waiter of this._waiters) {
      if (waiter.method === message.method && waiter.predicate(message.params || {})) {
        clearTimeout(waiter.timer);
        waiter.resolve(message.params || {});
      } else {
        keep.push(waiter);
      }
    }
    this._waiters = keep;
  }

  send(method, params) {
    if (this._closed || !this._socket || this._socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('CDP socket is not open'));
    }
    const id = this._nextId++;
    const payload = JSON.stringify({ id, method, params: params || {} });
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      this._socket.send(payload);
    });
  }

  waitFor(method, predicate, timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._waiters = this._waiters.filter(waiter => waiter !== record);
        reject(new Error('Timed out waiting for ' + method));
      }, timeoutMs || READY_TIMEOUT_MS);
      const record = {
        method,
        predicate: predicate || (() => true),
        reject,
        resolve,
        timer,
      };
      this._waiters.push(record);
    });
  }

  async close() {
    if (!this._socket) return;
    if (this._socket.readyState === WebSocket.OPEN) {
      this._socket.close();
    }
    await delay(50);
  }
}

async function setViewport(cdp, width, height) {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
    screenWidth: width,
    screenHeight: height,
    positionX: 0,
    positionY: 0,
    dontSetVisibleSize: false,
  });
}

async function navigateAndWait(cdp, url) {
  const loaded = cdp.waitFor('Page.loadEventFired', null, READY_TIMEOUT_MS);
  await cdp.send('Page.navigate', { url });
  await loaded;
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails;
    const description = detail.exception && detail.exception.description;
    const stack = detail.stackTrace && Array.isArray(detail.stackTrace.callFrames)
      ? detail.stackTrace.callFrames.map(frame => {
        return (frame.functionName || '<anonymous>') + '@' + frame.url + ':'
          + frame.lineNumber + ':' + frame.columnNumber;
      }).join(' | ')
      : '';
    const message = [
      detail.text,
      description,
      stack,
      'line=' + detail.lineNumber + ', column=' + detail.columnNumber,
    ].filter(Boolean).join(' | ') || 'Runtime.evaluate failed';
    throw new Error(message);
  }
  return result.result ? result.result.value : undefined;
}

function measurementExpression(width, proofMode) {
  return `
(async function () {
  function q(selector, root) { return (root || document).querySelector(selector); }
  function round(value) { return Number(Number(value).toFixed(2)); }
  function rect(node) {
    var box = node.getBoundingClientRect();
    return {
      left: round(box.left),
      top: round(box.top),
      right: round(box.right),
      bottom: round(box.bottom),
      width: round(box.width),
      height: round(box.height)
    };
  }
  function metrics(node) {
    return {
      clientWidth: node.clientWidth,
      scrollWidth: node.scrollWidth,
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
      rect: rect(node)
    };
  }
  function textMetrics(node) {
    var style = getComputedStyle(node);
    return Object.assign({
      text: node.textContent,
      title: node.title || '',
      color: style.color,
      fontWeight: style.fontWeight
    }, metrics(node));
  }
  function overflowSnapshot() {
    return {
      document: {
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth
      },
      table: {
        clientWidth: table.clientWidth,
        scrollWidth: table.scrollWidth
      }
    };
  }
  function applyProof(mode) {
    if (!mode) return;
    var style = document.createElement('style');
    style.id = 'wm-measure-proof';
    if (mode === 'overflow') {
      style.textContent = [
        'html, body { overflow-x: auto !important; }',
        'body { min-width: calc(100vw + 24px) !important; }',
        '.fleet-shell {',
        '  min-width: calc(100vw + 24px) !important;',
        '  width: calc(100vw + 24px) !important;',
        '  max-width: none !important;',
        '}',
        '.fleet-grid { min-width: calc(100% + 24px) !important; }'
      ].join('\\n');
    } else if (mode === 'emphasis') {
      style.textContent = [
        '.fleet-ewar.active {',
        '  color: var(--fleet-incoming-threat) !important;',
        '  font-weight: 400 !important;',
        '}',
        '.fleet-damage-in.warn .fleet-damage-value {',
        '  font-weight: 700 !important;',
        '}'
      ].join('\\n');
    } else {
      throw new Error('Unknown proof mode: ' + mode);
    }
    document.head.appendChild(style);
  }
  async function frame() {
    await new Promise(function (resolve) {
      requestAnimationFrame(function () { requestAnimationFrame(resolve); });
    });
  }
  async function show(kind) {
    await window.DEV.fleetBar(kind);
    await frame();
  }
  function stateSnapshot() {
    return {
      rowCount: q('#fleet-rows').children.length,
      emptyHidden: q('#fleet-empty').hidden,
      emptyText: q('#fleet-empty').textContent,
      noteHidden: q('#fleet-note').hidden,
      noteText: q('#fleet-note').textContent,
      healthText: q('#fleet-health').textContent
    };
  }
  if (!window.DEV || typeof window.DEV.fleetBar !== 'function') {
    throw new Error('DEV.fleetBar is unavailable');
  }
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await frame();

  var proofMode = ${JSON.stringify(proofMode || '')};
  applyProof(proofMode);
  await frame();

  var shell = q('#fleet-shell');
  var table = q('#fleet-table');
  var title = q('#fleet-title');
  var titleEnd = q('#fleet-title-end');
  var drag = q('#fleet-drag');
  var actions = q('#fleet-title-actions');
  var reset = q('#fleet-reset-width');
  var head = q('.fleet-head');
  var fixtures = {};

  await show('threat');
  fixtures.threat = overflowSnapshot();
  var threatRow = q('.fleet-row');
  var threatIncoming = q('.fleet-damage-in .fleet-damage-value', threatRow);
  var threatEwar = q('.fleet-ewar.active', threatRow);
  var beforeHeader = {
    titleHeight: round(title.getBoundingClientRect().height),
    titleEndWidth: round(titleEnd.getBoundingClientRect().width),
    drag: rect(drag),
    actions: rect(actions)
  };
  reset.focus();
  await frame();
  var afterHeader = {
    titleHeight: round(title.getBoundingClientRect().height),
    titleEndWidth: round(titleEnd.getBoundingClientRect().width),
    drag: rect(drag),
    actions: rect(actions)
  };
  q('#fleet-health').hidden = true;
  q('#fleet-title-error').hidden = false;
  q('#fleet-title-error').textContent = 'Example error';
  titleEnd.classList.add('error-active');
  reset.focus();
  await frame();
  var errorFocused = {
    actionsOpacity: Number(getComputedStyle(actions).opacity),
    actionsPointerEvents: getComputedStyle(actions).pointerEvents
  };
  titleEnd.classList.remove('error-active');
  q('#fleet-title-error').hidden = true;
  q('#fleet-title-error').textContent = '';
  q('#fleet-health').hidden = false;
  var surfaces = {
    threat: getComputedStyle(threatRow).backgroundColor,
    threatSample: {
      x: Math.max(0, Math.floor(threatRow.getBoundingClientRect().left + 4)),
      y: Math.max(0, Math.floor(threatRow.getBoundingClientRect().top + 4))
    }
  };
  var emphasis = {
    incomingColor: getComputedStyle(threatIncoming).color,
    incomingFontWeight: getComputedStyle(threatIncoming).fontWeight,
    ewarColor: getComputedStyle(threatEwar).color,
    ewarFontWeight: getComputedStyle(threatEwar).fontWeight,
    backgroundSample: surfaces.threatSample
  };
  table.focus();
  await frame();

  await show('zero');
  fixtures.zero = overflowSnapshot();
  surfaces.neutral = getComputedStyle(q('.fleet-row')).backgroundColor;
  surfaces.neutralSample = {
    x: Math.max(0, Math.floor(q('.fleet-row').getBoundingClientRect().left + 4)),
    y: Math.max(0, Math.floor(q('.fleet-row').getBoundingClientRect().top + 4))
  };

  await show('long');
  fixtures.long = overflowSnapshot();
  var longName = textMetrics(q('.fleet-character'));

  await show('exact10m');
  fixtures.exact10m = overflowSnapshot();
  var exactRow = q('.fleet-row');
  var exact10m = {
    character: metrics(exactRow.children[0]),
    outgoing: textMetrics(q('.fleet-damage-out .fleet-damage-value', exactRow)),
    incoming: textMetrics(q('.fleet-damage-in .fleet-damage-value', exactRow)),
    axis: rect(q('.fleet-damage-axis', exactRow)),
    damage: metrics(q('.fleet-damage', exactRow)),
    ewar: textMetrics(q('.fleet-ewar', exactRow))
  };

  await show('mixed');
  fixtures.mixed = overflowSnapshot();
  var mixed = {
    header: rect(q('.fleet-damage-head')),
    rows: Array.from(document.querySelectorAll('.fleet-row')).map(function (row) {
      return { damage: rect(q('.fleet-damage', row)), axis: rect(q('.fleet-damage-axis', row)),
        remote: Boolean(q('.fleet-remote', row)) };
    })
  };

  await show('remote');
  fixtures.remote = overflowSnapshot();
  var remote = {
    ewar: textMetrics(q('.fleet-ewar'))
  };

  await show('empty');
  fixtures.empty = stateSnapshot();

  await show('allhidden');
  fixtures.allhidden = stateSnapshot();

  await show('nolog');
  fixtures.nolog = stateSnapshot();

  await show('missing');
  fixtures.missing = stateSnapshot();

  await show('waiting');
  fixtures.waiting = stateSnapshot();

  await show('error');
  fixtures.error = stateSnapshot();

  await show('roster');
  fixtures.roster = overflowSnapshot();
  var headTopBefore = round(head.getBoundingClientRect().top);
  table.scrollTop = table.scrollHeight;
  await frame();
  var headTopAfter = round(head.getBoundingClientRect().top);

  return {
    requestedWidth: ${JSON.stringify(width)},
    proofMode: proofMode || null,
    viewportWidth: window.innerWidth,
    shellWidth: round(shell.getBoundingClientRect().width),
    tracks: {
      character: exact10m.character.rect.width,
      damage: exact10m.damage.rect.width,
      ewar: exact10m.ewar.rect.width
    },
    fixtures: fixtures,
    header: {
      before: beforeHeader,
      after: afterHeader,
      errorFocused: errorFocused
    },
    surfaces: surfaces,
    emphasis: emphasis,
    longName: longName,
    exact10m: exact10m,
    mixed: mixed,
    remote: remote,
    sticky: {
      beforeTop: headTopBefore,
      afterTop: headTopAfter
    },
    roster: {
      rowCount: document.getElementById('fleet-rows').children.length,
      clientHeight: table.clientHeight,
      scrollHeight: table.scrollHeight
    }
  };
})()
`;
}

function parseColor(colorText) {
  const text = String(colorText || '').trim().toLowerCase();
  let match = text.match(/^#([0-9a-f]{6})$/i);
  if (match) {
    const hex = match[1];
    return {
      r: Number.parseInt(hex.slice(0, 2), 16),
      g: Number.parseInt(hex.slice(2, 4), 16),
      b: Number.parseInt(hex.slice(4, 6), 16),
      a: 255,
    };
  }
  match = text.match(/^#([0-9a-f]{3})$/i);
  if (match) {
    const hex = match[1];
    return {
      r: Number.parseInt(hex[0] + hex[0], 16),
      g: Number.parseInt(hex[1] + hex[1], 16),
      b: Number.parseInt(hex[2] + hex[2], 16),
      a: 255,
    };
  }
  match = text.match(/rgba?\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(',').map(part => part.trim());
  const number = value => {
    if (/%$/.test(value)) return Math.round(Number(value.slice(0, -1)) * 2.55);
    return Number(value);
  };
  const rgba = parts.map(number);
  if (rgba.length < 3 || rgba.slice(0, 3).some(value => !Number.isFinite(value))) {
    return null;
  }
  return {
    r: rgba[0],
    g: rgba[1],
    b: rgba[2],
    a: rgba.length >= 4 && Number.isFinite(rgba[3]) ? rgba[3] : 255,
  };
}

function relativeLuminance(color) {
  const transform = component => {
    const normalized = component / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : Math.pow((normalized + 0.055) / 1.055, 2.4);
  };
  const r = transform(color.r);
  const g = transform(color.g);
  const b = transform(color.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(foreground, background) {
  const light = Math.max(relativeLuminance(foreground), relativeLuminance(background));
  const dark = Math.min(relativeLuminance(foreground), relativeLuminance(background));
  return (light + 0.05) / (dark + 0.05);
}

function parseFontWeight(weightText) {
  const value = Number.parseInt(String(weightText || '').trim(), 10);
  if (Number.isFinite(value)) return value;
  if (String(weightText).trim().toLowerCase() == 'bold') return 700;
  return 400;
}

function emphasisStrength(colorText, fontWeightText, background) {
  const color = parseColor(colorText);
  if (!color) {
    throw new Error('Could not parse rendered text color: ' + colorText);
  }
  return {
    color: colorText,
    fontWeight: parseFontWeight(fontWeightText),
    contrast: Number(contrastRatio(color, background).toFixed(4)),
  };
}

function strongerEmphasis(ewar, incoming) {
  const contrastGap = ewar.contrast - incoming.contrast;
  if (contrastGap > 0.01) {
    return { ok: true, reason: 'contrast', delta: Number(contrastGap.toFixed(4)) };
  }
  if (Math.abs(contrastGap) <= 0.01 && ewar.fontWeight > incoming.fontWeight) {
    return { ok: true, reason: 'fontWeight', delta: ewar.fontWeight - incoming.fontWeight };
  }
  return { ok: false, reason: 'incoming-equal-or-stronger', delta: Number(contrastGap.toFixed(4)) };
}

function decodePng(buffer) {
  const signature = '89504e470d0a1a0a';
  if (buffer.subarray(0, 8).toString('hex') !== signature) {
    throw new Error('captureScreenshot did not return a PNG');
  }
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idat = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    offset += 4;
    const type = buffer.subarray(offset, offset + 4).toString('ascii');
    offset += 4;
    const data = buffer.subarray(offset, offset + length);
    offset += length + 4;
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
  }
  if (bitDepth !== 8 || (colorType !== 6 && colorType !== 2)) {
    throw new Error('Unsupported screenshot PNG format');
  }
  const bytesPerPixel = colorType === 6 ? 4 : 3;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * bytesPerPixel;
  const pixels = Buffer.alloc(stride * height);
  let input = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[input];
    input += 1;
    const rowStart = y * stride;
    for (let x = 0; x < stride; x += 1) {
      const value = raw[input];
      input += 1;
      const left = x >= bytesPerPixel ? pixels[rowStart + x - bytesPerPixel] : 0;
      const up = y > 0 ? pixels[rowStart - stride + x] : 0;
      const upLeft = y > 0 && x >= bytesPerPixel
        ? pixels[rowStart - stride + x - bytesPerPixel]
        : 0;
      let out = value;
      if (filter === 1) out = (value + left) & 0xff;
      else if (filter === 2) out = (value + up) & 0xff;
      else if (filter === 3) out = (value + Math.floor((left + up) / 2)) & 0xff;
      else if (filter === 4) {
        const p = left + up - upLeft;
        const pa = Math.abs(p - left);
        const pb = Math.abs(p - up);
        const pc = Math.abs(p - upLeft);
        const predictor = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
        out = (value + predictor) & 0xff;
      } else if (filter !== 0) {
        throw new Error('Unsupported PNG filter ' + filter);
      }
      pixels[rowStart + x] = out;
    }
  }
  return { width, height, bytesPerPixel, pixels };
}

async function captureBackgroundPixel(cdp, point) {
  const screenshot = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    clip: {
      x: point.x,
      y: point.y,
      width: 1,
      height: 1,
      scale: 1,
    },
  });
  const png = decodePng(Buffer.from(screenshot.data, 'base64'));
  return {
    r: png.pixels[0],
    g: png.pixels[1],
    b: png.pixels[2],
    a: png.bytesPerPixel === 4 ? png.pixels[3] : 255,
  };
}

function fixtureEvidenceExpression(kind) {
  return `
(async function () {
  function q(selector, root) {
    var node = (root || document).querySelector(selector);
    if (!node) throw new Error('Missing ' + selector + ' for ${kind} evidence');
    return node;
  }
  await window.DEV.fleetBar(${JSON.stringify(kind)});
  await new Promise(function (resolve) {
    requestAnimationFrame(function () { requestAnimationFrame(resolve); });
  });
  var row = q('.fleet-row');
  var result = {
    surfaceColor: getComputedStyle(row).backgroundColor,
    backgroundSample: {
      x: Math.max(0, Math.floor(row.getBoundingClientRect().left + 4)),
      y: Math.max(0, Math.floor(row.getBoundingClientRect().top + 4))
    }
  };
  if (${JSON.stringify(kind)} === 'threat') {
    var incoming = q('.fleet-damage-in .fleet-damage-value', row);
    var ewar = q('.fleet-ewar.active', row);
    result.incomingColor = getComputedStyle(incoming).color;
    result.incomingFontWeight = getComputedStyle(incoming).fontWeight;
    result.ewarColor = getComputedStyle(ewar).color;
    result.ewarFontWeight = getComputedStyle(ewar).fontWeight;
  }
  if (${JSON.stringify(kind)} === 'remote') {
    var marker = q('.fleet-remote', row);
    result.markerColor = getComputedStyle(marker).color;
    result.markerFontWeight = getComputedStyle(marker).fontWeight;
  }
  return result;
})()
`;
}

function clipped(label, metric) {
  return metric.scrollWidth > metric.clientWidth + EPSILON
    ? label + ' clipped (' + metric.scrollWidth + ' > ' + metric.clientWidth + ')'
    : null;
}

function validateMeasurement(measurement) {
  const errors = [];
  const width = measurement.requestedWidth;
  if (Math.abs(measurement.shellWidth - width) > EPSILON) {
    errors.push(width + ': shell width ' + measurement.shellWidth + ' != requested ' + width);
  }
  if (measurement.mixed.rows.length !== 2 || !measurement.mixed.rows.some(row => row.remote)) {
    errors.push(width + ': mixed-row alignment fixture is incomplete');
  }
  const header = measurement.mixed.header;
  for (const row of measurement.mixed.rows) {
    for (const edge of ['left', 'right']) {
      if (Math.abs(row.damage[edge] - header[edge]) > EPSILON) {
        errors.push(width + ': mixed DPS ' + edge + ' does not align with header');
      }
    }
    if (Math.abs((row.axis.left + row.axis.right) / 2 - (header.left + header.right) / 2) > EPSILON) {
      errors.push(width + ': mixed DPS axis does not align with header center');
    }
  }
  for (const fixtureName of ['long', 'exact10m', 'remote', 'mixed', 'roster']) {
    const fixture = measurement.fixtures[fixtureName];
    if (!fixture) {
      errors.push(width + ': missing fixture widths for ' + fixtureName);
      continue;
    }
    if (fixture.document.scrollWidth > fixture.document.clientWidth + EPSILON) {
      errors.push(
        width + ': ' + fixtureName + ' document overflow '
          + fixture.document.scrollWidth + ' > ' + fixture.document.clientWidth
      );
    }
    if (fixture.table.scrollWidth > fixture.table.clientWidth + EPSILON) {
      errors.push(
        width + ': ' + fixtureName + ' Fleet table overflow '
          + fixture.table.scrollWidth + ' > ' + fixture.table.clientWidth
      );
    }
  }
  if (measurement.tracks.character <= 92) {
    errors.push(width + ': Character track is at or below 92px (' + measurement.tracks.character + ')');
  }
  if (measurement.longName.scrollWidth <= measurement.longName.clientWidth + EPSILON) {
    errors.push(width + ': long character name did not overflow, so ellipsis was not exercised');
  }
  if (measurement.longName.title !== measurement.longName.text) {
    errors.push(width + ': long character name is missing title metadata');
  }
  const exactOut = clipped(width + ': exact 10m outgoing', measurement.exact10m.outgoing);
  if (exactOut) errors.push(exactOut);
  const exactIn = clipped(width + ': exact 10m incoming', measurement.exact10m.incoming);
  if (exactIn) errors.push(exactIn);
  const localEwar = clipped(width + ': local full EWAR', measurement.exact10m.ewar);
  if (localEwar) errors.push(localEwar);
  const remoteEwar = clipped(width + ': remote full EWAR', measurement.remote.ewar);
  if (remoteEwar) errors.push(remoteEwar);
  if (measurement.exact10m.outgoing.text !== '10000000') {
    errors.push(width + ': exact outgoing 10m text is ' + JSON.stringify(measurement.exact10m.outgoing.text));
  }
  if (measurement.exact10m.incoming.text !== '10000000') {
    errors.push(width + ': exact incoming 10m text is ' + JSON.stringify(measurement.exact10m.incoming.text));
  }
  if (measurement.exact10m.character.rect.right > measurement.exact10m.damage.rect.left + EPSILON) {
    errors.push(width + ': Character and Damage overlap in exact-10m row');
  }
  if (measurement.exact10m.outgoing.rect.right > measurement.exact10m.axis.left + EPSILON) {
    errors.push(width + ': exact outgoing overlaps the center axis');
  }
  if (measurement.exact10m.incoming.rect.left + EPSILON < measurement.exact10m.axis.right) {
    errors.push(width + ': exact incoming overlaps the center axis');
  }
  if (measurement.exact10m.ewar.rect.left + EPSILON < measurement.exact10m.damage.rect.right) {
    errors.push(width + ': local full EWAR overlaps the Damage cell');
  }
  if (measurement.surfaces.threat === measurement.surfaces.neutral) {
    errors.push(width + ': threat and neutral row surfaces are indistinguishable');
  }
  if (!measurement.emphasis.backgroundColor) {
    errors.push(width + ': missing sampled threat-row background color');
  }
  if (!measurement.surfaces.neutralBackgroundColor) {
    errors.push(width + ': missing sampled neutral-row background color');
  } else if (measurement.emphasis.backgroundColor === measurement.surfaces.neutralBackgroundColor) {
    errors.push(width + ': threat-row and neutral-row sampled backgrounds are identical');
  }
  if (!measurement.emphasis.ewarStrength || !measurement.emphasis.incomingStrength) {
    errors.push(width + ': missing rendered emphasis strengths');
  } else {
    const relation = strongerEmphasis(
      measurement.emphasis.ewarStrength,
      measurement.emphasis.incomingStrength
    );
    measurement.emphasis.relation = relation;
    if (!relation.ok) {
      errors.push(
        width + ': rendered EWAR emphasis is not stronger than incoming '
          + '(contrast ' + measurement.emphasis.ewarStrength.contrast
          + '@' + measurement.emphasis.ewarStrength.fontWeight
          + ' vs ' + measurement.emphasis.incomingStrength.contrast
          + '@' + measurement.emphasis.incomingStrength.fontWeight + ')'
      );
    }
  }
  if (Math.abs(measurement.header.before.titleHeight - measurement.header.after.titleHeight) > EPSILON) {
    errors.push(
      width + ': header height shifted from ' + measurement.header.before.titleHeight
        + ' to ' + measurement.header.after.titleHeight
    );
  }
  if (Math.abs(measurement.header.before.titleEndWidth - measurement.header.after.titleEndWidth) > EPSILON) {
    errors.push(
      width + ': header end width shifted from ' + measurement.header.before.titleEndWidth
        + ' to ' + measurement.header.after.titleEndWidth
    );
  }
  if (!measurement.header.errorFocused
      || measurement.header.errorFocused.actionsOpacity < 0.99
      || measurement.header.errorFocused.actionsPointerEvents !== 'auto') {
    errors.push(width + ': focused header actions disappear under error-active');
  }
  if (measurement.header.after.actions.left + EPSILON < measurement.header.after.drag.right) {
    errors.push(
      width + ': actions overlap drag region ('
        + measurement.header.after.actions.left + ' < '
        + measurement.header.after.drag.right + ')'
    );
  }
  if (Math.abs(measurement.sticky.beforeTop - measurement.sticky.afterTop) > EPSILON) {
    errors.push(
      width + ': sticky header moved from ' + measurement.sticky.beforeTop
        + ' to ' + measurement.sticky.afterTop
    );
  }
  const states = {
    empty: {
      rowCount: 0,
      emptyHidden: false,
      healthText: 'LOCAL WAITING',
      noteHidden: true
    },
    allhidden: {
      rowCount: 0,
      emptyHidden: false,
      emptyText: 'All running characters are hidden.',
      healthText: 'LOCAL LIVE'
    },
    nolog: {
      rowCount: 1,
      emptyHidden: true,
      noteHidden: true,
      healthText: 'LOCAL LIVE'
    },
    missing: {
      rowCount: 0,
      emptyHidden: false,
      noteHidden: false,
      noteText: 'Set the Gamelog folder in Settings › Alerts.',
      healthText: 'LOCAL NO LOG FOLDER'
    },
    waiting: {
      rowCount: 0,
      emptyHidden: false,
      healthText: 'LOCAL WAITING',
      noteHidden: true
    },
    error: {
      rowCount: 0,
      emptyHidden: false,
      noteHidden: false,
      noteText: 'Gamelogs could not be read.',
      healthText: 'LOCAL ERROR'
    }
  };
  for (const name of Object.keys(states)) {
    const actual = measurement.fixtures[name];
    if (!actual) {
      errors.push(width + ': missing rendered state fixture ' + name);
      continue;
    }
    const expected = states[name];
    for (const key of Object.keys(expected)) {
      if (actual[key] !== expected[key]) {
        errors.push(width + ': ' + name + ' ' + key + ' is ' + JSON.stringify(actual[key])
          + ' not ' + JSON.stringify(expected[key]));
      }
    }
  }
  if (measurement.roster.rowCount !== 128) {
    errors.push(width + ': roster fixture rendered ' + measurement.roster.rowCount + ' rows instead of 128');
  }
  if (measurement.roster.scrollHeight <= measurement.roster.clientHeight + EPSILON) {
    errors.push(
      width + ': roster did not overflow vertically (' + measurement.roster.scrollHeight
        + ' <= ' + measurement.roster.clientHeight + ')'
    );
  }
  if (measurement.roster.clientHeight > 480 + EPSILON) {
    errors.push(width + ': roster client height exceeds 480px cap (' + measurement.roster.clientHeight + ')');
  }
  if (!measurement.remote.markerStrength) {
    errors.push(width + ': missing rendered REMOTE threat contrast evidence');
  } else if (measurement.remote.markerStrength.contrast < 4.5) {
    errors.push(
      width + ': threat-row REMOTE contrast '
        + measurement.remote.markerStrength.contrast + ' is below 4.5:1'
    );
  }
  return errors;
}

function fixtureWidthSummary(fixture) {
  return 'doc ' + fixture.document.scrollWidth + '/' + fixture.document.clientWidth
    + ', table ' + fixture.table.scrollWidth + '/' + fixture.table.clientWidth;
}

function measurementSummary(data) {
  const lines = [];
  lines.push('Chromium layout evidence only; not Windows/WebView2 native acceptance.');
  if (data.proofMode) lines.push('Proof mode: ' + data.proofMode);
  lines.push('SHA: ' + data.sha);
  lines.push('Browser: ' + data.browserVersion);
  for (const measurement of data.measurements) {
    lines.push(
      measurement.requestedWidth + 'px: tracks '
        + measurement.tracks.character + ' / '
        + measurement.tracks.damage + ' / '
        + measurement.tracks.ewar
        + '; shell ' + measurement.shellWidth
        + '; header ' + measurement.header.before.titleHeight + '→' + measurement.header.after.titleHeight
        + '; roster ' + measurement.roster.clientHeight + '/' + measurement.roster.scrollHeight
        + '; EWAR ' + measurement.emphasis.ewarStrength.contrast + '@'
        + measurement.emphasis.ewarStrength.fontWeight
        + ' vs IN ' + measurement.emphasis.incomingStrength.contrast + '@'
        + measurement.emphasis.incomingStrength.fontWeight
    );
    lines.push(
      '  long ' + fixtureWidthSummary(measurement.fixtures.long)
      + '; exact10m ' + fixtureWidthSummary(measurement.fixtures.exact10m)
      + '; remote ' + fixtureWidthSummary(measurement.fixtures.remote)
      + '; roster ' + fixtureWidthSummary(measurement.fixtures.roster)
    );
  }
  if (data.errors.length) {
    lines.push('FAILURES:');
    data.errors.forEach(error => lines.push('- ' + error));
  } else {
    lines.push('PASS');
  }
  return lines.join('\n');
}

async function terminateBrowser(processInfo) {
  if (!processInfo || !processInfo.browser) return;
  const browser = processInfo.browser;
  if (browser.exitCode !== null) return;
  browser.kill('SIGTERM');
  const finished = await Promise.race([
    new Promise(resolve => browser.once('exit', () => resolve(true))),
    delay(1000).then(() => false),
  ]);
  if (!finished && browser.exitCode === null) {
    browser.kill('SIGKILL');
    await new Promise(resolve => browser.once('exit', () => resolve()));
  }
}

function gitSha() {
  try {
    const result = childProcess.spawnSync('git', ['rev-parse', 'HEAD'], {
      cwd: ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    if (result.status === 0) return result.stdout.trim();
  } catch {
    return 'UNKNOWN';
  }
  return 'UNKNOWN';
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  const chromePath = discoverChrome(args.chrome);
  const profileDir = await fsp.mkdtemp(path.join(os.tmpdir(), 'wingman-fleetbar-'));
  let serverInfo = null;
  let chrome = null;
  let cdp = null;
  try {
    serverInfo = await startServer(WEB_ROOT);
    chrome = spawnChrome(chromePath, profileDir);
    const devtools = await waitForDevTools(profileDir, chrome.browser, chrome.stderr);
    const version = await httpJson('http://127.0.0.1:' + devtools.port + '/json/version');
    const page = await waitForPageTarget(devtools.port);
    cdp = new CdpClient(page.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    // Intercept before the first page navigation, in this process's new profile
    // and ephemeral CDP port. Fixtures may load only our owned loopback origin.
    cdp._requestOrigin = serverInfo.baseUrl;
    await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });

    const pageUrl = serverInfo.baseUrl + '/fleetbar.html?dev=1';
    const measurements = [];
    const errors = [];
    for (const width of WIDTHS) {
      await setViewport(cdp, width, VIEWPORT_HEIGHT);
      await navigateAndWait(cdp, pageUrl);
      await evaluate(cdp, `
(async function () {
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await new Promise(function (resolve) {
    requestAnimationFrame(function () { requestAnimationFrame(resolve); });
  });
  if (!window.DEV || typeof window.DEV.fleetBar !== 'function') {
    throw new Error('Fleet dev harness did not initialize');
  }
  if (typeof window.onFleetSnapshot !== 'function') {
    throw new Error('Fleet snapshot handler did not initialize');
  }
  return true;
})()
      `);
      const measurement = await evaluate(cdp, measurementExpression(width, args.proof));
      const threatEvidence = await evaluate(cdp, fixtureEvidenceExpression('threat'));
      measurement.surfaces.threat = threatEvidence.surfaceColor;
      const threatBackground = await captureBackgroundPixel(cdp, threatEvidence.backgroundSample);
      measurement.emphasis.backgroundColor = 'rgba(' + [threatBackground.r, threatBackground.g, threatBackground.b, Number((threatBackground.a / 255).toFixed(3))].join(', ') + ')';
      measurement.emphasis.ewarColor = threatEvidence.ewarColor;
      measurement.emphasis.ewarFontWeight = threatEvidence.ewarFontWeight;
      measurement.emphasis.incomingColor = threatEvidence.incomingColor;
      measurement.emphasis.incomingFontWeight = threatEvidence.incomingFontWeight;
      measurement.emphasis.ewarStrength = emphasisStrength(
        threatEvidence.ewarColor,
        threatEvidence.ewarFontWeight,
        threatBackground
      );
      measurement.emphasis.incomingStrength = emphasisStrength(
        threatEvidence.incomingColor,
        threatEvidence.incomingFontWeight,
        threatBackground
      );
      const neutralEvidence = await evaluate(cdp, fixtureEvidenceExpression('zero'));
      measurement.surfaces.neutral = neutralEvidence.surfaceColor;
      const neutralBackground = await captureBackgroundPixel(cdp, neutralEvidence.backgroundSample);
      measurement.surfaces.neutralBackgroundColor = 'rgba(' + [neutralBackground.r, neutralBackground.g, neutralBackground.b, Number((neutralBackground.a / 255).toFixed(3))].join(', ') + ')';
      const remoteEvidence = await evaluate(cdp, fixtureEvidenceExpression('remote'));
      const remoteBackground = await captureBackgroundPixel(cdp, remoteEvidence.backgroundSample);
      measurement.remote.markerColor = remoteEvidence.markerColor;
      measurement.remote.markerFontWeight = remoteEvidence.markerFontWeight;
      measurement.remote.backgroundColor = 'rgba(' + [remoteBackground.r, remoteBackground.g, remoteBackground.b, Number((remoteBackground.a / 255).toFixed(3))].join(', ') + ')';
      measurement.remote.markerStrength = emphasisStrength(
        remoteEvidence.markerColor,
        remoteEvidence.markerFontWeight,
        remoteBackground
      );
      measurements.push(measurement);
      errors.push.apply(errors, validateMeasurement(measurement));
    }

    const data = {
      browserPath: chromePath,
      browserVersion: version.Browser || 'UNKNOWN',
      measurements,
      errors,
      proofMode: args.proof,
      sha: gitSha(),
    };
    console.log(measurementSummary(data));
    console.log(JSON.stringify(data, null, 2));
    if (errors.length) process.exitCode = 1;
  } finally {
    if (cdp) await cdp.close().catch(() => {});
    await terminateBrowser(chrome).catch(() => {});
    if (serverInfo) await stopServer(serverInfo.server).catch(() => {});
    await fsp.rm(profileDir, { recursive: true, force: true }).catch(() => {});
  }
}

run().catch(error => {
  console.error(error && error.stack || String(error));
  process.exitCode = 1;
});
