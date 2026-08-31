"""Pygame UI: main loop, rendering, and drag-to-rectangle input translation.

Depends on ``fruitbox.engine`` and ``fruitbox.solver``; nothing else in the
project may depend on this package (SPEC.md section 7). ``renderer`` (board
and HUD drawing), ``input`` (pixel-drag to grid-rectangle translation), and
``app`` (drag/timer/session state plus the pygame main loop) have all
landed. The game is runnable via ``python -m fruitbox.ui.app``.
"""
