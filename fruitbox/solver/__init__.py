"""Solver/analyzer: move enumeration, ranking, search, and board analysis.

Depends on ``fruitbox.engine`` only, never on ``fruitbox.ui``, so it stays
usable headlessly from the CLI with no display (SPEC.md section 7, NFR1a).
``move_scanner`` (legal-move enumeration), ``strategies`` (single-step move
ranking), and ``analyzer`` (greedy playout) have landed; ``search`` and the
rest of ``analyzer`` (bounded search, full-clear analysis) land in later
issues.
"""
