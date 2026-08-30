"""Pygame UI: main loop, rendering, and drag-to-rectangle input translation.

Depends on ``fruitbox.engine`` and ``fruitbox.solver``; nothing else in the
project may depend on this package (SPEC.md section 7). ``renderer`` (board
and HUD drawing) and ``input`` (pixel-drag to grid-rectangle translation)
have landed; ``app`` currently holds drag state tracking and FR10 move
application, with the pygame main loop still to come in a later issue.
"""
