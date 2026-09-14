"""Saved primary layouts on borrowed bridge-call threads, never another worker.

The store orders durable generations; the host owns native completion. This owner
only reserves named actions, accepts commits and publishes detached semantic state.
No effect or future wait runs under its condition, including final publication.
"""

import copy
import logging
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, replace
from threading import Condition

from . import layout, roster
from . import savedlayouts as model
from .geometry import Rect
from .layoutadmission import PrimaryLayoutAdmission, PrimaryLayoutLease
from .savedlayouts import LayoutCommit, PrimaryLayoutCapture, PrimaryLayoutLiveResult
from .store import LayoutStore

logger = logging.getLogger(__name__)
_BUSY = "Finish the pending Preview change and try again."
_CLOSED = "Previews are shutting down."


@dataclass(frozen=True)
class PreviewLayoutsPorts:
    read_preview: Callable[[], dict]
    live_names: Callable[[], tuple[str, ...]]
    capture: Callable[[PrimaryLayoutLease], Future[PrimaryLayoutCapture]]
    apply: Callable[
        [
            PrimaryLayoutLease,
            PrimaryLayoutCapture,
            LayoutCommit,
            Mapping[str, Rect | None],
        ],
        Future[PrimaryLayoutLiveResult],
    ]
    refresh_visibility: Callable[[PrimaryLayoutLease], Future[PrimaryLayoutLiveResult]]
    refresh_geometry: Callable[[], dict]
    release: Callable[[PrimaryLayoutLease], None]
    publish_state: Callable[[dict], None]


class PreviewGeometryUnavailable(Exception):
    """A failed fresh observation retains the last detached projection, if any."""

    def __init__(self, message: str, geometry: dict | None):
        super().__init__(message)
        self.geometry = geometry


class _Unchanged(Exception):
    """Abort settings.update without rewriting already committed metadata."""


class PreviewLayoutsController:
    def __init__(
        self,
        initial: dict,
        *,
        store: LayoutStore,
        admission: PrimaryLayoutAdmission,
        ports: PreviewLayoutsPorts,
        id_factory: Callable[[], str],
    ):
        self._store = store
        self._admission = admission
        self._ports = ports
        self._id_factory = id_factory
        self._condition = Condition()
        self._closed = False
        self._active = set()
        self._named = None
        self._operation = None
        self._next_id = 0
        self._revision = 0
        self._commit_revision = 0
        self._latest_commit: LayoutCommit | None = None
        self._preview = copy.deepcopy(initial)

    def state(self) -> dict:
        with self._condition:
            commit = self._latest_commit
            needs_projection = (
                commit is not None and commit.revision > self._commit_revision
            )
        if needs_projection:
            try:
                self._accept_commit(commit)
            except Exception:
                # Keep the last usable projection, but never discard the durable
                # authority. A later read can recover without another mutation.
                logger.exception("Could not rebuild committed Preview state")
        # Sampling may overlap a commit. Only owner evidence is borrowed; never
        # replace accepted exclusions/records with a stale sampled dictionary.
        sampled = model.known_owners(
            self._ports.read_preview(), self._ports.live_names()
        )
        admission = self._admission.snapshot()
        with self._condition:
            preview = copy.deepcopy(self._preview)
            revision = self._revision
            operation = copy.deepcopy(self._operation)
            named, closed = self._named is not None, self._closed
        records = model.deserialize(preview.get("saved_layouts"))
        shared = not (closed or admission.closed or admission.exclusive)
        return {
            "revision": revision,
            "layouts": [
                {
                    "id": r.id,
                    "name": r.name,
                    "revision": model.record_revision(r),
                    "character_count": len(r.characters),
                }
                for r in records
            ],
            "owners": list(model.known_owners(preview, sampled)),
            "excluded": list(preview.get("excluded") or []),
            "busy": named or admission.exclusive or bool(admission.shared_count),
            "availability": {
                "capture": shared and not named and not admission.shared_count,
                "edit": shared and not named,
                "visibility": shared,
            },
            "operation": operation,
        }

    def close_admission(self) -> None:
        with self._condition:
            if not self._closed:
                self._closed = True
                self._revision += 1
        self._admission.close()

    def shutdown(self, timeout: float = 5.0) -> bool:
        self.close_admission()
        with self._condition:
            return self._condition.wait_for(lambda: not self._active, timeout)

    def save_current(self, name) -> dict:
        return self._run("save", name=name)

    def apply(self, layout_id, revision) -> dict:
        return self._run("apply", layout_id=layout_id, revision=revision)

    def update_saved(self, layout_id, revision) -> dict:
        return self._run("update", layout_id=layout_id, revision=revision)

    def rename(self, layout_id, revision, name) -> dict:
        return self._run("rename", layout_id=layout_id, revision=revision, name=name)

    def remove(self, layout_id, revision) -> dict:
        return self._run("remove", layout_id=layout_id, revision=revision)

    def set_excluded(self, name, excluded) -> dict:
        return self._run("excluded", name=name, excluded=bool(excluded))

    @staticmethod
    def _record(records, layout_id, revision):
        record = next((r for r in records if r.id == layout_id), None)
        if record is None:
            raise ValueError("That saved layout no longer exists.")
        if model.record_revision(record) != revision:
            raise ValueError("That saved layout changed. Select it again and retry.")
        return record

    @staticmethod
    def _name(name, records, layout_id=None):
        if not isinstance(name, str) or not name.strip() or not name.isprintable():
            raise ValueError("Saved layout name must be nonblank and printable.")
        name = name.strip()
        if any(
            r.id != layout_id and r.name.casefold() == name.casefold() for r in records
        ):
            raise ValueError("A saved layout already has that name.")
        return name

    def _validate(self, action, records, layout_id, revision, name):
        if action == "excluded":
            # Ordinary exclusions predate strict snapshot owners. Keep their
            # identity policy, including exact whitespace/control characters.
            if not roster.deserialize([name], cap=None):
                raise ValueError("Invalid Preview character name.")
            return None, name
        record = (
            None if action == "save" else self._record(records, layout_id, revision)
        )
        if action in ("save", "rename"):
            name = self._name(name, records, layout_id if action == "rename" else None)
        return record, name

    def _accept_commit(self, commit: LayoutCommit) -> None:
        with self._condition:
            if (
                commit is not self._latest_commit
                or commit.revision <= self._commit_revision
            ):
                return
        saved = model.serialize(commit.saved)
        layouts = layout.serialize(dict(commit.layouts))
        with self._condition:
            # Projection may finish after another caller accepted a newer commit.
            if (
                commit is self._latest_commit
                and commit.revision > self._commit_revision
            ):
                self._preview.update(
                    saved_layouts=saved, layouts=layouts, excluded=list(commit.excluded)
                )
                self._commit_revision = commit.revision
                self._revision += 1

    def _publish(self) -> str | None:
        try:
            payload = self.state()
            with self._condition:
                allowed = not self._closed
            if allowed:
                # The production adapter rechecks final delivery immediately
                # before touching the page. Closure never waits for that page.
                self._ports.publish_state(payload)
        except Exception as exc:
            logger.exception("Could not publish Preview layouts")
            return f"Could not refresh Preview layout state: {exc}"
        return None

    def _receipt(self, operation, geometry=None) -> dict:
        return {
            **{
                k: operation[k]
                for k in ("applied", "persisted", "error", "live", "warning")
            },
            "operation_id": operation["id"],
            "geometry": geometry,
            "state": self.state(),
        }

    def _run(self, action, *, layout_id=None, revision=None, name=None, excluded=False):
        named = action != "excluded"
        with self._condition:
            self._next_id += 1
            operation = {
                "id": self._next_id,
                "action": action,
                "pending": False,
                "applied": False,
                "persisted": False,
                "live": None,
                "warning": None,
                "error": None,
            }
            records = (
                self._latest_commit.saved
                if self._latest_commit is not None
                else model.deserialize(self._preview.get("saved_layouts"))
            )
        try:
            _, name = self._validate(action, records, layout_id, revision, name)
        except ValueError as exc:
            operation["error"] = str(exc)
            return self._receipt(operation)
        with self._condition:
            if self._closed or (named and self._named is not None):
                operation["error"] = _CLOSED if self._closed else _BUSY
            else:
                self._active.add(operation["id"])
                operation["pending"] = True
                if named:
                    self._named = operation["id"]
                    self._operation = dict(operation)
                self._revision += 1
        if operation["error"]:
            return self._receipt(operation)
        lease = None
        commit = None
        captured = None
        target = None
        warnings = []
        geometry = None
        try:
            try:
                lease = self._admission.try_begin(
                    exclusive=action in ("save", "update", "apply")
                )
                if lease is None:
                    raise ValueError(_BUSY)
                warning = self._publish()
                if warning:
                    warnings.append(warning)
                if action in ("save", "update", "apply"):
                    captured = self._ports.capture(lease).result()
                identity = self._id_factory() if action == "save" else layout_id

                def mutate(section):
                    nonlocal target
                    # This is the last pre-write fence. Once admitted here, the
                    # settings transaction finishes even if final close follows.
                    with self._condition:
                        if self._closed:
                            raise ValueError(_CLOSED)
                    records = model.deserialize(section.get("saved_layouts"))
                    target, clean_name = self._validate(
                        action, records, layout_id, revision, name
                    )
                    if action == "excluded":
                        current = list(section.get("excluded") or [])
                        if (name in current) == excluded:
                            with self._condition:
                                acknowledged = (
                                    tuple(current) == self._latest_commit.excluded
                                    if self._latest_commit is not None
                                    else current == self._preview.get("excluded", [])
                                )
                            if acknowledged:
                                raise _Unchanged
                            # A prior successful callback may still be delayed.
                            # Obtain a newer STORE receipt rather than inventing
                            # a sequence for sampled/no-op configuration.
                        section["excluded"] = (
                            [*current, name]
                            if excluded
                            else [n for n in current if n != name]
                        )
                    elif action == "apply":
                        model.apply_snapshot(section, target)
                    else:
                        if action in ("save", "update"):
                            preview = copy.deepcopy(captured.preview)
                            # All named sessions count, even when no primary was
                            # created. Do not mutate the host's exact capture token.
                            preview["seen"] = list(
                                model.known_owners(
                                    preview,
                                    tuple(s.character for s in captured.sessions),
                                )
                            )
                            characters = model.capture_characters(
                                preview,
                                dict(captured.retained),
                                dict(captured.live_rectangles),
                            )
                            proposed = model.SavedLayout(
                                identity,
                                clean_name if action == "save" else target.name,
                                characters,
                            )
                        elif action == "rename":
                            if target.name == clean_name:
                                raise _Unchanged
                            proposed = replace(target, name=clean_name)
                        if action == "save":
                            records = (*records, proposed)
                        elif action == "remove":
                            records = tuple(r for r in records if r.id != layout_id)
                        else:
                            records = tuple(
                                proposed if r.id == layout_id else r for r in records
                            )
                        section["saved_layouts"] = model.serialize(records)

                commit = self._store.transact(mutate)
            except _Unchanged:
                operation.update(applied=True, persisted=True)
            except Exception as exc:  # noqa: BLE001 -- borrowed bridge thread must settle precommit failures and release its exact lease.
                operation["error"] = str(exc) or type(exc).__name__
            else:
                # Retain immutable authority before any fallible projection or
                # publication. Delayed older callers cannot replace this receipt.
                with self._condition:
                    if (
                        self._latest_commit is None
                        or commit.revision > self._latest_commit.revision
                    ):
                        self._latest_commit = commit
                # Never let cache/page/native failures turn a durable acceptance
                # into a false rollback receipt. Native still consumes the commit.
                operation.update(applied=True, persisted=True)
                try:
                    self._accept_commit(commit)
                except Exception as exc:
                    logger.exception("Could not accept committed Preview state")
                    warnings.append(
                        f"Saved, but could not refresh Preview state: {exc}"
                    )
                with self._condition:
                    if named:
                        self._operation = dict(operation)
                        self._revision += 1
                warning = self._publish()
                if warning:
                    warnings.append(warning)
            if operation["persisted"] and action in ("apply", "excluded"):
                try:
                    if action == "apply":
                        preferred = dict(commit.layouts)
                        rectangles = {
                            c.name: preferred[c.name].rect
                            if c.rect is not None
                            else None
                            for c in target.characters
                        }
                        result = self._ports.apply(
                            lease, captured, commit, rectangles
                        ).result()
                    else:
                        result = self._ports.refresh_visibility(lease).result()
                    operation["live"] = result.live
                    if result.warning:
                        warnings.append(result.warning)
                except Exception as exc:
                    logger.exception("Could not deliver committed Preview change")
                    operation["live"] = "incomplete"
                    warnings.append(
                        f"Saved, but live Preview application is incomplete: {exc}"
                    )
            if operation["persisted"]:
                try:
                    # Native and retained authority have settled. Apply still
                    # owns exclusive admission; metadata/visibility remain shared.
                    geometry = self._ports.refresh_geometry()
                except Exception as exc:
                    logger.exception("Could not sample settled Preview geometry")
                    if isinstance(exc, PreviewGeometryUnavailable):
                        geometry = exc.geometry
                    warnings.append(
                        f"Saved, but could not refresh Preview geometry: {exc}"
                    )
        finally:
            if lease is not None:
                try:
                    self._ports.release(lease)
                except Exception as exc:
                    logger.exception("Could not release Preview layout host state")
                    warnings.append(f"Could not finish Preview delivery: {exc}")
                finally:
                    self._admission.finish(lease)
            operation["pending"] = False
            operation["warning"] = " ".join(warnings) or None
            with self._condition:
                if named:
                    self._named = None
                    self._operation = dict(operation)
                self._revision += 1
            try:
                warning = self._publish()
                if warning:
                    operation["warning"] = " ".join(
                        filter(None, (operation["warning"], warning))
                    )
                    with self._condition:
                        if named and self._operation["id"] == operation["id"]:
                            self._operation = dict(operation)
                            self._revision += 1
                receipt = self._receipt(operation, geometry)
            finally:
                with self._condition:
                    self._active.remove(operation["id"])
                    self._condition.notify_all()
        return receipt
