"""Settings export/import: one JSON envelope over the DEFAULTS document.

``model`` is pure; ``controller`` owns the one pending import offer and the
named file operations. New code imports from here, not from the submodules.
"""

from .controller import SettingsShareController, SettingsSharePorts
from .model import (
    EXCLUDED_KEYS,
    FORMAT,
    MAX_BYTES,
    TYPE,
    VERSION,
    SettingsShareError,
    apply_document,
    export_document,
    export_text,
    parse_text,
    review,
)

__all__ = [
    "EXCLUDED_KEYS",
    "FORMAT",
    "MAX_BYTES",
    "TYPE",
    "VERSION",
    "SettingsShareController",
    "SettingsShareError",
    "SettingsSharePorts",
    "apply_document",
    "export_document",
    "export_text",
    "parse_text",
    "review",
]
