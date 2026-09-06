/* Shared EVE character management inside Settings.
 *
 * The bridge event is only a semantic "something changed" signal; every
 * production render still comes from a fresh read of eve_characters_state().
 * The screenshot tool's bounded onEveAuthorityScreenshotState hook is the one
 * deliberate exception: it stages a deterministic read-only fixture in the
 * live page without calling a real sign-in, cancel, or forget writer. A stale
 * read must not repaint over a newer one, and a hidden section must not do
 * work the user cannot see.
 */
(function () {
  'use strict';

  var WM = window.WM;
  var section = WM && WM.el && WM.el('section-characters');
  if (!section) { return; }

  var count = WM.el('characters-count');
  var authenticate = WM.el('characters-authenticate');
  var activity = WM.el('characters-activity');
  var cancel = WM.el('characters-cancel');
  var notice = WM.el('characters-notice');
  var live = WM.el('characters-live');
  var roster = WM.el('characters-roster');
  var empty = WM.el('characters-empty');
  var filter = WM.el('characters-filter');
  var filterClear = WM.el('characters-filter-clear');
  var menu = WM.el('characters-menu');
  var forget = WM.el('characters-menu-forget');
  if (!count || !authenticate || !activity || !cancel || !notice || !live
      || !roster || !empty || !filter || !filterClear || !menu || !forget) {
    return;
  }

  var active = false;
  var requestSequence = 0;
  var filterText = '';
  var state = emptyState();
  var authRequestPending = false;
  var localNotice = '';
  var localNoticeKind = '';
  var readErrorNotice = '';
  var menuCharacterId = 0;
  var menuCharacterName = '';
  var menuTrigger = null;

  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', 'Character actions');
  menu.hidden = true;
  forget.setAttribute('role', 'menuitem');
  forget.className = 'danger';
  forget.disabled = true;

  function emptyState() {
    return {
      available: false,
      auth_configured: false,
      authorization_activity: 'idle',
      authorization_notice: '',
      warnings: [],
      characters: []
    };
  }

  function asText(value) {
    return value == null ? '' : String(value);
  }

  function normalizeRow(row) {
    row = row || {};
    return {
      character_id: row.character_id,
      character_name: asText(row.character_name),
      authenticated_utc: asText(row.authenticated_utc),
      skills: row.skills === 'authorized' ? 'authorized' : 'sign_in',
      fittings: row.fittings === 'authorized' ? 'authorized' : 'sign_in',
      needs_reauth: !!row.needs_reauth,
      persistence_error: asText(row.persistence_error)
    };
  }

  function normalizeState(payload) {
    var raw = payload || {};
    var warnings = Array.isArray(raw.warnings)
      ? raw.warnings.slice(0, 20).map(asText)
      : [];
    var characters = Array.isArray(raw.characters)
      ? raw.characters.map(normalizeRow)
      : [];
    return {
      available: raw.available !== false,
      auth_configured: !!raw.auth_configured,
      authorization_activity: raw.authorization_activity === 'waiting'
        ? 'waiting' : 'idle',
      authorization_notice: asText(raw.authorization_notice),
      warnings: warnings,
      characters: characters
    };
  }

  function isVisible() {
    return active && WM.current_route === 'settings'
      && WM.current_section === 'characters'
      && section.classList.contains('active');
  }

  function statusLabel(value, needsReauth) {
    if (value === 'authorized') return 'Authorized';
    if (needsReauth) return 'Access expired';
    return 'Access needed';
  }

  function formatAuthenticated(iso) {
    var match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(asText(iso));
    if (!match) return '';
    return match[1] + '-' + match[2] + '-' + match[3] + ' ' + match[4]
      + ':' + match[5] + ' UTC';
  }

  function countLabel(total, shown) {
    if (!filterText.trim()) {
      return total + (total === 1 ? ' character' : ' characters');
    }
    return shown + ' of ' + total + ' characters';
  }

  function rosterLabel(total, shown) {
    if (!filterText.trim()) return 'Character roster';
    return shown + ' of ' + total + ' characters matching ' + filterText.trim();
  }

  function rowFilterText(row) {
    return [
      asText(row.character_name),
      statusLabel(row.skills, row.needs_reauth),
      statusLabel(row.fittings, row.needs_reauth),
      formatAuthenticated(row.authenticated_utc)
    ].join(' ').toLowerCase();
  }

  function matchingCharacters(characters) {
    var needle = filterText.trim().toLowerCase();
    if (!needle) return characters;
    return characters.filter(function (row) {
      return rowFilterText(row).indexOf(needle) !== -1;
    });
  }

  function resetNotice() {
    localNotice = '';
    localNoticeKind = '';
  }

  function showNotice(text, kind) {
    localNotice = asText(text);
    localNoticeKind = kind || '';
    renderNotice();
  }

  function showReadError(text) {
    readErrorNotice = asText(text).slice(0, 500);
    authRequestPending = false;
    closeMenu(false);
    renderButtons();
    renderActivity();
    renderNotice();
  }

  function announce(text) {
    live.textContent = asText(text);
  }

  function renderNotice() {
    var primary = localNotice || state.authorization_notice;
    var warnings = state.available && state.warnings ? state.warnings : [];
    var parts = [];
    if (primary) parts.push(primary);
    if (readErrorNotice) parts.push(readErrorNotice);
    warnings.forEach(function (warning) {
      if (warning) parts.push(warning);
    });
    var kind = readErrorNotice ? 'err'
      : (localNotice ? localNoticeKind : (primary ? '' : (parts.length ? 'warn' : '')));
    notice.className = 'field-msg' + (kind ? ' ' + kind : '');
    notice.textContent = parts.join('\n');
    notice.hidden = !parts.length;
  }

  function renderActivity() {
    if (state.authorization_activity === 'waiting') {
      activity.textContent = 'Waiting for EVE SSO…';
      return;
    }
    if (!state.characters.length) {
      activity.textContent = 'Use EVE sign-in to add your first character.';
      return;
    }
    activity.textContent = 'Use EVE sign-in to add a character or update access for Skills and Fittings.';
  }

  function renderButtons() {
    authenticate.textContent = 'Authenticate character…';
    authenticate.title = state.auth_configured
      ? '' : 'This build has no EVE application id configured.';
    authenticate.disabled = !state.auth_configured
      || state.authorization_activity === 'waiting'
      || authRequestPending;

    cancel.textContent = 'Cancel';
    cancel.hidden = state.authorization_activity !== 'waiting';
    cancel.disabled = state.authorization_activity !== 'waiting'
      || authRequestPending;

    filter.disabled = !state.available || !state.characters.length;
    filterClear.disabled = !filterText.trim();
    filterClear.hidden = !filterText.trim();
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderEmpty(message) {
    clearNode(empty);
    empty.hidden = !message;
    if (!message) return;
    var cell = WM.make('span', '', asText(message));
    cell.setAttribute('role', 'cell');
    empty.appendChild(cell);
    clearNode(roster);
    roster.appendChild(empty);
  }

  function menuItems() {
    return Array.prototype.filter.call(
      menu.querySelectorAll('[role="menuitem"]'),
      function (item) { return !item.disabled && !item.hidden; }
    );
  }

  function focusMenuItem(last) {
    var items = menuItems();
    if (!items.length) return;
    items[last ? items.length - 1 : 0].focus();
  }

  function closeMenu(restoreFocus) {
    var trigger = menuTrigger;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    menu.hidden = true;
    menuCharacterId = 0;
    menuCharacterName = '';
    forget.disabled = true;
    menu.setAttribute('aria-label', 'Character actions');
    menuTrigger = null;
    if (restoreFocus && trigger && !trigger.disabled && trigger.focus) {
      trigger.focus();
    }
  }

  function openMenu(trigger, row, focusLast) {
    var rect = trigger.getBoundingClientRect();
    menuCharacterId = row.character_id;
    menuCharacterName = row.character_name || 'this character';
    menu.setAttribute('aria-label', 'Actions for ' + menuCharacterName);
    menuTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    forget.textContent = 'Forget character';
    forget.setAttribute('aria-label', 'Forget ' + menuCharacterName);
    forget.disabled = false;
    menu.hidden = false;
    menu.style.left = '0px';
    menu.style.top = '0px';
    var menuRect = menu.getBoundingClientRect();
    var left = Math.max(6, Math.min(rect.left,
                                    window.innerWidth - menuRect.width - 6));
    var top = rect.bottom + 4;
    if (window.innerHeight - rect.bottom < menuRect.height + 4) {
      top = rect.top - menuRect.height - 4;
    }
    top = Math.max(6, Math.min(top, window.innerHeight - menuRect.height - 6));
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
    focusMenuItem(!!focusLast);
  }

  function makeHeader() {
    var head = WM.make('div', 'characters-head');
    head.setAttribute('role', 'row');
    ['Character', 'Skills', 'Fittings', 'Authenticated', 'Actions']
      .forEach(function (label) {
        var cell = WM.make('span', '', label);
        cell.setAttribute('role', 'columnheader');
        head.appendChild(cell);
      });
    return head;
  }

  function makeStatusCell(value, needsReauth) {
    var stateClass = value === 'authorized' ? 'authorized'
      : (needsReauth ? 'access-expired' : 'access-needed');
    var cell = WM.make('span', 'characters-status ' + stateClass,
                       statusLabel(value, needsReauth));
    cell.setAttribute('role', 'cell');
    return cell;
  }

  function startAuthenticationError(result) {
    return (result && result.error) || 'Could not start EVE sign-in.';
  }

  function cancelAuthenticationError(result) {
    return (result && result.error) || 'Could not cancel EVE sign-in.';
  }

  function forgetError(result) {
    return (result && result.error) || 'Could not forget this character.';
  }

  function makeRow(row) {
    var node = WM.make('div', 'characters-row');
    node.setAttribute('role', 'row');

    var name = WM.make('div', 'characters-name');
    name.setAttribute('role', 'cell');
    var nameText = WM.make('span', 'characters-name-text',
                           row.character_name || String(row.character_id));
    var authenticated = formatAuthenticated(row.authenticated_utc);
    name.appendChild(nameText);
    if (row.persistence_error) {
      name.appendChild(WM.make('span', 'characters-name-note', row.persistence_error));
    }
    node.appendChild(name);
    node.appendChild(makeStatusCell(row.skills, row.needs_reauth));
    node.appendChild(makeStatusCell(row.fittings, row.needs_reauth));
    var authenticatedCell = WM.make('span', 'characters-authenticated',
                                    authenticated ? authenticated : '');
    authenticatedCell.setAttribute('role', 'cell');
    node.appendChild(authenticatedCell);

    var actions = WM.make('div', 'characters-actions');
    actions.setAttribute('role', 'cell');
    var more = WM.make('button', 'linkbtn characters-menu-trigger', '⋯');
    more.type = 'button';
    more.title = 'More actions';
    more.setAttribute('aria-haspopup', 'menu');
    more.setAttribute('aria-controls', 'characters-menu');
    more.setAttribute('aria-expanded', 'false');
    more.setAttribute('aria-label', 'More actions for '
                      + (row.character_name || 'this character'));
    more.addEventListener('click', function (event) {
      event.preventDefault();
      if (menuTrigger === more && !menu.hidden) {
        closeMenu(false);
        return;
      }
      openMenu(more, row, false);
    });
    more.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openMenu(more, row, false);
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        openMenu(more, row, true);
      }
    });
    actions.appendChild(more);

    node.appendChild(actions);
    return node;
  }

  function renderRoster() {
    var characters = state.characters;
    var rows = matchingCharacters(characters);
    clearNode(roster);
    roster.setAttribute('aria-label', rosterLabel(characters.length, rows.length));
    count.textContent = countLabel(characters.length, rows.length);

    if (!state.available) {
      renderEmpty((state.warnings && state.warnings[0])
        || 'The shared EVE character authority is unavailable.');
      return;
    }
    if (!characters.length) {
      renderEmpty('No characters yet.');
      return;
    }
    if (!rows.length) {
      renderEmpty('No characters match “' + filterText.trim() + '”.');
      return;
    }

    empty.textContent = '';
    empty.hidden = true;
    roster.appendChild(makeHeader());
    rows.forEach(function (row) { roster.appendChild(makeRow(row)); });
  }

  function render(payload) {
    authRequestPending = false;
    readErrorNotice = '';
    closeMenu(false);
    state = normalizeState(payload);
    renderButtons();
    renderActivity();
    renderNotice();
    renderRoster();
  }

  function requestState() {
    requestSequence += 1;
    var wanted = requestSequence;
    WM.send('eve_characters_state').then(function (payload) {
      if (wanted !== requestSequence || !isVisible()) return;
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        showReadError('Could not refresh the authorized characters. Keeping the previous roster.');
        return;
      }
      render(payload);
    });
  }

  window.onEveAuthorityScreenshotState = function (payload) {
    if (!isVisible()) return;
    requestSequence += 1;
    authRequestPending = false;
    resetNotice();
    announce('');
    render(payload);
  };

  function forgetCurrentCharacter() {
    if (forget.disabled || !menuCharacterId) return;
    var characterId = menuCharacterId;
    var characterName = menuCharacterName || 'This character';
    closeMenu(true);
    WM.confirm('Forget character',
      characterName + ' is removed from Skills and Fittings, and you will '
      + 'have to authenticate it again to add it back.',
      { destructive: true })
      .then(function (ok) {
        if (!ok) return;
        announce('');
        resetNotice();
        renderNotice();
        WM.send('eve_characters_forget', characterId).then(function (result) {
          if (!result || !result.applied) {
            showNotice(forgetError(result), 'err');
            return;
          }
          if (!result.persisted) {
            showNotice((result && result.error)
              || 'This character was removed, but some cleanup was not saved.',
              'warn');
            announce(characterName + ' was removed.');
            requestState();
            return;
          }
          announce(characterName + ' was removed.');
          requestState();
        });
      });
  }

  function enterSection() {
    active = true;
    filterText = filter.value;
    closeMenu(false);
  }

  function leaveSection() {
    if (!active) return;
    active = false;
    closeMenu(false);
    announce('');
  }

  filter.addEventListener('input', function () {
    filterText = filter.value;
    renderButtons();
    renderRoster();
  });

  filterClear.addEventListener('click', function () {
    filter.value = '';
    filterText = '';
    renderButtons();
    renderRoster();
    filter.focus();
  });

  authenticate.addEventListener('click', function () {
    announce('');
    resetNotice();
    renderNotice();
    authRequestPending = true;
    renderButtons();
    WM.send('eve_characters_authenticate').then(function (result) {
      if (!result || !result.accepted) {
        authRequestPending = false;
        renderButtons();
        showNotice(startAuthenticationError(result), 'err');
      }
    });
  });

  cancel.addEventListener('click', function () {
    announce('');
    resetNotice();
    renderNotice();
    authRequestPending = true;
    renderButtons();
    WM.send('eve_characters_cancel_auth').then(function (result) {
      if (!result || !result.accepted) {
        authRequestPending = false;
        renderButtons();
        showNotice(cancelAuthenticationError(result), 'err');
      }
    });
  });

  forget.addEventListener('click', forgetCurrentCharacter);

  menu.addEventListener('keydown', function (event) {
    var items = menuItems();
    var current = document.activeElement;
    var index = items.indexOf(current);
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    if (!items.length) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[index < 0 || index === items.length - 1 ? 0 : index + 1].focus();
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[index <= 0 ? items.length - 1 : index - 1].focus();
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      items[0].focus();
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      items[items.length - 1].focus();
      return;
    }
    if ((event.key === 'Enter' || event.key === ' ') && current && current.click) {
      event.preventDefault();
      current.click();
    }
  });

  document.addEventListener('mousedown', function (event) {
    if (menu.hidden) return;
    if (menu.contains(event.target)) return;
    if (menuTrigger && menuTrigger.contains(event.target)) return;
    closeMenu(false);
  });
  window.addEventListener('blur', function () { closeMenu(false); });

  document.addEventListener('wm:eve-authority', function () {
    if (!isVisible()) return;
    requestState();
  });

  document.addEventListener('wm:section', function (ev) {
    if (ev.detail === 'characters') {
      enterSection();
      requestState();
      return;
    }
    leaveSection();
  });
})();
