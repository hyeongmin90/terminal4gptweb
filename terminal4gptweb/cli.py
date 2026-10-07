from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .background import (
    InstanceLock,
    daemon_status,
    restart_daemon,
    show_logs,
    start_daemon,
    stop_daemon,
)
from .config import DEFAULT_CONFIG_PATH, load_config
from .daemon import TerminalDaemon
from .notion import NotionClient, NotionError
from .sandbox import SRT_INSTALL_HINT, sandbox_dependencies
from .wizard import run_init, run_reinit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="t4g",
        description="Bridge GPT Web to local terminal and Playwright browser tools through Notion.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init", "reinit", "run", "doctor"):
        command = sub.add_parser(name)
        command.add_argument(
            "--config",
            type=Path,
            default=DEFAULT_CONFIG_PATH,
            help=f"Config path (default: {DEFAULT_CONFIG_PATH})",
        )

    daemon = sub.add_parser("daemon", help="Manage the detached background daemon.")
    daemon.add_argument(
        "action",
        choices=("start", "stop", "restart", "status", "logs"),
        help="Daemon lifecycle action.",
    )
    daemon.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Config path (default: {DEFAULT_CONFIG_PATH})",
    )
    daemon.add_argument(
        "-n",
        "--lines",
        type=int,
        default=100,
        help="Number of lines for 'daemon logs' (default: 100).",
    )
    daemon.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow daemon logs until Ctrl-C.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            run_init(args.config)
            return 0

        if args.command == "reinit":
            run_reinit(args.config)
            return 0

        if args.command == "run":
            config = load_config(args.config)
            with InstanceLock():
                print(f"Terminal4GPTWeb {__version__}")
                pages = config.notion.terminal_pages[: config.terminal.count]
                if pages:
                    print("Notion terminal pages:")
                    for index, page in enumerate(pages):
                        print(
                            f"  {index + 1}. {config.terminal.names[index]}: "
                            f"{page.page_url or page.page_id}"
                        )
                print(
                    f"Starting {config.terminal.count} persistent PTY session(s) in foreground. "
                    "Press Ctrl-C here to stop."
                )
                TerminalDaemon(config, config_path=args.config).run()
            return 0

        if args.command == "doctor":
            return doctor(args.config)

        if args.command == "daemon":
            if args.action == "start":
                return start_daemon(args.config)
            if args.action == "stop":
                return stop_daemon()
            if args.action == "restart":
                return restart_daemon(args.config)
            if args.action == "status":
                return daemon_status(args.config)
            if args.action == "logs":
                return show_logs(lines=args.lines, follow=args.follow)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


def doctor(config_path: Path) -> int:
    checks: list[tuple[bool, str]] = []
    try:
        config = load_config(config_path)
        checks.append((True, f"Config loaded: {config_path.expanduser()}"))
    except Exception as exc:
        print(f"✗ Config: {exc}")
        return 1

    checks.append((sys.platform.startswith("linux"), f"Linux/WSL platform: {platform.platform()}"))
    checks.append((Path(config.terminal.shell).exists(), f"Shell exists: {config.terminal.shell}"))
    checks.append((Path(config.terminal.cwd).expanduser().is_dir(), f"Working directory exists: {config.terminal.cwd}"))
    checks.append((os.access(Path(config.terminal.cwd).expanduser(), os.R_OK | os.X_OK), "Working directory is accessible"))

    sandbox = config.terminal.sandbox
    if not sandbox.enabled:
        checks.append((True, "PTY sandbox: disabled (shell runs unrestricted; srt not required)"))
    else:
        checks.append((
            True,
            "PTY sandbox: enabled via srt "
            f"(read_only={str(sandbox.read_only).lower()}, "
            f"workspace={str(sandbox.workspace).lower()}, effective={sandbox.mode})",
        ))
        checks.append((
            True,
            f"Network allowlist: {', '.join(sandbox.allowed_domains) or 'none (all network blocked)'}",
        ))
        checks.append((
            True,
            "Credential rules: "
            f"{len(sandbox.credential_files)} file(s), {len(sandbox.credential_env)} env var(s)",
        ))
        dependencies = sandbox_dependencies(sandbox)
        for name, path in dependencies:
            hint = ""
            if path is None:
                hint = f" — install: {SRT_INSTALL_HINT}" if name == "srt" else ""
            checks.append((path is not None, f"{name} is installed: {path or 'not found'}{hint}"))
        if sandbox.workspace:
            workspace = Path(sandbox.workspace_path or config.terminal.cwd).expanduser()
            checks.append((workspace.is_dir(), f"Sandbox workspace exists: {workspace}"))
        if all(path is not None for _name, path in dependencies):
            checks.append(_sandbox_smoke_test(config))
    try:
        import playwright  # noqa: F401
        checks.append((True, "Playwright Python package is installed"))
    except ImportError:
        checks.append((False, "Playwright package missing: pip install -e ."))

    try:
        with NotionClient(config.notion.token, api_version=config.notion.api_version) as notion:
            pages = config.notion.terminal_pages[: config.terminal.count]
            for index, page in enumerate(pages):
                notion.get_page(page.page_id)
                terminal = notion.get_block(page.terminal_block_id)
                input_block = notion.get_block(page.input_block_id)
                label = config.terminal.names[index]
                checks.append((
                    terminal.get("type") == "code" and not terminal.get("archived", False),
                    f"Terminal block is active: {label}",
                ))
                checks.append((
                    input_block.get("type") == "code" and not input_block.get("archived", False),
                    f"Input block is active: {label}",
                ))

            if len(pages) < config.terminal.count:
                checks.append((
                    True,
                    f"{config.terminal.count - len(pages)} terminal page(s) will be created on next daemon start",
                ))

            browser_status = (
                notion.get_block(config.notion.browser_status_block_id)
                if config.notion.browser_status_block_id
                else None
            )
        if browser_status is not None:
            checks.append((browser_status.get("type") == "code" and not browser_status.get("archived", False), "Browser Status block is active on the first terminal page"))
        else:
            checks.append((True, "Browser Status will be created on the first terminal page on next daemon start"))
        checks.append((True, f"{len(pages)} configured Notion terminal page(s) are readable"))
    except NotionError as exc:
        checks.append((False, f"Notion access: {exc}"))

    failed = False
    for ok, message in checks:
        print(("✓" if ok else "✗") + " " + message)
        failed |= not ok
    return 1 if failed else 0


def _sandbox_smoke_test(config) -> tuple[bool, str]:
    """Run `true` through srt with the configured policy."""
    from .sandbox import (
        build_srt_settings,
        require_sandbox_dependencies,
        srt_package_root,
        workspace_dir,
        write_srt_settings,
    )

    terminal = config.terminal
    cwd = Path(terminal.cwd).expanduser().resolve()
    run_cwd = workspace_dir(terminal) if terminal.sandbox.workspace else cwd
    try:
        srt = require_sandbox_dependencies(terminal.sandbox)
        with tempfile.TemporaryDirectory(prefix="t4g-doctor-") as tmp:
            settings_path = write_srt_settings(
                build_srt_settings(
                    terminal,
                    cwd=cwd,
                    readable_paths=[srt_package_root(srt)],
                ),
                Path(tmp) / "srt-settings.json",
            )
            result = subprocess.run(
                [srt, "-s", str(settings_path), "-c", "true"],
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
    except Exception as exc:
        return False, f"srt sandbox smoke test: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return False, "srt sandbox smoke test failed: " + (detail[0] if detail else f"exit {result.returncode}")
    return True, "srt sandbox smoke test passed"


if __name__ == "__main__":
    raise SystemExit(main())
