"""Tests for legal-move enumeration (issues #6, #7).

Covers SPEC.md section 10's must-haves: an exact hand-verified move set,
overlapping candidate rectangles, a rectangle spanning empty cells, zero
legal moves, the sorted-order contract, and the non-mutation guarantee
(issue #6) -- plus a brute-force cross-check against ``BoardState.is_legal``
across randomized and mid-game boards, analytic uniform-value fixtures at
full board scale, and additional boundary fixtures (issue #7). All headless
-- no display, no pygame.

NFR4 (full-board enumeration well under 1 second) is deliberately left
unmeasured here: a wall-clock assertion belongs to the benchmark script
(SPEC.md section 10), not this correctness suite.
"""

import random

import pytest

from fruitbox.config import GRID_COLS, GRID_ROWS, TARGET_SUM
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


# --- Test helpers (issue #7) ---------------------------------------------------


def _brute_force_legal_moves(state: BoardState) -> list[Move]:
    """Independent reference enumerator: every in-bounds rectangle, kept iff
    ``state.is_legal`` (naive per-cell summation) says so.

    Deliberately does not use the prefix-sum machinery under test, so
    agreement with :func:`find_legal_moves` is a genuine cross-check between
    two independent code paths (SPEC.md section 10). Naturally emits moves in
    the same ``(row_start, col_start, row_end, col_end)`` order
    ``find_legal_moves`` promises, since it iterates in that order too.
    """
    moves = []
    for row_start in range(state.rows):
        for col_start in range(state.cols):
            for row_end in range(row_start, state.rows):
                for col_end in range(col_start, state.cols):
                    move = Move(
                        row_start=row_start,
                        col_start=col_start,
                        row_end=row_end,
                        col_end=col_end,
                    )
                    if state.is_legal(move):
                        moves.append(move)
    return moves


def _uniform_board(value: int, rows: int, cols: int) -> BoardState:
    """A ``rows`` x ``cols`` board where every cell holds ``value``."""
    return BoardState(grid=[[value] * cols for _ in range(rows)], rows=rows, cols=cols)


def _expected_uniform_moves(value: int, rows: int, cols: int) -> set[Move]:
    """Closed-form legal-move set for a uniform-value board.

    On a board of all ``value``, an ``h x w`` rectangle sums to
    ``value * h * w``, so it is legal iff ``value`` divides ``TARGET_SUM`` and
    ``h * w == TARGET_SUM // value``. Every ``(h, w)`` factor pair of that
    area is placed at every position it fits.
    """
    if TARGET_SUM % value != 0:
        return set()

    area = TARGET_SUM // value
    expected = set()
    for h in range(1, min(rows, area) + 1):
        if area % h != 0:
            continue
        w = area // h
        if w > cols:
            continue
        for row_start in range(rows - h + 1):
            for col_start in range(cols - w + 1):
                expected.add(
                    Move(
                        row_start=row_start,
                        col_start=col_start,
                        row_end=row_start + h - 1,
                        col_end=col_start + w - 1,
                    )
                )
    return expected


def _sorted_key(move: Move) -> tuple[int, int, int, int]:
    return (move.row_start, move.col_start, move.row_end, move.col_end)


def _random_playout_states(state: BoardState, rng: random.Random):
    """Mutate ``state`` in place through a random legal playout, yielding it
    after each applied move, until no legal moves remain.

    Move selection is driven by :func:`_brute_force_legal_moves`, not the
    code under test, so the resulting sequence of mid-game boards is
    independent of any bug that ``find_legal_moves`` might have. Caller owns
    ``state`` -- pass a board it is fine to mutate.
    """
    while True:
        legal = _brute_force_legal_moves(state)
        if not legal:
            return
        move = rng.choice(legal)
        state.apply_move(move)
        yield state


def test_brute_force_reference_matches_hand_authored_expectation():
    # Anchors the reference enumerator itself against the known-good 3x3
    # fixture from test_returns_exact_expected_move_set above.
    state = BoardState(
        grid=[
            [1, 2, 7],
            [3, 4, 0],
            [5, 5, 0],
        ],
        rows=3,
        cols=3,
    )

    expected = {
        Move(row_start=0, col_start=0, row_end=0, col_end=2),
        Move(row_start=0, col_start=0, row_end=1, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=1),
        Move(row_start=2, col_start=0, row_end=2, col_end=2),
    }
    assert set(_brute_force_legal_moves(state)) == expected


# --- Cross-check: fresh boards ---------------------------------------------------


@pytest.mark.parametrize("rows,cols", [(3, 3), (4, 4), (5, 6), (6, 6)])
@pytest.mark.parametrize("seed", range(10))
def test_matches_brute_force_on_random_small_boards(seed, rows, cols):
    state = BoardState.generate_board(rows=rows, cols=cols, seed=seed)

    assert set(find_legal_moves(state)) == set(_brute_force_legal_moves(state))


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
def test_matches_brute_force_on_full_size_boards(seed):
    state = BoardState.generate_board(seed=seed)

    assert set(find_legal_moves(state)) == set(_brute_force_legal_moves(state))


# --- Cross-check: mid-game and terminal boards ------------------------------------


@pytest.mark.parametrize("seed", range(8))
def test_matches_brute_force_along_random_playout(seed):
    # Checks agreement at every state of a random playout, from the fresh
    # board through to the terminal (stuck) board it eventually reaches --
    # exercising the "rectangle spans empty cells" path at increasing scale
    # as the board empties out.
    state = BoardState.generate_board(rows=6, cols=6, seed=seed)
    rng = random.Random(seed)

    assert set(find_legal_moves(state)) == set(_brute_force_legal_moves(state))
    for _ in _random_playout_states(state, rng):
        assert set(find_legal_moves(state)) == set(_brute_force_legal_moves(state))


@pytest.mark.parametrize("seed", [7, 2024])
def test_matches_brute_force_on_mid_game_full_size_board(seed):
    state = BoardState.generate_board(seed=seed)
    rng = random.Random(seed)

    playout = _random_playout_states(state, rng)
    for i, _ in enumerate(playout):
        assert set(find_legal_moves(state)) == set(_brute_force_legal_moves(state))
        if i == 4:
            break


# --- Ordering contract on random boards -------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_results_are_sorted_on_random_boards(seed):
    state = BoardState.generate_board(seed=seed)

    result = find_legal_moves(state)

    assert result == sorted(result, key=_sorted_key)


# --- Analytic uniform-value boards -------------------------------------------------


@pytest.mark.parametrize("value", [1, 2, 3, 5, 9])
@pytest.mark.parametrize("rows,cols", [(5, 5), (10, 17)])
def test_uniform_board_matches_analytic_expectation(rows, cols, value):
    state = _uniform_board(value, rows, cols)

    result = set(find_legal_moves(state))

    assert result == _expected_uniform_moves(value, rows, cols)


def test_all_ones_full_board_move_count():
    state = _uniform_board(1, GRID_ROWS, GRID_COLS)

    result = find_legal_moves(state)

    # Area-10 rectangle shapes on a 10x17 board of all 1s: legal iff
    # h * w == 10, i.e. (h, w) in {(1,10), (2,5), (5,2), (10,1)}, each placed
    # at every position it fits:
    #   1x10:  10 rows *  8 col positions (17-10+1) =  80
    #   2x5:    9 rows * 13 col positions (17-5+1)  = 117
    #   5x2:    6 rows * 16 col positions (17-2+1)  =  96
    #   10x1:   1 row  * 17 col positions           =  17
    # Total = 80 + 117 + 96 + 17 = 310
    assert len(result) == 310


def test_all_nines_board_returns_no_moves():
    # TARGET_SUM (10) is not a multiple of 9, so no rectangle of any shape
    # can sum to it -- this is also the "richer stuck board" fixture.
    state = _uniform_board(9, GRID_ROWS, GRID_COLS)

    assert find_legal_moves(state) == []


# --- Boundary / degenerate geometry -------------------------------------------------


@pytest.mark.parametrize("value", range(1, 10))
def test_single_cell_board_never_yields_a_move(value):
    state = BoardState(grid=[[value]], rows=1, cols=1)

    assert find_legal_moves(state) == []


def test_single_row_board_finds_all_contiguous_segments():
    # Sums (verified by hand): [4,6]=10 (cols 0-1), [3,7]=10 (cols 2-3),
    # [7,1,2]=10 (cols 3-5). No other contiguous run sums to 10.
    state = BoardState(grid=[[4, 6, 3, 7, 1, 2]], rows=1, cols=6)

    result = set(find_legal_moves(state))

    expected = {
        Move(row_start=0, col_start=0, row_end=0, col_end=1),
        Move(row_start=0, col_start=2, row_end=0, col_end=3),
        Move(row_start=0, col_start=3, row_end=0, col_end=5),
    }
    assert result == expected


def test_single_column_board_finds_all_contiguous_segments():
    # Transpose of the single-row fixture above -- same sums, rows instead of
    # cols, guarding against a row/col loop mix-up that a square fixture
    # couldn't reveal.
    state = BoardState(grid=[[4], [6], [3], [7], [1], [2]], rows=6, cols=1)

    result = set(find_legal_moves(state))

    expected = {
        Move(row_start=0, col_start=0, row_end=1, col_end=0),
        Move(row_start=2, col_start=0, row_end=3, col_end=0),
        Move(row_start=3, col_start=0, row_end=5, col_end=0),
    }
    assert result == expected


def test_move_anchored_at_bottom_right_corner_is_found():
    # Verified by hand: the only rectangle summing to 10 is rows 1-2 x
    # cols 1-2 (1+2+3+4=10), anchored at the grid's bottom-right corner.
    # Every other rectangle over- or under-shoots (checked exhaustively:
    # single cells top out at 8, and every other pair/triple/full-span sum
    # lands somewhere in {3,4,6,7,9,11,12,13,15,16,18,20,23,24,25,34,36,49}).
    state = BoardState(
        grid=[
            [8, 8, 7],
            [8, 1, 2],
            [8, 3, 4],
        ],
        rows=3,
        cols=3,
    )

    result = find_legal_moves(state)

    assert result == [Move(row_start=1, col_start=1, row_end=2, col_end=2)]


def test_legal_move_spanning_a_large_empty_region():
    # A full-size board that is all zeros except two nonzero cells at the
    # far left and far right of row 0, summing to exactly 10 together.
    grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    grid[0][0] = 4
    grid[0][GRID_COLS - 1] = 6
    state = BoardState(grid=grid, rows=GRID_ROWS, cols=GRID_COLS)

    result = set(find_legal_moves(state))

    # Every legal rectangle must span the full column range to capture both
    # nonzero cells, and must start at row 0 to include them -- but its
    # row_end may extend anywhere down to the last row, since every cell in
    # between is 0.
    expected = {
        Move(row_start=0, col_start=0, row_end=row_end, col_end=GRID_COLS - 1)
        for row_end in range(GRID_ROWS)
    }
    assert result == expected
    assert len(expected) == GRID_ROWS


# --- Non-mutation on random boards -------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_enumeration_does_not_mutate_a_random_board(seed):
    state = BoardState.generate_board(seed=seed)
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    find_legal_moves(state)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before
