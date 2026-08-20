"""Tk window: video list, link column, upload and delete controls."""
import shutil
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

from . import library, paths, settings as settings_mod, stitch, uploader


def resolve_binary(name: str) -> str | None:
    """Find a bundled binary, falling back to PATH."""
    exe = f"{name}.exe"
    candidate = paths.bundle_dir() / "bin" / exe
    if candidate.exists():
        return str(candidate)
    candidate = paths.bundle_dir() / exe
    if candidate.exists():
        return str(candidate)
    return shutil.which(name)


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
        self.links: dict[Path, tk.Entry] = {}
        self.upload_thread: threading.Thread | None = None
        self.on_deleted = None  # set by the tray app to notify the watcher
        self.on_settings_saved = None  # set by the tray app; see _settings_saved
        self.retry_state: "RetryState | None" = None

        root.title("OBS → YouTube Uploader")
        root.geometry("1350x650")
        root.minsize(750, 450)
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
        meta = ttk.LabelFrame(self.root, text="Video details", padding=8)
        meta.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(meta, text="Title:").grid(row=0, column=0, sticky=tk.W)
        self.title_var = tk.StringVar(value="")
        ttk.Entry(meta, textvariable=self.title_var).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(meta, text="Description:").grid(row=1, column=0, sticky=tk.NW, pady=(5, 0))
        self.desc_txt = tk.Text(meta, height=3, wrap=tk.WORD)
        self.desc_txt.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(5, 0))
        meta.columnconfigure(1, weight=1)

        self.list_frame = ttk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        hdr = ttk.Frame(self.list_frame)
        hdr.pack(fill=tk.X)
        for text, width in (("☑", 3), ("Filename", 30), ("Date", 14),
                            ("Size", 9), ("Duration", 8), ("YouTube Link", 48)):
            anchor = tk.CENTER if text == "☑" else tk.W
            ttk.Label(hdr, text=text, width=width, anchor=anchor).pack(side=tk.LEFT, padx=2)
        ttk.Separator(self.list_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        self.canvas = tk.Canvas(self.list_frame, highlightthickness=0)
        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.stitch_var = tk.BooleanVar(value=False)
        bot = ttk.Frame(self.root)
        bot.pack(fill=tk.X, padx=5, pady=5)
        self.stitch_chk = ttk.Checkbutton(bot, text="Stitch selected videos",
                                          variable=self.stitch_var)
        self.stitch_chk.pack(side=tk.LEFT)
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            ttk.Label(bot, text="(ffmpeg not found — stitching unavailable)",
                      foreground="orange").pack(side=tk.LEFT, padx=6)
        for text, cmd in (("Upload Selected", self._start_upload),
                          ("Delete Selected", self._delete_selected),
                          ("Select None", lambda: self._set_all(False)),
                          ("Select All", lambda: self._set_all(True))):
            ttk.Button(bot, text=text, command=cmd).pack(side=tk.RIGHT, padx=2)
        self.retry_btn = ttk.Button(bot, text="Retry", command=self._manual_retry)
        self.retry_btn.pack(side=tk.RIGHT, padx=2)
        self.retry_btn.state(["disabled"])
        ttk.Button(bot, text="Settings", command=self._open_settings).pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=5, pady=(0, 3))
        self.status = ttk.Label(self.root, text="")
        self.status.pack(fill=tk.X, padx=5, pady=(0, 5))

    def refresh(self, preselect: set | None = None) -> None:
        """Rebuild the list. Paths in *preselect* start checked.

        The watcher passes newly-ready recordings here so the common case —
        finish a fight, open the window, hit Upload — needs no clicking.
        """
        preselect = preselect or set()
        for child in self.inner.winfo_children():
            child.destroy()
        self.selected.clear()
        self.links.clear()
        self.infos = [
            library.build_info(p, self.state.ffprobe_bin)
            for p in library.discover(self.state.recording_dir)
        ]
        for info in self.infos:
            row = ttk.Frame(self.inner)
            row.pack(fill=tk.X, pady=1)
            var = tk.BooleanVar(value=info.path in preselect)
            self.selected[info.path] = var
            ttk.Checkbutton(row, variable=var, width=2).pack(side=tk.LEFT, padx=2)
            for text, width in ((info.path.name, 30), (info.date_str, 14),
                                (info.size_str, 9), (info.duration_str, 8)):
                ttk.Label(row, text=text, width=width, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            entry = tk.Entry(row, width=48, state="readonly", relief=tk.FLAT, fg="blue")
            entry.pack(side=tk.LEFT, padx=2)
            self.links[info.path] = entry
            ttk.Button(row, text="Copy", width=5,
                       command=lambda e=entry: self._copy(e)).pack(side=tk.LEFT, padx=2)
            ttk.Button(row, text="Open", width=5,
                       command=lambda e=entry: self._open(e)).pack(side=tk.LEFT, padx=(0, 8))
        self.status.config(text=f"Found {len(self.infos)} video(s)")

    def _set_all(self, value: bool) -> None:
        for var in self.selected.values():
            var.set(value)

    def _chosen(self) -> list[library.VideoInfo]:
        return [i for i in self.infos if self.selected.get(i.path, tk.BooleanVar()).get()]

    def _copy(self, entry: tk.Entry) -> None:
        url = entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.status.config(text="Link copied to clipboard", foreground="green")

    def _open(self, entry: tk.Entry) -> None:
        url = entry.get()
        if url:
            webbrowser.open(url)

    def _set_link(self, path: Path, video_id: str) -> None:
        """Link rows by source path, never by list position.

        Position-based matching (as in b04c3a7) shifts every subsequent row
        when one upload returns no ID.
        """
        entry = self.links.get(path)
        if entry is None:
            return
        entry.config(state=tk.NORMAL)
        entry.delete(0, tk.END)
        entry.insert(0, f"https://www.youtube.com/watch?v={video_id}")
        entry.config(state="readonly")

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

    def _ui(self, fn, *args) -> None:
        """Marshal a call onto the Tk main thread. Workers never touch widgets."""
        self.root.after(0, lambda: fn(*args))

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
                with stitch.stitched(sources, self.state.ffmpeg_bin, paths.tmp_dir()) as merged:
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
            self._ui(self.status.config, {"text": "Upload complete!", "foreground": "green"})
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
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._ui(self.status.config, {"text": str(exc), "foreground": "red"})
            if exc.outcome is uploader.Outcome.RETRY:
                self._ui(self.retry_btn.state, ["!disabled"])
        except Exception as exc:
            self.retry_state = None
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._ui(self.status.config, {"text": f"Error: {exc}", "foreground": "red"})

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total) -> str:
        body = uploader.build_body(job.title, job.description, job.privacy,
                                   job.category, index, total)
        media = MediaFileUpload(str(path), chunksize=uploader.CHUNK_SIZE, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        def on_progress(fraction: float) -> None:
            pct = ((index + fraction) / total) * 100
            self._ui(self.progress.config, {"value": pct})
            self._ui(self.status.config,
                     {"text": f"Uploading {index + 1}/{total} — {fraction * 100:.1f}%"})

        def on_retry(attempt: int, delay: float) -> None:
            self._ui(self.status.config,
                     {"text": f"Network problem — retrying in {delay:.0f}s "
                              f"(attempt {attempt})", "foreground": "orange"})

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
            self._ui(self.status.config, {"text": str(exc), "foreground": "red"})
            self._ui(self.retry_btn.state, ["!disabled"])
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            self._upload_worker(replace(state.job, start_index=state.resume_index + 1))
        else:
            self.retry_state = None
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": "green"})
            self._ui(self.progress.config, {"value": 100})
            self._ui(self.retry_btn.state, ["disabled"])

    def _open_settings(self) -> None:
        # Imported lazily: settingsui.py does not exist until Task 11. A
        # top-level import here would break this task before that module
        # is written.
        from .settingsui import SettingsWindow
        SettingsWindow(self.root, self.state, on_saved=self._settings_saved)

    def _settings_saved(self) -> None:
        if self.on_settings_saved is not None:
            self.on_settings_saved()
        self.refresh()
