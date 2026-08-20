#!/usr/bin/env python3
"""
OBS YouTube Uploader
Standalone GUI that opens when OBS stops recording.
"""

import os
import sys
import platform
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import json
import threading
import datetime
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve all paths relative to THIS script so OBS's CWD doesn't matter
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / "youtube_token.json"
CLIENT_SECRETS_FILE = SCRIPT_DIR / "client_secrets.json"
SETTINGS_FILE = SCRIPT_DIR / "uploader_settings.json"
LOG_FILE = SCRIPT_DIR / "uploader_debug.log"
VIDEO_EXTS = {".mkv", ".mp4", ".flv", ".mov", ".avi", ".ts", ".m4v", ".webm"}

# ---------------------------------------------------------------------------
# Optional Google imports
# ---------------------------------------------------------------------------
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------
def log(msg):
    ts = datetime.datetime.now().isoformat()
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(line, end="")

# ---------------------------------------------------------------------------
# FFmpeg binary resolution — script dir first, then system PATH
# ---------------------------------------------------------------------------
def _resolve_bin(name: str) -> str | None:
    """Look for ffmpeg/ffprobe in SCRIPT_DIR first, then PATH."""
    # Windows executable names
    if platform.system() == "Windows":
        candidates = [f"{name}.exe", f"{name}.cmd", f"{name}.bat"]
    else:
        candidates = [name]

    # 1. Check script directory
    for c in candidates:
        local = SCRIPT_DIR / c
        if local.exists():
            return str(local)

    # 2. Check system PATH
    for c in candidates:
        # shutil.which handles PATH lookup cross-platform
        import shutil
        found = shutil.which(c)
        if found:
            return found

    return None

FFMPEG_BIN = _resolve_bin("ffmpeg")
FFPROBE_BIN = _resolve_bin("ffprobe")

def format_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def check_ffmpeg():
    return FFMPEG_BIN is not None and FFPROBE_BIN is not None

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
class VideoEntry:
    def __init__(self, path: Path):
        self.path = path
        self.selected = tk.BooleanVar(value=False)
        self._load_info()

    def _load_info(self):
        st = self.path.stat()
        self.mtime = st.st_mtime
        self.size = st.st_size
        self.date_str = datetime.datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")
        self.size_str = format_size(self.size)
        try:
            result = subprocess.run(
                [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(self.path)],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                dur = float(result.stdout.strip())
                self.duration = dur
                m, s = divmod(int(dur), 60)
                self.duration_str = f"{m}:{s:02d}"
            else:
                self.duration = 0
                self.duration_str = "?"
        except Exception:
            self.duration = 0
            self.duration_str = "?"

# ---------------------------------------------------------------------------
# Settings / OAuth window
# ---------------------------------------------------------------------------
class SettingsWindow:
    def __init__(self, parent, app):
        self.app = app
        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        self.win.geometry("520x620")
        self.win.transient(parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self._load_state()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 10}
        frm = ttk.Frame(self.win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        auth = ttk.LabelFrame(frm, text="YouTube Authentication", padding=10)
        auth.pack(fill=tk.X, **pad)

        self.lbl_auth = ttk.Label(auth, text="Not Connected", foreground="red")
        self.lbl_auth.pack(anchor=tk.W)

        btn_frm = ttk.Frame(auth)
        btn_frm.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frm, text="Connect Google Account", command=self._connect).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frm, text="Disconnect", command=self._disconnect).pack(side=tk.LEFT, padx=2)

        defaults = ttk.LabelFrame(frm, text="Upload Defaults", padding=10)
        defaults.pack(fill=tk.X, **pad)

        ttk.Label(defaults, text="Privacy:").grid(row=0, column=0, sticky=tk.W)
        self.privacy = tk.StringVar(value="unlisted")
        ttk.Combobox(defaults, textvariable=self.privacy, values=["private", "unlisted", "public"],
                     state="readonly", width=12).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(defaults, text="Category ID:").grid(row=1, column=0, sticky=tk.W, pady=(8,0))
        self.category = tk.StringVar(value="20")
        ttk.Entry(defaults, textvariable=self.category, width=10).grid(row=1, column=1, sticky=tk.W, padx=5, pady=(8,0))
        defaults.columnconfigure(2, weight=1)

        info = ttk.LabelFrame(frm, text="How to connect", padding=10)
        info.pack(fill=tk.BOTH, expand=True, **pad)
        txt = (
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a new project and enable \"YouTube Data API v3\"\n"
            "3. Go to Credentials → Create Credentials → OAuth client ID\n"
            "4. Choose \"Desktop app\", give it a name, then click Create\n"
            "5. Download the JSON file and rename it to:\n"
            "   client_secrets.json\n"
            "6. Go to OAuth consent screen → Audience → Test users\n"
            "   and ADD YOUR EMAIL ADDRESS as a test user\n"
            "7. Place client_secrets.json in the same folder as this script:\n"
            f"   {SCRIPT_DIR}\n"
            "8. Click \"Connect Google Account\" above"
        )
        ttk.Label(info, text=txt, justify=tk.LEFT).pack(anchor=tk.W)

        ttk.Button(frm, text="Close", command=self._on_close).pack(pady=5)

    def _load_state(self):
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            self.privacy.set(data.get("privacy", "unlisted"))
            self.category.set(data.get("category", "20"))
        if TOKEN_FILE.exists():
            self.lbl_auth.config(text="Connected", foreground="green")

    def _on_close(self):
        data = {"privacy": self.privacy.get(), "category": self.category.get()}
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f)
        self.win.destroy()

    def _connect(self):
        log("Connect button clicked")
        if not GOOGLE_AVAILABLE:
            messagebox.showerror("Missing Libraries",
                "Google API libraries not installed.\n\n"
                "Run: pip install google-api-python-client google-auth-oauthlib")
            return
        if not CLIENT_SECRETS_FILE.exists():
            messagebox.showerror("Missing File",
                f"client_secrets.json not found!\n\n"
                f"Expected at: {CLIENT_SECRETS_FILE}")
            return

        self.lbl_auth.config(text="Authenticating… check your browser", foreground="orange")

        def worker():
            try:
                log("Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
                log("Launching local server for OAuth callback...")
                creds = flow.run_local_server(port=0)
                log(f"OAuth flow returned credentials for: {getattr(creds, 'client_id', 'unknown')}")

                token_data = creds.to_json()
                log(f"Token JSON length: {len(token_data)} chars")

                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(token_data)
                log(f"Token saved to: {TOKEN_FILE}")

                self.win.after(0, lambda: self.lbl_auth.config(text="Connected", foreground="green"))
                self.win.after(0, lambda: messagebox.showinfo("Success", "YouTube account connected!"))
            except Exception as exc:
                full_tb = traceback.format_exc()
                log(f"AUTH FAILED:\n{full_tb}")
                err_msg = f"{type(exc).__name__}: {exc}\n\nSee log for full details:\n{LOG_FILE}"
                self.win.after(0, lambda: self.lbl_auth.config(text="Connection failed", foreground="red"))
                self.win.after(0, lambda msg=err_msg: messagebox.showerror("Auth Error", msg))

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect(self):
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self.lbl_auth.config(text="Not Connected", foreground="red")

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class UploaderApp:
    def __init__(self, root: tk.Tk, recording_dir: str):
        self.root = root
        self.dir = Path(recording_dir)
        self.videos: list[VideoEntry] = []
        self.has_ffmpeg = check_ffmpeg()
        self.upload_thread = None
        self.stitch_var = tk.BooleanVar(value=False)

        self.root.title("OBS → YouTube Uploader")
        self.root.geometry("950x650")
        self.root.minsize(750, 450)

        self._build_ui()
        self._scan_videos()

        if not self.has_ffmpeg:
            self.status.config(
                text="WARNING: ffmpeg/ffprobe not found in script folder or PATH. Stitching disabled.",
                foreground="red"
            )

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=5)
        top.pack(fill=tk.X)
        ttk.Label(top, text=f"Directory: {self.dir}", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh", command=self._scan_videos).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="Settings", command=self._open_settings).pack(side=tk.RIGHT, padx=3)

        meta = ttk.LabelFrame(self.root, text="Upload Details", padding=8)
        meta.pack(fill=tk.X, padx=5, pady=3)

        ttk.Label(meta, text="Title:").grid(row=0, column=0, sticky=tk.W)
        self.title_var = tk.StringVar(value="EVE Online Recording")
        ttk.Entry(meta, textvariable=self.title_var).grid(row=0, column=1, sticky=tk.EW, padx=5)

        ttk.Label(meta, text="Description:").grid(row=1, column=0, sticky=tk.NW, pady=(5,0))
        self.desc_txt = tk.Text(meta, height=3, wrap=tk.WORD)
        self.desc_txt.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(5,0))
        self.desc_txt.insert("1.0", "Recorded with OBS + FightRecorder\nUploaded via OBS YouTube Uploader")
        meta.columnconfigure(1, weight=1)

        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        hdr = ttk.Frame(list_frame)
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="☑", width=4, anchor=tk.CENTER).pack(side=tk.LEFT)
        ttk.Label(hdr, text="Filename", width=45, anchor=tk.W).pack(side=tk.LEFT, padx=2)
        ttk.Label(hdr, text="Date", width=16, anchor=tk.W).pack(side=tk.LEFT, padx=2)
        ttk.Label(hdr, text="Size", width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)
        ttk.Label(hdr, text="Duration", width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)
        ttk.Separator(list_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        self.canvas = tk.Canvas(list_frame, highlightthickness=0)
        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.canvas.configure(yscrollcommand=vsb.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        bot = ttk.Frame(self.root, padding=5)
        bot.pack(fill=tk.X)

        ttk.Checkbutton(bot, text="Stitch selected videos (earliest → latest)",
                       variable=self.stitch_var).pack(side=tk.LEFT)

        ttk.Button(bot, text="Select All", command=self._select_all).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bot, text="Select None", command=self._select_none).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bot, text="Upload Selected", command=self._start_upload).pack(side=tk.RIGHT, padx=2)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=5, pady=(0, 3))

        self.status = ttk.Label(self.root, text="Ready", anchor=tk.W)
        self.status.pack(fill=tk.X, padx=5)

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _scan_videos(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.videos.clear()

        if not self.dir.exists():
            self.status.config(text=f"Directory not found: {self.dir}")
            return

        files = [f for f in self.dir.iterdir() if f.suffix.lower() in VIDEO_EXTS]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for f in files:
            v = VideoEntry(f)
            self.videos.append(v)
            row = ttk.Frame(self.inner)
            row.pack(fill=tk.X, pady=1)
            ttk.Checkbutton(row, variable=v.selected, width=2).pack(side=tk.LEFT, padx=2)
            ttk.Label(row, text=f.name, width=45, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            ttk.Label(row, text=v.date_str, width=16, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            ttk.Label(row, text=v.size_str, width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            ttk.Label(row, text=v.duration_str, width=10, anchor=tk.W).pack(side=tk.LEFT, padx=2)

        self.status.config(text=f"Found {len(self.videos)} video(s)")

    def _select_all(self):
        for v in self.videos:
            v.selected.set(True)

    def _select_none(self):
        for v in self.videos:
            v.selected.set(False)

    def _open_settings(self):
        SettingsWindow(self.root, self)

    def _start_upload(self):
        selected = [v for v in self.videos if v.selected.get()]
        if not selected:
            messagebox.showwarning("No Selection", "Select at least one video to upload.")
            return
        if self.stitch_var.get() and not self.has_ffmpeg:
            messagebox.showerror("FFmpeg Missing",
                "Stitching requires ffmpeg.exe and ffprobe.exe in the script folder or system PATH.")
            return
        if self.upload_thread and self.upload_thread.is_alive():
            messagebox.showwarning("Busy", "An upload is already in progress.")
            return

        self.upload_thread = threading.Thread(target=self._upload_worker, args=(selected,), daemon=True)
        self.upload_thread.start()

    def _upload_worker(self, selected: list[VideoEntry]):
        try:
            self.root.after(0, lambda: self.status.config(text="Preparing…"))

            if self.stitch_var.get():
                if len(selected) < 2:
                    self.root.after(0, lambda: messagebox.showwarning("Stitch", "Select 2+ videos to stitch."))
                    return
                self.root.after(0, lambda: self.status.config(text="Stitching with FFmpeg…"))
                upload_path = self._stitch(selected)
                if not upload_path:
                    return
                files = [upload_path]
                cleanup_stitch = True
            else:
                files = [v.path for v in selected]
                cleanup_stitch = False

            if not TOKEN_FILE.exists():
                self.root.after(0, lambda: messagebox.showerror("Not Authenticated",
                    "Connect your Google account in Settings first."))
                return

            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if not creds.valid:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            privacy = "unlisted"
            category = "20"
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    d = json.load(f)
                privacy = d.get("privacy", "private")
                category = d.get("category", "20")

            title = self.title_var.get() or "Untitled"
            description = self.desc_txt.get("1.0", tk.END).strip()

            total = len(files)
            for idx, fp in enumerate(files):
                self._upload_one(youtube, fp, idx, total, title, description, privacy, category)

            self.root.after(0, lambda: self.status.config(text="Upload complete!", foreground="green"))
            self.root.after(0, lambda: self.progress.config(value=100))

            if cleanup_stitch and os.path.exists(upload_path):
                os.remove(upload_path)

        except Exception as e:
            full_tb = traceback.format_exc()
            log(f"UPLOAD FAILED:\n{full_tb}")
            self.root.after(0, lambda: self.status.config(text=f"Error: {e}", foreground="red"))
            self.root.after(0, lambda: messagebox.showerror("Upload Failed", str(e)))

    def _stitch(self, videos: list[VideoEntry]) -> Path | None:
        videos = sorted(videos, key=lambda v: v.mtime)
        tmp = Path(os.environ.get("TEMP", "/tmp"))
        out_file = tmp / "obs_stitched_upload.mkv"

        inputs = []
        filter_parts = []
        for i, v in enumerate(videos):
            inputs.extend(["-i", str(v.path)])
            filter_parts.append(f"[{i}:v][{i}:a]")

        n = len(videos)
        filter_str = f"{''.join(filter_parts)}concat=n={n}:v=1:a=1[outv][outa]"

        cmd = [
            FFMPEG_BIN, "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_file)
        ]

        self.root.after(0, lambda: self.status.config(text="Stitching with FFmpeg…"))
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            self.root.after(0, lambda: messagebox.showerror("Stitch Failed", result.stderr[-800:]))
            return None
        return out_file

    def _upload_one(self, youtube, file_path: Path, idx: int, total: int,
                    title: str, description: str, privacy: str, category: str):
        body = {
            "snippet": {
                "title": title if total == 1 else f"{title} ({idx+1}/{total})",
                "description": description,
                "categoryId": category,
            },
            "status": {"privacyStatus": privacy},
        }

        media = MediaFileUpload(str(file_path), chunksize=4 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = ((idx + status.progress()) / total) * 100
                self.root.after(0, lambda p=pct: self.progress.config(value=p))
                self.root.after(0, lambda: self.status.config(
                    text=f"Uploading {idx+1}/{total} — {status.progress()*100:.1f}%"
                ))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    log(f"=== Uploader started. Args: {sys.argv} ===")
    log(f"SCRIPT_DIR: {SCRIPT_DIR}")
    log(f"FFMPEG_BIN: {FFMPEG_BIN}")
    log(f"FFPROBE_BIN: {FFPROBE_BIN}")
    if len(sys.argv) >= 2:
        rec_dir = sys.argv[1]
    else:
        rec_dir = filedialog.askdirectory(title="Select your OBS recording folder")
        if not rec_dir:
            return

    root = tk.Tk()
    app = UploaderApp(root, rec_dir)
    root.mainloop()

if __name__ == "__main__":
    main()
