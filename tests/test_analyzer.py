"""Tests for the greedy playout orchestration layer (SPEC.md FR17, section 9.4).

Covers ``ClearResult``'s shape (two fields, everything else derived), the
core outcomes of ``play_greedy`` on hand-authored fixtures (full clear,
partial clear with apples stranded, stuck-from-start, already-empty),
non-mutation of the caller's board, invariants over randomized boards,
degenerate/edge-case boards, and strategy pluggability (NFR7). All headless
-- no display, no pygame.

Includes the tests originally scoped to issue #11 ("Solver playout tests"),
folded into this issue per its own description.

Every full-clear assertion below is written against
``result.final_state.apples_remaining`` -- ``ClearResult`` has no stored
``found_full_clear`` flag by design (SPEC.md section 9.4): a stored bool
could disagree with the board it describes, while a derived check cannot.
"""

import dataclasses
import random

import pytest

from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move
from fruitbox.solver.analyzer import ClearResult, play_greedy
from fruitbox.solver.move_scanner import find_legal_moves
from fruitbox.solver.strategies import (
    STRATEGIES,
    make_random_strategy,
    strategy_max_apples,
    strategy_min_apples,
)


def _moves_used(result: ClearResult) -> int:
    return len(result.moves)


def _apples_cleared(before: BoardState, result: ClearResult) -> int:
    return before.apples_remaining - result.final_state.apples_remaining


# --- Fixtures ------------------------------------------------------------------
#
# All hand-authored and cross-checked by actually running play_greedy against
# them (not guessed). Each factory returns a fresh BoardState over copied
# rows, so no test mutates a shared layout list.

FULL_CLEAR = [
    [1, 9, 4, 6],
    [2, 8, 3, 7],
]
# Under strategy_max_apples: the only initially legal moves are the four
# disjoint pairs (1,9), (4,6), (2,8), (3,7), each worth 2 apples -- every
# move is a tie, so the exact sequence follows enumeration order rather than
# being hand-picked. As cells clear, new zero-spanning 2-apple rectangles
# appear, and the board always finishes in exactly 4 moves / 8 apples
# cleared (verified by running the real implementation).

PARTIAL = [
    [1, 2, 3],
    [4, 5, 1],
    [3, 2, 9],
]
# Initially legal: row 1 (4+5+1=10, 3 apples) and the col-2 pair spanning
# rows 1-2 (1+9=10, 2 apples). strategy_max_apples takes row 1; the residual
# grid [[1,2,3],[0,0,0],[3,2,9]] has zero legal rectangles (verified
# exhaustively), so the playout halts with 6 apples stranded.
#
# The same layout, reused under strategy_min_apples, is this file's
# DIVERGENCE case: min_apples takes the 2-apple col-2 pair first, then a
# 3-apple move, then a 4-apple move, clearing the board completely -- same
# board, opposite outcome, proving both that `strategy` is honoured and
# SPEC.md section 9.2's point that greedy-largest is not optimal.

STUCK_FROM_START = [
    [9, 0],
    [0, 9],
]

ALREADY_EMPTY = [
    [0, 0],
    [0, 0],
]


def _board_full_clear() -> BoardState:
    return BoardState(grid=[row[:] for row in FULL_CLEAR], rows=2, cols=4)


def _board_partial() -> BoardState:
    return BoardState(grid=[row[:] for row in PARTIAL], rows=3, cols=3)


def _board_stuck_from_start() -> BoardState:
    return BoardState(grid=[row[:] for row in STUCK_FROM_START], rows=2, cols=2)


def _board_already_empty() -> BoardState:
    return BoardState(grid=[row[:] for row in ALREADY_EMPTY], rows=2, cols=2)


ALL_FIXTURE_FACTORIES = [
    _board_full_clear,
    _board_partial,
    _board_stuck_from_start,
    _board_already_empty,
]


def test_fixtures_are_what_the_comments_claim():
    assert _board_full_clear().apples_remaining == 8
    assert len(find_legal_moves(_board_full_clear())) == 4

    assert _board_partial().apples_remaining == 9
    assert len(find_legal_moves(_board_partial())) == 2

    assert _board_stuck_from_start().apples_remaining == 2
    assert find_legal_moves(_board_stuck_from_start()) == []

    assert _board_already_empty().apples_remaining == 0
    assert find_legal_moves(_board_already_empty()) == []


# --- Core outcomes and internal consistency -------------------------------------


def test_full_clear_board_is_fully_cleared():
    state = _board_full_clear()

    result = play_greedy(state)

    assert result.final_state.apples_remaining == 0
    assert _moves_used(result) == 4
    assert _apples_cleared(state, result) == 8


def test_partial_board_stops_with_apples_stranded():
    state = _board_partial()

    result = play_greedy(state)

    assert result.final_state.apples_remaining == 6  # not 0: greedy got stuck
    assert _moves_used(result) == 1
    assert _apples_cleared(state, result) == 3
    assert result.moves == [Move(row_start=1, col_start=0, row_end=1, col_end=2)]


def test_stuck_from_start_returns_no_moves():
    state = _board_stuck_from_start()

    result = play_greedy(state)

    assert result.moves == []
    assert result.final_state.apples_remaining == 2
    assert _apples_cleared(state, result) == 0
    assert result.final_state.grid == STUCK_FROM_START


def test_already_empty_board_is_reported_as_fully_cleared():
    state = _board_already_empty()

    result = play_greedy(state)

    assert result.moves == []
    assert result.final_state.apples_remaining == 0


@pytest.mark.parametrize("factory", ALL_FIXTURE_FACTORIES)
def test_final_state_apples_remaining_matches_a_fresh_recount(factory):
    result = play_greedy(factory())

    fs = result.final_state
    recount = sum(1 for row in fs.grid for v in row if v != 0)
    assert fs.apples_remaining == recount


@pytest.mark.parametrize("factory", ALL_FIXTURE_FACTORIES)
def test_final_state_passes_verify(factory):
    result = play_greedy(factory())

    assert result.final_state.verify() is None


@pytest.mark.parametrize("factory", ALL_FIXTURE_FACTORIES)
def test_replaying_the_moves_reproduces_the_final_state(factory):
    # The strongest single check in this file: replay result.moves through a
    # completely independent path (BoardState.apply_move on a fresh copy of
    # the original board) and confirm it lands on the same board -- and that
    # every move really was legal at the moment it was played (apply_move
    # raises ValueError otherwise, which is itself the assertion).
    before = factory()
    result = play_greedy(before)

    replay = factory()
    removed_total = 0
    for move in result.moves:
        removed_total += replay.apply_move(move)

    assert replay.grid == result.final_state.grid
    assert replay.apples_remaining == result.final_state.apples_remaining
    assert removed_total == _apples_cleared(before, result)


def test_no_move_is_repeated_and_every_move_removes_at_least_one_apple():
    for factory in (_board_full_clear, _board_partial):
        state = factory()
        result = play_greedy(state)

        replay = factory()
        for move in result.moves:
            removed = replay.apply_move(move)
            assert removed >= 1

        assert len(set(result.moves)) == len(result.moves)


@pytest.mark.parametrize("factory", ALL_FIXTURE_FACTORIES)
def test_playout_ends_with_no_legal_moves_remaining(factory):
    result = play_greedy(factory())

    assert find_legal_moves(result.final_state) == []


# --- Non-mutation / ownership ---------------------------------------------------


@pytest.mark.parametrize("factory", ALL_FIXTURE_FACTORIES)
def test_play_greedy_does_not_mutate_the_caller_board(factory):
    state = factory()
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    play_greedy(state)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


def test_final_state_is_not_the_caller_board():
    state = _board_full_clear()

    result = play_greedy(state)

    assert result.final_state is not state
    assert result.final_state.grid is not state.grid
    assert all(a is not b for a, b in zip(result.final_state.grid, state.grid))


def test_mutating_the_result_does_not_affect_the_caller_board():
    state = _board_full_clear()
    result = play_greedy(state)

    result.final_state.grid[0][0] = 42

    assert state.grid == FULL_CLEAR


def test_play_greedy_is_repeatable_on_the_same_board():
    state = _board_partial()

    first = play_greedy(state)
    second = play_greedy(state)

    assert first == second


def test_play_greedy_does_not_disturb_global_random_state():
    random.seed(12345)
    expected = [random.random() for _ in range(3)]

    random.seed(12345)
    play_greedy(_board_partial())
    play_greedy(_board_full_clear(), strategy=make_random_strategy(seed=7))
    actual = [random.random() for _ in range(3)]

    assert actual == expected


def test_play_greedy_does_not_mutate_a_shared_layout_constant():
    # Every _board_*() factory copies its rows, so running the whole suite
    # must never perturb the module-level layout lists themselves.
    assert FULL_CLEAR == [[1, 9, 4, 6], [2, 8, 3, 7]]
    assert PARTIAL == [[1, 2, 3], [4, 5, 1], [3, 2, 9]]
    assert STUCK_FROM_START == [[9, 0], [0, 9]]
    assert ALREADY_EMPTY == [[0, 0], [0, 0]]


# --- Random-board invariants ------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
def test_playout_terminates_and_is_self_consistent_on_random_boards(seed):
    state = BoardState.generate_board(seed=seed)
    before_apples = state.apples_remaining

    result = play_greedy(state)

    assert find_legal_moves(result.final_state) == []
    fs = result.final_state
    recount = sum(1 for row in fs.grid for v in row if v != 0)
    assert fs.apples_remaining == recount
    cleared = _apples_cleared(state, result)
    assert 0 <= cleared <= before_apples
    assert _moves_used(result) >= 1
    assert result.final_state.verify() is None


@pytest.mark.parametrize("rows,cols,seed", [(5, 5, 0), (5, 5, 1), (6, 6, 2)])
def test_playout_terminates_and_is_self_consistent_on_small_random_boards(rows, cols, seed):
    state = BoardState.generate_board(rows=rows, cols=cols, seed=seed)

    result = play_greedy(state)

    assert find_legal_moves(result.final_state) == []
    assert result.final_state.verify() is None


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_random_board_moves_replay_exactly(seed):
    state = BoardState.generate_board(seed=seed)
    original_grid = [row[:] for row in state.grid]

    result = play_greedy(state)

    replay = BoardState(grid=[row[:] for row in original_grid], rows=state.rows, cols=state.cols)
    for move in result.moves:
        replay.apply_move(move)

    assert replay.grid == result.final_state.grid
    assert replay.apples_remaining == result.final_state.apples_remaining


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_random_board_playout_does_not_mutate_the_input(seed):
    state = BoardState.generate_board(seed=seed)
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    play_greedy(state)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_apples_cleared_is_a_multiple_of_ten_in_value_not_count(seed):
    # The *sum of values* removed by a legal move is always exactly
    # TARGET_SUM (10); over moves_used moves that totals 10 * moves_used.
    # Checked independently of apple *counts*, so it catches a class of bug
    # apple-count checks alone would not.
    state = BoardState.generate_board(seed=seed)
    original_grid = [row[:] for row in state.grid]

    result = play_greedy(state)

    replay = BoardState(grid=[row[:] for row in original_grid], rows=state.rows, cols=state.cols)
    value_sum = 0
    for move in result.moves:
        value_sum += sum(replay.grid[r][c] for r, c in move.cells())
        replay.apply_move(move)

    assert value_sum == 10 * _moves_used(result)


def test_full_clears_are_rare_but_stuck_states_are_normal_on_random_boards():
    # A soft characterization test, not a rate assertion (that's issue #12's
    # benchmark script's job, per SPEC.md section 10). Guards against a
    # "clears everything, always" bug masking real greedy behavior.
    stuck_count = 0
    for seed in range(20):
        state = BoardState.generate_board(seed=seed)
        result = play_greedy(state)
        if result.final_state.apples_remaining > 0:
            stuck_count += 1

    assert stuck_count >= 1


# --- Edge cases --------------------------------------------------------------------


def test_single_cell_board_is_never_clearable():
    state = BoardState(grid=[[5]], rows=1, cols=1)

    result = play_greedy(state)

    assert result.moves == []
    assert result.final_state.apples_remaining == 1


def test_board_that_is_one_legal_move_from_empty():
    state = BoardState(grid=[[4, 6]], rows=1, cols=2)

    result = play_greedy(state)

    assert len(result.moves) == 1
    assert result.final_state.apples_remaining == 0


def test_legal_move_spanning_already_empty_cells_is_played():
    state = BoardState(grid=[[7, 0, 3]], rows=1, cols=3)

    result = play_greedy(state)

    assert result.moves == [Move(row_start=0, col_start=0, row_end=0, col_end=2)]
    assert result.final_state.apples_remaining == 0


def test_full_board_playout_is_fast():
    # A runaway-loop tripwire only -- not a solver metric. The solver's only
    # efficiency metric is move count, never elapsed time (SPEC.md section 9).
    import time

    state = BoardState.generate_board(seed=7)

    start = time.perf_counter()
    play_greedy(state)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0


# --- Strategy pluggability (NFR7) --------------------------------------------------


def test_default_strategy_is_used_when_omitted():
    state_a = _board_partial()
    state_b = _board_partial()

    default = play_greedy(state_a)
    explicit = play_greedy(state_b, strategy=strategy_max_apples)

    assert default.moves == explicit.moves
    assert default.final_state.apples_remaining == 6
    assert explicit.final_state.apples_remaining == 6


def test_min_apples_clears_a_board_max_apples_gets_stuck_on():
    max_apples_result = play_greedy(_board_partial(), strategy=strategy_max_apples)
    min_apples_result = play_greedy(_board_partial(), strategy=strategy_min_apples)

    state_for_derivation = _board_partial()
    assert max_apples_result.final_state.apples_remaining == 6
    assert _apples_cleared(state_for_derivation, max_apples_result) == 3

    assert min_apples_result.final_state.apples_remaining == 0
    assert _moves_used(min_apples_result) == 3
    assert _apples_cleared(state_for_derivation, min_apples_result) == 9


@pytest.mark.parametrize("strategy_name", list(STRATEGIES))
def test_every_registered_strategy_produces_a_valid_playout(strategy_name):
    strategy = STRATEGIES[strategy_name]

    for factory in (_board_full_clear, lambda: BoardState.generate_board(seed=5)):
        state = factory()
        grid_before = [row[:] for row in state.grid]

        result = play_greedy(state, strategy=strategy)

        assert find_legal_moves(result.final_state) == []
        assert state.grid == grid_before  # input still untouched


def test_an_arbitrary_custom_strategy_works():
    def by_row_start(_state, move):
        return float(move.row_start)

    state = _board_full_clear()

    result = play_greedy(state, strategy=by_row_start)

    assert find_legal_moves(result.final_state) == []


def test_seeded_random_strategy_gives_a_reproducible_playout():
    # make_random_strategy's closure is stateful (documented in
    # strategies.py and test_strategies.py), so reproducibility requires
    # building a *fresh* strategy per call, not reusing one object.
    state_a = _board_full_clear()
    state_b = _board_full_clear()

    result_a = play_greedy(state_a, strategy=make_random_strategy(seed=17))
    result_b = play_greedy(state_b, strategy=make_random_strategy(seed=17))

    assert result_a == result_b


# --- ClearResult shape --------------------------------------------------------------


def test_clear_result_has_exactly_two_fields():
    assert [f.name for f in dataclasses.fields(ClearResult)] == ["moves", "final_state"]


def test_clear_result_is_frozen():
    result = play_greedy(_board_full_clear())

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.moves = []


def test_clear_result_is_not_hashable():
    result = play_greedy(_board_full_clear())

    with pytest.raises(TypeError):
        hash(result)


def test_clear_result_compares_by_value():
    a = play_greedy(_board_full_clear())
    b = play_greedy(_board_full_clear())
    c = play_greedy(_board_partial())

    assert a == b
    assert a != c


def test_clear_result_can_be_constructed_directly():
    empty = _board_already_empty()

    result = ClearResult(moves=[], final_state=empty)

    assert result.moves == []
    assert result.final_state.apples_remaining == 0
