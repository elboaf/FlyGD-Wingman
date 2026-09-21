// Focused DOM/bridge boundary for production Profiles painters and listeners.
// No CSS rendering or browser-native keyboard claims: tests deliver toggle and
// focus events explicitly and supply measured rectangles at the DOM boundary.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '..', 'wingman', 'web');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const markup = new Map(Array.from(html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g),
  match => [match[2], match[1]]));
const elements = {};
const handlers = {};
const calls = [];
function eventTarget(node) {
  node.listeners = {};
  node.addEventListener = function (name, callback) {
    (this.listeners[name] || (this.listeners[name] = [])).push(callback);
  };
  node.fire = function (name, fields = {}) {
    const event = fields.preventDefault ? fields : {target: this, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...fields};
    (this.listeners[name] || []).forEach(callback => callback(event));
    if (this.parentNode && ['keydown', 'focusout'].includes(name)) {
      this.parentNode.fire(name, event);
    }
    return event;
  };
  return node;
}
function element(tag) {
  const node = eventTarget({tagName: tag.toUpperCase(), children: [],
    value: '', hidden: false, disabled: false, checked: false, open: false,
    className: '', attrs: {}, style: {}, scrollTop: 0, _text: '',
    rect: {left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0},
    set textContent(value) { this._text = value; this.children = []; },
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); },
    set innerHTML(value) { assert.equal(value, ''); this.children = []; this.value = ''; },
    appendChild(child) {
      child.parentNode = this; this.children.push(child);
      if (this.tagName === 'SELECT' && (this.children.length === 1 || child.selected)) {
        this.value = child.value;
      }
      return child;
    },
    prepend(child) { child.parentNode = this; this.children.unshift(child); },
    setAttribute(name, value) { this.attrs[name] = value; },
    getAttribute(name) { return this.attrs[name] ?? null; },
    contains(other) { return this === other || this.children.some(child => child.contains(other)); },
    querySelectorAll(selector) {
      const descendants = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
      return descendants.filter(child => selector === '*' ||
        (selector === '.bk-menu[open]' ? child.classList.contains('bk-menu') && child.open :
          selector.startsWith('.') ? child.classList.contains(selector.slice(1)) :
            child.tagName.toLowerCase() === selector));
    },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    getBoundingClientRect() { return this.rect; },
    focus(options) { document.activeElement = this; this.focusOptions = options; },
    click() { if (!this.disabled) this.fire('click'); }
  });
  node.classList = {
    contains(name) { return node.className.split(/\s+/).includes(name); },
    add(name) { if (!this.contains(name)) node.className += ' ' + name; },
    remove(name) { node.className = node.className.split(/\s+/).filter(cls => cls !== name).join(' '); },
    toggle(name, force) {
      const add = force === undefined ? !this.contains(name) : force;
      if (add) this.add(name); else this.remove(name);
      return add;
    }
  };
  return node;
}
function el(id) {
  assert.ok(markup.has(id), 'Missing production markup: ' + id);
  return elements[id] || (elements[id] = element(markup.get(id)));
}
const radios = ['characters', 'accounts'].map(value => {
  const radio = element('input'); radio.value = value; radio.checked = value === 'characters';
  return radio;
});
const document = eventTarget({readyState: 'loading', activeElement: null,
  createElement: element,
  querySelector(selector) {
    return selector === 'input[name="es-kind"]:checked' ? radios.find(radio => radio.checked) : null;
  },
  querySelectorAll(selector) { return selector === 'input[name="es-kind"]' ? radios : []; }
});
const window = eventTarget({innerHeight: 625, innerWidth: 840});
const WM = {
  el, current_route: 'evesettings', handle(name, callback) { handlers[name] = callback; },
  make(tag, cls, text) {
    const node = element(tag); node.className = cls; node.textContent = text || ''; return node;
  },
  setEnabled(id, enabled) { el(id).disabled = !enabled; },
  send(...args) {
    calls.push(args);
    if (args[0] === 'eve_settings_state') return Promise.resolve(initial);
    assert.ok(['eve_settings_copy', 'eve_settings_restore', 'eve_settings_delete_backup'].includes(args[0]),
      'Unexpected bridge operation: ' + args[0]);
    return Promise.resolve(true);
  }
};
const initial = {
  root: '/eve', profile: '/eve/profile', server: '/eve/server',
  profiles: [{path: '/eve/profile', name: 'Fleet profile with a long exact name'}],
  servers: [{path: '/eve/server', name: 'Tranquility'}],
  characters: [
    {path: '/char/source', name: 'Source', display_name: 'Source pilot'},
    {path: '/char/alpha', name: 'Alpha', display_name: 'Alpha pilot'},
    {path: '/char/beta', name: 'Beta', display_name: 'Beta pilot'},
    {path: '/char/other', name: 'Other', display_name: 'Other pilot'}
  ],
  accounts: [
    {path: '/account/source', name: 'Main account · Source pilot', display_name: 'Main account', display_meta: 'Source pilot'},
    {path: '/account/alt', name: 'Alt account · Alpha pilot', display_name: 'Alt account', display_meta: 'Alpha pilot'}
  ],
  copy_groups: {
    characters: [{id: 'windows', label: 'Windows', default_on: true},
      {id: 'overview', label: 'Overview', default_on: false}],
    accounts: [{id: 'windows', label: 'Account windows', default_on: false}]
  },
  selective_copy_available: true, eve_running: true, identification_active: false,
  auto_keep: 10, backups_unreadable: false,
  backups: Array.from({length: 25}, (_, index) => ({
    path: '/backups/archive-' + index + '.zip', created: '20260824-140300',
    origin: 'auto', kind: 'profile', display_name: 'Fleet ' + index + ' ' + 'long identity '.repeat(8),
    display_meta: 'Profile settings'
  }))
};
function backupMenus() { return el('es-backups').querySelectorAll('.bk-menu'); }
function measuredMenu(menu, top, bottom) {
  menu.querySelector('summary').rect = {left: 780, right: 812, top, bottom, width: 32, height: bottom - top};
  menu.querySelector('button').rect = {left: 700, right: 812, top: bottom + 4, bottom: bottom + 36, width: 112, height: 32};
}
function nativeToggle(menu, open = true) { menu.open = open; menu.fire('toggle'); }
function chooseKind(value) {
  radios.forEach(radio => { radio.checked = radio.value === value; });
  radios.find(radio => radio.checked).fire('change');
}
const scenario = fs.readFileSync(0, 'utf8');
const source = fs.readFileSync(path.join(web, 'evesettings.js'), 'utf8');
const closure = source.match(/}\(\)\);\r?\n$/);
assert.ok(closure);
const exercise = `
  state = initial;
  wire();
  renderSource(); renderCopyGroups(); renderTargets(); renderBackups();
  paintPill(state.eve_running);
  ${scenario}
`;
vm.runInNewContext(source.slice(0, closure.index) + exercise + '\n}());\n',
  {WM, window, document, assert, el, handlers, calls, initial, backupMenus,
    measuredMenu, nativeToggle, chooseKind}, {filename: 'evesettings.js'});
