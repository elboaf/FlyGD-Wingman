"""Runtime owner for shared EVE identities, grants, and lifecycle gates."""

import logging
import threading
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from . import application, tokens
from . import jwt as jwt_mod
from . import loopback as loopback_mod
from . import sso as sso_mod
from . import state as state_mod
from .cleanup import CleanupVerification

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_MARGIN_S = 30
ROTATION_PERSISTENCE_ERROR = "The rotated EVE token is live but could not be saved."
GRANT_PERSISTENCE_ERROR = "The EVE grant changed in memory but could not be saved."
ACCESS_REASON_INVALID_GRANT = "invalid_grant"
ACCESS_REASON_IDENTITY_MISMATCH = "identity_mismatch"
ACCESS_REASON_OWNER_CHANGED = "owner_changed"
ACCESS_REASON_DECRYPTION_FAILED = "decryption_failed"


@dataclass(frozen=True)
class AuthorityCharacter:
    """Immutable runtime view of one app-wide EVE identity and grant."""

    character_id: int
    character_name: str
    owner_hash: str
    scopes: tuple[str, ...]
    authenticated_utc: datetime | None
    needs_reauth: bool
    generation: int
    persistence_error: str = ""


@dataclass(frozen=True)
class AccessTokenResult:
    token: str | None
    error: str
    grant_invalidated: bool
    reason: str = ""


@dataclass(frozen=True)
class MutationResult:
    applied: bool
    persisted: bool
    error: str


@dataclass(frozen=True)
class AuthorizationCommandResult:
    accepted: bool
    error: str = ""


@dataclass(frozen=True)
class _AuthorizationAttempt:
    attempt_id: int
    cancellation_generation: int
    known_generations: tuple[tuple[int, int], ...]
    cancelled: threading.Event


@dataclass(frozen=True)
class LifecycleLease:
    character: AuthorityCharacter | None
    capability: str
    generation: int


class CharacterParticipant(Protocol):
    """Feature-state hooks called in lifecycle-then-feature lock order."""

    def prepare_forget(self, character_id: int) -> MutationResult: ...

    def authority_removed(self, character_id: int) -> MutationResult: ...

    def grant_invalidated(self, character_id: int) -> None: ...

    def reconcile_characters(
        self, characters: tuple[AuthorityCharacter, ...]
    ) -> CleanupVerification: ...


class _AuthorizationFailure(Exception):
    def __init__(self, title: str, body: str, *, finalized: bool = False) -> None:
        super().__init__(body)
        self.title = title
        self.body = body
        self.finalized = finalized


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _owner_matches(stored: str, returned: str) -> bool:
    return not stored or not returned or stored == returned


def _merged_owner(stored: str, returned: str) -> str:
    return stored or returned


def _noop_alert(kind: str, title: str, body: str) -> None:
    del kind, title, body


def _noop_changed() -> None:
    pass


class AuthorityController:
    """The sole runtime and persistent owner of EVE OAuth grants."""

    def __init__(
        self,
        *,
        state_path,
        authority: state_mod.AuthorityState | None = None,
        alert: Callable[[str, str, str], None] = _noop_alert,
        changed: Callable[[], None] = _noop_changed,
        key_source=None,
        spawn=threading.Thread,
        launch_browser=webbrowser.open,
        now=_utcnow,
        sso=None,
        listener_factory=None,
        validate_token=None,
        wrap_token=tokens.wrap,
        unwrap_token=tokens.unwrap,
        save_authority=state_mod.save_authority,
    ) -> None:
        self._state_path = Path(state_path)
        self._alert = alert
        self._changed = changed
        self._key_source = key_source
        self._spawn = spawn
        self._launch_browser = launch_browser
        self._now = now
        self._sso = sso or sso_mod
        self._listener_factory = listener_factory or loopback_mod.LoopbackListener
        self._validate_token = validate_token or jwt_mod.validate
        self._wrap_token = wrap_token
        self._unwrap_token = unwrap_token
        self._save_authority = save_authority

        self._lock = threading.RLock()
        if authority is None:
            loaded, warnings = state_mod.load_authority(self._state_path)
            if loaded is None:
                detail = warnings[0] if warnings else "unknown authority load error"
                raise OSError(f"EVE authority is unavailable: {detail}")
            authority = loaded
            self._load_warnings = warnings
        else:
            self._load_warnings = ()
        self._state = state_mod.AuthorityState(list(authority.characters))

        self._access_tokens: dict[int, tuple[str, datetime]] = {}
        # Used only when a freshly rotated token cannot be DPAPI-wrapped. The
        # old persisted token is already invalid, so the live replacement must
        # remain usable in memory without ever being written as plaintext.
        self._refresh_tokens: dict[int, str] = {}
        self._persistence_errors: dict[int, str] = {}
        self._generations = {
            character.character_id: 0 for character in self._state.characters
        }
        self._lifecycle_gates: dict[int, threading.RLock] = {}
        self._lifecycle_gates_lock = threading.Lock()
        self._participants: dict[str, CharacterParticipant | None] = {
            application.SKILLS: None,
            application.FITTINGS: None,
        }
        self._cleanup_verification = {
            name: CleanupVerification(
                False,
                error=f"{name.title()} cleanup is unavailable.",
            )
            for name in self._participants
        }

        self._auth_latch = threading.Lock()
        self._auth_in_progress = False
        self._active_attempt: _AuthorizationAttempt | None = None
        self._next_attempt_id = 1
        self._cancellation_generation = 0
        self._authorization_activity = "idle"
        self._authorization_notice = ""
        self._listener = None
        self._listener_attempt_id: int | None = None
        self._stopping = threading.Event()

    @property
    def characters(self) -> tuple[AuthorityCharacter, ...]:
        with self._lock:
            return tuple(self._snapshot(row) for row in self._state.characters)

    @property
    def auth_in_progress(self) -> bool:
        with self._lock:
            return self._auth_in_progress

    @property
    def authorization_activity(self) -> str:
        with self._lock:
            return self._authorization_activity

    @property
    def authorization_notice(self) -> str:
        with self._lock:
            return self._authorization_notice

    def character(self, character_id: int) -> AuthorityCharacter | None:
        wanted = self._coerce_character_id(character_id)
        if wanted is None:
            return None
        with self._lock:
            row = self._find_locked(wanted)
            return self._snapshot(row) if row is not None else None

    def capability_status(self, character_id: int, capability: str) -> str:
        required = self._capability_scopes(capability)
        character = self.character(character_id)
        if character is None:
            return "missing"
        if character.needs_reauth:
            return "reauthenticate"
        with self._lock:
            row = self._find_locked(character.character_id)
            has_token = bool(
                row
                and (
                    row.refresh_token_blob
                    or self._refresh_tokens.get(character.character_id)
                )
            )
        if not has_token:
            return "reauthenticate"
        if required.issubset(character.scopes):
            return "enabled"
        return "enable"

    def access_token(
        self,
        character_id: int,
        capability: str,
        *,
        rejected_token: str | None = None,
    ) -> AccessTokenResult:
        """Return a capability token, refreshing once under its lifecycle gate.

        Endpoint statuses never enter this API. A rejected access token can ask
        for a refresh, but only the refresh response and validated identity can
        invalidate the shared grant.
        """
        if self._stopping.is_set():
            return AccessTokenResult(None, "EVE authority is shutting down.", False)
        wanted = self._coerce_character_id(character_id)
        if wanted is None:
            return AccessTokenResult(None, "Unknown EVE character.", False)
        required = self._capability_scopes(capability)
        gate = self._lifecycle_gate(wanted)
        with gate:
            if self._stopping.is_set():
                return AccessTokenResult(None, "EVE authority is shutting down.", False)
            with self._lock:
                row = self._find_locked(wanted)
                if row is None:
                    return AccessTokenResult(None, "Unknown EVE character.", False)
                memory_refresh = self._refresh_tokens.get(wanted)
                if row.needs_reauth or not (row.refresh_token_blob or memory_refresh):
                    return AccessTokenResult(
                        None, "Re-authenticate this EVE character.", False
                    )
                if not required.issubset(row.scopes):
                    return AccessTokenResult(
                        None, f"Enable {capability} for this EVE character.", False
                    )
                cached = self._access_tokens.get(wanted)
                refresh_blob = row.refresh_token_blob
                stored_owner = row.owner_hash

            now = self._now()
            if cached is not None:
                token, expires_at = cached
                fresh = (expires_at - now).total_seconds() > TOKEN_EXPIRY_MARGIN_S
                if fresh and (rejected_token is None or rejected_token != token):
                    return AccessTokenResult(
                        token, self._persistence_errors.get(wanted, ""), False
                    )

            refresh = memory_refresh or self._unwrap_token(refresh_blob)
            if refresh is None:
                self._invalidate_grant(wanted)
                return AccessTokenResult(
                    None,
                    "Re-authenticate this EVE character.",
                    True,
                    ACCESS_REASON_DECRYPTION_FAILED,
                )

            try:
                token_set = self._sso.refresh_token(refresh)
                identity = self._validate_token(
                    token_set.access_token,
                    client_id=application.CLIENT_ID,
                    required_scopes=frozenset(),
                    key_source=self._keys(),
                )
            except sso_mod.OAuthError as exc:
                if exc.code == "invalid_grant":
                    self._invalidate_grant(wanted)
                    return AccessTokenResult(
                        None,
                        "Re-authenticate this EVE character.",
                        True,
                        ACCESS_REASON_INVALID_GRANT,
                    )
                return AccessTokenResult(
                    None, f"EVE SSO refused the token refresh: {exc}", False
                )
            except jwt_mod.JwtError as exc:
                logger.warning("Refreshed EVE token failed validation", exc_info=True)
                return AccessTokenResult(
                    None, f"EVE SSO returned an unusable access token: {exc}", False
                )
            except Exception as exc:
                logger.warning("EVE token refresh failed", exc_info=True)
                return AccessTokenResult(None, f"Could not reach EVE SSO: {exc}", False)

            if identity.character_id != wanted:
                self._invalidate_grant(wanted)
                return AccessTokenResult(
                    None,
                    "The refreshed token belongs to a different character.",
                    True,
                    ACCESS_REASON_IDENTITY_MISMATCH,
                )
            if not _owner_matches(stored_owner, identity.owner_hash):
                self._invalidate_grant(wanted)
                return AccessTokenResult(
                    None,
                    "Character ownership changed. Re-authenticate.",
                    True,
                    ACCESS_REASON_OWNER_CHANGED,
                )

            rotated = bool(token_set.refresh_token.strip())
            refresh_to_store = token_set.refresh_token if rotated else ""
            if not refresh_to_store and memory_refresh and not refresh_blob:
                # A previous DPAPI failure left the rotated token live only in
                # memory. An omitted token means "keep it", so retry wrapping
                # that same token rather than persisting the empty sentinel.
                refresh_to_store = memory_refresh
            wrap_failed = False
            wrapped_refresh = ""
            if refresh_to_store:
                try:
                    wrapped_refresh = self._wrap_token(refresh_to_store)
                except Exception:
                    # DPAPI providers vary by platform; the live rotated token
                    # remains memory-only and the persistence risk is surfaced.
                    logger.warning("Could not protect rotated EVE token", exc_info=True)
                    wrap_failed = True

            with self._lock:
                current = self._find_locked(wanted)
                if current is None:
                    return AccessTokenResult(None, "Unknown EVE character.", False)
                updated = replace(
                    current,
                    character_name=identity.name,
                    owner_hash=_merged_owner(current.owner_hash, identity.owner_hash),
                    scopes=tuple(sorted(identity.scopes)),
                    needs_reauth=False,
                    refresh_token_blob=(
                        ""
                        if wrap_failed
                        else wrapped_refresh or current.refresh_token_blob
                    ),
                )
                candidate = self._with_row_locked(updated)
                persistence_error = ""
                if wrap_failed:
                    # The old refresh token may already be invalid after rotation.
                    # Keeping the new raw token in memory is safer than rollback;
                    # it is never written to disk without DPAPI protection.
                    self._state = candidate
                    persistence_error = ROTATION_PERSISTENCE_ERROR
                    self._persistence_errors[wanted] = persistence_error
                    self._refresh_tokens[wanted] = refresh_to_store
                else:
                    try:
                        self._save_authority(self._state_path, candidate)
                    except (OSError, ValueError):
                        logger.warning(
                            "Could not persist refreshed EVE grant", exc_info=True
                        )
                        # A successfully wrapped token is retained in the live
                        # state even when the atomic disk swap fails.
                        self._state = candidate
                        persistence_error = (
                            ROTATION_PERSISTENCE_ERROR
                            if refresh_to_store
                            else GRANT_PERSISTENCE_ERROR
                        )
                        self._persistence_errors[wanted] = persistence_error
                    else:
                        self._state = candidate
                        self._persistence_errors.pop(wanted, None)
                    self._refresh_tokens.pop(wanted, None)
                self._access_tokens[wanted] = (
                    token_set.access_token,
                    now + timedelta(seconds=max(0, int(token_set.expires_in))),
                )

            self._changed_safely()
            if not required.issubset(identity.scopes):
                return AccessTokenResult(
                    None, f"Enable {capability} for this EVE character.", False
                )
            return AccessTokenResult(token_set.access_token, persistence_error, False)

    @contextmanager
    def lifecycle(self, character_id: int, capability: str) -> Iterator[LifecycleLease]:
        wanted = self._coerce_character_id(character_id)
        if wanted is None:
            raise KeyError("Unknown EVE character.")
        gate = self._lifecycle_gate(wanted)
        with gate:
            character = self._required_capability(wanted, capability)
            yield LifecycleLease(character, capability, character.generation)

    def start_full_authorization(self) -> AuthorizationCommandResult:
        if self._stopping.is_set():
            return AuthorizationCommandResult(
                False,
                "EVE authority is shutting down.",
            )
        if not application.is_configured():
            error = "This build has no configured EVE application client id."
            self._alert("warning", "EVE sign-in is not configured", error)
            return AuthorizationCommandResult(False, error)
        with self._lock:
            if self._active_attempt is not None:
                error = "An EVE sign-in is already in progress."
                attempt = None
            else:
                attempt = _AuthorizationAttempt(
                    attempt_id=self._next_attempt_id,
                    cancellation_generation=self._cancellation_generation,
                    known_generations=self._generation_roster_locked(),
                    cancelled=threading.Event(),
                )
                self._next_attempt_id += 1
                self._active_attempt = attempt
                self._auth_in_progress = True
                self._authorization_activity = "waiting"
                self._authorization_notice = ""
                error = ""
        if attempt is None:
            self._alert("warning", "Sign-in already in progress", error)
            return AuthorizationCommandResult(False, error)
        self._changed_safely()
        try:
            worker = self._spawn(
                target=lambda: self._auth_worker(
                    attempt=attempt,
                    scopes=application.FULL_AUTH_SCOPES,
                ),
                daemon=True,
            )
            worker.start()
        except Exception as exc:
            logger.warning("Could not start EVE authorization worker", exc_info=True)
            error = f"Could not start EVE sign-in: {exc}"
            self._finish_attempt(attempt, error)
            self._alert("warning", "Sign-in failed", error)
            return AuthorizationCommandResult(False, error)
        return AuthorizationCommandResult(True, "")

    def authenticate_skills(self) -> MutationResult:
        """Compatibility adapter until shared Settings callers land."""
        result = self.start_full_authorization()
        return MutationResult(result.accepted, result.accepted, result.error)

    def enable_capability(self, character_id: int, capability: str) -> MutationResult:
        """Compatibility adapter until shared Settings callers land."""
        del character_id
        self._capability_scopes(capability)
        result = self.start_full_authorization()
        return MutationResult(result.accepted, result.accepted, result.error)

    def cancel_authorization(self) -> AuthorizationCommandResult:
        with self._lock:
            attempt = self._active_attempt
            if attempt is None:
                return AuthorizationCommandResult(
                    False,
                    "The EVE sign-in already finished.",
                )
            attempt.cancelled.set()
            self._cancellation_generation += 1
            listener = None
            if self._listener_attempt_id == attempt.attempt_id:
                listener = self._listener
                self._listener = None
                self._listener_attempt_id = None
            self._finalize_attempt_locked(attempt, "")
        if listener is not None:
            self._cancel_listener_safely(listener)
        self._changed_safely()
        return AuthorizationCommandResult(True, "")

    def cancel_auth(self) -> None:
        """Compatibility adapter until shared Settings callers land."""
        self.cancel_authorization()

    def forget(self, character_id: int) -> MutationResult:
        """Persist authority removal before pruning any participant state."""
        wanted = self._coerce_character_id(character_id)
        if wanted is None:
            return MutationResult(False, False, "Unknown EVE character.")
        gate = self._lifecycle_gate(wanted)
        with gate:
            participants = self._participant_slots_snapshot()
            participants_by_capability = dict(participants)
            refusals = []
            for _capability, participant in participants:
                try:
                    prepared = participant.prepare_forget(wanted)
                except Exception as exc:
                    logger.warning(
                        "EVE participant could not prepare forget", exc_info=True
                    )
                    refusals.append(f"A feature could not prepare removal: {exc}")
                    continue
                if not prepared.applied:
                    refusals.append(prepared.error or "A feature refused removal.")
                elif not prepared.persisted:
                    refusals.append(
                        prepared.error
                        or "A feature could not save its removal preflight."
                    )
            if refusals:
                return MutationResult(False, False, refusals[0])

            with self._lock:
                already_absent = self._find_locked(wanted) is None
                if not already_absent:
                    candidate = state_mod.AuthorityState(
                        [
                            row
                            for row in self._state.characters
                            if row.character_id != wanted
                        ]
                    )
                    try:
                        self._save_authority(self._state_path, candidate)
                    except (OSError, ValueError) as exc:
                        logger.warning(
                            "Could not persist EVE authority removal", exc_info=True
                        )
                        return MutationResult(
                            False, False, f"The character was not forgotten: {exc}"
                        )
                    self._state = candidate
                    self._access_tokens.pop(wanted, None)
                    self._refresh_tokens.pop(wanted, None)
                    self._persistence_errors.pop(wanted, None)
                    self._generations[wanted] = self._generations.get(wanted, 0) + 1

            cleanup_errors = []
            for capability, participant in participants:
                try:
                    result = participant.authority_removed(wanted)
                except Exception:
                    logger.warning("EVE participant cleanup failed", exc_info=True)
                    verification = self._blocked_unavailable_cleanup(capability, wanted)
                    self._store_cleanup_verification(capability, verification)
                    cleanup_errors.append(verification.error)
                    continue
                self._store_cleanup_verification(
                    capability,
                    self._cleanup_verification_for_removal(
                        capability,
                        wanted,
                        result,
                    ),
                )
                if not result.applied or not result.persisted:
                    cleanup_errors.append(
                        result.error or "A feature cleanup is incomplete."
                    )
            for capability in application.FULL_AUTH_CAPABILITIES:
                if capability in participants_by_capability:
                    continue
                verification = self._blocked_unavailable_cleanup(capability, wanted)
                self._store_cleanup_verification(capability, verification)
                cleanup_errors.append(verification.error)
            self._changed_safely()
            if cleanup_errors:
                return MutationResult(True, False, cleanup_errors[0])
            return MutationResult(True, True, "")

    def register_participant(
        self, capability: str, participant: CharacterParticipant
    ) -> CleanupVerification:
        """Register one named feature owner and reconcile its derived roster."""
        self._capability_scopes(capability)
        with self._lock:
            existing = self._participants.get(capability)
            if existing is not None:
                raise ValueError(
                    f"EVE capability {capability!r} is already registered."
                )
            self._participants[capability] = participant
            roster = tuple(self._snapshot(row) for row in self._state.characters)
        self._reconcile_participant(capability, participant, roster)
        with self._lock:
            return self._aggregate_cleanup_verification_locked()

    def shutdown(self) -> None:
        """Stop accepting token work and cancel a pending browser authorization."""
        self._stopping.set()
        try:
            self.cancel_auth()
        except Exception:
            logger.warning("EVE authority shutdown was not clean", exc_info=True)

    def _auth_worker(
        self,
        *,
        attempt: _AuthorizationAttempt,
        scopes: frozenset[str],
    ) -> None:
        try:
            roster = self._run_auth(attempt=attempt, scopes=scopes)
        except loopback_mod.CallbackCancelled:
            logger.info("EVE authorization cancelled")
            self._finish_attempt(attempt, "")
            return
        except loopback_mod.CallbackTimeout:
            body = "No response from EVE SSO within five minutes."
            if self._finish_attempt(attempt, body):
                self._alert("warning", "Sign-in timed out", body)
            return
        except _AuthorizationFailure as exc:
            if exc.finalized or self._finish_attempt(attempt, exc.body):
                if exc.finalized:
                    self._changed_safely()
                self._alert("warning", exc.title, exc.body)
            return
        except sso_mod.OAuthError as exc:
            body = str(exc)
            if self._finish_attempt(attempt, body):
                self._alert("warning", "EVE refused the sign-in", body)
            return
        except jwt_mod.JwtError as exc:
            body = str(exc)
            if self._finish_attempt(attempt, body):
                self._alert("warning", "EVE returned a token we cannot trust", body)
            return
        except Exception as exc:
            logger.warning("EVE authorization failed", exc_info=True)
            body = str(exc)
            if self._finish_attempt(attempt, body):
                self._alert("warning", "Sign-in failed", body)
            return

        participants = self._participant_slots_snapshot()
        for capability, participant in participants:
            self._reconcile_participant(capability, participant, roster)
        self._changed_safely()

    def _run_auth(
        self,
        *,
        attempt: _AuthorizationAttempt,
        scopes: frozenset[str],
    ) -> tuple[AuthorityCharacter, ...]:
        pkce = self._sso.generate_pkce()
        with self._listener_factory(
            host=application.REDIRECT_HOST,
            port=application.REDIRECT_PORT,
            path=application.REDIRECT_PATH,
        ) as listener:
            if not self._bind_listener(attempt, listener):
                self._cancel_listener_safely(listener)
                raise loopback_mod.CallbackCancelled()
            try:
                if attempt.cancelled.is_set():
                    self._cancel_listener_safely(listener)
                    raise loopback_mod.CallbackCancelled()
                self._launch_browser(self._sso.authorize_url(pkce, scopes))
                callback = listener.wait(pkce.state)
            finally:
                self._clear_listener(attempt)
        if callback.error:
            raise _AuthorizationFailure("EVE refused the sign-in", callback.error)
        token_set = self._sso.exchange_code(callback.code, pkce.verifier)
        identity = self._validate_token(
            token_set.access_token,
            client_id=application.CLIENT_ID,
            required_scopes=scopes,
            key_source=self._keys(),
        )
        return self._commit_authorization(
            attempt=attempt,
            identity=identity,
            token_set=token_set,
        )

    def _commit_authorization(
        self,
        *,
        attempt: _AuthorizationAttempt,
        identity,
        token_set,
    ) -> tuple[AuthorityCharacter, ...]:
        character_id = identity.character_id
        known_generations = dict(attempt.known_generations)
        gate = self._lifecycle_gate(character_id)
        with gate:
            unknown_verification = None
            if character_id not in known_generations:
                unknown_verification = self._verify_unknown_character(character_id)
            try:
                blob = self._wrap_token(token_set.refresh_token)
            except Exception as exc:
                raise _AuthorizationFailure(
                    "Could not save the sign-in", str(exc)
                ) from exc

            with self._lock:
                if (
                    self._active_attempt is not attempt
                    or self._cancellation_generation != attempt.cancellation_generation
                    or attempt.cancelled.is_set()
                ):
                    raise loopback_mod.CallbackCancelled()

                if self._generation_roster_locked() != attempt.known_generations:
                    body = (
                        "The character roster changed: a character was forgotten "
                        "or is no longer at the authorisation generation that "
                        "started this sign-in."
                    )
                    self._finalize_attempt_locked(attempt, body)
                    raise _AuthorizationFailure(
                        "Sign-in not completed",
                        body,
                        finalized=True,
                    )

                current = self._find_locked(character_id)
                generation = self._generations.get(character_id, 0)
                if current is None:
                    if (
                        unknown_verification is not None
                        and not unknown_verification.applied
                    ):
                        body = unknown_verification.error or "Reconcile first."
                        self._finalize_attempt_locked(attempt, body)
                        raise _AuthorizationFailure(
                            "Sign-in not completed",
                            body,
                            finalized=True,
                        )
                    if len(self._state.characters) >= state_mod.MAX_CHARACTERS:
                        body = (
                            f"Wingman stores at most {state_mod.MAX_CHARACTERS} "
                            "characters. Forget one before adding another."
                        )
                        self._finalize_attempt_locked(attempt, body)
                        raise _AuthorizationFailure(
                            "Too many characters",
                            body,
                            finalized=True,
                        )

                stored_owner = current.owner_hash if current is not None else ""
                if current is not None and not _owner_matches(
                    stored_owner,
                    identity.owner_hash,
                ):
                    body = (
                        "Character ownership changed. Forget the existing character "
                        "before authenticating it again."
                    )
                    self._finalize_attempt_locked(attempt, body)
                    raise _AuthorizationFailure(
                        "Sign-in not completed",
                        body,
                        finalized=True,
                    )

                row = state_mod.AuthorityCharacter(
                    character_id=character_id,
                    character_name=identity.name,
                    owner_hash=_merged_owner(stored_owner, identity.owner_hash),
                    scopes=tuple(sorted(identity.scopes)),
                    authenticated_utc=self._now(),
                    needs_reauth=False,
                    refresh_token_blob=blob,
                )
                candidate = self._with_row_locked(row)
                try:
                    self._save_authority(self._state_path, candidate)
                except (OSError, ValueError):
                    logger.warning("Could not persist EVE authorization", exc_info=True)
                    body = (
                        "The sign-in was not saved and the previous authority remains "
                        "in use."
                    )
                    self._finalize_attempt_locked(attempt, body)
                    raise _AuthorizationFailure(
                        "Could not save the sign-in",
                        body,
                        finalized=True,
                    )

                self._state = candidate
                self._persistence_errors.pop(character_id, None)
                self._refresh_tokens.pop(character_id, None)
                self._access_tokens[character_id] = (
                    token_set.access_token,
                    self._now() + timedelta(seconds=max(0, int(token_set.expires_in))),
                )
                self._generations.setdefault(character_id, generation)
                roster = tuple(self._snapshot(row) for row in self._state.characters)
                self._finalize_attempt_locked(attempt, "")
        return roster

    def _finish_attempt(
        self,
        attempt: _AuthorizationAttempt,
        notice: str,
    ) -> bool:
        with self._lock:
            finished = self._finalize_attempt_locked(attempt, notice)
        if finished:
            self._changed_safely()
        return finished

    def _finalize_attempt_locked(
        self,
        attempt: _AuthorizationAttempt,
        notice: str,
    ) -> bool:
        if self._active_attempt is not attempt:
            if self._listener_attempt_id == attempt.attempt_id:
                self._listener = None
                self._listener_attempt_id = None
            return False
        self._active_attempt = None
        self._auth_in_progress = False
        self._authorization_activity = "idle"
        self._authorization_notice = self._bounded_notice(notice)
        if self._listener_attempt_id == attempt.attempt_id:
            self._listener = None
            self._listener_attempt_id = None
        return True

    def _bind_listener(self, attempt: _AuthorizationAttempt, listener) -> bool:
        with self._lock:
            if self._active_attempt is not attempt:
                return False
            self._listener = listener
            self._listener_attempt_id = attempt.attempt_id
            return True

    def _clear_listener(self, attempt: _AuthorizationAttempt) -> None:
        with self._lock:
            if self._listener_attempt_id == attempt.attempt_id:
                self._listener = None
                self._listener_attempt_id = None

    @staticmethod
    def _cancel_listener_safely(listener) -> None:
        try:
            listener.cancel()
        except Exception:
            logger.warning("Could not cancel EVE authorization", exc_info=True)

    def _required_capability(
        self, character_id: int, capability: str
    ) -> AuthorityCharacter:
        status = self.capability_status(character_id, capability)
        if status == "missing":
            raise KeyError("Unknown EVE character.")
        if status != "enabled":
            raise PermissionError(
                f"EVE capability {capability!r} is not enabled for this character."
            )
        character = self.character(character_id)
        if character is None:  # Defensive against a future non-gated caller.
            raise KeyError("Unknown EVE character.")
        return character

    def _invalidate_grant(self, character_id: int) -> None:
        """Invalidate only after invalid_grant or a validated identity mismatch."""
        with self._lock:
            current = self._find_locked(character_id)
            if current is None:
                return
            updated = replace(current, needs_reauth=True, refresh_token_blob="")
            candidate = self._with_row_locked(updated)
            try:
                self._save_authority(self._state_path, candidate)
            except (OSError, ValueError):
                logger.warning(
                    "Could not persist EVE grant invalidation", exc_info=True
                )
                self._persistence_errors[character_id] = GRANT_PERSISTENCE_ERROR
            else:
                self._persistence_errors.pop(character_id, None)
            # Never retain a credential known to be invalid merely because disk
            # is unavailable. A later save can repair persistence.
            self._state = candidate
            self._access_tokens.pop(character_id, None)
            self._refresh_tokens.pop(character_id, None)
            self._generations[character_id] = self._generations.get(character_id, 0) + 1
        participants = self._participant_snapshot()
        self._notify_participants(participants, "grant_invalidated", character_id)
        self._changed_safely()

    def _participant_snapshot(self) -> tuple[CharacterParticipant, ...]:
        with self._lock:
            return tuple(
                participant
                for participant in self._participants.values()
                if participant is not None
            )

    def _participant_slots_snapshot(
        self,
    ) -> tuple[tuple[str, CharacterParticipant], ...]:
        with self._lock:
            return tuple(
                (capability, participant)
                for capability, participant in self._participants.items()
                if participant is not None
            )

    def _cleanup_unavailable(self, capability: str) -> CleanupVerification:
        return CleanupVerification(
            False,
            error=f"{capability.title()} cleanup is unavailable.",
        )

    def _blocked_unavailable_cleanup(
        self, capability: str, character_id: int
    ) -> CleanupVerification:
        with self._lock:
            previous = self._cleanup_verification[capability]
        return CleanupVerification(
            False,
            frozenset({*previous.blocked_character_ids, character_id}),
            self._cleanup_unavailable(capability).error,
        )

    def _store_cleanup_verification(
        self, capability: str, verification: CleanupVerification
    ) -> None:
        with self._lock:
            self._cleanup_verification[capability] = verification

    def _aggregate_cleanup_verification_locked(self) -> CleanupVerification:
        blocked_ids: set[int] = set()
        for capability in application.FULL_AUTH_CAPABILITIES:
            verification = self._cleanup_verification[capability]
            blocked_ids.update(verification.blocked_character_ids)
            if not verification.verified:
                return CleanupVerification(
                    False,
                    frozenset(blocked_ids),
                    verification.error or self._cleanup_unavailable(capability).error,
                )
        return CleanupVerification(True, frozenset(blocked_ids), "")

    def _cleanup_verification_for_removal(
        self,
        capability: str,
        character_id: int,
        result: MutationResult,
    ) -> CleanupVerification:
        with self._lock:
            previous = self._cleanup_verification[capability]
        blocked_ids = set(previous.blocked_character_ids)
        if result.applied and result.persisted:
            blocked_ids.discard(character_id)
            return CleanupVerification(True, frozenset(blocked_ids), "")
        blocked_ids.add(character_id)
        if result.applied:
            return CleanupVerification(
                True,
                frozenset(blocked_ids),
                result.error or "A feature cleanup is incomplete.",
            )
        return CleanupVerification(
            False,
            frozenset(blocked_ids),
            result.error or self._cleanup_unavailable(capability).error,
        )

    def _reconcile_participant(
        self,
        capability: str,
        participant: CharacterParticipant,
        roster: tuple[AuthorityCharacter, ...],
    ) -> CleanupVerification:
        try:
            verification = participant.reconcile_characters(roster)
        except Exception:
            logger.warning("EVE participant reconciliation failed", exc_info=True)
            verification = self._cleanup_unavailable(capability)
        if not isinstance(verification, CleanupVerification):
            verification = self._cleanup_unavailable(capability)
        self._store_cleanup_verification(capability, verification)
        return verification

    def _verify_unknown_character(self, character_id: int) -> MutationResult:
        wanted = self._coerce_character_id(character_id)
        if wanted is None:
            return MutationResult(False, False, "Unknown EVE character.")
        gate = self._lifecycle_gate(wanted)
        with gate:
            with self._lock:
                roster = tuple(self._snapshot(row) for row in self._state.characters)
                participants = tuple(
                    (capability, participant)
                    for capability, participant in self._participants.items()
                    if participant is not None
                    and (
                        not self._cleanup_verification[capability].verified
                        or self._cleanup_verification[capability].blocked_character_ids
                    )
                )
            for capability, participant in participants:
                self._reconcile_participant(capability, participant, roster)
            with self._lock:
                verification = self._aggregate_cleanup_verification_locked()
            if not verification.verified:
                return MutationResult(
                    False,
                    False,
                    verification.error or "Reconcile first.",
                )
            if wanted in verification.blocked_character_ids:
                return MutationResult(False, False, "Reconcile first.")
            return MutationResult(True, True, "")

    @staticmethod
    def _notify_participants(participants, hook: str, character_id: int) -> None:
        for participant in participants:
            try:
                getattr(participant, hook)(character_id)
            except Exception:
                logger.warning("EVE participant notification failed", exc_info=True)

    def _snapshot(self, row: state_mod.AuthorityCharacter) -> AuthorityCharacter:
        return AuthorityCharacter(
            character_id=row.character_id,
            character_name=row.character_name,
            owner_hash=row.owner_hash,
            scopes=tuple(row.scopes),
            authenticated_utc=row.authenticated_utc,
            needs_reauth=row.needs_reauth,
            generation=self._generations.get(row.character_id, 0),
            persistence_error=self._persistence_errors.get(row.character_id, ""),
        )

    def _generation_roster_locked(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row.character_id, self._generations.get(row.character_id, 0))
            for row in self._state.characters
        )

    def _find_locked(self, character_id: int) -> state_mod.AuthorityCharacter | None:
        return next(
            (
                character
                for character in self._state.characters
                if character.character_id == character_id
            ),
            None,
        )

    def _with_row_locked(
        self, row: state_mod.AuthorityCharacter
    ) -> state_mod.AuthorityState:
        rows = [
            row if current.character_id == row.character_id else current
            for current in self._state.characters
        ]
        if not any(
            current.character_id == row.character_id
            for current in self._state.characters
        ):
            rows.append(row)
        return state_mod.AuthorityState(rows)

    def _lifecycle_gate(self, character_id: int) -> threading.RLock:
        with self._lifecycle_gates_lock:
            gate = self._lifecycle_gates.get(character_id)
            if gate is None:
                gate = threading.RLock()
                self._lifecycle_gates[character_id] = gate
            return gate

    def _keys(self):
        with self._lock:
            if self._key_source is None:
                self._key_source = jwt_mod.SigningKeySource()
            return self._key_source

    @staticmethod
    def _coerce_character_id(value) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            character_id = int(value)
        except (TypeError, ValueError):
            return None
        return character_id if character_id > 0 else None

    @staticmethod
    def _capability_scopes(capability: str) -> frozenset[str]:
        try:
            return application.CAPABILITY_SCOPES[capability]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Unknown EVE capability: {capability!r}.") from exc

    @staticmethod
    def _bounded_notice(message: str) -> str:
        if len(message) <= 500:
            return message
        return message[:500]

    def _changed_safely(self) -> None:
        try:
            self._changed()
        except Exception:
            logger.warning("Could not publish EVE authority change", exc_info=True)
