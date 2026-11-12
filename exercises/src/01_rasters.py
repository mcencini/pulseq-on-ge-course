# %% [markdown]
# # 01 · From the pypulseq GRE to GE: raster times
#
# We start from the 2D gradient echo that ships with pypulseq,
# [`examples/scripts/write_gre.py`](https://github.com/imr-framework/pypulseq/blob/a8cb2a8a4fc4acda71998378927a7014b334e72c/examples/scripts/write_gre.py),
# and take it, one issue at a time, towards the gre2d of the pge2 examples
# ([`write2DGRE.m`](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/2DGRE/write2DGRE.m)).
#
# Every step runs the sequence through the chain used before a scan:
#
# 1. **`pulseg.fromSeq`** groups the blocks of the `.seq` file into
#    *segments*, the units the GE sequencer plays;
# 2. **`pge2.check`** checks block timing, peak B1, peak gradient, slew rate
#    and PNS against the scanner;
# 3. **`pge2.validate`** compares the waveforms the interpreter will play with
#    the `.seq` file.
#
# pulseg and pge2 are MATLAB toolboxes; here they run in GNU Octave, called
# from Python through the `ge` object created below.

# %%
#INCLUDE _setup.py

# %% [markdown]
# ## The pypulseq GRE
#
# This is `write_gre.py` with plotting and file writing removed, and with two
# changes, both marked `pge2`:
#
# - `system` is an argument, so we can change it below;
# - the first block of every TR carries a `TRID` label. pulseg needs it to know
#   where a segment starts; TRIDs get their own exercise later. For now: one
#   TRID, set on the first block of every TR.

# %%
def write_gre(system, fov=256e-3, n_x=64, n_y=64, flip_angle_deg=10, slice_thickness=3e-3, tr=12e-3, te=5e-3):
    seq = pp.Sequence(system)
    rf_spoiling_inc = 117

    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=np.deg2rad(flip_angle_deg),
        duration=3e-3,
        slice_thickness=slice_thickness,
        apodization=0.42,
        time_bw_product=4,
        system=system,
        return_gz=True,
        delay=system.rf_dead_time,
        use="excitation",
    )

    delta_kx = 1 / fov
    delta_ky = 1 / fov
    gx = pp.make_trapezoid(channel="x", flat_area=n_x * delta_kx, flat_time=3.2e-3, system=system)
    adc = pp.make_adc(num_samples=n_x, duration=gx.flat_time, delay=gx.rise_time, system=system)
    gx_pre = pp.make_trapezoid(channel="x", area=-gx.area / 2, duration=1e-3, system=system)
    gz_reph = pp.make_trapezoid(channel="z", area=-gz.area / 2, duration=1e-3, system=system)
    phase_areas = (np.arange(n_y) - n_y / 2) * delta_ky

    gx_spoil = pp.make_trapezoid(channel="x", area=2 * n_x * delta_kx, system=system)
    gz_spoil = pp.make_trapezoid(channel="z", area=4 / slice_thickness, system=system)

    te_delay = (
        te
        - (pp.calc_duration(gz, rf) - pp.calc_rf_center(rf)[0] - rf.delay)
        - pp.calc_duration(gx_pre)
        - pp.calc_duration(gx) / 2
        - pp.eps
    )
    te_delay = np.ceil(te_delay / seq.grad_raster_time) * seq.grad_raster_time
    tr_delay = tr - pp.calc_duration(gz, rf) - pp.calc_duration(gx_pre) - pp.calc_duration(gx) - te_delay
    tr_delay = np.ceil(tr_delay / seq.grad_raster_time) * seq.grad_raster_time

    rf_phase = 0
    rf_inc = 0
    for i_phase in range(n_y):
        rf.phase_offset = rf_phase / 180 * np.pi
        adc.phase_offset = rf_phase / 180 * np.pi
        rf_inc = divmod(rf_inc + rf_spoiling_inc, 360.0)[1]
        rf_phase = divmod(rf_phase + rf_inc, 360.0)[1]

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=1))  # pge2: segment start
        gy_pre = pp.make_trapezoid(
            channel="y",
            area=phase_areas[i_phase],
            duration=pp.calc_duration(gx_pre),
            system=system,
        )
        seq.add_block(gx_pre, gy_pre, gz_reph)
        seq.add_block(pp.make_delay(te_delay))
        seq.add_block(gx, adc)
        gy_pre.amplitude = -gy_pre.amplitude
        seq.add_block(pp.make_delay(tr_delay), gx_spoil, gy_pre, gz_spoil)

    seq.set_definition(key="FOV", value=[fov, fov, slice_thickness])
    seq.set_definition(key="Name", value="gre")
    return seq


# %% [markdown]
# The system limits of the example:

# %%
system = pp.Opts(
    max_grad=28,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
)

seq = write_gre(system)
print("Pulseq timing check passed:", seq.check_timing()[0])

# %% [markdown]
# ## Run the chain
#
# pulseg converts it. The report lists each virtual segment, how many times it
# is played, and its **layout**: one letter per *base block* (a block with
# normalised amplitudes), `d` for a pure delay of fixed length.

# %%
ge.from_seq(seq)

# %% [markdown]
# One segment of five blocks, played 64 times: excitation `A`, prephasers
# `B`, the TE delay `d`, readout `C`, spoilers with the TR delay `D`.
#
# Now the hardware check:

# %%
try:
    ge.check()
except pgecourse.PGE2Error as err:
    print("pge2.check:", err)

# %% [markdown]
# ## Why: rasters
#
# pge2 does not resample waveforms: what is in the `.seq` file goes straight
# to the hardware. Every time in the file must be an integer multiple of the
# GE raster:
#
# | quantity | GE raster |
# |---|---|
# | gradient samples, ramp and flat-top times, gradient delays | 4 µs |
# | block durations | 4 µs |
# | RF samples and RF delays | 2 µs |
# | ADC dwell time | 2 µs (1 µs on some gradient systems) |
# | ADC delay | 1 µs |
#
# pypulseq's defaults are not these:

# %%
for name in ("grad_raster_time", "block_duration_raster", "rf_raster_time", "adc_raster_time"):
    print(f"{name:>22} = {getattr(system, name) * 1e6:g} us")

# %% [markdown]
# `seq.check_timing()` passed because it checks against the rasters you give
# it. Only `pge2.check` checks against the scanner's.
#
# <!-- TODO (Matteo): add the decimation figure from the pge2 manual here. -->

# %% [markdown]
# ## Your turn
#
# 1. Add the four GE rasters to `system` and run the chain again. The raster
#    error goes away, and a different one appears: what is it?
# 2. Fix that one too, changing only the gradient limits.
# 3. Bonus: set only the gradient rasters right (leave RF and ADC at the
#    defaults), then only the RF and ADC ones. Which block fails each time, and
#    on what?

# %% tags=["raises-exception"]
system = pp.Opts(
    max_grad=28,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
    # TODO: GE rasters
)

seq = write_gre(system)
print(ge.from_seq(seq))
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
# 1. GE rasters. pge2.check then stops on PNS: at 150 T/m/s the gradient
#    ramps stimulate above the first-controlled-mode limit of the coil model.
system = pp.Opts(
    max_grad=28,
    grad_unit="mT/m",
    max_slew=150,
    slew_unit="T/m/s",
    rf_ringdown_time=20e-6,
    rf_dead_time=100e-6,
    adc_dead_time=10e-6,
    grad_raster_time=4e-6,
    block_duration_raster=4e-6,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
)
ge.from_seq(write_gre(system))
try:
    ge.check()
except pgecourse.PGE2Error as err:
    print("1.", err)

# 2. The pge2 gre2d uses 50 mT/m and 120 T/m/s, each divided by sqrt(3), so
#    that the sequence stays within limits in any oblique plane. That slew
#    rate also keeps PNS below the normal-mode limit.
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
seq = write_gre(system)
ge.from_seq(seq)
print("2.", ge.check())
print("   pge2.validate:", ge.validate())

# 3. Each half of the fix leaves the other half's error.
for label, rasters in (
    ("gradient rasters only", dict(grad_raster_time=4e-6, block_duration_raster=4e-6)),
    ("RF and ADC rasters only", dict(rf_raster_time=2e-6, adc_raster_time=2e-6)),
):
    partial = pp.Opts(
        max_grad=50 / np.sqrt(3),
        grad_unit="mT/m",
        max_slew=120 / np.sqrt(3),
        slew_unit="T/m/s",
        rf_ringdown_time=20e-6,
        rf_dead_time=100e-6,
        adc_dead_time=10e-6,
        **rasters,
    )
    ge.from_seq(write_gre(partial))
    try:
        ge.check()
    except pgecourse.PGE2Error as err:
        print(f"3. {label}: {err}")

# %% [markdown]
# ## Take-home
#
# - Set all four rasters in `pp.Opts` explicitly; the defaults are not GE's.
# - `seq.check_timing()` only checks against your own rasters; `pge2.check`
#   checks against the scanner, PNS included.
#
# The sequence now passes every check. Notebook 02 asks whether it plays what
# we meant.
