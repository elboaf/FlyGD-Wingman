import obspython as obs
import subprocess
import os
import platform

# Globals configured via OBS script UI
recording_dir = ""
python_path = ""
uploader_path = ""

def script_description():
    return "Launches the YouTube Uploader GUI whenever OBS stops recording."

def script_properties():
    props = obs.obs_properties_create()

    obs.obs_properties_add_path(
        props, "recording_dir", "Recording Directory", 
        obs.OBS_PATH_DIRECTORY, "", ""
    )

    obs.obs_properties_add_path(
        props, "python_path", "Python Executable (use pythonw.exe on Windows for no console)", 
        obs.OBS_PATH_FILE, "Executable (*.exe);;All Files (*)", ""
    )

    return props

def script_update(settings):
    global recording_dir, python_path, uploader_path
    recording_dir = obs.obs_data_get_string(settings, "recording_dir")
    python_path = obs.obs_data_get_string(settings, "python_path")

    if not python_path:
        # Default: pythonw on Windows (no console window), python elsewhere
        python_path = "pythonw" if platform.system() == "Windows" else "python"

    # Auto-locate the uploader script next to this OBS script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    uploader_path = os.path.join(script_dir, "youtube_uploader.py")

def on_event(event):
    if event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        if not recording_dir:
            print("[OBS Uploader] Error: Recording directory not configured in script properties.")
            return
        if not os.path.exists(uploader_path):
            print(f"[OBS Uploader] Error: Uploader script not found at {uploader_path}")
            return

        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            subprocess.Popen(
                [python_path, uploader_path, recording_dir],
                close_fds=True,
                startupinfo=startupinfo
            )
            print(f"[OBS Uploader] Launched uploader for: {recording_dir}")
        except Exception as e:
            print(f"[OBS Uploader] Failed to launch: {e}")

def script_load(settings):
    obs.obs_frontend_add_event_callback(on_event)

def script_unload():
    pass
