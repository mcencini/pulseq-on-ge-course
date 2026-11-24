# %% [markdown]
# # 03b · Risk #3: TRID placement in an MPRAGE
#
# An MPRAGE shot is a recovery delay, a non-selective inversion, an
# inversion delay (TI), then a train of short spoiled gradient-echo TRs. The
# whole shot repeats once per kz, so one TRID per shot is a valid choice:
# every shot has the same blocks.
#
# Valid is not the same as efficient. A segment is loaded into the
# sequencer's waveform memory as a whole, and the instructions it needs grow
# with the number of blocks in it. A shot holds the full readout train; in
# a clinical protocol that is a few hundred TRs, and it may not fit.
#
# This notebook compares three placements on the same MPRAGE.

# %%
#INCLUDE _setup.py

# %% [markdown]
# `mprage` builds the sequence (reduced to 64 × 64 × 16 so that the checks
# run quickly). It takes a function `choose_trid(kind)` that returns the TRID
# for each kind of block, or None for no label. The kinds, in the order they
# are played in a shot, are:
#
# | kind | block |
# |---|---|
# | `"recovery"` | pure delay that completes the shot TR |
# | `"inversion"` | inversion pulse (followed by a spoiler and the TI delay) |
# | `"readout"` | first block of every readout TR |

# %%
from pgecourse.sequences.mprage import mprage

# %% [markdown]
# ## Case A: one TRID per shot
#
# A TRID on the first block of every shot only:

# %%
report_a = ge.from_seq(mprage(lambda kind: 1 if kind == "recovery" else None))
print(report_a)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# Every check passes. The segment holds 260 blocks: the recovery delay,
# the inversion, the TI delay and 64 readout TRs, all loaded at once. With a
# clinical matrix (for example 256 phase encodes per shot) the same segment
# would hold more than 1000 blocks.
#
# Yet only 6 of them are different (the base blocks): the readout TR is the
# same 4 base blocks repeated. Give the readout TR its own segment, and the
# sequencer holds 4 blocks instead of 256.

# %% [markdown]
# ## Your turn
#
# 1. Write a `choose_trid` that gives two segments: the preparation
#    (recovery, inversion, TI) and one readout TR.
# 2. Then three segments: the recovery delay on its own, the inversion with
#    its TI delay, and the readout TR.
#
# For each, check the number of blocks per segment in the report, and that
# `pge2.check` and `pge2.validate` pass.

# %% tags=["raises-exception"]
def choose_trid(kind):
    ...  # TODO


report = ge.from_seq(mprage(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
TWO = {"recovery": 1, "inversion": None, "readout": 2}
THREE = {"recovery": 1, "inversion": 2, "readout": 3}

for placement in (TWO, THREE):
    report = ge.from_seq(mprage(placement.get))
    print(report)
    print(ge.check())
    print("pge2.validate:", ge.validate())
    print()

# %% [markdown]
# With two TRIDs the largest segment is the 4-block preparation; the
# readout TR is a 4-block segment played 1024 times. The third TRID makes the
# recovery delay a pure delay segment of its own (layout `d`), so the shot TR
# can be changed through that delay alone.

# %% [markdown]
# ## Take-home
#
# - One TRID per shot is valid, but the segment grows with the readout train
#   and may exceed the sequencer's instruction memory.
# - Give each kind of TR its own TRID: preparation, readout TR, and long
#   waits as pure delay segments.
# - The number of base blocks does not change between placements; only the
#   size of the segments does.
