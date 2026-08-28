"""Board state representation, move legality/application, and seeded generation.

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
from .moves import Move

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

    A board also owns the rules that relate it to a
    :class:`~fruitbox.engine.moves.Move`: :meth:`is_legal` decides whether a
    rectangle may be played (FR2) and :meth:`apply_move` plays one. Both live
    here rather than on ``Move`` because both need the board's dimensions and
    cell values; ``Move`` itself stays purely geometric.

    Note that ``BoardState`` intentionally does not retain the board's initial
    layout. Supporting "reset to initial state" (FR12) is a ``GameEngine``-layer
    concern -- it holds onto the seed or a pristine deep copy itself.
    """

    grid: Grid
    rows: int = GRID_ROWS
    cols: int = GRID_COLS
    min_value: int = MIN_CELL_VALUE
    max_value: int = MAX_CELL_VALUE

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
            min_value=self.min_value,
            max_value=self.max_value,
        )

    def is_legal(self, move: Move) -> bool:
        """Return whether ``move`` is legal on this board (SPEC.md FR2).

        A move is legal if and only if its rectangle lies entirely within the
        grid and the sum of the rectangle's current cell values is exactly
        ``TARGET_SUM``. Empty cells hold 0 and so contribute nothing -- spanning
        cleared cells is fine, and no separate occupancy check is needed.

        This board is assumed well-formed (``grid`` really is ``rows`` x
        ``cols``); validating that is :meth:`verify`'s job, not this hot path's.

        Args:
            move: The candidate rectangle. Not mutated, and neither is this
                board. ``Move``'s constructor already guarantees it is
                non-negative and correctly ordered, so only the grid's upper
                extent needs checking here.

        Returns:
            ``True`` if the move may be played on this board, else ``False``.
        """
        # Bounds first, and return early on failure: the sum below indexes into
        # the grid, so a rectangle running off the board must never reach it.
        if move.row_end >= self.rows or move.col_end >= self.cols:
            return False

        return sum(self.grid[row][col] for row, col in move.cells()) == TARGET_SUM

    def apply_move(self, move: Move) -> int:
        """Play ``move``: zero its still-occupied cells and report how many.

        Legality is checked here via :meth:`is_legal`, so nothing is mutated
        unless the move is legal -- a rejected move leaves the grid exactly as
        it was.

        Args:
            move: The rectangle to clear. Must be legal on this board.

        Returns:
            The number of cells that were **actually nonzero** before the move
            -- not the rectangle's area. A rectangle spanning already-cleared
            cells therefore reports only the apples it really removed.

        Raises:
            ValueError: If ``move`` is out of bounds or its cells do not sum to
                the target.
        """
        if not self.is_legal(move):
            raise ValueError(
                f"illegal move: rectangle rows {move.row_start}-{move.row_end}, "
                f"cols {move.col_start}-{move.col_end} is out of bounds or does "
                f"not sum to the target"
            )

        removed = 0
        for row, col in move.cells():
            if self.grid[row][col] != 0:
                removed += 1
                self.grid[row][col] = 0

        return removed

    def verify(self) -> None:
        """Assert this board's structural invariants hold.

        Checks that ``grid`` has exactly ``rows`` rows of exactly ``cols``
        columns each, and that every cell is either 0 (empty) or within
        ``[min_value, max_value]`` (occupied). Raises ``AssertionError`` with a
        descriptive message on the first violation found; returns ``None`` if
        every invariant holds. Intended for use in tests, e.g. ``state.verify()``.
        """
        assert len(self.grid) == self.rows, (
            f"expected {self.rows} rows, got {len(self.grid)}"
        )
        for r, row in enumerate(self.grid):
            assert len(row) == self.cols, (
                f"row {r}: expected {self.cols} columns, got {len(row)}"
            )
        for r, row in enumerate(self.grid):
            for c, value in enumerate(row):
                assert value == 0 or self.min_value <= value <= self.max_value, (
                    f"cell ({r}, {c}) holds {value}, expected 0 or a value in "
                    f"[{self.min_value}, {self.max_value}]"
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

    # Every ordered pair of in-range values whose sum lands on that residual.
    #
    # FR1 describes this step as "pick the second-to-last cell uniformly at
    # random, derive the last cell, and re-roll if the derived value falls
    # outside [min_value, max_value]". That rejection loop is unnecessary: the
    # full set of valid pairs is cheaply computable up front, so we draw
    # uniformly from *that* set directly and always succeed on the first try.
    #
    # The candidate set is never empty for any `needed` in [0, TARGET_SUM - 1],
    # given at least one occupied value in [min_value, max_value] -- which is
    # the same guarantee FR1 relies on to argue its retry loop terminates. For
    # the default 1-9 range: if `needed` is 0 all nine values of `a` work;
    # otherwise only `a == needed` is excluded (it would require a `last` of 0),
    # leaving eight.
    candidates = [
        (a, b)
        for a in range(min_value, max_value + 1)
        for b in range(min_value, max_value + 1)
        if (a + b) % TARGET_SUM == needed
    ]
    assert len(candidates) > 0, "Zero candidates for last 2 values."
    second_to_last, last = rng.choice(candidates)
    values.append(second_to_last)
    values.append(last)

    grid: Grid = [values[r * cols : (r + 1) * cols] for r in range(rows)]
    return BoardState(
        grid=grid,
        rows=rows,
        cols=cols,
        min_value=min_value,
        max_value=max_value,
    )
