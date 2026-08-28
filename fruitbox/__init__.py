"""Fruit Box clone: game engine, solver/analyzer, and pygame UI.

Subpackages:
    engine  -- pure-Python board state, move legality, scoring (no pygame).
    solver  -- move enumeration, ranking, search, analysis (depends on engine only).
    ui      -- pygame front end (depends on engine and solver).

See SPEC.md section 7 for the module layout and dependency direction.
"""
