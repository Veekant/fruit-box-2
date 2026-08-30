"""Tests for board state, legality, move application, and seeded generation.

Covers SPEC.md FR1 (generation with a guaranteed multiple-of-10 total), FR2
(``is_legal``: bounds and sum, with empty cells contributing 0), FR3
(``apply_move`` clears a legal rectangle and reports the apples it really
removed), section 8 (``BoardState`` and its ``copy()`` deep-copy contract), and
NFR5 (seed reproducibility). All headless -- no display, no pygame.

The FR2 legality tests live here, alongside the ``apply_move`` tests that depend
on them, because ``BoardState.is_legal`` is where the rule actually lives:
``game.py`` holds no legality code of its own and merely delegates to the board.
"""

import pytest

from fruitbox.config import (
    GRID_COLS,
    GRID_ROWS,
    MAX_CELL_VALUE,
    MIN_CELL_VALUE,
    TARGET_SUM,
)
from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move

# A 4x4 hand-authored layout carrying a witness for every legality and
# apply_move case below:
#
#   - rows 0-1, cols 0-1 (2x2)  -> 1+2+4+3 = 10, legal, 4 apples removed
#   - row 2, cols 0-3 (1x4)     -> 0+0+9+1 = 10, legal across empties, 2 removed
#   - col 0, rows 1-3 (3x1)     -> 4+0+6   = 10, legal across an empty, 2 removed
#   - row 0, cols 0-1           -> 1+2     =  3, illegal (too low)
#   - row 0, cols 0-3           -> 1+2+3+5 = 11, illegal (too high)
#   - row 2, cols 0-1           -> 0+0     =  0, illegal (all-empty)
#
# It holds 3 empty cells -- (2,0), (2,1), (3,2) -- so 13 apples in total.
LAYOUT = [
    [1, 2, 3, 5],
    [4, 3, 2, 1],
    [0, 0, 9, 1],
    [6, 8, 0, 5],
]
LAYOUT_APPLES = 13

SQUARE = Move(row_start=0, col_start=0, row_end=1, col_end=1)
ROW_OVER_EMPTIES = Move(row_start=2, col_start=0, row_end=2, col_end=3)
COL_OVER_EMPTY = Move(row_start=1, col_start=0, row_end=3, col_end=0)
ILLEGAL = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # sums to 3


def _board() -> BoardState:
    """A fresh 4x4 ``BoardState`` on ``LAYOUT`` (never the shared list)."""
    return BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)


def _total(state: BoardState) -> int:
    return sum(sum(row) for row in state.grid)


# --- BoardState.apples_remaining -------------------------------------------


def test_apples_remaining_is_computed_from_the_grid_when_not_supplied():
    # LAYOUT holds 3 empty cells, so 13 of its 16 cells are apples.
    assert _board().apples_remaining == LAYOUT_APPLES


def test_apples_remaining_counts_every_cell_of_a_fully_occupied_board():
    state = BoardState(grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], rows=3, cols=3)

    assert state.apples_remaining == 9


def test_apples_remaining_is_zero_on_an_empty_grid():
    state = BoardState(grid=[[0, 0], [0, 0]], rows=2, cols=2)

    assert state.apples_remaining == 0


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
    assert clone.apples_remaining == original.apples_remaining == 9
    # The row lists must be distinct objects, not shared references.
    assert all(a is not b for a, b in zip(clone.grid, original.grid))


def test_copy_carries_over_the_current_apple_count_mid_game():
    # The count must ride along as-is rather than being rederived: a copy taken
    # after play starts describes the played board, not a fresh one.
    original = _board()
    original.apply_move(SQUARE)

    clone = original.copy()

    assert clone.apples_remaining == original.apples_remaining == LAYOUT_APPLES - 4
    # And the two counts move independently from there.
    clone.apply_move(ROW_OVER_EMPTIES)

    assert clone.apples_remaining == LAYOUT_APPLES - 6
    assert original.apples_remaining == LAYOUT_APPLES - 4


def test_copy_of_original_does_not_alias_after_mutating_original():
    original = BoardState(grid=[[1, 2, 3], [4, 5, 6], [7, 8, 9]], rows=3, cols=3)

    clone = original.copy()
    original.grid[0][0] = 0

    assert clone.grid[0][0] == 1


# --- BoardState.is_legal(): legal ------------------------------------------


def test_rectangle_summing_to_ten_is_legal():
    # rows 0-1, cols 0-1: 1 + 2 + 4 + 3 == 10
    assert _board().is_legal(SQUARE)


def test_rectangle_spanning_empty_cells_is_legal():
    # row 2: 0 + 0 + 9 + 1 == 10. The two empty cells contribute nothing and do
    # not disqualify the rectangle (SPEC.md section 2: no occupancy check).
    assert _board().is_legal(ROW_OVER_EMPTIES)


def test_vertical_rectangle_spanning_an_empty_cell_is_legal():
    # col 0, rows 1-3: 4 + 0 + 6 == 10
    assert _board().is_legal(COL_OVER_EMPTY)


def test_cells_cleared_by_a_move_behave_like_empties_for_later_moves():
    # The design invariant behind having no separate occupancy mask (SPEC.md
    # section 2, section 8): a cell zeroed by an earlier move is indistinguishable
    # from one authored empty. LAYOUT's empties are hand-authored, so this uses a
    # board where the empties are made by play.
    state = BoardState(grid=[[6, 4, 1], [2, 8, 9], [5, 5, 3]], rows=3, cols=3)
    state.apply_move(Move(row_start=0, col_start=0, row_end=0, col_end=1))  # 6+4

    # rows 0-1, cols 0-1 is now 0 + 0 + 2 + 8: legal only because the two cells
    # the first move cleared count as 0.
    spanning_cleared = Move(row_start=0, col_start=0, row_end=1, col_end=1)

    assert state.is_legal(spanning_cleared)
    # And it removes 2 apples, not the rectangle's 4 cells.
    assert state.apply_move(spanning_cleared) == 2
    assert state.grid == [[0, 0, 1], [0, 0, 9], [5, 5, 3]]
    assert state.apples_remaining == 5


def test_legality_check_does_not_mutate_the_board():
    state = _board()
    before = [row[:] for row in state.grid]

    state.is_legal(SQUARE)

    assert state.grid == before


# --- BoardState.is_legal(): illegal sums -----------------------------------


def test_sum_below_target_is_illegal():
    # row 0, cols 0-1: 1 + 2 == 3
    assert not _board().is_legal(ILLEGAL)


def test_sum_above_target_is_illegal():
    # row 0, cols 0-3: 1 + 2 + 3 + 5 == 11
    assert not _board().is_legal(Move(row_start=0, col_start=0, row_end=0, col_end=3))


def test_all_empty_rectangle_is_illegal():
    # row 2, cols 0-1: 0 + 0 == 0
    assert not _board().is_legal(Move(row_start=2, col_start=0, row_end=2, col_end=1))


def test_single_cell_move_is_never_legal():
    # SPEC.md section 2's explicit degenerate-shape case: a 1x1 rectangle holds
    # either 0 or 1-9, so it can never sum to 10. Falls out of the sum check --
    # there is no special-cased size rule in the code.
    state = _board()

    for row, col in [(0, 0), (2, 2), (3, 1), (2, 0)]:
        move = Move(row_start=row, col_start=col, row_end=row, col_end=col)

        assert not state.is_legal(move)


# --- BoardState.is_legal(): out of bounds ----------------------------------


def test_rectangle_extending_past_last_row_is_illegal():
    # row_end == 4 on a 4-row board.
    assert not _board().is_legal(Move(row_start=0, col_start=0, row_end=4, col_end=0))


def test_rectangle_extending_past_last_col_is_illegal():
    # col_end == 4 on a 4-column board.
    assert not _board().is_legal(Move(row_start=0, col_start=0, row_end=0, col_end=4))


def test_out_of_bounds_rectangle_returns_false_rather_than_raising():
    # The in-bounds part of this rectangle (row 2, cols 0-3) does sum to 10, so
    # this pins down that the bounds check runs first and short-circuits: the
    # result is False, not an IndexError and not True.
    state = _board()
    move = Move(row_start=2, col_start=0, row_end=2, col_end=9)

    assert not state.is_legal(move)


def test_rectangle_entirely_outside_the_board_is_illegal():
    assert not _board().is_legal(
        Move(row_start=10, col_start=10, row_end=11, col_end=11)
    )


def test_move_legal_on_a_larger_board_is_out_of_bounds_on_a_smaller_one():
    small = BoardState(grid=[[4, 6], [1, 2]], rows=2, cols=2)
    large = BoardState(grid=[[4, 6, 1], [1, 2, 3], [7, 8, 9]], rows=3, cols=3)
    # rows 0-2, col 0 on the 3x3: 4 + 1 + 7 == 12; rows 0-1 col 0 there is 5.
    spanning = Move(row_start=0, col_start=0, row_end=2, col_end=0)

    assert not small.is_legal(spanning)  # off the bottom of the 2x2
    assert not large.is_legal(spanning)  # in bounds, but sums to 12
    # Bounds are read from the state, not from module-level config.
    assert small.is_legal(Move(row_start=0, col_start=0, row_end=0, col_end=1))


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
    assert state.apples_remaining == LAYOUT_APPLES - 4


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
    # Decremented by the apples actually removed, not by the rectangle's area.
    assert state.apples_remaining == LAYOUT_APPLES - 2


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
    assert state.apples_remaining == LAYOUT_APPLES - 6


# --- BoardState.apply_move(): rejected moves -------------------------------


def test_apply_move_rejects_a_rectangle_that_does_not_sum_to_the_target():
    state = _board()

    with pytest.raises(ValueError):
        state.apply_move(ILLEGAL)  # 1 + 2 == 3

    assert state.grid == LAYOUT
    assert state.apples_remaining == LAYOUT_APPLES


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


# --- BoardState.count_apples() ----------------------------------------------


def test_count_apples_of_a_fully_occupied_rectangle_equals_its_area():
    assert _board().count_apples(SQUARE) == 4


def test_count_apples_counts_apples_not_area_across_a_row_of_empties():
    # row 2 is 0+0+9+1: a 4-cell rectangle holding only 2 apples.
    assert _board().count_apples(ROW_OVER_EMPTIES) == 2


def test_count_apples_counts_apples_not_area_across_a_column_of_empties():
    # col 0, rows 1-3: 4, 0, 6 -- a 3-cell rectangle holding only 2 apples.
    assert _board().count_apples(COL_OVER_EMPTY) == 2


def test_count_apples_of_an_all_empty_rectangle_is_zero():
    # row 2, cols 0-1: both cells are the hand-authored empties.
    assert _board().count_apples(Move(row_start=2, col_start=0, row_end=2, col_end=1)) == 0


def test_count_apples_of_a_single_occupied_cell_is_one():
    assert _board().count_apples(Move(row_start=0, col_start=0, row_end=0, col_end=0)) == 1


def test_count_apples_of_a_single_empty_cell_is_zero():
    assert _board().count_apples(Move(row_start=2, col_start=0, row_end=2, col_end=0)) == 0


def test_count_apples_of_the_whole_board_equals_apples_remaining():
    state = _board()

    whole_board = Move(row_start=0, col_start=0, row_end=3, col_end=3)

    assert state.count_apples(whole_board) == LAYOUT_APPLES == state.apples_remaining


def test_count_apples_does_not_check_legality():
    # ILLEGAL sums to 3, not TARGET_SUM -- count_apples doesn't care.
    assert not _board().is_legal(ILLEGAL)
    assert _board().count_apples(ILLEGAL) == 2  # cells hold 1 and 2, both occupied


def test_count_apples_agrees_with_apply_moves_return_value():
    for move in (SQUARE, ROW_OVER_EMPTIES, COL_OVER_EMPTY):
        counted = _board().count_apples(move)
        applied = _board().apply_move(move)

        assert counted == applied


def test_count_apples_reflects_cells_cleared_by_an_earlier_move():
    state = _board()
    state.apply_move(SQUARE)  # zeroes rows 0-1, cols 0-1

    # Re-counting the same rectangle now finds nothing left to clear.
    assert state.count_apples(SQUARE) == 0
    # A rectangle overlapping the cleared region counts only what survives:
    # rows 0-1, cols 0-2 was 1+2+3 + 4+3+2 = 15 originally (6 apples); after
    # SQUARE clears cols 0-1, only the col-2 apples (3, 2) remain.
    overlapping = Move(row_start=0, col_start=0, row_end=1, col_end=2)
    assert state.count_apples(overlapping) == 2


def test_count_apples_does_not_mutate_the_board():
    state = _board()
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    state.count_apples(ROW_OVER_EMPTIES)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


def test_count_apples_raises_on_a_rectangle_extending_past_the_board():
    state = _board()

    with pytest.raises(IndexError):
        state.count_apples(Move(row_start=2, col_start=0, row_end=2, col_end=9))


def test_count_apples_raises_on_a_rectangle_entirely_off_the_board():
    state = _board()

    with pytest.raises(IndexError):
        state.count_apples(Move(row_start=10, col_start=10, row_end=11, col_end=11))


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
def test_count_apples_matches_an_independent_reference_on_random_boards(seed):
    state = BoardState.generate_board(seed=seed)

    candidates = [
        Move(row_start=0, col_start=0, row_end=0, col_end=0),
        Move(row_start=0, col_start=0, row_end=2, col_end=2),
        Move(row_start=3, col_start=4, row_end=5, col_end=9),
        Move(row_start=0, col_start=0, row_end=state.rows - 1, col_end=state.cols - 1),
    ]

    for move in candidates:
        reference = sum(
            1 for row, col in move.cells() if state.grid[row][col] != 0
        )
        assert state.count_apples(move) == reference

    # Clear a couple of cells directly (no need for a legal move here -- this
    # is only checking that count_apples keeps tracking the grid correctly
    # once some cells go empty) and re-check the same reference agrees.
    state.grid[0][0] = 0
    state.grid[1][0] = 0

    for move in candidates:
        reference = sum(
            1 for row, col in move.cells() if state.grid[row][col] != 0
        )
        assert state.count_apples(move) == reference


# --- BoardState.move_sum() ---------------------------------------------------


def test_move_sum_of_a_fully_occupied_rectangle():
    assert _board().move_sum(SQUARE) == 10


def test_move_sum_counts_empty_cells_as_zero():
    # row 2 is 0+0+9+1; col 0 rows 1-3 is 4+0+6 -- both sum to 10 with an
    # empty cell contributing nothing.
    assert _board().move_sum(ROW_OVER_EMPTIES) == 10
    assert _board().move_sum(COL_OVER_EMPTY) == 10


def test_move_sum_below_target():
    assert _board().move_sum(ILLEGAL) == 3


def test_move_sum_above_target():
    over = Move(row_start=0, col_start=0, row_end=0, col_end=3)
    assert _board().move_sum(over) == 11


def test_move_sum_of_an_all_empty_rectangle_is_zero():
    all_empty = Move(row_start=2, col_start=0, row_end=2, col_end=1)
    assert _board().move_sum(all_empty) == 0


def test_move_sum_of_a_single_cell_is_its_value():
    occupied = Move(row_start=0, col_start=0, row_end=0, col_end=0)
    empty = Move(row_start=2, col_start=0, row_end=2, col_end=0)

    assert _board().move_sum(occupied) == 1
    assert _board().move_sum(empty) == 0


def test_move_sum_of_the_whole_board_equals_the_grid_total():
    state = _board()
    whole_board = Move(row_start=0, col_start=0, row_end=3, col_end=3)

    assert state.move_sum(whole_board) == _total(state)


def test_move_sum_makes_no_legality_claim():
    # ILLEGAL doesn't sum to TARGET_SUM -- move_sum reports the value anyway,
    # without raising or otherwise reacting to the mismatch.
    assert _board().move_sum(ILLEGAL) == 3
    assert not _board().is_legal(ILLEGAL)


def test_move_sum_does_not_mutate_the_board():
    state = _board()
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    state.move_sum(ROW_OVER_EMPTIES)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


def test_move_sum_reflects_cells_cleared_by_an_earlier_move():
    state = _board()
    state.apply_move(SQUARE)  # zeroes rows 0-1, cols 0-1

    assert state.move_sum(SQUARE) == 0

    # rows 0-1, cols 0-2 was 1+2+3 + 4+3+2 = 15 originally; after SQUARE
    # clears cols 0-1, only the col-2 apples (3, 2) remain.
    overlapping = Move(row_start=0, col_start=0, row_end=1, col_end=2)
    assert state.move_sum(overlapping) == 5


def test_move_sum_raises_on_a_rectangle_extending_past_the_board():
    state = _board()

    with pytest.raises(IndexError):
        state.move_sum(Move(row_start=2, col_start=0, row_end=2, col_end=9))


def test_move_sum_raises_on_a_rectangle_entirely_off_the_board():
    state = _board()

    with pytest.raises(IndexError):
        state.move_sum(Move(row_start=10, col_start=10, row_end=11, col_end=11))


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
def test_move_sum_matches_an_independent_reference_on_random_boards(seed):
    state = BoardState.generate_board(seed=seed)

    candidates = [
        Move(row_start=0, col_start=0, row_end=0, col_end=0),
        Move(row_start=0, col_start=0, row_end=2, col_end=2),
        Move(row_start=3, col_start=4, row_end=5, col_end=9),
        Move(row_start=0, col_start=0, row_end=state.rows - 1, col_end=state.cols - 1),
    ]

    for move in candidates:
        reference = sum(state.grid[row][col] for row, col in move.cells())
        assert state.move_sum(move) == reference


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
def test_is_legal_agrees_with_move_sum_against_the_target(seed):
    # Regression guard for the is_legal -> move_sum delegation: two
    # independent-looking calls must never disagree on a random board.
    state = BoardState.generate_board(seed=seed)

    candidates = [
        Move(row_start=0, col_start=0, row_end=0, col_end=0),
        Move(row_start=0, col_start=0, row_end=2, col_end=2),
        Move(row_start=1, col_start=1, row_end=4, col_end=6),
        Move(row_start=3, col_start=4, row_end=5, col_end=9),
        Move(row_start=0, col_start=0, row_end=state.rows - 1, col_end=state.cols - 1),
    ]

    for move in candidates:
        assert state.is_legal(move) == (state.move_sum(move) == TARGET_SUM)


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
    first = BoardState.generate_board(seed=42)
    second = BoardState.generate_board(seed=42)

    assert first.grid == second.grid


def test_different_seeds_produce_different_boards():
    # Not a strict mathematical guarantee, but with 170 cells a collision is
    # astronomically unlikely.
    a = BoardState.generate_board(seed=1)
    b = BoardState.generate_board(seed=2)
    c = BoardState.generate_board(seed=3)

    assert a.grid != b.grid
    assert b.grid != c.grid
    assert a.grid != c.grid


def test_generation_does_not_disturb_global_random_state():
    import random

    random.seed(12345)
    expected = [random.random() for _ in range(3)]

    random.seed(12345)
    BoardState.generate_board(seed=7)
    BoardState.generate_board()
    actual = [random.random() for _ in range(3)]

    assert actual == expected


# --- generate_board: FR1 sum invariant -------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234, 20260828])
def test_total_sum_is_multiple_of_ten_default_grid(seed):
    state = BoardState.generate_board(seed=seed)

    assert _total(state) % TARGET_SUM == 0


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234, 20260828])
def test_total_sum_is_multiple_of_ten_small_grid(seed):
    state = BoardState.generate_board(rows=3, cols=3, seed=seed)

    assert _total(state) % TARGET_SUM == 0


@pytest.mark.parametrize("rows,cols", [(1, 2), (2, 2), (3, 3), (4, 7), (10, 17)])
def test_total_sum_is_multiple_of_ten_across_shapes(rows, cols):
    state = BoardState.generate_board(rows=rows, cols=cols, seed=2024)

    assert _total(state) % TARGET_SUM == 0


# --- generate_board: value range and dimensions ----------------------------


@pytest.mark.parametrize("seed", [0, 5, 42, 777])
def test_all_cells_within_value_range(seed):
    state = BoardState.generate_board(seed=seed)

    for row in state.grid:
        for value in row:
            # A freshly generated board has no empty cells, so 0 is excluded.
            assert MIN_CELL_VALUE <= value <= MAX_CELL_VALUE


@pytest.mark.parametrize("rows,cols", [(1, 2), (3, 3), (10, 17)])
def test_dimensions_match_requested_shape(rows, cols):
    state = BoardState.generate_board(rows=rows, cols=cols, seed=11)

    assert state.rows == rows
    assert state.cols == cols
    assert len(state.grid) == rows
    assert all(len(row) == cols for row in state.grid)


def test_defaults_come_from_config():
    state = BoardState.generate_board(seed=3)

    assert state.rows == GRID_ROWS
    assert state.cols == GRID_COLS
    assert len(state.grid) == GRID_ROWS
    assert all(len(row) == GRID_COLS for row in state.grid)


# --- generate_board: minimum-size edge case --------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_minimum_board_of_two_cells(seed):
    """rows*cols - 2 == 0: the whole board is just the two adjusted cells."""
    state = BoardState.generate_board(rows=1, cols=2, seed=seed)

    assert state.rows == 1
    assert state.cols == 2
    assert len(state.grid) == 1
    assert len(state.grid[0]) == 2
    assert all(MIN_CELL_VALUE <= v <= MAX_CELL_VALUE for v in state.grid[0])
    assert _total(state) % TARGET_SUM == 0


# --- generate_board: unseeded -----------------------------------------------


def test_unseeded_generation_still_satisfies_invariants():
    for _ in range(5):
        state = BoardState.generate_board()

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
