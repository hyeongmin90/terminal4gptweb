import json
import shlex
from pathlib import Path

import pytest

from terminal4gptweb import sandbox as sandbox_module
from terminal4gptweb.config import (
    CredentialEnvSettings,
    CredentialFileSettings,
    SandboxSettings,
    TerminalSettings,
)
from terminal4gptweb.sandbox import (
    SandboxUnavailableError,
    build_shell_launch,
    build_srt_settings,
    descendant_pids,
    srt_package_root,
)


def _settings(tmp_path: Path, **sandbox_kwargs) -> tuple[TerminalSettings, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    sandbox_kwargs.setdefault("workspace_path", str(workspace))
    return (
        TerminalSettings(
            shell="/bin/bash",
            cwd=str(workspace),
            sandbox=SandboxSettings(**sandbox_kwargs),
        ),
        workspace,
    )


@pytest.fixture
def fake_tools(monkeypatch, tmp_path):
    """Pretend srt and its system dependencies are installed."""
    paths = {
        "srt": "/opt/bin/srt",
        "bwrap": "/usr/bin/bwrap",
        "socat": "/usr/bin/socat",
        "rg": "/usr/bin/rg",
        "script": "/usr/bin/script",
    }
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda name: paths.get(name))
    return paths


def test_disabled_sandbox_launches_shell_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda name: None)
    settings, workspace = _settings(tmp_path, enabled=False, read_only=True, workspace=True)

    launch = build_shell_launch(settings, cwd=workspace, shell=Path("/bin/bash"), rcfile=None)

    assert launch.executable == "/bin/bash"
    assert launch.argv == ["/bin/bash", "-i"]
    assert launch.cwd == str(workspace)


def test_disabled_sandbox_passes_rcfile(tmp_path):
    settings, workspace = _settings(tmp_path, enabled=False)
    rcfile = tmp_path / "bashrc"

    launch = build_shell_launch(settings, cwd=workspace, shell=Path("/bin/bash"), rcfile=rcfile)

    assert launch.argv == ["/bin/bash", "--rcfile", str(rcfile), "-i"]


def test_enabled_sandbox_without_srt_reports_install_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sandbox_module.shutil,
        "which",
        lambda name: None if name == "srt" else f"/usr/bin/{name}",
    )
    settings, workspace = _settings(tmp_path, enabled=True)

    with pytest.raises(SandboxUnavailableError) as excinfo:
        build_shell_launch(settings, cwd=workspace, shell=Path("/bin/bash"), rcfile=None)

    message = str(excinfo.value)
    assert "srt" in message
    assert "npm install -g @anthropic-ai/sandbox-runtime" in message
    assert "sandbox.enabled = false" in message


def test_enabled_sandbox_lists_missing_system_packages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sandbox_module.shutil,
        "which",
        lambda name: None if name in {"socat", "rg"} else f"/usr/bin/{name}",
    )
    settings, workspace = _settings(tmp_path, enabled=True)

    with pytest.raises(SandboxUnavailableError, match="sudo apt install -y socat ripgrep"):
        build_shell_launch(settings, cwd=workspace, shell=Path("/bin/bash"), rcfile=None)


def test_explicit_srt_path_must_be_executable(tmp_path, fake_tools):
    settings, workspace = _settings(
        tmp_path,
        enabled=True,
        srt_path=str(tmp_path / "missing-srt"),
    )

    with pytest.raises(SandboxUnavailableError, match="missing-srt"):
        build_shell_launch(settings, cwd=workspace, shell=Path("/bin/bash"), rcfile=None)


def test_enabled_sandbox_wraps_shell_in_srt_and_script(tmp_path, fake_tools):
    settings, workspace = _settings(tmp_path, enabled=True)
    rcfile = tmp_path / "bashrc"
    settings_path = tmp_path / "srt.json"

    launch = build_shell_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=rcfile,
        srt_settings_path=settings_path,
    )

    assert launch.executable == "/opt/bin/srt"
    assert launch.argv == [
        "/opt/bin/srt",
        "-s",
        str(settings_path),
        "--",
        "/usr/bin/script",
        "-qfec",
        shlex.join(["/bin/bash", "--rcfile", str(rcfile), "-i"]),
        "/dev/null",
    ]
    assert launch.cwd == str(workspace)
    assert settings_path.stat().st_mode & 0o777 == 0o600
    document = json.loads(settings_path.read_text())
    assert document["filesystem"]["allowWrite"] == ["/"]


def test_workspace_launch_runs_in_workspace(tmp_path, fake_tools):
    other = tmp_path / "project"
    other.mkdir()
    settings, cwd = _settings(tmp_path, enabled=True, workspace=True, workspace_path=str(other))

    launch = build_shell_launch(
        settings,
        cwd=cwd,
        shell=Path("/bin/bash"),
        rcfile=None,
        srt_settings_path=tmp_path / "srt.json",
    )

    assert launch.cwd == str(other)


def test_workspace_launch_keeps_srt_package_readable(tmp_path, monkeypatch):
    # srt installed under the home directory (e.g. nvm) runs its seccomp
    # helper from the package inside the sandbox, so workspace mode must
    # not hide it.
    package = tmp_path / "home" / ".nvm" / "lib" / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
    (package / "dist").mkdir(parents=True)
    (package / "dist" / "cli.js").write_text("")
    bin_dir = tmp_path / "home" / ".nvm" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "srt").symlink_to(package / "dist" / "cli.js")
    paths = {
        "srt": str(bin_dir / "srt"),
        "bwrap": "/usr/bin/bwrap",
        "socat": "/usr/bin/socat",
        "rg": "/usr/bin/rg",
        "script": "/usr/bin/script",
    }
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda name: paths.get(name))
    settings, workspace = _settings(tmp_path, enabled=True, workspace=True)
    settings_path = tmp_path / "srt.json"

    build_shell_launch(
        settings,
        cwd=workspace,
        shell=Path("/bin/bash"),
        rcfile=None,
        srt_settings_path=settings_path,
    )

    allow_read = json.loads(settings_path.read_text())["filesystem"]["allowRead"]
    assert str(package) in allow_read


def test_srt_package_root_follows_bin_symlink(tmp_path):
    package = tmp_path / "sandbox-runtime"
    (package / "dist").mkdir(parents=True)
    (package / "dist" / "cli.js").write_text("")
    link = tmp_path / "srt"
    link.symlink_to(package / "dist" / "cli.js")

    assert srt_package_root(str(link)) == package.resolve()


def test_missing_workspace_is_rejected(tmp_path, fake_tools):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        workspace=True,
        workspace_path=str(tmp_path / "nope"),
    )

    with pytest.raises(FileNotFoundError, match="workspace does not exist"):
        build_shell_launch(
            settings,
            cwd=cwd,
            shell=Path("/bin/bash"),
            rcfile=None,
            srt_settings_path=tmp_path / "srt.json",
        )


def test_host_mode_allows_writes_everywhere(tmp_path):
    settings, cwd = _settings(tmp_path, enabled=True)

    document = build_srt_settings(settings, cwd=cwd)

    assert document["filesystem"] == {
        "denyRead": [],
        "allowRead": [],
        "allowWrite": ["/"],
        "denyWrite": [],
    }
    assert document["network"] == {"allowedDomains": [], "deniedDomains": []}
    assert "credentials" not in document


def test_read_only_mode_allows_no_writes(tmp_path):
    settings, cwd = _settings(tmp_path, enabled=True, read_only=True)

    document = build_srt_settings(settings, cwd=cwd)

    assert document["filesystem"]["allowWrite"] == []


def test_read_only_mode_keeps_explicit_allow_write(tmp_path):
    settings, cwd = _settings(tmp_path, enabled=True, read_only=True, allow_write=["~/.cache"])

    document = build_srt_settings(settings, cwd=cwd)

    assert document["filesystem"]["allowWrite"] == [str(Path.home() / ".cache")]


def test_workspace_mode_hides_user_data_and_rebinds_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_module, "WORKSPACE_HIDDEN_ROOTS", ("/home", str(tmp_path / "absent")))
    settings, workspace = _settings(tmp_path, enabled=True, workspace=True)
    rcfile = tmp_path / "bashrc"

    document = build_srt_settings(settings, cwd=workspace, readable_paths=[rcfile])

    filesystem = document["filesystem"]
    assert filesystem["denyRead"] == ["/home"]
    assert filesystem["allowRead"] == [str(workspace), str(rcfile)]
    assert filesystem["allowWrite"] == [str(workspace)]


def test_allow_read_is_forwarded(tmp_path):
    settings, workspace = _settings(
        tmp_path,
        enabled=True,
        workspace=True,
        allow_read=["~/.nvm", "tools"],
    )

    allow_read = build_srt_settings(settings, cwd=workspace)["filesystem"]["allowRead"]

    assert str(Path.home() / ".nvm") in allow_read
    assert str(workspace / "tools") in allow_read


def test_workspace_read_only_mode_exposes_workspace_without_writes(tmp_path):
    settings, workspace = _settings(tmp_path, enabled=True, workspace=True, read_only=True)

    document = build_srt_settings(settings, cwd=workspace)

    assert str(workspace) in document["filesystem"]["allowRead"]
    assert document["filesystem"]["allowWrite"] == []


def test_relative_policy_paths_resolve_against_workspace(tmp_path):
    other = tmp_path / "project"
    other.mkdir()
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        workspace=True,
        workspace_path=str(other),
        deny_write=["migrations", "./.git/"],
        deny_read=["secrets"],
        allow_write=["/var/cache/app"],
    )

    filesystem = build_srt_settings(settings, cwd=cwd)["filesystem"]

    assert filesystem["denyWrite"] == [str(other / "migrations"), str(other / ".git")]
    assert str(other / "secrets") in filesystem["denyRead"]
    assert filesystem["allowWrite"] == [str(other), "/var/cache/app"]


def test_relative_policy_paths_resolve_against_cwd_outside_workspace(tmp_path):
    settings, cwd = _settings(tmp_path, enabled=True, deny_write=[".env"])

    filesystem = build_srt_settings(settings, cwd=cwd)["filesystem"]

    assert filesystem["denyWrite"] == [str(cwd / ".env")]


def test_network_settings_are_forwarded(tmp_path):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        allowed_domains=["github.com", "*.npmjs.org"],
        denied_domains=["evil.github.com"],
        tls_terminate=True,
    )

    network = build_srt_settings(settings, cwd=cwd)["network"]

    assert network == {
        "allowedDomains": ["github.com", "*.npmjs.org"],
        "deniedDomains": ["evil.github.com"],
        "tlsTerminate": {},
    }


def test_credentials_translate_to_srt_rules(tmp_path):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        tls_terminate=True,
        credential_files=[
            CredentialFileSettings(
                path=".env",
                extract=r"API_KEY=(\S+)",
                on_extract_no_match="deny",
                mask_duplicates=True,
                inject_hosts=["api.example.com"],
            ),
            CredentialFileSettings(path="~/.ssh", mode="deny", extract="ignored=(x)"),
        ],
        credential_env=[
            CredentialEnvSettings(name="GITHUB_TOKEN", inject_hosts=["api.github.com"]),
            CredentialEnvSettings(
                name="DATABASE_URL",
                extract=r"://[^:]+:([^@]+)@",
                on_extract_no_match="error",
            ),
        ],
    )

    credentials = build_srt_settings(settings, cwd=cwd)["credentials"]

    assert credentials == {
        "files": [
            {
                "path": str(cwd / ".env"),
                "mode": "mask",
                "extract": r"API_KEY=(\S+)",
                "onExtractNoMatch": "deny",
                "maskDuplicates": True,
                "injectHosts": ["api.example.com"],
            },
            {"path": str(Path.home() / ".ssh"), "mode": "deny"},
        ],
        "envVars": [
            {"name": "GITHUB_TOKEN", "mode": "mask", "injectHosts": ["api.github.com"]},
            {
                "name": "DATABASE_URL",
                "mode": "mask",
                "extract": r"://[^:]+:([^@]+)@",
                "onExtractNoMatch": "error",
            },
        ],
    }


def test_omitted_inject_hosts_is_omitted_from_srt_rule(tmp_path):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        tls_terminate=True,
        credential_env=[CredentialEnvSettings(name="TOKEN")],
    )

    rule = build_srt_settings(settings, cwd=cwd)["credentials"]["envVars"][0]

    assert rule == {"name": "TOKEN", "mode": "mask"}


def test_empty_inject_hosts_is_rejected_before_srt(tmp_path):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        tls_terminate=True,
        credential_env=[CredentialEnvSettings(name="TOKEN", inject_hosts=[])],
    )

    with pytest.raises(ValueError, match="empty injectHosts"):
        build_srt_settings(settings, cwd=cwd)


def test_plaintext_inject_opt_in_is_forwarded(tmp_path):
    settings, cwd = _settings(
        tmp_path,
        enabled=True,
        allow_plaintext_inject=True,
        credential_env=[CredentialEnvSettings(name="TOKEN")],
    )

    credentials = build_srt_settings(settings, cwd=cwd)["credentials"]

    assert credentials["allowPlaintextInject"] is True


def test_descendant_pids_finds_grandchildren():
    import os
    import signal
    import subprocess
    import time

    parent = subprocess.Popen(["bash", "-c", "sleep 30 & wait"], start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        found: list[int] = []
        while time.monotonic() < deadline and not found:
            found = descendant_pids(parent.pid)
            time.sleep(0.05)
        assert found
        assert parent.pid not in found
    finally:
        os.killpg(parent.pid, signal.SIGKILL)
        parent.wait()



def test_oversized_input_is_rejected_before_writing_and_noticed(tmp_path, monkeypatch):
    from terminal4gptweb import terminal as terminal_module
    from terminal4gptweb.terminal import MAX_INPUT_BYTES, InputTooLargeError, PTYSession

    session = PTYSession(TerminalSettings(cwd=str(tmp_path)))
    session.master_fd = -1
    monkeypatch.setattr(session, "is_alive", lambda: True)
    sent: list[bytes] = []
    monkeypatch.setattr(
        terminal_module.os, "write", lambda _fd, data: sent.append(bytes(data)) or len(data)
    )

    with pytest.raises(InputTooLargeError):
        session.send_line("가" * (MAX_INPUT_BYTES // 3 + 1))
    assert sent == []

    session.send_line("x" * (MAX_INPUT_BYTES - 1))
    assert sent == [b"x" * (MAX_INPUT_BYTES - 1) + b"\r"]
    session.master_fd = None

    session.show_notice("[Terminal4GPTWeb] Input not sent")
    assert "[Terminal4GPTWeb] Input not sent" in session.render()
