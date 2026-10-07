from __future__ import annotations

import codecs
import errno
import fcntl
import os
import pty
import re
import shlex
import signal
import struct
import termios
from pathlib import Path
from urllib.parse import unquote

import pyte

from .config import CACHE_DIR, TerminalSettings
from .sandbox import build_shell_launch, descendant_pids, process_name


# The kernel tty input queue holds 4096 bytes. A larger write to the
# non-blocking PTY master fails part-way and leaves a truncated line queued
# in front of the next command, so reject oversized input before writing.
MAX_INPUT_BYTES = 4000

OSC7_RE = re.compile(r"\x1b]7;file://[^/]*(/[^\x07\x1b]*)\x07")

KEYS: dict[str, bytes] = {
    "UP": b"\x1b[A",
    "DOWN": b"\x1b[B",
    "RIGHT": b"\x1b[C",
    "LEFT": b"\x1b[D",
    "HOME": b"\x1b[H",
    "END": b"\x1b[F",
    "PAGEUP": b"\x1b[5~",
    "PAGEDOWN": b"\x1b[6~",
    "INSERT": b"\x1b[2~",
    "DELETE": b"\x1b[3~",
    "TAB": b"\t",
    "ENTER": b"\r",
    "ESC": b"\x1b",
    "ESCAPE": b"\x1b",
    "BACKSPACE": b"\x7f",
    "F1": b"\x1bOP",
    "F2": b"\x1bOQ",
    "F3": b"\x1bOR",
    "F4": b"\x1bOS",
    "F5": b"\x1b[15~",
    "F6": b"\x1b[17~",
    "F7": b"\x1b[18~",
    "F8": b"\x1b[19~",
    "F9": b"\x1b[20~",
    "F10": b"\x1b[21~",
    "F11": b"\x1b[23~",
    "F12": b"\x1b[24~",
}


class InputTooLargeError(ValueError):
    pass


class PTYSession:
    """Persistent PTY-backed shell plus a text-mode terminal emulator."""

    def __init__(self, settings: TerminalSettings) -> None:
        self.settings = settings
        self.pid: int | None = None
        self.master_fd: int | None = None
        self.screen = pyte.Screen(settings.columns, settings.rows)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.current_cwd = str(Path(settings.cwd).expanduser().resolve())
        self._osc_buffer = ""
        self._rcfile: Path | None = None
        self._closed = False

    def start(self) -> None:
        if self.pid is not None:
            raise RuntimeError("PTY session is already running")

        cwd = Path(self.settings.cwd).expanduser().resolve()
        if not cwd.is_dir():
            raise FileNotFoundError(f"Working directory does not exist: {cwd}")

        shell = Path(self.settings.shell).expanduser()
        if not shell.exists():
            raise FileNotFoundError(f"Shell does not exist: {shell}")

        if shell.name == "bash":
            self._rcfile = self._write_bash_rcfile()

        launch = build_shell_launch(
            self.settings,
            cwd=cwd,
            shell=shell,
            rcfile=self._rcfile,
        )
        self.current_cwd = launch.cwd

        pid, master_fd = pty.fork()
        if pid == 0:
            os.chdir(launch.cwd)
            # Size the PTY before exec so a sandboxed `script` copies the
            # right dimensions onto its inner terminal at startup.
            winsize = struct.pack("HHHH", self.settings.rows, self.settings.columns, 0, 0)
            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env.setdefault("COLORTERM", "truecolor")
            env["COLUMNS"] = str(self.settings.columns)
            env["LINES"] = str(self.settings.rows)

            os.execvpe(launch.executable, launch.argv, env)
            raise SystemExit(127)

        self.pid = pid
        self.master_fd = master_fd
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.resize(self.settings.columns, self.settings.rows)

    def fileno(self) -> int:
        if self.master_fd is None:
            raise RuntimeError("PTY session is not running")
        return self.master_fd

    def read_ready(self) -> bool:
        if self.master_fd is None:
            return False
        changed = False
        while True:
            try:
                chunk = os.read(self.master_fd, 65536)
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            changed = True
            text = self.decoder.decode(chunk)
            if text:
                self._capture_cwd(text)
                self.stream.feed(text)
        return changed

    def send_text(self, text: str) -> None:
        self.send_bytes(text.encode("utf-8"))

    def send_line(self, text: str) -> None:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.send_text(normalized.replace("\n", "\r") + "\r")

    def send_bytes(self, data: bytes) -> None:
        if len(data) > MAX_INPUT_BYTES:
            raise InputTooLargeError(
                f"Input not sent: {len(data)} bytes exceeds the {MAX_INPUT_BYTES}-byte "
                "limit (UTF-8). Split it into smaller submissions."
            )
        if not self.is_alive() or self.master_fd is None:
            raise RuntimeError("Shell session is not running")
        view = memoryview(data)
        while view:
            written = os.write(self.master_fd, view)
            view = view[written:]

    def send_control(self, key: str) -> None:
        normalized = key.strip().upper()
        if normalized in {"\\", "BACKSLASH"}:
            self.send_bytes(b"\x1c")
            return
        if len(normalized) != 1 or not ("@" <= normalized <= "_"):
            raise ValueError(f"Unsupported Ctrl key: {key}")
        self.send_bytes(bytes([ord(normalized) & 0x1F]))

    def send_key(self, key: str) -> None:
        normalized = key.strip().upper().replace("_", "")
        aliases = {
            "PGUP": "PAGEUP",
            "PGDN": "PAGEDOWN",
            "DEL": "DELETE",
            "INS": "INSERT",
            "RETURN": "ENTER",
            "RET": "ENTER",
            "ENT": "ENTER",
            "BS": "BACKSPACE",
            "BKSP": "BACKSPACE",
        }
        normalized = aliases.get(normalized, normalized)
        data = KEYS.get(normalized)
        if data is None:
            raise ValueError(f"Unsupported key: {key}")
        self.send_bytes(data)

    def show_notice(self, text: str) -> None:
        """Print a daemon message on the rendered screen without involving the shell."""
        self.stream.feed("\r\n" + text.replace("\n", "\r\n") + "\r\n")

    def resize(self, columns: int, rows: int) -> None:
        if not (20 <= columns <= 400 and 5 <= rows <= 200):
            raise ValueError("Terminal size must be within 20..400 columns and 5..200 rows")
        self.settings.columns = columns
        self.settings.rows = rows
        self.screen.resize(lines=rows, columns=columns)
        if self.master_fd is not None:
            winsize = struct.pack("HHHH", rows, columns, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            if self.pid and self.is_alive():
                self._signal_winch()

    def render(self) -> str:
        lines = list(self.screen.display)
        if self.settings.show_cursor and self.screen.cursor and 0 <= self.screen.cursor.y < len(lines):
            y = self.screen.cursor.y
            x = min(max(self.screen.cursor.x, 0), max(self.settings.columns - 1, 0))
            line = lines[y]
            if len(line) < self.settings.columns:
                line = line.ljust(self.settings.columns)
            lines[y] = line[:x] + "▌" + line[x + 1 :]
        return "\n".join(line.rstrip() for line in lines).rstrip("\n")

    def prompt(self) -> str:
        return f"{self.settings.user}@{self.settings.host}:{self.current_cwd}$ "

    def is_alive(self) -> bool:
        if self.pid is None:
            return False
        try:
            waited, _status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return False
        return waited == 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.pid is not None and self.is_alive():
            try:
                os.kill(self.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
        self.pid = None

    def _signal_winch(self) -> None:
        assert self.pid is not None
        targets = [self.pid]
        if self.settings.sandbox.enabled:
            # srt runs the shell in a new session, so the kernel's SIGWINCH
            # never reaches it. `script` relays the new size to the inner PTY.
            targets.extend(
                pid for pid in descendant_pids(self.pid) if process_name(pid) == "script"
            )
        for pid in targets:
            try:
                os.kill(pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass

    def _capture_cwd(self, text: str) -> None:
        self._osc_buffer = (self._osc_buffer + text)[-8192:]
        matches = list(OSC7_RE.finditer(self._osc_buffer))
        if matches:
            path = unquote(matches[-1].group(1))
            if path:
                self.current_cwd = path
            self._osc_buffer = self._osc_buffer[-1024:]

    def _write_bash_rcfile(self) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        rcfile = CACHE_DIR / "bashrc"

        lines: list[str] = []
        if self.settings.source_bashrc:
            lines.extend([
                'if [ -f "$HOME/.bashrc" ]; then',
                '  . "$HOME/.bashrc"',
                "fi",
            ])

        prompt = f"{self.settings.user}@{self.settings.host}:\\w\\$ "
        lines.extend([
            "__t4g_emit_cwd() {",
            "  printf '\\033]7;file://localhost%s\\007' \"$PWD\"",
            "}",
            'if [ -n "${PROMPT_COMMAND-}" ]; then',
            '  PROMPT_COMMAND="__t4g_emit_cwd;${PROMPT_COMMAND}"',
            "else",
            '  PROMPT_COMMAND="__t4g_emit_cwd"',
            "fi",
            f"PS1={shlex.quote(prompt)}",
            "export PS1 PROMPT_COMMAND",
            "",
        ])
        rcfile.write_text("\n".join(lines), encoding="utf-8")
        try:
            rcfile.chmod(0o600)
        except OSError:
            pass
        return rcfile
