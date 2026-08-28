"""Tests for the ``Move`` rectangle representation (issue #3).

Covers SPEC.md section 8 (the ``Move`` dataclass and its ``cells()`` iterator)
and the section 2 rule that a 1x1 rectangle is a valid *shape*, whatever its
legality later turns out to be. All headless -- no display, no pygame.

``Move`` is purely geometric and knows nothing about any board, so legality
(FR2) is not tested here: those tests live in ``test_board.py``, alongside the
``BoardState.is_legal`` and ``BoardState.apply_move`` code that owns the rule.
"""

import dataclasses

import pytest

from fruitbox.engine.moves import Move

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


def test_rejection_messages_distinguish_the_three_failure_modes():
    # All three branches of __post_init__ raise the same exception type, so the
    # message is the only thing telling them apart -- worth pinning down.
    with pytest.raises(ValueError, match="inverted rectangle: row_start"):
        Move(row_start=2, col_start=0, row_end=0, col_end=1)

    with pytest.raises(ValueError, match="inverted rectangle: col_start"):
        Move(row_start=0, col_start=3, row_end=1, col_end=1)

    with pytest.raises(ValueError, match="negative coordinate"):
        Move(row_start=-1, col_start=0, row_end=1, col_end=1)


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
