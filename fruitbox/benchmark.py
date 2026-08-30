"""Strategy comparison harness (SPEC.md section 9.2, section 10).

Runs every registered strategy through :func:`~fruitbox.solver.analyzer.play_greedy`
over the same population of freshly-generated random boards and reports, per
strategy, the min/max/mean apples cleared and moves used. This is explicitly
**not a pass/fail test** (SPEC.md section 10) -- it is a demonstration/
validation tool, run manually via ``python -m fruitbox.benchmark``.

Contains no solving logic of its own (NFR1a): board generation comes from
``BoardState.generate_board``, playouts from ``play_greedy``, and strategy
selection from the ``STRATEGIES`` registry. This module only loops, derives
the headline numbers from a ``ClearResult`` plus the board it was given
(SPEC.md section 9.4's derived-never-stored pattern), aggregates, and
formats -- imports ``fruitbox.config``, ``fruitbox.engine``, and
``fruitbox.solver`` only, never ``fruitbox.ui``.

Move count is the only efficiency metric anywhere in this module; wall-clock
time is never measured or reported (SPEC.md section 9).

Boards are generated unseeded, so every run of this script sees a different
board population -- there is no ``--seed`` flag and no reproducibility
guarantee run-to-run. What *is* held constant is fairness **within** a run:
each board is generated once and that same ``BoardState`` object is handed
to every strategy in turn, so within a single invocation every strategy is
compared on an identical set of boards (a paired comparison), even though
that set itself is different on the next invocation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from .config import GRID_COLS, GRID_ROWS
from .engine.board import BoardState
from .solver.analyzer import play_greedy
from .solver.strategies import STRATEGIES, StrategyFn

#: Default number of boards benchmarked, matching SPEC.md section 10's
#: "e.g. 100 random boards".
DEFAULT_BOARD_COUNT = 100


@dataclass(frozen=True)
class BoardOutcome:
    """One strategy's result on one board.

    ``index`` identifies the board's position within this run (0-based, in
    generation order) -- boards are unseeded, so there is no seed to record;
    ``index`` is only for correlating a strategy's outcomes across boards
    within a single run, not for reproducing a board later.

    ``apples_total`` is the board's ``apples_remaining`` before the playout
    -- captured so ``apples_cleared`` is interpretable on its own ("cleared
    97 of 170") rather than requiring the reader to know the grid size.
    """

    index: int
    apples_total: int
    apples_cleared: int
    moves_used: int

    @property
    def fully_cleared(self) -> bool:
        """Whether this playout cleared every apple on the board."""
        return self.apples_cleared == self.apples_total


@dataclass(frozen=True)
class StrategySummary:
    """Aggregate statistics for one strategy over the boards it was run on."""

    name: str
    boards: int
    min_apples_cleared: int
    max_apples_cleared: int
    mean_apples_cleared: float
    min_moves_used: int
    max_moves_used: int
    mean_moves_used: float


def run_board(state: BoardState, strategy: StrategyFn, index: int) -> BoardOutcome:
    """Play ``state`` out under ``strategy`` and package the result (FR17).

    ``state`` is never mutated -- ``play_greedy`` plays on its own copy --
    which is what makes ``apples_cleared`` derivable from the before/after
    difference of ``state.apples_remaining``.

    Args:
        state: The board to play. Not mutated.
        strategy: The strategy ``play_greedy`` ranks moves with.
        index: Recorded on the returned ``BoardOutcome`` for traceability
            within this run; not used to generate ``state`` (the caller
            already did that).
    """
    apples_total = state.apples_remaining
    result = play_greedy(state, strategy=strategy)
    apples_cleared = apples_total - result.final_state.apples_remaining

    return BoardOutcome(
        index=index,
        apples_total=apples_total,
        apples_cleared=apples_cleared,
        moves_used=len(result.moves),
    )


def run_boards(
    strategies: dict[str, StrategyFn],
    count: int,
    rows: int = GRID_ROWS,
    cols: int = GRID_COLS,
) -> dict[str, list[BoardOutcome]]:
    """Run every strategy over the same population of freshly-generated boards.

    ``count`` boards are generated, each **once** and unseeded, and each
    same ``BoardState`` object is handed to every strategy in turn -- safe
    because ``play_greedy`` never mutates its input, and it means every
    strategy faces an identical board population within this run (a paired
    comparison) even though that population is different on the next run.

    Args:
        strategies: Name -> ``StrategyFn`` to run, e.g. a subset of
            ``STRATEGIES``. Iterated in dict order, so the returned dict's
            key order matches.
        count: Number of boards to generate.
        rows: Board row count for ``BoardState.generate_board``.
        cols: Board column count for ``BoardState.generate_board``.

    Returns:
        One list of ``BoardOutcome``, in generation order, per strategy name.
    """
    outcomes: dict[str, list[BoardOutcome]] = {name: [] for name in strategies}

    for index in range(count):
        board = BoardState.generate_board(rows=rows, cols=cols)
        for name, strategy in strategies.items():
            outcomes[name].append(run_board(board, strategy, index))

    return outcomes


def summarize(name: str, outcomes: list[BoardOutcome]) -> StrategySummary:
    """Aggregate one strategy's per-board outcomes into a ``StrategySummary``.

    Raises:
        ValueError: If ``outcomes`` is empty -- there is no meaningful
            min/max/mean over zero boards.
    """
    if not outcomes:
        raise ValueError(f"cannot summarize zero outcomes for strategy {name!r}")

    apples = [outcome.apples_cleared for outcome in outcomes]
    moves = [outcome.moves_used for outcome in outcomes]

    return StrategySummary(
        name=name,
        boards=len(outcomes),
        min_apples_cleared=min(apples),
        max_apples_cleared=max(apples),
        mean_apples_cleared=sum(apples) / len(apples),
        min_moves_used=min(moves),
        max_moves_used=max(moves),
        mean_moves_used=sum(moves) / len(moves),
    )


def run_benchmark(
    strategy_names: list[str] | None = None,
    boards: int = DEFAULT_BOARD_COUNT,
    rows: int = GRID_ROWS,
    cols: int = GRID_COLS,
) -> list[StrategySummary]:
    """Run the benchmark and return one summary per requested strategy.

    Args:
        strategy_names: Names to look up in ``STRATEGIES``. ``None`` (the
            default) runs every registered strategy, in registry order.
        boards: Number of boards to generate, unseeded -- every call sees a
            fresh, different board population.
        rows: Board row count.
        cols: Board column count.

    Returns:
        One ``StrategySummary`` per requested strategy, in the order given
        (or registry order, if ``strategy_names`` is ``None``).
    """
    names = list(STRATEGIES) if strategy_names is None else strategy_names
    strategies = {name: STRATEGIES[name] for name in names}

    outcomes = run_boards(strategies, boards, rows=rows, cols=cols)

    return [summarize(name, outcomes[name]) for name in names]


def format_report(
    summaries: list[StrategySummary],
    *,
    boards: int,
    rows: int,
    cols: int,
) -> str:
    """Render ``summaries`` as a fixed-width comparison table (a string, not printed)."""
    lines = [
        f"Benchmark: {len(summaries)} strategies x {boards} boards "
        f"(freshly generated, unseeded), grid {rows}x{cols}, playout: play_greedy",
        "Note: boards are regenerated every run -- results are not reproducible run-to-run,",
        "but every strategy above was compared on the same set of boards this run.",
        "",
        f"{'':<12}{'':>8}{'apples cleared':>24}{'moves used':>22}",
        f"{'strategy':<12}{'boards':>8}{'min':>8}{'mean':>8}{'max':>8}{'min':>8}{'mean':>8}{'max':>8}",
        "-" * 68,
    ]
    for s in summaries:
        lines.append(
            f"{s.name:<12}{s.boards:>8}"
            f"{s.min_apples_cleared:>8}{s.mean_apples_cleared:>8.2f}{s.max_apples_cleared:>8}"
            f"{s.min_moves_used:>8}{s.mean_moves_used:>8.2f}{s.max_moves_used:>8}"
        )

    return "\n".join(lines)


def _positive_int(value: str) -> int:
    """argparse ``type=`` callable: a clean usage error instead of a runaway/empty run."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {parsed}")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m fruitbox.benchmark",
        description="Compare solver strategies over freshly-generated random boards (SPEC.md section 9.2, section 10).",
    )
    parser.add_argument(
        "--boards",
        type=_positive_int,
        default=DEFAULT_BOARD_COUNT,
        help=f"number of boards to run per strategy (default: {DEFAULT_BOARD_COUNT})",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=list(STRATEGIES),
        default=None,
        help="strategies to run (default: all registered strategies)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    summaries = run_benchmark(
        strategy_names=args.strategies,
        boards=args.boards,
    )
    print(
        format_report(
            summaries,
            boards=args.boards,
            rows=GRID_ROWS,
            cols=GRID_COLS,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
