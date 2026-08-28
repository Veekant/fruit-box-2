"""Move representation and move legality checking.

A move is an axis-aligned rectangle of grid cells (SPEC.md section 2, section 8).
Like :mod:`fruitbox.engine.board`, this module is pure Python with no pygame,
solver, or UI dependency.

Legality (FR2) is deliberately just two checks: the rectangle must lie inside the
grid, and the sum of the cells' **current** values must equal ``TARGET_SUM``.
There is no separate occupancy check, because empty cells hold 0 and so
contribute nothing to the sum -- a rectangle may freely span already-cleared
cells alongside occupied ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..config import TARGET_SUM
from .board import BoardState


@dataclass(frozen=True)
class Move:
    """An axis-aligned rectangle of cells, with both endpoints **inclusive**.

    Degenerate shapes are valid ``Move`` shapes: a 1x1 single cell and 1xN / Nx1
    lines all construct fine. A 1x1 move can never be *legal*, since a single
    cell holds either 0 or 1-9 and so never sums to 10 -- but that falls out of
    the sum check in :func:`is_legal_move` rather than being special-cased here
    (SPEC.md section 2).

    A ``Move`` must be well-formed at construction: endpoints in order
    (``row_start <= row_end``, ``col_start <= col_end``) and no negative
    coordinates. Violating either raises ``ValueError`` rather than being
    silently repaired, so a malformed rectangle surfaces at the point it was
    built instead of turning into a mystery ``False`` from
    :func:`is_legal_move` further downstream. Callers that work in unordered
    corners -- notably a UI drag, whose release corner may be above/left of its
    anchor -- are responsible for ordering the two corners before constructing
    the ``Move``.
    """

    row_start: int
    col_start: int
    row_end: int  # inclusive
    col_end: int  # inclusive

    def __post_init__(self) -> None:
        """Reject inverted rectangles and negative coordinates.

        Raises:
            ValueError: If either axis has its endpoints reversed, or any
                coordinate is negative.
        """
        if self.row_start > self.row_end:
            raise ValueError(
                f"inverted rectangle: row_start ({self.row_start}) > row_end "
                f"({self.row_end})"
            )
        if self.col_start > self.col_end:
            raise ValueError(
                f"inverted rectangle: col_start ({self.col_start}) > col_end "
                f"({self.col_end})"
            )
        # Only the low corner needs testing: the ordering checks above already
        # put the high corner at or above it on each axis.
        if self.row_start < 0 or self.col_start < 0:
            raise ValueError(
                f"negative coordinate: ({self.row_start}, {self.col_start})"
            )

    def cells(self) -> Iterator[tuple[int, int]]:
        """Yield every ``(row, col)`` in the rectangle, in row-major order.

        Because construction rejects inverted rectangles, this always yields at
        least one cell -- never an empty iterator. Coordinates are not
        bounds-checked against any board here; ``Move`` knows nothing about a
        particular :class:`~fruitbox.engine.board.BoardState`.
        """
        for row in range(self.row_start, self.row_end + 1):
            for col in range(self.col_start, self.col_end + 1):
                yield (row, col)


def is_legal_move(state: BoardState, move: Move) -> bool:
    """Return whether ``move`` is legal on ``state`` (SPEC.md FR2).

    A move is legal if and only if its rectangle lies entirely within the grid
    and the sum of the rectangle's current cell values is exactly ``TARGET_SUM``.
    Empty cells hold 0 and so contribute nothing -- spanning cleared cells is
    fine, and no separate occupancy check is needed.

    ``state`` is assumed well-formed (``grid`` really is ``rows`` x ``cols``);
    validating that is :meth:`BoardState.verify`'s job, not this hot path's.

    Args:
        state: The board to test the move against. Not mutated.
        move: The candidate rectangle. Guaranteed by ``Move``'s constructor to
            be non-negative and correctly ordered, so only the grid's upper
            extent needs checking here.

    Returns:
        ``True`` if the move may be played on ``state``, else ``False``.
    """
    # Bounds first, and return early on failure: the sum below indexes into the
    # grid, so a rectangle running off the board must never reach it.
    if move.row_end >= state.rows or move.col_end >= state.cols:
        return False

    return sum(state.grid[row][col] for row, col in move.cells()) == TARGET_SUM
