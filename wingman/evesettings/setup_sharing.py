"""Strict Wingman JSON transport with a separate bounded native YAML path.

The model stays a leaf. Native syntax is not a recovery path for a claimed
Wingman envelope. Probe-formation sharing retains its separate existing parser.
"""

import json

from . import overview_yaml
from . import setup_model as model
from .setup_model import ParsedSetup, SetupError


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SetupError("duplicate_field", f"Duplicate field: {key}")
        result[key] = value
    return result


def _constant(value):
    raise SetupError("invalid_json", f"Invalid JSON number: {value}.")


def parse_text(text: str) -> ParsedSetup:
    """Byte-bound first, then decode strictly and validate before domain copying."""
    model.check_text_budget(text)
    try:
        value = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_constant
        )
    except SetupError:
        raise
    except RecursionError as error:
        raise SetupError(
            "depth_limit", f"Setup JSON exceeds nesting depth {model.MAX_DEPTH}."
        ) from error
    except json.JSONDecodeError as error:
        # Flow-style native YAML also starts with '{'. Let the native parser
        # recognize its own strict schema, which excludes ALL envelope fields.
        # It cannot rescue a trailing-comma/otherwise malformed Wingman object.
        try:
            return overview_yaml.parse_text(text)
        except SetupError as native_error:
            if native_error.code in (
                "invalid_yaml",
                "unsupported_input",
            ) and text.lstrip().startswith(("{", "[")):
                raise SetupError(
                    "invalid_json", f"Invalid setup JSON: {error}"
                ) from error
            raise
    except (ValueError, OverflowError) as error:
        raise SetupError("invalid_json", f"Invalid setup JSON: {error}") from error
    model.check_structure_budget(value)
    if type(value) is dict and value and value.keys() <= overview_yaml.NATIVE_FIELDS:
        # JSON syntax is a YAML subset, but native semantics must still travel
        # through native validation, not the full/reset Wingman model path.
        return overview_yaml.parse_text(text)
    # Claimed JSON envelopes, including unsupported versions/types or missing
    # markers, are validated exactly once; domain errors never trigger fallback.
    return model.validate_wingman(value)


def export_text(value: dict) -> str:
    """Serialize a validated semantic envelope, never project a DAT document."""
    parsed = model.validate_wingman(value)
    envelope = {
        "format": model.FORMAT,
        "version": model.VERSION,
        "type": model.TYPE,
        "overview": parsed.overview,
        "layout": parsed.layout,
    }
    # Full normalization adds explicit clear fields. The canonical artifact
    # must remain readable under the same structural budget as its input.
    model.check_structure_budget(envelope)
    text = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    model.check_text_budget(text)
    return text
