"""Tests for pixel-drag to grid-rectangle translation (SPEC.md FR8, section 11).

Includes the tests originally scoped to issue #15 ("Input translation unit
tests"), folded into this issue per its own description.

Covers ``cell_at``'s consistency with ``renderer.cell_rect`` (the forward
geometry), its raw arithmetic and out-of-range behaviour, and
``selection_from_drag``'s corner normalization, clamping/miss semantics, and
randomized invariants. Per SPEC.md section 10, this is a pure function and
is tested with entirely synthetic coordinates -- no display, no event loop.

Only the ``cell_rect``-consistency section needs pygame (to compute the
forward geometry it cross-checks against); every other test in this file
runs with pygame absent, matching ``fruitbox.ui.input``'s own no-pygame-import
discipline.
"""

import random

import pytest

from fruitbox.config import (
    CELL_SIZE_PX,
    GRID_COLS,
    GRID_ORIGIN_X_PX,
    GRID_ORIGIN_Y_PX,
    GRID_ROWS,
    HUD_HEIGHT_PX,
)
from fruitbox.engine.moves import Move
from fruitbox.ui.input import cell_at, selection_from_drag

# --- cell_at: consistency with renderer.cell_rect (needs pygame) ---------------

pygame = pytest.importorskip("pygame")

from fruitbox.ui.renderer import cell_rect  # noqa: E402  (after importorskip)


def test_cell_at_inverts_cell_rect_centers():
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            assert cell_at(cell_rect(row, col).center) == (row, col)


def test_cell_at_inverts_cell_rect_topleft_corner():
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            assert cell_at(cell_rect(row, col).topleft) == (row, col)


def test_cell_at_inverts_cell_rect_bottomright_inner_corner():
    # The rect's own bottomright is exclusive (pygame convention) and
    # belongs to the *next* cell, per test_cell_at_half_open_boundary below --
    # so the last pixel genuinely inside this cell is (right - 1, bottom - 1).
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            rect = cell_rect(row, col)
            assert cell_at((rect.right - 1, rect.bottom - 1)) == (row, col)


def test_cell_at_half_open_boundary():
    row, col = 2, 3
    rect = cell_rect(row, col)

    # Crossing the right edge belongs to the next column; crossing the
    # bottom edge belongs to the next row -- the exact tiling property
    # test_cells_tile_without_gaps_or_overlap (test_renderer.py) implies,
    # made explicit for the inverse direction.
    assert cell_at(rect.topright) == (row, col + 1)
    assert cell_at(rect.bottomleft) == (row + 1, col)


# --- cell_at: raw arithmetic and out-of-range behaviour (pygame-free) ----------


def test_cell_at_grid_origin():
    assert cell_at((GRID_ORIGIN_X_PX, GRID_ORIGIN_Y_PX)) == (0, 0)


def test_cell_at_one_pixel_before_origin_floors_not_truncates():
    # Floor division, not truncation-toward-zero: one pixel left/above the
    # origin must land at index -1, not jump straight to some other value.
    assert cell_at((GRID_ORIGIN_X_PX - 1, GRID_ORIGIN_Y_PX)) == (0, -1)
    assert cell_at((GRID_ORIGIN_X_PX, GRID_ORIGIN_Y_PX - 1)) == (-1, 0)


def test_cell_at_hud_strip_pixel_is_negative_row():
    # A pixel in the top HUD strip is well above the grid's origin.
    assert cell_at((GRID_ORIGIN_X_PX, HUD_HEIGHT_PX // 2))[0] < 0


def test_cell_at_far_past_the_grid():
    row, col = cell_at(
        (GRID_ORIGIN_X_PX + GRID_COLS * CELL_SIZE_PX + 500, GRID_ORIGIN_Y_PX + GRID_ROWS * CELL_SIZE_PX + 500)
    )
    assert row >= GRID_ROWS
    assert col >= GRID_COLS


def test_cell_at_is_monotonic_across_the_origin():
    xs = [GRID_ORIGIN_X_PX + dx for dx in range(-CELL_SIZE_PX * 2, CELL_SIZE_PX * 2, 5)]
    cols = [cell_at((x, GRID_ORIGIN_Y_PX))[1] for x in xs]

    assert cols == sorted(cols)


def test_cell_at_accepts_float_coordinates():
    # Floats are truncated to int before flooring, not rejected.
    row, col = cell_at((GRID_ORIGIN_X_PX + 1.9, GRID_ORIGIN_Y_PX + 1.9))
    assert (row, col) == (0, 0)


# --- selection_from_drag: corner normalization (the core of the issue) --------


def _cell_pixel_center(row: int, col: int) -> tuple[int, int]:
    return (
        GRID_ORIGIN_X_PX + col * CELL_SIZE_PX + CELL_SIZE_PX // 2,
        GRID_ORIGIN_Y_PX + row * CELL_SIZE_PX + CELL_SIZE_PX // 2,
    )


def test_single_cell_drag_yields_a_one_by_one_move():
    pixel = _cell_pixel_center(2, 3)

    assert selection_from_drag(pixel, pixel) == Move(row_start=2, col_start=3, row_end=2, col_end=3)


def test_forward_drag_top_left_to_bottom_right():
    start = _cell_pixel_center(1, 1)
    end = _cell_pixel_center(4, 6)

    assert selection_from_drag(start, end) == Move(row_start=1, col_start=1, row_end=4, col_end=6)


@pytest.mark.parametrize(
    "corner_a,corner_b",
    [
        ((1, 1), (4, 6)),  # top-left -> bottom-right
        ((4, 6), (1, 1)),  # bottom-right -> top-left
        ((1, 6), (4, 1)),  # top-right -> bottom-left
        ((4, 1), (1, 6)),  # bottom-left -> top-right
    ],
)
def test_all_four_corner_drag_permutations_agree(corner_a, corner_b):
    a = _cell_pixel_center(*corner_a)
    b = _cell_pixel_center(*corner_b)

    assert selection_from_drag(a, b) == Move(row_start=1, col_start=1, row_end=4, col_end=6)


@pytest.mark.parametrize("seed", range(10))
def test_selection_from_drag_is_symmetric(seed):
    rng = random.Random(seed)
    a = (rng.randint(-200, 1000), rng.randint(-200, 700))
    b = (rng.randint(-200, 1000), rng.randint(-200, 700))

    assert selection_from_drag(a, b) == selection_from_drag(b, a)


def test_interior_pixels_snap_the_same_as_centers():
    row, col = 3, 5
    rect_center = _cell_pixel_center(row, col)
    # A pixel a couple of px off-center, still well inside the cell.
    interior = (rect_center[0] - 5, rect_center[1] + 5)

    assert selection_from_drag(interior, interior) == selection_from_drag(rect_center, rect_center)


# --- selection_from_drag: clamping and misses -----------------------------------


def test_drag_far_off_bottom_right_clamps_to_last_cell():
    start = _cell_pixel_center(2, 2)
    end = (GRID_ORIGIN_X_PX + GRID_COLS * CELL_SIZE_PX + 10_000, GRID_ORIGIN_Y_PX + GRID_ROWS * CELL_SIZE_PX + 10_000)

    result = selection_from_drag(start, end)

    assert result == Move(row_start=2, col_start=2, row_end=GRID_ROWS - 1, col_end=GRID_COLS - 1)


def test_drag_to_negative_pixels_clamps_to_first_cell():
    start = _cell_pixel_center(2, 2)
    end = (-500, -500)

    result = selection_from_drag(start, end)

    assert result == Move(row_start=0, col_start=0, row_end=2, col_end=2)


def test_drag_starting_in_hud_strip_clamps_row_only():
    hud_pixel = (GRID_ORIGIN_X_PX + 3 * CELL_SIZE_PX, HUD_HEIGHT_PX // 2)
    grid_pixel = _cell_pixel_center(2, 3)

    result = selection_from_drag(hud_pixel, grid_pixel)

    assert result == Move(row_start=0, col_start=3, row_end=2, col_end=3)


def test_drag_entirely_within_hud_strip_returns_none():
    a = (GRID_ORIGIN_X_PX, 2)
    b = (GRID_ORIGIN_X_PX + 5 * CELL_SIZE_PX, HUD_HEIGHT_PX - 2)

    assert selection_from_drag(a, b) is None


def test_drag_entirely_left_of_grid_returns_none():
    a = (GRID_ORIGIN_X_PX - 100, GRID_ORIGIN_Y_PX)
    b = (GRID_ORIGIN_X_PX - 10, GRID_ORIGIN_Y_PX + 3 * CELL_SIZE_PX)

    assert selection_from_drag(a, b) is None


def test_drag_entirely_below_grid_returns_none():
    bottom = GRID_ORIGIN_Y_PX + GRID_ROWS * CELL_SIZE_PX
    a = (GRID_ORIGIN_X_PX, bottom + 10)
    b = (GRID_ORIGIN_X_PX + 3 * CELL_SIZE_PX, bottom + 100)

    assert selection_from_drag(a, b) is None


def test_drag_spanning_the_whole_window_covers_the_full_grid():
    a = (-10_000, -10_000)
    b = (10_000, 10_000)

    result = selection_from_drag(a, b)

    assert result == Move(row_start=0, col_start=0, row_end=GRID_ROWS - 1, col_end=GRID_COLS - 1)


def test_non_default_grid_size_is_honoured():
    a = _cell_pixel_center(0, 0)
    b = (10_000, 10_000)

    result = selection_from_drag(a, b, rows=3, cols=4)

    assert result == Move(row_start=0, col_start=0, row_end=2, col_end=3)


# --- Invariants / randomized cross-check ----------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_selection_from_drag_never_raises_and_stays_well_formed(seed):
    rng = random.Random(seed)
    a = (rng.randint(-5000, 5000), rng.randint(-5000, 5000))
    b = (rng.randint(-5000, 5000), rng.randint(-5000, 5000))

    result = selection_from_drag(a, b)

    if result is None:
        return

    assert 0 <= result.row_start <= result.row_end < GRID_ROWS
    assert 0 <= result.col_start <= result.col_end < GRID_COLS

    row_a, col_a = cell_at(a)
    row_b, col_b = cell_at(b)
    row_lo, row_hi = sorted((row_a, row_b))
    col_lo, col_hi = sorted((col_a, col_b))

    assert result.row_start == min(max(row_lo, 0), GRID_ROWS - 1)
    assert result.row_end == min(max(row_hi, 0), GRID_ROWS - 1)
    assert result.col_start == min(max(col_lo, 0), GRID_COLS - 1)
    assert result.col_end == min(max(col_hi, 0), GRID_COLS - 1)
