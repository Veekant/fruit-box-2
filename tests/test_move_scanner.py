"""Tests for legal-move enumeration (issue #6).

Covers SPEC.md section 10's must-have cases -- overlapping candidate
rectangles, a rectangle spanning empty cells, and zero legal moves -- plus the
ordering contract and the non-mutation guarantee. All headless -- no display,
no pygame.

The randomized cross-check against ``BoardState.is_legal``, a full-board
timing assertion (NFR4), and additional edge fixtures are deferred to issue
#7, which owns broader enumeration test coverage.
"""

from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move
from fruitbox.solver.move_scanner import find_legal_moves

# --- Exact move sets ---------------------------------------------------------


def test_returns_exact_expected_move_set():
    # Legal set (verified by hand): (0,0,0,2) [1+2+7], (0,0,1,1) [1+2+3+4],
    # (2,0,2,1) [5+5], (2,0,2,2) [5+5+0] -- two overlapping pairs.
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )

    result = find_legal_moves(state)

    expected = {
        Move(row_start=0, col_start=0, row_end=0, col_end=2),
        Move(row_start=0, col_start=0, row_end=1, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=2),
    }
    assert set(result) == expected


def test_overlapping_candidate_rectangles_are_both_found():
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )

    result = set(find_legal_moves(state))

    # (0,0,0,2) and (0,0,1,1) both contain (0,0) and (0,1).
    assert Move(row_start=0, col_start=0, row_end=0, col_end=2) in result
    assert Move(row_start=0, col_start=0, row_end=1, col_end=1) in result
    # (2,0,2,1) and (2,0,2,2) both contain (2,0) and (2,1).
    assert Move(row_start=2, col_start=0, row_end=2, col_end=1) in result
    assert Move(row_start=2, col_start=0, row_end=2, col_end=2) in result


def test_rectangle_spanning_empty_cells_is_found():
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )

    result = find_legal_moves(state)

    # (2,0,2,2) sums to 10 only because the cleared cell (2,2) contributes 0.
    assert Move(row_start=2, col_start=0, row_end=2, col_end=2) in result


# --- Zero legal moves ---------------------------------------------------------


def test_stuck_board_returns_no_moves():
    # Every rectangle sums to 9, 18, or 36 -- never 10.
    state = BoardState(grid=[[9, 0], [0, 9]], rows=2, cols=2)

    assert find_legal_moves(state) == []


def test_fully_cleared_board_returns_no_moves():
    state = BoardState(grid=[[0, 0], [0, 0]], rows=2, cols=2)

    assert find_legal_moves(state) == []


# --- Ordering contract --------------------------------------------------------


def test_results_are_sorted_by_move_coordinates():
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )

    result = find_legal_moves(state)

    expected_order = [
        Move(row_start=0, col_start=0, row_end=0, col_end=2),
        Move(row_start=0, col_start=0, row_end=1, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=2),
    ]
    assert result == expected_order


# --- Non-mutation --------------------------------------------------------------


def test_enumeration_does_not_mutate_the_board():
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    find_legal_moves(state)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


# --- Bottom-edge pruning boundary ----------------------------------------------


def test_move_whose_column_sums_to_exactly_target_is_found():
    # Regression test for the bottom-edge (row_end) prune: the running
    # column-0 sum hits exactly TARGET_SUM at row_end=1 (5+5=10). A
    # ">="-instead-of-">" bug would break the row_end loop right there and
    # silently drop this legal move instead of recording it.
    state = BoardState(
        grid=[
            [5, 9],
            [5, 9],
            [1, 9],
        ],
        rows=3,
        cols=2,
    )

    result = set(find_legal_moves(state))

    expected = {
        Move(row_start=0, col_start=0, row_end=1, col_end=0),
        Move(row_start=2, col_start=0, row_end=2, col_end=1),
    }
    assert result == expected
