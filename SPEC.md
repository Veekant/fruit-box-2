# Fruit Box Clone + Solver — Software Specification

## 0. Document Purpose

This is a build specification intended to be read by an AI coding agent (Claude Code) or a human developer implementing this project from scratch. It defines scope, architecture, and data structures. It intentionally favors simplicity over generality — this is a solo-developer, small-to-medium sized project, not a platform.

---

## 1. Product Overview

**Fruit Box** is a puzzle game played on a grid of cells, each containing a digit 1–9. The player draws rectangular selections over axis-aligned, contiguous groups of cells. If the sum of the digits inside the rectangle equals exactly 10, all apples in that rectangle are removed (cells become empty but remain part of the grid — they do not shift or collapse). The player scores points per apple removed. The game is typically played against a timer (e.g. 100 seconds), and the objective is to clear as many apples as possible before time runs out.

This project has two deliverables:

1. **A playable clone** — a pygame desktop application that reproduces the core mechanic: click-drag rectangle selection, sum validation, removal, scoring, timer, win/loss state.
2. **A solver/analyzer** — a separate, decoupled Python package that operates on a board state (independent of pygame) and can:
   - Enumerate all legal moves on a given board.
   - Determine whether a board is fully solvable (can every apple be removed via some sequence of valid moves).
   - Rank/recommend moves at a given state according to pluggable heuristics or search strategies.
   - Optionally play out a full game and report the move sequence and the number of moves used.

The solver's notion of "efficiency" is strictly **number of moves used**, never wall-clock time — the timer in the playable clone is a UI/human-facing concept only and has no bearing on how the solver reasons about a board (see §9). The solver is explicitly designed to start simple (greedy heuristics) and support incremental upgrades (lookahead, search, pruning) without rewriting the interface.

**The solver must be usable from both surfaces, not just one**: (a) inside the pygame UI, via the hint feature (FR13) and any auto-solve toggle; and (b) headlessly via a CLI (FR19), for running the solver against a board with no display and printing results directly. Both surfaces call into the same `solver` package — the UI and CLI are two thin front ends over identical solver functions, never separate solver logic.

---

## 2. Game Rules and Assumptions

- Grid size: 17 columns × 10 rows (170 cells), matching the original Fruit Box layout. Grid dimensions should be a configurable constant, not hardcoded throughout — but 17×10 is the default and only officially supported size for the MVP.
- Each cell contains an integer 1–9, generated randomly (uniform, independent), **with one added constraint**: the total sum of all 170 values must be a multiple of 10 (a necessary condition for the board to be fully clearable at all, since every move removes a subset summing to 10 — a non-multiple-of-10 total makes a full clear provably impossible before a single move is made). See FR1 for the generation algorithm. A fixed seed/board may be supplied for reproducibility, bypassing generation entirely.
- A **move** is defined by a rectangle: a contiguous, axis-aligned block of cells specified by (row_start, col_start, row_end, col_end).
- **Empty cells count as zero.** A rectangle may freely span both occupied and already-empty cells — there is no requirement that every cell in the rectangle be occupied. An empty cell simply contributes 0 to the rectangle's sum. This matches real Fruit Box play (experienced players routinely drag selections through empty space to reach a sum of 10) and has a useful implementation consequence: since removed apples become 0 and empty cells are already 0, the grid of current values doubles as its own occupancy record — **no separate occupancy mask is needed** (see §8).
- A move is **legal** if and only if:
  - The rectangle lies entirely within grid bounds.
  - The sum of the current values of all cells in the rectangle (occupied cells at their value, empty cells counted as 0) equals exactly 10.
- Degenerate rectangle shapes: 1×1 cells and 1×N/N×1 lines are valid `Move` *shapes* (the rectangle abstraction does not impose a minimum size). In practice a 1×1 cell can never be legal, since a single cell's value is either 0 (empty) or 1–9, never 10 — this is enforced naturally by the sum check, not by a special-cased size rule, and should be covered by an explicit test case (see §10).
- When a move is executed, every cell in the rectangle that was still occupied (nonzero) becomes 0; already-empty cells caught inside the rectangle are simply left at 0 (a no-op for them). **Apples do not fall, shift, or refill.** The grid is static in shape; only cell values change (nonzero → 0).
- Score: 1 point per apple actually removed by a move — i.e., the count of cells inside the rectangle that were nonzero *before* the move, not the rectangle's total cell count (flat scoring; see §5.1 FR3 and §12 for alternate scoring as a future possibility).
- Time limit: default 100 seconds (configurable). This is a **UI-only** concept — the solver/analyzer never reasons about wall-clock time; its sole efficiency metric is the number of moves used (see §9).
- A board is **solvable** only if a move sequence exists that clears *all 170 cells*. Partial clears do not count as "solved," but the maximum number of apples clearable from a given board is still a useful, separately-tracked metric for boards that aren't fully solvable (see §9.4).
- **Assumption**: the board is static once generated (no new apples appear during play). This matches the real game.

---

## 3. MVP Scope

The MVP should be playable and demonstrably useful end-to-end. It includes:

1. Board generation (random, seedable).
2. Pygame UI: render grid, click-and-drag rectangle selection, live sum preview, valid/invalid selection highlighting, apple removal animation (can be instant — simple fade or just disappearance), score display, countdown timer, game-over screen.
3. Core game engine (pure Python, no pygame dependency) that pygame UI calls into: apply_move, is_legal_move, get_state, reset.
4. Solver v1: brute-force **legal move enumerator** (finds all valid rectangles at a given state) + a **greedy heuristic move ranker** (e.g., prefer moves that remove the most apples, or prefer moves involving cells nearer to already-sparse areas — heuristic choice documented in code).
5. Solver mode available from **both** the UI and the CLI (see §1): the UI displays/highlights the solver's top-ranked suggested move on request (hint); the CLI can run the solver's greedy strategy against a board headlessly and report the resulting move sequence and stats.
6. Basic automated tests for engine and solver (see §10).
7. A simple CLI entry point to run: (a) the game, (b) the solver against a board and print results, headless.

---

## 4. Explicitly Excluded Features (Non-Goals)

To keep scope controlled, the following are **out of scope** for this project unless explicitly revisited later:

- Networked/multiplayer play.
- Leaderboards, accounts, on-disk/cross-session persistence of any kind (a high score is tracked in-memory for the current session only — see FR13a — but is not written to disk).
- Apple "falling"/gravity mechanics (not part of real Fruit Box rules — grid is static).
- Grid sizes other than 17×10 as a first-class supported configuration (code should not hardcode it, but no UI for arbitrary sizes is required).
- Mobile/touch support, web deployment, packaging as an installable binary.
- A provably optimal solver (see §9 — this is NP-hard; true optimality is not a project goal).
- Undo/redo, replay system, move history scrubbing.
- Sound effects/music (nice-to-have stretch only).
- Difficulty levels, power-ups, or any mechanic not in the original Fruit Box.
- Animations beyond simple visual feedback (no particle systems, physics, etc).

---

## 5. Functional Requirements

### 5.1 Game Engine (pygame-independent)
- FR1: Generate a new board of configurable dimensions with random integers 1–9 per cell, optionally seeded for reproducibility, using the following algorithm to guarantee the total sum is a multiple of 10:
  1. Generate the first `rows*cols - 2` cells uniformly at random from 1–9.
  2. Compute `needed = (-running_sum) mod 10` — the residual the final two cells must contribute.
  3. Pick the second-to-last cell uniformly at random from 1–9; compute the last cell as the value in 1–9 satisfying `(second_to_last + last) mod 10 == needed`. If no valid `last` value in range 1–9 exists for the chosen `second_to_last` (this can happen since `last` would need to be 0 or 10), re-roll `second_to_last` and retry — this converges in a handful of attempts at most, since at least one of the 9 possible `second_to_last` values will always yield a valid `last`.
  This keeps generation uniform-random in spirit (no board-quality filtering, no guarantee of solvability) while enforcing the one necessary precondition for a full clear to even be theoretically possible.
- FR2: Given a board state and a candidate rectangle, determine legality (bounds check, sum check — sum is computed over the rectangle's current cell values, with empty cells contributing 0; no separate occupancy check is needed, see §2).
- FR3: Apply a legal move: set every still-occupied (nonzero) cell in the rectangle to 0 in place; update score by the count of cells that were actually nonzero before the move (not the rectangle's total area). `BoardState` must also support `copy()` so callers (notably the solver) can branch into hypothetical futures without disturbing the original state.
- FR4: Report current state: grid values (0 = empty), score, count of apples remaining (count of nonzero cells).
- FR5: Report whether the board is in a terminal state (no cells remain).
- FR6: Support loading a board from a fixed layout (e.g., list of lists / file) for testing and reproducibility.

### 5.2 Pygame UI
- FR7: Render the grid: each occupied cell as a colored shape (e.g. a circle) with its digit centered on it; each empty cell left blank (nothing drawn there). An empty cell is visually distinct from an occupied one simply by having no shape drawn in it — no separate empty-cell fill or lines between individual cells are required. A thin border around the grid's outer boundary as a whole is drawn, to frame the play area.
- FR8: Support mouse click-drag to define a rectangular selection; the rectangle should snap to whole cells only.
- FR9: While dragging, display a three-way visual cue (e.g., color) derived from the live sum of the current selection (empty cells contribute 0, matching §2): one state while the sum is under 10 ("keep dragging"), one exactly at 10 (legal), and one over 10 (overshot). No numeric sum needs to be rendered — the three-way cue alone is strictly more informative than a binary legal/illegal indicator, since it tells the player which direction to adjust.
- FR10: On mouse release, if the selection is legal, apply the move and update the UI (removal, score). If illegal, discard the selection with no state change.
- FR11: Display running score and remaining time; on timer expiration or terminal board state, show a game-over/summary screen with final score.
- FR12: Provide a way to start a new game (new random board) and to reset the current board to its initial state.
- FR13 (solver integration): Provide a key/button to request "hint" — engine asks solver for its single top-ranked move (MVP shows exactly one candidate, not a ranked list — see §12 for multi-candidate hints as a future possibility) and highlights it on the grid. Must return sub-second (see NFR4a).
- FR13a: Track a high score for the current process/session only (updated whenever a game's final score beats the running session-best); reset is not required between games, but no on-disk persistence is needed for MVP (see §12).

### 5.3 Solver/Analyzer
- FR14: `find_legal_moves(state) -> list[Move]` — enumerate all currently legal rectangles. Must be correct and complete (see §9.1 for algorithmic approach).
- FR15: `rank_moves(state, moves, strategy, count=None) -> list[RankedMove]` — apply a pluggable per-move scoring/heuristic function to order legal moves from "best" to "worst" per the current strategy, optionally truncated to the top `count` results (all of them when `count` is omitted). Must support swapping strategies without changing the interface (see §9 Strategy design). The moves passed in are assumed to be legal already — they come from FR14 — and ranking does not re-validate them.
- FR16: `attempt_full_clear(state, budget) -> ClearResult` — best-effort determination of whether the board is fully solvable (see §9.4). "Solvable" means strictly a full clear of all cells; the function must not claim a proof of unsolvability, only "no full clear found within budget." `ClearResult` (the shared result type of FR16/FR17/FR18, defined in §9.4) carries the move sequence found plus the `final_state` those moves lead to; a full clear is recognised as `result.final_state.apples_remaining == 0`, and a **nonzero** remainder means only "search budget exhausted without finding a full clear" — never a proof that none exists. Because `final_state` is reported unconditionally, the best (maximum) apples-cleared count found during the search is always available as `state.apples_remaining - result.final_state.apples_remaining`, even when no full clear is found — a separately useful metric for boards that aren't fully solvable.
- FR17: `play_greedy(state, strategy=DEFAULT_STRATEGY) -> ClearResult` — repeatedly apply the top-ranked move from `rank_moves` until no legal moves remain. The playout runs on a `state.copy()`, so the caller's board is never mutated. Returns the same `ClearResult` as FR16 (see §9.4): the move sequence played and the resulting `final_state`. The headline numbers are derived rather than stored — `moves_used == len(result.moves)`, `apples_cleared == state.apples_remaining - result.final_state.apples_remaining` (well defined precisely because the input state is left untouched), and "fully cleared" is `result.final_state.apples_remaining == 0`. The ranking strategy is injected (defaulting to §9.2's `DEFAULT_STRATEGY`) so the CLI (FR19) and benchmark script can run any registered strategy through this one playout function rather than reimplementing the loop (NFR1a, NFR7). Move count is the primary efficiency metric the solver optimizes toward (see §9), not elapsed time.
- FR18: `play_lookahead(state, depth) -> ClearResult` — as FR17 (identical return shape, identical derived `moves_used` / `apples_cleared` / full-clear check, identical no-mutation-of-the-caller's-board contract) but choosing moves via limited-depth search rather than a single-step heuristic, aiming to minimize moves used to reach a full (or maximal) clear (stretch goal beyond MVP greedy solver, but interface should anticipate it — see §9.3). Sharing FR17's result type is the point: swapping a greedy playout for a lookahead playout must not change any caller's result-handling code.
- FR19: A CLI or script that takes a board (random or file-based), runs a chosen solver strategy, and prints the move sequence, apples-cleared count, moves used, and whether the board was fully cleared.

---

## 6. Non-Functional Requirements

- NFR1: **Modularity** — game engine, solver, and UI must be separable packages/modules with no circular dependencies. The solver must be importable and testable with zero pygame dependency.
- NFR1a: **Dual solver access** — every solver capability the project ships (hint, greedy playout, analysis) must be reachable from both the pygame UI and the standalone CLI, backed by the same underlying functions in `solver/`. Neither surface may implement its own copy of solver logic.
- NFR2: **Understandability** — target a single developer maintaining this. Favor plain functions and small classes over deep inheritance hierarchies, metaprogramming, or plugin frameworks. Docstrings and type hints throughout.
- NFR3: **Testability** — engine and solver logic must be unit-testable headlessly (no display, no event loop required).
- NFR4: **Performance** — legal move enumeration on a 17×10 board must run well under 1 second on commodity hardware (this is achievable — see §9.1 complexity analysis). UI must maintain interactive frame rates (30+ FPS) during selection dragging.
- NFR4a: **Hint latency** — a hint request (FR13) must resolve in **well under 1 second**, since its purpose is unsticking a player mid-game; this bounds the depth/beam-width constants usable for any lookahead used to generate a hint (a single-step `rank_moves` call trivially satisfies this; if lookahead is used for hints post-MVP, its budget must still fit this window).
- NFR4b: **Full-clear attempt latency** — `attempt_full_clear` (FR16) runs offline/on-demand (e.g., from the CLI or an "analyze this board" UI action, not on every frame) and may take up to **a few minutes** per board before giving up, since it's an analysis tool rather than an interactive one.
- NFR5: **Determinism for testing** — random board generation must accept a seed so tests and solver benchmarking are reproducible.
- NFR6: **Minimal dependencies** — Python standard library plus `pygame` for the UI and `pytest` for testing. Avoid adding numpy/scipy/etc. unless a concrete performance need arises; prefer plain lists/tuples given the small board size (170 cells).
- NFR7: **Incremental solver upgrade path** — the solver's move-ranking strategy must be swappable (e.g., function injection or a small strategy interface) so that a future smarter strategy does not require changing FR14/FR17's call sites.

---

## 7. Suggested Architecture / Modules

```
fruitbox/
├── engine/
│   ├── __init__.py
│   ├── board.py          # Board generation, state representation (single grid, 0 = empty)
│   ├── moves.py          # Move (rectangle) representation, legality checking
│   └── game.py           # GameEngine: ties board+moves together, scoring, terminal-state check
│
├── solver/
│   ├── __init__.py
│   ├── move_scanner.py   # find_legal_moves: prefix-sum based rectangle search
│   ├── strategies.py     # Pluggable move-ranking heuristics (greedy variants)
│   ├── search.py         # Lookahead / bounded search (post-MVP; stub interface in MVP)
│   └── analyzer.py       # ClearResult (moves + final_state), play_greedy, attempt_full_clear, play_lookahead — orchestration layer
│
├── ui/
│   ├── __init__.py
│   ├── app.py            # Pygame main loop, event handling
│   ├── renderer.py       # Drawing grid, cells, selection rectangle, HUD
│   └── input.py          # Mouse drag -> rectangle translation
│
├── cli.py                # Entry point: `python -m fruitbox.cli play|solve|benchmark` (its `benchmark` subcommand delegates to benchmark.py, never duplicates it — NFR1a)
├── benchmark.py          # Strategy comparison harness: `python -m fruitbox.benchmark`
├── config.py             # Grid dimensions, timer length, value range, constants
│
tests/
├── test_board.py
├── test_moves.py
├── test_game.py
├── test_move_scanner.py
├── test_strategies.py
└── test_analyzer.py
```

**Dependency direction**: `ui` depends on `engine` and `solver`. `solver` depends on `engine` (reads state, uses `Move`/legality helpers) but never on `ui`. `engine` depends on nothing else in this project. This keeps the solver and engine independently testable and reusable (e.g., in the CLI without pygame installed at all, if pygame import is deferred to `ui/`).

---

## 8. Data Structures

Keep these simple — plain dataclasses/namedtuples, no ORM-like abstractions.

```python
# engine/board.py
Grid = list[list[int]]   # grid[row][col] = current value; 0 means empty (never removed and refilled, or already removed)

@dataclass
class BoardState:
    grid: Grid            # mutated in place as moves are applied; occupied cells hold 1-9, empty/removed cells hold 0
    rows: int
    cols: int

    def copy(self) -> "BoardState":
        """Return an independent BoardState with its own grid (deep-copied
        row lists). Used by the solver before exploring a hypothetical move,
        so the original state is never disturbed by search/lookahead."""
        ...
```

```python
# engine/moves.py
@dataclass(frozen=True)
class Move:
    row_start: int
    col_start: int
    row_end: int    # inclusive
    col_end: int    # inclusive

    def cells(self) -> Iterator[tuple[int, int]]: ...
```

**Mutability decision (resolved)**: `BoardState` is **mutable**. `GameEngine.apply_move` and any solver-side move application mutate `grid` in place (zeroing removed cells) and update score, rather than returning a new object each time. `BoardState` must expose an explicit `copy()` method (a deep copy of the row lists, since it's the sole source of truth now that there's no separate occupancy mask). This keeps the hot path (UI render loop, greedy playouts) cheap — no allocation per move — while still giving the solver a safe way to branch: before exploring a hypothetical move during lookahead/search (§9.3, §9.4), the solver calls `state.copy()` and mutates the copy, leaving the original untouched. Solver code must **never** mutate a `BoardState` it does not own a copy of; this is the one discipline the mutable-state design requires and should be called out in code comments/docstrings on `apply_move` and `copy()`.

**Reset note**: because `BoardState.grid` is mutated destructively during play, `GameEngine` (not `BoardState` itself) is responsible for retaining whatever it needs to support "reset to initial state" (FR12) — e.g. holding onto the original seed and regenerating, or keeping a separate plain deep copy of the freshly-generated grid taken once at game start, outside of `BoardState`. This is a `GameEngine`-layer concern, not something `BoardState`/the solver needs to know about.

```python
# solver
@dataclass(frozen=True)
class RankedMove:
    move: Move
    score: float          # heuristic-dependent, higher = better
    apples_removed: int

# A strategy is just a function that scores ONE move against ONE state:
StrategyFn = Callable[[BoardState, Move], float]
```

**Strategy shape (resolved)**: a `StrategyFn` scores a *single* move, not a whole list. Ordering, `RankedMove` construction, and truncation belong to `rank_moves` — not to each strategy — so a new heuristic is a one-line scoring function with no sorting boilerplate to get wrong, and every strategy inherits identical ordering and tie-breaking behavior for free. `rank_moves(state, moves, strategy, count=None)` calls `strategy` once per move, wraps each result in a `RankedMove` (attaching the apples that move would actually remove, via `BoardState.count_apples`), sorts by `score` descending, and returns the top `count` — all of them when `count` is `None`. Ties keep the input order, which for moves taken straight from `find_legal_moves` is deterministic (§9.1). Note that `count` cannot avoid any *scoring* work: a black-box per-move scorer must be called on every move before the best one is knowable. It only avoids fully ordering results the caller is going to discard, which matters most for the single-move hint path (FR13).

Score representation: rectangle-sum queries use a 2D prefix-sum array (see §9.1) built directly from `grid`'s current values (empty cells are already 0, so they need no special handling), rebuilt or incrementally updated after each move — this is the key data structure enabling fast legal-move enumeration.

---

## 9. Solver Design

The spec explicitly separates four distinct concerns. **Do not conflate these in one function.**

### 9.1 Finding Legal Moves (`find_legal_moves`, implemented in `solver/move_scanner.py`, named to avoid shadowing Python's `enumerate` builtin)

This is a well-defined, tractable subproblem: enumerate every axis-aligned rectangle in the grid whose cell-value sum (empty cells counted as 0, per §2) equals exactly 10.

**Naive approach**: for every pair of corners (O(rows²·cols²) rectangles ≈ 17²×10² ≈ 28,900 candidates for the full grid), compute the sum in O(1) using a 2D prefix-sum array built directly from `grid`'s current values. No separate occupancy check is needed — empty cells are already 0 in `grid`, so the sum check alone determines legality. This is entirely feasible: ~29K O(1) checks is trivial for Python at interactive speed.

**Further pruning (optional, not required for MVP)**: since all values are positive (1-9), any rectangle can be grown in a scanning fashion with an early cutoff — once a partial sum from a fixed top-left corner exceeds 10, no further growth in that direction can be legal. This bounds practical enumeration far below the worst case. Not required for MVP given the small grid, but the MVP implementation includes it anyway: both cutoffs — stop extending the rectangle's right edge, and stop extending its bottom edge, once the running sum exceeds 10 — fall out naturally of the enumeration loop and cost nothing in clarity.

**Output**: a list of `Move` objects. This function must be *exhaustive and correct* — every solver capability downstream depends on it.

### 9.2 Ranking Individual Moves (`rank_moves` / strategies)

Given the current state and the full legal-move list, assign each move a score for a **single step** — no lookahead. This is where "which move is best right now" heuristics live. The solver's overall objective is minimizing the **number of moves** used to reach a full (or maximal) clear — never elapsed time (see §9). A strategy is a plain function scoring one move against one state (`StrategyFn`, §8); `rank_moves` owns applying it across the legal-move list, sorting, and truncating. Moves handed to `rank_moves` are assumed legal — it is fed the output of `find_legal_moves` (§9.1) — so neither it nor any strategy re-checks bounds or sums. Implement as swappable scoring functions, e.g.:

- `strategy_max_apples`: prefer moves that clear the most apples — it scores a move by the number of still-occupied cells its rectangle covers, **not** by the rectangle's area (a rectangle spanning already-cleared cells is worth only the apples it really removes). This is a reasonable single-step proxy for the move-count objective (fewer, larger moves tend toward fewer total moves), though it is not guaranteed optimal — a greedy large move can sometimes fragment the board and cost more moves overall than a smaller one would have.
- `strategy_min_apples`: prefer smallest/cheapest moves — the negation of `strategy_max_apples`'s score, so "higher is better" still holds (preserves optionality, sometimes better for full-clear rate, at the cost of using more moves along the way).
- `strategy_edge_preference`: prefer moves along grid edges/corners (reduces future dead zones — an original-Fruit-Box community heuristic).
- `strategy_random`: baseline for benchmarking (a sanity floor) — ignores both of its arguments and returns a random float, so ranking produces a uniformly random order.

The MVP implements `strategy_max_apples`, `strategy_min_apples`, and `strategy_random`; the important design requirement is that they share a common function signature (`StrategyFn`) so they're interchangeable and testable independently, and so a benchmark script can compare them head-to-head (average moves used and clear rate over N random boards — see §10). A name → function registry (`STRATEGIES`) lets the CLI and benchmark script select one by string without importing each individually.

### 9.3 Looking Ahead at Future Board States (`play_lookahead`, `search.py`)

This is explicitly a **post-MVP, stretch** capability, but the interfaces above should be designed so it slots in without rework:

- A simple version: depth-limited minimax-style search with no adversary (single-agent, so effectively a bounded DFS/best-first search over move sequences), scored primarily by whether/how quickly (in move count) it reaches a full clear within the horizon, or by resulting number of remaining legal moves (a proxy for "keeping the board alive"). Elapsed wall-clock time is never part of the scoring — only move count and clear progress.
- A slightly smarter version: beam search — keep the top-K states at each depth rather than exhaustively expanding (controls the exponential blowup).
- This module should depend on `find_legal_moves` and `BoardState`, and should NOT need to know about strategies in §9.2 (though it may reuse a strategy as a leaf-node evaluation heuristic).
- Document expected complexity honestly: branching factor is the count of legal moves at each state (can be dozens early in the game), so full-depth search is infeasible; depth and/or beam width must be small constants. If this module is ever used to power the in-game hint (FR13), its constants must be tuned to fit the sub-second budget in NFR4a; the offline `attempt_full_clear` path (§9.4) has much more room (NFR4b) and can use larger constants.

### 9.4 Determining an Optimal Solution / Solvability (`attempt_full_clear`, `analyzer.py`)

**Explicitly acknowledge in code comments and docs**: determining whether a board can be *fully cleared*, and finding the move sequence that clears it in the fewest moves, is combinatorially explosive — closely related to exact cover / set packing style problems, which are NP-hard in general. This project does **not** aim to solve this exactly for a full 170-cell board.

A board is **solvable** strictly if a sequence exists clearing all 170 cells — there is no partial-credit definition of "solvable." However, for boards that are not (or not provably) fully solvable, the **maximum number of apples clearable** is still a useful, separately-reported metric, since most randomly-generated boards likely won't be fully clearable and "how good can we do anyway" is the practically interesting question.

What IS in scope:
- A **best-effort** `attempt_full_clear(state, budget) -> ClearResult` implemented via the same bounded/beam search as §9.3, clearly documented as a heuristic approximation, not a guarantee. `ClearResult` is the single result type shared by every playout/analysis entry point (FR16, FR17, FR18) and carries exactly **two** fields:
  - `moves: list[Move]` — the move sequence played or found, in the order applied. For `attempt_full_clear` this doubles as the *certificate*: if it clears the board, replaying it proves the board clearable.
  - `final_state: BoardState` — the board those moves lead to. It is a board the result **owns**, always produced from `state.copy()`, never the caller's own object; no analysis or playout call may mutate the board it was handed.
  - Everything else is **derived, never stored**, so a `ClearResult` can never contradict itself:
    - fully cleared ⇔ `result.final_state.apples_remaining == 0`;
    - `moves_used` == `len(result.moves)` — the headline efficiency number per §9's move-count objective;
    - apples cleared == `state.apples_remaining - result.final_state.apples_remaining`, well defined because the input state is left untouched. This is the number that answers "how many apples can we clear from this board" even when no full clear was found, and it is available unconditionally.
  - **A nonzero `result.final_state.apples_remaining` means "search budget exhausted without finding a full clear" — NOT a proof of unsolvability.** Deriving this check rather than storing a `found_full_clear` flag does not weaken the caveat: the derived check is exactly as non-committal as the flag was, and it must still be documented on `attempt_full_clear` and honored by everything that consumes a `ClearResult` (e.g. the CLI, §5.3 FR19), which must never print or imply "this board is unsolvable" — only "no full clear found within budget."
  - `ClearResult` is a frozen dataclass, but note it is *not* deeply immutable (`moves` is a list; `final_state` is a mutable `BoardState`) and is therefore not hashable at runtime; treat a returned result as read-only.
- Optionally, for small sub-boards or truncated grids (useful for tests), exhaustive search may actually be tractable — this is a good place for correctness tests of the search machinery itself.
- A benchmark/analysis script that runs the chosen strategy across many random boards and reports statistics (average apples cleared, average `best_apples_cleared`, % of boards fully cleared, average moves used) — this is the practical "how good is our solver" measurement, and is more valuable to build than chasing true optimality.

---

## 10. Testing Strategy

All engine and solver tests should run headlessly with `pytest`, no pygame/display required.

- **Board/engine tests**: fixed small hand-authored boards (e.g., 3×3 or 4×4) with known legal moves, to test:
  - Legality checks (bounds, sum correctness) — including deliberately illegal cases (sum ≠ 10, out-of-bounds), and a deliberately *legal* case where the selected rectangle spans one or more already-empty (0) cells alongside occupied ones, confirming they contribute 0 without breaking legality.
  - `apply_move` correctly zeroes out only the cells that were nonzero before the move, updates score by that count (not the rectangle's full area), and leaves already-empty cells and cells outside the rectangle alone.
  - Terminal-state detection (no legal moves left) on a constructed "stuck" board.
- **Enumeration tests**: on small fixed boards, assert `find_legal_moves` returns the exact expected set of rectangles (order-independent comparison). Include an edge case with zero legal moves, one with overlapping candidate rectangles, and one where a legal rectangle spans empty cells.
- **Strategy tests**: given a fixed state and legal move list, assert a given strategy orders moves as expected (e.g., `strategy_max_apples` puts the move removing the most apples first — including a case where that is *not* the largest-area rectangle, because a larger rectangle spans already-cleared cells).
- **Analyzer tests**: on a small hand-crafted fully-clearable board, assert `attempt_full_clear`/`play_greedy` finds a full clear within a small budget; on a hand-crafted unclearable board, assert it correctly reports no full clear found (and does not falsely claim a proof of unsolvability beyond what's documented).
- **Property-based / randomized checks** (optional but recommended, plain `random` + seeds is enough — no need for `hypothesis` unless already comfortable with it): generate N random seeded boards, run `find_legal_moves`, and assert every returned move independently re-validates as legal via the low-level legality checker (cross-check two independent code paths against each other).
- **UI**: manual/smoke testing is acceptable for pygame rendering itself (visual correctness is hard to unit test meaningfully); however, the *translation* of mouse-drag pixel coordinates into a grid rectangle (`input.py`) should be a pure function and unit-tested with synthetic coordinates.
- **Benchmark script** (not a pass/fail test, but part of the testing/validation story): run each strategy over e.g. 100 freshly-generated, unseeded random boards — the same board population for every strategy within one run, for a fair comparison, but not reproducible run-to-run — and report min/max/mean apples cleared and moves used — useful both for validating the solver behaves sensibly and for demonstrating engineering rigor.

---

## 11. User Interface Requirements

- Grid rendered with no lines between individual cells (a thin border frames the grid's outer boundary as a whole) — each occupied cell shown as a colored circle with its digit centered; empty cells are left blank (nothing drawn), which is what makes them visually distinct from occupied cells.
- Click-and-drag defines a selection rectangle that snaps to cell boundaries (no partial-cell selection).
- Real-time feedback during drag: a distinct fill/border color state for each of three cases, based on the selection's running sum (empty cells contribute 0, and a legal selection may freely span them) — under 10 ("keep dragging"), exactly 10 (legal), over 10 (overshot) — this is the core game-feel requirement and should not be skipped. The numeric sum itself is not displayed; the three-way color cue is the sole feedback channel and is strictly more informative than a binary legal/illegal indicator, since it also tells the player which direction to adjust.
- On release: legal selections clear immediately; illegal selections simply vanish with no penalty (matches original game feel — no penalty for a "bad" attempt).
- HUD: current score, session high score, time remaining, apples remaining count.
- Game-over screen: final score, apples cleared / total, session high score, option to restart.
- Hint feature (FR13): a keypress or button that highlights the solver's single top-ranked current move (e.g., draw its rectangle outline in a distinct color) without auto-applying it — the player chooses whether to take it. MVP shows one candidate only; multiple ranked candidates are a later feature (see §12).
- Optional/stretch: an "auto-solve" toggle that watches the greedy solver play itself out, for demo purposes.
- Keep visuals simple: solid colors, basic shapes, system or bundled font. No asset pipeline needed (no sprites required — colored circles/squares with numbers are sufficient and thematically fine).

---

## 12. Future Development Possibilities

(Explicitly deferred — listed to show the architecture accommodates them, not to be built now.)

- Smarter lookahead: Monte Carlo tree search or beam search with learned/tuned evaluation functions.
- Difficulty-aware board generation (e.g., biasing toward boards with a known high maximum-clear percentage).
- A "solvability score" displayed in the UI in real time as a player plays (how many apples the solver believes are still clearable from the current state).
- Replay/move-history export for sharing interesting boards or solutions.
- Alternate grid sizes / custom board import (e.g., paste in a board from a screenshot / OCR — well outside MVP).
- Web port (e.g., via pygbag) if desired later — architecture's UI/engine separation makes this more feasible without a full rewrite.
- Comparing solver strategies statistically over large randomized benchmarks and visualizing results (a small data-analysis side-project layered on top of `analyzer.py`).
- Alternate scoring rules (e.g., weighting by rectangle size/apple count per move, combo/streak bonuses, time-remaining bonuses) — MVP scoring is a flat 1 point per apple; revisit only if a richer scoring model becomes motivating.
- Multi-candidate hints — showing the top 2–3 ranked moves instead of a single top pick (MVP hint shows exactly one).
- On-disk persistence of high scores, last-used seeds, or settings across process restarts (MVP high score is session/in-memory only).

---

*End of specification.*