#!/usr/bin/env node
'use strict';

const childProcess = require('node:child_process');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, 'wingman', 'web');
const WIDTHS = [420, 500, 720];
const VIEWPORT_HEIGHT = 900;
const READY_TIMEOUT_MS = 15000;
const EPSILON = 1;

function parseArgs(argv) {
  const args = { chrome: null };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--chrome') {
      if (!argv[i + 1]) throw new Error('--chrome needs a path');
      args.chrome = argv[i + 1];
      i += 1;
      continue;
    }
    throw new Error('Unknown argument: ' + argv[i]);
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
    const message = result.exceptionDetails.text
      || (result.exceptionDetails.exception && result.exceptionDetails.exception.description)
      || 'Runtime.evaluate failed';
    throw new Error(message);
  }
  return result.result ? result.result.value : undefined;
}

function measurementExpression(width) {
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
    return Object.assign({
      text: node.textContent,
      title: node.title || '',
      color: getComputedStyle(node).color
    }, metrics(node));
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
  if (!window.DEV || typeof window.DEV.fleetBar !== 'function') {
    throw new Error('DEV.fleetBar is unavailable');
  }
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await frame();

  var shell = q('#fleet-shell');
  var table = q('#fleet-table');
  var title = q('#fleet-title');
  var titleEnd = q('#fleet-title-end');
  var drag = q('#fleet-drag');
  var actions = q('#fleet-title-actions');
  var reset = q('#fleet-reset-width');
  var head = q('.fleet-head');

  await show('threat');
  var threatRow = q('.fleet-row');
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
  var surfaces = {
    threat: getComputedStyle(threatRow).backgroundColor
  };
  var emphasis = {
    incomingColor: getComputedStyle(q('.fleet-damage-in .fleet-damage-value', threatRow)).color,
    ewarColor: getComputedStyle(q('.fleet-ewar.active', threatRow)).color
  };
  table.focus();
  await frame();

  await show('zero');
  surfaces.neutral = getComputedStyle(q('.fleet-row')).backgroundColor;

  await show('long');
  var longName = textMetrics(q('.fleet-character'));

  await show('exact10m');
  var exactRow = q('.fleet-row');
  var exact10m = {
    character: metrics(exactRow.children[0]),
    outgoing: textMetrics(q('.fleet-damage-out .fleet-damage-value', exactRow)),
    incoming: textMetrics(q('.fleet-damage-in .fleet-damage-value', exactRow)),
    axis: rect(q('.fleet-damage-axis', exactRow)),
    damage: metrics(q('.fleet-damage', exactRow)),
    ewar: textMetrics(q('.fleet-ewar', exactRow))
  };

  await show('remote');
  var remote = {
    ewar: textMetrics(q('.fleet-ewar'))
  };

  await show('roster');
  var headTopBefore = round(head.getBoundingClientRect().top);
  table.scrollTop = table.scrollHeight;
  await frame();
  var headTopAfter = round(head.getBoundingClientRect().top);

  return {
    requestedWidth: ${JSON.stringify(width)},
    viewportWidth: window.innerWidth,
    shellWidth: round(shell.getBoundingClientRect().width),
    documentClientWidth: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    tableWidth: metrics(table),
    tracks: {
      character: exact10m.character.rect.width,
      damage: exact10m.damage.rect.width,
      ewar: exact10m.ewar.rect.width
    },
    header: {
      before: beforeHeader,
      after: afterHeader
    },
    surfaces: surfaces,
    tokens: {
      warn: getComputedStyle(document.documentElement).getPropertyValue('--warn').trim(),
      incoming: getComputedStyle(document.documentElement).getPropertyValue('--fleet-incoming-threat').trim()
    },
    emphasis: emphasis,
    longName: longName,
    exact10m: exact10m,
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
    };
  }
  match = text.match(/^#([0-9a-f]{3})$/i);
  if (match) {
    const hex = match[1];
    return {
      r: Number.parseInt(hex[0] + hex[0], 16),
      g: Number.parseInt(hex[1] + hex[1], 16),
      b: Number.parseInt(hex[2] + hex[2], 16),
    };
  }
  match = text.match(/rgba?\(([^)]+)\)/i);
  if (!match) return null;
  const parts = match[1].split(',').map(part => Number(part.trim().replace(/%$/, '')));
  if (parts.length < 3 || parts.some(part => !Number.isFinite(part))) return null;
  return { r: parts[0], g: parts[1], b: parts[2] };
}

function sameColor(left, right) {
  const a = parseColor(left);
  const b = parseColor(right);
  return Boolean(a && b && a.r === b.r && a.g === b.g && a.b === b.b);
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
  if (measurement.documentScrollWidth > measurement.documentClientWidth + EPSILON) {
    errors.push(
      width + ': horizontal overflow ' + measurement.documentScrollWidth + ' > '
        + measurement.documentClientWidth
    );
  }
  if (measurement.tableWidth.scrollWidth > measurement.tableWidth.clientWidth + EPSILON) {
    errors.push(
      width + ': table horizontal overflow ' + measurement.tableWidth.scrollWidth + ' > '
        + measurement.tableWidth.clientWidth
    );
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
  if (sameColor(measurement.emphasis.ewarColor, measurement.emphasis.incomingColor)) {
    errors.push(width + ': EWAR and incoming colors are identical');
  }
  if (!sameColor(measurement.emphasis.ewarColor, measurement.tokens.warn)) {
    errors.push(width + ': active EWAR does not resolve to --warn (' + measurement.emphasis.ewarColor + ')');
  }
  if (!sameColor(measurement.emphasis.incomingColor, measurement.tokens.incoming)) {
    errors.push(width + ': incoming threat does not resolve to --fleet-incoming-threat (' + measurement.emphasis.incomingColor + ')');
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
  return errors;
}

function measurementSummary(data) {
  const lines = [];
  lines.push('Chromium layout evidence only; not Windows/WebView2 native acceptance.');
  lines.push('SHA: ' + data.sha);
  lines.push('Browser: ' + data.browserVersion);
  for (const measurement of data.measurements) {
    lines.push(
      measurement.requestedWidth + 'px: tracks '
        + measurement.tracks.character + ' / '
        + measurement.tracks.damage + ' / '
        + measurement.tracks.ewar
        + '; shell ' + measurement.shellWidth
        + '; doc ' + measurement.documentScrollWidth + '/' + measurement.documentClientWidth
        + '; header ' + measurement.header.before.titleHeight + '→' + measurement.header.after.titleHeight
        + '; roster ' + measurement.roster.clientHeight + '/' + measurement.roster.scrollHeight
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
      const measurement = await evaluate(cdp, measurementExpression(width));
      measurements.push(measurement);
      errors.push.apply(errors, validateMeasurement(measurement));
    }

    const data = {
      browserPath: chromePath,
      browserVersion: version.Browser || 'UNKNOWN',
      measurements,
      errors,
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
