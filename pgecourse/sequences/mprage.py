"""3D MPRAGE with three ways of placing the TRID labels (notebook 03)."""

import numpy as np
import pypulseq as pp

from .gre2d import GE_SYSTEM


def mprage(
    system=GE_SYSTEM,
    trid="split",
    fov=(256e-3, 256e-3, 192e-3),
    matrix=(64, 64, 16),
    flip_angle=8,
    dwell=16e-6,
    ti=0.9,
    shot_tr=2.3,
):
    """Inversion-prepared 3D spoiled gradient echo.

    One shot = non-selective inversion, inversion delay, ``matrix[1]``
    readout TRs (ky inner loop), recovery delay. One shot per kz.

    Parameters
    ----------
    trid : {"single", "per_shot", "split"}
        ``"single"``: one TRID on the first block of the scan.
        ``"per_shot"``: one TRID on every inversion; a shot is one segment.
        ``"split"``: three TRIDs: inversion + TI delay, readout TR,
        recovery delay.
    """
    nx, ny, nz = matrix
    seq = pp.Sequence(system)

    # inversion: non-selective hard pulse, then spoiler
    rf_inv = pp.make_block_pulse(np.pi, duration=1e-3, system=system, use="inversion")
    gz_inv_spoil = pp.make_trapezoid("z", area=8 / (fov[2] / nz), system=system)

    # readout TR: non-selective excitation
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

    tr_blocks = [
        pp.calc_duration(rf),
        pp.calc_duration(gx_pre, gy_pe, gz_pe),
        pp.calc_duration(gx),
        pp.calc_duration(gx_spoil, gy_pe, gz_pe),
    ]
    readout_time = ny * sum(tr_blocks)
    inv_time = pp.calc_duration(rf_inv) + pp.calc_duration(gz_inv_spoil)
    ti_delay = ti - inv_time - readout_time / 2
    rec_delay = shot_tr - inv_time - ti_delay - readout_time
    grid = system.block_duration_raster
    ti_delay = np.round(ti_delay / grid) * grid
    rec_delay = np.round(rec_delay / grid) * grid
    assert ti_delay > 0 and rec_delay > 0, "TI or shot TR too short"

    def label(value, first):
        if trid == "single":
            return [pp.make_label(type="SET", label="TRID", value=1)] if first else []
        if trid == "per_shot":
            return [pp.make_label(type="SET", label="TRID", value=1)] if value == 1 else []
        return [pp.make_label(type="SET", label="TRID", value=value)]

    rf_phase = rf_inc = 0.0
    first = True
    for iz in range(nz):
        seq.add_block(rf_inv, *label(1, first))
        first = False
        seq.add_block(gz_inv_spoil)
        seq.add_block(pp.make_delay(ti_delay))
        for iy in range(ny):
            rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
            rf_inc = (rf_inc + 117) % 360
            rf_phase = (rf_phase + rf_inc) % 360
            sy, sz = ky[iy] / gy_pe.area, kz[iz] / gz_pe.area
            seq.add_block(rf, *label(2, False))
            seq.add_block(gx_pre, pp.scale_grad(gy_pe, sy), pp.scale_grad(gz_pe, sz))
            seq.add_block(gx, adc)
            seq.add_block(gx_spoil, pp.scale_grad(gy_pe, -sy), pp.scale_grad(gz_pe, -sz))
        seq.add_block(pp.make_delay(rec_delay), *label(3, False))

    seq.set_definition("FOV", list(fov))
    seq.set_definition("Name", "mprage")
    return seq
