"""The playable game: applying moves, scoring, state reporting, and reset.

:class:`GameEngine` is the layer that wraps a :class:`~fruitbox.engine.board.BoardState`
with the score a played game needs (SPEC.md FR3-FR6); the apple count is the board's
own business. Like the rest of ``fruitbox.engine`` it is pure Python: no pygame, and
no imports from ``fruitbox.solver`` or ``fruitbox.ui`` (SPEC.md section 7).

The rules relating a :class:`~fruitbox.engine.moves.Move` to a board live on
``BoardState`` itself; this module re-exposes the legality rule as the free
function :func:`is_legal_move` for callers that prefer that shape.

The engine -- not ``BoardState`` -- owns "reset to initial state" (FR12). Because
``grid`` is mutated destructively as moves are applied, ``BoardState`` cannot
recover its own starting layout; the engine therefore keeps a pristine private
snapshot taken once at construction (SPEC.md section 8).
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import BoardState, Grid
from .moves import Move


def is_legal_move(state: BoardState, move: Move) -> bool:
    """Return whether ``move`` is legal on ``state`` (SPEC.md FR2).

    A thin wrapper over :meth:`BoardState.is_legal`, which holds the actual
    rule (in-bounds, and cell values summing to the target). It is kept as a
    free function so callers holding a state and a candidate move -- a future
    hint or solver caller enumerating possibilities, say -- can check legality
    without reaching through the state object.

    Args:
        state: The board to test the move against. Not mutated.
        move: The candidate rectangle.

    Returns:
        ``True`` if the move may be played on ``state``, else ``False``.
    """
    return state.is_legal(move)


@dataclass(frozen=True)
class GameState:
    """A snapshot of what the engine currently reports (SPEC.md FR4).

    ``board`` is the engine's **live** ``BoardState``, not a defensive copy:
    reading ``state.board.grid`` after a subsequent :meth:`GameEngine.apply_move`
    will show the updated grid. It is read-only *by convention*, consistent with
    the rest of the project, which likewise hands out ``BoardState.grid``
    directly rather than copying on every access -- callers that want an
    independent board to mutate should call ``state.board.copy()``.

    ``score`` is a plain int and so is a genuine point-in-time value, unaffected
    by later moves. The apple count is deliberately *not* duplicated here: it
    lives on the board as ``state.board.apples_remaining``, which -- like
    ``board.grid`` -- reads through to the live board.
    """

    board: BoardState
    score: int


class GameEngine:
    """Plays moves against a board, tracking the score.

    The apple count is not an engine-level counter: ``BoardState`` maintains its
    own ``apples_remaining`` as moves are applied, and this layer simply reads
    ``self.board.apples_remaining`` when it needs one.

    The engine mutates its ``board`` in place (via :meth:`apply_move`) rather
    than producing new states, keeping the hot path allocation-free for the UI
    render loop. Solver code that wants to explore hypothetical futures should
    branch on a ``BoardState.copy()`` rather than driving an engine.
    """

    def __init__(self, state: BoardState) -> None:
        """Wrap ``state`` in a fresh game at score 0.

        Args:
            state: The board to play on. The engine takes ownership: it mutates
                this exact object in place, so callers must not keep playing
                with it independently. A pristine copy is taken here to back
                :meth:`reset`.
        """
        self.board = state
        self.score = 0

        # A private, never-mutated snapshot of the starting layout. BoardState
        # deliberately does not retain its own initial grid, so retaining one is
        # this layer's job (SPEC.md section 8). The starting apple count rides
        # along on the snapshot, since copy() carries `apples_remaining` over --
        # so reset() need not rescan either.
        self._initial_state: BoardState = state.copy()

    @classmethod
    def load(cls, grid: Grid) -> "GameEngine":
        """Build an engine from a fixed layout (SPEC.md FR6).

        Dimensions are inferred from ``grid`` itself, so hand-authored test
        boards need not restate them.

        Args:
            grid: Rows of cell values, 0 for empty and ``min_value``-``max_value``
                for occupied. Taken by reference and mutated in place as moves
                are applied.

        Returns:
            A ``GameEngine`` at score 0 playing on the given layout.

        Raises:
            AssertionError: If ``grid`` is ragged or holds an out-of-range
                value; propagated from :meth:`BoardState.verify`, so a
                malformed fixture surfaces at load time rather than as strange
                behaviour several moves later.
        """
        rows = len(grid)
        cols = len(grid[0]) if grid else 0
        state = BoardState(grid=grid, rows=rows, cols=cols)
        state.verify()
        return cls(state)

    def apply_move(self, move: Move) -> None:
        """Play ``move``, clearing its cells and scoring them (SPEC.md FR3).

        The legality check, the clearing itself, and the board's own apple
        count all belong to :meth:`BoardState.apply_move`; this layer only keeps
        the score in step with the removals it reports. The score increases by
        the number of cells that were **actually nonzero** before the move --
        not by the rectangle's area -- so a rectangle that spans already-cleared
        cells scores only the apples it really removed.

        Nothing is mutated unless the move is legal; a rejected move leaves the
        grid, score, and apple count exactly as they were, since the board
        raises before touching a cell and the score is only updated after it
        returns.

        Args:
            move: The rectangle to clear. Must be legal on the current board.

        Raises:
            ValueError: If ``move`` is out of bounds or its cells do not sum to
                the target. Propagated from :meth:`BoardState.apply_move`.
        """
        removed = self.board.apply_move(move)

        self.score += removed

    def get_state(self) -> GameState:
        """Report the current board and score (SPEC.md FR4).

        The apple count is reached through the reported board, as
        ``get_state().board.apples_remaining`` -- the counter ``BoardState``
        maintains incrementally, not a fresh scan of the grid.
        """
        return GameState(board=self.board, score=self.score)

    def is_terminal(self) -> bool:
        """Return whether the board has been fully cleared.

        **Deliberate simplification of SPEC.md FR5.** FR5's literal wording
        defines terminal as "no legal moves remain, regardless of whether
        nonzero cells remain", which would require scanning for move
        availability. By explicit product decision for the MVP, this engine
        instead treats terminal as simply "the board is empty"
        (``board.apples_remaining == 0``). This is the intended final behaviour
        for this method, not a placeholder for a legal-move scan: a board with
        apples left but no playable rectangle is *not* reported as terminal
        here.
        """
        return self.board.apples_remaining == 0

    def reset(self) -> None:
        """Restore the board to its starting layout and zero the score (FR12).

        The grid contents are restored onto the *same* ``BoardState`` object, so
        any reference already held to ``engine.board`` (or to a previously
        returned ``GameState.board``) stays valid and sees the reset board. The
        row lists are freshly copied out of the private snapshot, which is never
        handed out and never mutated -- so ``reset`` may be called any number of
        times and always reproduces the identical starting board.

        The board's own ``apples_remaining`` is restored from the snapshot too:
        it is maintained incrementally, so restoring the grid alone would leave
        it stale.
        """
        self.board.grid = [row[:] for row in self._initial_state.grid]
        self.board.apples_remaining = self._initial_state.apples_remaining
        self.score = 0
