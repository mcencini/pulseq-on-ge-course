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
# 8 slices, 64 lines, TR = 200 ms. Events first, then the delay that fills
# the TR after the last slice.

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

fov = 240e-3
n = 64
n_slices = 8
slice_thickness = 5e-3
slice_gap = 2.5e-3
dwell = 20e-6
tr = 0.2

rf, gz, _ = pp.make_sinc_pulse(
    flip_angle=np.deg2rad(30),
    duration=3e-3,
    slice_thickness=slice_thickness,
    apodization=0.42,
    time_bw_product=4,
    system=system,
    return_gz=True,
    use="excitation",
)
gz_reph = pp.make_trapezoid("z", area=-gz.area / 2, duration=1e-3, system=system)
dk = 1 / fov
gx = pp.make_trapezoid("x", flat_area=n * dk, flat_time=n * dwell, system=system)
adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
pe = (np.arange(n) - n / 2) * dk
gy_pe = pp.make_trapezoid("y", area=np.max(np.abs(pe)), duration=1e-3, system=system)
gx_spoil = pp.make_trapezoid("x", area=2 * n * dk, system=system)
gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

z = (np.arange(n_slices) - (n_slices - 1) / 2) * (slice_thickness + slice_gap)
slice_tr = (
    pp.calc_duration(rf, gz)
    + pp.calc_duration(gx_pre, gy_pe, gz_reph)
    + pp.calc_duration(gx)
    + pp.calc_duration(gx_spoil, gy_pe, gz_spoil)
)
grid = system.block_duration_raster
fill = np.round((tr - n_slices * slice_tr) / grid) * grid

TRID = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2)]

# %% [markdown]
# ## Case A: a TRID on every slice, none on the fill delay
#
# Every slice excitation starts a segment, so the fill delay belongs to the
# segment of the last slice:

# %%
seq_a = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iy in range(n):
    scale = pe[iy] / gy_pe.area
    for s in range(n_slices):
        rf.freq_offset = gz.amplitude * z[s]  # slice position
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        seq_a.add_block(rf, gz, TRID[0])
        seq_a.add_block(gx_pre, pp.scale_grad(gy_pe, scale), gz_reph)
        seq_a.add_block(gx, adc)
        seq_a.add_block(gx_spoil, pp.scale_grad(gy_pe, -scale), gz_spoil)
    seq_a.add_block(pp.make_delay(fill))

try:
    psq = pulseg.fromSeq(seq_a)
except pge2.PGE2Error as err:
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
seq_b = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iy in range(n):
    scale = pe[iy] / gy_pe.area
    for s in range(n_slices):
        rf.freq_offset = gz.amplitude * z[s]  # slice position
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        if s == 0:
            seq_b.add_block(rf, gz, TRID[0])
        else:
            seq_b.add_block(rf, gz)
        seq_b.add_block(gx_pre, pp.scale_grad(gy_pe, scale), gz_reph)
        seq_b.add_block(gx, adc)
        seq_b.add_block(gx_spoil, pp.scale_grad(gy_pe, -scale), gz_spoil)
    seq_b.add_block(pp.make_delay(fill))

psq = pulseg.fromSeq(seq_b)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))

# %% [markdown]
# This one is valid: 33 blocks per segment. But the segment is 8 copies of
# the same 4 base blocks, and changing the number of slices changes the
# segment itself.

# %% [markdown]
# ## Your turn
#
# Add the labels so that there is one segment per slice and a separate pure
# delay segment for the fill delay. Check that `pulseg.fromSeq` reports 2
# segments, with 512 and 64 instances, and that `pge2.check` and
# `pge2.validate` pass.

# %% tags=["raises-exception"]
seq = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iy in range(n):
    scale = pe[iy] / gy_pe.area
    for s in range(n_slices):
        rf.freq_offset = gz.amplitude * z[s]  # slice position
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        seq.add_block(rf, gz)  # TODO
        seq.add_block(gx_pre, pp.scale_grad(gy_pe, scale), gz_reph)
        seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -scale), gz_spoil)
    seq.add_block(pp.make_delay(fill))  # TODO

psq = pulseg.fromSeq(seq)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))

# %% cellView="form"
# @title Solution (double-click to show the code)
seq = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iy in range(n):
    scale = pe[iy] / gy_pe.area
    for s in range(n_slices):
        rf.freq_offset = gz.amplitude * z[s]  # slice position
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        seq.add_block(rf, gz, TRID[0])
        seq.add_block(gx_pre, pp.scale_grad(gy_pe, scale), gz_reph)
        seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -scale), gz_spoil)
    seq.add_block(pp.make_delay(fill), TRID[1])

psq = pulseg.fromSeq(seq)
print(psq)
print(pge2.check(psq, sys_ge))
print("pge2.validate:", pge2.validate(psq, sys_ge))

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
