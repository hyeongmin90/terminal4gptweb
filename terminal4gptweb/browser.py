from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from math import ceil

from PIL import Image

from .config import BrowserSettings


class BrowserError(RuntimeError):
    pass


MAX_FULL_PAGE_TILES = 20


@dataclass(slots=True)
class BrowserCaptureTile:
    index: int
    total: int
    y: int
    height: int
    screenshot: bytes


@dataclass(slots=True)
class BrowserObservation:
    observation_id: str
    screenshot: bytes
    url: str
    title: str
    width: int
    height: int
    scroll_x: float
    scroll_y: float
    cursor_x: float | None
    cursor_y: float | None
    created_at: str
    vision_base64: str = ""
    vision_quality: int = 0


class BrowserController:
    """Persistent Playwright browser controlled with viewport-relative CSS pixels."""

    def __init__(self, settings: BrowserSettings) -> None:
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._counter = 0
        self._observation_id = ""
        self._last_observation: BrowserObservation | None = None
        self._cursor_x: float | None = None
        self._cursor_y: float | None = None

    @property
    def started(self) -> bool:
        return self._page is not None

    @property
    def observation_id(self) -> str:
        return self._observation_id

    @property
    def last_observation(self) -> BrowserObservation | None:
        return self._last_observation

    def start(self) -> None:
        if self.started:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserError(
                "Playwright is not installed. Run: pip install -e . && playwright install chromium"
            ) from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.settings.headless)
            self._context = self._browser.new_context(
                viewport={"width": self.settings.width, "height": self.settings.height},
                device_scale_factor=1,
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.settings.timeout_ms)
        except Exception as exc:
            self.close()
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message.lower():
                raise BrowserError(
                    "Chromium for Playwright is not installed. Run: playwright install chromium"
                ) from exc
            raise BrowserError(f"Could not start Playwright Chromium: {exc}") from exc

    def close(self) -> None:
        for obj in (self._context, self._browser):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None

    def execute(self, command: str) -> BrowserObservation:
        self.start()
        assert self._page is not None

        name, args = parse_browser_command(command)

        try:
            if name in {"goto", "open"}:
                if len(args) != 1:
                    raise BrowserError("Usage: :b goto <url>")
                self._page.goto(args[0], wait_until="domcontentloaded")
                self._cursor_x = None
                self._cursor_y = None

            elif name == "shot":
                if args:
                    raise BrowserError("Usage: :b shot")

            elif name == "click":
                obs_id, coords = self._coordinate_args(args, 2, "click <observation_id> <x> <y>")
                self._assert_observation(obs_id)
                x, y = coords
                self._page.mouse.click(x, y)
                self._cursor_x, self._cursor_y = x, y

            elif name == "move":
                obs_id, coords = self._coordinate_args(args, 2, "move <observation_id> <x> <y>")
                self._assert_observation(obs_id)
                x, y = coords
                self._page.mouse.move(x, y)
                self._cursor_x, self._cursor_y = x, y

            elif name == "drag":
                obs_id, coords = self._coordinate_args(
                    args, 4, "drag <observation_id> <x1> <y1> <x2> <y2>"
                )
                self._assert_observation(obs_id)
                x1, y1, x2, y2 = coords
                self._page.mouse.move(x1, y1)
                self._page.mouse.down()
                self._page.mouse.move(x2, y2, steps=8)
                self._page.mouse.up()
                self._cursor_x, self._cursor_y = x2, y2

            elif name == "scroll":
                if len(args) != 2:
                    raise BrowserError("Usage: :b scroll <dx> <dy>")
                dx, dy = map(_number, args)
                self._page.mouse.wheel(dx, dy)

            elif name == "type":
                value = command.split(maxsplit=1)[1] if len(command.split(maxsplit=1)) == 2 else ""
                if not value:
                    raise BrowserError("Usage: :b type <text>")
                self._page.keyboard.insert_text(value)

            elif name == "key":
                if len(args) != 1:
                    raise BrowserError("Usage: :b key <key>")
                self._page.keyboard.press(args[0])

            elif name == "back":
                if args:
                    raise BrowserError("Usage: :b back")
                self._page.go_back(wait_until="domcontentloaded")

            elif name == "reload":
                if args:
                    raise BrowserError("Usage: :b reload")
                self._page.reload(wait_until="domcontentloaded")

            else:
                raise BrowserError(
                    "Unknown browser command. Supported: goto/open, shot, click, move, drag, "
                    "scroll, type, key, back, reload"
                )
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(f"Browser action failed: {exc}") from exc

        if self.settings.settle_ms > 0:
            self._page.wait_for_timeout(self.settings.settle_ms)
        return self.observe()

    def observe(self) -> BrowserObservation:
        self.start()
        assert self._page is not None

        last_error: Exception | None = None
        for attempt in range(4):
            try:
                self._draw_cursor_overlay()
                png = self._page.screenshot(type="png", full_page=False, scale="css")
                vision_base64, vision_quality = self._capture_vision_base64()
                scroll = self._page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
                title = self._page.title()
                url = self._page.url
                break
            except Exception as exc:
                if not _is_navigation_race(exc):
                    raise BrowserError(f"Could not capture browser observation: {exc}") from exc
                last_error = exc
                try:
                    self._page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=min(self.settings.timeout_ms, 3000),
                    )
                except Exception:
                    pass
                self._page.wait_for_timeout(150 * (attempt + 1))
        else:
            raise BrowserError(
                f"Could not capture browser observation after navigation settled: {last_error}"
            ) from last_error

        self._counter += 1
        stamp = datetime.now(timezone.utc)
        self._observation_id = f"obs_{stamp.strftime('%Y%m%dT%H%M%SZ')}_{self._counter:04d}"

        observation = BrowserObservation(
            observation_id=self._observation_id,
            screenshot=png,
            url=url,
            title=title,
            width=self.settings.width,
            height=self.settings.height,
            scroll_x=float(scroll.get("x", 0)),
            scroll_y=float(scroll.get("y", 0)),
            cursor_x=self._cursor_x,
            cursor_y=self._cursor_y,
            created_at=stamp.isoformat(),
            vision_base64=vision_base64,
            vision_quality=vision_quality,
        )
        self._last_observation = observation
        return observation

    def capture_full_page(self) -> bytes:
        """Capture one full-height PNG.

        Browser-native image documents bypass Chrome's image viewer entirely:
        the image's natural pixels are extracted and returned directly, with
        optional downscaling to the configured viewport width.
        """
        return self._capture_full_page_png()

    def capture_full_page_tiles(
        self,
        *,
        max_tiles: int = MAX_FULL_PAGE_TILES,
    ) -> list[BrowserCaptureTile]:
        """Capture a full page and split it into viewport-height PNG tiles."""
        png = self._capture_full_page_png()

        try:
            with Image.open(BytesIO(png)) as image:
                width, full_height = image.size
                tile_height = max(1, self.settings.height)
                total = max(1, ceil(full_height / tile_height))
                if total > max_tiles:
                    raise BrowserError(
                        f"Full page needs {total} tiles, exceeding the safety limit of {max_tiles}. "
                        "Use :b scroll and :b save for selected sections instead."
                    )

                tiles: list[BrowserCaptureTile] = []
                for index in range(total):
                    y = index * tile_height
                    bottom = min(y + tile_height, full_height)
                    crop = image.crop((0, y, width, bottom))
                    buffer = BytesIO()
                    crop.save(buffer, format="PNG")
                    tiles.append(
                        BrowserCaptureTile(
                            index=index + 1,
                            total=total,
                            y=y,
                            height=bottom - y,
                            screenshot=buffer.getvalue(),
                        )
                    )
                return tiles
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(f"Could not split full-page screenshot: {exc}") from exc

    def _capture_full_page_png(self) -> bytes:
        self.start()
        assert self._page is not None

        direct_image = self._capture_direct_image_png()
        if direct_image is not None:
            return direct_image

        marker_visible = False
        try:
            marker_visible = bool(
                self._page.evaluate(
                    """() => {
                        const marker = document.getElementById('__t4g_cursor_overlay__');
                        if (!marker) return false;
                        const wasVisible = marker.style.visibility !== 'hidden';
                        marker.style.visibility = 'hidden';
                        return wasVisible;
                    }"""
                )
            )
            return self._page.screenshot(type="png", full_page=True, scale="css")
        except Exception as exc:
            raise BrowserError(f"Could not capture full page: {exc}") from exc
        finally:
            if marker_visible:
                try:
                    self._page.evaluate(
                        """() => {
                            const marker = document.getElementById('__t4g_cursor_overlay__');
                            if (marker) marker.style.visibility = 'visible';
                        }"""
                    )
                except Exception:
                    pass

    def _capture_direct_image_png(self) -> bytes | None:
        """Return natural pixels for a browser-native image document.

        Chrome displays tall direct images with fit-to-height styling. Reading
        the rendered viewport would therefore preserve large side margins.
        Instead, draw the image at natural size on an offscreen canvas and
        serialize those pixels directly.
        """
        assert self._page is not None
        try:
            result = self._page.evaluate(
                """() => {
                    if (!String(document.contentType || '').startsWith('image/')) {
                        return null;
                    }
                    const img = document.querySelector('img');
                    if (!img || !img.naturalWidth || !img.naturalHeight) {
                        return null;
                    }
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) throw new Error('2D canvas context unavailable');
                    ctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight);
                    return {
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        dataUrl: canvas.toDataURL('image/png'),
                    };
                }"""
            )
        except Exception as exc:
            raise BrowserError(f"Could not extract direct image pixels: {exc}") from exc

        if not isinstance(result, dict):
            return None

        data_url = str(result.get("dataUrl", ""))
        prefix = "data:image/png;base64,"
        if not data_url.startswith(prefix):
            raise BrowserError("Direct image extraction returned an invalid PNG data URL.")

        try:
            png = base64.b64decode(data_url[len(prefix):], validate=True)
        except Exception as exc:
            raise BrowserError(f"Could not decode direct image pixels: {exc}") from exc

        try:
            with Image.open(BytesIO(png)) as image:
                image.load()
                if image.width <= self.settings.width:
                    return png
                target_height = max(
                    1,
                    round(image.height * (self.settings.width / image.width)),
                )
                resized = image.resize(
                    (self.settings.width, target_height),
                    Image.Resampling.LANCZOS,
                )
                buffer = BytesIO()
                resized.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception as exc:
            raise BrowserError(f"Could not normalize direct image pixels: {exc}") from exc

    def _capture_vision_base64(self) -> tuple[str, int]:
        if not self.settings.vision_enabled:
            return "", 0
        assert self._page is not None

        qualities: list[int] = []
        for quality in (self.settings.vision_quality, 25, 15, 8):
            quality = max(1, min(100, quality))
            if quality not in qualities:
                qualities.append(quality)

        for quality in qualities:
            jpeg = self._page.screenshot(
                type="jpeg",
                quality=quality,
                full_page=False,
                scale="css",
            )
            encoded = base64.b64encode(jpeg).decode("ascii")
            if len(encoded) <= self.settings.vision_max_base64_chars:
                return encoded, quality

        raise BrowserError(
            "Vision screenshot is too large for the Notion payload. "
            "Reduce browser viewport size or vision_max_base64_chars requirements."
        )

    def _assert_observation(self, observation_id: str) -> None:
        if not self._observation_id:
            raise BrowserError("No browser observation exists yet. Run :b shot first.")
        if observation_id != self._observation_id:
            raise BrowserError(
                f"STALE_OBSERVATION: expected {self._observation_id}, got {observation_id}. "
                "Read the latest Browser Status and use its observation_id."
            )

    def _coordinate_args(
        self,
        args: list[str],
        count: int,
        usage: str,
    ) -> tuple[str, list[float]]:
        if len(args) != count + 1:
            raise BrowserError(f"Usage: :b {usage}")
        obs_id = args[0]
        values = [_number(value) for value in args[1:]]
        for index in range(0, len(values), 2):
            x, y = values[index], values[index + 1]
            if x < 0 or x > self.settings.width or y < 0 or y > self.settings.height:
                raise BrowserError(
                    f"Coordinate ({x}, {y}) is outside viewport "
                    f"{self.settings.width}x{self.settings.height}."
                )
        return obs_id, values

    def _draw_cursor_overlay(self) -> None:
        if not self.settings.show_cursor_overlay or self._cursor_x is None or self._cursor_y is None:
            return
        assert self._page is not None
        self._page.evaluate(
            """([x, y]) => {
                let marker = document.getElementById('__t4g_cursor_overlay__');
                if (!marker) {
                    marker = document.createElement('div');
                    marker.id = '__t4g_cursor_overlay__';
                    Object.assign(marker.style, {
                        position: 'fixed',
                        zIndex: '2147483647',
                        width: '14px',
                        height: '14px',
                        border: '2px solid #ff3355',
                        borderRadius: '50%',
                        background: 'rgba(255,51,85,0.2)',
                        pointerEvents: 'none',
                        transform: 'translate(-50%, -50%)',
                        boxSizing: 'border-box'
                    });
                    document.documentElement.appendChild(marker);
                }
                marker.style.left = x + 'px';
                marker.style.top = y + 'px';
            }""",
            [self._cursor_x, self._cursor_y],
        )


def _is_navigation_race(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "execution context was destroyed" in message
        or "cannot find context with specified id" in message
        or "frame was detached" in message
    )


def parse_browser_command(command: str) -> tuple[str, list[str]]:
    value = command.strip()
    if not value:
        raise BrowserError(
            "Usage: :b <goto|shot|save|full|full-tiles|clear-saved|click|move|drag|scroll|type|key|back|reload> ..."
        )
    parts = value.split()
    return parts[0].lower(), parts[1:]


def _number(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise BrowserError(f"Expected a number, got: {value}") from exc
    if not (-1_000_000 <= number <= 1_000_000):
        raise BrowserError(f"Coordinate/scroll value is unreasonable: {value}")
    return number
