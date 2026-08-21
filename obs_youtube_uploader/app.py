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
               settings as settings_mod, stitch, theme, tooltip, uploader)

# Re-exported, not reimplemented. The copy moved to ui/copy.py ahead of the
# webview port; these names stay resolvable because the Tk window still
# calls them by bare name and will until it is deleted.
from .ui.copy import (format_destination, format_progress,
                       format_selection_summary, format_title_hint,
                       format_upload_confirm)  # noqa: F401

if TYPE_CHECKING:
    # Only for annotations. PIL stays a lazy runtime import (see
    # _build_checkbox_images and __main__.build_tray) so importing app.py
    # does not drag Pillow in.
    from PIL import ImageTk

logger = logging.getLogger(__name__)


def _close_media(media) -> None:
    """Release the file handle a MediaFileUpload holds, best effort.

    MediaFileUpload closes its descriptor only in `__del__`, so anything
    that needs the file released *now* -- to unlink a stitched temporary,
    or to stop blocking a rename of the user's own recording on Windows --
    has to close it explicitly. Tolerates None and objects without a
    stream so callers can hand it whatever they have.
    """
    stream = getattr(media, "stream", None)
    if stream is None:
        return
    try:
        stream().close()
    except Exception:
        # Never worth failing an upload over, but never worth hiding
        # either: a handle that stays open turns into a file the user
        # cannot delete, with no other clue as to why.
        logger.warning("Could not close upload stream", exc_info=True)

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


# Treeview column geometry in pixels at 100%; every value is multiplied by
# dpi_scale() when the columns are configured.
#
# `filename` is the ONLY stretching column, so it is the only one that
# grows on a wider window and the only one that can be squeezed on a
# narrower one: ttk.Treeview distributes both a width surplus and a width
# deficit across its STRETCHING columns and leaves the rest at their
# configured width. A minimum on a non-stretching column is therefore
# never exercised -- it is a floor those columns already sit on.
#
# The consequence is that the list's real floor is the preferred widths of
# the five fixed columns plus `filename`'s MINIMUM, and the window minimum
# is set so that always fits. Measured at 100% against a real window (tree
# viewport = window width - margins - the 300px panel - the pane gap - the
# scrollbar, less a 10px inset inside the tree; the inset is a constant 10
# at 96, 144 and 192 dpi -- it does not scale):
#
#   fixed columns (#0 34 + date 120 + size 84 + length 76 + link 46) = 360px
#   plus filename's 120px minimum                                    = 480px
#   plus the 10px inset                                              = 490px
#   a 750px window gives a 381px viewport -- nowhere near enough
#   an 800px window gives a 431px viewport -- still not enough
#   an 860px window gives a 491px viewport -- 490 fits
#
# So the window minimum IS raised, to 860x450 at 100% (see __init__).
# Making date/size/duration stretch so their minimums became reachable was
# tried and rejected: stretch is symmetric in ttk, so those columns then
# also took an equal share of a SURPLUS (a 1920px window handed Size 344px
# to right-align "1.0 KB" in), and undoing that needed a <Configure>
# handler switching regimes at a threshold width. 60px more minimum window
# width buys the same result with no machinery: "a wider window widens the
# filename column" is true by construction at every width.
#
# No horizontal scrollbar is added: on a list whose elastic column is the
# filename, one trades a rare annoyance for a permanent one. A window
# dragged to its floor still shows a short filename column -- every column
# present and readable, none clipped; that is accepted.
COLUMN_SPEC = (
    # column key, heading text, sort key, width, minwidth, stretch, anchor
    # A bare check, deliberately NOT the ☑ box glyph: every heading in this
    # tree is a sort control, and a box in the header position reads as a
    # select-all checkbox — an affordance this column does not have and does
    # not want, since Select All / Select None are buttons under the list.
    # The mark labels what the column holds; clicking it sorts by it.
    ("#0", "✓", "checked", 34, 34, False, tk.CENTER),
    ("filename", "Filename", "filename", 260, 120, True, tk.W),
    ("date", "Date", "date", 120, 90, False, tk.W),
    ("size", "Size", "size", 84, 64, False, tk.E),
    # Header text only. The KEY stays "duration" because _sort_by dispatches
    # on it, and self.infos exposes info.duration under that name.
    ("duration", "Length", "duration", 76, 56, False, tk.E),
    # NOT stretching: a fixed-width glyph cell that must not grow, and it is
    # already at its minimum, so it never needs to compress either.
    ("link", "Link", "link", 46, 46, False, tk.CENTER),
)

# The link column shows a glyph rather than the URL it used to render across
# ~35% of the list. Nothing is lost: the URL was never selectable inside a
# Treeview, and every consumer of a link (double-click, the context menu,
# the has_link row colour) reads self.links, not the cell.
LINK_GLYPH = "↗"


def link_cell(url: str | None) -> str:
    return LINK_GLYPH if url else ""


def configure_tree_columns(tree: "ttk.Treeview", scale: float,
                           on_sort) -> None:
    """Apply COLUMN_SPEC to *tree*, scaled by *scale*.

    Module-level rather than a method so the geometry can be verified
    against a real widget without standing up a whole UploaderWindow.
    Each heading is anchored like its column: headers were centred over
    left- and right-aligned data, which read as misalignment rather than
    as a deliberate choice.
    """
    for key, text, sort_key, width, minwidth, stretch, anchor in COLUMN_SPEC:
        tree.heading(key, text=text, anchor=anchor,
                     command=lambda k=sort_key: on_sort(k))
        tree.column(key, width=int(width * scale),
                    minwidth=int(minwidth * scale),
                    stretch=stretch, anchor=anchor)


def row_height(checkbox_height: int, linespace: int, scale: float) -> int:
    """Row height in pixels — see _apply_row_height for why each term exists.

    Split out as a pure function because the two font-derived inputs cannot
    be measured meaningfully on the Linux test host (no Xft), while the
    arithmetic that combines them is exactly what regresses.
    """
    return max(checkbox_height + 4, linespace + 3, int(28 * scale))


# Named styles, so emphasis is declared in one place and every consumer
# spells it the same way. TREE_STYLE is the Treeview's own style: ttk
# derives a heading's style by appending ".Heading" to it, and a style with
# no layout of its own falls back to its parent's, so "Wingman.Treeview"
# inherits sv-ttk's Treeview appearance (and the rowheight
# _apply_row_height sets on "Treeview") while giving the headings a name of
# their own to hang a font on.
TREE_STYLE = "Wingman.Treeview"
SECTION_HEADING_STYLE = "Section.TLabel"   # panel section headings ("Upload")
MUTED_STYLE = "Muted.TLabel"               # selection summary, hint labels
HEADING_FONT = "WingmanHeadingFont"
COLUMN_HEADING_FONT = "WingmanColumnFont"  # Treeview column headers
SMALL_FONT = "WingmanSmallFont"            # muted secondary text

# The type scale, as multipliers of sv-ttk's body size.
#
# Everything in this app used to render at one size, with hierarchy carried
# only by bold: column headers, filenames, dates, hints and the status line
# were all identical, so nothing guided the eye down a 132-row list.
#
# Product-register ratios, deliberately tighter than the 1.25 a marketing
# page would use: dense, data-heavy UI wants steps that separate roles
# without making any one of them shout.
SECTION_RATIO = 1.2    # "Upload", settings group titles -- one step above body
SMALL_RATIO = 0.875    # muted text and column headers -- one step below

# Column headers sit BELOW body rather than above it on purpose. They label
# the data; they are not the data. At the same size and weight as the
# filenames underneath, they competed with the content the window exists to
# show.


def scaled_font_size(base: int, ratio: float) -> int:
    """Scale a Tk -size, preserving the unit its sign encodes.

    Tk reads a positive -size as points and a negative one as pixels, so the
    magnitude is scaled and the sign restored: dropping it would silently
    reinterpret the unit and produce a font an order of magnitude wrong.

    A 0 base is returned unchanged -- `font configure` reports 0 for a font
    that has not resolved yet, and inventing a size from that is worse than
    inheriting one. The result is clamped away from 0 for the same reason a
    shrinking step must not erase the text it applies to.
    """
    if not base:
        return 0
    scaled = int(round(abs(base) * ratio))
    return max(1, scaled) * (1 if base > 0 else -1)

# Preference order for what the heading font is derived from. The sv-ttk
# fonts come first because theme._rescale_sv_fonts has already corrected
# them for `tk scaling`; the Tk defaults are a fallback for a build with no
# sv-ttk, not the intended source.
_HEADING_FONT_BASES = ("SunValleyBodyStrongFont", "SunValleyBodyFont",
                       "TkHeadingFont", "TkDefaultFont")


def apply_typography(root: tk.Misc) -> None:
    """Declare the app's emphasis styles. Idempotent; safe to re-run.

    MUST be re-run on every theme change. ttk stores style options per
    theme and sv_ttk.set_theme swaps the theme wholesale, so a style
    configured once is silently gone after the first light/dark switch --
    the same hazard _apply_row_height's docstring describes, and the
    reason both are re-asserted from _on_theme_changed rather than set up
    once in _build.

    The fonts are re-derived from sv-ttk's own font on every call rather
    than remembered, because theme.apply rescales those fonts (for `tk
    scaling`) immediately before the consumers run: copying here is how
    the scale inherits the corrected size instead of freezing a 96-DPI
    one. Family is always sv-ttk's; -size is then multiplied by this
    step's ratio and -weight set per step.

    Row text is deliberately NOT touched. ttk.Treeview has no per-column
    fonts, and per-row tags -- the only other channel -- are already
    fully spent on zebra striping, preselection and has_link (see
    _row_tags), where the tag listed first wins. There is nothing left to
    carry emphasis with, so within the list the scale acts on the column
    headers only, demoting them below the data they label.
    """
    names = {str(n) for n in root.tk.splitlist(root.tk.call("font", "names"))}
    base = next((n for n in _HEADING_FONT_BASES if n in names), None)

    def derive(font_name: str, ratio: float) -> None:
        """Create/refresh one scale step as a copy of the sv-ttk base."""
        if font_name not in names:
            root.tk.call("font", "create", font_name)
        if base is not None:
            root.tk.call("font", "configure", font_name,
                         *root.tk.splitlist(
                             root.tk.call("font", "configure", base)))
            size = int(root.tk.call("font", "configure", font_name, "-size"))
            root.tk.call("font", "configure", font_name, "-size",
                         scaled_font_size(size, ratio))

    derive(HEADING_FONT, SECTION_RATIO)
    derive(COLUMN_HEADING_FONT, SMALL_RATIO)
    derive(SMALL_FONT, SMALL_RATIO)
    root.tk.call("font", "configure", HEADING_FONT, "-weight", "bold")
    root.tk.call("font", "configure", COLUMN_HEADING_FONT, "-weight", "bold")
    # SMALL_FONT keeps the base weight: it carries secondary text, which is
    # demoted by size and colour, not emphasised.
    root.tk.call("font", "configure", SMALL_FONT, "-weight", "normal")

    style = ttk.Style(root)
    style.configure(f"{TREE_STYLE}.Heading", font=COLUMN_HEADING_FONT)
    style.configure(SECTION_HEADING_STYLE, font=HEADING_FONT)
    # Settings' LabelFrame titles are the same role as the panel's "Upload"
    # heading, so they take the same step. One style covers every group in
    # the dialog.
    style.configure("TLabelframe.Label", font=HEADING_FONT)
    # The one secondary-text colour, read live from the token table so a
    # switch recolours it rather than baking in the mode that was active
    # when the widget was built.
    style.configure(MUTED_STYLE, foreground=theme.token("MUTED"),
                    font=SMALL_FONT)


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
        # prevent. At 150% the raw floor is 1200x675, which overflows
        # narrow panels.
        #
        # 860, not the historical 750: measured against a real window, a
        # 750px floor leaves the list viewport 381px wide, which cannot hold
        # the 490px the columns need (see COLUMN_SPEC) — Length was clipped
        # and Link fell off the edge entirely. 860 gives 491px.
        root.minsize(min(int(860 * scale), width), min(int(450 * scale), height))
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()
        self.refresh()

    def show(self, preselect: set | None = None) -> None:
        self.root.deiconify()
        self.root.lift()
        # Re-applied on every show, not only in _build. _build runs while the
        # root is still withdrawn, and a window manager can hand out a
        # different frame after mapping (measured on X11; Tk returns 0x0 for
        # an unmapped window). Win32 HWNDs do not reparent, so this is
        # probably redundant on the target platform — but the failure mode
        # if it is not is silent: both DwmSetWindowAttribute calls simply
        # no-op on a stale handle, nothing raises, and the title bar stays
        # light until the user changes their OS theme. Cheap insurance.
        theme.apply_titlebar(self.root, theme.current_mode())
        self.refresh(preselect)

    def hide(self) -> None:
        self.root.withdraw()

    def _build(self) -> None:
        """Assemble the window: a two-pane body over a full-width status strip.

        Everything hangs off ONE padded frame instead of each section
        packing itself against the root with its own padx/pady. That single
        wrapper is what gives the window outer margins at all — the previous
        layout could only ever put space *between* sections, never around
        them, which is why no amount of tuning the old PAD_* constants
        produced a margin.

        The four regions are built by three helpers rather than inline. Not
        opportunistic tidying: the regions no longer appear in the order a
        reader walks the window (the panel's contents come from what used to
        be three separate places), so a single 110-line method would no
        longer describe anything.
        """
        self._pad = spacing(self.root)
        # Shared helper, not an independent computation: checkbox images,
        # window geometry and panel width must all agree on the scale.
        self._dpi_scale = dpi_scale(self.root)
        # Before any widget is created: the builders below NAME styles
        # (TREE_STYLE, SECTION_HEADING_STYLE, MUTED_STYLE) rather than
        # configuring fonts inline, and a widget naming a style that does
        # not exist yet renders with the theme default and no error.
        apply_typography(self.root)

        outer = ttk.Frame(self.root, padding=self._pad.margin)
        outer.pack(fill=tk.BOTH, expand=True)
        # The body takes every pixel a resize adds; the status strip keeps
        # its natural height, so a taller window grows the list, not the
        # progress bar.
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        body = ttk.Frame(outer)
        body.grid(row=0, column=0, sticky=tk.NSEW)
        body.rowconfigure(0, weight=1)
        # Only the list column stretches. The panel is a fixed width (see
        # _build_upload_panel), so all the slack a wider window brings goes
        # to the list — and `filename` being the tree's only stretching
        # column keeps it going to the one place that benefits from it.
        body.columnconfigure(0, weight=1)

        self._build_list_pane(body)
        # A rule between the panes rather than whitespace alone: at the
        # minimum window width the gap compresses to almost nothing, and
        # two unseparated button groups read as one.
        ttk.Separator(body, orient=tk.VERTICAL).grid(
            row=0, column=1, sticky=tk.NS, padx=(self._pad.loose, 0))
        self._build_upload_panel(body)
        self._build_status_strip(outer)

        # The initial application is explicit, not left to registration:
        # __main__.main() calls theme.apply() before this window is
        # constructed, so a consumer registered here is not invoked until the
        # NEXT theme switch. Registration alone would leave the title bar
        # light until the user changed their OS theme.
        theme.apply_titlebar(self.root, theme.current_mode())

        # Registered last, deliberately: _on_theme_changed dereferences
        # self.ffmpeg_warn_label, self.status and self.desc_txt, all created
        # above. A consumer registered earlier would be fine only for as
        # long as _build stays synchronous.
        theme.register(self._on_theme_changed)

    def _build_list_pane(self, parent: tk.Misc) -> None:
        """The recording list, its scrollbar, and the commands that act on
        the list itself.

        Select All / Select None / Delete Selected sit UNDER the list rather
        than in a shared bottom bar. They operate on rows; the old bar mixed
        them with upload actions and a checkbox, so eight controls of three
        different kinds read as one undifferentiated strip.

        grid rather than pack (the tree used pack before): the button row
        below has to span both the tree and its scrollbar, which pack cannot
        express without a second nesting frame.
        """
        self.list_frame = ttk.Frame(parent)
        self.list_frame.grid(row=0, column=0, sticky=tk.NSEW)
        self.list_frame.rowconfigure(0, weight=1)
        self.list_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self.list_frame,
            columns=("filename", "date", "size", "duration", "link"),
            show="tree headings",
            style=TREE_STYLE,
            # The checkbox is the selection model. A competing
            # highlight-selection would give the user two contradictory
            # notions of "selected", and a stray click would wipe out the
            # watcher's preselection.
            selectmode="none",
        )
        # configure_tree_columns owns the whole column spec — widths, minwidths, anchors,
        # stretch, heading text and their sort commands. Configuring any of
        # it here would silently revert that task.
        configure_tree_columns(self.tree, self._dpi_scale, self._sort_by)

        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scroll.grid(row=0, column=1, sticky=tk.NS)

        self._build_checkbox_images()
        self._apply_row_height()
        self._configure_tree_tags()
        self._build_context_menu()
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_row_double_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<FocusIn>", self._on_tree_focus_in)
        # One instance serves every cell: the callback resolves the text per
        # pointer position, so no per-row wiring survives a refresh().
        tooltip.Tooltip(self.tree, self._tree_tooltip)

        list_actions = ttk.Frame(self.list_frame)
        list_actions.grid(row=1, column=0, columnspan=2, sticky=tk.EW,
                          pady=(self._pad.normal, 0))
        # Delete last and separated: it is the only irreversible action in
        # the group, and it used to sit second from the left, between two
        # harmless ones.
        ttk.Button(list_actions, text="Select All",
                   command=lambda: self._set_all(True)).pack(
            side=tk.LEFT, padx=(0, self._pad.tight))
        ttk.Button(list_actions, text="Select None",
                   command=lambda: self._set_all(False)).pack(
            side=tk.LEFT, padx=(0, self._pad.loose))
        ttk.Button(list_actions, text="Delete Selected",
                   command=self._delete_selected).pack(side=tk.LEFT)

    def _build_upload_panel(self, parent: tk.Misc) -> None:
        """The upload panel: the two fields, the stitch option, and the three
        buttons that consume them.

        Title and Description are the primary input of the common session
        ("fight ended → open → the new recording is preselected → title it →
        upload"), and they used to sit at the top of the window while the
        button that reads them sat at the bottom. They are grouped with that
        button here instead.

        FIXED width, with grid_propagate off: without it the panel would
        size to its widest child (the ffmpeg warning, when present) and the
        window's proportions would depend on whether ffmpeg happens to be
        installed. Fixed also means the panel costs proportionally more the
        narrower the window is — accepted, and covered by the column
        minimums; see "Narrow windows" in ui-layout-design.md.

        Row map, since the selection summary grids into it: 0 heading, 1 separator, 2-3
        Title, 4-5 Description, 6 Stitch, 7 ffmpeg warning, 8 selection
        summary, 9 combat logs, 10 destination, 11 last upload, 12 Retry +
        Upload.
        """
        self._panel_width = int(300 * self._dpi_scale)
        self.upload_panel = ttk.Frame(parent, width=self._panel_width)
        self.upload_panel.grid(row=0, column=2, sticky=tk.NSEW,
                               padx=(self._pad.loose, 0))
        self.upload_panel.grid_propagate(False)
        self.upload_panel.columnconfigure(0, weight=1)
        # The Description box absorbs the panel's vertical slack. Verified
        # on a real display: a bordered box that grows with the window reads
        # as a field, while the same slack left as empty space between
        # groups reads as a hole in the layout.
        self.upload_panel.rowconfigure(5, weight=1)

        # Bold comes from the shared named styles, never from a font
        # pinned on this widget: ttk stores style options per theme, so a
        # font configured here would be wiped by the first light/dark
        # switch. apply_typography re-asserts the style after every switch.
        heading = ttk.Label(self.upload_panel, text="Upload",
                            style=SECTION_HEADING_STYLE)
        heading.grid(row=0, column=0, sticky=tk.W)
        ttk.Separator(self.upload_panel, orient=tk.HORIZONTAL).grid(
            row=1, column=0, sticky=tk.EW, pady=(self._pad.tight, self._pad.normal))

        self.title_label = ttk.Label(self.upload_panel, text="Title")
        self.title_label.grid(row=2, column=0, sticky=tk.W,
                              pady=(0, self._pad.tight))
        self.title_var = tk.StringVar(value="")
        ttk.Entry(self.upload_panel, textvariable=self.title_var).grid(
            row=3, column=0, sticky=tk.EW)

        ttk.Label(self.upload_panel, text="Description").grid(
            row=4, column=0, sticky=tk.W, pady=(self._pad.normal, self._pad.tight))
        # height=3 is a FLOOR, not the rendered height: row 5 carries the
        # weight, so the box grows to whatever the panel has spare. Given a
        # visible border because it is now the panel's largest element —
        # unbordered, a box that big reads as a gap rather than a field.
        # The border width is scaled like every other pixel constant here:
        # a 1px rule around the panel's dominant element is a hairline at
        # 200%, which is exactly the class of defect this layout fixes.
        self.desc_txt = tk.Text(self.upload_panel, height=3, wrap=tk.WORD,
                                relief=tk.SOLID, bd=max(1, int(round(self._dpi_scale))),
                                highlightthickness=0)
        self.desc_txt.grid(row=5, column=0, sticky=tk.NSEW)
        self._apply_desc_colors()
        # ...and again once the event queue drains. theme.apply runs before
        # this window is built, and the <<ThemeChanged>> it queues has not
        # been dispatched yet: sv.tcl's tk_setPalette therefore fires on the
        # first idle tick AFTER the build and stomps the colours just set,
        # exactly as it does on a live switch. Same deferral, same reason;
        # measured, not assumed.
        self.root.after_idle(self._apply_desc_colors)

        self.stitch_var = tk.BooleanVar(value=False)
        # Repaints the Title label: stitching collapses a batch into one
        # video, so it changes what the Title field will actually produce.
        self.stitch_chk = ttk.Checkbutton(self.upload_panel,
                                          text="Stitch selected videos",
                                          variable=self.stitch_var,
                                          command=self._update_selection_summary)
        self.stitch_chk.grid(row=6, column=0, sticky=tk.W,
                             pady=(self._pad.normal, 0))
        self.ffmpeg_warn_label = None
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            # Directly under the checkbox it explains, and WRAPPED: this
            # label came from a full-width bottom bar and does not fit on
            # one line in a 300px panel. Without wraplength Tk would size
            # the label to its full natural width and the fixed panel would
            # simply clip the tail of the sentence.
            self.ffmpeg_warn_label = ttk.Label(
                self.upload_panel, text="(ffmpeg not found — stitching unavailable)",
                foreground=theme.token("WARNING"), justify=tk.LEFT,
                wraplength=self._panel_width - self._pad.normal)
            self.ffmpeg_warn_label.grid(row=7, column=0, sticky=tk.EW,
                                        pady=(self._pad.tight, 0))

        # Row 8. Muted via the shared named styles rather than a
        # foreground set here: apply_typography re-asserts MUTED_STYLE on
        # every theme change, so this label needs no entry in
        # _on_theme_changed -- a manual recolour would be redundant with the
        # style and would drift from it the moment the token changes.
        #
        # A readout, not a control, and placed immediately above the upload
        # buttons: it exists to answer "am I about to upload what I think I
        # am?" at the moment the user is reaching for Upload Selected.
        #
        # Deliberately NOT folded into self.status: that line is owned by
        # progress, errors and "Found N video(s)", all of which overwrite
        # each other. A summary sharing it would be destroyed by the first
        # progress tick of the upload it describes.
        self.selection_summary = ttk.Label(self.upload_panel, text="",
                                           style=MUTED_STYLE, justify=tk.LEFT,
                                           wraplength=self._panel_width - self._pad.normal)
        self.selection_summary.grid(row=8, column=0, sticky=tk.W,
                                    pady=(self._pad.normal, 0))

        # Upload combat logs is a peer upload action, NOT accented, so the
        # primary action stays unambiguous — the same reasoning the old
        # bottom bar carried, preserved here. Full width because it is the
        # only control on its row.
        ttk.Button(self.upload_panel, text="Upload combat logs",
                   command=self._start_combat_log_upload).grid(
            row=9, column=0, sticky=tk.EW, pady=(self._pad.normal, 0))

        # Directly above the button it describes, for the same reason the
        # selection summary sits where it does: this answers "where is this
        # going?" at the moment the user is reaching for Upload Selected.
        # MUTED because it is a readout, not a control, and wrapped because
        # a channel name is user-supplied and can be any length.
        self.destination_label = ttk.Label(
            self.upload_panel, text="", style=MUTED_STYLE, justify=tk.LEFT,
            wraplength=self._panel_width - self._pad.normal)
        self.destination_label.grid(row=10, column=0, sticky=tk.W,
                                    pady=(self._pad.normal, 0))

        # The finished upload's link. Hidden until there is one, because an
        # empty pair of dead buttons is worse than no row at all -- and it
        # is grid_remove()d rather than destroyed so the geometry is
        # already solved the moment an upload lands.
        #
        # Two explicit buttons rather than a clickable URL: the panel is
        # 300px, a YouTube URL does not fit in it, and a truncated link is
        # both unreadable and unselectable inside a ttk.Label.
        self.last_upload_url: str | None = None
        self.last_upload_frame = ttk.Frame(self.upload_panel)
        self.last_upload_frame.grid(row=11, column=0, sticky=tk.EW,
                                    pady=(self._pad.normal, 0))
        self.last_upload_frame.columnconfigure(0, weight=1)
        self.last_upload_frame.columnconfigure(1, weight=1)
        ttk.Button(self.last_upload_frame, text="Open video",
                   command=self._open_last_upload).grid(
            row=0, column=0, sticky=tk.EW, padx=(0, self._pad.tight))
        ttk.Button(self.last_upload_frame, text="Copy link",
                   command=self._copy_last_upload).grid(
            row=0, column=1, sticky=tk.EW)
        self.last_upload_frame.grid_remove()

        actions = ttk.Frame(self.upload_panel)
        actions.grid(row=12, column=0, sticky=tk.EW, pady=(self._pad.tight, 0))
        # Only Upload Selected stretches: Retry keeps its natural width so
        # the accent button is visibly the larger target, and the pair still
        # fills the panel at every scale.
        actions.columnconfigure(1, weight=1)
        self.retry_btn = ttk.Button(actions, text="Retry", command=self._manual_retry)
        self.retry_btn.grid(row=0, column=0, sticky=tk.W, padx=(0, self._pad.tight))
        self.retry_btn.state(["disabled"])
        # Disabled is its normal state, so it reads as broken rather than as
        # dormant. The tooltip is the only place that says what would enable
        # it; ttk still delivers <Motion> to a disabled button.
        tooltip.Tooltip(self.retry_btn,
                        "Enabled after an upload fails.\n"
                        "Resumes the interrupted upload instead of restarting it.")
        ttk.Button(actions, text="Upload Selected", style="Accent.TButton",
                   command=self._start_upload).grid(row=0, column=1, sticky=tk.EW)

    def _build_status_strip(self, parent: tk.Misc) -> None:
        """The full-width strip under both panes: Settings, progress, status.

        Settings moves here because it configures the app rather than acting
        on the list or on an upload, and it was the leftmost item of the old
        action bar — first in reading order, ahead of the two buttons the
        user actually came for.

        No fixed height any more (the old status_bar pinned 48px with
        pack_propagate off). The strip is a single row of three widgets, so
        its natural height is already correct, and a pinned one would clip
        the progress bar at 200%.
        """
        strip = ttk.Frame(parent)
        strip.grid(row=1, column=0, sticky=tk.EW, pady=(self._pad.loose, 0))
        # The bar takes the slack; the message keeps its natural width and
        # stays pinned to the right edge instead of drifting with it.
        strip.columnconfigure(1, weight=1)
        ttk.Button(strip, text="Settings", command=self._open_settings).grid(
            row=0, column=0, sticky=tk.W, padx=(0, self._pad.loose))
        self.progress = ttk.Progressbar(strip, mode="determinate")
        self.progress.grid(row=0, column=1, sticky=tk.EW)
        self.status = ttk.Label(strip, text="")
        self.status.grid(row=0, column=2, sticky=tk.E, padx=(self._pad.loose, 0))

    def _apply_desc_colors(self, mode: str | None = None) -> None:
        """Paint the Description box from theme tokens.

        This box used to be left deliberately unstyled, riding on sv-ttk's
        tk_setPalette side effect. That stops being enough once it has a
        border and is the panel's dominant element: tk_setPalette gives it
        the window background, so a bordered box painted the same colour as
        everything around it reads as a rectangle drawn on nothing.

        ROW_EVEN is reused rather than a new token invented: it is the
        app's existing "surface slightly off the window background" colour
        in both modes, and this box wants exactly that.
        """
        self.desc_txt.config(background=theme.token("ROW_EVEN", mode),
                             foreground=theme.token("FG", mode),
                             insertbackground=theme.token("FG", mode))

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

        A third term, int(28 * scale), is a comfort floor rather than a
        correctness one: over a hundred rows, a height that merely avoids
        clipping reads as a dense spreadsheet. It sits inside the SAME
        max() as the other two, so neither existing guarantee is weakened
        - the checkbox is still never clipped, and the measured line box
        is still never cropped. It scales because a 28px row at 200% is
        the cramped row it exists to prevent.

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
        needed = row_height(self._checkbox_images[True].height(), linespace,
                            self._dpi_scale)
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
        self._update_selection_summary()

    def _on_tree_click(self, event: tk.Event) -> None:
        # The WHOLE row is the click target, not just the checkbox cell: a
        # 34px column is a small thing to ask someone to hit when the intent
        # "I mean this recording" is unambiguous anywhere on the line.
        iid = self.tree.identify_row(event.y)
        if not iid:
            return  # header, or empty space below the last row
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
        # Now that every cell toggles, a double-click anywhere opens the
        # video — the old "skip the checkbox column" guard described a
        # special case that no longer exists.
        #
        # Tk delivers exactly ONE <Button-1> before <Double-Button-1>: the
        # second press dispatches to the more specific binding rather than
        # firing <Button-1> again. (The previous comment here claimed two,
        # which measurement disproved — a double-click on the checkbox cell
        # left the row selected, it did not return it to where it started.)
        # So exactly one toggle has already landed by the time we arrive,
        # and we undo it: opening a video is not a selection gesture, and a
        # user reaching for their upload should not find an extra row
        # ticked afterwards.
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self._toggle_row(iid)
        self._open(Path(iid))

    def _on_theme_changed(self, mode: str) -> None:
        """Registered with theme.register in _build. Regenerates everything
        that bakes theme colours into pixels rather than reading a ttk
        style live: checkbox images and Treeview tag colours.

        This is UploaderWindow's ONE theme consumer. Callers EXTEND this
        method for the status line and ffmpeg warning — it must not define
        and register a second one, or a live switch runs two half-updates
        against the same window.
        """
        self._build_checkbox_images()
        # Beside _apply_row_height for the same reason: set_theme swaps the
        # ttk theme, taking every style option configured against the old
        # one with it.
        apply_typography(self.root)
        self._apply_row_height()
        self._configure_tree_tags()
        for iid in self.tree.get_children(""):
            var = self.selected.get(Path(iid))
            if var is not None:
                self.tree.item(iid, image=self._checkbox_image(var.get()))
        # Widgets whose colour was set directly rather
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
        # Same after_idle reasoning as the two labels above: tk_setPalette
        # runs on the next tick and resets this classic widget's colours.
        # Measured, not assumed — without the deferral the box reverts one
        # tick after the switch. (ttk widgets need nothing here: their
        # colours come from named styles, which apply_typography re-asserts.)
        self.root.after_idle(lambda m=mode: self._apply_desc_colors(m))
        # Extends this window's single consumer rather than registering
        # another: two consumers against one window means two half-updates on
        # a live switch, and this one is not unregistered anywhere.
        theme.apply_titlebar(self.root, mode)

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
        # Links are keyed by path and now OUTLIVE the rebuild. They used to
        # be cleared at the top of this method, which meant the ↗ appeared
        # when an upload finished and then vanished a moment later, because
        # poll() fires a deferred refresh() on exactly that event. Pruning
        # rather than keeping everything: a path that is no longer in the
        # list cannot be shown, opened or copied, so retaining it would only
        # grow the map for the life of the process.
        live = {info.path for info in self.infos}
        self.links = {path: url for path, url in self.links.items()
                      if path in live}
        self._refresh_last_upload()
        pending = durations.resolve(self.duration_cache, self.infos)

        first_preselected_iid = None
        for position, info in enumerate(self.infos):
            var = tk.BooleanVar(value=info.path in preselect)
            self.selected[info.path] = var
            iid = str(info.path)
            self.tree.insert(
                "", tk.END, iid=iid,
                image=self._checkbox_image(var.get()),
                # link_cell rather than a literal "": links now survive a
                # rebuild (they are pruned above, not cleared), so a row
                # whose upload finished keeps its glyph across the refresh
                # that upload triggers.
                values=(info.path.name, info.date_str, info.size_str,
                        info.duration_str, link_cell(self.links.get(info.path))),
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
        # After the rebuild, not before: self.selected was cleared and
        # repopulated above, and the watcher's preselect means a refresh can
        # arrive with rows already checked.
        self._update_selection_summary()

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
        # The summary's duration total is only as complete as the probes
        # behind it. This method is the ONLY place a duration becomes known
        # after the list is drawn, so without this call the "+" partial
        # marker would still be showing on a selection that is now fully
        # measured. Unconditional rather than guarded on "is this info
        # selected": the check costs a dict lookup either way, and a guard
        # that gets the membership test subtly wrong fails silently.
        self._update_selection_summary()

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
        for path, var in self.selected.items():
            var.set(value)
            # The image too, not just the var: nothing traces these
            # BooleanVars, so a row's checkbox is only ever repainted where
            # it is written. Without this, Select All left every box drawn
            # empty while the summary underneath said "N selected".
            self.tree.item(str(path), image=self._checkbox_image(value))
        # Once, after the loop: the label is recomputed from the whole
        # selection, so doing it per row would be N identical repaints of
        # intermediate states.
        self._update_selection_summary()

    def _chosen(self) -> list[library.VideoInfo]:
        return [i for i in self.infos if self.selected.get(i.path, tk.BooleanVar()).get()]

    def _tree_tooltip(self, event) -> str | None:
        """Help text for whatever cell the pointer is over, or None.

        Reads the cell's RENDERED text and hands it to tooltip_for_cell, so
        the help can never describe a glyph the row is not showing.

        Headings and the space below the last row identify as regions other
        than "cell" and get nothing: a tooltip following the pointer across
        empty space would be noise.
        """
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        row = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not row or not column:
            return None
        try:
            # identify_column returns "#N"; #0 is the tree column (the
            # checkbox), which has no help, and displaycolumns maps the rest.
            index = int(column[1:]) - 1
        except ValueError:
            return None
        columns = self.tree.cget("columns")
        if index < 0 or index >= len(columns):
            return None
        key = str(columns[index])
        return tooltip.tooltip_for_cell(key, self.tree.set(row, key))

    def _update_selection_summary(self) -> None:
        """Repaint the panel's selection readout.

        TWO triggers feed this, not one. Selection changes are the obvious
        one -- _toggle_row, _set_all, and refresh() (which rebuilds
        self.selected from scratch and re-applies the watcher's preselect).
        The second is probe completion: _apply_duration writes a resolved
        duration into one Treeview cell by iid and deliberately touches
        nothing else, so a summary wired only to selection changes would sit
        stale behind every probe that lands -- showing a partial total, with
        its "+" marker, long after the probe that completed it.

        Cheap enough to call unconditionally: _chosen() is a list
        comprehension over infos already in memory, and the formatter reads
        only info.size and info.duration.

        The destination line and the Title label ride the same triggers.
        Both depend on the selection (the Title label on its size, to warn
        about batch numbering), so anything that changes what is selected
        has to repaint all three or they drift apart.
        """
        chosen = self._chosen()
        self.selection_summary.config(text=format_selection_summary(chosen))
        self._update_destination()
        self.title_label.config(
            text=format_title_hint(len(chosen), self.stitch_var.get()))

    def _update_destination(self) -> None:
        """Repaint the "uploads go to X" line from stored settings."""
        self.destination_label.config(text=format_destination(
            self.state.settings.get("channel_title", ""),
            self.state.settings.get("privacy", "unlisted")))

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
        refresh() ran mid-upload).

        Links now survive a rebuild: refresh() prunes self.links to the
        paths still listed instead of clearing it, so the glyph set here
        outlives the deferred refresh() that poll() fires the moment the
        upload finishes.
        """
        iid = str(path)
        if not self.tree.exists(iid):
            return
        url = f"https://www.youtube.com/watch?v={video_id}"
        self.links[path] = url
        self.tree.set(iid, "link", link_cell(url))
        self._apply_zebra_tags()
        self._show_last_upload(url)

    def _show_last_upload(self, url: str | None) -> None:
        """Reveal (or hide) the Open/Copy pair for the newest upload."""
        self.last_upload_url = url
        if url:
            self.last_upload_frame.grid()
        else:
            self.last_upload_frame.grid_remove()

    def _refresh_last_upload(self) -> None:
        """Re-point the Open/Copy pair after the list is rebuilt.

        Called from refresh() once self.links has been pruned. If the
        recording behind the last upload is gone, so are the buttons:
        offering "Open video" for a row the user can no longer see is worse
        than offering nothing.

        Newest-first ordering comes from self.infos, which library.discover
        already sorts that way, so this re-derives "most recent" from the
        list rather than remembering an order that a rebuild invalidates.
        """
        for info in self.infos:
            url = self.links.get(info.path)
            if url:
                self._show_last_upload(url)
                return
        self._show_last_upload(None)

    def _open_last_upload(self) -> None:
        if self.last_upload_url:
            webbrowser.open(self.last_upload_url)

    def _copy_last_upload(self) -> None:
        if not self.last_upload_url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_upload_url)
        self._status_kind = "SUCCESS"
        self.status.config(text="Link copied to clipboard",
                           foreground=theme.token("SUCCESS"))

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
        # The last gate before anything becomes public. Deleting local files
        # already confirmed with a full list; publishing to YouTube, which
        # this app cannot undo, did not. Built from the job rather than from
        # the widgets so what is shown is what will be sent.
        if not messagebox.askyesno("Confirm Upload", format_upload_confirm(
                chosen, job.title, job.privacy,
                self.state.settings.get("channel_title", ""), job.stitch)):
            return
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
                    vid = self._upload_one(youtube, MediaFileUpload, merged,
                                           job, 0, 1, close_media=True)
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
            # Gated on RETRY as well, not just on the stitch path: only a
            # RETRY outcome enables the button below, so for anything else
            # the retained request is unreachable -- and it keeps the
            # MediaFileUpload, and with it an open handle on the user's own
            # recording, alive until the next failure replaces this state.
            # On Windows that blocks renaming or deleting that file.
            resumable = (exc.request is not None and not job.stitch
                         and exc.outcome is uploader.Outcome.RETRY)
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

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total,
                    close_media: bool = False) -> str:
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
                     {"text": format_progress(index, total, fraction),
                      "foreground": theme.token("FG")})

        def on_retry(attempt: int, delay: float) -> None:
            self._status_kind = "WARNING"
            self._ui(self.status.config,
                     {"text": f"Network problem — retrying in {delay:.0f}s "
                              f"(attempt {attempt})", "foreground": theme.token("WARNING")})

        try:
            return uploader.upload(request, on_progress=on_progress,
                                   on_retry=on_retry,
                                   on_response=self._remember_channel)
        finally:
            if close_media:
                # The caller is about to delete `path`, and Windows refuses
                # to unlink a file that still has an open handle. Off for
                # the plain path on purpose: UploadFailed hands the
                # resumable request to manual Retry, which resumes by
                # reading from this very stream.
                _close_media(media)

    def _remember_channel(self, response) -> None:
        """Learn the destination channel from a successful insert response.

        This is the only channel information the app can get: SCOPES holds
        youtube.upload alone, and channels.list needs a second scope, which
        would sign every existing user out and add a scope to an OAuth app
        still in verification review.

        Runs on the upload worker thread, so the label repaint is marshalled
        through _ui like every other cross-thread config. The settings write
        is left on this thread deliberately: it is a short plain-file write,
        and persisting here means the channel survives a crash before the
        next clean exit.

        Silent when the response carries no channel (channel_of returns
        ("", "")): the video uploaded fine, and a warning about a missing
        display field would be noise attached to a success.
        """
        channel_id, channel_title = uploader.channel_of(response)
        if not channel_title:
            return
        if (self.state.settings.get("channel_id") == channel_id
                and self.state.settings.get("channel_title") == channel_title):
            return
        self.state.settings["channel_id"] = channel_id
        self.state.settings["channel_title"] = channel_title
        try:
            settings_mod.save(self.state.settings)
        except OSError:
            # Established policy for optional facilities: a settings file
            # that cannot be written must not fail an upload that succeeded.
            logger.exception("could not persist the destination channel")
        self._ui(self._update_destination)

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
            # Same gate as _upload_worker, for the same two reasons: only a
            # RETRY outcome re-enables the button below, so keeping the
            # request for any other outcome retains something unreachable —
            # and that something owns an open handle on the user's own
            # recording, which blocks renaming or deleting it on Windows.
            # Dropping the reference is not enough on its own: closing is
            # left to MediaFileUpload.__del__, whose timing is exactly what
            # made the stitched temp file survive in the first place.
            retryable = exc.outcome is uploader.Outcome.RETRY
            if not retryable:
                _close_media(getattr(exc.request, "resumable", None))
            self.retry_state = replace(state,
                                       request=exc.request if retryable else None)
            self._status_kind = "ERROR"
            self._ui(self.status.config, {"text": str(exc), "foreground": theme.token("ERROR")})
            if retryable:
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
        # Imported lazily because settingsui imports this module at the top
        # level (`from . import app as app_mod`), so a top-level import here
        # would be circular.
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
