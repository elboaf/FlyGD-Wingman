"""Profiles runtime ownership: selection, identification, workers and mutations.

All Profiles locks and process caches live here. Named ports retain UI and
infrastructure ownership outside this module without exposing bridge transport.
The live settings document is shared by reference; never retain a nested section
across its canonical update, which rebuilds sections in place.
"""

import contextlib
import datetime
import logging
import os
import stat
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import atomicio
from .. import settings as settings_mod
from . import backup as evesettings_backup
from . import characters as evesettings_characters
from . import codec as evesettings_codec
from . import formation_sharing as evesettings_formation_sharing
from . import formations as evesettings_formations
from . import identity as evesettings_identity
from . import names as evesettings_names
from . import ops as evesettings_ops
from . import profilecopy as evesettings_profilecopy
from . import selective as evesettings_selective
from . import setup_documents, setup_model, setup_profile, setup_sharing
from . import tree as evesettings_tree

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfilesPorts:
    """Named effects only; spawn returns an unstarted worker handle.

    UI collaborators are resolved by composition adapters at invocation time.
    Confirmation is bounded even when the page never answers. No port is called
    during construction, and none exposes an arbitrary page handler name.
    """

    publish_running: Callable[[dict], None]
    publish_names: Callable[[dict], None]
    publish_done: Callable[[dict], None]
    alert: Callable[[str, str, str], None]
    status: Callable[[str], None]
    confirm: Callable[..., bool]
    choose_root: Callable[[str], str]
    choose_setup_input: Callable[[], str]
    choose_setup_output: Callable[[str], str]
    spawn: Callable[..., threading.Thread]
    advisory_client_running: Callable[[], bool]
    strict_client_running: Callable[[], bool]
    profile_copy_refusal: Callable[[], str | None]
    backup_root: Callable[[], Path]
    update_settings: Callable[[dict], None]
    format_copy_confirm: Callable[..., str]
    format_copy_done: Callable[..., str]


def _eve_same_path(candidate: Path | None, requested) -> bool:
    """Whether *candidate* IS the path the caller named, not a fallback
    discover() supplied for it.

    discover() falls back to the first server/profile it finds when a
    requested token matches nothing on disk, so comparing the requested
    token against the RESULT can't tell a genuine selection from a
    fabricated one that happened to land on the default. Two-way
    containment (rather than a lexical `==`) is what tree.py's own
    equality-through-is_under idiom uses, and it is what makes this call
    resilient to a trailing separator or an unresolved symlink either
    side names the same directory with.
    """
    if candidate is None:
        return False
    return evesettings_tree.is_under(
        candidate, requested
    ) and evesettings_tree.is_under(requested, candidate)


@dataclass(frozen=True)
class _EveContext:
    """The Profiles selection a resolver pass may speak for.

    Canonical paths -- realpath plus platform case folding, the same
    identity rule evesettings.tree containment uses -- because a pass that
    started on one selection must not clean or repaint another that merely
    spells its folder differently.

    `datasource` is ESI's, and it is empty for anything but a server this
    process could positively identify as Tranquility. Empty therefore means
    "no authoritative status source": no deletion verdict may be recorded
    against it, none may be read for it, and no account identity metadata
    -- which this product interprets as Tranquility's -- may be applied.
    """

    root: str = ""
    server: str = ""
    profile: str = ""
    datasource: str = ""

    @property
    def trusted(self) -> bool:
        return bool(self.datasource)


# What a context had already published: (id, name) pairs and deleted ids.
_EVE_NO_FACTS: tuple[frozenset, frozenset] = (frozenset(), frozenset())


@dataclass(frozen=True)
class _EveCandidate:
    """One offered account/character pair, and what authorized it.

    `generation` is the identification generation the observation behind
    this offer was made under. It travels WITH the pair rather than beside
    it so a publication cannot half-happen: an offer that outlives its
    generation -- cancelled, superseded, or invalidated by a learned
    deletion -- is recognizable as stale by the value it carries, both here
    and on the page one round trip later.
    """

    generation: int
    account_id: str
    character_ids: tuple[str, ...]


@dataclass(frozen=True)
class _SetupReview:
    review_id: str
    text: str
    keep_ship_labels: bool
    selection_context: _EveContext
    generation: int
    plan: evesettings_profilecopy.ProfileCopyPlan
    account_filename: str
    character_filename: str
    account_id: str
    character_id: str
    manifest: setup_profile.ProfileManifest


# Saved account names and links carry no datasource, so this product reads
# them as Tranquility's. Elsewhere they are not applied and not editable --
# a migration would be disproportionate for a feature used off Tranquility
# about never, and a Tranquility verdict must not rewrite another shard.
_EVE_IDENTITY_UNAVAILABLE = (
    "Account identity is available only for Tranquility profiles."
)
_EVE_CHARACTER_DELETED = "That character no longer exists."
_EVE_CLEANUP_FAILED = "Could not remove deleted character links."


class ProfilesController:
    """One owner of the complete Profiles synchronization topology."""

    def __init__(self, settings: dict, *, ports: ProfilesPorts):
        self._settings = settings
        self._ports = ports
        # One mutation at a time. A per-mutation worker says nothing about
        # how many may exist at once, and confirmation parks each one
        # independently -- so two operations approved moments apart could
        # otherwise interleave over the same files.
        self._eve_mutation = threading.Lock()
        # Identification state is reached by the bridge thread (start,
        # check, confirm, cancel) and by the resolver worker (a learned
        # deletion invalidates the offer it names). Its own lock, held only
        # to read, clear, or compare-and-publish the three fields below --
        # never across discovery, an ESI call, a settings write or a
        # dialog. LOCK ORDER IS FIXED: _eve_mutation may be taken before
        # this one, NEVER after, so cleanup (which owns _eve_mutation) and
        # a cancellation (which must never wait for it) cannot deadlock.
        self._eve_identification_lock = threading.Lock()
        # Monotonic for the process. Every invalidation -- cancel, restart,
        # selection change, learned deletion -- claims a new number, which
        # is what makes "this answer was computed before that event"
        # decidable here and on the page.
        self._eve_identification_generation = 0
        # A snapshot exists only during an explicit identification pass.
        # Timestamps are evidence for that pass, never durable identity.
        self._eve_identification = None
        # The latest observed account and the characters it offered. This is
        # ephemeral authorization for confirmation, not persisted identity.
        self._eve_identification_candidate: _EveCandidate | None = None
        # Process-lifetime memo. Names are cosmetic and free to re-fetch.
        self._eve_names = evesettings_names.NameCache()
        # (datasource, character id) pairs ESI explicitly reported as
        # deleted. Monotonic for the process and NEVER persisted: a launch
        # that cannot reach ESI must not inherit a blacklist from an
        # obsolete answer, and every launch revalidates when Profiles opens.
        # "Active" is deliberately not cached here -- see the resolver.
        self._eve_deleted: set[tuple[str, int]] = set()
        # What each canonical context last PUBLISHED. Remote facts are
        # global; applying them to a selection is not, so a trailing pass
        # can push what a superseded pass merely learned, and a pass that
        # changes nothing for its own context stays silent.
        self._eve_applied: dict[_EveContext, tuple[frozenset, frozenset]] = {}
        # Single-flight with one coalesced trailing pass. Held only to read
        # and write the two flags below -- never across a network call, a
        # settings write, or a spawn.
        self._eve_resolve_lock = threading.Lock()
        self._eve_resolve_running = False
        self._eve_resolve_pending = False
        # Last known answer for the advisory "EVE running" pill, or None
        # for "nobody has looked yet". None rather than False because the
        # pill is the ONLY warning before a copy, and False is the
        # reassuring guess: the probe is off the bridge thread precisely
        # because its first, uncached pass is slow, so a fabricated
        # "EVE closed" would be on screen for exactly as long as it takes
        # to be wrong about. The page renders the third state as
        # "Checking...". Read on the bridge thread, written by the probe;
        # a plain assignment, so no lock is needed for coherence.
        self._eve_running = None
        # One probe at a time. eve_settings_state() fires one on every
        # call -- route open, and after every mutation -- so two easily
        # overlap, and a slow probe finishing after a fast one would
        # otherwise publish the OLDER observation and leave it cached.
        self._eve_probe = threading.Lock()
        # Only original text/choices and immutable filesystem/context authority;
        # parsed models and recipient documents never outlive a review call.
        self._setup_review: _SetupReview | None = None

    @staticmethod
    def _field_ok(persisted: bool = True) -> dict:
        return {"applied": True, "persisted": persisted, "error": None}

    @staticmethod
    def _field_refused(error: str) -> dict:
        return {"applied": False, "persisted": False, "error": error}

    def _eve_section(self) -> dict:
        # validated_eve_settings, not the private _eve_settings_defaults:
        # it is the public surface for this section, and it already returns
        # a fresh dict per call rather than the module global. Reaching
        # across a module boundary for a private name is how a caller ends
        # up depending on something the owning module is free to rename.
        return self._settings.setdefault(
            "eve_settings", settings_mod.validated_eve_settings({})
        )

    def _eve_clear_identification(self) -> int:
        """Discard the observation and any pair it authorized.

        Claims a new generation as it goes, and returns it: everything
        computed under the old number -- an in-flight publication here, a
        rendered offer on the page -- is stale from this moment.
        """
        with self._eve_identification_lock:
            return self._eve_clear_identification_locked()

    def _eve_clear_identification_locked(self) -> int:
        """_eve_clear_identification for a caller that already holds the lock."""
        self._eve_identification_generation += 1
        self._eve_identification = None
        self._eve_identification_candidate = None
        return self._eve_identification_generation

    def _eve_generation(self) -> int:
        """The identification generation, read atomically."""
        with self._eve_identification_lock:
            return self._eve_identification_generation

    def _eve_identification_state(
        self,
    ) -> tuple[int, evesettings_identity.Snapshot | None, _EveCandidate | None]:
        """Generation, observation and offer, as one coherent reading."""
        with self._eve_identification_lock:
            return (
                self._eve_identification_generation,
                self._eve_identification,
                self._eve_identification_candidate,
            )

    def _eve_identification_cancelled_locked(self) -> dict:
        """The answer to a pass whose generation was claimed by someone else.

        No error text: nothing failed. The user (or a confirmed deletion)
        ended this pass while it was still working, and the number tells
        the page that this response is the older of the two it holds.
        """
        return {
            "status": "cancelled",
            "error": None,
            "identification_generation": self._eve_identification_generation,
        }

    def _eve_account_identity(self, account_id: str, names=None, links=None) -> dict:
        section = self._eve_section()
        return evesettings_identity.account_identity(
            account_id,
            section.get("account_names") or {} if names is None else names,
            section.get("account_characters") or {} if links is None else links,
            lambda character_id: self._eve_names.label(int(character_id)),
        )

    def _eve_identity(self, path, names=None, links=None) -> dict:
        """One display representation for every Profiles identity surface.

        `names`/`links` are the account metadata to apply. They are passed
        explicitly rather than read here so one state request decides ONCE
        whether Tranquility metadata may be applied at all -- the answer
        depends on the discovered server, and re-deriving it per row would
        cost a discovery pass per file.
        """
        kind = evesettings_tree.file_kind(path)
        ident = evesettings_tree.file_id(path)
        if kind == "character" and ident.isdigit():
            primary = self._eve_names.label(int(ident))
            return {
                "primary": primary,
                "secondary": f"Character {ident}",
                "option": primary,
            }
        if kind == "account" and ident:
            return self._eve_account_identity(ident, names, links)
        primary = Path(path).stem
        return {"primary": primary, "secondary": "", "option": primary}

    def _eve_label(self, path) -> str:
        """The compact label shared by pickers, confirmations and status."""
        return self._eve_identity(path)["option"]

    def _eve_backup_identity(self, item, names=None, links=None) -> tuple[str, str]:
        if item.kind in ("character", "account"):
            prefix = "core_char_" if item.kind == "character" else "core_user_"
            suffix = item.stem.removeprefix(prefix)
            if suffix != item.stem and suffix.isascii() and suffix.isdigit():
                identity = self._eve_identity(f"{item.stem}.dat", names, links)
                if item.kind == "account":
                    return identity["primary"], identity["secondary"]
                return identity["primary"], f"Character {suffix}"
            return item.stem, item.kind.title()
        if item.kind == "profile":
            return item.stem.removeprefix("settings_"), "Profile"
        return item.stem, item.kind.title()

    @staticmethod
    def _eve_canonical(path) -> str:
        """realpath plus platform case folding, or "" for nothing selected."""
        if not path:
            return ""
        return os.path.normcase(os.path.realpath(os.path.expandvars(str(path))))

    def _eve_context(self, found) -> _EveContext:
        """The context *found* speaks for, and whether it can be trusted.

        Trust needs BOTH halves. `_shard()` calls anything containing
        "tranquil" Tranquility, which is right for a label and far too
        permissive for a persisted deletion, so the strict predicate has to
        agree -- and the server must be one discovery actually offered under
        that key, not a stale stored string.
        """
        server = self._eve_canonical(found.server)
        known = next(
            (s for s in found.servers if self._eve_canonical(s.path) == server), None
        )
        trusted = bool(
            server
            and known is not None
            and known.key == "tranquility"
            and evesettings_tree.is_tranquility_server(found.server)
        )
        return _EveContext(
            root=self._eve_canonical(found.root),
            server=server,
            profile=self._eve_canonical(found.profile),
            datasource="tranquility" if trusted else "",
        )

    def _eve_account_identity_available(self, found) -> bool:
        """Whether saved account names and links apply to this selection."""
        return self._eve_context(found).trusted

    def _eve_deleted_ids(self, found) -> set[str]:
        """Ids confirmed deleted that this selection would otherwise show.

        Empty for an untrusted context, whatever the cache holds: a
        Tranquility verdict is not evidence about another shard.
        """
        context = self._eve_context(found)
        if not context.trusted:
            return set()
        candidates = {r.file_id for r in found.characters if r.file_id.isdigit()}
        candidates.update(
            character_id
            for values in (self._eve_section().get("account_characters") or {}).values()
            for character_id in values
            if character_id.isdigit()
        )
        return {
            character_id
            for character_id in candidates
            if (context.datasource, int(character_id)) in self._eve_deleted
        }

    def _eve_is_deleted(self, character_id) -> bool:
        """One confirmed-deleted id, without a discovery pass.

        Account metadata is Tranquility's by definition (there is no
        datasource in the schema), so a Tranquility verdict disqualifies an
        id from being linked regardless of what is selected right now.
        """
        return (
            isinstance(character_id, str)
            and character_id.isascii()
            and character_id.isdigit()
            and ("tranquility", int(character_id)) in self._eve_deleted
        )

    def _eve_prune_deleted_links_locked(self, deleted_ids: set) -> bool:
        """Drop *deleted_ids* from every saved account. Caller holds the lock.

        True when no saved link references a deleted id any more -- both
        "there was nothing to do" and "pruned and persisted". False means the
        write failed and the links are still saved, which is the pending
        state: the payload keeps hiding them, the next pass retries, and an
        account edit is refused until it succeeds.
        """
        if not deleted_ids:
            return True
        section = self._eve_section()
        saved = section.get("account_characters") or {}
        pruned = {
            account_id: [c for c in character_ids if c not in deleted_ids]
            for account_id, character_ids in saved.items()
        }
        pruned = {
            account_id: character_ids
            for account_id, character_ids in pruned.items()
            if character_ids
        }
        if pruned == saved:
            return True
        try:
            self._ports.update_settings({"account_characters": pruned})
        except OSError:
            # Ids only. Account names are private local metadata and never
            # belong in a log line.
            logger.exception(
                "Could not remove deleted EVE character links %s", sorted(deleted_ids)
            )
            return False
        return True

    def _eve_describe_file(self, record, identity_names, identity_links) -> dict:
        identity = self._eve_identity(record.path, identity_names, identity_links)
        item = {
            "path": str(record.path),
            "id": record.file_id,
            "name": identity["option"],
            "display_name": identity["primary"],
            "display_meta": identity["secondary"],
        }
        if record.kind == "account":
            item["account_name"] = identity_names.get(record.file_id, "")
            item["character_ids"] = list(identity_links.get(record.file_id, []))
        return item

    def state(self) -> dict:
        """The whole visible tree. Cheap enough to answer on the bridge
        thread: scandir over a few dozen files, and listing backups is one
        listdir with no archive opened.

        The one thing here that is NOT that -- the running-client probe --
        runs on a background thread and is read from cache below."""
        self._eve_refresh_running()
        section = self._eve_section()
        root = section.get("root")
        found = evesettings_tree.discover(
            root, section.get("server"), section.get("profile")
        )
        store = self._ports.backup_root()
        # Decided ONCE per request, from the discovered server: whether this
        # selection may wear Tranquility's account metadata, and which of
        # its characters ESI has confirmed deleted. Nothing below re-derives
        # either, and found.characters is never mutated -- only the payload
        # is filtered, so discovery stays a pure inventory of local files.
        identity_available = self._eve_account_identity_available(found)
        deleted_ids = self._eve_deleted_ids(found)
        identity_names = (
            (section.get("account_names") or {}) if identity_available else {}
        )
        identity_links = (
            {
                account_id: [c for c in character_ids if c not in deleted_ids]
                for account_id, character_ids in (
                    section.get("account_characters") or {}
                ).items()
            }
            if identity_available
            else {}
        )
        visible_characters = [
            record for record in found.characters if record.file_id not in deleted_ids
        ]

        def backup_payload(item):
            display_name, display_meta = self._eve_backup_identity(
                item, identity_names, identity_links
            )
            return {
                "path": str(item.path),
                "created": item.created,
                "origin": item.origin,
                "kind": item.kind,
                "stem": item.stem,
                "display_name": display_name,
                "display_meta": display_meta,
            }

        def roster(records):
            """The order the Profiles roster reads in: by name (R1/D4).

            Sorted HERE and not in evesettings.tree, which is where the
            file_id sort this one supersedes still lives (as its stable
            base -- see the note there): tree.py has no names. A name
            is ESI's answer to a character id, resolved through
            _eve_label, and it arrives after discover() has returned --
            so the tree can only order by the id in the filename, which
            is what put 32 characters on screen in an order with no human
            pattern and made the filter box the only route to one of
            them. `.es-roster` is `columns: 170px` and flows
            top-to-bottom, so alphabetical reads down each column.

            Case-folded, and the id is the tie-break: an unresolved name
            degrades to "Character 98123456" (unidentified accounts sort
            by their explicit ID metadata), and two of those must not be free
            to swap places between two renders of the same folder.

            This reorders on the name push as well as at first render --
            eve_settings_resolve_names makes the page refetch once the
            real names land, which is the moment the roster becomes
            sortable at all.
            """
            return sorted(
                (
                    self._eve_describe_file(r, identity_names, identity_links)
                    for r in records
                ),
                key=lambda row: (row["name"].casefold(), row["id"]),
            )

        listed, backups_unreadable = evesettings_backup.enumerate_backups(store)
        codec_available = evesettings_codec.codec_available()
        identity_character_ids: set = set()
        if identity_available:
            identity_character_ids = {record.file_id for record in visible_characters}
            identity_character_ids.update(
                character_id
                for values in identity_links.values()
                for character_id in values
            )
        return {
            "root": str(found.root) if found.root else "",
            "default_root": str(evesettings_tree.default_root()),
            "server": str(found.server) if found.server else "",
            "profile": str(found.profile) if found.profile else "",
            "unreadable": found.unreadable,
            # Refused for being too wide to be an EVE folder, rather than
            # probed slowly. Distinct from `unreadable` because the user
            # action differs: this one means "pick a narrower folder".
            "too_broad": found.too_broad,
            # The LAST KNOWN answer, never a fresh probe. See
            # _eve_refresh_running: this method is costed as scandir over
            # a few dozen files and must stay that.
            "eve_running": self._eve_running,
            "identification_active": self._eve_identification is not None,
            # Derived here, never in the page: account names and links are
            # this product's Tranquility metadata, and recognizing a shard
            # is a Python job with a strict predicate behind it.
            "account_identity_available": identity_available,
            "servers": [{"path": str(s.path), "name": s.name} for s in found.servers],
            "profiles": [
                {"path": str(p.path), "name": p.name, "file_count": p.file_count}
                for p in found.profiles
            ],
            "characters": roster(visible_characters),
            "identity_characters": sorted(
                (
                    {
                        "id": character_id,
                        "name": self._eve_names.label(int(character_id)),
                    }
                    for character_id in identity_character_ids
                ),
                key=lambda item: (item["name"].casefold(), item["id"]),
            ),
            "accounts": roster(found.accounts),
            # Reported separately from an empty list for the same reason
            # `unreadable` is: "we could not read your backups" and "you
            # have no backups yet" are different answers, and telling a
            # user the second when the first is true invites them to
            # overwrite settings they believe are unprotected.
            "backups_unreadable": backups_unreadable,
            # The prune depth, so the page can say how many backups are
            # kept without typing the number into itself. Four places once
            # carried the bookmark-keybind count and three of them drifted;
            # this is the same shape, and DESIGN.md's "state that must not
            # be retyped" is the rule it is avoiding.
            "auto_keep": int(section.get("auto_keep", 10)),
            # Whether the bundled codec sidecar is present, so the page can
            # hide the formations editor entirely rather than let a click
            # end in eve_settings_formations's "not available in this
            # install" error.
            "formations_available": codec_available,
            "selective_copy_available": codec_available,
            "setup_available": codec_available,
            "copy_groups": {
                "characters": evesettings_selective.groups_payload("character"),
                "accounts": evesettings_selective.groups_payload("account"),
            },
            "backups": [backup_payload(item) for item in listed],
        }

    def setup_limits(self) -> dict:
        return setup_model.limits_payload()

    @staticmethod
    def _setup_require_entry(path: Path, *, directory: bool = False) -> None:
        """Setup reads refuse aliases too; ordinary profile-copy rules stay intact."""
        info = path.lstat()
        linked = stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        regular = (
            stat.S_ISDIR(info.st_mode)
            if directory
            else (stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        )
        if linked or not regular or ".." in path.parts:
            raise setup_model.SetupError(
                "invalid_request",
                "Choose an ordinary local profile and settings files, not linked aliases.",
            )

    def _setup_selection(self):
        found = self._eve_discover()
        section = self._eve_section()
        _, server, profile = evesettings_tree.normalize_selection(
            section.get("root"), section.get("server"), section.get("profile")
        )
        if (
            found.unreadable
            or found.too_broad
            or found.root is None
            or found.server is None
            or found.profile is None
            or (server is not None and server != found.server)
            or (profile is not None and profile != found.profile)
        ):
            raise setup_model.SetupError(
                "invalid_request",
                "The Profiles selection changed or cannot be read. Reopen Profiles.",
            )
        if not self._eve_context(found).trusted:
            raise setup_model.SetupError("invalid_request", _EVE_IDENTITY_UNAVAILABLE)
        for path in (found.root, found.server, found.profile):
            self._setup_require_entry(path, directory=True)
        if found.server != found.root and found.server.parent != found.root:
            raise setup_model.SetupError(
                "invalid_request", "The server is outside the selected root."
            )
        if found.profile.parent != found.server:
            raise setup_model.SetupError(
                "invalid_request", "The profile is outside the selected server."
            )
        evesettings_tree.require_under(found.root, found.server)
        evesettings_tree.require_under(found.server, found.profile)
        return found

    def _setup_found(self, profile: str):
        selected = self._setup_selection()
        if not isinstance(profile, str) or not profile:
            raise setup_model.SetupError(
                "invalid_request", "Choose a local base profile."
            )
        requested = Path(profile)
        if requested.parent != selected.server:
            raise setup_model.SetupError(
                "invalid_request", "Choose a sibling profile on the selected server."
            )
        self._setup_require_entry(requested, directory=True)
        found = evesettings_tree.discover(selected.root, selected.server, requested)
        if found.profile != requested or found.unreadable or found.too_broad:
            raise setup_model.SetupError(
                "invalid_request", "That profile is no longer available."
            )
        evesettings_tree.require_under(selected.server, requested)
        return found, self._eve_context(selected)

    def _setup_links(self, found) -> dict:
        """Confirmed ownership is server-owned; an offline second owner is ambiguous."""
        saved = self._eve_section().get("account_characters") or {}
        local_characters = {row.file_id for row in found.characters}
        return {
            row.file_id: [
                cid
                for cid in saved.get(row.file_id, [])
                if cid in local_characters
                and not self._eve_is_deleted(cid)
                and sum(cid in values for values in saved.values()) == 1
            ]
            for row in found.accounts
        }

    def _setup_pair(self, found, account_path: str, character_path: str):
        pair = []
        for requested, records in (
            (account_path, found.accounts),
            (character_path, found.characters),
        ):
            if not isinstance(requested, str) or not requested:
                raise setup_model.SetupError(
                    "invalid_request", "Choose a local account and character pair."
                )
            path = Path(requested)
            record = next((row for row in records if row.path == path), None)
            if record is None or path.parent != found.profile:
                raise setup_model.SetupError(
                    "invalid_request", "The selected pair is not in this profile."
                )
            self._setup_require_entry(path)
            evesettings_tree.require_under(found.profile, path)
            pair.append(record)
        account, character = pair
        if character.file_id not in self._setup_links(found).get(account.file_id, []):
            raise setup_model.SetupError(
                "invalid_request",
                "Choose an unambiguous confirmed account/character pair with both local files.",
            )
        return account, character

    def setup_context(self, profile: str) -> dict:
        reply = {
            "ok": False,
            "error": "",
            "root": "",
            "server": "",
            "profile": "",
            "profiles": [],
            "accounts": [],
            "characters": [],
            "account_identity_available": False,
            "setup_available": evesettings_codec.codec_available(),
        }
        # Unlike state(), browsing must neither probe/publish nor resolve names.
        with self._eve_identity_hold() as held:
            if not held:
                return {**reply, "error": "Another Profiles operation is running."}
            try:
                found, _ = self._setup_found(profile)
                links = self._setup_links(found)
                names = self._eve_section().get("account_names") or {}
                characters = [
                    row
                    for row in found.characters
                    if not self._eve_is_deleted(row.file_id)
                ]

                def roster(records):
                    for row in records:
                        self._setup_require_entry(row.path)
                    return sorted(
                        (self._eve_describe_file(row, names, links) for row in records),
                        key=lambda row: (row["name"].casefold(), row["id"]),
                    )

                return {
                    **reply,
                    "ok": True,
                    "root": str(found.root),
                    "server": str(found.server),
                    "profile": str(found.profile),
                    "account_identity_available": True,
                    "profiles": [
                        {
                            "path": str(p.path),
                            "name": p.name,
                            "file_count": p.file_count,
                        }
                        for p in found.profiles
                    ],
                    "accounts": roster(found.accounts),
                    "characters": roster(characters),
                }
            except (OSError, ValueError) as error:
                return {**reply, "error": str(error)}

    def _setup_require_closed(self) -> None:
        try:
            refusal = self._ports.profile_copy_refusal()
        except Exception as error:
            raise setup_model.SetupError(
                "eve_not_closed",
                "Wingman could not verify that EVE is closed. Close EVE and retry.",
            ) from error
        if refusal is not None:
            raise setup_model.SetupError("eve_not_closed", refusal)
        if not evesettings_codec.codec_available():
            raise setup_model.SetupError(
                "unsupported_setup",
                "The settings codec is not available in this install.",
            )

    def _setup_require_context(self, context: _EveContext, generation: int) -> None:
        if (
            self._eve_context(self._setup_selection()) != context
            or self._eve_generation() != generation
        ):
            raise setup_model.SetupError(
                "stale_review",
                "The Profiles selection or identification changed. Review the setup again.",
            )

    def setup_export(
        self, expected_profile: str, account_path: str, character_path: str
    ) -> dict:
        reply = {"ok": False, "error": "", "text": "", "summary": {}, "warnings": []}
        with self._eve_identity_hold() as held:
            if not held:
                return {**reply, "error": "Another Profiles operation is running."}
            try:
                self._setup_require_closed()
                generation = self._eve_generation()
                found, context = self._setup_found(expected_profile)
                account, character = self._setup_pair(
                    found, account_path, character_path
                )
                account_snapshot = evesettings_codec.read_snapshot(account.path)
                character_snapshot = evesettings_codec.read_snapshot(character.path)
                envelope, warnings = setup_documents.export_setup(
                    account_snapshot.document, character_snapshot.document
                )
                text = setup_sharing.export_text(envelope)
                summary = setup_model.summarize(setup_model.validate_wingman(envelope))
                self._setup_require_context(context, generation)
                found, _ = self._setup_found(expected_profile)
                self._setup_pair(found, account_path, character_path)
                self._setup_require_closed()
                evesettings_codec.require_content_revision(
                    account.path, account_snapshot.content_revision
                )
                evesettings_codec.require_content_revision(
                    character.path, character_snapshot.content_revision
                )
                return {
                    **reply,
                    "ok": True,
                    "text": text,
                    "summary": summary,
                    "warnings": list(warnings),
                }
            except (OSError, ValueError, evesettings_codec.CodecError) as error:
                return {**reply, "error": str(error)}

    def setup_read_file(self) -> dict:
        reply = {"ok": False, "cancelled": False, "error": "", "text": ""}
        try:
            chosen = self._ports.choose_setup_input()
            if not chosen:
                return {**reply, "cancelled": True}
            with Path(chosen).open("rb") as stream:
                raw = stream.read(setup_model.MAX_BYTES + 1)
            if len(raw) > setup_model.MAX_BYTES:
                raise setup_model.SetupError(
                    "byte_limit", "Shared setup file exceeds the UTF-8 byte limit."
                )
            text = raw.decode("utf-8-sig")
            setup_model.check_text_budget(text)
            return {**reply, "ok": True, "text": text}
        except Exception as error:
            # Native dialog implementations can raise platform-specific exceptions.
            logger.exception("Could not read a shared UI setup file")
            return {**reply, "error": str(error)}

    def setup_save_file(self, text: str) -> dict:
        reply = {"ok": False, "cancelled": False, "error": "", "path": ""}
        try:
            parsed = setup_sharing.parse_text(text)
            if parsed.source_kind != "wingman":
                raise setup_model.SetupError(
                    "unsupported_setup",
                    "Only a full Wingman JSON setup can be saved here.",
                )
            canonical = setup_sharing.export_text(
                {
                    "format": setup_model.FORMAT,
                    "version": setup_model.VERSION,
                    "type": setup_model.TYPE,
                    "overview": parsed.overview,
                    "layout": parsed.layout,
                }
            )
            chosen = self._ports.choose_setup_output("wingman-ui-setup.json")
            if not chosen:
                return {**reply, "cancelled": True}
            destination = Path(chosen)
            if destination.suffix.lower() != ".json":
                raise setup_model.SetupError(
                    "invalid_request", "Choose a .json filename for the shared setup."
                )
            atomicio.write_atomic(destination, canonical)
            return {**reply, "ok": True, "path": str(destination)}
        except Exception as error:
            # A failed dialog/publication is an error, never cancellation or a saved path.
            logger.exception("Could not save a shared UI setup file")
            return {**reply, "error": str(error)}

    def setup_review(
        self,
        text: str,
        expected_profile: str,
        account_path: str,
        character_path: str,
        destination_name: str,
        keep_ship_labels: bool = False,
    ) -> dict:
        reply = {
            "ok": False,
            "error": "",
            "error_code": "",
            "review_id": "",
            "summary": {},
            "warnings": [],
            "needs_label_choice": False,
        }
        with self._eve_identity_hold() as held:
            if not held:
                return {
                    **reply,
                    "error_code": "busy",
                    "error": "Another Profiles operation is running.",
                }
            # Admission replaces the old authorization even when parsing fails.
            self._setup_review = None
            try:
                self._setup_require_closed()
                generation = self._eve_generation()
                found, context = self._setup_found(expected_profile)
                account, character = self._setup_pair(
                    found, account_path, character_path
                )
                if type(keep_ship_labels) is not bool:
                    raise setup_model.SetupError(
                        "invalid_request", "Choose whether to keep your ship labels."
                    )
                parsed = setup_sharing.parse_text(text)
                reply["summary"] = setup_model.summarize(parsed)
                reply["warnings"] = list(parsed.warnings)
                if parsed.ambiguous_labels and not keep_ship_labels:
                    reply["needs_label_choice"] = True
                    raise setup_model.SetupError(
                        "label_choice_required",
                        "Choose Keep my ship labels explicitly for this YAML.",
                    )
                try:
                    plan = evesettings_profilecopy.prepare_copy(
                        found, expected_profile, "new", destination_name
                    )
                except ValueError as error:
                    collision = isinstance(destination_name, str) and any(
                        row.name.casefold() == destination_name.strip().casefold()
                        for row in found.profiles
                    )
                    raise setup_model.SetupError(
                        "destination_exists" if collision else "invalid_request",
                        str(error),
                    ) from error
                if any(
                    not (plan.source / name).exists()
                    for name in ("core_public__.yaml", "prefs.ini")
                ):
                    raise setup_model.SetupError(
                        "missing_local_preferences",
                        "The base profile needs both core_public__.yaml and prefs.ini. Choose a normally initialized recipient profile.",
                    )
                manifest = setup_profile.capture_manifest(plan)
                revisions = {row.name: row.sha256 for row in manifest.files}
                if not {account.path.name, character.path.name} <= revisions.keys():
                    raise setup_model.SetupError(
                        "stale_review", "The selected files changed during review."
                    )
                account_snapshot = evesettings_codec.read_snapshot(account.path)
                character_snapshot = evesettings_codec.read_snapshot(character.path)
                if (
                    account_snapshot.content_revision != revisions[account.path.name]
                    or character_snapshot.content_revision
                    != revisions[character.path.name]
                ):
                    raise setup_model.SetupError(
                        "stale_review", "The selected files changed during review."
                    )
                setup_profile.require_manifest(plan, manifest)
                # Same pure application as staging, with no encode/write or publication.
                setup_documents.apply_setup(
                    account_snapshot.document,
                    character_snapshot.document,
                    parsed,
                    keep_ship_labels=keep_ship_labels,
                    now=time.time(),
                )
                self._setup_require_context(context, generation)
                found, _ = self._setup_found(expected_profile)
                self._setup_pair(found, account_path, character_path)
                self._setup_require_closed()
                setup_profile.require_manifest(plan, manifest)
                offer = _SetupReview(
                    str(uuid.uuid4()),
                    text,
                    keep_ship_labels,
                    context,
                    generation,
                    plan,
                    account.path.name,
                    character.path.name,
                    account.file_id,
                    character.file_id,
                    manifest,
                )
                # Cancellation/deletion may claim a generation without the mutation
                # hold. Compare-and-install under its lock so it cannot half-happen.
                with self._eve_identification_lock:
                    if generation != self._eve_identification_generation:
                        raise setup_model.SetupError(
                            "stale_review",
                            "Identification changed. Review the setup again.",
                        )
                    self._setup_review = offer
                return {**reply, "ok": True, "review_id": offer.review_id}
            except setup_model.SetupError as error:
                return {**reply, "error": str(error), "error_code": error.code}
            except FileExistsError as error:
                return {
                    **reply,
                    "error": str(error),
                    "error_code": "destination_exists",
                }
            except (OSError, ValueError, evesettings_codec.CodecError) as error:
                return {**reply, "error": str(error), "error_code": "unsupported_setup"}

    def setup_discard(self, review_id: str) -> bool:
        with self._eve_identity_hold() as held:
            if not held:
                return False
            offer = self._setup_review
            if (
                offer is None
                or not isinstance(review_id, str)
                or offer.review_id != review_id
            ):
                return False
            try:
                self._setup_require_context(offer.selection_context, offer.generation)
            except (OSError, ValueError):
                return False
            self._setup_review = None
            return True

    def _setup_require_offer(self, offer: _SetupReview) -> None:
        """Revalidate selection authority separately from the browsed sibling base."""
        try:
            self._setup_require_context(offer.selection_context, offer.generation)
            if self._eve_identification is not None:
                raise ValueError("Finish or cancel account identification first.")
            found, _ = self._setup_found(str(offer.plan.source))
            account, character = self._setup_pair(
                found,
                str(offer.plan.source / offer.account_filename),
                str(offer.plan.source / offer.character_filename),
            )
            if (account.file_id, character.file_id) != (
                offer.account_id,
                offer.character_id,
            ) or not {offer.account_filename, offer.character_filename} <= {
                row.name for row in offer.manifest.files
            }:
                raise ValueError("The reviewed account/character pair changed.")
        except (OSError, ValueError) as error:
            raise setup_model.SetupError("stale_review", str(error)) from error
        for name in ("core_public__.yaml", "prefs.ini"):
            if not (offer.plan.source / name).exists():
                raise setup_model.SetupError(
                    "missing_local_preferences",
                    f"The base profile is missing required local preferences: {name}.",
                )
        # Discovery supplies the case-insensitive collision rule on Linux too;
        # lexists also refuses files and dangling links not offered as profiles.
        if os.path.lexists(offer.plan.destination) or any(
            row.path.name.casefold() == offer.plan.destination.name.casefold()
            for row in found.profiles
        ):
            raise setup_model.SetupError(
                "destination_exists", f"{offer.plan.destination_name!r} already exists."
            )

    def setup_create(self, review_id: str, request_id: str) -> dict:
        """Consume one reviewed offer, never queue or change selection at admission."""
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            return {
                "accepted": False,
                "error": "A create request needs a request ID of 1 to 128 characters.",
            }
        if self._eve_identification is not None:
            return {
                "accepted": False,
                "error": "Finish or cancel account identification first.",
            }
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "accepted": False,
                "error": "Another Profiles operation is running.",
            }
        offer = self._setup_review
        consumed = False
        worker_entered = False
        handed_off = False

        def worker():
            nonlocal worker_entered
            # A port may finish inline before start() returns (or raises). Once
            # entered, only the worker owns release/completion; never restore it.
            worker_entered = True
            self._eve_setup_create_worker(offer, request_id)

        try:
            if (
                offer is None
                or not isinstance(review_id, str)
                or offer.review_id != review_id
            ):
                raise setup_model.SetupError(
                    "stale_review",
                    "That review is no longer available. Review the setup again.",
                )
            self._setup_require_closed()
            self._setup_require_offer(offer)
            setup_profile.require_manifest(offer.plan, offer.manifest)
            self._setup_require_offer(offer)
            with self._eve_identification_lock:
                if (
                    self._setup_review is not offer
                    or offer.generation != self._eve_identification_generation
                ):
                    raise setup_model.SetupError(
                        "stale_review",
                        "Identification changed. Review the setup again.",
                    )
                self._setup_review = None
                consumed = True
            self._ports.spawn(target=worker, args=(), daemon=True).start()
            handed_off = True
        except Exception as error:
            if worker_entered:
                logger.exception("Setup worker entered before its start handle failed")
                return {"accepted": True, "error": None}
            logger.warning("Setup creation not started: %s", error)
            return {
                "accepted": False,
                "error": str(error) or "Setup creation could not be started.",
            }
        finally:
            if not handed_off and not worker_entered:
                try:
                    if consumed and self._setup_review is None:
                        # Still holding mutation authority: another review cannot
                        # race restoration. Cancellation can, so compare generation
                        # again under its own lock after all external checks.
                        self._setup_require_closed()
                        self._setup_require_offer(offer)
                        setup_profile.require_manifest(offer.plan, offer.manifest)
                        self._setup_require_offer(offer)
                        with self._eve_identification_lock:
                            if (
                                self._setup_review is None
                                and offer.generation
                                == self._eve_identification_generation
                            ):
                                self._setup_review = offer
                except Exception:
                    # A failed start is retryable only while the same review is
                    # still valid. Leave stale authority consumed, not resurrected.
                    logger.info(
                        "Setup review expired during worker start", exc_info=True
                    )
                finally:
                    self._eve_mutation.release()
        return {"accepted": True, "error": None}

    def _eve_setup_create_worker(self, offer: _SetupReview, request_id: str) -> None:
        published = False
        created = None
        selection_persisted = False
        error_code = "create_failed"
        error_message = "Setup creation was interrupted."
        warning = ""
        try:
            parsed = setup_sharing.parse_text(offer.text)
            if parsed.ambiguous_labels and not offer.keep_ship_labels:
                raise setup_model.SetupError(
                    "unsupported_setup",
                    "Review the setup and choose Keep my ship labels.",
                )
            self._setup_require_offer(offer)
            try:
                setup_profile.require_manifest(offer.plan, offer.manifest)
            except ValueError as error:
                raise setup_model.SetupError("stale_review", str(error)) from error
            self._setup_require_closed()
            with setup_profile.stage_setup(
                offer.plan,
                offer.manifest,
                offer.account_filename,
                offer.character_filename,
                parsed,
                keep_ship_labels=offer.keep_ship_labels,
                now=time.time(),
            ) as staged:
                self._setup_require_offer(offer)
                try:
                    setup_profile.require_manifest(offer.plan, offer.manifest)
                except ValueError as error:
                    raise setup_model.SetupError("stale_review", str(error)) from error
                self._setup_require_closed()
                # The process probe can be slow. Its CLOSED answer cannot make
                # context or filesystem observations from before it fresh again.
                self._setup_require_offer(offer)
                try:
                    setup_profile.require_manifest(offer.plan, offer.manifest)
                except ValueError as error:
                    raise setup_model.SetupError("stale_review", str(error)) from error
                # Hashing may outlive cancellation or a learned deletion. Neither
                # needs the mutation hold to invalidate this offer's authority.
                self._setup_require_offer(offer)
                created = evesettings_profilecopy.publish_new(staged)
                # This is the irreversible outcome, before cleanup, persistence,
                # or page status. None of those may invite a duplicate retry.
                published = True
                error_code = ""
                error_message = ""
            selection_persisted = self._eve_select_created_profile(offer.plan, created)
            if not selection_persisted:
                warning = (
                    f"Created {offer.plan.destination_name}, but Wingman could not remember "
                    "the selection. Select it from Profile."
                )
            self._ports.status(f"Created {offer.plan.destination_name}.")
        except Exception as error:
            if published:
                logger.exception("Setup profile created, but a follow-up effect failed")
                warning = " ".join(
                    filter(
                        None,
                        [warning, f"Profile created, but a follow-up failed: {error}"],
                    )
                )
            else:
                logger.exception("Setup profile creation failed")
                error_message = str(error) or "Setup creation could not be completed."
                if isinstance(error, setup_model.SetupError):
                    error_code = error.code
                elif isinstance(error, evesettings_codec.ContentChangedError):
                    error_code = "stale_review"
                elif isinstance(error, FileExistsError):
                    error_code = "destination_exists"
                else:
                    error_code = "create_failed"
        finally:
            self._eve_mutation.release()
            self._eve_done(
                published,
                operation="ui_setup_create",
                request_id=request_id,
                review_id=offer.review_id,
                published=published,
                path=str(created) if published else "",
                selection_persisted=selection_persisted,
                error_code=error_code,
                error=error_message,
                warning=warning,
            )

    def _eve_refresh_running(self) -> None:
        """Re-probe for a running client, off the bridge thread.

        eve_settings_state() is costed in the design as "scandir over a
        few dozen files", and list_clients() is not that: it enumerates
        every top-level window and resolves PIDs to executables. It caches
        per PID, so it is cheap in steady state, but the first call after
        a client starts or stops is not -- and it was being paid inline on
        the thread the whole UI answers on.

        It only drives an advisory pill, so a slightly stale answer costs
        nothing: state returns the last known value immediately and this
        pushes when the value actually CHANGES, which is the only moment
        the page has anything to redraw. Same push channel the name
        resolver uses, and for the same reason -- request/response cannot
        express an answer that arrives after the response did.
        """

        def worker() -> None:
            try:
                value = self._ports.advisory_client_running()
                if value != self._eve_running:
                    self._eve_running = value
                    self._ports.publish_running({"running": value})
            except Exception:
                logger.debug("EVE client probe failed", exc_info=True)
            finally:
                self._eve_probe.release()

        # Single-flight. Skipping is safe because the caller re-reads the
        # cached value either way, and the probe already in flight will
        # publish a fresher answer than this one could.
        if not self._eve_probe.acquire(blocking=False):
            return
        try:
            self._ports.spawn(target=worker, daemon=True).start()
        except Exception:
            # Only the worker releases, and a worker that never started
            # never will -- that would wedge the probe for the process's
            # lifetime and freeze the pill on whatever it last said.
            self._eve_probe.release()
            logger.debug("Could not start the EVE client probe", exc_info=True)
        except BaseException:
            self._eve_probe.release()
            raise

    @contextlib.contextmanager
    def _eve_hold(self):
        """The mutation lock, for work that runs ON the bridge thread.

        Yields True when the lock was taken and False when it was already
        held; the caller declines in that case, exactly as _eve_begin
        does. `root` is an input to every containment check, so changing
        it while a restore or a copy is in flight would have that
        operation validate against a different root than the one in effect
        when it was approved -- and _eve_begin's stated policy is that EVE
        Settings mutations are refused rather than interleaved.

        Non-blocking, and not merely to match that policy. A worker
        holding the lock is parked in the confirmation port waiting for an answer
        the page delivers over the bridge, so blocking here would stop the
        bridge from carrying that answer. It is not a true deadlock --
        the confirmation port has a bounded wait and reads a
        missing answer as "no", so the worker unwinds and releases -- but
        the price of blocking is a UI frozen for up to five minutes, which
        is not meaningfully better than one.
        """
        if not self._eve_mutation.acquire(blocking=False):
            self._ports.alert(
                "warning",
                "EVE Settings busy",
                "Another EVE Settings operation is still running. "
                "Wait for it to finish, then try again.",
            )
            yield False
            return
        try:
            yield True
        finally:
            self._eve_mutation.release()

    def pick_root(self) -> str:
        # The lock is held across the dialog too, so a mutation cannot
        # start while the user is choosing. The alternative -- lock only
        # the write -- lets the user pick a folder and then discards it,
        # which is a worse answer to the same race.
        with self._eve_hold() as held:
            if not held:
                return ""
            section = self._eve_section()
            start = str(section.get("root") or evesettings_tree.default_root())
            picked = self._ports.choose_root(start)
            if not picked:
                return ""
            # The old server and profile belong to a tree that is no
            # longer the one on screen -- but rather than merely clearing
            # them, discover the tree the picked folder actually names
            # and persist ITS complete triple. normalize_selection lifts a
            # folder pointed at a server or a profile back up to the real
            # root, and the freshly discovered server/profile are what the
            # page renders as selected on the very next state() call,
            # instead of showing "none chosen" for a folder that plainly
            # has one.
            self._eve_clear_identification()
            found = evesettings_tree.discover(picked)
            self._eve_persist_selection(found)
            return str(found.root) if found.root else ""

    def detect_root(self) -> str:
        """Detect the EVE settings root, the way Folders detects OBS's.

        Profiles 4: `Detect` exists in Settings > Folders AND on the
        first-run screen, for a folder that is shallower and better known
        than this one -- while the EVE settings root, the folder the
        product is named for, got `Choose folder...` alone. PRODUCT.md
        names the job directly: "assume fluency. Do not explain EVE. Do
        explain Wingman -- where a folder is."

        A sibling of eve_settings_pick_root rather than a branch of
        detect_folder, and the difference is deliberate. detect_folder
        RETURNS a suggestion and leaves Save to the user, because its
        fields sit in an immediate-save form where writing under the user
        would discard their other edits. This screen has no form: its
        neighbour `Choose folder...` commits the moment the dialog closes.
        A Detect that only suggested, beside a Choose that commits, would
        be two behaviours for one question on one screen -- which is the
        class of inconsistency this whole round is about.

        So: same lock, same selection reset, same return shape as the
        picker. The lock is held across the probe for the picker's reason
        -- a mutation must not start midway.
        """
        with self._eve_hold() as held:
            if not held:
                return ""
            default = evesettings_tree.default_root()
            if not default.is_dir():
                # Named, not just refused. The path is the useful half of
                # the answer: a user whose EVE lives somewhere else learns
                # where we looked, which is what tells them Choose folder...
                # is the way out.
                self._ports.alert(
                    "info",
                    "EVE settings folder not found",
                    "Could not find an EVE settings folder at:\n"
                    f"{default}\n\n"
                    "Use Choose folder... to point at it.",
                )
                return ""
            found = evesettings_tree.discover(default)
            section = self._eve_section()
            if str(found.root) == str(section.get("root") or ""):
                # Agreement reported as agreement, not as a silent rewrite
                # -- detect_folder's rule, and the reason it compares the
                # live value rather than blindly rewriting. Returning ""
                # here also keeps the selection intact, which the write
                # path below would otherwise clear for no reason.
                self._ports.alert(
                    "info",
                    "EVE settings folder",
                    f"Already set to the detected folder:\n{found.root}",
                )
                return ""
            self._eve_clear_identification()
            self._eve_persist_selection(found)
            return str(found.root)

    def select(self, server: str, profile: str) -> bool:
        with self._eve_hold() as held:
            if not held:
                return False
            # The EFFECTIVE root, not the raw stored value: normalize_selection
            # rewrites a root pointed at a profile or server directory, and
            # in doing so it also discards whatever server/profile the
            # caller asked for in favor of the ones implied by that deep
            # root (see tree.py's normalize_selection). Discovering directly
            # from a legacy deep `root` would therefore silently overrule a
            # real selection change -- e.g. picking a sibling profile from a
            # pre-canonicalization install that stored `root` as the
            # original profile itself. Resolving the canonical root FIRST,
            # then discovering from IT with the requested tokens, is what
            # lets normalize_selection's third branch (which passes both
            # tokens through untouched) actually see them.
            effective_root = self._eve_discover().root
            found = evesettings_tree.discover(
                effective_root, server or None, profile or None
            )
            if found.root is None:
                return False
            # discover() falls back to the first server/profile it finds
            # when the requested token matches nothing on disk -- a
            # fabricated server or profile must not silently persist as
            # "whatever discover() picked instead". An empty profile is
            # the one deliberate case that IS a fallback: it asks for the
            # requested server's first profile, which is exactly what
            # discover() returns for a None profile.
            if server and not _eve_same_path(found.server, server):
                return False
            if profile and not _eve_same_path(found.profile, profile):
                return False
            self._eve_clear_identification()
            self._eve_persist_selection(found)
            return True

    def _eve_persist_selection(self, found) -> None:
        """The one place that writes root/server/profile to settings.

        Every explicit selection -- picker, Detect, eve_settings_select, and
        the profile a copy creates -- discovers a Tree first and persists ITS
        complete triple here, rather than writing back whatever the caller
        was originally given. A picked or typed value can be a server or a
        profile directory, or a legacy root that pointed one or two levels
        too deep; discover() already normalizes all of those, and persisting
        anything other than its answer would let the stored root drift out of
        step with the server/profile that were actually chosen alongside it.
        That is also why there is no per-leg override argument: a caller that
        wants a particular profile remembered discovers it first (see
        _eve_select_created_profile) so the whole triple stays consistent,
        rather than pasting one leg over a Tree that disagrees with it.
        """
        self._ports.update_settings(
            {
                "root": str(found.root) if found.root else None,
                "server": str(found.server) if found.server else None,
                "profile": str(found.profile) if found.profile else None,
            },
        )

    def _eve_discover(self):
        section = self._eve_section()
        return evesettings_tree.discover(
            section.get("root"), section.get("server"), section.get("profile")
        )

    @staticmethod
    def _eve_decimal_id(value) -> bool:
        return isinstance(value, str) and value.isascii() and value.isdigit()

    @staticmethod
    def _eve_validate_account_name(
        account_id: str, name: str, names: dict
    ) -> tuple[str | None, str | None]:
        cleaned = name.strip()
        if not cleaned:
            return None, "Enter an EVE Online username."
        if len(cleaned) > 80:
            return None, "Account names can be up to 80 characters."
        folded = cleaned.casefold()
        if any(
            other_id != account_id and str(other_name).strip().casefold() == folded
            for other_id, other_name in names.items()
        ):
            return (
                None,
                "That EVE Online username is already assigned to another account.",
            )
        return cleaned, None

    @staticmethod
    def _eve_relink_account_characters(
        associations: dict,
        account_id: str,
        remove_character_ids: list[str],
        account_characters: list[str],
    ) -> tuple[dict | None, str | None]:
        if len(set(account_characters)) > 3:
            return None, "An EVE account can have up to three characters."
        updated = {
            saved_account: [
                saved_character
                for saved_character in saved_characters
                if saved_character not in remove_character_ids
            ]
            for saved_account, saved_characters in associations.items()
        }
        updated = {
            saved_account: saved_characters
            for saved_account, saved_characters in updated.items()
            if saved_characters
        }
        if account_characters:
            updated[account_id] = account_characters
        else:
            updated.pop(account_id, None)
        return updated, None

    @contextlib.contextmanager
    def _eve_identity_hold(self):
        """Serialize synchronous identity edits without blocking the bridge.

        A worker can hold this lock while awaiting a page confirmation. Manual
        account edits must refuse in that state rather than block the bridge
        that delivers the answer and leave the worker parked until its timeout.
        """
        if not self._eve_mutation.acquire(blocking=False):
            yield False
            return
        try:
            yield True
        finally:
            self._eve_mutation.release()

    def set_account_name(self, account_id: str, name: str) -> dict:
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            if not self._eve_decimal_id(account_id) or not isinstance(name, str):
                return self._field_refused("Choose a valid account.")
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                return self._field_refused(_EVE_IDENTITY_UNAVAILABLE)
            if account_id not in {item.file_id for item in found.accounts}:
                return self._field_refused("That account is not in this profile.")
            if not self._eve_prune_deleted_links_locked(self._eve_deleted_ids(found)):
                return self._field_refused(_EVE_CLEANUP_FAILED)
            names = dict(self._eve_section().get("account_names") or {})
            cleaned, error = self._eve_validate_account_name(account_id, name, names)
            if error:
                return self._field_refused(error)
            names[account_id] = cleaned
            try:
                self._ports.update_settings({"account_names": names})
            except OSError:
                logger.exception("Could not persist EVE account name")
                return self._field_refused("Could not save this account name.")
            return self._field_ok()

    def set_account_characters(self, account_id: str, character_ids: list) -> dict:
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            if not self._eve_decimal_id(account_id) or not isinstance(
                character_ids, list
            ):
                return self._field_refused("Choose a valid account and characters.")
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                return self._field_refused(_EVE_IDENTITY_UNAVAILABLE)
            if account_id not in {item.file_id for item in found.accounts}:
                return self._field_refused("That account is not in this profile.")
            section = self._eve_section()
            if account_id not in (section.get("account_names") or {}):
                return self._field_refused(
                    "Name this account before adding characters."
                )
            # Before reading the roster, not after: the page submits its
            # VISIBLE list as the complete set, so a link it cannot see must
            # be gone from the saved mapping first or this edit would decide
            # its fate silently.
            deleted_ids = self._eve_deleted_ids(found)
            if not self._eve_prune_deleted_links_locked(deleted_ids):
                return self._field_refused(_EVE_CLEANUP_FAILED)
            # Re-read live section: update_section replaces the nested dict
            # object, so the snapshot taken above is stale after the prune.
            # Reading associations from it would re-persist a deleted link
            # that the prune just removed from another account.
            section = self._eve_section()
            associations = {
                key: list(value)
                for key, value in (section.get("account_characters") or {}).items()
            }
            known = {
                item.file_id
                for item in found.characters
                if item.file_id not in deleted_ids
            }
            known.update(value for values in associations.values() for value in values)
            wanted = []
            for value in character_ids:
                if self._eve_is_deleted(value):
                    return self._field_refused(_EVE_CHARACTER_DELETED)
                if not self._eve_decimal_id(value) or value not in known:
                    return self._field_refused(
                        "That character is not known to Wingman."
                    )
                if value not in wanted:
                    wanted.append(value)
            associations, error = self._eve_relink_account_characters(
                associations, account_id, wanted, wanted
            )
            if error:
                return self._field_refused(error)
            try:
                self._ports.update_settings(
                    {"account_characters": associations},
                )
            except OSError:
                logger.exception("Could not persist EVE account characters")
                return self._field_refused("Could not save these character links.")
            return self._field_ok()

    def identification_start(self) -> dict:
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "status": "busy",
                "error": "Another Profiles operation is running.",
                "identification_generation": self._eve_generation(),
            }
        try:
            # The claim comes first: the previous observation dies here, so
            # anything still working under the old number is already stale.
            generation = self._eve_clear_identification()
            found = self._eve_discover()
            if not self._eve_account_identity_available(found):
                raise ValueError(_EVE_IDENTITY_UNAVAILABLE)
            deleted_ids = self._eve_deleted_ids(found)
            snapshot = evesettings_identity.take_snapshot(found)
            if not found.accounts or not [
                record
                for record in found.characters
                if record.file_id not in deleted_ids
            ]:
                raise ValueError(
                    "This profile needs an account and a character to identify."
                )
            # Compare-and-publish. The discovery above is filesystem work
            # done off the state lock, and a cancellation that landed
            # during it must win: either it ran before this and the claim
            # no longer matches, or it runs after and clears what was
            # published. There is no window in which neither is true.
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification = snapshot
        except (OSError, ValueError) as error:
            return {
                "status": "error",
                "error": str(error),
                "identification_generation": self._eve_generation(),
            }
        finally:
            self._eve_mutation.release()
        return {
            "status": "watching",
            "error": None,
            "identification_generation": generation,
        }

    def identification_check(self) -> dict:
        # A worker can hold this lock while parked on a bridge confirmation.
        # Refusing preserves the bridge thread that must deliver that answer.
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "status": "busy",
                "error": "Another Profiles operation is running.",
                "identification_generation": self._eve_generation(),
            }
        try:
            # A check speaks for the observation it reads, so it publishes
            # under that observation's generation rather than claiming one
            # of its own. Every status below carries the number it was
            # computed under, and the page discards an answer older than
            # the highest it has already seen.
            generation, snapshot, _ = self._eve_identification_state()
            if snapshot is None:
                return {
                    "status": "error",
                    "error": "Start account identification first.",
                    "identification_generation": generation,
                }
            # A new check supersedes every former offer, including one that
            # cannot compare because EVE has not closed yet.
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification_candidate = None
            try:
                if self._ports.strict_client_running():
                    return {
                        "status": "watching",
                        "error": "EVE is still running. Close that client, then check again.",
                        "identification_generation": generation,
                    }
            except Exception:
                # Fail closed: an unverified running state must not be treated as
                # the clean shutdown whose file changes identify an account.
                logger.warning(
                    "Could not verify EVE state during identification", exc_info=True
                )
                return {
                    "status": "watching",
                    "error": "Could not confirm that EVE is closed. Close it and try again.",
                    "identification_generation": generation,
                }
            found = self._eve_discover()
            changed = evesettings_identity.changes_since(snapshot, found)
            if changed.invalidated:
                with self._eve_identification_lock:
                    if self._eve_identification_generation != generation:
                        return self._eve_identification_cancelled_locked()
                    invalidated = self._eve_clear_identification_locked()
                return {
                    "status": "invalidated",
                    "error": "The selected EVE profile changed. Start identification again.",
                    "identification_generation": invalidated,
                }
            if len(changed.accounts) > 1:
                return {
                    "status": "ambiguous",
                    "error": "More than one account changed. Close the other EVE clients and start again.",
                    "identification_generation": generation,
                }
            # A deleted character's file can still be written by the client
            # that owned it, so it can still LOOK like the change that
            # identifies an account. It can never be offered as one.
            deleted_ids = self._eve_deleted_ids(found)
            characters = tuple(
                character_id
                for character_id in changed.characters
                if character_id not in deleted_ids
            )
            if len(changed.accounts) != 1 or not characters:
                return {
                    "status": "none",
                    "error": "No account and character changes were found. Make a small settings change in the client, then close it completely and check again.",
                    "identification_generation": generation,
                }
            account_id = changed.accounts[0]
            with self._eve_identification_lock:
                if self._eve_identification_generation != generation:
                    return self._eve_identification_cancelled_locked()
                self._eve_identification_candidate = _EveCandidate(
                    generation, account_id, characters
                )
            return {
                "status": "candidate",
                "error": None,
                "account": {"id": account_id, **self._eve_account_identity(account_id)},
                "characters": [
                    {
                        "id": character_id,
                        "name": self._eve_names.label(int(character_id)),
                    }
                    for character_id in characters
                ],
                "identification_generation": generation,
            }
        finally:
            self._eve_mutation.release()

    def identification_confirm(
        self, account_id: str, character_id: str, account_name: str
    ) -> dict:
        """Persist one offered account/character pair as one settings update."""
        with self._eve_identity_hold() as held:
            if not held:
                return self._field_refused("Another Profiles operation is running.")
            candidate = None
            generation, _, offered = self._eve_identification_state()
            # The generation is read WITH the offer, not beside it: an
            # offer whose authorizing observation has been replaced is
            # stale even if the object survived the swap.
            if offered is not None and offered.generation == generation:
                candidate = offered
            if candidate is None:
                return self._field_refused("Start account identification again.")
            if (
                account_id != candidate.account_id
                or character_id not in candidate.character_ids
            ):
                return self._field_refused("That account match is no longer available.")
            if not isinstance(account_name, str):
                return self._field_refused("Enter an EVE Online username.")
            # The offer may have been made before the resolver learned this
            # character was gone; authorization is revalidated at the write.
            if self._eve_is_deleted(character_id):
                return self._field_refused(_EVE_CHARACTER_DELETED)
            # Pending cleanup first, exactly as the manual account edits do
            # it: this write replaces the whole mapping, so a deleted link
            # still saved for ANOTHER account would be carried along by it.
            if not self._eve_prune_deleted_links_locked(
                self._eve_deleted_ids(self._eve_discover())
            ):
                return self._field_refused(_EVE_CLEANUP_FAILED)

            # Read the live section AFTER the prune: update_section replaces
            # the nested dict object rather than mutating it, so a snapshot
            # taken earlier would re-persist the links just removed.
            section = self._eve_section()
            names = dict(section.get("account_names") or {})
            cleaned_name, error = self._eve_validate_account_name(
                account_id, account_name, names
            )
            if error:
                return self._field_refused(error)
            associations = {
                saved_account: list(character_ids)
                for saved_account, character_ids in (
                    section.get("account_characters") or {}
                ).items()
            }
            destination = associations.get(account_id, [])

            final_names = {**names, account_id: cleaned_name}
            final_associations = associations
            if character_id not in destination:
                final_associations, error = self._eve_relink_account_characters(
                    associations,
                    account_id,
                    [character_id],
                    [*destination, character_id],
                )
                if error:
                    return self._field_refused(error)

            if final_names != names or final_associations != associations:
                try:
                    self._ports.update_settings(
                        {
                            "account_names": final_names,
                            "account_characters": final_associations,
                        },
                    )
                except OSError:
                    # Account names are private local metadata; never include the
                    # supplied username in diagnostics.
                    logger.exception("Could not persist identified EVE account")
                    return self._field_refused("Could not save this account identity.")
            self._eve_clear_identification()
            return self._field_ok()

    def identification_cancel(self) -> dict:
        """End the pass. Never refused, never blocked, always a new number.

        Takes only the identification-state lock. Route exit cancels, and
        cleanup can own _eve_mutation for a whole ESI pass -- a cancel that
        waited for it would freeze the page on the way out of Profiles.

        The generation is the answer's substance, not decoration: a check
        whose candidate is still in flight returns the OLD number, so the
        page can drop it instead of rendering an offer the user just
        cancelled.
        """
        return {
            "status": "idle",
            "error": None,
            "identification_generation": self._eve_clear_identification(),
        }

    def resolve_names(self) -> None:
        """Verify and name the selected profile's characters, off the bridge.

        The one thing a request/response bridge cannot express on its own:
        the state that triggered this was already returned, carrying
        fallback ids and possibly a row for a character that no longer
        exists. One push per pass, not per name.

        Single-flight with ONE trailing pass. The page asks on every route
        entry and every profile switch, so requests arrive in bursts; a
        worker per request would multiply ESI traffic and let a slow pass
        publish over a newer one. A request that arrives while a pass runs
        is remembered, not queued, so switching A -> B mid-pass always ends
        up resolving B without another user action.
        """
        with self._eve_resolve_lock:
            if self._eve_resolve_running:
                self._eve_resolve_pending = True
                return
            self._eve_resolve_running = True
        self._eve_spawn_resolver()

    def _eve_spawn_resolver(self) -> None:
        """Start the worker that owns the claim, or give the claim back.

        A claim held by a worker that never started would silence the
        resolver for the life of the process -- every later request would
        coalesce into a pass nobody is running.
        """
        try:
            self._ports.spawn(target=self._eve_resolve_worker, daemon=True).start()
        except Exception:
            self._eve_release_resolver()
            logger.warning("Could not start the EVE character resolver", exc_info=True)
        except BaseException:
            self._eve_release_resolver()
            raise

    def _eve_release_resolver(self) -> None:
        with self._eve_resolve_lock:
            self._eve_resolve_running = False
            self._eve_resolve_pending = False

    def _eve_resolve_worker(self) -> None:
        try:
            self._eve_resolve_pass()
        except Exception:
            logger.warning("EVE character resolution failed", exc_info=True)
        finally:
            # Running stays claimed ACROSS the handoff when a pass is owed,
            # so a request arriving in this gap coalesces into that pass
            # instead of starting a second worker beside it. The spawn is
            # decided under the lock and performed outside it: spawning
            # while holding it would re-enter this method under an inline
            # thread seam and deadlock.
            with self._eve_resolve_lock:
                restart = self._eve_resolve_pending
                self._eve_resolve_pending = False
                self._eve_resolve_running = restart
            if restart:
                self._eve_spawn_resolver()

    def _eve_resolve_pass(self) -> None:
        found = self._eve_discover()
        context = self._eve_context(found)
        local_ids = {int(r.file_id) for r in found.characters if r.file_id.isdigit()}
        linked_ids = {
            int(character_id)
            for values in (self._eve_section().get("account_characters") or {}).values()
            for character_id in values
            if character_id.isdigit()
        }
        if context.trusted:
            # Deleted is monotonic, so a confirmed id is never asked about
            # again. Active is NOT cached: a character alive on this visit
            # can be deleted before the next one, and a session can outlive
            # both. /universe/names still answers for ids with no local file
            # here -- they are names to show, not deletion candidates.
            unchecked = sorted(
                ident
                for ident in local_ids
                if (context.datasource, ident) not in self._eve_deleted
            )
            names, deleted = evesettings_characters.resolve(unchecked)
            self._eve_names.names.update(names)
            for ident in deleted:
                self._eve_deleted.add((context.datasource, ident))
            self._eve_names.resolve_missing(sorted(linked_ids - local_ids))
        else:
            self._eve_names.resolve_missing(sorted(local_ids | linked_ids))
        self._eve_apply_facts(context, local_ids | linked_ids)

    def _eve_apply_facts(self, context: _EveContext, ids: set) -> None:
        """Publish what the caches now say about *context*, if it is current.

        Remote facts are global and were cached above regardless. Applying
        them is per selection: a superseded pass may not clean, clear an
        identification, or repaint the profile that replaced it, and the
        trailing pass that follows re-evaluates the same cache against the
        selection that IS current -- which is how a fact learned by a stale
        pass still reaches the page.
        """
        if self._eve_context(self._eve_discover()) != context:
            return
        changed = False
        invalidated: tuple[str, ...] = ()
        deleted_ids = {
            str(ident)
            for ident in ids
            if (context.datasource, ident) in self._eve_deleted
        }
        if context.trusted and deleted_ids:
            changed, invalidated = self._eve_clean_deleted(context, deleted_ids)
        facts = (
            frozenset(
                (ident, self._eve_names.names[ident])
                for ident in ids
                if ident in self._eve_names.names
            ),
            frozenset(deleted_ids),
        )
        if facts != self._eve_applied.get(context, _EVE_NO_FACTS):
            self._eve_applied[context] = facts
            changed = True
        if changed:
            # Both keys always, the list empty when this pass invalidated
            # nothing: the page decides from the values, never from whether
            # a key happens to be present.
            self._ports.publish_names(
                {
                    "identification_generation": self._eve_generation(),
                    "deleted_candidate_ids": sorted(invalidated),
                },
            )

    def _eve_clean_deleted(
        self, context: _EveContext, deleted_ids: set
    ) -> tuple[bool, tuple[str, ...]]:
        """Remove confirmed deleted ids from saved metadata.

        Returns (changed, invalidated_candidate_ids): whether anything the
        page shows moved, and which offered character ids this pass
        disqualified -- the page needs the ids to reset the one focused
        step it may be sitting on.

        Waits for the mutation lock rather than declining like the bridge
        endpoints do: this is already a background thread, so waiting costs
        nothing a user sees, and no network call is held across it. The
        context is revalidated INSIDE the lock, and the mapping is read
        there too -- a prune computed before the wait would write back a
        roster the user edited during it.
        """
        with self._eve_mutation:
            if self._eve_context(self._eve_discover()) != context:
                return False, ()
            before = self._eve_section().get("account_characters") or {}
            saved = {key: list(value) for key, value in before.items()}
            persisted = self._eve_prune_deleted_links_locked(deleted_ids)
            changed = (
                persisted
                and (self._eve_section().get("account_characters") or {}) != saved
            )
            # The offer on screen may name a character ESI has just called
            # deleted. Confirming it would persist a link this pass exists
            # to remove, so the whole observation goes -- under the state
            # lock, which this thread takes while holding _eve_mutation and
            # never the other way round.
            with self._eve_identification_lock:
                candidate = self._eve_identification_candidate
                invalidated: tuple[str, ...] = ()
                if candidate is not None:
                    invalidated = tuple(
                        character_id
                        for character_id in candidate.character_ids
                        if character_id in deleted_ids
                    )
                if invalidated:
                    self._eve_clear_identification_locked()
            return changed or bool(invalidated), invalidated

    def _eve_begin(self, worker, args) -> bool:
        """Claim the mutation lock and hand the work to a thread.

        Refused rather than queued: a queued operation's own confirmation
        would describe state that has since changed.
        """
        if self._eve_identification is not None:
            self._ports.alert(
                "warning",
                "Account identification active",
                "Finish or cancel account identification, then try again.",
            )
            return False
        if not self._eve_mutation.acquire(blocking=False):
            self._ports.alert(
                "warning",
                "EVE Settings busy",
                "Another EVE Settings operation is still running.",
            )
            return False
        try:
            self._ports.spawn(target=worker, args=args, daemon=True).start()
        except Exception:
            # Only the worker releases the lock, and a worker that never
            # started never will: without this the feature is dead until
            # the app restarts.
            self._eve_mutation.release()
            logger.exception("Could not start the EVE Settings worker")
            self._ports.alert(
                "error", "EVE Settings", "That operation could not be started."
            )
            return False
        except BaseException:
            self._eve_mutation.release()
            raise
        return True

    def _eve_done(self, ok: bool, **details) -> None:
        """Tell the page the mutation finished, so it can re-enable its
        buttons and refresh. The bridge call returned as soon as the worker
        was spawned, so this push is the page's only completion signal.

        *details* is how whole-profile copy says more than "finished"
        without a second completion channel: two handlers for one operation
        would let the page close its disclosure on one event and refresh on
        the other, in whichever order they happened to arrive. Callers with
        nothing extra to say pass `ok` alone and the payload is unchanged.
        """
        self._ports.publish_done({"ok": bool(ok), **details})

    def _eve_auto_backup(self, target):
        store = self._ports.backup_root()
        evesettings_backup.create_file_backup(store, target, origin="auto")

    def _eve_prune(self, keep: int, *, candidates=None) -> None:
        store = self._ports.backup_root()
        report = (
            evesettings_backup.prune(store, keep)
            if candidates is None
            else evesettings_backup.prune(store, keep, candidates=candidates)
        )
        if report.failed:
            count = len(report.failed)
            self._ports.alert(
                "warning",
                "Some automatic backups were not removed",
                f"Could not delete {count} automatic backup"
                f"{'s' if count != 1 else ''}. Wingman will try again later.",
            )

    def set_auto_keep(self, value) -> dict:
        current = int(self._eve_section().get("auto_keep", 10))
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        text = str(value).strip()
        if not text.isascii() or not text.isdigit():
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        wanted = int(text)
        if wanted < 1 or wanted > 100:
            return {
                "accepted": False,
                "value": current,
                "error": "Enter a number from 1 to 100.",
            }
        if wanted == current:
            return {"accepted": False, "value": current, "error": None}
        accepted = self._eve_begin(self._eve_auto_keep_worker, (wanted, current))
        return {
            "accepted": accepted,
            "value": current,
            "error": None if accepted else "Another Profiles operation is running.",
        }

    def _eve_auto_keep_worker(self, wanted: int, previous: int) -> None:
        ok = False
        try:
            store = self._ports.backup_root()
            candidates = evesettings_backup.prune_candidates(store, wanted)
            if wanted < previous and candidates:
                count = len(candidates)
                noun = "backup" if count == 1 else "backups"
                if not self._ports.confirm(
                    "Change automatic backup retention",
                    f"Keep {wanted} automatic backups per item?\n\n"
                    f"This will permanently delete {count} older automatic {noun}. "
                    "Manual backups will be kept.",
                    destructive=True,
                ):
                    return
            self._ports.update_settings({"auto_keep": wanted})
            self._eve_prune(wanted, candidates=candidates)
            self._ports.status(f"Keeping {wanted} automatic backups per item.")
            ok = True
        except Exception as error:
            logger.exception("Could not change EVE backup retention")
            self._ports.alert("error", "Retention not changed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def copy(self, source: str, targets: list, groups: list | None = None) -> bool:
        return self._eve_begin(
            self._eve_copy_worker,
            (source, [str(t) for t in targets or []], groups),
        )

    def _eve_copy_worker(
        self, source: str, targets: list, groups: list | None = None
    ) -> None:
        ok = False
        try:
            # None alone means the legacy byte-copy path. An empty list is
            # still a deliberate structured copy that preserves every
            # offered group from each target.
            if groups is None:
                # Derived from the targets, not passed by the page: the
                # Characters / Accounts switch already decides which files are
                # offered, so a mode argument on the bridge would be the same
                # fact written twice and free to disagree. A mixed set (which
                # the page cannot produce, but the bridge does not forbid)
                # resolves to None and falls back to naming files.
                kinds = {evesettings_tree.file_kind(t) for t in targets}
                kind = next(iter(kinds)) if len(kinds) == 1 else None
                # Plain copy remains advisory and best-effort for backwards
                # compatibility: a positive result warns in the confirmation.
                running = self._ports.advisory_client_running()
                preserved_labels = None
            else:
                kind = evesettings_tree.file_kind(source)
                offered = evesettings_selective.groups_for_kind(kind)
                valid_ids = {group.id for group in offered}
                if (
                    not isinstance(groups, list)
                    or any(not isinstance(group_id, str) for group_id in groups)
                    or len(set(groups)) != len(groups)
                    or not set(groups) <= valid_ids
                ):
                    raise ValueError(
                        "Selected groups must be a unique list offered for this file kind."
                    )
                preserved_labels = [
                    group.label for group in offered if group.id not in set(groups)
                ]
                try:
                    running = self._ports.strict_client_running()
                except Exception:
                    logger.exception("Could not verify that EVE is closed")
                    self._ports.alert(
                        "error",
                        "Copy not started",
                        "Wingman could not verify that EVE is closed. "
                        "Close EVE and retry.",
                    )
                    return
                if running:
                    self._ports.alert(
                        "error",
                        "Copy not started",
                        "EVE is running. Close EVE and retry.",
                    )
                    return

            if not self._ports.confirm(
                "Confirm Copy",
                self._ports.format_copy_confirm(
                    [self._eve_label(t) for t in targets],
                    kind,
                    running,
                    source_name=self._eve_label(source),
                    preserved_groups=preserved_labels,
                ),
                destructive=True,
            ):
                return
            if groups is None:
                report = evesettings_ops.copy_to_targets(
                    source,
                    targets,
                    root=self._eve_section().get("root"),
                    backup=self._eve_auto_backup,
                )
            else:
                report = evesettings_ops.copy_selected_to_targets(
                    source,
                    targets,
                    selected_groups=groups,
                    root=self._eve_section().get("root"),
                    backup=self._eve_auto_backup,
                )
            keep = int(self._eve_section().get("auto_keep", 10))
            self._eve_prune(keep)
            if report.failed:
                names = "\n".join(
                    f"  • {Path(o.path).stem}: {o.reason}" for o in report.failed
                )
                self._ports.alert(
                    "error",
                    "Some copies did not happen",
                    f"Copied to {len(report.succeeded)} of "
                    f"{len(report.outcomes)}.\n\n{names}",
                )
            else:
                self._ports.status(
                    self._ports.format_copy_done(len(report.succeeded), kind)
                )
                ok = True
        except Exception as error:
            logger.exception("EVE settings copy failed")
            self._ports.alert("error", "Copy failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    # ---- whole-profile copy ----------------------------------------------

    def copy_profile(self, expected_source: str, mode: str, destination: str) -> dict:
        """Create a new profile from the selected one, or replace another.

        The lock is claimed here rather than through _eve_begin, because two
        things have to happen on the bridge thread before a worker can
        exist. The request is validated against a freshly discovered tree,
        so a token the page rendered before a selection change landed comes
        back as a refusal the user reads beside the button they pressed --
        not as an alert about work that appeared to start. And any legacy
        deep `root` is canonicalized and persisted before a single file is
        touched. A worker could do neither: its answer would arrive after
        this call had already returned "accepted".

        Returns immediately. The outcome arrives through _eve_done.
        """
        if self._eve_identification is not None:
            return {
                "accepted": False,
                "error": "Finish or cancel account identification first.",
            }
        if not self._eve_mutation.acquire(blocking=False):
            return {
                "accepted": False,
                "error": "Another Profiles operation is running.",
            }
        try:
            found = self._eve_discover()
            plan = evesettings_profilecopy.prepare_copy(
                found, expected_source, mode, destination
            )
            try:
                self._eve_persist_selection(found)
            except OSError as error:
                # Aborts untouched. The tree this request was validated
                # against would not be the one on disk in settings, and the
                # design's rule is that a failed canonical write is a copy
                # that never started rather than one that half-happened.
                logger.exception("Could not persist the canonical EVE selection")
                raise ValueError(
                    "Wingman could not save the folder selection, so nothing was "
                    "copied. Check that the settings file is writable and retry."
                ) from error
            self._ports.spawn(
                target=self._eve_copy_profile_worker, args=(plan,), daemon=True
            ).start()
        except (OSError, ValueError) as error:
            self._eve_mutation.release()
            return {"accepted": False, "error": str(error)}
        except Exception:
            # Only the worker releases the lock, and a worker that never
            # started never will -- _eve_begin's rule, and the same cost:
            # every later Profiles mutation refused until the app restarts.
            self._eve_mutation.release()
            logger.exception("Could not start EVE profile copy")
            return {"accepted": False, "error": "Profile copy could not be started."}
        except BaseException:
            self._eve_mutation.release()
            raise
        return {"accepted": True, "error": None}

    def _eve_select_created_profile(self, plan, created) -> bool:
        """Persist the newly created profile as the selection.

        Returns False rather than raising: the profile exists on disk
        either way, and the design keeps publication and remembering the
        selection as separate outcomes so a retry never implies nothing was
        created. A discover() that fell back to some OTHER profile (the
        created one vanished under us) is that same failure, not a licence
        to persist a selection nobody asked for.
        """
        try:
            found = evesettings_tree.discover(plan.root, plan.server, created)
            if not _eve_same_path(found.profile, created):
                logger.warning("The created profile %s was not discoverable", created)
                return False
            self._eve_persist_selection(found)
        except (OSError, ValueError):
            logger.exception("Could not persist the new EVE profile selection")
            return False
        return True

    def _eve_copy_profile_worker(self, plan) -> None:
        ok = False
        published = False
        # Whether the selection the page will see is the one this operation
        # intends. Replacement does not move the selection, and the source
        # it retains was persisted with the whole canonical triple before
        # this worker was spawned -- so it is already true here, on every
        # exit including a declined confirmation or a failed rollback.
        # Creation is the only mode with a NEW selection to save, and only
        # its own save decides this.
        selection_persisted = plan.mode != "new"
        error_message = None
        # Retention runs only once the destination has settled -- after a
        # successful publication, or after a rollback that put the old one
        # back. Pruning while the destination holds a mix of both profiles
        # would consider deleting automatic backups during the one window
        # in which the newest of them is the only way back.
        prune_after = False
        try:
            error_message = self._ports.profile_copy_refusal()
            if error_message:
                self._ports.alert("error", "Copy not started", error_message)
                return
            created = None
            with evesettings_profilecopy.stage_copy(plan) as staged:
                if plan.mode == "new":
                    # No confirmation: creating a profile overwrites
                    # nothing, so there is nothing to warn about.
                    created = evesettings_profilecopy.publish_new(staged)
                    published = True
                else:
                    if not self._ports.confirm(
                        "Confirm Replace",
                        f"Replace {plan.destination_name} with a copy of "
                        f"{plan.source_name}?\n\n{plan.destination_name} is backed "
                        "up first. Its EVE settings files are replaced with "
                        f"{plan.source_name}'s, and any settings file "
                        f"{plan.source_name} does not have is removed.",
                        destructive=True,
                    ):
                        return
                    # Staging happened before the question, so the answer is
                    # the last thing between here and the destination -- and
                    # EVE can start while a confirmation sits on screen.
                    error_message = self._ports.profile_copy_refusal()
                    if error_message:
                        self._ports.alert("error", "Copy not started", error_message)
                        return
                    store = self._ports.backup_root()
                    try:
                        archive = evesettings_backup.create_profile_backup(
                            store, plan.destination, origin="auto"
                        )
                    except Exception as failure:
                        logger.exception(
                            "Could not back up %s before replacing it", plan.destination
                        )
                        error_message = (
                            f"{plan.destination_name} was not changed: Wingman "
                            "could not back it up first. "
                            f"{evesettings_ops.describe(failure)}"
                        )
                        self._ports.alert(
                            "error", "Destination unchanged", error_message
                        )
                        return

                    def rollback() -> None:
                        # backup_current=False: the archive taken moments ago
                        # IS what rollback restores from. A fresh backup here
                        # would archive the half-published profile this call
                        # exists to erase, and would add a second chance to
                        # fail inside the recovery path itself.
                        evesettings_backup.restore(
                            store, archive, plan.root, backup_current=False
                        )

                    try:
                        evesettings_profilecopy.publish_replacement(
                            staged, rollback=rollback
                        )
                    except evesettings_profilecopy.ReplacementFailed as failure:
                        logger.exception("EVE profile replacement failed")
                        prune_after = failure.destination_restored
                        if failure.destination_restored:
                            error_message = (
                                f"{plan.destination_name} was restored from its "
                                "automatic backup and is unchanged. "
                                f"{evesettings_ops.describe(failure.publication_error)}"
                            )
                            self._ports.alert(
                                "error", "Replacement failed", error_message
                            )
                        else:
                            # The archive is named because it is now the only
                            # way back, and Backups is where it is restored
                            # from -- an instruction, not an error code.
                            error_message = (
                                f"{plan.destination_name} may now hold a mix of both "
                                "profiles and Wingman could not put it back. Restore "
                                f"{archive.name} from Backups. "
                                f"{evesettings_ops.describe(failure.publication_error)}"
                            )
                            self._ports.alert(
                                "error",
                                "Replacement and rollback failed",
                                error_message,
                            )
                        return
                    published = True
                    prune_after = True
            # Staging is gone by here: the design removes it before
            # retention runs, and before anything reports success.
            if plan.mode == "new":
                selection_persisted = self._eve_select_created_profile(plan, created)
                if selection_persisted:
                    self._ports.status(f"Created {plan.destination_name}.")
                else:
                    # Still ok: the profile is on disk and the refreshed
                    # dropdown offers it. Only the selection was lost, and
                    # saying "failed" would invite a retry that collides
                    # with the profile this call just created.
                    error_message = (
                        f"Created {plan.destination_name}, but Wingman could not "
                        "remember the selection. Select it from Profile."
                    )
                    self._ports.alert("warning", "Profile created", error_message)
            else:
                # The source stays selected, and it already is -- see the
                # initialiser above: the canonical triple was persisted
                # when the request was accepted, and replacement never
                # moves the selection.
                self._ports.status(
                    f"Replaced {plan.destination_name} with a copy of "
                    f"{plan.source_name}."
                )
            ok = True
        except Exception as failure:
            logger.exception("EVE profile copy failed")
            error_message = evesettings_ops.describe(failure)
            self._ports.alert("error", "Copy failed", error_message)
        finally:
            if prune_after:
                try:
                    self._eve_prune(int(self._eve_section().get("auto_keep", 10)))
                except Exception:
                    # Retention is housekeeping. It must never be the reason
                    # the lock is not released or the page never hears that
                    # the copy it is waiting on has finished.
                    logger.exception("Could not prune automatic backups")
            self._eve_mutation.release()
            self._eve_done(
                ok,
                operation="profile_copy",
                mode=plan.mode,
                published=published,
                selection_persisted=selection_persisted,
                error=error_message,
            )

    def backup(self, path: str, kind: str) -> bool:
        return self._eve_begin(self._eve_backup_worker, (path, kind))

    def _eve_backup_worker(self, path: str, kind: str) -> None:
        ok = False
        try:
            # Decided here, not in the page: an empty path is what Path()
            # resolves to the app's own working directory, which
            # create_profile_backup would happily walk and report as a
            # successful backup of nothing.
            if not path:
                raise ValueError("Choose a settings set to back up first.")
            resolved = evesettings_tree.require_under(
                self._eve_section().get("root"), path
            )
            if not resolved.exists():
                raise ValueError("That no longer exists.")
            store = self._ports.backup_root()
            if kind == "profile":
                evesettings_backup.create_profile_backup(store, path, origin="manual")
            else:
                evesettings_backup.create_file_backup(store, path, origin="manual")
            label = (
                f"{resolved.name.removeprefix('settings_')} profile"
                if kind == "profile"
                else self._eve_label(resolved)
            )
            self._ports.status(f"Backed up {label}.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings backup failed")
            self._ports.alert("error", "Backup failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def restore(self, archive: str) -> bool:
        return self._eve_begin(self._eve_restore_worker, (archive,))

    def _eve_restore_worker(self, archive: str) -> None:
        ok = False
        try:
            info = evesettings_backup.parse_name(Path(archive).name)
            target = "this backup"
            created = ""
            if info is not None:
                target = self._eve_backup_identity(info)[0]
                try:
                    match = datetime.datetime.strptime(
                        info.created, "%Y%m%d-%H%M%S"
                    ).replace(tzinfo=datetime.UTC)
                except ValueError:
                    created = f" from {info.created}"
                else:
                    created = f" from {match:%Y-%m-%d %H:%M UTC}"
            if not self._ports.confirm(
                "Confirm Restore",
                f"Restore {target}{created}?\n\nThe current settings are backed "
                "up first. For a whole settings set, any file not in the "
                "backup is removed.",
                destructive=True,
            ):
                return
            store = self._ports.backup_root()
            found = self._eve_discover()
            if found.root is None:
                raise ValueError("Choose the EVE settings folder first.")
            written = evesettings_backup.restore(store, archive, found.root)
            keep = int(self._eve_section().get("auto_keep", 10))
            self._eve_prune(keep)
            self._ports.status(f"Restored into {written.name}.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings restore failed")
            self._ports.alert("error", "Restore failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    def delete_backup(self, archive: str) -> bool:
        return self._eve_begin(self._eve_delete_backup_worker, (archive,))

    def _eve_delete_backup_worker(self, archive: str) -> None:
        ok = False
        try:
            if not self._ports.confirm(
                "Confirm Delete",
                f"Permanently delete {Path(archive).name}?\n\nThis cannot be undone.",
                destructive=True,
            ):
                return
            evesettings_backup.delete(self._ports.backup_root(), archive)
            self._ports.status("Backup deleted.")
            ok = True
        except Exception as error:
            logger.exception("EVE settings backup delete failed")
            self._ports.alert("error", "Delete failed", str(error))
        finally:
            self._eve_mutation.release()
            self._eve_done(ok)

    # -- probe formations ---------------------------------------------------

    def _eve_account_file(self, path: str) -> Path:
        """Containment + kind check shared by the two formation endpoints."""
        root = self._eve_section().get("root")
        if not root:
            raise ValueError("Choose the EVE settings folder first.")
        resolved = evesettings_tree.require_under(root, path, suffix=".dat")
        if evesettings_tree.file_kind(resolved) != "account":
            raise ValueError(
                "Formations live in an account file, not a character file."
            )
        return resolved

    def formations(self, path: str) -> dict:
        """Decode one account file and return its user formations, in meters.

        Synchronous on purpose: a decode is milliseconds, and the page needs
        the answer to draw the editor. _eve_hold keeps it from reading a
        file a copy worker is mid-way through replacing.
        """
        with self._eve_hold() as held:
            if not held:
                return {
                    "ok": False,
                    "error": "Another EVE Settings operation is still running.",
                }
            try:
                target = self._eve_account_file(path)
                snapshot = evesettings_codec.read_snapshot(target)
                found = evesettings_formations.read_formations(snapshot.document.doc)
            except (ValueError, OSError, evesettings_codec.CodecError) as error:
                return {"ok": False, "error": str(error)}
            return {
                "ok": True,
                "path": str(target),
                "name": self._eve_label(str(target)),
                "formations": evesettings_formations.to_payload(found),
                "content_revision": snapshot.content_revision,
                "sharing_limits": evesettings_formation_sharing.limits_payload(),
            }

    def export_formations(self, items: list) -> dict:
        """Prepare selected draft values only; the page owns clipboard outcomes."""
        try:
            return {
                "ok": True,
                "text": evesettings_formation_sharing.export_text(items),
            }
        except ValueError as error:
            return {"ok": False, "error": str(error)}

    def parse_formations(self, text: str, existing_names: list) -> dict:
        """Review clipboard text against draft names, never against an account file."""
        try:
            found = evesettings_formation_sharing.parse_text(text)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return self.validate_formation_import(
            evesettings_formations.to_payload(found), existing_names
        )

    def validate_formation_import(self, items: list, existing_names: list) -> dict:
        """Revalidate an explicit Add snapshot; no pending Python import session."""
        try:
            found, conflicts = evesettings_formation_sharing.prepare_import(
                items, existing_names
            )
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {
            "ok": True,
            "formations": evesettings_formations.to_payload(found),
            "conflicts": conflicts,
        }

    def save_formations(
        self,
        path: str,
        formations: list,
        expected_content_revision: str = "",
        request_id: str = "",
    ) -> bool:
        return self._eve_begin(
            self._eve_save_formations_worker,
            (path, formations, expected_content_revision, request_id),
        )

    def _eve_save_formations_worker(
        self, path: str, items: list, expected_content_revision: str, request_id: str
    ) -> None:
        ok = False
        committed_revision = ""
        error_code = ""
        error_message = ""
        warnings = []
        completed_path = path if isinstance(path, str) else ""
        correlation = ""
        try:
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ValueError(
                    "A save request needs a request ID of 1 to 128 characters."
                )
            correlation = request_id
            if (
                not isinstance(expected_content_revision, str)
                or len(expected_content_revision) != 64
                or any(c not in "0123456789abcdef" for c in expected_content_revision)
            ):
                raise ValueError(
                    "Reload this account before saving: a content revision is required."
                )
            target = self._eve_account_file(path)
            completed_path = str(target)
            wanted = evesettings_formations.from_payload(items)
            evesettings_formations.validate(wanted)
            # Fail closed while a client runs: EVE holds core_*.dat open for
            # the session and rewrites it on exit, so a write now is either
            # refused by the sharing violation or silently overwritten
            # later. Copy merely warns because its targets are usually not
            # the running character; this always is the running account.
            try:
                running = self._ports.strict_client_running()
            except Exception as error:
                logger.exception("Could not verify that EVE is closed")
                raise RuntimeError(
                    "Wingman could not verify that EVE is closed. Close EVE and retry."
                ) from error
            if running:
                raise RuntimeError("The file is in use. Close EVE and retry.")
            snapshot = evesettings_codec.read_snapshot(target)
            if snapshot.content_revision != expected_content_revision:
                raise evesettings_codec.ContentChangedError(
                    "The settings file changed."
                )
            updated = evesettings_formations.write_formations(
                snapshot.document.doc, wanted, now=time.time()
            )
            committed_revision = evesettings_codec.write_document(
                target,
                evesettings_codec.Document(updated, snapshot.document.had_crc),
                backup=self._eve_auto_backup,
                expected_content_revision=expected_content_revision,
            )
            ok = True
            # Publication is final. Housekeeping failures must not invite a
            # retry of committed edits or erase the baseline the page now owns.
            try:
                self._eve_prune(int(self._eve_section().get("auto_keep", 10)))
            except Exception:
                logger.exception(
                    "Could not prune automatic backups after formation save"
                )
                warnings.append(
                    "Formations saved, but automatic backups could not be pruned."
                )
            try:
                self._ports.status(
                    f"Saved {len(wanted)} formation(s) to {self._eve_label(str(target))}."
                )
            except Exception:
                logger.exception("Could not report formation save status")
                warnings.append(
                    "Formations saved, but Wingman could not update its status."
                )
        except evesettings_codec.ContentChangedError:
            error_code = "stale_file"
            error_message = (
                "This account's settings changed since you opened them. Nothing was saved. "
                "Copy the formations you want to keep, then reload the account before pasting them back."
            )
        except ValueError as error:
            error_code = "invalid_request"
            error_message = str(error)
        except evesettings_codec.CodecError as error:
            error_code = "save_failed"
            error_message = str(error)
        except Exception as error:
            logger.exception("formation save failed")
            error_code = "save_failed"
            error_message = evesettings_ops.describe(error)
        finally:
            try:
                if not ok:
                    self._ports.alert("error", "Formations not saved", error_message)
            finally:
                self._eve_mutation.release()
                self._eve_done(
                    ok,
                    operation="formations_save",
                    path=completed_path,
                    request_id=correlation,
                    content_revision=committed_revision,
                    error_code=error_code,
                    error=error_message,
                    warning=" ".join(warnings),
                )
