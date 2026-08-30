"""Tests for the pygame drawing scaffold (SPEC.md FR7, section 11).

Covers the pure geometry (``cell_rect``, ``window_size``) and string
formatting (``format_hud``) pieces of ``fruitbox.ui.renderer`` -- these
involve no rendering or pixel inspection, so they're unit-tested directly,
per SPEC.md section 10's carve-out for pure UI translation functions.

Deliberately does NOT assert on drawn pixel colors, digit glyph presence, or
HUD text presence: the actual visual look (apple radius, colors, font
choice) is confirmed by eye and tuned as needed, not pinned by brittle
pixel-color assertions that would break on every cosmetic tweak. The one
exception is a non-visual smoke test confirming ``draw_frame`` runs without
raising -- it makes no claim about what was drawn, only that drawing
completed, which catches API-level breakage (font init, argument mismatches,
off-by-one on non-default board sizes) that eyeballing a window wouldn't
catch as quickly.

All headless -- pygame.Rect/Surface/font all work with no display and no
``pygame.display.set_mode()``.
"""

import inspect

import pytest

pygame = pytest.importorskip("pygame")

from fruitbox.config import (
    CELL_SIZE_PX,
    GRID_COLS,
    GRID_MARGIN_PX,
    GRID_ORIGIN_X_PX,
    GRID_ORIGIN_Y_PX,
    GRID_ROWS,
    HUD_HEIGHT_PX,
)
from fruitbox.engine.board import BoardState
from fruitbox.ui.renderer import Renderer, cell_rect, format_hud, grid_bounds, window_size

# --- cell_rect ---------------------------------------------------------------


def test_cell_rect_origin():
    rect = cell_rect(0, 0)

    assert rect.topleft == (GRID_ORIGIN_X_PX, GRID_ORIGIN_Y_PX)
    assert rect.size == (CELL_SIZE_PX, CELL_SIZE_PX)


def test_cell_rect_matches_formula():
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            rect = cell_rect(row, col)

            assert rect.x == GRID_ORIGIN_X_PX + col * CELL_SIZE_PX
            assert rect.y == GRID_ORIGIN_Y_PX + row * CELL_SIZE_PX
            assert rect.size == (CELL_SIZE_PX, CELL_SIZE_PX)


def test_cells_tile_without_gaps_or_overlap():
    for row in range(GRID_ROWS - 1):
        for col in range(GRID_COLS - 1):
            here = cell_rect(row, col)
            right = cell_rect(row, col + 1)
            below = cell_rect(row + 1, col)

            assert here.right == right.left
            assert here.bottom == below.top


def test_cell_rect_centers_are_unique_and_ordered():
    centers = {(row, col): cell_rect(row, col).center for row in range(6) for col in range(6)}

    assert len(set(centers.values())) == len(centers)

    for row in range(5):
        assert centers[(row, 0)][1] < centers[(row + 1, 0)][1]
    for col in range(5):
        assert centers[(0, col)][0] < centers[(0, col + 1)][0]


def test_cell_rect_center_inverts_to_same_cell():
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cx, cy = cell_rect(row, col).center

            recovered_row = (cy - GRID_ORIGIN_Y_PX) // CELL_SIZE_PX
            recovered_col = (cx - GRID_ORIGIN_X_PX) // CELL_SIZE_PX

            assert (recovered_row, recovered_col) == (row, col)


# --- grid_bounds ---------------------------------------------------------------


def test_grid_bounds_matches_first_and_last_cell_union():
    rows, cols = 5, 7

    bounds = grid_bounds(rows, cols)

    assert bounds == cell_rect(0, 0).union(cell_rect(rows - 1, cols - 1))


def test_grid_bounds_contains_every_cell():
    rows, cols = 3, 4
    bounds = grid_bounds(rows, cols)

    for row in range(rows):
        for col in range(cols):
            assert bounds.contains(cell_rect(row, col))


# --- window_size ---------------------------------------------------------------


def test_window_size_defaults_to_config_grid():
    assert window_size() == window_size(GRID_ROWS, GRID_COLS)


def test_window_size_matches_layout():
    width, height = window_size(3, 4)

    assert width == 2 * GRID_MARGIN_PX + 4 * CELL_SIZE_PX
    assert height == HUD_HEIGHT_PX + 2 * GRID_MARGIN_PX + 3 * CELL_SIZE_PX


def test_window_size_contains_every_cell():
    rows, cols = 3, 4
    window = pygame.Rect((0, 0), window_size(rows, cols))

    for row in range(rows):
        for col in range(cols):
            assert window.contains(cell_rect(row, col))


# --- format_hud ---------------------------------------------------------------


def test_format_hud_exact_string():
    assert format_hud(42, 87.0, 128) == "Score: 42   Time: 87   Apples: 128"


def test_format_hud_truncates_seconds():
    assert format_hud(0, 87.9, 0) == "Score: 0   Time: 87   Apples: 0"
    assert format_hud(0, 0.4, 0) == "Score: 0   Time: 0   Apples: 0"


def test_format_hud_clamps_negative_seconds():
    assert format_hud(0, -0.5, 0) == "Score: 0   Time: 0   Apples: 0"
    assert format_hud(0, -3.0, 0) == "Score: 0   Time: 0   Apples: 0"


def test_format_hud_accepts_zero_values():
    assert format_hud(0, 0, 0) == "Score: 0   Time: 0   Apples: 0"


def test_format_hud_has_no_high_score_field():
    assert "High" not in format_hud(0, 0, 0)
    assert list(inspect.signature(format_hud).parameters) == [
        "score",
        "seconds_remaining",
        "apples_remaining",
    ]


# --- Renderer: non-pixel smoke test ---------------------------------------------


def test_draw_frame_runs_headlessly():
    renderer = Renderer()
    surface = pygame.Surface(window_size(3, 4))
    board = BoardState(
        grid=[
            [1, 2, 3, 4],
            [0, 0, 9, 1],
            [5, 5, 0, 0],
        ],
        rows=3,
        cols=4,
    )

    renderer.draw_frame(surface, board, score=0, seconds_remaining=100)
