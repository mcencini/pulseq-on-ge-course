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
# The sequence is reduced to 64 × 64 × 16 so that the checks run quickly.
# Events first, as usual, and the delays that set TI and the shot TR.

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

fov = (256e-3, 256e-3, 192e-3)
nx, ny, nz = 64, 64, 16
dwell = 16e-6
ti = 0.9        # inversion time (s), inversion to centre of the readout train
shot_tr = 2.3   # (s)

rf_inv = pp.make_block_pulse(np.pi, duration=1e-3, system=system, use="inversion")
gz_inv_spoil = pp.make_trapezoid("z", area=8 / (fov[2] / nz), system=system)

rf = pp.make_block_pulse(np.deg2rad(8), duration=100e-6, system=system, use="excitation")
dk = 1 / np.asarray(fov)
gx = pp.make_trapezoid("x", flat_area=nx * dk[0], flat_time=nx * dwell, system=system)
adc = pp.make_adc(nx, duration=gx.flat_time, delay=gx.rise_time, system=system)
gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
gx_spoil = pp.make_trapezoid("x", area=2 * nx * dk[0], system=system)

ky = (np.arange(ny) - ny / 2) * dk[1]
kz = (np.arange(nz) - nz / 2) * dk[2]
gy_pe = pp.make_trapezoid("y", area=np.max(np.abs(ky)), duration=1e-3, system=system)
gz_pe = pp.make_trapezoid("z", area=np.max(np.abs(kz)), duration=1e-3, system=system)

readout_tr = (
    pp.calc_duration(rf)
    + pp.calc_duration(gx_pre, gy_pe, gz_pe)
    + pp.calc_duration(gx)
    + pp.calc_duration(gx_spoil, gy_pe, gz_pe)
)
inv_time = pp.calc_duration(rf_inv) + pp.calc_duration(gz_inv_spoil)
grid = system.block_duration_raster
ti_delay = np.round((ti - inv_time - ny * readout_tr / 2) / grid) * grid
rec_delay = np.round((shot_tr - inv_time - ti_delay - ny * readout_tr) / grid) * grid

TRID = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2, 3)]

# %% [markdown]
# ## Case A: one TRID per shot
#
# A TRID on the inversion only:

# %%
seq_a = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iz in range(nz):
    seq_a.add_block(rf_inv, TRID[0])
    seq_a.add_block(gz_inv_spoil)
    seq_a.add_block(pp.make_delay(ti_delay))
    for iy in range(ny):
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
        seq_a.add_block(rf)
        seq_a.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
        seq_a.add_block(gx, adc)
        seq_a.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
    seq_a.add_block(pp.make_delay(rec_delay))

print(ge.from_seq(seq_a))
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
seq_b = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iz in range(nz):
    seq_b.add_block(rf_inv, TRID[0])
    seq_b.add_block(gz_inv_spoil)
    seq_b.add_block(pp.make_delay(ti_delay))
    for iy in range(ny):
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
        seq_b.add_block(rf, TRID[1])
        seq_b.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
        seq_b.add_block(gx, adc)
        seq_b.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
    seq_b.add_block(pp.make_delay(rec_delay))

try:
    ge.from_seq(seq_b)
except pge2py.PGE2Error as err:
    print("from_seq:", err)

# %% [markdown]
# Without a label, the recovery delay belongs to the segment of the last
# readout TR of the shot, which then has 5 blocks instead of 4. A segment
# instance cannot gain a block.

# %% [markdown]
# ## Your turn
#
# Add the labels so that there are three segments: the inversion with its
# TI delay, the readout TR, and the recovery delay. Check the number of
# blocks per segment in the report, and that `pge2.check` and
# `pge2.validate` pass.

# %% tags=["raises-exception"]
seq = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iz in range(nz):
    seq.add_block(rf_inv)  # TODO
    seq.add_block(gz_inv_spoil)
    seq.add_block(pp.make_delay(ti_delay))
    for iy in range(ny):
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
        seq.add_block(rf)  # TODO
        seq.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
        seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
    seq.add_block(pp.make_delay(rec_delay))  # TODO

print(ge.from_seq(seq))
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
seq = pp.Sequence(system)
rf_phase = rf_increment = 0.0
for iz in range(nz):
    seq.add_block(rf_inv, TRID[0])
    seq.add_block(gz_inv_spoil)
    seq.add_block(pp.make_delay(ti_delay))
    for iy in range(ny):
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
        seq.add_block(rf, TRID[1])
        seq.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
        seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
    seq.add_block(pp.make_delay(rec_delay), TRID[2])

print(ge.from_seq(seq))
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
