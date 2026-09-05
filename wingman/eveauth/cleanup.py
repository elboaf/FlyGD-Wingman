from dataclasses import dataclass


@dataclass(frozen=True)
class LoadHealth:
    cleanup_verifiable: bool
    rewrite_required: bool = False


@dataclass(frozen=True)
class CleanupVerification:
    verified: bool
    blocked_character_ids: frozenset[int] = frozenset()
    error: str = ""
