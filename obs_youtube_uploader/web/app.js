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
                 'onRetryAvailable', 'onLink', 'onSettings', 'onChannel',
                 'onAuthState', 'onDialog', 'onFirstRun'];

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

  // ---- routing ------------------------------------------------------
  // Settings is a route in this window, not a second OS window. Switching
  // is pure client state; Python is not told which route is showing.
  WM.route = function (name) {
    var routes = { main: 'route-main', settings: 'route-settings',
                   firstrun: 'route-firstrun' };
    var labels = { main: 'Uploader', settings: 'Settings',
                   firstrun: 'Setup' };
    Object.keys(routes).forEach(function (key) {
      WM.el(routes[key]).classList.toggle('active', key === name);
    });
    WM.el('route-label').textContent = labels[name] || 'Uploader';
    WM.el('btn-settings').classList.toggle('active', name === 'settings');
    // First run is not dismissable: the app cannot watch a folder it does
    // not have, so the gear is hidden rather than merely inert.
    WM.el('btn-settings').hidden = (name === 'firstrun');
    WM.current_route = name;
    document.dispatchEvent(new CustomEvent('wm:route', { detail: name }));
  };

  // ---- title bar ----------------------------------------------------
  WM.el('btn-minimize').addEventListener('click', function () {
    WM.send('minimize');
  });
  WM.el('btn-close').addEventListener('click', function () {
    WM.send('close');
  });
  // Settings moves out of the bottom-left corner to the title bar, where a
  // window-level action belongs.
  WM.el('btn-settings').addEventListener('click', function () {
    WM.route(WM.current_route === 'settings' ? 'main' : 'settings');
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
  });
}());
