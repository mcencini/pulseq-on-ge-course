"""GE-friendly 2D spoiled gradient echo, as built in notebook 00."""

import numpy as np
import pypulseq as pp

#: System limits for sequence design on a GE scanner: GE raster times, and
#: gradient limits divided by sqrt(3) so that any oblique plane is allowed.
GE_SYSTEM = pp.Opts(
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


def gre2d(
    system=GE_SYSTEM,
    fov=240e-3,
    n=128,
    slice_thickness=5e-3,
    flip_angle=6,
    dwell=20e-6,
    tr_delay=5e-3,
    n_dummy=20,
    pislquant=10,
):
    """Single-slice 2D RF-spoiled gradient echo with three kinds of TR.

    The scan plays ``n_dummy`` dummy TRs (no ADC), then ``pislquant`` TRs
    that Auto Prescan uses to set the receive gain (ADC on, no phase
    encoding), then the ``n`` phase-encoding lines.

    Parameters
    ----------
    system : pypulseq.Opts
        System limits.
    fov : float
        Field of view in m (square).
    n : int
        Matrix size (square).
    slice_thickness : float
        Slice thickness in m.
    flip_angle : float
        Flip angle in degrees.
    dwell : float
        ADC dwell time in s.
    tr_delay : float
        Delay added at the end of every TR, in s.
    n_dummy : int
        Number of dummy TRs.
    pislquant : int
        Number of receive-gain TRs.

    Returns
    -------
    pypulseq.Sequence
    """
    seq = pp.Sequence(system)

    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=np.deg2rad(flip_angle),
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

    trid = {"dummy": 1, "receive_gain": 2, "acquire": 3}

    rf_phase = 0.0
    rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        if iy < -pislquant:
            segment = "dummy"
        elif iy < 0:
            segment = "receive_gain"
        else:
            segment = "acquire"

        rf.phase_offset = np.deg2rad(rf_phase)
        adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360

        pe = pe_scales[iy] if segment == "acquire" else 0.0

        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=trid[segment]))
        seq.add_block(gx_pre, pp.scale_grad(gy_pre, pe), gz_reph)
        if segment == "dummy":
            seq.add_block(gx)
        else:
            seq.add_block(gx, adc)
        seq.add_block(gx_spoil, pp.scale_grad(gy_pre, -pe), gz_spoil)
        seq.add_block(pp.make_delay(tr_delay))

    seq.set_definition("FOV", [fov, fov, slice_thickness])
    seq.set_definition("Name", "gre2d")
    return seq
