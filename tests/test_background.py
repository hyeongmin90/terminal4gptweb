from pathlib import Path

import pytest

import terminal4gptweb.background as background


def test_tail_lines(tmp_path: Path):
    path = tmp_path / "daemon.log"
    path.write_text("a\nb\nc\n", encoding="utf-8")
    assert background._tail_lines(path, 2) == ["b\n", "c\n"]


def test_instance_lock_rejects_second_owner(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(background, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(background, "LOCK_FILE", tmp_path / "instance.lock")

    with background.InstanceLock():
        with pytest.raises(RuntimeError, match="already running"):
            with background.InstanceLock():
                pass


def test_cli_daemon_command_parses():
    from terminal4gptweb.cli import build_parser

    args = build_parser().parse_args(["daemon", "logs", "-n", "50", "-f"])
    assert args.command == "daemon"
    assert args.action == "logs"
    assert args.lines == 50
    assert args.follow is True


def test_process_is_our_daemon_fails_closed_when_cmdline_is_unreadable(monkeypatch):
    monkeypatch.setattr(background, "process_exists", lambda _pid: True)

    def unreadable(_self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", unreadable)

    assert background.process_is_our_daemon(12345) is False

