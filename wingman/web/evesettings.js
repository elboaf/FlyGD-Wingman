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
  // Choices belong to a kind: both payloads may use the same id for groups
  // with different settings semantics. Missing ids are initialized when
  // first seen, so a later state repaint cannot overwrite a user's choice.
  var copyGroupSelections = { characters: {}, accounts: {} };
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
  var identityExpanded = false;
  var backupVisible = 20;
  var identifyCandidate = null;
  var identityStep = 'idle';
  var identityMessage = '';
  var pendingCharacterId = '';
  var rosterAccountId = '';
  var additionAvailable = false;
  var identityRouteOpen = false;

  function kind() {
    var checked = document.querySelector('input[name="es-kind"]:checked');
    return checked ? checked.value : 'characters';
  }

  function rows() {
    if (!state) return [];
    return kind() === 'accounts' ? state.accounts : state.characters;
  }

  function refresh() {
    return WM.send('eve_settings_state').then(render);
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
    renderIdentity();
    renderCopyGroups();
    renderTargets();
    renderBackups();
    renderFormationsCard();
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

  function accountById(accountId) {
    return ((state && state.accounts) || []).filter(function (account) {
      return account.id === accountId;
    })[0] || null;
  }

  function characterById(characterId) {
    return ((state && state.identity_characters) || []).filter(function (character) {
      return character.id === characterId;
    })[0] || null;
  }

  function confirmCharacterMove(accountId, characterId, done) {
    var account = accountById(accountId);
    var owner = (state.accounts || []).filter(function (other) {
      return other.id !== accountId
        && (other.character_ids || []).indexOf(characterId) !== -1;
    })[0];
    if (!owner || !account) { done(); return; }
    var character = characterById(characterId);
    WM.confirm('Move character?',
      (character ? character.name : 'This character') + ' is linked to '
      + owner.display_name + '. Move the link to ' + account.display_name + '?')
      .then(function (yes) { if (yes) done(); });
  }

  function addCharacterLink(accountId, characterId, done, statusId) {
    var account = accountById(accountId);
    var ids = account ? (account.character_ids || []).slice() : [];
    if (ids.indexOf(characterId) === -1) ids.push(characterId);
    var save = function () {
      WM.send('eve_settings_set_account_characters', accountId, ids)
        .then(function (result) {
          WM.el(statusId || 'es-identity-status').textContent =
            result && result.error || '';
          if (result && result.applied) done();
        });
    };
    confirmCharacterMove(accountId, characterId, save);
  }

  function renderIdentity() {
    var accountsMode = kind() === 'accounts';
    WM.el('es-account-tools').hidden = !accountsMode;
    if (WM.current_route !== 'accountidentity') return;

    var panel = WM.el('es-identity-panel');
    WM.el('es-manage-toggle').textContent = identityExpanded
      ? 'Close names and character links' : 'Manage names and character links…';
    panel.hidden = !identityExpanded;
    if (identityExpanded) {
      var picker = WM.el('es-identity-account');
      var keep = picker.value;
      picker.textContent = '';
      (state.accounts || []).forEach(function (account) {
        var option = document.createElement('option');
        option.value = account.id;
        option.textContent = account.name;
        picker.appendChild(option);
      });
      if (keep && accountById(keep)) picker.value = keep;
      renderIdentityAccount();
    }
    var step = identityStep === 'idle' && state.identification_active ? 'watching' : identityStep;
    renderRoster();
    paintIdentification(step, identityMessage);
  }

  function renderIdentityAccount() {
    var account = accountById(WM.el('es-identity-account').value);
    WM.el('es-manage-account-name').value = account ? account.account_name : '';
    var linked = account ? account.character_ids || [] : [];
    var host = WM.el('es-account-characters');
    host.textContent = '';
    linked.forEach(function (characterId) {
      var character = characterById(characterId);
      var line = WM.make('div', 'es-linked-character');
      line.appendChild(WM.make('span', '', character ? character.name :
        'Character ' + characterId));
      var remove = WM.make('button', 'linkbtn', 'Remove');
      remove.type = 'button';
      remove.setAttribute('aria-label', 'Remove ' + (character
        ? character.name : 'Character ' + characterId));
      remove.disabled = busy || !!state.identification_active;
      remove.addEventListener('click', function () {
        var remaining = linked.filter(function (id) { return id !== characterId; });
        WM.send('eve_settings_set_account_characters', account.id, remaining)
          .then(function (result) {
            WM.el('es-manage-status').textContent = result && result.error || '';
            if (result && result.applied) refresh();
          });
      });
      line.appendChild(remove);
      host.appendChild(line);
    });
    if (!host.children.length) {
      host.appendChild(WM.make('p', 'empty', 'No confirmed characters yet.'));
    }

    var add = WM.el('es-character-add');
    add.textContent = '';
    ((state && state.identity_characters) || []).forEach(function (character) {
      if (linked.indexOf(character.id) !== -1) return;
      var option = document.createElement('option');
      option.value = character.id;
      option.textContent = character.name;
      add.appendChild(option);
    });
    var cannotAdd = !account || linked.length >= 3 || !add.options.length;
    WM.el('es-character-add-row').hidden = cannotAdd;
    WM.el('es-character-add-btn').disabled = cannotAdd;
  }

  function renderRoster() {
    var account = accountById(rosterAccountId);
    var linked = account ? account.character_ids || [] : [];
    var host = WM.el('ai-roster-characters');
    host.textContent = '';
    linked.forEach(function (characterId) {
      var character = characterById(characterId);
      host.appendChild(WM.make('div', 'es-linked-character', character
        ? character.name : 'Character ' + characterId));
    });
    WM.el('ai-roster-heading').textContent = account
      ? account.account_name : 'Account roster';
    WM.el('ai-roster-count').textContent = linked.length + ' of 3 characters linked';
    var add = WM.el('ai-roster-character');
    add.textContent = '';
    ((state && state.identity_characters) || []).forEach(function (character) {
      if (linked.indexOf(character.id) !== -1) return;
      var option = document.createElement('option');
      option.value = character.id;
      option.textContent = character.name;
      add.appendChild(option);
    });
    additionAvailable = !!account && linked.length < 3 && !!add.options.length;
    WM.el('ai-roster-add-row').hidden = !additionAvailable;
    var identified = (state.accounts || []).filter(function (account) { return account.account_name; }).length;
    WM.el('ai-roster-identified').textContent = identified + ' of '
      + (state.accounts || []).length + ' accounts identified in this profile';
    WM.el('ai-roster-empty').textContent = linked.length >= 3
      ? 'This account has all 3 character links. Remove a wrong or obsolete link in account management.'
      : (additionAvailable ? ''
        : 'Only characters discovered in this EVE profile can be offered. Launch another character, make a small settings change, and close EVE completely to make it available later.');
  }

  function paintIdentification(step, message) {
    var previous = identityStep;
    var watching = step === 'watching';
    var candidate = step === 'candidate';
    var name = step === 'name';
    var roster = step === 'roster';
    identityStep = step;
    identityMessage = message || '';
    WM.el('ai-intro').hidden = watching || candidate || name || roster;
    WM.el('ai-watching-step').hidden = !watching;
    WM.el('es-identify-candidate').hidden = !candidate;
    WM.el('ai-name-step').hidden = !name;
    WM.el('ai-roster-step').hidden = !roster;
    WM.el('es-identify-start').hidden = watching || candidate || name || roster;
    WM.el('es-identify-check').hidden = !watching;
    WM.el('es-identify-cancel').hidden = !(watching || candidate || name);
    WM.el('es-identify-start').classList.toggle('acc', step === 'idle');
    WM.el('es-identify-check').classList.toggle('acc', watching);
    WM.el('es-identify-link').classList.toggle('acc', candidate);
    WM.el('es-account-name-save').classList.toggle('acc', name);
    WM.el('ai-roster-add').classList.toggle('acc', roster && additionAvailable);
    WM.el('ai-roster-done').classList.toggle('acc', roster && !additionAvailable);
    var defaultMessage = watching
      ? 'Launch one character, enter the game, make a small settings change, then close the client completely.'
      : '';
    WM.el('es-identity-status').textContent = message || defaultMessage;
    if (previous !== step) {
      var heading = WM.el(step === 'watching' ? 'ai-watching-heading'
        : step === 'candidate' ? 'es-identify-candidate-heading'
        : step === 'name' ? 'ai-name-heading'
        : step === 'roster' ? 'ai-roster-heading' : 'ai-intro-heading');
      heading.focus();
    }
  }

  function renderCandidate(payload) {
    identifyCandidate = payload;
    var select = WM.el('es-identify-character');
    select.textContent = '';
    payload.characters.forEach(function (character) {
      var option = document.createElement('option');
      option.value = character.id;
      option.textContent = character.name;
      select.appendChild(option);
    });
    var message = payload.characters.length === 1
      ? payload.characters[0].name + ' changed with ' + payload.account.option + '.'
      : 'Choose which changed character belongs to ' + payload.account.option + '.';
    paintIdentification('candidate', message);
  }

  function renderCopyGroups() {
    var row = WM.el('es-copy-options');
    var host = WM.el('es-copy-groups');
    row.hidden = true;
    host.innerHTML = '';
    if (!state) return;

    var available = !!state.selective_copy_available;
    row.hidden = !available;
    if (!available) return;

    var currentKind = kind();
    var choices = copyGroupSelections[currentKind];
    var groups = (state.copy_groups && state.copy_groups[currentKind]) || [];
    groups.forEach(function (group) {
      if (!Object.prototype.hasOwnProperty.call(choices, group.id)) {
        choices[group.id] = !!group.default_on;
      }

      var groupBox = document.createElement('input');
      groupBox.type = 'checkbox';
      // Construct the dark wrapper before wiring behavior. A bare generated
      // checkbox is a native white Windows control in this dark card.
      var groupLabel = WM.make('label', 'check', ' ' + group.label);
      groupLabel.prepend(WM.make('span', 'box'));
      groupLabel.prepend(groupBox);
      groupBox.checked = choices[group.id];
      groupBox.value = group.id;
      groupBox.addEventListener('change', function () {
        choices[group.id] = groupBox.checked;
      });
      host.appendChild(groupLabel);
    });
  }

  function selectedGroupIds() {
    var currentKind = kind();
    var choices = copyGroupSelections[currentKind];
    var groups = (state.copy_groups && state.copy_groups[currentKind]) || [];
    return groups.filter(function (group) {
      return !!choices[group.id];
    }).map(function (group) { return group.id; });
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
      var label = WM.make('label', 'check es-target-choice');
      var styledBox = WM.make('span', 'box');
      var text = WM.make('span', 'es-target-text');
      box.value = row.path;
      box.checked = !!selected[row.path];
      box.addEventListener('change', function () {
        selected[row.path] = box.checked;
        paintCommit();
      });
      text.appendChild(WM.make('span', 'es-target-name', row.display_name || row.name));
      if (row.display_meta && kind() === 'accounts') {
        text.appendChild(WM.make('span', 'es-target-meta', row.display_meta));
      } else if (row.display_meta) {
        label.title = row.display_meta;
      }
      label.appendChild(box);
      label.appendChild(styledBox);
      label.appendChild(text);
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
    var backups = state.backups || [];
    host.innerHTML = '';
    var profileName = nameOf(state.profiles, state.profile);
    var backupButton = WM.el('es-backup-profile');
    backupButton.textContent = profileName
      ? 'Back up ' + profileName + ' profile'
      : 'Back up profile';
    backupButton.disabled = busy || !profileName || !!state.identification_active;
    var keepInput = WM.el('es-auto-keep');
    if (document.activeElement !== keepInput) keepInput.value = state.auto_keep;

    // The depth comes off the payload, never a literal. Four places once
    // carried the bookmark-keybind count and three of them drifted.
    var note =
      'Every copy backs up what it is about to overwrite. The newest '
      + state.auto_keep + ' automatic backups of each character, account '
      + 'or profile are kept.';
    WM.el('es-backup-note').textContent = note;
    var commitNote = WM.el('es-copy-backup-note');
    if (commitNote) commitNote.textContent = note.split('. ')[0] + '.';

    var head = WM.el('es-backup-head');
    head.hidden = !backups.length || state.backups_unreadable;
    if (state.backups_unreadable || !backups.length) {
      var empty = document.createElement('p');
      empty.className = 'hint';
      empty.textContent = state.backups_unreadable
        ? "Couldn't read the backups folder. Check it is still readable."
        : 'No backups yet.';
      host.appendChild(empty);
    }
    backups.slice(0, backupVisible).forEach(function (item) {
      var line = WM.make('div', 'es-backup-grid es-backup-row');
      line.appendChild(WM.make('span', 'bk-when', whenText(item.created)));
      var target = WM.make('span', 'bk-what');
      target.title = item.display_name + ' · ' + item.display_meta;
      target.appendChild(WM.make('span', 'bk-name', item.display_name));
      target.appendChild(WM.make('span', 'bk-meta', item.display_meta));
      line.appendChild(target);
      line.appendChild(WM.make('span', 'bk-origin',
        item.origin === 'auto' ? 'Automatic' : 'Manual'));
      var actions = WM.make('span', 'bk-actions');
      actions.appendChild(button('Restore', function () {
        mutate('eve_settings_restore', item.path);
      }));
      actions.appendChild(button('Delete', function () {
        mutate('eve_settings_delete_backup', item.path);
      }, 'danger'));
      line.appendChild(actions);
      host.appendChild(line);
    });
    var more = WM.el('es-backups-more');
    more.hidden = backups.length <= backupVisible;
    more.disabled = busy || !!state.identification_active;
    if (!more.hidden) {
      more.textContent = 'Show ' + Math.min(20, backups.length - backupVisible)
        + ' older backups';
    }
    WM.el('es-auto-keep-apply').disabled = busy || !!state.identification_active;
  }

  // The way into the probe formation editor. Accounts only, always: a
  // formation lives in the account file, so the Characters/Accounts switch
  // above deliberately does NOT reach this card -- it would otherwise
  // decide whether the entry point exists at all.
  //
  // The whole card is hidden when Python reports no decoder, rather than
  // shown and then refused: eve_settings_formations' answer in that state
  // is a sentence, and a control whose only outcome is that sentence is
  // worse than no control.
  function renderFormationsCard() {
    var card = WM.el('es-formations-card');
    var sel = WM.el('es-formations-account');
    card.hidden = !(state && state.formations_available
                    && state.accounts && state.accounts.length);
    if (card.hidden) return;
    // The chosen account survives a refresh: onEveSettingsDone refreshes
    // after every mutation, and rebuilding the list would silently reset
    // the pick back to the first account between two clicks.
    var keep = sel.value;
    sel.textContent = '';
    state.accounts.forEach(function (account) {
      var option = document.createElement('option');
      option.value = account.path;
      option.textContent = account.name;
      sel.appendChild(option);
    });
    if (keep) sel.value = keep;
    WM.setEnabled('es-formations-open', !busy && !!sel.value
                  && !(state && state.identification_active));
  }

  function button(text, handler, extra) {
    var el = document.createElement('button');
    el.className = extra ? 'btn ' + extra : 'btn';
    el.textContent = text;
    el.disabled = busy || !!(state && state.identification_active);
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
    WM.setEnabled('es-copy', !busy && count > 0
                  && !(state && state.identification_active));
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
    // Same reason: the formations card's button is inert while a copy or a
    // restore is in flight, and paintCommit does not own it.
    renderFormationsCard();
    var identifying = !!(state && state.identification_active);
    WM.el('es-backup-profile').disabled = value || identifying
      || !(state && state.profile);
    ['es-auto-keep-apply', 'es-formations-open', 'es-backups-more',
     'es-identify-open', 'es-identify-start', 'es-manage-toggle',
     'es-account-name-apply', 'es-character-add-btn'].forEach(function (id) {
      WM.el(id).disabled = value || identifying;
    });
    ['es-identify-check', 'es-identify-cancel', 'es-account-name-save',
     'ai-roster-add', 'ai-roster-done', 'ai-identify-another'].forEach(function (id) {
      WM.el(id).disabled = value;
    });
    WM.el('es-account-name').disabled = value;
    ['es-identity-account', 'es-manage-account-name', 'es-character-add'].forEach(function (id) {
      WM.el(id).disabled = value || identifying;
    });
    Array.prototype.forEach.call(
      WM.el('es-backups').querySelectorAll('button'), function (el) {
        el.disabled = value || identifying;
      });
    Array.prototype.forEach.call(
      WM.el('es-account-characters').querySelectorAll('button'), function (el) {
        el.disabled = value || identifying;
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
          renderIdentity();
          renderCopyGroups();
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

    WM.el('es-identify-open').addEventListener('click', function () {
      identityExpanded = false;
      identityStep = 'idle';
      identityMessage = '';
      pendingCharacterId = '';
      rosterAccountId = '';
      WM.route('accountidentity');
    });

    WM.el('es-manage-toggle').addEventListener('click', function () {
      identityExpanded = !identityExpanded;
      renderIdentity();
    });

    function clearIdentification() {
      identifyCandidate = null;
      pendingCharacterId = '';
      rosterAccountId = '';
      identityMessage = '';
    }

    function backToProfiles() {
      WM.send('eve_settings_identification_cancel').then(function () {
        if (state) state.identification_active = false;
        clearIdentification();
        identityStep = 'idle';
        identityRouteOpen = false;
        WM.route('evesettings');
      });
    }
    WM.el('ai-back').addEventListener('click', backToProfiles);
    WM.el('ai-roster-done').addEventListener('click', backToProfiles);

    WM.el('es-identity-account').addEventListener('change', renderIdentityAccount);

    function saveManagedAccountName() {
      var accountId = WM.el('es-identity-account').value;
      WM.send('eve_settings_set_account_name', accountId,
              WM.el('es-manage-account-name').value).then(function (result) {
        WM.el('es-manage-status').textContent = result && result.error || '';
        if (result && result.applied) refresh();
      });
    }
    WM.el('es-account-name-apply').addEventListener('click', saveManagedAccountName);
    WM.el('es-manage-account-name').addEventListener('keydown', function (event) {
      if (event.key === 'Enter') saveManagedAccountName();
    });

    WM.el('es-character-add-btn').addEventListener('click', function () {
      var accountId = WM.el('es-identity-account').value;
      var characterId = WM.el('es-character-add').value;
      if (!accountId || !characterId) return;
      addCharacterLink(accountId, characterId, refresh, 'es-manage-status');
    });

    WM.el('es-identify-start').addEventListener('click', function () {
      WM.send('eve_settings_identification_start').then(function (result) {
        var step = result && result.status === 'watching' ? 'watching' : 'idle';
        if (state) state.identification_active = step === 'watching';
        clearIdentification();
        paintIdentification(step, result && result.error);
        setBusy(busy);
      });
    });

    WM.el('es-identify-check').addEventListener('click', function () {
      WM.send('eve_settings_identification_check').then(function (result) {
        if (result && result.status === 'candidate') {
          if (state) state.identification_active = true;
          renderCandidate(result);
        } else {
          // Check failures are waiting variants: paint the returned result so
          // a failed restart cannot leave stale page-local state on screen.
          if (state) {
            state.identification_active = !!result && (result.status === 'watching'
              || result.status === 'none' || result.status === 'ambiguous');
          }
          identifyCandidate = null;
          pendingCharacterId = '';
          paintIdentification('watching', result && result.error
            || 'No account and character changes were found. Make a small settings change in the client, then close it completely and check again.');
        }
        setBusy(busy);
      });
    });

    WM.el('es-identify-cancel').addEventListener('click', function () {
      WM.send('eve_settings_identification_cancel').then(function () {
        if (state) state.identification_active = false;
        clearIdentification();
        paintIdentification('idle');
        setBusy(busy);
      });
    });

    function openRoster(accountId) {
      rosterAccountId = accountId;
      pendingCharacterId = '';
      identifyCandidate = null;
      identityMessage = '';
      refresh().then(function () { paintIdentification('roster'); setBusy(busy); });
    }

    function confirmIdentification(accountId, characterId, accountName) {
      WM.send('eve_settings_identification_confirm', accountId, characterId, accountName)
        .then(function (result) {
          var error = result && result.error || '';
          WM.el('ai-name-status').textContent = error;
          if (result && result.applied) {
            openRoster(accountId);
          } else if (identityStep !== 'name') {
            paintIdentification(identityStep, error);
          }
        });
    }

    function saveIdentificationName() {
      if (!identifyCandidate || !pendingCharacterId) return;
      confirmIdentification(identifyCandidate.account.id, pendingCharacterId,
        WM.el('es-account-name').value);
    }
    WM.el('es-account-name-save').addEventListener('click', saveIdentificationName);
    WM.el('es-account-name').addEventListener('keydown', function (event) {
      if (event.key === 'Enter') WM.el('es-account-name-save').click();
    });

    WM.el('es-identify-link').addEventListener('click', function () {
      if (!identifyCandidate) return;
      var accountId = identifyCandidate.account.id;
      var characterId = WM.el('es-identify-character').value;
      if (!identifyCandidate.characters.some(function (character) {
        return character.id === characterId;
      })) return;
      var account = accountById(accountId);
      var continueLink = function () {
        if (account && account.account_name) {
          confirmIdentification(accountId, characterId, account.account_name);
          return;
        }
        pendingCharacterId = characterId;
        WM.el('ai-name-match').textContent = (characterById(characterId) || {
          name: 'Character ' + characterId
        }).name + ' will be linked to ' + accountId + '.';
        WM.el('ai-name-status').textContent = '';
        paintIdentification('name');
      };
      confirmCharacterMove(accountId, characterId, continueLink);
    });

    WM.el('ai-roster-add').addEventListener('click', function () {
      var characterId = WM.el('ai-roster-character').value;
      if (!rosterAccountId || !characterId || !additionAvailable) return;
      addCharacterLink(rosterAccountId, characterId, function () {
        identityStep = 'roster';
        refresh();
      }, 'ai-roster-empty');
    });

    WM.el('ai-identify-another').addEventListener('click', function () {
      WM.send('eve_settings_identification_cancel').then(function () {
        if (state) state.identification_active = false;
        clearIdentification();
        paintIdentification('idle');
        setBusy(busy);
      });
    });

    WM.el('es-copy').addEventListener('click', function () {
      var targets = chosenTargets();
      if (!targets.length) return;
      if (state.selective_copy_available) {
        mutate('eve_settings_copy', WM.el('es-source').value, targets,
               selectedGroupIds());
      } else {
        mutate('eve_settings_copy', WM.el('es-source').value, targets);
      }
    });

    WM.el('es-formations-open').addEventListener('click', function () {
      var path = WM.el('es-formations-account').value;
      // Guarded on WM.openFormations rather than assumed: formations.js
      // loads after this file, and a page that lost the script tag would
      // otherwise throw inside a click handler where nothing reports it.
      if (path && WM.openFormations) WM.openFormations(path);
    });

    WM.el('es-backup-profile').addEventListener('click', function () {
      // Saves a pointless round trip. It is NOT the guard: _eve_backup_worker
      // rejects an empty or missing path itself, because this file cannot be
      // tested and that decision has to be one that is.
      if (!state || !state.profile) return;
      mutate('eve_settings_backup', state.profile, 'profile');
    });

    WM.el('es-auto-keep-apply').addEventListener('click', function () {
      if (busy) return;
      WM.el('es-auto-keep-status').textContent = '';
      setBusy(true);
      WM.send('eve_settings_set_auto_keep', WM.el('es-auto-keep').value)
        .then(function (result) {
          if (result && result.accepted) return;
          setBusy(false);
          if (result) WM.el('es-auto-keep').value = result.value;
          WM.el('es-auto-keep-status').textContent = result && result.error || '';
        });
    });
    WM.el('es-auto-keep').addEventListener('keydown', function (event) {
      if (event.key === 'Enter') WM.el('es-auto-keep-apply').click();
    });

    WM.el('es-backups-more').addEventListener('click', function () {
      backupVisible += 20;
      renderBackups();
    });

    document.addEventListener('wm:route', function (event) {
      var leavingIdentity = identityRouteOpen
        && event.detail !== 'accountidentity';
      identityRouteOpen = event.detail === 'accountidentity';
      if (identityRouteOpen) {
        identityExpanded = false;
        clearIdentification();
        identityStep = 'idle';
        refresh();
        WM.send('eve_settings_resolve_names');
        return;
      }
      // Every route away from the focused identity flow cancels its
      // ephemeral snapshot. The durable links already confirmed stay.
      if (leavingIdentity) {
        WM.send('eve_settings_identification_cancel');
        if (state) state.identification_active = false;
      }
      if (event.detail !== 'evesettings') return;
      // Every visit starts collapsed. render() is what repaints it, and it
      // runs off the refresh below.
      expanded = false;
      identityExpanded = false;
      clearIdentification();
      identityStep = 'idle';
      backupVisible = 20;
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
  //
  // It is also the formation editor's completion signal, and this is the
  // only registration of it. WM.handle assigns window[name] outright, so a
  // second WM.handle('onEveSettingsDone') in formations.js would replace
  // this one and leave copy, backup and restore stuck busy for the rest of
  // the session, with nothing in the console to say so. The push is
  // forwarded instead; formations.js exposes WM.formationsDone and ignores
  // anything that arrives while its route is not showing.
  WM.handle('onEveSettingsDone', function (payload) {
    if (WM.formationsDone) WM.formationsDone(payload);
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
