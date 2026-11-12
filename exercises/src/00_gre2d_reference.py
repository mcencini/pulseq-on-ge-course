# %% [markdown]
# # 00 · A GE-friendly 2D gradient echo
#
# Every exercise in this part of the course starts from the same sequence: a
# single-slice, RF-spoiled 2D gradient echo (gre2d). This notebook builds the
# version that follows the pge2 design rules, and runs it through the same
# chain you will use before every scan:
#
# 1. **`pulseg.fromSeq`** groups the blocks of the `.seq` file into
#    *segments*, the units the GE sequencer plays.
# 2. **`pge2.check`** checks block timing, peak B1, peak gradient, slew rate
#    and PNS against the scanner.
# 3. **`pge2.validate`** replays every segment instance as the interpreter
#    will play it and compares the waveforms with the `.seq` file.
# 4. **`pge2.serialize`** writes the `.pge` file that goes to the scanner.
#
# pulseg and pge2 are MATLAB toolboxes. Here they run in GNU Octave, called
# from Python; the `ge` object below does that for you.
#
# Reference: [pge2 sequence design rules](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/docs/pge2-sequence-design-rules.md).

# %%
#INCLUDE _setup.py

# %% [markdown]
# ## System limits
#
# pge2 places the waveforms of the `.seq` file directly on the hardware, with
# no interpolation, so every time in the file must sit on the GE raster:
# 4 µs for gradients and block durations, 2 µs for RF samples and ADC dwell.
# Notebook 01 shows what happens otherwise.
#
# The gradient limits are divided by √3 so that the same sequence can be
# played in any oblique plane.

# %%
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=100e-6,
    rf_ringdown_time=60e-6,
    adc_dead_time=40e-6,
    rf_raster_time=2e-6,
    adc_raster_time=2e-6,
    grad_raster_time=4e-6,
    block_duration_raster=4e-6,
    B0=3.0,
)

# %% [markdown]
# ## Events: defined once, before the scan loop
#
# A GE sequence is built from a small set of waveforms that are replayed many
# times, changing only their amplitude, the RF/ADC phase and frequency, and
# the rotation. pulseg follows the same idea: it reduces every block to a
# **base block** with normalised amplitude.
#
# So every RF pulse, gradient and ADC event is created here, once. Inside the
# loop we only scale them with `pp.scale_grad` and set phases. Notebook 02
# shows what goes wrong when events are created inside the loop.

# %%
fov = 240e-3
n = 128
slice_thickness = 5e-3
dwell = 20e-6
tr_delay = 5e-3

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

# One phase-encoding trapezoid, sized for the largest |ky|; each line scales it.
pe_areas = (np.arange(n) - n / 2) * delta_k
gy_pre = pp.make_trapezoid("y", area=np.max(np.abs(pe_areas)), duration=1e-3, system=system)
pe_scales = pe_areas / gy_pre.area

gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

# %% [markdown]
# ## Scan loop: one TRID per kind of TR
#
# A **segment** is a run of blocks that is always played together, such as a
# TR. It starts at a block carrying a `TRID` label and ends just before the
# next `TRID` label. The first time a TRID appears, pge2 stores that run of
# blocks as the segment's definition; later instances replay it with their
# own amplitudes and phases.
#
# This scan has three kinds of TR, so three TRIDs:
#
# | TRID | TR | ADC |
# |---|---|---|
# | 1 `dummy` | approach to steady state | off |
# | 2 `receive_gain` | Auto Prescan sets the receive gain on these (`pislquant` of them) | on, no phase encoding |
# | 3 `acquire` | one phase-encoding line each | on |
#
# Dummy and imaging TRs need different TRIDs because an ADC is present in one
# and absent in the other (notebook 03).

# %%
n_dummy = 20
pislquant = 10
TRID = {"dummy": 1, "receive_gain": 2, "acquire": 3}

seq = pp.Sequence(system)
rf_phase = 0.0
rf_increment = 0.0
for iy in range(-n_dummy - pislquant, n):
    if iy < -pislquant:
        segment = "dummy"
    elif iy < 0:
        segment = "receive_gain"
    else:
        segment = "acquire"

    # RF spoiling: quadratic phase increment of 117 degrees
    rf.phase_offset = np.deg2rad(rf_phase)
    adc.phase_offset = np.deg2rad(rf_phase)
    rf_increment = (rf_increment + 117) % 360
    rf_phase = (rf_phase + rf_increment) % 360

    pe = pe_scales[iy] if segment == "acquire" else 0.0

    seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=TRID[segment]))
    seq.add_block(gx_pre, pp.scale_grad(gy_pre, pe), gz_reph)
    if segment == "dummy":
        seq.add_block(gx)
    else:
        seq.add_block(gx, adc)
    seq.add_block(gx_spoil, pp.scale_grad(gy_pre, -pe), gz_spoil)
    seq.add_block(pp.make_delay(tr_delay))

seq.set_definition("FOV", [fov, fov, slice_thickness])
seq.set_definition("Name", "gre2d")

ok, report = seq.check_timing()
print("Pulseq timing check:", "passed" if ok else report)

# %%
tr = sum(seq.block_durations[i] for i in range(1, 6))
seq.plot(time_range=(0, 3 * tr));

# %% [markdown]
# ## 1. From blocks to segments: `pulseg.fromSeq`
#
# The report lists each virtual segment, how many times it is played, and its
# **layout**: one letter per base block, `d` for a pure delay of fixed
# length and `v` for a pure delay whose length changes between instances.

# %%
report = ge.from_seq(seq)
report

# %% [markdown]
# Things to notice:
#
# - 790 blocks became 3 segments built from only 5 base blocks.
# - `receive_gain` and `acquire` have the same layout `ABEDd`: same events,
#   different TRID. That is fine; the TRID marks a distinct part of the scan.
# - `dummy` uses base block `C` (readout gradient alone) where the others use
#   `E` (readout gradient with ADC).
# - Base block `B` is the prephasing block. Its phase-encoding gradient has a
#   different amplitude in every instance, yet it is one base block, because
#   every line uses `gy_pre` scaled.

# %% [markdown]
# ## 2. Hardware checks: `pge2.check`
#
# Returns peak B1 (G), peak gradient (G/cm) and peak slew rate (G/cm/ms)
# over the whole scan. It raises an error if any block breaks a timing rule or
# a hardware limit.

# %%
ge.check()

# %% [markdown]
# ## 3. Does the interpreter play what the `.seq` file says? `pge2.validate`
#
# This is the check that catches sequences that download, run, and give the
# wrong image.

# %%
ge.validate()

# %% [markdown]
# ## 4. Write the `.pge` file

# %%
ge.serialize("gre2d.pge", pislquant=pislquant)

# %% [markdown]
# ## What made this sequence GE-friendly
#
# 1. System rasters set to the GE values (notebook 01).
# 2. Every event created once before the loop; amplitudes changed with
#    `pp.scale_grad` (notebook 02).
# 3. One TRID per kind of TR, set on the first block of every TR, so each
#    segment has the same blocks and events in every instance (notebook 03).
