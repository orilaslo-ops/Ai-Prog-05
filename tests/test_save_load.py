import json
import threading
import urllib.error
import urllib.request

import pytest

from game import copy_position, move, new_position
from server import make_server
from session import SAVE_FORMAT, SAVE_VERSION, Session, load_file, save_file


def play(session, *moves):
    for source, target in moves:
        session.dispatch({"action": "move", "source": source, "target": target})


def same_game(a, b):
    assert a.view() == b.view()
    assert a.history == b.history
    assert a.redo == b.redo


def test_new_game_round_trip():
    session = Session()
    data = session.save_data()
    assert data["format"] == SAVE_FORMAT
    assert data["version"] == SAVE_VERSION
    assert data["moves"] == [] and data["redo"] == []
    loaded = Session.from_save(data)
    same_game(session, loaded)
    assert loaded.position == new_position()


def test_mid_game_with_capture_survives_a_file_and_a_fresh_instance(tmp_path):
    session = Session()
    play(session, ("e2", "e4"), ("d7", "d5"), ("e4", "d5"))
    path = tmp_path / "game.save.json"
    save_file(session, path)
    assert json.loads(path.read_text())["turn"] == "b"

    loaded = load_file(path)
    same_game(session, loaded)
    assert loaded.view()["moves"] == ["e2-e4", "d7-d5", "e4xd5"]
    assert loaded.position[0]["d5"] == "wP"
    assert len(loaded.position[0]) == 31
    assert loaded.position[1] == "b"
    # The loaded game continues normally.
    play(loaded, ("d8", "d5"))
    assert loaded.view()["moves"][-1] == "d8xd5"


def test_check_survives_loading():
    session = Session()
    play(session, ("e2", "e4"), ("f7", "f6"), ("d1", "h5"))
    loaded = Session.from_save(session.save_data())
    assert loaded.view()["status"] == "check"
    assert loaded.view()["moves"][-1] == "d1-h5+"


def test_computer_opponent_is_restored():
    session = Session()
    session.dispatch({"action": "new", "opponent": "computer"})
    play(session, ("e2", "e4"))
    loaded = Session.from_save(session.save_data())
    assert loaded.view()["opponent"] == "computer"
    assert loaded.computer_to_move()
    with pytest.raises(ValueError):
        play(loaded, ("e7", "e5"))
    view = loaded.dispatch({"action": "computer-move"})
    assert view["turn"] == "w" and len(view["moves"]) == 2


def test_two_player_game_stays_two_player():
    session = Session()
    play(session, ("e2", "e4"))
    loaded = Session.from_save(session.save_data())
    assert loaded.view()["opponent"] == "human"
    with pytest.raises(ValueError):
        loaded.dispatch({"action": "computer-move"})


def test_history_allows_undoing_moves_made_before_saving():
    session = Session()
    play(session, ("g1", "f3"), ("b8", "c6"), ("f3", "e5"), ("c6", "e5"))
    loaded = Session.from_save(session.save_data())
    assert loaded.history == [("g1", "f3"), ("b8", "c6"), ("f3", "e5"), ("c6", "e5")]
    # Replaying all but the last move gives the position before it, captured knight included.
    earlier = new_position()
    for source, target in loaded.history[:-1]:
        move(earlier, source, target)
    assert earlier[0]["e5"] == "wN"
    assert earlier[1] == "b"


def test_redo_moves_are_saved_and_restored():
    session = Session()
    play(session, ("e2", "e4"))
    session.redo = [("e7", "e5"), ("g1", "f3")]
    data = session.save_data()
    assert data["redo"] == [{"source": "e7", "target": "e5"},
                            {"source": "g1", "target": "f3"}]
    assert Session.from_save(data).redo == [("e7", "e5"), ("g1", "f3")]


def test_promotion_setup_game_round_trip():
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    same_game(session, Session.from_save(session.save_data()))


def test_load_action_replaces_the_game_and_new_game_clears_it():
    source = Session()
    source.dispatch({"action": "new", "opponent": "computer"})
    play(source, ("e2", "e4"))
    saved = source.dispatch({"action": "save"})["save"]
    # Through JSON, as the browser sends it.
    saved = json.loads(json.dumps(saved))

    target = Session()
    play(target, ("d2", "d4"), ("d7", "d5"))
    view = target.dispatch({"action": "load", "game": saved})
    assert view["moves"] == ["e2-e4"]
    assert view["opponent"] == "computer"
    target.dispatch({"action": "new"})
    assert target.history == [] and target.redo == []
    assert target.position == new_position()


def corrupt(change):
    session = Session()
    play(session, ("e2", "e4"), ("e7", "e5"))
    data = session.save_data()
    change(data)
    return data


@pytest.mark.parametrize("data", [
    None,
    [],
    "text",
    {},
    corrupt(lambda d: d.update(format="something-else")),
    corrupt(lambda d: d.update(version=99)),
    corrupt(lambda d: d.update(opponent="robot")),
    corrupt(lambda d: d.update(moves="e2e4")),
    corrupt(lambda d: d.update(moves=[["e2", "e4"]])),
    corrupt(lambda d: d["moves"].append({"source": "e1", "target": "e5"})),
    corrupt(lambda d: d["moves"].append({"source": "z9"})),
    corrupt(lambda d: d.pop("moves")),
    corrupt(lambda d: d["board"].update(e4="wQ")),
    corrupt(lambda d: d.update(turn="b")),
    corrupt(lambda d: d.pop("board")),
    corrupt(lambda d: d.update(redo=[{"source": "e5", "target": "e4"}])),
    corrupt(lambda d: d.update(redo={"source": "g1", "target": "f3"})),
])
def test_invalid_saves_are_rejected_and_leave_the_game_unchanged(data):
    session = Session()
    play(session, ("d2", "d4"))
    before = (copy_position(session.position), list(session.notation),
              list(session.history), session.opponent)
    with pytest.raises(ValueError):
        session.dispatch({"action": "load", "game": data})
    assert (session.position, session.notation, session.history,
            session.opponent) == before


@pytest.mark.parametrize("content", [b"not json", b"\xff\xfe\x00", b'{"format": 1}', b""])
def test_unreadable_files_are_rejected(tmp_path, content):
    path = tmp_path / "bad.save.json"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        load_file(path)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_file(tmp_path / "missing.save.json")


def test_save_and_load_over_http():
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/action"

    def post(action):
        request = urllib.request.Request(url, json.dumps(action).encode(),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        post({"action": "move", "source": "e2", "target": "e4"})
        saved = post({"action": "save"})["save"]
        post({"action": "new"})
        view = post({"action": "load", "game": saved})
        assert view["moves"] == ["e2-e4"] and view["turn"] == "b"
        with pytest.raises(urllib.error.HTTPError) as error:
            post({"action": "load", "game": {"format": "nope"}})
        assert error.value.code == 400
        error.value.close()
        assert post({"action": "save"})["save"]["moves"] == saved["moves"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
