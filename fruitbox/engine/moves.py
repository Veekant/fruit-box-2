"""Move representation.

A move is an axis-aligned rectangle of grid cells (SPEC.md section 2, section 8).
Like :mod:`fruitbox.engine.board`, this module is pure Python with no pygame,
solver, or UI dependency -- and, deliberately, no dependency on anything else in
this project either. A ``Move`` is purely geometric: it knows nothing about any
particular board.

Legality (FR2) therefore lives elsewhere: it is implemented by
:meth:`fruitbox.engine.board.BoardState.is_legal`, which owns the rule outright.
Keeping legality out of this module is what lets ``board`` import ``Move``
without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Move:
    """An axis-aligned rectangle of cells, with both endpoints **inclusive**.

    Degenerate shapes are valid ``Move`` shapes: a 1x1 single cell and 1xN / Nx1
    lines all construct fine. A 1x1 move can never be *legal*, since a single
    cell holds either 0 or 1-9 and so never sums to 10 -- but that falls out of
    the sum check in :meth:`~fruitbox.engine.board.BoardState.is_legal` rather
    than being special-cased here (SPEC.md section 2).

    A ``Move`` must be well-formed at construction: endpoints in order
    (``row_start <= row_end``, ``col_start <= col_end``) and no negative
    coordinates. Violating either raises ``ValueError`` rather than being
    silently repaired, so a malformed rectangle surfaces at the point it was
    built instead of turning into a mystery ``False`` from a legality check
    further downstream. Callers that work in unordered corners -- notably a UI
    drag, whose release corner may be above/left of its anchor -- are
    responsible for ordering the two corners before constructing the ``Move``.
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
