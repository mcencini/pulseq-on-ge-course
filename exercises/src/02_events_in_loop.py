# %% [markdown]
# # 02 · Risk #2: creating events inside the scan loop
#
# Many Pulseq scripts create the phase-encoding gradient inside the loop,
# one `make_trapezoid` per line. On GE that is risky. pulseg builds each
# segment's definition from its **first instance**, and pge2 plays every
# later instance by scaling the waveforms of that definition. If a later
# instance has a gradient with a different *shape* (other ramp or flat-top
# times), the scanner still plays the first shape, only rescaled.

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
# ## The naive gre2d
#
# Events as in notebook 00, except the phase-encoding gradient. Here each line
# makes its own minimum-time trapezoid with the area it needs.

# %%
fov = 240e-3
n = 128
slice_thickness = 5e-3
dwell = 20e-6
tr_delay = 5e-3
n_dummy = 20
pislquant = 10
TRID = {"dummy": 1, "receive_gain": 2, "acquire": 3}

rf, gz, _ = pp.make_sinc_pulse(
    flip_angle=np.deg2rad(6),
    duration=3e-3,
    delay=system.rf_dead_time,
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
gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)
pe_areas = (np.arange(n) - n / 2) * delta_k


def naive_gre2d():
    seq = pp.Sequence(system)
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        segment = "dummy" if iy < -pislquant else "receive_gain" if iy < 0 else "acquire"
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360

        area = pe_areas[iy] if segment == "acquire" else 0.0
        gy_pre = pp.make_trapezoid("y", area=area, system=system)  # new event every TR
        gy_rew = pp.make_trapezoid("y", area=-area, system=system)

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=TRID[segment]))
        seq.add_block(gx_pre, gy_pre, gz_reph)
        if segment == "dummy":
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, gy_rew, gz_spoil)
        seq.add_block(pp.make_delay(tr_delay))
    return seq


seq = naive_gre2d()
print("Pulseq timing check passed:", seq.check_timing()[0])

# %% [markdown]
# ## Run the chain
#
# Conversion and hardware checks both pass:

# %%
report = ge.from_seq(seq)
print(report)
print(ge.check())

# %% [markdown]
# ...but validation does not:

# %%
ok = ge.validate()
print("pge2.validate:", ok)
print("\n".join(ge.last_messages[:5]))

# %% [markdown]
# ## What happened
#
# Look at two phase-encoding lines. `make_trapezoid` picks the shortest
# trapezoid for each area, so the ramp and flat-top times change from line
# to line:

# %%
for iy in (0, n // 4, n // 2 - 1):
    g = pp.make_trapezoid("y", area=pe_areas[iy], system=system)
    print(
        f"line {iy:3d}: rise {g.rise_time * 1e6:5.0f} us, flat {g.flat_time * 1e6:5.0f} us, "
        f"amplitude {g.amplitude / system.gamma * 1e3:6.2f} mT/m"
    )

# %% [markdown]
# The `acquire` segment was defined by its first instance, line 0. Every other
# line is played with line 0's ramp and flat-top times, scaled to the new
# peak amplitude, so its gradient area, and the k-space line it encodes,
# is wrong. Nothing fails at download or during the scan; only the image is
# wrong. That is why `pge2.validate` belongs in every workflow.

# %% [markdown]
# ## Your turn
#
# Rewrite the loop so that pge2 plays the intended gradients:
#
# 1. Create **one** phase-encoding trapezoid before the loop, sized for the
#    largest |ky| area.
# 2. In the loop, scale it with `pp.scale_grad` (both prephaser and rewinder).
# 3. Check that `ge.validate()` returns `True` and that the report shows
#    fewer base blocks.

# %% tags=["raises-exception"]
def fixed_gre2d():
    seq = pp.Sequence(system)
    # TODO: create the phase-encoding trapezoid here
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        segment = "dummy" if iy < -pislquant else "receive_gain" if iy < 0 else "acquire"
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360

        # TODO: replace these two lines
        gy_pre = ...
        gy_rew = ...

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=TRID[segment]))
        seq.add_block(gx_pre, gy_pre, gz_reph)
        if segment == "dummy":
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, gy_rew, gz_spoil)
        seq.add_block(pp.make_delay(tr_delay))
    return seq


print(ge.from_seq(fixed_gre2d()))
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
def fixed_gre2d():
    seq = pp.Sequence(system)
    gy_base = pp.make_trapezoid("y", area=np.max(np.abs(pe_areas)), duration=1e-3, system=system)
    pe_scales = pe_areas / gy_base.area
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        segment = "dummy" if iy < -pislquant else "receive_gain" if iy < 0 else "acquire"
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360

        pe = pe_scales[iy] if segment == "acquire" else 0.0
        gy_pre = pp.scale_grad(gy_base, pe)
        gy_rew = pp.scale_grad(gy_base, -pe)

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=TRID[segment]))
        seq.add_block(gx_pre, gy_pre, gz_reph)
        if segment == "dummy":
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, gy_rew, gz_spoil)
        seq.add_block(pp.make_delay(tr_delay))
    return seq


print(ge.from_seq(fixed_gre2d()))
print("pge2.validate:", ge.validate())

# %% [markdown]
# ## Going further: "it works" is not the same as "it is right"
#
# Make the in-loop trapezoid with a fixed duration,
# `pp.make_trapezoid("y", area=area, duration=1e-3, system=system)`, and run
# the chain again. With pypulseq 1.5 it validates, because a fixed duration
# happens to give the same ramp times for every area. It still costs two extra
# base blocks, and it depends on how a library version rounds ramp times. One
# event, scaled in the loop, does not.

# %% [markdown]
# ## Take-home
#
# - Create every RF, gradient and ADC event once, before the loop.
# - In the loop, change only amplitudes (`pp.scale_grad`), RF/ADC phase and
#   frequency, rotations, and the length of pure delay blocks.
# - Run `pge2.validate`: a sequence can pass every other check and still play
#   the wrong gradients.
