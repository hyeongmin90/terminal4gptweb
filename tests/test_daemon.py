from terminal4gptweb.config import AppConfig, NotionSettings, TerminalPageSettings, TerminalSettings
from terminal4gptweb.daemon import TerminalDaemon, sanitize_terminal_for_notion


def test_sanitize_terminal_for_notion_leaves_normal_text_unchanged():
    assert sanitize_terminal_for_notion("hello\nworld") == "hello\nworld"


def test_sanitize_terminal_for_notion_breaks_markdown_fences():
    value = sanitize_terminal_for_notion("before ```python after")
    assert "```" not in value
    assert value.replace("\u00a0", "") == "before ```python after"


def test_sanitize_terminal_for_notion_breaks_long_backtick_runs():
    value = sanitize_terminal_for_notion("``````")
    assert "```" not in value
    assert value.replace("\u00a0", "") == "``````"



def test_multi_terminal_sessions_have_independent_terminal_settings(tmp_path):
    pages = [
        TerminalPageSettings("page-1", "terminal-1", "input-1"),
        TerminalPageSettings("page-2", "terminal-2", "input-2"),
    ]
    config = AppConfig(
        notion=NotionSettings(
            token="test",
            page_id="page-1",
            terminal_block_id="terminal-1",
            input_block_id="input-1",
            terminal_pages=pages,
        ),
        terminal=TerminalSettings(
            cwd=str(tmp_path),
            count=2,
            names=["Shell", "Server"],
            columns=120,
            rows=60,
        ),
    )

    daemon = TerminalDaemon(config)
    try:
        daemon._build_runtimes()
        first = daemon.runtimes[0].session
        second = daemon.runtimes[1].session

        assert first.settings is not second.settings
        first.settings.columns = 200
        first.settings.rows = 80
        assert second.settings.columns == 120
        assert second.settings.rows == 60
        assert config.terminal.columns == 120
        assert config.terminal.rows == 60
    finally:
        daemon.selector.close()
        daemon.browser.close()
        daemon.notion.close()
