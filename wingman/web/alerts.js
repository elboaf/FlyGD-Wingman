// ---- Gamelog alerts --------------------------------------------------
// Its own section, Settings > Alerts, since round 5's D1 -- it was the
// third card in Settings > Previews, alongside previews.js and the
// keybind block in settings.js. Not folded into either: this owns none
// of the win32/AutoHotkey machinery those files do, and gets its own
// bridge endpoints for the same reason set_preview_enabled does --
// toggling `enabled` here starts or stops a polling thread (the gamelog
// tailer), not merely a settings write.
//
// A READ, not a push: get_alert_state exists precisely so this can ask
// on wm:section, the same reasoning get_preview_hotkey_state documents --
// the tailer can start before the webview exists (start_previews_if_
// enabled runs before window_mod.run()), so a health change discovered
// at launch would be pushed into a window that is not there yet.
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
     #4dd2ff and both on Notify: a cyan pulse that could mean "you are
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
  function paintSwatches(row, id, colour) {
    if (!row.colors) { return; }
    var wanted = COLOURS.slice();
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
        var name = colourName(hex);
        label.title = name === hex ? hex : name + ' (' + hex + ')';
        input.setAttribute('aria-label', name);
        label.appendChild(input);
        label.appendChild(dot);
        row.colors.appendChild(label);
      });
      // The dots remain the compact chooser; this line gives the selected
      // value a word without adding a sixth column to the floor-width grid.
      var readout = WM.make('span', 'swatch-name');
      readout.setAttribute('aria-hidden', 'true');
      row.colors.appendChild(readout);
      row.colors.setAttribute('data-built', wanted.join(','));
    }

    var boxes = row.colors.querySelectorAll('input');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = boxes[i].value === colour;
    }
    setText(row.colors.querySelector('.swatch-name'), colourName(colour));
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
        // The dot follows the native radio immediately; the word follows the
        // accepted value here so a refused write never labels an unsaved choice.
        setText(row.colors.querySelector('.swatch-name'), colourName(wanted));
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

  // The health line and the characters are ALWAYS one sentence, on
  // purpose: a list rendered on its own keeps reading "watching Alice,
  // Bob" after the tailer thread has died, which is a healthy-looking
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
  // service.py's _resolved_folder gates the THREAD on three things --
  // previews on, master switch on, a folder that still resolves -- so
  // `running: true` proves all three. It proves nothing at all about the
  // event table, which service.py's _handle consults separately and which
  // drops every event whose spec is not `enabled`. Untick all three rows
  // and the tailer genuinely is reading gamelogs, genuinely has thirteen
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
    if (!anyEventEnabled(state.alerts)) {
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
    WM.send('get_alert_state').then(function (state) {
      if (!state) { return; }
      render(state, controls);
    });
  }

  function refresh() { read(true); }

  // The first setInterval in the page, so it is worth saying why.
  //
  // get_alert_state is deliberately a READ, not a push -- the tailer can
  // start before the webview exists, so a health change discovered at
  // launch would be pushed into a window that is not there. That is still
  // right. What it left was a card that reads its state exactly three
  // times: on section entry, on a previews toggle, and immediately after
  // the alerts switch.
  //
  // That last one is the bug this fixes, and it was reported from a real
  // session: enabling alerts refreshes AT ONCE, while AlertService has
  // only just been reconciled and its tailer's first rescan is up to
  // POLL_INTERVAL_S away. So the card read `running: true, characters:
  // []`, rendered "no characters online yet", and nothing ever read
  // again -- five characters online and the card saying none, for as long
  // as you left it open.
  //
  // The same gap hid the failure the health line exists to catch: a
  // tailer that dies at minute 40 of a sit kept reading as healthy,
  // because nothing asked again.
  //
  // Only while the section is showing. Nothing needs to be current when
  // it is not, which is the same reasoning the one-shot reads were built
  // on.
  var STATUS_POLL_MS = 2000;
  var poll = null;

  function startPolling() {
    if (poll === null) { poll = window.setInterval(function () { read(false); },
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
      refresh();
      startPolling();
    } else {
      stopPolling();
    }
  });

  // A route change leaves Settings without dispatching wm:section at all,
  // so the section listener above never hears about it and the poll would
  // outlive the screen.
  document.addEventListener('wm:route', function (event) {
    if (event.detail !== 'settings') { stopPolling(); }
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
