"""Exhaustive legal-move enumeration (SPEC.md FR14, section 9.1).

``find_legal_moves`` answers "what rectangles can be played on this board
right now?" -- exhaustively and correctly. Every downstream solver capability
(ranking, lookahead, full-clear analysis) and the UI hint are built on top of
it, so both properties matter more than raw speed, though speed matters too
(NFR4).

Named ``move_scanner`` rather than ``enumerate`` (as SPEC.md section 7 first
suggested) to avoid shadowing Python's ``enumerate`` builtin inside this
module and the ``fruitbox.solver`` namespace.

This module depends only on ``fruitbox.engine`` and ``fruitbox.config``, never
on ``fruitbox.ui`` (SPEC.md section 7, NFR1a). It only ever *reads* the
``BoardState`` it is given -- it never mutates a board it does not own, the
same discipline ``BoardState``'s own docstring asks of all solver code.
"""

from __future__ import annotations

from ..config import TARGET_SUM
from ..engine.board import BoardState
from ..engine.moves import Move


def find_legal_moves(state: BoardState) -> list[Move]:
    """Return every legal move on ``state``, exhaustively.

    A rectangle is legal iff it lies within the grid and its current cell
    values (empty cells contributing 0, per SPEC.md section 2) sum to exactly
    ``TARGET_SUM`` -- the same rule ``BoardState.is_legal`` checks, but
    computed here via a 2D prefix-sum table (SPEC.md section 9.1) so every
    rectangle's sum is an O(1) lookup instead of an O(area) scan.

    Results are returned in a deterministic order, sorted by
    ``(row_start, col_start, row_end, col_end)``. Downstream code (ranking,
    playouts, benchmarks) may rely on this ordering for reproducibility
    (NFR5).

    This board is assumed well-formed, the same posture ``BoardState.is_legal``
    takes -- validating that is ``BoardState.verify()``'s job, not this
    hot path's.

    Args:
        state: The board to scan. Never mutated.

    Returns:
        Every legal ``Move``, in the order described above. Empty if the
        board has no legal moves, including when it is fully cleared.
    """
    if state.apples_remaining == 0:
        return []

    grid = state.grid
    rows = state.rows
    cols = state.cols
    prefix = _build_prefix_sums(state)

    moves: list[Move] = []
    for row_start in range(rows):
        for col_start in range(cols):
            # Running sum of the single column at col_start, over
            # row_start..row_end. It is a lower bound on every rectangle
            # sharing this row_start/col_start/row_end (every such rectangle
            # contains this column segment) and non-decreasing as row_end
            # grows, so once it exceeds TARGET_SUM no larger row_end -- at
            # any col_end -- can be legal either.
            col_sum = 0
            for row_end in range(row_start, rows):
                col_sum += grid[row_end][col_start]
                if col_sum > TARGET_SUM:
                    break

                for col_end in range(col_start, cols):
                    total = (
                        prefix[row_end + 1][col_end + 1]
                        - prefix[row_start][col_end + 1]
                        - prefix[row_end + 1][col_start]
                        + prefix[row_start][col_start]
                    )
                    if total > TARGET_SUM:
                        # Non-negative cell values mean this sum only grows
                        # as col_end extends, so no larger col_end can be
                        # legal either.
                        break
                    if total == TARGET_SUM:
                        moves.append(
                            Move(
                                row_start=row_start,
                                col_start=col_start,
                                row_end=row_end,
                                col_end=col_end,
                            )
                        )

    return moves


def _build_prefix_sums(state: BoardState) -> list[list[int]]:
    """Build a zero-padded 2D inclusive prefix-sum table over ``state.grid``.

    ``table[r][c]`` is the sum of every cell strictly above and left of
    ``(r, c)`` -- i.e. rows ``0..r-1`` and columns ``0..c-1`` of the grid. The
    table is one row and one column larger than the grid so that any
    rectangle's sum is the standard four-term inclusion-exclusion query with
    no boundary special-casing.
    """
    grid = state.grid
    rows = state.rows
    cols = state.cols

    table = [[0] * (cols + 1) for _ in range(rows + 1)]
    for r in range(rows):
        row_sum = 0
        for c in range(cols):
            row_sum += grid[r][c]
            table[r + 1][c + 1] = table[r][c + 1] + row_sum

    return table
