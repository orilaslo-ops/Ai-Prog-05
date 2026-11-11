"""The page in a real browser: promotion dialog, save and load.

Needs Playwright and its Chromium (see CLAUDE.md); skipped when they are missing.
"""

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from server import make_server

sync_api = pytest.importorskip("playwright.sync_api")

PROMOTION_SETUP = ["a2a4", "h7h5", "a4a5", "h5h4", "a5a6", "h4h3", "a6b7", "h3g2"]


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # noqa: BLE001 - any launch failure means no browser
            pytest.skip(f"Chromium is not available: {error}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = browser.new_page(accept_downloads=True)
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    page.wait_for_selector('[data-square="e2"] .piece')
    yield page
    page.close()
    server.shutdown()
    server.server_close()
    thread.join()


def square(page: Any, name: str) -> Any:
    return page.locator(f'[data-square="{name}"]')


def click_move(page: Any, coordinates: str) -> None:
    square(page, coordinates[:2]).click()
    page.wait_for_selector(f'[data-square="{coordinates[2:]}"].target')
    square(page, coordinates[2:]).click()


def moves(page: Any) -> list[str]:
    result: list[str] = page.locator("#moves span").all_inner_texts()
    return result


def reach_promotion(page: Any) -> None:
    for number, coordinates in enumerate(PROMOTION_SETUP, 1):
        click_move(page, coordinates)
        page.wait_for_function(
            f"document.querySelectorAll('#moves span').length == {number}"
        )
    click_move(page, "b7a8")
    page.wait_for_selector("#promotion[open]")


def test_choosing_a_piece_promotes_to_it(page: Any) -> None:
    reach_promotion(page)
    page.locator('#promotion-choices button[aria-label="knight"]').click()
    page.wait_for_function("document.querySelectorAll('#moves span').length == 9")
    assert moves(page)[-1] == "b7xa8=N"
    assert square(page, "a8").get_attribute("aria-label") == "a8 White knight"
    assert "bR" not in page.locator("#captured").inner_text()


def test_escape_cancels_the_promotion_without_moving(page: Any) -> None:
    reach_promotion(page)
    page.keyboard.press("Escape")
    page.wait_for_function("!document.querySelector('#promotion').open")
    page.wait_for_timeout(300)
    assert len(moves(page)) == 8
    assert square(page, "b7").get_attribute("aria-label") == "b7 White pawn"
    assert square(page, "a8").get_attribute("aria-label") == "a8 Black rook"
    assert page.locator("#turn").inner_text() == "White to move"
    # The game goes on normally after cancelling.
    click_move(page, "b7a8")
    page.wait_for_selector("#promotion[open]")
    page.locator('#promotion-choices button[aria-label="queen"]').click()
    page.wait_for_function("document.querySelectorAll('#moves span').length == 9")
    assert moves(page)[-1] == "b7xa8=Q"


def test_save_then_load_restores_the_game(page: Any, tmp_path: Path) -> None:
    click_move(page, "e2e4")
    page.wait_for_function("document.querySelectorAll('#moves span').length == 1")
    with page.expect_download() as download:
        page.locator("#save").click()
    path = tmp_path / "game.save.json"
    download.value.save_as(path)
    assert json.loads(path.read_text())["notation"] == ["e2-e4"]
    page.locator('[data-action="new"][data-opponent="human"]').click()
    page.wait_for_function("document.querySelectorAll('#moves span').length == 0")
    page.locator("#load-file").set_input_files(path)
    page.wait_for_function(
        "document.querySelector('#message').textContent == 'Game loaded'"
    )
    assert moves(page) == ["e2-e4"]
    assert square(page, "e4").get_attribute("aria-label") == "e4 White pawn"


@pytest.mark.parametrize(
    "content,error",
    [
        (b"this is not json", "That file is not a saved chess game"),
        (b'{"format": "something-else"}', "That file is not a saved chess game"),
    ],
)
def test_loading_a_bad_file_shows_an_error_and_keeps_the_board(
    page: Any, tmp_path: Path, content: bytes, error: str
) -> None:
    click_move(page, "e2e4")
    page.wait_for_function("document.querySelectorAll('#moves span').length == 1")
    path = tmp_path / "bad.save.json"
    path.write_bytes(content)
    page.locator("#load-file").set_input_files(path)
    page.wait_for_function(
        f"document.querySelector('#message').textContent == {json.dumps(error)}"
    )
    assert moves(page) == ["e2-e4"]
    assert square(page, "e4").get_attribute("aria-label") == "e4 White pawn"


def press(page: Any, key: str, code: str, shift: bool = False) -> None:
    """Dispatch a Ctrl shortcut with the given key text, as another layout would send it."""
    page.evaluate(
        "([key, code, shift]) => document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key, code, ctrlKey: true, shiftKey: shift, bubbles: true}))",
        [key, code, shift],
    )


def test_redo_button_and_shortcuts(page: Any) -> None:
    redo_button = page.locator("#redo")
    assert redo_button.is_disabled()
    click_move(page, "e2e4")
    page.wait_for_function("document.querySelectorAll('#moves span').length == 1")
    page.locator("#undo").click()
    page.wait_for_function("document.querySelectorAll('#moves span').length == 0")
    assert redo_button.is_enabled()
    redo_button.click()
    page.wait_for_function("document.querySelectorAll('#moves span').length == 1")
    assert redo_button.is_disabled()
    assert square(page, "e4").get_attribute("aria-label") == "e4 White pawn"
    # Ctrl+Y and Ctrl+Shift+Z, with a Hebrew layout (key "ט" / "ז") as well.
    for key, code, shift in (
        ("y", "KeyY", False),
        ("ט", "KeyY", False),
        ("ז", "KeyZ", True),
    ):
        press(page, "ז", "KeyZ")
        page.wait_for_function("document.querySelectorAll('#moves span').length == 0")
        press(page, key, code, shift)
        page.wait_for_function("document.querySelectorAll('#moves span').length == 1")
