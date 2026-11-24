"""Timing helpers for the course notebooks.

The check chain itself (pulseg.fromSeq, pge2.check, pge2.validate,
pge2.serialize) is in pge2py.
"""

import numpy as np

#: Time the sequencer takes at the start and at the end of every segment
#: instance, in s (pge2.opts defaults: segment_dead_time,
#: segment_ringdown_time = SSI time + SSP pulse + end of sequence).
SEGMENT_DEAD_TIME = 12e-6
SEGMENT_RINGDOWN_TIME = 105e-6


def played_block_starts(seq):
    """Start time of every block as pge2 plays it, in s.

    Every segment instance (from one TRID label to the next) is played with
    ``SEGMENT_DEAD_TIME`` before its first block and
    ``SEGMENT_RINGDOWN_TIME`` after its last one, time that is not in the
    ``.seq`` file. Blocks before the first TRID label are counted from the
    start of the file.

    Parameters
    ----------
    seq : pypulseq.Sequence

    Returns
    -------
    numpy.ndarray
        One start time per block, in block order.
    """
    import numpy as np

    starts = []
    t = 0.0
    started = False
    for n in seq.block_events:
        labels = seq.get_block(n).label or {}
        if any(lab.label == "TRID" for lab in labels.values()):
            if started:
                t += SEGMENT_RINGDOWN_TIME
            t += SEGMENT_DEAD_TIME
            started = True
        starts.append(t)
        t += seq.block_durations[n]
    return np.array(starts)
