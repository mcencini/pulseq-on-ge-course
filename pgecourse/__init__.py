"""Helpers for the Pulseq on GE (pge2) course notebooks.

The check chain (pulseg and pge2) is in pge2py: ``pge2py.GE``.
"""

from .timing import SEGMENT_DEAD_TIME, SEGMENT_RINGDOWN_TIME, played_block_starts

__all__ = ["SEGMENT_DEAD_TIME", "SEGMENT_RINGDOWN_TIME", "played_block_starts"]
