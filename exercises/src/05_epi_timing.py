# %% [markdown]
# # 05 · Timing: an EPI train in one segment
#
# Same idea as notebook 04, on a single-shot 2D EPI with fat saturation. An EPI
# readout is a train of short lines; whatever is added between them adds up
# over the whole train.

# %%
#INCLUDE _setup.py

# %%
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
    grad_raster_time=4e-6,
    block_duration_raster=4e-6,
    B0=3.0,
)

# %% [markdown]
# ## Events
#
# Single-shot 2D gradient-echo EPI, 64 × 64, with fat saturation; 4
# repetitions, TR = 100 ms. Each phase blip is a block of its own between
# two readouts.

# %%
fov = 240e-3
n = 64
dwell = 4e-6
slice_thickness = 5e-3
tr = 0.1
repetitions = 4
R = system.grad_raster_time


def rup(t):
    """Round a time up to the gradient raster."""
    return np.ceil(round(t / R, 6)) * R


dk = 1 / fov
fat_offset = -3.35e-6 * system.B0 * system.gamma  # fat frequency (Hz)
fs = pp.make_gauss_pulse(
    np.deg2rad(110), duration=4e-3, bandwidth=abs(fat_offset), freq_offset=fat_offset,
    system=system, use="saturation",
)
g_fs = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)
rf, gz, _ = pp.make_sinc_pulse(
    np.pi / 2, duration=2e-3, slice_thickness=slice_thickness, time_bw_product=4,
    system=system, return_gz=True, use="excitation",
)
gx = pp.make_trapezoid("x", flat_area=n * dk, flat_time=n * dwell, system=system)
adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
blip_dur = max(
    rup(2 * np.sqrt(dk / system.max_slew)),
    pp.calc_duration(pp.make_trapezoid("y", area=-dk, system=system)),
)
gy = pp.make_trapezoid("y", area=-dk, duration=blip_dur, system=system)
t_pre = rup(max(
    pp.calc_duration(pp.make_trapezoid(ch, area=a, system=system))
    for ch, a in (("x", gx.area / 2), ("y", n / 2 * dk), ("z", gz.area / 2))
))
gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=t_pre, system=system)
gy_pre = pp.make_trapezoid("y", area=n / 2 * dk, duration=t_pre, system=system)
gz_reph = pp.make_trapezoid("z", area=-gz.area / 2, duration=t_pre, system=system)
g_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

esp = pp.calc_duration(gx) + blip_dur
before_train = pp.calc_duration(fs) + pp.calc_duration(g_fs) + pp.calc_duration(rf, gz) + t_pre
fill = rup(tr - (before_train + n * esp + pp.calc_duration(g_spoil)))
print(f"echo spacing in the file: {1e6 * esp:.0f} us")

TRID = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2, 3, 4)]

# %% [markdown]
# `epi_timing` prints the echo spacing and the time from the excitation to
# the centre line, in the file and as pge2 plays them
# (`pgecourse.played_block_starts` adds the 117 µs per segment instance).

# %%
from pgecourse import played_block_starts


def epi_timing(seq):
    """Echo spacing and excitation -> centre line, in the file and as played."""
    adc_blocks = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).adc is not None]
    rf_blocks = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).rf is not None]
    exc = rf_blocks[1]  # rf_blocks[0] is the fat saturation
    played = played_block_starts(seq)
    in_file = np.cumsum([0] + [seq.block_durations[k] for k in seq.block_events])[:-1]
    for name, t in (("file", in_file), ("played", played)):
        print(f"{name:>7}: echo spacing {1e6 * (t[adc_blocks[1]] - t[adc_blocks[0]]):.0f} us, "
              f"excitation -> centre line {1e3 * (t[adc_blocks[n // 2]] - t[exc]):.2f} ms")


# %% [markdown]
# ## Case A: one TRID per readout line

# %%
seq_a = pp.Sequence(system)
for _ in range(repetitions):
    seq_a.add_block(fs, TRID[0])
    seq_a.add_block(g_fs)
    seq_a.add_block(rf, gz)
    seq_a.add_block(gx_pre, gy_pre, gz_reph)
    g = gx
    for i in range(n):
        seq_a.add_block(g, adc, TRID[1])
        seq_a.add_block(gy if i < n - 1 else pp.scale_grad(gy, 0.0))  # last blip at zero: same blocks every TR
        g = pp.scale_grad(g, -1)  # alternate the readout polarity
    seq_a.add_block(g_spoil, TRID[2])
    seq_a.add_block(pp.make_delay(fill), TRID[3])

psq = pulseg.fromSeq(seq_a)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))
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
# Change the labels so that the whole TR, from fat saturation to spoiler, is
# one segment, with the fill delay on its own. Compare the played timing
# with the file.

# %%
seq = pp.Sequence(system)
for _ in range(repetitions):
    seq.add_block(fs, TRID[0])
    seq.add_block(g_fs)
    seq.add_block(rf, gz)
    seq.add_block(gx_pre, gy_pre, gz_reph)
    g = gx
    for i in range(n):
        seq.add_block(g, adc, TRID[1])  # TODO
        seq.add_block(gy if i < n - 1 else pp.scale_grad(gy, 0.0))  # last blip at zero: same blocks every TR
        g = pp.scale_grad(g, -1)  # alternate the readout polarity
    seq.add_block(g_spoil, TRID[2])  # TODO
    seq.add_block(pp.make_delay(fill), TRID[3])

psq = pulseg.fromSeq(seq)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))
epi_timing(seq)

# %% cellView="form"
# @title Solution (double-click to show the code)
seq = pp.Sequence(system)
for _ in range(repetitions):
    seq.add_block(fs, TRID[0])
    seq.add_block(g_fs)
    seq.add_block(rf, gz)
    seq.add_block(gx_pre, gy_pre, gz_reph)
    g = gx
    for i in range(n):
        seq.add_block(g, adc)
        seq.add_block(gy if i < n - 1 else pp.scale_grad(gy, 0.0))  # last blip at zero: same blocks every TR
        g = pp.scale_grad(g, -1)  # alternate the readout polarity
    seq.add_block(g_spoil)
    seq.add_block(pp.make_delay(fill), TRID[3])

psq = pulseg.fromSeq(seq)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))
epi_timing(seq)

# %% [markdown]
# In one segment the played timing is the file's.

# %% [markdown]
# ## Blips in the readout ramps
#
# Inside a segment the phase gradient need not be zero at block boundaries.
# Split each blip in two halves and play them during the ramps of two
# consecutive readouts, as in pypulseq's `write_epi`: one block per line, no
# blip blocks.

# %%
half = pp.split_gradient_at(grad=gy, time_point=blip_dur / 2, system=system)
up, down, _ = pp.align(right=half[0], left=[half[1], gx])  # end of one readout, start of the next
downup = pp.add_gradients((down, up), system=system)
blips = [up] + [downup] * (n - 2) + [down]

esp_packed = pp.calc_duration(gx)
fill_packed = rup(tr - (before_train + n * esp_packed + pp.calc_duration(g_spoil)))
print(f"echo spacing in the file: {1e6 * esp_packed:.0f} us (was {1e6 * esp:.0f} us)")

seq_c = pp.Sequence(system)
for _ in range(repetitions):
    seq_c.add_block(fs, TRID[0])
    seq_c.add_block(g_fs)
    seq_c.add_block(rf, gz)
    seq_c.add_block(gx_pre, gy_pre, gz_reph)
    g = gx
    for i in range(n):
        seq_c.add_block(g, adc, blips[i])
        g = pp.scale_grad(g, -1)
    seq_c.add_block(g_spoil)
    seq_c.add_block(pp.make_delay(fill_packed), TRID[3])

psq = pulseg.fromSeq(seq_c)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))
epi_timing(seq_c)

# %% [markdown]
# One block per line instead of two: 80 µs shorter echo spacing and about
# 2.6 ms shorter TE. The phase gradient is now non-zero at the block
# boundaries, so a packed EPI cannot be split per line at all. Plot a few
# lines:

# %%
seq_c.plot(time_range=(0.0125, 0.0125 + 4 * esp_packed));

# %% [markdown]
# ## Take-home
#
# - Put the whole EPI train in one segment; a segment boundary per line costs
#   117 µs per line and shifts TE.
# - Blips in the readout ramps (gradients across block boundaries) shorten the
#   echo spacing; they require the train to be one segment.
