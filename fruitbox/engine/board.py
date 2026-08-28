"""Board state representation and seeded board generation.

This module is pure Python with no pygame (or solver, or UI) dependency: it sits
at the bottom of the dependency graph described in SPEC.md section 7.

The single source of truth for the board is :class:`BoardState.grid`. There is
deliberately **no separate occupancy mask** (SPEC.md section 2, section 8): a cell
holding 0 is empty (removed, or never occupied) and a cell holding 1-9 is
occupied at that value. Rectangle sums therefore work directly over the current
grid values, with empty cells contributing 0 for free.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..config import GRID_COLS, GRID_ROWS, MAX_CELL_VALUE, MIN_CELL_VALUE, TARGET_SUM

#: ``grid[row][col]`` is the cell's current value; 0 means empty (never occupied,
#: or already removed), 1-9 means occupied at that value.
Grid = list[list[int]]


@dataclass
class BoardState:
    """The mutable state of a board.

    ``grid`` is mutated **in place** as moves are applied (removed cells are set
    to 0) rather than replaced with a new object, keeping the hot path -- the UI
    render loop and greedy solver playouts -- allocation-free (SPEC.md section 8).

    The discipline this mutability requires: solver code must **never** mutate a
    ``BoardState`` it does not own. Before exploring a hypothetical move during
    lookahead or search, call :meth:`copy` and mutate the copy instead.

    Note that ``BoardState`` intentionally does not retain the board's initial
    layout. Supporting "reset to initial state" (FR12) is a ``GameEngine``-layer
    concern -- it holds onto the seed or a pristine deep copy itself.
    """

    grid: Grid
    rows: int
    cols: int

    def copy(self) -> "BoardState":
        """Return an independent ``BoardState`` with its own grid.

        The row lists are deep-copied, so mutating the returned board's grid
        (e.g. applying a hypothetical move during search/lookahead) never
        disturbs this one. ``grid`` holds plain ints, so copying the row lists
        is a full deep copy -- no nested structure needs recursing into.
        """
        return BoardState(
            grid=[row[:] for row in self.grid],
            rows=self.rows,
            cols=self.cols,
        )


def generate_board(
    rows: int = GRID_ROWS,
    cols: int = GRID_COLS,
    seed: int | None = None,
    min_value: int = MIN_CELL_VALUE,
    max_value: int = MAX_CELL_VALUE,
) -> BoardState:
    """Generate a random board whose total sum is a multiple of ``TARGET_SUM``.

    Implements the two-cell-adjustment algorithm of SPEC.md FR1: all but the
    final two cells are drawn uniformly at random from ``[min_value, max_value]``,
    then the last two cells (the last two positions in row-major order, i.e. the
    bottom-right corner of the final row) are chosen so the grand total is
    congruent to 0 mod ``TARGET_SUM``. That congruence is a necessary
    precondition for the board to be fully clearable at all, since every legal
    move removes a subset summing to exactly ``TARGET_SUM``. It is *only* a
    necessary condition -- generation does no board-quality filtering and makes
    no solvability guarantee.

    Args:
        rows: Number of grid rows.
        cols: Number of grid columns. ``rows * cols`` must be at least 2, since
            the algorithm reserves two cells for the sum adjustment.
        seed: If given, seeds a local RNG so the board is reproducible (NFR5).
            If ``None``, an unseeded local RNG is used. Either way the
            module-level :mod:`random` state is left untouched, so callers'
            global randomness is never disturbed by generating a board.
        min_value: Smallest value an occupied cell may hold.
        max_value: Largest value an occupied cell may hold.

    Returns:
        A freshly generated :class:`BoardState`; every cell is occupied
        (nonzero) and the total sum is a multiple of ``TARGET_SUM``.
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    # All cells but the final two, drawn uniformly at random, in row-major order.
    values = [rng.randint(min_value, max_value) for _ in range(rows * cols - 2)]
    running_sum = sum(values)

    # The residual the last two cells must contribute for the total to be 0 mod
    # TARGET_SUM.
    needed = (-running_sum) % TARGET_SUM

    second_to_last, last = _pick_adjustment_pair(rng, needed, min_value, max_value)
    values.append(second_to_last)
    values.append(last)

    grid: Grid = [values[r * cols : (r + 1) * cols] for r in range(rows)]
    return BoardState(grid=grid, rows=rows, cols=cols)


def _pick_adjustment_pair(
    rng: random.Random,
    needed: int,
    min_value: int,
    max_value: int,
) -> tuple[int, int]:
    """Pick the final two cell values, summing to ``needed`` mod ``TARGET_SUM``.

    FR1 describes this as "pick the second-to-last cell uniformly at random,
    derive the last cell, and re-roll if the derived value falls outside
    ``[min_value, max_value]``". That rejection loop is unnecessary: the set of
    second-to-last values admitting a valid partner is cheaply computable up
    front, so we draw uniformly from *that* set directly and always succeed on
    the first try. This is distributionally identical to re-rolling until a
    valid pair appears (rejection sampling over a uniform draw yields a uniform
    draw over the accepted values), just without the loop.

    Concretely, for the default 1-9 range: if ``needed`` is 0 all nine values of
    ``second_to_last`` work; otherwise the single choice ``second_to_last ==
    needed`` is rejected because it would require a ``last`` of 0, leaving eight.
    The candidate set is therefore never empty, which is the same guarantee FR1
    relies on to argue its retry loop converges.
    """
    candidates = [
        (a, b)
        for a in range(min_value, max_value + 1)
        for b in range(min_value, max_value + 1)
        if (a + b) % TARGET_SUM == needed
    ]

    # Draw the second-to-last cell uniformly over the values that admit a
    # partner, then its partner uniformly among the values that pair with it.
    # (For a value range narrower than TARGET_SUM -- the 1-9 default -- each
    # `a` has exactly one partner, so this is just a uniform draw over `a`.)
    valid_seconds = sorted({a for a, _ in candidates})
    second_to_last = rng.choice(valid_seconds)
    last = rng.choice([b for a, b in candidates if a == second_to_last])
    return second_to_last, last
