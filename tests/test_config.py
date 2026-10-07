from pathlib import Path

import pytest

from terminal4gptweb.config import (
    AppConfig,
    CredentialEnvSettings,
    CredentialFileSettings,
    DEFAULT_CONFIG_PATH,
    NotionSettings,
    SandboxSettings,
    TerminalPageSettings,
    TerminalSettings,
    load_config,
    write_config,
)


def test_default_config_path_uses_t4g_directory():
    assert DEFAULT_CONFIG_PATH == Path.home() / ".config" / "t4g" / "config.toml"


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    config = AppConfig(
        notion=NotionSettings(
            token="secret_test",
            page_id="page",
            terminal_block_id="terminal",
            input_block_id="input",
            page_url="https://notion.so/test",
            parent_page_id="parent",
            help_page_id="help",
            help_page_url="https://notion.so/help",
            terminal_pages=[
                TerminalPageSettings(
                    page_id="page",
                    terminal_block_id="terminal",
                    input_block_id="input",
                    page_url="https://notion.so/test",
                ),
                TerminalPageSettings(
                    page_id="page-2",
                    terminal_block_id="terminal-2",
                    input_block_id="input-2",
                    page_url="https://notion.so/test-2",
                ),
            ],
        ),
        terminal=TerminalSettings(
            shell="/bin/bash",
            cwd="/tmp",
            user="user",
            host="ubuntu",
            count=2,
            names=["Local", "Server"],
            input_prompt="",
            columns=100,
            rows=30,
            poll_interval=1.0,
            refresh_interval=1.5,
            health_check_interval=12.0,
            sandbox=SandboxSettings(
                enabled=True,
                srt_path="/opt/bin/srt",
                read_only=False,
                workspace=True,
                workspace_path="/tmp/project",
                allow_read=["~/.nvm"],
                allow_write=["~/.cache"],
                deny_read=["secrets/"],
                deny_write=[".git"],
                allowed_domains=["github.com", "*.npmjs.org"],
                denied_domains=["evil.github.com"],
                tls_terminate=True,
                credential_files=[
                    CredentialFileSettings(
                        path=".env",
                        mode="mask",
                        extract=r"(?m)^API_KEY=(\S+)$",
                        on_extract_no_match="deny",
                        mask_duplicates=True,
                        inject_hosts=["api.example.com"],
                    )
                ],
                credential_env=[
                    CredentialEnvSettings(
                        name="GITHUB_TOKEN",
                        inject_hosts=["api.github.com"],
                    ),
                    CredentialEnvSettings(name="DEFAULT_SCOPE"),
                ],
            ),
        ),
    )
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.notion.token == "secret_test"
    assert loaded.notion.parent_page_id == "parent"
    assert loaded.notion.help_page_id == "help"
    assert loaded.notion.help_page_url == "https://notion.so/help"
    assert len(loaded.notion.terminal_pages) == 2
    assert loaded.notion.terminal_pages[1].page_id == "page-2"
    assert loaded.terminal.count == 2
    assert loaded.terminal.names == ["Local", "Server"]
    assert loaded.terminal.input_prompt == ""
    assert loaded.terminal.columns == 100
    assert loaded.terminal.rows == 30
    assert loaded.terminal.health_check_interval == 12.0
    sandbox = loaded.terminal.sandbox
    assert sandbox.enabled is True
    assert sandbox.srt_path == "/opt/bin/srt"
    assert sandbox.read_only is False
    assert sandbox.workspace is True
    assert sandbox.mode == "workspace"
    assert sandbox.workspace_path == "/tmp/project"
    assert sandbox.allow_read == ["~/.nvm"]
    assert sandbox.allow_write == ["~/.cache"]
    assert sandbox.deny_read == ["secrets/"]
    assert sandbox.deny_write == [".git"]
    assert sandbox.allowed_domains == ["github.com", "*.npmjs.org"]
    assert sandbox.denied_domains == ["evil.github.com"]
    assert sandbox.tls_terminate is True
    assert sandbox.allow_plaintext_inject is False
    assert len(sandbox.credential_files) == 1
    masked = sandbox.credential_files[0]
    assert masked.path == ".env"
    assert masked.mode == "mask"
    assert masked.extract == r"(?m)^API_KEY=(\S+)$"
    assert masked.on_extract_no_match == "deny"
    assert masked.mask_duplicates is True
    assert masked.inject_hosts == ["api.example.com"]
    assert len(sandbox.credential_env) == 2
    env = sandbox.credential_env[0]
    assert env.name == "GITHUB_TOKEN"
    assert env.mode == "mask"
    assert env.inject_hosts == ["api.github.com"]
    default_scope = sandbox.credential_env[1]
    assert default_scope.name == "DEFAULT_SCOPE"
    assert default_scope.inject_hosts is None
    assert loaded.browser.width == 1280
    assert loaded.browser.height == 720


def test_minimal_config_uses_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
parent_page_id = "parent"

[[notion.terminals]]
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
shell = "/bin/bash"
cwd = "/tmp"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.terminal.input_prompt == ""
    assert loaded.terminal.count == 1
    assert loaded.terminal.names == ["Terminal4GPTWeb"]
    assert len(loaded.notion.terminal_pages) == 1
    assert loaded.notion.terminal_pages[0].page_id == "page"
    assert loaded.terminal.rows == 60
    assert loaded.terminal.sandbox.enabled is False
    assert loaded.terminal.sandbox.read_only is False
    assert loaded.terminal.sandbox.workspace is False
    assert loaded.terminal.sandbox.mode == "none"
    assert loaded.terminal.sandbox.workspace_path == ""
    assert loaded.terminal.sandbox.allowed_domains == []
    assert loaded.terminal.sandbox.deny_read == []
    assert loaded.terminal.sandbox.deny_write == []
    assert loaded.terminal.sandbox.credential_files == []
    assert loaded.terminal.sandbox.credential_env == []



def test_minimal_config_gets_browser_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
parent_page_id = "parent"

[[notion.terminals]]
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
shell = "/bin/bash"
cwd = "/tmp"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.notion.parent_page_id == "parent"
    assert loaded.notion.help_page_id == ""
    assert loaded.notion.help_page_url == ""
    assert loaded.notion.browser_status_block_id == ""
    assert loaded.notion.browser_image_block_id == ""
    assert loaded.browser.width == 1280
    assert loaded.browser.height == 720
    assert loaded.browser.headless is True
    assert loaded.browser.vision_enabled is True
    assert loaded.browser.vision_quality == 35
    assert loaded.notion.browser_vision_page_id == ""
    assert loaded.notion.browser_vision_block_id == ""


HEADER = """
[notion]
token = "secret_test"
parent_page_id = "parent"

[[notion.terminals]]
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
shell = "/bin/bash"
cwd = "/tmp"
""".strip()


def _load(tmp_path: Path, sandbox_toml: str):
    path = tmp_path / "config.toml"
    path.write_text(HEADER + "\n\n" + sandbox_toml.strip(), encoding="utf-8")
    return load_config(path).terminal.sandbox


def test_disabled_sandbox_keeps_inactive_rules(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
enabled = false
read_only = true
workspace = true
workspace_path = "/tmp/project"

[[sandbox.credentials.files]]
path = ".env"
mode = "deny"
""")
    assert sandbox.enabled is False
    assert sandbox.active is False
    assert sandbox.mode == "none"
    assert sandbox.read_only is True
    assert sandbox.workspace is True
    assert len(sandbox.credential_files) == 1


def test_enabled_without_restrictions_is_host_mode(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
enabled = true
""")
    assert sandbox.enabled is True
    assert sandbox.mode == "host"


def test_read_only_and_workspace_can_be_enabled_together(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
enabled = true
read_only = true
workspace = true
workspace_path = "/tmp/project"
""")
    assert sandbox.mode == "workspace_read_only"







def test_credential_extract_requires_one_capture_group(tmp_path: Path):
    with pytest.raises(ValueError, match="exactly one capture group"):
        _load(tmp_path, """
[sandbox]
enabled = true
tls_terminate = true

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = 'TOKEN=\\S+'
""")


def test_credential_env_name_must_be_valid(tmp_path: Path):
    with pytest.raises(ValueError, match="environment variable name"):
        _load(tmp_path, """
[sandbox]
enabled = true
tls_terminate = true

[[sandbox.credentials.env]]
name = "NOT-A-NAME"
""")


def test_masking_requires_tls_terminate_or_plaintext_opt_in(tmp_path: Path):
    with pytest.raises(ValueError, match="tls_terminate"):
        _load(tmp_path, """
[sandbox]
enabled = true

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
""")

    sandbox = _load(tmp_path, """
[sandbox]
enabled = true
allow_plaintext_inject = true

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
""")
    assert sandbox.allow_plaintext_inject is True


def test_deny_only_credentials_do_not_need_tls_terminate(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
enabled = true

[[sandbox.credentials.files]]
path = "~/.ssh"
mode = "deny"
""")
    assert sandbox.credential_files[0].mode == "deny"


def test_empty_inject_hosts_is_rejected_for_mask_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="inject_hosts cannot be empty"):
        _load(tmp_path, """
[sandbox]
enabled = true
tls_terminate = true

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = []
""")


def test_omitted_inject_hosts_uses_srt_default_scope(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
enabled = true
tls_terminate = true

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
""")
    assert sandbox.credential_env[0].inject_hosts is None


def test_domain_entries_must_not_contain_spaces(tmp_path: Path):
    with pytest.raises(ValueError, match="allowed_domains"):
        _load(tmp_path, """
[sandbox]
enabled = true
allowed_domains = ["github.com pypi.org"]
""")


def test_multi_terminal_defaults_generate_distinct_names(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
parent_page_id = "parent"

[[notion.terminals]]
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
count = 3
shell = "/bin/bash"
cwd = "/tmp"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(path)
    assert loaded.terminal.count == 3
    assert loaded.terminal.names == [
        "Terminal4GPTWeb 1",
        "Terminal4GPTWeb 2",
        "Terminal4GPTWeb 3",
    ]
    assert len(loaded.notion.terminal_pages) == 1


def test_multi_terminal_names_must_be_unique(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[notion]
token = "secret_test"
parent_page_id = "parent"

[[notion.terminals]]
page_id = "page"
terminal_block_id = "terminal"
input_block_id = "input"

[terminal]
count = 2
names = ["Work", "work"]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unique"):
        load_config(path)


def test_notion_token_env_var_is_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret_from_env")
    path = tmp_path / "config.toml"
    path.write_text(HEADER.replace('token = "secret_test"\n', ""), encoding="utf-8")
    with pytest.raises(ValueError, match="notion.token"):
        load_config(path)

    path.write_text(HEADER.replace("secret_test", "secret_from_file"), encoding="utf-8")
    config = load_config(path)
    assert config.notion.token == "secret_from_file"
    write_config(config, path)
    assert "secret_from_env" not in path.read_text(encoding="utf-8")


def test_sandbox_stays_disabled_unless_enabled(tmp_path: Path):
    sandbox = _load(tmp_path, """
[sandbox]
read_only = true
deny_write = [".git"]
""")
    assert sandbox.enabled is False


def test_sandbox_workspace_must_be_boolean(tmp_path: Path):
    with pytest.raises(ValueError, match="sandbox.workspace must be true or false"):
        _load(tmp_path, """
[sandbox]
enabled = true
workspace = "/tmp/project"
""")


@pytest.mark.parametrize(
    ("removed", "message"),
    [
        ('parent_page_id = "parent"\n', "parent_page_id"),
        ('\n[[notion.terminals]]\npage_id = "page"\nterminal_block_id = "terminal"\ninput_block_id = "input"\n', "notion.terminals"),
    ],
)
def test_required_notion_entries(tmp_path: Path, removed: str, message: str):
    path = tmp_path / "config.toml"
    assert removed in HEADER
    path.write_text(HEADER.replace(removed, ""), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_config(path)
