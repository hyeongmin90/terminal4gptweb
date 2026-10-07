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
    monkeypatch.setattr(background, "LEGACY_LOCK_FILE", tmp_path / "missing" / "instance.lock")

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


def test_instance_lock_also_blocks_legacy_daemon(tmp_path: Path, monkeypatch):
    import fcntl

    monkeypatch.setattr(background, "CACHE_DIR", tmp_path / "t4g")
    monkeypatch.setattr(background, "LOCK_FILE", tmp_path / "t4g" / "instance.lock")
    legacy_lock = tmp_path / "notion_is_terminal" / "instance.lock"
    legacy_lock.parent.mkdir()
    monkeypatch.setattr(background, "LEGACY_LOCK_FILE", legacy_lock)

    with legacy_lock.open("a+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            with background.InstanceLock():
                pass

    # The new lock was released on failure, so a later start still works.
    with background.InstanceLock():
        pass


def test_read_pid_falls_back_to_legacy_pid_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(background, "PID_FILE", tmp_path / "t4g" / "daemon.pid")
    legacy_pid = tmp_path / "notion_is_terminal" / "daemon.pid"
    legacy_pid.parent.mkdir()
    legacy_pid.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(background, "LEGACY_PID_FILE", legacy_pid)

    assert background.read_pid() == 4242
    background._remove_pid_file()
    assert not legacy_pid.exists()
