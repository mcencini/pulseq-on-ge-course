# Pulseq on GE (pge2) course

Hands-on material for writing Pulseq sequences that run well on GE scanners
with the pge2 interpreter.

## Part 1: writing a GE-friendly Pulseq sequence

Each notebook starts from the same 2D gradient echo (gre2d), breaks one
pge2 design rule, shows what the checks report, and asks you to fix it.

| notebook | topic |
|---|---|
| [00_gre2d_reference](exercises/00_gre2d_reference.ipynb) | the GE-friendly gre2d and the check chain: `pulseg.fromSeq`, `pge2.check`, `pge2.validate`, `pge2.serialize` |
| [01_raster_time](exercises/01_raster_time.ipynb) | risk #1: pypulseq's default rasters are not GE's |
| [02_events_in_loop](exercises/02_events_in_loop.ipynb) | risk #2: creating gradients inside the scan loop |
| [03a_trid_gre](exercises/03a_trid_gre.ipynb) | risk #3: where TRID labels go (segment consistency and segment length) |
| [03b_trid_mprage](exercises/03b_trid_mprage.ipynb) | risk #3 in an MPRAGE: one segment per shot vs one per kind of TR |
| [03c_trid_multislice](exercises/03c_trid_multislice.ipynb) | risk #3 in a multislice sequence: a pure delay segment to fill the TR |
| [04_fse_timing](exercises/04_fse_timing.ipynb) | timing: an FSE echo train in one segment, packed gradients |
| [05_epi_timing](exercises/05_epi_timing.ipynb) | timing: an EPI train in one segment, blips in the readout ramps |

The rules themselves are in the
[pge2 sequence design rules](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/docs/pge2-sequence-design-rules.md).

## Running the notebooks

The sequences are written in Python with [pypulseq](https://github.com/imr-framework/pypulseq).
They are checked with the same MATLAB toolboxes used before a scan,
[pulseg](https://github.com/HarmonizedMRI/pulseg) and [pge2](https://github.com/HarmonizedMRI/pge2),
running in GNU Octave and called from Python through oct2py. The `pgecourse`
helper package downloads the Pulseq, pulseg and pge2 MATLAB toolboxes at
pinned commits on first use.

**Google Colab** (nothing to install): open a notebook in Colab and run its
first code cell, the one-line setup

```
!pip -q install git+https://github.com/GEHC-External/pulseq-ge-course && python -m pgecourse.colab
```

which installs this package and GNU Octave (about 2 minutes).

**Your own computer**: install [GNU Octave](https://octave.org/download) and
git, then, in this repository,

```bash
pip install -e . jupyterlab
jupyter lab
```

and skip the setup cell.

## For course authors

Notebooks are generated from the percent-format scripts in `exercises/src/`,
which diff cleanly. Edit the script, then rebuild and test:

```bash
pip install -e .[dev]
python exercises/build.py
pytest -q
```

`exercises/src/_setup.py` holds the setup cells shared by every notebook;
the Colab install cell is tagged `colab-only`, and the tests skip it.
Solution cells carry Colab's `cellView: form`, so Colab shows them collapsed.
"Your turn" cells are tagged `raises-exception`, so a notebook still runs top
to bottom before the participant fills them in.
