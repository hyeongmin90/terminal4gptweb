from __future__ import annotations

import re
import selectors
from dataclasses import dataclass, replace
import signal
import time
from pathlib import Path

from .browser import BrowserController, BrowserError, BrowserObservation, parse_browser_command
from .config import AppConfig, DEFAULT_CONFIG_PATH, TerminalPageSettings, write_config
from .notion import NotionClient, NotionError, page_title
from .protocol import InputAction, InputKind, extract_submission
from .sandbox import SandboxUnavailableError
from .terminal import PTYSession


@dataclass(slots=True)
class TerminalRuntime:
    index: int
    name: str
    page: TerminalPageSettings
    session: PTYSession
    last_input_written: str = ""
    last_terminal_written: str = ""
    dirty: bool = True
    ended_reported: bool = False


# Keep routine Input polling below the standard Notion connection budget and
# leave headroom for terminal renders, health checks, and browser updates.
MIN_INPUT_POLL_SLOT = 0.6


def input_poll_slot(count: int, poll_interval: float) -> float:
    return max(poll_interval / count, MIN_INPUT_POLL_SLOT)


class TerminalDaemon:
    def __init__(
        self,
        config: AppConfig,
        *,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path).expanduser()
        self.notion = NotionClient(config.notion.token, api_version=config.notion.api_version)
        self.browser = BrowserController(config.browser)
        self.selector = selectors.DefaultSelector()
        self.runtimes: list[TerminalRuntime] = []
        self._stop_requested = False

    @property
    def input_prompt(self) -> str:
        return self.config.terminal.input_prompt

    def request_stop(self) -> None:
        self._stop_requested = True

    def _ensure_terminal_pages(self) -> None:
        pages = self.config.notion.terminal_pages
        if not pages:
            pages.append(
                TerminalPageSettings(
                    page_id=self.config.notion.page_id,
                    terminal_block_id=self.config.notion.terminal_block_id,
                    input_block_id=self.config.notion.input_block_id,
                    page_url=self.config.notion.page_url,
                )
            )

        if self.config.terminal.count > len(pages):
            parent_page_id = self.config.notion.parent_page_id.strip()
            if not parent_page_id:
                raise RuntimeError(
                    "terminal.count exceeds the configured Notion terminal pages, but "
                    "notion.parent_page_id is missing. Run `t4g reinit` once to rebuild "
                    "the multi-terminal page set."
                )
            for index in range(len(pages), self.config.terminal.count):
                name = self.config.terminal.names[index]
                created = self.notion.create_terminal_page(
                    parent_page_id=parent_page_id,
                    title=name,
                    terminal_text=(
                        f"Terminal4GPTWeb · {name}\n\n"
                        "Local PTY is not connected yet. Run: t4g daemon start"
                    ),
                    input_text=self.input_prompt,
                )
                pages.append(
                    TerminalPageSettings(
                        page_id=created.page_id,
                        terminal_block_id=created.terminal_block_id,
                        input_block_id=created.input_block_id,
                        page_url=created.page_url,
                    )
                )
            write_config(self.config, self.config_path)

        active_pages = pages[: self.config.terminal.count]
        for index, page in enumerate(active_pages):
            self.notion.get_page(page.page_id)
            self.notion.update_page_title(page.page_id, self.config.terminal.names[index])

        primary = active_pages[0]
        self.config.notion.page_id = primary.page_id
        self.config.notion.terminal_block_id = primary.terminal_block_id
        self.config.notion.input_block_id = primary.input_block_id
        self.config.notion.page_url = primary.page_url

    def _build_runtimes(self) -> None:
        self.runtimes = [
            TerminalRuntime(
                index=index,
                name=self.config.terminal.names[index],
                page=page,
                # PTYSession.resize() mutates TerminalSettings. Give every
                # terminal its own settings object so resizing one PTY cannot
                # change another PTY's render dimensions.
                session=PTYSession(replace(self.config.terminal)),
            )
            for index, page in enumerate(
                self.config.notion.terminal_pages[: self.config.terminal.count]
            )
        ]

    def run(self) -> None:
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda _signum, _frame: self.request_stop())
        try:
            self._ensure_terminal_pages()
            self._build_runtimes()

            started: list[TerminalRuntime] = []
            try:
                for runtime in self.runtimes:
                    runtime.session.start()
                    started.append(runtime)
                    self.selector.register(
                        runtime.session.fileno(),
                        selectors.EVENT_READ,
                        data=runtime.index,
                    )
            except SandboxUnavailableError as exc:
                self._report_startup_failure(f"[SANDBOX UNAVAILABLE]\n{exc}")
                for runtime in started:
                    runtime.session.close()
                raise

            self._health_check()
            self._reset_browser_surface()
            for runtime in self.runtimes:
                self._reset_input(runtime)
                self._write_terminal(runtime, force=True)

            now = time.monotonic()
            poll_cursor = 0
            health_cursor = 0
            poll_slot = input_poll_slot(
                len(self.runtimes),
                self.config.terminal.poll_interval,
            )
            next_poll = now
            next_render = now
            next_health = now + self.config.terminal.health_check_interval

            while not self._stop_requested and any(
                runtime.session.is_alive() for runtime in self.runtimes
            ):
                now = time.monotonic()
                next_due = min(next_poll, next_render, next_health)
                timeout = max(0.0, next_due - now)
                events = self.selector.select(timeout=min(timeout, 0.25))
                for key, _mask in events:
                    runtime = self.runtimes[key.data]
                    if runtime.session.read_ready():
                        runtime.dirty = True

                now = time.monotonic()
                if now >= next_poll:
                    runtime = self.runtimes[poll_cursor]
                    if runtime.session.is_alive():
                        self._poll_input(runtime)
                    poll_cursor = (poll_cursor + 1) % len(self.runtimes)
                    next_poll = now + poll_slot

                if now >= next_render:
                    for runtime in self.runtimes:
                        self._write_terminal(runtime)
                    next_render = now + self.config.terminal.refresh_interval

                for runtime in self.runtimes:
                    if not runtime.session.is_alive() and not runtime.ended_reported:
                        self._mark_session_ended(runtime)

                if now >= next_health:
                    runtime = self.runtimes[health_cursor]
                    self._health_check_runtime(runtime)
                    if health_cursor == 0:
                        self._health_check_browser()
                    health_cursor = (health_cursor + 1) % len(self.runtimes)
                    next_health = now + self.config.terminal.health_check_interval

            if self._stop_requested:
                for runtime in self.runtimes:
                    if runtime.session.is_alive():
                        runtime.session.send_control("C")
                        time.sleep(0.02)
                        runtime.session.close()
                    if not runtime.ended_reported:
                        try:
                            self.notion.update_code_block(
                                runtime.page.input_block_id,
                                "[DAEMON STOPPED] Start with: t4g daemon start",
                                language="plain text",
                            )
                        except NotionError:
                            pass
            else:
                for runtime in self.runtimes:
                    if not runtime.ended_reported:
                        self._mark_session_ended(runtime)
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            try:
                self.selector.close()
            finally:
                self.browser.close()
                for runtime in self.runtimes:
                    runtime.session.close()
                self.notion.close()

    def _report_startup_failure(self, text: str) -> None:
        for page in self.config.notion.terminal_pages[: self.config.terminal.count]:
            try:
                self.notion.update_code_block(
                    page.input_block_id,
                    text,
                    language="plain text",
                )
            except NotionError:
                pass

    def _poll_input(self, runtime: TerminalRuntime) -> None:
        try:
            text = self.notion.get_code_text(runtime.page.input_block_id)
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks(runtime)
                return
            print(f"[notion:{runtime.name}] input poll failed: {exc}")
            return

        action, should_reset = extract_submission(text, runtime.last_input_written)
        if action is None:
            return

        try:
            self._dispatch(runtime, action)
        except Exception as exc:
            print(f"[input:{runtime.name}] {exc}")
            runtime.dirty = True
        finally:
            if should_reset:
                self._reset_input(runtime)

    def _dispatch(self, runtime: TerminalRuntime, action: InputAction) -> None:
        if action.kind is InputKind.NONE:
            return
        if action.kind is InputKind.LINE:
            runtime.session.send_line(action.value)
            return
        if action.kind is InputKind.RAW:
            runtime.session.send_text(action.value)
            return
        if action.kind is InputKind.CONTROL:
            runtime.session.send_control(action.value)
            return
        if action.kind is InputKind.KEY:
            runtime.session.send_key(action.value)
            return
        if action.kind is InputKind.RESIZE:
            assert action.columns is not None and action.rows is not None
            runtime.session.resize(action.columns, action.rows)
            runtime.dirty = True
            return
        if action.kind is InputKind.BROWSER:
            if runtime.index != 0:
                raise ValueError(
                    "Browser commands are available on the first terminal page only. "
                    f"Use {self.config.terminal.names[0]!r} for :b commands."
                )
            self._handle_browser(action.value)
            return
        raise ValueError(f"Unhandled input action: {action.kind}")

    def _handle_browser(self, command: str) -> None:
        self._ensure_browser_blocks()
        self._set_browser_status(
            "status: running\n"
            f"command: {command}\n"
            f"viewport: {self.config.browser.width}x{self.config.browser.height}\n"
        )
        try:
            name, args = parse_browser_command(command)
            if name == "save":
                self._save_browser_view(args)
                return
            if name == "full":
                self._save_browser_full_page(args)
                return
            if name == "full-tiles":
                self._save_browser_full_page_tiles(args)
                return
            if name == "clear-saved":
                if args:
                    raise BrowserError("Usage: :b clear-saved")
                removed = self.notion.clear_browser_saved_images(
                    page_id=self.config.notion.page_id
                )
                observation = self.browser.last_observation
                if observation is None:
                    self._set_browser_status(
                        self._browser_idle_status()
                        + f"saved_cleared: {removed}\n"
                    )
                else:
                    self._set_browser_status(
                        self._browser_ready_status(
                            observation,
                            extra_lines=[f"saved_cleared: {removed}"],
                        )
                    )
                return

            observation = self.browser.execute(command)
            self._publish_browser_observation(observation)
        except Exception as exc:
            try:
                self._set_browser_status(
                    "status: failed\n"
                    f"command: {command}\n"
                    f"error: {exc}\n"
                    f"viewport: {self.config.browser.width}x{self.config.browser.height}\n"
                )
            except Exception as status_exc:
                print(f"[notion] browser failure status update failed: {status_exc}")
            raise

    def _save_browser_view(self, args: list[str]) -> None:
        observation = self.browser.last_observation
        if observation is None:
            raise BrowserError("No browser observation exists yet. Run :b shot first.")
        label = self._browser_capture_label(args, observation)
        self.notion.append_browser_saved_images(
            page_id=self.config.notion.page_id,
            images=[
                (
                    observation.screenshot,
                    f"{label} · {observation.observation_id} · viewport",
                )
            ],
        )
        self._set_browser_status(
            self._browser_ready_status(
                observation,
                extra_lines=[f"saved_view: {label}"],
            )
        )

    def _save_browser_full_page(self, args: list[str]) -> None:
        previous = self.browser.last_observation
        if previous is None:
            raise BrowserError("No browser observation exists yet. Run :b shot first.")
        label = self._browser_capture_label(args, previous)
        screenshot = self.browser.capture_full_page()
        self.notion.append_browser_saved_images(
            page_id=self.config.notion.page_id,
            images=[(screenshot, f"{label} · full-width")],
        )
        observation = self.browser.observe()
        self._publish_browser_observation(
            observation,
            extra_lines=[f"saved_full: {label}", "saved_full_mode: single"],
        )

    def _save_browser_full_page_tiles(self, args: list[str]) -> None:
        previous = self.browser.last_observation
        if previous is None:
            raise BrowserError("No browser observation exists yet. Run :b shot first.")
        label = self._browser_capture_label(args, previous)
        tiles = self.browser.capture_full_page_tiles()
        images = [
            (
                tile.screenshot,
                f"{label} · full {tile.index}/{tile.total} · y={tile.y}",
            )
            for tile in tiles
        ]
        self.notion.append_browser_saved_images(
            page_id=self.config.notion.page_id,
            images=images,
        )
        observation = self.browser.observe()
        self._publish_browser_observation(
            observation,
            extra_lines=[
                f"saved_full_tiles: {label}",
                f"saved_tiles: {len(tiles)}",
            ],
        )

    @staticmethod
    def _browser_capture_label(
        args: list[str],
        observation: BrowserObservation,
    ) -> str:
        label = " ".join(args).strip()
        if not label:
            label = observation.title.strip() or observation.url.strip() or observation.observation_id
        label = " ".join(label.split())
        return label[:120]

    def _publish_browser_observation(
        self,
        observation: BrowserObservation,
        *,
        extra_lines: list[str] | None = None,
    ) -> None:
        new_image_id = self.notion.replace_browser_image(
            page_id=self.config.notion.page_id,
            old_image_block_id=self.config.notion.browser_image_block_id,
            image_bytes=observation.screenshot,
            caption=observation.observation_id,
        )
        if new_image_id != self.config.notion.browser_image_block_id:
            self.config.notion.browser_image_block_id = new_image_id
            write_config(self.config, self.config_path)

        cursor = "none"
        if observation.cursor_x is not None and observation.cursor_y is not None:
            cursor = f"{observation.cursor_x:g},{observation.cursor_y:g}"

        self._publish_browser_vision(observation)

        vision_status = "disabled"
        vision_page = ""
        if self.config.browser.vision_enabled:
            vision_status = f"ready (jpeg quality {observation.vision_quality})"
            vision_page = self.config.notion.browser_vision_page_url

        self._set_browser_status(
            self._browser_ready_status(
                observation,
                cursor=cursor,
                vision_status=vision_status,
                vision_page=vision_page,
                extra_lines=extra_lines,
            )
        )

    def _browser_ready_status(
        self,
        observation: BrowserObservation,
        *,
        cursor: str | None = None,
        vision_status: str | None = None,
        vision_page: str | None = None,
        extra_lines: list[str] | None = None,
    ) -> str:
        if cursor is None:
            cursor = "none"
            if observation.cursor_x is not None and observation.cursor_y is not None:
                cursor = f"{observation.cursor_x:g},{observation.cursor_y:g}"
        if vision_status is None:
            vision_status = "disabled"
            if self.config.browser.vision_enabled:
                vision_status = f"ready (jpeg quality {observation.vision_quality})"
        if vision_page is None:
            vision_page = (
                self.config.notion.browser_vision_page_url
                if self.config.browser.vision_enabled
                else ""
            )

        text = (
            "status: ready\n"
            f"observation_id: {observation.observation_id}\n"
            f"url: {observation.url}\n"
            f"title: {observation.title}\n"
            f"viewport: {observation.width}x{observation.height}\n"
            f"scroll: {observation.scroll_x:g},{observation.scroll_y:g}\n"
            f"cursor: {cursor}\n"
            f"vision: {vision_status}\n"
            f"vision_page_url: {vision_page}\n"
            f"created_at: {observation.created_at}\n"
        )
        if extra_lines:
            text += "".join(f"{line}\n" for line in extra_lines)
        return text

    def _publish_browser_vision(self, observation: BrowserObservation) -> None:
        if not self.config.browser.vision_enabled:
            return
        if not observation.vision_base64:
            raise BrowserError("Vision payload is enabled but the observation has no JPEG payload.")

        self._ensure_browser_vision_page()
        payload = (
            f"observation_id: {observation.observation_id}\n"
            "mime: image/jpeg\n"
            "encoding: base64\n"
            f"viewport: {observation.width}x{observation.height}\n"
            f"quality: {observation.vision_quality}\n"
            "data_base64:\n"
            f"{observation.vision_base64}\n"
        )
        self.notion.update_code_block(
            self.config.notion.browser_vision_block_id,
            payload,
            language="plain text",
        )

    def _vision_idle_status(self) -> str:
        return (
            "status: idle\n"
            "mime: image/jpeg\n"
            "encoding: base64\n"
            "data_base64:\n"
        )

    def _ensure_browser_vision_page(self) -> None:
        if not self.config.browser.vision_enabled:
            return
        vision = self.notion.ensure_browser_vision_page(
            parent_page_id=self.config.notion.page_id,
            page_id=self.config.notion.browser_vision_page_id,
            block_id=self.config.notion.browser_vision_block_id,
            idle_text=self._vision_idle_status(),
        )
        changed = (
            vision.recreated
            or vision.page_id != self.config.notion.browser_vision_page_id
            or vision.block_id != self.config.notion.browser_vision_block_id
            or vision.page_url != self.config.notion.browser_vision_page_url
        )
        self.config.notion.browser_vision_page_id = vision.page_id
        self.config.notion.browser_vision_block_id = vision.block_id
        self.config.notion.browser_vision_page_url = vision.page_url
        if changed:
            write_config(self.config, self.config_path)
            print("[notion] browser vision payload page created or repaired.")

    def _reset_browser_surface(self) -> None:
        try:
            removed = self.notion.clear_browser_images(page_id=self.config.notion.page_id)
            self.notion.clear_browser_saved_images(page_id=self.config.notion.page_id)
            if removed or self.config.notion.browser_image_block_id:
                self.config.notion.browser_image_block_id = ""
                write_config(self.config, self.config_path)
            if self.config.browser.vision_enabled:
                self._ensure_browser_vision_page()
                self.notion.update_code_block(
                    self.config.notion.browser_vision_block_id,
                    self._vision_idle_status(),
                    language="plain text",
                )
            self._set_browser_status(self._browser_idle_status())
        except NotionError as exc:
            print(f"[notion] browser surface reset failed: {exc}")

    def _browser_idle_status(self) -> str:
        vision_page = (
            self.config.notion.browser_vision_page_url
            if self.config.browser.vision_enabled
            else ""
        )
        return (
            "status: idle\n"
            "browser: not started\n"
            f"viewport: {self.config.browser.width}x{self.config.browser.height}\n"
            f"vision_page_url: {vision_page}\n"
            "hint: :b goto <url> or :b shot\n"
        )

    def _set_browser_status(self, text: str) -> None:
        block_id = self.config.notion.browser_status_block_id
        if not block_id:
            self._ensure_browser_blocks()
            block_id = self.config.notion.browser_status_block_id
        try:
            self.notion.update_code_block(block_id, text, language="plain text")
        except NotionError as exc:
            if exc.is_not_found:
                self._ensure_browser_blocks()
                self.notion.update_code_block(
                    self.config.notion.browser_status_block_id,
                    text,
                    language="plain text",
                )
                return
            raise

    def _ensure_browser_blocks(self) -> None:
        blocks = self.notion.ensure_browser_blocks(
            page_id=self.config.notion.page_id,
            status_block_id=self.config.notion.browser_status_block_id,
            image_block_id=self.config.notion.browser_image_block_id,
            status_text=self._browser_idle_status(),
        )
        if blocks.recreated:
            self.config.notion.browser_status_block_id = blocks.status_block_id
            self.config.notion.browser_image_block_id = blocks.image_block_id
            write_config(self.config, self.config_path)
            print("[notion] browser status/screenshot surface created or repaired.")

        self.notion.ensure_browser_saved_section(page_id=self.config.notion.page_id)

    def _reset_input(self, runtime: TerminalRuntime) -> None:
        self._set_input(runtime, self.input_prompt)

    def _set_input(self, runtime: TerminalRuntime, text: str) -> None:
        try:
            self.notion.update_code_block(
                runtime.page.input_block_id,
                text,
                language="bash",
            )
            runtime.last_input_written = text
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks(runtime)
                return
            print(f"[notion:{runtime.name}] input update failed: {exc}")

    def _write_terminal(
        self,
        runtime: TerminalRuntime,
        *,
        force: bool = False,
        suffix: str = "",
    ) -> None:
        if not force and not runtime.dirty:
            return
        text = sanitize_terminal_for_notion(runtime.session.render() + suffix)
        if not force and text == runtime.last_terminal_written:
            runtime.dirty = False
            return
        try:
            self.notion.update_code_block(
                runtime.page.terminal_block_id,
                text,
                language="plain text",
            )
            runtime.last_terminal_written = text
            runtime.dirty = False
        except NotionError as exc:
            if exc.is_not_found:
                self._recover_runtime_blocks(runtime)
                return
            print(f"[notion:{runtime.name}] terminal update failed: {exc}")

    def _mark_session_ended(self, runtime: TerminalRuntime) -> None:
        try:
            self.selector.unregister(runtime.session.fileno())
        except Exception:
            pass
        runtime.session.read_ready()
        runtime.dirty = True
        self._write_terminal(
            runtime,
            force=True,
            suffix="\n\n[Terminal4GPTWeb: shell session ended]",
        )
        try:
            self.notion.update_code_block(
                runtime.page.input_block_id,
                "[SESSION ENDED] Restart with: t4g daemon restart",
                language="plain text",
            )
        except NotionError:
            pass
        runtime.ended_reported = True

    def _health_check(self) -> None:
        for runtime in self.runtimes:
            self._health_check_runtime(runtime)
        self._health_check_browser()

    def _health_check_runtime(self, runtime: TerminalRuntime) -> None:
        try:
            self._ensure_runtime_blocks(runtime)
        except NotionError as exc:
            if exc.is_not_found:
                raise RuntimeError(
                    f"The Notion terminal page {runtime.name!r} no longer exists or "
                    "is not accessible. Run `t4g reinit` if the page was deleted."
                ) from exc
            print(f"[notion:{runtime.name}] runtime block health check failed: {exc}")

    def _health_check_browser(self) -> None:
        try:
            self._ensure_browser_blocks()
            self._ensure_browser_vision_page()
        except NotionError as exc:
            print(f"[notion] browser surface health check failed: {exc}")

    def _recover_runtime_blocks(self, runtime: TerminalRuntime) -> None:
        try:
            self._ensure_runtime_blocks(runtime)
        except NotionError as exc:
            if exc.is_not_found:
                raise RuntimeError(
                    f"The Notion terminal page {runtime.name!r} no longer exists or "
                    "is not accessible. Run `t4g reinit` if the page was deleted."
                ) from exc
            print(f"[notion:{runtime.name}] runtime block recovery failed: {exc}")

    def _ensure_runtime_blocks(self, runtime: TerminalRuntime) -> None:
        terminal_text = sanitize_terminal_for_notion(runtime.session.render())
        input_text = self.input_prompt
        blocks = self.notion.ensure_runtime_blocks(
            page_id=runtime.page.page_id,
            terminal_block_id=runtime.page.terminal_block_id,
            input_block_id=runtime.page.input_block_id,
            terminal_text=terminal_text,
            input_text=input_text,
        )
        if not blocks.recreated:
            return

        runtime.page.terminal_block_id = blocks.terminal_block_id
        runtime.page.input_block_id = blocks.input_block_id
        if runtime.index == 0:
            self.config.notion.terminal_block_id = blocks.terminal_block_id
            self.config.notion.input_block_id = blocks.input_block_id
        write_config(self.config, self.config_path)

        runtime.last_terminal_written = terminal_text
        runtime.last_input_written = input_text
        runtime.dirty = False

        print(
            f"[notion:{runtime.name}] one or more runtime blocks were missing, "
            "invalid, or misplaced."
        )
        print(
            f"[notion:{runtime.name}] repaired only the affected runtime block(s) "
            "and updated config.toml."
        )



_BACKTICK_RUN = re.compile(r"`{3,}")


def sanitize_terminal_for_notion(text: str) -> str:
    """Prevent terminal output from becoming Markdown fences in connector serialization."""
    def split_run(match: re.Match[str]) -> str:
        run = match.group(0)
        return "\u00a0".join(run[i : i + 2] for i in range(0, len(run), 2))

    return _BACKTICK_RUN.sub(split_run, text)
