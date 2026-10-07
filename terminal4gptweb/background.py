from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TextIO

from .config import CACHE_DIR, DEFAULT_CONFIG_PATH, load_config


PID_FILE = CACHE_DIR / "daemon.pid"
LOG_FILE = CACHE_DIR / "daemon.log"
LOCK_FILE = CACHE_DIR / "instance.lock"

# Releases before the rename kept runtime state under the old project name.
# A daemon started by one of them still holds this lock and PID file, so honour
# both: otherwise an upgrade could start a second daemon on the same pages and
# `t4g daemon stop` could not find the old one.
LEGACY_CACHE_DIR = Path.home() / ".cache" / "notion_is_terminal"
LEGACY_PID_FILE = LEGACY_CACHE_DIR / "daemon.pid"
LEGACY_LOCK_FILE = LEGACY_CACHE_DIR / "instance.lock"


class InstanceLock:
    def __init__(self) -> None:
        self._streams: list[TextIO] = []

    def __enter__(self) -> "InstanceLock":
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stream = _acquire_lock(LOCK_FILE)
        stream.seek(0)
        stream.truncate()
        stream.write(str(os.getpid()))
        stream.flush()
        self._streams.append(stream)

        if LEGACY_LOCK_FILE.exists():
            try:
                self._streams.append(_acquire_lock(LEGACY_LOCK_FILE))
            except RuntimeError:
                self.__exit__()
                raise
        return self

    def __exit__(self, *exc_info: object) -> None:
        while self._streams:
            stream = self._streams.pop()
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()


def _acquire_lock(path: Path) -> TextIO:
    stream = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise RuntimeError(
            "another Terminal4GPTWeb session is already running "
            "(foreground or daemon)"
        )
    return stream


def start_daemon(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    config_path = Path(config_path).expanduser().resolve()
    load_config(config_path)

    existing = read_pid()
    if existing and process_is_our_daemon(existing):
        print(f"Terminal4GPTWeb daemon is already running (pid {existing}).")
        return 0
    if existing:
        _remove_pid_file()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_FILE.open("ab", buffering=0)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["T4G_DAEMON_MODE"] = "1"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "terminal4gptweb",
            "run",
            "--config",
            str(config_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
        env=env,
    )
    log.close()

    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    try:
        PID_FILE.chmod(0o600)
    except OSError:
        pass

    time.sleep(0.15)
    if process.poll() is not None:
        _remove_pid_file()
        print(f"daemon failed to start; check {LOG_FILE}", file=sys.stderr)
        return process.returncode or 1

    print(f"started Terminal4GPTWeb daemon (pid {process.pid})")
    print(f"log: {LOG_FILE}")
    return 0


def stop_daemon(*, timeout: float = 5.0) -> int:
    pid = read_pid()
    if not pid:
        print("Terminal4GPTWeb daemon is not running.")
        return 0

    if not process_is_our_daemon(pid):
        _remove_pid_file()
        print("removed stale daemon pid file.")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _remove_pid_file()
        print("Terminal4GPTWeb daemon is not running.")
        return 0

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_exists(pid):
            _remove_pid_file()
            print("stopped Terminal4GPTWeb daemon.")
            return 0
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    for _ in range(20):
        if not process_exists(pid):
            break
        time.sleep(0.05)

    _remove_pid_file()
    print("stopped Terminal4GPTWeb daemon (forced).")
    return 0


def restart_daemon(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    code = stop_daemon()
    if code != 0:
        return code
    return start_daemon(config_path)


def daemon_status(config_path: Path | str = DEFAULT_CONFIG_PATH) -> int:
    pid = read_pid()
    if not pid or not process_is_our_daemon(pid):
        if pid:
            _remove_pid_file()
        print("Terminal4GPTWeb daemon: stopped")
        return 1

    print(f"Terminal4GPTWeb daemon: running (pid {pid})")
    try:
        config = load_config(config_path)
        if config.notion.page_url:
            print(f"Notion: {config.notion.page_url}")
    except Exception:
        pass
    print(f"log: {LOG_FILE}")
    return 0


def show_logs(*, lines: int = 100, follow: bool = False) -> int:
    if not LOG_FILE.exists():
        print(f"no daemon log yet: {LOG_FILE}")
        return 0

    if not follow:
        for line in _tail_lines(LOG_FILE, lines):
            print(line, end="")
        return 0

    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as stream:
        stream.seek(0, os.SEEK_END)
        try:
            while True:
                line = stream.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.25)
        except KeyboardInterrupt:
            return 0


def read_pid() -> int | None:
    for path in (PID_FILE, LEGACY_PID_FILE):
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError, OSError):
            continue
    return None


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_is_our_daemon(pid: int) -> bool:
    if not process_exists(pid):
        return False

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        # A stale PID file may now point at an unrelated process. If /proc
        # cannot prove ownership, fail closed and never signal that PID.
        return False

    # notion_is_terminal is the module name of daemons started before the
    # package rename; they may still be running after an in-place upgrade.
    return (
        (" terminal4gptweb " in f" {cmdline} " or " notion_is_terminal " in f" {cmdline} ")
        and " run " in f" {cmdline} "
    )


def _remove_pid_file() -> None:
    for path in (PID_FILE, LEGACY_PID_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _tail_lines(path: Path, count: int) -> list[str]:
    if count <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        data = stream.readlines()
    return data[-count:]
