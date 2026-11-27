"""Before/after sequence pairs for the course's design rules, written as files.

Each case pairs a sequence that breaks one pge2 design rule with the same
sequence written correctly. ``python -m pgecourse.examples OUTDIR`` writes,
for every case, ``before.seq`` and ``after.seq``, the ``.pge`` file of each
that passes ``pge2.check``, and a README that records where in the pge2 chain
(``pulseg.fromSeq``, ``pge2.check``, ``pge2.validate``) each one stopped.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pypulseq as pp

from .sequences import GE_SYSTEM, gre2d
from .timing import played_block_starts
from .sequences.epi import epi
from .sequences.fse import fse
from .sequences.mprage import mprage
from .sequences.multislice import multislice_gre

#: pypulseq's default rasters (10 us gradient and block, 1 us RF, 0.1 us ADC)
#: with GE_SYSTEM's gradient limits.
DEFAULT_RASTERS = pp.Opts(
    max_grad=GE_SYSTEM.max_grad,
    grad_unit="Hz/m",
    max_slew=GE_SYSTEM.max_slew,
    slew_unit="Hz/m/s",
    rf_dead_time=0,
    rf_ringdown_time=0,
    adc_dead_time=0,
    B0=3.0,
)


def _gre2d(trid: Callable[[int, str], int | None], pe_in_loop: bool = False, system=GE_SYSTEM):
    """The gre2d of notebook 00 with the TRID of each TR chosen by ``trid(iy, kind)``.

    With ``pe_in_loop``, every line makes its own shortest phase-encoding
    trapezoid, as in notebook 02's naive loop.
    """
    fov, n, thickness, dwell = 240e-3, 128, 5e-3, 20e-6
    n_dummy, pislquant = 20, 10
    rf, gz, _ = pp.make_sinc_pulse(
        flip_angle=np.deg2rad(6),
        duration=3e-3,
        slice_thickness=thickness,
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
    gx_spoil = pp.make_trapezoid("x", area=2 * n * delta_k, system=system)
    gz_spoil = pp.make_trapezoid("z", area=4 / thickness, system=system)

    seq = pp.Sequence(system)
    rf_phase = rf_increment = 0.0
    for iy in range(-n_dummy - pislquant, n):
        kind = "dummy" if iy < -pislquant else "receive_gain" if iy < 0 else "acquire"
        rf.phase_offset = adc.phase_offset = np.deg2rad(rf_phase)
        rf_increment = (rf_increment + 117) % 360
        rf_phase = (rf_phase + rf_increment) % 360
        area = pe_areas[iy] if kind == "acquire" else 0.0
        if pe_in_loop:
            g_pre = pp.make_trapezoid("y", area=area, system=system)
            g_rew = pp.make_trapezoid("y", area=-area, system=system)
        else:
            g_pre = pp.scale_grad(gy_pre, area / gy_pre.area)
            g_rew = pp.scale_grad(gy_pre, -area / gy_pre.area)
        label = trid(iy + n_dummy + pislquant, kind)
        seq.add_block(rf, gz, *([pp.make_label(type="SET", label="TRID", value=label)] if label else []))
        seq.add_block(gx_pre, g_pre, gz_reph)
        seq.add_block(gx) if kind == "dummy" else seq.add_block(gx, adc)
        seq.add_block(gx_spoil, g_rew, gz_spoil)
        seq.add_block(pp.make_delay(5e-3))
    return seq


def _starts(seq):
    """Block start times in the file and as pge2 plays them, in s."""
    in_file = np.cumsum([0] + [seq.block_durations[k] for k in seq.block_events])[:-1]
    return in_file, played_block_starts(seq)


def _cpmg_timing(seq) -> str:
    r = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).rf is not None]
    in_file, played = _starts(seq)
    return "; ".join(
        f"{name}: 90-180 {1e3 * (t[r[1]] - t[r[0]]):.3f} ms, echo spacing {1e3 * (t[r[2]] - t[r[1]]):.3f} ms"
        for name, t in (("file", in_file), ("played", played))
    )


def _epi_timing(seq) -> str:
    a = [i for i, k in enumerate(seq.block_events) if seq.get_block(k).adc is not None]
    in_file, played = _starts(seq)
    return "; ".join(
        f"{name}: echo spacing {1e6 * (t[a[1]] - t[a[0]]):.0f} us" for name, t in (("file", in_file), ("played", played))
    )


def _per_kind(tr: int, kind: str) -> int:
    return {"dummy": 1, "receive_gain": 2, "acquire": 3}[kind]


@dataclass(frozen=True)
class Case:
    """One design rule: a sequence that breaks it, the same sequence written correctly, and what to look for."""

    name: str
    notebook: str
    rule: str
    before: Callable[[], pp.Sequence]
    after: Callable[[], pp.Sequence]
    before_shows: str
    after_fix: str
    timing: Callable[[pp.Sequence], str] | None = None


CASES = (
    Case(
        "01_raster_time",
        "01_raster_time",
        "Every time in the file is a multiple of the GE raster: 4 us gradients and blocks, 2 us RF and ADC.",
        lambda: _gre2d(_per_kind, system=DEFAULT_RASTERS),
        lambda: gre2d(),
        "pypulseq's default rasters: the sinc pulse is sampled every 1 us.",
        "GE rasters in pp.Opts.",
    ),
    Case(
        "02_events_in_loop",
        "02_events_in_loop",
        "Events are made once, before the loop, and scaled in it.",
        lambda: _gre2d(_per_kind, pe_in_loop=True),
        lambda: gre2d(),
        "Each line makes its own shortest phase-encoding trapezoid; the segment is defined by its "
        "first instance, so every other line is played with line 0's ramps, rescaled: wrong k-space "
        "lines, no error at download or scan.",
        "One phase-encoding trapezoid for the largest area, scaled with pp.scale_grad.",
    ),
    Case(
        "03a_trid_dummy",
        "03a_trid_gre",
        "Every instance of a segment has the same blocks and the same kinds of events.",
        lambda: _gre2d(lambda tr, kind: 1),
        lambda: gre2d(),
        "Dummy TRs (no ADC) share the imaging TRID: the segment, defined by a dummy TR, has no ADC "
        "for the imaging TRs to switch on.",
        "One TRID per kind of TR: dummy, receive gain, acquire.",
    ),
    Case(
        "03a_trid_whole_scan",
        "03a_trid_gre",
        "Segments are short, about one TR: a segment is loaded whole into the sequencer's waveform memory.",
        lambda: _gre2d(lambda tr, kind: 1 if tr == 0 else None),
        lambda: gre2d(),
        "One TRID on the first block: the whole scan is one segment of 790 blocks, played once. The "
        "checks pass; whether it loads depends on the scanner's memory and on the scan's length.",
        "One TRID per kind of TR.",
    ),
    Case(
        "03b_trid_mprage",
        "03b_trid_mprage",
        "The same blocks in every instance; a delay that ends a shot has a TRID of its own.",
        lambda: mprage("two"),
        lambda: mprage("three"),
        "Preparation and readout TR labelled, recovery delay not: it joins the last readout TR, "
        "which then has one block more than the others.",
        "Three TRIDs: inversion and TI, readout TR, recovery delay.",
    ),
    Case(
        "03c_trid_multislice",
        "03c_trid_multislice",
        "The same blocks in every instance; a fill delay has a TRID of its own.",
        lambda: multislice_gre("fill_unlabelled"),
        lambda: multislice_gre("slice_and_fill"),
        "A TRID on every slice, none on the fill delay: it joins the last slice's instance, which then "
        "has one block more than the others.",
        "One segment per slice and one pure-delay segment for the fill.",
    ),
    Case(
        "04_fse_timing",
        "04_fse_timing",
        "Each segment instance ends with a gap the file does not contain; keep an echo train in one segment.",
        lambda: fse("per_echo")[0],
        lambda: fse("train", packed=True)[0],
        "One TRID per echo: a gap after every echo spacing, so the echo spacing played is not twice "
        "the 90-180 time and the CPMG condition is broken.",
        "The echo train in one segment, the z gradient joined across block boundaries.",
        _cpmg_timing,
    ),
    Case(
        "05_epi_timing",
        "05_epi_timing",
        "Each segment instance ends with a gap the file does not contain; keep an EPI train in one segment.",
        lambda: epi("per_line")[0],
        lambda: epi("train", packed=True)[0],
        "One TRID per readout line: a gap after every line, adding up over the train.",
        "The train in one segment, the blips in the readout ramps.",
        _epi_timing,
    ),
)


def run_chain(seq: pp.Sequence, pge_path: Path, sys_ge, pislquant: int = 10) -> str:
    """Run pulseg.fromSeq, pge2.check and pge2.validate; write the .pge if check passes.

    Returns one line stating where the chain stopped, or that it passed.
    """
    import pge2py as pge2
    from pge2py import pulseg

    try:
        psq = pulseg.fromSeq(seq)
    except pge2.PGE2Error as err:
        return f"refused by pulseg.fromSeq: {_first_line(err)}"
    segments = f"{len(psq.segments)} segment(s), {psq.n_base_blocks} base blocks"
    try:
        params = pge2.check(psq, sys_ge)
    except pge2.PGE2Error as err:
        return f"{segments}; refused by pge2.check: {_first_line(err)}"
    pge2.serialize(psq, pge_path, pislquant=pislquant, params=params)
    if not pge2.validate(psq, sys_ge):
        first = pge2.last_messages[0] if getattr(pge2, "last_messages", None) else ""
        return f"{segments}; check passed, .pge written; pge2.validate FAILED: {first}"
    return f"{segments}; check and validate passed, .pge written"


def _first_line(err: Exception) -> str:
    text = str(err).strip().splitlines()
    return text[0] if text else type(err).__name__


def write(outdir: Path, cases=CASES) -> list[tuple[Case, str, str]]:
    """Write every case's files under ``outdir/<case>/`` and ``outdir/README.md``; return the outcomes."""
    import pge2py as pge2

    sys_ge = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        folder = outdir / case.name
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
        outcome = {}
        for side, make in (("before", case.before), ("after", case.after)):
            seq = make()
            seq.write(str(folder / f"{side}.seq"))
            outcome[side] = run_chain(seq, folder / f"{side}.pge", sys_ge)
            if case.timing:
                outcome[side] += f" ({case.timing(seq)})"
            print(f"{case.name} {side}: {outcome[side]}", file=sys.stderr)
        results.append((case, outcome["before"], outcome["after"]))
    (outdir / "README.md").write_text(_readme(results))
    return results


def _readme(results) -> str:
    lines = [
        "# Before/after examples",
        "",
        "One folder per pge2 design rule, from the course notebook named in its",
        "row. `before.seq` breaks the rule, `after.seq` follows it. A `.pge` is",
        "written for each file that passes `pge2.check`, with",
        '`pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")` and `pislquant=10`;',
        "a file stopped earlier has none, and its row says where it stopped.",
        "",
        "Written by `python -m pgecourse.examples <folder>`; the pge2 chain",
        "column is what that run printed. The timing cases also give the",
        "timing in the file and as pge2 plays it, with the segment dead and",
        "ringdown times of `pgecourse.timing`.",
        "",
    ]
    for case, before, after in results:
        lines += [
            f"## {case.name}",
            "",
            f"Rule: {case.rule}",
            "",
            f"Notebook: `exercises/{case.notebook}.ipynb`",
            "",
            "| | File | What it does | pge2 chain |",
            "|---|---|---|---|",
            f"| Before | `before.seq` | {case.before_shows} | {before} |",
            f"| After | `after.seq` | {case.after_fix} | {after} |",
            "",
        ]
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("outdir", type=Path)
    write(parser.parse_args(argv).outdir)


if __name__ == "__main__":
    main()
