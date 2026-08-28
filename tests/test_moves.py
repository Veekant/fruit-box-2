"""Tests for move representation and legality checking (issue #3).

Covers SPEC.md FR2 (bounds + sum legality), section 8 (the ``Move`` dataclass and
its ``cells()`` iterator), and the section 2 rules that empty cells count as zero
and that a 1x1 rectangle is a valid *shape* but never a legal *move*. All
headless -- no display, no pygame.
"""

import dataclasses

import pytest

from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move, is_legal_move


def _board() -> BoardState:
    """A 4x4 hand-authored board with known legal and illegal rectangles.

    Laid out so that every legality case below has a witness:

    - ``rows 0-1, cols 0-1`` (2x2)      -> 1+2+4+3 = 10, legal
    - ``row 2, cols 0-3`` (1x4)         -> 0+0+9+1 = 10, legal across empties
    - ``col 0, rows 1-3`` (3x1)         -> 4+0+6   = 10, legal across an empty
    - ``row 0, cols 0-1``               -> 1+2     =  3, too low
    - ``row 0, cols 0-3``               -> 1+2+3+5 = 11, too high
    - ``row 2, cols 0-1``               -> 0+0     =  0, all-empty
    """
    return BoardState(
        grid=[
            [1, 2, 3, 5],
            [4, 3, 2, 1],
            [0, 0, 9, 1],
            [6, 8, 0, 5],
        ],
        rows=4,
        cols=4,
    )


# --- Move.cells() ----------------------------------------------------------


def test_single_cell_move_yields_exactly_one_coordinate():
    move = Move(row_start=1, col_start=1, row_end=1, col_end=1)

    assert list(move.cells()) == [(1, 1)]


def test_multi_row_multi_col_move_yields_all_cells_in_row_major_order():
    move = Move(row_start=1, col_start=1, row_end=2, col_end=3)

    assert list(move.cells()) == [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (2, 2),
        (2, 3),
    ]


def test_single_row_move_yields_horizontal_line():
    move = Move(row_start=0, col_start=0, row_end=0, col_end=3)

    assert list(move.cells()) == [(0, 0), (0, 1), (0, 2), (0, 3)]


def test_single_column_move_yields_vertical_line():
    move = Move(row_start=0, col_start=2, row_end=3, col_end=2)

    assert list(move.cells()) == [(0, 2), (1, 2), (2, 2), (3, 2)]


def test_cells_returns_a_fresh_iterator_each_call():
    move = Move(row_start=0, col_start=0, row_end=1, col_end=1)

    assert list(move.cells()) == list(move.cells())


# --- Move construction: rejected inputs ------------------------------------


def test_inverted_rows_are_rejected():
    with pytest.raises(ValueError):
        Move(row_start=2, col_start=0, row_end=0, col_end=1)


def test_inverted_cols_are_rejected():
    with pytest.raises(ValueError):
        Move(row_start=0, col_start=3, row_end=1, col_end=1)


def test_doubly_inverted_rectangle_is_rejected():
    with pytest.raises(ValueError):
        Move(row_start=2, col_start=3, row_end=0, col_end=1)


@pytest.mark.parametrize(
    "row_start,col_start,row_end,col_end",
    [
        (-1, 0, 1, 1),  # negative row_start
        (0, -1, 1, 1),  # negative col_start
        (-1, -1, 1, 1),  # both negative
        (-2, 0, -1, 1),  # ordered, but entirely off the top of the grid
    ],
)
def test_negative_coordinates_are_rejected(row_start, col_start, row_end, col_end):
    with pytest.raises(ValueError):
        Move(
            row_start=row_start,
            col_start=col_start,
            row_end=row_end,
            col_end=col_end,
        )


# --- Move: frozen dataclass semantics --------------------------------------


def test_move_is_immutable():
    move = Move(row_start=0, col_start=0, row_end=1, col_end=1)

    with pytest.raises(dataclasses.FrozenInstanceError):
        move.row_start = 5  # type: ignore[misc]


def test_moves_compare_and_hash_by_value():
    a = Move(row_start=0, col_start=0, row_end=1, col_end=1)
    b = Move(row_start=0, col_start=0, row_end=1, col_end=1)
    c = Move(row_start=0, col_start=0, row_end=1, col_end=2)

    assert a == b
    assert a != c
    assert len({a, b, c}) == 2


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
