"""Tk window: video list, link column, upload and delete controls."""
import datetime
import logging
import queue
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from . import (combatlog, discord, durations, library, paths,
               settings as settings_mod, stitch, theme, uploader)

if TYPE_CHECKING:
    # Only for annotations. PIL stays a lazy runtime import (see
    # _build_checkbox_images and __main__.build_tray) so importing app.py
    # does not drag Pillow in.
    from PIL import ImageTk

logger = logging.getLogger(__name__)

# How often the main thread checks for finished duration probes. Short
# enough that rows fill in as they resolve, long enough to be free.
PROBE_DRAIN_MS = 100


def resolve_binary(name: str) -> str | None:
    """Find a bundled binary, falling back to PATH.

    In a frozen build, `bundle_dir()` is `sys._MEIPASS` and the bundled
    binary lives at its `bin/` subfolder — that path is verified correct
    and left untouched. In a source checkout, `bundle_dir()` is the repo
    root, but `packaging/fetch_ffmpeg.py` writes into `packaging/bin`, not
    `<repo>/bin`. Without this extra lookup, running from source never
    finds the fetched ffmpeg and silently falls back to PATH.
    """
    exe = f"{name}.exe"
    candidate = paths.bundle_dir() / "bin" / exe
    if candidate.exists():
        return str(candidate)
    candidate = paths.bundle_dir() / exe
    if candidate.exists():
        return str(candidate)
    if not hasattr(sys, "_MEIPASS"):
        candidate = paths.bundle_dir() / "packaging" / "bin" / exe
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def dpi_scale(widget: tk.Misc) -> float:
    """Scale factor relative to 100% (96 DPI), for pixel constants chosen
    before this process was DPI-aware.

    `tk scaling` is points-per-pixel (set once in __main__.py as dpi/72);
    dividing by the 96-DPI baseline's own scaling value (96/72) converts
    that back to a plain "1.0 at 100%, 1.5 at 150%" multiplier.

    Rounded to 2 decimals because the round-trip through Tcl is lossy: Tcl
    formats the stored scaling to 5 significant figures, so 96 DPI comes
    back as 1.3331 rather than 1.33333 and this returns 0.99982, not 1.0.
    Every caller then truncates with int(), silently losing a pixel from
    every scaled constant at 100%. Windows display scaling only ever offers
    quarter steps (1.0, 1.25, 1.5, 1.75, 2.0, ...), all of which 2 decimals
    represent exactly, so this recovers the intended factor rather than
    approximating it. Rounding here fixes every call site at once.
    """
    return round(float(widget.tk.call("tk", "scaling")) / (96.0 / 72.0), 2)


@dataclass(frozen=True)
class Spacing:
    """DPI-scaled spacing steps.

    Derived from dpi_scale() rather than kept as fixed pixels, because the
    unscaled constants this replaces were the reason high-DPI layouts grew
    while the space between things did not: at 150% every control was half
    again as tall inside gaps still measured for 96 DPI.

    Frozen so a window cannot mutate the steps for one section and leave the
    rest of the app disagreeing about what "loose" means.
    """
    tight: int    # within one control group (e.g. buttons in one row)
    normal: int   # between controls in a section
    loose: int    # between sections
    margin: int   # window edge; new step, no unscaled equivalent existed
    frame: int    # internal padding of a bordered frame


def spacing(widget: tk.Misc) -> Spacing:
    """Scale the 100% base steps for *widget*'s display.

    max(1, ...) rather than a plain round: a scale small enough to round a
    step to 0 would read as a layout bug (controls touching), not as tight
    spacing. Callers take this once per build and reuse the result, so the
    Tcl round-trip in dpi_scale() is paid once per window, not per widget.
    """
    scale = dpi_scale(widget)
    return Spacing(
        tight=max(1, int(round(4 * scale))),
        normal=max(1, int(round(8 * scale))),
        loose=max(1, int(round(12 * scale))),
        margin=max(1, int(round(16 * scale))),
        frame=max(1, int(round(8 * scale))),
    )


@dataclass
class AppState:
    recording_dir: Path
    settings: dict = field(default_factory=settings_mod.load)
    ffmpeg_bin: str | None = field(default_factory=lambda: resolve_binary("ffmpeg"))
    ffprobe_bin: str | None = field(default_factory=lambda: resolve_binary("ffprobe"))


@dataclass
class UploadJob:
    """Every value the upload worker needs, captured on the main thread.

    Tk is not thread-safe: a worker calling .get() on a StringVar is the
    same violation as configuring a widget from one. Snapshotting into a
    plain dataclass at dispatch time removes the whole class of bug.

    `start_index` lets a retry resume partway through without renumbering
    the "(2/3)" title suffixes: the worker skips earlier indices but still
    computes totals from the full list.
    """
    items: list["library.VideoInfo"]
    title: str
    description: str
    stitch: bool
    privacy: str
    category: str
    start_index: int = 0


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""
    job: UploadJob
    resume_index: int
    request: object | None


class UploaderWindow:
    """The main list window.

    Owns no logic beyond presentation: discovery, stitching, and uploading
    all live in tested modules.
    """

    def __init__(self, root: tk.Tk, state: AppState):
        self.root = root
        self.state = state
        self.infos: list[library.VideoInfo] = []
        self.selected: dict[Path, tk.BooleanVar] = {}
        self.links: dict[Path, str] = {}
        self._preselected: set[Path] = set()
        self._sort_reverse: dict[str, bool] = {}
        self._checkbox_images: dict[bool, "ImageTk.PhotoImage"] = {}
        self._status_kind: str | None = None
        self.upload_thread: threading.Thread | None = None
        self.on_deleted = None  # set by the tray app to notify the watcher
        self.on_settings_saved = None  # set by the tray app; see _settings_saved
        self.retry_state: "RetryState | None" = None
        # Durations are expensive (one ffprobe process each) and never
        # change for a given (path, size, mtime), so they are cached across
        # runs and probed off the main thread. `_refresh_generation` is what
        # makes the async part safe: every refresh() bumps it, and a probe
        # result carrying a stale generation is dropped rather than written
        # into a list that has since been rebuilt.
        self.duration_cache = durations.load(paths.durations_file())
        self._refresh_generation = 0
        self._probe_queue: queue.Queue = queue.Queue()

        root.title("FlyGD Wingman")
        icon_path = paths.icon_file()
        if icon_path is not None:
            try:
                root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass  # Cosmetic only; a bad/missing .ico must not block startup.
        scale = dpi_scale(root)
        width = min(int(1350 * scale), root.winfo_screenwidth())
        height = min(int(650 * scale), root.winfo_screenheight())
        root.geometry(f"{width}x{height}")
        # Clamped against the geometry above, not just scaled: Tk enforces
        # minsize over geometry, so an unclamped minsize larger than the
        # screen would reopen the window oversized *and* make it
        # unshrinkable — exactly what the clamp two lines up exists to
        # prevent. At 150% the raw floor is 1125x675, which overflows
        # narrow panels.
        root.minsize(min(int(750 * scale), width), min(int(450 * scale), height))
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()
        self.refresh()

    def show(self, preselect: set | None = None) -> None:
        self.root.deiconify()
        self.root.lift()
        self.refresh(preselect)

    def hide(self) -> None:
        self.root.withdraw()

    def _build(self) -> None:
        # One lookup for the whole build, mirroring settingsui._build: the
        # Tcl scaling round-trip is per-window state, not per-widget.
        pad = spacing(self.root)
        meta = ttk.LabelFrame(self.root, text="Video details", padding=pad.frame)
        meta.pack(fill=tk.X, padx=pad.normal, pady=pad.tight)
        ttk.Label(meta, text="Title:").grid(row=0, column=0, sticky=tk.W)
        self.title_var = tk.StringVar(value="")
        ttk.Entry(meta, textvariable=self.title_var).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(meta, text="Description:").grid(row=1, column=0, sticky=tk.NW, pady=(5, 0))
        # Deliberately unstyled and NOT in _on_theme_changed: this classic
        # tk.Text follows the theme only because sv-ttk's configure_colors
        # calls tk_setPalette, which reconfigures existing classic widgets.
        # That is sv-ttk's doing, not ours - do not assume our code themes it.
        self.desc_txt = tk.Text(meta, height=3, wrap=tk.WORD)
        self.desc_txt.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(5, 0))
        meta.columnconfigure(1, weight=1)

        self.list_frame = ttk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=pad.normal)

        # Task 4's shared helper — do not compute scale independently here,
        # or checkbox images and window geometry can disagree.
        self._dpi_scale = dpi_scale(self.root)

        self.tree = ttk.Treeview(
            self.list_frame,
            columns=("filename", "date", "size", "duration", "link"),
            show="tree headings",
            # The checkbox is the selection model. A competing
            # highlight-selection would give the user two contradictory
            # notions of "selected", and a stray click would wipe out the
            # watcher's preselection.
            selectmode="none",
        )
        self.tree.heading("#0", text="☑", command=lambda: self._sort_by("checked"))
        self.tree.column("#0", width=int(34 * self._dpi_scale), anchor=tk.CENTER, stretch=False)
        for key, text, chars in (
            ("filename", "Filename", 30),
            ("date", "Date", 14),
            ("size", "Size", 9),
            ("duration", "Duration", 8),
            ("link", "YouTube Link", 48),
        ):
            self.tree.heading(key, text=text, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=int(chars * 7 * self._dpi_scale), anchor=tk.W)

        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._build_checkbox_images()
        self._apply_row_height()
        self._configure_tree_tags()
        self._build_context_menu()
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_row_double_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<FocusIn>", self._on_tree_focus_in)

        self.stitch_var = tk.BooleanVar(value=False)
        bot = ttk.Frame(self.root)
        bot.pack(fill=tk.X, padx=pad.normal, pady=pad.normal)

        ttk.Button(bot, text="Settings", command=self._open_settings).pack(
            side=tk.LEFT, padx=(0, pad.loose))
        ttk.Button(bot, text="Delete Selected", command=self._delete_selected).pack(
            side=tk.LEFT, padx=pad.tight)
        ttk.Button(bot, text="Select All", command=lambda: self._set_all(True)).pack(
            side=tk.LEFT, padx=pad.tight)
        ttk.Button(bot, text="Select None", command=lambda: self._set_all(False)).pack(
            side=tk.LEFT, padx=pad.tight)

        self.stitch_chk = ttk.Checkbutton(bot, text="Stitch selected videos",
                                          variable=self.stitch_var)
        self.stitch_chk.pack(side=tk.LEFT, padx=(pad.loose, pad.tight))
        self.ffmpeg_warn_label = None
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            self.ffmpeg_warn_label = ttk.Label(
                bot, text="(ffmpeg not found — stitching unavailable)",
                foreground=theme.token("WARNING"))
            self.ffmpeg_warn_label.pack(side=tk.LEFT, padx=pad.tight)

        # Right side, packed in visual order: Upload Selected is the accent
        # action, Retry sits beside it, and Upload combat logs — added by the
        # combat-log feature — is a peer upload action, NOT accented, so the
        # primary action stays unambiguous.
        ttk.Button(bot, text="Upload Selected", style="Accent.TButton",
                   command=self._start_upload).pack(side=tk.RIGHT, padx=pad.tight)
        self.retry_btn = ttk.Button(bot, text="Retry", command=self._manual_retry)
        self.retry_btn.pack(side=tk.RIGHT, padx=pad.tight)
        self.retry_btn.state(["disabled"])
        ttk.Button(bot, text="Upload combat logs",
                   command=self._start_combat_log_upload).pack(
            side=tk.RIGHT, padx=pad.tight)

        status_bar = ttk.Frame(self.root, height=int(48 * self._dpi_scale))
        status_bar.pack(fill=tk.X, padx=pad.normal, pady=(0, pad.normal))
        status_bar.pack_propagate(False)  # fixed height regardless of child content
        self.progress = ttk.Progressbar(status_bar, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(pad.tight, 0))
        self.status = ttk.Label(status_bar, text="")
        self.status.pack(fill=tk.X, anchor=tk.W, pady=(pad.tight, 0))

        # Registered last, deliberately: _on_theme_changed dereferences
        # self.ffmpeg_warn_label and self.status, both created above. A
        # consumer registered earlier would be fine only for as long as
        # _build stays synchronous.
        theme.register(self._on_theme_changed)

    def _build_checkbox_images(self) -> None:
        """Generate checked/unchecked box images at the current DPI scale
        and theme colours. Must be re-called on every theme switch — the
        colours are baked into the pixels, not read live like a ttk style.
        """
        from PIL import Image, ImageDraw, ImageTk

        size = max(16, int(16 * self._dpi_scale))
        border = theme.token("MUTED")
        check = theme.token("SUCCESS")
        inset = max(1, size // 8)

        def make(checked: bool) -> "ImageTk.PhotoImage":
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                (inset, inset, size - inset, size - inset),
                radius=max(2, size // 8),
                outline=border,
                width=max(1, size // 10),
            )
            if checked:
                mid_x, mid_y = size * 0.4, size - inset - size * 0.15
                draw.line((inset + size * 0.15, size * 0.5, mid_x, mid_y),
                          fill=check, width=max(2, size // 8))
                draw.line((mid_x, mid_y, size - inset - size * 0.1, inset + size * 0.15),
                          fill=check, width=max(2, size // 8))
            return ImageTk.PhotoImage(img)

        # Held on self so the PhotoImage objects stay referenced; Tk drops
        # unreferenced PhotoImages even while still assigned to a widget.
        self._checkbox_images = {False: make(False), True: make(True)}

    def _checkbox_image(self, checked: bool) -> "ImageTk.PhotoImage":
        return self._checkbox_images[checked]

    def _apply_row_height(self) -> None:
        """Grow the Treeview row so the DPI-scaled checkbox is not clipped.

        Two things have to fit: the DPI-scaled checkbox image, and the
        line box of the text beside it.

        sv-ttk sets `-rowheight` to `[font metrics SunValleyBodyFont
        -linespace] + 3` inside `ttk::style theme create ... -settings`,
        which Tcl evaluates ONCE while sourcing sv.tcl - before
        theme._rescale_sv_fonts() has corrected the font, and never again
        on later switches. So sv-ttk's value is frozen at the 96-DPI line
        height and is independent of the font we actually render with.

        That was harmless while the font was pinned at 14px: the row was
        taller than its text by accident. Now that the font follows `tk
        scaling`, the checkbox-derived floor only wins below ~125%, and
        above that a stale rowheight would crop the text it has to hold.
        So the line height is re-measured HERE, after the rescale, and
        folded into the same max().

        Re-applied from _on_theme_changed because sv_ttk.set_theme rewrites
        rowheight from its .tcl on every switch; theme.apply runs set_theme
        before its consumers, so re-asserting here wins.

        Note this configures the shared "Treeview" style, so it is
        process-global rather than scoped to this widget — a deliberate
        trade, reviewed and kept: this is the app's only Treeview, and a
        second one inheriting a row tall enough for a scaled checkbox is
        benign. A named per-widget style would be more precise but buys
        nothing today. The outer max() below means a theme's own larger
        rowheight is never shrunk.
        """
        # +3 mirrors sv-ttk's own formula, so a correctly-scaled font
        # reproduces the padding sv-ttk intended rather than inventing one.
        # Guarded: the font only exists once sv-ttk has loaded, and this
        # runs unconditionally from _build.
        try:
            linespace = int(self.root.tk.call(
                "font", "metrics", "SunValleyBodyFont", "-linespace"))
        except tk.TclError:
            linespace = 0
        needed = max(self._checkbox_images[True].height() + 4, linespace + 3)
        style = ttk.Style(self.root)
        current = style.lookup("Treeview", "rowheight")
        try:
            current = int(current)
        except (TypeError, ValueError):
            current = 0
        style.configure("Treeview", rowheight=max(current, needed))

    def _configure_tree_tags(self) -> None:
        self.tree.tag_configure("row_odd", background=theme.token("ROW_ODD"))
        self.tree.tag_configure("row_even", background=theme.token("ROW_EVEN"))
        self.tree.tag_configure("row_preselect", background=theme.token("ROW_PRESELECT"))
        self.tree.tag_configure("has_link", foreground=theme.token("LINK"))

    def _row_tags(self, path: Path, position: int) -> tuple[str, ...]:
        # ttk.Treeview gives priority to whichever conflicting tag is
        # listed FIRST, so preselect (a background) must precede the zebra
        # tag (also a background) to win.
        tags = []
        if path in self._preselected:
            tags.append("row_preselect")
        tags.append("row_odd" if position % 2 else "row_even")
        if self.links.get(path):
            tags.append("has_link")
        return tuple(tags)

    def _apply_zebra_tags(self) -> None:
        """Recompute tags for every displayed row, in current display order.

        Needed both after a sort (position changed) and after _set_link
        (has_link tag changed) — cheap enough to just redo all of them.
        """
        for position, iid in enumerate(self.tree.get_children("")):
            path = Path(iid)
            self.tree.item(iid, tags=self._row_tags(path, position))

    def _sort_by(self, column: str) -> None:
        """Display-only sort: it moves Treeview rows and nothing else.

        self.infos keeps its discovery order, so _chosen() (which iterates
        self.infos) and stitch.order_for_stitch() (which re-sorts by mtime)
        are both unaffected by what the user sees on screen.
        """
        info_by_path = {i.path: i for i in self.infos}

        def key(path: Path):
            info = info_by_path[path]
            if column == "checked":
                return self.selected[path].get()
            if column == "filename":
                return info.path.name.lower()
            if column == "date":
                return info.mtime
            if column == "size":
                return info.size
            if column == "duration":
                return info.duration if info.duration is not None else -1.0
            if column == "link":
                return self.links.get(path, "")
            raise ValueError(f"unknown sort column: {column}")

        reverse = self._sort_reverse.get(column, False)
        ordered = sorted(info_by_path.keys(), key=key, reverse=reverse)
        for index, path in enumerate(ordered):
            self.tree.move(str(path), "", index)
        self._sort_reverse[column] = not reverse
        self._apply_zebra_tags()

    def _toggle_row(self, iid: str) -> None:
        """The single toggle path, shared by the mouse and keyboard bindings.

        Kept as one function so the displayed image can never drift out of
        step with the BooleanVar that _chosen() actually reads.
        """
        var = self.selected.get(Path(iid))
        if var is None:
            return
        var.set(not var.get())
        self.tree.item(iid, image=self._checkbox_image(var.get()))

    def _on_tree_click(self, event: tk.Event) -> None:
        if self.tree.identify_region(event.x, event.y) != "tree":
            return  # click landed in a data column, not the checkbox column
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self._toggle_row(iid)

    def _on_tree_space(self, event: tk.Event) -> str:
        """Keyboard equivalent of clicking the checkbox.

        The list this replaced used focusable per-row ttk.Checkbuttons, so
        Tab+Space checked a row; selectmode="none" plus mouse-only bindings
        would have dropped that capability entirely.

        Returns "break" so Tk's own class-level <space> binding
        (ttk::treeview::ToggleFocus, which expands/collapses children) does
        not also fire. It is inert on our flat rows today, but only by
        accident of them having no children.
        """
        iid = self.tree.focus()
        if iid:
            self._toggle_row(iid)
        return "break"

    def _ensure_focus_item(self) -> None:
        """Give the tree a focus item if it has none.

        Tk's arrow-key handler (ttk::treeview::Keynav) returns immediately
        when the focus item is "", and refresh() leaves it "" because every
        row is deleted and reinserted. Without this, tabbing to the list and
        pressing Down does nothing, and _on_tree_space is unreachable
        without first reaching for the mouse — which would leave the
        keyboard path only nominally restored.

        selectmode="none" is not what makes this necessary: Tk's own
        select.choose.none does `$w focus $item`, so focus tracking is
        deliberately alive in this mode. It is the empty starting value.
        """
        if not self.tree.focus():
            children = self.tree.get_children("")
            if children:
                self.tree.focus(children[0])

    def _on_tree_focus_in(self, event: tk.Event) -> None:
        self._ensure_focus_item()

    def _build_context_menu(self) -> None:
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy link", command=self._context_copy)
        self.context_menu.add_command(label="Open in browser", command=self._context_open)
        self._context_path: Path | None = None

    def _show_context_menu(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        path = Path(iid)
        self._context_path = path
        state = tk.NORMAL if self.links.get(path) else tk.DISABLED
        self.context_menu.entryconfig("Copy link", state=state)
        self.context_menu.entryconfig("Open in browser", state=state)
        # try/finally per the documented Tk idiom: a menu dismissed by
        # clicking away can otherwise keep the pointer grab, leaving the
        # window ignoring clicks until another menu is posted — which users
        # report as the app hanging.
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _context_copy(self) -> None:
        if self._context_path is not None:
            self._copy(self._context_path)

    def _context_open(self) -> None:
        if self._context_path is not None:
            self._open(self._context_path)

    def _on_row_double_click(self, event: tk.Event) -> None:
        # A double-click delivers two <Button-1> before <Double-Button-1>, so
        # in the checkbox column the row has already toggled twice. Opening a
        # browser tab on top of that is an action the user never asked for.
        if self.tree.identify_region(event.x, event.y) == "tree":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self._open(Path(iid))

    def _on_theme_changed(self, mode: str) -> None:
        """Registered with theme.register in _build. Regenerates everything
        that bakes theme colours into pixels rather than reading a ttk
        style live: checkbox images and Treeview tag colours.

        This is UploaderWindow's ONE theme consumer. Task 6 EXTENDS this
        method for the status line and ffmpeg warning — it must not define
        and register a second one, or a live switch runs two half-updates
        against the same window.
        """
        self._build_checkbox_images()
        self._apply_row_height()
        self._configure_tree_tags()
        for iid in self.tree.get_children(""):
            var = self.selected.get(Path(iid))
            if var is not None:
                self.tree.item(iid, image=self._checkbox_image(var.get()))
        # Added in Task 6: widgets whose colour was set directly rather
        # than through a ttk style. _status_kind survives the switch so a
        # red error stays red rather than snapping back to default.
        #
        # Deferred via after_idle rather than applied here directly: sv_ttk's
        # `ttk::style theme use` (already run by theme.apply before this
        # consumer fires) queues a Tk <<ThemeChanged>> virtual event rather
        # than firing it synchronously. That event's handler
        # (sv.tcl's configure_colors, via tk_setPalette) does not run until
        # the next idle/event cycle -- i.e. AFTER this method returns -- and
        # it resets any widget still holding the old theme's literal
        # foreground back to the new theme's default. Scheduling the
        # re-colour with after_idle queues it behind that pending event, so
        # it applies last and wins. Verified against a real window: without
        # this, a foreground set here reads back correctly immediately but
        # is stomped to the default by the time the next event-loop tick
        # (root.update()) runs.
        if self.ffmpeg_warn_label is not None:
            self.root.after_idle(
                lambda label=self.ffmpeg_warn_label, m=mode:
                    label.config(foreground=theme.token("WARNING", m)))
        if self._status_kind is not None:
            self.root.after_idle(
                lambda kind=self._status_kind, m=mode:
                    self.status.config(foreground=theme.token(kind, m)))

    def refresh(self, preselect: set | None = None) -> None:
        """Rebuild the list. Paths in *preselect* start checked.

        The watcher passes newly-ready recordings here so the common case —
        finish a fight, open the window, hit Upload — needs no clicking.

        Rows are drawn from a plain stat and shown immediately; durations
        come from the cache when they can, and from a background probe when
        they cannot. This used to run one ffprobe synchronously per file
        before the window appeared, which froze the app for seconds on
        every launch, tray open, settings save, and delete.
        """
        preselect = preselect or set()
        preselect = preselect or set()
        self._preselected = set(preselect)
        # Invalidate any probe still running for the previous list: its
        # results refer to rows that are about to be replaced.
        self._refresh_generation += 1
        generation = self._refresh_generation
        self.selected.clear()
        self.links.clear()
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)

        paths_found = library.discover(self.state.recording_dir)
        infos = []
        for p in paths_found:
            try:
                infos.append(library.stat_info(p))
            except OSError:
                # Vanished between discover() and stat -- discover() already
                # tolerates this race, so the list must too.
                continue
        self.infos = infos
        pending = durations.resolve(self.duration_cache, self.infos)

        first_preselected_iid = None
        for position, info in enumerate(self.infos):
            var = tk.BooleanVar(value=info.path in preselect)
            self.selected[info.path] = var
            iid = str(info.path)
            self.tree.insert(
                "", tk.END, iid=iid,
                image=self._checkbox_image(var.get()),
                values=(info.path.name, info.date_str, info.size_str, info.duration_str, ""),
                tags=self._row_tags(info.path, position),
            )
            if info.path in preselect and first_preselected_iid is None:
                first_preselected_iid = iid
        if first_preselected_iid is not None:
            self.tree.see(first_preselected_iid)
        # Rebuilding cleared the focus item. Only re-seed it if the user is
        # already on the list, or arrow keys go dead mid-session with no
        # FocusIn coming to fix it; seeding unconditionally would put a
        # focus ring on a list nobody has tabbed to yet.
        if self.tree.focus_get() is self.tree:
            self._ensure_focus_item()
        # Colour reset with the text: this line overwrites whatever the
        # last operation left behind, so without it a red error's colour
        # bleeds into a neutral message - and _status_kind would keep it red
        # across a theme switch too.
        self._status_kind = "FG"
        self.status.config(text=f"Found {len(self.infos)} video(s)",
                           foreground=theme.token("FG"))

        # Drop cache entries for recordings no longer in the folder, using
        # the scan just performed rather than a second pass over the disk,
        # and persist immediately when something was actually dropped --
        # deleting from a fully cached folder starts no probe, so the only
        # other writes would never happen and the file would grow forever.
        #
        # An empty scan is never treated as "everything was deleted".
        # discover() returns [] for an unreachable folder exactly as it
        # does for an empty one (library.discover), and recordings on a
        # network or external drive make that a routine event -- one blip
        # while the poll loop calls refresh() would otherwise wipe the
        # whole cache to disk and re-probe every file when the drive
        # returns. A genuinely empty folder just keeps its stale entries
        # until a recording appears, which costs nothing.
        if paths_found and durations.prune(self.duration_cache, paths_found):
            durations.save(paths.durations_file(), self.duration_cache)
        if pending:
            self._start_probe(pending, generation)

    def _start_probe(self, pending: list[library.VideoInfo], generation: int) -> None:
        """Probe *pending* durations on a worker, draining results on the main thread.

        The worker touches no Tk object at all: it pushes results onto a
        queue, and the main thread drains that queue from an ``after``
        callback it scheduled itself.

        The shorter alternative is for the worker to call ``root.after``
        directly, as ``_ui`` does for the upload and combat-log workers.
        That relies on Tkinter marshaling a cross-thread call to the main
        interpreter, which the Windows build's Tk 8.6 does correctly --
        but it is not guaranteed everywhere: on a Tcl 9.0 development
        machine such calls were observed being dropped silently, with no
        exception raised. A dropped status update is a cosmetic loss; a
        dropped probe result would leave the Duration column stuck on "…"
        with no way to recover. Not depending on the behavior at all costs
        one extra timer and removes the question.

        Deliberately not tied to `upload_thread`: that handle is the app's
        "an upload is running" guard, which gates the Upload buttons and
        defers refreshes in __main__.poll. A probe must do neither.
        """
        def worker() -> None:
            try:
                for info in pending:
                    if generation != self._refresh_generation:
                        break  # A newer refresh owns the list now.
                    if info.probed:
                        # _probe_now already resolved this one on demand
                        # (the user clicked something that needed it).
                        # Re-probing would spawn a second ffprobe on the
                        # same file for an answer already in hand.
                        continue
                    duration, definitive = library.probe(
                        info.path, self.state.ffprobe_bin)
                    self._probe_queue.put((generation, info, duration, definitive))
            except Exception:
                # probe() swallows its own failures, so reaching here means
                # something unforeseen. Log it: the rows left unprobed keep
                # showing "…" and in a console=False build stderr goes
                # nowhere, so this would otherwise be invisible.
                logger.warning("Duration probe worker failed", exc_info=True)
            finally:
                # Always sent, including on an early exit or an unexpected
                # error, so the drain loop can stop rescheduling itself.
                self._probe_queue.put((generation, None, None, False))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(PROBE_DRAIN_MS, lambda: self._drain_probes(generation))

    def _drain_probes(self, generation: int) -> None:
        """Apply queued probe results. Runs on the main thread only."""
        if generation != self._refresh_generation:
            return  # Superseded; the newer refresh has its own drain loop.
        done = False
        applied = 0
        while True:
            try:
                gen, info, duration, definitive = self._probe_queue.get_nowait()
            except queue.Empty:
                break
            if gen != self._refresh_generation:
                continue  # Straggler from a previous refresh.
            if info is None:
                done = True
                continue
            self._apply_duration(info, duration, definitive)
            applied += 1
        # Persisted per drain tick rather than only at the end: a cold scan
        # of a large folder takes a while, and a user who opens the window
        # from the tray and quits partway through would otherwise lose
        # every duration measured so far and start over next launch.
        if applied:
            durations.save(paths.durations_file(), self.duration_cache)
        if done:
            return
        self.root.after(PROBE_DRAIN_MS, lambda: self._drain_probes(generation))

    def _apply_duration(self, info: library.VideoInfo, duration: float | None,
                        definitive: bool) -> None:
        """Record one probe result and update its row. Main thread only."""
        if info.probed:
            # Already resolved -- by _probe_now, racing the worker that had
            # this same info in its pending list. Keeping the first answer
            # matters: if the second probe times out it would replace a
            # good duration with a cached "unreadable" that survives
            # restarts and blocks the combat-log upload for that file.
            return
        info.duration = duration
        info.probed = True
        if definitive:
            durations.remember(self.duration_cache, info.path,
                               info.size, info.mtime, duration)
        # The row is addressed by iid (the path), which is what refresh()
        # inserts it under, so updating one cell needs no widget bookkeeping
        # and leaves the checkbox image, tags and link column alone.
        # exists() is defensive: every caller is either synchronous on the
        # current list or generation-guarded, so a missing row should be
        # unreachable.
        iid = str(info.path)
        if self.tree.exists(iid):
            self.tree.set(iid, "duration", info.duration_str)

    def _probe_now(self, infos: list[library.VideoInfo]) -> None:
        """Resolve a selection's durations synchronously, in place.

        The background probe walks the whole folder; a user who selects a
        couple of recordings and immediately clicks a button that needs
        durations should not wait for it, nor be told ffprobe is broken
        because their files happen to be near the end of the queue.

        This does block the main thread -- it is called from a button
        handler that cannot continue without the answer. Usually that is a
        file or two, but "Select All" is right there, and each probe can
        take up to probe()'s 15s timeout, so the loop reports progress and
        shows a busy cursor rather than presenting a frozen window with no
        explanation.
        """
        unprobed = [i for i in infos if not i.probed]
        if not unprobed:
            return
        total = len(unprobed)
        previous_cursor = self.root.cget("cursor")
        # Both halves of the status are saved: the text AND the kind that
        # drives its colour. Restoring the text alone would leave a red
        # error's colour on a neutral message, and would leave _status_kind
        # describing a message no longer on screen -- which a live theme
        # switch would then re-derive from.
        previous_status = self.status.cget("text")
        previous_kind = self._status_kind
        self.root.config(cursor="watch")
        try:
            for index, info in enumerate(unprobed, start=1):
                self._status_kind = "FG"
                self.status.config(
                    text=f"Reading recording lengths… ({index}/{total})",
                    foreground=theme.token("FG"))
                # Redraw the status and cursor without processing user
                # input: update() here would re-enter button handlers from
                # inside one, allowing a second upload to start mid-loop.
                self.root.update_idletasks()
                duration, definitive = library.probe(info.path, self.state.ffprobe_bin)
                self._apply_duration(info, duration, definitive)
        finally:
            self.root.config(cursor=previous_cursor)
            # Callers set their own status next, except on the paths that
            # bail out with a warning dialog -- those should not leave the
            # progress counter frozen on screen as if still working.
            self._status_kind = previous_kind
            self.status.config(
                text=previous_status,
                foreground=theme.token(previous_kind or "FG"))
        durations.save(paths.durations_file(), self.duration_cache)

    def _set_all(self, value: bool) -> None:
        for var in self.selected.values():
            var.set(value)

    def _chosen(self) -> list[library.VideoInfo]:
        return [i for i in self.infos if self.selected.get(i.path, tk.BooleanVar()).get()]

    def _copy(self, path: Path) -> None:
        url = self.links.get(path)
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._status_kind = "SUCCESS"
            self.status.config(text="Link copied to clipboard",
                               foreground=theme.token("SUCCESS"))

    def _open(self, path: Path) -> None:
        url = self.links.get(path)
        if url:
            webbrowser.open(url)

    def _set_link(self, path: Path, video_id: str) -> None:
        """Link rows by source path, never by list position.

        Position-based matching (as in b04c3a7) shifts every subsequent row
        when one upload returns no ID.

        The existence check below guards a `_ui`-queued update arriving for
        a path no longer in the rebuilt tree (e.g. the file was deleted, or
        refresh() ran mid-upload). It does NOT protect against refresh()
        clearing self.links on every rebuild — that clearing is preserved
        deliberately (see refresh()); this guard is a different case.
        """
        iid = str(path)
        if not self.tree.exists(iid):
            return
        url = f"https://www.youtube.com/watch?v={video_id}"
        self.links[path] = url
        self.tree.set(iid, "link", url)
        self._apply_zebra_tags()

    def _delete_selected(self) -> None:
        chosen = self._chosen()
        if not chosen:
            messagebox.showwarning("No Selection", "Select at least one video to delete.")
            return
        names = "\n".join(f"  • {i.path.name}" for i in chosen)
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete these files from disk?\n\n{names}\n\nThis cannot be undone.",
        ):
            return
        deleted, failures = library.delete([i.path for i in chosen])
        # Forget only what actually went. A file that failed to delete still
        # exists, and dropping its seen-entry would make the watcher
        # announce it again as if it were new.
        failed_paths = {p for p, _ in failures}
        if self.on_deleted is not None:
            for info in chosen:
                if info.path not in failed_paths:
                    self.on_deleted(info.path)
        self.refresh()
        msg = f"Deleted {deleted} file(s)."
        if failures:
            msg += f" {len(failures)} failed."
        self.status.config(text=msg)

    def _start_upload(self) -> None:
        chosen = self._chosen()
        if not chosen:
            messagebox.showwarning("No Selection", "Select at least one video to upload.")
            return
        if self.stitch_var.get() and len(chosen) < 2:
            messagebox.showwarning("Stitch", "Select at least two videos to stitch.")
            return
        if self.upload_thread and self.upload_thread.is_alive():
            messagebox.showwarning("Busy", "An upload is already in progress.")
            return
        # Read every widget value HERE, on the main thread. Tk is not
        # thread-safe, and .get() on a StringVar/Text/BooleanVar from a
        # worker is the same violation as configuring a label from one.
        job = UploadJob(
            items=chosen,
            title=self.title_var.get(),
            description=self.desc_txt.get("1.0", tk.END).strip(),
            stitch=self.stitch_var.get(),
            privacy=self.state.settings["privacy"],
            category=self.state.settings["category"],
        )
        self.upload_thread = threading.Thread(
            target=self._upload_worker, args=(job,), daemon=True)
        self.upload_thread.start()

    def _start_combat_log_upload(self) -> None:
        chosen = self._chosen()
        if not chosen:
            messagebox.showwarning("No Selection",
                                   "Select at least one recording to upload logs for.")
            return
        # Reuses the SAME guard as the YouTube upload: one upload of either
        # kind at a time. This inherits the Busy warning and __main__'s
        # refresh deferral, both of which key off upload_thread.
        if self.upload_thread and self.upload_thread.is_alive():
            messagebox.showwarning("Busy", "An upload is already in progress.")
            return

        cfg = self.state.settings
        hook, error = discord.parse_webhook(cfg.get("discord_webhook"))
        if hook is None:
            messagebox.showwarning(
                "Discord not configured",
                f"{error}\n\nAdd a webhook URL in Settings first.")
            return

        gamelogs = cfg.get("gamelogs_dir")
        gamelogs_dir = Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()
        if gamelogs_dir is None or not gamelogs_dir.is_dir():
            messagebox.showwarning(
                "Gamelogs not found",
                "Could not find your EVE Gamelogs folder. Set it in Settings.")
            return

        # A recording with no duration has no start time, so there is no
        # window to build. probe_duration returns None whenever ffprobe is
        # missing or fails, which is a supported state -- refuse rather than
        # invent a window that would silently pull logs from another fight.
        #
        # Resolve any still-pending probe for THIS selection first. Since
        # probing moved to a background worker, an unprobed recording also
        # leaves duration None, and refusing on that would blame ffprobe for
        # a probe that simply had not reached these files yet. Typically one
        # or two files, so the wait is short and only paid by users who beat
        # the worker to the button.
        self._probe_now(chosen)
        missing = [i.path.name for i in chosen if i.duration is None]
        if missing:
            messagebox.showwarning(
                "Cannot determine the time window",
                "These recordings have no readable duration, so the combat-log "
                "window cannot be worked out:\n\n  "
                + "\n  ".join(missing)
                + "\n\nThis usually means ffprobe is unavailable.")
            return

        # Union across the selection: earliest start to latest end, one
        # archive, matching how stitching treats a multi-selection.
        start_utc = min(
            datetime.datetime.fromtimestamp(i.mtime - i.duration, datetime.timezone.utc)
            for i in chosen)
        end_utc = max(
            datetime.datetime.fromtimestamp(i.mtime, datetime.timezone.utc)
            for i in chosen)

        self.upload_thread = threading.Thread(
            target=self._combat_log_worker,
            args=(hook, gamelogs_dir, start_utc, end_utc),
            daemon=True)
        self.upload_thread.start()

    def _ui(self, fn, *args) -> None:
        """Marshal a call onto the Tk main thread. Workers never touch widgets."""
        self.root.after(0, lambda: fn(*args))

    def _combat_log_worker(self, hook, gamelogs_dir, start_utc, end_utc) -> None:
        archive = None
        try:
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Collecting combat logs…", "foreground": theme.token("FG")})
            selection = combatlog.select_logs(gamelogs_dir, start_utc, end_utc)
            if not selection.logs:
                self._ui(messagebox.showinfo, "No logs found", (
                    "No EVE logs overlap that window.\n\n"
                    f"Window (UTC): {start_utc:%Y-%m-%d %H:%M} to {end_utc:%H:%M}\n"
                    f"Folder: {gamelogs_dir}\n\n"
                    "EVE writes log timestamps in UTC, so this window is in "
                    "UTC too."))
                self._status_kind = "FG"
                self._ui(self.status.config,
                         {"text": "No combat logs found.", "foreground": theme.token("FG")})
                return

            stamp = start_utc.strftime("%Y-%m-%d_%H-%M")
            out = paths.tmp_dir() / f"combatlogs-{stamp}.zip"
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Building archive…", "foreground": theme.token("FG")})
            archive = combatlog.build_archive(selection, out, start_utc, end_utc)

            content = combatlog.summarize_archive(archive, start_utc, end_utc)
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": "Posting to Discord…", "foreground": theme.token("FG")})
            result = discord.post_archive(hook, archive.path, content)

            if result.ok:
                # Only remove the archive once Discord has it.
                try:
                    archive.path.unlink()
                except OSError:
                    pass
                # Discord's response message alone (e.g. "Posted x.zip (KB).")
                # doesn't mention a cap; append the same drop note so the
                # status label doesn't quietly disagree with the content the
                # user just sent.
                status_text = result.message
                note = combatlog.dropped_note(archive.dropped)
                if note:
                    status_text += f" ({note})"
                self._status_kind = "SUCCESS"
                self._ui(self.status.config,
                         {"text": status_text, "foreground": theme.token("SUCCESS")})
            else:
                # Keep the archive: the window is fixed by the recording and
                # there is no UI for selecting fewer logs, so a user told
                # "too large" has no move available unless the file survives.
                self._ui(messagebox.showerror, "Combat log upload failed", (
                    f"{result.message}\n\nThe archive was kept so you can "
                    f"upload it by hand:\n{archive.path}"))
                self._status_kind = "ERROR"
                self._ui(self.status.config,
                         {"text": result.message, "foreground": theme.token("ERROR")})
        except Exception as exc:
            # post_archive never raises, but build_archive and
            # summarize_archive can -- and by then the archive may already be
            # on disk. Without this the user gets a bare str(exc) and the
            # "kept so you can upload it by hand" promise, which the failed
            # -post branch above makes and the smoke checklist tests, quietly
            # does not hold on this path.
            detail = str(exc)
            if archive is not None and archive.path.exists():
                detail += ("\n\nThe archive was kept so you can upload it "
                           f"by hand:\n{archive.path}")
            self._ui(messagebox.showerror, "Combat log upload failed", detail)
            self._status_kind = "ERROR"
            self._ui(self.status.config,
                     {"text": f"Error: {exc}", "foreground": theme.token("ERROR")})

    def _upload_worker(self, job: "UploadJob") -> None:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        index = job.start_index
        try:
            creds = uploader.load_credentials(paths.token_file())
            if uploader.needs_reauth(creds):
                creds = uploader.run_oauth_flow()
            elif not creds.valid:
                creds = uploader.refresh_credentials(creds)
            uploader.save_credentials(creds, paths.token_file())
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            if job.stitch:
                ordered = stitch.order_for_stitch(job.items)
                sources = [i.path for i in ordered]
                # A stream copy runs at disk speed, but a multi-gigabyte
                # join is still seconds of no other signal to the user, and
                # ffmpeg reports no progress this code can read. Switch the
                # bar to indeterminate for the duration.
                # Neutral colour set with the text, for the same reason
                # on_progress does it: _start_upload writes no status before
                # launching this worker, so a red error from the previous
                # attempt would otherwise survive into this message.
                self._status_kind = "FG"
                self._ui(self.status.config,
                         {"text": "Stitching with FFmpeg…",
                          "foreground": theme.token("FG")})
                self._ui(self.progress.config, {"mode": "indeterminate"})
                self._ui(self.progress.start, 12)
                with stitch.stitched(sources, self.state.ffmpeg_bin, paths.tmp_dir()) as merged:
                    self._ui(self.progress.stop)
                    self._ui(self.progress.config, {"mode": "determinate", "value": 0})
                    vid = self._upload_one(youtube, MediaFileUpload, merged, job, 0, 1)
                for info in job.items:
                    self._ui(self._set_link, info.path, vid)
            else:
                total = len(job.items)
                for index in range(job.start_index, total):
                    info = job.items[index]
                    vid = self._upload_one(youtube, MediaFileUpload, info.path,
                                           job, index, total)
                    self._ui(self._set_link, info.path, vid)

            self.retry_state = None
            self._status_kind = "SUCCESS"
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": theme.token("SUCCESS")})
            self._ui(self.progress.config, {"value": 100})
            self._ui(self.retry_btn.state, ["disabled"])
        except uploader.UploadFailed as exc:
            # Stitched failures cannot resume: the context manager has
            # already deleted the merged file the session points at, which
            # is the correct trade for never leaking multi-GB temporaries.
            # Retry re-stitches instead.
            resumable = exc.request is not None and not job.stitch
            self.retry_state = RetryState(
                job=job,
                # On the stitch path `index` never advances past
                # job.start_index, so resume_index is not the failing item —
                # but it is never read there either, since `resumable` above
                # forces request=None for stitch failures.
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._status_kind = "ERROR"
            self._ui(self.status.config, {"text": str(exc), "foreground": theme.token("ERROR")})
            if exc.outcome is uploader.Outcome.RETRY:
                self._ui(self.retry_btn.state, ["!disabled"])
        except Exception as exc:
            self.retry_state = None
            # Covers a stitch failure too (StitchError isn't an
            # UploadFailed): if the bar was left indeterminate above, stop
            # it rather than leaving it animating after the error dialog.
            self._ui(self.progress.stop)
            self._ui(self.progress.config, {"mode": "determinate", "value": 0})
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._status_kind = "ERROR"
            self._ui(self.status.config,
                     {"text": f"Error: {exc}", "foreground": theme.token("ERROR")})

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total) -> str:
        body = uploader.build_body(job.title, job.description, job.privacy,
                                   job.category, index, total)
        media = MediaFileUpload(str(path), chunksize=uploader.CHUNK_SIZE, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        def on_progress(fraction: float) -> None:
            pct = ((index + fraction) / total) * 100
            self._ui(self.progress.config, {"value": pct})
            # Neutral foreground set explicitly, not just the text: progress
            # follows on_retry's warning and a previous upload's error, whose
            # colours would otherwise persist through this whole upload.
            self._status_kind = "FG"
            self._ui(self.status.config,
                     {"text": f"Uploading {index + 1}/{total} — {fraction * 100:.1f}%",
                      "foreground": theme.token("FG")})

        def on_retry(attempt: int, delay: float) -> None:
            self._status_kind = "WARNING"
            self._ui(self.status.config,
                     {"text": f"Network problem — retrying in {delay:.0f}s "
                              f"(attempt {attempt})", "foreground": theme.token("WARNING")})

        return uploader.upload(request, on_progress=on_progress, on_retry=on_retry)

    def _manual_retry(self) -> None:
        state = self.retry_state
        if state is None:
            return
        self.retry_btn.state(["disabled"])
        self.upload_thread = threading.Thread(
            target=self._retry_worker, args=(state,), daemon=True)
        self.upload_thread.start()

    def _retry_worker(self, state: "RetryState") -> None:
        """Resume the interrupted upload, then finish the rest of the job."""
        from dataclasses import replace
        if state.request is None:
            # Stitched, or no session to resume: redo the whole job.
            self._upload_worker(replace(state.job, start_index=0))
            return
        try:
            info = state.job.items[state.resume_index]
            total = len(state.job.items)

            def on_progress(fraction: float) -> None:
                pct = ((state.resume_index + fraction) / total) * 100
                self._ui(self.progress.config, {"value": pct})

            vid = uploader.upload(state.request, on_progress=on_progress)
            self._ui(self._set_link, info.path, vid)
        except uploader.UploadFailed as exc:
            self.retry_state = replace(state, request=exc.request)
            self._status_kind = "ERROR"
            self._ui(self.status.config, {"text": str(exc), "foreground": theme.token("ERROR")})
            self._ui(self.retry_btn.state, ["!disabled"])
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            self._upload_worker(replace(state.job, start_index=state.resume_index + 1))
        else:
            self.retry_state = None
            self._status_kind = "SUCCESS"
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": theme.token("SUCCESS")})
            self._ui(self.progress.config, {"value": 100})
            self._ui(self.retry_btn.state, ["disabled"])

    def _open_settings(self) -> None:
        # Imported lazily: settingsui.py does not exist until Task 11. A
        # top-level import here would break this task before that module
        # is written.
        from .settingsui import SettingsWindow
        SettingsWindow(self.root, self.state, on_saved=self._settings_saved)

    def _settings_saved(self) -> None:
        """Settings were saved. The tray app replaces on_settings_saved with a
        handler that rebinds the watcher AND refreshes; when running standalone
        with no such handler, refresh here instead. Not both — refresh() re-probes
        every recording with ffprobe."""
        if self.on_settings_saved is not None:
            self.on_settings_saved()
        else:
            self.refresh()
