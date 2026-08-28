"""Tests for the game engine: moves, scoring, state, terminal, load, reset.

Covers SPEC.md FR3 (apply a move, scoring actual removals rather than rectangle
area), FR4 (state reporting), FR6 (load a fixed layout), FR12 / section 8 (reset
is a ``GameEngine`` concern), and the MVP's deliberately simplified FR5
(``is_terminal`` means "fully cleared", not "no legal moves remain"). All
headless -- no display, no pygame.
"""

import pytest

from fruitbox.engine.board import BoardState
from fruitbox.engine.game import GameEngine, GameState
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


# --- construction ----------------------------------------------------------


def test_new_engine_starts_at_zero_score_with_every_apple_remaining():
    engine = _engine()

    assert engine.score == 0
    assert engine.apples_remaining == LAYOUT_APPLES


def test_engine_plays_on_the_board_object_it_was_given():
    state = BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)
    engine = GameEngine(state)

    assert engine.board is state


# --- apply_move ------------------------------------------------------------


def test_applying_a_legal_move_zeroes_exactly_the_rectangle():
    engine = _engine()

    engine.apply_move(SQUARE)

    assert engine.board.grid == [
        [0, 0, 3, 5],  # cols 0-1 cleared
        [0, 0, 2, 1],  # cols 0-1 cleared
        [0, 0, 9, 1],  # untouched
        [6, 8, 0, 5],  # untouched
    ]


def test_applying_a_legal_move_scores_the_cells_removed():
    engine = _engine()

    engine.apply_move(SQUARE)

    assert engine.score == 4
    assert engine.apples_remaining == LAYOUT_APPLES - 4


def test_move_spanning_empty_cells_scores_removals_not_rectangle_area():
    # row 2 is 0+0+9+1: a 4-cell rectangle that removes only 2 apples. Score and
    # the apple count must both move by 2, not by the rectangle's area of 4.
    engine = _engine()

    engine.apply_move(ROW_OVER_EMPTIES)

    assert engine.score == 2
    assert engine.apples_remaining == LAYOUT_APPLES - 2
    assert engine.board.grid[2] == [0, 0, 0, 0]


def test_vertical_move_spanning_an_empty_cell_scores_two():
    # col 0, rows 1-3: 4+0+6, so 3 cells of area but only 2 apples.
    engine = _engine()

    engine.apply_move(COL_OVER_EMPTY)

    assert engine.score == 2
    assert engine.apples_remaining == LAYOUT_APPLES - 2
    assert [row[0] for row in engine.board.grid] == [1, 0, 0, 0]


def test_apply_move_returns_none():
    engine = _engine()

    result = engine.apply_move(SQUARE)

    assert result is None


def test_successive_moves_accumulate_score():
    engine = _engine()

    engine.apply_move(SQUARE)  # 4 apples
    engine.apply_move(ROW_OVER_EMPTIES)  # 2 apples

    assert engine.score == 6
    assert engine.apples_remaining == LAYOUT_APPLES - 6


def test_apply_move_mutates_the_board_in_place_rather_than_replacing_it():
    engine = _engine()
    board_before = engine.board

    engine.apply_move(SQUARE)

    assert engine.board is board_before


def test_illegal_move_raises_value_error():
    engine = _engine()

    with pytest.raises(ValueError):
        engine.apply_move(ILLEGAL)


def test_illegal_move_leaves_grid_score_and_apple_count_untouched():
    engine = _engine()
    grid_before = [row[:] for row in engine.board.grid]

    with pytest.raises(ValueError):
        engine.apply_move(ILLEGAL)

    assert engine.board.grid == grid_before
    assert engine.score == 0
    assert engine.apples_remaining == LAYOUT_APPLES


def test_out_of_bounds_move_raises_value_error_and_changes_nothing():
    engine = _engine()
    grid_before = [row[:] for row in engine.board.grid]

    with pytest.raises(ValueError):
        # In bounds this row sums to 10, but col_end 9 runs off the 4-wide board.
        engine.apply_move(Move(row_start=2, col_start=0, row_end=2, col_end=9))

    assert engine.board.grid == grid_before
    assert engine.score == 0
    assert engine.apples_remaining == LAYOUT_APPLES


def test_replaying_an_already_cleared_rectangle_is_illegal():
    engine = _engine()
    engine.apply_move(SQUARE)

    with pytest.raises(ValueError):
        engine.apply_move(SQUARE)  # now sums to 0

    assert engine.score == 4
    assert engine.apples_remaining == LAYOUT_APPLES - 4


# --- get_state -------------------------------------------------------------


def test_get_state_reports_the_live_board_and_current_counters():
    engine = _engine()
    engine.apply_move(SQUARE)
    engine.apply_move(ROW_OVER_EMPTIES)

    state = engine.get_state()

    assert isinstance(state, GameState)
    assert state.board is engine.board
    assert state.score == engine.score == 6
    assert state.apples_remaining == engine.apples_remaining == LAYOUT_APPLES - 6


def test_get_state_apple_count_matches_a_direct_scan_of_the_grid():
    engine = _engine()
    engine.apply_move(SQUARE)

    state = engine.get_state()
    scanned = sum(1 for row in state.board.grid for value in row if value != 0)

    assert state.apples_remaining == scanned


def test_get_state_on_a_fresh_engine_reflects_the_starting_board():
    engine = _engine()

    state = engine.get_state()

    assert state.board.grid == LAYOUT
    assert state.score == 0
    assert state.apples_remaining == LAYOUT_APPLES


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

    assert engine.apples_remaining == 0
    assert engine.board.grid == [[0, 0], [0, 0]]
    assert engine.is_terminal()


def test_engine_loaded_on_an_already_empty_board_is_terminal():
    engine = GameEngine.load([[0, 0], [0, 0]])

    assert engine.apples_remaining == 0
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
    assert state.apples_remaining == LAYOUT_APPLES


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
    assert engine.apples_remaining == LAYOUT_APPLES


def test_reset_on_an_unplayed_engine_is_a_no_op():
    engine = _engine()

    engine.reset()

    assert engine.board.grid == LAYOUT
    assert engine.score == 0
    assert engine.apples_remaining == LAYOUT_APPLES


def test_reset_keeps_the_same_board_object():
    engine = _engine()
    board_before = engine.board
    engine.apply_move(SQUARE)

    engine.reset()

    assert engine.board is board_before


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
    assert engine.apples_remaining == LAYOUT_APPLES


def test_play_after_reset_behaves_like_a_fresh_game():
    engine = _engine()
    engine.apply_move(SQUARE)
    engine.reset()

    engine.apply_move(SQUARE)

    assert engine.score == 4
    assert engine.apples_remaining == LAYOUT_APPLES - 4


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
