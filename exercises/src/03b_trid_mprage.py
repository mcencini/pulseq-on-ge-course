# %% [markdown]
# # 03b · Risk #3: TRID placement in an MPRAGE
#
# An MPRAGE shot is a non-selective inversion, an inversion delay (TI), a
# train of short spoiled gradient-echo TRs, and a recovery delay that
# completes the shot TR. The whole shot repeats once per kz, so one TRID per
# shot is a valid choice: every shot has the same blocks.
#
# Valid is not the same as efficient. A segment is loaded into the
# sequencer as a whole, and the instructions it needs grow with the number
# of blocks in it. A shot holds the full readout train; in a clinical
# protocol that is a few hundred TRs.
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
# | `"inversion"` | inversion pulse (followed by a spoiler and the TI delay) |
# | `"readout"` | first block of every readout TR |
# | `"recovery"` | pure delay that completes the shot TR |

# %%
from pgecourse.sequences.mprage import mprage

# %% [markdown]
# ## Case A: one TRID per shot
#
# A TRID on the inversion only:

# %%
report_a = ge.from_seq(mprage(lambda kind: 1 if kind == "inversion" else None))
print(report_a)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# Every check passes. The segment holds 260 blocks: the inversion, its
# spoiler and TI delay, 64 readout TRs and the recovery delay, all loaded at
# once. With a clinical matrix (for example 256 phase encodes per shot) the
# same segment would hold more than 1000 blocks.
#
# Yet only 6 of them are different (the base blocks): the readout TR is the
# same 4 base blocks repeated. Give the readout TR its own segment, and the
# sequencer holds 4 blocks instead of 256.

# %% [markdown]
# ## Case B: preparation and readout TR, recovery delay unlabelled

# %%
try:
    ge.from_seq(mprage(lambda kind: {"inversion": 1, "readout": 2}.get(kind)))
except pgecourse.PGE2Error as err:
    print("from_seq:", err)

# %% [markdown]
# Without a label, the recovery delay belongs to the segment of the last
# readout TR of the shot, which then has 5 blocks instead of 4. A segment
# instance cannot gain a block.

# %% [markdown]
# ## Your turn
#
# Write a `choose_trid` that gives three segments: the inversion with its
# TI delay, the readout TR, and the recovery delay. Check the number of
# blocks per segment in the report, and that `pge2.check` and
# `pge2.validate` pass.

# %% tags=["raises-exception"]
def choose_trid(kind):
    ...  # TODO


report = ge.from_seq(mprage(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
def choose_trid(kind):
    return {"inversion": 1, "readout": 2, "recovery": 3}[kind]


report = ge.from_seq(mprage(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# The largest segment now has 4 blocks; the readout TR is played 1024 times.
# The recovery delay is a pure delay segment (layout `d`), so the shot TR can
# be changed through that delay alone.

# %% [markdown]
# ## Take-home
#
# - One TRID per shot is valid, but the segment grows with the readout train
#   and may exceed the sequencer's instruction memory.
# - Give each kind of TR its own TRID, and long waits their own pure delay
#   segment.
# - The number of base blocks does not change between placements; only the
#   size of the segments does.
