from pathlib import Path


UNIT_PATH = Path(__file__).parents[1] / "contrib" / "systemd" / "terminal4gptweb.service"


def test_systemd_user_unit_runs_foreground_daemon() -> None:
    unit = UNIT_PATH.read_text(encoding="utf-8")

    assert "[Service]" in unit
    assert "Type=simple" in unit
    assert "ExecStart=%h/terminal4gptweb/.venv/bin/t4g run" in unit
    assert "Restart=always" in unit
    assert "WantedBy=default.target" in unit


def test_systemd_user_unit_does_not_start_detached_daemon() -> None:
    unit = UNIT_PATH.read_text(encoding="utf-8")

    assert "daemon start" not in unit
