from types import SimpleNamespace

from terminal4gptweb.config import AppConfig, NotionSettings, TerminalPageSettings, TerminalSettings
from terminal4gptweb.daemon import TerminalDaemon, input_poll_slot, sanitize_terminal_for_notion


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



class _LegacyTitleNotion:
    def __init__(self, title):
        self.title = title
        self.updated = []

    def get_page(self, page_id):
        return {
            "id": page_id,
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": self.title}],
                }
            },
        }

    def update_page_title(self, page_id, title):
        self.updated.append((page_id, title))

    def create_terminal_page(self, *, parent_page_id, title, terminal_text, input_text):
        index = len(self.updated) + 2
        return SimpleNamespace(
            page_id=f"page-{index}",
            terminal_block_id=f"terminal-{index}",
            input_block_id=f"input-{index}",
            page_url=f"https://notion.so/page-{index}",
        )

    def close(self):
        pass


def test_legacy_single_terminal_adopts_existing_notion_page_title(tmp_path):
    page = TerminalPageSettings("page-1", "terminal-1", "input-1")
    config = AppConfig(
        notion=NotionSettings(
            token="test",
            page_id=page.page_id,
            terminal_block_id=page.terminal_block_id,
            input_block_id=page.input_block_id,
            terminal_pages=[page],
        ),
        terminal=TerminalSettings(
            cwd=str(tmp_path),
            count=1,
            names=["Terminal4GPTWeb"],
            names_explicit=False,
        ),
    )

    daemon = TerminalDaemon(config)
    daemon.notion.close()
    fake = _LegacyTitleNotion("My Existing Terminal")
    daemon.notion = fake
    try:
        daemon._ensure_terminal_pages()
        assert config.terminal.names == ["My Existing Terminal"]
        assert fake.updated == [("page-1", "My Existing Terminal")]
    finally:
        daemon.selector.close()
        daemon.browser.close()
        daemon.notion.close()



def test_input_poll_slot_preserves_single_terminal_interval_and_throttles_many():
    assert input_poll_slot(1, 1.2) == 1.2
    assert input_poll_slot(2, 1.2) == 0.6
    assert input_poll_slot(3, 1.2) == 0.6
    assert input_poll_slot(8, 1.2) == 0.6



def test_legacy_title_is_persisted_after_multi_terminal_page_expansion(tmp_path):
    page = TerminalPageSettings("page-1", "terminal-1", "input-1")
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        notion=NotionSettings(
            token="test",
            page_id=page.page_id,
            terminal_block_id=page.terminal_block_id,
            input_block_id=page.input_block_id,
            parent_page_id="parent",
            terminal_pages=[page],
        ),
        terminal=TerminalSettings(
            cwd=str(tmp_path),
            count=2,
            names=["Terminal4GPTWeb 1", "Terminal4GPTWeb 2"],
            names_explicit=False,
        ),
    )

    daemon = TerminalDaemon(config, config_path=config_path)
    daemon.notion.close()
    fake = _LegacyTitleNotion("My Existing Terminal")
    daemon.notion = fake
    try:
        daemon._ensure_terminal_pages()
        assert config.terminal.names == ["My Existing Terminal", "Terminal4GPTWeb 2"]
        written = config_path.read_text(encoding="utf-8")
        assert 'names = ["My Existing Terminal", "Terminal4GPTWeb 2"]' in written
        assert "[[notion.terminals]]" in written
        assert 'page_id = "page-2"' in written
    finally:
        daemon.selector.close()
        daemon.browser.close()
        daemon.notion.close()
