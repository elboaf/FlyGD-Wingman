"""The Tk UI is gone, and must stay gone.

Two failure modes this guards, both of which look fine locally and break a
frozen build:

  * a module left importable invites a new call site against a UI that no
    longer has a window to attach to;
  * a stray `import tkinter` anywhere in the import graph drags Tcl/Tk into
    the PyInstaller bundle, silently adding megabytes and a dependency the
    spec says we no longer have.
"""

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.mark.parametrize("name", ["app", "settingsui", "theme", "tooltip"])
def test_the_tk_ui_modules_are_gone(name):
    """Deleted, not deprecated -- the same reasoning that removed the
    unscaled pad constants rather than leaving them importable."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"obs_youtube_uploader.{name}")


def test_importing_the_entry_point_does_not_pull_in_tkinter():
    """Run in a subprocess on purpose: another test in this session may have
    imported tkinter already, which would make an in-process sys.modules
    check pass or fail for reasons unrelated to our import graph."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import obs_youtube_uploader.__main__ as m, sys;"
            "print(','.join(n for n in sys.modules if n.startswith('tkinter')))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", (
        f"tkinter reached the import graph via: {result.stdout.strip()}"
    )


def test_sv_ttk_is_no_longer_a_dependency():
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    assert not any(d.lower().startswith("sv-ttk") for d in deps)


def test_pywebview_is_pinned_not_ranged():
    """6.x has live API churn -- FOLDER_DIALOG was deprecated for
    FileDialog.FOLDER mid-series. A range would let an upgrade land without
    a smoke pass on a UI with no automated coverage."""
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    pins = [d for d in deps if d.lower().startswith("pywebview")]
    assert pins == ["pywebview==6.2.1"], pins


def test_pillow_is_kept():
    """It looks like a Tk-era dependency and is not: build_tray() opens the
    bundled .ico with it and draws the generated fallback icon."""
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    assert any(d.lower().startswith("pillow") for d in deps)
