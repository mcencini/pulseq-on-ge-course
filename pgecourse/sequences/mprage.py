"""3D MPRAGE with a configurable TRID placement (notebook 03b)."""

import numpy as np
import pypulseq as pp

from .gre2d import GE_SYSTEM

#: Ready-made TRID placements. Each maps a block kind to a TRID value, or
#: None for no label. The kinds are, in the order they are played in a shot:
#: "inversion" (inversion pulse, then spoiler and TI delay), "readout" (first
#: block of every readout TR) and "recovery" (pure delay ending the shot).
PLACEMENTS = {
    # one TRID per shot: the whole shot is one segment
    "per_shot": {"inversion": 1, "readout": None, "recovery": None},
    # preparation and readout TR; the recovery delay joins the last readout
    # TR, which then has one block more than the others (refused)
    "two": {"inversion": 1, "readout": 2, "recovery": None},
    # inversion + TI, readout TR, recovery delay
    "three": {"inversion": 1, "readout": 2, "recovery": 3},
}


def mprage(
    choose_trid="three",
    system=GE_SYSTEM,
    fov=(256e-3, 256e-3, 192e-3),
    matrix=(64, 64, 16),
    flip_angle=8,
    dwell=16e-6,
    ti=0.9,
    shot_tr=2.3,
):
    """Inversion-prepared 3D spoiled gradient echo, one shot per kz.

    One shot = non-selective inversion, spoiler, TI delay, ``matrix[1]``
    readout TRs (ky), then a recovery delay that completes the shot TR.

    Parameters
    ----------
    choose_trid : str or callable
        A key of ``PLACEMENTS``, or a function ``choose_trid(kind)`` that
        returns the TRID for a block of that kind ("inversion", "readout",
        "recovery"), or None for no label.
    """
    if isinstance(choose_trid, str):
        placement = PLACEMENTS[choose_trid]
        choose_trid = placement.get

    def labels(kind):
        trid = choose_trid(kind)
        return [pp.make_label(type="SET", label="TRID", value=trid)] if trid is not None else []

    nx, ny, nz = matrix
    seq = pp.Sequence(system)

    rf_inv = pp.make_block_pulse(np.pi, duration=1e-3, system=system, use="inversion")
    gz_inv_spoil = pp.make_trapezoid("z", area=8 / (fov[2] / nz), system=system)

    rf = pp.make_block_pulse(np.deg2rad(flip_angle), duration=100e-6, system=system, use="excitation")
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
    assert ti_delay > 0 and rec_delay > 0, "TI or shot TR too short"

    rf_phase = rf_inc = 0.0
    for iz in range(nz):
        seq.add_block(rf_inv, *labels("inversion"))
        seq.add_block(gz_inv_spoil)
        seq.add_block(pp.make_delay(ti_delay))
        for iy in range(ny):
            rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
            rf_inc = (rf_inc + 117) % 360
            rf_phase = (rf_phase + rf_inc) % 360
            sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
            seq.add_block(rf, *labels("readout"))
            seq.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
            seq.add_block(gx, adc)
            seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
        seq.add_block(pp.make_delay(rec_delay), *labels("recovery"))

    seq.set_definition("FOV", list(fov))
    seq.set_definition("Name", "mprage")
    return seq
