import json
import random
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from game import copy_position, new_position
from server import make_server
from session import SAVE_FORMAT, SAVE_VERSION, Session, load_file, save_file


def play(session: Session, *moves: tuple[str, str]) -> None:
    for source, target in moves:
        session.dispatch({"action": "move", "source": source, "target": target})


def reload(session: Session) -> Session:
    """Save and load through JSON text, as the browser does."""
    return Session.from_save(json.loads(json.dumps(session.save_data())))


def same_game(a: Session, b: Session) -> None:
    assert a.view() == b.view()
    assert a.history == b.history
    assert a.position == b.position


def test_new_game_round_trip() -> None:
    session = Session()
    data = session.save_data()
    assert data["format"] == SAVE_FORMAT
    assert data["version"] == SAVE_VERSION
    assert data["notation"] == []
    assert data["history"] == [{"board": new_position()[0], "turn": "w"}]
    loaded = reload(session)
    same_game(session, loaded)
    assert loaded.view()["can_undo"] is False


def test_mid_game_with_capture_survives_a_file_and_a_fresh_instance(
    tmp_path: Path,
) -> None:
    session = Session()
    play(session, ("e2", "e4"), ("d7", "d5"), ("e4", "d5"))
    path = tmp_path / "game.save.json"
    save_file(session, path)
    assert json.loads(path.read_text())["history"][-1]["turn"] == "b"

    loaded = load_file(path)
    same_game(session, loaded)
    assert loaded.view()["moves"] == ["e2-e4", "d7-d5", "e4xd5"]
    assert loaded.position[0]["d5"] == "wP"
    assert len(loaded.position[0]) == 31
    # The loaded game continues normally.
    play(loaded, ("d8", "d5"))
    assert loaded.view()["moves"][-1] == "d8xd5"


def test_check_survives_loading() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("f7", "f6"), ("d1", "h5"))
    loaded = reload(session)
    assert loaded.view()["status"] == "check"
    assert loaded.view()["moves"][-1] == "d1-h5+"


def test_computer_opponent_is_restored() -> None:
    session = Session()
    session.dispatch({"action": "new", "opponent": "computer"})
    play(session, ("e2", "e4"))
    loaded = reload(session)
    assert loaded.view()["opponent"] == "computer"
    assert loaded.computer_to_move()
    with pytest.raises(ValueError):
        play(loaded, ("e7", "e5"))
    view = loaded.dispatch({"action": "computer-move"})
    assert view["turn"] == "w" and len(view["moves"]) == 2


def test_two_player_game_stays_two_player() -> None:
    session = Session()
    play(session, ("e2", "e4"))
    loaded = reload(session)
    assert loaded.view()["opponent"] == "human"
    with pytest.raises(ValueError):
        loaded.dispatch({"action": "computer-move"})


def test_undo_after_loading_restores_a_captured_piece() -> None:
    session = Session()
    play(session, ("g1", "f3"), ("b8", "c6"), ("f3", "e5"), ("c6", "e5"))
    loaded = reload(session)
    assert loaded.view()["can_undo"] is True
    loaded.dispatch({"action": "undo"})
    assert loaded.position[0]["e5"] == "wN"
    assert loaded.position[0]["c6"] == "bN"
    assert loaded.view()["turn"] == "b"
    assert loaded.view()["moves"] == ["g1-f3", "b8-c6", "f3-e5"]
    # Every move made before saving can be undone.
    for _ in range(3):
        loaded.dispatch({"action": "undo"})
    assert loaded.position == new_position()
    assert loaded.view()["can_undo"] is False


def test_undo_after_loading_against_the_computer_returns_to_white() -> None:
    random.seed(3)
    session = Session("computer")
    for move in (("e2", "e4"), ("d2", "d4")):
        play(session, move)
        session.dispatch({"action": "computer-move"})
    after_first_round = copy_position(session.history[2])
    loaded = reload(session)
    view = loaded.dispatch({"action": "undo"})
    assert loaded.position == after_first_round
    assert view["turn"] == "w"
    assert len(view["moves"]) == 2


def test_save_after_undo_stores_the_current_continuation() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("e7", "e5"), ("d2", "d4"))
    session.dispatch({"action": "undo"})
    loaded = reload(session)
    same_game(session, loaded)
    assert loaded.view()["moves"] == ["e2-e4", "e7-e5"]
    assert len(loaded.history) == 3
    play(loaded, ("g1", "f3"))
    assert loaded.view()["moves"] == ["e2-e4", "e7-e5", "g1-f3"]


def test_loaded_positions_are_independent_of_each_other() -> None:
    session = Session()
    play(session, ("e2", "e4"))
    loaded = reload(session)
    play(loaded, ("e7", "e5"))
    loaded.dispatch({"action": "undo"})
    assert loaded.position[0].get("e7") == "bP"
    assert "e5" not in loaded.position[0]


def test_promotion_setup_game_round_trip() -> None:
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    same_game(session, reload(session))


def test_load_action_replaces_the_game_and_new_game_clears_it() -> None:
    source = Session()
    source.dispatch({"action": "new", "opponent": "computer"})
    play(source, ("e2", "e4"))
    saved = json.loads(json.dumps(source.dispatch({"action": "save"})["save"]))

    target = Session()
    play(target, ("d2", "d4"), ("d7", "d5"))
    view = target.dispatch({"action": "load", "game": saved})
    assert view["moves"] == ["e2-e4"]
    assert view["opponent"] == "computer"
    assert view["can_undo"] is True
    target.dispatch({"action": "new"})
    assert target.history == [new_position()]
    assert target.position == new_position()


def corrupt(change: Callable[[dict[str, Any]], object]) -> dict[str, Any]:
    session = Session()
    play(session, ("e2", "e4"), ("e7", "e5"))
    data: dict[str, Any] = json.loads(json.dumps(session.save_data()))
    change(data)
    return data


def board(data: dict[str, Any], index: int) -> dict[str, str]:
    result: dict[str, str] = data["history"][index]["board"]
    return result


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "text",
        {},
        corrupt(lambda d: d.update(format="something-else")),
        corrupt(lambda d: d.update(version=99)),
        corrupt(lambda d: d.update(opponent="robot")),
        corrupt(lambda d: d.pop("history")),
        corrupt(lambda d: d.pop("notation")),
        corrupt(lambda d: d.update(history=[])),
        corrupt(lambda d: d.update(history="e2e4")),
        corrupt(lambda d: d["history"].append(["board", "w"])),
        corrupt(lambda d: d["history"][1].update(board=None)),
        corrupt(lambda d: d["history"][1].update(turn="x")),
        corrupt(lambda d: board(d, 2).update(z9="bP")),
        corrupt(lambda d: board(d, 2).update(a3="bX")),
        corrupt(lambda d: board(d, 0).pop("a1")),
        corrupt(lambda d: board(d, 2).update(e4="wQ")),
        corrupt(lambda d: d["history"][2].update(turn="b")),
        corrupt(lambda d: d["history"].pop()),
        corrupt(lambda d: d["notation"].pop()),
        corrupt(lambda d: d.update(notation=["e2-e4", "e7-e6"])),
        corrupt(lambda d: d.update(notation=["e2-e4", 5])),
        # Two moves at once, and an illegal knight jump.
        corrupt(lambda d: d["history"].pop(1) and d["notation"].pop(0)),
        corrupt(lambda d: board(d, 2).update(e5="bN", g8="bP")),
    ],
)
def test_invalid_saves_are_rejected_and_leave_the_game_unchanged(data: object) -> None:
    session = Session()
    play(session, ("d2", "d4"))
    before = (
        copy_position(session.position),
        list(session.notation),
        [copy_position(position) for position in session.history],
        session.opponent,
    )
    with pytest.raises(ValueError):
        session.dispatch({"action": "load", "game": data})
    assert (
        session.position,
        session.notation,
        session.history,
        session.opponent,
    ) == before


@pytest.mark.parametrize(
    "content", [b"not json", b"\xff\xfe\x00", b'{"format": 1}', b""]
)
def test_unreadable_files_are_rejected(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.save.json"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        load_file(path)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_file(tmp_path / "missing.save.json")


def test_save_load_and_undo_over_http() -> None:
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/action"

    def post(action: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            url, json.dumps(action).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        post({"action": "move", "source": "e2", "target": "e4"})
        saved = post({"action": "save"})["save"]
        post({"action": "new"})
        view = post({"action": "load", "game": saved})
        assert view["moves"] == ["e2-e4"] and view["turn"] == "b"
        assert post({"action": "undo"})["moves"] == []
        with pytest.raises(urllib.error.HTTPError) as error:
            post({"action": "load", "game": {"format": "nope"}})
        assert error.value.code == 400
        error.value.close()
        assert post({"action": "save"})["save"]["notation"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
