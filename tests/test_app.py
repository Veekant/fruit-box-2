"""Tests for drag state tracking and move application on release (SPEC.md FR10).

Covers ``apply_selection`` (the FR10 rule: apply a legal candidate, discard
an illegal one with no state change) and ``Drag`` (the UI's only stateful
piece so far -- anchor pixel, current pixel, and the candidate rectangle
between them).

``apply_selection`` returns nothing (SPEC.md/plan-discussion decision): a
caller cannot read back whether a move landed, only observe it via engine
state. Every test below therefore asserts on ``engine.board.grid``,
``engine.score``, and ``engine.board.apples_remaining`` directly, never on a
return value.

All headless -- no display, no event loop. ``fruitbox.ui.app`` imports no
pygame at this stage (only ``fruitbox.config``, ``fruitbox.engine``, and
``fruitbox.ui.input``), so this file needs no ``pytest.importorskip``.
"""

import random

import pytest

from fruitbox.config import CELL_SIZE_PX, GRID_ORIGIN_X_PX, GRID_ORIGIN_Y_PX, HUD_HEIGHT_PX
from fruitbox.engine.board import BoardState
from fruitbox.engine.game import GameEngine
from fruitbox.engine.moves import Move
from fruitbox.solver.move_scanner import find_legal_moves
from fruitbox.ui.app import Drag, apply_selection


def _cell_pixel_center(row: int, col: int) -> tuple[int, int]:
    return (
        GRID_ORIGIN_X_PX + col * CELL_SIZE_PX + CELL_SIZE_PX // 2,
        GRID_ORIGIN_Y_PX + row * CELL_SIZE_PX + CELL_SIZE_PX // 2,
    )


def _snapshot(engine: GameEngine):
    """(grid deep copy, score, apples_remaining) for byte-for-byte no-op assertions."""
    return ([row[:] for row in engine.board.grid], engine.score, engine.board.apples_remaining)


# --- apply_selection: core FR10 behaviour ---------------------------------------


def test_apply_selection_legal_move_clears_scores_and_decrements():
    engine = GameEngine.load([[4, 6], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # 4+6=10, 2 apples

    apply_selection(engine, move)

    assert engine.board.grid == [[0, 0], [1, 1]]  # row 1 untouched
    assert engine.score == 2
    assert engine.board.apples_remaining == 2


def test_apply_selection_spanning_an_empty_cell_scores_only_real_apples():
    engine = GameEngine.load([[4, 0, 6], [1, 1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=2)  # 4+0+6=10, 2 apples

    apply_selection(engine, move)

    assert engine.board.grid[0] == [0, 0, 0]
    assert engine.score == 2  # not 3: the middle cell was already empty
    assert engine.board.apples_remaining == 3  # 5 - 2


def test_apply_selection_below_target_changes_nothing():
    engine = GameEngine.load([[4, 5], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # sum 9
    before = _snapshot(engine)

    apply_selection(engine, move)

    assert _snapshot(engine) == before


def test_apply_selection_above_target_changes_nothing():
    engine = GameEngine.load([[9, 9], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=1)  # sum 18
    before = _snapshot(engine)

    apply_selection(engine, move)

    assert _snapshot(engine) == before


def test_apply_selection_out_of_bounds_changes_nothing_and_does_not_raise():
    engine = GameEngine.load([[4, 6], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=1, col_end=2)  # col_end == 2 >= cols
    before = _snapshot(engine)

    apply_selection(engine, move)  # must not raise IndexError

    assert _snapshot(engine) == before


@pytest.mark.parametrize("value", range(1, 10))
def test_apply_selection_single_cell_never_applies(value):
    engine = GameEngine.load([[value, 1], [1, 9]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=0)
    before = _snapshot(engine)

    apply_selection(engine, move)

    assert _snapshot(engine) == before


def test_apply_selection_none_changes_nothing():
    engine = GameEngine.load([[4, 6], [1, 1]])
    before = _snapshot(engine)

    apply_selection(engine, None)

    assert _snapshot(engine) == before


def test_apply_selection_same_move_twice_second_call_is_a_noop():
    engine = GameEngine.load([[4, 6], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=1)

    apply_selection(engine, move)
    assert engine.score == 2

    before = _snapshot(engine)
    apply_selection(engine, move)  # now sums to 0

    assert _snapshot(engine) == before


def test_apply_selection_on_a_terminal_board_does_not_raise_or_change_state():
    engine = GameEngine.load([[4, 6]])
    apply_selection(engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))
    assert engine.is_terminal()
    before = _snapshot(engine)

    apply_selection(engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))
    apply_selection(engine, Move(row_start=0, col_start=0, row_end=0, col_end=0))

    assert _snapshot(engine) == before


def test_apply_selection_clears_only_the_intended_rectangle():
    engine = GameEngine.load([[1, 2, 5], [3, 4, 5], [9, 9, 9]])
    move = Move(row_start=0, col_start=0, row_end=1, col_end=1)  # 1+2+3+4=10

    apply_selection(engine, move)

    assert engine.board.grid == [[0, 0, 5], [0, 0, 5], [9, 9, 9]]
    assert engine.score == 4
    assert engine.board.apples_remaining == 5  # 9 - 4


def test_apply_selection_result_visible_through_get_state():
    engine = GameEngine.load([[4, 6], [1, 1]])
    move = Move(row_start=0, col_start=0, row_end=0, col_end=1)

    apply_selection(engine, move)

    state = engine.get_state()
    assert state.score == 2
    assert state.board.apples_remaining == 2


def test_apply_selection_does_not_mutate_the_move_object():
    engine = GameEngine.load([[4, 6], [1, 1]])
    legal = Move(row_start=0, col_start=0, row_end=0, col_end=1)
    legal_copy = Move(row_start=0, col_start=0, row_end=0, col_end=1)
    illegal = Move(row_start=1, col_start=0, row_end=1, col_end=0)
    illegal_copy = Move(row_start=1, col_start=0, row_end=1, col_end=0)

    apply_selection(engine, illegal)
    assert illegal == illegal_copy

    apply_selection(engine, legal)
    assert legal == legal_copy


# --- Drag: state machine ----------------------------------------------------------


def test_fresh_drag_is_idle():
    drag = Drag()

    assert drag.is_dragging is False
    assert drag.selection is None


def test_begin_yields_a_one_by_one_selection():
    drag = Drag()

    drag.begin(_cell_pixel_center(0, 0))

    assert drag.is_dragging is True
    assert drag.selection == Move(row_start=0, col_start=0, row_end=0, col_end=0)


def test_update_grows_the_selection():
    drag = Drag()

    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(1, 2))

    assert drag.selection == Move(row_start=0, col_start=0, row_end=1, col_end=2)


def test_backwards_drag_normalizes():
    drag = Drag()

    drag.begin(_cell_pixel_center(2, 3))
    drag.update(_cell_pixel_center(0, 1))

    assert drag.selection == Move(row_start=0, col_start=1, row_end=2, col_end=3)


def test_update_before_begin_is_a_noop():
    drag = Drag()

    drag.update(_cell_pixel_center(1, 1))

    assert drag.is_dragging is False
    assert drag.selection is None


def test_release_returns_the_candidate_and_ends_the_drag():
    drag = Drag()
    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(1, 1))
    expected = drag.selection

    result = drag.release(_cell_pixel_center(1, 1))

    assert result == expected
    assert drag.is_dragging is False
    assert drag.selection is None


def test_release_returns_illegal_candidates_too():
    drag = Drag()

    drag.begin(_cell_pixel_center(0, 0))
    one_by_one = drag.release(_cell_pixel_center(0, 0))

    assert one_by_one == Move(row_start=0, col_start=0, row_end=0, col_end=0)


def test_release_without_a_prior_begin_returns_none():
    drag = Drag()

    assert drag.release(_cell_pixel_center(0, 0)) is None
    assert drag.is_dragging is False


def test_release_implies_a_final_update():
    drag = Drag()
    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(0, 0))  # stale position

    result = drag.release(_cell_pixel_center(2, 2))  # release moves further

    assert result == Move(row_start=0, col_start=0, row_end=2, col_end=2)


def test_cancel_discards_the_drag():
    drag = Drag()
    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(1, 1))

    drag.cancel()

    assert drag.is_dragging is False
    assert drag.selection is None
    assert drag.release(_cell_pixel_center(1, 1)) is None


def test_cancel_on_an_idle_drag_is_a_noop():
    drag = Drag()

    drag.cancel()  # must not raise

    assert drag.is_dragging is False


def test_off_grid_drag_yields_none_selection_but_is_still_dragging():
    drag = Drag()
    hud_pixel = (GRID_ORIGIN_X_PX, HUD_HEIGHT_PX // 2)

    drag.begin(hud_pixel)
    drag.update(hud_pixel)

    assert drag.is_dragging is True
    assert drag.selection is None


def test_non_default_rows_and_cols_are_honoured():
    drag = Drag(rows=2, cols=2)

    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(5, 5))

    assert drag.selection == Move(row_start=0, col_start=0, row_end=1, col_end=1)


def test_begin_while_already_dragging_reanchors():
    drag = Drag()
    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(3, 3))

    drag.begin(_cell_pixel_center(1, 1))

    assert drag.selection == Move(row_start=1, col_start=1, row_end=1, col_end=1)


# --- End-to-end --------------------------------------------------------------------


def test_drag_release_apply_legal_path():
    engine = GameEngine.load([[4, 6], [1, 1]])
    drag = Drag(rows=2, cols=2)

    drag.begin(_cell_pixel_center(0, 0))
    drag.update(_cell_pixel_center(0, 1))
    move = drag.release(_cell_pixel_center(0, 1))
    apply_selection(engine, move)

    assert engine.board.grid == [[0, 0], [1, 1]]
    assert engine.score == 2
    assert engine.board.apples_remaining == 2
    assert drag.is_dragging is False


def test_drag_release_apply_illegal_path():
    engine = GameEngine.load([[4, 6], [1, 1]])
    drag = Drag(rows=2, cols=2)
    before = _snapshot(engine)

    drag.begin(_cell_pixel_center(1, 0))
    drag.update(_cell_pixel_center(1, 1))  # 1+1=2, illegal
    move = drag.release(_cell_pixel_center(1, 1))
    apply_selection(engine, move)

    assert _snapshot(engine) == before
    assert drag.is_dragging is False


@pytest.mark.parametrize("seed", range(20))
def test_apply_selection_deltas_agree_with_is_legal_and_count_apples_on_random_boards(seed):
    engine = GameEngine(BoardState.generate_board(seed=seed))
    rng = random.Random(seed)
    total_expected = 0
    initial_apples = engine.board.apples_remaining

    for _ in range(200):
        candidate_kind = rng.random()
        if candidate_kind < 0.4:
            legal_moves = find_legal_moves(engine.board)
            move = rng.choice(legal_moves) if legal_moves else None
        elif candidate_kind < 0.7:
            r0, r1 = sorted(rng.randint(0, engine.board.rows - 1) for _ in range(2))
            c0, c1 = sorted(rng.randint(0, engine.board.cols - 1) for _ in range(2))
            move = Move(row_start=r0, col_start=c0, row_end=r1, col_end=c1)
        elif candidate_kind < 0.9:
            move = Move(
                row_start=engine.board.rows,
                col_start=engine.board.cols,
                row_end=engine.board.rows + 2,
                col_end=engine.board.cols + 2,
            )
        else:
            move = None

        legal = move is not None and engine.board.is_legal(move)
        expected = engine.board.count_apples(move) if legal else 0

        before_apples = engine.board.apples_remaining
        before_score = engine.score
        grid_before = [row[:] for row in engine.board.grid] if not legal else None

        apply_selection(engine, move)

        assert before_apples - engine.board.apples_remaining == expected
        assert engine.score - before_score == expected
        if expected == 0:
            assert engine.board.grid == grid_before

        total_expected += expected

    assert total_expected == initial_apples - engine.board.apples_remaining
    assert total_expected == engine.score
