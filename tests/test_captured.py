import json
import random

from session import Session


def test_display_after_capture_and_new_game() -> None:
    session = Session()
    assert session.view()["captured"] == []
    session.play("e2", "e4")
    session.play("d7", "d5")
    session.play("e4", "d5")
    assert session.view()["captured"] == ["bP"]
    session.dispatch({"action": "new"})
    assert session.view()["captured"] == []


def play(session: Session, *moves: tuple[str, str]) -> None:
    for source, target in moves:
        session.dispatch({"action": "move", "source": source, "target": target})


CAPTURES = (
    ("e2", "e4"),
    ("d7", "d5"),
    ("e4", "d5"),
    ("d8", "d5"),
    ("b1", "c3"),
    ("d5", "a2"),
)


def test_both_sides_captures_are_listed() -> None:
    session = Session()
    play(session, *CAPTURES)
    assert session.view()["captured"] == ["bP", "wP", "wP"]


def test_undoing_a_capture_removes_it_from_the_display() -> None:
    session = Session()
    play(session, *CAPTURES)
    session.dispatch({"action": "undo"})
    assert session.view()["captured"] == ["bP", "wP"]
    session.dispatch({"action": "undo"})
    session.dispatch({"action": "undo"})
    assert session.view()["captured"] == ["bP"]
    session.dispatch({"action": "undo"})
    assert session.view()["captured"] == []


def test_a_different_move_after_undo_updates_the_display() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("d7", "d5"), ("e4", "d5"))
    session.dispatch({"action": "undo"})
    play(session, ("e4", "e5"))
    assert session.view()["captured"] == []


def test_captured_pieces_survive_save_and_load() -> None:
    session = Session()
    play(session, *CAPTURES)
    loaded = Session.from_save(json.loads(json.dumps(session.save_data())))
    assert loaded.view()["captured"] == ["bP", "wP", "wP"]
    loaded.dispatch({"action": "undo"})
    assert loaded.view()["captured"] == ["bP", "wP"]


def test_loading_replaces_the_captured_pieces_of_the_current_game() -> None:
    session = Session()
    play(session, *CAPTURES)
    session.dispatch({"action": "load", "game": Session().save_data()})
    assert session.view()["captured"] == []


def test_undo_against_the_computer_restores_its_captures_too() -> None:
    random.seed(1)
    session = Session("computer")
    for move in (("e2", "e4"), ("d1", "h5"), ("h5", "f7")):
        play(session, move)
        session.dispatch({"action": "computer-move"})
    # Qxf7+ takes a pawn and the king takes the queen back.
    assert session.view()["moves"][-2:] == ["h5xf7+", "e8xf7"]
    assert session.view()["captured"] == ["bP", "wQ"]
    session.dispatch({"action": "undo"})
    assert session.view()["turn"] == "w"
    assert session.view()["captured"] == []


def test_promotion_setup_lists_its_two_pawn_captures() -> None:
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    assert session.view()["captured"] == ["bP", "wP"]
