"""Pixel-drag to grid-rectangle translation (SPEC.md FR8, section 11).

The inverse of ``ui/renderer.py``'s geometry: where ``renderer.cell_rect(row,
col)`` maps a cell index forward to a pixel rectangle, :func:`cell_at` maps a
pixel position backward to a cell index, and :func:`selection_from_drag`
turns a drag's two endpoint pixels into a cell-snapped
:class:`~fruitbox.engine.moves.Move` (FR8's "snap to whole cells only").

Pure functions only -- no drag state, no pygame event handling, no
rendering, no engine mutation. Tracking "the mouse is currently down,
anchored here" belongs to later UI issues (``app.py``); applying the
returned ``Move`` to a board belongs to the engine. A ``Move`` returned here
is a *candidate* selection, not a validated legal move -- legality is
``BoardState.is_legal``'s call, not this module's.

Deliberately imports neither ``renderer`` nor pygame: the arithmetic here is
derived independently from ``fruitbox.config``'s geometry constants rather
than by importing ``renderer.cell_rect`` and inverting it, so this module
(and its tests) can run with pygame absent, matching SPEC.md section 10's
"no display required" spirit for input translation. Consistency between the
two directions is enforced by tests, not by a shared import.

``Move.__post_init__`` rejects inverted rectangles and negative coordinates
and explicitly assigns corner-ordering to "a UI drag, whose release corner
may be above/left of its anchor" -- that ordering is exactly
:func:`selection_from_drag`'s job, regardless of which of the two endpoints
the caller passes first.

Endpoint cells are inclusive on both ends and boundaries are half-open (a
pixel exactly on a cell's right/bottom edge belongs to the next cell,
matching ``renderer.cell_rect``'s tiling). A drag that never leaves one cell
still yields a legal-*shaped* 1x1 ``Move`` -- SPEC.md section 2 already
guarantees a 1x1 can never be legal via the sum check, so no special-casing
is needed here.

A drag whose two pixels are both outside the grid bounds on the same axis
(e.g. entirely within the HUD strip, or entirely off one edge) misses the
grid entirely and returns ``None``. Otherwise -- including a drag that
starts or ends outside the grid but overlaps it -- both corners are clamped
into ``[0, rows) x [0, cols)`` rather than rejected, since pygame reports
mouse positions outside the window (including negative ones) while a button
is held, and a drag that overshoots an edge should still select up to that
edge, not silently fail.
"""

from __future__ import annotations

from ..config import CELL_SIZE_PX, GRID_COLS, GRID_ORIGIN_X_PX, GRID_ORIGIN_Y_PX, GRID_ROWS
from ..engine.moves import Move


def cell_at(pos: tuple[float, float]) -> tuple[int, int]:
    """Return the ``(row, col)`` of the cell containing pixel ``pos``.

    Pure inverse of ``renderer.cell_rect``. Not bounds-checked against any
    grid size -- a pixel above/left of the grid origin yields a negative
    index, and one far past the last cell yields an index past ``rows``/
    ``cols``. Floor division, so the mapping is monotonic across the origin
    (an index of ``-1`` covers the pixel row/column immediately before 0,
    not a truncation-toward-zero jump straight to 0).

    ``pos`` may hold floats (e.g. a scaled display or touch input) -- each
    coordinate is truncated to an int before the floor division.

    Args:
        pos: An ``(x, y)`` pixel position, matching ``pygame.mouse.get_pos()``.

    Returns:
        The ``(row, col)`` of the cell that pixel falls within.
    """
    x, y = int(pos[0]), int(pos[1])
    row = (y - GRID_ORIGIN_Y_PX) // CELL_SIZE_PX
    col = (x - GRID_ORIGIN_X_PX) // CELL_SIZE_PX
    return row, col


def _clamp_cell(row: int, col: int, rows: int, cols: int) -> tuple[int, int]:
    """Clamp a (possibly out-of-range) cell index into ``[0, rows) x [0, cols)``."""
    return min(max(row, 0), rows - 1), min(max(col, 0), cols - 1)


def selection_from_drag(
    start: tuple[float, float],
    end: tuple[float, float],
    rows: int = GRID_ROWS,
    cols: int = GRID_COLS,
) -> Move | None:
    """Turn a drag's two endpoint pixels into a cell-snapped ``Move`` (FR8).

    Maps both pixels through :func:`cell_at`, orders each axis independently
    so the result is well-formed regardless of which corner the drag started
    from, and clamps into the ``rows`` x ``cols`` grid. Returns ``None`` only
    when the drag misses the grid entirely on some axis (e.g. wholly within
    the HUD strip) -- every other drag, including one that starts or ends
    outside the grid but overlaps it, is clamped and returned as a ``Move``.

    Args:
        start: The drag's anchor pixel (where the mouse button went down).
        end: The drag's current or release pixel.
        rows: Grid row count, for clamping. Defaults to the configured grid.
        cols: Grid column count, for clamping. Defaults to the configured grid.

    Returns:
        A ``Move`` spanning the two endpoint cells (order-independent,
        clamped into the grid), or ``None`` if the drag lies entirely
        outside the grid on some axis.
    """
    row_a, col_a = cell_at(start)
    row_b, col_b = cell_at(end)

    row_lo, row_hi = sorted((row_a, row_b))
    col_lo, col_hi = sorted((col_a, col_b))

    if row_hi < 0 or row_lo >= rows or col_hi < 0 or col_lo >= cols:
        return None

    row_start, col_start = _clamp_cell(row_lo, col_lo, rows, cols)
    row_end, col_end = _clamp_cell(row_hi, col_hi, rows, cols)

    return Move(row_start=row_start, col_start=col_start, row_end=row_end, col_end=col_end)
