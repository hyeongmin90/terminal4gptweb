"""PTY sandboxing through Anthropic Sandbox Runtime (srt).

With ``sandbox.enabled = false`` the shell is launched directly and none of
the tools below are required. With it enabled, the shell runs as

    srt -s <settings.json> -- script -qfec "<shell argv>" /dev/null

srt applies the filesystem, network and credential policy (bubblewrap +
an egress proxy that swaps masked credential sentinels for the real values).
``script`` gives the shell a controlling terminal inside srt's new session so
job control and Ctrl-C keep working.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import CACHE_DIR, SandboxSettings, TerminalSettings


SRT_INSTALL_HINT = "npm install -g @anthropic-ai/sandbox-runtime"
DEFAULT_SRT_SETTINGS_PATH = CACHE_DIR / "srt-settings.json"

# Host directories hidden in workspace mode. The workspace (and any
# allow_write path) is bound back on top of them by srt.
WORKSPACE_HIDDEN_ROOTS = ("/home", "/root", "/mnt", "/media")


class SandboxUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class ShellLaunch:
    executable: str
    argv: list[str]
    cwd: str


def resolve_srt(sandbox: SandboxSettings) -> str | None:
    if sandbox.srt_path:
        path = Path(sandbox.srt_path).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which("srt")


def sandbox_dependencies(sandbox: SandboxSettings) -> list[tuple[str, str | None]]:
    """Return (name, resolved path or None) for every tool the sandbox needs."""
    return [
        ("srt", resolve_srt(sandbox)),
        ("bwrap", shutil.which("bwrap")),
        ("socat", shutil.which("socat")),
        ("rg", shutil.which("rg")),
        ("script", shutil.which("script")),
    ]


def require_sandbox_dependencies(sandbox: SandboxSettings) -> str:
    deps = sandbox_dependencies(sandbox)
    missing = [name for name, path in deps if path is None]
    if missing:
        lines = [
            "sandbox.enabled = true but required tools are missing: " + ", ".join(missing) + ".",
        ]
        if "srt" in missing:
            where = f" at {sandbox.srt_path}" if sandbox.srt_path else " on PATH"
            lines.append(
                f"Anthropic Sandbox Runtime (srt) was not found{where}. "
                f"Install it with: {SRT_INSTALL_HINT} (requires Node.js 22.12+)."
            )
        system = [name for name in missing if name != "srt"]
        if system:
            packages = {
                "bwrap": "bubblewrap",
                "socat": "socat",
                "rg": "ripgrep",
                "script": "util-linux",
            }
            lines.append(
                "Install system packages with: sudo apt install -y "
                + " ".join(packages[name] for name in system)
            )
        lines.append("Or set sandbox.enabled = false to run the shell without a sandbox.")
        raise SandboxUnavailableError("\n".join(lines))
    srt = deps[0][1]
    assert srt is not None
    return srt


def srt_package_root(srt: str) -> Path:
    """Directory holding srt's package, which srt reads from inside the sandbox.

    The `srt` command is usually a symlink to `<package>/dist/cli.js`; srt
    runs helpers such as `vendor/seccomp/*/apply-seccomp` from that package
    inside the sandbox, so it must stay readable in workspace mode.
    """
    resolved = Path(srt).resolve()
    if resolved.parent.name == "dist":
        return resolved.parent.parent
    return resolved.parent


def workspace_dir(settings: TerminalSettings) -> Path:
    return Path(settings.sandbox.workspace_path or settings.cwd).expanduser().resolve()


def build_srt_settings(
    settings: TerminalSettings,
    *,
    cwd: Path,
    readable_paths: list[Path] | None = None,
) -> dict:
    """Translate the t4g sandbox config into an srt settings document."""
    sandbox = settings.sandbox
    workspace = workspace_dir(settings) if sandbox.workspace else None
    base = workspace if workspace is not None else cwd

    allow_write: list[str] = []
    deny_read: list[str] = []
    allow_read: list[str] = []

    if workspace is not None:
        deny_read.extend(root for root in WORKSPACE_HIDDEN_ROOTS if Path(root).exists())
        allow_read.append(str(workspace))
        allow_read.extend(str(path) for path in readable_paths or [])
        if not sandbox.read_only:
            allow_write.append(str(workspace))
    elif not sandbox.read_only:
        allow_write.append("/")

    allow_read.extend(_absolute(value, base) for value in sandbox.allow_read)

    allow_write.extend(_absolute(value, base) for value in sandbox.allow_write)
    deny_read.extend(_absolute(value, base) for value in sandbox.deny_read)

    document: dict = {
        "network": {
            "allowedDomains": list(sandbox.allowed_domains),
            "deniedDomains": list(sandbox.denied_domains),
        },
        "filesystem": {
            "denyRead": _unique(deny_read),
            "allowRead": _unique(allow_read),
            "allowWrite": _unique(allow_write),
            "denyWrite": _unique(_absolute(value, base) for value in sandbox.deny_write),
        },
    }
    if sandbox.tls_terminate:
        document["network"]["tlsTerminate"] = {}

    files = [
        _credential_rule(
            {"path": _absolute(item.path, base)},
            item,
            mask_duplicates=item.mask_duplicates,
        )
        for item in sandbox.credential_files
    ]
    env_vars = [_credential_rule({"name": item.name}, item) for item in sandbox.credential_env]
    if files or env_vars:
        credentials: dict = {}
        if files:
            credentials["files"] = files
        if env_vars:
            credentials["envVars"] = env_vars
        if sandbox.allow_plaintext_inject:
            credentials["allowPlaintextInject"] = True
        document["credentials"] = credentials
    return document


def build_shell_launch(
    settings: TerminalSettings,
    *,
    cwd: Path,
    shell: Path,
    rcfile: Path | None,
    srt_settings_path: Path | None = None,
) -> ShellLaunch:
    shell_path = str(shell)
    if shell.name == "bash" and rcfile is not None:
        shell_argv = [shell_path, "--rcfile", str(rcfile), "-i"]
    else:
        shell_argv = [shell_path, "-i"]

    sandbox = settings.sandbox
    if not sandbox.enabled:
        return ShellLaunch(executable=shell_path, argv=shell_argv, cwd=str(cwd))

    srt = require_sandbox_dependencies(sandbox)
    script = shutil.which("script")
    assert script is not None

    if sandbox.workspace:
        workspace = workspace_dir(settings)
        if not workspace.is_dir():
            raise FileNotFoundError(f"Sandbox workspace does not exist: {workspace}")
        launch_cwd = workspace
    else:
        launch_cwd = cwd

    readable_paths = [srt_package_root(srt)]
    if rcfile is not None:
        readable_paths.append(rcfile)
    document = build_srt_settings(settings, cwd=cwd, readable_paths=readable_paths)
    settings_path = write_srt_settings(document, srt_settings_path or DEFAULT_SRT_SETTINGS_PATH)

    argv = [
        srt,
        "-s",
        str(settings_path),
        "--",
        script,
        "-qfec",
        shlex.join(shell_argv),
        "/dev/null",
    ]
    return ShellLaunch(executable=srt, argv=argv, cwd=str(launch_cwd))


def write_srt_settings(document: dict, path: Path) -> Path:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def descendant_pids(root: int) -> list[int]:
    """Return every live descendant of ``root`` by walking /proc."""
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        # The command name may contain spaces/parens; ppid follows the last ')'.
        fields = stat[stat.rfind(")") + 2 :].split()
        if len(fields) < 2:
            continue
        children.setdefault(int(fields[1]), []).append(int(entry.name))

    found: list[int] = []
    stack = [root]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def process_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def _credential_rule(
    rule: dict,
    item,
    *,
    mask_duplicates: bool = False,
) -> dict:
    rule["mode"] = item.mode
    if item.mode == "mask":
        if item.extract:
            rule["extract"] = item.extract
            rule["onExtractNoMatch"] = item.on_extract_no_match
            if mask_duplicates:
                rule["maskDuplicates"] = True
        if item.inject_hosts == []:
            raise ValueError(
                "SRT does not support mode='mask' with an empty injectHosts list; "
                "use mode='deny', omit inject_hosts, or specify at least one host."
            )
        if item.inject_hosts is not None:
            rule["injectHosts"] = list(item.inject_hosts)
    return rule


def _absolute(value: str, base: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return os.path.normpath(path)


def _unique(values) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
