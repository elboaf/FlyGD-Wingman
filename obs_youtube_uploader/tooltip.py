"""Hover tooltips.

Tk ships none, so this is the whole implementation: a borderless Toplevel
shown after a delay and destroyed on leave.

The text DECISION is separated from the widget machinery (tooltip_for_cell),
because the decision is what regresses and the machinery is in the layer this
repo has no test harness for -- the same split library.duration_str and
app.format_selection_summary already use.
"""
import tkinter as tk
from tkinter import ttk

from .ui.copy import tooltip_for_cell  # noqa: F401

# Long enough not to fire while the pointer crosses the list on its way
# somewhere else; short enough that deliberately resting on a glyph feels
# answered rather than ignored.
DELAY_MS = 450


class Tooltip:
    """A hover tooltip for one widget.

    *text* is either a string, or a callable taking the motion event and
    returning a string (show it) or None (show nothing). The callable form is
    what lets a single instance serve every cell of a Treeview.
    """

    def __init__(self, widget: tk.Misc, text) -> None:
        self.widget = widget
        self.text = text
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        self._shown_for: str | None = None
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        # Any click means the user is acting, not asking. Also covers the
        # case where a click opens a dialog and the tip would otherwise be
        # orphaned above it.
        widget.bind("<Button>", self._on_leave, add="+")

    def _resolve(self, event) -> str | None:
        if callable(self.text):
            try:
                return self.text(event)
            except Exception:
                # A tooltip must never take down the widget it decorates.
                return None
        return self.text

    def _on_motion(self, event) -> None:
        text = self._resolve(event)
        if text is None:
            self._on_leave(event)
            return
        if text == self._shown_for and self._tip is not None:
            return  # already showing this exact text; do not restart it
        self._cancel()
        self._destroy()
        self._after_id = self.widget.after(
            DELAY_MS, lambda: self._show(text, event.x_root, event.y_root))

    def _on_leave(self, _event=None) -> None:
        self._cancel()
        self._destroy()

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _destroy(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
        self._shown_for = None

    def _show(self, text: str, x_root: int, y_root: int) -> None:
        self._after_id = None
        if not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)          # no title bar, no border
        tip.wm_geometry(f"+{x_root + 12}+{y_root + 18}")
        # A themed Label inside a themed Frame, so the tip follows light/dark
        # with the rest of the app rather than staying a Tk-default yellow.
        frame = ttk.Frame(tip, relief=tk.SOLID, borderwidth=1)
        frame.pack()
        ttk.Label(frame, text=text, justify=tk.LEFT, padding=6).pack()
        self._tip = tip
        self._shown_for = text
