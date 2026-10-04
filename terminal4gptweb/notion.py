from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx


MAX_RICH_TEXT_CHUNK = 1900
MAX_RICH_TEXT_ITEMS = 100


class NotionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404 or self.code == "object_not_found"


@dataclass(slots=True)
class NotionPageSearchResult:
    page_id: str
    title: str
    url: str


@dataclass(slots=True)
class CreatedTerminalPage:
    page_id: str
    page_url: str
    terminal_block_id: str
    input_block_id: str


@dataclass(slots=True)
class RuntimeBlocks:
    terminal_block_id: str
    input_block_id: str
    recreated: bool = False


@dataclass(slots=True)
class RuntimeAnchors:
    terminal_anchor_id: str
    input_anchor_id: str


@dataclass(slots=True)
class BrowserBlocks:
    status_block_id: str
    image_block_id: str = ""
    recreated: bool = False


@dataclass(slots=True)
class BrowserAnchors:
    status_anchor_id: str
    screenshot_anchor_id: str


@dataclass(slots=True)
class BrowserVisionPage:
    page_id: str
    page_url: str
    block_id: str
    recreated: bool = False


@dataclass(slots=True)
class HelpPage:
    page_id: str
    page_url: str


class NotionClient:
    def __init__(self, token: str, *, api_version: str = "2026-03-11", timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "User-Agent": "terminal4gptweb/0.1",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NotionClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{page_id}")

    def search_pages(self, query: str = "", *, limit: int = 10) -> list[NotionPageSearchResult]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        payload: dict[str, Any] = {
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": limit,
        }
        query = query.strip()
        if query:
            payload["query"] = query

        response = self._request("POST", "/search", json=payload)
        pages: list[NotionPageSearchResult] = []
        for item in response.get("results", []):
            if item.get("object") != "page" or not item.get("id"):
                continue
            pages.append(
                NotionPageSearchResult(
                    page_id=str(item["id"]),
                    title=page_title(item) or "(untitled)",
                    url=str(item.get("url", "")),
                )
            )
            if len(pages) >= limit:
                break
        return pages

    def get_block(self, block_id: str) -> dict[str, Any]:
        return self._request("GET", f"/blocks/{block_id}")

    def get_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            path = f"/blocks/{block_id}/children?page_size=100"
            if start_cursor:
                path += f"&start_cursor={start_cursor}"
            response = self._request("GET", path)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                return results
            start_cursor = response.get("next_cursor")
            if not start_cursor:
                return results

    def get_code_text(self, block_id: str) -> str:
        block = self.get_block(block_id)
        if not block_is_usable_code(block):
            raise NotionError(f"Block {block_id} is not an active code block.")
        return "".join(item.get("plain_text", "") for item in block.get("code", {}).get("rich_text", []))

    def update_code_block(self, block_id: str, text: str, *, language: str = "plain text") -> None:
        self._request("PATCH", f"/blocks/{block_id}", json={
            "code": {"rich_text": rich_text_payload(text), "language": language}
        })

    def archive_block(self, block_id: str) -> None:
        # Notion API 2026-03-11 removes blocks through DELETE. The returned
        # block is marked in_trash=true and can still be restored in Notion.
        self._request("DELETE", f"/blocks/{block_id}")

    def create_terminal_page(
        self,
        *,
        parent_page_id: str,
        title: str,
        terminal_text: str,
        input_text: str,
    ) -> CreatedTerminalPage:
        page = self._request("POST", "/pages", json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "text": {"content": title}}],
                }
            },
        })

        page_id = page["id"]
        children = self._request("PATCH", f"/blocks/{page_id}/children", json={
            "children": terminal_page_children(terminal_text, input_text)
        })
        terminal_id, input_id = _runtime_code_block_ids(children.get("results", []))

        return CreatedTerminalPage(
            page_id=page_id,
            page_url=page.get("url", ""),
            terminal_block_id=terminal_id,
            input_block_id=input_id,
        )

    def create_help_page(
        self,
        *,
        parent_page_id: str,
        title: str = "Terminal4GPTWeb Help",
    ) -> HelpPage:
        page = self._request("POST", "/pages", json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "text": {"content": title}}],
                }
            },
        })
        page_id = page["id"]
        self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={"children": help_page_children()},
        )
        return HelpPage(page_id=page_id, page_url=page.get("url", ""))

    def ensure_runtime_blocks(
        self,
        *,
        page_id: str,
        terminal_block_id: str,
        input_block_id: str,
        terminal_text: str,
        input_text: str,
    ) -> RuntimeBlocks:
        # The page is the durable anchor. If it is gone, silently creating a new
        # page elsewhere would be surprising, so page loss remains a hard error.
        self.get_page(page_id)

        terminal = self._try_get_block(terminal_block_id)
        input_block = self._try_get_block(input_block_id)
        children = self.get_block_children(page_id)
        anchors = find_runtime_anchors(children)

        if anchors:
            terminal_ok = block_is_usable_code(terminal) and runtime_block_is_in_place(
                children,
                anchor_id=anchors.terminal_anchor_id,
                block_id=terminal_block_id,
            )
            input_ok = block_is_usable_code(input_block) and runtime_block_is_in_place(
                children,
                anchor_id=anchors.input_anchor_id,
                block_id=input_block_id,
            )

            if terminal_ok and input_ok:
                return RuntimeBlocks(
                    terminal_block_id=terminal_block_id,
                    input_block_id=input_block_id,
                    recreated=False,
                )

            repaired = False
            new_terminal_id = terminal_block_id
            new_input_id = input_block_id

            # Repair only the broken side. A healthy runtime block keeps its
            # original Notion block ID and remains untouched.
            if not terminal_ok:
                if terminal is not None and not terminal.get("archived") and not terminal.get("in_trash"):
                    try:
                        self.archive_block(terminal_block_id)
                    except NotionError:
                        pass
                new_terminal_id = self.restore_runtime_block_at_anchor(
                    page_id=page_id,
                    anchor_id=anchors.terminal_anchor_id,
                    text=terminal_text,
                    language="plain text",
                )
                repaired = True

            if not input_ok:
                if input_block is not None and not input_block.get("archived") and not input_block.get("in_trash"):
                    try:
                        self.archive_block(input_block_id)
                    except NotionError:
                        pass
                new_input_id = self.restore_runtime_block_at_anchor(
                    page_id=page_id,
                    anchor_id=anchors.input_anchor_id,
                    text=input_text,
                    language="bash",
                )
                repaired = True

            return RuntimeBlocks(
                terminal_block_id=new_terminal_id,
                input_block_id=new_input_id,
                recreated=repaired,
            )

        # Legacy/fallback path if a user also deleted or substantially changed
        # the stable headings/description blocks. With no anchors, we cannot
        # reliably restore only one side to its original position.
        for block_id, block in (
            (terminal_block_id, terminal),
            (input_block_id, input_block),
        ):
            if block is not None and not block.get("archived") and not block.get("in_trash"):
                try:
                    self.archive_block(block_id)
                except NotionError:
                    pass

        return self.append_runtime_blocks(
            page_id=page_id,
            terminal_text=terminal_text,
            input_text=input_text,
        )

    def restore_runtime_block_at_anchor(
        self,
        *,
        page_id: str,
        anchor_id: str,
        text: str,
        language: str,
    ) -> str:
        response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": [code_block_payload(text, language=language)],
                "position": {
                    "type": "after_block",
                    "after_block": {"id": anchor_id},
                },
            },
        )

        try:
            return response["results"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise NotionError("Notion did not return the recreated runtime block ID.") from exc

    def append_runtime_blocks(
        self,
        *,
        page_id: str,
        terminal_text: str,
        input_text: str,
    ) -> RuntimeBlocks:
        children = self._request("PATCH", f"/blocks/{page_id}/children", json={
            "children": [
                heading_payload("Terminal"),
                paragraph_payload("Live PTY screen. Do not edit this block manually."),
                code_block_payload(terminal_text, language="plain text"),
                heading_payload("Input"),
                paragraph_payload(
                    "Input has no leading prompt. Normal text is sent after one Enter. "
                    "For TUI programs, use the key/control commands below when a real key press is required."
                ),
                code_block_payload(input_text, language="bash"),
                callout_payload("Runtime blocks were automatically recreated by Terminal4GPTWeb.", "♻️"),
            ]
        })
        terminal_id, input_id = _runtime_code_block_ids(children.get("results", []))
        return RuntimeBlocks(
            terminal_block_id=terminal_id,
            input_block_id=input_id,
            recreated=True,
        )

    def ensure_browser_vision_page(
        self,
        *,
        parent_page_id: str,
        page_id: str,
        block_id: str,
        idle_text: str,
    ) -> BrowserVisionPage:
        page: dict[str, Any] | None = None
        if page_id:
            try:
                page = self.get_page(page_id)
            except NotionError as exc:
                if not exc.is_not_found:
                    raise

        if page is not None and not page.get("archived") and not page.get("in_trash"):
            block = self._try_get_block(block_id) if block_id else None
            if block_is_usable_code(block):
                return BrowserVisionPage(
                    page_id=page_id,
                    page_url=page.get("url", ""),
                    block_id=block_id,
                    recreated=False,
                )

            if block is not None and not block.get("archived") and not block.get("in_trash"):
                self.archive_block(block_id)

            response = self._request(
                "PATCH",
                f"/blocks/{page_id}/children",
                json={"children": [code_block_payload(idle_text, language="plain text")]},
            )
            code_blocks = [
                item for item in response.get("results", [])
                if item.get("type") == "code"
            ]
            if not code_blocks:
                raise NotionError("Notion did not return the Browser Vision code block.")
            return BrowserVisionPage(
                page_id=page_id,
                page_url=page.get("url", ""),
                block_id=code_blocks[0]["id"],
                recreated=True,
            )

        vision_page = self._request(
            "POST",
            "/pages",
            json={
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "Browser Vision Payload"},
                            }
                        ],
                    }
                },
            },
        )
        new_page_id = vision_page["id"]
        response = self._request(
            "PATCH",
            f"/blocks/{new_page_id}/children",
            json={
                "children": [
                    callout_payload(
                        "Machine-readable compressed browser screenshot for GPT Vision. "
                        "Fetch this page, decode data_base64 as image/jpeg, and only act when "
                        "its observation_id matches the current Browser Status observation_id. "
                        "Do not edit this page manually.",
                        "👁️",
                    ),
                    code_block_payload(idle_text, language="plain text"),
                ]
            },
        )
        code_blocks = [
            item for item in response.get("results", [])
            if item.get("type") == "code"
        ]
        if not code_blocks:
            raise NotionError("Notion did not return the Browser Vision code block.")

        return BrowserVisionPage(
            page_id=new_page_id,
            page_url=vision_page.get("url", ""),
            block_id=code_blocks[0]["id"],
            recreated=True,
        )

    def ensure_browser_blocks(
        self,
        *,
        page_id: str,
        status_block_id: str,
        image_block_id: str,
        status_text: str,
    ) -> BrowserBlocks:
        self.get_page(page_id)
        children = self.get_block_children(page_id)
        anchors = find_browser_anchors(children)

        if anchors is None:
            return self.append_browser_blocks(page_id=page_id, status_text=status_text)

        status = self._try_get_block(status_block_id) if status_block_id else None
        status_ok = block_is_usable_code(status) and runtime_block_is_in_place(
            children,
            anchor_id=anchors.status_anchor_id,
            block_id=status_block_id,
        )

        new_status_id = status_block_id
        repaired = False
        if not status_ok:
            if status is not None and not status.get("archived") and not status.get("in_trash"):
                try:
                    self.archive_block(status_block_id)
                except NotionError:
                    pass
            new_status_id = self.restore_runtime_block_at_anchor(
                page_id=page_id,
                anchor_id=anchors.status_anchor_id,
                text=status_text,
                language="plain text",
            )
            repaired = True

        new_image_id = image_block_id
        if image_block_id:
            image = self._try_get_block(image_block_id)
            image_ok = block_is_usable_image(image) and runtime_block_is_in_place(
                children,
                anchor_id=anchors.screenshot_anchor_id,
                block_id=image_block_id,
            )
            if not image_ok:
                if image is not None and not image.get("archived") and not image.get("in_trash"):
                    try:
                        self.archive_block(image_block_id)
                    except NotionError:
                        pass
                new_image_id = ""
                repaired = True

        return BrowserBlocks(
            status_block_id=new_status_id,
            image_block_id=new_image_id,
            recreated=repaired,
        )

    def append_browser_blocks(self, *, page_id: str, status_text: str) -> BrowserBlocks:
        response = self._request("PATCH", f"/blocks/{page_id}/children", json={
            "children": [
                divider_payload(),
                heading_payload("Browser"),
                paragraph_payload(
                    "Playwright browser status. Coordinates use viewport-relative CSS pixels. "
                    "Use :b goto <url> or :b shot to observe. Mouse actions must use the latest "
                    "observation_id. For GPT Vision, fetch vision_page_url from Browser Status, "
                    "decode data_base64 as image/jpeg, and verify the payload observation_id matches."
                ),
                code_block_payload(status_text, language="plain text"),
                heading_payload("Browser Screenshot"),
                paragraph_payload(
                    "Latest Playwright viewport screenshot for GPT Vision. "
                    "The image is replaced after each browser action."
                ),
                heading_payload("Browser Saved Snapshots"),
                paragraph_payload(
                    "Temporary comparison captures. Use :b save [label] for the current viewport, "
                    ":b full [label] for a long page split into readable tiles, and :b clear-saved to remove them."
                ),
            ]
        })
        code_blocks = [item for item in response.get("results", []) if item.get("type") == "code"]
        if not code_blocks:
            raise NotionError("Notion did not return the Browser Status code block.")
        return BrowserBlocks(
            status_block_id=code_blocks[0]["id"],
            image_block_id="",
            recreated=True,
        )

    def ensure_browser_saved_section(self, *, page_id: str) -> str:
        children = self.get_block_children(page_id)
        anchor_id = find_browser_saved_anchor(children)
        if anchor_id:
            return anchor_id

        anchors = find_browser_anchors(children)
        if anchors is None:
            raise NotionError("Browser section anchors are missing.")

        live_images = browser_screenshot_image_ids(
            children,
            anchor_id=anchors.screenshot_anchor_id,
        )
        after_id = live_images[-1] if live_images else anchors.screenshot_anchor_id
        response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": [
                    heading_payload("Browser Saved Snapshots"),
                    paragraph_payload(
                        "Temporary comparison captures. Use :b save [label] for the current viewport, "
                        ":b full [label] for a long page split into readable tiles, and :b clear-saved to remove them."
                    ),
                ],
                "position": {
                    "type": "after_block",
                    "after_block": {"id": after_id},
                },
            },
        )
        results = response.get("results", [])
        for item in results:
            if item.get("type") == "paragraph" and item.get("id"):
                return str(item["id"])
        raise NotionError("Notion did not return the Browser Saved Snapshots anchor.")

    def append_browser_saved_images(
        self,
        *,
        page_id: str,
        images: list[tuple[bytes, str]],
    ) -> list[str]:
        if not images:
            return []

        anchor_id = self.ensure_browser_saved_section(page_id=page_id)
        payloads: list[dict[str, Any]] = []
        for index, (image_bytes, caption) in enumerate(images, start=1):
            file_upload_id = self.upload_file(
                filename=f"terminal4gptweb-saved-{index}.png",
                data=image_bytes,
                content_type="image/png",
            )
            payloads.append(image_block_payload(file_upload_id, caption=caption))

        response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": payloads,
                "position": {
                    "type": "after_block",
                    "after_block": {"id": anchor_id},
                },
            },
        )
        return [
            str(item["id"])
            for item in response.get("results", [])
            if item.get("type") == "image" and item.get("id")
        ]

    def clear_browser_saved_images(self, *, page_id: str) -> int:
        children = self.get_block_children(page_id)
        anchor_id = find_browser_saved_anchor(children)
        if not anchor_id:
            return 0

        image_ids = browser_screenshot_image_ids(children, anchor_id=anchor_id)
        for block_id in image_ids:
            self.archive_block(block_id)
        return len(image_ids)

    def clear_browser_images(self, *, page_id: str) -> bool:
        children = self.get_block_children(page_id)
        anchors = find_browser_anchors(children)
        if anchors is None:
            return False

        removed = False
        for block_id in browser_screenshot_image_ids(
            children,
            anchor_id=anchors.screenshot_anchor_id,
        ):
            self.archive_block(block_id)
            removed = True
        return removed

    def replace_browser_image(
        self,
        *,
        page_id: str,
        old_image_block_id: str,
        image_bytes: bytes,
        caption: str,
    ) -> str:
        children = self.get_block_children(page_id)
        anchors = find_browser_anchors(children)
        if anchors is None:
            raise NotionError("Browser Screenshot anchor is missing.")

        file_upload_id = self.upload_file(
            filename="terminal4gptweb-browser.png",
            data=image_bytes,
            content_type="image/png",
        )

        # Keep the screenshot section single-image. Archive the previous block
        # before inserting the replacement so a failed archive cannot silently
        # leave an ever-growing image history behind.
        if old_image_block_id:
            old = self._try_get_block(old_image_block_id)
            if old is not None and not old.get("archived") and not old.get("in_trash"):
                self.archive_block(old_image_block_id)

        # Also clean up stale image blocks left by an interrupted/older daemon.
        for stale_id in browser_screenshot_image_ids(
            children,
            anchor_id=anchors.screenshot_anchor_id,
        ):
            if stale_id != old_image_block_id:
                stale = self._try_get_block(stale_id)
                if stale is not None and not stale.get("archived") and not stale.get("in_trash"):
                    self.archive_block(stale_id)

        response = self._request(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={
                "children": [image_block_payload(file_upload_id, caption=caption)],
                "position": {
                    "type": "after_block",
                    "after_block": {"id": anchors.screenshot_anchor_id},
                },
            },
        )
        try:
            new_image_id = response["results"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise NotionError("Notion did not return the Browser Screenshot image block.") from exc

        return new_image_id

    def upload_file(self, *, filename: str, data: bytes, content_type: str) -> str:
        upload = self._request(
            "POST",
            "/file_uploads",
            json={
                "mode": "single_part",
                "filename": filename,
                "content_type": content_type,
            },
        )
        upload_id = upload.get("id")
        upload_url = upload.get("upload_url")
        if not upload_id or not upload_url:
            raise NotionError("Notion did not return a file upload ID and upload URL.")

        try:
            response = self._client.request(
                "POST",
                upload_url,
                files={"file": (filename, data, content_type)},
            )
        except httpx.HTTPError as exc:
            raise NotionError(f"Notion file upload failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                error = response.json()
                message = error.get("message") or response.text
                code = error.get("code")
            except ValueError:
                message = response.text
                code = None
            raise NotionError(
                f"Notion file upload {response.status_code}: {message}",
                status_code=response.status_code,
                code=code,
            )

        payload = response.json()
        if payload.get("status") not in {None, "uploaded"}:
            raise NotionError(f"Notion file upload did not complete: {payload.get('status')}")
        return str(upload_id)

    def _try_get_block(self, block_id: str) -> dict[str, Any] | None:
        try:
            return self.get_block(block_id)
        except NotionError as exc:
            if exc.is_not_found:
                return None
            raise

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = 0.75
        for attempt in range(6):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.HTTPError as exc:
                if attempt == 5:
                    raise NotionError(f"Notion request failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue

            if response.status_code < 400:
                return response.json()

            if response.status_code in {429, 503, 504, 529} and attempt < 5:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = max(float(retry_after), 0.25) if retry_after else delay
                except ValueError:
                    wait = delay
                time.sleep(wait)
                delay = min(delay * 2, 8.0)
                continue

            try:
                error = response.json()
                message = error.get("message") or response.text
                code = error.get("code")
            except ValueError:
                message = response.text
                code = None
            suffix = f" ({code})" if code else ""
            raise NotionError(
                f"Notion API {response.status_code}{suffix}: {message}",
                status_code=response.status_code,
                code=code,
            )

        raise NotionError("Notion request failed after retries.")


def page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties", {})
    if not isinstance(properties, dict):
        return ""

    for prop in properties.values():
        if not isinstance(prop, dict) or prop.get("type") != "title":
            continue
        items = prop.get("title", [])
        return "".join(str(item.get("plain_text", "")) for item in items).strip()
    return ""


def block_is_usable_image(block: dict[str, Any] | None) -> bool:
    return bool(
        block
        and block.get("type") == "image"
        and not block.get("archived", False)
        and not block.get("in_trash", False)
    )


def block_is_usable_code(block: dict[str, Any] | None) -> bool:
    return bool(
        block
        and block.get("type") == "code"
        and not block.get("archived", False)
        and not block.get("in_trash", False)
    )


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type:
        return ""
    content = block.get(block_type, {})
    return "".join(item.get("plain_text", "") for item in content.get("rich_text", []))


def find_runtime_anchors(children: list[dict[str, Any]]) -> RuntimeAnchors | None:
    terminal_anchor: str | None = None
    input_anchor: str | None = None
    section: str | None = None

    for block in children:
        if block.get("archived") or block.get("in_trash"):
            continue

        if block.get("type") == "heading_2":
            title = block_plain_text(block).strip()
            if title == "Terminal" and terminal_anchor is None:
                section = "terminal"
                continue
            if title == "Input" and input_anchor is None:
                section = "input"
                continue
            if section in {"terminal", "input"}:
                section = None

        if block.get("type") == "paragraph":
            if section == "terminal" and terminal_anchor is None:
                terminal_anchor = block.get("id")
                section = None
            elif section == "input" and input_anchor is None:
                input_anchor = block.get("id")
                section = None

        if terminal_anchor and input_anchor:
            return RuntimeAnchors(terminal_anchor, input_anchor)

    return None


def find_browser_saved_anchor(children: list[dict[str, Any]]) -> str | None:
    section = False
    for block in children:
        if block.get("archived") or block.get("in_trash"):
            continue
        if block.get("type") == "heading_2":
            section = block_plain_text(block).strip() == "Browser Saved Snapshots"
            continue
        if section and block.get("type") == "paragraph":
            return str(block.get("id", "")) or None
        if section and block.get("type") in {"heading_2", "child_page"}:
            return None
    return None


def find_browser_anchors(children: list[dict[str, Any]]) -> BrowserAnchors | None:
    status_anchor: str | None = None
    screenshot_anchor: str | None = None
    section: str | None = None

    for block in children:
        if block.get("archived") or block.get("in_trash"):
            continue

        if block.get("type") == "heading_2":
            title = block_plain_text(block).strip()
            if title == "Browser" and status_anchor is None:
                section = "status"
                continue
            if title == "Browser Screenshot" and screenshot_anchor is None:
                section = "screenshot"
                continue
            if section in {"status", "screenshot"}:
                section = None

        if block.get("type") == "paragraph":
            if section == "status" and status_anchor is None:
                status_anchor = block.get("id")
                section = None
            elif section == "screenshot" and screenshot_anchor is None:
                screenshot_anchor = block.get("id")
                section = None

        if status_anchor and screenshot_anchor:
            return BrowserAnchors(status_anchor, screenshot_anchor)

    return None


def browser_screenshot_image_ids(
    children: list[dict[str, Any]],
    *,
    anchor_id: str,
) -> list[str]:
    active = [
        block for block in children
        if not block.get("archived") and not block.get("in_trash")
    ]
    try:
        index = next(i for i, block in enumerate(active) if block.get("id") == anchor_id)
    except StopIteration:
        return []

    image_ids: list[str] = []
    for block in active[index + 1 :]:
        if block.get("type") in {"heading_2", "child_page"}:
            break
        if block.get("type") == "image" and block.get("id"):
            image_ids.append(block["id"])
    return image_ids


def runtime_block_is_in_place(
    children: list[dict[str, Any]],
    *,
    anchor_id: str,
    block_id: str,
) -> bool:
    active = [
        block for block in children
        if not block.get("archived") and not block.get("in_trash")
    ]
    ids = [block.get("id") for block in active]

    try:
        anchor_index = ids.index(anchor_id)
    except ValueError:
        return False

    return anchor_index + 1 < len(ids) and ids[anchor_index + 1] == block_id


def runtime_blocks_are_in_place(
    children: list[dict[str, Any]],
    *,
    terminal_anchor_id: str,
    input_anchor_id: str,
    terminal_block_id: str,
    input_block_id: str,
) -> bool:
    return (
        runtime_block_is_in_place(
            children,
            anchor_id=terminal_anchor_id,
            block_id=terminal_block_id,
        )
        and runtime_block_is_in_place(
            children,
            anchor_id=input_anchor_id,
            block_id=input_block_id,
        )
    )

def terminal_page_children(terminal_text: str, input_text: str) -> list[dict[str, Any]]:
    return [
        callout_payload(
            "For AI: Read the Terminal4GPTWeb Help page before using this control surface.",
            "🤖",
        ),
        callout_payload(
            "Live local terminal and browser control surface. Anything submitted in Input runs with the permissions of the local Linux/WSL user.",
            "⚠️",
        ),
        heading_payload("Terminal"),
        paragraph_payload("Live PTY screen. Do not edit this block manually."),
        code_block_payload(terminal_text, language="plain text"),
        heading_payload("Input"),
        paragraph_payload("Type one action and press Enter once to submit. Input is executed only when the text ends with a newline; if a command remains visible here instead of running, check the missing trailing newline first."),
        code_block_payload(input_text, language="bash"),
        divider_payload(),
        heading_payload("Quick Commands"),
        bulleted_payload("Shell command — pwd  (press Enter once)"),
        bulleted_payload("Key press — :k ENTER"),
        bulleted_payload("Ctrl key — :c C"),
        bulleted_payload("Browser open — :b goto https://example.com"),
        bulleted_payload("Browser screenshot — :b shot"),
        bulleted_payload("Save current browser view — :b save [label]"),
        bulleted_payload("Save long page as readable tiles — :b full [label]"),
        bulleted_payload("Clear saved browser captures — :b clear-saved"),
        bulleted_payload("Browser click — :b click <observation_id> <x> <y>"),
        paragraph_payload(
            "Open the Terminal4GPTWeb Help child page for agent instructions, full command reference, examples, and recovery."
        ),
    ]


def help_page_children() -> list[dict[str, Any]]:
    return [
        callout_payload(
            "Terminal4GPTWeb connects GPT Web to a persistent local PTY and a Playwright browser through Notion. This page is documentation; use the parent page for live control.",
            "ℹ️",
        ),
        heading_payload("For Humans"),
        paragraph_payload(
            "Use the parent Terminal4GPTWeb page. Read Terminal for current shell state and write commands in Input. "
            "Normal shell input is submitted by pressing Enter once. Merely writing command text is not enough: the Input text must end with a newline."
        ),
        bulleted_payload("Run in background: t4g daemon start"),
        bulleted_payload("Check status: t4g daemon status"),
        bulleted_payload("Restart daemon: t4g daemon restart"),
        bulleted_payload("Stop daemon: t4g daemon stop"),
        bulleted_payload("Diagnostics: t4g doctor"),
        bulleted_payload("Recreate deleted Notion pages: t4g reinit"),
        heading_payload("For GPT / Agents"),
        callout_payload(
            "Input submission rule: text is executed only when the actual Input content ends with a newline. In the Notion UI, press Enter once after the action. Through an API/connector, preserve a trailing \\n; for Markdown-style code-block edits, leave one blank line after the action before the closing code fence. If the command stays visible in Input instead of resetting, check this first.",
            "↩️",
        ),
        paragraph_payload(
            "Treat the parent page as a tool surface. Read Terminal before acting. Write exactly one command or control action to Input, "
            "wait for Input to reset, then read Terminal or Browser Status again before the next action."
        ),
        heading_payload("ChatGPT Connections"),
        bulleted_payload("Required for GPT Web control — connect Notion and grant ChatGPT access to the Terminal4GPTWeb control page and Help page."),
        bulleted_payload("Recommended for development — connect GitHub so GPT can read repository history, issues, pull requests, and code while using the local terminal for builds and tests."),
        bulleted_payload("Optional for operations — use ChatGPT scheduled tasks/automations, where available, to run recurring health checks through this Notion control surface."),
        paragraph_payload(
            "A useful development pattern is: GitHub for repository context and code review, Terminal4GPTWeb for local execution, "
            "and Playwright + Vision for browser E2E verification."
        ),
        heading_payload("Example Workflows"),
        bulleted_payload("Development — inspect a GitHub issue or diff, edit locally, run tests in Terminal, then verify the UI with Playwright."),
        bulleted_payload("Browser E2E — open the local app, inspect the screenshot with Vision, interact through coordinates/keyboard, and verify the resulting observation."),
        bulleted_payload("OPS — inspect process/container status, health endpoints, recent logs, disk/memory usage, and report only actionable failures."),
        bulleted_payload("Scheduled OPS — periodically ask GPT to inspect the Notion control surface, run a fixed health checklist, and notify only when a check fails."),
        bulleted_payload("Shell: write one command in Input and press Enter once. Example: pwd"),
        bulleted_payload("Never assume a browser coordinate from an old screenshot. Use the latest Browser Status observation_id."),
        bulleted_payload("For visual browser reasoning, fetch vision_page_url, decode data_base64 as image/jpeg, and verify observation_id matches."),
        bulleted_payload("After each browser action, wait for Browser Status to return to ready or failed before continuing."),
        heading_payload("Terminal Commands"),
        bulleted_payload("Normal shell command — <command>, then Enter once. Example: git status"),
        bulleted_payload("Special key — :key NAME or :k NAME. Example: :k ENTER. Control commands must be submitted as their own Input action; do not append :k ENTER to ordinary text."),
        bulleted_payload("Ctrl combination — :ctrl KEY or :c KEY. Example: :c C"),
        bulleted_payload(r"Raw input — :send TEXT or :s TEXT. Escapes: \e, \x1b, \n, \r, \t, \\"),
        bulleted_payload("Resize PTY — :resize COLSxROWS or :rs COLSxROWS. Example: :rs 140x50"),
        heading_payload("Terminal Keys"),
        paragraph_payload(
            "Supported names include ENTER/RETURN/RET/ENT, BACKSPACE/BS/BKSP, ESC/ESCAPE, DELETE/DEL, INSERT/INS, "
            "PAGEUP/PGUP, PAGEDOWN/PGDN, UP, DOWN, LEFT, RIGHT, HOME, END, TAB, and F1 through F12."
        ),
        paragraph_payload(
            "Immediate tokens ^C, ^D, ^Z, ^L and ^\\ are recognized without the extra blank-line submit."
        ),
        heading_payload("Browser Commands"),
        bulleted_payload("Open URL — :b goto <url> (alias: :b open <url>)"),
        bulleted_payload("Fresh observation — :b shot"),
        bulleted_payload("Save current viewport for comparison — :b save [label]"),
        bulleted_payload("Save a long page as viewport-height tiles — :b full [label]"),
        bulleted_payload("Clear temporary saved captures — :b clear-saved"),
        bulleted_payload("Move / hover — :b move <observation_id> <x> <y>"),
        bulleted_payload("Click — :b click <observation_id> <x> <y>"),
        bulleted_payload("Drag — :b drag <observation_id> <x1> <y1> <x2> <y2>"),
        bulleted_payload("Scroll — :b scroll <dx> <dy> (positive dy scrolls down)"),
        bulleted_payload("Type literal text into the focused element — :b type <text>"),
        bulleted_payload("Press browser key — :b key <key>, e.g. Enter, Tab, Escape, ArrowDown, Control+A"),
        bulleted_payload("Back — :b back"),
        bulleted_payload("Reload — :b reload"),
        heading_payload("Browser Control Loop"),
        paragraph_payload(
            "Every successful browser action publishes a new observation after the configured settle delay. "
            "Treat each screenshot as immutable: read Browser Status, require status ready, note observation_id, "
            "inspect the matching screenshot or Vision payload, issue exactly one action, then wait for the next ready observation."
        ),
        bulleted_payload("Coordinate actions move/click/drag require the latest observation_id and reject stale IDs with STALE_OBSERVATION."),
        bulleted_payload("Scroll/type/key/navigation do not take an observation_id, but they still create a new observation; wait for it before the next action."),
        bulleted_payload("Mouse coordinates are viewport-relative CSS pixels. Browser Status scroll is page metadata; click coordinates remain relative to the visible viewport."),
        bulleted_payload("The live Browser Screenshot stays viewport-only for coordinate accuracy. Use :b full [label] to save a long page as multiple readable tiles instead of one tiny full-page image."),
        bulleted_payload("Use :b save [label] before navigating away when several page results need side-by-side comparison. Saved captures are temporary and are cleared on daemon restart or with :b clear-saved."),
        bulleted_payload("For hover UI, send :b move, inspect the newly rendered hover state, then click using the new observation_id."),
        heading_payload("Browser Focus and Keys"),
        paragraph_payload(
            ":b type inserts literal text into the currently focused element and does not press Enter. "
            "A reliable form flow is click field → wait for ready → type → wait → key Tab/Enter → wait."
        ),
        bulleted_payload("Playwright key examples — Enter, Tab, Escape, ArrowUp/ArrowDown, Shift+Tab, Control+A."),
        bulleted_payload("With show_cursor_overlay enabled, the last mouse position appears as a marker in subsequent screenshots."),
        heading_payload("Browser Failure Recovery"),
        paragraph_payload(
            "Browser Status transitions idle → running → ready, or running → failed. On failed, read command/error and do not keep using old coordinates. "
            "If page state is uncertain, run :b shot and continue only from the new ready observation."
        ),
        bulleted_payload("STALE_OBSERVATION — reread Browser Status/Screenshot and use the new observation_id."),
        bulleted_payload("Coordinate outside viewport — scroll or choose a point inside the configured viewport."),
        bulleted_payload("Late SPA/async render — run :b shot to recapture current state without interacting."),
        bulleted_payload("Vision payload observation_id must match Browser Status before using it for coordinate reasoning."),
        heading_payload("Common TUI Examples"),
        bulleted_payload("Codex / Claude Code — submit the text first. If it appears but does not submit, use a new Terminal4GPTWeb Input action containing only :k ENTER; do not append :k ENTER to the text."),
        bulleted_payload("nano — save :c O, confirm :k ENTER, exit :c X, search :c W."),
        bulleted_payload(r"vim — save and quit with :s \e:wq\r"),
        heading_payload("Recovery"),
        paragraph_payload(
            "If only Terminal or Input is deleted, the running daemon repairs the missing runtime block automatically. "
            "If the entire Terminal4GPTWeb page is deleted, stop the daemon if needed and run t4g reinit. "
            "The command recreates the main page, Help page, Browser Vision page, and runtime block IDs using the saved local configuration."
        ),
        bulleted_payload("Deleted runtime block only — wait for self-healing or run t4g daemon restart."),
        bulleted_payload("Deleted whole Notion page — run t4g reinit, then t4g daemon restart."),
        heading_payload("Security"),
        paragraph_payload(
            "The PTY sandbox is optional. With sandbox.enabled = true the shell runs inside "
            "Anthropic Sandbox Runtime (srt), which enforces filesystem, network, and credential rules."
        ),
        bulleted_payload("Unrestricted PTY — enabled = false (srt not required)"),
        bulleted_payload("Host view, writable — enabled = true, read_only = false, workspace = false"),
        bulleted_payload("Read-only host view — enabled = true, read_only = true"),
        bulleted_payload("Workspace isolation — enabled = true, workspace = true, plus workspace_path (read_only = true makes it read-only)"),
        bulleted_payload("Writes are denied outside allowed paths; extra writable paths come from allow_write, exceptions from deny_write."),
        bulleted_payload("Network is blocked except allowed_domains. A blocked request returns 'Connection blocked by network allowlist'."),
        bulleted_payload("Masked credentials appear as fake_value_<uuid> inside the shell; srt swaps in the real value only on requests to allowed hosts."),
        bulleted_payload("Inside the sandbox, a server started in the shell is not reachable from the Playwright browser, which runs outside the sandbox network."),
        callout_payload(
            "Even with sandboxing, do not send sudo passwords, API keys, SSH private keys, or other secrets through Notion Input. Credential masking protects configured files and environment variables; it is not a universal secret scanner.",
            "🔐",
        ),
    ]

def rich_text_payload(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    if len(chunks) > MAX_RICH_TEXT_ITEMS:
        max_chars = MAX_RICH_TEXT_CHUNK * MAX_RICH_TEXT_ITEMS
        text = text[-max_chars:]
        chunks = [text[i:i + MAX_RICH_TEXT_CHUNK] for i in range(0, len(text), MAX_RICH_TEXT_CHUNK)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _simple_rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text}}]


def code_block_payload(text: str, *, language: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {"caption": [], "rich_text": rich_text_payload(text), "language": language},
    }


def image_block_payload(file_upload_id: str, *, caption: str = "") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "image",
        "image": {
            "caption": _simple_rich_text(caption) if caption else [],
            "type": "file_upload",
            "file_upload": {"id": file_upload_id},
        },
    }


def heading_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _simple_rich_text(text)},
    }


def paragraph_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _simple_rich_text(text)},
    }


def bulleted_payload(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _simple_rich_text(text)},
    }


def callout_payload(text: str, emoji: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _simple_rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }


def divider_payload() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _runtime_code_block_ids(results: list[dict[str, Any]]) -> tuple[str, str]:
    code_blocks = [item for item in results if item.get("type") == "code"]
    if len(code_blocks) < 2:
        raise NotionError("Notion did not return the two runtime code blocks.")
    return code_blocks[0]["id"], code_blocks[1]["id"]


def parse_page_id(value: str) -> str:
    compact = value.strip()
    uuid_match = re.fullmatch(
        r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}",
        compact,
    )
    if uuid_match:
        return _hyphenate_uuid(re.sub(r"-", "", compact))

    matches = re.findall(r"[0-9a-fA-F]{32}", compact)
    if not matches:
        raise ValueError("Could not find a Notion page ID in the provided value.")
    return _hyphenate_uuid(matches[-1])


def _hyphenate_uuid(value: str) -> str:
    raw = value.replace("-", "")
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
