# %% [markdown]
# # 03 · Risk #3: where the TRID labels go
#
# Segment boundaries come only from `TRID` labels. A segment runs from a block
# carrying a TRID up to, not including, the next TRID. Two rules follow:
#
# - **Strict:** every instance of a segment has the same blocks, with the same
#   kinds of events (RF, gradients, ADC, trigger) in each. Amplitudes, phases,
#   frequencies and the length of pure delays may change.
# - **Soft:** keep segments short, about one TR. The whole segment is loaded
#   into the waveform memory of the sequencer, which is limited.
#
# This notebook breaks each rule with the gre2d.

# %%
#INCLUDE _setup.py

# %%
from pgecourse.sequences import GE_SYSTEM as system

# %% [markdown]
# Events as in notebook 00. `gre2d_loop` builds the scan loop and takes a
# function that chooses the TRID of each TR, so that only the labelling
# changes between the cases below.

# %%
fov = 240e-3
n = 128
slice_thickness = 5e-3
dwell = 20e-6
tr_delay = 5e-3
n_dummy = 20
pislquant = 10

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
pe_areas = (np.arange(n) - n / 2) * delta_k
gy_pre = pp.make_trapezoid("y", area=np.max(np.abs(pe_areas)), duration=1e-3, system=system)
pe_scales = pe_areas / gy_pre.area
gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
gz_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)


def trid_label(value):
    return pp.make_label(type="SET", label="TRID", value=value)


def gre2d_loop(choose_trid):
    """choose_trid(iy, segment) returns a TRID value, or None for no label."""
    seq = pp.Sequence(system)
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        segment = "dummy" if iy < -pislquant else "receive_gain" if iy < 0 else "acquire"
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        pe = pe_scales[iy] if segment == "acquire" else 0.0

        trid = choose_trid(iy, segment)
        labels = [trid_label(trid)] if trid is not None else []
        seq.add_block(rf, gz, *labels)
        seq.add_block(gx_pre, pp.scale_grad(gy_pre, pe), gz_reph)
        if segment == "dummy":
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pre, -pe), gz_spoil)
        seq.add_block(pp.make_delay(tr_delay))
    return seq


# %% [markdown]
# ## Case A: dummy TRs share the imaging TRID
#
# It is tempting to label every TR the same way. The dummy TRs have no ADC,
# the others do.

# %%
seq_a = gre2d_loop(lambda iy, segment: 1)
try:
    ge.from_seq(seq_a)
except pgecourse.PGE2Error as err:
    print("pulseg.fromSeq:", err)

# %% [markdown]
# The first instance of TRID 1 is a dummy TR, so the segment definition has a
# readout block *without* ADC. When a later instance asks for an ADC in that
# block, the definition has none to play. pulseg stops here. A sequencer that
# accepted it would play the scan without acquiring a single sample.
#
# The same applies to any event that is present in some instances and absent
# in others: an RF pulse turned off, a gradient present only on some lines,
# a block inserted with an `if`. To vary timing, keep a pure delay block in
# every instance and change only its length.

# %% [markdown]
# ## Case B: one TRID for the whole scan
#
# Label only the very first block:

# %%
seq_b = gre2d_loop(lambda iy, segment: 1 if iy == -n_dummy - pislquant else None)
report_b = ge.from_seq(seq_b)
print(report_b)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# Every check passes. But the scan is now one segment of 790 blocks, played
# once, and pge2 has to load all of it into the sequencer's waveform memory at
# the same time. Its size grows with the number of TRs, while the memory
# does not, so a longer version of the same scan, or the same scan on another
# system, may fail to load.
#
# The opposite extreme, a TRID on every block, is not better either. Each
# segment ends with a 117 µs gap on the scanner, gradients have to return to
# zero at every segment boundary, and the code no longer says what a TR is.

# %% [markdown]
# ## Your turn
#
# Write a `choose_trid` that gives three segments, `dummy`, `receive_gain`
# and `acquire`, each one TR long. Check that:
#
# - `pulseg.fromSeq` reports 3 segments with 20, 10 and 128 instances;
# - `pge2.check` and `pge2.validate` pass.

# %% tags=["raises-exception"]
def choose_trid(iy, segment):
    ...  # TODO


report = ge.from_seq(gre2d_loop(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% cellView="form"
# @title Solution (double-click to show the code)
TRID = {"dummy": 1, "receive_gain": 2, "acquire": 3}


def choose_trid(iy, segment):
    return TRID[segment]


report = ge.from_seq(gre2d_loop(choose_trid))
print(report)
print(ge.check())
print("pge2.validate:", ge.validate())

# %% [markdown]
# ## Take-home
#
# - Put a TRID on the first block of every TR, and use one TRID value per
#   *kind* of TR: dummy, calibration, imaging, navigator...
# - Within a TRID, never add or remove a block or an event. Vary amplitudes,
#   phases and the length of pure delays instead.
# - Coming next, with the same rules: inversion-prepared 3D sequences
#   (MPRAGE) and multi-slice sequences with a pure delay segment.
