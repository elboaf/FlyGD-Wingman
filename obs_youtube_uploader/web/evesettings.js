/* FlyGD Wingman — the Profiles route (EVE settings copier).
 *
 * Deliberately dumb, for the same reason bookmarks.js is: this repo has no
 * way to test JavaScript (docs/history/webview-replatform-design.md:545),
 * so every decision -- what is a valid target, what may be overwritten,
 * what gets backed up -- happens in Python. This file captures events,
 * sends them, and renders the answer.
 */
(function () {
  'use strict';

  var state = null;
  var selected = {};
  // The rows renderTargets() actually drew. Select-all and the copy list
  // are both taken from this rather than from rows(), so what the filter
  // shows and what the button acts on can never disagree.
  var visible = [];
  var busy = false;
  // The folder card's second face. Collapsed on every entry to the route
  // rather than remembered: the point of collapsing it is that the target
  // list is on screen at open, and a card that stayed expanded across
  // visits would give that back. There is also nowhere to persist it --
  // no bridge method on this screen carries page state.
  var expanded = false;

  function kind() {
    var checked = document.querySelector('input[name="es-kind"]:checked');
    return checked ? checked.value : 'characters';
  }

  function rows() {
    if (!state) return [];
    return kind() === 'accounts' ? state.accounts : state.characters;
  }

  function refresh() {
    WM.send('eve_settings_state').then(render);
  }

  function render(payload) {
    if (!payload) return;
    state = payload;
    WM.el('es-root').textContent = payload.root || 'No folder selected';
    paintPill(payload.eve_running);
    paintFolder();

    var warning = WM.el('es-warning');
    // "Couldn't read", "too wide to be an EVE folder" and "nothing there"
    // are three different answers, and each asks the user for something
    // different. Python decides which; this only picks the sentence.
    warning.hidden = !(payload.unreadable || payload.too_broad);
    if (payload.too_broad) {
      warning.textContent =
        'That folder was too large to search fully, so this list may be '
        + 'incomplete. Pick the EVE folder itself, usually '
        + (payload.default_root || '%LOCALAPPDATA%\\CCP\\EVE') + '.';
    } else if (payload.unreadable) {
      warning.textContent =
        "Couldn't read that folder. Check it still exists and is readable.";
    } else {
      warning.textContent = '';
    }

    // Short on purpose: .settings .row > select.field is a fixed 150px, and
    // "Choose a folder first" rendered as "Choose a folder fi". A truncated
    // placeholder is a worse answer than the blank it replaced.
    fill('es-server', payload.servers, payload.server, 'No folder chosen');
    fill('es-profile', payload.profiles, payload.profile, 'No folder chosen');
    renderSource();
    renderTargets();
    renderBackups();
  }

  // No root, or a folder Python could not read through: there is nothing
  // to summarise and the user has to act on it, so the controls open
  // regardless of what the Change link was last told.
  function forcedOpen() {
    return !state || !state.root || state.unreadable || state.too_broad;
  }

  function nameOf(items, path) {
    var match = (items || []).filter(function (item) {
      return item.path === path;
    })[0];
    return match ? match.name : '';
  }

  // R5: each name carries its noun. Collapsed, this row read `Folder
  // <path> Tranquility - Default`: one labelled value beside two unlabelled
  // ones, though the server and the profile decide what a copy will hit
  // exactly as much as the folder does, and `Default` on its own is not
  // obviously a profile name at all. The words go IN the text rather than
  // into two more .lab elements, because `.settings .row > .lab` is
  // width:100% -- a second label in this row would stack and break it
  // across three lines -- and because the labelled form is what the
  // expanded face already shows, in its own Server and Profile rows.
  function setLabel(name, noun) {
    return name ? name + ' ' + noun : '';
  }

  function paintFolder() {
    var open = forcedOpen() || expanded;
    WM.el('es-folder-summary').hidden = open;
    WM.el('es-folder-detail').hidden = !open;
    if (open) return;
    WM.el('es-folder-root').textContent = state.root;
    WM.el('es-folder-set').textContent =
      [setLabel(nameOf(state.servers, state.server), 'server'),
       setLabel(nameOf(state.profiles, state.profile), 'profile')]
        .filter(Boolean).join(' \u00b7 ');
  }

  // Three states, not two. null means the probe has not answered yet, and
  // rendering that as "EVE closed" would be a reassuring guess about the
  // only warning shown before a copy -- the probe runs off the bridge
  // thread precisely because its first pass is slow.
  //
  // Painted over BOTH mount points (Profiles 1). The pill in the folder
  // card's heading is off-screen at the moment that matters -- `Copy to
  // selected` sits at the bottom of the second card, and in the scrolled
  // capture the button is visible and the pill is not. The second one rides
  // with the button. One function over two elements rather than two
  // renderers, so the two can never disagree about the same probe.
  function paintPill(running) {
    var pills = [WM.el('es-eve-state'), WM.el('es-eve-state-commit')]
      .filter(Boolean);
    if (!pills.length) return;
    var text, cls;
    if (running === null || running === undefined) {
      text = 'Checking for EVE\u2026';
      cls = 'pill idle';
    } else {
      text = running ? 'EVE running' : 'EVE closed';
      cls = 'pill ' + (running ? 'warn' : 'idle');
    }
    pills.forEach(function (pill) {
      pill.textContent = text;
      pill.className = cls;
    });
  }

  // Profiles 6: with nothing to offer, Server and Profile rendered exactly
  // like working dropdowns -- blank, un-placeholdered, undimmed -- so an
  // un-chosen folder looked like a broken control rather than a control
  // that has nothing to say yet. A disabled select with one placeholder
  // option says which of the two it is. `empty` names the reason rather
  // than the state ("Choose a folder first"), because the reason is the
  // half the user can act on and the control they must act on is in the
  // same row.
  function fill(id, items, current, empty) {
    var el = WM.el(id);
    el.innerHTML = '';
    var list = items || [];
    el.disabled = !list.length;
    if (!list.length) {
      var placeholder = document.createElement('option');
      // An <option> with no value attribute reports its TEXT as .value, so
      // without this the select's value is the placeholder sentence itself
      // -- a string the rest of this file compares against real paths.
      placeholder.value = '';
      placeholder.textContent = empty;
      el.appendChild(placeholder);
      return;
    }
    list.forEach(function (item) {
      var option = document.createElement('option');
      option.value = item.path;
      option.textContent = item.name;
      option.selected = item.path === current;
      el.appendChild(option);
    });
  }

  // Profiles 6 names Server and Profile. `Copy from` is the same control
  // with the same failure -- and once the other two carry a placeholder,
  // leaving the third blank beside them states the finding more loudly than
  // before rather than less. Extended deliberately, not in passing.
  function renderSource() {
    var el = WM.el('es-source');
    var previous = el.value;
    var list = rows();
    el.innerHTML = '';
    el.disabled = !list.length;
    if (!list.length) {
      var placeholder = document.createElement('option');
      // Empty value for fill()'s reason, and it bites harder here:
      // renderTargets excludes `row.path === es-source.value` from the
      // roster, so a placeholder reporting its own text would be compared
      // against every character's path on every keystroke of the filter.
      placeholder.value = '';
      placeholder.textContent =
        'No ' + (kind() === 'accounts' ? 'accounts' : 'characters');
      el.appendChild(placeholder);
      return;
    }
    list.forEach(function (row) {
      var option = document.createElement('option');
      option.value = row.path;
      option.textContent = row.name;
      option.selected = row.path === previous;
      el.appendChild(option);
    });
  }

  function renderTargets() {
    var host = WM.el('es-targets');
    var needle = (WM.el('es-filter').value || '').toLowerCase();
    var source = WM.el('es-source').value;
    host.innerHTML = '';
    visible = [];
    rows().forEach(function (row) {
      if (row.path === source) return;
      if (needle && row.name.toLowerCase().indexOf(needle) === -1) return;
      visible.push(row);
      // The .check/.box pattern, NOT a bare input: nothing in style.css
      // targets input[type=checkbox], so the dark appearance comes ENTIRELY
      // from this wrapper (.check input is opacity:0 and the styled .box is
      // what you see). A bare input here painted one native white Win32
      // checkbox per character inside a dark card. bookmarks.js:113-115
      // builds the same control and carries the same warning.
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = row.path;
      box.checked = !!selected[row.path];
      box.addEventListener('change', function () {
        selected[row.path] = box.checked;
        paintCommit();
      });
      var label = WM.make('label', 'check', ' ' + row.name);
      label.prepend(WM.make('span', 'box'));
      label.prepend(box);
      host.appendChild(label);
    });
    // Collapses to ZERO height when nothing matches -- no border, no
    // background, no min-height -- so the card silently showed a source
    // dropdown, a filter and a Copy button with a void between them.
    // Nothing distinguished "filter matched nothing" from "this folder has
    // no characters" from "not loaded yet".
    if (!visible.length) host.appendChild(WM.make('p', 'empty', emptyText(needle)));
    // Every path that changes what is on screen ends here -- filter, source,
    // Characters/Accounts, Select all, Clear, and the initial render -- so
    // the count and the button's enabled state are decided in one place
    // rather than at six call sites that would drift.
    paintCommit();
  }

  // Profiles 5: with no folder chosen this said "No other characters in
  // this profile." There is no profile. It reported a downstream condition
  // -- true, and unactionable -- instead of the one actually stopping the
  // user, which is the same mistake the Uploader's empty state makes
  // (walkthrough finding 12) and wants the same instinct: name the thing
  // that is blocking you, then what to do about it (PRODUCT.md's tone rule,
  // "say what happened and what to do").
  //
  // Ordered blocking-first. The filter is last because it is the only one
  // of the four the user reached deliberately, so it cannot be the answer
  // while an earlier condition is still unmet.
  function emptyText(needle) {
    var noun = kind() === 'accounts' ? 'accounts' : 'characters';
    if (!state || !state.root) {
      return 'No EVE settings folder chosen yet. Choose or detect one above.';
    }
    // #es-warning already carries the whole diagnosis and what to do about
    // it; repeating it here would say it twice in one card. This only has
    // to stop claiming the folder is empty when it was never read.
    if (state.unreadable || state.too_broad) {
      return 'Nothing could be read from that folder. See the warning above.';
    }
    if (needle) return 'No ' + noun + ' match that filter.';
    return 'No other ' + noun + ' in this profile.';
  }

  // Backup stamps arrive exactly as they are spelled in the filename --
  // backup.parse_name joins its date and time groups raw, so `created` is
  // 20260824-140300 and not the "2026-08-24 14:03" it reads as. Punctuating
  // it is what makes the column scannable, which is the whole reason the
  // row became columns. Guarded rather than sliced blind: a stamp that ever
  // stops being YYYYMMDD-HHMMSS renders as itself instead of as nonsense.
  function whenText(created) {
    var stamp = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}$/.exec(created || '');
    if (!stamp) return created || '';
    return stamp[1] + '-' + stamp[2] + '-' + stamp[3]
      + ' ' + stamp[4] + ':' + stamp[5];
  }

  function renderBackups() {
    var host = WM.el('es-backups');
    host.innerHTML = '';
    // The depth comes off the payload, never a literal. Four places once
    // carried the bookmark-keybind count and three of them drifted, and
    // this is the same shape: a number the page would have to keep in step
    // with settings.json by hand. "of each" is load-bearing rather than
    // padding -- backup.prune keys on (kind, source, stem), so eleven
    // copies onto eleven different characters prune nothing.
    WM.el('es-backup-note').textContent =
      'Every copy backs up what it is about to overwrite. The newest '
      + state.auto_keep + ' automatic backups of each character, account '
      + 'or profile are kept; the ones you make here stay until you '
      + 'delete them.';
    // An empty list means one of two things and only Python knows which.
    // Saying "No backups yet" about a store we were denied would invite an
    // overwrite the user believes is protected.
    if (state.backups_unreadable || !(state.backups || []).length) {
      var note = document.createElement('p');
      note.className = 'hint';
      note.textContent = state.backups_unreadable
        ? "Couldn't read the backups folder. Check it is still readable."
        : 'No backups yet.';
      host.appendChild(note);
      if (state.backups_unreadable) return;
    }
    (state.backups || []).forEach(function (item) {
      var line = WM.make('div', 'row');
      line.appendChild(WM.make('span', 'bk-when', whenText(item.created)));
      line.appendChild(WM.make('span', 'bk-what',
        item.kind + ' \u00b7 ' + item.stem));
      // Both origins named in full, rather than a bare "(auto)" on half the
      // rows and nothing on the other half. The suffix had no key anywhere
      // in the app; a column that says "manual" too explains it by
      // contrast, and the note above says what "automatic" costs.
      line.appendChild(WM.make('span', 'bk-origin',
        item.origin === 'auto' ? 'automatic' : 'manual'));
      line.appendChild(button('Restore', function () {
        mutate('eve_settings_restore', item.path);
      }));
      // Deleting a backup is the only irreversible action on this screen
      // that Restore is not -- and both were the same plain .btn. The
      // treatment is the one skills.js already uses for Forget character.
      line.appendChild(button('Delete', function () {
        mutate('eve_settings_delete_backup', item.path);
      }, 'danger'));
      host.appendChild(line);
    });
  }

  function button(text, handler, extra) {
    var el = document.createElement('button');
    el.className = extra ? 'btn ' + extra : 'btn';
    el.textContent = text;
    el.disabled = busy;
    el.addEventListener('click', handler);
    return el;
  }

  function chosenTargets() {
    // Only what is on screen: a path checked before the filter narrowed,
    // or before it became the source, is no longer a target the user can
    // see and must not inflate the confirmation's count.
    return visible.filter(function (row) {
      return !!selected[row.path];
    }).map(function (row) { return row.path; });
  }

  // Profiles 1's other half, and X1's execution on this route.
  //
  // The count is the cost, stated on the page before the irreversible
  // action rather than only inside the confirm. ui/copy.py already puts a
  // count in the dialog (Profiles 3); what the SCREEN had was no quantity
  // at all, while the Uploader prints "1 selected - 108.8 MB" a route away.
  //
  // The noun is taken from the Characters/Accounts switch, which is the
  // authority for what the user believes they ticked. ui/copy.py derives
  // its noun from the target paths instead, and deliberately: the two can
  // only disagree for a mixed selection, which this page cannot produce and
  // the bridge does not forbid. Do not "fix" one to match the other.
  //
  // X1: the disabled treatment already existed and worked -- what was
  // missing was the attribute, so `Copy to selected` was full-strength
  // accent with nothing ticked, no folder chosen, and "No other characters
  // in this profile" printed above it. Busy and empty are one decision
  // here because they are one question: can this button act right now.
  function paintCommit() {
    var count = chosenTargets().length;
    var noun = kind() === 'accounts' ? 'account' : 'character';
    var label = WM.el('es-copy-count');
    label.textContent = count
      ? count + ' ' + noun + (count === 1 ? '' : 's') + ' will be overwritten'
      : 'Nothing selected';
    // Dimmed, not emptied: a blank slot beside a disabled button reads as a
    // layout gap rather than as the answer to "how many".
    label.classList.toggle('none', !count);
    WM.setEnabled('es-copy', !busy && count > 0);
    // The hazard is about what this button is ABOUT to do, so it appears
    // only while the button can do it: with nothing selected it would say
    // "EVE running" about a copy that cannot happen.
    //
    // It does NOT stop the two pills sharing a viewport, and this comment
    // used to claim it did ("the one state where both are on screen
    // together -- no folder chosen"). False: the heading pill lives in the
    // h2 precisely so it survives the folder card collapsing, so with a
    // folder chosen and a character selected a tall window shows both,
    // about 545 CSS px apart (round 3, P8).
    //
    // That overlap is accepted. The two answer different questions -- the
    // heading pill is the screen's standing answer, this one is the
    // commit's -- and outside the overlap their coverage is complementary:
    // while choosing, only the heading pill is up; scrolled to the button,
    // the heading pill has left the viewport and only this one is (which is
    // why the second was added at all, see paintPill). Neither is
    // removable, and closing the overlap by weakening this guard would
    // drop the hazard in the state where it is the only warning.
    WM.el('es-eve-state-commit').hidden = count === 0;
  }

  function setBusy(value) {
    busy = value;
    // Not `es-copy.disabled = value`: that is half the question. paintCommit
    // owns the whole of it, so a copy that finishes cannot re-enable a
    // button whose selection was cleared by the same push.
    paintCommit();
    WM.el('es-backup-profile').disabled = value;
    Array.prototype.forEach.call(
      WM.el('es-backups').querySelectorAll('button'), function (el) {
        el.disabled = value;
      });
  }

  function mutate(method) {
    // Every mutation goes through here. The bridge returns as soon as the
    // worker is spawned, so a falsy answer means no worker started (the
    // lock was held, or the spawn failed) and nothing will ever push --
    // anything else waits for onEveSettingsDone.
    var args = Array.prototype.slice.call(arguments);
    if (busy) return;
    setBusy(true);
    WM.send.apply(null, args).then(function (accepted) {
      if (!accepted) setBusy(false);
    });
  }

  function wire() {
    // Hidden before the route is ever entered, so the gap between the page
    // loading and the first state landing does not render "EVE closed" --
    // a reassuring guess about the only warning shown before a copy, which
    // is the thing paintPill's three-state handling exists to avoid.
    WM.el('es-eve-state-commit').hidden = true;

    WM.el('es-folder-edit').addEventListener('click', function () {
      expanded = true;
      paintFolder();
    });

    // Profiles 4. Both controls answer the same question -- where is the
    // EVE settings folder -- so they end the same way: selection dropped
    // (a source picked in the old tree does not exist in the new one),
    // state re-read, names re-resolved.
    //
    // Neither reads the return value, and Detect's is not special. The
    // bridge writes the root itself and returns "" for all three of "the
    // lock was held", "nothing found" and "already set to this" -- the
    // last two having already said so through _alert -- so a page that
    // branched on it would be second-guessing an answer Python has already
    // given the user. refresh() is what shows the outcome, in every case.
    function chooseRoot(method) {
      return function () {
        WM.send(method).then(function () {
          selected = {};
          refresh();
          WM.send('eve_settings_resolve_names');
        });
      };
    }

    WM.el('es-pick').addEventListener('click',
      chooseRoot('eve_settings_pick_root'));
    WM.el('es-detect').addEventListener('click',
      chooseRoot('eve_settings_detect_root'));

    ['es-server', 'es-profile'].forEach(function (id) {
      WM.el(id).addEventListener('change', function () {
        // A source picked in the old settings set does not exist in the new
        // one, so the selection is dropped rather than carried.
        selected = {};
        WM.send('eve_settings_select', WM.el('es-server').value,
                WM.el('es-profile').value).then(function () {
          refresh();
          WM.send('eve_settings_resolve_names');
        });
      });
    });

    Array.prototype.forEach.call(
      document.querySelectorAll('input[name="es-kind"]'), function (radio) {
        radio.addEventListener('change', function () {
          selected = {};
          renderSource();
          renderTargets();
        });
      });

    WM.el('es-filter').addEventListener('input', renderTargets);
    WM.el('es-source').addEventListener('change', renderTargets);

    WM.el('es-all').addEventListener('click', function () {
      visible.forEach(function (row) { selected[row.path] = true; });
      renderTargets();
    });

    WM.el('es-none').addEventListener('click', function () {
      selected = {};
      renderTargets();
    });

    WM.el('es-copy').addEventListener('click', function () {
      var targets = chosenTargets();
      if (!targets.length) return;
      mutate('eve_settings_copy', WM.el('es-source').value, targets);
    });

    WM.el('es-backup-profile').addEventListener('click', function () {
      // Saves a pointless round trip. It is NOT the guard: _eve_backup_worker
      // rejects an empty or missing path itself, because this file cannot be
      // tested and that decision has to be one that is.
      if (!state || !state.profile) return;
      mutate('eve_settings_backup', state.profile, 'profile');
    });

    document.addEventListener('wm:route', function (event) {
      if (event.detail !== 'evesettings') return;
      // Every visit starts collapsed. render() is what repaints it, and it
      // runs off the refresh below.
      expanded = false;
      refresh();
      // Names are resolved on first open, never at launch: the tray app
      // starts hidden and must not make a network call nobody asked for.
      WM.send('eve_settings_resolve_names');
    });
  }

  WM.handle('onEveSettingsNames', function () { refresh(); });

  // The running-client probe answers after the state that triggered it was
  // already returned, so the pill is repainted in place. Only the pill: a
  // full refresh would rebuild the target checklist under the user's
  // cursor for an advisory badge nothing is blocked on.
  WM.handle('onEveSettingsRunning', function (payload) {
    if (state) state.eve_running = payload.running;
    paintPill(payload.running);
  });

  // The completion signal for every mutation. It replaces a setTimeout that
  // fired 250ms into a copy the worker had barely started, and it is what
  // re-enables the buttons disabled on send.
  WM.handle('onEveSettingsDone', function (payload) {
    if (payload.ok) selected = {};
    setBusy(false);
    refresh();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
}());
