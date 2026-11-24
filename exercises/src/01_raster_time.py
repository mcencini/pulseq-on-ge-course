# %% [markdown]
# # 01 · Risk #1: the wrong raster time
#
# pge2 does not resample waveforms: what is in the `.seq` file goes straight
# to the hardware. Every time in the file must therefore be an integer
# multiple of the GE raster:
#
# | quantity | GE raster |
# |---|---|
# | gradient samples, ramp and flat-top times, gradient delays | 4 µs |
# | block durations | 4 µs |
# | RF samples and RF delays | 2 µs |
# | ADC dwell time | 2 µs (1 µs on some gradient systems) |
# | ADC delay | 1 µs |
#
# <!-- TODO (Matteo): add the decimation figure from the pge2 manual here. -->

# %%
#INCLUDE _setup.py

# %% [markdown]
# ## The trap: pypulseq's defaults are not GE's
#
# A `pp.Opts` with only the gradient limits set keeps pypulseq's default
# rasters. Print them:

# %%
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    B0=3.0,
)
for name in ("grad_raster_time", "block_duration_raster", "rf_raster_time", "adc_raster_time"):
    print(f"{name:>22} = {getattr(system, name) * 1e6:g} us")

# %% [markdown]
# The gre2d of notebook 00, written as a function of the system limits and
# the dwell time, so that we can build it with different `pp.Opts`:

# %%
def gre2d(system, dwell=20e-6, fov=240e-3, n=128, slice_thickness=5e-3, n_dummy=20, pislquant=10):
    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=np.deg2rad(6),
        duration=3e-3,
        slice_thickness=slice_thickness,
        apodization=0.42,
        time_bw_product=4,
        system=system,
        return_gz=True,
        use="excitation",
    )
    gz_reph = pp.make_trapezoid("z", area=-gz.area / 2, duration=1e-3, system=system)
    delta_k = 1 / fov
    gx = pp.make_trapezoid("x", flat_area=n * delta_k, flat_time=n * dwell, system=system)
    adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
    gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=1e-3, system=system)
    pe_areas = (np.arange(n) - n / 2) * delta_k
    gy_pre = pp.make_trapezoid("y", area=np.max(np.abs(pe_areas)), duration=1e-3, system=system)
    pe_scales = pe_areas / gy_pre.area
    gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
    gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

    TRID = [pp.make_label(type="SET", label="TRID", value=v) for v in (1, 2, 3)]

    seq = pp.Sequence(system)
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        pe = pe_scales[iy] if iy >= 0 else 0.0

        if iy < -pislquant:
            seq.add_block(rf, gz, TRID[0])  # dummy
        elif iy < 0:
            seq.add_block(rf, gz, TRID[1])  # receive gain
        else:
            seq.add_block(rf, gz, TRID[2])  # acquire
        seq.add_block(gx_pre, pp.scale_grad(gy_pre, pe), gz_reph)
        if iy < -pislquant:
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pre, -pe), gz_spoil)
        seq.add_block(pp.make_delay(5e-3))
    return seq


# %% [markdown]
# Build it with the default rasters. Pulseq's own timing check is happy,
# because every time is on *these* rasters:

# %%
seq = gre2d(system)
print("Pulseq timing check passed:", seq.check_timing()[0])

# %% [markdown]
# pulseg converts it without complaint too, since segment detection does not
# look at rasters. `pge2.check` is where it fails:

# %%
psq = pulseg.fromSeq(seq)
try:
    pge2.check(psq, sys_ge)
except pge2.PGE2Error as err:
    print("pge2.check:", err)

# %% [markdown]
# The sinc pulse was sampled every 1 µs. The scanner's RF sequencer updates
# every 2 µs, so pge2 refuses the block rather than play a pulse whose
# duration and shape differ from what you designed.

# %% [markdown]
# ## Your turn
#
# 1. Fix `system` so that `pge2.check` passes. Change only the rasters.
# 2. Then set only the RF and ADC rasters right, leaving the gradient raster
#    at 10 µs. Which block fails now, and why?
# 3. Bonus: keep the GE rasters and call `gre2d(system, dwell=15e-6)`. What
#    does pge2 say, and what is the closest dwell time that works?

# %% tags=["raises-exception"]
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    B0=3.0,
    # TODO: set the four rasters here
)

psq = pulseg.fromSeq(gre2d(system))
pge2.check(psq, sys_ge)

# %% cellView="form"
# @title Solution (double-click to show the code)
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    B0=3.0,
    grad_raster_time=4e-6,
    block_duration_raster=4e-6,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
)
psq = pulseg.fromSeq(gre2d(system))
print("1.", pge2.check(psq, sys_ge))

# 2. With a 10 us gradient raster, the readout trapezoid ramps take a
#    multiple of 10 us, which is not a multiple of 4 us.
wrong_grad = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    B0=3.0,
    grad_raster_time=10e-6,
    block_duration_raster=10e-6,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
)
psq = pulseg.fromSeq(gre2d(wrong_grad))
try:
    pge2.check(psq, sys_ge)
except pge2.PGE2Error as err:
    print("2.", err)

# 3. A 15 us dwell is not a multiple of 2 us; 14 us or 16 us works.
#    pypulseq's own check flags this one too, as a warning when writing.
psq = pulseg.fromSeq(gre2d(system, dwell=15e-6))
try:
    pge2.check(psq, sys_ge)
except pge2.PGE2Error as err:
    print("3.", err)

# %% [markdown]
# ## Take-home
#
# - Always set all four rasters in `pp.Opts` explicitly; the defaults are not
#   GE's.
# - `seq.check_timing()` only checks against the rasters you gave it. Only
#   `pge2.check` checks against the scanner's.
