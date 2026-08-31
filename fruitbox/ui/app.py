"""Drag state, move application, timer, session, and the main loop (SPEC.md FR8-FR12, section 11).

This module holds :class:`Drag` (FR8/FR9's in-progress drag state),
:func:`apply_selection` (FR10's "apply on release if legal" rule),
:class:`Timer` (FR11's countdown), :class:`Session` (FR11/FR12's
game-over/reset/new-game rules, which need both an engine and a timer), and
now :func:`run` -- the pygame main loop that drives all of the above.

:class:`Drag` and :class:`Timer` still touch no pygame in their own
interfaces: :class:`Drag` takes bare ``(x, y)`` pixel positions rather than
``pygame.event.Event`` objects, and :class:`Timer` takes bare millisecond
tick integers rather than reading any clock itself. :func:`run` is the one
place those bare values come from real pygame events and
``pygame.time.get_ticks()``, read once per frame. Removal is instant --
``Renderer`` already redraws from live board state each frame, so no
rendering change or animation is needed here (SPEC.md section 3 explicitly
permits this).

:class:`Drag` holds only pixel state -- no :class:`~fruitbox.engine.game.GameEngine`
reference, no board. It defers all geometry to
:func:`~fruitbox.ui.input.selection_from_drag`, so drag tracking and board
mutation stay separable: :meth:`Session.new_game` can swap the engine out
from under a `Drag` object without either needing to know about the other.

:class:`Timer` is pure tick arithmetic with zero dependencies: it stores the
tick value it started at and the tick value it was last told about via
:meth:`Timer.update`, and computes elapsed/remaining/expired from the
difference. This keeps ``Timer`` directly testable with plain integers,
with no clock stub needed.

:func:`run` is deliberately written as one function with a plain
``if``/``elif`` event dispatch inline in its loop body -- there is no
``Intent`` abstraction, no event-translation layer, and no ``App`` class.
Each pygame event is handled exactly once, at the one place it matters, and
the ordering within the ``if``/``elif`` chain is what encodes the rules
(e.g. quit/restart/new-game stay live even after the game is over; mouse
input does not). See :func:`run`'s own docstring for the exact ordering
rationale.

Key bindings (:data:`RESTART_KEY`, :data:`NEW_GAME_KEY`) are plain
``pygame.K_*`` constants declared directly here, matched against
``event.key``. They are independently declared from
``config.RESTART_KEY_LABEL``/``NEW_GAME_KEY_LABEL`` (which drive the
on-screen prompt text in ``ui/renderer.py``) rather than derived from them
at runtime -- ``config.py`` must stay pygame-free, so it cannot hold a
``pygame.K_*`` constant itself, and deriving one from a string at import
time would touch pygame key-name lookup before ``pygame.init()`` has run.
Keeping the label and the binding in agreement is therefore a manual
discipline: if one changes, the other must be updated too.
"""

from __future__ import annotations

import argparse

import pygame

from ..config import GRID_COLS, GRID_ROWS, TARGET_FPS, TIMER_SECONDS
from ..engine.board import BoardState
from ..engine.game import GameEngine
from ..engine.moves import Move
from .input import selection_from_drag
from .renderer import Renderer, window_size

#: The pygame window's caption. A single-consumer presentational string, so
#: it lives here rather than in config.py, matching renderer.py's ownership
#: of GAME_OVER_TITLE.
WINDOW_TITLE = "Fruit Box"

#: Bound to config.RESTART_KEY_LABEL ("R") -- see this module's docstring
#: for why the two are declared independently rather than derived from one
#: another.
RESTART_KEY = pygame.K_r

#: Bound to config.NEW_GAME_KEY_LABEL ("N") -- see RESTART_KEY.
NEW_GAME_KEY = pygame.K_n

#: The one place the milliseconds-per-second conversion is named. A unit
#: conversion, not a tunable, so it lives here rather than in config.py.
_MS_PER_SECOND = 1000


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


class Timer:
    """A countdown driven by externally supplied millisecond tick values (SPEC.md FR11).

    Reads no clock itself. The caller pushes tick values in via
    :meth:`update`; in the eventual main loop (issue #19) that value will be
    ``pygame.time.get_ticks()``, read once per frame. This keeps ``Timer``
    (and this module) free of any ``time``/pygame import, and makes it
    directly testable with plain integers instead of a fake-clock object.

    Elapsed time (:attr:`duration`) is measured in **milliseconds**, matching
    the tick values it is fed. :attr:`remaining` and the constructor's
    ``end_time`` are in **seconds**, matching ``Renderer.draw_hud`` /
    ``format_hud``'s ``seconds_remaining`` parameter -- this class is the
    only place the millisecond/second unit conversion happens.
    """

    def __init__(self, start_ticks: int, end_time: float = TIMER_SECONDS) -> None:
        """Start counting from ``start_ticks``, expiring after ``end_time`` seconds.

        Args:
            start_ticks: The tick value "now" -- typically the caller's
                current ``pygame.time.get_ticks()`` reading at construction
                time. Required rather than defaulted, so a construction site
                can never silently start the clock from the wrong epoch.
            end_time: Seconds until expiry. Defaults to
                ``config.TIMER_SECONDS``.
        """
        self._start_ticks = start_ticks
        self._current_ticks = start_ticks
        self._end_time = end_time
        self._stopped = False

    @property
    def duration(self) -> int:
        """Elapsed milliseconds since ``start_ticks`` (or the last :meth:`restart`).

        Named ``duration`` per this class's design, even though it reports
        *elapsed* time rather than the configured target -- the target lives
        in the constructor's ``end_time``, never exposed under this name.
        """
        return self._current_ticks - self._start_ticks

    @property
    def remaining(self) -> float:
        """Seconds remaining until expiry. Goes negative past expiry -- never
        clamped here; ``format_hud`` already clamps for display.
        """
        return self._end_time - self.duration / _MS_PER_SECOND

    @property
    def expired(self) -> bool:
        """Whether elapsed time has gone **strictly past** ``end_time``.

        At exactly ``end_time`` (``remaining == 0.0``) the timer is *not yet*
        expired; expiry begins at the first tick past it -- at most 1ms late
        on a millisecond clock. Implemented via :attr:`remaining` so the two
        accessors can never disagree.
        """
        return self.remaining < 0

    @property
    def stopped(self) -> bool:
        """Whether the timer is currently frozen (see :meth:`stop`)."""
        return self._stopped

    def update(self, ticks: int) -> None:
        """Advance to ``ticks``. A no-op while :attr:`stopped`.

        Does not guard against a ``ticks`` value earlier than the last one --
        a backwards tick simply yields a smaller (or negative) elapsed time.
        The caller's clock (``pygame.time.get_ticks()``) is assumed
        monotonic; this is documented, not defended against.
        """
        if self._stopped:
            return
        self._current_ticks = ticks

    def stop(self) -> None:
        """Freeze the timer: further :meth:`update` calls are no-ops until :meth:`restart`.

        Idempotent.
        """
        self._stopped = True

    def restart(self, ticks: int) -> None:
        """Reset elapsed time to zero, counting from ``ticks``, and un-freeze.

        Un-freezes by design: a restarted game must tick again, and a
        separate "resume" step would be a footgun with no benefit.

        Args:
            ticks: The tick value "now". Required, not defaulted -- a
                restart happens mid-run, where defaulting to 0 would corrupt
                elapsed-time math (the next :meth:`update` would report a
                huge, wrong elapsed time).
        """
        self._start_ticks = ticks
        self._current_ticks = ticks
        self._stopped = False


class Session:
    """Owns an engine and a timer together, implementing FR11/FR12's combined rules.

    The single per-frame entry point a future main loop needs:
    :meth:`update` advances the timer and freezes it the moment the game
    ends, so elapsed time on a game-over screen stops growing once the game
    is actually over.
    """

    def __init__(self, engine: GameEngine, timer: Timer) -> None:
        """Wrap ``engine`` with ``timer``.

        Args:
            engine: The game to play. ``Session`` reads and replaces this
                attribute directly (see :meth:`new_game`) -- callers should
                read ``session.engine``, not hold a separate reference.
            timer: The countdown to pair with it. Required rather than
                defaulted, so a construction site can never silently start
                the countdown from the wrong epoch -- the same reasoning
                ``Timer.__init__``'s ``start_ticks`` docstring gives.
        """
        self.engine = engine
        self.timer = timer

    @property
    def is_over(self) -> bool:
        """Whether the game has ended: the timer expired, or the board is fully cleared (FR11).

        ``GameEngine.is_terminal()`` is deliberately "board fully cleared,"
        not "no legal moves remain" (see its own docstring) -- a player
        stuck with apples left but no legal rectangle is *not* reported as
        over here and must wait out the timer, by design.
        """
        return self.timer.expired or self.engine.is_terminal()

    def update(self, ticks: int) -> None:
        """Advance the timer to ``ticks``, then freeze it if the game just ended.

        Recording the crossing tick before freezing means elapsed time is
        exact up to the instant the game ended, not the previous frame's
        value.
        """
        self.timer.update(ticks)
        if self.is_over:
            self.timer.stop()

    def summary(self) -> tuple[int, float]:
        """Return ``(score, elapsed_seconds)`` for a game-over screen."""
        return self.engine.score, self.timer.duration / _MS_PER_SECOND

    def reset(self, ticks: int) -> None:
        """Replay the current board from its initial layout, restarting the timer (FR12).

        ``GameEngine.reset()`` rebinds ``engine.board`` to a fresh object, so
        callers must read ``session.engine.board`` afterward rather than a
        cached reference.

        Args:
            ticks: The tick value "now", forwarded to ``Timer.restart``.
        """
        self.engine.reset()
        self.timer.restart(ticks)

    def new_game(self, ticks: int, seed: int | None = None) -> None:
        """Replace the board with a freshly generated one, restarting the timer (FR12).

        The new board carries over the current board's dimensions and value
        range. Replaces ``self.engine`` wholesale -- callers must read
        ``session.engine``, not hold a separate reference.

        Args:
            ticks: The tick value "now", forwarded to ``Timer.restart``.
            seed: Forwarded to ``BoardState.generate_board`` for reproducible
                boards (NFR5). ``None`` (the default) generates an unseeded
                random board.
        """
        old_board = self.engine.board
        new_board = BoardState.generate_board(
            rows=old_board.rows,
            cols=old_board.cols,
            seed=seed,
            min_value=old_board.min_value,
            max_value=old_board.max_value,
        )
        self.engine = GameEngine(new_board)
        self.timer.restart(ticks)


def run(seed: int | None, seconds: float) -> None:
    """Open a window and run the game until it's closed (SPEC.md FR8-FR12).

    Owns the whole pygame lifecycle: init, window/clock/renderer setup, the
    event pump, and teardown. Every event is handled inline in the loop
    below via a plain ``if``/``elif`` chain -- there is deliberately no
    separate event-translation or intent-dispatch layer; each pygame event
    is converted straight into the one call it means (``drag.begin``,
    ``session.reset``, etc.) at the single place that matters.

    Ordering within the ``if``/``elif`` chain is load-bearing:
    ``pygame.QUIT`` and the restart/new-game keys are checked first and stay
    live at all times, including once the game is over (FR12) -- pressing R
    or N is the only way to leave the game-over screen. The
    ``elif session.is_over: continue`` branch comes next, so every mouse
    branch after it is skipped once the game has ended; that single
    placement is enough to gate all three mouse intents without repeating
    the check in each one.

    Args:
        seed: Seeds the starting board (NFR5), or ``None`` for an unseeded
            board. Not required -- callers (currently just :func:`main`)
            decide the default; ``run`` itself doesn't have one.
        seconds: Countdown length in seconds, forwarded to ``Timer``. Also
            not defaulted here -- the one place a default lives is
            :func:`_build_parser`'s ``--time`` argument.
    """
    pygame.init()
    screen = pygame.display.set_mode(window_size())
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()
    renderer = Renderer()

    board = BoardState.generate_board(rows=GRID_ROWS, cols=GRID_COLS, seed=seed)
    session = Session(GameEngine(board), Timer(pygame.time.get_ticks(), end_time=seconds))
    drag = Drag()

    running = True
    while running:
        ticks = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == RESTART_KEY:
                drag.cancel()
                session.reset(ticks)
            elif event.type == pygame.KEYDOWN and event.key == NEW_GAME_KEY:
                drag.cancel()
                session.new_game(ticks)  # no seed: N always means a genuinely new board
            elif session.is_over:
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                drag.begin(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                drag.update(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                apply_selection(session.engine, drag.release(event.pos))

        session.update(ticks)

        renderer.draw_frame(
            screen,
            session.engine.board,
            session.engine.score,
            session.timer.remaining,
            drag.selection,
        )
        if session.is_over:
            score, elapsed = session.summary()
            renderer.draw_game_over(screen, score, elapsed)
        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m fruitbox.ui.app",
        description="Play Fruit Box (SPEC.md FR8-FR12, section 11).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="seed for the initial board (default: unseeded)",
    )
    parser.add_argument(
        "--time",
        "-t",
        type=float,
        default=TIMER_SECONDS,
        help=f"countdown length in seconds (default: {TIMER_SECONDS})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    run(seed=args.seed, seconds=args.time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
