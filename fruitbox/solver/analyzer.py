"""Orchestration layer: drives a board forward to report what happened (SPEC.md FR17, section 9.4).

``find_legal_moves`` (``move_scanner.py``) and ``rank_moves`` (``strategies.py``)
each answer a question about a single position. This module is the first to
*drive* a board forward through many positions: :func:`play_greedy` loops
enumerate -> rank -> apply until no legal move remains, and reports the
result as a :class:`ClearResult`.

:class:`ClearResult` is the shared result type for every solver entry point
that plays a line of moves to its end -- ``play_greedy`` here now, and later
``attempt_full_clear`` (FR16) and ``play_lookahead`` (FR18), which return the
same shape (SPEC.md section 9.4) so a caller's result-handling code never
needs to change when the underlying strategy does.

This module depends only on ``fruitbox.engine`` and its sibling ``solver``
modules, never on ``fruitbox.ui`` (SPEC.md section 7, NFR1a). Its only
efficiency metric is move count, never elapsed time (SPEC.md section 9).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.board import BoardState
from ..engine.moves import Move
from .move_scanner import find_legal_moves
from .strategies import DEFAULT_STRATEGY, StrategyFn, rank_moves


@dataclass(frozen=True)
class ClearResult:
    """The outcome of playing a line of moves to its end (SPEC.md section 9.4).

    Carries exactly two fields; everything else is derived, never stored, so
    a ``ClearResult`` can never disagree with itself:

    - fully cleared iff ``result.final_state.apples_remaining == 0``. A
      nonzero remainder means only "this line of play ended without clearing
      the board" -- for a bounded search (FR16) that means "budget exhausted
      without finding a full clear," **never** a proof that no full clear
      exists.
    - ``moves_used`` is ``len(result.moves)``.
    - ``apples_cleared`` is ``state.apples_remaining - result.final_state.apples_remaining``,
      where ``state`` is the caller's original, unmutated input board --
      every producer of a ``ClearResult`` plays out on a copy and never
      touches the board it was handed, which is what makes this derivation
      always valid.

    Frozen, but not *deeply* immutable: ``moves`` is a plain list and
    ``final_state`` is a mutable ``BoardState``. Treat a returned result as a
    read-only report -- mutating either field's contents is legal Python but
    defeats the point, and don't try to hash a ``ClearResult``: the list
    field and ``BoardState``'s own unhashability (it is an unfrozen,
    ``eq=True`` dataclass) both make ``hash()`` raise at runtime.
    """

    moves: list[Move]
    final_state: BoardState


def play_greedy(state: BoardState, strategy: StrategyFn = DEFAULT_STRATEGY) -> ClearResult:
    """Repeatedly play the top-ranked legal move until none remain (FR17).

    Runs entirely on an internal ``state.copy()`` -- the caller's ``state``
    is never mutated, which is what makes ``apples_cleared`` (see
    :class:`ClearResult`) derivable from it afterward. Each step asks
    :func:`~fruitbox.solver.move_scanner.find_legal_moves` for the legal
    moves on the current (copied) board, then :func:`~fruitbox.solver.strategies.rank_moves`
    with ``count=1`` for the single best move under ``strategy``, and applies
    it. Stops as soon as no legal move remains.

    No move-count safety cap is needed: a legal move's rectangle sums to
    exactly ``TARGET_SUM`` over non-negative cell values, so it always
    contains at least one occupied cell, and ``apply_move`` reports at least
    one apple removed. ``apples_remaining`` therefore strictly decreases
    every iteration, bounding the loop and guaranteeing termination.

    Args:
        state: The board to play out. Never mutated.
        strategy: Ranks each step's legal moves; the top-ranked move is
            played. Defaults to :data:`~fruitbox.solver.strategies.DEFAULT_STRATEGY`.
            Injecting a different ``StrategyFn`` here is how a benchmark
            script or CLI compares strategies through this one playout
            function rather than each reimplementing the loop (NFR1a, NFR7).

    Returns:
        A :class:`ClearResult` describing the line played and the board it
        led to.
    """
    working_state = state.copy()
    moves: list[Move] = []
    legal_moves = find_legal_moves(working_state)

    while len(legal_moves) > 0:
        best_move = rank_moves(working_state, legal_moves, strategy=strategy, count=1)[0].move
        working_state.apply_move(best_move)
        moves.append(best_move)

        legal_moves = find_legal_moves(working_state)

    return ClearResult(moves=moves, final_state=working_state)
