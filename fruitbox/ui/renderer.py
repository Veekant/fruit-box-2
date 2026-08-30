"""Drawing-only pygame scaffold: board + HUD onto a caller-supplied surface (SPEC.md FR7, section 11).

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
:func:`window_size`) that combines the config constants with a cell index or
grid size into actual pixel geometry. That arithmetic is the single place
every draw call (and, later, the reverse pixel-to-cell lookup in
``ui/input.py``) gets its numbers from, so a config tweak can't silently
desync one call site from another.

This module never mutates the ``BoardState`` it is given. Depends on
``fruitbox.engine`` and ``fruitbox.config`` plus pygame; nothing else in the
project may depend on ``fruitbox.ui`` (SPEC.md section 7).
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
)
from ..engine.board import BoardState

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

#: Apple circle radius as a fraction of the cell size.
_APPLE_RADIUS_RATIO = 0.42

#: Digit font size as a fraction of the cell size.
_DIGIT_FONT_RATIO = 0.6

#: HUD font size as a fraction of the HUD strip height.
_HUD_FONT_RATIO = 0.5


def cell_rect(row: int, col: int) -> pygame.Rect:
    """Return the pixel rectangle cell ``(row, col)`` occupies on screen.

    Pure arithmetic combining ``fruitbox.config``'s grid origin and cell size
    with a cell index. Takes no board and does no bounds checking -- defined
    for any integer row/col. Cells tile with no gap: the right edge of
    ``(r, c)`` is exactly the left edge of ``(r, c + 1)``.

    This is the single place cell-index-to-pixel arithmetic lives; every
    draw call in :class:`Renderer` goes through it, and a future reverse
    pixel-to-cell lookup (``ui/input.py``) should stay consistent with it
    rather than recomputing the same formula separately.
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

    def draw_frame(
        self,
        surface: pygame.Surface,
        board: BoardState,
        score: int,
        seconds_remaining: float,
    ) -> None:
        """Draw one complete frame: background, HUD, then the board.

        The single call a future ``app.py`` main loop makes per frame.
        ``apples_remaining`` is read from ``board`` itself rather than taken
        as a separate parameter, so it can never disagree with the board it
        describes.
        """
        surface.fill(COLOR_BACKGROUND)
        self.draw_hud(surface, score, seconds_remaining, board.apples_remaining)
        self.draw_board(surface, board)
