"""Synthetic setup fixtures; never read a user's settings directory.

The public Jotunn context is recognized; identities and setup content are invented.
Public canonical regression data is separately labeled in test_ui_setup_v24.py.

Factories reload JSON so mutating one review/document cannot mutate a later
case. The portable fixture is hand-authored independently of the DAT fixtures,
not computed by a projection that could duplicate an adapter's mistakes.
"""

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from wingman.evesettings import codec

_FIXTURES = Path(__file__).parent / "fixtures" / "ui_setup"


@dataclass(frozen=True)
class ProfileFixture:
    root: Path
    server: Path
    profile: Path
    account_path: Path
    character_path: Path


def wire() -> dict:
    return json.loads((_FIXTURES / "wingman-preset.json").read_text(encoding="utf-8"))


def wire_with_tabs(count, *, group_count=1) -> dict:
    """Invented complete tabs, with interleaved groups and exact active geometry."""
    data = wire()
    templates = data["overview"]["tabs"]
    data["overview"]["tabs"] = [
        {
            **copy.deepcopy(templates[i % len(templates)]),
            "id": i,
            "name": f"Synthetic tab {i}",
        }
        for i in range(count)
    ]
    data["overview"]["windowGroups"] = [
        list(range(i, count, group_count)) for i in range(group_count)
    ]
    fixed = [
        w for w in data["layout"]["windows"] if not w["key"].startswith("overview")
    ]
    data["layout"]["windows"] = [
        {
            "key": "overview" if i == 0 else f"overview_{i}",
            "geometry": [100 * i, 40, 300, 400, 1920, 1080],
            "state": {"open": True},
        }
        for i in range(group_count)
    ] + fixed
    return data


def native_with_tabs(count) -> dict:
    """Extend only invented tab records in the existing synthetic native fixture."""
    data = yaml.safe_load(
        (_FIXTURES / "native-complete.yaml").read_text(encoding="utf-8")
    )
    templates = data["tabSetup"]
    data["tabSetup"] = []
    for i in range(count):
        fields = copy.deepcopy(templates[i % len(templates)][1])
        next(pair for pair in fields if pair[0] == "name")[1] = f"Synthetic tab {i}"
        data["tabSetup"].append([i, fields])
    return data


def source_with_tabs(count) -> tuple[codec.Document, codec.Document]:
    """Physical source slots built without any production projection or writer."""
    account, character = documents()
    overview = account.doc["bytes:overview"]
    templates = list(overview["bytes:tabsettings_new"]["tuple"][1].values())
    overview["bytes:tabsettings_new"]["tuple"][1] = {
        f"int:{i}": {
            **copy.deepcopy(templates[i % len(templates)]),
            "bytes:name": f"utf8:Synthetic tab {i}",
        }
        for i in range(count)
    }
    overview["bytes:tabsByWindowInstanceID"]["tuple"][1] = [list(range(count))]
    return account, character


def documents(case="source") -> tuple[codec.Document, codec.Document]:
    if case not in ("source", "recipient"):
        raise ValueError(f"Unknown synthetic setup case: {case}")

    def load(kind):
        value = json.loads(
            (_FIXTURES / f"{case}-{kind}.json").read_text(encoding="utf-8")
        )
        return codec.Document(**value)

    return load("account"), load("character")


def install_lossless_codec(monkeypatch) -> None:
    """Replace only subprocess transport, not verification or filesystem effects."""

    def transport(mode, payload, **kwargs):
        if mode == "encode":
            return b"\x7d" + payload
        assert mode == "decode" and payload.startswith(b"\x7d")
        return payload[1:]

    monkeypatch.setattr(codec, "_run", transport)
    monkeypatch.setattr(codec, "codec_available", lambda: True)


def seed_profile(tmp_path, *, case="recipient", name="Base") -> ProfileFixture:
    """Seed test-only files through the real codec writer and atomic publication.

    Install the lossless transport first for portable tests. The YAML/INI are
    deliberately invented byte sentinels, not a claim about EVE's display schema.
    """
    account, character = documents(case)
    root = tmp_path / "EVE"
    server = root / "c_eve_sharedcache_tq_tranquility"
    profile = server / f"settings_{name}"
    profile.mkdir(parents=True)
    account_id, character_id = (10, 11) if case == "source" else (20, 30)
    account_path = profile / f"core_user_{account_id}.dat"
    character_path = profile / f"core_char_{character_id}.dat"
    for path, document in ((account_path, account), (character_path, character)):
        # These files do not exist yet; there is no previous content to back up.
        codec.write_document(path, document, backup=lambda path: None)
    if case == "source":
        yaml_bytes = b"# synthetic source local preferences\nuiScale: 1.0\n"
        ini_bytes = b"; synthetic source local preferences\nmonitor=1\n"
    else:
        yaml_bytes = b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n"
        ini_bytes = b"; synthetic recipient local preferences\r\nmonitor=2\r\n"
    (profile / "core_public__.yaml").write_bytes(yaml_bytes)
    (profile / "prefs.ini").write_bytes(ini_bytes)
    return ProfileFixture(root, server, profile, account_path, character_path)
