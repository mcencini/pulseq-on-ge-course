"""2D CPMG fast spin echo (notebook 04)."""

import numpy as np
import pypulseq as pp

from .gre2d import GE_SYSTEM

#: Ready-made TRID placements: block kind -> TRID value, or None for no
#: label. Kinds: "excitation" (90 degree pulse, first block of a shot),
#: "echo" (180 degree pulse, first block of every echo spacing), "fill"
#: (pure delay completing the TR).
PLACEMENTS = {
    "per_echo": {"excitation": 1, "echo": 2, "fill": 3},
    "train": {"excitation": 1, "echo": None, "fill": 3},
}


def fse(
    choose_trid="train",
    packed=False,
    system=GE_SYSTEM,
    fov=240e-3,
    nx=128,
    ny=64,
    etl=8,
    slice_thickness=5e-3,
    dwell=14e-6,
    tr=1.0,
):
    """2D CPMG fast spin echo, ``ny / etl`` shots of ``etl`` echoes.

    Each echo spacing is four blocks: 180 degree pulse with slice select,
    crusher + phase encoding, readout, rewinder + crusher.

    Parameters
    ----------
    choose_trid : str or callable
        A key of ``PLACEMENTS``, or a function ``choose_trid(kind)`` returning
        the TRID for a block of that kind, or None for no label.
    packed : bool
        If True, the z gradient from the crusher before each 180 degree pulse,
        through its slice select, to the crusher after it is one extended
        trapezoid split at the block boundaries (non-zero there). If False,
        slice select and crushers are separate trapezoids that start and end
        at zero in every block.

    Returns
    -------
    seq : pypulseq.Sequence
    esp : float
        Echo spacing in the ``.seq`` file, in s.
    """
    if isinstance(choose_trid, str):
        choose_trid = PLACEMENTS[choose_trid].get

    def labels(kind):
        trid = choose_trid(kind)
        return [pp.make_label(type="SET", label="TRID", value=trid)] if trid is not None else []

    R = system.grad_raster_time
    slew = 0.98 * system.max_slew
    g_crush = 0.9 * system.max_grad

    def rup(t):
        return np.ceil(round(t / R, 6)) * R

    def ramp(dg):
        return max(R, rup(abs(dg) / slew))

    def ext(times, amps):
        keep = [0] + [i for i in range(1, len(times)) if times[i] - times[i - 1] > 1e-9]
        return pp.make_extended_trapezoid(
            "z", times=np.array([times[i] for i in keep]), amplitudes=np.array([amps[i] for i in keep]), system=system
        )

    def lobe(area, g0, g1, dur=None):
        """z lobe from level g0 to level g1 through a plateau, zero-padded to dur."""
        g = g_crush
        r1, r2 = ramp(g - g0), ramp(g - g1)
        if area < (g0 + g) / 2 * r1 + (g1 + g) / 2 * r2:  # lower the plateau
            lo, hi = max(g0, g1), g_crush
            for _ in range(60):
                g = (lo + hi) / 2
                r1, r2 = ramp(g - g0), ramp(g - g1)
                if (g0 + g) / 2 * r1 + (g1 + g) / 2 * r2 > area:
                    hi = g
                else:
                    lo = g
            g = lo
            r1, r2 = ramp(g - g0), ramp(g - g1)
        flat = rup((area - (g0 + g) / 2 * r1 - (g1 + g) / 2 * r2) / g)
        length = r1 + flat + r2
        dur = length if dur is None else dur
        t, a = [0, r1, r1 + flat, length], [g0, g, g, g1]
        if dur - length > 1e-9:
            if g1 == 0:
                t, a = t + [dur], a + [0]
            else:
                t, a = [0] + [x + dur - length for x in t], [0] + a
        return ext(t, a)

    dk = 1 / fov
    rf90, gz90, _ = pp.make_sinc_pulse(
        np.pi / 2, duration=1.6e-3, slice_thickness=slice_thickness, time_bw_product=4,
        phase_offset=np.pi / 2, system=system, return_gz=True, use="excitation",
    )
    t_rf = 3.2e-3
    rf180 = pp.make_sinc_pulse(np.pi, duration=t_rf, slice_thickness=slice_thickness, time_bw_product=4,
                               system=system, use="refocusing")
    g_ss = 4 / t_rf / slice_thickness
    a_crush = 4 / slice_thickness
    gx = pp.make_trapezoid("x", flat_area=nx * dk, flat_time=nx * dwell, system=system)
    adc = pp.make_adc(nx, duration=gx.flat_time, delay=gx.rise_time, system=system)
    pe = (np.arange(ny) - ny / 2) * dk
    order = np.arange(ny).reshape(etl, -1).T  # shot, echo -> phase-encoding line

    gy_min = pp.make_trapezoid("y", area=pe.max() - pe.min(), system=system)
    gx_pre_min = pp.make_trapezoid("x", area=gx.area / 2, system=system)
    if packed:
        rf180.delay = 0
        z_rf = ext([0, t_rf], [g_ss, g_ss])
        lobe_min = max(pp.calc_duration(lobe(a_crush, g_ss, 0)), pp.calc_duration(lobe(a_crush - gz90.area / 2, 0, g_ss)))
        dur_c = rup(max(lobe_min, pp.calc_duration(gy_min), pp.calc_duration(gx_pre_min)))
        z_after = lobe(a_crush, g_ss, 0, dur_c)
        z_before = lobe(a_crush, 0, g_ss, dur_c)
        z_first = lobe(a_crush - gz90.area / 2, 0, g_ss, dur_c)
        z_last = lobe(a_crush, 0, 0, max(dur_c, pp.calc_duration(lobe(a_crush, 0, 0))))
        rf_block = [rf180, z_rf]
    else:
        gss = pp.make_trapezoid("z", amplitude=g_ss, flat_time=t_rf, rise_time=ramp(g_ss), system=system)
        rf180.delay = gss.rise_time
        crush_min = pp.calc_duration(pp.make_trapezoid("z", area=a_crush, system=system))
        dur_c = rup(max(crush_min, pp.calc_duration(gy_min), pp.calc_duration(gx_pre_min)))
        z_after = z_before = z_last = pp.make_trapezoid("z", area=a_crush, duration=dur_c, system=system)
        z_first = pp.make_trapezoid("z", area=a_crush - gz90.area / 2, duration=dur_c, system=system)
        rf_block = [rf180, gss]
    gy_pe = pp.make_trapezoid("y", area=pe.max() - pe.min(), duration=dur_c, system=system)
    gx_pre = pp.make_trapezoid("x", area=gx.area / 2, duration=dur_c, system=system)

    esp = pp.calc_duration(*rf_block) + 2 * dur_c + pp.calc_duration(gx)
    half90 = pp.calc_duration(rf90, gz90) - (rf90.delay + rf90.shape_dur / 2)
    tau = rup(esp / 2 - half90 - dur_c - pp.calc_duration(*rf_block) / 2)
    assert tau >= 0, "echo spacing too short for the excitation side; lengthen the readout"

    seq = pp.Sequence(system)
    for shot in range(order.shape[0]):
        n0 = len(seq.block_events)
        seq.add_block(rf90, gz90, *labels("excitation"))
        if tau > 0:
            seq.add_block(pp.make_delay(tau))
        seq.add_block(gx_pre, z_first)
        for e in range(etl):
            scale = pe[order[shot, e]] / gy_pe.area
            seq.add_block(*rf_block, *labels("echo"))
            seq.add_block(z_after, pp.scale_grad(gy_pe, scale))
            seq.add_block(gx, adc)
            seq.add_block(z_before if e < etl - 1 else z_last, pp.scale_grad(gy_pe, -scale))
        used = sum(seq.block_durations[k] for k in list(seq.block_durations)[n0:])
        seq.add_block(pp.make_delay(rup(tr - used)), *labels("fill"))

    seq.set_definition("FOV", [fov, fov, slice_thickness])
    seq.set_definition("Name", "fse")
    return seq, esp
