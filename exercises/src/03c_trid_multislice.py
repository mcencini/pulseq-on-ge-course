# %% [markdown]
# # 03c · Risk #3: TRID placement in a multislice sequence
#
# An interleaved multislice gradient echo excites every slice in turn for
# each phase-encoding line, then waits until the TR is over. The slice is
# selected by the RF frequency, which can change between segment instances,
# so all slices can share one segment. The wait at the end of the TR is a
# pure delay.

# %%
#INCLUDE _setup.py

# %% [markdown]
# `multislice_gre` builds an 8-slice, 64-line sequence with TR = 200 ms. It
# takes a function `choose_trid(kind, s)` that returns the TRID for the
# first block of slice `s` (kind `"slice"`) or for the delay that fills the
# TR (kind `"fill"`, `s` is None), or None for no label.

# %%
from pgecourse.sequences.multislice import multislice_gre

# %% [markdown]
# ## Case A: a TRID on every slice, none on the fill delay
#
# Every slice excitation starts a segment, so the fill delay belongs to the
# segment of the last slice:

# %%
try:
    ge.from_seq(multislice_gre(lambda kind, s: 1 if kind == "slice" else None))
except pgecourse.PGE2Error as err:
    print("from_seq:", err)

# %% [markdown]
# Seven instances of TRID 1 have 4 blocks, the eighth has 5. A segment
# instance cannot gain a block, so the sequence is refused. (pulseg itself
# does not check this: it takes the segment length from the first instance.
# The course helper checks it before calling pulseg.)

# %% [markdown]
# ## Case B: one TRID per TR
#
# A TRID on the first slice only: all slices and the fill delay are one
# segment.

# %%
report_b = ge.from_seq(multislice_gre(lambda kind, s: 1 if (kind == "slice" and s == 0) else None))
print(report_b)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# This one is valid: 33 blocks per segment. But the segment is 8 copies of
# the same 4 base blocks, and changing the number of slices changes the
# segment itself.

# %% [markdown]
# ## Your turn
#
# Write a `choose_trid` that gives one segment per slice and a separate pure
# delay segment for the fill delay. Check that `pulseg.fromSeq` reports 2
# segments, with 512 and 64 instances, and that `pge2.check` and
# `pge2.validate` pass.

# %% tags=["raises-exception"]
def choose_trid(kind, s):
    ...  # TODO


report = ge.from_seq(multislice_gre(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
def choose_trid(kind, s):
    return {"slice": 1, "fill": 2}[kind]


report = ge.from_seq(multislice_gre(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# The slice segment has 4 blocks whatever the number of slices, and the fill
# delay is a segment of layout `d`. Its duration can change between
# instances, so TR can change without touching the slice segment.

# %% [markdown]
# ## Take-home
#
# - Waits that complete a TR (or a shot, or a TI) go in their own pure
#   delay segment.
# - A block that only some instances of a segment would have, like a fill
#   delay after the last slice, needs its own TRID.
