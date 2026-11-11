import re
from pathlib import Path

APP = (Path(__file__).parent.parent / "static" / "app.js").read_text(encoding="utf-8")


def keydown_handler() -> str:
    match = re.search(r"addEventListener\('keydown'.*?\n\}\);", APP, re.DOTALL)
    assert match, "app.js should listen for keydown"
    return match.group(0)


def test_ctrl_z_uses_the_physical_key_so_any_keyboard_layout_works() -> None:
    # With a Hebrew layout, Ctrl+Z sends event.key "ז"; event.code is still "KeyZ".
    handler = keydown_handler()
    assert "event.code === 'KeyZ'" in handler
    assert "event.ctrlKey || event.metaKey" in handler
    assert "#undo" in handler


def test_undo_button_is_on_the_page() -> None:
    html = (Path(__file__).parent.parent / "static" / "index.html").read_text()
    assert 'id="undo"' in html and 'data-action="undo"' in html
