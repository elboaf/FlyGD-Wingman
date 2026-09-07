"""Strict Wingman setup JSON transport; native YAML is not enabled yet.

The model is a leaf. A future native parser is called from this transport, never
from the model and never as a recovery path for a claimed malformed/unsupported
Wingman artifact. Probe-formation sharing retains its separate existing parser.
"""

import json

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
        if text.lstrip().startswith(("{", "[")):
            raise SetupError("invalid_json", f"Invalid setup JSON: {error}") from error
        # Task 3 owns safe native parsing/dispatch. Do not implement a permissive
        # fallback or infer native semantics just to admit unsupported input.
        raise SetupError(
            "unsupported_input",
            "Native YAML or other input is not supported yet; use Wingman setup JSON.",
        ) from error
    except (ValueError, OverflowError) as error:
        raise SetupError("invalid_json", f"Invalid setup JSON: {error}") from error
    # validate_wingman starts with the structural budget, before any conversion.
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
