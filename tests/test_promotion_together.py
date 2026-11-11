"""Promotion together with captured pieces, undo, save/load and the computer."""

import json
import random
from typing import Any

import pytest

from game import Position, copy_position
from session import Session


def play(session: Session, source: str, target: str, promotion: Any = None) -> None:
    action = {"action": "move", "source": source, "target": target}
    if promotion is not None:
        action["promotion"] = promotion
    session.dispatch(action)


def reload(session: Session) -> Session:
    return Session.from_save(json.loads(json.dumps(session.save_data())))


def promoted(piece: str = "Q") -> Session:
    """promotion-setup, then White plays b7xa8 promoting to piece."""
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    play(session, "b7", "a8", piece)
    return session


def from_position(position: Position, opponent: str = "human") -> Session:
    """A session whose game starts from position instead of the usual start."""
    session = Session(opponent)
    session.position = copy_position(position)
    session.history = [copy_position(position)]
    session.after_move()
    return session


# Captured pieces: a promotion is not a capture, and a captured piece keeps its type.


def test_capture_promotion_lists_only_the_captured_rook() -> None:
    session = promoted()
    assert session.view()["moves"][-1] == "b7xa8=Q"
    assert session.view()["captured"] == ["bP", "bR", "wP"]


def test_black_promotion_is_not_a_capture_either() -> None:
    session = promoted()
    play(session, "g2", "h1", "N")
    assert session.view()["captured"] == ["bP", "bR", "wP", "wR"]


def test_quiet_promotion_captures_nothing() -> None:
    session = from_position([{"e1": "wK", "e8": "bK", "b7": "wP"}, "w"])
    play(session, "b7", "b8", "Q")
    assert session.position[0]["b8"] == "wQ"
    assert session.view()["captured"] == []


def test_a_captured_promoted_queen_is_shown_as_a_queen() -> None:
    session = from_position([{"e1": "wK", "h8": "bK", "b7": "wP", "c8": "bR"}, "w"])
    play(session, "b7", "b8", "Q")
    play(session, "c8", "b8")
    assert session.view()["captured"] == ["wQ"]


def test_undoing_a_promotion_restores_the_pawn_and_the_captured_list() -> None:
    session = promoted()
    session.dispatch({"action": "undo"})
    assert session.position[0]["b7"] == "wP"
    assert session.position[0]["a8"] == "bR"
    assert session.view()["captured"] == ["bP", "wP"]
    assert session.view()["moves"][-1] == "h3xg2"


# Save and load


@pytest.mark.parametrize("piece", list("QRBN"))
def test_a_game_with_a_promotion_can_be_saved_and_loaded(piece: str) -> None:
    session = promoted(piece)
    loaded = reload(session)
    assert loaded.position[0]["a8"] == "w" + piece
    assert loaded.view() == session.view()
    assert loaded.history == session.history


def test_undo_after_loading_a_promotion() -> None:
    session = promoted()
    play(session, "g2", "h1", "Q")
    loaded = reload(session)
    loaded.dispatch({"action": "undo"})
    assert loaded.position[0]["g2"] == "bP"
    assert loaded.position[0]["h1"] == "wR"
    loaded.dispatch({"action": "undo"})
    assert loaded.position[0]["b7"] == "wP"
    assert loaded.view()["captured"] == ["bP", "wP"]


def change_promotion(data: dict[str, Any], piece: str, label: str) -> None:
    data["history"][-1]["board"]["a8"] = piece
    data["notation"][-1] = label


@pytest.mark.parametrize(
    "piece,label",
    [
        ("wK", "b7xa8=K"),  # Kings are not a promotion choice.
        ("wP", "b7xa8"),  # A pawn may not stay a pawn on the last rank.
        ("wN", "b7xa8=Q"),  # The board and the notation disagree.
        ("bQ", "b7xa8=Q"),  # The promoted piece changed sides.
    ],
)
def test_an_invalid_promotion_in_a_save_is_rejected(piece: str, label: str) -> None:
    data = json.loads(json.dumps(promoted().save_data()))
    change_promotion(data, piece, label)
    session = Session()
    with pytest.raises(ValueError):
        session.dispatch({"action": "load", "game": data})
    assert session.view()["moves"] == []


# The computer


def test_the_computer_promotes_and_undo_takes_it_back() -> None:
    random.seed(0)
    session = from_position(
        [{"a2": "wK", "e8": "bK", "h2": "bP", "c3": "wP"}, "w"], "computer"
    )
    play(session, "c3", "c4")
    session.dispatch({"action": "computer-move"})
    assert session.view()["moves"][-1] == "h2-h1=Q"
    assert session.position[0]["h1"] == "bQ"
    assert session.view()["captured"] == []
    session.dispatch({"action": "undo"})
    assert session.position[0]["h2"] == "bP"
    assert session.view()["turn"] == "w"
