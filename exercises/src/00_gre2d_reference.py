# %% [markdown]
# # 00 · 2D spoiled GRE for pge2
#
# Reference sequence for the course. Every other notebook starts from it.
#
# Workflow, as in the [HarmonizedMRI pge2 examples](https://github.com/HarmonizedMRI/SequenceExamples-GE/tree/main/pge2):
#
# `.seq` file ⇒ PulSeg object (`pulseg.fromSeq`) ⇒ `pge2.check`, `pge2.validate` ⇒ `.pge` file ⇒ scanner
#
# pulseg and pge2 are MATLAB toolboxes; here they run in GNU Octave, called
# from Python through the `ge` object. Read the code and the comments
# carefully.
#
# Design rules: [pge2-sequence-design-rules.md](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/docs/pge2-sequence-design-rules.md).

# %%
#INCLUDE _setup.py

# %% [markdown]
# ## Write the `.seq` file

# %%
# System parameters for sequence design.
#
# pge2 plays the waveforms of the .seq file directly, with no interpolation,
# so every time in the file must be on the GE raster (notebook 01).
#
# Block boundaries are invisible inside a segment, so set the dead and
# ringdown times to zero. Otherwise pypulseq may silently insert delays that
# you did not intend.
#
# Gradients are reduced by a factor of 1/sqrt(3) to accommodate oblique
# orientations.
system = pp.Opts(
    max_grad=50 / np.sqrt(3),
    grad_unit="mT/m",
    max_slew=120 / np.sqrt(3),
    slew_unit="T/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    rf_raster_time=2e-6,          # 2 us, or any integer multiple
    adc_raster_time=2e-6,         # GE dwell time must be a multiple of 2 us
    grad_raster_time=4e-6,        # 4 us, or any integer multiple
    block_duration_raster=4e-6,   # 4 us, or any integer multiple
    B0=3.0,
)

# %%
# Acquisition parameters
fov = 240e-3              # field of view (m)
n = 128                   # matrix size
slice_thickness = 5e-3    # (m)
flip_angle = 6            # (degrees)
dwell = 20e-6             # ADC sample time (s)
tr_delay = 5e-3           # delay at the end of each TR (s)
rf_spoiling_increment = 117   # (degrees)

n_dummy = 20      # shots to reach steady state
pislquant = 10    # shots used by Auto Prescan to set the receive gain

# %%
# Create every RF, gradient and ADC event here, once.
# These become the 'base blocks' of the PulSeg representation.
# In the scan loop we only scale amplitudes and set phases; we do NOT create
# new events there, since events created on the fly may differ from these in
# subtle ways (notebook 02).

rf, gz, _ = pp.make_sinc_pulse(
    flip_angle=np.deg2rad(flip_angle),
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

# One phase-encoding gradient, sized for the largest |ky|; each line scales it.
phase_areas = (np.arange(n) - n / 2) * delta_k
gy_pre = pp.make_trapezoid("y", area=np.max(np.abs(phase_areas)), duration=1e-3, system=system)
pe_scales = phase_areas / gy_pre.area

gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

# %%
# Segment labels.
#
# A segment starts at a block with a TRID label and runs up to (not
# including) the next TRID label. Use one TRID per logically distinct
# sub-sequence. pypulseq has no seq.add_TRID('name') as MATLAB Pulseq does,
# so we name the integer labels here.
TRID = {
    "dummy": pp.make_label(type="SET", label="TRID", value=1),
    "receive_gain": pp.make_label(type="SET", label="TRID", value=2),
    "acquire": pp.make_label(type="SET", label="TRID", value=3),
}

# %%
# Scan loop
# iy < -pislquant         dummy shots to reach steady state (no ADC)
# -pislquant <= iy < 0    ADC on, used for receive gain calibration on GE
# iy >= 0                 image acquisition
seq = pp.Sequence(system)

rf_phase = 0.0
rf_increment = 0.0
for iy in range(-n_dummy - pislquant, n):
    is_dummy_tr = iy < -pislquant
    is_receive_gain_tr = -pislquant <= iy < 0

    # RF spoiling
    rf.phase_offset = np.deg2rad(rf_phase)
    adc.phase_offset = np.deg2rad(rf_phase)
    rf_increment = (rf_increment + rf_spoiling_increment) % 360
    rf_phase = (rf_phase + rf_increment) % 360

    # Mark the start of each segment instance with a TRID label; the
    # following blocks of the TR are NOT labelled (akin to SEQLENGTH in EPIC).
    #
    #  'segment': the definition, stored the first time a TRID appears,
    #      with normalised waveform amplitudes.
    #  'segment instance': one execution of a segment. All instances of a
    #      segment contain the same blocks and events; only these may change:
    #        - RF and gradient waveform amplitude
    #        - RF frequency offset
    #        - RF/ADC phase offsets
    #        - duration of pure delay blocks
    if is_dummy_tr:
        trid = TRID["dummy"]
    elif is_receive_gain_tr:
        trid = TRID["receive_gain"]
    else:
        trid = TRID["acquire"]

    # Phase encoding off (amplitude 0) until iy >= 0
    pe = pe_scales[iy] if iy >= 0 else 0.0

    seq.add_block(rf, gz, trid)
    seq.add_block(gx_pre, pp.scale_grad(gy_pre, pe), gz_reph)
    if is_dummy_tr:
        seq.add_block(gx)  # same gradient, no ADC: needs its own TRID (notebook 03a)
    else:
        seq.add_block(gx, adc)
    seq.add_block(gx_spoil, pp.scale_grad(gy_pre, -pe), gz_spoil)
    seq.add_block(pp.make_delay(tr_delay))

    # We're now at the end of a segment instance

# %%
# Check sequence timing (pypulseq's own check, against the rasters in `system`)
ok, error_report = seq.check_timing()
print("Timing check passed" if ok else error_report)

seq.set_definition("FOV", [fov, fov, slice_thickness])
seq.set_definition("Name", "gre2d")
seq.write("gre2d.seq")

tr = sum(seq.block_durations[i] for i in range(1, 6))
seq.plot(time_range=(0, 3 * tr));

# %% [markdown]
# ## Convert to a PulSeg object: `pulseg.fromSeq`
#
# Layout: one letter per base block; `d` is a pure delay of fixed duration,
# `v` one whose duration changes between instances.

# %%
psg = ge.from_seq(seq)
psg

# %% [markdown]
# - 790 blocks, 3 segments, 5 base blocks.
# - `dummy` has `C` (readout gradient alone) where the others have `E`
#   (readout gradient with ADC).
# - `B` is one base block for all phase-encoding steps: only its amplitude
#   changes.

# %% [markdown]
# ## Define the hardware parameters of your scanner
#
# These are the arguments of `pge2.opts`.

# %%
ge.scanner = dict(
    psd_rf_wait=100e-6,    # RF-gradient delay (s), scanner-specific
    psd_grd_wait=100e-6,   # ADC-gradient delay (s), scanner-specific
    b1_max=0.25,           # Gauss
    g_max=5,               # Gauss/cm
    slew_max=20,           # Gauss/cm/ms
    coil="xrm",            # see pge2.opts(): 'xrm' (MR750), 'hrmw' (Premier), 'magnus', ...
)

# %% [markdown]
# ## Check timing, PNS and b1/gradient limits: `pge2.check`
#
# Gradient heating, SAR and the other RF checks are done by the interpreter
# at scan time.

# %%
params = ge.check(pns_weights=(1, 1, 1))  # directional PNS weights, see pge2.pns()
params

# %% [markdown]
# ## Validate the PulSeg object against the `.seq` file: `pge2.validate`
#
# Cycles through all segment instances and stops at the first mismatch.
# Strongly recommended before every scan: it catches sequences that download
# and run, but do not play what the `.seq` file says.

# %%
ge.validate()

# %% [markdown]
# ## Write the `.pge` file: `pge2.serialize`

# %%
ge.serialize("gre2d.pge", pislquant=pislquant)

# %% [markdown]
# ## Next
#
# - 01: raster times
# - 02: events created in the scan loop
# - 03a–c: TRID placement
