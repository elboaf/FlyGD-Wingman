/* FlyGD Wingman — bridge client and page shell.
 *
 * One rule carries over from app.py's _ui() chokepoint: Python pushes
 * semantic events, never widget calls. Python reaches the page only by
 * calling window.<handler>(payload); the page reaches Python only through
 * WM.send(), which wraps pywebview.api.
 *
 * Selection, sort order, and row focus are CLIENT state and never cross
 * the bridge — the sole exception is the `preselected` flag arriving on
 * onRows, because the watcher preselects newly-finished recordings so the
 * common case needs no clicking.
 */
(function () {
  'use strict';

  var WM = window.WM = {};

  // ---- bridge -------------------------------------------------------
  // pywebview injects window.pywebview.api asynchronously and fires
  // `pywebviewready` when it is usable. Every send() awaits that, so a
  // click landing during startup queues instead of throwing.
  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) { resolve(); return; }
    window.addEventListener('pywebviewready', function () { resolve(); },
                            { once: true });
  });

  WM.send = function (method) {
    var args = Array.prototype.slice.call(arguments, 1);
    return ready.then(function () {
      var api = window.pywebview && window.pywebview.api;
      var fn = api && api[method];
      if (typeof fn !== 'function') {
        console.error('bridge: no such method: ' + method);
        return null;
      }
      return fn.apply(api, args);
    }).catch(function (err) {
      // A bridge failure must never take the page down: the window would
      // stay up with a dead UI and no diagnostic.
      console.error('bridge: ' + method + ' failed', err);
      return null;
    });
  };

  // Handlers are registered here rather than assigned to window directly,
  // so a typo'd name is caught at registration and every Python push has
  // one visible owner.
  WM.HANDLERS = ['onRows', 'onDuration', 'onProgress', 'onStatus',
                 'onRetryAvailable', 'onCancelAvailable',
                 'onUploadDone', 'onLogPostRunning', 'onRowRenamed',
                 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog', 'onFirstRun',
                 'onBookmarks', 'onEveStatus', 'onPreviewHotkeys',
                 'onPreviewBindCaptured',
                 'onEveSettingsNames',
                 'onEveSettingsRunning', 'onEveSettingsDone',
                 'onSigBarState', 'onUpdateStatus',
                 'onSkills', 'onSkillsProgress'];

  WM.handle = function (name, fn) {
    if (WM.HANDLERS.indexOf(name) === -1) {
      throw new Error('unknown bridge handler: ' + name);
    }
    window[name] = function (payload) {
      try {
        fn(payload || {});
      } catch (err) {
        console.error(name + ' handler failed', err, payload);
      }
    };
  };

  // Every handler exists from load, so a push arriving before its module
  // registers is logged rather than becoming "is not a function" in the
  // WebView2 console where nobody is looking.
  WM.HANDLERS.forEach(function (name) {
    window[name] = function (payload) {
      console.warn('bridge: ' + name + ' arrived before a handler was '
                   + 'registered', payload);
    };
  });

  // ---- dom helpers --------------------------------------------------
  WM.el = function (id) { return document.getElementById(id); };

  WM.make = function (tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  // ---- enabled state --------------------------------------------------
  // THE way a control is made inert. There is no styling half to this: the
  // disabled treatment already exists and works (style.css, the
  // `button.btn.acc:disabled` rule -- first run's Continue renders as a
  // muted maroon through it). What three screens were missing is the
  // `disabled` ATTRIBUTE, so Upload with nothing selected, Copy to
  // selected with no targets, and Show / Remove with no webhook were
  // genuinely live in states where they cannot act, not merely dressed as
  // live.
  //
  // The rule that decides when to call this, because the screens answered
  // it three different ways: a control is disabled when the app already
  // knows the action cannot be carried out from the state it is holding --
  // nothing selected, no folder chosen, no webhook configured. It is NOT
  // for an action that might fail once attempted; that is what the status
  // strip and the dialog layer are for. A disabled control must also be
  // reachable back out of the state that disabled it, so nothing here is
  // permitted to disable the only route to its own precondition.
  //
  // Takes an element or an id so callers can pass either without wrapping
  // every site in WM.el(). A missing element is warned about rather than
  // ignored: the failure mode of a typo'd id is a button that stays live
  // in exactly the state this exists to cover, and silence there is how
  // the finding happened in the first place.
  WM.setEnabled = function (target, enabled) {
    var node = (typeof target === 'string') ? WM.el(target) : target;
    if (!node) {
      console.warn('setEnabled: no such element: ' + target);
      return null;
    }
    node.disabled = !enabled;
    return node;
  };

  // ---- routing ------------------------------------------------------
  // Settings is a route in this window, not a second OS window. Switching
  // is pure client state; Python is not told which route is showing.

  // Routes that show no title-bar chrome: no destination buttons, no
  // gear. These entries are here because the screen must not be leavable
  // sideways -- see the block inside WM.route that reads this list.
  WM.CHROMELESS_ROUTES = ['firstrun', 'formations', 'accountidentity'];

  WM.route = function (name) {
    // Bookmarks and Previews are NOT here any more: both are sections of
    // the Settings route, reached through WM.section.
    // formations, accountidentity and backups have no title-bar buttons:
    // all are SUB-SCREENS of Profiles, reached from that destination.
    // The formation editor and account identification are focused workflows,
    // so they hide the bar outright; see CHROMELESS_ROUTES. Backups is ordinary
    // management and keeps the destination chrome, with Profiles lit below.
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun',
                   evesettings: 'route-evesettings',
                   skills: 'route-skills',
                   formations: 'route-formations',
                   accountidentity: 'route-accountidentity',
                   backups: 'route-backups' };
    Object.keys(routes).forEach(function (key) {
      WM.el(routes[key]).classList.toggle('active', key === name);
    });
    // Standing in any Profiles sub-screen lights PROFILES, because that is where you
    // are: a sub-screen with no button of its own would otherwise darken
    // the whole bar and read as having left the destination entirely.
    // This mapping is the answer to "where am I", not merely "what button was
    // clicked". It keeps Profiles visibly selected on Backups and preserves
    // the correct state behind the hidden bar on the two focused workflows.
    var lit = (name === 'formations' || name === 'accountidentity'
      || name === 'backups') ? 'evesettings' : name;
    Array.prototype.forEach.call(
      document.querySelectorAll('.navbtn'), function (btn) {
        btn.classList.toggle('active', btn.dataset.route === lit);
      });
    WM.el('btn-settings').classList.toggle('active', name === 'settings');
    // Three routes offer no chrome. First run is not dismissable: there is
    // nowhere else to go yet. Account identity is a focused setup flow whose
    // Back control cancels its ephemeral observation. The formation editor
    // holds unsaved edits and `< Profiles` is the only exit that asks before
    // discarding them. The nav and gear call WM.route straight through and
    // know nothing about the editor's dirty flag, so leaving them up gave the
    // editor five exits of which four threw edits away in silence. Visibility
    // is decided HERE, per route, rather than by each editor toggling it on
    // entry and exit: apply_eve_gate below can route away without using Back.
    var chromeless = WM.CHROMELESS_ROUTES.indexOf(name) !== -1;
    WM.el('btn-settings').hidden = chromeless;
    WM.el('routenav').hidden = chromeless;
    // The gear returns to wherever you were: Settings is a window-level
    // action layered on top of a peer destination, not a peer itself.
    if (name === 'main' || name === 'evesettings' || name === 'skills') {
      // Peer destinations, unlike Settings: the gear returns to whichever
      // of these you came from.
      WM.last_destination = name;
    }
    WM.current_route = name;
    document.dispatchEvent(new CustomEvent('wm:route', { detail: name }));
    // Sections live inside the Settings route, so entering or leaving that
    // route is also entering or leaving whichever section is showing. A
    // module folded into Settings would otherwise never learn it had been
    // left -- see WM.section below for why that matters.
    WM.notify_section(name === 'settings' ? WM.current_section : '');
  };

  // ---- sections -------------------------------------------------------
  // The Settings route holds several groups and shows one at a time. This
  // is deliberately the SAME enter/leave contract WM.route provides, not a
  // simpler "which tab is open" flag.
  //
  // The reason is specific. bookmarks.js and previews.js each install a
  // document-level keydown listener while capturing a keybind, and each
  // disarms it on being LEFT -- both files carry a comment explaining that
  // stopPropagation() does not stop a sibling listener on the same node,
  // so an armed capture consumes the next keystroke typed anywhere and
  // writes it into the wrong bind, off-screen and silently persisted.
  // Once those two are sections rather than routes, switching away from
  // them is no longer a route change, and without this event an armed
  // capture would survive into Uploading or Alerts and swallow whatever is
  // typed there -- its handler preventDefault()s every key, Tab included.
  //
  // Round 5's E1 merged Account/Uploads/Folders/Discord into Uploading, so
  // the landing moved with the section that absorbed it. It is one of the
  // two sections that survive the EVE gate being switched off, which is
  // why it is a landing that always exists. Held in step with the rail's
  // `active` class and the pane's by test_page_conventions.py.
  WM.current_section = 'uploading';

  WM.notify_section = function (name) {
    document.dispatchEvent(new CustomEvent('wm:section', { detail: name }));
  };

  WM.section = function (name) {
    WM.current_section = name;
    Array.prototype.forEach.call(
      document.querySelectorAll('.settings-pane > .settings'),
      function (node) {
        node.classList.toggle('active', node.id === 'section-' + name);
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('.rail-item'), function (btn) {
        btn.classList.toggle('active', btn.dataset.section === name);
      });
    WM.notify_section(name);
  };

  Array.prototype.forEach.call(
    document.querySelectorAll('.rail-item'), function (btn) {
      btn.addEventListener('click', function () {
        WM.section(btn.dataset.section);
      });
    });

  // ---- the EVE gate ---------------------------------------------------
  // Visibility only. Nothing here starts or stops a feature; Python's
  // set_show_eve_tools refuses to turn the gate off while either is
  // running, precisely so this can never hide a live feature's off switch.
  //
  // With both destinations hidden the nav has one entry left, so it hides
  // altogether -- which is the single-screen app the README describes.
  // Profiles child routes have no navbtn to hide, so the first loop below
  // is a no-op for them. They are listed anyway for the SECOND half: with
  // the gate off, a user standing in one has to be moved off it like
  // anyone standing on a hidden destination, or the nav disappears around
  // them and there is no way back.
  WM.EVE_ROUTES = ['evesettings', 'skills', 'formations', 'accountidentity', 'backups'];
  // Alerts joined this list in round 5 (D1) when it stopped being a card
  // inside Previews and became a section. It is EVE-gated for the same
  // reason the other two are: it reads the EVE gamelogs folder and draws
  // on a preview window, so with the gate off it configures nothing that
  // can happen. This is also what takes the rail to TWO entries in that
  // mode -- five, less these three -- which is the whole of E1's argument
  // that the merge axis is the product's own independence claim.
  WM.EVE_SECTIONS = ['bookmarks', 'previews', 'alerts'];

  WM.apply_eve_gate = function (shown) {
    WM.eve_shown = shown !== false;
    WM.EVE_ROUTES.forEach(function (name) {
      var btn = document.querySelector('.navbtn[data-route="' + name + '"]');
      if (btn) { btn.hidden = !WM.eve_shown; }
    });
    WM.EVE_SECTIONS.forEach(function (name) {
      var btn = document.querySelector('.rail-item[data-section="' + name + '"]');
      if (btn) { btn.hidden = !WM.eve_shown; }
    });
    // One destination left is not a choice, so the whole bar goes. This
    // also hands its width back to the drag region.
    WM.el('routenav').classList.toggle('single', !WM.eve_shown);
    // Hiding a screen you can still reach would strand you on it, so every
    // route into one has to be cut -- not just the one you are standing on.
    //
    // last_destination is the one that bites. The toggle lives in Settings,
    // so current_route is 'settings' when it fires and the check below
    // never matches: you untick from Skills, press the gear to leave, and
    // the gear returns you to Skills -- with the nav now hidden and no way
    // out. Found by smoke test, exactly the case the first version missed.
    if (!WM.eve_shown) {
      if (WM.EVE_ROUTES.indexOf(WM.current_route) !== -1) { WM.route('main'); }
      if (WM.EVE_ROUTES.indexOf(WM.last_destination) !== -1) {
        WM.last_destination = 'main';
      }
      if (WM.EVE_SECTIONS.indexOf(WM.current_section) !== -1) {
        WM.section('general');
      }
    }
  };

  document.addEventListener('wm:settings', function (ev) {
    var cfg = (ev.detail || {}).settings || {};
    WM.apply_eve_gate(cfg.show_eve_tools !== false);
    // The version rides the settings payload rather than a push of its
    // own: get_settings is a RETURN, deliberately (api.py argues a push of
    // the whole settings dict would throw away unsaved edits in an open
    // form), so this is the one moment the page is handed app-level state
    // it did not compose. An older build that has not learned the key
    // leaves the titlebar as it was rather than printing `undefined`.
    var version = (ev.detail || {}).version;
    if (version) { WM.el('app-version').textContent = version; }
  });

  // ---- title bar ----------------------------------------------------
  // Cached reads may resolve after a newer Python push. Advancing on every
  // accepted render, including same-state progress, lets each read prove no
  // fresher badge payload arrived while it was in flight.
  var updateBadgeGeneration = 0;

  function renderUpdateBadge(payload) {
    updateBadgeGeneration += 1;
    var gear = WM.el('btn-settings');
    var available = !!payload.update_available;
    gear.classList.toggle('update-available', available);
    gear.title = available ? 'Settings — update available' : 'Settings';
    gear.setAttribute('aria-label', gear.title);
    document.dispatchEvent(new CustomEvent('wm:update-status', {detail: payload}));
  }
  WM.handle('onUpdateStatus', renderUpdateBadge);

  WM.el('btn-minimize').addEventListener('click', function () {
    WM.send('minimize');
  });
  WM.el('btn-close').addEventListener('click', function () {
    WM.send('close');
  });
  // Settings moves out of the bottom-left corner to the title bar, where a
  // window-level action belongs.
  WM.el('btn-settings').addEventListener('click', function () {
    WM.route(WM.current_route === 'settings'
             ? (WM.last_destination || 'main') : 'settings');
  });
  Array.prototype.forEach.call(
    document.querySelectorAll('.navbtn'), function (btn) {
      btn.addEventListener('click', function () {
        WM.route(btn.dataset.route);
      });
    });

  // ---- startup ------------------------------------------------------
  ready.then(function () {
    // The page asks for state; Python does not push it unprompted at boot.
    WM.send('list_rows');
    // Settings are asked for the same way, and routed through the same
    // handler a Save-time push uses, so there is one renderer. Without
    // this the Settings form opened blank on a configured install and a
    // Save from it wrote the blanks back.
    WM.send('get_settings').then(function (payload) {
      if (payload) window.onSettings(payload);
    });
    // Keep this cached read for dev mode, where Python never pushes, but do
    // not let its older snapshot repaint over an update push that won the
    // race while the bridge promise was pending.
    var badgeGenerationAtRead = updateBadgeGeneration;
    WM.send('update_status').then(function (payload) {
      if (payload && updateBadgeGeneration === badgeGenerationAtRead) {
        window.onUpdateStatus(payload);
      }
    });
  });
}());
