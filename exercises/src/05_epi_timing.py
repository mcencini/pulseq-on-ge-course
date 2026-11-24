# %% [markdown]
# # 05 · Timing: an EPI train in one segment
#
# Same idea as notebook 04, on a single-shot 2D EPI with fat saturation. An EPI
# readout is a train of short lines; whatever is added between them adds up
# over the whole train.

# %%
#INCLUDE _setup.py

# %% [markdown]
# `epi` builds the sequence. It takes `choose_trid(kind)` with kinds
# `"excitation"` (fat saturation, first block of the TR), `"line"` (every
# readout line), `"spoiler"` and `"fill"`. With `packed=False` each phase blip
# is a block of its own between two readouts; with `packed=True` each blip is
# split in two halves played during the ramps of two consecutive readouts.

# %%
from pgecourse import played_block_starts
from pgecourse.sequences.epi import epi


def epi_timing(seq, n=64):
    """Echo spacing and excitation -> centre line, in the file and as played."""
    adc = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).adc is not None]
    rf = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).rf is not None]
    exc = rf[1]  # rf[0] is the fat saturation
    played = played_block_starts(seq)
    in_file = np.cumsum([0] + [seq.block_durations[k] for k in seq.block_events])[:-1]
    for name, t in (("file", in_file), ("played", played)):
        print(f"{name:>7}: echo spacing {1e6 * (t[adc[1]] - t[adc[0]]):.0f} us, "
              f"excitation -> centre line {1e3 * (t[adc[n // 2]] - t[exc]):.2f} ms")


# %% [markdown]
# ## Case A: one TRID per readout line

# %%
seq_a, esp_a = epi(lambda kind: {"excitation": 1, "line": 2, "spoiler": 3, "fill": 4}[kind])
print(ge.from_seq(seq_a))
print(ge.check())
print("pge2.validate:", ge.validate())
epi_timing(seq_a)

# %% [markdown]
# Every check passes. Each line is a segment instance, so each line is played
# 117 µs later than the one before it in the file. The centre of k-space is
# reached after 33 segment instances: TE grows by almost 4 ms, and the longer
# echo spacing lowers the bandwidth along the phase-encoding direction (more
# distortion).

# %% [markdown]
# ## Your turn
#
# 1. Put the whole TR, from fat saturation to spoiler, in one segment, with
#    the fill delay on its own. Compare the played timing with the file.
# 2. Then build it with `packed=True`. What happens to the echo spacing, the
#    number of blocks per segment and the number of base blocks?

# %% tags=["raises-exception"]
def choose_trid(kind):
    ...  # TODO


seq_b, esp_b = epi(choose_trid)
print(ge.from_seq(seq_b))
print(ge.check())
print("pge2.validate:", ge.validate())
epi_timing(seq_b)

# %% cellView="form"
# @title Solution (double-click to show the code)
def choose_trid(kind):
    return {"excitation": 1, "line": None, "spoiler": None, "fill": 2}[kind]


for packed in (False, True):
    seq_b, esp_b = epi(choose_trid, packed=packed)
    print(f"packed={packed}")
    print(ge.from_seq(seq_b))
    print(ge.check())
    print("pge2.validate:", ge.validate())
    epi_timing(seq_b)
    print()

# %% [markdown]
# In one segment the played timing is the file's. Packing the blips into the
# readout ramps removes the blip blocks: one block per line instead of two,
# 80 µs shorter echo spacing and about 2.6 ms shorter TE. The phase gradient is
# now non-zero at the block boundaries, so a packed EPI cannot be split per
# line at all. Plot a few lines:

# %%
seq_c, esp_c = epi(choose_trid, packed=True)
seq_c.plot(time_range=(0.0125, 0.0125 + 4 * esp_c))

# %% [markdown]
# ## Take-home
#
# - Put the whole EPI train in one segment; a segment boundary per line costs
#   117 µs per line and shifts TE.
# - Blips in the readout ramps (gradients across block boundaries) shorten the
#   echo spacing; they require the train to be one segment.
