"""Solver/analyzer: move enumeration, ranking, search, and board analysis.

Depends on ``fruitbox.engine`` only, never on ``fruitbox.ui``, so it stays
usable headlessly from the CLI with no display (SPEC.md section 7, NFR1a).
``move_scanner`` (legal-move enumeration) has landed; ``strategies``,
``search``, and ``analyzer`` land in later issues.
"""
