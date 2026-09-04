"""The Characters Settings shell, checked lexically and through app.js.

Task 7 adds only the Settings shell: a gated rail item, the inert pane
markup, the route-safe navigation helper, and the module include. The
roster's behaviour lands later, so these tests stop at the shell and at the
route/section event contract it depends on.
"""

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
APP = (WEB / "app.js").read_text(encoding="utf-8")


def _settings_route() -> str:
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
    start = body.index('<div class="route" id="route-settings">')
    end = body.index('<div class="route" id="route-evesettings">')
    return body[start:end]


def _characters_pane() -> str:
    route = _settings_route()
    match = re.search(
        r'<div class="settings[^"]*" id="section-characters">(.*?)'
        r'(?=<div class="settings[^"]*" id="section-[\w-]+">|$)',
        route,
        re.DOTALL,
    )
    assert match, "Settings has no Characters pane"
    return match.group(1)


def test_characters_shell_has_the_approved_heading_and_required_ids():
    pane = _characters_pane()
    headings = [h.strip() for h in re.findall(r"<h2>([^<]+)</h2>", pane)]
    assert headings, "Characters has no card heading"
    assert headings[0] == "EVE authorization"

    for element_id in (
        "characters-count",
        "characters-authenticate",
        "characters-activity",
        "characters-cancel",
        "characters-notice",
        "characters-filter",
        "characters-filter-clear",
        "characters-roster",
        "characters-empty",
        "characters-menu",
        "characters-menu-forget",
    ):
        assert f'id="{element_id}"' in pane, f"Characters shell is missing #{element_id}"

    live = re.search(r'<[^>]+id="characters-live"[^>]*>', pane)
    assert live, "Characters shell is missing the always-mounted live region"
    tag = live.group(0)
    assert 'role="status"' in tag
    assert "hidden" not in tag, "#characters-live must stay mounted when idle"


def test_characters_module_exists_and_listens_for_section_entry():
    path = WEB / "characters.js"
    assert path.is_file(), "wingman/web/characters.js does not exist"
    js = path.read_text(encoding="utf-8")
    assert "document.addEventListener('wm:section'" in js
    assert "ev.detail === 'characters'" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_open_settings_section_enters_characters_once_and_keeps_last_destination():
    script = textwrap.dedent(
        f"""
        const vm = require('vm');

        function ClassList(initial) {{
          this._set = new Set(initial || []);
        }}
        ClassList.prototype.toggle = function (name, force) {{
          if (force === undefined) {{
            if (this._set.has(name)) {{
              this._set.delete(name);
              return false;
            }}
            this._set.add(name);
            return true;
          }}
          if (force) this._set.add(name);
          else this._set.delete(name);
          return !!force;
        }};
        ClassList.prototype.contains = function (name) {{
          return this._set.has(name);
        }};

        function makeNode(id, classes, dataset) {{
          return {{
            id: id,
            dataset: dataset || {{}},
            hidden: false,
            disabled: false,
            textContent: '',
            title: '',
            listeners: {{}},
            classList: new ClassList(classes || []),
            addEventListener: function (type, fn) {{
              (this.listeners[type] || (this.listeners[type] = [])).push(fn);
            }},
            dispatchEvent: function (ev) {{
              (this.listeners[ev.type] || []).forEach(function (fn) {{ fn.call(this, ev); }}, this);
            }},
            setAttribute: function (name, value) {{ this[name] = value; }},
            getAttribute: function (name) {{ return this[name] == null ? null : this[name]; }}
          }};
        }}

        const nodes = {{}};
        function add(id, classes, dataset) {{
          const node = makeNode(id, classes, dataset);
          nodes[id] = node;
          return node;
        }}

        const routeNames = ['main', 'settings', 'firstrun', 'evesettings', 'skills',
                            'fittings', 'formations', 'accountidentity', 'backups'];
        routeNames.forEach(function (name) {{
          add('route-' + name, name === 'main' ? ['route', 'active'] : ['route']);
        }});

        const navButtons = [
          add('nav-main', ['navbtn', 'active'], {{ route: 'main' }}),
          add('nav-evesettings', ['navbtn'], {{ route: 'evesettings' }}),
          add('nav-skills', ['navbtn'], {{ route: 'skills' }}),
          add('nav-fittings', ['navbtn'], {{ route: 'fittings' }}),
        ];
        const railButtons = [
          add('rail-uploading', ['rail-item', 'active'], {{ section: 'uploading' }}),
          add('rail-characters', ['rail-item'], {{ section: 'characters' }}),
          add('rail-bookmarks', ['rail-item'], {{ section: 'bookmarks' }}),
          add('rail-previews', ['rail-item'], {{ section: 'previews' }}),
          add('rail-alerts', ['rail-item'], {{ section: 'alerts' }}),
          add('rail-general', ['rail-item'], {{ section: 'general' }}),
        ];
        const sectionNames = ['uploading', 'characters', 'bookmarks', 'previews', 'alerts', 'general'];
        const panes = sectionNames.map(function (name) {{
          return add('section-' + name, name === 'uploading' ? ['settings', 'active'] : ['settings']);
        }});

        add('btn-settings', ['winbtn', 'gear']);
        add('btn-minimize', ['winbtn']);
        add('btn-close', ['winbtn', 'close']);
        add('routenav', ['routenav']);
        add('app-version', ['version']);

        const documentListeners = {{}};
        const document = {{
          getElementById: function (id) {{ return nodes[id] || null; }},
          querySelectorAll: function (selector) {{
            if (selector === '.navbtn') return navButtons;
            if (selector === '.rail-item') return railButtons;
            if (selector === '.settings-pane > .settings') return panes;
            return [];
          }},
          querySelector: function (selector) {{
            let match = selector.match(/^\\.navbtn\\[data-route="([^"]+)"\\]$/);
            if (match) return navButtons.find(function (btn) {{ return btn.dataset.route === match[1]; }}) || null;
            match = selector.match(/^\\.rail-item\\[data-section="([^"]+)"\\]$/);
            if (match) return railButtons.find(function (btn) {{ return btn.dataset.section === match[1]; }}) || null;
            return null;
          }},
          addEventListener: function (type, fn) {{
            (documentListeners[type] || (documentListeners[type] = [])).push(fn);
          }},
          dispatchEvent: function (ev) {{
            (documentListeners[ev.type] || []).forEach(function (fn) {{ fn(ev); }});
          }}
        }};

        const windowListeners = {{}};
        const window = {{
          document: document,
          addEventListener: function (type, fn) {{
            (windowListeners[type] || (windowListeners[type] = [])).push(fn);
          }},
          dispatchEvent: function (ev) {{
            (windowListeners[ev.type] || []).forEach(function (fn) {{ fn(ev); }});
          }}
        }};

        function CustomEvent(type, init) {{
          this.type = type;
          this.detail = init && init.detail;
        }}

        global.window = window;
        global.document = document;
        global.CustomEvent = CustomEvent;
        global.console = console;

        vm.runInThisContext({json.dumps(APP)}, {{ filename: 'app.js' }});

        const sectionEvents = [];
        document.addEventListener('wm:section', function (ev) {{
          sectionEvents.push(ev.detail);
        }});

        window.WM.route('skills');
        sectionEvents.length = 0;
        window.WM.openSettingsSection('characters');

        console.log(JSON.stringify({{
          currentRoute: window.WM.current_route,
          currentSection: window.WM.current_section,
          lastDestination: window.WM.last_destination,
          sectionEvents: sectionEvents,
          charactersRailActive: nodes['rail-characters'].classList.contains('active'),
          charactersPaneActive: nodes['section-characters'].classList.contains('active'),
          settingsGearActive: nodes['btn-settings'].classList.contains('active')
        }}));
        """
    )

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        path = pathlib.Path(fh.name)
    try:
        proc = subprocess.run(
            ["node", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)

    assert proc.returncode == 0, proc.stderr or proc.stdout
    result = json.loads(proc.stdout)
    assert result == {
        "currentRoute": "settings",
        "currentSection": "characters",
        "lastDestination": "skills",
        "sectionEvents": ["characters"],
        "charactersRailActive": True,
        "charactersPaneActive": True,
        "settingsGearActive": True,
    }
