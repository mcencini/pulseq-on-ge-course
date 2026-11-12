import numpy as np
import pypulseq as pp
import pytest

import pgecourse

GE_RASTERS = dict(grad_raster_time=4e-6, block_duration_raster=4e-6, rf_raster_time=2e-6, adc_raster_time=2e-6)


def tiny_gre(system, n=16, pe_in_loop=True, fixed_duration=True):
    seq = pp.Sequence(system)
    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=0.2, duration=2e-3, slice_thickness=5e-3, time_bw_product=4,
        delay=system.rf_dead_time, system=system, return_gz=True, use="excitation",
    )
    gx = pp.make_trapezoid("x", flat_area=n / 0.256, flat_time=2.56e-3, system=system)
    adc = pp.make_adc(n, duration=gx.flat_time, delay=gx.rise_time, system=system)
    areas = (np.arange(n) - n / 2) / 0.256
    base = pp.make_trapezoid("y", area=np.max(np.abs(areas)), duration=1e-3, system=system)
    for a in areas:
        if pe_in_loop:
            kw = {"duration": 1e-3} if fixed_duration else {}
            gy = pp.make_trapezoid("y", area=a, system=system, **kw)
        else:
            gy = pp.scale_grad(base, a / base.area)
        seq.add_block(rf, gz, pp.make_label(type="SET", label="TRID", value=1))
        seq.add_block(gy, pp.make_delay(1.2e-3))
        seq.add_block(gx, adc)
        seq.add_block(pp.make_delay(2e-3))
    return seq


@pytest.fixture(scope="module")
def ge():
    return pgecourse.GE()


@pytest.fixture
def ge_system():
    return pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=69, slew_unit="T/m/s", rf_dead_time=100e-6, **GE_RASTERS)


def test_pypulseq_default_rasters_are_rejected_by_pge2_check(ge):
    system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=69, slew_unit="T/m/s", rf_dead_time=100e-6)
    ge.from_seq(tiny_gre(system, pe_in_loop=False))
    with pytest.raises(pgecourse.PGE2Error, match="UPDATE_TIME"):
        ge.check()


def test_scaled_phase_encoding_is_played_exactly(ge, ge_system):
    report = ge.from_seq(tiny_gre(ge_system, pe_in_loop=False))
    assert [s.layout for s in report.segments] == ["ABCd"]
    ge.check()
    assert ge.validate()
    w = ge.instance_waveforms(4 * 3 + 1)
    for key in ("seq", "played"):
        assert w[key]["gy"][0].size > 0


def test_minimum_time_phase_encoding_created_in_loop_fails_validate(ge, ge_system):
    ge.from_seq(tiny_gre(ge_system, pe_in_loop=True, fixed_duration=False))
    ge.check()
    assert not ge.validate()


def test_sequence_without_trid_is_refused_before_pulseg(ge, ge_system):
    seq = pp.Sequence(ge_system)
    seq.add_block(pp.make_delay(1e-3))
    with pytest.raises(pgecourse.PGE2Error, match="no TRID"):
        ge.from_seq(seq)
