# %% [markdown]
# # 04 · Timing: an FSE echo train in one segment
#
# Inside a segment the sequencer plays the blocks back to back, and gradients
# may run across block boundaries. Between two segment instances it stops:
# the gradients must be at zero, and every instance costs extra time that is
# not in the `.seq` file (12 µs at its start and 105 µs at its end with the
# pge2 defaults, 117 µs in all).
#
# For a CPMG fast spin echo that matters: the echo spacing must be twice the
# time from the 90° to the first 180°. This notebook plays the same FSE three
# ways and compares the timing pge2 plays with the timing in the file.

# %%
#INCLUDE _setup.py

# %% [markdown]
# `fse` builds a 2D CPMG FSE with 8 echoes per shot. Like the MPRAGE of 03b,
# it takes a function `choose_trid(kind)`, with kinds `"excitation"` (the
# 90°), `"echo"` (every 180°) and `"fill"` (the delay that completes the TR).
# `packed=True` joins crusher, slice select and crusher into one gradient
# across the block boundaries.
#
# `pgecourse.played_block_starts(seq)` gives the start time of every block as
# pge2 plays it, with the 117 µs per segment instance added.

# %%
from pgecourse import played_block_starts
from pgecourse.sequences.fse import fse


def rf_blocks(seq):
    """Indices of the blocks that play an RF pulse."""
    return [i for i, n in enumerate(seq.block_events) if seq.get_block(n).rf is not None]


def cpmg_timing(seq):
    """90 to first 180, and first to second 180, in ms: in the file and as played."""
    r = rf_blocks(seq)
    played = played_block_starts(seq)
    in_file = np.cumsum([0] + [seq.block_durations[n] for n in seq.block_events])[:-1]
    for name, t in (("file", in_file), ("played", played)):
        print(f"{name:>7}: 90 -> 180 {1e3 * (t[r[1]] - t[r[0]]):.3f} ms, "
              f"echo spacing {1e3 * (t[r[2]] - t[r[1]]):.3f} ms")


# %% [markdown]
# ## Case A: one TRID per echo

# %%
seq_a, esp_a = fse(lambda kind: {"excitation": 1, "echo": 2, "fill": 3}[kind])
print(ge.from_seq(seq_a))
print(ge.check())
print("pge2.validate:", ge.validate())
cpmg_timing(seq_a)

# %% [markdown]
# Every check passes, but each echo is its own segment instance, played
# 117 µs longer than in the file. The 90° segment grows by 117 µs once; the
# echo spacing grows by 117 µs at every echo. The two no longer match, so the
# CPMG condition is broken and each echo forms away from the centre of its
# ADC window. No check reports it: the waveforms of every instance are right,
# only the time between instances is not.

# %% [markdown]
# ## Your turn
#
# 1. Write a `choose_trid` that puts the whole echo train in one segment
#    (excitation and echoes together, fill delay on its own). Check that the
#    played timing matches the file.
# 2. Build the same placement with `packed=True`. How much shorter is the echo
#    spacing, and where do the gradients cross block boundaries?

# %% tags=["raises-exception"]
def choose_trid(kind):
    ...  # TODO


seq_b, esp_b = fse(choose_trid)
print(ge.from_seq(seq_b))
print(ge.check())
print("pge2.validate:", ge.validate())
cpmg_timing(seq_b)

# %% cellView="form"
# @title Solution (double-click to show the code)
def choose_trid(kind):
    return {"excitation": 1, "echo": None, "fill": 2}[kind]


for packed in (False, True):
    seq_b, esp_b = fse(choose_trid, packed=packed)
    print(f"packed={packed}: echo spacing in the file {1e3 * esp_b:.3f} ms")
    print(ge.from_seq(seq_b))
    print(ge.check())
    print("pge2.validate:", ge.validate())
    cpmg_timing(seq_b)
    print()

# %% [markdown]
# With the train in one segment, the played timing is the file's timing.
# Packing the z gradient removes the ramps to and from zero around each slice
# select: 0.25 ms shorter per echo spacing. Plot the z gradient of a few echoes
# to see it run across the block boundaries:

# %%
seq_c, esp_c = fse(choose_trid, packed=True)
seq_c.plot(time_range=(0, 4 * esp_c))

# %% [markdown]
# ## Take-home
#
# - Everything whose relative timing matters (an echo train) goes in one
#   segment; every segment boundary adds time that is not in the file.
# - Inside a segment, gradients may run across block boundaries: join them
#   to save the ramps.
# - The packed train cannot be split per echo: its gradients are not zero at
#   the echo boundaries.
