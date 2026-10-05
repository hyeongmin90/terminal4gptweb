from terminal4gptweb.notion import NotionPageSearchResult
import pytest

from terminal4gptweb.wizard import _choose_parent_page, _prompt_terminal_names


class FakeNotion:
    def __init__(self):
        self.queries = []

    def search_pages(self, query: str = "", *, limit: int = 10):
        self.queries.append((query, limit))
        return [
            NotionPageSearchResult("page-1", "Projects", "https://notion.so/projects"),
            NotionPageSearchResult("page-2", "Developer Tools", "https://notion.so/dev"),
        ]


def test_choose_parent_page_from_search(monkeypatch):
    answers = iter(["", "dev", "2"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    notion = FakeNotion()
    selected = _choose_parent_page(notion)

    assert selected == "page-2"
    assert notion.queries == [("dev", 10)]


def test_choose_parent_page_can_switch_to_url(monkeypatch):
    answers = iter([
        "",  # default Search pages
        "",  # recent pages
        "u",
        "https://www.notion.so/Test-123456781234123412341234567890ab?pvs=4",
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    selected = _choose_parent_page(FakeNotion())

    assert selected == "12345678-1234-1234-1234-1234567890ab"


def test_choose_parent_page_direct_url(monkeypatch):
    answers = iter([
        "2",
        "123456781234123412341234567890ab",
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    selected = _choose_parent_page(FakeNotion())

    assert selected == "12345678-1234-1234-1234-1234567890ab"


def test_prompt_terminal_names_uses_numbered_defaults(monkeypatch):
    answers = iter(["", "", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert _prompt_terminal_names(3, "Terminal4GPTWeb") == [
        "Terminal4GPTWeb 1",
        "Terminal4GPTWeb 2",
        "Terminal4GPTWeb 3",
    ]


def test_prompt_terminal_names_rejects_duplicate_names(monkeypatch):
    answers = iter(["Work", "work"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    with pytest.raises(ValueError, match="unique"):
        _prompt_terminal_names(2, "Terminal4GPTWeb")
