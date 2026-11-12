# %% [markdown]
# # 02 · Events created inside the scan loop
#
# At the end of notebook 01, the pypulseq GRE passes `pulseg.fromSeq`,
# `pge2.check` and `pge2.validate`. This notebook asks whether it plays the
# phase encoding we asked for.

# %%
#INCLUDE _setup.py

# %% [markdown]
# The GRE and the system limits from the end of notebook 01. Note how the
# phase-encoding gradient is made: a new `make_trapezoid` in every TR, with the
# area of that line and a fixed duration.

# %%
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
    grad_raster_time=4e-6,
    block_duration_raster=4e-6,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
)

fov = 256e-3
n_x = n_y = 64
slice_thickness = 3e-3
tr, te = 12e-3, 5e-3

rf, gz, _ = pp.make_sinc_pulse(
    flip_angle=np.deg2rad(10),
    duration=3e-3,
    slice_thickness=slice_thickness,
    apodization=0.42,
    time_bw_product=4,
    system=system,
    return_gz=True,
    delay=system.rf_dead_time,
    use="excitation",
)
delta_k = 1 / fov
gx = pp.make_trapezoid(channel="x", flat_area=n_x * delta_k, flat_time=3.2e-3, system=system)
adc = pp.make_adc(num_samples=n_x, duration=gx.flat_time, delay=gx.rise_time, system=system)
gx_pre = pp.make_trapezoid(channel="x", area=-gx.area / 2, duration=1e-3, system=system)
gz_reph = pp.make_trapezoid(channel="z", area=-gz.area / 2, duration=1e-3, system=system)
phase_areas = (np.arange(n_y) - n_y / 2) * delta_k
gx_spoil = pp.make_trapezoid(channel="x", area=2 * n_x * delta_k, system=system)
gz_spoil = pp.make_trapezoid(channel="z", area=4 / slice_thickness, system=system)

te_delay = (
    te
    - (pp.calc_duration(gz, rf) - pp.calc_rf_center(rf)[0] - rf.delay)
    - pp.calc_duration(gx_pre)
    - pp.calc_duration(gx) / 2
    - pp.eps
)
te_delay = np.ceil(te_delay / system.grad_raster_time) * system.grad_raster_time
tr_delay = tr - pp.calc_duration(gz, rf) - pp.calc_duration(gx_pre) - pp.calc_duration(gx) - te_delay
tr_delay = np.ceil(tr_delay / system.grad_raster_time) * system.grad_raster_time


def write_gre():
    seq = pp.Sequence(system)
    rf_phase = rf_inc = 0
    for i_phase in range(n_y):
        rf.phase_offset = adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = divmod(rf_inc + 117, 360.0)[1]
        rf_phase = divmod(rf_phase + rf_inc, 360.0)[1]

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=1))
        gy_pre = pp.make_trapezoid(
            channel="y", area=phase_areas[i_phase], duration=pp.calc_duration(gx_pre), system=system
        )
        seq.add_block(gx_pre, gy_pre, gz_reph)
        seq.add_block(pp.make_delay(te_delay))
        seq.add_block(gx, adc)
        gy_pre.amplitude = -gy_pre.amplitude
        seq.add_block(pp.make_delay(tr_delay), gx_spoil, gy_pre, gz_spoil)
    return seq


seq = write_gre()
print(ge.from_seq(seq))
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# ## What does the scanner play?
#
# `ge.instance_waveforms(row)` returns the gradients of one segment instance
# twice: as the `.seq` file has them, and as pge2 builds them for the
# hardware. Each TR is 5 blocks, so phase-encoding line `i` starts at block
# `5 * i + 1`. Here is the prephasing block of line 16:

# %%
import matplotlib.pyplot as plt

w = ge.instance_waveforms(5 * 16 + 1)
t0, t1 = w["block_edges"][1], w["block_edges"][2]
fig, ax = plt.subplots(figsize=(7, 3))
for key, style in (("seq", "-"), ("played", "--")):
    t, g = w[key]["gy"]
    keep = (t >= t0) & (t <= t1)
    ax.plot((t[keep] - t0) * 1e3, g[keep], style, label=key)
ax.set(xlabel="time in block (ms)", ylabel="gy (mT/m)", title="line 16, phase-encoding prephaser")
ax.legend()
plt.show()

# %% [markdown]
# Same peak, different ramps. Over all lines, the difference in phase-encoding
# area, in units of Δk = 1/FOV:

# %%
GAMMA = 42.576e3  # Hz/(mT/m s) -> 1/m


def pe_area_error(seq_n_lines):
    errors = []
    for i in range(seq_n_lines):
        w = ge.instance_waveforms(5 * i + 1)
        t0, t1 = w["block_edges"][1], w["block_edges"][2]
        areas = {}
        for key in ("seq", "played"):
            t, g = w[key]["gy"]
            keep = (t >= t0 - 1e-9) & (t <= t1 + 1e-9)
            areas[key] = np.trapezoid(g[keep], t[keep]) * GAMMA if keep.sum() > 1 else 0.0
        errors.append((areas["played"] - areas["seq"]) / delta_k)
    return np.array(errors)


errors = pe_area_error(n_y)
plt.figure(figsize=(7, 3))
plt.plot(np.arange(n_y) - n_y / 2, errors, ".")
plt.xlabel("ky line (units of Δk)")
plt.ylabel("played − intended (Δk)")
plt.title("phase-encoding error")
plt.show()
print(f"largest error: {np.max(np.abs(errors)):.2f} Δk")

# %% [markdown]
# Lines are encoded up to about one Δk away from where they should be, and no
# check said so.
#
# ## Why
#
# 1. **pge2 replays shapes.** A segment's base blocks come from its *first*
#    instance. Every later instance plays the same waveform shapes, scaled to
#    its own amplitude. Here the first instance is line 0, the largest |ky|.
# 2. **`make_trapezoid` changes the shape with the area**, even at a fixed
#    duration: it uses the shortest ramp the slew rate allows for each
#    amplitude, and lengthens the flat top to fill the duration.

# %%
for i in (0, 8, 16, 24, 31):
    g = pp.make_trapezoid("y", area=phase_areas[i], duration=pp.calc_duration(gx_pre), system=system)
    print(f"line {i:2d}: rise {g.rise_time * 1e6:4.0f} us, flat {g.flat_time * 1e6:4.0f} us")

# %% [markdown]
# 3. **`pge2.validate` compares sample by sample** with a tolerance of a few
#    slew-rate steps, so a ramp that is a few tens of µs off passes. The
#    accumulated area does not.
#
# The GE way, and the way pge2 expects: create the event once, with the largest
# area it will need, and scale it in the loop. Then every instance has the
# same shape by construction.

# %% [markdown]
# ## Your turn
#
# Rewrite `write_gre` so that:
#
# 1. one phase-encoding trapezoid is created **before** the loop, for the
#    largest |ky| area;
# 2. the loop uses `pp.scale_grad` for the prephaser and the rewinder.
#
# Then check that `pe_area_error` drops to the precision of the numerical
# integration (about 10⁻³ Δk) for every line.

# %% tags=["raises-exception"]
def write_gre_ge():
    seq = pp.Sequence(system)
    # TODO: create the phase-encoding trapezoid here
    rf_phase = rf_inc = 0
    for i_phase in range(n_y):
        rf.phase_offset = adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = divmod(rf_inc + 117, 360.0)[1]
        rf_phase = divmod(rf_phase + rf_inc, 360.0)[1]

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=1))
        gy_pre = ...  # TODO
        gy_rew = ...  # TODO
        seq.add_block(gx_pre, gy_pre, gz_reph)
        seq.add_block(pp.make_delay(te_delay))
        seq.add_block(gx, adc)
        seq.add_block(pp.make_delay(tr_delay), gx_spoil, gy_rew, gz_spoil)
    return seq


print(ge.from_seq(write_gre_ge()))
ge.check()
print("pge2.validate:", ge.validate())
print(f"largest error: {np.max(np.abs(pe_area_error(n_y))):.2e} Δk")

# %% cellView="form"
# @title Solution (double-click to show the code)
def write_gre_ge():
    seq = pp.Sequence(system)
    gy_base = pp.make_trapezoid(
        channel="y", area=np.max(np.abs(phase_areas)), duration=pp.calc_duration(gx_pre), system=system
    )
    pe_scales = phase_areas / gy_base.area
    rf_phase = rf_inc = 0
    for i_phase in range(n_y):
        rf.phase_offset = adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = divmod(rf_inc + 117, 360.0)[1]
        rf_phase = divmod(rf_phase + rf_inc, 360.0)[1]

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=1))
        gy_pre = pp.scale_grad(gy_base, pe_scales[i_phase])
        gy_rew = pp.scale_grad(gy_base, -pe_scales[i_phase])
        seq.add_block(gx_pre, gy_pre, gz_reph)
        seq.add_block(pp.make_delay(te_delay))
        seq.add_block(gx, adc)
        seq.add_block(pp.make_delay(tr_delay), gx_spoil, gy_rew, gz_spoil)
    return seq


print(ge.from_seq(write_gre_ge()))
ge.check()
print("pge2.validate:", ge.validate())
print(f"largest error: {np.max(np.abs(pe_area_error(n_y))):.2e} Δk")

# %% [markdown]
# ## Going further: when validate does catch it
#
# Drop `duration=` from the in-loop `make_trapezoid`, so that every line gets
# the shortest trapezoid for its area. The shapes now differ by hundreds of
# µs, and `pge2.validate` reports the mismatch. The fixed-duration version is
# the more dangerous one, because it looks clean.

# %% [markdown]
# ## Take-home
#
# - Create every RF, gradient and ADC event once, before the loop.
# - In the loop, change only amplitudes (`pp.scale_grad`), RF/ADC phase and
#   frequency, and the length of pure delay blocks.
# - Passing `pge2.validate` does not prove the phase encoding is right; a
#   shape created per line can hide a k-space error below its tolerance.
#
# ## Still to come on the way to the pge2 gre2d
#
# The sequence now follows the two rules covered so far. The gre2d of the pge2
# examples also has dummy TRs and receive-gain TRs under their own TRIDs, a
# second echo with a different ADC, pure delays whose length varies between
# instances, and noise scans.
