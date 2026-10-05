from __future__ import annotations

import getpass
import os
import shutil
from pathlib import Path

from .config import (
    AppConfig,
    BrowserSettings,
    DEFAULT_CONFIG_PATH,
    NotionSettings,
    SandboxSettings,
    TerminalPageSettings,
    TerminalSettings,
    load_config,
    write_config,
)
from .notion import NotionClient, parse_page_id
from .sandbox import SRT_INSTALL_HINT, sandbox_dependencies


def run_init(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    print("Terminal4GPTWeb setup")
    print(
        "Creates a compact live control page, a separate Help page, and a "
        "Playwright Vision payload page.\n"
    )

    token = getpass.getpass("Notion API token (PAT or internal connection token): ").strip()
    if not token:
        raise ValueError("Notion API token is required.")

    with NotionClient(token) as notion:
        parent_page_id = _choose_parent_page(notion)
    shell = _prompt("Shell", shutil.which("bash") or "/bin/bash")
    cwd = str(Path(_prompt("Initial working directory", str(Path.home()))).expanduser().resolve())
    sandbox = _prompt_sandbox(cwd)
    user = _prompt("Prompt user", os.environ.get("USER", "user"))
    host = _prompt("Prompt host", "ubuntu")
    columns = int(_prompt("Terminal columns", "120"))
    rows = int(_prompt("Terminal rows", "60"))
    poll_interval = float(_prompt("Input poll interval (seconds)", "1.2"))
    refresh_interval = float(_prompt("Screen refresh interval (seconds)", "1.5"))
    count = int(_prompt("Terminal count", "1"))
    if count < 1 or count > 16:
        raise ValueError("Terminal count must be between 1 and 16.")
    base_title = _prompt("Base Notion page title", "Terminal4GPTWeb")
    names = _prompt_terminal_names(count, base_title)

    terminal = TerminalSettings(
        shell=shell,
        cwd=cwd,
        user=user,
        host=host,
        count=count,
        names=names,
        names_explicit=True,
        input_prompt="",
        columns=columns,
        rows=rows,
        poll_interval=poll_interval,
        refresh_interval=refresh_interval,
        health_check_interval=10.0,
        show_cursor=True,
        source_bashrc=True,
        sandbox=sandbox,
    )
    browser = BrowserSettings()

    config = _create_notion_surfaces(
        token=token,
        parent_page_id=parent_page_id,
        terminal=terminal,
        browser=browser,
    )
    _print_init_result(config, config_path, reinitialized=False)
    return config


def run_reinit(config_path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    print("Terminal4GPTWeb reinitialize")
    print("Recreates deleted Notion pages while preserving local terminal/browser settings.\n")

    current = load_config(config_path)
    parent_page_id = current.notion.parent_page_id.strip()
    if not parent_page_id:
        with NotionClient(current.notion.token) as notion:
            parent_page_id = _choose_parent_page(notion)

    config = _create_notion_surfaces(
        token=current.notion.token,
        parent_page_id=parent_page_id,
        terminal=current.terminal,
        browser=current.browser,
    )
    _print_init_result(config, config_path, reinitialized=True)
    return config


def _choose_parent_page(notion: NotionClient) -> str:
    print("\nChoose parent Notion page")
    print("  1. Search pages")
    print("  2. Enter URL / page ID")

    while True:
        choice = _prompt("Select", "1").strip()
        if choice == "1":
            break
        if choice == "2":
            return _enter_parent_page()
        print("Invalid selection. Choose 1 or 2.")

    while True:
        query = input("\nSearch page title (blank = recent pages): ").strip()
        pages = notion.search_pages(query, limit=10)

        if not pages:
            print("No accessible pages found.")
        else:
            print("")
            for index, page in enumerate(pages, start=1):
                print(f"  {index}. {page.title}")
                if page.url:
                    print(f"     {page.url}")

        print("\n  r. Search again")
        print("  u. Enter URL / page ID")
        selected = input("Select page: ").strip().lower()

        if selected == "r":
            continue
        if selected == "u":
            return _enter_parent_page()
        if selected.isdigit():
            index = int(selected)
            if 1 <= index <= len(pages):
                return pages[index - 1].page_id

        print("Invalid selection. Choose a page number, r, or u.")


def _enter_parent_page() -> str:
    value = input("Parent Notion page URL or page ID: ").strip()
    return parse_page_id(value)


DEFAULT_ALLOWED_DOMAINS = (
    "github.com",
    "*.github.com",
    "*.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
)


def _prompt_sandbox(cwd: str) -> SandboxSettings:
    print("\nPTY sandbox (Anthropic Sandbox Runtime / srt)")
    print("Disabled: the shell runs with your full user permissions and srt is not needed.")
    enabled = _prompt_bool("Enable sandbox", False)
    if not enabled:
        return SandboxSettings(enabled=False)

    sandbox = SandboxSettings(enabled=True)
    missing = [name for name, path in sandbox_dependencies(sandbox) if path is None]
    if missing:
        print(f"  Warning: missing tools: {', '.join(missing)}.")
        if "srt" in missing:
            print(f"  Install srt with: {SRT_INSTALL_HINT}")
        print("  The daemon will refuse to start until they are installed (see: t4g doctor).")

    sandbox.read_only = _prompt_bool("Read-only filesystem", False)
    sandbox.workspace = _prompt_bool("Restrict filesystem to one workspace", False)
    if sandbox.workspace:
        sandbox.workspace_path = str(
            Path(_prompt("Workspace path", cwd)).expanduser().resolve()
        )
        if sandbox.read_only:
            print("  Workspace will be visible but read-only.")
        else:
            print("  Workspace will be visible read/write.")

    sandbox.allow_write = _prompt_path_list(
        "Extra writable paths (comma-separated, optional, e.g. ~/.cache)",
    )
    sandbox.deny_read = _prompt_path_list(
        "Deny read paths (comma-separated, optional)",
    )
    sandbox.deny_write = _prompt_path_list(
        "Deny write paths (comma-separated, optional)",
    )
    domains = _prompt(
        "Allowed network domains (comma-separated, '-' = no network)",
        ",".join(DEFAULT_ALLOWED_DOMAINS),
    )
    if domains.strip() != "-":
        sandbox.allowed_domains = [part.strip() for part in domains.split(",") if part.strip()]
    print("  Add credential masking rules ([[sandbox.credentials.*]]) in config.toml after setup.")
    return sandbox


def _prompt_bool(label: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "true", "1"}:
            return True
        if value in {"n", "no", "false", "0"}:
            return False
        print("Please enter y or n.")

def _prompt_path_list(label: str) -> list[str]:
    value = input(f"{label}: ").strip()
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _create_notion_surfaces(
    *,
    token: str,
    parent_page_id: str,
    terminal: TerminalSettings,
    browser: BrowserSettings,
) -> AppConfig:
    print("\nChecking Notion access and creating pages...")
    with NotionClient(token) as notion:
        notion.get_page(parent_page_id)
        created_pages = [
            notion.create_terminal_page(
                parent_page_id=parent_page_id,
                title=name,
                terminal_text=(
                    f"Terminal4GPTWeb · {name}\n\n"
                    "Local PTY is not connected yet. Run: t4g daemon start"
                ),
                input_text=terminal.input_prompt,
            )
            for name in terminal.names
        ]
        created = created_pages[0]
        help_page = notion.create_help_page(parent_page_id=created.page_id)
        vision_page = notion.ensure_browser_vision_page(
            parent_page_id=created.page_id,
            page_id="",
            block_id="",
            idle_text=(
                "status: idle\n"
                "mime: image/jpeg\n"
                "encoding: base64\n"
                "data_base64:\n"
            ),
        )
        browser_blocks = notion.ensure_browser_blocks(
            page_id=created.page_id,
            status_block_id="",
            image_block_id="",
            status_text=(
                "status: idle\n"
                "browser: not started\n"
                f"viewport: {browser.width}x{browser.height}\n"
                f"vision_page_url: {vision_page.page_url}\n"
                "hint: :b goto <url> or :b shot\n"
            ),
        )

    terminal_pages = [
        TerminalPageSettings(
            page_id=page.page_id,
            terminal_block_id=page.terminal_block_id,
            input_block_id=page.input_block_id,
            page_url=page.page_url,
        )
        for page in created_pages
    ]

    return AppConfig(
        notion=NotionSettings(
            token=token,
            page_id=created.page_id,
            terminal_block_id=created.terminal_block_id,
            input_block_id=created.input_block_id,
            page_url=created.page_url,
            parent_page_id=parent_page_id,
            help_page_id=help_page.page_id,
            help_page_url=help_page.page_url,
            browser_status_block_id=browser_blocks.status_block_id,
            browser_image_block_id=browser_blocks.image_block_id,
            browser_vision_page_id=vision_page.page_id,
            browser_vision_block_id=vision_page.block_id,
            browser_vision_page_url=vision_page.page_url,
            terminal_pages=terminal_pages,
        ),
        terminal=terminal,
        browser=browser,
    )


def _prompt_terminal_names(count: int, base_title: str) -> list[str]:
    defaults = (
        [base_title]
        if count == 1
        else [f"{base_title} {index}" for index in range(1, count + 1)]
    )
    names: list[str] = []
    for index, default in enumerate(defaults, start=1):
        names.append(_prompt(f"Terminal {index} page name", default))
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Terminal page names must be unique.")
    return names


def _print_init_result(
    config: AppConfig,
    config_path: Path | str,
    *,
    reinitialized: bool,
) -> None:
    written = write_config(config, config_path)

    print("\n✓ Notion connection verified")
    print(f"✓ {config.terminal.count} Terminal / Input control page(s) created")
    print("✓ Terminal4GPTWeb Help child page created")
    print("✓ Browser Status / Browser Screenshot surface created")
    print("✓ Browser Vision Payload child page created")
    print("✓ Runtime block self-healing enabled")
    print(f"✓ Config written: {written}")
    if config.notion.terminal_pages:
        print("\nTerminal pages:")
        for index, page in enumerate(config.notion.terminal_pages[: config.terminal.count]):
            name = config.terminal.names[index]
            print(f"  {index + 1}. {name}: {page.page_url or page.page_id}")
    if config.notion.help_page_url:
        print(f"Help: {config.notion.help_page_url}")

    if reinitialized:
        print("\nNotion pages were recreated. Restart the daemon to load the new IDs:")
        print("  t4g daemon restart")
    else:
        print("\nStart in background with:")
        print("  t4g daemon start")
        print("\nOr run in foreground with:")
        print("  t4g run")


def _prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default
