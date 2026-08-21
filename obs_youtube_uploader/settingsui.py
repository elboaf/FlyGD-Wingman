"""Settings dialog: upload defaults, notification mode, Google account."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import app as app_mod
from . import combatlog, discord, obsconfig, paths, settings as settings_mod, uploader

PRIVACY_CHOICES = ["private", "unlisted", "public"]
NOTIFY_CHOICES = ["toast", "popup"]


class SettingsWindow:
    def __init__(self, parent: tk.Misc, state, on_saved=None):
        self.state = state
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        self.win.transient(parent)
        self.win.grab_set()

        cfg = state.settings
        self.privacy = tk.StringVar(value=cfg["privacy"])
        self.category = tk.StringVar(value=cfg["category"])
        self.notify = tk.StringVar(value=cfg["notify_mode"])
        self.rec_dir = tk.StringVar(value=str(state.recording_dir))
        self.webhook = tk.StringVar(value=cfg.get("discord_webhook", "") or "")
        self.gamelogs = tk.StringVar(value=cfg.get("gamelogs_dir") or "")
        self._build()
        self._refresh_auth_label()
        self._refresh_webhook_label()

        # Size the window to what its content actually needs rather than a
        # fixed guess: at higher Windows display-scaling factors (125%,
        # 150%) the six packed LabelFrames are taller than any hard-coded
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
        pad = {"padx": 8, "pady": 6}

        acct = ttk.LabelFrame(self.win, text="Google account", padding=10)
        acct.pack(fill=tk.X, **pad)
        self.lbl_auth = ttk.Label(acct, text="Checking…")
        self.lbl_auth.pack(anchor=tk.W)
        ttk.Button(acct, text="Connect Google Account",
                   command=self._connect).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            acct,
            text=("If this is a pre-release build, only approved testers can "
                  "sign in."),
            foreground="gray", wraplength=460, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        up = ttk.LabelFrame(self.win, text="Upload defaults", padding=10)
        up.pack(fill=tk.X, **pad)
        ttk.Label(up, text="Privacy:").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(up, textvariable=self.privacy, values=PRIVACY_CHOICES,
                     state="readonly", width=12).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(up, text="Category ID:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(up, textvariable=self.category, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Label(up, text="(20 = Gaming)", foreground="gray").grid(
            row=1, column=2, sticky=tk.W)

        beh = ttk.LabelFrame(self.win, text="When a recording finishes", padding=10)
        beh.pack(fill=tk.X, **pad)
        ttk.Radiobutton(beh, text="Show a tray notification (recommended)",
                        variable=self.notify, value="toast").pack(anchor=tk.W)
        ttk.Radiobutton(beh, text="Open the uploader window immediately",
                        variable=self.notify, value="popup").pack(anchor=tk.W)

        disc = ttk.LabelFrame(self.win, text="Discord (combat logs)", padding=10)
        disc.pack(fill=tk.X, **pad)
        ttk.Label(disc, text="Webhook URL:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(disc, textvariable=self.webhook, width=44).grid(
            row=0, column=1, sticky=tk.EW, padx=6)
        self.lbl_webhook = ttk.Label(disc, text="", foreground="gray")
        self.lbl_webhook.grid(row=1, column=1, sticky=tk.W, padx=6)
        ttk.Label(disc, text="Gamelogs:").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(disc, textvariable=self.gamelogs).grid(
            row=2, column=1, sticky=tk.EW, padx=6, pady=(6, 0))
        btns = ttk.Frame(disc)
        btns.grid(row=2, column=2, sticky=tk.W, pady=(6, 0))
        ttk.Button(btns, text="Browse…", command=self._browse_gamelogs).pack(side=tk.LEFT)
        ttk.Button(btns, text="Detect", command=self._detect_gamelogs).pack(
            side=tk.LEFT, padx=(4, 0))
        disc.columnconfigure(1, weight=1)

        folder = ttk.LabelFrame(self.win, text="Recording folder", padding=10)
        folder.pack(fill=tk.X, **pad)
        ttk.Entry(folder, textvariable=self.rec_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder, text="Browse…", command=self._browse).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(folder, text="Detect", command=self._detect).pack(
            side=tk.LEFT, padx=(6, 0))

        row = ttk.Frame(self.win)
        row.pack(fill=tk.X, **pad)
        ttk.Button(row, text="Save", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.win.destroy).pack(
            side=tk.RIGHT, padx=6)

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

    def _refresh_auth_label(self) -> None:
        creds = uploader.load_credentials(paths.token_file())
        if creds is not None and not uploader.needs_reauth(creds):
            self.lbl_auth.config(text="Connected", foreground="green")
        else:
            self.lbl_auth.config(text="Not connected", foreground="red")

    def _connect(self) -> None:
        """Run OAuth off the main thread; it blocks on a browser round-trip.

        This worker thread must never touch a Tk widget directly (Tk is not
        thread-safe) -- all UI updates are marshaled back via
        ``self.win.after(0, ...)``.
        """
        self.lbl_auth.config(text="Waiting for browser…", foreground="orange")

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
