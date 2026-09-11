// ---- Gamelog alerts --------------------------------------------------
// Its own section, Settings > Alerts, since round 5's D1 -- it was the
// third card in Settings > Previews, alongside previews.js and the
// keybind block in settings.js. Not folded into either: this owns none
// of the win32/AutoHotkey machinery those files do, and gets its own
// bridge endpoints for the same reason set_preview_enabled does --
// toggling `enabled` changes whether shared telemetry feeds AlertPolicy,
// while Fleet Bar may independently keep the reader running.
//
// A READ, not a push: get_alert_state exists precisely so this can ask
// on wm:section, the same reasoning get_preview_hotkey_state documents --
// shared telemetry can start before the webview exists, so a health change
// discovered at launch would be pushed into a window that is not there yet.
(function () {
  var enabledBox = WM.el('alert-enabled');
  if (!enabledBox) { return; }

  var pveBox = WM.el('alert-pve-filter');
  var persistBox = WM.el('alert-persist');
  var offBanner = WM.el('alerts-previews-off');
  var folderBanner = WM.el('alerts-no-folder');
  var healthLine = WM.el('alerts-health');
  var status = WM.el('alerts-status');
  var depends = WM.el('alerts-depends');
  var collision = WM.el('alerts-collision');

  // Everything below the master switch is a preference that CAN be
  // recorded for later, so none of it is disabled -- that is S3's rule,
  // applied one card up by settings.js's restore-preview-positions block
  // and stated there: "Previews controls stay live, because recording a
  // preference for later is an action that can be carried out."
  //
  // What was wrong here was not the controls being live. It was that
  // twelve of them sit under a switch that turns them all off, with the
  // only contradicting line -- "Not watching gamelogs." -- ABOVE them in
  // the faintest text on the card. So the row says so instead, and only
  // while it is true.
  //
  // That sentence used to add "rendered as its peers", which round 5's A4
  // has since made only half true: the PvE filter and Keep-pulsing moved
  // below the event table into .alert-mods, because they modify that table
  // rather than sit beside the switch. They are still under the switch, so
  // this line still has to cover them -- "below" is what it says, and
  // .alert-mods is below.
  var DEPENDS = 'Alerts are off, so nothing below is watching yet — these '
              + 'apply when you turn them on.';

  // Ids only. The display names used to be carried here as well, for
  // messages that named their event ("Combat colour is set for this
  // session..."). Those messages now render INSIDE the event's own row,
  // so the name would be repeating the label six inches to its left --
  // and a hand-kept copy of three labels that index.html already holds is
  // exactly the drift CLAUDE.md's derive-don't-retype rule is about.
  //
  // These ids are still a hand-kept copy of settings.py's
  // _ALERT_EVENT_DEFAULTS keys. That one is load-bearing and untested;
  // see the id/option guard in tests/test_page_conventions.py.
  var EVENTS = ['combat', 'warp_scramble', 'decloak'];

  // The colours offered, and the whole reason this is not an
  // <input type="color">. That control opened the native Win32 dialog --
  // the only unstyled system chrome left in a frameless dark app that
  // restyled the scrollbar precisely because native chrome was a tell --
  // and offered 16.7 million choices for a decision with about five good
  // answers. The ring is read in peripheral vision, on a small tile, over
  // arbitrary game content, while you are aligned on a wormhole. Two
  // similar purples silently destroy the one thing that makes three
  // alerts distinguishable, and nothing ever told you.
  //
  // Five, well separated in hue and all bright enough to hold up over
  // moving game content. The three settings.py defaults are among them by
  // rule, not by luck -- tests/test_page_conventions.py pins that, since a
  // default that is not offered would render as an unlabelled sixth
  // swatch on every fresh install.
  //
  // Deliberately no second teal: the SELECTED-preview ring is
  // (0,200,220) in window.py, and decloak's #4dd2ff already sits close
  // enough to it that the smoke checklist has an item asking whether the
  // two can be told apart.
  var COLOURS = ['#ff4d4d', '#ffd24d', '#4dff7a', '#4dd2ff', '#ff4db8'];

  // Round 6, P2-5. The five swatches carried their HEX as title and
  // aria-label, under a comment conceding "the hex is not a name, but it
  // is honest". Honest and unusable: "#4dd2ff" does not tell a sighted
  // user what they are picking, does not read aloud as anything, and --
  // the reason it mattered -- gives the collision note nothing to say. A
  // fixed palette of five can afford five words.
  //
  // Indexed against COLOURS above rather than keyed by hex, so the two
  // cannot drift apart silently: a colour changed there with no name
  // added here falls back to the hex, which is what the sixth (out-of-
  // palette, hand-edited settings.json) swatch gets by design.
  var COLOUR_NAMES = ['Red', 'Amber', 'Green', 'Cyan', 'Magenta'];

  function colourName(hex) {
    var i = COLOURS.indexOf(hex);
    return i === -1 ? hex : COLOUR_NAMES[i];
  }

  // Last-known-good color/sound per event, so a refused or bridge-
  // failed change has something to revert the control to -- by the
  // time 'change' fires the browser has already committed the new
  // value into the element, so the element itself cannot tell us
  // what it was before.
  var lastGood = {};

  // Every write below goes through this. The five text slots in this card
  // are role="status" live regions now, and replacing a text node
  // re-announces it even when the string is identical -- render() sets the
  // health line unconditionally on section entry and on every
  // wm:preview-enabled-changed, so an unguarded write would read "Not
  // watching gamelogs." aloud again on each one.
  //
  // The four .field-msg slots in the other Settings cards have the same
  // gap and are deliberately NOT changed here: they are live regions
  // nowhere yet, and arming them without reading how their own modules
  // write to them is how this kind of noise ships.
  function setText(el, text) {
    var next = text || '';
    if (el && el.textContent !== next) { el.textContent = next; }
  }

  function say(text) { setText(status, text); }

  function showDepends(enabled) {
    if (!depends) { return; }
    setText(depends, enabled ? '' : DEPENDS);
    depends.hidden = enabled;
  }

  function eventRow(id) {
    return {
      enabled: WM.el('alert-event-' + id + '-enabled'),
      colors: WM.el('alert-event-' + id + '-colors'),
      sound: WM.el('alert-event-' + id + '-sound'),
      flashes: WM.el('alert-event-' + id + '-flashes'),
      speed: WM.el('alert-event-' + id + '-speed'),
      test: WM.el('alert-event-' + id + '-test'),
      msg: WM.el('alert-event-' + id + '-msg')
    };
  }

  // How many flashes an event may be given. Built here rather than typed
  // into index.html so the ceiling is one number rather than ten <option>
  // elements, and kept well inside settings.validated_alerts' 1-16 clamp:
  // past about eight the ring is still pulsing when the next event lands,
  // and the count stops being something anyone counts.
  // test_page_conventions.py checks this against the clamp.
  var FLASH_COUNTS = [1, 2, 3, 4, 5, 6, 8, 10];

  function paintFlashCounts(row, stored) {
    if (!row.flashes) { return; }
    var wanted = FLASH_COUNTS.slice();
    // A stored count outside the offered set gets its own option rather
    // than leaving the <select> blank. settings.validated_alerts keeps
    // anything from 1 to 16, so a hand-edited 7 is a legitimate state --
    // and a blank control would be the card failing to show a setting
    // that is genuinely in force. Same reasoning, and same shape, as
    // paintSwatches' out-of-palette colour above.
    var extra = parseInt(stored, 10);
    if (extra > 0 && wanted.indexOf(extra) === -1) {
      wanted.push(extra);
      wanted.sort(function (a, b) { return a - b; });
    }
    if (row.flashes.getAttribute('data-built') === wanted.join(',')) { return; }
    row.flashes.textContent = '';
    wanted.forEach(function (n) {
      var opt = document.createElement('option');
      opt.value = String(n);
      // textContent, not innerHTML: the same DOM-text rule WM.choose's
      // options are built under.
      opt.textContent = String(n);
      row.flashes.appendChild(opt);
    });
    row.flashes.setAttribute('data-built', wanted.join(','));
  }

  // Each event row reports its own outcome, beside the control that
  // produced it. #alerts-status stays for CARD-level state only (the three
  // top-level switches), which is the one thing it was ever right for.
  //
  // `hidden` alone is enough: .field-msg carries its own [hidden] override
  // (style.css:1845), so this is not the trap DESIGN.md names.
  function sayRow(row, text, severity) {
    if (!row.msg) { return; }
    setText(row.msg, text);
    row.msg.className = 'field-msg' + (text && severity ? ' ' + severity : '');
    row.msg.hidden = !text;
  }

  // The event's visible name, read off its own checkbox rather than kept
  // as a fourth copy of the three event names (EVENTS has the ids,
  // index.html has the labels, settings.py has the defaults). A label
  // renamed in the markup renames itself here.
  function eventLabel(id) {
    var box = WM.el('alert-event-' + id + '-enabled');
    var label = box && box.parentNode;
    return label ? (label.textContent || '').trim() : id;
  }

  /* Two enabled events set to the same colour are one alert with two
     meanings, and until round 6 nothing said so.

     This card already narrowed 16.7 million colours to five for exactly
     this reason -- see COLOURS above: "Two similar purples silently
     destroy the one thing that makes three alerts distinguishable, and
     nothing ever told you." Narrowing made a near-miss unreachable and
     left an EXACT match five clicks away, still silent. The round-6
     captures caught a live install with Combat and Decloak both on
     #4dd2ff and both on the same sound: a cyan pulse that could mean "you are
     being shot" or "you just decloaked", which are opposite responses.

     Colour is the channel, not sound. The ring is what you read in
     peripheral vision on a small tile over moving game content, which is
     COLOURS' own argument; the sound is secondary and may be off, muted,
     or lost under comms. So a shared colour warns on its own, and changing
     only the sound neither makes nor clears that collision.

     One relationship-level live region sits below the table. Per-row live
     regions remain exclusively for the outcome of the control beside them,
     so clearing a standing collision can never clear a refused write.

     The app does this for keybinds already (.bindbtn.clash). Keybinds are
     configuration you check twice ever; alerts are the only thing in the
     product that interrupts you mid-fight. */
  function flagCollisions() {
    var byColour = {};
    EVENTS.forEach(function (id) {
      var row = eventRow(id);
      if (!row.enabled || !row.enabled.checked) { return; }
      var good = lastGood[id] || {};
      if (!good.color) { return; }
      var key = String(good.color).toLowerCase();
      if (!byColour[key]) { byColour[key] = []; }
      byColour[key].push(id);
    });

    var warnings = [];
    Object.keys(byColour).forEach(function (key) {
      var ids = byColour[key];
      if (ids.length < 2) { return; }
      var names = ids.map(eventLabel);
      var subject = names.length === 2
        ? names[0] + ' and ' + names[1]
        : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
      warnings.push(subject + (ids.length === 2 ? ' both use ' : ' use ')
        + colourName(key) + '. Their preview pulses are indistinguishable.');
    });
    setText(collision, warnings.join(' '));
  }

  // Drops every note that was only true while alerts were off. Keyed on
  // the tag rather than the text, so rewording the sentence cannot quietly
  // strand it again, and it leaves a row's OWN errors alone -- a refused
  // colour write is still true after the master switch moves.
  function clearWhileOffNotes() {
    EVENTS.forEach(function (id) {
      var row = eventRow(id);
      if (row.msg && row.msg.dataset.whileOff) {
        delete row.msg.dataset.whileOff;
        sayRow(row, '');
      }
    });
  }

  // Built here rather than typed into index.html: the page would
  // otherwise carry fifteen colour literals, and DESIGN.md keeps colour
  // decisions out of the markup. The hex reaches CSS as a custom property
  // on the element, so the stylesheet still owns every other pixel of the
  // control.
  //
  // A stored colour outside the palette gets its own swatch, appended and
  // selected, instead of being silently snapped to the nearest offered
  // one. settings.validated_alerts accepts any #rrggbb, so a hand-edited
  // settings.json is a legitimate state -- and quietly rewriting a user's
  // choice the moment they open the card would be the card editing
  // settings it was only asked to display.
  function paintSwatches(row, id, colour, custom) {
    if (!row.colors) { return; }
    var wanted = COLOURS.slice();
    if (custom) {
      wanted.push('#ff8c42');
      // Keep a stored extra choice when selecting a palette colour. Dropping
      // it would rebuild the group and detach the radio holding focus.
      var built = row.colors.getAttribute('data-built');
      if (built && wanted.indexOf(colour) !== -1) { wanted = built.split(','); }
    }
    if (colour && wanted.indexOf(colour) === -1) { wanted.push(colour); }

    if (row.colors.getAttribute('data-built') !== wanted.join(',')) {
      row.colors.textContent = '';
      wanted.forEach(function (hex) {
        var label = document.createElement('label');
        label.className = 'swatch';
        var input = document.createElement('input');
        input.type = 'radio';
        input.name = 'alert-color-' + id;
        input.value = hex;
        var dot = document.createElement('span');
        dot.className = 'dot';
        dot.style.setProperty('--swatch', hex);
        // The name, with the hex kept in the tooltip: the name is what
        // identifies the choice, the hex is what identifies the pixel, and
        // someone comparing this against a hand-edited settings.json
        // still wants the second. An out-of-palette colour has no name and
        // gets the hex for both, unchanged.
        var name = custom && hex === '#ff8c42' ? 'Orange' : colourName(hex);
        label.title = name === hex ? hex : name + ' (' + hex + ')';
        input.setAttribute('aria-label', name);
        label.appendChild(input);
        label.appendChild(dot);
        row.colors.appendChild(label);
      });
      row.colors.setAttribute('data-built', wanted.join(','));
    }

    var boxes = row.colors.querySelectorAll('input');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = boxes[i].value === colour;
    }
  }

  // Shared by the wm:settings hydration and refresh() (get_alert_state),
  // so the per-event rows repaint from the same shape either way.
  function applyAlerts(alerts) {
    var events = (alerts && alerts.events) || {};
    EVENTS.forEach(function (id) {
      var row = eventRow(id);
      if (!row.enabled) { return; }
      var spec = events[id] || {};
      row.enabled.checked = !!spec.enabled;
      var color = spec.color || (lastGood[id] || {}).color || COLOURS[0];
      var sound = spec.sound || 'none';
      // Absent means the shipped default, matching pve_filter's precedent
      // above: an upgrading user's file predates both keys, and a blank
      // <select> would read as "no flashes" for a feature that has always
      // flashed three times.
      var flashes = String(spec.pulses || 3);
      var speed = spec.flash_rate || 'normal';
      paintSwatches(row, id, color);
      paintFlashCounts(row, flashes);
      row.sound.value = sound;
      row.flashes.value = flashes;
      row.speed.value = speed;
      lastGood[id] = {
        color: color, sound: sound, flashes: flashes, speed: speed
      };
    });
    // After the loop, not inside it: a collision is a fact about the
    // whole card, and checking mid-loop would read lastGood entries the
    // rows below have not refreshed yet.
    flagCollisions();
  }

  // Shared by all three top-level checkboxes. WM.send resolves to null
  // on a bridge failure (app.js) -- that reverts the box, same as
  // `applied: false`, which the bridge now also returns when a settings
  // write raised and was rolled back (api.py's _write_alert_setting):
  // the value genuinely never took effect, so leaving the checkbox
  // showing it would be showing a state the app is not in. Only
  // `applied: true, persisted: false` (a session-only write) leaves the
  // box alone -- that one really did take effect, and reverting it
  // would be the opposite lie. Mirrors set_restore_preview_positions in
  // previews.js.
  function writeFlag(box, method, label) {
    box.addEventListener('change', function () {
      var wanted = box.checked;
      WM.send(method, wanted).then(function (res) {
        if (!res || !res.applied) {
          box.checked = !wanted;
          if (res && res.error) { say(res.error); }
          return;
        }
        if (!res.persisted) {
          say(label + ' is ' + (wanted ? 'on' : 'off')
            + ' for this session, but could not be written to settings — '
            + 'it will not survive a restart.');
        } else {
          say('');
        }
        if (method === 'set_alert_enabled') {
          clearWhileOffNotes();
          refresh();
        }
      });
    });
  }

  writeFlag(enabledBox, 'set_alert_enabled', 'Alerts');
  writeFlag(pveBox, 'set_alert_pve_filter', 'The PvE filter');
  writeFlag(persistBox, 'set_alert_persist', 'Persisting alerts');

  // ---- volume ---------------------------------------------------------
  // One level for all three sounds. Modelled on settings.js's opacity
  // slider, including the two halves that are easy to get wrong: the
  // readout follows `input` so the number tracks the thumb, and the WRITE
  // happens on `change` only -- a range fires `input` per pixel dragged,
  // and DESIGN.md's "discrete controls commit on change" exists to stop a
  // settings write per pixel.
  var volumeBox = WM.el('alert-volume');
  var volumeValue = WM.el('alert-volume-value');
  var volumeStatus = WM.el('alert-volume-status');
  var lastGoodVolume = null;

  function showVolume() {
    if (volumeValue) { volumeValue.textContent = volumeBox.value + '%'; }
  }

  function applyVolume(alerts) {
    if (!volumeBox) { return; }
    // Absent means full volume, matching settings.py's default: a missing
    // key on an upgrading install must not render as a silent app.
    var stored = (alerts && typeof alerts.volume === 'number')
      ? alerts.volume : 100;
    volumeBox.value = String(stored);
    lastGoodVolume = volumeBox.value;
    showVolume();
  }

  if (volumeBox) {
    volumeBox.addEventListener('input', showVolume);
    volumeBox.addEventListener('change', function () {
      var wanted = parseInt(volumeBox.value, 10);
      WM.send('set_alert_volume', wanted).then(function (res) {
        // The same three-way answer every field on this page gives, and
        // the same reason each is distinct: a refusal never took effect
        // (put the thumb back), a failed write did (leave it, and say it
        // will not survive a restart).
        if (!res) {
          volumeBox.value = lastGoodVolume;
          showVolume();
          setText(volumeStatus, 'Could not reach the app. Nothing was changed.');
          return;
        }
        if (!res.applied) {
          volumeBox.value = lastGoodVolume;
          showVolume();
          setText(volumeStatus, res.error || 'That value was not accepted.');
          return;
        }
        lastGoodVolume = volumeBox.value;
        setText(volumeStatus, res.persisted ? ''
          : 'Volume ' + wanted + '% is set for this session, but could not '
            + 'be written to settings — it will not survive a restart.');
      });
    });
  }

  EVENTS.forEach(function (id) {
    var row = eventRow(id);
    if (!row.enabled) { return; }

    row.enabled.addEventListener('change', function () {
      var wanted = row.enabled.checked;
      WM.send('set_alert_event', id, 'enabled', wanted).then(function (res) {
        // set_alert_event refuses an unknown event/field outright but a
        // clamped value is still applied -- only a refusal or a bridge
        // failure reverts the box.
        if (!res || !res.applied) {
          row.enabled.checked = !wanted;
          sayRow(row, (res && res.error)
            || 'That could not be changed, so it has been put back.', 'err');
          return;
        }
        sayRow(row, '');
        // A disabled event cannot collide, and re-enabling one can revive
        // a collision that was true all along. flagCollisions reads the
        // checkbox, so it has to run after the box has settled.
        flagCollisions();
      });
    });
    // Delegated: the swatches are rebuilt whenever a stored colour falls
    // outside the palette, so a listener bound to each input would be lost
    // on the rebuild that replaces them.
    row.colors.addEventListener('change', function (event) {
      var wanted = event.target && event.target.value;
      if (!wanted) { return; }
      WM.send('set_alert_event', id, 'color', wanted).then(function (res) {
        if (!res || !res.applied) {
          paintSwatches(row, id, (lastGood[id] || {}).color || wanted);
          sayRow(row, (res && res.error)
            || 'That colour could not be set, so it has been put back.', 'err');
          return;
        }
        lastGood[id] = lastGood[id] || {};
        lastGood[id].color = wanted;
        if (!res.persisted) {
          sayRow(row, 'The colour is set for this session, but could not be '
            + 'written to settings — it will not survive a restart.', 'warn');
        } else {
          sayRow(row, '');
        }
        // The colour IS the collision key, so this is the change most
        // likely to make or clear one. After the sayRow above, which owns
        // this row's own outcome and outranks a collision note.
        flagCollisions();
      });
    });
    row.sound.addEventListener('change', function () {
      var wanted = row.sound.value;
      WM.send('set_alert_event', id, 'sound', wanted).then(function (res) {
        if (!res || !res.applied) {
          row.sound.value = (lastGood[id] || {}).sound || wanted;
          sayRow(row, (res && res.error)
            || 'That sound could not be set, so it has been put back.', 'err');
          return;
        }
        lastGood[id] = lastGood[id] || {};
        lastGood[id].sound = wanted;
        if (!res.persisted) {
          sayRow(row, 'The sound is set for this session, but could not be '
            + 'written to settings — it will not survive a restart.', 'warn');
        } else {
          sayRow(row, '');
        }
      });
    });

    // The two flash controls are the same write in both cases -- one
    // <select>, one field, one revert -- so they share a closure rather
    // than repeating it twice per event. Deliberately NOT extended to
    // sound or colour above: those two carry their own copy because each
    // has a revert that is not a `.value` assignment (colour repaints a
    // radiogroup) or its own sentence.
    function writeChoice(control, field, key, noun) {
      if (!control) { return; }
      control.addEventListener('change', function () {
        var wanted = control.value;
        // Numbers cross the bridge as numbers: settings.py's clamp checks
        // isinstance(value, int), so a string "5" is silently dropped and
        // the flash count would appear to revert on the next read with
        // nothing said.
        var value = field === 'pulses' ? parseInt(wanted, 10) : wanted;
        WM.send('set_alert_event', id, field, value).then(function (res) {
          if (!res || !res.applied) {
            control.value = (lastGood[id] || {})[key] || wanted;
            sayRow(row, (res && res.error)
              || 'That could not be changed, so it has been put back.', 'err');
            return;
          }
          lastGood[id] = lastGood[id] || {};
          lastGood[id][key] = wanted;
          if (!res.persisted) {
            sayRow(row, 'The ' + noun + ' is set for this session, but could '
              + 'not be written to settings — it will not survive a '
              + 'restart.', 'warn');
          } else {
            sayRow(row, '');
          }
        });
      });
    }

    writeChoice(row.flashes, 'pulses', 'flashes', 'flash count');
    writeChoice(row.speed, 'flash_rate', 'speed', 'flash speed');
    row.test.addEventListener('click', function () {
      // Never persistent (api.py's test_alert docstring): nothing here
      // is looking at a preview to acknowledge it, so nothing is saved.
      WM.send('test_alert', id).then(function (res) {
        if (res && res.error) { sayRow(row, res.error, 'warn'); return; }
        // A successful Test with the master switch off is the one way
        // this card can actively mislead: a ring pulses, a sound plays,
        // and nothing is watching gamelogs. The DEPENDS line says so
        // permanently; this says it at the moment it would be believed.
        if (!enabledBox.checked) {
          sayRow(row, 'That is what the alert looks like. Alerts are still '
            + 'off, so nothing is watching gamelogs yet.', 'warn');
          // Tagged because it OUTLIVES the condition it states. Testing an
          // event with alerts off, then switching them on, left this note
          // sitting under a ticked Enable next to a health line reading
          // "Watching gamelogs" -- the card contradicting itself in three
          // places at once. Nothing cleared it: sayRow is only ever called
          // by the row's own controls, and the master switch is not one.
          row.msg.dataset.whileOff = '1';
        } else {
          sayRow(row, '');
        }
      });
    });
  });

  // ---- Custom rules: authority is not the editor ----------------------
  // Each row serializes full mutations. Read replies and mutation snapshots
  // can include later commits; neither is a copy of the submitted draft.
  var customList = WM.el('custom-alert-list');
  var customAdd = WM.el('custom-alert-add');
  var customHealth = WM.el('custom-alert-health');
  var customStatus = WM.el('custom-alert-status');
  var customRecovery = WM.el('custom-alert-recovery');
  var customRetry = WM.el('custom-alert-retry');
  var customReadFailed = false;
  var controlsReadPending = 0;
  var addRecoveryMessage = false;
  var customRows = Object.create(null);
  var tombstones = Object.create(null);
  var customState = null;
  var committedRevision = 0;
  var viewEpoch = 0;
  var visible = false;
  var customReady = false;
  var readSerial = 0;
  var renderedSerial = 0;
  var hydratedSerial = 0;
  var addPending = false;
  var addUncertain = false;
  var addRecoverySerial = 0;
  var disclosure = null;
  var builtinReadSerial = 0;
  var builtinRenderedSerial = 0;

  function ownsView(epoch) { return visible && epoch === viewEpoch; }
  function customId(id, suffix) { return 'custom-alert-' + id + '-' + suffix; }
  function node(tag, className, text) {
    var el = document.createElement(tag);
    el.className = className || '';
    if (text) { el.textContent = text; }
    return el;
  }
  function styleDraft(row) {
    var selected = row.colors.querySelector('input:checked');
    return {color: selected ? selected.value : row.ack.color,
      sound: row.sound.value, cooldown_s: Number(row.cooldown.value)};
  }
  function fullDraft(row, textFromAuthority, style) {
    style = style || styleDraft(row);
    return {name: textFromAuthority ? row.ack.name : row.name.value,
      search: textFromAuthority ? row.ack.search : row.search.value,
      enabled: textFromAuthority ? row.ack.enabled : row.enabled.checked,
      color: style.color, sound: style.sound, cooldown_s: style.cooldown_s};
  }
  function textDirty(row) {
    return row.name.value !== row.ack.name || row.search.value !== row.ack.search;
  }
  function clean(row) {
    var style = styleDraft(row);
    return !textDirty(row) && row.enabled.checked === row.ack.enabled
      && style.color === row.ack.color && style.sound === row.ack.sound
      && style.cooldown_s === row.ack.cooldown_s;
  }
  function customMessage(row) {
    var draft = textDirty(row) ? 'Name or search has unapplied changes. Press Enter or Apply.' : '';
    sayRow(row, [row.error, draft, row.recoveryMessage, row.notice].filter(function (s) { return !!s; }).join(' '),
      row.error ? 'err' : (draft || row.recoveryMessage || row.notice ? 'warn' : ''));
  }
  function paintCustom(row, kind, intents) {
    function owns(key) { return !intents || intents[key] === row.intents[key]; }
    if (!kind || kind === 'apply') {
      if (owns('name')) { row.name.value = row.ack.name; }
      if (owns('search')) { row.search.value = row.ack.search; }
    }
    if (!kind || kind === 'apply' || kind === 'style') {
      if (owns('color')) { paintSwatches(row, 'custom-' + row.ack.id, row.ack.color, true); }
      if (owns('sound')) { row.sound.value = row.ack.sound; }
      if (owns('cooldown_s')) { row.cooldown.value = String(row.ack.cooldown_s); }
    }
    // A full edit can disable a cleared search. New text/style intent does
    // not own the checkbox; only a newer enabled intent may protect it.
    if (kind !== 'remove' && owns('enabled')) { row.enabled.checked = row.ack.enabled; }
  }
  function controlsReady(row) {
    var ready = visible && customReady && !row.dead && !row.removing && !row.uncertain;
    row.controls.forEach(function (el) { el.disabled = !ready; });
    row.colors.querySelectorAll('input').forEach(function (el) { el.disabled = !ready; });
  }
  function updateAdmission() {
    if (!customAdd) { return; }
    var count = customState ? customState.rules.length : 0;
    var limit = customState ? customState.limit : 0;
    customAdd.disabled = !visible || !customReady || addPending || addUncertain || count >= limit;
    customAdd.textContent = addPending ? 'Adding…' : 'Add alert';
    customAdd.title = customState && count >= limit ? 'Limit of ' + limit + ' custom alerts reached.' : '';
    var needsAuthority = !customReady || addUncertain || Object.keys(customRows).some(function (id) {
      return !customRows[id].dead && customRows[id].uncertain;
    });
    if (!needsAuthority) { customReadFailed = false; }
    customRecovery.hidden = !visible || !customReadFailed || !needsAuthority;
    customRetry.disabled = customRecovery.hidden || !!controlsReadPending;
    customRetry.textContent = controlsReadPending ? 'Retrying…' : 'Retry';
    Object.keys(customRows).forEach(function (id) { controlsReady(customRows[id]); });
  }
  function openEditor(row) {
    if (!visible || !customReady || row.dead) { return; }
    if (disclosure && customRows[disclosure]) {
      customRows[disclosure].editor.hidden = true;
      customRows[disclosure].edit.setAttribute('aria-expanded', 'false');
    }
    disclosure = row.ack.id;
    row.editor.hidden = false;
    row.edit.setAttribute('aria-expanded', 'true');
    row.name.focus();
  }
  function makeCustomRow(rule) {
    var row = {ack: rule, counter: 0, queue: [], busy: null, dead: false, deferredAcks: {},
      uncertain: false, removing: false, error: '', notice: '', recoveryMessage: '', controls: [], testSerial: 0,
      intents: {name: 0, search: 0, color: 0, sound: 0, cooldown_s: 0, enabled: 0}};
    row.root = node('div', 'custom-alert-row');
    row.root.setAttribute('data-rule-id', rule.id);
    var top = node('div', 'custom-alert-summary');
    var label = node('label', 'check');
    row.enabled = node('input');
    row.enabled.type = 'checkbox';
    label.appendChild(row.enabled);
    label.appendChild(node('span', 'box'));
    row.title = node('span', 'custom-alert-name');
    label.appendChild(row.title);
    row.enabled.id = customId(rule.id, 'enabled');
    row.controls.push(row.enabled);
    top.appendChild(label);
    row.root.appendChild(top);
    row.editor = node('div', 'custom-alert-editor');
    row.editor.id = customId(rule.id, 'editor');
    row.editor.hidden = true;
    function button(suffix, text, parent, action) {
      var button = node('button', suffix === 'remove' ? 'btn danger' : 'btn', text);
      button.type = 'button'; button.id = customId(rule.id, suffix);
      button.addEventListener('click', function () {
        if (visible && customReady && !row.dead && !row.removing && !row.uncertain) { action(); }
      });
      parent.appendChild(button); row.controls.push(button); row[suffix] = button;
      return button;
    }
    button('edit', 'Edit…', top, function () { openEditor(row); });
    row.edit.setAttribute('aria-controls', row.editor.id);
    row.edit.setAttribute('aria-expanded', 'false');
    button('remove', 'Remove', top, function () {
      var epoch = viewEpoch;
      WM.confirm('Remove custom alert', 'Remove “' + row.ack.name + '”? This rule cannot be recovered.',
        {destructive: true}).then(function (ok) {
        if (!ok || !ownsView(epoch) || row.dead || customRows[rule.id] !== row) { return; }
        submitCustom(row, 'remove');
      });
    });
    function field(suffix, title, tag) {
      var wrap = node('div', 'row');
      var label = node('label', 'lab', title);
      var input = node(tag || 'input', 'field');
      input.id = customId(rule.id, suffix);
      label.setAttribute('for', input.id);
      input.setAttribute('aria-describedby', customId(rule.id, 'msg'));
      wrap.appendChild(label); wrap.appendChild(input); row.editor.appendChild(wrap);
      row.controls.push(input); return input;
    }
    row.name = field('name', 'Name');
    row.search = field('search', 'Search text');
    row.search.placeholder = 'At least 3 visible characters';
    row.editor.appendChild(node('p', 'hint', 'Apply an empty search to switch this rule off.'));
    var styles = node('div', 'custom-alert-style');
    row.colors = node('div', 'swatches'); row.colors.id = customId(rule.id, 'color');
    row.colors.setAttribute('role', 'radiogroup');
    var colorWrap = node('div', 'custom-alert-colour');
    var colorLabel = node('span', 'lab', 'Colour');
    colorWrap.appendChild(colorLabel); colorWrap.appendChild(row.colors); styles.appendChild(colorWrap);
    row.sound = field('sound', 'Sound', 'select');
    // The existing built-in options are already checked against VALID_SOUNDS.
    var options = WM.el('alert-event-combat-sound').options;
    for (var i = 0; i < options.length; i++) {
      var option = node('option', '', options[i].textContent);
      option.value = options[i].value; row.sound.appendChild(option);
    }
    styles.appendChild(row.sound.parentNode);
    row.cooldown = field('cooldown', 'Cooldown (seconds)', 'select');
    for (var n = 0; n <= 120; n++) {
      var seconds = node('option', '', String(n)); seconds.value = String(n); row.cooldown.appendChild(seconds);
    }
    styles.appendChild(row.cooldown.parentNode);
    row.editor.appendChild(styles);
    var actions = node('div', 'custom-alert-actions');
    button('apply', 'Apply', actions, function () { submitCustom(row, 'apply'); });
    button('cancel', 'Cancel', actions, function () {
      row.counter++;
      Object.keys(row.intents).forEach(function (key) { row.intents[key]++; });
      paintCustom(row); customMessage(row);
      row.editor.hidden = true; row.edit.setAttribute('aria-expanded', 'false');
      disclosure = null; row.edit.focus();
    });
    button('test', 'Test', actions, function () {
      var epoch = viewEpoch, serial = ++row.testSerial, counter = row.counter;
      WM.send('test_custom_alert', rule.id, styleDraft(row)).then(finished, function () { finished(null); });
      function finished(res) {
        if (!ownsView(epoch) || row.dead || serial !== row.testSerial || counter !== row.counter) { return; }
        row.notice = !res ? 'Could not reach the app. Test outcome is unknown.'
          : res.error || (res.applied ? 'Test played. No settings changed.' : 'No sound or preview played.');
        // Test never owns the persisted baseline or a mutation failure.
        customMessage(row);
      }
    });
    row.editor.appendChild(actions); row.root.appendChild(row.editor);
    row.msg = node('div', 'field-msg'); row.msg.id = customId(rule.id, 'msg');
    row.msg.setAttribute('role', 'status'); row.msg.hidden = true; row.root.appendChild(row.msg);
    ['name', 'search'].forEach(function (key) {
      var input = row[key];
      input.addEventListener('input', function () {
        row.counter++; row.intents[key]++; row.notice = ''; customMessage(row);
      });
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') { event.preventDefault(); row.apply.click(); }
      });
    });
    row.enabled.addEventListener('change', function () { submitCustom(row, 'enabled'); });
    row.colors.addEventListener('change', function () { submitCustom(row, 'style', 'color'); });
    row.sound.addEventListener('change', function () { submitCustom(row, 'style', 'sound'); });
    row.cooldown.addEventListener('change', function () { submitCustom(row, 'style', 'cooldown_s'); });
    paintCustom(row);
    return row;
  }
  function labelCustom(row, position) {
    setText(row.title, row.ack.name);
    // Position disambiguates duplicate names for assistive technology; stable
    // IDs, never names/positions, address every bridge operation.
    var name = row.ack.name + ', custom alert ' + (position + 1);
    row.enabled.setAttribute('aria-label', 'Enable ' + name);
    row.colors.setAttribute('aria-label', 'Colour: ' + name);
    ['edit', 'remove', 'apply', 'cancel', 'test'].forEach(function (key) {
      row[key].setAttribute('aria-label', row[key].textContent + ': ' + name);
    });
    row.root.setAttribute('role', 'group'); row.root.setAttribute('aria-label', name);
  }
  function adoptCustom(state, paint) {
    if (!state || state.revision < committedRevision) { return false; }
    committedRevision = state.revision; customState = state;
    var present = Object.create(null);
    state.rules.forEach(function (rule) {
      present[rule.id] = true;
      var row = customRows[rule.id];
      if (row && !row.dead) {
        var repaint = paint && !row.busy && !row.uncertain && !row.queue.length && clean(row);
        row.ack = rule;
        if (repaint) { paintCustom(row); }
      }
    });
    Object.keys(customRows).forEach(function (id) {
      if (present[id]) { return; }
      var row = customRows[id];
      row.dead = true; row.queue = [];
      tombstones[id] = committedRevision;
    });
    if (paint) { renderCustomRows(); }
    return true;
  }
  function focusCustomNeighbour() {
    var next = customState.rules[0];
    if (next && customRows[next.id]) { customRows[next.id].edit.focus(); }
    else { customAdd.focus(); }
  }
  function renderCustomRows() {
    if (!customList || !customState) { return; }
    var lostFocus = false;
    Object.keys(customRows).forEach(function (id) {
      var row = customRows[id];
      if (!row.dead) { return; }
      var recovery = row.recovery;
      var focused = row.root.contains(document.activeElement)
        || (recovery && recovery.kind === 'remove' && ownsView(recovery.epoch)
          && recovery.focused && document.activeElement === recovery.focus);
      if (row.root.parentNode) { row.root.parentNode.removeChild(row.root); }
      delete customRows[id];
      if (disclosure === id) { disclosure = null; }
      if (focused) { lostFocus = true; }
    });
    if (!customState.rules.length) {
      setText(customList, 'No custom alerts. Add an alert, then apply a search before enabling it.');
    } else {
      // Clear only the initial/empty hint, never live editor nodes.
      if (!customList.querySelectorAll('[data-rule-id]').length) { customList.textContent = ''; }
      customState.rules.forEach(function (rule, index) {
        if (tombstones[rule.id] && customState.revision <= tombstones[rule.id]) { return; }
        var row = customRows[rule.id];
        if (!row) {
          row = makeCustomRow(rule); customRows[rule.id] = row; customList.appendChild(row.root);
        }
        labelCustom(row, index); customMessage(row);
      });
    }
    updateAdmission();
    if (lostFocus) { focusCustomNeighbour(); }
  }
  function submitCustom(row, kind, field) {
    if (!visible || !customReady || row.dead || row.removing || row.uncertain) { return; }
    row.counter++;
    var intents = {};
    Object.keys(row.intents).forEach(function (key) {
      if (kind === 'apply' || key === field || (kind === 'enabled' && key === 'enabled')) { row.intents[key]++; }
      intents[key] = row.intents[key];
    });
    var request = {kind: kind, intents: intents, epoch: viewEpoch,
      draft: kind === 'apply' ? fullDraft(row, false) : null,
      style: kind === 'style' ? styleDraft(row) : null, enabled: row.enabled.checked,
      focused: row.root.contains(document.activeElement)};
    row.queue.push(request);
    if (kind === 'remove') { row.removing = true; }
    row.notice = ''; row.recoveryMessage = ''; updateAdmission();
    // Disabling a focused Remove can move focus to the document. That is
    // not the user choosing another control; capture the post-disable owner.
    request.focus = document.activeElement;
    drainCustom(row);
  }
  function finishDraft(row, request) {
    paintCustom(row, request.kind, request.intents);
    customMessage(row);
  }
  function drainCustom(row) {
    if (row.busy || row.uncertain || row.dead || !row.queue.length) { return; }
    var request = row.queue.shift(), promise;
    row.busy = request;
    if (request.kind === 'apply' || request.kind === 'style') {
      var draft = request.kind === 'apply' ? request.draft : fullDraft(row, true, request.style);
      promise = WM.send('edit_custom_alert', row.ack.id, draft);
    } else if (request.kind === 'enabled') {
      promise = WM.send('set_custom_alert_enabled', row.ack.id, request.enabled);
    } else {
      promise = WM.send('remove_custom_alert', row.ack.id);
    }
    promise.then(finished, function () { finished(null); });
    function finished(res) {
      var owned = ownsView(request.epoch);
      var restoreFocus = owned && request.kind === 'remove' && request.focused
        && (row.root.contains(document.activeElement) || document.activeElement === request.focus);
      // A deleted row's request identity cannot address a later rendered row.
      if (row.busy !== request) { return; }
      if (res && res.state) { adoptCustom(res.state, owned); }
      row.busy = null;
      if (row.dead) {
        if (owned) { renderCustomRows(); if (restoreFocus) { focusCustomNeighbour(); } }
        else if (visible) { readCustom(true); }
        return;
      }
      if (!res) {
        row.uncertain = true; row.recovery = request;
        row.recoverySerial = readSerial + 1;
        // Recovery owns a separate message, not the preceding save error or
        // a Test result that may arrive while the authority read is pending.
        row.recoveryMessage = 'Could not reach the app. The outcome is unknown; checking saved settings.';
      } else {
        row.removing = false;
        row.error = res.applied ? '' : res.error || 'That change was not accepted.';
        row.notice = res.applied && !res.persisted
          ? 'Applied for this session, but it will not survive a restart.' : '';
      }
      // Losing the view defers reconciliation; it does not turn an optimistic
      // control into a new draft. Later requests of the same kind subsume the
      // earlier field intents, so retain only one acknowledgment per kind.
      if (res && !owned) { row.deferredAcks[request.kind] = request; }
      if (owned) { if (res) { finishDraft(row, request); } else { customMessage(row); } updateAdmission(); }
      if (visible && (!owned || !res)) { readCustom(true); }
      drainCustom(row);
    }
  }
  function customHealthText(state) {
    if (!state.previews_enabled || !state.alerts_enabled) {
      return 'Custom matching is inactive. Preferences remain editable; turn on Previews and Alerts to watch.';
    }
    var reader = state.reader;
    if (!reader.running || reader.last_error) {
      return 'Custom alerts are not watching — ' + (reader.last_error
        || (!reader.gamelogs_folder ? 'set a valid Gamelogs folder below.' : 'the reader is unavailable.'));
    }
    if (!reader.characters.length) { return 'Custom alerts are not watching — no characters monitored yet.'; }
    if (state.matcher.state === 'degraded') {
      return 'Custom matching failed. Built-in alerts and Fleet remain independent.';
    }
    if (!state.rules.some(function (rule) { return rule.enabled; })) { return 'Custom matching is inactive — no custom alerts are enabled.'; }
    if (state.matcher.state !== 'active') { return 'Custom alerts are waiting for a new gamelog line.'; }
    return 'Custom matching is active — ' + reader.characters.slice().sort().join(', ') + '.';
  }
  function readCustom(controls) {
    if (!visible) { return; }
    var epoch = viewEpoch, serial = ++readSerial;
    if (controls) { controlsReadPending = serial; updateAdmission(); }
    WM.send('get_custom_alert_state').then(finished, function () { finished(null); });
    function finished(state) {
      if (!ownsView(epoch)) { return; }
      // Health and configuration have separate read owners. A fast health
      // poll must not strand a slow entry/recovery read, but that hydration
      // must not replace the newer health (including an unreachable reply).
      if (serial >= renderedSerial) {
        renderedSerial = serial;
        if (!state) { setText(customHealth, 'Could not reach the app. Custom alert health is unknown.'); }
        else if (state.revision >= committedRevision) { setText(customHealth, customHealthText(state)); }
      }
      if (!controls || serial < hydratedSerial) { return; }
      hydratedSerial = serial;
      if (serial === controlsReadPending) { controlsReadPending = 0; }
      if (!state || state.revision < committedRevision) {
        customReadFailed = true; updateAdmission(); return;
      }
      customReady = true;
      // A read already in flight when a write became uncertain cannot prove
      // its outcome, even at the same revision. Each recovery fences issuance,
      // independently of health/hydration completion order and other rows.
      if (addUncertain && serial >= addRecoverySerial) {
        addUncertain = false;
        if (addRecoveryMessage) {
          setText(customStatus, 'Saved settings reloaded. Review the list before adding another alert.');
          addRecoveryMessage = false;
        }
      }
      adoptCustom(state, true);
      Object.keys(customRows).forEach(function (id) {
        var row = customRows[id];
        if (row.uncertain && serial >= row.recoverySerial) {
          row.uncertain = false; row.removing = false;
          row.recoveryMessage = 'Saved settings reloaded. Review before retrying changes.';
          finishDraft(row, row.recovery); row.recovery = null;
        }
        if (!row.uncertain) {
          // Reuse field ownership against current authority, not an old result's
          // state/message/focus. New drafts and newer failures remain theirs.
          Object.keys(row.deferredAcks).forEach(function (kind) {
            finishDraft(row, row.deferredAcks[kind]);
          });
          row.deferredAcks = {};
        }
        drainCustom(row);
      });
      updateAdmission();
    }
  }
  if (customRetry) {
    customRetry.addEventListener('click', function () {
      // Only a fresh controls read can release uncertainty. Health polling
      // stays health-only, and Retry never replays the ambiguous mutation.
      if (visible && !customRecovery.hidden && !customRetry.disabled) { readCustom(true); }
    });
  }
  if (customAdd) {
    customAdd.addEventListener('click', function () {
      if (!visible || !customReady || addPending || addUncertain || customState.rules.length >= customState.limit) { return; }
      var epoch = viewEpoch;
      addPending = true; addRecoveryMessage = false; updateAdmission(); setText(customStatus, '');
      var focus = document.activeElement;
      WM.send('add_custom_alert').then(finished, function () { finished(null); });
      function finished(res) {
        var owned = ownsView(epoch);
        if (res && res.state) { adoptCustom(res.state, owned); }
        addPending = false; addUncertain = !res;
        if (!res) { addRecoverySerial = readSerial + 1; }
        if (owned) {
          addRecoveryMessage = !res;
          setText(customStatus, !res ? 'Could not reach the app. Add may have completed; checking saved settings before another Add.'
            : res.error || (res.applied && !res.persisted ? 'Added for this session, but it will not survive a restart.' : ''));
          updateAdmission();
          var row = res && res.applied && customRows[res.rule_id];
          if (row && !row.dead && document.activeElement === focus) { openEditor(row); }
        }
        if (visible && (!owned || !res)) { readCustom(true); }
      }
    });
  }

  // The health line and the characters are ALWAYS one sentence, on
  // purpose: a list rendered on its own keeps reading "watching Alice,
  // Bob" after the shared reader has failed, which is a healthy-looking
  // card sitting above a feature that stopped alerting.
  //
  // NAMES, not a count. "5 characters online" is the number you already
  // assumed when you started five clients; the fact you actually need is
  // WHICH one is missing when it says four, and get_alert_state already
  // ships the list (api.py's `characters`) for the card to throw away.
  // Sorted so the same five clients render in the same order every time
  // and a gap is something you can spot rather than re-read.
  //
  // Capped, because this is one line in a card and a fleet is not five
  // accounts. The overflow keeps counting, since past the cap the number
  // is the only thing left that is useful.
  var HEALTH_NAMES_MAX = 6;

  // Round 5, A1. `running` is only two thirds of the answer, and the line
  // shipped four rounds saying it was all of it.
  //
  // Api.get_alert_state gates `running` on three things -- previews on,
  // master switch on, a healthy shared reader with a real folder -- so
  // `running: true` proves all three. It proves nothing at all about the
  // event table, which service.py's _handle consults separately and which
  // drops every event whose spec is not `enabled`. Untick all three rows
  // and shared telemetry genuinely is reading gamelogs and has thirteen
  // characters, and cannot raise an alert for any of them: the card
  // rendered "Watching gamelogs — Aiga Otsolen, ... and 7 more" over a
  // feature that was switched off. That is the exact shape PRODUCT.md
  // names as this line's reason to exist ("an alert you configured and
  // cannot tell is running is the failure mode, not a missed pulse"), and
  // the sibling instance at the Test-while-off note below is why the
  // class is worth naming rather than patching.
  //
  // Counted off the payload's OWN events dict, not the EVENTS list above:
  // this is the same table _handle reads, so the answer stays true for
  // whatever settings.json holds rather than for the three ids this file
  // happens to render.
  //
  // Deliberately NOT extended to the PvE filter. It suppresses only
  // likely-NPC sources on two of the three events (patterns.py's
  // FILTERED_EVENTS), so there is no setting of it that makes alerting
  // impossible -- a clause claiming otherwise would be this same bug with
  // the sign flipped.
  function anyEventEnabled(alerts) {
    var events = (alerts && alerts.events) || {};
    for (var id in events) {
      if (Object.prototype.hasOwnProperty.call(events, id)
          && events[id] && events[id].enabled) { return true; }
    }
    return false;
  }

  function healthText(state) {
    if (!state.running) {
      return state.last_error
        ? 'Not watching gamelogs — ' + state.last_error
        : 'Not watching gamelogs.';
    }
    var customs = (state.alerts && state.alerts.custom_rules) || [];
    var customEnabled = customs.some(function (rule) { return rule.enabled; });
    if (!anyEventEnabled(state.alerts) && !customEnabled) {
      // Ahead of the character list on purpose, and instead of it: with no
      // event enabled it does not matter which clients are online, and
      // naming thirteen of them beside "nothing can alert" would be the
      // healthy-looking card again in a different sentence.
      return 'Watching gamelogs, but no events are switched on below — '
        + 'nothing can alert yet.';
    }
    var characters = (state.characters || []).slice().sort();
    if (!characters.length) {
      // Running with nothing to read is a real and reachable state: the
      // folder is set and the thread is alive, but no client is logged
      // in yet. "0 characters online" read as a fault.
      return 'Watching gamelogs — no characters online yet.';
    }
    var shown = characters.slice(0, HEALTH_NAMES_MAX);
    var rest = characters.length - shown.length;
    return 'Watching gamelogs — ' + shown.join(', ')
      + (rest ? ' and ' + rest + ' more' : '') + '.';
  }

  // Three states, and a card that silently shows nothing is the failure
  // mode this feature exists to avoid:
  //   1. Previews off -- alerts cannot draw, so say that plainly.
  //   2. No Gamelogs folder -- the important one, since without it
  //      alerts silently do nothing, indistinguishable from nothing
  //      happening in game.
  //   3. Otherwise, the health line above (running + the characters).
  //
  // `controls` is false on the status poll below: re-applying the stored
  // spec to the checkboxes, swatches and selects every two seconds would
  // fight a click whose write is still in flight, snapping the control
  // back to the old value for one frame. The poll is about what the app
  // is DOING; the controls belong to whoever last touched them.
  function render(state, controls) {
    if (offBanner) {
      offBanner.hidden = !!state.previews_enabled;
    }
    if (folderBanner) {
      folderBanner.hidden = !!state.gamelogs_folder;
    }
    setText(healthLine, healthText(state));
    // Read from get_alert_state's own `enabled`, not the checkbox: the box
    // is what the user just clicked, and a refused or bridge-failed write
    // reverts it. This must describe what the app is actually doing.
    showDepends(!!(state.alerts && state.alerts.enabled));
    if (controls) {
      applyAlerts(state.alerts);
      // Under `controls` with the rest: the two-second status poll must
      // not drag the thumb back under a hand that is still moving it.
      applyVolume(state.alerts);
    }
  }

  function read(controls) {
    if (!visible) { return; }
    var epoch = viewEpoch, serial = ++builtinReadSerial;
    WM.send('get_alert_state').then(function (state) {
      if (!ownsView(epoch) || serial < builtinRenderedSerial) { return; }
      builtinRenderedSerial = serial;
      if (!state) { setText(healthLine, 'Could not reach the app. Alert health is unknown.'); return; }
      render(state, controls);
    });
  }

  function refresh() { read(true); readCustom(true); }

  // The first setInterval in the page, so it is worth saying why.
  //
  // get_alert_state is deliberately a READ, not a push -- shared telemetry
  // can start before the webview exists, so a health change discovered at
  // launch would be pushed into a window that is not there. That is still
  // right. What it left was a card that reads its state exactly three
  // times: on section entry, on a previews toggle, and immediately after
  // the alerts switch.
  //
  // That last one is the bug this fixes, and it was reported from a real
  // session: enabling alerts refreshes AT ONCE, while shared telemetry has
  // only just been reconciled and its first rescan is up to one poll away.
  // So the card read `running: true, characters:
  // []`, rendered "no characters online yet", and nothing ever read
  // again -- five characters online and the card saying none, for as long
  // as you left it open.
  //
  // The same gap hid the failure the health line exists to catch: a
  // reader that dies at minute 40 of a sit kept reading as healthy,
  // because nothing asked again.
  //
  // Only while the section is showing. Nothing needs to be current when
  // it is not, which is the same reasoning the one-shot reads were built
  // on.
  var STATUS_POLL_MS = 2000;
  var poll = null;

  function startPolling() {
    if (poll === null) { poll = window.setInterval(function () { read(false); readCustom(false); },
                                                   STATUS_POLL_MS); }
  }

  function stopPolling() {
    if (poll !== null) { window.clearInterval(poll); poll = null; }
  }

  // panel.js owns onSettings and re-dispatches it; the three checkboxes
  // and the per-event rows hydrate from `preview.alerts`, which
  // _settings_payload ships for free as part of its shallow dict(cfg).
  document.addEventListener('wm:settings', function (ev) {
    var s = (ev.detail || {}).settings || {};
    var alerts = (s.preview && s.preview.alerts) || {};
    enabledBox.checked = !!alerts.enabled;
    showDepends(!!alerts.enabled);
    // Absent means on, matching restore-preview-positions's precedent in
    // previews.js: an upgrading user's file predates the key.
    pveBox.checked = alerts.pve_filter !== false;
    persistBox.checked = alerts.persist_until_selected !== false;
    applyAlerts(alerts);
    applyVolume(alerts);
  });

  // Refreshed on section entry, same reasoning as previews.js and
  // bookmarks.js. Leaving is load-bearing here, as DESIGN.md says of every
  // enter/leave contract on this page: the poll must stop, or a card
  // nobody is looking at keeps a bridge call running every two seconds
  // for the life of the session.
  //
  // 'alerts', not 'previews', since round 5's D1 gave this card a section
  // of its own. The name here is the SECTION THIS CARD IS IN and nothing
  // else -- left at 'previews' it inverts exactly: the poll would run
  // while the user is on Previews, where the card is no longer rendered,
  // and stop the moment they open Alerts.
  document.addEventListener('wm:section', function (event) {
    if (event.detail === 'alerts') {
      if (!visible) { visible = true; viewEpoch++; customReady = false; updateAdmission(); }
      refresh();
      startPolling();
    } else {
      leaveAlerts();
    }
  });

  // A route change leaves Settings without dispatching wm:section at all,
  // so the section listener above never hears about it and the poll would
  // outlive the screen.
  function leaveAlerts() {
    if (visible) {
      viewEpoch++; visible = false; customReady = false;
      customReadFailed = false; controlsReadPending = 0; updateAdmission();
    }
    stopPolling();
  }
  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'settings') { leaveAlerts(); }
  });

  // Belt and braces since round 5's D1, and KEPT deliberately.
  //
  // It was load-bearing: #preview-enabled and this card shared ONE section
  // with no navigation between them, so toggling previews off had to stop
  // showing a healthy-looking card without waiting for a route change.
  // D1 moved this card to a section of its own, so the user must now cross
  // a section boundary to see it after touching that toggle, and the
  // wm:section listener above already refreshes on arrival. That makes
  // this redundant rather than wrong -- and re-deriving it would be the
  // expensive way to find out, so it stays with the reason written down.
  //
  // settings.js dispatches it once its own bridge call settles (not on the
  // raw DOM change), so this refresh cannot race ahead of the host.stop()
  // / alerts.reconcile() that call performs.
  document.addEventListener('wm:preview-enabled-changed', refresh);
}());
