"""Pump-owned companion resources. Persistence and page publication live elsewhere.

A hidden candidate is not live authority. Only the worker's promote command can
swap it after persistence; its original pump/family epoch is never rewritten.
"""

import itertools
import ntpath
from dataclasses import dataclass
from uuid import uuid4

from . import geometry, win32
from .companions import (
    MAX_ENABLED,
    CompanionEvent,
    CompanionSelection,
    CompanionSpec,
    CompanionToken,
    GeometryDelta,
    PreparedCompanion,
    RegionSelection,
    matching_sources,
    region_from_pixels,
    region_to_pixels,
)
from .companionwindow import CompanionWindow
from .layout import Rect
from .regionpicker import RegionPicker
from .sources import SourceCatalog, SourceUnavailable


@dataclass
class _Live:
    spec: CompanionSpec
    binding: object
    revision: int
    window: object = None


@dataclass
class _Candidate:
    token: CompanionToken
    binding: object
    definition: object = None
    window: object = None
    picker: object = None
    terminal: tuple | None = None
    selection: object = None


class CompanionFamily:
    def __init__(
        self,
        libs,
        controller,
        *,
        pump_epoch,
        authorized,
        temporary,
        monitors,
        catalog=None,
        create_window=CompanionWindow.create,
        create_picker=RegionPicker.create,
    ):
        self._libs = libs
        self._controller = controller
        self._pump_epoch = pump_epoch
        self._authorized = authorized
        self._temporary_available = temporary
        self._monitors = monitors
        self._catalog = (
            catalog
            if catalog is not None
            else SourceCatalog(libs, libs.kernel32.GetCurrentProcessId())
        )
        self._create_window = create_window
        self._create_picker = create_picker
        self._epoch = 0
        self._specs = {}
        self.live = {}
        self._candidate = None
        self._retired = []
        self._revisions = {}
        self._errors = {}
        self._failed_sources = {}
        self._sequence = itertools.count(1)
        self._activation = None
        self._closed = False

    @property
    def temporary_busy(self):
        return self._candidate is not None or bool(self._retired)

    def _event(self, kind, token=None, payload=None):
        # Controller.native_event is a bounded metadata enqueue, never IO/JS.
        self._controller.native_event(CompanionEvent(kind, token, payload))

    def _token(self, spec):
        return CompanionToken(
            0, spec.definition.id, self._pump_epoch, self._epoch, spec.generation, None
        )

    def _next_revision(self, identity, minimum=0):
        value = max(self._revisions.get(identity, 0), minimum) + 1
        self._revisions[identity] = value
        return value

    def _status(self):
        rows = []
        for identity, spec in self._specs.items():
            live = self.live.get(identity)
            status, error = self._errors.get(identity, ("waiting", None))
            if status == "stopping":
                pass  # A failed native release remains visible even after Off.
            elif not spec.definition.enabled:
                status, error = "disabled", None
            elif not self._authorized(self._token(spec), promotion=True):
                status = "off"
            elif live is not None and not live.window.failed and error is None:
                status, error = "live", None
            rows.append(
                dict(
                    id=identity,
                    generation=spec.generation,
                    binding_revision=self._revisions.get(
                        identity, spec.binding_revision
                    ),
                    status=status,
                    error=error,
                    binding=live.binding
                    if live is not None and status == "live"
                    else None,
                    rect=live.window.rect
                    if live is not None
                    else spec.definition.window,
                )
            )
        self._event("status", payload=tuple(rows))

    def _verify(self, binding):
        return self._catalog.verify(binding)

    def _close_live(self, identity):
        live = self.live.get(identity)
        if live is None:
            return True
        live.window.set_hidden(True)
        if not live.window.close():
            self._errors[identity] = ("stopping", "Companion cleanup is still pending")
            return False
        self.live.pop(identity, None)
        self._next_revision(identity, live.revision)
        if self._activation and self._activation[0] is live:
            self._activation = None
        return True

    def _clean_retired(self):
        self._retired = [window for window in self._retired if not window.close()]
        return not self._retired

    def _finish(self, candidate, kind="closed", reason=None):
        if self._candidate is not candidate:
            return True
        candidate.terminal = (kind, reason)
        if candidate.picker is not None:
            picker = candidate.picker
            picker.cancel(reason or "Selection cancelled")
            if self._candidate is not candidate:
                return True  # Synchronous cleanup already delivered the one ack.
            # Picker callbacks certify release of the complete native bundle.
            if candidate.picker is not None:
                return False
        if candidate.window is not None:
            if not candidate.window.close():
                return False
            candidate.window = None
        self._candidate = None
        self._event(kind, candidate.token, reason)
        return True

    def _reserve(self, token, binding):
        if self._candidate is not None:
            if self._candidate.token == token and self._candidate.terminal is None:
                return self._candidate
            self._event("failed", token, "Another source selection is still pending")
            return None
        if self._closed or self._retired or not self._temporary_available():
            self._event("failed", token, "Another preview selection is still pending")
            return None
        candidate = _Candidate(token, binding)
        self._candidate = candidate
        return candidate

    def command(self, command):
        token, payload = command.token, command.payload
        if command.kind == "reconcile":
            self.reconcile(*payload)
            return
        if command.kind in ("promote", "discard"):
            candidate = self._candidate
            if candidate is None or candidate.token != token:
                self._event("closed", token)
            elif command.kind == "discard":
                self._finish(candidate)
            else:
                self._promote(candidate)
            return
        if token is None or not self._authorized(token):
            self._event("failed", token, "Source selection expired")
            return
        try:
            if command.kind == "enumerate":
                bindings = {
                    uuid4().hex: binding for binding in self._catalog.enumerate()
                }
                rows = tuple(
                    dict(
                        candidate_token=key,
                        application=ntpath.basename(value.executable_path),
                        title=value.title,
                    )
                    for key, value in bindings.items()
                )
                self._event("sources", token, (rows, bindings))
            elif command.kind == "prepare":
                self._prepare(token, *payload)
            elif command.kind == "pick-region":
                self._pick(token, payload)
            elif command.kind == "reset":
                live = self.live.get(token.id)
                if live is not None and live.spec.generation == token.generation:
                    live.window.move(
                        geometry.clamp_to_monitors(payload, self._monitors())
                    )
            elif command.kind == "activate":
                live = self.live.get(token.id)
                if (
                    live is not None
                    and live.spec.generation == token.generation
                    and live.revision == payload
                ):
                    self._activate(live)
        except (SourceUnavailable, OSError, ValueError) as exc:
            candidate = self._candidate
            if candidate is not None and candidate.token == token:
                self._finish(candidate, "failed", str(exc))
            else:
                self._event("failed", token, str(exc))

    def _placement(self, definition, binding, source, *, new=False):
        monitors = self._monitors()
        if not monitors:
            raise SourceUnavailable("No display is available for the companion")
        if new:
            area = source or Rect(0, 0, *binding.client_size)
            monitor = monitors[0]
            scale = min(
                320 / area.w, 210 / area.h, monitor.w / area.w, monitor.h / area.h
            )
            size = max(1, int(area.w * scale)), max(1, int(area.h * scale))
            return geometry.default_stack(0, monitor, size)
        return geometry.clamp_to_monitors(definition.window, monitors)

    def _prepare(self, token, definition, binding):
        candidate = self._reserve(token, binding)
        if candidate is None:
            return
        if candidate.picker is not None or candidate.window is not None:
            return
        fresh = self._verify(binding)
        if fresh is None or fresh.client_size != binding.client_size:
            raise SourceUnavailable("Source window changed. Choose it again.")
        source = None
        if definition.region is not None:
            original = (
                definition.region.original_client_w,
                definition.region.original_client_h,
            )
            if candidate.selection is not None and fresh.client_size != original:
                raise SourceUnavailable("Source size changed. Select the region again.")
            if (
                candidate.selection is not None
                and candidate.selection.region != definition.region
            ):
                raise SourceUnavailable("Region selection expired")
            source = region_to_pixels(definition.region, fresh.client_size)
            if source is None:
                raise SourceUnavailable("The selected region is too small")
        candidate.definition, candidate.binding = definition, fresh
        rect = self._placement(definition, fresh, source, new=token.generation == 1)
        candidate.window = self._create_window(
            self._libs,
            fresh,
            rect,
            source,
            on_activate=lambda: None,
            on_geometry=lambda rect: None,
        )
        if candidate.window is None or candidate.window.failed:
            raise SourceUnavailable("Source window could not be captured")
        verified = self._verify(fresh)
        if (
            verified is None
            or verified.client_size != fresh.client_size
            or not self._authorized(token)
        ):
            raise SourceUnavailable("Source changed while preparing the companion")
        self._event(
            "prepared",
            token,
            PreparedCompanion(verified, verified.client_size, rect, definition.region),
        )

    def _pick(self, token, request):
        if token.selection_lease is None:
            raise SourceUnavailable("A source selection lease is required")
        candidate = self._reserve(token, request.binding)
        if (
            candidate is None
            or candidate.picker is not None
            or candidate.window is not None
        ):
            return
        fresh = self._verify(request.binding)
        if fresh is None or fresh.client_size != request.binding.client_size:
            raise SourceUnavailable("Source changed. Choose the window again.")
        monitors = self._monitors()
        if not monitors:
            raise SourceUnavailable("No display is available for selection")
        candidate.binding = fresh

        def confirm(binding, pixels, size):
            candidate.picker = None
            if self._candidate is not candidate:
                return
            if candidate.terminal is not None:
                self._finish(candidate, *candidate.terminal)
                return
            try:
                verified = self._verify(binding)
                if (
                    verified is None
                    or verified.client_size != size
                    or size != fresh.client_size
                    or not self._authorized(token)
                ):
                    raise SourceUnavailable("Source changed. Select the region again.")
                selection = RegionSelection(
                    verified, size, region_from_pixels(pixels, size)
                )
                candidate.selection = selection
                self._event("region-selected", token, selection)
            except (SourceUnavailable, ValueError, OSError) as exc:
                self._finish(candidate, "failed", str(exc))

        def cancel(reason):
            candidate.picker = None
            if self._candidate is candidate:
                self._finish(candidate, *(candidate.terminal or ("failed", reason)))

        picker = self._create_picker(
            self._libs,
            fresh,
            monitors[0],
            caption=request.caption,
            on_confirm=confirm,
            on_cancel=cancel,
        )
        if self._candidate is candidate and candidate.selection is None:
            candidate.picker = picker
            if picker is None:
                self._finish(candidate, "failed", "Region picker could not open")
            else:
                verified = self._verify(fresh)
                if (
                    verified is None
                    or verified.client_size != fresh.client_size
                    or not self._authorized(token)
                ):
                    self._finish(
                        candidate, "failed", "Source changed while opening selection"
                    )

    def _wire_window(self, live):
        def activate():
            self._activate(live)

        def moved(rect):
            identity = live.spec.definition.id
            if self.live.get(identity) is live and self._authorized(
                self._token(live.spec), promotion=True
            ):
                self._event(
                    "geometry",
                    payload=GeometryDelta(
                        identity,
                        live.spec.generation,
                        live.revision,
                        next(self._sequence),
                        rect,
                    ),
                )

        return activate, moved

    def _promote(self, candidate):
        token = candidate.token
        if (
            candidate.window is None
            or candidate.window.failed
            or candidate.terminal is not None
        ):
            self._finish(candidate)
            return
        definition = candidate.definition
        current = self._specs.get(token.id)
        if (
            not self._authorized(token, promotion=True)
            or not definition.enabled
            or (current is not None and current.generation > token.generation)
        ):
            self._finish(candidate)
            return
        try:
            fresh = self._verify(candidate.binding)
            if fresh is None or fresh.client_size != candidate.binding.client_size:
                self._finish(candidate)
                return
            if token.id not in self.live and len(self.live) >= MAX_ENABLED:
                self._finish(candidate)
                return
            if not self._close_live(token.id):
                # Retain both owners; retry at the next pump boundary, not IO.
                candidate.terminal = ("promote", None)
                return
            if not self._authorized(token, promotion=True):
                self._finish(candidate)
                return
            revision = self._next_revision(token.id)
            spec = CompanionSpec(
                definition,
                token.generation,
                revision,
                CompanionSelection(token.generation, fresh),
            )
            live = _Live(spec, fresh, revision, candidate.window)
            activate, moved = self._wire_window(live)
            live.window._on_activate, live.window._on_geometry = activate, moved
            self.live[token.id] = live
            self._specs[token.id] = spec
            self._epoch = token.family_epoch
            candidate.window = None
            live.window.set_hidden(
                False,
                authorized=lambda: (
                    self.live.get(token.id) is live
                    and self._authorized(token, promotion=True)
                ),
            )
            if live.window.failed or live.window.hidden:
                self._close_live(token.id)
            else:
                self._errors.pop(token.id, None)
                self._failed_sources.pop(token.id, None)
            self._status()
            self._finish(candidate)
        except (SourceUnavailable, OSError):
            self._finish(candidate)

    def reconcile(self, specs, family_epoch):
        if self._closed or family_epoch < self._epoch:
            return
        self._epoch = family_epoch
        self._specs = {spec.definition.id: spec for spec in specs}
        for identity, spec in self._specs.items():
            self._revisions[identity] = max(
                self._revisions.get(identity, 0), spec.binding_revision
            )
        self.scan()

    def scan(self):
        self._clean_retired()
        self._retry_candidate(check_source=True)
        if self._closed:
            return
        if not any(
            self._authorized(self._token(spec), promotion=True)
            for spec in self._specs.values()
        ):
            self._status()
            return
        try:
            candidates = self._catalog.enumerate()
            scan_error = None
        except (SourceUnavailable, OSError) as exc:
            candidates, scan_error = (), str(exc)
        for identity, live in tuple(self.live.items()):
            spec = self._specs.get(identity)
            try:
                fresh = self._verify(live.binding)
            except (SourceUnavailable, OSError):
                fresh = None
            if (
                spec is None
                or not spec.definition.enabled
                or not self._authorized(self._token(spec), promotion=True)
                or fresh is None
                or live.window.failed
                or (
                    spec.selection is not None
                    and (
                        live.spec.selection is None
                        or spec.selection.generation != live.spec.selection.generation
                    )
                )
            ):
                # Only metadata edits inherit a verified binding. Once an
                # explicit replacement commits, the old source is no rollback.
                self._close_live(identity)
                continue
            # Label/title edits keep a verified binding, even if its caption no
            # longer matches. Matching is only for initial binding/rebinding.
            live.spec, live.binding = spec, fresh
            live.window.binding = fresh
            source = (
                region_to_pixels(spec.definition.region, fresh.client_size)
                if spec.definition.region
                else None
            )
            if spec.definition.region and source is None:
                self._close_live(identity)
                self._errors[identity] = (
                    "source-unavailable",
                    "The source region is unavailable",
                )
            else:
                live.window.set_source_rect(source)
        for identity, spec in self._specs.items():
            if (
                identity in self.live
                or not spec.definition.enabled
                or not self._authorized(self._token(spec), promotion=True)
            ):
                continue
            if self._candidate is not None and self._candidate.token.id == identity:
                continue  # Do not replace the committed owner during selection.
            selected = None
            if spec.selection is not None:
                try:
                    selected = self._verify(spec.selection.binding)
                except (SourceUnavailable, OSError):
                    # The bounded scan still decides ordinary rebinding.
                    selected = None
            matches = (
                (selected,)
                if selected is not None
                else matching_sources(spec.definition.source, candidates)
            )
            if scan_error and selected is None:
                self._errors[identity] = ("source-unavailable", scan_error)
            elif len(matches) != 1:
                self._errors[identity] = (
                    "needs-selection" if matches else "waiting",
                    None,
                )
            elif len(self.live) >= MAX_ENABLED or self._retired:
                self._errors[identity] = (
                    "source-unavailable",
                    "Disable another companion first",
                )
            else:
                self._bind(spec, matches[0])
        self._status()

    def _bind(self, spec, binding):
        identity = spec.definition.id
        episode = (binding.hwnd, binding.pid, binding.process_created, spec.generation)
        if self._failed_sources.get(identity) == episode:
            return
        window = None
        try:
            fresh = self._verify(binding)
            if fresh is None:
                raise SourceUnavailable("Source window is unavailable")
            source = (
                region_to_pixels(spec.definition.region, fresh.client_size)
                if spec.definition.region
                else None
            )
            if spec.definition.region is not None and source is None:
                raise SourceUnavailable("The source region is unavailable")
            live = _Live(
                spec, fresh, self._next_revision(identity, spec.binding_revision)
            )
            activate, moved = self._wire_window(live)
            rect = self._placement(spec.definition, fresh, source)
            window = self._create_window(
                self._libs, fresh, rect, source, on_activate=activate, on_geometry=moved
            )
            live.window = window
            verified = self._verify(fresh)
            if (
                window is None
                or window.failed
                or verified is None
                or verified.client_size != fresh.client_size
                or not self._authorized(self._token(spec), promotion=True)
            ):
                raise SourceUnavailable("Source window could not be captured")
            self.live[identity] = live
            window.set_hidden(
                False,
                authorized=lambda: (
                    self.live.get(identity) is live
                    and self._authorized(self._token(spec), promotion=True)
                ),
            )
            if window.failed or window.hidden:
                self.live.pop(identity, None)
                raise SourceUnavailable("Source capture is unavailable")
            self._errors.pop(identity, None)
            self._failed_sources.pop(identity, None)
        except (SourceUnavailable, OSError) as exc:
            if window is not None and not window.close():
                self._retired.append(window)
            self._errors[identity] = ("source-unavailable", str(exc))
            self._failed_sources[identity] = episode

    def _retry_candidate(self, *, check_source=False):
        candidate = self._candidate
        if candidate is None:
            return
        if candidate.terminal is not None:
            kind, reason = candidate.terminal
            if kind == "promote":
                candidate.terminal = None
                self._promote(candidate)
            else:
                self._finish(candidate, kind, reason)
        elif not self._authorized(candidate.token):
            self._finish(candidate, "failed", "Source selection expired")
        elif check_source:
            try:
                fresh = self._verify(candidate.binding)
                if fresh is None or fresh.client_size != candidate.binding.client_size:
                    self._finish(candidate, "failed", "Source changed during selection")
            except (SourceUnavailable, OSError) as exc:
                self._finish(candidate, "failed", str(exc))

    def process_dialog_message(self, message):
        candidate = self._candidate
        consumed = bool(
            candidate
            and candidate.picker
            and candidate.picker.process_dialog_message(message)
        )
        self._retry_candidate()
        return consumed

    def stop_live(self, family_epoch):
        self._epoch = max(self._epoch, family_epoch)
        self._activation = None
        result = all([self._close_live(identity) for identity in tuple(self.live)])
        self._retry_candidate()  # Leases survive ordinary master-off.
        self._status()
        return result and self._clean_retired()

    def fail(self, reason):
        candidate = self._candidate
        if candidate is not None and candidate.terminal is None:
            candidate.terminal = ("failed", reason)
        self._errors.update(
            {identity: ("source-unavailable", reason) for identity in self._specs}
        )
        self.close_native()
        self._status()

    def close_native(self):
        self._closed = True
        self._activation = None
        result = all([self._close_live(identity) for identity in tuple(self.live)])
        candidate = self._candidate
        if candidate is not None:
            terminal = candidate.terminal
            result = (
                self._finish(
                    candidate,
                    *(
                        terminal
                        if terminal and terminal[0] != "promote"
                        else ("closed", None)
                    ),
                )
                and result
            )
        return self._clean_retired() and self._catalog.close() and result

    def _activate(self, live):
        identity = live.spec.definition.id
        if self.live.get(identity) is not live or not self._authorized(
            self._token(live.spec), promotion=True
        ):
            return
        self._activation = (live, 0)
        self.tick_activation()

    @property
    def activation_pending(self):
        return self._activation is not None

    def tick_activation(self):
        if self._activation is None:
            return
        live, attempts = self._activation
        try:
            if (
                self.live.get(live.spec.definition.id) is not live
                or not self._authorized(self._token(live.spec), promotion=True)
                or self._verify(live.binding) is None
            ):
                raise SourceUnavailable("Source window is unavailable")
            user, kernel = self._libs.user32, self._libs.kernel32
            hwnd = live.binding.hwnd
            if user.IsIconic(hwnd):
                if attempts == 0:
                    user.ShowWindowAsync(hwnd, win32.SW_RESTORE)
            else:
                user.SetForegroundWindow(hwnd)
                if user.GetForegroundWindow() == hwnd:
                    self._activation = None
                    self._errors.pop(live.spec.definition.id, None)
                    self._status()
                    return
                our_thread = kernel.GetCurrentThreadId()
                target_thread = user.GetWindowThreadProcessId(hwnd, None)
                attached = bool(
                    target_thread
                    and target_thread != our_thread
                    and user.AttachThreadInput(our_thread, target_thread, True)
                )
                try:
                    user.SetForegroundWindow(hwnd)
                finally:
                    if attached:
                        user.AttachThreadInput(our_thread, target_thread, False)
                if user.GetForegroundWindow() == hwnd:
                    self._activation = None
                    self._errors.pop(live.spec.definition.id, None)
                    self._status()
                    return
            if attempts >= 24:
                raise SourceUnavailable("Windows refused source activation")
            self._activation = (live, attempts + 1)
        except (SourceUnavailable, OSError) as exc:
            self._activation = None
            self._errors[live.spec.definition.id] = ("source-unavailable", str(exc))
            self._status()
