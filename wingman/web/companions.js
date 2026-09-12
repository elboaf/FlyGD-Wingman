// Companion configuration owns drafts, never native identity or operation lifetime.
(function () {
  'use strict';
  WM.handle('onCompanionPreviews', function (payload) {
    if (screenshotFixture) {
      if (payload && payload.revision >= screenshotLive.revision) screenshotLive = payload;
      return;
    }
    accept(payload);
  });

  var screenshotFixture = null, screenshotLive = null, screenshotChooser = false;
  // Tool-only presentation, installed before section entry. Pending writes are
  // not a safe capture boundary; fail instead of abandoning their receipts.
  WM.companionsScreenshot = function (payload) {
    if (payload && (payload.kind !== 'companions-screenshot-v1' || JSON.stringify(payload).length > 16384
        || !payload.state || !Array.isArray(payload.state.rows) || payload.state.rows.length !== 2
        || !Array.isArray(payload.sources) || payload.sources.length !== 2)) {
      throw new Error('Invalid companions screenshot fixture');
    }
    if (payload && !screenshotFixture && !WM.el('overlay').hidden) {
      throw new Error('A live dialog is open — finish it before capturing companions');
    }
    if (payload && !screenshotFixture && (requests.length || sourceBusy || selectionBusy || master.busy)) {
      throw new Error('Companion operation in progress — retry capture when settled');
    }
    if (!payload && !screenshotFixture) return;
    var live = screenshotFixture ? screenshotLive : state;
    epoch += 1; flow += 1; requests = [];
    if (screenshotChooser) { WM.el('dlg-cancel').click(); screenshotChooser = false; }
    sourceBusy = selectionBusy = false; message = recoveryMessage = '';
    recovering = false; recoveryOperation = null;
    master.queue = []; master.busy = false; master.error = '';
    views = Object.create(null); WM.el('companion-list').textContent = '';
    WM.el('companion-add-form').hidden = true; WM.el('companion-add-label').value = '';
    addMode = 'whole'; WM.el('companion-add-whole').checked = true; WM.el('companion-add-region').checked = false;
    screenshotFixture = payload ? JSON.parse(JSON.stringify(payload)) : null;
    screenshotLive = payload ? live : null;
    state = {revision: -1, rows: [], operations: [], limits: {}};
    hydrated = false;
    if (payload || live.revision >= 0) accept(payload ? screenshotFixture.state : live);
    else master.base = false;
    paint();
  };

  var state = {revision: -1, rows: [], operations: [], limits: {}};
  var hydrated = false, active = false, epoch = 0, flow = 0;
  var views = Object.create(null), requests = [];
  var sourceBusy = false, selectionBusy = false, message = '';
  var recovering = false, recoveryOperation = null, recoveryMessage = '';
  var addMode = 'whole';
  var master = {base: false, seq: 0, busy: false, queue: [], error: ''};
  var statuses = {
    off: 'Off', disabled: 'Disabled', live: 'Live', waiting: 'Waiting for source',
    'needs-selection': 'Multiple matches — reselect source',
    'source-unavailable': 'Source unavailable — reselect source', stopping: 'Stopping…'
  };

  function ready() { return active && hydrated && state.available; }
  function owns(view) { return views[view.row.id] === view; }
  function pending(row) { return row.pending_operation_id !== null && row.pending_operation_id !== undefined; }
  function countText(text) {
    // Python validators count Unicode code points, not UTF-16 code units.
    return (text.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]|[\s\S]/g) || []).length;
  }
  function textError(name, value) {
    var maximum = name === 'label' ? state.limits.label_max_chars : state.limits.title_hint_max_chars;
    if (!value.trim()) return name === 'label' ? 'Enter a label.' : 'Enter a window title to match.';
    return countText(value) > maximum ? 'Use at most ' + maximum + ' characters.' : '';
  }
  function outcome(result) {
    if (!result) return 'Could not confirm the request. Refresh this section before retrying.';
    if (result.applied && !result.persisted) return result.error || 'Applied for this session only. This change will not survive restart.';
    return result.error || (result.applied ? '' : 'The change was not applied. Try again.');
  }
  function refresh() {
    if (screenshotFixture) { accept(screenshotFixture.state); return; }
    var owner = epoch;
    WM.send('companion_previews_state').then(function (payload) {
      if (owner !== epoch || !active) return;
      if (!payload) { message = 'Could not load companions. Reopen this section to retry.'; paint(); return; }
      accept(payload);
    });
  }

  // Terminal receipts are retained in state. Do not mistake a pending bridge
  // reply for the latest outcome: its completion event can arrive first.
  function request(send, done, screenshotRead) {
    if (screenshotFixture && !screenshotRead) return;
    recoveryOperation = null; recoveryMessage = '';
    var item = {operation: null, result: null, done: done, refreshing: false};
    requests.push(item);
    send().then(function (result) {
      if (requests.indexOf(item) === -1) return;
      item.result = result || {pending: false, applied: false, persisted: false,
        error: 'Could not confirm the request. Reopen this section before retrying.'};
      item.operation = result && result.operation_id;
      settle();
      paint();
    });
  }
  function settle() {
    requests.slice().forEach(function (item) {
      if (!item.result) return;
      var retained = state.operations.filter(function (receipt) {
        return receipt.operation_id === item.operation;
      })[0];
      // A terminal direct response cannot be demoted by an older pending push.
      var result = retained && !retained.pending ? retained : item.result;
      if (result.pending) return;
      // Generation for a queued write comes from acknowledged state, not a
      // guessed increment. A direct success may precede its state publication.
      if (result.applied && result.revision > state.revision && !result.sources) {
        if (!item.refreshing && active) { item.refreshing = true; refresh(); }
        return;
      }
      requests.splice(requests.indexOf(item), 1);
      item.done(result);
    });
  }
  function accept(payload) {
    if (!payload || typeof payload.revision !== 'number' || payload.revision < state.revision) return;
    state = payload;
    hydrated = active;
    master.base = !!state.enabled;
    if (recovering) {
      recovering = false;
      // Operation IDs are monotonic controller counters, unlike definition IDs.
      // Recover the most recent outcome without reusing abandoned page drafts.
      var latest = state.operations.reduce(function (previous, receipt) {
        return !previous || receipt.operation_id > previous.operation_id ? receipt : previous;
      }, null);
      recoveryOperation = latest && latest.operation_id;
    }
    if (recoveryOperation !== null) {
      var recovered = state.operations.filter(function (receipt) {
        return receipt.operation_id === recoveryOperation && !receipt.pending;
      })[0];
      if (recovered) {
        recoveryMessage = !recovered.sources && outcome(recovered)
          ? 'Last companion operation: ' + outcome(recovered) : '';
        recoveryOperation = null;
      }
    }
    var kept = Object.create(null);
    state.rows.forEach(function (row) {
      kept[row.id] = true;
      var view = views[row.id];
      if (!view) { view = makeRow(row); views[row.id] = view; WM.el('companion-list').appendChild(view.node); }
      view.row = row;
      Object.keys(view.fields).forEach(function (name) {
        var field = view.fields[name];
        field.base = name === 'label' || name === 'enabled' ? row[name] : row.source[name];
        if (!field.dirty) setValue(field, field.base);
      });
      if (!view.modeDirty) view.mode = row.mode;
    });
    Object.keys(views).forEach(function (id) {
      if (!kept[id]) { views[id].node.remove(); delete views[id]; }
    });
    settle();
    Object.keys(views).forEach(function (id) { drain(views[id]); });
    paint();
  }
  function setValue(field, value) {
    field.value = value;
    if (field.name === 'enabled') field.input.checked = value;
    else field.input.value = value;
  }
  function changeField(view, name) {
    var field = view.fields[name];
    field.seq += 1;
    field.value = name === 'enabled' ? field.input.checked : field.input.value;
    field.dirty = true;
    field.error = '';
    paintField(field);
  }
  function paintField(field) {
    var unsent = field.dirty && field.name !== 'enabled' && field.name !== 'title_mode';
    field.status.textContent = field.error || (unsent ? 'Press Enter or Apply to commit.' : '');
    field.status.className = 'hint' + (field.error ? ' err' : '');
  }
  function commit(view, name) {
    if (screenshotFixture) return;
    if (!ready() || !owns(view)) return;
    var field = view.fields[name];
    var error = name === 'label' || name === 'title_hint' ? textError(name, field.value) : '';
    if (error) { field.error = error; paintField(field); return; }
    view.queue.push({name: name, value: field.value, seq: field.seq, epoch: epoch});
    drain(view);
  }
  function drain(view) {
    if (!owns(view) || view.busy || pending(view.row) || !ready()) return;
    var edit = view.queue.shift();
    if (!edit) return;
    if (edit.epoch !== epoch) { drain(view); return; }
    var row = view.row;
    view.busy = true;
    request(function () {
      if (edit.name === 'enabled') return WM.send('companion_preview_set_enabled', row.id, edit.value, row.generation);
      // Each field commits independently. Never include another field's unsent
      // text merely because the controller accepts one complete edit proposal.
      return WM.send('companion_preview_edit', row.id,
        edit.name === 'label' ? edit.value : row.label,
        edit.name === 'title_mode' ? edit.value : row.source.title_mode,
        edit.name === 'title_hint' ? edit.value : row.source.title_hint,
        row.generation);
    }, function (result) {
      if (!owns(view)) return;
      view.busy = false;
      var field = view.fields[edit.name];
      if (edit.epoch === epoch && field.seq === edit.seq) {
        field.dirty = false;
        setValue(field, field.base);
        field.error = !result.applied && view.row.generation !== row.generation
          && result.revision < state.revision ? '' : outcome(result);
      }
      drain(view);
    });
    paint();
  }
  function mutate(view, send) {
    if (screenshotFixture) return;
    if (!ready() || !owns(view) || view.busy || pending(view.row)) return;
    view.busy = true;
    view.error = '';
    var owner = epoch;
    request(send, function (result) {
      if (!owns(view)) return;
      view.busy = false;
      if (owner === epoch) view.error = outcome(result);
      drain(view);
    });
    paint();
  }
  function button(view, name, text, callback, parent) {
    var node = WM.make('button', name === 'remove' ? 'btn danger' : 'btn', text);
    node.id = 'companion-' + view.row.id + '-' + name;
    node.type = 'button'; node.addEventListener('click', callback);
    parent.appendChild(node); return node;
  }
  function makeField(view, name, labelText, parent) {
    var group = WM.make('div', 'row');
    var input = WM.make(name === 'title_mode' ? 'select' : 'input', 'field');
    input.id = 'companion-' + view.row.id + '-' + name;
    var label = WM.make('label', 'lab', labelText); label.htmlFor = input.id;
    group.appendChild(label); group.appendChild(input);
    if (name === 'title_mode') {
      [['exact', 'Exactly matches'], ['contains', 'Contains']].forEach(function (option) {
        var node = WM.make('option', '', option[1]); node.value = option[0]; input.appendChild(node);
      });
    } else { input.type = 'text'; input.autocomplete = 'off'; }
    var status = WM.make('span', 'hint'); status.id = input.id + '-status';
    input.setAttribute('aria-describedby', status.id);
    var field = {name: name, input: input, status: status, seq: 0, dirty: false, error: ''};
    view.fields[name] = field;
    if (name === 'title_mode') {
      input.addEventListener('change', function () { changeField(view, name); commit(view, name); });
    } else {
      input.addEventListener('input', function () { changeField(view, name); });
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') { event.preventDefault(); commit(view, name); }
      });
      field.apply = button(view, name + '-apply', 'Apply', function () { commit(view, name); }, group);
    }
    group.appendChild(status); parent.appendChild(group);
  }
  function modeRadios(view, parent) {
    var group = WM.make('div', 'row');
    var label = WM.make('span', 'lab', 'Capture when selecting a source');
    label.id = 'companion-' + view.row.id + '-mode-label'; group.appendChild(label);
    var modes = WM.make('div', 'companion-actions');
    modes.setAttribute('role', 'radiogroup'); modes.setAttribute('aria-labelledby', label.id);
    view.radios = {};
    [['whole', 'Whole window'], ['region', 'Selected region']].forEach(function (pair) {
      var label = WM.make('label', 'radio'); var input = WM.make('input');
      input.type = 'radio'; label.appendChild(input); label.appendChild(WM.make('span', 'ring'));
      label.appendChild(WM.make('span', '', pair[1]));
      input.name = 'companion-' + view.row.id + '-mode'; input.value = pair[0];
      input.addEventListener('change', function () {
        if (input.checked) { view.mode = pair[0]; view.modeDirty = true; }
      });
      view.radios[pair[0]] = input; modes.appendChild(label);
    });
    group.appendChild(modes); parent.appendChild(group);
  }
  function makeRow(row) {
    var view = {row: row, node: WM.make('div', 'companion-row'), fields: {}, queue: [], busy: false, error: '', mode: row.mode};
    var summary = WM.make('div', 'companion-summary');
    var check = WM.make('label', 'check'), input = WM.make('input');
    input.type = 'checkbox'; check.appendChild(input); check.appendChild(WM.make('span', 'box'));
    check.appendChild(WM.make('span', '', 'Enabled'));
    input.id = 'companion-' + row.id + '-enabled';
    input.addEventListener('change', function () { changeField(view, 'enabled'); commit(view, 'enabled'); });
    var enabledStatus = WM.make('span', 'hint');
    view.fields.enabled = {name: 'enabled', input: input, status: enabledStatus, seq: 0, dirty: false, error: ''};
    view.name = WM.make('strong', 'companion-name');
    view.source = WM.make('span', 'companion-source hint');
    view.modeText = WM.make('span', 'hint');
    view.status = WM.make('span', 'hint'); view.status.id = 'companion-' + row.id + '-status';
    view.status.setAttribute('role', 'status');
    var identity = WM.make('div', 'companion-identity'); identity.appendChild(view.name); identity.appendChild(view.source);
    summary.appendChild(identity); summary.appendChild(check); summary.appendChild(view.modeText);
    view.node.appendChild(summary); view.node.appendChild(view.status); view.node.appendChild(enabledStatus);
    var details = WM.make('details', 'companion-detail'); details.appendChild(WM.make('summary', '', 'Edit & source'));
    makeField(view, 'label', 'Label', details);
    makeField(view, 'title_mode', 'Window title matching', details);
    makeField(view, 'title_hint', 'Window title', details);
    modeRadios(view, details);
    var actions = WM.make('div', 'companion-actions');
    view.reselect = button(view, 'source', 'Reselect source…', function () { chooseSource(view); }, actions);
    view.region = button(view, 'region', 'Reselect region…', function () {
      if (screenshotFixture) return;
      WM.endPreviewCapture();
      mutate(view, function () { return WM.send('companion_preview_reselect_region', row.id, view.row.generation); });
    }, actions);
    view.reset = button(view, 'reset', 'Reset position', function () {
      mutate(view, function () { return WM.send('companion_preview_reset_geometry', row.id, view.row.generation); });
    }, actions);
    view.remove = button(view, 'remove', 'Remove…', function () {
      if (screenshotFixture) return;
      if (!ready() || view.busy || pending(view.row)) return;
      WM.endPreviewCapture();
      var owner = epoch, generation = view.row.generation;
      WM.confirm('Remove "' + view.row.label + '"?',
        'Remove this saved companion, its region and position. This cannot be undone. The source application stays open.',
        {destructive: true}).then(function (yes) {
        if (!yes || owner !== epoch || !owns(view) || view.row.generation !== generation) return;
        mutate(view, function () { return WM.send('companion_preview_remove', row.id, generation); });
      });
    }, actions);
    details.appendChild(actions); view.node.appendChild(details);
    return view;
  }
  function chooseSource(view) {
    if (!ready() || sourceBusy || selectionBusy || (view && (view.busy || pending(view.row)))) return;
    var label = view ? view.row.label : WM.el('companion-add-label').value;
    var error = textError('label', label);
    if (error) { message = error; paint(); return; }
    var owner = epoch, attempt = ++flow, generation = view && view.row.generation;
    var mode = view ? view.mode : addMode;
    function current() { return ready() && epoch === owner && flow === attempt && (!view || (owns(view) && view.row.generation === generation)); }
    sourceBusy = true; message = 'Finding source windows…';
    if (!screenshotFixture) WM.endPreviewCapture();
    request(function () {
      return screenshotFixture ? Promise.resolve({applied: true, persisted: true, pending: false, sources: screenshotFixture.sources})
        : WM.send('companion_previews_sources');
    }, function (result) {
      if (owner !== epoch || attempt !== flow) return;
      sourceBusy = false;
      if (!current()) return;
      if (result.error || !result.sources) { message = outcome(result); return; }
      if (!result.sources.length) {
        message = 'No eligible source windows. Open a non-EVE window, then choose source again.'; return;
      }
      message = '';
      sourceBusy = true;
      if (!screenshotFixture) WM.endPreviewCapture();
      screenshotChooser = !!screenshotFixture;
      WM.choose('Choose companion source', 'Select a non-EVE window to preview.',
        [{label: 'Open windows', options: result.sources.map(function (source) {
          return {value: source.candidate_token, label: source.application + ' — ' + source.title};
        })}], 'Choose', 'Source', {compact: true}).then(function (token) {
        if (owner !== epoch || attempt !== flow) return;
        sourceBusy = false;
        screenshotChooser = false;
        // Choosing a fixture option must never be a native selection, even if
        // someone presses Choose while the capture tool has the dialog open.
        if (screenshotFixture) { paint(); return; }
        if (!current() || token === null) { paint(); return; }
        var source = result.sources.filter(function (item) { return item.candidate_token === token; })[0];
        if (!source) { message = 'Source selection expired. Choose source again.'; paint(); return; }
        selectionBusy = true; message = mode === 'region' ? 'Selecting region… Confirm or cancel in the picker.' : 'Selecting source…';
        if (view) view.busy = true;
        request(function () {
          return WM.send('companion_preview_select', view ? view.row.id : null, token, mode, label,
            view ? view.row.source.title_mode : 'exact', source.title, view ? generation : null);
        }, function (selected) {
          selectionBusy = false;
          if (view && owns(view)) { view.busy = false; drain(view); }
          if (owner !== epoch || attempt !== flow) return;
          message = outcome(selected);
          if (selected.applied) {
            if (!view) { WM.el('companion-add-form').hidden = true; WM.el('companion-add-label').value = ''; }
            else if (owns(view)) { view.modeDirty = false; view.mode = view.row.mode; }
          }
        });
        paint();
      });
    }, true);
    paint();
  }
  function drainMaster() {
    if (screenshotFixture) return;
    if (!ready() || master.busy || !master.queue.length) return;
    var edit = master.queue.shift();
    master.busy = true;
    request(function () { return WM.send('set_companion_previews_enabled', edit.value); }, function (result) {
      master.busy = false;
      if (edit.epoch === epoch && edit.seq === master.seq) master.error = outcome(result);
      drainMaster();
    });
    paint();
  }
  function paint() {
    var enabled = ready();
    WM.setEnabled('companion-enabled', enabled);
    if (!master.busy && !master.queue.length) WM.el('companion-enabled').checked = master.base;
    WM.el('companion-master-status').textContent = master.error;
    WM.el('companion-master-status').className = 'hint' + (master.error ? ' err' : '');
    WM.el('companion-off-note').hidden = !hydrated || !!state.enabled;
    var count = state.rows.filter(function (row) { return row.enabled; }).length;
    var full = state.rows.length >= state.limits.definitions || count >= state.limits.enabled;
    var serverBusy = state.operations.some(function (receipt) { return receipt.pending; });
    WM.setEnabled('companion-add', enabled && !sourceBusy && !selectionBusy && !serverBusy && !full);
    WM.el('companion-count').textContent = hydrated ? count + ' / ' + state.limits.enabled + ' enabled' : '';
    ['label', 'whole', 'region', 'source'].forEach(function (suffix) {
      WM.setEnabled('companion-add-' + suffix, enabled && !sourceBusy && !selectionBusy && !serverBusy && !full);
    });
    WM.el('companion-status').textContent = message || recoveryMessage || (!hydrated ? 'Loading companions…' :
      (!state.available ? 'Companion previews are unavailable in this runtime.' :
        (serverBusy ? 'Change in progress… Waiting for completion.' :
          (full ? 'Companion limit reached. Disable or remove a companion to add another.' : ''))));
    WM.el('companion-empty').hidden = state.rows.length !== 0;
    Object.keys(views).forEach(function (id) {
      var view = views[id], row = view.row;
      view.name.textContent = row.label; view.name.title = row.label;
      view.fields.enabled.input.setAttribute('aria-label', 'Enable ' + row.label);
      view.source.textContent = row.source.executable_name + ' — ' + row.source.last_title;
      view.source.title = view.source.textContent;
      view.modeText.textContent = row.mode === 'region' ? 'Selected region' : 'Whole window';
      view.status.textContent = view.error || row.error || (view.busy || pending(row) ? 'Change in progress…' : statuses[row.status] || row.status);
      view.status.className = 'hint' + (view.error || row.error ? ' err' : '');
      Object.keys(view.fields).forEach(function (name) {
        var field = view.fields[name]; WM.setEnabled(field.input, enabled);
        if (field.apply) WM.setEnabled(field.apply, enabled);
        paintField(field);
      });
      Object.keys(view.radios).forEach(function (mode) {
        view.radios[mode].checked = view.mode === mode;
        WM.setEnabled(view.radios[mode], enabled && !view.busy && !pending(row));
      });
      var mutable = enabled && !view.busy && !pending(row);
      WM.setEnabled(view.reselect, mutable && !sourceBusy && !selectionBusy);
      view.region.hidden = row.mode !== 'region';
      WM.setEnabled(view.region, mutable && !sourceBusy && !selectionBusy);
      WM.setEnabled(view.reset, mutable); WM.setEnabled(view.remove, mutable);
    });
  }
  WM.el('companion-enabled').addEventListener('change', function () {
    if (screenshotFixture || !ready()) return;
    master.seq += 1; master.error = '';
    master.queue.push({value: WM.el('companion-enabled').checked, seq: master.seq, epoch: epoch});
    drainMaster();
  });
  WM.el('companion-add').addEventListener('click', function () {
    if (!ready() || WM.el('companion-add').disabled) return;
    if (!screenshotFixture) WM.endPreviewCapture();
    WM.el('companion-add-form').hidden = false; WM.el('companion-add-label').focus();
  });
  ['whole', 'region'].forEach(function (mode) {
    WM.el('companion-add-' + mode).addEventListener('change', function () {
      if (WM.el('companion-add-' + mode).checked) addMode = mode;
    });
  });
  WM.el('companion-add-source').addEventListener('click', function () { chooseSource(null); });
  WM.el('companion-add-cancel').addEventListener('click', function () {
    flow += 1; sourceBusy = false; message = ''; WM.el('companion-add-form').hidden = true; paint();
  });
  document.addEventListener('wm:section', function (event) {
    active = event.detail === 'companions'; hydrated = false; epoch += 1; flow += 1;
    recovering = active; recoveryOperation = null; recoveryMessage = '';
    // Only local reply ownership ends here. The controller retains admitted
    // operations; the next state read recovers them even if a promise was lost.
    requests = []; sourceBusy = false; selectionBusy = false;
    message = ''; master.queue = []; master.busy = false; master.error = '';
    WM.el('companion-add-form').hidden = true;
    Object.keys(views).forEach(function (id) {
      var view = views[id]; view.queue = []; view.busy = false; view.error = ''; view.modeDirty = false;
      Object.keys(view.fields).forEach(function (name) {
        var field = view.fields[name]; field.seq += 1; field.dirty = false; field.error = ''; setValue(field, field.base);
      });
    });
    if (active) refresh(); else if (!screenshotFixture) WM.endPreviewCapture();
    paint();
  });
  paint();
}());
