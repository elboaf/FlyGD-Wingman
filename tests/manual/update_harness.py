"""Manual Windows integration harness for the production updater seams.

Importing this module is inert on every platform. Native calls occur only after
an explicit subcommand is parsed, and commands that can mutate or launch the
fixture require the long opt-in flag.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from wingman import updates

_FIXTURE_NAME = "Wingman-Update-Harness-Setup.exe"
_MUTEX_NAME = r"Local\FlyGDWingmanUpdateHarness"
_OPT_IN = "--i-understand-this-launches-a-test-exe"
_SERVE_PAYLOAD = b"repeatable updater harness response\n"
_SERVE_URL = (
    "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
    "v0.0.0/Wingman-Update-Harness-Setup.exe"
)
_ERROR_SHARING_VIOLATION = 32


class _FixtureOpener:
    def __init__(self, payload: bytes):
        self._payload = payload

    def open(self, request, timeout=None):
        return io.BytesIO(self._payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_for_payload(payload: bytes, source_url: str, asset_name: str):
    return updates.ReleaseInfo(
        version=(1, 0, 0),
        tag="v1.0.0",
        asset_name=asset_name,
        url=source_url,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        content_type="application/x-msdos-program",
    )


def _release_for_path(path: Path, source_url: str):
    if path.is_file():
        size = path.stat().st_size
        digest = _sha256(path)
    else:
        # The missing-path manual case must still enter launch_verified so its
        # real Attachment Services/protected-open failure path is exercised.
        size = 1
        digest = "0" * 64
    return updates.ReleaseInfo(
        version=(1, 0, 0),
        tag="v1.0.0",
        asset_name=path.name,
        url=source_url,
        size=size,
        sha256=digest,
        content_type="application/x-msdos-program",
    )


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("this subcommand requires Windows")


def _require_fixture(path: Path) -> Path:
    path = Path(path)
    if path.name.casefold() != _FIXTURE_NAME.casefold():
        raise RuntimeError(f"PATH must name the harmless {_FIXTURE_NAME} fixture")
    if path.is_symlink():
        raise RuntimeError("fixture symlinks are refused")
    return path


def _file_facts(path: Path):
    with updates._open_locked(path) as locked:
        identity, size = locked.identity_and_size()
        digest = locked.sha256()
    return identity, size, digest


def _zone_identifier_present(path: Path) -> bool:
    stream_path = Path(f"{path}:Zone.Identifier")
    try:
        with stream_path.open("rb"):
            return True
    except FileNotFoundError:
        return False


def _serve(args, staging_root: Path) -> None:
    expected = _SERVE_PAYLOAD
    if args.mode == "complete":
        response = expected
    elif args.mode == "truncated":
        response = expected[:-1]
    else:
        response = bytes([expected[0] ^ 0xFF]) + expected[1:]

    release = _release_for_payload(expected, _SERVE_URL, _FIXTURE_NAME)
    try:
        path = updates.download_release(
            release,
            staging_root,
            opener=_FixtureOpener(response),
        )
    except updates.UpdateFailure as exc:
        expected_code = {
            "truncated": "size",
            "checksum-mismatch": "checksum",
        }.get(args.mode)
        if exc.code != expected_code:
            raise
        if list(staging_root.iterdir()):
            raise RuntimeError("production download seam retained a partial file")
        print(f"expected failure: stage={exc.stage} code={exc.code}")
        print("partial retention: none")
        return

    if args.mode != "complete":
        raise RuntimeError(f"{args.mode} response unexpectedly passed verification")

    identity, size, digest = _file_facts(path)
    marker = updates.write_handoff_marker(path, release)
    print(f"downloaded: {path}")
    print(f"identity: {identity}")
    print(f"size: {size}")
    print(f"sha256: {digest}")
    print(f"handoff marker created: {marker.name}")
    updates.remove_handoff_marker(marker)
    print(f"handoff marker removed: {not marker.exists()}")


def _attachment(args, staging_root: Path) -> None:
    _require_windows()
    path = _require_fixture(args.path)
    updates.validate_download_origin(args.source_url)
    updates.save_attachment(path, args.source_url)
    identity, size, digest = _file_facts(path)
    zone = "present" if _zone_identifier_present(path) else "absent"
    print(f"identity: {identity}")
    print(f"size: {size}")
    print(f"sha256: {digest}")
    print(f"Zone.Identifier: {zone}")


def _lock_race(args, staging_root: Path) -> None:
    _require_windows()
    source = _require_fixture(args.path)
    staged = staging_root / "update-lock-race.ready.exe"
    replacement = staging_root / "replacement.exe"
    shutil.copy2(source, staged)
    shutil.copy2(source, replacement)
    with replacement.open("r+b") as stream:
        first = stream.read(1)
        if not first:
            raise RuntimeError("fixture is empty")
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0xFF]))

    start_replacement = threading.Event()
    replacement_done = threading.Event()
    result: dict[str, OSError | bool] = {}

    def replace_after_barrier() -> None:
        if not start_replacement.wait(5):
            result["timed_out"] = True
            replacement_done.set()
            return
        try:
            os.replace(replacement, staged)
        except OSError as exc:
            result["error"] = exc
        else:
            result["replaced"] = True
        finally:
            replacement_done.set()

    replacement_thread = threading.Thread(
        target=replace_after_barrier,
        name="update-harness-replacement",
    )
    replacement_thread.start()
    try:
        with updates._open_locked(staged) as locked:
            identity_before, size_before = locked.identity_and_size()
            digest_before = locked.sha256()
            start_replacement.set()
            if not replacement_done.wait(5):
                raise RuntimeError("replacement thread did not finish")
            identity_during, size_during = locked.identity_and_size()
    finally:
        start_replacement.set()
        replacement_thread.join(5)

    if replacement_thread.is_alive():
        raise RuntimeError("replacement thread did not stop")
    error = result.get("error")
    if not isinstance(error, OSError):
        raise RuntimeError("replacement unexpectedly succeeded")
    if getattr(error, "winerror", None) != _ERROR_SHARING_VIOLATION:
        raise RuntimeError(f"replacement failed without sharing violation: {error}")

    identity_after, size_after, digest_after = _file_facts(staged)
    unchanged_identity = identity_before == identity_during == identity_after
    unchanged_size = size_before == size_during == size_after
    unchanged_digest = digest_before == digest_after
    if not (unchanged_identity and unchanged_size and unchanged_digest):
        raise RuntimeError("protected fixture identity, size, or digest changed")

    print("safe retention: sharing violation (winerror=32)")
    print(f"identity unchanged: yes ({identity_after})")
    print(f"size unchanged: yes ({size_after})")
    print(f"sha256 unchanged: yes ({digest_after})")


def _shell_launch(args, staging_root: Path) -> None:
    _require_windows()
    path = _require_fixture(args.path)
    updates.validate_download_origin(args.source_url)
    release = _release_for_path(path, args.source_url)
    process_handle = updates.launch_verified(release, path)
    print(f"returned process handle: {process_handle}")
    updates.close_process_handle(process_handle)
    print("process handle closed: yes")


def _mutex_holder(args, staging_root: Path) -> None:
    _require_windows()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_wchar_p,
    ]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int32

    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        error = ctypes.get_last_error()
        raise OSError(error, f"CreateMutexW failed with error {error}")
    try:
        print(f"holding {_MUTEX_NAME}; press Enter to release")
        input()
    finally:
        if not kernel32.CloseHandle(handle):
            error = ctypes.get_last_error()
            raise OSError(error, f"CloseHandle failed with error {error}")


def _add_opt_in(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        _OPT_IN,
        action="store_true",
        required=True,
        help="required acknowledgement for native fixture mutation/launch",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise Wingman updater seams against a harmless fixture.",
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser(
        "serve", help="inject a local download response", allow_abbrev=False
    )
    serve.add_argument(
        "--mode",
        choices=("complete", "truncated", "checksum-mismatch"),
        required=True,
    )
    serve.set_defaults(handler=_serve)

    attachment = commands.add_parser(
        "attachment", help="run Windows Attachment Services", allow_abbrev=False
    )
    _add_opt_in(attachment)
    attachment.add_argument("path", type=Path)
    attachment.add_argument("source_url")
    attachment.set_defaults(handler=_attachment)

    lock_race = commands.add_parser(
        "lock-race",
        help="race replacement against the protected-file seam",
        allow_abbrev=False,
    )
    _add_opt_in(lock_race)
    lock_race.add_argument("path", type=Path)
    lock_race.set_defaults(handler=_lock_race)

    shell_launch = commands.add_parser(
        "shell-launch",
        help="verify and shell-launch the harmless fixture",
        allow_abbrev=False,
    )
    _add_opt_in(shell_launch)
    shell_launch.add_argument("path", type=Path)
    shell_launch.add_argument("source_url")
    shell_launch.set_defaults(handler=_shell_launch)

    mutex_holder = commands.add_parser(
        "mutex-holder", help="hold only the update harness mutex", allow_abbrev=False
    )
    mutex_holder.set_defaults(handler=_mutex_holder)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="update-native-harness-") as tmp:
            staging_root = Path(tmp)
            print(f"temporary staging root: {staging_root}")
            args.handler(args, staging_root)
        print("temporary staging root removed: yes")
    except updates.UpdateFailure as exc:
        print(
            f"updater failure: stage={exc.stage} code={exc.code} detail={exc.detail}",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"harness failure: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
