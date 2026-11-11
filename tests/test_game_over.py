"""Checkmate and stalemate together with undo and save/load."""

import json

from session import Session

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]
# Sam Loyd's ten-move stalemate; legal here because it needs no castling or en passant.
STALEMATE = [
    "e2e3",
    "a7a5",
    "d1h5",
    "a8a6",
    "h5a5",
    "h7h5",
    "h2h4",
    "a6h6",
    "a5c7",
    "f7f6",
    "c7d7",
    "e8f7",
    "d7b7",
    "d8d3",
    "b7b8",
    "d3h7",
    "b8c8",
    "f7g6",
    "c8e6",
]


def played(moves: list[str], opponent: str = "human") -> Session:
    session = Session(opponent)
    for coordinates in moves:
        session.play(coordinates[:2], coordinates[2:])
    return session


def reload(session: Session) -> Session:
    return Session.from_save(json.loads(json.dumps(session.save_data())))


def test_checkmate_is_reported_and_ends_the_game() -> None:
    view = played(FOOLS_MATE).view()
    assert view["moves"][-1] == "d8-h4#"
    assert view["status"] == "checkmate"
    assert view["winner"] == "Black"


def test_undo_out_of_checkmate_resumes_play() -> None:
    session = played(FOOLS_MATE)
    view = session.dispatch({"action": "undo"})
    assert view["status"] is None and view["winner"] is None
    assert view["turn"] == "b"
    session.dispatch({"action": "move", "source": "d8", "target": "g5"})
    assert session.view()["status"] is None


def test_a_saved_checkmate_loads_as_checkmate() -> None:
    loaded = reload(played(FOOLS_MATE))
    assert loaded.view()["status"] == "checkmate"
    assert loaded.view()["winner"] == "Black"
    assert loaded.dispatch({"action": "legal", "source": "e1"})["targets"] == []
    loaded.dispatch({"action": "undo"})
    assert loaded.view()["status"] is None


def test_stalemate_is_a_draw_and_survives_save_and_load() -> None:
    session = played(STALEMATE)
    assert session.view()["status"] == "stalemate"
    assert session.view()["winner"] is None
    loaded = reload(session)
    assert loaded.view()["status"] == "stalemate"
    assert loaded.view()["winner"] is None
    assert loaded.view()["captured"] == ["bB", "bN", "bP", "bP", "bP", "bP"]


def test_undo_out_of_stalemate_resumes_play() -> None:
    session = played(STALEMATE)
    session.dispatch({"action": "undo"})
    assert session.view()["status"] is None
    assert session.view()["turn"] == "w"


def test_no_computer_move_after_checkmate_even_after_loading() -> None:
    # White is mated in a game against the computer: nothing is left to play.
    loaded = reload(played(FOOLS_MATE, "computer"))
    assert loaded.view()["opponent"] == "computer"
    assert not loaded.computer_to_move()
