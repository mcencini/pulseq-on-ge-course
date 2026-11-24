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

# %%
from pgecourse.sequences import gre2d

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
# Build the gre2d of notebook 00 with these limits (`gre2d` is the same
# function, packaged so that this notebook can focus on the system limits).
# Pulseq's own timing check is happy, because every time is on *these*
# rasters:

# %%
seq = gre2d(system)
print("Pulseq timing check passed:", seq.check_timing()[0])

# %% [markdown]
# pulseg converts it without complaint too, since segment detection does not
# look at rasters. `pge2.check` is where it fails:

# %%
ge.from_seq(seq)
try:
    ge.check()
except pgecourse.PGE2Error as err:
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

ge.from_seq(gre2d(system))
ge.check()

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
ge.from_seq(gre2d(system))
print("1.", ge.check())

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
ge.from_seq(gre2d(wrong_grad))
try:
    ge.check()
except pgecourse.PGE2Error as err:
    print("2.", err)

# 3. A 15 us dwell is not a multiple of 2 us; 14 us or 16 us works.
#    pypulseq's own check flags this one too, as a warning when writing.
ge.from_seq(gre2d(system, dwell=15e-6))
try:
    ge.check()
except pgecourse.PGE2Error as err:
    print("3.", err)

# %% [markdown]
# ## Take-home
#
# - Always set all four rasters in `pp.Opts` explicitly; the defaults are not
#   GE's.
# - `seq.check_timing()` only checks against the rasters you gave it. Only
#   `pge2.check` checks against the scanner's.
