/* FlyGD Wingman — the probe formation editor.
 *
 * A sub-screen of Profiles on a route id the title bar never shows (see
 * app.js's WM.route map and index.html's #route-formations comment).
 *
 * Edit state lives here in km (positions) and AU (ranges); the bridge and
 * the .dat both speak meters, so the two conversions happen in exactly two
 * places -- load() and save() -- and nowhere else. A third one is a double
 * conversion, and the failure is silent: a formation 1000x out still draws
 * as a formation. test_page_conventions.py pins the count.
 *
 * Ids travel with their formation (null = new). The client keys its
 * selectedFormationID on the id, so a save that re-numbered by list
 * position would move which formation the client has selected -- the bug
 * docs/eve-settings-decode-design.md names in eve-wrench.
 *
 * Deliberately dumb about validity, for evesettings.js's reason: nothing
 * in this repo executes JavaScript, so what a legal formation IS lives in
 * wingman/evesettings/formations.py, which is tested. This file captures
 * edits, sends them, and renders the answer.
 */
(function () {
  'use strict';

  var KM = 1000;
  var AU = 149597870700;
  // The launcher holds eight. Kept in step with formations.MAX_PROBES by
  // Python refusing a ninth -- this only stops the button offering one.
  var MAX_PROBES = 8;
  // Valid scan ranges are powers of two from 0.25 to 32 AU.
  var RANGES = [0.25, 0.5, 1, 2, 4, 8, 16, 32];

  var state = {
    path: '', name: '', formations: [], selected: 0, dirty: false, busy: false
  };
  var yaw = 0.6, pitch = 0.4, dragging = false, lastX = 0, lastY = 0;

  function probe(x, y, z) { return { x: x, y: y, z: z, range: 32 }; }
  function spread(d) {
    return [probe(d, 0, 0), probe(-d, 0, 0), probe(0, 0, d), probe(0, 0, -d),
            probe(0, d, 0), probe(0, -d, 0), probe(0, 2 * d, 0),
            probe(0, -2 * d, 0)];
  }
  // A line of seven along one axis plus one counterweight so the centroid
  // is zero: EVE re-centres a launched formation on its centroid, so a
  // one-sided line would launch centred on the ship rather than reaching
  // the way it is drawn.
  function stack(axis, sign) {
    var total = 0, out = [], i, d;
    for (i = 1; i <= 7; i++) { total += i * 200; }
    for (i = 1; i <= 8; i++) {
      d = (i <= 7 ? i * 200 : -total) * sign;
      out.push(probe(axis === 'x' ? d : 0, axis === 'y' ? d : 0,
                     axis === 'z' ? d : 0));
    }
    return out;
  }
  var PRESETS = [
    { id: 'blank', label: 'Blank spread (250 km)',
      probes: function () { return spread(250); } },
    { id: 'pinpoint', label: 'Pinpoint (500 km)',
      probes: function () { return spread(500); } },
    { id: 'drifter', label: 'Drifter', probes: function () {
      return [probe(11000, 3400, 0), probe(-11000, -3400, 0)]
        .concat(spread(250).slice(0, 6));
    } },
    { id: 'north', label: 'Stack north',
      probes: function () { return stack('z', 1); } },
    { id: 'south', label: 'Stack south',
      probes: function () { return stack('z', -1); } },
    { id: 'west', label: 'Stack west',
      probes: function () { return stack('x', 1); } },
    { id: 'east', label: 'Stack east',
      probes: function () { return stack('x', -1); } },
    { id: 'up', label: 'Stack up',
      probes: function () { return stack('y', 1); } },
    { id: 'down', label: 'Stack down',
      probes: function () { return stack('y', -1); } }
  ];

  function current() { return state.formations[state.selected] || null; }
  function round3(v) { return Math.round(v * 1000) / 1000; }
  function markDirty() { state.dirty = true; paintCommit(); }

  function centroid(f) {
    var c = { x: 0, y: 0, z: 0 }, n = f.probes.length, i;
    if (!n) { return c; }
    for (i = 0; i < n; i++) {
      c.x += f.probes[i].x; c.y += f.probes[i].y; c.z += f.probes[i].z;
    }
    return { x: c.x / n, y: c.y / n, z: c.z / n };
  }
  function shift(f) {
    var c = centroid(f);
    return Math.sqrt(c.x * c.x + c.y * c.y + c.z * c.z);
  }
  // Half a km, not zero: the coordinates are f64 meters coming back from
  // the file and a formation the user drew as symmetric can miss by
  // floating-point dust. Half a km is invisible at every scan range and
  // is well under the smallest offset anyone types.
  function balanced(f) { return shift(f) < 0.5; }

  // Zero the centroid with one counterweight: append if the launcher has
  // room, otherwise repurpose the last probe.
  function balance() {
    var f = current(), full, rest, s = { x: 0, y: 0, z: 0 }, i, cw;
    if (!f || !f.probes.length || balanced(f)) { return; }
    full = f.probes.length >= MAX_PROBES;
    rest = full ? f.probes.slice(0, -1) : f.probes;
    for (i = 0; i < rest.length; i++) {
      s.x += rest[i].x; s.y += rest[i].y; s.z += rest[i].z;
    }
    cw = { x: round3(-s.x), y: round3(-s.y), z: round3(-s.z),
           range: rest[0].range };
    if (full) { f.probes[f.probes.length - 1] = cw; } else { f.probes.push(cw); }
    markDirty(); renderProbes(); renderPreview();
  }

  /* ---- load / save: the only two places meters appear ---- */
  function fromMeters(f) {
    return { id: f.id, name: f.name, probes: f.probes.map(function (p) {
      return { x: p.x / KM, y: p.y / KM, z: p.z / KM, range: p.range / AU };
    }) };
  }
  function toMeters(f) {
    return { id: f.id, name: f.name, probes: f.probes.map(function (p) {
      return { x: p.x * KM, y: p.y * KM, z: p.z * KM, range: p.range * AU };
    }) };
  }

  function load(path) {
    state.busy = true; paintCommit();
    return WM.send('eve_settings_formations', path).then(function (reply) {
      state.busy = false;
      if (!reply || !reply.ok) {
        // Back to Profiles FIRST, so the answer is read over the screen
        // that offered the button rather than over an empty editor.
        //
        // WM.confirm, because it is the only dialog the page owns and it
        // has no OK-only face (panel.js hides Cancel for kind 'info',
        // which only Python can raise). Both answers mean the same thing
        // here -- you are already back on Profiles -- so the reply is
        // deliberately not read.
        WM.route('evesettings');
        WM.confirm('Formations',
                   (reply && reply.error) || 'The file could not be read.');
        return;
      }
      state.path = reply.path;
      state.name = reply.name;
      state.formations = reply.formations.map(fromMeters);
      state.selected = 0;
      state.dirty = false;
      WM.el('fm-account').textContent = reply.name;
      renderAll();
    });
  }

  function save() {
    if (state.busy || !state.path) { return; }
    state.busy = true; paintCommit();
    WM.send('eve_settings_save_formations', state.path,
            state.formations.map(toMeters)).then(function (accepted) {
      // The bridge returns as soon as a worker is spawned, so a falsy
      // answer means none did and nothing will ever push. Same contract
      // evesettings.js's mutate() is written against.
      if (!accepted) { state.busy = false; paintCommit(); }
    });
  }

  // onEveSettingsDone has ONE owner, evesettings.js: WM.handle assigns
  // window[name] outright, so a second registration here would silently
  // replace the Profiles handler and leave copy, backup and restore stuck
  // busy for the rest of the session. Profiles forwards the push here
  // instead. test_page_conventions.py pins both halves.
  WM.formationsDone = function (payload) {
    if (WM.current_route !== 'formations') { return; }
    state.busy = false;
    if (payload && payload.ok) { state.dirty = false; }
    paintCommit();
  };

  /* ---- rendering ---- */
  function renderAll() {
    renderList(); renderPane(); renderPreview(); paintCommit();
  }

  function renderList() {
    var box = WM.el('fm-list');
    box.textContent = '';
    if (!state.formations.length) {
      box.appendChild(WM.make('div', 'empty', 'No formations yet.'));
      return;
    }
    state.formations.forEach(function (f, i) {
      // .fm-item, NOT .rail-item. The two share one rule in style.css
      // because they are one affordance, but app.js sweeps every
      // `.rail-item` on the page when a Settings section changes and
      // toggles `active` from its data-section -- which would quietly
      // un-select whichever formation is open. Same treatment, different
      // name, so that sweep cannot reach here.
      var item = WM.make('button', 'fm-item' + (i === state.selected ? ' active' : ''),
                         f.name || 'Unnamed');
      item.type = 'button';
      item.addEventListener('click', function () {
        state.selected = i;
        renderAll();
      });
      box.appendChild(item);
    });
  }

  function renderPane() {
    var f = current();
    WM.el('fm-name').value = f ? f.name : '';
    WM.setEnabled('fm-name', !!f);
    WM.setEnabled('fm-delete', !!f);
    WM.setEnabled('fm-add-probe', !!f && f.probes.length < MAX_PROBES);
    renderProbes();
  }

  function rangeSelect(value, onChange, label) {
    var sel = document.createElement('select'), opts = RANGES.slice();
    sel.className = 'field';
    sel.setAttribute('aria-label', label);
    // Keep an out-of-range value from an existing file SELECTABLE rather
    // than rewriting it: the design doc's format note is explicit that a
    // value the editor does not offer is still the user's.
    if (opts.indexOf(value) === -1 && isFinite(value)) {
      opts.push(value);
      opts.sort(function (a, b) { return a - b; });
    }
    opts.forEach(function (r) {
      var o = document.createElement('option');
      o.value = String(r);
      o.textContent = r + ' AU';
      sel.appendChild(o);
    });
    sel.value = String(value);
    sel.addEventListener('change', function () { onChange(Number(sel.value)); });
    return sel;
  }

  function renderProbes() {
    var grid = WM.el('fm-probes'), f = current();
    grid.textContent = '';
    if (!f) {
      WM.setEnabled('fm-all-range', false);
      paintBalance();
      return;
    }
    ['#', 'West (km)', 'Up (km)', 'North (km)', 'Range', ''].forEach(function (h) {
      grid.appendChild(WM.make('div', 'fm-head', h));
    });
    f.probes.forEach(function (p, i) {
      grid.appendChild(WM.make('div', 'fm-idx', String(i + 1)));
      ['x', 'y', 'z'].forEach(function (axis) {
        var input = document.createElement('input');
        input.type = 'number';
        input.className = 'field';
        input.step = 'any';
        input.value = String(p[axis]);
        input.setAttribute('aria-label', 'Probe ' + (i + 1) + ' ' + axis);
        // `change`, so a half-typed value never commits: DESIGN.md's rule
        // for free text is Enter or an explicit button, never blur alone,
        // and a number input fires change on both.
        input.addEventListener('change', function () {
          var n = Number(input.value);
          if (input.value !== '' && isFinite(n)) {
            p[axis] = n;
            markDirty();
            // paintBalance, NOT renderProbes: rebuilding the grid from
            // inside one of its own inputs' change handler destroys the
            // element the event is still running on and drops the focus
            // the user was about to tab out of.
            paintBalance();
            renderPreview();
          } else {
            input.value = String(p[axis]);
          }
        });
        grid.appendChild(input);
      });
      grid.appendChild(rangeSelect(p.range, function (r) {
        p.range = r;
        markDirty();
      }, 'Probe ' + (i + 1) + ' range'));
      var rm = WM.make('button', 'linkbtn', 'Remove');
      rm.type = 'button';
      rm.addEventListener('click', function () {
        f.probes.splice(i, 1);
        markDirty();
        renderPane();
        renderPreview();
      });
      grid.appendChild(rm);
    });
    // An ACTION, not a value: the first option is a placeholder so the
    // control never states a range the formation does not have, and it
    // returns to the placeholder after applying one.
    var all = WM.el('fm-all-range');
    all.textContent = '';
    var head = document.createElement('option');
    head.value = '';
    head.textContent = 'Set every range…';
    all.appendChild(head);
    RANGES.forEach(function (r) {
      var o = document.createElement('option');
      o.value = String(r);
      o.textContent = 'All ' + r + ' AU';
      all.appendChild(o);
    });
    all.value = '';
    WM.setEnabled('fm-all-range', !!f.probes.length);
    paintBalance();
  }

  // The one line on this screen that is about what the CLIENT will do
  // rather than about what is drawn: EVE re-centres a launched formation
  // on its centroid, so a formation whose centroid is not the ship lands
  // somewhere other than where it was drawn. Split out of renderProbes
  // because a coordinate edit changes it without changing the grid.
  function paintBalance() {
    var f = current();
    WM.el('fm-balance-note').textContent = f && f.probes.length
      ? (balanced(f)
          ? 'Launches as drawn.'
          : 'Launch shifts every probe by ' + formatKm(shift(f)) + '.')
      : '';
    WM.setEnabled('fm-balance', !!(f && f.probes.length && !balanced(f)));
  }

  function formatKm(km) {
    var AU_KM = AU / KM;
    return km >= AU_KM / 100
      ? (km / AU_KM).toFixed(2) + ' AU'
      : Math.round(km).toLocaleString() + ' km';
  }

  /* ---- SVG preview: yaw/pitch projection, equatorial rings, tethers ----
     Hand-rolled, the way eve-wrench's is: forty lines of trigonometry, no
     library, no build step -- which is the only shape wingman/web/ has
     room for. */
  var SVG = 'http://www.w3.org/2000/svg';
  function el(tag, attrs) {
    var node = document.createElementNS(SVG, tag), k;
    for (k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        node.setAttribute(k, String(attrs[k]));
      }
    }
    return node;
  }
  function project(x, y, z) {
    var x1 = x * Math.cos(yaw) + z * Math.sin(yaw);
    var z1 = -x * Math.sin(yaw) + z * Math.cos(yaw);
    var y1 = y * Math.cos(pitch) - z1 * Math.sin(pitch);
    var depth = y * Math.sin(pitch) + z1 * Math.cos(pitch);
    return { sx: x1, sy: -y1, depth: depth };
  }
  function niceStep(target) {
    var pow = Math.pow(10, Math.floor(Math.log(target) / Math.LN10));
    var mults = [1, 2, 2.5, 5, 10], i;
    for (i = 0; i < mults.length; i++) {
      if (pow * mults[i] >= target) { return pow * mults[i]; }
    }
    return pow * 10;
  }

  // The viewBox is set to the element's own CSS pixel size on every draw,
  // rather than being a fixed square the browser then scales. One user
  // unit is one CSS pixel, so a stroke of 1 is a hairline and the ring
  // labels can take --fs-label from the stylesheet and mean it. A fixed
  // viewBox scaled 9px type down to about 5px at the 840x625 floor, which
  // is the whole reason this is computed rather than declared.
  var MARGIN = 26;

  function renderPreview() {
    var svg = WM.el('fm-preview'), f = current();
    var rect = svg.getBoundingClientRect();
    var w = Math.round(rect.width), h = Math.round(rect.height);
    var cx = w / 2, cy = h / 2;
    var extent = 1, scale, step, i, r, a, pts, p, c, items, label;
    svg.textContent = '';
    // Off-route (or mid-layout) the element has no box, and every
    // coordinate below would be NaN.
    if (!f || w < 2 || h < 2) { return; }
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    f.probes.forEach(function (q) {
      extent = Math.max(extent, Math.abs(q.x), Math.abs(q.y), Math.abs(q.z));
    });
    step = niceStep(extent / 3);
    // The outer ring, not the outermost probe, decides the scale: niceStep
    // rounds up, so three rings can reach half again as far as the widest
    // probe and the outer one would be drawn outside the box.
    scale = Math.max(10, Math.min(w, h) / 2 - MARGIN) / Math.max(extent, step * 3);
    for (i = 1; i <= 3; i++) {
      r = step * i;
      pts = [];
      for (a = 0; a < 72; a++) {
        p = project(r * Math.cos(a / 72 * Math.PI * 2), 0,
                    r * Math.sin(a / 72 * Math.PI * 2));
        pts.push((cx + p.sx * scale).toFixed(1) + ','
                 + (cy + p.sy * scale).toFixed(1));
      }
      svg.appendChild(el('polygon', { points: pts.join(' '), 'class': 'fm-ring' }));
      // At the ring's widest point, end-anchored so the text lands INSIDE
      // the ring it names, and stepped down by a line each so the three do
      // not pile up: the rings flatten with pitch, and at a shallow one
      // three labels on one horizontal line overlap each other.
      label = el('text', { x: cx + r * scale - 4, y: cy + (i - 2) * 13,
                           'class': 'fm-ring-label' });
      label.textContent = formatKm(r);
      svg.appendChild(label);
    }
    // Painted back to front, so a probe in front of another overlaps it
    // rather than the draw order deciding at random.
    items = f.probes.map(function (q, idx) {
      var top = project(q.x, q.y, q.z), base = project(q.x, 0, q.z);
      return { idx: idx, x: cx + top.sx * scale, y: cy + top.sy * scale,
               depth: top.depth,
               bx: cx + base.sx * scale, by: cy + base.sy * scale };
    }).sort(function (m, n) { return m.depth - n.depth; });
    items.forEach(function (it) {
      svg.appendChild(el('line', { x1: it.bx, y1: it.by, x2: it.x, y2: it.y,
                                   'class': 'fm-tether' }));
      svg.appendChild(el('circle', { cx: it.x, cy: it.y, r: 5,
                                     'class': 'fm-probe' }));
      var t = el('text', { x: it.x + 7, y: it.y - 7, 'class': 'fm-probe-label' });
      t.textContent = String(it.idx + 1);
      svg.appendChild(t);
    });
    svg.appendChild(el('circle', { cx: cx, cy: cy, r: 3, 'class': 'fm-ship' }));
    // The centroid is drawn only when it is off the ship, because that is
    // the one state it explains: where the formation will actually be
    // centred once launched. Balance is the control that closes it.
    if (!balanced(f)) {
      c = centroid(f);
      p = project(c.x, c.y, c.z);
      svg.appendChild(el('circle', { cx: cx + p.sx * scale, cy: cy + p.sy * scale,
                                     r: 4, 'class': 'fm-centroid' }));
    }
  }

  function paintCommit() {
    WM.setEnabled('fm-save', state.dirty && !state.busy);
    WM.el('fm-dirty').textContent = state.busy
      ? 'Saving…'
      : (state.dirty ? 'Unsaved changes' : '');
    WM.setEnabled('fm-add', !state.busy);
  }

  /* ---- wiring ---- */
  function wire() {
    var svg = WM.el('fm-preview'), preset = WM.el('fm-preset');
    PRESETS.forEach(function (pr) {
      var o = document.createElement('option');
      o.value = pr.id;
      o.textContent = pr.label;
      preset.appendChild(o);
    });

    WM.el('fm-back').addEventListener('click', function () {
      if (!state.dirty) { WM.route('evesettings'); return; }
      WM.confirm('Discard changes?',
                 'Your formation edits have not been saved.',
                 { destructive: true }).then(function (yes) {
        if (yes) { state.dirty = false; WM.route('evesettings'); }
      });
    });

    WM.el('fm-add').addEventListener('click', function () {
      var pr = PRESETS.filter(function (x) {
        return x.id === preset.value;
      })[0] || PRESETS[0];
      state.formations.push({
        id: null,
        name: 'Formation ' + (state.formations.length + 1),
        probes: pr.probes()
      });
      state.selected = state.formations.length - 1;
      markDirty();
      renderAll();
    });

    WM.el('fm-delete').addEventListener('click', function () {
      var f = current();
      if (!f) { return; }
      // "when you save", because nothing has been written yet: the delete
      // is an edit to the list this screen holds, and Save is the only
      // thing that touches the file.
      WM.confirm('Delete formation?',
                 '"' + f.name + '" is removed when you save.',
                 { destructive: true }).then(function (yes) {
        if (!yes) { return; }
        state.formations.splice(state.selected, 1);
        state.selected = Math.max(0, state.selected - 1);
        markDirty();
        renderAll();
      });
    });

    WM.el('fm-name').addEventListener('change', function () {
      var f = current();
      if (f) {
        f.name = WM.el('fm-name').value.trim();
        markDirty();
        renderList();
      }
    });

    WM.el('fm-add-probe').addEventListener('click', function () {
      var f = current();
      if (f && f.probes.length < MAX_PROBES) {
        f.probes.push(probe(0, 0, 0));
        markDirty();
        renderPane();
        renderPreview();
      }
    });

    WM.el('fm-all-range').addEventListener('change', function () {
      var f = current(), r = Number(WM.el('fm-all-range').value);
      if (!f || WM.el('fm-all-range').value === '' || !isFinite(r)) { return; }
      f.probes.forEach(function (p) { p.range = r; });
      markDirty();
      renderProbes();
    });

    WM.el('fm-balance').addEventListener('click', balance);
    WM.el('fm-save').addEventListener('click', save);

    svg.addEventListener('mousedown', function (e) {
      e.preventDefault();
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener('mouseup', function () { dragging = false; });
    window.addEventListener('mousemove', function (e) {
      if (!dragging) { return; }
      yaw += (e.clientX - lastX) * 0.01;
      pitch = Math.max(-Math.PI / 2,
                       Math.min(Math.PI / 2, pitch + (e.clientY - lastY) * 0.01));
      lastX = e.clientX;
      lastY = e.clientY;
      renderPreview();
    });

    // The viewBox is the element's own pixel size, so a resize changes
    // every coordinate in the drawing.
    window.addEventListener('resize', function () {
      if (WM.current_route === 'formations') { renderPreview(); }
    });

    // Leaving is load-bearing here for one reason only: the drag listeners
    // are on `window`, so a pointer released outside the page while the
    // route changed would leave the preview spinning under the next
    // screen's mouse movement.
    document.addEventListener('wm:route', function (event) {
      if (event.detail !== 'formations') { dragging = false; }
    });
  }

  // The Profiles card's entry point, and the only way in.
  WM.openFormations = function (path) {
    WM.route('formations');
    load(path);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
