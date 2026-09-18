"""The Characters Settings section, checked lexically and in a Node DOM stub.

The tests cover fresh reads on entry, stale-reply suppression, dense roster
rendering, authorization actions, one fixed menu, and the three forget outcomes.
They exercise behavior but do not render CSS; browser and WebView2 smoke checks
remain necessary for layout changes.
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
JS = (WEB / "characters.js").read_text(encoding="utf-8")
CSS = (WEB / "style.css").read_text(encoding="utf-8")


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


def test_characters_shell_splits_authorization_from_the_wide_roster():
    pane = _characters_pane()
    headings = [h.strip() for h in re.findall(r"<h2>([^<]+)</h2>", pane)]
    assert headings == ["EVE authorization", "Character access"]
    assert pane.count('<section class="card characters-') == 2
    assert 'class="card characters-auth-card"' in pane
    assert 'class="card characters-roster-card"' in pane

    auth_card, roster_card = pane.split(
        '<section class="card characters-roster-card">', 1
    )
    assert 'id="characters-authenticate"' in auth_card
    assert 'id="characters-count"' not in auth_card
    assert 'id="characters-count"' in roster_card
    assert 'id="characters-filter"' in roster_card
    assert 'id="characters-roster"' in roster_card

    assert "#section-characters { height: 100%; max-width: none; }" in CSS
    assert re.search(r"\.characters-auth-card\s*\{[^}]*max-width:\s*620px", CSS)
    assert re.search(
        r"\.characters-roster-card\s*\{[^}]*flex:\s*1[^}]*min-height:\s*0",
        CSS,
    )
    shared_grid = re.search(
        r"\.characters-head,\s*\.characters-row\s*\{([^}]*)\}", CSS, re.DOTALL
    )
    assert shared_grid
    assert "max-content" not in shared_grid.group(1)
    assert "minmax(180px, 1fr) 112px 112px 64px" in shared_grid.group(1)
    assert "gap: 12px" in shared_grid.group(1)
    assert re.search(
        r"\.characters-head > span:not\(:first-child\)\s*\{[^}]*text-align:\s*center",
        CSS,
    )
    assert re.search(r"\.characters-actions\s*\{[^}]*justify-self:\s*center", CSS)
    assert re.search(r"\.characters-status\s*\{[^}]*justify-content:\s*center", CSS)
    assert re.search(r"\.characters-head\s*\{[^}]*padding:\s*\S+ 10px", CSS)
    assert re.search(r"\.characters-row\s*\{[^}]*padding:\s*\S+ 10px", CSS)
    assert "characters-authenticated" not in CSS

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
        assert f'id="{element_id}"' in pane, (
            f"Characters shell is missing #{element_id}"
        )

    live = re.search(r'<[^>]+id="characters-live"[^>]*>', pane)
    assert live, "Characters shell is missing the always-mounted live region"
    tag = live.group(0)
    assert 'role="status"' in tag
    assert "hidden" not in tag, "#characters-live must stay mounted when idle"


def test_characters_overflow_menu_uses_only_the_fixed_menu_pattern():
    pane = _characters_pane()
    menu_markup = re.search(
        r'(<div[^>]+id="characters-menu"[^>]*>)(.*?)</div>', pane, re.DOTALL
    )
    assert menu_markup, "Characters has no overflow menu"
    menu_tag, menu_body = menu_markup.groups()
    assert 'class="ctxmenu"' in menu_tag
    assert "bk-menu" not in menu_tag
    assert "<summary" not in menu_body

    assert re.search(r"WM\.make\('button', 'btn characters-menu-trigger', '⋯'\)", JS)
    assert "more.setAttribute('aria-label', 'More actions for '" in JS


def test_characters_module_exists_and_listens_for_section_entry():
    path = WEB / "characters.js"
    assert path.is_file(), "wingman/web/characters.js does not exist"
    assert "document.addEventListener('wm:section'" in JS
    assert "ev.detail === 'characters'" in JS


def test_characters_module_guards_every_shell_node_it_now_uses():
    for element_id in (
        "section-characters",
        "characters-count",
        "characters-authenticate",
        "characters-activity",
        "characters-cancel",
        "characters-notice",
        "characters-live",
        "characters-roster",
        "characters-empty",
        "characters-filter",
        "characters-filter-clear",
        "characters-menu",
        "characters-menu-forget",
    ):
        assert f"WM.el('{element_id}')" in JS

    assert re.search(
        r"if \(!count\s*\|\|\s*!authenticate\s*\|\|\s*!activity\s*\|\|\s*!cancel\s*"
        r"\|\|\s*!notice\s*\|\|\s*!live\s*\|\|\s*!roster\s*\|\|\s*!empty\s*"
        r"\|\|\s*!filter\s*\|\|\s*!filterClear\s*\|\|\s*!menu\s*\|\|\s*!forget\)"
        r"\s*\{\s*return;\s*\}",
        JS,
        re.DOTALL,
    )


def test_characters_re_read_on_entry_and_visible_authority_change_with_stale_guard():
    assert "WM.send('eve_characters_state')" in JS
    assert "requestSequence += 1" in JS
    assert re.search(
        r"requestSequence \+= 1;\s*var wanted = requestSequence;\s*"
        r"WM\.send\('eve_characters_state'\)\.then\(function \(payload\) \{\s*"
        r"if \(wanted !== requestSequence \|\| !isVisible\(\)\) return;\s*"
        r"if \(!payload \|\| typeof payload !== 'object' \|\| Array\.isArray\(payload\)\) \{\s*"
        r"showReadError\('Could not refresh the authorized characters\. Keeping the previous roster\.'\);\s*"
        r"return;\s*\}\s*render\(payload\);",
        JS,
        re.DOTALL,
    )

    assert "document.addEventListener('wm:eve-authority'" in JS
    assert re.search(
        r"document\.addEventListener\('wm:eve-authority', function \(\) \{\s*"
        r"if \(!isVisible\(\)\) return;\s*requestState\(\);\s*\}\);",
        JS,
        re.DOTALL,
    )

    section_listener = JS.split("document.addEventListener('wm:section'", 1)[1]
    assert section_listener.index("enterSection();") < section_listener.index(
        "requestState();"
    )


# The shared event carries only a semantic "something changed" signal
# (Task 6 / app.js fan-out), so the Characters module must re-ask for state
# rather than treat the payload itself as renderable data.
def test_characters_event_path_re_reads_state_rather_than_rendering_event_payloads():
    authority_listener = JS.split("document.addEventListener('wm:eve-authority'", 1)[1]
    authority_listener = authority_listener.split("});", 1)[0]
    assert "render(" not in authority_listener
    assert "requestState();" in authority_listener


# The filter is client state: it changes only what the page draws, so it
# never crosses the bridge. The roster names the filtered result set for
# assistive tech, and the clear action is a subordinate inline control.
def test_characters_filter_and_empty_states_are_rendered_locally():
    assert "characters.length" in JS
    assert "raw.characters.map(normalizeRow)" in JS
    assert "raw.characters.slice(0, 50)" not in JS
    assert "roster.setAttribute('aria-label'" in JS
    assert "filterClear.hidden = !filterText.trim();" in JS
    assert "filter.value = '';" in JS
    assert "filter.focus();" in JS
    assert "No characters yet." in JS
    assert "No authorized characters yet." not in JS
    assert "No characters match \u201c" in JS
    assert "The shared EVE character authority is unavailable." in JS
    assert "return 'Character roster';" in JS


# Wire values and the retained authentication search stay compatible. Only
# the visible authorized label and date column change; missing/expired access
# remains a condition, not an invitation to authenticate that particular row.
def test_characters_render_uses_ready_without_removing_authentication_search():
    assert "row.skills === 'authorized'" in JS
    assert "row.fittings === 'authorized'" in JS
    assert "return 'Ready';" in JS
    assert "return 'Access needed';" in JS
    assert "return 'Access expired';" in JS
    assert "return 'Sign in';" not in JS
    assert "authenticated_utc" in JS
    assert "'Authenticated ' + authenticated" not in JS
    assert "formatAuthenticated(row.authenticated_utc)" in JS
    assert "characters-authenticated" not in JS


def test_characters_roster_exposes_table_semantics():
    pane = _characters_pane()
    roster = re.search(r'<div[^>]+id="characters-roster"[^>]*>', pane)
    assert roster
    assert 'role="table"' in roster.group(0)
    assert 'aria-colcount="4"' in roster.group(0)
    assert "head.setAttribute('role', 'row');" in JS
    assert "cell.setAttribute('role', 'columnheader');" in JS
    assert "node.setAttribute('role', 'row');" in JS
    assert "name.setAttribute('role', 'cell');" in JS
    assert "['Character', 'Skills', 'Fittings', 'Actions']" in JS
    assert "actions.setAttribute('role', 'cell');" in JS
    status_cell = re.search(r"function makeStatusCell\(.*?\n  \}", JS, re.DOTALL)
    assert status_cell
    assert "cell.setAttribute('role', 'cell');" in status_cell.group(0)


def test_characters_authorization_copy_covers_both_maintenance_cases():
    pane = _characters_pane()
    copy = (
        "Use EVE sign-in to add a character or update access for Skills and Fittings."
    )
    assert copy in pane
    assert copy in JS
    assert "Wingman shares one EVE sign-in across Skills and Fittings." not in JS
    assert "Account</span>" not in pane


# The start/cancel calls return only {accepted, error}. A successful click is
# NOT completion; waiting/idle state comes back from a later authority read.
def test_characters_auth_controls_use_shared_endpoints_without_optimistic_state():
    assert "WM.send('eve_characters_authenticate')" in JS
    assert "WM.send('eve_characters_cancel_auth')" in JS
    assert "Authenticate character\u2026" in JS
    assert "Finish EVE sign-in in your browser." in JS
    assert "authorization_activity = 'waiting'" not in JS
    assert "var authRequestPending = false;" in JS
    assert "characters-auth-action" not in JS
    assert re.search(
        r"authenticate\.disabled = !state\.auth_configured\s*"
        r"\|\| state\.authorization_activity === 'waiting'\s*"
        r"\|\| authRequestPending;",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"cancel\.disabled = state\.authorization_activity !== 'waiting'\s*"
        r"\|\| authRequestPending;",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"authRequestPending = false;\s*readErrorNotice = '';\s*closeMenu\(false\);\s*"
        r"state = normalizeState\(payload\);",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"authRequestPending = true;\s*renderButtons\(\);\s*"
        r"WM\.send\('eve_characters_authenticate'\)",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"authRequestPending = true;\s*renderButtons\(\);\s*"
        r"WM\.send\('eve_characters_cancel_auth'\)",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"WM\.send\('eve_characters_authenticate'\)\.then\(function \(result\) \{\s*"
        r"if \(!result \|\| !result\.accepted\) \{\s*authRequestPending = false;"
        r"\s*renderButtons\(\);",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"WM\.send\('eve_characters_cancel_auth'\)\.then\(function \(result\) \{\s*"
        r"if \(!result \|\| !result\.accepted\) \{\s*authRequestPending = false;"
        r"\s*renderButtons\(\);",
        JS,
        re.DOTALL,
    )


# One fixed-position menu portal, outside the scroller, means every row reuses
# the same menu object and only the current trigger/id move.
def test_characters_menu_and_forget_flow_are_fixed_accessible_and_tri_state():
    assert "aria-haspopup', 'menu'" in JS
    assert "menu.setAttribute('role', 'menu');" in JS
    assert "menu.setAttribute('aria-label', 'Character actions');" in JS
    assert "menu.setAttribute('aria-label', 'Actions for ' + menuCharacterName);" in JS
    assert "forget.setAttribute('role', 'menuitem');" in JS
    assert "forget.disabled = true;" in JS
    assert re.search(
        r"openMenu\(trigger, row, focusLast\) \{.*?forget\.disabled = false;",
        JS,
        re.DOTALL,
    )
    assert re.search(
        r"closeMenu\(restoreFocus\) \{.*?forget\.disabled = true;",
        JS,
        re.DOTALL,
    )
    assert "aria-expanded" in JS
    assert "ArrowDown" in JS
    assert "ArrowUp" in JS
    assert "Home" in JS
    assert "End" in JS
    assert "Escape" in JS
    assert "document.addEventListener('mousedown'" in JS
    assert "window.addEventListener('blur', function () { closeMenu(false); });" in JS
    assert "menu.style.left" in JS
    assert "menu.style.top" in JS
    assert "rect.top - menuRect.height - 4" in JS
    assert "window.innerWidth - menuRect.width - 6" in JS
    assert "WM.confirm('Forget character'" in JS
    assert "Skills and Fittings" in JS
    assert "WM.send('eve_characters_forget', characterId)" in JS
    assert "if (!result || !result.applied)" in JS
    assert "if (!result.persisted)" in JS
    assert "requestState();" in JS
    assert ".focus();" in JS
    assert re.search(
        r"function render\(payload\) \{\s*authRequestPending = false;\s*"
        r"readErrorNotice = '';\s*closeMenu\(false\);",
        JS,
        re.DOTALL,
    )


def _run_characters_page(scenario):
    """Execute the production closure; only DOM and bridge boundaries are doubled."""
    script = textwrap.dedent(
        rf"""
        const vm = require('vm');

        function ClassList(initial) {{
          this._set = new Set(initial || []);
        }}
        ClassList.prototype.add = function (name) {{ this._set.add(name); }};
        ClassList.prototype.remove = function (name) {{ this._set.delete(name); }};
        ClassList.prototype.contains = function (name) {{ return this._set.has(name); }};
        ClassList.prototype.toggle = function (name, force) {{
          if (force === undefined) {{
            if (this._set.has(name)) {{ this._set.delete(name); return false; }}
            this._set.add(name); return true;
          }}
          if (force) this._set.add(name); else this._set.delete(name);
          return !!force;
        }};

        function makeNode(tag, id, classes) {{
          const node = {{
            tagName: (tag || 'div').toUpperCase(),
            id: id || '',
            className: classes || '',
            dataset: {{}},
            hidden: false,
            disabled: false,
            open: false,
            textContent: '',
            title: '',
            value: '',
            style: {{}},
            attributes: {{}},
            children: [],
            parentNode: null,
            listeners: {{}},
            classList: new ClassList((classes || '').split(/\s+/).filter(Boolean)),
            appendChild: function (child) {{ child.parentNode = this; this.children.push(child); return child; }},
            removeChild: function (child) {{
              const at = this.children.indexOf(child);
              if (at !== -1) this.children.splice(at, 1);
              child.parentNode = null;
              return child;
            }},
            addEventListener: function (type, fn) {{
              (this.listeners[type] || (this.listeners[type] = [])).push(fn);
            }},
            dispatchEvent: function (ev) {{
              ev.target = ev.target || this;
              ev.preventDefault = ev.preventDefault || function () {{ this.defaultPrevented = true; }};
              (this.listeners[ev.type] || []).forEach((fn) => fn.call(this, ev));
            }},
            setAttribute: function (name, value) {{ this.attributes[name] = String(value); }},
            getAttribute: function (name) {{ return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null; }},
            focus: function (options) {{
              this.focusOptions = options;
              this.focusCalls = (this.focusCalls || 0) + 1;
              document.activeElement = this;
            }},
            contains: function (target) {{
              for (let cur = target; cur; cur = cur.parentNode) if (cur === this) return true;
              return false;
            }},
            querySelectorAll: function (selector) {{
              const out = [];
              function walk(node) {{
                node.children.forEach(function (child) {{
                  if (selector === '[role="menuitem"]' && child.attributes.role === 'menuitem') out.push(child);
                  walk(child);
                }});
              }}
              walk(this);
              return out;
            }},
            querySelector: function (selector) {{
              if (selector === 'summary') {{
                return this.children.find((child) => child.tagName === 'SUMMARY') || null;
              }}
              return null;
            }},
            getBoundingClientRect: function () {{
              return this.rect || {{ left: 100, top: 100, bottom: 120, width: 80, height: 20 }};
            }}
          }};
          Object.defineProperty(node, 'firstChild', {{
            get: function () {{ return this.children.length ? this.children[0] : null; }}
          }});
          return node;
        }}

        const nodes = {{}};
        function add(tag, id, classes) {{
          const node = makeNode(tag, id, classes);
          if (id) nodes[id] = node;
          return node;
        }}

        const documentListeners = {{}};
        const document = {{
          activeElement: null,
          getElementById: function (id) {{ return nodes[id] || null; }},
          createElement: function (tag) {{ return makeNode(tag, '', ''); }},
          addEventListener: function (type, fn) {{
            (documentListeners[type] || (documentListeners[type] = [])).push(fn);
          }},
          dispatchEvent: function (ev) {{
            (documentListeners[ev.type] || []).forEach((fn) => fn(ev));
          }}
        }};

        const windowListeners = {{}};
        const window = {{
          document,
          innerWidth: 800,
          innerHeight: 600,
          addEventListener: function (type, fn) {{
            (windowListeners[type] || (windowListeners[type] = [])).push(fn);
          }},
          dispatchEvent: function (ev) {{
            (windowListeners[ev.type] || []).forEach((fn) => fn(ev));
          }}
        }};

        function CustomEvent(type, init) {{
          this.type = type;
          this.detail = init && init.detail;
        }}

        const section = add('div', 'section-characters', 'settings active');
        const count = add('p', 'characters-count', 'hint');
        const authenticate = add('button', 'characters-authenticate', 'btn');
        const activity = add('p', 'characters-activity', 'hint');
        const cancel = add('button', 'characters-cancel', 'btn');
        const notice = add('p', 'characters-notice', 'field-msg');
        const live = add('p', 'characters-live', 'hint');
        const filter = add('input', 'characters-filter', 'field');
        const filterClear = add('button', 'characters-filter-clear', 'linkbtn');
        const roster = add('div', 'characters-roster', '');
        const statusbar = add('div', 'statusbar-slot', '');
        statusbar.rect = {{ left: 0, top: 550, bottom: 600, width: 800, height: 50 }};
        const empty = add('div', 'characters-empty', 'empty');
        roster.appendChild(empty);
        const menu = add('div', 'characters-menu', 'ctxmenu');
        const forget = add('button', 'characters-menu-forget', '');
        forget.disabled = true;
        menu.appendChild(forget);

        section.appendChild(count);
        section.appendChild(authenticate);
        section.appendChild(activity);
        section.appendChild(cancel);
        section.appendChild(notice);
        section.appendChild(filter);
        section.appendChild(filterClear);
        section.appendChild(live);
        section.appendChild(roster);
        section.appendChild(menu);

        let authResolve;
        let cancelResolve;
        let deferReads = false;
        const stateReads = [];
        const calls = [];
        const confirmations = [];
        let confirmResult = true;
        let forgetResult = {{ applied: true, persisted: true, error: '' }};
        let statePayload = {{
          available: true,
          auth_configured: true,
          authorization_activity: 'idle',
          authorization_notice: 'Last sign-in failed.',
          warnings: ['Restored eve_authority.json from backup.', 'The EVE fittings subsystem is unavailable.'],
          characters: [{{
            character_id: 4,
            character_name: 'Needs Reauth',
            authenticated_utc: '2026-09-04T12:00:00+00:00',
            skills: 'sign_in',
            fittings: 'sign_in',
            needs_reauth: true,
            persistence_error: ''
          }}]
        }};

        window.WM = {{
          current_route: 'settings',
          current_section: 'characters',
          el: function (id) {{ return document.getElementById(id); }},
          make: function (tag, cls, text) {{
            const node = makeNode(tag, '', cls || '');
            if (cls) node.className = cls;
            if (text !== undefined && text !== null) node.textContent = String(text);
            return node;
          }},
          send: function (method, ...args) {{
            calls.push([method, ...args]);
            if (method === 'eve_characters_state') {{
              if (deferReads) return new Promise((resolve) => stateReads.push(resolve));
              return Promise.resolve(statePayload);
            }}
            if (method === 'eve_characters_authenticate') {{
              return new Promise(function (resolve) {{ authResolve = resolve; }});
            }}
            if (method === 'eve_characters_cancel_auth') {{
              return new Promise(function (resolve) {{ cancelResolve = resolve; }});
            }}
            if (method === 'eve_characters_forget') {{
              return Promise.resolve(forgetResult);
            }}
            throw new Error('unexpected method ' + method);
          }},
          confirm: function (...args) {{ confirmations.push(args); return Promise.resolve(confirmResult); }}
        }};

        global.window = window;
        global.document = document;
        global.CustomEvent = CustomEvent;
        global.console = console;

        vm.runInThisContext({json.dumps(JS)}, {{ filename: 'characters.js' }});

        function tick() {{ return new Promise((resolve) => setTimeout(resolve, 0)); }}
        function findByClass(node, cls) {{
          if ((node.className || '').split(/\s+/).indexOf(cls) !== -1) return node;
          for (const child of node.children) {{
            const found = findByClass(child, cls);
            if (found) return found;
          }}
          return null;
        }}

        const assert = require('node:assert/strict');
        (async function () {{
          {scenario}
        }})().catch(function (error) {{ console.error(error); process.exitCode = 1; }});
        """
    )

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        path = pathlib.Path(fh.name)
    try:
        proc = subprocess.run(
            ["node", str(path)], capture_output=True, text=True, check=False
        )
    finally:
        path.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout) if proc.stdout.strip() else None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize(
    "forget_result",
    [
        {"applied": True, "persisted": False, "error": "Cleanup was not saved."},
        {"applied": True, "persisted": False, "error": ""},
        {"applied": False, "persisted": False, "error": "Copy is still running."},
        None,
    ],
)
def test_characters_warnings_menu_and_global_auth_commands_behave_together(
    forget_result,
):
    result = _run_characters_page(
        rf"""
          document.dispatchEvent(new CustomEvent('wm:section', {{ detail: 'characters' }}));
          await tick();
          const initialNotice = notice.textContent;
          const menuTrigger = findByClass(roster, 'characters-menu-trigger');
          menuTrigger.dispatchEvent({{ type: 'click' }});
          const forgetEnabledWhenOpen = !forget.disabled && !menu.hidden;
          const openMenuLabel = menu.getAttribute('aria-label');
          const rowAuthButtonPresent = !!findByClass(roster, 'characters-auth-action');

          statePayload = Object.assign({{}}, statePayload, {{
            authorization_notice: '',
            characters: [{{
              character_id: 5,
              character_name: 'Replacement Pilot',
              authenticated_utc: '2026-09-04T12:30:00+00:00',
              skills: 'authorized',
              fittings: 'authorized',
              needs_reauth: false,
              persistence_error: ''
            }}]
          }});
          document.dispatchEvent(new CustomEvent('wm:eve-authority', {{ detail: {{}} }}));
          await tick();
          const menuClosedAfterAuthorityRender = menu.hidden && forget.disabled
            && menuTrigger.getAttribute('aria-expanded') === 'false';
          const menuLabelAfterAuthorityRender = menu.getAttribute('aria-label');

          const replacementTrigger = findByClass(roster, 'characters-menu-trigger');
          replacementTrigger.dispatchEvent({{ type: 'click' }});
          forgetResult = {json.dumps(forget_result)};
          forget.dispatchEvent({{ type: 'click' }});
          await tick();
          await tick();
          await tick();
          const localNoticeWithWarnings = notice.textContent;

          statePayload = null;
          document.dispatchEvent(new CustomEvent('wm:eve-authority', {{ detail: {{}} }}));
          await tick();
          const preservedRosterRowCount = roster.children.length;
          const preservedRosterName = findByClass(roster, 'characters-name-text').textContent;
          const readErrorNotice = notice.textContent;
          const emptyHiddenAfterReadError = empty.hidden;

          statePayload = {{
            available: true,
            auth_configured: true,
            authorization_activity: 'idle',
            authorization_notice: '',
            warnings: ['Restored eve_authority.json from backup.', 'The EVE fittings subsystem is unavailable.'],
            characters: [{{
              character_id: 6,
              character_name: 'Recovered Pilot',
              authenticated_utc: '2026-09-04T12:45:00+00:00',
              skills: 'authorized',
              fittings: 'authorized',
              needs_reauth: false,
              persistence_error: ''
            }}]
          }};
          document.dispatchEvent(new CustomEvent('wm:eve-authority', {{ detail: {{}} }}));
          await tick();
          const recoveredRosterName = findByClass(roster, 'characters-name-text').textContent;
          const noticeAfterRecovery = notice.textContent;

          authenticate.dispatchEvent({{ type: 'click' }});
          const authDisabledImmediately = authenticate.disabled;

          authResolve({{ accepted: true, error: '' }});
          statePayload = Object.assign({{}}, statePayload, {{ authorization_activity: 'waiting' }});
          document.dispatchEvent(new CustomEvent('wm:eve-authority', {{ detail: {{}} }}));
          await tick();

          const waitingActivity = activity.textContent;
          const waitingCancel = {{text: cancel.textContent, hidden: cancel.hidden, disabled: cancel.disabled}};
          cancel.dispatchEvent({{ type: 'click' }});
          const cancelDisabledImmediately = cancel.disabled;

          console.log(JSON.stringify({{
            initialNotice,
            forgetEnabledWhenOpen,
            openMenuLabel,
            rowAuthButtonPresent,
            menuClosedAfterAuthorityRender,
            menuLabelAfterAuthorityRender,
            localNoticeWithWarnings,
            preservedRosterRowCount,
            preservedRosterName,
            readErrorNotice,
            emptyHiddenAfterReadError,
            recoveredRosterName,
            noticeAfterRecovery,
            authDisabledImmediately,
            waitingActivity,
            waitingCancel,
            cancelDisabledImmediately
          }}));
        """
    )
    assert "Last sign-in failed." in result["initialNotice"]
    assert "Restored eve_authority.json from backup." in result["initialNotice"]
    assert "The EVE fittings subsystem is unavailable." in result["initialNotice"]
    assert result["forgetEnabledWhenOpen"] is True
    assert result["openMenuLabel"] == "Actions for Needs Reauth"
    assert result["rowAuthButtonPresent"] is False
    assert result["menuClosedAfterAuthorityRender"] is True
    assert result["menuLabelAfterAuthorityRender"] == "Character actions"
    # The menu has closed and later roster reads can replace this row. The
    # operation's captured identity, not the latest roster, owns its outcome.
    operation_notice = result["localNoticeWithWarnings"]
    assert "Replacement Pilot" in operation_notice
    if forget_result and forget_result["applied"]:
        outcome = operation_notice.split("\n")[0]
        assert "authorization" in outcome.lower()
        assert "was removed" in outcome
        assert "local Skills/Fittings data" in outcome
        assert "Restart Wingman" in outcome
        assert "authenticating this character again" in outcome
    elif forget_result:
        assert "Could not forget" in operation_notice
        assert "was removed" not in operation_notice
    else:
        assert "Could not confirm whether" in operation_notice
        assert "before trying again" in operation_notice
    if forget_result and forget_result["error"]:
        assert forget_result["error"] in operation_notice
    assert (
        "Restored eve_authority.json from backup." in result["localNoticeWithWarnings"]
    )
    assert (
        "The EVE fittings subsystem is unavailable."
        in result["localNoticeWithWarnings"]
    )
    assert result["preservedRosterRowCount"] == 2
    assert result["preservedRosterName"] == "Replacement Pilot"
    assert result["emptyHiddenAfterReadError"] is True
    assert operation_notice.split("\n")[0] in result["readErrorNotice"]
    assert "Could not refresh the authorized characters." in result["readErrorNotice"]
    assert result["recoveredRosterName"] == "Recovered Pilot"
    assert "Replacement Pilot" in result["noticeAfterRecovery"]
    assert result["noticeAfterRecovery"] == result["localNoticeWithWarnings"]
    assert result["authDisabledImmediately"] is True
    assert "Finish EVE sign-in in your browser." in result["waitingActivity"]
    assert result["waitingCancel"] == {
        "text": "Cancel",
        "hidden": False,
        "disabled": False,
    }
    assert result["cancelDisabledImmediately"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_characters_four_cells_keep_full_identity_status_classes_and_search_aliases():
    _run_characters_page(
        r"""
        const longName = 'A very long pilot identity that must remain available in full';
        const original = statePayload.characters[0];
        statePayload.characters = [
          Object.assign({}, original, {character_name: longName, skills: 'authorized',
            fittings: 'authorized', needs_reauth: false}),
          Object.assign({}, original, {character_id: 5, character_name: 'Partial Pilot',
            skills: 'authorized', needs_reauth: false, authenticated_utc: '2026-08-02T05:30:00Z'}),
          Object.assign({}, original, {character_id: 6, character_name: 'Expired Pilot',
            authenticated_utc: 'invalid'}),
          Object.assign({}, original, {character_id: 7, character_name: 'New Pilot',
            needs_reauth: false, authenticated_utc: ''})
        ];
        document.dispatchEvent(new CustomEvent('wm:section', {detail: 'characters'}));
        await tick();
        assert.deepEqual(roster.children[0].children.map(c => c.textContent),
          ['Character', 'Skills', 'Fittings', 'Actions']);
        assert.ok(roster.children[0].children.every(c => c.getAttribute('role') === 'columnheader'));
        roster.children.slice(1).forEach(row => {
          assert.equal(row.getAttribute('role'), 'row');
          assert.equal(row.children.length, 4);
          assert.ok(row.children.every(c => c.getAttribute('role') === 'cell'));
          assert.equal(findByClass(row, 'characters-authenticated'), null);
          assert.equal(findByClass(row, 'characters-auth-action'), null);
        });
        const first = roster.children[1];
        assert.equal(findByClass(first, 'characters-name-text').textContent, longName);
        assert.equal(findByClass(first, 'characters-name-text').title, longName);
        assert.equal(findByClass(first, 'characters-menu-trigger').title, 'More actions');
        assert.equal(findByClass(first, 'characters-menu-trigger').getAttribute('aria-label'),
          'More actions for ' + longName);
        assert.deepEqual(roster.children.slice(1).map(row => row.children.slice(1, 3)
          .map(c => [c.textContent, c.className])), [
          [['Ready', 'characters-status authorized'], ['Ready', 'characters-status authorized']],
          [['Ready', 'characters-status authorized'], ['Access needed', 'characters-status access-needed']],
          [['Access expired', 'characters-status access-expired'], ['Access expired', 'characters-status access-expired']],
          [['Access needed', 'characters-status access-needed'], ['Access needed', 'characters-status access-needed']]
        ]);
        const readsBeforeFilter = calls.length;
        for (const [query, names] of [
          [' ready ', [longName, 'Partial Pilot']],
          ['AUTHORIZED', [longName, 'Partial Pilot']],
          ['Authorized Authorized', [longName]],
          ['Partial Pilot Authorized Access needed', ['Partial Pilot']],
          ['Partial Pilot Ready Access needed', ['Partial Pilot']],
          ['Ready Ready 2026-09-04', [longName]],
          ['Access needed 2026-08-02', ['Partial Pilot']],
          ['2026-09-04 12:00 UTC', [longName]],
          ['2026-08-02', ['Partial Pilot']],
          ['Access expired', ['Expired Pilot']],
          ['Access needed', ['Partial Pilot', 'New Pilot']],
          ['invalid', []]
        ]) {
          filter.value = query;
          filter.dispatchEvent({type: 'input'});
          assert.deepEqual(roster.children.filter(row => row.className === 'characters-row')
            .map(row => findByClass(row, 'characters-name-text').textContent), names, query);
        }
        assert.equal(calls.length, readsBeforeFilter, 'filter stays page-local');
        filterClear.dispatchEvent({type: 'click'});
        assert.equal(count.textContent, '4 characters');
        assert.equal(document.activeElement, filter);
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("statusbar_top", [550, 480, None])
def test_characters_menu_stays_inside_viewport_above_measured_statusbar(statusbar_top):
    _run_characters_page(
        rf"""
        document.dispatchEvent(new CustomEvent('wm:section', {{detail: 'characters'}}));
        await tick();
        const trigger = findByClass(roster, 'characters-menu-trigger');
        const stripTop = {json.dumps(statusbar_top)};
        if (stripTop === null) delete nodes['statusbar-slot'];
        else {{
          statusbar.rect.top = stripTop;
          statusbar.rect.height = window.innerHeight - stripTop;
        }}
        menu.rect = {{left: 0, top: 0, bottom: 40, width: 190, height: 40}};
        for (const top of [10, 450, 510, 575]) {{
          trigger.rect = {{left: 775, top, bottom: top + 24, width: 24, height: 24}};
          trigger.dispatchEvent({{type: 'click'}});
          const x = parseFloat(menu.style.left), y = parseFloat(menu.style.top);
          assert.ok(x >= 6 && x + 190 <= 794, 'menu stays within horizontal viewport');
          assert.ok(y >= 6 && y + 40 <= (stripTop === null ? 600 : stripTop) - 6,
            'menu bottom must clear the actual status strip, not only the viewport');
          menu.dispatchEvent({{type: 'keydown', key: 'Escape'}});
          assert.equal(document.activeElement, trigger);
        }}
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("shift", [False, True])
def test_characters_menu_tab_rejoins_native_row_order_without_scroll_or_trap(shift):
    _run_characters_page(
        rf"""
        document.dispatchEvent(new CustomEvent('wm:section', {{detail: 'characters'}}));
        await tick();
        const trigger = findByClass(roster, 'characters-menu-trigger');
        trigger.dispatchEvent({{type: 'keydown', key: 'ArrowDown'}});
        assert.equal(document.activeElement, forget);
        const event = {{type: 'keydown', key: 'Tab', shiftKey: {json.dumps(shift)}}};
        menu.dispatchEvent(event);
        assert.equal(menu.hidden, true, 'Tab dismisses the fixed menu');
        assert.equal(trigger.getAttribute('aria-expanded'), 'false');
        assert.equal(document.activeElement, trigger, 'native Tab resumes at its row trigger');
        assert.equal(trigger.focusOptions.preventScroll, true, 'returning focus must not scroll the roster');
        assert.ok(!event.defaultPrevented, 'browser owns forward/backward Tab traversal');
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("event_target", ["roster", "window"])
@pytest.mark.parametrize("outside_focus", [False, True])
def test_characters_menu_dismisses_stale_anchor_without_stealing_focus(
    event_target, outside_focus
):
    _run_characters_page(
        rf"""
        document.dispatchEvent(new CustomEvent('wm:section', {{detail: 'characters'}}));
        await tick();
        const trigger = findByClass(roster, 'characters-menu-trigger');
        trigger.dispatchEvent({{type: 'click'}});
        if ({json.dumps(outside_focus)}) filter.focus();
        const target = {event_target};
        target.dispatchEvent({{type: target === roster ? 'scroll' : 'resize'}});
        assert.equal(menu.hidden, true, 'an invalidated anchor cannot leave its fixed menu behind');
        assert.equal(trigger.getAttribute('aria-expanded'), 'false');
        assert.equal(document.activeElement, {"filter" if outside_focus else "trigger"});
        if (!{json.dumps(outside_focus)}) assert.equal(trigger.focusOptions.preventScroll, true);
        const focusCalls = trigger.focusCalls || 0;
        filter.focus();
        target.dispatchEvent({{type: target === roster ? 'scroll' : 'resize'}});
        assert.equal(document.activeElement, filter);
        assert.equal(trigger.focusCalls || 0, focusCalls, 'closed menus cannot reclaim focus');
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_characters_delayed_reads_retain_roster_and_reject_stale_or_hidden_replies():
    _run_characters_page(
        r"""
        document.dispatchEvent(new CustomEvent('wm:section', {detail: 'characters'}));
        await tick();
        const prior = roster.children[1];
        deferReads = true;
        document.dispatchEvent(new CustomEvent('wm:eve-authority'));
        document.dispatchEvent(new CustomEvent('wm:eve-authority'));
        assert.equal(roster.children[1], prior, 'pending reads retain the painted roster');
        const updated = Object.assign({}, statePayload, {characters: [Object.assign({},
          statePayload.characters[0], {character_name: 'Newest Pilot'})]});
        stateReads[1](updated);
        await tick();
        stateReads[0](statePayload);
        await tick();
        assert.equal(findByClass(roster, 'characters-name-text').textContent, 'Newest Pilot');
        document.dispatchEvent(new CustomEvent('wm:eve-authority'));
        document.dispatchEvent(new CustomEvent('wm:section', {detail: 'general'}));
        stateReads[2](statePayload);
        await tick();
        assert.equal(findByClass(roster, 'characters-name-text').textContent, 'Newest Pilot');
        document.dispatchEvent(new CustomEvent('wm:eve-authority'));
        assert.equal(stateReads.length, 3, 'hidden authority events do not read');
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("accepted", [False, True])
def test_characters_waiting_disables_authentication_but_retains_cancel_until_idle(
    accepted,
):
    _run_characters_page(
        rf"""
        statePayload.authorization_activity = 'waiting';
        statePayload.auth_configured = false;
        document.dispatchEvent(new CustomEvent('wm:section', {{detail: 'characters'}}));
        await tick();
        assert.equal(authenticate.disabled, true);
        assert.equal(cancel.hidden, false);
        assert.equal(cancel.disabled, false, 'Cancel does not require a configured Authenticate button');
        cancel.dispatchEvent({{type: 'click'}});
        assert.equal(cancel.disabled, true);
        cancelResolve({{accepted: {json.dumps(accepted)}, error: 'Cancellation was refused.'}});
        await tick();
        assert.equal(cancel.hidden, false, 'acceptance/refusal is not an idle-state observation');
        assert.equal(authenticate.disabled, true);
        assert.equal(cancel.disabled, {json.dumps(accepted)});
        if (!{json.dumps(accepted)}) assert.ok(notice.textContent.includes('Cancellation was refused.'));
        statePayload.authorization_activity = 'idle';
        document.dispatchEvent(new CustomEvent('wm:eve-authority'));
        await tick();
        assert.equal(cancel.hidden, true);
        assert.deepEqual(calls.filter(call => call[0] !== 'eve_characters_state'),
          [['eve_characters_cancel_auth']]);
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("persisted", [False, True])
def test_characters_forget_receipt_retains_removed_identity_after_row_disappears(
    persisted,
):
    _run_characters_page(
        rf"""
        document.dispatchEvent(new CustomEvent('wm:section', {{detail: 'characters'}}));
        await tick();
        const trigger = findByClass(roster, 'characters-menu-trigger');
        trigger.dispatchEvent({{type: 'click'}});
        confirmResult = false;
        forget.dispatchEvent({{type: 'click'}});
        await tick();
        assert.equal(document.activeElement, trigger);
        assert.equal(menu.hidden, true);
        assert.equal(calls.filter(call => call[0] === 'eve_characters_forget').length, 0);
        assert.equal(confirmations[0][0], 'Forget character');
        assert.ok(confirmations[0][1].includes('Needs Reauth'));
        assert.ok(confirmations[0][1].includes('Skills and Fittings'));
        assert.equal(confirmations[0][2].destructive, true);
        confirmResult = true;
        trigger.dispatchEvent({{type: 'click'}});
        statePayload.characters = [];
        forgetResult = {{applied: true, persisted: {json.dumps(persisted)}, error: ''}};
        forget.dispatchEvent({{type: 'click'}});
        await tick();
        await tick();
        assert.deepEqual(calls.filter(call => call[0] === 'eve_characters_forget'),
          [['eve_characters_forget', 4]]);
        assert.equal(findByClass(roster, 'characters-row'), null);
        assert.equal(live.textContent, 'Needs Reauth was removed.');
        if ({json.dumps(persisted)}) {{
          assert.ok(!notice.textContent.includes('Restart Wingman'));
        }} else {{
          assert.ok(notice.textContent.includes('Needs Reauth'));
          assert.ok(notice.textContent.includes('Restart Wingman'));
          const receipt = notice.textContent;
          statePayload = null;
          document.dispatchEvent(new CustomEvent('wm:eve-authority'));
          await tick();
          assert.ok(notice.textContent.includes('Restart Wingman'));
          assert.ok(notice.textContent.includes('Needs Reauth'));
          assert.ok(notice.textContent.includes('Could not refresh'));
          assert.ok(receipt.includes('local Skills/Fittings data'));
        }}
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_characters_menu_preserves_keyboard_navigation_and_outside_dismissal():
    _run_characters_page(
        r"""
        document.dispatchEvent(new CustomEvent('wm:section', {detail: 'characters'}));
        await tick();
        const trigger = findByClass(roster, 'characters-menu-trigger');
        for (const key of ['ArrowDown', 'ArrowUp', 'Enter', ' ']) {
          trigger.dispatchEvent({type: 'keydown', key});
          assert.equal(menu.hidden, false);
          assert.equal(document.activeElement, forget);
          assert.equal(trigger.getAttribute('aria-haspopup'), 'menu');
          assert.equal(trigger.getAttribute('aria-expanded'), 'true');
          for (const key of ['ArrowDown', 'ArrowUp', 'Home', 'End']) {
            menu.dispatchEvent({type: 'keydown', key});
            assert.equal(document.activeElement, forget);
          }
          menu.dispatchEvent({type: 'keydown', key: 'Escape'});
          assert.equal(document.activeElement, trigger);
          assert.equal(menu.hidden, true);
        }
        trigger.dispatchEvent({type: 'click'});
        filter.focus();
        document.dispatchEvent({type: 'mousedown', target: filter});
        assert.equal(menu.hidden, true);
        assert.equal(document.activeElement, filter, 'outside dismissal cannot reclaim focus');
        trigger.dispatchEvent({type: 'click'});
        filter.focus();
        window.dispatchEvent({type: 'blur'});
        assert.equal(menu.hidden, true);
        assert.equal(document.activeElement, filter);
        """
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("section", ["characters", "fleet"])
def test_open_settings_section_enters_once_restores_and_respects_eve_gate(section):
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

        const routeNames = {json.dumps(re.findall('id="route-([a-z0-9-]+)"', HTML))};
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
          add('rail-fleet', ['rail-item'], {{ section: 'fleet' }}),
          add('rail-alerts', ['rail-item'], {{ section: 'alerts' }}),
          add('rail-general', ['rail-item'], {{ section: 'general' }}),
        ];
        const sectionNames = ['uploading', 'characters', 'bookmarks', 'previews', 'fleet', 'alerts', 'general'];
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
        window.WM.openSettingsSection({json.dumps(section)});

        const firstEvents = sectionEvents.slice();
        const WM = window.WM;
        const assert = require('node:assert/strict');
        assert.equal(nodes['rail-' + {json.dumps(section)}].classList.contains('active'), true);
        assert.equal(nodes['section-' + {json.dumps(section)}].classList.contains('active'), true);
        nodes['btn-settings'].dispatchEvent({{type: 'click'}});
        assert.equal(WM.current_route, 'skills');
        nodes['btn-settings'].dispatchEvent({{type: 'click'}});
        assert.equal(WM.current_section, {json.dumps(section)});
        WM.apply_eve_gate(false);
        assert.equal(nodes['rail-' + {json.dumps(section)}].hidden, true);
        assert.equal(WM.current_section, 'general');
        WM.openSettingsSection({json.dumps(section)});
        assert.equal(WM.current_section, 'general', 'deep links cannot reopen a gated section');
        WM.section({json.dumps(section)});
        assert.equal(WM.current_section, 'general', 'direct selection cannot reopen a gated section');
        WM.route('main');
        nodes['btn-settings'].dispatchEvent({{type: 'click'}});
        assert.equal(WM.current_section, 'general', 'the gear cannot restore a hidden section');
        WM.apply_eve_gate(true);
        WM.route('skills');
        WM.openSettingsSection({json.dumps(section)});

        console.log(JSON.stringify({{
          currentRoute: window.WM.current_route,
          currentSection: window.WM.current_section,
          lastDestination: window.WM.last_destination,
          sectionEvents: firstEvents,
          sectionRailActive: nodes['rail-' + {json.dumps(section)}].classList.contains('active'),
          sectionPaneActive: nodes['section-' + {json.dumps(section)}].classList.contains('active'),
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
        "currentSection": section,
        "lastDestination": "skills",
        "sectionEvents": [section],
        "sectionRailActive": True,
        "sectionPaneActive": True,
        "settingsGearActive": True,
    }
