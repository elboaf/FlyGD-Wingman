"""Thin EVE roster adapter over the source-agnostic region picker.

Keep the existing caption, resize/reselect behavior, callbacks and test seams;
character/session policy still belongs to CropController, not RegionPicker.
"""

from . import regionpicker
from .regionpicker import (  # noqa: F401 — compatibility seams used by picker callers/tests
    _PICKERS,
    _RGB,
    _THEME,
    _dispatch,
    _render_overlay,
    layered,
)

_CLASS_REGISTERED = False


def _ensure_class(libs):
    global _CLASS_REGISTERED
    if not _CLASS_REGISTERED:
        regionpicker._register_class(libs, "WingmanPreviewCropPicker")
        _CLASS_REGISTERED = True


class CropPicker(regionpicker.RegionPicker):
    class_name = "WingmanPreviewCropPicker"

    @staticmethod
    def _ensure_class(libs):
        _ensure_class(libs)

    @classmethod
    def create(cls, libs, client, monitor, *, on_confirm, on_cancel):
        return super().create(
            libs,
            client,
            monitor,
            caption=f"FlyGD Wingman crop - {client.character}",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            strict_size=False,
        )
