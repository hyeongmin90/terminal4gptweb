from io import BytesIO

import pytest
from PIL import Image

from terminal4gptweb.browser import BrowserController, BrowserError, _is_navigation_race, parse_browser_command
from terminal4gptweb.config import BrowserSettings


def test_parse_browser_command():
    name, args = parse_browser_command("click obs_1 100 200")
    assert name == "click"
    assert args == ["obs_1", "100", "200"]


def test_parse_browser_command_rejects_empty():
    with pytest.raises(BrowserError):
        parse_browser_command("")


def test_coordinate_validation_rejects_outside_viewport():
    controller = BrowserController(BrowserSettings(width=1280, height=720))
    with pytest.raises(BrowserError, match="outside viewport"):
        controller._coordinate_args(
            ["obs_1", "1281", "10"],
            2,
            "click <observation_id> <x> <y>",
        )


def test_stale_observation_is_rejected():
    controller = BrowserController(BrowserSettings())
    controller._observation_id = "obs_latest"
    with pytest.raises(BrowserError, match="STALE_OBSERVATION"):
        controller._assert_observation("obs_old")


class _FakeScreenshotPage:
    def __init__(self):
        self.qualities = []

    def screenshot(self, *, type, quality, full_page, scale):
        assert type == "jpeg"
        assert full_page is False
        assert scale == "css"
        self.qualities.append(quality)
        return b"x" * (300 if quality >= 35 else 60)


def test_vision_payload_reduces_quality_until_it_fits():
    controller = BrowserController(
        BrowserSettings(
            vision_enabled=True,
            vision_quality=35,
            vision_max_base64_chars=100,
        )
    )
    page = _FakeScreenshotPage()
    controller._page = page

    encoded, quality = controller._capture_vision_base64()

    assert quality == 25
    assert len(encoded) <= 100
    assert page.qualities == [35, 25]


def test_vision_payload_can_be_disabled():
    controller = BrowserController(BrowserSettings(vision_enabled=False))
    assert controller._capture_vision_base64() == ("", 0)


def test_navigation_race_detection():
    assert _is_navigation_race(RuntimeError("Execution context was destroyed, most likely because of a navigation"))
    assert _is_navigation_race(RuntimeError("Frame was detached"))
    assert not _is_navigation_race(RuntimeError("selector timeout"))


class _FakeFullPage:
    def __init__(self, *, width: int, height: int):
        self.width = width
        self.height = height

    def evaluate(self, script):
        return False

    def screenshot(self, *, type, full_page, scale):
        assert type == "png"
        assert full_page is True
        assert scale == "css"
        image = Image.new("RGB", (self.width, self.height))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def test_full_page_capture_returns_one_full_height_image():
    controller = BrowserController(BrowserSettings(width=1280, height=720))
    controller._page = _FakeFullPage(width=1280, height=1805)

    screenshot = controller.capture_full_page()

    with Image.open(BytesIO(screenshot)) as image:
        assert image.size == (1280, 1805)


def test_full_page_capture_is_split_into_viewport_height_tiles():
    controller = BrowserController(BrowserSettings(width=1280, height=720))
    controller._page = _FakeFullPage(width=1280, height=1500)

    tiles = controller.capture_full_page_tiles()

    assert len(tiles) == 3
    assert [tile.y for tile in tiles] == [0, 720, 1440]
    assert [tile.height for tile in tiles] == [720, 720, 60]
    assert [tile.index for tile in tiles] == [1, 2, 3]
    assert all(tile.total == 3 for tile in tiles)


def test_full_page_capture_rejects_too_many_tiles():
    controller = BrowserController(BrowserSettings(width=20, height=10))
    controller._page = _FakeFullPage(width=20, height=210)

    with pytest.raises(BrowserError, match="safety limit"):
        controller.capture_full_page_tiles(max_tiles=20)
