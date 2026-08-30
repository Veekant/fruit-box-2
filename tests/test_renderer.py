"""Tests for the pygame drawing scaffold (SPEC.md FR7, FR9, section 11).

Covers the pure geometry (``cell_rect``, ``grid_bounds``, ``window_size``,
``selection_rect``), the pure legality-cue mapping (``selection_color``),
and string formatting (``format_hud``) pieces of ``fruitbox.ui.renderer`` --
these involve no rendering or pixel inspection, so they're unit-tested
directly, per SPEC.md section 10's carve-out for pure UI translation
functions.

Deliberately does NOT assert on drawn pixel colors, digit glyph presence, or
HUD text presence: the actual visual look (apple radius, colors, font
choice) is confirmed by eye and tuned as needed, not pinned by brittle
pixel-color assertions that would break on every cosmetic tweak. The
exceptions are non-visual smoke tests confirming drawing methods run without
raising, and one test that a selection's fill/outline mark *something* at
the right location without asserting *which* color -- these catch
API-level breakage (font init, argument mismatches, bad alpha-surface
handling, off-by-one on non-default board sizes) that eyeballing a window
wouldn't catch as quickly.

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
    TARGET_SUM,
)
from fruitbox.engine.board import BoardState
from fruitbox.engine.moves import Move
from fruitbox.ui.renderer import (
    COLOR_BACKGROUND,
    COLOR_SELECTION_EXACT,
    COLOR_SELECTION_OVER,
    COLOR_SELECTION_UNDER,
    Renderer,
    cell_rect,
    format_hud,
    grid_bounds,
    selection_color,
    selection_rect,
    window_size,
)

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


# The cell_rect <-> pixel-to-cell round trip (formerly hand-rolled here) is
# now tested against the real inverse, fruitbox.ui.input.cell_at, in
# tests/test_input.py -- asserting the actual consistency contract rather
# than a copy of the formula it's meant to guard.


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


# --- selection_rect -------------------------------------------------------------


def test_selection_rect_of_a_single_cell_equals_cell_rect():
    move = Move(row_start=2, col_start=3, row_end=2, col_end=3)

    assert selection_rect(move) == cell_rect(2, 3)


def test_selection_rect_spans_both_corner_cells():
    move = Move(row_start=1, col_start=1, row_end=4, col_end=6)

    assert selection_rect(move) == cell_rect(1, 1).union(cell_rect(4, 6))
    assert selection_rect(move).topleft == cell_rect(1, 1).topleft


def test_selection_rect_size_matches_cell_span():
    move = Move(row_start=1, col_start=1, row_end=4, col_end=6)  # 4 rows x 6 cols

    rect = selection_rect(move)

    assert rect.size == (6 * CELL_SIZE_PX, 4 * CELL_SIZE_PX)


def test_selection_rect_contains_every_cell_it_spans():
    move = Move(row_start=1, col_start=1, row_end=4, col_end=6)
    rect = selection_rect(move)

    for row in range(1, 5):
        for col in range(1, 7):
            assert rect.contains(cell_rect(row, col))


def test_selection_rect_of_a_single_row_or_column():
    row_move = Move(row_start=2, col_start=0, row_end=2, col_end=4)
    col_move = Move(row_start=0, col_start=2, row_end=4, col_end=2)

    assert selection_rect(row_move).size == (5 * CELL_SIZE_PX, CELL_SIZE_PX)
    assert selection_rect(col_move).size == (CELL_SIZE_PX, 5 * CELL_SIZE_PX)


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


# --- selection_color -------------------------------------------------------------


@pytest.mark.parametrize("total", [0, 1, TARGET_SUM // 2])
def test_selection_color_under_target(total):
    assert selection_color(total) == COLOR_SELECTION_UNDER


def test_selection_color_immediately_below_target():
    assert selection_color(TARGET_SUM - 1) == COLOR_SELECTION_UNDER


def test_selection_color_at_target():
    assert selection_color(TARGET_SUM) == COLOR_SELECTION_EXACT


def test_selection_color_immediately_above_target():
    assert selection_color(TARGET_SUM + 1) == COLOR_SELECTION_OVER


@pytest.mark.parametrize("total", [TARGET_SUM + 2, 45, 200])
def test_selection_color_well_over_target(total):
    assert selection_color(total) == COLOR_SELECTION_OVER


def test_selection_color_covers_every_sum_in_a_range():
    for total in range(0, 31):
        color = selection_color(total)
        if total < TARGET_SUM:
            assert color == COLOR_SELECTION_UNDER
        elif total == TARGET_SUM:
            assert color == COLOR_SELECTION_EXACT
        else:
            assert color == COLOR_SELECTION_OVER


def test_selection_colors_are_distinct():
    colors = [COLOR_SELECTION_UNDER, COLOR_SELECTION_EXACT, COLOR_SELECTION_OVER]

    assert len(set(colors)) == 3
    for color in colors:
        assert len(color) == 3
        assert all(isinstance(c, int) and 0 <= c <= 255 for c in color)


# --- Renderer: non-pixel smoke tests ---------------------------------------------


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


def _small_board() -> BoardState:
    return BoardState(
        grid=[
            [1, 2, 3, 4],
            [0, 0, 9, 1],
            [5, 5, 0, 0],
        ],
        rows=3,
        cols=4,
    )


@pytest.mark.parametrize(
    "move",
    [
        Move(row_start=0, col_start=0, row_end=0, col_end=0),  # under (sum=1)
        Move(row_start=1, col_start=2, row_end=1, col_end=3),  # exact (9+1=10)
        Move(row_start=0, col_start=0, row_end=2, col_end=3),  # over (whole board, sum=30)
    ],
)
def test_draw_selection_runs_headlessly_for_each_color_state(move):
    renderer = Renderer()
    surface = pygame.Surface(window_size(3, 4))
    board = _small_board()

    renderer.draw_selection(surface, board, move)


def test_draw_selection_does_not_mutate_the_board():
    renderer = Renderer()
    surface = pygame.Surface(window_size(3, 4))
    board = _small_board()
    grid_before = [row[:] for row in board.grid]
    apples_before = board.apples_remaining

    renderer.draw_selection(surface, board, Move(row_start=1, col_start=2, row_end=1, col_end=3))

    assert board.grid == grid_before
    assert board.apples_remaining == apples_before


def test_draw_selection_marks_the_selected_area():
    renderer = Renderer()
    board = BoardState(grid=[[0] * 4 for _ in range(3)], rows=3, cols=4)
    surface = pygame.Surface(window_size(3, 4))
    surface.fill(COLOR_BACKGROUND)

    move = Move(row_start=1, col_start=1, row_end=1, col_end=2)
    renderer.draw_selection(surface, board, move)

    inside = selection_rect(move).center
    # A point well inside the grid but outside the selection and away from
    # the grid border.
    outside = cell_rect(0, 0).center

    assert surface.get_at(inside)[:3] != COLOR_BACKGROUND
    assert surface.get_at(outside)[:3] == COLOR_BACKGROUND


def test_draw_frame_accepts_a_selection():
    renderer = Renderer()
    surface = pygame.Surface(window_size(3, 4))
    board = _small_board()

    renderer.draw_frame(
        surface,
        board,
        score=0,
        seconds_remaining=100,
        selection=Move(row_start=1, col_start=2, row_end=1, col_end=3),
    )


def test_draw_frame_selection_defaults_to_none():
    params = inspect.signature(Renderer.draw_frame).parameters
    assert list(params)[-1] == "selection"
    assert params["selection"].default is None

    # The pre-existing four-positional-arg call shape still works unchanged.
    renderer = Renderer()
    surface = pygame.Surface(window_size(3, 4))
    board = _small_board()
    renderer.draw_frame(surface, board, 0, 100)
