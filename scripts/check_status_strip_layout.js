#!/usr/bin/env node
'use strict';
// Standalone rendered gate, not a pytest skip. Requires Node with native fetch/WebSocket.
// node scripts/check_status_strip_layout.js --chrome /usr/bin/google-chrome --out /tmp/status-strip
// Only production index/CSS/fonts and the four strip/shell owners load; no dev.js or Python.
// --negative-control hidden-value|transparent-value must exit 1 on screenshot paint assertions.
// Geometry + Chromium paint evidence only; not native WebView2 acceptance.
const fs = require('node:fs/promises');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {parseArgs} = require('node:util');
const {setTimeout: delay} = require('node:timers/promises');
const WEB = path.resolve(__dirname, '../wingman/web');

async function ready(probe, description) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const value = await probe();
    if (value) return value;
    await delay(50);
  }
  throw new Error('Timed out: ' + description);
}

async function cdp(url, event) {
  const socket = new WebSocket(url), pending = new Map();
  let serial = 0, failure;
  socket.addEventListener('error', () => { failure = new Error('CDP socket error'); });
  socket.addEventListener('close', () => {
    failure = new Error('CDP socket closed');
    for (const p of pending.values()) { clearTimeout(p.timer); p.reject(failure); }
    pending.clear();
  });
  socket.addEventListener('message', ({data}) => {
    const message = JSON.parse(data), p = pending.get(message.id);
    if (!p) { if (message.method) event(message); return; }
    pending.delete(message.id); clearTimeout(p.timer);
    if (message.error) p.reject(new Error(JSON.stringify(message.error)));
    else p.resolve(message.result);
  });
  try {
    await ready(() => { if (failure) throw failure; return socket.readyState === WebSocket.OPEN; }, 'CDP socket');
  } catch (error) { socket.close(); throw error; }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    if (failure) { reject(failure); return; }
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)); }, 10000);
    pending.set(id, {resolve, reject, timer}); socket.send(JSON.stringify({id, method, params}));
  });
  send.close = () => socket.close();
  return send;
}

// This executes in the real document. No copy of the production progress algorithm.
async function drawState(c) {
  const assertions = [], check = (name, pass) => assertions.push({name, pass: !!pass});
  onProgress({pct: 0, busy: false}); onStatus({text: 'Idle', kind: 'FG', busy: false});
  WM.route('main');
  const root = c.eve === 'stress' ? 'SYNTHETICROOT'.repeat(4) : 'J123456';
  onEveStatus({state: c.eve === 'off' ? 'off' : 'running', root, sig: '-ABC',
    next_num: root + '1', next_alpha: root + 'A', failed_binds: [], last_error: ''});
  onStatus({text: c.text, kind: c.kind, busy: c.busy});
  if (c.progress) onProgress(c.progress);
  let text = c.text, kind = c.kind;
  if (c.route) {
    for (const route of ['settings', 'main']) {
      WM.route(route);
      check('route ' + route + ' status', WM.el('status').textContent === (c.busy ? c.text : 'Idle'));
      check('route ' + route + ' progress', c.busy
        ? !WM.el('track').hidden && WM.el('pct').textContent === '55%' && WM.el('bar').style.transform === 'scaleX(0.55)'
        : WM.el('track').hidden && WM.el('pct').textContent === '' && WM.el('bar').style.transform === '');
    }
    if (!c.busy) { text = 'Idle'; kind = 'FG'; }
  }
  await document.fonts.ready;
  await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 160)));
  const ids = ['statusbar-slot', 'btn-fleetbar', 'btn-sigbar', 'evestat', 'status', 'track', 'bar', 'pct'];
  const geometry = {};
  for (const id of ids) {
    const node = WM.el(id), r = node.getBoundingClientRect(), s = getComputedStyle(node);
    geometry[id] = {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height,
      client: node.clientWidth, scroll: node.scrollWidth, hidden: node.hidden, display: s.display, visibility: s.visibility,
      font: parseFloat(s.fontSize), overflow: s.overflow, ellipsis: s.textOverflow, whiteSpace: s.whiteSpace,
      animation: s.animationName, transform: s.transform, background: s.backgroundImage, color: s.color};
  }
  const slot = geometry['statusbar-slot'], status = geometry.status, track = geometry.track, pct = geometry.pct;
  const inside = r => r.left >= slot.left + 16 - 0.01 && r.right <= slot.right - 16 + 0.01
    && r.top >= slot.top && r.bottom <= slot.bottom;
  check('exact viewport', innerWidth === c.width && innerHeight === c.height);
  check('slot has no horizontal overflow', slot.scroll === slot.client);
  check('document equals viewport', document.documentElement.scrollWidth === innerWidth);
  check('strip stays 53px and baseline height', slot.height === 53 && slot.height === c.baselineHeight);
  check('strip remains at window bottom', slot.bottom === innerHeight);
  check('status bounded inside strip', status.width > 0 && inside(status));
  check('status ellipsis nowrap', status.overflow === 'hidden' && status.ellipsis === 'ellipsis' && status.whiteSpace === 'nowrap');
  check('full text title and kind retained', WM.el('status').textContent === text && WM.el('status').title === text && WM.el('status').className === kind);
  if (text.length > 100) check('long text actually ellipsizes', status.scroll > status.client);
  for (const id of ['btn-fleetbar', 'btn-sigbar']) {
    const r = geometry[id];
    check(id + ' 44x32 inside strip', r.width === 44 && r.height === 32 && inside(r));
  }
  check('percentage 42px fully inside', pct.width === 42 && pct.scroll === pct.client && inside(pct));
  check('progress hidden/display state', track.hidden === !c.visible && (track.display === 'none') === !c.visible);
  check('percentage text', WM.el('pct').textContent === c.percent);
  if (c.visible) {
    check('active progress at least 4em', track.width + 0.01 >= 4 * track.font);
    check('active progress inside strip', inside(track));
    if (c.scale !== undefined) check('determinate scale', Math.abs(new DOMMatrix(geometry.bar.transform).a - c.scale) < 0.001);
  }
  const visible = ids.filter(id => id !== 'bar' && id !== 'statusbar-slot' && geometry[id].display !== 'none');
  check('strip children ordered without overlap', visible.every((id, i) => !i || geometry[id].left >= geometry[visible[i - 1]].right));
  const eveChildren = Array.from(WM.el('evestat').children).filter(n => !n.hidden).map(n => {
    const r = n.getBoundingClientRect(); return {text: n.textContent, left: r.left, right: r.right, client: n.clientWidth, scroll: n.scrollWidth};
  });
  check('EVE visibility', WM.el('evestat').hidden === (c.eve === 'off') && (c.eve === 'off'
    ? geometry.evestat.display === 'none' && geometry.evestat.width === 0
    : geometry.evestat.display !== 'none' && geometry.evestat.visibility === 'visible'
      && geometry.evestat.width > 0 && geometry.evestat.height > 0));
  if (c.eve !== 'off') check('complete EVE values retained', WM.el('eve-root').textContent === root
    && WM.el('eve-sig').textContent === '-ABC' && WM.el('eve-next').textContent === root + '1 / ' + root + 'A');
  if (c.eve === 'ordinary') check('ordinary EVE children not clipped', eveChildren.every(r =>
    r.left >= geometry.evestat.left - 1 && r.right <= geometry.evestat.right + 1 && r.scroll <= r.client + 1));
  const chrome = Array.from(document.querySelectorAll('.titlebar, .titlebar button, #routenav, .route.active')).map(n => {
    const r = n.getBoundingClientRect(); return {id: n.id || n.className, left: r.left, right: r.right, top: r.top, bottom: r.bottom};
  });
  check('main chrome in viewport', chrome.every(r => r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight));
  if (c.media === 'reduced' || c.reduced) {
    check('reduced motion active', matchMedia('(prefers-reduced-motion: reduce)').matches);
    check('reduced motion static full bar without fake percent', geometry.bar.animation === 'none'
      && Math.abs(geometry.bar.width - track.width) < 0.01 && new DOMMatrix(geometry.bar.transform).a === 1 && c.percent === '');
  }
  if (c.media === 'forced') check('forced colors active', matchMedia('(forced-colors: active)').matches);
  return {id: c.id, assertions, geometry, eveChildren, chrome, text, kind, documentWidth: document.documentElement.scrollWidth};
}

// Called only after drawState has checked the unmodified layout/route/motion state.
// The sole mutation outside animation freezing is an explicitly requested negative control.
async function prepareForcedPaint(c, negativeControl) {
  const track = WM.el('track'), bar = WM.el('bar'), inline = bar.style.cssText;
  const originalPaint = {background:getComputedStyle(bar).backgroundColor, visibility:getComputedStyle(bar).visibility};
  const animations = bar.getAnimations().filter(a => a.animationName === 'slide').map(animation =>
    ({animation, time: animation.currentTime, running: animation.playState === 'running'}));
  window.__restoreStatusPaint = () => {
    // CSSOM restoration respects the fixture CSP; setAttribute('style') does not.
    bar.style.cssText = inline;
    for (const a of animations) { a.animation.currentTime = a.time; if (a.running) a.animation.play(); }
    delete window.__restoreStatusPaint;
    return bar.style.cssText === inline && getComputedStyle(bar).backgroundColor === originalPaint.background
      && getComputedStyle(bar).visibility === originalPaint.visibility;
  };
  for (const a of animations) {
    a.animation.pause(); a.animation.currentTime = a.animation.effect.getTiming().duration / 2;
  }
  const assertions = [], check = (name, pass) => assertions.push({name:'forced paint style: ' + name, pass:!!pass});
  const root = getComputedStyle(document.documentElement), probe = document.createElement('span'), colors = {};
  probe.hidden = true; probe.style.forcedColorAdjust = 'none'; document.documentElement.appendChild(probe);
  try {
    for (const [role, fallback] of [['surface', 'Canvas'], ['value', 'CanvasText'], ['boundary', 'CanvasText'], ['canvas', 'Canvas']]) {
      const token = '--status-progress-forced-' + role, raw = role === 'canvas' ? fallback : root.getPropertyValue(token).trim();
      if (role !== 'canvas') check(role + ' root token present and valid', !!raw && CSS.supports('color', raw));
      // Missing tokens must fail assertions, not prevent the baseline's invisible pixels being measured.
      probe.style.color = fallback;
      if (role !== 'canvas') probe.style.color = 'var(' + token + ', ' + fallback + ')';
      const css = getComputedStyle(probe).color;
      colors[role] = {token:role === 'canvas' ? null : token, raw, css, rgb:css.match(/[\d.]+/g).slice(0, 3).map(Number)};
    }
  } finally { probe.remove(); }
  const ts = getComputedStyle(track), bs = getComputedStyle(bar);
  const styles = {track:{background:ts.backgroundColor, image:ts.backgroundImage, adjust:ts.forcedColorAdjust,
    outline:ts.outlineStyle, outlineWidth:ts.outlineWidth, outlineColor:ts.outlineColor, outlineOffset:ts.outlineOffset},
    bar:{background:bs.backgroundColor, image:bs.backgroundImage, adjust:bs.forcedColorAdjust, opacity:Number(bs.opacity)}};
  check('track uses resolved surface without an image', styles.track.background === colors.surface.css && styles.track.image === 'none');
  check('value uses resolved color without a gradient', styles.bar.background === colors.value.css && styles.bar.image === 'none');
  check('track and value retain explicit forced paint', styles.track.adjust === 'none' && styles.bar.adjust === 'none');
  check('1px boundary outside a 1px gap', styles.track.outline === 'solid' && styles.track.outlineWidth === '1px'
    && styles.track.outlineOffset === '1px' && styles.track.outlineColor === colors.boundary.css);
  check('value opacity preserves reduced-motion cue', styles.bar.opacity === (c.reduced ? 0.45 : 1));
  if (negativeControl === 'hidden-value') bar.style.visibility = 'hidden';
  if (negativeControl === 'transparent-value') bar.style.background = 'transparent';
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const rect = node => {
    const r = node.getBoundingClientRect();
    return {left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:r.width, height:r.height};
  };
  const t = rect(track), b = rect(bar), intersection = {left:Math.max(t.left, b.left), right:Math.min(t.right, b.right),
    top:Math.max(t.top, b.top), bottom:Math.min(t.bottom, b.bottom)};
  check('paint retains shared 4px track height', t.height === 4);
  if (c.progress.mode === 'indeterminate' && !c.reduced) check('indeterminate midpoint frozen for paint only',
    animations.length === 1 && animations[0].animation.playState === 'paused' && intersection.right > intersection.left);
  // Integer clip edges make screenshot pixels map directly back to CSS pixels at DPR 1.
  // Include outer Canvas, the outline at top-2, its 1px gap, and the actual track.
  const clip = {x:Math.floor(t.left) - 4, y:Math.floor(t.top) - 4,
    width:Math.ceil(t.right) - Math.floor(t.left) + 8, height:Math.ceil(t.bottom) - Math.floor(t.top) + 8, scale:1};
  return {assertions, colors, styles, track:t, bar:b, intersection, clip, negativeControl,
    staticFull:!!c.reduced, frozenAnimations:animations.length};
}

// Decode the actual CDP PNG in the page, not a redraw of the DOM or a computed-style proxy.
// Blob/ImageBitmap + an off-DOM canvas need no decoder dependency or relaxed CSP.
async function inspectForcedPaint(base64, p) {
  const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(base64), ch => ch.charCodeAt(0))], {type:'image/png'}));
  const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
  const context = canvas.getContext('2d'); context.drawImage(bitmap, 0, 0); bitmap.close();
  const image = context.getImageData(0, 0, canvas.width, canvas.height), assertions = [];
  const check = (name, pass) => assertions.push({name:'paint: ' + name, pass:!!pass});
  const sampleRow = (left, right, y) => {
    // Central ranges avoid the track/value/outline rounded corners and transformed edges.
    const inset = Math.max(3, (right - left) * 0.2), pixels = [];
    const start = Math.ceil(left + inset), end = Math.floor(right - inset);
    for (let x = start; x < end; x++) {
      const px = x - p.clip.x, py = y - p.clip.y;
      if (px >= 0 && px < image.width && py >= 0 && py < image.height) {
        const offset = (py * image.width + px) * 4;
        pixels.push(Array.from(image.data.slice(offset, offset + 4)));
      }
    }
    return {left:start, right:end, y, pixels};
  };
  const delta = (a, b) => Math.max(...a.slice(0, 3).map((channel, i) => Math.abs(channel - b[i])));
  const matches = (row, rgb) => row.pixels.length >= 3 && row.pixels.every(pixel => pixel[3] === 255 && delta(pixel, rgb) <= 2);
  const luminance = rgb => rgb.slice(0, 3).map(channel => {
    const s = channel / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, channel, i) => sum + channel * [0.2126, 0.7152, 0.0722][i], 0);
  const contrast = (a, b) => {
    const x = luminance(a), y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };
  const minimumContrast = (a, b) => {
    if (!a.length || !b.length) return 0;
    let minimum = Infinity;
    for (const x of a) for (const y of b) minimum = Math.min(minimum, contrast(x, y));
    return minimum;
  };
  const t = p.track, i = p.intersection, y = Math.floor((t.top + t.bottom) / 2);
  // Sample Canvas below the bottom outline: the route watermark can paint above
  // the track, but ends at the strip centre and must not contaminate this reference.
  const value = sampleRow(i.left, i.right, y), outer = sampleRow(t.left, t.right, p.clip.y + p.clip.height - 1);
  const empty = [[t.left, i.left], [i.right, t.right]].sort((a, b) => (b[1] - b[0]) - (a[1] - a[0]))[0];
  const surface = p.staticFull ? null : sampleRow(empty[0], empty[1], y);
  // Chrome can round a fractional outline edge by a pixel. Only accept a full central
  // row in the outside-boundary band — never a value pixel or rounded-corner antialiasing.
  const boundaryCandidates = Array.from(new Set([Math.floor(t.top) - 3, Math.floor(t.top) - 2, Math.ceil(t.top) - 2]))
    .map(row => sampleRow(t.left, t.right, row));
  const distance = row => row.pixels.length ? Math.max(...row.pixels.map(pixel => delta(pixel, p.colors.boundary.rgb))) : Infinity;
  const boundary = boundaryCandidates.slice().sort((a, b) => distance(a) - distance(b))[0];
  const expectedValue = p.colors.value.rgb.map((channel, index) =>
    Math.round(channel * p.styles.bar.opacity + p.colors.surface.rgb[index] * (1 - p.styles.bar.opacity)));
  // A static reduced-motion bar covers all of the track: no empty-track pixel exists.
  // Use the resolved surface token there, AND check actual outer Canvas pixels independently.
  const surfacePixels = surface ? surface.pixels : [p.colors.surface.rgb];
  const ratios = {valueSurface:minimumContrast(value.pixels, surfacePixels), valueOuter:minimumContrast(value.pixels, outer.pixels),
    boundarySurface:minimumContrast(boundary.pixels, surfacePixels), boundaryOuter:minimumContrast(boundary.pixels, outer.pixels)};
  check('PNG dimensions match cropped track and outline', image.width === p.clip.width && image.height === p.clip.height);
  check('value pixels match resolved token with opacity composition', matches(value, expectedValue));
  check('outer pixels match system Canvas', matches(outer, p.colors.canvas.rgb));
  check(p.staticFull ? 'covered surface reference agrees with outer Canvas' : 'empty-track pixels match resolved surface',
    matches(surface || outer, p.colors.surface.rgb));
  check('boundary pixels match resolved token outside the gap', matches(boundary, p.colors.boundary.rgb));
  check('value is distinct from surface and outer Canvas at >=3:1', ratios.valueSurface >= 3 && ratios.valueOuter >= 3);
  check('boundary is distinct from surface and outer Canvas at >=3:1', ratios.boundarySurface >= 3 && ratios.boundaryOuter >= 3);
  return {assertions, samples:{value, surface, outer, boundary, boundaryCandidates}, expectedValue, ratios,
    surfaceReference:surface ? 'actual empty-track pixels' : 'resolved root surface token; static full bar covers track, outer Canvas pixels checked separately'};
}

(async () => {
  const {values} = parseArgs({options: {chrome: {type: 'string'}, out: {type: 'string'}, 'negative-control': {type:'string'}}, strict: true});
  if (!values.chrome || !values.out) throw new Error('Required: --chrome EXECUTABLE --out DIRECTORY');
  const negativeControl = values['negative-control'] || null;
  if (negativeControl && !['hidden-value', 'transparent-value'].includes(negativeControl)) throw new Error('Invalid --negative-control: ' + negativeControl);
  const out = path.resolve(values.out);
  await fs.mkdir(out, {recursive: true});
  const report = {cases: [], assertions: [], pageErrors: [], requests: [], screenshots: [], negativeControl,
    fixture: 'production index + app/bookmarks/fleet/panel; no dev.js or pywebview'};
  let browser, profile, send, server, origin;
  try {
    const allowed = new Set(['app.js', 'bookmarks.js', 'fleet.js', 'panel.js']);
    const html = (await fs.readFile(path.join(WEB, 'index.html'), 'utf8')).replace(/<script src="([^"]+)"><\/script>/g,
      (tag, name) => allowed.has(name) ? tag : '');
    server = http.createServer(async (req, res) => {
      try {
        const pathname = decodeURIComponent(new URL(req.url, origin).pathname);
        if (pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
        const file = path.resolve(WEB, '.' + pathname);
        if (req.method !== 'GET' || !file.startsWith(WEB + path.sep)) { res.writeHead(403); res.end(); return; }
        const body = pathname === '/index.html' ? html : await fs.readFile(file);
        res.writeHead(200, {'Content-Type': {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml'}[path.extname(file)] || 'application/octet-stream',
          'Content-Security-Policy': "default-src 'self'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'", 'Cache-Control': 'no-store'});
        res.end(body);
      } catch (error) { report.pageErrors.push('asset server: ' + error.message); res.writeHead(500); res.end(); }
    });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    origin = 'http://127.0.0.1:' + server.address().port;
    profile = await fs.mkdtemp(path.join(os.tmpdir(), 'wingman-status-strip-'));
    browser = spawn(values.chrome, ['--headless=new', '--disable-background-networking', '--disable-component-update', '--disable-default-apps',
      '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check', '--metrics-recording-only',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], {stdio: ['ignore', 'ignore', 'pipe']});
    let launchError; report.chromeStderr = '';
    browser.on('error', error => { launchError = error; });
    browser.stderr.on('data', data => { report.chromeStderr = (report.chromeStderr + data).slice(-6000); });
    const port = await ready(async () => {
      if (launchError) throw launchError;
      if (browser.exitCode !== null) throw new Error('Chrome exited: ' + report.chromeStderr);
      try { return Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); }
      catch (error) { if (error.code !== 'ENOENT') throw error; return false; }
    }, 'owned Chrome port');
    const targets = await (await fetch('http://127.0.0.1:' + port + '/json/list', {signal: AbortSignal.timeout(10000)})).json();
    const target = targets.find(t => t.type === 'page');
    if (!target) throw new Error('No page target');
    send = await cdp(target.webSocketDebuggerUrl, ({method, params}) => {
      if (method === 'Runtime.exceptionThrown') report.pageErrors.push(params.exceptionDetails);
      if (method === 'Runtime.consoleAPICalled' && params.type === 'error') report.pageErrors.push(params.args);
      if (method === 'Fetch.requestPaused') {
        const local = new URL(params.request.url).origin === origin;
        report.requests.push({url: params.request.url, method: params.request.method, blocked: !local});
        send(local ? 'Fetch.continueRequest' : 'Fetch.failRequest', local ? {requestId: params.requestId} : {requestId: params.requestId, errorReason: 'BlockedByClient'})
          .catch(error => report.pageErrors.push(error.message));
      }
    });
    await send('Runtime.enable'); await send('Page.enable'); await send('Accessibility.enable');
    await send('Fetch.enable', {patterns: [{urlPattern: '*'}]});
    await send('Page.addScriptToEvaluateOnNewDocument', {source: `
      window.open = function () { throw new Error('window.open forbidden'); };
      Object.defineProperty(navigator, 'clipboard', {value: Object.fromEntries(['read','write','readText','writeText'].map(k => [k, () => { throw new Error('clipboard forbidden'); }]))});
      const exec = document.execCommand.bind(document);
      document.execCommand = function (command, ...args) { if (/^(copy|cut|paste)$/i.test(command)) throw new Error('clipboard forbidden'); return exec(command, ...args); };
    `});
    await send('Page.navigate', {url: origin + '/index.html?dev=1'});
    await ready(async () => {
      const r = await send('Runtime.evaluate', {expression: "document.readyState === 'complete' && !!window.WM && !!window.onProgress && document.fonts.status === 'loaded'", returnByValue: true});
      return r.result.value;
    }, 'real page and fonts');
    const toggles = await send('Runtime.evaluate', {awaitPromise: true, returnByValue: true, expression: `(async () => {
      const calls = [], checks = [], original = WM.send;
      WM.send = (...args) => { calls.push(args); return Promise.resolve({applied:true, persisted:true, error:null}); };
      try {
        for (const [id, handler, method] of [['btn-sigbar', onSigBarState, 'toggle_sig_bar'], ['btn-fleetbar', onFleetBarState, 'toggle_fleet_bar']]) {
          const button = WM.el(id);
          handler({enabled:false, revision:1, characters:[]}); button.click(); await Promise.resolve();
          checks.push({name:id+' click waits for push', pass:button.getAttribute('aria-pressed') === 'false' && !button.classList.contains('active')});
          handler({enabled:true, revision:2, characters:[]});
          checks.push({name:id+' push enables', pass:button.getAttribute('aria-pressed') === 'true' && button.classList.contains('active')});
          button.click(); await Promise.resolve(); handler({enabled:false, revision:3, characters:[]});
          checks.push({name:id+' push disables and request direction', pass:button.getAttribute('aria-pressed') === 'false' && !button.classList.contains('active') && JSON.stringify(calls.splice(0)) === JSON.stringify([[method,true],[method,false]])});
        }
        return checks;
      } finally { WM.send = original; }
    })()`});
    if (toggles.exceptionDetails || !Array.isArray(toggles.result.value)) throw new Error('Toggle checks did not complete');
    report.assertions.push(...toggles.result.value);
    const spaced = 'Synthetic long status '.repeat(25), unbroken = 'X'.repeat(500);
    const states = [
      {name:'idle', text:'Idle', kind:'FG', visible:false, percent:''},
      {name:'busy55', text:'Uploading', kind:'FG', busy:true, progress:{pct:55,busy:true}, visible:true, percent:'55%', scale:0.55},
      {name:'spaced55', text:spaced, kind:'ERROR', busy:true, progress:{pct:55,busy:true}, visible:true, percent:'55%', scale:0.55},
      {name:'unbroken55', text:unbroken, kind:'ERROR', busy:true, progress:{pct:55,busy:true}, visible:true, percent:'55%', scale:0.55},
      {name:'long-no-progress', text:spaced, kind:'ERROR', visible:false, percent:''},
      {name:'indeterminate', text:spaced, kind:'WARNING', busy:true, progress:{mode:'indeterminate',busy:true}, visible:true, percent:''},
      {name:'busy0', text:'Starting', kind:'FG', busy:true, progress:{pct:0,busy:true}, visible:true, percent:'0%', scale:0},
      {name:'settled100', text:'Finished', kind:'SUCCESS', progress:{pct:100,busy:false}, visible:true, percent:'100%', scale:1},
      {name:'settled0', text:'Cancelled', kind:'FG', progress:{pct:0,busy:false}, visible:false, percent:''},
      {name:'route-busy', text:spaced, kind:'ERROR', busy:true, progress:{pct:55,busy:true}, route:true, visible:true, percent:'55%', scale:0.55},
      {name:'route-settled', text:spaced, kind:'SUCCESS', progress:{pct:100,busy:false}, route:true, visible:false, percent:''},
      {name:'reduced-motion', media:'reduced', text:spaced, kind:'WARNING', busy:true, progress:{mode:'indeterminate',busy:true}, visible:true, percent:''},
      {name:'forced-colors', media:'forced', text:spaced, kind:'ERROR', busy:true, progress:{pct:55,busy:true}, visible:true, percent:'55%', scale:0.55},
      {name:'forced-indeterminate', media:'forced', text:spaced, kind:'WARNING', busy:true, progress:{mode:'indeterminate',busy:true}, visible:true, percent:''},
      {name:'forced-reduced-indeterminate', media:'forced', reduced:true, text:spaced, kind:'WARNING', busy:true, progress:{mode:'indeterminate',busy:true}, visible:true, percent:''}
    ];
    report.expectedCases = 2 * 3 * states.length;
    report.expectedPaintCases = 2 * 3 * states.filter(state => state.media === 'forced').length;
    for (const [width, height] of [[1015, 633], [840, 625]]) {
      await send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor:1, mobile:false});
      const baseline = await send('Runtime.evaluate', {expression: "document.getElementById('statusbar-slot').getBoundingClientRect().height", returnByValue:true});
      for (const eve of ['off', 'ordinary', 'stress']) for (const state of states) {
        await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:state.media === 'reduced' || state.reduced ? 'reduce' : 'no-preference'}, {name:'forced-colors',value:state.media === 'forced' ? 'active' : 'none'}]});
        const c = {...state, width, height, eve, baselineHeight:baseline.result.value, id:width + '-' + eve + '-' + state.name};
        const result = await send('Runtime.evaluate', {expression:'(' + drawState.toString() + ')(' + JSON.stringify(c) + ')', awaitPromise:true, returnByValue:true});
        if (result.exceptionDetails || !result.result.value) throw new Error('Missing case result: ' + c.id + ' ' + JSON.stringify(result.exceptionDetails));
        const measured = result.result.value;
        if (eve === 'ordinary' && ['busy55', 'unbroken55'].includes(state.name)) {
          const ax = await send('Accessibility.getFullAXTree');
          measured.axStaticText = ax.nodes.filter(n => !n.ignored && n.role.value === 'StaticText' && n.name && n.name.value === c.text).map(n => n.name.value);
          measured.assertions.push({name:'AX StaticText retains full status', pass:measured.axStaticText.length > 0});
        }
        report.cases.push(measured);
        if (state.media === 'forced') {
          try {
            const prepared = await send('Runtime.evaluate', {expression:'(' + prepareForcedPaint.toString() + ')(' + JSON.stringify(c) + ', ' + JSON.stringify(negativeControl) + ')', awaitPromise:true, returnByValue:true});
            if (prepared.exceptionDetails || !prepared.result.value) throw new Error('Paint preparation failed: ' + c.id + ' ' + JSON.stringify(prepared.exceptionDetails));
            const paint = prepared.result.value, filename = c.id + '-paint.png';
            const image = await send('Page.captureScreenshot', {format:'png', clip:paint.clip, fromSurface:true});
            await fs.writeFile(path.join(out, filename), Buffer.from(image.data, 'base64')); report.screenshots.push(filename);
            const inspected = await send('Runtime.evaluate', {expression:'(' + inspectForcedPaint.toString() + ')(' + JSON.stringify(image.data) + ', ' + JSON.stringify(paint) + ')', awaitPromise:true, returnByValue:true});
            if (inspected.exceptionDetails || !inspected.result.value) throw new Error('PNG paint inspection failed: ' + c.id + ' ' + JSON.stringify(inspected.exceptionDetails));
            measured.assertions.push(...paint.assertions, ...inspected.result.value.assertions);
            delete paint.assertions; delete inspected.result.value.assertions;
            measured.paint = {...paint, ...inspected.result.value, screenshot:filename};
          } finally {
            const restored = await send('Runtime.evaluate', {expression:'window.__restoreStatusPaint && window.__restoreStatusPaint()', returnByValue:true});
            measured.assertions.push({name:'paint sampling restores inline and computed bar styles',
              pass:!restored.exceptionDetails && restored.result.value === true});
          }
        }
        if (eve === 'ordinary' && ['idle', 'spaced55', 'reduced-motion'].includes(state.name)) {
          const image = await send('Page.captureScreenshot', {format:'png'}), filename = c.id + '.png';
          await fs.writeFile(path.join(out, filename), Buffer.from(image.data, 'base64')); report.screenshots.push(filename);
        }
      }
    }
    report.assertions.push({name:'all matrix results present', pass:report.cases.length === report.expectedCases},
      {name:'all forced-color PNG paint results present', pass:report.cases.filter(c => c.paint).length === report.expectedPaintCases});
  } catch (error) { report.fatal = error.stack; }
  finally {
    if (send) send.close();
    if (browser && browser.pid && browser.exitCode === null) {
      browser.kill('SIGTERM');
      await ready(() => browser.exitCode !== null || browser.signalCode !== null, 'Chrome cleanup').catch(() => browser.kill('SIGKILL'));
    }
    if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
    if (profile) await fs.rm(profile, {recursive:true, force:true, maxRetries:5, retryDelay:100});
    report.assertions.push({name:'no JavaScript or request errors', pass:report.pageErrors.length === 0},
      {name:'no external requests attempted', pass:report.requests.every(r => !r.blocked)});
    const assertions = report.assertions.concat(report.cases.flatMap(c => c.assertions));
    const paintAssertions = assertions.filter(a => a.name.startsWith('paint:'));
    report.totals = {cases:report.cases.length, assertions:assertions.length, passed:assertions.filter(a => a.pass).length, failed:assertions.filter(a => !a.pass).length,
      paintCases:report.cases.filter(c => c.paint).length, paintAssertions:paintAssertions.length, paintFailed:paintAssertions.filter(a => !a.pass).length};
    await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report.totals) + '\n' + path.join(out, 'report.json'));
    if (report.fatal) console.error(report.fatal);
    process.exitCode = report.fatal || report.totals.failed || report.cases.length !== report.expectedCases ? 1 : 0;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
