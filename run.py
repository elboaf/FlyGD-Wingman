"""Frozen-application entry point.

PyInstaller runs its entry file as a bare script, so relative imports inside
__main__.py would fail. This shim imports the package absolutely instead.
"""

from obs_youtube_uploader.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
