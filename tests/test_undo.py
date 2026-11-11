import random

from game import copy_position, new_position
from session import Session


def play(session: Session, *moves: tuple[str, str]) -> None:
    for source, target in moves:
        session.dispatch({"action": "move", "source": source, "target": target})


def test_undo_at_the_beginning_does_nothing() -> None:
    session = Session()
    view = session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert view["moves"] == []
    assert view["can_undo"] is False


def test_undo_restores_board_turn_and_notation() -> None:
    session = Session()
    play(session, ("e2", "e4"))
    assert session.view()["can_undo"] is True
    view = session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert view["turn"] == "w"
    assert view["moves"] == []
    assert view["can_undo"] is False


def test_undo_restores_a_captured_piece() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("d7", "d5"))
    before = copy_position(session.position)
    play(session, ("e4", "d5"))
    assert len(session.position[0]) == 31
    session.dispatch({"action": "undo"})
    assert session.position == before
    assert session.position[0]["d5"] == "bP"
    assert session.position[0]["e4"] == "wP"
    assert session.view()["turn"] == "w"
    assert session.view()["moves"] == ["e2-e4", "d7-d5"]


def test_repeated_undo_walks_back_to_the_start_one_move_at_a_time() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("e7", "e5"), ("g1", "f3"))
    session.dispatch({"action": "undo"})
    assert session.view()["moves"] == ["e2-e4", "e7-e5"]
    assert session.view()["turn"] == "w"
    session.dispatch({"action": "undo"})
    assert session.view()["turn"] == "b"
    session.dispatch({"action": "undo"})
    session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert session.view()["moves"] == []
    view = session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert view["moves"] == []
    assert view["turn"] == "w"


def test_repeated_undo_against_the_computer_reaches_the_start() -> None:
    random.seed(2)
    session = Session("computer")
    for move in (("e2", "e4"), ("g1", "f3"), ("b1", "c3")):
        play(session, move)
        session.dispatch({"action": "computer-move"})
    lengths = []
    while session.view()["can_undo"]:
        view = session.dispatch({"action": "undo"})
        assert view["turn"] == "w"
        lengths.append(len(view["moves"]))
    assert lengths == [4, 2, 0]
    assert session.position == new_position()
    session.dispatch({"action": "undo"})
    assert session.position == new_position()


def test_a_different_move_after_undo_replaces_the_continuation() -> None:
    session = Session()
    play(session, ("e2", "e4"))
    session.dispatch({"action": "undo"})
    play(session, ("d2", "d4"))
    assert session.view()["moves"] == ["d2-d4"]
    assert session.position[0]["d4"] == "wP"
    assert "e4" not in session.position[0]
    assert len(session.history) == 2


def test_undo_keeps_the_position_independent_of_history() -> None:
    session = Session()
    play(session, ("e2", "e4"), ("e7", "e5"))
    session.dispatch({"action": "undo"})
    play(session, ("d7", "d5"))
    session.dispatch({"action": "undo"})
    assert session.position[0].get("d7") == "bP"
    assert "d5" not in session.position[0]


def test_undo_against_the_computer_takes_back_its_reply_too() -> None:
    random.seed(0)
    session = Session("computer")
    play(session, ("e2", "e4"))
    session.dispatch({"action": "computer-move"})
    assert len(session.view()["moves"]) == 2
    view = session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert view["turn"] == "w"
    assert view["moves"] == []


def test_undo_against_the_computer_before_it_replies() -> None:
    session = Session("computer")
    play(session, ("e2", "e4"))
    view = session.dispatch({"action": "undo"})
    assert session.position == new_position()
    assert view["turn"] == "w"


def test_undo_against_the_computer_returns_to_the_players_turn_mid_game() -> None:
    random.seed(1)
    session = Session("computer")
    for source, target in (("e2", "e4"), ("d2", "d4")):
        play(session, (source, target))
        session.dispatch({"action": "computer-move"})
    after_first_round = copy_position(session.history[2])
    session.dispatch({"action": "undo"})
    assert session.position == after_first_round
    assert session.view()["turn"] == "w"
    assert len(session.view()["moves"]) == 2


def test_new_game_clears_undo_history() -> None:
    session = Session()
    play(session, ("e2", "e4"))
    view = session.dispatch({"action": "new"})
    assert view["can_undo"] is False
    assert session.history == [new_position()]
    session.dispatch({"action": "undo"})
    assert session.position == new_position()


def test_promotion_setup_moves_can_be_undone() -> None:
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    session.dispatch({"action": "undo"})
    assert session.position[0]["h3"] == "bP"
    assert session.position[0]["g2"] == "wP"
    assert session.view()["turn"] == "b"
    assert len(session.view()["moves"]) == 7
