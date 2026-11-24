import pypulseq as pp
import pytest

import pgecourse
from pgecourse.sequences import GE_SYSTEM, gre2d


@pytest.fixture(scope="module")
def ge():
    return pgecourse.GE()


def test_reference_gre2d_has_three_one_tr_segments_from_five_base_blocks(ge):
    report = ge.from_seq(gre2d())
    assert [(s.trid, s.n_instances, s.layout) for s in report.segments] == [
        (1, 20, "ABCDd"),
        (2, 10, "ABEDd"),
        (3, 128, "ABEDd"),
    ]
    assert report.n_base_blocks == 5
    assert not report.warnings


def test_reference_gre2d_passes_pge2_check_and_validate(ge, tmp_path):
    ge.from_seq(gre2d())
    ge.check()
    assert ge.validate()
    assert ge.serialize(tmp_path / "gre2d.pge").stat().st_size > 0


def test_pypulseq_default_rasters_are_rejected_by_pge2_check(ge):
    system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=69, slew_unit="T/m/s", rf_dead_time=100e-6)
    ge.from_seq(gre2d(system))
    with pytest.raises(pgecourse.PGE2Error, match="RF_UPDATE_TIME"):
        ge.check()


def test_sequence_without_trid_is_refused_before_pulseg(ge):
    seq = pp.Sequence(GE_SYSTEM)
    seq.add_block(pp.make_delay(1e-3))
    with pytest.raises(pgecourse.PGE2Error, match="no TRID"):
        ge.from_seq(seq)


def test_segment_instances_with_different_block_counts_are_refused(ge):
    from pgecourse.sequences.multislice import multislice_gre

    seq = multislice_gre(lambda kind, s: 1 if kind == "slice" else None, n=4)
    with pytest.raises(pgecourse.PGE2Error, match="different numbers of blocks"):
        ge.from_seq(seq)


def test_mprage_placements_give_expected_segment_lengths(ge):
    from pgecourse.sequences.mprage import mprage

    lengths = {}
    for name in ("per_shot", "two", "three"):
        report = ge.from_seq(mprage(name, matrix=(32, 16, 4)))
        lengths[name] = [len(s.layout) for s in report.segments]
    assert lengths == {"per_shot": [68], "two": [4, 4], "three": [1, 3, 4]}
