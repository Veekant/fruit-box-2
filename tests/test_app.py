"""Tests for drag/timer/session state and move application (SPEC.md FR10-FR12).

Covers ``apply_selection`` (FR10: apply a legal candidate, discard an
illegal one with no state change), ``Drag`` (anchor pixel, current pixel,
and the candidate rectangle between them), ``Timer`` (FR11's countdown,
driven by externally supplied millisecond tick values -- no clock, no fake
clock, just plain integers), and ``Session`` (FR11/FR12: game-over,
reset, new game -- the object owning an engine + a timer together).

``apply_selection`` returns nothing (SPEC.md/plan-discussion decision): a
caller cannot read back whether a move landed, only observe it via engine
state. Every test below therefore asserts on ``engine.board.grid``,
``engine.score``, and ``engine.board.apples_remaining`` directly, never on a
return value.

All headless -- no display, no event loop. ``fruitbox.ui.app`` now also
contains the pygame main loop (``run``/``main``), so importing it requires
pygame -- hence ``pytest.importorskip("pygame")`` below. The classes tested
here (``Drag``, ``Timer``, ``Session``, ``apply_selection``) remain
pygame-free in their own interfaces (bare tuples, bare ints), and every test
in this file stays headless: no display, no event loop, and ``run``/``main``
are not exercised here at all (SPEC.md section 10 -- the loop itself is
manually/smoke-tested, see the PR's manual verification checklist).
"""

import inspect
import random

import pytest

pytest.importorskip("pygame")

from fruitbox.config import (
    CELL_SIZE_PX,
    GRID_ORIGIN_X_PX,
    GRID_ORIGIN_Y_PX,
    HUD_HEIGHT_PX,
    TARGET_SUM,
    TIMER_SECONDS,
)
from fruitbox.engine.board import BoardState
from fruitbox.engine.game import GameEngine
from fruitbox.engine.moves import Move
from fruitbox.solver.move_scanner import find_legal_moves
from fruitbox.ui.app import Drag, Session, Timer, apply_selection


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


# --- Timer -------------------------------------------------------------------------


def test_fresh_timer_is_at_zero_elapsed_and_full_remaining():
    t = Timer(0)

    assert t.duration == 0
    assert t.remaining == TIMER_SECONDS
    assert t.expired is False
    assert t.stopped is False


def test_end_time_defaults_to_config_timer_seconds():
    assert Timer(0).remaining == TIMER_SECONDS


def test_update_advances_elapsed_and_shrinks_remaining():
    t = Timer(0, end_time=100)

    t.update(30_000)

    assert t.duration == 30_000
    assert t.remaining == pytest.approx(70.0)


def test_duration_is_measured_from_start_ticks():
    t = Timer(5_000, end_time=100)

    t.update(8_000)

    assert t.duration == 3_000
    assert t.remaining == pytest.approx(97.0)


def test_successive_updates_are_absolute_not_cumulative():
    t = Timer(0)

    t.update(1_000)
    t.update(4_000)

    assert t.duration == 4_000


def test_remaining_goes_negative_past_end_time():
    t = Timer(0, end_time=100)

    t.update(105_000)

    assert t.remaining == pytest.approx(-5.0)


def test_duration_is_in_milliseconds_and_remaining_in_seconds():
    t = Timer(0, end_time=TIMER_SECONDS)

    t.update(1_000)

    assert t.duration == 1_000
    assert TIMER_SECONDS - t.remaining == pytest.approx(1.0)


def test_backwards_tick_yields_smaller_elapsed():
    t = Timer(0)

    t.update(5_000)
    t.update(2_000)

    assert t.duration == 2_000


def test_not_expired_just_before_end_time():
    t = Timer(0, end_time=100)

    t.update(99_999)

    assert t.expired is False


def test_not_expired_exactly_at_end_time():
    t = Timer(0, end_time=100)

    t.update(100_000)

    assert t.expired is False
    assert t.remaining == pytest.approx(0.0)


def test_expired_one_tick_past_end_time():
    t = Timer(0, end_time=100)

    t.update(100_001)

    assert t.expired is True


@pytest.mark.parametrize("ticks", [0, 1, 50_000, 99_999, 100_000, 100_001, 250_000])
def test_expired_agrees_with_remaining_sign(ticks):
    t = Timer(0, end_time=100)

    t.update(ticks)

    assert t.expired == (t.remaining < 0)


def test_custom_end_time_is_honoured():
    t = Timer(0, end_time=5)

    t.update(5_000)
    assert t.expired is False

    t.update(5_001)
    assert t.expired is True


def test_fractional_end_time():
    t = Timer(0, end_time=0.5)

    t.update(500)
    assert t.expired is False

    t.update(501)
    assert t.expired is True


def test_stop_freezes_elapsed_and_remaining():
    t = Timer(0, end_time=100)

    t.update(30_000)
    t.stop()
    t.update(90_000)

    assert t.duration == 30_000
    assert t.remaining == pytest.approx(70.0)


def test_stop_is_idempotent():
    t = Timer(0, end_time=100)

    t.update(30_000)
    t.stop()
    t.stop()
    t.update(90_000)

    assert t.duration == 30_000


def test_a_stopped_expired_timer_stays_expired():
    t = Timer(0, end_time=100)

    t.update(200_000)
    t.stop()
    t.update(0)

    assert t.expired is True


def test_restart_zeroes_elapsed_from_the_given_tick():
    t = Timer(0, end_time=100)

    t.update(50_000)
    t.restart(50_000)

    assert t.duration == 0
    assert t.remaining == pytest.approx(100.0)

    t.update(53_000)
    assert t.duration == 3_000


def test_restart_unfreezes_a_stopped_timer():
    t = Timer(0, end_time=100)

    t.stop()
    t.restart(60_000)

    assert t.stopped is False

    t.update(63_000)
    assert t.duration == 3_000


def test_restart_clears_expiry():
    t = Timer(0, end_time=100)

    t.update(200_000)
    t.restart(200_000)

    assert t.expired is False
    assert t.remaining == pytest.approx(100.0)


def test_restart_requires_a_tick_value():
    assert inspect.signature(Timer.restart).parameters["ticks"].default is inspect.Parameter.empty


def test_timer_init_requires_a_tick_value():
    assert inspect.signature(Timer.__init__).parameters["start_ticks"].default is inspect.Parameter.empty


def test_a_pygame_style_tick_sequence_drives_the_timer_monotonically():
    t = Timer(0, end_time=100)

    remaining_values = []
    expired_flags = []
    for ticks in range(0, 120_001, 16):
        t.update(ticks)
        remaining_values.append(t.remaining)
        expired_flags.append(t.expired)

    assert remaining_values == sorted(remaining_values, reverse=True)
    # expired flips from False to True exactly once
    transitions = sum(
        1 for a, b in zip(expired_flags, expired_flags[1:]) if a != b
    )
    assert transitions == 1
    assert expired_flags[0] is False
    assert expired_flags[-1] is True


# --- Session -----------------------------------------------------------------------


def test_new_session_has_a_full_timer_and_an_untouched_engine():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))

    assert session.timer.remaining == TIMER_SECONDS
    assert session.engine.score == 0
    assert session.is_over is False


def test_session_accepts_an_injected_timer():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=5))

    assert session.timer.remaining == 5


def test_session_update_forwards_ticks_to_the_timer():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))

    session.update(12_000)

    assert session.timer.duration == 12_000


def test_session_is_over_when_the_timer_expires():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=5))

    session.update(5_001)

    assert session.is_over is True


def test_session_is_not_over_at_exactly_the_end_time():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=5))

    session.update(5_000)

    assert session.is_over is False


def test_session_is_over_when_the_board_is_cleared():
    session = Session(GameEngine.load([[4, 6]]), Timer(0))
    apply_selection(session.engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))

    session.update(1_000)

    assert session.is_over is True


def test_session_is_not_over_while_apples_remain_and_time_is_left():
    # A deliberately stuck board -- no legal moves -- must NOT read as over.
    session = Session(GameEngine.load([[9, 9], [9, 9]]), Timer(0))

    session.update(1_000)

    assert session.is_over is False


def test_session_update_stops_the_timer_once_over():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=100))

    session.update(100_001)
    before = session.summary()
    session.update(200_000)
    after = session.summary()

    assert session.timer.stopped is True
    assert before == after


def test_session_update_records_the_crossing_tick_before_stopping():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=100))

    session.update(100_001)

    assert session.timer.duration == 100_001


def test_session_summary_returns_score_and_elapsed_seconds():
    session = Session(GameEngine.load([[4, 6]]), Timer(0))
    apply_selection(session.engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))

    session.update(12_000)

    assert session.summary() == (2, pytest.approx(12.0))


def test_session_summary_is_score_then_elapsed_seconds():
    session = Session(GameEngine.load([[4, 6]]), Timer(0))
    session.update(3_000)

    score, elapsed = session.summary()

    assert isinstance(score, int)
    assert elapsed == pytest.approx(session.timer.duration / 1000)


def test_session_summary_on_a_fresh_session_is_zero_zero():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))

    assert session.summary() == (0, pytest.approx(0.0))


def test_session_reset_restores_the_board_and_score():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    apply_selection(session.engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))

    session.reset(40_000)

    assert session.engine.board.grid == [[4, 6], [1, 1]]
    assert session.engine.score == 0
    assert session.engine.board.apples_remaining == 4


def test_session_reset_restarts_the_timer_from_the_given_tick():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    session.update(40_000)

    session.reset(40_000)

    assert session.timer.duration == 0
    assert session.timer.remaining == pytest.approx(TIMER_SECONDS)

    session.update(41_000)
    assert session.timer.duration == 1_000


def test_session_reset_after_expiry_resumes_play():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0, end_time=100))
    session.update(200_000)
    assert session.is_over is True

    session.reset(200_000)

    assert session.is_over is False
    assert session.timer.stopped is False

    session.update(200_500)
    assert session.timer.duration == 500


def test_session_reset_after_a_full_clear_makes_the_session_playable_again():
    session = Session(GameEngine.load([[4, 6]]), Timer(0))
    apply_selection(session.engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))
    session.update(1_000)
    assert session.is_over is True

    session.reset(1_000)

    assert session.is_over is False
    assert session.engine.board.grid == [[4, 6]]


def test_session_new_game_replaces_the_engine_and_zeroes_the_score():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    apply_selection(session.engine, Move(row_start=0, col_start=0, row_end=0, col_end=1))
    engine_before = session.engine

    session.new_game(0)

    assert session.engine is not engine_before
    assert session.engine.score == 0
    assert session.engine.board.apples_remaining == session.engine.board.rows * session.engine.board.cols


def test_session_new_game_with_a_seed_is_reproducible():
    session_a = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    session_b = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    session_c = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))

    session_a.new_game(0, seed=7)
    session_b.new_game(0, seed=7)
    session_c.new_game(0, seed=8)

    assert session_a.engine.board.grid == session_b.engine.board.grid
    assert session_a.engine.board.grid != session_c.engine.board.grid


def test_session_new_game_keeps_board_dimensions_and_value_range():
    session = Session(GameEngine.load([[4, 6, 1], [1, 1, 1]]), Timer(0))

    session.new_game(0, seed=3)

    assert session.engine.board.rows == 2
    assert session.engine.board.cols == 3
    assert session.engine.board.min_value == 1
    assert session.engine.board.max_value == 9


def test_session_new_game_restarts_the_timer():
    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    session.update(70_000)

    session.new_game(70_000)

    assert session.timer.duration == 0
    assert session.timer.remaining == pytest.approx(TIMER_SECONDS)


def test_session_new_game_seed_is_optional():
    params = inspect.signature(Session.new_game).parameters
    assert params["ticks"].default is inspect.Parameter.empty
    assert params["seed"].default is None

    session = Session(GameEngine.load([[4, 6], [1, 1]]), Timer(0))
    session.new_game(0)

    assert session.engine.board.verify() is None
    total = sum(sum(row) for row in session.engine.board.grid)
    assert total % TARGET_SUM == 0


def test_session_reset_and_new_game_require_a_tick_value():
    assert inspect.signature(Session.reset).parameters["ticks"].default is inspect.Parameter.empty
    assert inspect.signature(Session.new_game).parameters["ticks"].default is inspect.Parameter.empty


def test_session_full_playthrough_end_to_end():
    session = Session(GameEngine.load([[4, 6], [3, 7]]), Timer(0))
    drag = Drag(rows=2, cols=2)

    def center(row, col):
        return (
            GRID_ORIGIN_X_PX + col * CELL_SIZE_PX + CELL_SIZE_PX // 2,
            GRID_ORIGIN_Y_PX + row * CELL_SIZE_PX + CELL_SIZE_PX // 2,
        )

    # First move: row 0 (4+6=10).
    drag.begin(center(0, 0))
    drag.update(center(0, 1))
    move = drag.release(center(0, 1))
    apply_selection(session.engine, move)
    session.update(10_000)

    assert session.engine.score == 2
    assert session.is_over is False

    # Second move: row 1 (3+7=10) -- clears the board.
    drag.begin(center(1, 0))
    drag.update(center(1, 1))
    move = drag.release(center(1, 1))
    apply_selection(session.engine, move)
    session.update(20_000)

    assert session.engine.score == 4
    assert session.is_over is True
    assert session.summary() == (4, pytest.approx(20.0))
