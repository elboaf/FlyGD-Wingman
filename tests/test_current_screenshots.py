"""Current main-window cards exercise real owners, never live domain actions."""

import json
import shutil
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest

from tests.html_tree import PageTree
from tests.node_scenario_worker import NodeScenarioFailure, NodeScenarioWorker
from tests.test_new_screenshots import ROOT, shoot

# Explicit coverage contract; the original inventory remains in order.
SYNTHETIC = {
    "settings-companions-populated": "companions",
    "settings-companions-detail-narrow": "companions",
    "settings-companions-add": "companions",
    "settings-companions-source-narrow": "companions",
    "settings-wanderer": "previews",
    "settings-wanderer-narrow": "previews",
    "settings-fleet-characters-narrow": "fleet",
    "settings-fleet-sharing": "fleet",
    "settings-fleet-sharing-details": "fleet",
    "settings-fleet-sharing-history-narrow": "fleet",
}
_SYNTHETIC_OWNER_REPRESENTATIVES = (
    "settings-companions-source-narrow",
    "settings-wanderer",
    "settings-fleet-sharing",
)
_SYNTHETIC_OWNER_CASES = tuple(
    (scenario, key)
    for scenario in ("normal", "late-read", "late-synthetic", "invalid")
    for key in (
        tuple(SYNTHETIC)
        if scenario == "normal"
        else _SYNTHETIC_OWNER_REPRESENTATIVES
    )
)
LIVE = {
    "settings-uploading": "uploading",
    "settings-uploading-recording": "uploading",
    "settings-uploading-integrations": "uploading",
    "settings-uploading-webhook": "uploading",
    "settings-bookmarks-windows": "bookmarks",
    "settings-bookmarks-sigbar": "bookmarks",
    "settings-alerts-custom-narrow": "alerts",
}


SUBPAGES = {
    "settings-uploading": "youtube",
    "settings-uploading-recording": "recording",
    "settings-uploading-integrations": "recording",
    "settings-uploading-webhook": "combatlogs",
    "settings-previews": "windows",
    "settings-previews-middle": "windows",
    "settings-previews-table": "characters",
    "settings-previews-sticky-conflict": "characters",
    "settings-previews-detail": "characters",
    "settings-previews-copy": "characters",
    "settings-previews-groups": "characters",
    "settings-previews-narrow": "characters",
    "settings-previews-crop-narrow": "characters",
    "settings-wanderer": "wanderer",
    "settings-wanderer-narrow": "wanderer",
}

_VM_INTRINSIC_MUTATION = r"""
(() => {
  const domMarker = '__wingmanCurrentScreenshotDOMProbe';
  const Element = document.constructor;
  const domTargets = [
    ['document', document],
    ['Element', Element],
    ['Element.prototype', Element.prototype],
    ['document.getElementById', document.getElementById],
    ['Element.prototype.querySelector', Element.prototype.querySelector],
    ['document.attrs', document.attrs],
    ['document.children', document.children],
    ['document.style', document.style]
  ];
  for (const [name, target] of domTargets) {
    for (let value = target; value; value = Object.getPrototypeOf(value)) {
      value[domMarker] = name;
    }
  }
  document.constructor.constructor('return globalThis')()[domMarker] = 'global';

  const realmMarker = '__wingmanCurrentScreenshotRealmEscapeProbe';
  function realmOf(value) {
    if (value === null || value === undefined) return null;
    const constructor = value.constructor;
    if (typeof constructor !== 'function' ||
        typeof constructor.constructor !== 'function') return null;
    return constructor.constructor('return globalThis')();
  }
  const boundaries = [];
  function collect(label, owner) {
    if (!owner) return;
    for (const key of Reflect.ownKeys(owner)) {
      const descriptor = Object.getOwnPropertyDescriptor(owner, key);
      if (!descriptor) continue;
      for (const [kind, value] of [
        ['value', descriptor.value], ['get', descriptor.get], ['set', descriptor.set]
      ]) {
        if (typeof value === 'function') {
          boundaries.push([label + '.' + String(key) + '.' + kind, value]);
        }
      }
    }
  }
  collect('console', console);
  collect('clipboard', navigator.clipboard);
  collect('document', document);
  collect('Element.prototype', Element.prototype);
  collect('WM', WM);
  for (const [name, value] of Object.entries({
    Event, CustomEvent, Element, TextEncoder, URLSearchParams,
    setTimeout, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame, matchMedia, getComputedStyle
  })) boundaries.push([name, value]);
  const timerArgument = {request_local: true};
  const timeoutToken = setTimeout(function (value) {
    const realm = realmOf(this);
    if (realm) realm[realmMarker] = 'timeout callback receiver';
    if (value !== timerArgument) {
      throw new Error('timeout argument left the request VM');
    }
  }, 0, timerArgument);
  const frameToken = requestAnimationFrame(function (...args) {
    const realm = realmOf(this);
    if (realm) realm[realmMarker] = 'animation callback receiver';
    if (args.length) throw new Error('animation frame gained host arguments');
  });
  const returnedValues = [
    ['window', window], ['document', document], ['location', location],
    ['navigator', navigator], ['clipboard', navigator.clipboard],
    ['Event result', new Event('realm-probe')],
    ['CustomEvent result', new CustomEvent('realm-probe', {detail: timerArgument})],
    ['matchMedia result', matchMedia('(min-width: 1px)')],
    ['getComputedStyle result', getComputedStyle(document.body)],
    ['timeout token', Object(timeoutToken)], ['frame token', Object(frameToken)]
  ];
  for (const [name, callable] of boundaries) {
    const realm = realmOf(callable);
    if (realm) realm[realmMarker] = name;
  }
  for (const [name, value] of returnedValues) {
    const realm = realmOf(value);
    if (realm) realm[realmMarker] = name;
  }
  for (const name of ['readText', 'writeText']) {
    try {
      navigator.clipboard[name]('probe');
    } catch (error) {
      const realm = realmOf(error);
      if (realm) realm[realmMarker] = 'clipboard ' + name + ' error';
    }
  }
  const escaped = [...boundaries, ...returnedValues].filter(([, value]) => {
    const realm = realmOf(value);
    return realm && (realm !== globalThis || 'process' in realm);
  }).map(([name]) => name);
  if (escaped.length) {
    throw new Error('public boundary escaped the request VM: ' + escaped.join(', '));
  }

  const marker = '__wingmanCurrentScreenshotRequestProbe';
  for (const [name, intrinsic] of Object.entries(
    {Promise, Math, Date, TextEncoder, URLSearchParams}
  )) {
    const targets = [
      ['constructor', intrinsic],
      ['prototype', intrinsic.prototype],
      ['constructor-base', Object.getPrototypeOf(intrinsic)],
      ['instance-base', intrinsic.prototype && Object.getPrototypeOf(intrinsic.prototype)]
    ];
    for (const [level, target] of targets) {
      if (target) target[marker] = name + '.' + level;
    }
  }
  const returnedMarker = '__wingmanCurrentReturnedPrototypeProbe';
  const params = new URLSearchParams('a=1&a=2');
  const iterator = params.entries();
  const returned = [
    new TextEncoder().encode('probe'),
    params.getAll('a'),
    iterator,
    iterator.next().value
  ];
  for (const value of returned) {
    for (let target = Object.getPrototypeOf(value); target;
        target = Object.getPrototypeOf(target)) {
      target[returnedMarker] = 'mutated';
    }
  }
  let errorRealm;
  try {
    new TextEncoder().encode(Symbol('host-realm-probe'));
  } catch (error) {
    errorRealm = error.constructor.constructor('return globalThis')();
  }
  if (!errorRealm) throw new Error('TextEncoder Symbol did not fail');
  errorRealm.__wingmanCurrentHostRealmProbe = 'mutated';
  if (!Object.prototype.hasOwnProperty.call(
      globalThis, '__wingmanCurrentIntervalMutationRan')) {
    globalThis.__wingmanCurrentIntervalMutationRan = true;
    const marker = '__wingmanCurrentIntervalTokenProbe';
    const intervalId = setInterval(() => {}, 60000);
    try {
      if (Number.isInteger(intervalId) && intervalId !== 1) {
        throw new Error('first request interval ID was not request-local');
      }
      const wrapper = Object(intervalId);
      wrapper[marker] = 'wrapper';
      for (let target = Object.getPrototypeOf(wrapper); target;
          target = Object.getPrototypeOf(target)) {
        target[marker] = 'prototype';
      }
    } finally {
      clearInterval(intervalId);
    }
    let callbackInterval;
    callbackInterval = setInterval(function (value) {
      const realm = realmOf(this);
      if (realm) realm[realmMarker] = 'interval callback receiver';
      clearInterval(callbackInterval);
      if (value !== timerArgument) {
        throw new Error('interval argument left the request VM');
      }
    }, 0, timerArgument);
  }
})()
"""

_VM_INTRINSIC_PRISTINE = r"""
(() => {
  const domMarker = '__wingmanCurrentScreenshotDOMProbe';
  const Element = document.constructor;
  const domRealms = [
    ['document', document.constructor.constructor('return globalThis')()],
    ['Element', Element.constructor('return globalThis')()],
    ['document.getElementById',
      document.getElementById.constructor('return globalThis')()],
    ['Element.prototype.querySelector',
      Element.prototype.querySelector.constructor('return globalThis')()]
  ];
  for (const [name, realm] of domRealms) {
    if (realm !== globalThis || 'process' in realm) {
      throw new Error('DOM callable escaped the request VM: ' + name);
    }
  }
  const realmMarker = '__wingmanCurrentScreenshotRealmEscapeProbe';
  function realmOf(value) {
    if (value === null || value === undefined) return null;
    const constructor = value.constructor;
    if (typeof constructor !== 'function' ||
        typeof constructor.constructor !== 'function') return null;
    return constructor.constructor('return globalThis')();
  }
  const boundaries = [];
  function collect(label, owner) {
    if (!owner) return;
    for (const key of Reflect.ownKeys(owner)) {
      const descriptor = Object.getOwnPropertyDescriptor(owner, key);
      if (!descriptor) continue;
      for (const [kind, value] of [
        ['value', descriptor.value], ['get', descriptor.get], ['set', descriptor.set]
      ]) {
        if (typeof value === 'function') {
          boundaries.push([label + '.' + String(key) + '.' + kind, value]);
        }
      }
    }
  }
  collect('console', console);
  collect('clipboard', navigator.clipboard);
  collect('document', document);
  collect('Element.prototype', Element.prototype);
  collect('WM', WM);
  for (const [name, value] of Object.entries({
    Event, CustomEvent, Element, TextEncoder, URLSearchParams,
    setTimeout, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame, matchMedia, getComputedStyle
  })) boundaries.push([name, value]);
  const timerArgument = {request_local: true};
  const timeoutToken = setTimeout(function (value) {
    const realm = realmOf(this);
    if (realm && (realm !== globalThis || 'process' in realm)) {
      realm[realmMarker] = 'timeout callback receiver';
    }
    if (value !== timerArgument) {
      throw new Error('timeout argument left the request VM');
    }
  }, 0, timerArgument);
  const frameToken = requestAnimationFrame(function (...args) {
    const realm = realmOf(this);
    if (realm && (realm !== globalThis || 'process' in realm)) {
      realm[realmMarker] = 'animation callback receiver';
    }
    if (args.length) throw new Error('animation frame gained host arguments');
  });
  const returnedValues = [
    ['window', window], ['document', document], ['location', location],
    ['navigator', navigator], ['clipboard', navigator.clipboard],
    ['Event result', new Event('realm-probe')],
    ['CustomEvent result', new CustomEvent('realm-probe', {detail: timerArgument})],
    ['matchMedia result', matchMedia('(min-width: 1px)')],
    ['getComputedStyle result', getComputedStyle(document.body)],
    ['timeout token', Object(timeoutToken)], ['frame token', Object(frameToken)]
  ];
  for (const [name, value] of [...boundaries, ...returnedValues]) {
    const realm = realmOf(value);
    if (!realm || realm !== globalThis || 'process' in realm) {
      throw new Error('public boundary escaped the request VM: ' + name);
    }
    if (Object.prototype.hasOwnProperty.call(realm, realmMarker) ||
        Object.prototype.hasOwnProperty.call(value, realmMarker)) {
      throw new Error('public boundary leaked between requests: ' + name);
    }
  }
  for (const name of ['readText', 'writeText']) {
    try {
      navigator.clipboard[name]('probe');
    } catch (error) {
      const realm = realmOf(error);
      if (!realm || realm !== globalThis || 'process' in realm) {
        throw new Error('clipboard error escaped the request VM: ' + name);
      }
      if (Object.prototype.hasOwnProperty.call(realm, realmMarker)) {
        throw new Error('clipboard error realm leaked between requests: ' + name);
      }
    }
  }
  const domTargets = [
    ['document', document],
    ['Element', Element],
    ['Element.prototype', Element.prototype],
    ['document.getElementById', document.getElementById],
    ['Element.prototype.querySelector', Element.prototype.querySelector],
    ['document.attrs', document.attrs],
    ['document.children', document.children],
    ['document.style', document.style]
  ];
  for (const [name, target] of domTargets) {
    for (let value = target; value; value = Object.getPrototypeOf(value)) {
      if (Object.prototype.hasOwnProperty.call(value, domMarker)) {
        throw new Error('request DOM leaked: ' + name);
      }
    }
  }

  const marker = '__wingmanCurrentScreenshotRequestProbe';
  for (const [name, intrinsic] of Object.entries(
    {Promise, Math, Date, TextEncoder, URLSearchParams}
  )) {
    const targets = [
      ['constructor', intrinsic],
      ['prototype', intrinsic.prototype],
      ['constructor-base', Object.getPrototypeOf(intrinsic)],
      ['instance-base', intrinsic.prototype && Object.getPrototypeOf(intrinsic.prototype)]
    ];
    for (const [level, target] of targets) {
      if (target && Object.prototype.hasOwnProperty.call(target, marker)) {
        throw new Error('request intrinsic leaked: ' + name + '.' + level);
      }
    }
  }
  for (const name of [
    '__wingmanStartupPageJson', '__wingmanPayloadJson',
    '__wingmanWebSourcesJson', '__wingmanDomFactorySource',
    '__wingmanTimerScheduleAdapter', '__wingmanTimerClearAdapter',
    '__wingmanTextEncoderAdapter', '__wingmanURLSearchParamsAdapter',
    '__wingmanUnhandledAdapter', '__wingmanProtocolEventAdapter',
    '__wingmanCompleteAdapter'
  ]) {
    if (name in globalThis) {
      throw new Error('host adapter remained globally reachable: ' + name);
    }
  }
  if (!Object.prototype.hasOwnProperty.call(
      globalThis, '__wingmanCurrentIntervalPristineRan')) {
    globalThis.__wingmanCurrentIntervalPristineRan = true;
    const marker = '__wingmanCurrentIntervalTokenProbe';
    const firstIntervalId = setInterval(() => {}, 60000);
    const secondIntervalId = setInterval(() => {}, 60000);
    try {
      const wrapper = Object(firstIntervalId);
      for (let target = wrapper; target; target = Object.getPrototypeOf(target)) {
        if (Object.prototype.hasOwnProperty.call(target, marker)) {
          throw new Error('interval token prototype leaked between requests');
        }
      }
      if (!Number.isInteger(firstIntervalId) ||
          !Number.isInteger(secondIntervalId)) {
        throw new Error('interval ID exposed a host object');
      }
      if (firstIntervalId !== 1 || secondIntervalId !== 2) {
        throw new Error('interval IDs were not numeric and request-local');
      }
      wrapper[marker] = 'pristine-wrapper';
    } finally {
      clearInterval(firstIntervalId);
      clearInterval(secondIntervalId);
    }
    let callbackInterval;
    callbackInterval = setInterval(function (value) {
      const realm = realmOf(this);
      if (realm && (realm !== globalThis || 'process' in realm)) {
        realm[realmMarker] = 'interval callback receiver';
      }
      clearInterval(callbackInterval);
      if (value !== timerArgument) {
        throw new Error('interval argument left the request VM');
      }
    }, 0, timerArgument);
  }
  let adapterError;
  let errorRealm;
  try {
    new TextEncoder().encode(Symbol('host-realm-probe'));
  } catch (error) {
    adapterError = error;
    errorRealm = error.constructor.constructor('return globalThis')();
  }
  if (!errorRealm) throw new Error('TextEncoder Symbol did not fail');
  if (!(adapterError instanceof TypeError)) {
    throw new Error('TextEncoder host error was not reconstructed as TypeError');
  }
  if (errorRealm.__wingmanCurrentHostRealmProbe) {
    throw new Error('host realm marker leaked between requests');
  }
  if (errorRealm !== globalThis) {
    throw new Error('TextEncoder error escaped the request VM');
  }
  const returnedMarker = '__wingmanCurrentReturnedPrototypeProbe';
  const isolationParams = new URLSearchParams('a=1&a=2');
  const isolationIterator = isolationParams.entries();
  const returned = [
    new TextEncoder().encode('probe'),
    isolationParams.getAll('a'),
    isolationIterator,
    isolationIterator.next().value
  ];
  if (!(returned[0] instanceof Uint8Array) || !Array.isArray(returned[1]) ||
      !Array.isArray(returned[3]) ||
      isolationIterator[Symbol.iterator]() !== isolationIterator) {
    throw new Error('adapter result was not reconstructed in the request VM');
  }
  for (const value of returned) {
    for (let target = Object.getPrototypeOf(value); target;
        target = Object.getPrototypeOf(target)) {
      if (Object.prototype.hasOwnProperty.call(target, returnedMarker)) {
        throw new Error('returned value prototype leaked between requests');
      }
    }
  }
  const encoder = new TextEncoder();
  if (encoder.encoding !== 'utf-8' ||
      Array.from(encoder.encode('Aé𐐀')).join(',') !==
        '65,195,169,240,144,144,128') {
    throw new Error('request TextEncoder behavior changed');
  }
  const destination = new Uint8Array(2);
  const encoded = encoder.encodeInto('éA', destination);
  if (encoded.read !== 1 || encoded.written !== 2 ||
      Array.from(destination).join(',') !== '195,169') {
    throw new Error('request TextEncoder encodeInto behavior changed');
  }
  const params = new URLSearchParams('?a=1&a=2&space=hello+world');
  if (params.get('a') !== '1' || params.getAll('a').join(',') !== '1,2' ||
      params.get('space') !== 'hello world' || !params.has('a', '2')) {
    throw new Error('request URLSearchParams read behavior changed');
  }
  params.delete('a', '1');
  params.set('a', '3');
  params.append('b', 'two words');
  params.sort();
  const serialized = 'a=3&b=two+words&space=hello+world';
  if (params.size !== 3 || params.toString() !== serialized ||
      new URLSearchParams(params).toString() !== serialized ||
      Array.from(params.keys()).join(',') !== 'a,b,space' ||
      Array.from(params.values()).join(',') !== '3,two words,hello world') {
    throw new Error('request URLSearchParams mutation behavior changed');
  }
  const visited = [];
  params.forEach((value, name, owner) => {
    if (owner !== params) throw new Error('URLSearchParams owner changed');
    visited.push(name + '=' + value);
  });
  if (visited.join('&') !== 'a=3&b=two words&space=hello world') {
    throw new Error('request URLSearchParams iteration behavior changed');
  }
})()
"""


@pytest.fixture(scope="session")
def current_screenshot_markup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    path = tmp_path_factory.mktemp("current-screenshot-worker") / "page.json"
    path.write_text(json.dumps(tree.root, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def current_screenshot_worker(current_screenshot_markup: Path):
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    worker = NodeScenarioWorker(
        [
            node,
            str(ROOT / "tests/fixtures/current_screenshot_pages.cjs"),
            str(current_screenshot_markup),
            str(ROOT / "wingman/web"),
        ],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()


def test_current_screenshot_worker_isolates_owner_families(
    current_screenshot_worker: NodeScenarioWorker,
):
    companion_probe = {
        "expected_revision": 0,
        "expected_label": "Mapper",
        "expected_last_title": "Example map — home chain",
    }
    _request_current_page(
        current_screenshot_worker,
        "settings-companions-populated",
        "normal",
        probes={"companion_live_probe": {**companion_probe, "poison": True}},
    )
    process = current_screenshot_worker._proc
    _request_current_page(current_screenshot_worker, "settings-wanderer", "late-read")
    _request_current_page(
        current_screenshot_worker, "settings-fleet-sharing", "late-synthetic"
    )
    invalid = _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "invalid"
    )
    assert invalid["output"] == (
        "PASS current screenshot settings-companions-populated invalid"
    )
    _request_current_page(
        current_screenshot_worker,
        "settings-companions-populated",
        "normal",
        probes={"companion_live_probe": {**companion_probe, "poison": False}},
    )
    assert current_screenshot_worker._proc is process


def test_current_screenshot_worker_vm_failures_preserve_stack_and_recover(
    current_screenshot_worker: NodeScenarioWorker,
):
    screen = next(
        screen
        for screen in shoot.SCREENS
        if screen.key == "settings-companions-populated"
    )
    stage = shoot.screen_setup_script(screen)
    _request_current_page(
        current_screenshot_worker,
        "settings-companions-populated",
        "normal",
        probes={"stage": stage + ";" + _VM_INTRINSIC_MUTATION},
    )
    process = current_screenshot_worker._proc
    pristine = _request_current_page(
        current_screenshot_worker,
        "settings-companions-populated",
        "normal",
        probes={"stage": _VM_INTRINSIC_PRISTINE + ";" + stage},
    )
    assert pristine["output"] == (
        "PASS current screenshot settings-companions-populated normal"
    )
    assert current_screenshot_worker._proc is process
    for mode, stack_name in [
        ("vm-throw", "protocolVmThrow"),
        ("vm-reject", "protocolVmReject"),
    ]:
        with pytest.raises(NodeScenarioFailure) as failure:
            current_screenshot_worker.request(
                f"protocol/{mode}",
                {"protocol_probe": mode, "failure_logs": True},
                timeout=20.0,
            )
        assert stack_name in failure.value.stack
        assert failure.value.reply is not None
        logs = failure.value.reply.get("logs")
        assert isinstance(logs, list)
        assert 1 <= len(logs) <= 40
        assert all(isinstance(line, str) and len(line) <= 400 for line in logs)
        for level in ("log", "info", "warn", "debug"):
            assert any(f"protocol {level} context" in line for line in logs)
        assert any(line.endswith("…") for line in logs)
        recovered = _request_current_page(
            current_screenshot_worker, "settings-companions-populated", "normal"
        )
        assert recovered["output"] == (
            "PASS current screenshot settings-companions-populated normal"
        )
        assert current_screenshot_worker._proc is process

    for kind in ("getters", "proxy"):
        with pytest.raises(NodeScenarioFailure) as failure:
            current_screenshot_worker.request(
                f"protocol/vm-reject/{kind}",
                {
                    "protocol_probe": "vm-reject",
                    "hostile_rejection": kind,
                    "failure_logs": True,
                },
                timeout=20.0,
            )
        assert "protocolHostileReject" in failure.value.stack
        assert failure.value.reply is not None
        recovered = _request_current_page(
            current_screenshot_worker,
            "settings-companions-populated",
            "normal",
            probes={"assert_unhandled_host_pristine": True},
        )
        assert recovered["output"] == (
            "PASS current screenshot settings-companions-populated normal"
        )
        assert f"protocol hostile {kind} rejection" in str(failure.value.reply["error"])
        assert any(
            "protocol log context" in line
            for line in failure.value.reply.get("logs", [])
        )
        assert current_screenshot_worker._proc is process


@pytest.mark.parametrize(
    "mode",
    ["pending-timer-normal-exit", "pending-timer-assertion-exit"],
    ids=["pending-timer-normal-exit", "pending-timer-assertion-exit"],
)
def test_current_screenshot_worker_cancels_pending_timer(
    current_screenshot_worker: NodeScenarioWorker, mode: str
):
    _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "normal"
    )
    process = current_screenshot_worker._proc
    with pytest.raises(NodeScenarioFailure) as failure:
        current_screenshot_worker.request(
            f"protocol/{mode}", {"protocol_probe": mode}, timeout=20.0
        )
    expected_error = (
        "request left a live timer"
        if mode == "pending-timer-normal-exit"
        else "protocol cleanup probe failure"
    )
    assert failure.value.reply is not None
    assert str(failure.value.reply["error"]).splitlines()[0] == expected_error
    assert expected_error in failure.value.stack
    recovered = _request_current_page(
        current_screenshot_worker, "settings-companions-populated", "normal"
    )
    assert recovered["output"] == (
        "PASS current screenshot settings-companions-populated normal"
    )
    assert current_screenshot_worker._proc is process


@pytest.mark.parametrize(
    "key", [key for key in SUBPAGES if key.startswith("settings-previews")]
)
def test_preview_stages_select_visible_subpages_and_their_scroll_owner(
    current_screenshot_worker: NodeScenarioWorker, key: str
):
    _request_current_page(current_screenshot_worker, key, "preview-subpage")


def test_current_inventory_and_floor_coverage():
    screens = {s.key: s for s in shoot.SCREENS}
    assert screens.keys() >= SYNTHETIC.keys() | LIVE.keys()
    for key, section in (SYNTHETIC | LIVE).items():
        assert screens[key].section == section
        assert screens[key].at_floor == key.endswith("-narrow")
        assert screens[key].gated == (section not in {"companions", "uploading"})
        assert shoot.screen_setup_script(screens[key])
        assert shoot.new_screen_verify_script(screens[key])


@pytest.mark.parametrize(("scenario", "key"), _SYNTHETIC_OWNER_CASES)
def test_current_synthetic_owners(
    current_screenshot_worker: NodeScenarioWorker, key: str, scenario: str
):
    _request_current_page(current_screenshot_worker, key, scenario)


@pytest.mark.parametrize("key", LIVE)
def test_lower_cards_frame_live_content_without_actions(
    current_screenshot_worker: NodeScenarioWorker, key: str
):
    _request_current_page(current_screenshot_worker, key, "live-card")


@pytest.mark.parametrize(
    "key",
    ["settings-companions-populated", "settings-wanderer", "settings-fleet-sharing"],
)
def test_cleanup_before_any_live_hydration_erases_synthetic_content(
    current_screenshot_worker: NodeScenarioWorker, key: str
):
    _request_current_page(current_screenshot_worker, key, "cold")


def test_companion_capture_does_not_take_over_a_live_dialog(
    current_screenshot_worker: NodeScenarioWorker,
):
    _request_current_page(
        current_screenshot_worker, "settings-companions-source-narrow", "live-dialog"
    )


def _sharing_screenshot_status(*, live=False, newer=False, pending=False):
    """Independent observations, not values read back from the JS fixture."""
    from wingman.fleetsharing import protocol as p
    from wingman.fleetsharing.config import canonical_origin
    from wingman.fleetsharing.state import AutomaticState
    from wingman.fleetsharing.worker import (
        PendingSourceStatus,
        SharingMetadata,
        SharingStatus,
    )

    source_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    source_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    source_generation = 4 if newer else 3
    consent = p.Consent(0, 0, False, None, None, None, None)
    status = SharingStatus(
        "active",
        metadata=SharingMetadata(
            loaded=True,
            binding="screenshot-only-binding",
            paired_origin="https://authgd.example",
            device_id=source_a,
            has_session=True,
            session_expires_at="2026-09-07T12:30:00.000Z",
            feature_enabled=True,
            approved_capabilities=(p.SHARED_CAPABILITY,),
            session_approved_capabilities=(p.SHARED_CAPABILITY,),
            acknowledged_capabilities=(p.SHARED_CAPABILITY,),
        ),
        sources=p.Sources(
            (
                p.SourceView(
                    source_a, source_generation, 1, "active", None, None, None
                ),
                p.SourceView(source_b, 2, 2, "ended", "boss_lost", None, None),
            ),
            (
                p.SourceCharacter(1, "Aiga Otsolen", source_a, True, True),
                p.SourceCharacter(2, "Ariadne", source_b, False, True),
            ),
        ),
        eligibility=p.Eligibility(
            1,
            "ready",
            tuple(
                p.EligibilityEntry(
                    character,
                    source_a,
                    source_generation,
                    1,
                    "2026-09-07T12:00:10.000Z",
                )
                for character in (1, 2)
            ),
        ),
        observed_participation=p.Participation(True, 1),
        automatic=AutomaticState(observed_consent=consent),
        automatic_status=p.AutomaticStatus(consent, "none", "off", "none", None, ()),
        automatic_stage="settled",
    )
    if live or newer:
        # Distinct live observations prove cleanup neither retains synthetic
        # consent nor restores stale binding/generation authority.
        consent = p.Consent(
            2 if newer else 1,
            2 if newer else 1,
            True,
            source_a,
            "2026-09-07T12:00:01.000Z" if newer else "2026-09-07T12:00:00.000Z",
            None,
            None,
        )
        capabilities = (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)
        status = replace(
            status,
            metadata=replace(
                status.metadata,
                binding="live-newer-binding" if newer else "live-only-binding",
                paired_origin="https://newer.example"
                if newer
                else "https://live.example",
                approved_capabilities=capabilities,
                session_approved_capabilities=capabilities,
                acknowledged_capabilities=capabilities,
            ),
            automatic=AutomaticState(observed_consent=consent),
            automatic_status=p.AutomaticStatus(
                consent, "this_device", "waiting_for_fleet", "none", None, ()
            ),
        )

    if pending:
        # An already-persisted live request exercises the separate worklist;
        # constructing this observation does not enqueue or execute a command.
        command = p.SourceStart(
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            1,
            source_a,
            "2026-09-07T12:00:01.000Z",
        )
        assert p.parse_source_command(p.source_command_body(command)) == command
        status = replace(
            status,
            pending_sources=(
                PendingSourceStatus(
                    command.source_id, "start", 1, "persisted", command
                ),
            ),
        )

    # Dataclasses do not validate wire enums, completeness or contradictions.
    # Round-trip observations through the real pure codecs before projecting.
    assert p.parse_consent(asdict(consent)) == consent
    assert (
        p.parse_automatic_status(_sharing_json(asdict(status.automatic_status)))
        == status.automatic_status
    )
    assert (
        p.parse_participation(asdict(status.observed_participation))
        == status.observed_participation
    )
    assert (
        p.parse_sources(
            {"protocol": p.API_VERSION, **_sharing_json(asdict(status.sources))}
        )
        == status.sources
    )
    assert (
        p.parse_eligibility(
            {"protocol": p.API_VERSION, **_sharing_json(asdict(status.eligibility))}
        )
        == status.eligibility
    )
    metadata = status.metadata
    for capabilities in (
        metadata.approved_capabilities,
        metadata.session_approved_capabilities,
        metadata.acknowledged_capabilities,
    ):
        assert p.capabilities(list(capabilities)) == capabilities
    assert canonical_origin(metadata.paired_origin) == metadata.paired_origin
    return status


def _sharing_json(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _sharing_screenshot_projection(*, live=False, newer=False, pending=False):
    from wingman.fleetsharing import config
    from wingman.ui.api import Api

    status = _sharing_screenshot_status(live=live, newer=newer, pending=pending)
    # No Api/worker construction: this read needs detached observations and a
    # liveness sentinel, never a real runtime, network, DPAPI or native owner.
    receiver = SimpleNamespace(
        _sharing_delivery_lock=RLock(),
        _sharing_status=status,
        _sharing_controls=Api._sharing_controls,
        _fleet_sharing=object(),
        _sharing_closed=False,
        _sharing_enabled=True,
        _sharing_preference_order=0,
        _sharing_preference_error=None,
        _sharing_runtime_error=None,
        _sharing_browser_error=None,
        _sharing_browser_retry=None,
        _sharing_telemetry_available=True,
        _sharing_presentation=None,
        _sharing_presentation_order=0,
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            config, "resolve_relay_origin", lambda: status.metadata.paired_origin
        )
        return _sharing_json(Api.fleet_sharing_state(receiver))


def _assert_sharing_projection(actual, expected, path=()):
    # Equality alone accepts bool/int substitutions, including inside arrays.
    assert type(actual) is type(expected), (path, actual, expected)
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), (path, actual.keys(), expected.keys())
        for key, value in expected.items():
            _assert_sharing_projection(actual[key], value, (*path, key))
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (path, len(actual), len(expected))
        for index, value in enumerate(expected):
            _assert_sharing_projection(actual[index], value, (*path, index))
    else:
        assert actual == expected, (path, actual, expected)


def test_sharing_screenshot_fixture_uses_current_control_projection():
    state = shoot.load_dev_tool_screenshot_fixture()["fleet"]["sharing"]["state"]
    _assert_sharing_projection(state, _sharing_screenshot_projection())


def _sharing_projection_mutations(value, path=()):
    """Derive guard probes from the real DTO, not another hand-kept schema."""
    if isinstance(value, dict):
        yield "extra-key", path, dict(value, unexpected=None)
        for key, item in value.items():
            yield "missing-key", path, {k: v for k, v in value.items() if k != key}
            yield from _sharing_projection_mutations(item, (*path, key))
    elif isinstance(value, list):
        yield "extra-item", path, [*value, value[0] if value else None]
        if value:
            yield "missing-item", path, value[1:]
        if len(value) > 1 and value != value[::-1]:
            yield "reordered-items", path, value[::-1]
        for index, item in enumerate(value):
            yield from _sharing_projection_mutations(item, (*path, index))
    elif type(value) is bool:
        yield "bool-as-int", path, int(value)
        yield "changed-bool", path, not value
    elif type(value) is int:
        yield "int-as-float", path, float(value)
        yield "changed-int", path, value + 1
        if value in (0, 1):
            yield "int-as-bool", path, bool(value)
    elif isinstance(value, str):
        yield "stale-string", path, "stale-" + value
    elif value is None:
        yield "changed-null", path, False


@pytest.mark.parametrize(
    "fault",
    [
        "missing-key",
        "extra-key",
        "missing-item",
        "extra-item",
        "reordered-items",
        "bool-as-int",
        "int-as-bool",
        "int-as-float",
        "changed-bool",
        "changed-int",
        "stale-string",
        "changed-null",
    ],
)
def test_sharing_screenshot_projection_guard_rejects_drift(fault):
    expected = _sharing_screenshot_projection()
    _assert_sharing_projection(deepcopy(expected), expected)
    cases = 0
    for kind, path, replacement in _sharing_projection_mutations(expected):
        if kind != fault:
            continue
        changed = deepcopy(expected)
        if path:
            owner = changed
            for step in path[:-1]:
                owner = owner[step]
            owner[path[-1]] = replacement
        else:
            changed = replacement
        with pytest.raises(AssertionError):
            _assert_sharing_projection(changed, expected)
        cases += 1
    assert cases, f"No projection paths exercise {fault}"


@pytest.mark.parametrize(
    "case",
    [
        "cold",
        "live-before",
        "live-during",
        "cold-then-live",
        "repeat",
        "authority",
        "focus",
        "worklists",
    ],
)
def test_sharing_screenshot_lifecycle_preserves_live_authority(
    current_screenshot_worker: NodeScenarioWorker, case: str
):
    _request_current_page(
        current_screenshot_worker,
        "settings-fleet-sharing",
        "sharing-lifecycle-" + case,
    )


@pytest.mark.parametrize("evidence", ["cached", "same", "newer"])
def test_sharing_cleanup_preserves_failed_refresh_authority(
    current_screenshot_worker: NodeScenarioWorker, evidence: str
):
    _request_current_page(
        current_screenshot_worker, "settings-fleet-sharing", "sharing-read-" + evidence
    )


@pytest.mark.parametrize("delivery", ["live", "buffered"])
def test_wanderer_cleanup_obeys_live_binding_health_fence(
    current_screenshot_worker: NodeScenarioWorker, delivery: str
):
    _request_current_page(
        current_screenshot_worker, "settings-wanderer", "wanderer-fence-" + delivery
    )


@pytest.mark.parametrize(
    "action", ["toggle-button", "toggle-check", "reset", "character", "overlap"]
)
def test_fleet_capture_refuses_pending_live_writes(
    current_screenshot_worker: NodeScenarioWorker, action: str
):
    _request_current_page(
        current_screenshot_worker,
        "settings-fleet-characters-narrow",
        "fleet-pending-" + action,
    )


@pytest.mark.parametrize("action", ["pair", "grant", "overlap"])
def test_sharing_capture_refuses_pending_browser_actions(
    current_screenshot_worker: NodeScenarioWorker, action: str
):
    _request_current_page(
        current_screenshot_worker,
        "settings-fleet-sharing",
        "sharing-pending-" + action,
    )


def test_fleet_cleanup_restores_focused_master_without_changing_live_focus_policy(
    current_screenshot_worker: NodeScenarioWorker,
):
    _request_current_page(
        current_screenshot_worker, "settings-fleet-characters-narrow", "fleet-focused"
    )


def _request_current_page(
    worker: NodeScenarioWorker,
    key: str,
    scenario: str,
    *,
    probes: dict[str, object] | None = None,
) -> dict[str, object]:
    screen = next((s for s in shoot.SCREENS if s.key == key), None)
    assert screen, f"missing current capture: {key}"
    payload: dict[str, object] = {
        "key": key,
        "section": screen.section,
        "scenario": scenario,
        "prepare": shoot.new_screen_prepare_script(screen),
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
        "fixture": shoot.load_dev_tool_screenshot_fixture(),
        "tab": SUBPAGES.get(key),
    }
    if screen.section == "fleet":
        payload["live_sharing"] = _sharing_screenshot_projection(live=True)
        payload["live_sharing_newer"] = _sharing_screenshot_projection(
            live=True, newer=True, pending=scenario == "sharing-lifecycle-worklists"
        )
    if probes:
        payload.update(probes)
    return worker.request(f"{key}/{scenario}", payload, timeout=20.0)


@pytest.mark.parametrize(
    "key",
    ["settings-companions-populated", "settings-fleet-sharing-history-narrow"],
)
@pytest.mark.parametrize(
    "failure", [None, "prepare", "entry", "stage", "verify", "capture"]
)
def test_current_walk_prepares_before_entry_and_always_cleans(
    tmp_path, monkeypatch, key, failure
):
    screen = next((s for s in shoot.SCREENS if s.key == key), None)
    assert screen, f"missing current capture: {key}"
    monkeypatch.setattr(shoot, "SCREENS", (screen,))
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    expressions = {
        "prepare": shoot.new_screen_prepare_script(screen),
        "entry": f"WM.openSettingsSection({screen.section!r})",
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
    }
    calls = []

    class CDP:
        def evaluate(self, expression):
            calls.append(expression)
            if expression == "WM.eve_shown !== false":
                return True
            if failure and expression == expressions.get(failure):
                raise shoot.TargetError("injected " + failure)
            return None

        def screenshot(self):
            calls.append("capture")
            if failure == "capture":
                raise shoot.TargetError("injected capture")
            return b"png"

        def set_device_metrics_override(self, *, width, height):
            assert (width, height) == (840, 625)
            calls.append("floor")

        def clear_device_metrics_override(self):
            calls.append("clear")

    shots, _, _ = shoot.walk(CDP(), tmp_path, settle_ms=0)
    assert bool(shots[0]["error"]) == bool(failure)
    assert shots[0]["fixture"] == "wingman/web/dev.js:DEV_TOOL_SCREENSHOT_FIXTURE"
    assert expressions["cleanup"] in calls
    if failure != "prepare":
        assert calls.index(expressions["prepare"]) < calls.index(expressions["entry"])
    if screen.at_floor:
        assert calls.index("floor") < calls.index(expressions["prepare"])
        assert calls[-1] == "clear"
