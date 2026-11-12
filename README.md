# Pulseq on GE (pge2) course

Hands-on material for writing Pulseq sequences that run well on GE scanners
with the pge2 interpreter.

## Part 1: writing a GE-friendly Pulseq sequence

The notebooks start from the 2D gradient echo that ships with pypulseq
(`examples/scripts/write_gre.py`) and fix one pge2 issue at a time, on the
way to the gre2d of the pge2 examples
([`write2DGRE.m`](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/2DGRE/write2DGRE.m)).

| notebook | topic |
|---|---|
| [01_rasters](exercises/01_rasters.ipynb) | the pypulseq GRE through `pulseg.fromSeq`, `pge2.check` and `pge2.validate`; GE raster times |
| [02_events_in_loop](exercises/02_events_in_loop.ipynb) | a phase-encoding gradient created in every TR: what the scanner plays, and the `scale_grad` fix |

The rules themselves are in the
[pge2 sequence design rules](https://github.com/HarmonizedMRI/SequenceExamples-GE/blob/main/pge2/docs/pge2-sequence-design-rules.md).

## Running the notebooks

The sequences are written in Python with [pypulseq](https://github.com/imr-framework/pypulseq).
They are checked with the same MATLAB toolboxes used before a scan,
[pulseg](https://github.com/HarmonizedMRI/pulseg) and [pge2](https://github.com/HarmonizedMRI/pge2),
running in GNU Octave and called from Python through oct2py. The `pgecourse`
helper package downloads the Pulseq, pulseg and pge2 MATLAB toolboxes at
pinned commits on first use.

**Google Colab** (nothing to install on your computer):

1. Get the repository folder: clone it, or use Code → Download ZIP on GitHub
   and unzip it.
2. Upload the whole folder to your Google Drive (My Drive, or a folder up to
   three levels below it).
3. In Drive, open a notebook from `exercises/` with Open with → Google
   Colaboratory.
4. Run the first code cell. It connects your Drive, finds the course folder,
   and installs the course package and GNU Octave (about 2 minutes).

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
the Colab cell, which installs from the course folder in Google Drive, is
tagged `colab-only`, and the tests skip it.
Solution cells carry Colab's `cellView: form`, so Colab shows them collapsed.
"Your turn" cells are tagged `raises-exception`, so a notebook still runs top
to bottom before the participant fills them in.
