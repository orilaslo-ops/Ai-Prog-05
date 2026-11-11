"""Redo, as agreed in lab-notes/redo-spec.md (numbers refer to its outcomes)."""

import json
import random
from typing import Any

import pytest

from game import copy_position, new_position
from session import Session


def play(session: Session, source: str, target: str, promotion: Any = None) -> None:
    action = {"action": "move", "source": source, "target": target}
    if promotion is not None:
        action["promotion"] = promotion
    session.dispatch(action)


def undo(session: Session) -> dict[str, Any]:
    return session.dispatch({"action": "undo"})


def redo(session: Session) -> dict[str, Any]:
    return session.dispatch({"action": "redo"})


def reload(session: Session) -> Session:
    return Session.from_save(json.loads(json.dumps(session.save_data())))


def snapshot(session: Session) -> tuple[Any, ...]:
    view = session.view()
    return (
        copy_position(session.position),
        list(view["moves"]),
        list(view["captured"]),
        view["status"],
        view["winner"],
        [copy_position(position) for position in session.history],
    )


CAPTURES = [("e2", "e4"), ("d7", "d5"), ("e4", "d5"), ("d8", "d5")]


# 1. Redo restores what undo removed.


def test_redo_restores_a_capture_and_the_display() -> None:
    session = Session()
    for move in CAPTURES:
        play(session, *move)
    before = snapshot(session)
    undo(session)
    assert session.view()["captured"] == ["bP"]
    view = redo(session)
    assert snapshot(session) == before
    assert view["moves"][-1] == "d8xd5"
    assert view["captured"] == ["bP", "wP"]
    assert view["turn"] == "w"


@pytest.mark.parametrize("piece", list("QRBN"))
def test_redo_restores_a_promotion_with_the_chosen_piece(piece: str) -> None:
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    play(session, "b7", "a8", piece)
    undo(session)
    assert session.position[0]["b7"] == "wP"
    view = redo(session)
    assert view["board"]["a8"] == "w" + piece
    assert "b7" not in view["board"]
    assert view["moves"][-1] == f"b7xa8={piece}"
    assert view["captured"] == ["bP", "bR", "wP"]


def test_redo_restores_a_copy_not_the_stored_position() -> None:
    session = Session()
    play(session, "e2", "e4")
    undo(session)
    redo(session)
    play(session, "e7", "e5")
    undo(session)
    assert session.position[0].get("e7") == "bP"
    assert session.history[-1] == session.position


# 2. One step at a time.


def test_several_undos_then_redos_walk_forward_one_move_at_a_time() -> None:
    session = Session()
    for move in CAPTURES:
        play(session, *move)
    steps = [snapshot(session)]
    for _ in CAPTURES:
        undo(session)
        steps.append(snapshot(session))
    assert session.position == new_position()
    for expected in reversed(steps[:-1]):
        view = redo(session)
        assert snapshot(session) == expected
    assert view["can_redo"] is False


def test_redo_with_nothing_to_redo_does_nothing() -> None:
    session = Session()
    view = redo(session)
    assert view["can_redo"] is False and view["moves"] == []
    play(session, "e2", "e4")
    before = snapshot(session)
    assert redo(session)["can_redo"] is False
    assert snapshot(session) == before


def test_can_redo_follows_undo_and_redo() -> None:
    session = Session()
    assert session.view()["can_redo"] is False
    play(session, "e2", "e4")
    assert undo(session)["can_redo"] is True
    assert redo(session)["can_redo"] is False


# 3. A different move discards redo.


def test_a_different_move_after_undo_discards_redo() -> None:
    session = Session()
    play(session, "e2", "e4")
    play(session, "e7", "e5")
    undo(session)
    undo(session)
    play(session, "d2", "d4")
    view = redo(session)
    assert view["can_redo"] is False
    assert view["moves"] == ["d2-d4"]


def test_playing_the_same_move_by_hand_also_discards_redo() -> None:
    session = Session()
    play(session, "e2", "e4")
    play(session, "e7", "e5")
    undo(session)
    undo(session)
    play(session, "e2", "e4")
    assert session.view()["can_redo"] is False
    assert redo(session)["moves"] == ["e2-e4"]


# 4. Against the computer.


def computer_game() -> Session:
    """A seeded game: the computer's king takes White's queen on f7."""
    random.seed(1)
    session = Session("computer")
    for move in (("e2", "e4"), ("d1", "h5"), ("h5", "f7")):
        play(session, *move)
        session.dispatch({"action": "computer-move"})
    return session


def test_redo_against_the_computer_restores_the_same_reply() -> None:
    session = computer_game()
    before = snapshot(session)
    assert session.view()["moves"][-2:] == ["h5xf7+", "e8xf7"]
    view = undo(session)
    assert view["turn"] == "w" and len(view["moves"]) == 4
    random.seed(99)  # A different random source must not change the redone reply.
    view = redo(session)
    assert snapshot(session) == before
    assert view["turn"] == "w"
    assert view["captured"] == ["bP", "wQ"]
    assert not session.computer_to_move()


def test_several_undos_and_redos_against_the_computer() -> None:
    session = computer_game()
    before = snapshot(session)
    for expected_moves in (4, 2, 0):
        assert len(undo(session)["moves"]) == expected_moves
    for expected_moves in (2, 4, 6):
        view = redo(session)
        assert len(view["moves"]) == expected_moves
        assert view["turn"] == "w"
    assert snapshot(session) == before


def test_redo_before_the_computer_replied_restores_only_the_players_move() -> None:
    session = Session("computer")
    play(session, "e2", "e4")
    undo(session)
    view = redo(session)
    assert view["moves"] == ["e2-e4"]
    assert view["can_redo"] is False
    # The computer now replies as usual.
    assert session.computer_to_move()
    assert session.dispatch({"action": "computer-move"})["turn"] == "w"


# 5. Save and load keep redo.


def test_undo_save_load_redo() -> None:
    session = Session()
    for move in CAPTURES:
        play(session, *move)
    before = snapshot(session)
    undo(session)
    undo(session)
    data = session.save_data()
    assert data["version"] == 2
    assert [entry["notation"] for entry in data["redo"]] == ["e4xd5", "d8xd5"]
    loaded = reload(session)
    assert loaded.view()["can_redo"] is True
    redo(loaded)
    redo(loaded)
    assert snapshot(loaded) == before


def test_undo_save_load_redo_against_the_computer() -> None:
    session = computer_game()
    before = snapshot(session)
    undo(session)
    loaded = reload(session)
    assert loaded.view()["opponent"] == "computer"
    random.seed(99)
    redo(loaded)
    assert snapshot(loaded) == before


def test_undo_save_load_redo_with_a_promotion() -> None:
    session = Session()
    session.dispatch({"action": "promotion-setup"})
    play(session, "b7", "a8", "N")
    undo(session)
    loaded = reload(session)
    assert redo(loaded)["board"]["a8"] == "wN"


def test_version_1_files_still_load_with_nothing_to_redo() -> None:
    session = Session()
    play(session, "e2", "e4")
    data = json.loads(json.dumps(session.save_data()))
    data["version"] = 1
    del data["redo"]
    loaded = Session.from_save(data)
    assert loaded.view()["moves"] == ["e2-e4"]
    assert loaded.view()["can_redo"] is False


def saved_with_redo() -> dict[str, Any]:
    session = Session()
    for move in CAPTURES:
        play(session, *move)
    undo(session)
    undo(session)
    data: dict[str, Any] = json.loads(json.dumps(session.save_data()))
    return data


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(redo="e4xd5"),
        lambda d: d.update(redo=[["board", "w"]]),
        lambda d: d.pop("redo"),
        lambda d: d["redo"][0].update(notation="e4-d5"),
        lambda d: d["redo"][0].pop("notation"),
        lambda d: d["redo"][1]["board"].update(d5="bK"),
        lambda d: d["redo"].reverse(),
        lambda d: d["redo"].pop(0),
        lambda d: d["redo"][0].update(turn="w"),
    ],
)
def test_an_invalid_redo_continuation_is_rejected(change: Any) -> None:
    data = saved_with_redo()
    change(data)
    session = Session()
    play(session, "g1", "f3")
    before = snapshot(session)
    with pytest.raises(ValueError):
        session.dispatch({"action": "load", "game": data})
    assert snapshot(session) == before
    assert session.view()["can_redo"] is False


# 6. New game clears everything.


@pytest.mark.parametrize(
    "action",
    [
        {"action": "new"},
        {"action": "new", "opponent": "computer"},
        {"action": "promotion-setup"},
    ],
)
def test_a_new_game_clears_undo_and_redo(action: dict[str, Any]) -> None:
    session = Session()
    for move in CAPTURES:
        play(session, *move)
    undo(session)
    view = session.dispatch(action)
    assert view["can_redo"] is False
    assert redo(session)["can_redo"] is False


def test_loading_replaces_the_redo_continuation() -> None:
    session = Session()
    play(session, "e2", "e4")
    undo(session)
    session.dispatch({"action": "load", "game": Session().save_data()})
    assert session.view()["can_redo"] is False


# 7. Game end.


def test_redo_into_checkmate_ends_the_game_again() -> None:
    session = Session()
    for source, target in (("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4")):
        play(session, source, target)
    assert session.view()["status"] == "checkmate"
    undo(session)
    assert session.view()["status"] is None
    view = redo(session)
    assert view["status"] == "checkmate"
    assert view["winner"] == "Black"
    assert view["moves"][-1] == "d8-h4#"
