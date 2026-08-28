"""Tests for board state, move application, and seeded generation (issues #2, #4).

Covers SPEC.md FR1 (generation with a guaranteed multiple-of-10 total), FR3
(``apply_move`` clears a legal rectangle and reports the apples it really
removed), section 8 (``BoardState`` and its ``copy()`` deep-copy contract), and
NFR5 (seed reproducibility). All headless -- no display, no pygame.

The legality *rule* behind ``apply_move`` is exercised through the
``is_legal_move`` free function in ``test_game.py``; what is tested here is that
``apply_move`` enforces it and mutates correctly when it passes.
"""

import pytest

from fruitbox.config import (
    GRID_COLS,
    GRID_ROWS,
    MAX_CELL_VALUE,
    MIN_CELL_VALUE,
    TARGET_SUM,
)
from fruitbox.engine.board import BoardState, generate_board
from fruitbox.engine.moves import Move

# A 4x4 hand-authored layout with known legal and illegal rectangles:
#
#   - rows 0-1, cols 0-1 (2x2)  -> 1+2+4+3 = 10, legal, 4 apples removed
#   - row 2, cols 0-3 (1x4)     -> 0+0+9+1 = 10, legal, only 2 apples removed
#   - col 0, rows 1-3 (3x1)     -> 4+0+6   = 10, legal, only 2 apples removed
#   - row 0, cols 0-1           -> 1+2     =  3, illegal (too low)
LAYOUT = [
    [1, 2, 3, 5],
    [4, 3, 2, 1],
    [0, 0, 9, 1],
    [6, 8, 0, 5],
]

SQUARE = Move(row_start=0, col_start=0, row_end=1, col_end=1)
ROW_OVER_EMPTIES = Move(row_start=2, col_start=0, row_end=2, col_end=3)
COL_OVER_EMPTY = Move(row_start=1, col_start=0, row_end=3, col_end=0)
ILLEGAL = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # sums to 3


def _board() -> BoardState:
    """A fresh 4x4 ``BoardState`` on ``LAYOUT`` (never the shared list)."""
    return BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)


def _total(state: BoardState) -> int:
    return sum(sum(row) for row in state.grid)


# --- BoardState.copy() -----------------------------------------------------


def test_copy_is_independent_of_original():
    original = BoardState(
        grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        rows=3,
        cols=3,
    )

    clone = original.copy()
    clone.grid[1][1] = 0

    assert original.grid == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert clone.grid == [[1, 2, 3], [4, 0, 6], [7, 8, 9]]


def test_copy_preserves_dimensions_and_contents():
    original = BoardState(grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], rows=3, cols=3)

    clone = original.copy()

    assert clone.rows == original.rows == 3
    assert clone.cols == original.cols == 3
    assert clone.grid == original.grid
    # The row lists must be distinct objects, not shared references.
    assert all(a is not b for a, b in zip(clone.grid, original.grid))


def test_copy_of_original_does_not_alias_after_mutating_original():
    original = BoardState(grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], rows=3, cols=3)

    clone = original.copy()
    original.grid[0][0] = 0

    assert clone.grid[0][0] == 1


# --- BoardState.apply_move(): legal moves ----------------------------------


def test_apply_move_zeroes_exactly_the_rectangle_and_returns_the_count():
    state = _board()

    removed = state.apply_move(SQUARE)

    assert removed == 4
    assert state.grid == [
        [0, 0, 3, 5],  # cols 0-1 cleared
        [0, 0, 2, 1],  # cols 0-1 cleared
        [0, 0, 9, 1],  # untouched
        [6, 8, 0, 5],  # untouched
    ]


def test_apply_move_spanning_empty_cells_returns_removals_not_rectangle_area():
    # row 2 is 0+0+9+1: a 4-cell rectangle that removes only 2 apples.
    state = _board()

    removed = state.apply_move(ROW_OVER_EMPTIES)

    assert removed == 2
    assert state.grid == [
        [1, 2, 3, 5],
        [4, 3, 2, 1],
        [0, 0, 0, 0],  # the two apples cleared, the two empties left alone
        [6, 8, 0, 5],
    ]


def test_apply_move_spanning_an_empty_cell_vertically_returns_two():
    # col 0, rows 1-3: 4+0+6, so 3 cells of area but only 2 apples.
    state = _board()

    removed = state.apply_move(COL_OVER_EMPTY)

    assert removed == 2
    assert state.grid == [
        [1, 2, 3, 5],  # untouched: the rectangle starts at row 1
        [0, 3, 2, 1],
        [0, 0, 9, 1],
        [0, 8, 0, 5],
    ]


def test_successive_apply_moves_each_report_their_own_removals():
    state = _board()

    first = state.apply_move(SQUARE)
    second = state.apply_move(ROW_OVER_EMPTIES)

    assert (first, second) == (4, 2)
    assert state.grid == [
        [0, 0, 3, 5],
        [0, 0, 2, 1],
        [0, 0, 0, 0],
        [6, 8, 0, 5],
    ]


# --- BoardState.apply_move(): rejected moves -------------------------------


def test_apply_move_rejects_a_rectangle_that_does_not_sum_to_the_target():
    state = _board()

    with pytest.raises(ValueError):
        state.apply_move(ILLEGAL)  # 1 + 2 == 3

    assert state.grid == LAYOUT


def test_apply_move_rejects_an_out_of_bounds_rectangle():
    # In bounds this row sums to 10, but col_end 9 runs off the 4-wide board.
    state = _board()

    with pytest.raises(ValueError):
        state.apply_move(Move(row_start=2, col_start=0, row_end=2, col_end=9))

    assert state.grid == LAYOUT


def test_apply_move_rejects_a_rectangle_entirely_off_the_board():
    state = _board()

    with pytest.raises(ValueError):
        state.apply_move(Move(row_start=10, col_start=10, row_end=11, col_end=11))

    assert state.grid == LAYOUT


def test_replaying_an_already_cleared_rectangle_is_rejected():
    state = _board()
    state.apply_move(SQUARE)
    grid_after_first = [row[:] for row in state.grid]

    with pytest.raises(ValueError):
        state.apply_move(SQUARE)  # now all zeros, so it sums to 0

    assert state.grid == grid_after_first


# --- BoardState.verify() ---------------------------------------------------


def test_verify_accepts_well_formed_board():
    state = BoardState(grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], rows=3, cols=3)

    assert state.verify() is None


def test_verify_rejects_mismatched_dimensions():
    # rows says 3, but the grid only holds 2 rows.
    state = BoardState(grid=[[1, 2, 3], [4, 5, 6]], rows=3, cols=3)

    with pytest.raises(AssertionError):
        state.verify()


def test_verify_rejects_out_of_range_cell_value():
    # 42 is neither 0 (empty) nor within [MIN_CELL_VALUE, MAX_CELL_VALUE].
    state = BoardState(grid=[[1, 2, 3], [4, 42, 6], [7, 8, 9]], rows=3, cols=3)

    with pytest.raises(AssertionError):
        state.verify()


# --- generate_board: determinism (NFR5) ------------------------------------


def test_same_seed_produces_identical_boards():
    first = generate_board(seed=42)
    second = generate_board(seed=42)

    assert first.grid == second.grid


def test_different_seeds_produce_different_boards():
    # Not a strict mathematical guarantee, but with 170 cells a collision is
    # astronomically unlikely.
    a = generate_board(seed=1)
    b = generate_board(seed=2)
    c = generate_board(seed=3)

    assert a.grid != b.grid
    assert b.grid != c.grid
    assert a.grid != c.grid


def test_generation_does_not_disturb_global_random_state():
    import random

    random.seed(12345)
    expected = [random.random() for _ in range(3)]

    random.seed(12345)
    generate_board(seed=7)
    generate_board()
    actual = [random.random() for _ in range(3)]

    assert actual == expected


# --- generate_board: FR1 sum invariant -------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234, 20260828])
def test_total_sum_is_multiple_of_ten_default_grid(seed):
    state = generate_board(seed=seed)

    assert _total(state) % TARGET_SUM == 0


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234, 20260828])
def test_total_sum_is_multiple_of_ten_small_grid(seed):
    state = generate_board(rows=3, cols=3, seed=seed)

    assert _total(state) % TARGET_SUM == 0


@pytest.mark.parametrize("rows,cols", [(1, 2), (2, 2), (3, 3), (4, 7), (10, 17)])
def test_total_sum_is_multiple_of_ten_across_shapes(rows, cols):
    state = generate_board(rows=rows, cols=cols, seed=2024)

    assert _total(state) % TARGET_SUM == 0


# --- generate_board: value range and dimensions ----------------------------


@pytest.mark.parametrize("seed", [0, 5, 42, 777])
def test_all_cells_within_value_range(seed):
    state = generate_board(seed=seed)

    for row in state.grid:
        for value in row:
            # A freshly generated board has no empty cells, so 0 is excluded.
            assert MIN_CELL_VALUE <= value <= MAX_CELL_VALUE


@pytest.mark.parametrize("rows,cols", [(1, 2), (3, 3), (10, 17)])
def test_dimensions_match_requested_shape(rows, cols):
    state = generate_board(rows=rows, cols=cols, seed=11)

    assert state.rows == rows
    assert state.cols == cols
    assert len(state.grid) == rows
    assert all(len(row) == cols for row in state.grid)


def test_defaults_come_from_config():
    state = generate_board(seed=3)

    assert state.rows == GRID_ROWS
    assert state.cols == GRID_COLS
    assert len(state.grid) == GRID_ROWS
    assert all(len(row) == GRID_COLS for row in state.grid)


# --- generate_board: minimum-size edge case --------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_minimum_board_of_two_cells(seed):
    """rows*cols - 2 == 0: the whole board is just the two adjusted cells."""
    state = generate_board(rows=1, cols=2, seed=seed)

    assert state.rows == 1
    assert state.cols == 2
    assert len(state.grid) == 1
    assert len(state.grid[0]) == 2
    assert all(MIN_CELL_VALUE <= v <= MAX_CELL_VALUE for v in state.grid[0])
    assert _total(state) % TARGET_SUM == 0


# --- generate_board: unseeded -----------------------------------------------


def test_unseeded_generation_still_satisfies_invariants():
    for _ in range(5):
        state = generate_board()

        assert state.rows == GRID_ROWS
        assert state.cols == GRID_COLS
        assert len(state.grid) == GRID_ROWS
        assert all(len(row) == GRID_COLS for row in state.grid)
        assert all(
            MIN_CELL_VALUE <= value <= MAX_CELL_VALUE
            for row in state.grid
            for value in row
        )
        assert _total(state) % TARGET_SUM == 0
