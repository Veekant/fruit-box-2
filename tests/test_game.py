"""Tests for the game engine: legality, scoring, state, terminal, load, reset.

Covers SPEC.md FR2 (the ``is_legal_move`` free function, which lives here rather
than in ``moves`` so that ``board`` can own the rule without a circular import),
FR3 (apply a move, scoring actual removals rather than rectangle area), FR4
(state reporting), FR6 (load a fixed layout), FR12 / section 8 (reset is a
``GameEngine`` concern), and the MVP's deliberately simplified FR5
(``is_terminal`` means "fully cleared", not "no legal moves remain"). All
headless -- no display, no pygame.

``GameEngine.apply_move`` delegates the legality check and the cell clearing to
``BoardState.apply_move``; the mechanics of that are tested in ``test_board.py``,
so the tests here only pin down what this layer adds -- counter updates and
exception propagation.
"""

import pytest

from fruitbox.engine.board import BoardState
from fruitbox.engine.game import GameEngine, GameState, is_legal_move
from fruitbox.engine.moves import Move

# A 4x4 hand-authored layout with known legal and illegal rectangles:
#
#   - rows 0-1, cols 0-1 (2x2)  -> 1+2+4+3 = 10, legal, 4 apples removed
#   - row 2, cols 0-3 (1x4)     -> 0+0+9+1 = 10, legal, only 2 apples removed
#   - col 0, rows 1-3 (3x1)     -> 4+0+6   = 10, legal, only 2 apples removed
#   - row 0, cols 0-1           -> 1+2     =  3, illegal (too low)
#   - row 0, cols 0-3           -> 1+2+3+5 = 11, illegal (too high)
#
# It holds 3 empty cells -- (2,0), (2,1), (3,2) -- so 13 apples in total.
LAYOUT = [
    [1, 2, 3, 5],
    [4, 3, 2, 1],
    [0, 0, 9, 1],
    [6, 8, 0, 5],
]
LAYOUT_APPLES = 13

# Legal on LAYOUT: a fully occupied 2x2 (4 apples) and a 1x4 row spanning two
# already-empty cells (2 apples, but 4 cells of area).
SQUARE = Move(row_start=0, col_start=0, row_end=1, col_end=1)
ROW_OVER_EMPTIES = Move(row_start=2, col_start=0, row_end=2, col_end=3)
COL_OVER_EMPTY = Move(row_start=1, col_start=0, row_end=3, col_end=0)
ILLEGAL = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # sums to 3


def _engine() -> GameEngine:
    """A fresh engine on a fresh copy of ``LAYOUT`` (never the shared list)."""
    return GameEngine.load([row[:] for row in LAYOUT])


def _clearable_engine() -> GameEngine:
    """A 2x2 board that two legal moves clear completely: 4+6 and 1+9."""
    return GameEngine.load([[4, 6], [1, 9]])


def _board() -> BoardState:
    """A fresh ``BoardState`` on ``LAYOUT``, for the ``is_legal_move`` tests.

    ``LAYOUT`` already carries a witness for every legality case below:

    - ``rows 0-1, cols 0-1`` (2x2)      -> 1+2+4+3 = 10, legal
    - ``row 2, cols 0-3`` (1x4)         -> 0+0+9+1 = 10, legal across empties
    - ``col 0, rows 1-3`` (3x1)         -> 4+0+6   = 10, legal across an empty
    - ``row 0, cols 0-1``               -> 1+2     =  3, too low
    - ``row 0, cols 0-3``               -> 1+2+3+5 = 11, too high
    - ``row 2, cols 0-1``               -> 0+0     =  0, all-empty
    """
    return BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)


# --- construction ----------------------------------------------------------


def test_new_engine_starts_at_zero_score_with_every_apple_remaining():
    engine = _engine()

    assert engine.score == 0
    assert engine.board.apples_remaining == LAYOUT_APPLES


def test_engine_plays_on_the_board_object_it_was_given():
    state = BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)
    engine = GameEngine(state)

    assert engine.board is state


# --- is_legal_move: legal --------------------------------------------------


def test_rectangle_summing_to_ten_is_legal():
    # rows 0-1, cols 0-1: 1 + 2 + 4 + 3 == 10
    assert is_legal_move(_board(), Move(row_start=0, col_start=0, row_end=1, col_end=1))


def test_rectangle_spanning_empty_cells_is_legal():
    # row 2: 0 + 0 + 9 + 1 == 10. The two empty cells contribute nothing and do
    # not disqualify the rectangle (SPEC.md section 2: no occupancy check).
    assert is_legal_move(_board(), Move(row_start=2, col_start=0, row_end=2, col_end=3))


def test_vertical_rectangle_spanning_an_empty_cell_is_legal():
    # col 0, rows 1-3: 4 + 0 + 6 == 10
    assert is_legal_move(_board(), Move(row_start=1, col_start=0, row_end=3, col_end=0))


def test_legality_check_does_not_mutate_the_board():
    state = _board()
    before = [row[:] for row in state.grid]

    is_legal_move(state, Move(row_start=0, col_start=0, row_end=1, col_end=1))

    assert state.grid == before


# --- is_legal_move: illegal sums -------------------------------------------


def test_sum_below_target_is_illegal():
    # row 0, cols 0-1: 1 + 2 == 3
    assert not is_legal_move(
        _board(), Move(row_start=0, col_start=0, row_end=0, col_end=1)
    )


def test_sum_above_target_is_illegal():
    # row 0, cols 0-3: 1 + 2 + 3 + 5 == 11
    assert not is_legal_move(
        _board(), Move(row_start=0, col_start=0, row_end=0, col_end=3)
    )


def test_all_empty_rectangle_is_illegal():
    # row 2, cols 0-1: 0 + 0 == 0
    assert not is_legal_move(
        _board(), Move(row_start=2, col_start=0, row_end=2, col_end=1)
    )


def test_single_cell_move_is_never_legal():
    # SPEC.md section 2's explicit degenerate-shape case: a 1x1 rectangle holds
    # either 0 or 1-9, so it can never sum to 10. Falls out of the sum check --
    # there is no special-cased size rule in the code.
    state = _board()

    for row, col in [(0, 0), (2, 2), (3, 1), (2, 0)]:
        move = Move(row_start=row, col_start=col, row_end=row, col_end=col)

        assert not is_legal_move(state, move)


# --- is_legal_move: out of bounds ------------------------------------------


def test_rectangle_extending_past_last_row_is_illegal():
    # row_end == 4 on a 4-row board.
    assert not is_legal_move(
        _board(), Move(row_start=0, col_start=0, row_end=4, col_end=0)
    )


def test_rectangle_extending_past_last_col_is_illegal():
    # col_end == 4 on a 4-column board.
    assert not is_legal_move(
        _board(), Move(row_start=0, col_start=0, row_end=0, col_end=4)
    )


def test_out_of_bounds_rectangle_returns_false_rather_than_raising():
    # The in-bounds part of this rectangle (row 2, cols 0-3) does sum to 10, so
    # this pins down that the bounds check runs first and short-circuits: the
    # result is False, not an IndexError and not True.
    state = _board()
    move = Move(row_start=2, col_start=0, row_end=2, col_end=9)

    assert not is_legal_move(state, move)


def test_rectangle_entirely_outside_the_board_is_illegal():
    assert not is_legal_move(
        _board(), Move(row_start=10, col_start=10, row_end=11, col_end=11)
    )


def test_move_legal_on_a_larger_board_is_out_of_bounds_on_a_smaller_one():
    small = BoardState(grid=[[4, 6], [1, 2]], rows=2, cols=2)
    large = BoardState(grid=[[4, 6, 1], [1, 2, 3], [7, 8, 9]], rows=3, cols=3)
    # rows 0-2, col 0 on the 3x3: 4 + 1 + 7 == 12; rows 0-1 col 0 there is 5.
    spanning = Move(row_start=0, col_start=0, row_end=2, col_end=0)

    assert not is_legal_move(small, spanning)  # off the bottom of the 2x2
    assert not is_legal_move(large, spanning)  # in bounds, but sums to 12
    # Bounds are read from the state, not from module-level config.
    assert is_legal_move(small, Move(row_start=0, col_start=0, row_end=0, col_end=1))


# --- apply_move ------------------------------------------------------------
#
# The clearing mechanics themselves (which cells are zeroed, what the removal
# count is, and that an illegal move mutates nothing) belong to
# BoardState.apply_move and are tested in test_board.py. What follows only
# covers what this layer adds on top of that delegation.


def test_successive_moves_accumulate_score_and_drain_the_apple_count():
    # SQUARE removes 4 apples from 4 cells; ROW_OVER_EMPTIES removes only 2 from
    # a 4-cell rectangle. The counters must therefore land on 6, not 8 -- the
    # delegated removal count, never the rectangle area.
    engine = _engine()

    engine.apply_move(SQUARE)  # 4 apples
    engine.apply_move(ROW_OVER_EMPTIES)  # 2 apples, 4 cells of area

    assert engine.score == 6
    assert engine.board.apples_remaining == LAYOUT_APPLES - 6


def test_apply_move_returns_none():
    engine = _engine()

    result = engine.apply_move(SQUARE)

    assert result is None


def test_apply_move_mutates_the_board_in_place_rather_than_replacing_it():
    engine = _engine()
    board_before = engine.board

    engine.apply_move(SQUARE)

    assert engine.board is board_before


def test_illegal_move_propagates_value_error_without_touching_any_state():
    # The board raises before mutating a cell, and the counters are only updated
    # once it returns -- so a rejected move must leave the engine untouched
    # rather than partially updated.
    engine = _engine()
    grid_before = [row[:] for row in engine.board.grid]

    with pytest.raises(ValueError):
        engine.apply_move(ILLEGAL)

    assert engine.board.grid == grid_before
    assert engine.score == 0
    assert engine.board.apples_remaining == LAYOUT_APPLES


# --- get_state -------------------------------------------------------------


def test_get_state_reports_the_live_board_and_current_counters():
    engine = _engine()
    engine.apply_move(SQUARE)
    engine.apply_move(ROW_OVER_EMPTIES)

    state = engine.get_state()

    assert isinstance(state, GameState)
    assert state.board is engine.board
    assert state.score == engine.score == 6
    assert state.board.apples_remaining == LAYOUT_APPLES - 6


def test_get_state_apple_count_matches_a_direct_scan_of_the_grid():
    engine = _engine()
    engine.apply_move(SQUARE)

    state = engine.get_state()
    scanned = sum(1 for row in state.board.grid for value in row if value != 0)

    assert state.board.apples_remaining == scanned


def test_get_state_on_a_fresh_engine_reflects_the_starting_board():
    engine = _engine()

    state = engine.get_state()

    assert state.board.grid == LAYOUT
    assert state.score == 0
    assert state.board.apples_remaining == LAYOUT_APPLES


# --- is_terminal -----------------------------------------------------------


def test_fresh_engine_on_a_non_empty_board_is_not_terminal():
    assert not _engine().is_terminal()


def test_partially_cleared_board_is_not_terminal():
    engine = _engine()

    engine.apply_move(SQUARE)

    assert not engine.is_terminal()


def test_fully_cleared_board_is_terminal():
    engine = _clearable_engine()

    engine.apply_move(Move(row_start=0, col_start=0, row_end=0, col_end=1))  # 4+6
    engine.apply_move(Move(row_start=1, col_start=0, row_end=1, col_end=1))  # 1+9

    assert engine.board.apples_remaining == 0
    assert engine.board.grid == [[0, 0], [0, 0]]
    assert engine.is_terminal()


def test_engine_loaded_on_an_already_empty_board_is_terminal():
    engine = GameEngine.load([[0, 0], [0, 0]])

    assert engine.board.apples_remaining == 0
    assert engine.is_terminal()


# --- load ------------------------------------------------------------------


def test_load_infers_rows_and_cols_from_the_grid():
    engine = GameEngine.load([[1, 2, 3, 4], [5, 6, 7, 8], [9, 1, 2, 3]])

    assert engine.board.rows == 3
    assert engine.board.cols == 4


def test_load_produces_a_working_engine_reflecting_the_given_layout():
    engine = GameEngine.load([row[:] for row in LAYOUT])

    state = engine.get_state()

    assert state.board.grid == LAYOUT
    assert state.score == 0
    assert state.board.apples_remaining == LAYOUT_APPLES


def test_loaded_engine_can_play_a_legal_move():
    engine = GameEngine.load([[4, 6], [1, 9]])

    engine.apply_move(Move(row_start=0, col_start=0, row_end=0, col_end=1))

    assert engine.score == 2
    assert engine.board.grid == [[0, 0], [1, 9]]


def test_load_rejects_a_ragged_grid():
    with pytest.raises(AssertionError):
        GameEngine.load([[1, 2, 3], [4, 5]])


def test_load_rejects_an_out_of_range_value():
    with pytest.raises(AssertionError):
        GameEngine.load([[1, 2], [3, 42]])


# --- reset -----------------------------------------------------------------


def test_reset_restores_grid_score_and_apple_count_after_play():
    engine = _engine()
    engine.apply_move(SQUARE)
    engine.apply_move(ROW_OVER_EMPTIES)

    engine.reset()

    assert engine.board.grid == LAYOUT
    assert engine.score == 0
    assert engine.board.apples_remaining == LAYOUT_APPLES


def test_reset_on_an_unplayed_engine_is_a_no_op():
    engine = _engine()

    engine.reset()

    assert engine.board.grid == LAYOUT
    assert engine.score == 0
    assert engine.board.apples_remaining == LAYOUT_APPLES


def test_reset_twice_around_different_play_still_restores_the_original():
    engine = _engine()

    engine.apply_move(SQUARE)
    engine.reset()
    # A different set of moves the second time round, to catch a snapshot that
    # is aliased to the live grid or otherwise mutated by intervening play.
    engine.apply_move(ROW_OVER_EMPTIES)
    engine.apply_move(COL_OVER_EMPTY)
    engine.reset()

    assert engine.board.grid == LAYOUT
    assert engine.score == 0
    assert engine.board.apples_remaining == LAYOUT_APPLES


def test_play_after_reset_behaves_like_a_fresh_game():
    engine = _engine()
    engine.apply_move(SQUARE)
    engine.reset()

    engine.apply_move(SQUARE)

    assert engine.score == 4
    assert engine.board.apples_remaining == LAYOUT_APPLES - 4


def test_reset_restores_a_fully_cleared_board():
    engine = _clearable_engine()
    engine.apply_move(Move(row_start=0, col_start=0, row_end=0, col_end=1))
    engine.apply_move(Move(row_start=1, col_start=0, row_end=1, col_end=1))
    assert engine.is_terminal()

    engine.reset()

    assert engine.board.grid == [[4, 6], [1, 9]]
    assert not engine.is_terminal()


def test_reset_is_unaffected_by_mutating_the_grid_the_engine_was_built_from():
    # The engine snapshots at construction, so later edits to the caller's grid
    # object (which the engine also plays on) must not leak into the snapshot.
    grid = [[4, 6], [1, 9]]
    engine = GameEngine.load(grid)

    grid[0][0] = 0
    grid[0][1] = 0
    engine.reset()

    assert engine.board.grid == [[4, 6], [1, 9]]
