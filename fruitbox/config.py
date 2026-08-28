"""Project-wide constants.

Grid dimensions, cell value range, timer length, and the target rectangle sum
live here so they are named in exactly one place rather than scattered as magic
numbers through the engine, solver, and UI (SPEC.md section 2, section 7).
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
