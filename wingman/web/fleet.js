// Fleet Settings and the global status-strip display toggle share this owner.
// Boot hydration is independent of Settings section entry.
(function () {
  var button = WM.el('btn-fleetbar');
  var check = WM.el('fleetbar-enabled');
  var reset = WM.el('fleetbar-reset');
  var status = WM.el('fleetbar-enabled-status');
  var characterHost = WM.el('fleetbar-character-list');
  var empty = WM.el('fleetbar-characters-empty');
  var characterStatus = WM.el('fleetbar-characters-status');
  var lastGood = false;
  var lastState = null;
  var lastRevision = -1;
  var hydrated = false;
  var hydrationInFlight = false;
  var hydrationFailure = false;
  var pending = Object.create(null);
  var defaultStatus = status ? status.textContent : '';

  if (button) { button.disabled = true; }
  if (check) { check.disabled = true; }
  if (reset) { reset.disabled = true; }

  function setStatusMessage(text) {
    if (!status) return;
    text = text || '';
    if (status.textContent !== text) { status.textContent = text; }
  }

  function fieldResult(result) {
    if (result && result.state) render(result.state);
    if (result && result.applied) {
      if (result.persisted === false && result.error) {
        setStatusMessage(result.error);
      } else {
        setStatusMessage(defaultStatus);
      }
      return true;
    }
    setStatusMessage(result && result.error);
    return false;
  }

  function accept(section) {
    var revision = Number(section && section.revision);
    if (!isFinite(revision) || revision < lastRevision) return false;
    lastRevision = revision;
    hydrated = true;
    return true;
  }

  function findCharacterRow(name) {
    var rows, index;
    if (!characterHost) return null;
    rows = characterHost.querySelectorAll('[data-fleet-character]');
    for (index = 0; index < rows.length; index += 1) {
      if (rows[index].getAttribute('data-fleet-character') === name) return rows[index];
    }
    return null;
  }

  function findCharacterInput(name) {
    var row = findCharacterRow(name);
    return row ? row.querySelector('input[type="checkbox"]') : null;
  }

  function commitMessage(result) {
    if (!characterStatus) return;
    if (result && result.applied) {
      characterStatus.textContent = '';
      characterStatus.hidden = true;
      return;
    }
    characterStatus.textContent = (result && result.error)
      || 'Could not change Fleet character visibility.';
    characterStatus.hidden = false;
  }

  function finishCharacterMutation(name, token, result, restoreFocus) {
    var current, remembered;
    // A later request owns the row now. It alone may re-enable or refocus it.
    if (pending[name] !== token) return;
    delete pending[name];
    if (result && result.state) render(result.state);
    else if (lastState) render(lastState);
    current = findCharacterInput(name);
    if (current) current.disabled = false;
    if ((!result || result.applied === false) && current) {
      // A bridge failure has no authoritative response, so restore the last
      // accepted value instead of leaving the user's rejected click painted.
      remembered = (lastState && lastState.characters || []).filter(function (row) {
        return row.name === name;
      })[0];
      if (remembered) current.checked = !!remembered.visible;
    }
    if (restoreFocus && document.activeElement === document.body && current) {
      current.focus();
    }
    commitMessage(result);
  }

  function changeCharacter(input, name) {
    var token, restoreFocus;
    if (!hydrated) return;
    token = (pending[name] || 0) + 1;
    pending[name] = token;
    restoreFocus = document.activeElement === input;
    input.disabled = true;
    WM.send('set_fleet_bar_character_visible', name, input.checked).then(function (res) {
      finishCharacterMutation(name, token, res, restoreFocus);
    }, function () {
      finishCharacterMutation(name, token, {
        applied: false,
        error: 'Could not change Fleet character visibility.'
      }, restoreFocus);
    });
  }

  function makeCharacterRow() {
    var row = WM.make('div', 'fleet-character-row');
    var label = WM.make('label', 'check');
    var input = WM.make('input');
    var box, name;
    input.type = 'checkbox';
    box = WM.make('span', 'box');
    name = WM.make('span', 'fleet-character-name');
    label.appendChild(input);
    label.appendChild(box);
    label.appendChild(name);
    row.appendChild(label);
    input.addEventListener('change', function () {
      changeCharacter(input, row.getAttribute('data-fleet-character'));
    });
    return row;
  }

  function renderCharacters(characters) {
    var groups, rows, groupName, group, row, input, position = 0;
    if (!characterHost) return;
    characters = Array.isArray(characters) ? characters : [];
    if (empty) empty.hidden = characters.length !== 0;
    groups = characters.some(function (item) { return item.running === null; })
      ? [{name: 'Known characters', rows: characters}]
      : [
        {name: 'Running', rows: characters.filter(function (item) { return item.running; })},
        {name: 'Offline', rows: characters.filter(function (item) { return !item.running; })}
      ];
    rows = Object.create(null);
    Array.prototype.forEach.call(
      characterHost.querySelectorAll('[data-fleet-character]'),
      function (item) { rows[item.getAttribute('data-fleet-character')] = item; }
    );
    groups.forEach(function (definition) {
      if (!definition.rows.length) return;
      groupName = definition.name;
      group = characterHost.querySelector('[data-fleet-group="' + groupName + '"]');
      if (!group) {
        group = WM.make('div', 'fleet-character-group');
        group.setAttribute('data-fleet-group', groupName);
        group.textContent = groupName;
      }
      // Re-appending even an unchanged row blurs its checkbox. Headings share
      // the same flat list, so they must also stay put on a heartbeat.
      if (characterHost.children[position] !== group) {
        characterHost.insertBefore(group, characterHost.children[position] || null);
      }
      position += 1;
      definition.rows.forEach(function (item) {
        row = rows[item.name] || makeCharacterRow();
        delete rows[item.name];
        row.setAttribute('data-fleet-character', item.name);
        input = row.querySelector('input[type="checkbox"]');
        input.checked = !!item.visible;
        input.disabled = !!pending[item.name];
        input.setAttribute('aria-label', 'Show ' + item.name + ' in Fleet Bar');
        row.querySelector('.fleet-character-name').textContent = item.name;
        if (characterHost.children[position] !== row) {
          characterHost.insertBefore(row, characterHost.children[position] || null);
        }
        position += 1;
      });
    });
    Object.keys(rows).forEach(function (name) { rows[name].remove(); });
    Array.prototype.forEach.call(
      characterHost.querySelectorAll('[data-fleet-group]'),
      function (item) {
        if (!characterHost.querySelector('[data-fleet-character]')
            || !groups.some(function (definition) {
              return definition.name === item.getAttribute('data-fleet-group')
                && definition.rows.length;
            })) item.remove();
      }
    );
  }

  function render(section) {
    if (!accept(section)) return;
    if (hydrationFailure) {
      hydrationFailure = false;
      setStatusMessage(defaultStatus);
    }
    lastState = section;
    lastGood = !!section.enabled;
    WM.fleet_bar_on = lastGood;
    if (button) {
      button.disabled = false;
      button.classList.toggle('active', lastGood);
      button.setAttribute('aria-pressed', lastGood ? 'true' : 'false');
      button.hidden = WM.eve_shown === false && !lastGood;
    }
    if (check) {
      check.disabled = false;
      if (check !== document.activeElement) check.checked = lastGood;
    }
    if (reset) { reset.disabled = false; }
    renderCharacters(section.characters);
  }

  function failed(restoreCheck, message) {
    if (restoreCheck && check) { check.checked = lastGood; }
    setStatusMessage(message);
  }

  WM.handle('onFleetBarState', render);

  if (button) {
    button.addEventListener('click', function () {
      if (!hydrated) return;
      WM.send('toggle_fleet_bar', !lastGood).then(function (res) {
        if (!fieldResult(res)) {
          if (!res || !res.error) { failed(true, 'Could not change the Fleet Bar.'); }
          else if (check) { check.checked = lastGood; }
        }
      }, function () {
        failed(true, 'Could not change the Fleet Bar.');
      });
    });
  }
  if (check) {
    check.addEventListener('change', function () {
      if (!hydrated) return;
      WM.send('toggle_fleet_bar', check.checked).then(function (res) {
        if (!fieldResult(res)) {
          if (!res || !res.error) { failed(true, 'Could not change the Fleet Bar.'); }
          else { check.checked = lastGood; }
        }
      }, function () {
        failed(true, 'Could not change the Fleet Bar.');
      });
    });
  }
  if (reset) {
    reset.addEventListener('click', function () {
      if (!hydrated) return;
      WM.send('reset_fleet_bar_width').then(function (res) {
        if (!fieldResult(res) && (!res || !res.error)) {
          failed(false, 'Could not reset Fleet Bar width.');
        }
      }, function () {
        failed(false, 'Could not reset Fleet Bar width.');
      });
    });
  }

  function hydrate() {
    if (hydrated || hydrationInFlight) return;
    hydrationInFlight = true;
    WM.send('fleet_bar_settings').then(function (section) {
      hydrationInFlight = false;
      if (section) render(section);
      else if (!hydrated) {
        // A push may already have recovered the controls while this read waited.
        hydrationFailure = true;
        setStatusMessage('Could not read Fleet Bar settings. Reopen Fleet telemetry to retry.');
      }
    });
  }

  document.addEventListener('wm:section', function (event) {
    if (event.detail === 'fleet') hydrate();
  });
  hydrate();
}());
