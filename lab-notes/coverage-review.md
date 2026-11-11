# Coverage review

Run on `main` at d0181e5 (after captured pieces and promotion were merged), Python 3.12.
No code was changed for this review.

## Commands and results

| Command | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 15 files already formatted |
| `mypy --strict .` | Success: no issues found in 13 source files |
| `python -m pytest --cov --cov-branch --cov-report=term-missing` | 117 passed; 97% total |

## Coverage per file (lines and branches)

| File | Stmts | Miss | Branches | Partial | Cover | Missed lines |
|---|---|---|---|---|---|---|
| captured.py | 9 | 0 | 6 | 0 | 100% | |
| computer.py | 35 | 1 | 20 | 1 | 96% | 39 |
| game.py | 108 | 0 | 44 | 0 | 100% | |
| server.py | 57 | 23 | 12 | 4 | 55% | 30-42, 46-47, 51, 54, 65-75 |
| session.py | 138 | 2 | 54 | 2 | 98% | 157, 180 |
| tests/*.py | | 0 | | 0 | 100% | |

What the gaps are and whether they matter:

- `computer.py:39` (`if result == "stalemate": return 0`): the computer's score for a move
  that stalemates. Matters a little: nothing checks that the computer avoids stalemating
  a lost opponent, or takes a stalemate when it is losing.
- `server.py:30-42`: `GET /api/state` and the static routes (`/`, `/app.js`, `/style.css`,
  404). Matters: a broken route or content type would break the page and no test would fail.
- `server.py:46-47, 51, 54`: `POST` to a wrong path (404), a missing or oversized body, and a
  JSON body that is not an object. These are the server's input checks. Worth one test.
- `server.py:65-75`: the `__main__` block (arguments, `serve_forever`, Ctrl+C). Low value.
- `session.py:157`: "The computer has no move". It is unreachable, because
  `computer_to_move()` is false when the game is over. Doesn't matter.
- `session.py:180`: "Unknown action". Trivial, but a one-line test would cover it.

## Behavior that runs but isn't really checked

High line coverage hides these:

- **The browser code has no tests at all.** `static/app.js` holds the promotion dialog
  (choose a piece, Esc cancels), the Save, Load and Undo buttons, Ctrl+Z, the "That file is
  not a saved chess game" message, the computer's reply delay, and rendering (check
  highlight, captured panel, move list). `tests/test_shortcuts.py` only checks the Ctrl+Z
  source text.
- **HTTP layer.** `test_save_load_and_undo_over_http` is the only test going through the
  server. It covers `POST /api/action` and one 400 error. It doesn't cover `GET`, the
  static files, 404s, or request-size limits.
- **The single-threaded server.** One idle browser connection blocks every other request,
  which happened twice in this session. No test shows this, and it is a design limit of
  `HTTPServer` in `server.py`.
- **The computer's choices.** Tests check material, checkmate preference, promotion and
  random tie-breaking. They don't check stalemate scoring (see the mutation results below),
  or what it does when every move loses material.
- **Game-ending states with undo or load.** Undo from checkmate or stalemate back into a
  playable position isn't tested. Loading a finished game (checkmate or stalemate status
  after load) isn't tested. The computer's "has no move" path isn't tested either.
- **Notation over undo and redo of promotions.** One test checks that undo removes
  `b7xa8=Q`. Check together with promotion (`=Q+`) isn't asserted anywhere.
- **File input and output.** Non-UTF-8, empty and missing files are tested. Very large
  files (the server limits requests to 1 MB) and saves from a future version (only
  "unsupported version" is checked) aren't tested beyond that.
- **Weak assertions.** `test_undo_against_the_computer_restores_its_captures_too` and
  similar computer tests depend on `random.seed`. If the computer's choice rules change,
  they fail for reasons unrelated to undo. Tests that need a specific computer move would
  be sturdier if they passed `choose_move` a fixed `random.Random`.

## Mutation spot-checks

Each line was changed in a scratch copy of the code to see whether the tests notice:

| Mutation | Result |
|---|---|
| Undo against the computer stops after one move | caught |
| A promotion counts as a capture | caught |
| Load doesn't compare notation with the positions | caught |
| Load always promotes to a queen | caught |
| The "+" for check is dropped from notation | caught |
| A pawn may double-step from any rank | **missed** |
| The computer ignores the checkmate bonus | caught |
| The computer scores stalemate as material | **missed** |
| The server answers a bad request with 200 | caught |
| The server serves `index.html` for unknown paths | **missed** |
| Esc in the promotion dialog still sends the move | **missed** |
| Loading a non-JSON file shows no error | **missed** |
| New game keeps the old captured list | caught |

Rule and integration changes are caught well. Gaps remain in pawn movement from a
non-starting rank, computer stalemate handling, the static routes and all of `app.js`.

## Tests worth adding (by priority)

1. **A pawn double-step is allowed only from its starting rank**, for both colors. For
   example, a pawn on e3 cannot play e3-e5. This is a basic rule with no test today.
2. **Browser test of the promotion dialog and save/load** (Playwright, which is installed on
   most machines). Promote by choosing a knight, cancel with Esc and check nothing moved,
   save, load a bad file and check the error message.
3. **HTTP routes**: `GET /`, `/app.js`, `/style.css` and `/api/state` return 200 with the
   right content type. Unknown paths return 404. A POST with no body or a non-object body
   returns 400.
4. **Game-ending states with undo and load**: undo from checkmate restores play. A saved
   checkmate or stalemate loads with the right status and winner.
5. **The computer and stalemate**: when winning, the computer prefers a capture to a
   stalemating move. Use a fixed `random.Random` so the test is deterministic.
