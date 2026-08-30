"""Single-step move ranking (SPEC.md FR15, section 9.2, NFR7).

``find_legal_moves`` (``move_scanner.py``) answers "what can I play?";
``rank_moves`` answers "which of those should I play right now?" -- with no
lookahead whatsoever (bounded lookahead is section 9.3's ``search.py``, a
separate concern) and no wall-clock reasoning (the solver's only efficiency
metric is move count, never elapsed time).

A ``StrategyFn`` scores a *single* move against a *single* state:

    StrategyFn = Callable[[BoardState, Move], float]   # higher = better

Ordering, ``RankedMove`` construction, and truncation are not a strategy's
job -- they belong to :func:`rank_moves`, the one place that applies a
strategy across a move list, sorts the results, and optionally truncates to
the top ``count``. This keeps every new heuristic a one-line scoring function
with no sorting boilerplate to get wrong, and guarantees every strategy
inherits identical ordering and tie-breaking behavior for free (NFR7).

Every function here only ever *reads* the ``BoardState`` it is given -- never
mutates it, the same discipline ``move_scanner`` documents and honours.
Moves passed to :func:`rank_moves` are assumed to already be legal on
``state`` (normally straight from ``find_legal_moves``); this layer ranks,
it does not re-validate, matching ``BoardState.is_legal``'s own "assume
well-formed on the hot path" posture.

This module depends only on ``fruitbox.engine`` and ``fruitbox.config``,
never on ``fruitbox.ui`` (SPEC.md section 7, NFR1a).
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass
from typing import Callable

from ..engine.board import BoardState
from ..engine.moves import Move


@dataclass(frozen=True)
class RankedMove:
    """A move together with its heuristic score and true apple count.

    ``score`` is heuristic-dependent (higher = better) and only meaningful
    for comparing moves ranked by the *same* strategy -- ``strategy_max_apples``
    and ``strategy_random`` do not produce comparable scores. ``apples_removed``
    is not a heuristic: it is always the count of cells the move would really
    clear (:meth:`BoardState.count_apples`), regardless of which strategy
    produced this ``RankedMove``.
    """

    move: Move
    score: float
    apples_removed: int


#: A strategy scores ONE move against ONE state; higher is better. It must
#: not mutate ``state`` and has no say in ordering or truncation -- that is
#: :func:`rank_moves`'s job.
StrategyFn = Callable[[BoardState, Move], float]


def strategy_max_apples(state: BoardState, move: Move) -> float:
    """Score a move by how many apples it would actually clear.

    Not the rectangle's area -- a rectangle spanning already-cleared cells is
    worth only the apples it really removes (SPEC.md section 2). A reasonable
    single-step proxy for the move-count objective (fewer, larger moves tend
    toward fewer total moves), though not guaranteed optimal: a greedy large
    move can fragment the board and cost more moves overall than a smaller
    one would have (SPEC.md section 9.2).
    """
    return float(state.count_apples(move))


def strategy_min_apples(state: BoardState, move: Move) -> float:
    """Score a move by preferring the *fewest* apples cleared.

    The negation of :func:`strategy_max_apples`'s score, so "higher is
    better" still holds. Preserves optionality -- sometimes better for
    full-clear rate, at the cost of using more moves along the way (SPEC.md
    section 9.2).
    """
    return -strategy_max_apples(state, move)


#: Backs the unseeded :func:`strategy_random`. Deliberately a module-private
#: RNG rather than the global ``random`` module, so calling this strategy
#: never disturbs a caller's own random stream -- the same discipline
#: ``BoardState.generate_board`` observes.
_UNSEEDED_RNG = random.Random()


def strategy_random(state: BoardState, move: Move) -> float:
    """Score every move with an independent random float in ``[0, 1)``.

    Ignores both arguments entirely; ranking under this strategy produces a
    uniformly random order. A baseline for benchmarking -- a sanity floor
    other strategies should beat (SPEC.md section 9.2).
    """
    return _UNSEEDED_RNG.random()


def make_random_strategy(seed: int | None = None) -> StrategyFn:
    """Return a random :class:`StrategyFn` backed by a private, seeded RNG.

    Unlike the module-level :func:`strategy_random`, the returned closure is
    reproducible: two strategies built with the same ``seed`` score an
    identical sequence of moves identically (NFR5), useful for repeatable
    benchmarks and tests.

    The returned closure is **stateful** -- each call advances its RNG, so
    successive :func:`rank_moves` calls using the *same* returned strategy
    give different orderings each time (the right behavior for a benchmark
    playout, which wants fresh randomness per move). To reproduce a specific
    ranking, build a fresh strategy from the same seed rather than reusing
    one across calls.

    Args:
        seed: Seeds the private RNG (NFR5). If ``None``, the RNG is
            unseeded and the strategy behaves like :func:`strategy_random`
            but with its own independent random stream.
    """
    rng = random.Random(seed)

    def _strategy(state: BoardState, move: Move) -> float:
        return rng.random()

    return _strategy


#: The MVP default strategy (SPEC.md section 9.2).
DEFAULT_STRATEGY: StrategyFn = strategy_max_apples

#: Name -> strategy registry, so the CLI (FR19) and benchmark script (section
#: 9.2) can select a strategy by string without either growing its own
#: mapping (NFR1a).
STRATEGIES: dict[str, StrategyFn] = {
    "max_apples": strategy_max_apples,
    "min_apples": strategy_min_apples,
    "random": strategy_random,
}


def rank_moves(
    state: BoardState,
    moves: list[Move],
    strategy: StrategyFn = DEFAULT_STRATEGY,
    count: int | None = None,
) -> list[RankedMove]:
    """Rank ``moves`` on ``state`` using ``strategy``, best first (FR15).

    Scores every move via ``strategy``, wraps each in a :class:`RankedMove`
    (attaching the apples it would truly remove, via
    :meth:`BoardState.count_apples`), and sorts by score descending. Moves
    that tie on score keep their relative input order -- for moves taken
    straight from ``find_legal_moves``, whose output is itself deterministic,
    this makes ranking fully deterministic end-to-end (NFR5).

    Every move in ``moves`` is assumed to already be legal on ``state``, and
    is never re-validated here -- the same "assume well-formed on the hot
    path" posture ``BoardState.is_legal`` and ``find_legal_moves`` take.
    Neither ``state`` nor ``moves`` is mutated.

    Args:
        state: The board the moves apply to. Read-only.
        moves: Candidate moves, normally the output of ``find_legal_moves``.
            Not mutated or reordered in place.
        strategy: Scores one move against ``state``; higher is better.
            Defaults to :data:`DEFAULT_STRATEGY`.
        count: If given, return only the top ``count`` results. Every move
            is still scored -- a strategy is an opaque per-move function, so
            there is no way to know which moves rank highest without scoring
            all of them -- but truncating avoids fully sorting (and the
            caller discarding) results beyond what was asked for, most
            useful for the single-move hint path (FR13). ``None`` (the
            default) returns every move ranked. Must not be negative.

    Returns:
        ``RankedMove``s in best-first order, length ``min(count, len(moves))``
        when ``count`` is given, else ``len(moves)``.

    Raises:
        ValueError: If ``count`` is negative.
    """
    if count is not None and count < 0:
        raise ValueError(f"count must be non-negative, got {count}")

    ranked_moves = [
        RankedMove(
            move=move,
            score=strategy(state, move),
            apples_removed=state.count_apples(move)
        )
        for move in moves
    ]

    if count is None:
        return sorted(ranked_moves, key=lambda move: move.score, reverse=True)

    return heapq.nlargest(count, ranked_moves, key=lambda move: move.score)