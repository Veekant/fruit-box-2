"""Smoke tests for the package skeleton and config constants (issue #1).

These assert only that the scaffolding is importable and that ``config`` exposes
the named constants with sane values. Behavioural tests for engine/solver/ui
arrive with those modules in later issues.
"""

import importlib


def test_top_level_package_imports():
    assert importlib.import_module("fruitbox") is not None


def test_subpackages_import():
    for name in ("fruitbox.engine", "fruitbox.solver", "fruitbox.ui"):
        assert importlib.import_module(name) is not None


def test_config_grid_dimensions():
    from fruitbox import config

    assert config.GRID_ROWS == 10
    assert config.GRID_COLS == 17


def test_config_cell_value_range():
    from fruitbox import config

    assert 1 <= config.MIN_CELL_VALUE < config.MAX_CELL_VALUE <= 9


def test_config_timer_seconds_positive():
    from fruitbox import config

    assert config.TIMER_SECONDS > 0


def test_config_target_sum():
    from fruitbox import config

    assert config.TARGET_SUM == 10
