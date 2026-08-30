"""Drag state tracking and move application on release (SPEC.md FR10, section 11).

This module currently holds only two things: :class:`Drag`, the UI's only
stateful piece so far (everything in ``renderer.py``/``input.py`` before it
is stateless), and :func:`apply_selection`, the FR10 rule itself -- "on
release, apply the move if legal; discard with no state change if not." The
pygame main loop (``pygame.display``, the clock, the event pump) lands in a
later issue; this module composes with it rather than anticipating it.

Deliberately imports no pygame at this stage: :class:`Drag` takes bare
``(x, y)`` pixel positions, not ``pygame.event.Event`` objects, so this
module (and its tests) stay display-free, matching ``ui/input.py``'s own
no-pygame-import discipline. Removal is instant -- ``Renderer`` already
redraws from live board state each frame, so no rendering change or
animation is needed here (SPEC.md section 3 explicitly permits this).

:class:`Drag` holds only pixel state -- no :class:`~fruitbox.engine.game.GameEngine`
reference, no board. It defers all geometry to
:func:`~fruitbox.ui.input.selection_from_drag`, so drag tracking and board
mutation stay separable: a future "new game" (issue #18) can swap the engine
out from under a `Drag` object without either needing to know about the
other.
"""

from __future__ import annotations

from ..config import GRID_COLS, GRID_ROWS
from ..engine.game import GameEngine
from ..engine.moves import Move
from .input import selection_from_drag


def apply_selection(engine: GameEngine, move: Move | None) -> None:
    """Apply ``move`` to ``engine`` if legal; otherwise do nothing (FR10).

    Guards with ``engine.board.is_legal(move)`` rather than catching the
    ``ValueError`` ``GameEngine.apply_move`` raises on an illegal move, so
    "no state change on an illegal selection" is explicit here rather than
    an exception-handling side effect. An out-of-bounds ``move`` is also a
    no-op (``is_legal`` bounds-checks before summing), and ``move is None``
    -- the "drag missed the grid entirely" case from ``selection_from_drag``
    -- is a no-op too. Never raises, and never gates on
    ``engine.is_terminal()``: a terminal (fully cleared) board admits no
    legal move, so the legality check alone already makes this a no-op
    there.

    Returns nothing: the caller learns whether ``move`` was applied by
    reading ``engine``'s state (e.g. ``engine.board.apples_remaining`` or
    ``engine.score`` before and after), not from a return value. This is a
    deliberate choice, not an oversight -- do not add a return value back in
    without re-checking this docstring's reasoning.

    Args:
        engine: The game to apply the move to.
        move: The candidate rectangle, or ``None``.
    """
    if move is None:
        return
    if not engine.board.is_legal(move):
        return
    engine.apply_move(move)


class Drag:
    """Tracks an in-progress mouse drag in pixel space (SPEC.md FR8/FR9).

    Holds only pixel positions -- no engine, no board, no pygame objects --
    so it stays entirely decoupled from what the drag will eventually be
    applied to. :attr:`selection` derives the current candidate rectangle
    by delegating to :func:`~fruitbox.ui.input.selection_from_drag`, which
    already owns corner normalization, clamping, and the "misses the grid
    entirely" case; this class adds nothing but memory of the anchor.
    """

    def __init__(self, rows: int = GRID_ROWS, cols: int = GRID_COLS) -> None:
        """Start idle, tracking a ``rows`` x ``cols`` grid for clamping.

        Args:
            rows: Grid row count, forwarded to ``selection_from_drag``.
            cols: Grid column count, forwarded to ``selection_from_drag``.
        """
        self._rows = rows
        self._cols = cols
        self._start: tuple[float, float] | None = None
        self._current: tuple[float, float] | None = None

    @property
    def is_dragging(self) -> bool:
        """Whether a drag is currently in progress (a button-down is outstanding)."""
        return self._start is not None and self._current is not None

    @property
    def selection(self) -> Move | None:
        """The current candidate rectangle, or ``None`` if idle or off-grid.

        Recomputed on every read from the current anchor/position -- cheap,
        and never goes stale.
        """
        if not self.is_dragging:
            return None
        return selection_from_drag(self._start, self._current, self._rows, self._cols)

    def begin(self, pos: tuple[float, float]) -> None:
        """Start a drag anchored at ``pos`` (mouse-down).

        A click with no subsequent motion already yields a 1x1
        :attr:`selection`, since ``_current`` starts equal to the anchor.
        Calling this while already dragging re-anchors at the new position
        -- the most recent press wins.
        """
        self._start = pos
        self._current = pos

    def update(self, pos: tuple[float, float]) -> None:
        """Move the drag's far corner to ``pos`` (mouse-motion).

        A no-op if no drag is in progress, so stray motion events between
        drags are harmless.
        """
        if self._start is None:
            return
        self._current = pos

    def release(self, pos: tuple[float, float]) -> Move | None:
        """End the drag at ``pos`` (mouse-up) and return its final candidate.

        Returns **every** candidate rectangle regardless of legality --
        this class never consults a board, so legality is entirely
        :func:`apply_selection`'s call. Returns ``None`` if no drag was in
        progress, or if the drag misses the grid entirely.
        """
        self.update(pos)
        result = self.selection
        self.cancel()
        return result

    def cancel(self) -> None:
        """Abandon the current drag with no result. Idempotent."""
        self._start = None
        self._current = None
