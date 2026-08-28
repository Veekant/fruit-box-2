"""Tests for board state and seeded board generation (issue #2).

Covers SPEC.md FR1 (generation with a guaranteed multiple-of-10 total), section 8
(``BoardState`` and its ``copy()`` deep-copy contract), and NFR5 (seed
reproducibility). All headless -- no display, no pygame.
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
