"""Tests for single-step move ranking (SPEC.md FR15, section 9.2, NFR7).

Covers ``RankedMove``/``StrategyFn``'s shape, the three MVP strategies
(``strategy_max_apples``, ``strategy_min_apples``, ``strategy_random`` /
``make_random_strategy``), ``rank_moves``'s ordering, tie-breaking, ``count``
truncation, and non-mutation guarantees, the ``STRATEGIES`` registry, and
integration with ``find_legal_moves``. All headless -- no display, no pygame.

A strategy is a per-move scorer (``Callable[[BoardState, Move], float]``);
``rank_moves`` owns applying it across a move list, building ``RankedMove``s,
sorting, and truncating (SPEC.md section 8's "Strategy shape (resolved)").
Moves are assumed to already be legal on the board they're ranked against --
this layer never re-validates, matching ``find_legal_moves``'s and
``BoardState.is_legal``'s own hot-path posture.
"""

import random

import pytest

from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move
from fruitbox.solver.move_scanner import find_legal_moves
from fruitbox.solver.strategies import (
    DEFAULT_STRATEGY,
    STRATEGIES,
    RankedMove,
    make_random_strategy,
    rank_moves,
    strategy_max_apples,
    strategy_min_apples,
    strategy_random,
)

# A 4x4 hand-authored layout with five legal moves whose apple counts give a
# strict three-level ordering plus a deliberate three-way tie -- and, crucially,
# a move whose *area* is the largest of all but whose *apple count* is not
# (SPARSE): any implementation that ranks by rectangle size instead of true
# apples-removed fails this fixture loudly.
#
#   BIG    rows 0-0, cols 0-3  -> 1+2+3+4 = 10, 4 apples, area 4
#   TRIPLE rows 0-3, col 0     -> 1+0+5+4 = 10, 3 apples, area 4
#   SPARSE rows 1-3, cols 2-3  -> 9+1+0+0+0+0 = 10, 2 apples, area 6
#   PAIR   row 2, cols 0-1     -> 5+5 = 10, 2 apples, area 2
#   BOTTOM row 3, cols 0-1     -> 4+6 = 10, 2 apples, area 2
#
# 10 apples total, 6 empty cells.
LAYOUT = [
    [1, 2, 3, 4],
    [0, 0, 9, 1],
    [5, 5, 0, 0],
    [4, 6, 0, 0],
]
LAYOUT_APPLES = 10

BIG = Move(row_start=0, col_start=0, row_end=0, col_end=3)
TRIPLE = Move(row_start=0, col_start=0, row_end=3, col_end=0)
SPARSE = Move(row_start=1, col_start=2, row_end=3, col_end=3)
PAIR = Move(row_start=2, col_start=0, row_end=2, col_end=1)
BOTTOM = Move(row_start=3, col_start=0, row_end=3, col_end=1)

ALL_MOVES = [BIG, TRIPLE, SPARSE, PAIR, BOTTOM]


def _board() -> BoardState:
    """A fresh 4x4 ``BoardState`` on ``LAYOUT`` (never the shared list)."""
    return BoardState(grid=[row[:] for row in LAYOUT], rows=4, cols=4)


def test_fixture_moves_are_all_legal_and_apple_count_is_correct():
    state = _board()

    for move in ALL_MOVES:
        assert state.is_legal(move)
    assert state.apples_remaining == LAYOUT_APPLES


# --- RankedMove ---------------------------------------------------------------


def test_ranked_move_holds_its_three_fields():
    rm = RankedMove(move=BIG, score=4.0, apples_removed=4)

    assert rm.move == BIG
    assert rm.score == 4.0
    assert rm.apples_removed == 4


def test_ranked_move_is_frozen():
    rm = RankedMove(move=BIG, score=4.0, apples_removed=4)

    with pytest.raises(Exception):
        rm.score = 99.0


def test_ranked_move_is_hashable_and_comparable_by_value():
    a = RankedMove(move=BIG, score=4.0, apples_removed=4)
    b = RankedMove(move=BIG, score=4.0, apples_removed=4)

    assert a == b
    assert hash(a) == hash(b)


# --- strategy_max_apples -------------------------------------------------------


@pytest.mark.parametrize(
    "move,expected",
    [(BIG, 4.0), (TRIPLE, 3.0), (SPARSE, 2.0), (PAIR, 2.0), (BOTTOM, 2.0)],
)
def test_strategy_max_apples_scores_by_apples_not_area(move, expected):
    state = _board()

    # SPARSE has the largest area (6) of every fixture move, yet its score
    # matches its (smaller) apple count, not its area.
    assert strategy_max_apples(state, move) == expected


def test_strategy_max_apples_equals_count_apples_for_every_move():
    state = _board()

    for move in ALL_MOVES:
        assert strategy_max_apples(state, move) == float(state.count_apples(move))


def test_strategy_max_apples_does_not_mutate_the_board():
    state = _board()
    grid_before = [row[:] for row in state.grid]

    for move in ALL_MOVES:
        strategy_max_apples(state, move)

    assert state.grid == grid_before


def test_strategy_max_apples_score_equals_area_when_rectangle_is_fully_occupied():
    # BIG's rectangle has no empty cells, so apples == area here (4).
    assert strategy_max_apples(_board(), BIG) == 4.0


# --- strategy_min_apples -------------------------------------------------------


@pytest.mark.parametrize("move", ALL_MOVES)
def test_strategy_min_apples_is_the_negation_of_max_apples(move):
    state = _board()

    assert strategy_min_apples(state, move) == -strategy_max_apples(state, move)


def test_strategy_min_apples_orders_inversely():
    state = _board()

    assert strategy_min_apples(state, PAIR) > strategy_min_apples(state, BIG)


def test_strategy_min_apples_does_not_mutate_the_board():
    state = _board()
    grid_before = [row[:] for row in state.grid]

    for move in ALL_MOVES:
        strategy_min_apples(state, move)

    assert state.grid == grid_before


# --- strategy_random / make_random_strategy ------------------------------------


def test_strategy_random_returns_a_float_in_unit_interval():
    state = _board()

    for move in ALL_MOVES:
        score = strategy_random(state, move)
        assert 0.0 <= score < 1.0


def test_strategy_random_varies_across_calls():
    state = _board()

    scores = {strategy_random(state, BIG) for _ in range(20)}

    assert len(scores) > 1


def test_strategy_random_does_not_touch_the_board():
    state = _board()
    grid_before = [row[:] for row in state.grid]

    for move in ALL_MOVES:
        strategy_random(state, move)

    assert state.grid == grid_before


def test_strategy_random_does_not_disturb_global_random_state():
    random.seed(12345)
    expected = [random.random() for _ in range(3)]

    random.seed(12345)
    state = _board()
    for _ in range(10):
        strategy_random(state, BIG)
    actual = [random.random() for _ in range(3)]

    assert actual == expected


def test_make_random_strategy_same_seed_gives_identical_scores():
    state = _board()
    a = make_random_strategy(seed=7)
    b = make_random_strategy(seed=7)

    assert [a(state, m) for m in ALL_MOVES] == [b(state, m) for m in ALL_MOVES]


def test_make_random_strategy_same_seed_gives_identical_rank_moves_output():
    state = _board()

    first = rank_moves(state, ALL_MOVES, strategy=make_random_strategy(seed=99))
    second = rank_moves(state, ALL_MOVES, strategy=make_random_strategy(seed=99))

    assert [rm.move for rm in first] == [rm.move for rm in second]


def test_make_random_strategy_different_seeds_differ():
    state = _board()
    a = make_random_strategy(seed=1)
    b = make_random_strategy(seed=2)

    assert [a(state, m) for m in ALL_MOVES] != [b(state, m) for m in ALL_MOVES]


def test_make_random_strategys_closure_is_stateful_across_calls():
    # Reusing the same strategy object across two rank_moves calls advances
    # its RNG each time, so the two results may differ -- this is documented,
    # intended behavior (fresh randomness per move during a playout), not a
    # bug. Reproducibility means re-making the strategy from its seed.
    state = _board()
    strategy = make_random_strategy(seed=5)

    first = [rm.move for rm in rank_moves(state, ALL_MOVES, strategy=strategy)]
    second = [rm.move for rm in rank_moves(state, ALL_MOVES, strategy=strategy)]
    reproduced = [
        rm.move
        for rm in rank_moves(state, ALL_MOVES, strategy=make_random_strategy(seed=5))
    ]

    assert first != second  # reusing the strategy object advances its RNG
    assert first == reproduced  # re-making from the same seed reproduces it


def test_make_random_strategy_without_a_seed_still_works():
    state = _board()
    strategy = make_random_strategy()

    result = rank_moves(state, ALL_MOVES, strategy=strategy)

    assert {rm.move for rm in result} == set(ALL_MOVES)


def test_make_random_strategy_does_not_disturb_global_random_state():
    random.seed(54321)
    expected = [random.random() for _ in range(3)]

    random.seed(54321)
    seeded = make_random_strategy(seed=1)
    unseeded = make_random_strategy()
    state = _board()
    for move in ALL_MOVES:
        seeded(state, move)
        unseeded(state, move)
    actual = [random.random() for _ in range(3)]

    assert actual == expected


# --- rank_moves: ordering and packaging ----------------------------------------


def test_rank_moves_default_strategy_orders_by_max_apples():
    state = _board()

    result = rank_moves(state, ALL_MOVES)

    assert [rm.move for rm in result] == [BIG, TRIPLE, SPARSE, PAIR, BOTTOM]


def test_default_strategy_is_max_apples():
    assert DEFAULT_STRATEGY is strategy_max_apples


def test_rank_moves_largest_area_move_does_not_win_under_max_apples():
    state = _board()

    result = rank_moves(state, ALL_MOVES)

    assert result[0].move == BIG
    # SPARSE has the largest area (6) of every fixture move, but ranks third.
    assert [rm.move for rm in result].index(SPARSE) == 2


def test_rank_moves_packages_apples_removed_and_score_correctly():
    state = _board()

    result = rank_moves(state, ALL_MOVES)

    for rm in result:
        assert rm.apples_removed == state.count_apples(rm.move)
        assert rm.score == float(rm.apples_removed)


@pytest.mark.parametrize("strategy", list(STRATEGIES.values()))
def test_rank_moves_scores_are_non_increasing(strategy):
    state = _board()

    result = rank_moves(state, ALL_MOVES, strategy=strategy)

    scores = [rm.score for rm in result]
    assert scores == sorted(scores, reverse=True)


def test_rank_moves_tie_break_preserves_input_order():
    state = _board()

    result = rank_moves(state, [SPARSE, PAIR, BOTTOM])
    assert [rm.move for rm in result] == [SPARSE, PAIR, BOTTOM]

    reordered = rank_moves(state, [BOTTOM, PAIR, SPARSE])
    assert [rm.move for rm in reordered] == [BOTTOM, PAIR, SPARSE]


def test_rank_moves_with_min_apples_reverses_the_strict_levels():
    state = _board()

    result = rank_moves(state, ALL_MOVES, strategy=strategy_min_apples)

    assert [rm.move for rm in result] == [SPARSE, PAIR, BOTTOM, TRIPLE, BIG]


def test_rank_moves_supports_an_arbitrary_custom_strategy():
    # NFR7 proof: a strategy defined entirely outside this module works with
    # no change to rank_moves's call site.
    state = _board()

    def by_row_start(_state, move):
        return float(move.row_start)

    result = rank_moves(state, ALL_MOVES, strategy=by_row_start)

    assert [rm.move for rm in result] == sorted(
        ALL_MOVES, key=lambda m: m.row_start, reverse=True
    )


@pytest.mark.parametrize("strategy", list(STRATEGIES.values()))
def test_rank_moves_result_is_a_permutation_of_the_input(strategy):
    state = _board()

    result = rank_moves(state, ALL_MOVES, strategy=strategy)

    assert len(result) == len(ALL_MOVES)
    assert {rm.move for rm in result} == set(ALL_MOVES)


def test_rank_moves_on_empty_input_returns_empty_list():
    assert rank_moves(_board(), []) == []


def test_rank_moves_on_single_move_input_returns_that_move():
    result = rank_moves(_board(), [PAIR])

    assert [rm.move for rm in result] == [PAIR]


# --- rank_moves: the count parameter --------------------------------------------


def test_rank_moves_count_none_returns_everything():
    state = _board()

    assert len(rank_moves(state, ALL_MOVES, count=None)) == len(ALL_MOVES)


def test_rank_moves_count_one_matches_the_untruncated_top_result():
    state = _board()

    full = rank_moves(state, ALL_MOVES)
    top = rank_moves(state, ALL_MOVES, count=1)

    assert len(top) == 1
    assert top[0] == full[0]


def test_rank_moves_count_three_matches_the_untruncated_prefix():
    state = _board()

    full = rank_moves(state, ALL_MOVES)
    truncated = rank_moves(state, ALL_MOVES, count=3)

    assert truncated == full[:3]


@pytest.mark.parametrize(
    "make_strategy", [lambda: strategy_max_apples, lambda: make_random_strategy(seed=17)]
)
@pytest.mark.parametrize("count", range(0, 8))
def test_rank_moves_truncated_and_untruncated_paths_agree(make_strategy, count):
    # Pins down that heapq.nlargest's selection agrees with sorting the full
    # list and slicing, including tie order -- true under max_apples (which
    # has real ties on this fixture) and under a fixed seeded random strategy
    # (which does not). A fresh strategy is built for each call: a seeded
    # random strategy is stateful, so reusing one object across both calls
    # would score the second call against an already-advanced RNG and make
    # the two paths incomparable -- that's make_random_strategy's documented
    # statefulness, not a bug in rank_moves.
    state = _board()

    full = rank_moves(state, ALL_MOVES, strategy=make_strategy())
    truncated = rank_moves(state, ALL_MOVES, strategy=make_strategy(), count=count)

    assert truncated == full[:count]


def test_rank_moves_count_larger_than_input_returns_everything():
    state = _board()

    result = rank_moves(state, ALL_MOVES, count=100)

    assert len(result) == len(ALL_MOVES)


def test_rank_moves_count_zero_returns_empty_list():
    assert rank_moves(_board(), ALL_MOVES, count=0) == []


def test_rank_moves_negative_count_raises_value_error():
    with pytest.raises(ValueError):
        rank_moves(_board(), ALL_MOVES, count=-1)


@pytest.mark.parametrize("count", [None, 0, 5])
def test_rank_moves_on_empty_moves_with_any_count(count):
    assert rank_moves(_board(), [], count=count) == []


@pytest.mark.parametrize("count", [1, 2, 100])
def test_rank_moves_single_move_input_with_various_counts(count):
    result = rank_moves(_board(), [PAIR], count=count)

    assert [rm.move for rm in result] == [PAIR]


# --- rank_moves: non-mutation ---------------------------------------------------


@pytest.mark.parametrize("strategy", list(STRATEGIES.values()))
@pytest.mark.parametrize("count", [None, 2])
def test_rank_moves_does_not_mutate_the_board(strategy, count):
    state = _board()
    grid_before = [row[:] for row in state.grid]
    apples_before = state.apples_remaining

    rank_moves(state, ALL_MOVES, strategy=strategy, count=count)

    assert state.grid == grid_before
    assert state.apples_remaining == apples_before


def test_rank_moves_does_not_reorder_the_callers_move_list():
    state = _board()
    moves = [SPARSE, PAIR, BOTTOM, TRIPLE, BIG]
    moves_before = list(moves)

    rank_moves(state, moves)

    assert moves == moves_before


def test_rank_moves_does_not_mutate_a_random_full_size_board():
    state = BoardState.generate_board(seed=2024)
    legal = find_legal_moves(state)
    grid_before = [row[:] for row in state.grid]

    rank_moves(state, legal)

    assert state.grid == grid_before


# --- STRATEGIES registry --------------------------------------------------------


def test_strategies_registry_has_exactly_the_expected_keys():
    assert set(STRATEGIES) == {"max_apples", "min_apples", "random"}


def test_strategies_registry_identity():
    assert STRATEGIES["max_apples"] is strategy_max_apples
    assert STRATEGIES["min_apples"] is strategy_min_apples
    assert STRATEGIES["random"] is strategy_random


# --- Integration with find_legal_moves ------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 1234])
@pytest.mark.parametrize(
    "strategy_factory",
    [
        lambda: strategy_max_apples,
        lambda: strategy_min_apples,
        lambda: make_random_strategy(seed=17),
    ],
)
def test_rank_moves_integrates_with_find_legal_moves_on_random_boards(seed, strategy_factory):
    # strategy_factory() is called fresh for each rank_moves call below: a
    # seeded random strategy is stateful, so reusing one object across both
    # calls would compare results scored against two different RNG states.
    state = BoardState.generate_board(seed=seed)
    legal = find_legal_moves(state)

    result = rank_moves(state, legal, strategy=strategy_factory())

    assert {rm.move for rm in result} == set(legal)
    scores = [rm.score for rm in result]
    assert scores == sorted(scores, reverse=True)
    for rm in result:
        assert rm.apples_removed == state.count_apples(rm.move)

    top_one = rank_moves(state, legal, strategy=strategy_factory(), count=1)
    assert top_one[0] == result[0]


def test_rank_moves_and_find_legal_moves_agree_on_a_stuck_board():
    state = BoardState(grid=[[9, 0], [0, 9]], rows=2, cols=2)

    legal = find_legal_moves(state)
    assert legal == []
    assert rank_moves(state, legal) == []


def test_rank_moves_and_find_legal_moves_agree_on_a_fully_cleared_board():
    state = BoardState(grid=[[0, 0], [0, 0]], rows=2, cols=2)

    legal = find_legal_moves(state)
    assert legal == []
    assert rank_moves(state, legal) == []


def test_greedy_composition_smoke_test():
    # rank_moves(count=1) composes cleanly with find_legal_moves and
    # apply_move to drive a board to a terminal state -- a light guard that
    # the pieces fit together; the real play_greedy is a later issue (FR17).
    state = BoardState.generate_board(rows=5, cols=5, seed=3)

    steps = 0
    while True:
        legal = find_legal_moves(state)
        if not legal:
            break
        top = rank_moves(state, legal, count=1)
        assert len(top) == 1
        before = state.apples_remaining
        state.apply_move(top[0].move)
        assert state.apples_remaining < before
        steps += 1
        assert steps < 1000  # loop-termination guard, not a tuned bound

    assert find_legal_moves(state) == []
