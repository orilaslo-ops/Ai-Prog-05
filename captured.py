"""The captured-pieces sidebar."""

from itertools import pairwise

from game import Position, other


def captured_pieces(history: list[Position]) -> list[str]:
    """Pieces captured in the game so far, as they were when captured, sorted.

    Each move can capture at most one piece (there is no en passant): an opponent
    piece whose square is taken over by the moving side. A promotion changes the
    mover's own piece, so on its own it captures nothing.
    """
    captured: list[str] = []
    for before, after in pairwise(history):
        opponent = other(before[1])
        for square, piece in before[0].items():
            if piece[0] == opponent and after[0].get(square) != piece:
                captured.append(piece)
    return sorted(captured)
