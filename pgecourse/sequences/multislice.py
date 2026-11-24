"""Multislice 2D GRE with a pure delay filling the TR (notebook 03c)."""

import numpy as np
import pypulseq as pp

from .gre2d import GE_SYSTEM

#: Ready-made TRID placements: block kind -> TRID value, or None for no
#: label. "slice" is the first block of every slice excitation, "fill" the
#: pure delay that completes the TR after the last slice.
PLACEMENTS = {
    # the fill delay has no label: it joins the last slice's segment instance
    "fill_unlabelled": {"slice": 1, "fill": None},
    # one TRID per TR: all slices and the fill delay in one segment
    "per_tr": {"slice": "first", "fill": None},
    # one segment per slice, one pure delay segment
    "slice_and_fill": {"slice": 1, "fill": 2},
}


def multislice_gre(
    choose_trid="slice_and_fill",
    system=GE_SYSTEM,
    fov=240e-3,
    n=64,
    n_slices=8,
    slice_thickness=5e-3,
    slice_gap=2.5e-3,
    flip_angle=30,
    dwell=20e-6,
    tr=0.2,
):
    """Interleaved multislice 2D spoiled GRE.

    For every phase-encoding line, all slices are excited in turn (slice
    position set by the RF frequency offset), then a pure delay fills the TR.

    Parameters
    ----------
    choose_trid : str or callable
        A key of ``PLACEMENTS``, or a function ``choose_trid(kind, s)`` that
        returns the TRID for the first block of slice ``s`` (kind "slice") or
        for the fill delay (kind "fill", ``s`` = None), or None for no label.
    """
    if isinstance(choose_trid, str):
        placement = PLACEMENTS[choose_trid]

        def choose_trid(kind, s, placement=placement):
            trid = placement[kind]
            if trid == "first":
                return 1 if s == 0 else None
            return trid

    def labels(kind, s=None):
        trid = choose_trid(kind, s)
        return [pp.make_label(type="SET", label="TRID", value=trid)] if trid is not None else []

    seq = pp.Sequence(system)
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
    assert fill > 0, "TR too short for this number of slices"

    rf_phase = rf_inc = 0.0
    for iy in range(n):
        scale = pe[iy] / gy_pe.area
        for s in range(n_slices):
            rf.freq_offset = gz.amplitude * z[s]
            rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
            rf_inc = (rf_inc + 117) % 360
            rf_phase = (rf_phase + rf_inc) % 360
            seq.add_block(rf, gz, *labels("slice", s))
            seq.add_block(gx_pre, pp.scale_grad(gy_pe, scale), gz_reph)
            seq.add_block(gx, adc)
            seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -scale), gz_spoil)
        seq.add_block(pp.make_delay(fill), *labels("fill"))

    seq.set_definition("FOV", [fov, fov, n_slices * (slice_thickness + slice_gap)])
    seq.set_definition("Name", "multislice_gre")
    return seq
