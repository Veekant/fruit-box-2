# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains only [SPEC.md](SPEC.md) — a complete build specification. No code has been written yet. There is no `pyproject.toml`, `requirements.txt`, or source tree. When implementing, follow SPEC.md's architecture exactly rather than improvising a different structure; it was written specifically to be handed to an AI coding agent and is detailed and prescriptive by design.

**Before writing code, (re-)read SPEC.md in full** — it is the source of truth for rules, data structures, module boundaries, and function signatures. The summary below is a navigation aid, not a replacement.

## What this project is

A clone of the puzzle game **Fruit Box** (drag a rectangle over grid cells whose digits sum to exactly 10 to clear them) plus a decoupled **solver/analyzer** that reasons about board states independent of the game UI. Two deliverables, one repo:
1. A pygame desktop game.
2. A `solver` package usable both as an in-game hint and headlessly via CLI — never two separate implementations of solving logic (NFR1a).

## Architecture (from SPEC.md §7)

```
fruitbox/
├── engine/     # pure Python, zero pygame dependency: board state, move legality, scoring
├── solver/     # depends on engine only, never on ui: move enumeration, ranking, search, analysis
├── ui/         # pygame main loop, rendering, input translation — depends on engine + solver
├── cli.py      # `python -m fruitbox.cli play|solve|benchmark` — thin front end over engine+solver
├── config.py   # grid dimensions, timer length, value range — no magic numbers scattered elsewhere
tests/          # headless pytest, no display required
```

**Dependency direction is one-way and load-bearing**: `engine` depends on nothing else in the project; `solver` depends only on `engine`; `ui` depends on both. Never let `solver` or `engine` import from `ui` — this is what keeps the solver usable from the CLI with no display and no pygame installed.

### Key design decisions to preserve

- **No separate occupancy mask.** `BoardState.grid` values double as occupancy: 0 means empty (never removed and refilled, or already removed), 1-9 means occupied. A rectangle sum is computed directly over current grid values; empty cells contribute 0 for free.
- **`BoardState` is mutable**, mutated in place by `apply_move` for a cheap hot path (UI render loop, greedy playouts). It exposes `copy()` (deep-copies row lists) for the solver to branch into hypothetical futures. Solver code must never mutate a `BoardState` it doesn't own a copy of.
- **The solver's efficiency metric is strictly move count, never wall-clock time.** The game's countdown timer is a UI-only concept with no bearing on solver logic. Don't let timing considerations leak into `solver/`.
- **Four distinct solver concerns, kept in separate modules** (SPEC.md §9): enumerating legal moves (`solver/move_scanner.py`, prefix-sum based), single-step move ranking (`solver/strategies.py`, pluggable `StrategyFn`), bounded lookahead (`solver/search.py`, post-MVP stub), and best-effort full-clear analysis (`solver/analyzer.py`, explicitly heuristic — this is NP-hard in general, not solved exactly).
- **`attempt_full_clear` never claims a proof of unsolvability.** `found_full_clear: False` means "search budget exhausted," not "impossible." Always report `best_apples_cleared` regardless of whether a full clear was found.
- **Board generation must guarantee total sum ≡ 0 (mod 10)** via the two-cell adjustment algorithm in SPEC.md §5.1 FR1 — this is a necessary precondition for full clearability and must stay seedable for reproducible tests/benchmarks.
- Strategy functions share one signature (`StrategyFn = Callable[[BoardState, list[Move]], list[RankedMove]]`) so they're swappable without touching call sites (NFR7).

## Testing approach (from SPEC.md §10)

- All engine/solver tests run headlessly via `pytest` — no display, no event loop.
- Use small hand-authored boards (3×3/4×4) with known legal moves for engine and enumeration tests, including deliberate edge cases: illegal sum, out-of-bounds, a legal rectangle spanning empty cells, zero legal moves available, a "stuck" terminal board.
- Cross-check `find_legal_moves` output against the low-level legality checker on randomized seeded boards as a consistency check between the two code paths.
- `ui/input.py` (pixel-drag → grid rectangle translation) should be a pure function, unit-tested with synthetic coordinates — the rest of the UI is smoke-tested manually.
- A benchmark script (not pass/fail) compares strategies over many seeded boards: average apples cleared, average moves used, % fully cleared.

## Performance constraints to respect

- Legal move enumeration over the full 17×10 board (~28,900 candidate rectangles) must stay well under 1 second — use a 2D prefix-sum array over `grid`, not per-rectangle summation.
- Hint requests (FR13) must resolve well under 1 second — bounds any lookahead depth/beam width usable for hints specifically.
- `attempt_full_clear` is an offline/on-demand analysis operation and may take up to a few minutes per board — do not conflate its budget with the hint-path budget.

## Working process

- For non-trivial changes, propose a plan first (files touched, ambiguities, testing approach) and wait for approval before writing code. Don't open PRs without explicit approval of the implementation.
- When working from a GitHub issue, use `/implement-issue <issue-number>` instead of improvising the workflow yourself — it runs the full plan → approve → implement → approve → PR flow, with the actual coding delegated to the `opus-coder` subagent (Opus) while planning and PR writeup stay on the lighter default model.
- Always read SPEC.md before proposing a plan or making architectural decisions — it's the source of truth for scope, data structures, and module boundaries. Don't rely on conversation history alone for this.
- Keep `engine/`, `solver/`, and `ui/` decoupled per SPEC.md §7 — the solver must never import from `ui/`, and both `ui/` and `cli.py` must call into the same `solver/` functions rather than each having their own logic (see SPEC.md NFR1a).