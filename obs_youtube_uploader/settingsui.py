"""Settings dialog: upload defaults, notification mode, Google account."""
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import app as app_mod
from . import combatlog, discord, obsconfig, paths, settings as settings_mod, theme, uploader

PRIVACY_CHOICES = ["private", "unlisted", "public"]
NOTIFY_CHOICES = ["toast", "popup"]

# How often the dialog checks whether the background auth lookup finished.
AUTH_POLL_MS = 50

# YouTube API Services Developer Policies III.A.1 requires an API Client to
# display a link to YouTube's Terms of Service. This is that link: it lives
# next to the sign-in button because that is where the user opts in to
# uploading, and it must stay reachable in the shipped UI -- a mention in the
# README alone does not satisfy "the API Client must display".
YOUTUBE_TOS_URL = "https://www.youtube.com/t/terms"


class SettingsWindow:
    def __init__(self, parent: tk.Misc, state, on_saved=None):
        self.state = state
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        icon_path = paths.icon_file()
        if icon_path is not None:
            try:
                self.win.iconbitmap(str(icon_path))
            except tk.TclError:
                pass  # Same optional-cosmetic policy as the main window.
        self.win.transient(parent)
        self.win.grab_set()

        cfg = state.settings
        self._auth_generation = 0
        self.privacy = tk.StringVar(value=cfg["privacy"])
        self.category = tk.StringVar(value=cfg["category"])
        self.notify = tk.StringVar(value=cfg["notify_mode"])
        self.rec_dir = tk.StringVar(value=str(state.recording_dir))
        self.webhook = tk.StringVar(value=cfg.get("discord_webhook", "") or "")
        self.gamelogs = tk.StringVar(value=cfg.get("gamelogs_dir") or "")
        self._auth_kind: str | None = None
        self._build()
        self._refresh_auth_label()
        self._refresh_webhook_label()
        # Keep the label in step with the field. Without this it describes
        # whatever was configured when the dialog opened, so a user who
        # pastes a new webhook sees the OLD one summarised underneath it --
        # misleading in the one place they look to confirm they pasted the
        # right thing. parse_webhook is a regex and a urlparse, so running
        # it per keystroke costs nothing worth caching.
        self.webhook.trace_add("write", lambda *_: self._refresh_webhook_label())

        theme.register(self._on_theme_changed)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self.win.bind("<Destroy>", self._on_destroy)

        # Size the window to what its content actually needs rather than a
        # fixed guess: at higher Windows display-scaling factors (125%,
        # 150%) the six packed frames are taller than any hard-coded
        # height, which used to clip the Recording folder frame and the
        # Save/Cancel row right off the bottom of the dialog (fixed in
        # b23f9cc, when there were five — the Discord frame has since been
        # added, so there is more content to clip, not less). Now that the
        # process declares DPI awareness (PROCESS_SYSTEM_DPI_AWARE,
        # __main__.py) instead of being bitmap-stretched by the OS,
        # winfo_reqwidth/winfo_reqheight already reflect real scaled pixels
        # — but the *floor* below was chosen in the pre-DPI-aware world and
        # must scale with it too, or it under-sizes the dialog at 125%/150%
        # relative to today's fix. Compute the natural size after layout,
        # keep a scaled starting width, and let height follow the content,
        # clamped so the dialog cannot open taller than the screen at 150%.
        #
        # That clamp subtracts a scaled margin rather than querying the real
        # work area: Tk exposes only winfo_screenheight(), which includes
        # the taskbar, and has no cross-platform work-area API. The margin
        # is a deliberate approximation of a bottom taskbar, not a measured
        # value.
        #
        # minsize normally pins the dialog at its natural size, which is the
        # b23f9cc guarantee: the user cannot shrink the Save/Cancel row back
        # out of view. But when the content genuinely does not fit the usable
        # height, pinning would re-create b23f9cc's own symptom with the
        # escape hatch closed — Save/Cancel behind the taskbar and no way to
        # resize down to reach them. In that case the floor drops to a modest
        # scaled minimum so the window stays shrinkable and movable.
        self.win.update_idletasks()
        scale = app_mod.dpi_scale(self.win)
        width = max(int(520 * scale), self.win.winfo_reqwidth())
        width = min(width, self.win.winfo_screenwidth())
        natural_height = self.win.winfo_reqheight()
        usable_height = self.win.winfo_screenheight() - int(80 * scale)
        height = min(natural_height, usable_height)
        min_height = (natural_height if natural_height <= usable_height
                      else min(int(400 * scale), usable_height))
        self.win.geometry(f"{width}x{height}")
        self.win.minsize(width, min_height)
        self.win.resizable(True, True)

    def _build(self) -> None:
        # One lookup for the whole build. Every raw pixel constant below is
        # multiplied by this, the same factor app.dpi_scale() gives the main
        # window - character widths (Entry/Combobox `width=`) are NOT pixels
        # and are deliberately left alone.
        scale = app_mod.dpi_scale(self.win)
        pad = app_mod.spacing(self.win)

        # The margin lives on one container rather than on each frame's padx.
        # Per-frame padding gives horizontal breathing room only, which is why
        # the dialog had no gap above the first frame or below Save/Cancel;
        # and it is measured after this runs (winfo_reqwidth, __init__) so the
        # margin has to be inside the geometry request, not outside it.
        body = ttk.Frame(self.win, padding=pad.margin)
        body.pack(fill=tk.BOTH, expand=True)

        acct = ttk.LabelFrame(body, text="Google account",
                              padding=pad.frame)
        acct.pack(fill=tk.X, pady=pad.tight)

        auth_row = ttk.Frame(acct)
        auth_row.pack(anchor=tk.W, fill=tk.X)
        # Scaled with the DPI factor, oval included, or the dot stays a
        # 10px speck beside text that is half again or twice as tall. The
        # inset scales too so it stays centred and round; at 100% this is
        # exactly the original 10x10 canvas with a (1,1)-(9,9) oval.
        dot = max(10, round(10 * scale))
        inset = max(1, round(scale))
        self.auth_dot = tk.Canvas(auth_row, width=dot, height=dot,
                                  highlightthickness=0)
        self.auth_dot.pack(side=tk.LEFT, padx=(0, pad.tight))
        self._auth_dot_id = self.auth_dot.create_oval(
            inset, inset, dot - inset, dot - inset, outline="")
        self.lbl_auth = ttk.Label(auth_row, text="Checking…")
        self.lbl_auth.pack(side=tk.LEFT)

        ttk.Button(acct, text="Connect Google Account",
                   command=self._connect).pack(anchor=tk.W, pady=(pad.tight, 0))
        self.lbl_acct_hint = ttk.Label(
            acct,
            text=("Google hasn't verified this app yet, so the sign-in page "
                  "shows a warning. Click Advanced, then \"Go to FlyGD "
                  "Wingman (unsafe)\" to continue."),
            # wraplength is in PIXELS, so an unscaled 460 wraps this hint at
            # half the apparent width at 200% and turns it into a narrow
            # column beside full-width controls. round(), not int(): the
            # scaling round-trip lands a hair under 1.0 at 96 DPI, and
            # truncating would silently narrow this by a pixel at 100%.
            foreground=theme.token("MUTED"), wraplength=round(460 * scale),
            justify=tk.LEFT,
        )
        self.lbl_acct_hint.pack(anchor=tk.W, pady=(pad.tight, 0))

        self.lbl_tos_hint = ttk.Label(
            acct,
            text=("Videos are uploaded to YouTube and are subject to the "
                  "YouTube Terms of Service:"),
            foreground=theme.token("MUTED"), wraplength=round(460 * scale),
            justify=tk.LEFT,
        )
        self.lbl_tos_hint.pack(anchor=tk.W, pady=(pad.tight, 0))
        self.lbl_tos = ttk.Label(
            acct,
            text=YOUTUBE_TOS_URL, foreground=theme.token("LINK"),
            cursor="hand2")
        self.lbl_tos.pack(anchor=tk.W)
        # Bound rather than made a Button so it reads as a link. The handler
        # is wrapped because webbrowser.open raises when no browser can be
        # resolved, and a dead link must not take the Settings dialog down.
        self.lbl_tos.bind("<Button-1>", lambda _e: self._open_tos())

        up = ttk.LabelFrame(body, text="Upload defaults",
                            padding=pad.frame)
        up.pack(fill=tk.X, pady=pad.tight)
        up.columnconfigure(0, minsize=int(90 * scale))
        ttk.Label(up, text="Privacy:", anchor=tk.E).grid(row=0, column=0, sticky=tk.E)
        ttk.Combobox(up, textvariable=self.privacy, values=PRIVACY_CHOICES,
                     state="readonly", width=12).grid(
            row=0, column=1, sticky=tk.W, padx=pad.tight)
        ttk.Label(up, text="Category ID:", anchor=tk.E).grid(
            row=1, column=0, sticky=tk.E, pady=(pad.tight, 0))
        ttk.Entry(up, textvariable=self.category, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=pad.tight,
            pady=(pad.tight, 0))
        self.lbl_category_hint = ttk.Label(up, text="(20 = Gaming)",
                                           foreground=theme.token("MUTED"))
        self.lbl_category_hint.grid(row=1, column=2, sticky=tk.W)

        beh = ttk.LabelFrame(body, text="When a recording finishes",
                             padding=pad.frame)
        beh.pack(fill=tk.X, pady=pad.tight)
        ttk.Radiobutton(beh, text="Show a tray notification (recommended)",
                        variable=self.notify, value="toast").pack(anchor=tk.W)
        ttk.Radiobutton(beh, text="Open the uploader window immediately",
                        variable=self.notify, value="popup").pack(anchor=tk.W)

        disc = ttk.LabelFrame(body, text="Discord (combat logs)",
                              padding=pad.frame)
        disc.pack(fill=tk.X, pady=pad.tight)
        disc.columnconfigure(0, minsize=int(90 * scale))
        ttk.Label(disc, text="Webhook URL:", anchor=tk.E).grid(
            row=0, column=0, sticky=tk.E)
        ttk.Entry(disc, textvariable=self.webhook, width=44).grid(
            row=0, column=1, sticky=tk.EW, padx=pad.tight)
        self.lbl_webhook = ttk.Label(disc, text="", foreground=theme.token("MUTED"))
        self.lbl_webhook.grid(row=1, column=1, sticky=tk.W, padx=pad.tight)
        ttk.Label(disc, text="Gamelogs:", anchor=tk.E).grid(
            row=2, column=0, sticky=tk.E, pady=(pad.tight, 0))
        ttk.Entry(disc, textvariable=self.gamelogs).grid(
            row=2, column=1, sticky=tk.EW, padx=pad.tight,
            pady=(pad.tight, 0))
        btns = ttk.Frame(disc)
        btns.grid(row=2, column=2, sticky=tk.W, pady=(pad.tight, 0))
        ttk.Button(btns, text="Browse…", command=self._browse_gamelogs).pack(side=tk.LEFT)
        ttk.Button(btns, text="Detect", command=self._detect_gamelogs).pack(
            side=tk.LEFT, padx=(pad.tight, 0))
        disc.columnconfigure(1, weight=1)

        folder = ttk.LabelFrame(body, text="Recording folder",
                                padding=pad.frame)
        folder.pack(fill=tk.X, pady=pad.tight)
        ttk.Entry(folder, textvariable=self.rec_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder, text="Browse…", command=self._browse).pack(
            side=tk.LEFT, padx=(pad.tight, 0))
        ttk.Button(folder, text="Detect", command=self._detect).pack(
            side=tk.LEFT, padx=(pad.tight, 0))

        row = ttk.Frame(body)
        row.pack(fill=tk.X, pady=pad.tight)
        ttk.Button(row, text="Save", command=self._save,
                   style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.win.destroy).pack(
            side=tk.RIGHT, padx=pad.tight)

    def _open_tos(self) -> None:
        try:
            webbrowser.open(YOUTUBE_TOS_URL)
        except Exception:
            messagebox.showinfo(
                "YouTube Terms of Service",
                f"Could not open a browser. The terms are at:\n{YOUTUBE_TOS_URL}")

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.rec_dir.get())
        if chosen:
            self.rec_dir.set(chosen)

    def _detect(self) -> None:
        """Re-run OBS config detection and let the user accept or reject it.

        This is the recovery path for a bad stored ``recording_dir``: the
        stored value normally wins over detection (correctly -- an explicit
        choice should outrank a guess), so once a wrong value is saved
        nothing ever re-runs the guess. This button re-runs it on demand,
        but only fills the entry -- Save is still required, so the user
        sees exactly what changed and can decline it.
        """
        detected = obsconfig.find_recording_dir()
        if detected is None or not detected.is_dir():
            messagebox.showinfo(
                "Detect recording folder",
                "Could not read OBS's configuration to detect a recording "
                "folder. Make sure OBS is installed and has recorded at "
                "least once, then try again.")
            return
        if str(detected) == self.rec_dir.get():
            messagebox.showinfo(
                "Detect recording folder",
                f"Already set to the detected folder:\n{detected}")
            return
        self.rec_dir.set(str(detected))

    def _browse_gamelogs(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.gamelogs.get() or None)
        if chosen:
            self.gamelogs.set(chosen)

    def _detect_gamelogs(self) -> None:
        found = combatlog.find_gamelogs_dir()
        if found is None:
            messagebox.showinfo(
                "Gamelogs not found",
                "Could not find an EVE Gamelogs folder under Documents or "
                "OneDrive\\Documents. Use Browse… to point at it.")
            return
        if str(found) == self.gamelogs.get():
            messagebox.showinfo("Gamelogs", f"Already set to the detected folder:\n{found}")
            return
        self.gamelogs.set(str(found))

    def _refresh_webhook_label(self) -> None:
        hook, _ = discord.parse_webhook(self.webhook.get())
        self.lbl_webhook.config(
            text=discord.describe(hook) if hook else "not configured")

    def _set_auth_status(self, text: str, token_name: str) -> None:
        """Update the status dot + text together. _auth_kind is retained so
        a live theme switch can re-derive the colour rather than reset it."""
        self._auth_kind = token_name
        color = theme.token(token_name)
        self.auth_dot.itemconfig(self._auth_dot_id, fill=color)
        self.lbl_auth.config(text=text, foreground=color)

    def _refresh_auth_label(self) -> None:
        """Resolve the Google auth state without blocking the dialog.

        load_credentials() lazily imports google.oauth2, which drags in
        google.auth, requests and cryptography. Off a PyInstaller build's
        disk that is a visible pause, and it used to happen in __init__ --
        before the dialog was drawn, so opening Settings appeared to hang.
        The label already reads "Checking…", which is now honest.

        The worker touches no Tk object; the main thread polls for its
        result from an ``after`` callback it scheduled itself, rather than
        having the worker call ``after`` itself. See app._start_probe for
        why that indirection is worth it -- here the stake is this label
        being stuck on "Checking…" permanently.

        Each call takes a ticket and only the newest one may write the
        status. On a cold start this lookup takes seconds, which is long
        enough for the user to click Connect Google Account in the
        meantime; without the ticket the in-flight lookup would land after
        _connect set "Waiting for browser…" and replace it with a red "Not
        connected" while the sign-in was still open in the browser.
        """
        if not self.lbl_auth.winfo_exists():
            # _connect's OAuth worker calls back in here when it finishes,
            # by which time the user may have closed the dialog.
            return
        self._auth_generation += 1
        generation = self._auth_generation
        # Through _set_auth_status, not a bare config: it also drives the
        # dot and records _auth_kind, so a theme switch while the lookup is
        # still running re-derives this colour instead of dropping it.
        self._set_auth_status("Checking…", "MUTED")
        result: dict = {}

        def worker() -> None:
            try:
                creds = uploader.load_credentials(paths.token_file())
                result["connected"] = creds is not None and not uploader.needs_reauth(creds)
            except Exception:
                # Never leave the label stuck on "Checking…": an unreadable
                # token is indistinguishable from not being connected, and
                # that is exactly what the user needs to be told.
                result["connected"] = False

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self.win.after(AUTH_POLL_MS,
                       lambda: self._poll_auth(thread, result, generation))

    def _poll_auth(self, thread: threading.Thread, result: dict,
                   generation: int) -> None:
        """Wait for the auth check without blocking. Main thread only."""
        if generation != self._auth_generation:
            return  # Superseded, or a sign-in is now in progress.
        if not self.lbl_auth.winfo_exists():
            return  # Dialog closed while the check was in flight.
        if thread.is_alive():
            self.win.after(AUTH_POLL_MS,
                           lambda: self._poll_auth(thread, result, generation))
            return
        if result.get("connected"):
            self._set_auth_status("Connected", "SUCCESS")
        else:
            self._set_auth_status("Not connected", "ERROR")

    def _connect(self) -> None:
        """Run OAuth off the main thread; it blocks on a browser round-trip.

        This worker thread must never touch a Tk widget directly (Tk is not
        thread-safe) -- all UI updates are marshaled back via
        ``self.win.after(0, ...)``.
        """
        # Claim the auth ticket so a still-running startup check cannot
        # land on top of "Waiting for browser…" with a stale verdict.
        self._auth_generation += 1
        self._set_auth_status("Waiting for browser…", "WARNING")

        def worker() -> None:
            try:
                creds = uploader.run_oauth_flow()
                uploader.save_credentials(creds, paths.token_file())
                self.win.after(0, self._refresh_auth_label)
            except Exception as exc:
                self.win.after(0, lambda: messagebox.showerror(
                    "Connection failed", str(exc)))
                self.win.after(0, self._refresh_auth_label)

        threading.Thread(target=worker, daemon=True).start()

    def _on_theme_changed(self, mode: str) -> None:
        """Re-apply colours set directly rather than through a ttk style:
        the Canvas dot, the auth label, the hint labels, and the YouTube
        Terms of Service link.

        Deferred via after_idle for the same reason UploaderWindow defers:
        sv_ttk.set_theme() fires ttk's <<ThemeChanged>>, which Tk QUEUES, and
        on the next tick tk_setPalette resets any directly-configured widget
        foreground to the new theme's default. Setting them inline here would
        be silently undone one tick later — verified on a real window during
        Task 6. Treeview tags and images are NOT affected; a directly-set
        ttk::Label/Canvas colour is.
        """
        self.win.after_idle(lambda: self._repaint_tokens(mode))

    def _repaint_tokens(self, mode: str) -> None:
        if not self.win.winfo_exists():
            return  # dialog closed between the switch and the idle callback
        self.lbl_acct_hint.config(foreground=theme.token("MUTED", mode))
        self.lbl_tos_hint.config(foreground=theme.token("MUTED", mode))
        self.lbl_tos.config(foreground=theme.token("LINK", mode))
        self.lbl_category_hint.config(foreground=theme.token("MUTED", mode))
        self.lbl_webhook.config(foreground=theme.token("MUTED", mode))
        if self._auth_kind is not None:
            color = theme.token(self._auth_kind, mode)
            self.auth_dot.itemconfig(self._auth_dot_id, fill=color)
            self.lbl_auth.config(foreground=color)

    def _on_destroy(self, event) -> None:
        # <Destroy> fires for every child widget too, so ignore all but the
        # toplevel's own event, or the consumer is removed while the dialog
        # is still alive.
        if event.widget is self.win:
            theme.unregister(self._on_theme_changed)

    def _close(self) -> None:
        self.win.destroy()

    def _save(self) -> None:
        category = self.category.get().strip()
        if not category.isdigit():
            messagebox.showwarning("Invalid category",
                                   "Category ID must be a number, e.g. 20.")
            return
        webhook_raw = self.webhook.get().strip()
        if webhook_raw:
            _, webhook_error = discord.parse_webhook(webhook_raw)
            if webhook_error:
                messagebox.showwarning("Invalid webhook", webhook_error)
                return
        rec_dir = Path(self.rec_dir.get())
        if not rec_dir.is_dir():
            messagebox.showwarning("Invalid folder",
                                   f"{rec_dir} is not a folder.")
            return
        cfg = dict(self.state.settings)
        cfg.update({
            "privacy": self.privacy.get(),
            "category": category,
            "notify_mode": self.notify.get(),
            "recording_dir": str(rec_dir),
            "discord_webhook": webhook_raw,
            "gamelogs_dir": self.gamelogs.get().strip() or None,
        })
        try:
            settings_mod.save(cfg)
        except OSError as exc:
            # settings.save() can fail (disk full, permissions, etc). Bail
            # out before touching in-memory state so state and disk never
            # diverge, and tell the user instead of failing silently -- the
            # dialog stays open with their edits intact so they can retry.
            messagebox.showerror(
                "Could not save settings",
                f"Settings were not saved: {exc}")
            return
        self.state.settings = settings_mod.load()
        self.state.recording_dir = rec_dir
        if self.on_saved is not None:
            self.on_saved()
        self.win.destroy()
