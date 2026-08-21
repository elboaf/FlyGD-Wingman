"""Measurement harness: the real window and the real page, nothing else.

Plan step 1 needs two numbers that cannot be derived on paper:

  1. the band the inset actually produces (asking for 6 produced 3 on the
     spike, cause unresolved);
  2. the narrowest width the list layout survives, which depends on `52ch`
     resolved against the bundled Inter face.

Both have to be measured against the REAL page -- the spike's placeholder
says nothing about where the list columns collide -- and against the REAL
`ui/chrome.py`, because the spike passing only ever proved the spike works.

So this calls `ui.window.create()` exactly as `__main__` does, and stops
there. What it deliberately does NOT do is everything else `__main__.main()
`does: no single-instance lock, no settings load, no watcher, no tray icon,
no scheduler, no OAuth. Running the real app to measure a window would take
the user's instance lock, poll their real recording folder, and mix the
measurement into their live logs.

`js_api` is a stub rather than the real `Api`. Importing `ui.api` would
drag in the Google client stack and the uploader for no benefit, and the
page only needs the bridge to exist -- its calls will fail, leaving an
empty list, which is exactly the state the column widths matter in anyway.

RUN IT (Windows, WebView2 present)
----------------------------------
    frameless-measure.exe

Read the `resize band:` line it prints for number 1. For number 2, drag the
window narrower until the list columns collide -- headers overlapping or
the filename column with no room left -- and read the width off the live
`size:` line.

Throwaway, like the spike beside it. Delete both once the constants land.
"""
from __future__ import annotations

import logging
import sys


class _StubApi:
    """Just enough to be a js_api.

    `_window` is underscored for the same reason the real Api underscores
    it: pywebview builds its JS proxy by walking PUBLIC attributes, and a
    public webview.Window sends that walk into WinForms until
    RecursionError kills the process.

    Only the two title-bar actions are implemented. Everything else the
    page calls -- list_rows, panel_text, auth_labels and the rest -- is
    absent on purpose, so the list stays empty and none of the app's
    machinery runs. That is the point of the harness; an empty list is
    also the state the column widths matter in.

    Without these two the window cannot be closed from its own UI at all,
    because the OS title bar is gone and the page's buttons are the only
    controls there are.
    """

    def __init__(self) -> None:
        self._window = None

    def minimize(self) -> None:
        self._window.minimize()

    def close(self) -> None:
        # DESTROY, unlike the real Api, which hides to the tray. There is
        # no tray here, so hiding would strand a running process with no
        # way to reach it.
        self._window.destroy()


def main() -> int:
    if sys.platform != "win32":
        print("Only meaningful on Windows.", file=sys.stderr)
        return 2

    # Line-buffered and on stdout: a frozen console build block-buffers
    # otherwise, and a run that has to be killed loses its measurements.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s",
                        stream=sys.stdout)

    # Deliberately NOT `from obs_youtube_uploader.__main__ import
    # set_dpi_awareness`: __main__ imports the watcher, the uploader and
    # the Google client stack, none of which this needs and all of which
    # PyInstaller would then have to resolve. Three lines copied is cheaper
    # than dragging the app in to measure its window. Mirrors
    # __main__.set_dpi_awareness() -- awareness level 1, PROCESS_SYSTEM_DPI
    # _AWARE -- and must stay in step with it, or this measures a window in
    # a coordinate space the app never runs in.
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass  # shcore.dll predates Windows 8.1, same swallow as the app.

    # ui.window imports only logging, sys, pathlib and ui.chrome, so this
    # stays light. ui.api would not -- hence the stub above.
    from obs_youtube_uploader.ui import window as window_mod

    # `--floor N` drops min_size so the layout's REAL collision point can be
    # found. The shipping floor stopped the drag before anything collided,
    # which proves it is safe but not that it is right -- an over-generous
    # floor stops people making the window as small as they want, and the
    # only way to know the true number is to get out of the way and look.
    # Overridden here rather than in window.py so the production constants
    # are never shipped at a measurement value.
    if "--floor" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--floor") + 1])
        window_mod.MIN_WIDTH = floor
        window_mod.MIN_HEIGHT = floor
        print(f"min_size overridden to {floor} x {floor} FOR MEASUREMENT")

    window = window_mod.create(_StubApi())

    def on_resized(width, height):
        # The number to read while dragging narrower. Logical pixels, as
        # pywebview reports them (winforms.py:435).
        print(f"size: {width} x {height}")

    window.events.resized += on_resized
    print(f"min_size asked for: {window_mod.MIN_WIDTH} x {window_mod.MIN_HEIGHT}")

    window_mod.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
