"""Project-wide constants.

Grid dimensions, cell value range, timer length, the target rectangle sum,
and UI grid geometry (cell size and the grid's location in screen space) live
here so they are named in exactly one place rather than scattered as magic
numbers through the engine, solver, and UI (SPEC.md section 2, section 7).

The UI geometry constants below are plain ints -- this module still imports
nothing and pulls in no pygame, so ``fruitbox.engine`` (which imports
``config``) stays exactly as pygame-free as before.
"""

#: Number of rows in the board. Default Fruit Box layout is 17 columns x 10 rows.
GRID_ROWS = 10

#: Number of columns in the board.
GRID_COLS = 17

#: Smallest value a generated (occupied) cell may hold. 0 is reserved for "empty".
MIN_CELL_VALUE = 1

#: Largest value a generated cell may hold.
MAX_CELL_VALUE = 9

#: Default countdown length, in seconds. UI-only concept: the solver never
#: reasons about wall-clock time, only move count (SPEC.md section 9).
TIMER_SECONDS = 100

#: A rectangle is a legal move if and only if its cell values sum to exactly this.
TARGET_SUM = 10

#: Width and height, in pixels, of one grid cell. Cells tile with no gap
#: between them (SPEC.md section 11 -- no explicit gridlines are drawn).
CELL_SIZE_PX = 48

#: Padding, in pixels, between the grid block and the window edges / the HUD
#: strip above it.
GRID_MARGIN_PX = 24

#: Height, in pixels, of the HUD strip along the top of the window
#: (``y`` in ``[0, HUD_HEIGHT_PX)``).
HUD_HEIGHT_PX = 56

#: X pixel coordinate of cell (0, 0)'s top-left corner -- the grid's screen
#: origin. Derived from the constants above so there is still one knob per
#: visual concept.
GRID_ORIGIN_X_PX = GRID_MARGIN_PX

#: Y pixel coordinate of cell (0, 0)'s top-left corner.
GRID_ORIGIN_Y_PX = HUD_HEIGHT_PX + GRID_MARGIN_PX
