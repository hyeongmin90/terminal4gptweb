from terminal4gptweb.notion import (
    MAX_RICH_TEXT_CHUNK,
    NotionClient,
    NotionError,
    NotionPageSearchResult,
    BrowserAnchors,
    RuntimeAnchors,
    RuntimeBlocks,
    block_is_usable_code,
    browser_screenshot_image_ids,
    find_browser_anchors,
    find_browser_saved_anchor,
    find_runtime_anchors,
    help_page_children,
    parse_page_id,
    rich_text_payload,
    runtime_blocks_are_in_place,
    terminal_page_children,
)


def _rich(text):
    return [{"plain_text": text}]


def test_parse_plain_uuid():
    value = "123456781234123412341234567890ab"
    assert parse_page_id(value) == "12345678-1234-1234-1234-1234567890ab"


def test_parse_notion_url():
    url = "https://www.notion.so/Test-123456781234123412341234567890ab?pvs=4"
    assert parse_page_id(url) == "12345678-1234-1234-1234-1234567890ab"


def test_rich_text_is_chunked_below_notion_limit():
    text = "x" * (MAX_RICH_TEXT_CHUNK + 10)
    payload = rich_text_payload(text)
    assert len(payload) == 2
    assert "".join(item["text"]["content"] for item in payload) == text
    assert all(len(item["text"]["content"]) <= MAX_RICH_TEXT_CHUNK for item in payload)


def test_generated_page_has_exactly_two_code_blocks():
    children = terminal_page_children("screen", "")
    code_blocks = [block for block in children if block["type"] == "code"]
    assert len(code_blocks) == 2
    assert code_blocks[0]["code"]["language"] == "plain text"
    assert code_blocks[1]["code"]["language"] == "bash"


def test_block_usability_rejects_archived_or_trashed_blocks():
    assert block_is_usable_code({"type": "code", "archived": False, "in_trash": False})
    assert not block_is_usable_code({"type": "code", "archived": True})
    assert not block_is_usable_code({"type": "code", "in_trash": True})
    assert not block_is_usable_code({"type": "paragraph"})


def test_notion_error_marks_object_not_found():
    exc = NotionError("missing", status_code=404, code="object_not_found")
    assert exc.is_not_found


def test_find_runtime_anchors_and_positions():
    children = [
        {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
        {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
        {"id": "terminal", "type": "code", "code": {"rich_text": []}},
        {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
        {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
        {"id": "input", "type": "code", "code": {"rich_text": []}},
    ]

    anchors = find_runtime_anchors(children)
    assert anchors == RuntimeAnchors("a-terminal", "a-input")
    assert runtime_blocks_are_in_place(
        children,
        terminal_anchor_id="a-terminal",
        input_anchor_id="a-input",
        terminal_block_id="terminal",
        input_block_id="input",
    )


def test_runtime_pair_at_page_end_is_not_considered_in_place():
    children = [
        {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
        {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
        {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
        {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
        {"id": "terminal-old", "type": "code", "code": {"rich_text": []}},
        {"id": "input-old", "type": "code", "code": {"rich_text": []}},
    ]
    assert not runtime_blocks_are_in_place(
        children,
        terminal_anchor_id="a-terminal",
        input_anchor_id="a-input",
        terminal_block_id="terminal-old",
        input_block_id="input-old",
    )


class FakeNotionClient(NotionClient):
    def __init__(self, *, missing: str):
        self.missing = missing
        self.blocks = {
            "terminal-old": {"id": "terminal-old", "type": "code", "archived": False, "in_trash": False},
            "input-old": {"id": "input-old", "type": "code", "archived": False, "in_trash": False},
        }
        if missing == "terminal":
            del self.blocks["terminal-old"]
        if missing == "input":
            del self.blocks["input-old"]
        self.archived = []
        self.restored = []

    def get_page(self, page_id):
        assert page_id == "page"
        return {"id": page_id}

    def get_block(self, block_id):
        if block_id not in self.blocks:
            raise NotionError("missing", status_code=404, code="object_not_found")
        return self.blocks[block_id]

    def get_block_children(self, block_id):
        assert block_id == "page"
        children = [
            {"id": "h-terminal", "type": "heading_2", "heading_2": {"rich_text": _rich("Terminal")}},
            {"id": "a-terminal", "type": "paragraph", "paragraph": {"rich_text": _rich("Live PTY")}},
        ]
        if "terminal-old" in self.blocks:
            children.append(self.blocks["terminal-old"])
        children.extend([
            {"id": "h-input", "type": "heading_2", "heading_2": {"rich_text": _rich("Input")}},
            {"id": "a-input", "type": "paragraph", "paragraph": {"rich_text": _rich("Input help")}},
        ])
        if "input-old" in self.blocks:
            children.append(self.blocks["input-old"])
        return children

    def archive_block(self, block_id):
        self.archived.append(block_id)
        self.blocks[block_id]["archived"] = True

    def restore_runtime_block_at_anchor(self, *, page_id, anchor_id, text, language):
        assert page_id == "page"
        self.restored.append((anchor_id, text, language))
        return "terminal-new" if anchor_id == "a-terminal" else "input-new"


def test_missing_terminal_reuses_existing_input_block():
    notion = FakeNotionClient(missing="terminal")
    blocks = notion.ensure_runtime_blocks(
        page_id="page",
        terminal_block_id="terminal-old",
        input_block_id="input-old",
        terminal_text="current screen",
        input_text="> ",
    )

    assert notion.archived == []
    assert notion.restored == [("a-terminal", "current screen", "plain text")]
    assert blocks.recreated is True
    assert blocks.terminal_block_id == "terminal-new"
    assert blocks.input_block_id == "input-old"


def test_missing_input_reuses_existing_terminal_block():
    notion = FakeNotionClient(missing="input")
    blocks = notion.ensure_runtime_blocks(
        page_id="page",
        terminal_block_id="terminal-old",
        input_block_id="input-old",
        terminal_text="current screen",
        input_text="> ",
    )

    assert notion.archived == []
    assert notion.restored == [("a-input", "> ", "bash")]
    assert blocks.recreated is True
    assert blocks.terminal_block_id == "terminal-old"
    assert blocks.input_block_id == "input-new"


def test_find_browser_anchors():
    children = [
        {"id": "h-browser", "type": "heading_2", "heading_2": {"rich_text": _rich("Browser")}},
        {"id": "a-browser", "type": "paragraph", "paragraph": {"rich_text": _rich("status")}},
        {"id": "status", "type": "code", "code": {"rich_text": []}},
        {"id": "h-shot", "type": "heading_2", "heading_2": {"rich_text": _rich("Browser Screenshot")}},
        {"id": "a-shot", "type": "paragraph", "paragraph": {"rich_text": _rich("latest image")}},
    ]
    assert find_browser_anchors(children) == BrowserAnchors("a-browser", "a-shot")


def test_find_browser_saved_anchor():
    children = [
        {"id": "heading", "type": "heading_2", "heading_2": {"rich_text": _rich("Browser Saved Snapshots")}},
        {"id": "anchor", "type": "paragraph", "paragraph": {"rich_text": _rich("temporary captures")}},
        {"id": "image-1", "type": "image", "image": {}},
        {"id": "next", "type": "heading_2", "heading_2": {"rich_text": _rich("Other")}},
    ]
    assert find_browser_saved_anchor(children) == "anchor"
    assert browser_screenshot_image_ids(children, anchor_id="anchor") == ["image-1"]


def test_browser_screenshot_image_ids_stop_at_next_section():
    children = [
        {"id": "anchor", "type": "paragraph", "paragraph": {"rich_text": _rich("latest")}},
        {"id": "image-1", "type": "image", "image": {}},
        {"id": "image-2", "type": "image", "image": {}},
        {"id": "next", "type": "heading_2", "heading_2": {"rich_text": _rich("Other")}},
        {"id": "image-3", "type": "image", "image": {}},
    ]
    assert browser_screenshot_image_ids(children, anchor_id="anchor") == ["image-1", "image-2"]


def test_terminal_page_children_are_compact():
    children = terminal_page_children("screen", "> ")
    text = " ".join(
        item.get(item.get("type", ""), {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
        for item in children
        if item.get("type") in {"paragraph", "bulleted_list_item", "heading_2", "callout"}
        and item.get(item.get("type", ""), {}).get("rich_text")
    )
    assert "For AI: Read the Terminal4GPTWeb Help page before using this control surface." in text
    assert "Input is executed only when the text ends with a newline" in text
    assert "Quick Commands" in text
    assert "Browser open" in text
    assert "Save current browser view" in text
    assert "Save long page as readable tiles" in text
    assert "Common TUI recipes" not in text
    assert "Key names and aliases" not in text


def test_help_page_contains_agent_commands_and_recovery():
    children = help_page_children()
    text = " ".join(
        item.get(item.get("type", ""), {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
        for item in children
        if item.get("type") in {"paragraph", "bulleted_list_item", "heading_2", "callout"}
        and item.get(item.get("type", ""), {}).get("rich_text")
    )
    assert "For GPT / Agents" in text
    assert "Input submission rule" in text
    assert "command stays visible in Input" in text
    assert ":b click <observation_id> <x> <y>" in text
    assert "Browser Control Loop" in text
    assert ":b save [label]" in text
    assert ":b full [label]" in text
    assert ":b clear-saved" in text
    assert "STALE_OBSERVATION" in text
    assert "click field → wait for ready → type" in text
    assert "do not append :k ENTER to ordinary text" in text
    assert "t4g reinit" in text


class FakeSearchNotionClient(NotionClient):
    def __init__(self):
        self.last_request = None

    def _request(self, method, path, *, json=None):
        self.last_request = (method, path, json)
        return {
            "results": [
                {
                    "object": "page",
                    "id": "page-1",
                    "url": "https://notion.so/project",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [
                                {"plain_text": "Project "},
                                {"plain_text": "Root"},
                            ],
                        }
                    },
                },
                {
                    "object": "database",
                    "id": "db-1",
                    "properties": {},
                },
                {
                    "object": "page",
                    "id": "page-2",
                    "url": "https://notion.so/untitled",
                    "properties": {},
                },
            ]
        }


def test_search_pages_filters_pages_and_extracts_titles():
    notion = FakeSearchNotionClient()
    results = notion.search_pages("project", limit=10)

    assert results == [
        NotionPageSearchResult("page-1", "Project Root", "https://notion.so/project"),
        NotionPageSearchResult("page-2", "(untitled)", "https://notion.so/untitled"),
    ]

    method, path, payload = notion.last_request
    assert method == "POST"
    assert path == "/search"
    assert payload["query"] == "project"
    assert payload["filter"] == {"property": "object", "value": "page"}
    assert payload["page_size"] == 10


def test_search_pages_blank_query_lists_recent_pages():
    notion = FakeSearchNotionClient()
    notion.search_pages("", limit=5)

    payload = notion.last_request[2]
    assert "query" not in payload
    assert payload["page_size"] == 5
