import re

import pytest

from pgecourse import examples

#: Where each case's "before" file stops in the pge2 chain, or what it shows.
BEFORE = {
    "01_raster_time": "refused by pge2.check",
    "02_events_in_loop": "pge2.validate FAILED",
    "03a_trid_dummy": "refused by pulseg.fromSeq",
    "03a_trid_whole_scan": "1 segment(s)",
    "03b_trid_mprage": "refused by pulseg.fromSeq",
    "03c_trid_multislice": "refused by pulseg.fromSeq",
    "04_fse_timing": "check and validate passed",
    "05_epi_timing": "check and validate passed",
}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    out = tmp_path_factory.mktemp("examples")
    return out, {case.name: (before, after) for case, before, after in examples.write(out)}


def test_every_case_has_its_expected_before_outcome():
    assert set(BEFORE) == {case.name for case in examples.CASES}


@pytest.mark.parametrize("name", sorted(BEFORE))
def test_before_file_fails_where_its_case_says(written, name):
    _, outcomes = written
    assert BEFORE[name] in outcomes[name][0]


@pytest.mark.parametrize("name", sorted(BEFORE))
def test_after_file_passes_check_and_validate_and_has_a_pge(written, name):
    out, outcomes = written
    assert "check and validate passed" in outcomes[name][1]
    assert (out / name / "after.pge").is_file()


@pytest.mark.parametrize("name", ["04_fse_timing", "05_epi_timing"])
def test_timing_case_plays_the_echo_spacing_of_its_file_only_after_the_fix(written, name):
    _, outcomes = written

    def spacings(outcome):
        return re.findall(r"echo spacing ([\d.]+)", outcome)

    file_before, played_before = spacings(outcomes[name][0])
    file_after, played_after = spacings(outcomes[name][1])
    assert file_before != played_before
    assert file_after == played_after
