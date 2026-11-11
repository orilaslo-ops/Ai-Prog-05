"""Application actions and information shown beside the board."""

import json
import os
from pathlib import Path
from typing import Any

from computer import choose_move
from captured import missing_pieces
from game import (
    Position,
    coordinates,
    copy_position,
    legal_moves,
    move,
    new_position,
    status,
    winner,
)

# Legal from the standard starting position under this game's rules.
# Next move: b7-a8, capturing a rook and reaching the last rank.
PROMOTION_SETUP = [
    ("a2", "a4"),
    ("h7", "h5"),
    ("a4", "a5"),
    ("h5", "h4"),
    ("a5", "a6"),
    ("h4", "h3"),
    ("a6", "b7"),
    ("h3", "g2"),
]

# A saved game is a JSON object (see README, "Saving and loading"):
#   {"format": "chess-workshop-save", "version": 1, "opponent": "human" | "computer",
#    "notation": ["e2-e4", ...],
#    "history": [{"board": {"e2": "wP", ...}, "turn": "w"}, ...]}
# "history" and "notation" are Session.history and Session.notation, so undo works
# after loading. Loading checks that each position follows from the one before by the
# legal move named in "notation".
SAVE_FORMAT = "chess-workshop-save"
SAVE_VERSION = 1
PIECES = {side + kind for side in "wb" for kind in "KQRBNP"}


class Session:
    def __init__(self, opponent: str = "human") -> None:
        if opponent not in ("human", "computer"):
            raise ValueError("Unknown opponent")
        self.position = new_position()
        self.notation: list[str] = []
        self.captured: list[str] = []
        self.opponent = opponent
        # Shared game information: history[0] is the start and history[i + 1] is the
        # position after notation[i]. Undo, redo and save/load all build on this list.
        self.history = [copy_position(self.position)]

    def play(self, source: str, target: str) -> None:
        label = move(self.position, source, target)
        self.notation.append(label)
        self.history.append(copy_position(self.position))
        self.after_move()

    def undo(self) -> None:
        """Take back the last move. Against the computer, return to White's turn."""
        while len(self.history) > 1:
            self.history.pop()
            self.notation.pop()
            if self.opponent != "computer" or self.history[-1][1] == "w":
                break
        self.position = copy_position(self.history[-1])
        self.after_move()

    def after_move(self) -> None:
        self.captured = missing_pieces(self.position)

    def view(self) -> dict[str, Any]:
        return {
            "board": self.position[0],
            "turn": self.position[1],
            "moves": self.notation,
            "opponent": self.opponent,
            "status": status(self.position),
            "winner": winner(self.position),
            "can_undo": len(self.history) > 1,
            **self.sidebar(),
        }

    def save_data(self) -> dict[str, Any]:
        """Return the game as a JSON-ready dictionary."""
        return {
            "format": SAVE_FORMAT,
            "version": SAVE_VERSION,
            "opponent": self.opponent,
            "notation": list(self.notation),
            "history": [
                {"board": dict(board), "turn": turn} for board, turn in self.history
            ],
        }

    @classmethod
    def from_save(cls, data: object) -> "Session":
        """Build a new session from save_data(). Raise ValueError if it is not valid."""
        if not isinstance(data, dict) or data.get("format") != SAVE_FORMAT:
            raise ValueError("That file is not a saved chess game")
        if data.get("version") != SAVE_VERSION:
            raise ValueError("Unsupported save version")
        opponent: Any = data.get("opponent")
        session = cls(opponent)
        try:
            history = [saved_position(entry) for entry in saved_list(data, "history")]
            notation = saved_list(data, "notation")
            if not history or history[0] != new_position():
                raise ValueError("The game does not begin at the starting position")
            if len(notation) != len(history) - 1:
                raise ValueError("Expected one move label per move")
            for before, after, label in zip(history, history[1:], notation):
                if move_between(before, after) != label:
                    raise ValueError(f"{label!r} does not lead to the next position")
        except (ValueError, TypeError) as error:
            raise ValueError(f"The saved game is not valid: {error}") from None
        session.history = history
        session.notation = notation
        session.position = copy_position(history[-1])
        session.after_move()
        return session

    def load(self, data: object) -> None:
        """Replace this game with a saved one; on error the current game is unchanged."""
        self.__dict__.update(type(self).from_save(data).__dict__)

    def computer_to_move(self) -> bool:
        return (
            self.opponent == "computer"
            and self.position[1] == "b"
            and status(self.position) not in ("checkmate", "stalemate")
        )

    def sidebar(self) -> dict[str, Any]:
        return {"captured": self.captured}

    def dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        command = action.get("action")
        # Squares come from the request as sent; the game rules reject anything else.
        source: Any = action.get("source")
        target: Any = action.get("target")
        if command == "move":
            if self.computer_to_move():
                raise ValueError("Wait for the computer's move")
            self.play(source, target)
        elif command == "computer-move":
            if not self.computer_to_move():
                raise ValueError("It is not the computer's turn")
            choice = choose_move(self.position)
            if choice is None:
                raise ValueError("The computer has no move")
            self.play(*choice)
        elif command == "legal":
            return {"targets": legal_moves(self.position, source)}
        elif command == "new":
            Session.__init__(self, action.get("opponent", "human"))
        elif command == "save":
            return {"save": self.save_data()}
        elif command == "load":
            self.load(action.get("game"))
        elif command == "promotion-setup":
            Session.__init__(self)
            for source, target in PROMOTION_SETUP:
                self.play(source, target)
        elif command == "undo":
            self.undo()
        else:
            raise ValueError("Unknown action")
        return self.view()


def saved_list(data: dict[Any, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise TypeError(f"Expected a list for {key!r}")
    return value


def saved_position(entry: object) -> Position:
    """Read {"board": {...}, "turn": "w"} as a position, checking squares and pieces."""
    if not isinstance(entry, dict) or not isinstance(entry.get("board"), dict):
        raise TypeError('Expected a position such as {"board": {...}, "turn": "w"}')
    board, turn = entry["board"], entry.get("turn")
    for square, piece in board.items():
        coordinates(square)
        if piece not in PIECES:
            raise ValueError(f"Unknown piece {piece!r}")
    if turn not in ("w", "b"):
        raise ValueError("The side to move must be 'w' or 'b'")
    return [dict(board), turn]


def move_between(before: Position, after: Position) -> str | None:
    """Return the label of the legal move from before to after, or None."""
    old, new = before[0], after[0]
    vacated = [square for square in old if square not in new]
    changed = [square for square in new if old.get(square) != new[square]]
    if len(vacated) != 1 or len(changed) != 1:
        return None
    trial = copy_position(before)
    label = move(trial, vacated[0], changed[0])
    return label if trial == after else None


def save_file(session: Session, path: str | os.PathLike[str]) -> None:
    """Write the game to path as JSON."""
    text = json.dumps(session.save_data(), indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def load_file(
    path: str | os.PathLike[str], session_class: type[Session] = Session
) -> Session:
    """Read a game written by save_file into a new session."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not read the saved game: {error}") from None
    return session_class.from_save(data)
