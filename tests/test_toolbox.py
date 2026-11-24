import pypulseq as pp
import pytest

import pge2py as pge2
from pge2py import pulseg
import pgecourse
from pgecourse.sequences import GE_SYSTEM, gre2d


SYS_GE = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")


@pytest.fixture(scope="module")
def ge():
    """Starts Octave once for the module (the first call starts it)."""
    return None


def test_reference_gre2d_has_three_one_tr_segments_from_five_base_blocks(ge):
    report = pulseg.fromSeq(gre2d())
    assert [(s.trid, s.n_instances, s.layout) for s in report.segments] == [
        (1, 20, "ABCDd"),
        (2, 10, "ABEDd"),
        (3, 128, "ABEDd"),
    ]
    assert report.n_base_blocks == 5
    assert not report.warnings


def test_reference_gre2d_passes_pge2_check_and_validate(ge, tmp_path):
    psq = pulseg.fromSeq(gre2d())
    pge2.check(psq, SYS_GE)
    assert pge2.validate(psq, SYS_GE)
    params = pge2.check(psq, SYS_GE)
    assert pge2.serialize(psq, tmp_path / "gre2d.pge", params=params).stat().st_size > 0


def test_pypulseq_default_rasters_are_rejected_by_pge2_check(ge):
    system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=69, slew_unit="T/m/s", rf_dead_time=100e-6)
    psq = pulseg.fromSeq(gre2d(system))
    with pytest.raises(pge2.PGE2Error, match="RF_UPDATE_TIME"):
        pge2.check(psq, SYS_GE)


def test_sequence_without_trid_is_refused_before_pulseg(ge):
    seq = pp.Sequence(GE_SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    with pytest.raises(pge2.PGE2Error, match="no TRID"):
        psq = pulseg.fromSeq(seq)


def test_segment_instances_with_different_block_counts_are_refused(ge):
    from pgecourse.sequences.multislice import multislice_gre

    seq = multislice_gre(lambda kind, s: 1 if kind == "slice" else None, n=4)
    with pytest.raises(pge2.PGE2Error, match="different numbers of blocks"):
        psq = pulseg.fromSeq(seq)


def test_mprage_placements_give_expected_segment_lengths(ge):
    from pgecourse.sequences.mprage import mprage

    lengths = {}
    for name in ("per_shot", "three"):
        report = pulseg.fromSeq(mprage(name, matrix=(32, 16, 4)))
        lengths[name] = [len(s.layout) for s in report.segments]
    assert lengths == {"per_shot": [68], "three": [3, 4, 1]}
    with pytest.raises(pge2.PGE2Error, match="different numbers of blocks"):
        psq = pulseg.fromSeq(mprage("two", matrix=(32, 16, 4)))


def test_played_timing_adds_the_segment_gap_per_echo_segment():
    from pgecourse import played_block_starts
    from pgecourse.sequences.fse import fse
    from pgecourse import SEGMENT_DEAD_TIME, SEGMENT_RINGDOWN_TIME

    gap = SEGMENT_DEAD_TIME + SEGMENT_RINGDOWN_TIME
    for placement, extra in (("per_echo", gap), ("train", 0.0)):
        seq, esp = fse(placement, ny=16)
        rf = [i for i, n in enumerate(seq.block_events) if seq.get_block(n).rf is not None]
        t = played_block_starts(seq)
        assert abs((t[rf[2]] - t[rf[1]]) - (esp + extra)) < 1e-9


def test_packed_epi_has_shorter_echo_spacing_and_validates(ge):
    from pgecourse.sequences.epi import epi

    seq, esp_packed = epi("train", packed=True, repetitions=1)
    _, esp_separate = epi("train", packed=False, repetitions=1)
    assert esp_packed < esp_separate
    psq = pulseg.fromSeq(seq)
    pge2.check(psq, SYS_GE)
    assert pge2.validate(psq, SYS_GE)
