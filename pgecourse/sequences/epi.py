"""Single-shot 2D EPI with fat saturation (notebook 05)."""

import numpy as np
import pypulseq as pp

from .gre2d import GE_SYSTEM

#: Ready-made TRID placements: block kind -> TRID value, or None for no
#: label. Kinds: "excitation" (fat saturation, first block of the TR),
#: "line" (first block of every readout line), "spoiler" (spoiler after the
#: train), "fill" (pure delay completing the TR).
PLACEMENTS = {
    "per_line": {"excitation": 1, "line": 2, "spoiler": 3, "fill": 4},
    "train": {"excitation": 1, "line": None, "spoiler": None, "fill": 4},
}


def epi(
    choose_trid="train",
    packed=False,
    system=GE_SYSTEM,
    fov=240e-3,
    n=64,
    dwell=4e-6,
    slice_thickness=5e-3,
    tr=0.1,
    repetitions=4,
):
    """Single-shot 2D gradient-echo EPI with fat saturation.

    Parameters
    ----------
    choose_trid : str or callable
        A key of ``PLACEMENTS``, or a function ``choose_trid(kind)`` returning
        the TRID for a block of that kind, or None for no label.
    packed : bool
        If True, every phase blip is split in two halves played at the end of
        one readout block and the start of the next, during the readout ramps
        (as in pypulseq's write_epi): one block per line. If False, each blip
        is a block of its own between two readouts: two blocks per line.

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

    def rup(t):
        return np.ceil(round(t / R, 6)) * R

    dk = 1 / fov
    fat_offset = -3.35e-6 * system.B0 * system.gamma
    fs = pp.make_gauss_pulse(np.deg2rad(110), duration=4e-3, bandwidth=abs(fat_offset), freq_offset=fat_offset,
                             system=system, use="saturation")
    g_fs = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)
    rf, gz, _ = pp.make_sinc_pulse(np.pi / 2, duration=2e-3, slice_thickness=slice_thickness, time_bw_product=4,
                                   system=system, return_gz=True, use="excitation")
    gx = pp.make_trapezoid("x", flat_area=n * dk, flat_time=n * dwell, system=system)
    adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
    blip_dur = max(rup(2 * np.sqrt(dk / system.max_slew)),
                   pp.calc_duration(pp.make_trapezoid("y", area=-dk, system=system)))
    gy = pp.make_trapezoid("y", area=-dk, duration=blip_dur, system=system)
    t_pre = rup(max(pp.calc_duration(pp.make_trapezoid(ch, area=a, system=system))
                    for ch, a in (("x", gx.area / 2), ("y", n / 2 * dk), ("z", gz.area / 2))))
    gx_pre = pp.make_trapezoid("x", area=-gx.area / 2, duration=t_pre, system=system)
    gy_pre = pp.make_trapezoid("y", area=n / 2 * dk, duration=t_pre, system=system)
    gz_reph = pp.make_trapezoid("z", area=-gz.area / 2, duration=t_pre, system=system)
    g_spoil = pp.make_trapezoid("z", area=4 / slice_thickness, system=system)

    if packed:
        parts = pp.split_gradient_at(grad=gy, time_point=blip_dur / 2, system=system)
        up, down, _ = pp.align(right=parts[0], left=[parts[1], gx])
        downup = pp.add_gradients((down, up), system=system)
        esp = pp.calc_duration(gx)
    else:
        esp = pp.calc_duration(gx) + blip_dur

    seq = pp.Sequence(system)
    for _ in range(repetitions):
        n0 = len(seq.block_events)
        seq.add_block(fs, *labels("excitation"))
        seq.add_block(g_fs)
        seq.add_block(rf, gz)
        seq.add_block(gx_pre, gy_pre, gz_reph)
        g = gx
        for i in range(n):
            if packed:
                blip = [up] if i == 0 else ([down] if i == n - 1 else [downup])
                seq.add_block(g, adc, *blip, *labels("line"))
            else:
                seq.add_block(g, adc, *labels("line"))
                seq.add_block(pp.scale_grad(gy, 0.0) if i == n - 1 else gy)
            g = pp.scale_grad(g, -1)
        seq.add_block(g_spoil, *labels("spoiler"))
        used = sum(seq.block_durations[k] for k in list(seq.block_durations)[n0:])
        seq.add_block(pp.make_delay(rup(tr - used)), *labels("fill"))

    seq.set_definition("FOV", [fov, fov, slice_thickness])
    seq.set_definition("Name", "epi")
    return seq, esp
