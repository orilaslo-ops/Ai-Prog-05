"""Application actions and information shown beside the board."""

import json
import os
from pathlib import Path
from typing import Any

from computer import choose_move
from game import (
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
    ("a2", "a4"), ("h7", "h5"),
    ("a4", "a5"), ("h5", "h4"),
    ("a5", "a6"), ("h4", "h3"),
    ("a6", "b7"), ("h3", "g2"),
]

# A saved game is a JSON object (see README, "Saving and loading"):
#   {"format": "chess-workshop-save", "version": 1, "opponent": "human" | "computer",
#    "moves": [{"source": "e2", "target": "e4"}, ...],   # every move from the start
#    "redo":  [{"source": ..., "target": ...}, ...],     # undone moves, next one first
#    "board": {"e4": "wP", ...}, "turn": "w" | "b"}      # position after "moves"
# Loading replays "moves" from the starting position with the normal rules, so the
# notation and any per-move history are rebuilt exactly as they were played.
SAVE_FORMAT = "chess-workshop-save"
SAVE_VERSION = 1


class Session:
    def __init__(self, opponent="human"):
        if opponent not in ("human", "computer"):
            raise ValueError("Unknown opponent")
        self.position = new_position()
        self.notation = []
        self.opponent = opponent
        # Every move played from the starting position, as (source, target).
        self.history: list[tuple[str, str]] = []
        # Undone moves that can be played again, next one first. Saved with the game.
        self.redo: list[tuple[str, str]] = []

    def play(self, source, target):
        label = move(self.position, source, target)
        self.notation.append(label)
        self.history.append((source, target))
        self.after_move()

    def after_move(self):
        pass

    def view(self):
        return {
            "board": self.position[0],
            "turn": self.position[1],
            "moves": self.notation,
            "opponent": self.opponent,
            "status": status(self.position),
            "winner": winner(self.position),
            **self.sidebar(),
        }

    def save_data(self) -> dict[str, Any]:
        """Return the game as a JSON-ready dictionary."""
        return {
            "format": SAVE_FORMAT,
            "version": SAVE_VERSION,
            "opponent": self.opponent,
            "moves": [{"source": s, "target": t} for s, t in self.history],
            "redo": [{"source": s, "target": t} for s, t in self.redo],
            "board": dict(self.position[0]),
            "turn": self.position[1],
        }

    @classmethod
    def from_save(cls, data: object) -> "Session":
        """Build a new session from save_data(). Raise ValueError if it is not valid."""
        if not isinstance(data, dict) or data.get("format") != SAVE_FORMAT:
            raise ValueError("That file is not a saved chess game")
        if data.get("version") != SAVE_VERSION:
            raise ValueError("Unsupported save version")
        session = cls(data.get("opponent"))
        try:
            for source, target in saved_moves(data.get("moves")):
                session.play(source, target)
            redo = saved_moves(data.get("redo", []))
            trial = copy_position(session.position)
            for source, target in redo:
                move(trial, source, target)
        except (ValueError, TypeError) as error:
            raise ValueError(f"The saved game is not valid: {error}") from None
        if (
            data.get("board") != session.position[0]
            or data.get("turn") != session.position[1]
        ):
            raise ValueError("The saved board does not match its moves")
        session.redo = redo
        return session

    def load(self, data: object) -> None:
        """Replace this game with a saved one; on error the current game is unchanged."""
        self.__dict__.update(type(self).from_save(data).__dict__)

    def computer_to_move(self):
        return (self.opponent == "computer" and self.position[1] == "b"
                and status(self.position) not in ("checkmate", "stalemate"))

    def sidebar(self):
        return {}

    def dispatch(self, action):
        command = action.get("action")
        if command == "move":
            if self.computer_to_move():
                raise ValueError("Wait for the computer's move")
            self.play(action.get("source"), action.get("target"))
        elif command == "computer-move":
            if not self.computer_to_move():
                raise ValueError("It is not the computer's turn")
            self.play(*choose_move(self.position))
        elif command == "legal":
            return {"targets": legal_moves(self.position, action.get("source"))}
        elif command == "new":
            self.__init__(action.get("opponent", "human"))
        elif command == "save":
            return {"save": self.save_data()}
        elif command == "load":
            self.load(action.get("game"))
        elif command == "promotion-setup":
            self.__init__()
            for source, target in PROMOTION_SETUP:
                self.play(source, target)
        else:
            raise ValueError("Unknown action")
        return self.view()


def saved_moves(entries: object) -> list[tuple[Any, Any]]:
    """Read [{"source": ..., "target": ...}, ...] as (source, target) pairs."""
    if not isinstance(entries, list):
        raise TypeError("Expected a list of moves")
    moves = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError('Expected a move such as {"source": "e2", "target": "e4"}')
        moves.append((entry.get("source"), entry.get("target")))
    return moves


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
