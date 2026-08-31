"""Drawing-only pygame scaffold: board + HUD + game-over screen onto a caller-supplied surface (SPEC.md FR7, FR11, section 11).

This module owns no window, no event loop, no clock, and no game state --
those belong to later UI issues (``app.py``, ``input.py``). It only knows how
to paint a :class:`~fruitbox.engine.board.BoardState` and a HUD line onto a
``pygame.Surface`` it is handed, via :class:`Renderer`.

**Deliberate simplification of SPEC.md section 11 and FR7** (matching the
precedent ``fruitbox.engine.game.GameEngine.is_terminal`` already sets for
documenting an intentional scope decision inline): there is no line drawn
between individual cells -- only a thin border around the grid's outer
boundary as a whole (see :data:`COLOR_GRID_BORDER`). Each occupied cell is a
colored circle with its digit centered on it; each empty cell has nothing
drawn in it. An empty cell is visually distinct from an occupied one simply
by having no shape drawn there -- this is the final intended look, not a
placeholder, and SPEC.md sections 5.2/11 have been updated to match.

Layout constants (cell size, the grid's screen origin, HUD strip height) live
in ``fruitbox.config`` -- this module only holds colours and look-and-feel
proportions, and the arithmetic (:func:`cell_rect`, :func:`grid_bounds`,
:func:`window_size`, :func:`selection_rect`) that combines the config
constants with a cell index or grid size into actual pixel geometry. That
arithmetic is the single place every draw call gets its numbers from, so a
config tweak can't silently desync one call site from another. The reverse
pixel-to-cell lookup lives in ``ui/input.py`` -- derived independently from
the same config constants rather than importing from this module, so
``ui/input.py`` stays pygame-free.

**Deliberate simplification of SPEC.md FR9 and section 11** (same posture as
the section 11/FR7 note above): live drag feedback is a **three-way color
cue only** -- the selection rectangle is tinted yellow while its cell-value
sum is under ``TARGET_SUM``, green exactly at it, and red once over -- with
no numeric sum ever rendered on screen. This is strictly more informative
than a binary legal/illegal cue (yellow means "keep dragging", red means
"you've overshot"), which is what makes dropping the numeric readout an
acceptable trade rather than a loss; SPEC.md sections 5.2/11 have been
updated to match. There is consequently no boolean legality check anywhere
in this module's drawing path -- :meth:`Renderer.draw_selection` reads
:meth:`~fruitbox.engine.board.BoardState.move_sum` once and picks a colour
off a three-way comparison, never calling ``is_legal``. Legality still
governs what happens on release (FR10); that is a later issue's concern.

This module never mutates the ``BoardState`` it is given, and -- matching
``ui/input.py``'s posture -- tracks no drag state of its own: every drawing
call takes an already-computed candidate ``Move`` (or ``None``), leaving
"is the mouse currently down, and where" to ``ui/app.py``. Depends on
``fruitbox.engine`` and ``fruitbox.config`` plus pygame; nothing else in the
project may depend on ``fruitbox.ui`` (SPEC.md section 7).

**Game-over screen (FR11).** :meth:`Renderer.draw_game_over` draws a dimming
overlay plus a centered summary (score, time played, session high score, and
the restart/new-game prompts) over an already-drawn frame -- it is a
separate method from :meth:`Renderer.draw_frame` rather than a parameter on
it, since it needs elapsed time and a high score that ``draw_frame`` has no
business knowing. The high score shown is currently always a caller-supplied
placeholder (``0`` by default); real session high-score tracking is a later
issue's job. The restart/new-game key labels shown in the prompts live in
``fruitbox.config`` (not here), so this module's rendered text and a future
key-handling module can both reference the same constants without either
importing the other.
"""

from __future__ import annotations

import pygame

from ..config import (
    CELL_SIZE_PX,
    GRID_COLS,
    GRID_MARGIN_PX,
    GRID_ORIGIN_X_PX,
    GRID_ORIGIN_Y_PX,
    GRID_ROWS,
    HUD_HEIGHT_PX,
    NEW_GAME_KEY_LABEL,
    RESTART_KEY_LABEL,
    TARGET_SUM,
)
from ..engine.board import BoardState
from ..engine.moves import Move

#: Fill for the entire surface.
COLOR_BACKGROUND = (30, 30, 30)

#: The circle drawn for an occupied cell.
COLOR_APPLE = (200, 40, 40)

#: The digit drawn on top of an apple.
COLOR_APPLE_TEXT = (255, 255, 255)

#: The HUD line's text colour. Kept separate from COLOR_APPLE_TEXT so the two
#: can be tuned independently even though both start out white.
COLOR_HUD_TEXT = (255, 255, 255)

#: The thin line drawn around the outside of the grid as a whole. There is
#: still no line drawn between individual cells -- only around the grid's
#: outer boundary.
COLOR_GRID_BORDER = (255, 255, 255)

#: Width, in pixels, of the outer grid border line.
_GRID_BORDER_WIDTH_PX = 1

#: Selection fill/outline colour while the candidate sum is under TARGET_SUM
#: ("keep dragging").
COLOR_SELECTION_UNDER = (235, 200, 60)

#: Selection fill/outline colour while the candidate sum is exactly
#: TARGET_SUM (releasing now plays the move).
COLOR_SELECTION_EXACT = (70, 205, 95)

#: Selection fill/outline colour once the candidate sum exceeds TARGET_SUM
#: ("overshot"). Deliberately close to COLOR_APPLE's red -- red is the
#: natural "too much" signal, and the yellow/green/red triad reads clearly
#: even though this shade resembles an apple's.
COLOR_SELECTION_OVER = (215, 65, 65)

#: Alpha (0-255) of the selection's translucent fill. Chosen so the tint is
#: unmistakable against COLOR_BACKGROUND while still leaving apples and
#: their digits legible underneath -- much lower and the tint washes out on
#: the dark background, much higher and digit contrast starts to suffer.
_SELECTION_FILL_ALPHA = 100

#: Width, in pixels, of the selection's opaque outline. Thicker than
#: _GRID_BORDER_WIDTH_PX so the selection reads as a distinct element rather
#: than a second grid frame.
_SELECTION_BORDER_WIDTH_PX = 3

#: Apple circle radius as a fraction of the cell size.
_APPLE_RADIUS_RATIO = 0.42

#: Digit font size as a fraction of the cell size.
_DIGIT_FONT_RATIO = 0.6

#: HUD font size as a fraction of the HUD strip height.
_HUD_FONT_RATIO = 0.5

#: Game-over screen heading.
GAME_OVER_TITLE = "Game Over"

#: Game-over restart prompt, built from the shared key-label constant so the
#: displayed text and the eventual key binding (issue #19) can't drift apart.
RESTART_PROMPT = f"Press {RESTART_KEY_LABEL} to replay this board"

#: Game-over new-game prompt, built the same way as RESTART_PROMPT.
NEW_GAME_PROMPT = f"Press {NEW_GAME_KEY_LABEL} for a new board"

#: Text colour for the game-over screen. Kept separate from COLOR_HUD_TEXT so
#: the two can be tuned independently even though both start out white.
COLOR_GAME_OVER_TEXT = (255, 255, 255)

#: Dimming wash drawn over the final board on the game-over screen.
COLOR_GAME_OVER_OVERLAY = (0, 0, 0)

#: Alpha (0-255) of the game-over dimming wash.
_GAME_OVER_OVERLAY_ALPHA = 190

#: Game-over font size as a fraction of the HUD strip height.
_GAME_OVER_FONT_RATIO = 0.7

#: Line pitch on the game-over screen, as a multiple of the font's line height.
_GAME_OVER_LINE_SPACING_RATIO = 1.3


def cell_rect(row: int, col: int) -> pygame.Rect:
    """Return the pixel rectangle cell ``(row, col)`` occupies on screen.

    Pure arithmetic combining ``fruitbox.config``'s grid origin and cell size
    with a cell index. Takes no board and does no bounds checking -- defined
    for any integer row/col. Cells tile with no gap: the right edge of
    ``(r, c)`` is exactly the left edge of ``(r, c + 1)``.

    This is the single place cell-index-to-pixel arithmetic lives; every
    draw call in :class:`Renderer` goes through it. The reverse pixel-to-cell
    lookup, ``fruitbox.ui.input.cell_at``, is derived independently from the
    same ``fruitbox.config`` constants (not by importing this function) --
    consistency between the two is enforced by tests, not a shared import.
    """
    return pygame.Rect(
        GRID_ORIGIN_X_PX + col * CELL_SIZE_PX,
        GRID_ORIGIN_Y_PX + row * CELL_SIZE_PX,
        CELL_SIZE_PX,
        CELL_SIZE_PX,
    )


def grid_bounds(rows: int, cols: int) -> pygame.Rect:
    """Return the pixel rectangle spanning the whole ``rows`` x ``cols`` grid.

    Exactly the union of ``cell_rect(0, 0)`` and ``cell_rect(rows - 1, cols - 1)``
    -- the outer boundary of the grid as a whole, not any individual cell.
    This is what the outer grid border is drawn around.
    """
    return cell_rect(0, 0).union(cell_rect(rows - 1, cols - 1))


def selection_rect(move: Move) -> pygame.Rect:
    """Return the pixel rectangle a candidate selection ``move`` spans.

    The multi-cell analogue of :func:`cell_rect` -- the union of the two
    corner cells' rectangles. Does no bounds checking against any board;
    defined for any well-formed ``Move``.
    """
    return cell_rect(move.row_start, move.col_start).union(cell_rect(move.row_end, move.col_end))


def selection_color(total: int) -> tuple[int, int, int]:
    """Map a candidate selection's cell-value sum to its display colour.

    Three-way, not binary legal/illegal: ``total < TARGET_SUM`` is
    :data:`COLOR_SELECTION_UNDER` ("keep dragging"), ``total == TARGET_SUM``
    is :data:`COLOR_SELECTION_EXACT`, and anything over is
    :data:`COLOR_SELECTION_OVER` ("overshot"). Pure function -- takes the sum
    itself rather than a precomputed legality flag.
    """
    if total < TARGET_SUM:
        return COLOR_SELECTION_UNDER
    if total == TARGET_SUM:
        return COLOR_SELECTION_EXACT
    return COLOR_SELECTION_OVER


def window_size(rows: int = GRID_ROWS, cols: int = GRID_COLS) -> tuple[int, int]:
    """Return the pixel ``(width, height)`` a window needs for a ``rows`` x ``cols`` grid.

    Accounts for the grid margin on all sides and the HUD strip above the
    grid. Defaults to the configured default board size; pass explicit
    ``rows``/``cols`` for any other size (e.g. in tests).
    """
    width = 2 * GRID_MARGIN_PX + cols * CELL_SIZE_PX
    height = HUD_HEIGHT_PX + 2 * GRID_MARGIN_PX + rows * CELL_SIZE_PX
    return width, height


def format_hud(score: int, seconds_remaining: float, apples_remaining: int) -> str:
    """Format the HUD line: score, time remaining, apples remaining.

    Time is a bare integer count of seconds, truncated toward zero (not
    rounded) and clamped at 0, so a timer that ticks slightly past expiry
    renders ``0`` rather than a negative number. Does not compute elapsed
    time itself -- displays whatever ``seconds_remaining`` it is given.

    No session-high-score field here; that lands with a later issue.
    """
    seconds = max(0, int(seconds_remaining))
    return f"Score: {score}   Time: {seconds}   Apples: {apples_remaining}"


def format_game_over(score: int, elapsed_time: float, high_score: int = 0) -> list[str]:
    """Format the game-over screen: one string per line to render.

    Lines, in order: title, final score, time played, session high score,
    and both restart/new-game prompts. Time played is a bare integer count
    of seconds, truncated toward zero (not rounded) and clamped at 0 --
    the same posture ``format_hud`` takes for time remaining. Labeled "Time
    played" rather than "Time" so it can't be misread as the HUD's
    time-*remaining* field.

    ``high_score`` defaults to ``0`` -- a placeholder. Real session
    high-score tracking is a later issue's job; this parameter exists now so
    that issue can start passing a real value with no signature change.
    No apples-cleared/apples-total fields -- score and elapsed time are the
    only game-over numbers this screen reports.

    Returns a list (one entry per line) rather than a single string, since
    ``pygame.font.Font.render`` does not lay out embedded newlines --
    something has to split the text, and doing it here makes the split
    explicit and exactly testable.
    """
    seconds = max(0, int(elapsed_time))
    return [
        GAME_OVER_TITLE,
        f"Score: {score}",
        f"Time played: {seconds}",
        f"High Score: {high_score}",
        RESTART_PROMPT,
        NEW_GAME_PROMPT,
    ]


class Renderer:
    """Draws a board and HUD onto a caller-supplied ``pygame.Surface``.

    Owns no window and no game state -- only the fonts, which must be built
    once (font construction is comparatively expensive) rather than per
    frame. Never mutates any ``BoardState`` it is given.
    """

    def __init__(self) -> None:
        pygame.font.init()
        self._digit_font = pygame.font.SysFont(None, int(CELL_SIZE_PX * _DIGIT_FONT_RATIO))
        self._hud_font = pygame.font.SysFont(None, int(HUD_HEIGHT_PX * _HUD_FONT_RATIO))
        self._game_over_font = pygame.font.SysFont(None, int(HUD_HEIGHT_PX * _GAME_OVER_FONT_RATIO))

    def draw_board(self, surface: pygame.Surface, board: BoardState) -> None:
        """Draw every occupied cell as an apple; leave empty cells untouched.

        Does not fill the background -- composites onto whatever is already
        on ``surface``. Iterates ``board.rows``/``board.cols``, never
        ``fruitbox.config``'s defaults, so a non-default-size board is drawn
        correctly. Read-only with respect to ``board``.

        Draws a thin border around the outside of the grid as a whole (see
        :data:`COLOR_GRID_BORDER`) -- still no line between individual cells.
        """
        radius = int(CELL_SIZE_PX * _APPLE_RADIUS_RATIO)

        for row in range(board.rows):
            for col in range(board.cols):
                value = board.grid[row][col]
                if value == 0:
                    continue

                center = cell_rect(row, col).center
                pygame.draw.circle(surface, COLOR_APPLE, center, radius)

                digit = self._digit_font.render(str(value), True, COLOR_APPLE_TEXT)
                surface.blit(digit, digit.get_rect(center=center))

        pygame.draw.rect(
            surface,
            COLOR_GRID_BORDER,
            grid_bounds(board.rows, board.cols),
            width=_GRID_BORDER_WIDTH_PX,
        )

    def draw_hud(
        self,
        surface: pygame.Surface,
        score: int,
        seconds_remaining: float,
        apples_remaining: int,
    ) -> None:
        """Draw the HUD line into the top strip, left-aligned and vertically centered.

        Draws no panel background of its own -- the text sits directly on
        whatever background ``surface`` already has.
        """
        text = self._hud_font.render(
            format_hud(score, seconds_remaining, apples_remaining), True, COLOR_HUD_TEXT
        )
        rect = text.get_rect()
        rect.left = GRID_MARGIN_PX
        rect.centery = HUD_HEIGHT_PX // 2
        surface.blit(text, rect)

    def draw_selection(self, surface: pygame.Surface, board: BoardState, move: Move) -> None:
        """Draw a candidate selection: translucent fill + opaque outline (FR9).

        Colour is picked from ``board.move_sum(move)`` via
        :func:`selection_color` -- a three-way under/exact/over cue, never a
        boolean legality check (``board.is_legal`` is not called here). No
        numeric sum is rendered; the colour is the only feedback signal.

        ``move`` is assumed to lie within ``board`` -- ``ui/input.py``'s
        ``selection_from_drag`` already clamps into the grid before this is
        ever called, so no defensive bounds check is done here; an
        out-of-bounds ``move`` raises ``IndexError`` from ``move_sum``, the
        same posture ``count_apples`` takes. Read-only with respect to
        ``board``.
        """
        total = board.move_sum(move)
        color = selection_color(total)
        rect = selection_rect(move)

        overlay = pygame.Surface(rect.size)
        overlay.set_alpha(_SELECTION_FILL_ALPHA)
        overlay.fill(color)
        surface.blit(overlay, rect.topleft)

        pygame.draw.rect(surface, color, rect, width=_SELECTION_BORDER_WIDTH_PX)

    def draw_game_over(
        self,
        surface: pygame.Surface,
        score: int,
        elapsed_time: float,
        high_score: int = 0,
    ) -> None:
        """Draw the game-over screen: a dimming overlay plus a centered summary (FR11).

        Draws no board and takes none -- callers draw the final frame first
        (via :meth:`draw_frame`) and call this on top, since it needs
        ``elapsed_time``/``high_score``, which ``draw_frame`` has no
        business knowing. Owns no state of its own.
        """
        overlay = pygame.Surface(surface.get_size())
        overlay.set_alpha(_GAME_OVER_OVERLAY_ALPHA)
        overlay.fill(COLOR_GAME_OVER_OVERLAY)
        surface.blit(overlay, (0, 0))

        lines = format_game_over(score, elapsed_time, high_score)
        rendered = [self._game_over_font.render(line, True, COLOR_GAME_OVER_TEXT) for line in lines]

        line_height = self._game_over_font.get_linesize()
        spacing = int(line_height * _GAME_OVER_LINE_SPACING_RATIO)
        block_height = spacing * (len(rendered) - 1) + line_height
        top = surface.get_height() // 2 - block_height // 2

        for i, text in enumerate(rendered):
            rect = text.get_rect()
            rect.centerx = surface.get_width() // 2
            rect.top = top + i * spacing
            surface.blit(text, rect)

    def draw_frame(
        self,
        surface: pygame.Surface,
        board: BoardState,
        score: int,
        seconds_remaining: float,
        selection: Move | None = None,
    ) -> None:
        """Draw one complete frame: background, HUD, board, then the selection.

        The single call a future ``app.py`` main loop makes per frame.
        ``apples_remaining`` is read from ``board`` itself rather than taken
        as a separate parameter, so it can never disagree with the board it
        describes.

        ``selection`` is the current candidate ``Move`` for an in-progress
        drag, or ``None`` when no drag is active -- this method holds no drag
        state of its own; the caller computes ``selection`` fresh each frame
        (e.g. via ``ui.input.selection_from_drag``) and passes it in.

        When the game has ended, the caller additionally calls
        :meth:`draw_game_over` after this method, so the "single call per
        frame" claim above stays accurate -- game-over is a separate method
        rather than a parameter here because it needs elapsed time and a
        high score, which this method has no business knowing.
        """
        surface.fill(COLOR_BACKGROUND)
        self.draw_hud(surface, score, seconds_remaining, board.apples_remaining)
        self.draw_board(surface, board)
        if selection is not None:
            self.draw_selection(surface, board, selection)
