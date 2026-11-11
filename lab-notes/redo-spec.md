# Redo: expected behavior

We agreed on this before implementing redo. Each point has a test in
`tests/test_redo.py` (unit and HTTP) or `tests/test_browser.py` (browser).

## Mechanism

Undo moves the positions it removes from `Session.history` (and their labels from
`Session.notation`) onto `Session.redo`. Redo moves them back. Redo restores the stored
positions exactly; it does not replay or recompute moves.

## Outcomes

1. **Redo restores what undo removed.** The board, the side to move, the notation and the
   captured-pieces display all come back. A redone capture is listed again, and a redone
   promotion restores the chosen piece (for example `b7xa8=N`, with a knight on a8).
2. **One step at a time.** Several undos followed by several redos walk forward one move
   at a time and end where they started. Redo with nothing to redo does nothing, and the
   Redo button is disabled (`can_redo` is false).
3. **A different move discards redo.** After an undo, any new move clears the redo
   continuation, including the same move played again by hand.
4. **Against the computer.** Undo takes back the player's move and the computer's reply
   together (existing behavior). Redo restores both, with the computer's **same** reply;
   nothing is chosen again. Redo never asks the computer for a new move. If the player
   undid before the computer replied, redo restores only the player's move. The computer
   then replies as usual, and that reply may differ.
5. **Save and load keep redo.** The save file stores the redo continuation (positions and
   notation, next move first), so undo → save → load → redo works, against the computer
   too. The save format becomes version 2. Version 1 files still load, with nothing to
   redo. When loading, each redo position must follow legally from the one before
   (promotions included) and match its notation; otherwise the file is rejected and the
   current game is unchanged.
6. **New game clears everything.** Starting a new game, with either opponent, clears both
   undo and redo history. The same goes for promotion-setup.
7. **Game end.** Redoing into checkmate or stalemate ends the game again with the same
   status and winner.
8. **Controls.** A **Redo** button next to **Undo**, disabled when there is nothing to
   redo. The keyboard shortcuts are Ctrl+Y and Ctrl+Shift+Z (Cmd on a Mac). They use the
   physical key (`event.code`), so they work with a Hebrew keyboard layout too.
