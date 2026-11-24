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
# 2D CPMG FSE, 8 echoes per shot, 8 shots. Each echo spacing is four
# blocks: 180° with slice select, crusher + phase encoding, readout,
# rewinder + crusher.

# %%
fov = 240e-3
nx, ny, etl = 128, 64, 8
slice_thickness = 5e-3
dwell = 14e-6
tr = 1.0
t_rf = 3.2e-3      # 180 duration
R = system.grad_raster_time


slew = 0.98 * system.max_slew


def rup(t):
    """Round a time up to the gradient raster."""
    return np.ceil(round(t / R, 6)) * R


def ramp(dg):
    """Ramp time from one gradient level to another."""
    return max(R, rup(abs(dg) / slew))


dk = 1 / fov
rf90, gz90, _ = pp.make_sinc_pulse(
    np.pi / 2, duration=1.6e-3, slice_thickness=slice_thickness, time_bw_product=4,
    phase_offset=np.pi / 2, system=system, return_gz=True, use="excitation",
)
rf180 = pp.make_sinc_pulse(
    np.pi, duration=t_rf, slice_thickness=slice_thickness, time_bw_product=4,
    system=system, use="refocusing",
)
g_ss = 4 / t_rf / slice_thickness   # slice-select amplitude of the 180 (Hz/m)
a_crush = 4 / slice_thickness       # crusher area (1/m)

gx = pp.make_trapezoid("x", flat_area=nx * dk, flat_time=nx * dwell, system=system)
adc = pp.make_adc(nx, duration=gx.flat_time, delay=gx.rise_time, system=system)
pe = (np.arange(ny) - ny / 2) * dk
order = np.arange(ny).reshape(etl, -1).T  # [shot, echo] -> phase-encoding line

# Separate trapezoids, each starting and ending at zero in its block
gss = pp.make_trapezoid("z", amplitude=g_ss, flat_time=t_rf, rise_time=ramp(g_ss), system=system)
dur_c = rup(max(
    pp.calc_duration(pp.make_trapezoid("z", area=a_crush, system=system)),
    pp.calc_duration(pp.make_trapezoid("y", area=pe.max() - pe.min(), system=system)),
    pp.calc_duration(pp.make_trapezoid("x", area=gx.area / 2, system=system)),
))
gz_crush = pp.make_trapezoid("z", area=a_crush, duration=dur_c, system=system)
gz_first = pp.make_trapezoid("z", area=a_crush - gz90.area / 2, duration=dur_c, system=system)
gy_pe = pp.make_trapezoid("y", area=pe.max() - pe.min(), duration=dur_c, system=system)
gx_pre = pp.make_trapezoid("x", area=gx.area / 2, duration=dur_c, system=system)

TRID = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2, 3)]


def cpmg_tau(esp, prephaser_duration, rf_block_duration):
    """Delay after the 90 so that 90 -> first 180 is half the echo spacing."""
    half90 = pp.calc_duration(rf90, gz90) - (rf90.delay + rf90.shape_dur / 2)
    return rup(esp / 2 - half90 - prephaser_duration - rf_block_duration / 2)


rf180.delay = gss.rise_time
esp = pp.calc_duration(rf180, gss) + 2 * dur_c + pp.calc_duration(gx)
tau = cpmg_tau(esp, dur_c, pp.calc_duration(rf180, gss))
shot = pp.calc_duration(rf90, gz90) + tau + dur_c + etl * esp
fill = rup(tr - shot)   # pure delay completing the TR
print(f"echo spacing in the file: {1e3 * esp:.3f} ms")

# %% [markdown]
# `pgecourse.played_block_starts(seq)` gives the start time of every block as
# pge2 plays it, with the 117 µs per segment instance added.

# %%
from pgecourse import played_block_starts


def cpmg_timing(seq):
    """90 to first 180, and first to second 180, in ms: in the file and as played."""
    r = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).rf is not None]
    played = played_block_starts(seq)
    in_file = np.cumsum([0] + [seq.block_durations[k] for k in seq.block_events])[:-1]
    for name, t in (("file", in_file), ("played", played)):
        print(f"{name:>7}: 90 -> 180 {1e3 * (t[r[1]] - t[r[0]]):.3f} ms, "
              f"echo spacing {1e3 * (t[r[2]] - t[r[1]]):.3f} ms")


# %% [markdown]
# ## Case A: one TRID per echo

# %%
seq_a = pp.Sequence(system)
for shot in range(order.shape[0]):
    seq_a.add_block(rf90, gz90, TRID[0])
    seq_a.add_block(pp.make_delay(tau))
    seq_a.add_block(gx_pre, gz_first)
    for e in range(etl):
        scale = pe[order[shot, e]] / gy_pe.area
        seq_a.add_block(rf180, gss, TRID[1])  # a segment per echo
        seq_a.add_block(gz_crush, pp.scale_grad(gy_pe, scale))
        seq_a.add_block(gx, adc)
        seq_a.add_block(gz_crush, pp.scale_grad(gy_pe, -scale))
    seq_a.add_block(pp.make_delay(fill), TRID[2])

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
# Change the labels so that the whole echo train is one segment (excitation
# and echoes together, fill delay on its own). Check that the played timing
# matches the file.

# %%
seq_b = pp.Sequence(system)
for shot in range(order.shape[0]):
    seq_b.add_block(rf90, gz90, TRID[0])
    seq_b.add_block(pp.make_delay(tau))
    seq_b.add_block(gx_pre, gz_first)
    for e in range(etl):
        scale = pe[order[shot, e]] / gy_pe.area
        seq_b.add_block(rf180, gss, TRID[1])  # TODO
        seq_b.add_block(gz_crush, pp.scale_grad(gy_pe, scale))
        seq_b.add_block(gx, adc)
        seq_b.add_block(gz_crush, pp.scale_grad(gy_pe, -scale))
    seq_b.add_block(pp.make_delay(fill), TRID[2])

print(ge.from_seq(seq_b))
print(ge.check())
print("pge2.validate:", ge.validate())
cpmg_timing(seq_b)

# %% cellView="form"
# @title Solution (double-click to show the code)
seq_b = pp.Sequence(system)
for shot in range(order.shape[0]):
    seq_b.add_block(rf90, gz90, TRID[0])
    seq_b.add_block(pp.make_delay(tau))
    seq_b.add_block(gx_pre, gz_first)
    for e in range(etl):
        scale = pe[order[shot, e]] / gy_pe.area
        seq_b.add_block(rf180, gss)  # no TRID: the echoes join the 90 segment
        seq_b.add_block(gz_crush, pp.scale_grad(gy_pe, scale))
        seq_b.add_block(gx, adc)
        seq_b.add_block(gz_crush, pp.scale_grad(gy_pe, -scale))
    seq_b.add_block(pp.make_delay(fill), TRID[2])

print(ge.from_seq(seq_b))
print(ge.check())
print("pge2.validate:", ge.validate())
cpmg_timing(seq_b)

# %% [markdown]
# With the train in one segment, the played timing is the file's timing.

# %% [markdown]
# ## Joining the gradients across blocks
#
# Inside a segment the gradients need not return to zero at block
# boundaries. The z gradient from the crusher before each 180°, through its
# slice select, to the crusher after it can be one extended trapezoid, split
# at the block boundaries: `z_before` ends at the slice-select level, `z_rf`
# holds it, `z_after` starts from it. That removes the ramps to and from zero
# around every slice select.

# %%
g_c = 0.9 * system.max_grad  # crusher plateau


def z_lobe(area, g_start, g_end, duration=0):
    """z gradient of the given area from g_start to g_end through a plateau,
    as an extended trapezoid, padded with zero to the given duration. The
    plateau is g_c, lowered when the area is too small for it."""
    g = g_c
    r1, r2 = ramp(g - g_start), ramp(g - g_end)
    if area < (g_start + g) / 2 * r1 + (g_end + g) / 2 * r2:  # lower the plateau
        lo, hi = max(g_start, g_end), g_c
        for _ in range(60):
            g = (lo + hi) / 2
            r1, r2 = ramp(g - g_start), ramp(g - g_end)
            if (g_start + g) / 2 * r1 + (g_end + g) / 2 * r2 > area:
                hi = g
            else:
                lo = g
        g = lo
        r1, r2 = ramp(g - g_start), ramp(g - g_end)
    flat = rup((area - (g_start + g) / 2 * r1 - (g_end + g) / 2 * r2) / g)
    length = r1 + flat + r2
    t, a = [0, r1, r1 + flat, length], [g_start, g, g, g_end]
    if duration - length > 1e-9:  # pad on the side that is at zero
        if g_end == 0:
            t, a = t + [duration], a + [0]
        else:
            t, a = [0] + [x + duration - length for x in t], [0] + a
    keep = [0] + [i for i in range(1, len(t)) if t[i] - t[i - 1] > 1e-9]
    return pp.make_extended_trapezoid(
        "z", times=np.array(t)[keep], amplitudes=np.array(a)[keep], system=system
    )


rf180_packed = pp.make_sinc_pulse(
    np.pi, duration=t_rf, slice_thickness=slice_thickness, time_bw_product=4,
    system=system, use="refocusing",
)
z_rf = pp.make_extended_trapezoid("z", times=np.array([0, t_rf]), amplitudes=np.array([g_ss, g_ss]), system=system)
dur_p = rup(max(
    pp.calc_duration(z_lobe(a_crush, g_ss, 0)),
    pp.calc_duration(z_lobe(a_crush - gz90.area / 2, 0, g_ss)),
    pp.calc_duration(pp.make_trapezoid("y", area=pe.max() - pe.min(), system=system)),
    pp.calc_duration(pp.make_trapezoid("x", area=gx.area / 2, system=system)),
))
z_after = z_lobe(a_crush, g_ss, 0, dur_p)                   # from the slice select down
z_before = z_lobe(a_crush, 0, g_ss, dur_p)                  # up to the slice select
z_first = z_lobe(a_crush - gz90.area / 2, 0, g_ss, dur_p)   # 90 rephaser + first crusher
z_last = z_lobe(a_crush, 0, 0, dur_p)                       # last crusher, back to zero
gy_pe_p = pp.make_trapezoid("y", area=pe.max() - pe.min(), duration=dur_p, system=system)
gx_pre_p = pp.make_trapezoid("x", area=gx.area / 2, duration=dur_p, system=system)

esp_packed = pp.calc_duration(rf180_packed, z_rf) + 2 * dur_p + pp.calc_duration(gx)
tau_packed = cpmg_tau(esp_packed, dur_p, pp.calc_duration(rf180_packed, z_rf))
shot_packed = (pp.calc_duration(rf90, gz90) + tau_packed + dur_p + etl * esp_packed
               - dur_p + pp.calc_duration(z_last, gy_pe_p))  # last block: z_last
fill_packed = rup(tr - shot_packed)
print(f"echo spacing in the file: {1e3 * esp_packed:.3f} ms (was {1e3 * esp:.3f} ms)")

seq_c = pp.Sequence(system)
for shot in range(order.shape[0]):
    seq_c.add_block(rf90, gz90, TRID[0])
    seq_c.add_block(pp.make_delay(tau_packed))
    seq_c.add_block(gx_pre_p, z_first)
    for e in range(etl):
        scale = pe[order[shot, e]] / gy_pe_p.area
        seq_c.add_block(rf180_packed, z_rf)
        seq_c.add_block(z_after, pp.scale_grad(gy_pe_p, scale))
        seq_c.add_block(gx, adc)
        seq_c.add_block(z_before if e < etl - 1 else z_last, pp.scale_grad(gy_pe_p, -scale))
    seq_c.add_block(pp.make_delay(fill_packed), TRID[2])

print(ge.from_seq(seq_c))
print(ge.check())
print("pge2.validate:", ge.validate())
cpmg_timing(seq_c)

# %% [markdown]
# Plot the z gradient of a few echoes to see it run across the block
# boundaries:

# %%
seq_c.plot(time_range=(0, 4 * esp_packed));

# %% [markdown]
# ## Take-home
#
# - Everything whose relative timing matters (an echo train) goes in one
#   segment; every segment boundary adds time that is not in the file.
# - Inside a segment, gradients may run across block boundaries: join them
#   to save the ramps.
# - The packed train cannot be split per echo: its gradients are not zero at
#   the echo boundaries.
