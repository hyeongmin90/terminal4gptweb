from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "t4g" / "config.toml"


@dataclass(slots=True)
class TerminalPageSettings:
    page_id: str
    terminal_block_id: str
    input_block_id: str
    page_url: str = ""


@dataclass(slots=True)
class NotionSettings:
    token: str
    page_id: str
    terminal_block_id: str
    input_block_id: str
    page_url: str = ""
    parent_page_id: str = ""
    help_page_id: str = ""
    help_page_url: str = ""
    api_version: str = "2026-03-11"
    browser_status_block_id: str = ""
    browser_image_block_id: str = ""
    browser_vision_page_id: str = ""
    browser_vision_block_id: str = ""
    browser_vision_page_url: str = ""
    terminal_pages: list[TerminalPageSettings] = field(default_factory=list)


@dataclass(slots=True)
class CredentialFileSettings:
    path: str
    mode: str = "mask"
    extract: str = ""
    on_extract_no_match: str = "warn"
    mask_duplicates: bool = False
    inject_hosts: list[str] | None = None


@dataclass(slots=True)
class CredentialEnvSettings:
    name: str
    mode: str = "mask"
    extract: str = ""
    on_extract_no_match: str = "warn"
    inject_hosts: list[str] | None = None


@dataclass(slots=True)
class SandboxSettings:
    """PTY sandbox policy, enforced by Anthropic Sandbox Runtime (srt).

    When ``enabled`` is false the shell runs directly and srt is not needed.
    """

    enabled: bool = False
    srt_path: str = ""
    read_only: bool = False
    workspace: bool = False
    workspace_path: str = ""
    allow_read: list[str] = field(default_factory=list)
    allow_write: list[str] = field(default_factory=list)
    deny_read: list[str] = field(default_factory=list)
    deny_write: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    denied_domains: list[str] = field(default_factory=list)
    tls_terminate: bool = False
    allow_plaintext_inject: bool = False
    credential_files: list[CredentialFileSettings] = field(default_factory=list)
    credential_env: list[CredentialEnvSettings] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.enabled

    @property
    def mode(self) -> str:
        """Human-readable effective mode for diagnostics."""
        if not self.enabled:
            return "none"
        if self.workspace and self.read_only:
            return "workspace_read_only"
        if self.workspace:
            return "workspace"
        if self.read_only:
            return "read_only"
        return "host"


@dataclass(slots=True)
class TerminalSettings:
    shell: str = "/bin/bash"
    cwd: str = str(Path.home())
    user: str = os.environ.get("USER", "user")
    host: str = "ubuntu"
    count: int = 1
    names: list[str] = field(default_factory=lambda: ["Terminal4GPTWeb"])
    names_explicit: bool = False
    input_prompt: str = ""
    columns: int = 120
    rows: int = 60
    poll_interval: float = 1.2
    refresh_interval: float = 1.5
    health_check_interval: float = 10.0
    show_cursor: bool = True
    source_bashrc: bool = True
    sandbox: SandboxSettings = field(default_factory=SandboxSettings)


@dataclass(slots=True)
class BrowserSettings:
    width: int = 1280
    height: int = 720
    headless: bool = True
    timeout_ms: int = 15000
    settle_ms: int = 350
    show_cursor_overlay: bool = True
    vision_enabled: bool = True
    vision_quality: int = 35
    vision_max_base64_chars: int = 160000


@dataclass(slots=True)
class AppConfig:
    notion: NotionSettings
    terminal: TerminalSettings
    browser: BrowserSettings = field(default_factory=BrowserSettings)


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path).expanduser()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    notion_raw = raw.get("notion", {})
    terminal_raw = raw.get("terminal", {})
    sandbox_raw = raw.get("sandbox", {})
    browser_raw = raw.get("browser", {})

    token = os.environ.get("NOTION_TOKEN") or notion_raw.get("token", "")
    if not token:
        raise ValueError("Notion token is missing from config and NOTION_TOKEN is not set.")

    count = int(terminal_raw.get("count", 1))
    names = _terminal_names(count, terminal_raw.get("names", []))

    terminal_pages_raw = notion_raw.get("terminals", [])
    terminal_pages: list[TerminalPageSettings] = []
    if isinstance(terminal_pages_raw, list):
        for item in terminal_pages_raw:
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id", "")).strip()
            terminal_block_id = str(item.get("terminal_block_id", "")).strip()
            input_block_id = str(item.get("input_block_id", "")).strip()
            if not (page_id and terminal_block_id and input_block_id):
                continue
            terminal_pages.append(
                TerminalPageSettings(
                    page_id=page_id,
                    terminal_block_id=terminal_block_id,
                    input_block_id=input_block_id,
                    page_url=str(item.get("page_url", "")),
                )
            )

    if terminal_pages:
        primary = terminal_pages[0]
    else:
        primary = TerminalPageSettings(
            page_id=_required(notion_raw, "page_id"),
            terminal_block_id=_required(notion_raw, "terminal_block_id"),
            input_block_id=_required(notion_raw, "input_block_id"),
            page_url=str(notion_raw.get("page_url", "")),
        )
        terminal_pages.append(primary)

    notion = NotionSettings(
        token=token,
        page_id=primary.page_id,
        terminal_block_id=primary.terminal_block_id,
        input_block_id=primary.input_block_id,
        page_url=primary.page_url,
        parent_page_id=str(notion_raw.get("parent_page_id", "")),
        help_page_id=str(notion_raw.get("help_page_id", "")),
        help_page_url=str(notion_raw.get("help_page_url", "")),
        api_version=notion_raw.get("api_version", "2026-03-11"),
        browser_status_block_id=str(notion_raw.get("browser_status_block_id", "")),
        browser_image_block_id=str(notion_raw.get("browser_image_block_id", "")),
        browser_vision_page_id=str(notion_raw.get("browser_vision_page_id", "")),
        browser_vision_block_id=str(notion_raw.get("browser_vision_block_id", "")),
        browser_vision_page_url=str(notion_raw.get("browser_vision_page_url", "")),
        terminal_pages=terminal_pages,
    )

    sandbox = _load_sandbox(sandbox_raw)

    input_prompt = str(terminal_raw.get("input_prompt", ""))
    rows = int(terminal_raw.get("rows", 60))
    if input_prompt == "> ":
        # Migrate the previous default UI settings together.
        input_prompt = ""
        if rows == 40:
            rows = 60

    terminal = TerminalSettings(
        shell=terminal_raw.get("shell", "/bin/bash"),
        cwd=terminal_raw.get("cwd", str(Path.home())),
        user=terminal_raw.get("user", os.environ.get("USER", "user")),
        host=terminal_raw.get("host", "ubuntu"),
        count=count,
        names=names,
        names_explicit="names" in terminal_raw,
        input_prompt=input_prompt,
        columns=int(terminal_raw.get("columns", 120)),
        rows=rows,
        poll_interval=float(terminal_raw.get("poll_interval", 1.2)),
        refresh_interval=float(terminal_raw.get("refresh_interval", 1.5)),
        health_check_interval=float(terminal_raw.get("health_check_interval", 10.0)),
        show_cursor=bool(terminal_raw.get("show_cursor", True)),
        source_bashrc=bool(terminal_raw.get("source_bashrc", True)),
        sandbox=sandbox,
    )

    browser = BrowserSettings(
        width=int(browser_raw.get("width", 1280)),
        height=int(browser_raw.get("height", 720)),
        headless=bool(browser_raw.get("headless", True)),
        timeout_ms=int(browser_raw.get("timeout_ms", 15000)),
        settle_ms=int(browser_raw.get("settle_ms", 350)),
        show_cursor_overlay=bool(browser_raw.get("show_cursor_overlay", True)),
        vision_enabled=bool(browser_raw.get("vision_enabled", True)),
        vision_quality=int(browser_raw.get("vision_quality", 35)),
        vision_max_base64_chars=int(browser_raw.get("vision_max_base64_chars", 160000)),
    )

    _validate_terminal(terminal)
    _validate_sandbox(terminal.sandbox)
    _validate_browser(browser)
    return AppConfig(notion=notion, terminal=terminal, browser=browser)


def write_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> Path:
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    sandbox = config.terminal.sandbox
    credential_lines: list[str] = []
    for item in sandbox.credential_files:
        credential_lines.extend([
            "[[sandbox.credentials.files]]",
            f"path = {_toml_string(item.path)}",
            f"mode = {_toml_string(item.mode)}",
            f"extract = {_toml_string(item.extract)}",
            f"on_extract_no_match = {_toml_string(item.on_extract_no_match)}",
            f"mask_duplicates = {_toml_bool(item.mask_duplicates)}",
        ])
        if item.inject_hosts is not None:
            credential_lines.append(f"inject_hosts = {_toml_list(item.inject_hosts)}")
        credential_lines.append("")
    for item in sandbox.credential_env:
        credential_lines.extend([
            "[[sandbox.credentials.env]]",
            f"name = {_toml_string(item.name)}",
            f"mode = {_toml_string(item.mode)}",
            f"extract = {_toml_string(item.extract)}",
            f"on_extract_no_match = {_toml_string(item.on_extract_no_match)}",
        ])
        if item.inject_hosts is not None:
            credential_lines.append(f"inject_hosts = {_toml_list(item.inject_hosts)}")
        credential_lines.append("")

    text = "\n".join(
        [
            "[notion]",
            f"token = {_toml_string(config.notion.token)}",
            f"api_version = {_toml_string(config.notion.api_version)}",
            f"page_id = {_toml_string(config.notion.page_id)}",
            f"terminal_block_id = {_toml_string(config.notion.terminal_block_id)}",
            f"input_block_id = {_toml_string(config.notion.input_block_id)}",
            f"page_url = {_toml_string(config.notion.page_url)}",
            f"parent_page_id = {_toml_string(config.notion.parent_page_id)}",
            f"help_page_id = {_toml_string(config.notion.help_page_id)}",
            f"help_page_url = {_toml_string(config.notion.help_page_url)}",
            f"browser_status_block_id = {_toml_string(config.notion.browser_status_block_id)}",
            f"browser_image_block_id = {_toml_string(config.notion.browser_image_block_id)}",
            f"browser_vision_page_id = {_toml_string(config.notion.browser_vision_page_id)}",
            f"browser_vision_block_id = {_toml_string(config.notion.browser_vision_block_id)}",
            f"browser_vision_page_url = {_toml_string(config.notion.browser_vision_page_url)}",
            "",
            *[
                line
                for page in config.notion.terminal_pages
                for line in (
                    "[[notion.terminals]]",
                    f"page_id = {_toml_string(page.page_id)}",
                    f"terminal_block_id = {_toml_string(page.terminal_block_id)}",
                    f"input_block_id = {_toml_string(page.input_block_id)}",
                    f"page_url = {_toml_string(page.page_url)}",
                    "",
                )
            ],
            "[terminal]",
            f"shell = {_toml_string(config.terminal.shell)}",
            f"cwd = {_toml_string(config.terminal.cwd)}",
            f"user = {_toml_string(config.terminal.user)}",
            f"host = {_toml_string(config.terminal.host)}",
            f"count = {config.terminal.count}",
            f"names = {_toml_list(config.terminal.names)}",
            f"input_prompt = {_toml_string(config.terminal.input_prompt)}",
            f"columns = {config.terminal.columns}",
            f"rows = {config.terminal.rows}",
            f"poll_interval = {config.terminal.poll_interval}",
            f"refresh_interval = {config.terminal.refresh_interval}",
            f"health_check_interval = {config.terminal.health_check_interval}",
            f"show_cursor = {'true' if config.terminal.show_cursor else 'false'}",
            f"source_bashrc = {'true' if config.terminal.source_bashrc else 'false'}",
            "",
            "[sandbox]",
            f"enabled = {_toml_bool(sandbox.enabled)}",
            f"srt_path = {_toml_string(sandbox.srt_path)}",
            f"read_only = {_toml_bool(sandbox.read_only)}",
            f"workspace = {_toml_bool(sandbox.workspace)}",
            f"workspace_path = {_toml_string(sandbox.workspace_path)}",
            f"allow_read = {_toml_list(sandbox.allow_read)}",
            f"allow_write = {_toml_list(sandbox.allow_write)}",
            f"deny_read = {_toml_list(sandbox.deny_read)}",
            f"deny_write = {_toml_list(sandbox.deny_write)}",
            f"allowed_domains = {_toml_list(sandbox.allowed_domains)}",
            f"denied_domains = {_toml_list(sandbox.denied_domains)}",
            f"tls_terminate = {_toml_bool(sandbox.tls_terminate)}",
            f"allow_plaintext_inject = {_toml_bool(sandbox.allow_plaintext_inject)}",
            "",
            *credential_lines,
            "[browser]",
            f"width = {config.browser.width}",
            f"height = {config.browser.height}",
            f"headless = {'true' if config.browser.headless else 'false'}",
            f"timeout_ms = {config.browser.timeout_ms}",
            f"settle_ms = {config.browser.settle_ms}",
            f"show_cursor_overlay = {'true' if config.browser.show_cursor_overlay else 'false'}",
            f"vision_enabled = {'true' if config.browser.vision_enabled else 'false'}",
            f"vision_quality = {config.browser.vision_quality}",
            f"vision_max_base64_chars = {config.browser.vision_max_base64_chars}",
            "",
        ]
    )

    config_path.write_text(text, encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    return config_path


def _terminal_names(count: int, raw_names: object) -> list[str]:
    if count < 1 or count > 16:
        raise ValueError("terminal.count must be between 1 and 16")

    provided = _str_list(raw_names)
    defaults = (
        ["Terminal4GPTWeb"]
        if count == 1
        else [f"Terminal4GPTWeb {index}" for index in range(1, count + 1)]
    )
    names: list[str] = []
    for index in range(count):
        value = provided[index].strip() if index < len(provided) else ""
        names.append(value or defaults[index])
    return names


def _required(raw: dict, key: str) -> str:
    value = str(raw.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing required config value: {key}")
    return value


def _validate_terminal(settings: TerminalSettings) -> None:
    if settings.count < 1 or settings.count > 16:
        raise ValueError("terminal.count must be between 1 and 16")
    if len(settings.names) != settings.count:
        raise ValueError("terminal.names must contain exactly terminal.count names")
    normalized_names = [name.strip() for name in settings.names]
    if any(not _single_line(name) for name in normalized_names):
        raise ValueError("terminal.names entries must be non-empty single-line strings")
    if len({name.casefold() for name in normalized_names}) != len(normalized_names):
        raise ValueError("terminal.names entries must be unique")
    if "\n" in settings.input_prompt or "\r" in settings.input_prompt:
        raise ValueError("terminal.input_prompt must be a single line")
    if settings.columns < 20 or settings.columns > 400:
        raise ValueError("terminal.columns must be between 20 and 400")
    if settings.rows < 5 or settings.rows > 200:
        raise ValueError("terminal.rows must be between 5 and 200")
    if settings.poll_interval < 0.5:
        raise ValueError("terminal.poll_interval must be >= 0.5 seconds")
    if settings.refresh_interval < 0.5:
        raise ValueError("terminal.refresh_interval must be >= 0.5 seconds")
    if settings.health_check_interval < 3.0:
        raise ValueError("terminal.health_check_interval must be >= 3.0 seconds")


def _load_sandbox(sandbox_raw: dict) -> SandboxSettings:
    credentials_raw = sandbox_raw.get("credentials", {})
    credential_files = [
        CredentialFileSettings(
            path=str(item.get("path", "")),
            mode=str(item.get("mode", "mask")),
            extract=str(item.get("extract", "")),
            on_extract_no_match=str(item.get("on_extract_no_match", "warn")),
            mask_duplicates=bool(item.get("mask_duplicates", False)),
            inject_hosts=_optional_str_list(item, "inject_hosts"),
        )
        for item in credentials_raw.get("files", [])
        if isinstance(item, dict)
    ]
    credential_env = [
        CredentialEnvSettings(
            name=str(item.get("name", "")),
            mode=str(item.get("mode", "mask")),
            extract=str(item.get("extract", "")),
            on_extract_no_match=str(item.get("on_extract_no_match", "warn")),
            inject_hosts=_optional_str_list(item, "inject_hosts"),
        )
        for item in credentials_raw.get("env", [])
        if isinstance(item, dict)
    ]

    # Older configs used `mode = "..."`, `workspace = "<path>"` and
    # `workspace_enabled`; map them onto the explicit switches.
    legacy_mode = str(sandbox_raw.get("mode", "none"))
    raw_workspace = sandbox_raw.get("workspace", False)
    if isinstance(raw_workspace, bool):
        workspace = raw_workspace
        legacy_workspace_path = ""
    else:
        legacy_workspace_path = str(raw_workspace)
        workspace = bool(
            sandbox_raw.get("workspace_enabled", legacy_mode == "workspace")
        )

    if "read_only" in sandbox_raw:
        read_only = bool(sandbox_raw.get("read_only"))
    else:
        read_only = legacy_mode == "read_only"

    deny_read = _str_list(sandbox_raw.get("deny_read", []))
    deny_write = _str_list(sandbox_raw.get("deny_write", []))

    if "enabled" in sandbox_raw:
        enabled = bool(sandbox_raw.get("enabled"))
    else:
        # Configs written before `enabled` existed turned the sandbox on
        # implicitly through any restriction switch; keep them protected.
        enabled = bool(
            read_only
            or workspace
            or sandbox_raw.get("masking", False)
            or deny_read
            or deny_write
        )

    return SandboxSettings(
        enabled=enabled,
        srt_path=str(sandbox_raw.get("srt_path", "")),
        read_only=read_only,
        workspace=workspace,
        workspace_path=str(
            sandbox_raw.get("workspace_path", legacy_workspace_path)
        ),
        allow_read=_str_list(sandbox_raw.get("allow_read", [])),
        allow_write=_str_list(sandbox_raw.get("allow_write", [])),
        deny_read=deny_read,
        deny_write=deny_write,
        allowed_domains=_str_list(sandbox_raw.get("allowed_domains", [])),
        denied_domains=_str_list(sandbox_raw.get("denied_domains", [])),
        tls_terminate=bool(sandbox_raw.get("tls_terminate", False)),
        allow_plaintext_inject=bool(sandbox_raw.get("allow_plaintext_inject", False)),
        credential_files=credential_files,
        credential_env=credential_env,
    )


def _validate_sandbox(settings: SandboxSettings) -> None:
    if settings.workspace and settings.workspace_path:
        workspace_path = Path(settings.workspace_path).expanduser()
        if not workspace_path.is_absolute():
            raise ValueError("sandbox.workspace_path must be an absolute path")
    for name, values in (
        ("sandbox.allow_read", settings.allow_read),
        ("sandbox.allow_write", settings.allow_write),
        ("sandbox.deny_read", settings.deny_read),
        ("sandbox.deny_write", settings.deny_write),
    ):
        for value in values:
            if not _single_line(value):
                raise ValueError(f"{name} entries must be non-empty single-line paths")
    for name, values in (
        ("sandbox.allowed_domains", settings.allowed_domains),
        ("sandbox.denied_domains", settings.denied_domains),
    ):
        for value in values:
            if not _single_line(value) or " " in value:
                raise ValueError(f"{name} entries must be non-empty domain patterns")

    for item in settings.credential_files:
        if not _single_line(item.path):
            raise ValueError("sandbox.credentials.files path must be a non-empty single-line path")
        _validate_credential_rule("sandbox.credentials.files", item.path, item)
    for item in settings.credential_env:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.name):
            raise ValueError(
                f"sandbox.credentials.env name must be an environment variable name: {item.name!r}"
            )
        _validate_credential_rule("sandbox.credentials.env", item.name, item)

    has_mask = any(
        item.mode == "mask"
        for item in [*settings.credential_files, *settings.credential_env]
    )
    if has_mask and not settings.tls_terminate and not settings.allow_plaintext_inject:
        raise ValueError(
            "Credential masking needs sandbox.tls_terminate = true so srt can "
            "inject the real value into HTTPS requests (or set "
            "sandbox.allow_plaintext_inject = true to inject over plain HTTP only)."
        )


def _validate_credential_rule(
    name: str,
    label: str,
    item: CredentialFileSettings | CredentialEnvSettings,
) -> None:
    if item.mode not in {"mask", "deny"}:
        raise ValueError(f"{name} mode must be 'mask' or 'deny': {label}")
    if item.on_extract_no_match not in {"warn", "deny", "error"}:
        raise ValueError(f"{name} on_extract_no_match must be warn, deny, or error: {label}")
    if item.mode == "mask" and item.inject_hosts == []:
        raise ValueError(
            f"{name} inject_hosts cannot be empty in mask mode: {label}. "
            "SRT rejects mask-without-injection; use mode='deny' to block the "
            "credential entirely, omit inject_hosts to use allowed_domains, "
            "or list the intended hosts."
        )
    for host in item.inject_hosts or []:
        if not _single_line(host) or " " in host:
            raise ValueError(f"{name} inject_hosts entries must be domain patterns: {label}")
    if item.extract:
        try:
            pattern = re.compile(item.extract)
        except re.error as exc:
            raise ValueError(
                f"Invalid sandbox credential extract regex for {label}: {exc}"
            ) from exc
        if pattern.groups != 1:
            raise ValueError(
                f"sandbox credential extract regex must contain exactly one capture group: {label}"
            )


def _single_line(value: str) -> bool:
    return bool(value) and not any(ch in value for ch in ("\x00", "\n", "\r"))


def _str_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def _optional_str_list(raw: dict, key: str) -> list[str] | None:
    if key not in raw:
        return None
    return _str_list(raw.get(key))


def _validate_browser(settings: BrowserSettings) -> None:
    if settings.width < 320 or settings.width > 3840:
        raise ValueError("browser.width must be between 320 and 3840")
    if settings.height < 240 or settings.height > 2160:
        raise ValueError("browser.height must be between 240 and 2160")
    if settings.timeout_ms < 1000:
        raise ValueError("browser.timeout_ms must be >= 1000")
    if settings.settle_ms < 0 or settings.settle_ms > 10000:
        raise ValueError("browser.settle_ms must be between 0 and 10000")
    if settings.vision_quality < 1 or settings.vision_quality > 100:
        raise ValueError("browser.vision_quality must be between 1 and 100")
    if settings.vision_max_base64_chars < 10000 or settings.vision_max_base64_chars > 180000:
        raise ValueError("browser.vision_max_base64_chars must be between 10000 and 180000")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)
