# Before/after examples

One folder per pge2 design rule, from the course notebook named in its
row. `before.seq` breaks the rule, `after.seq` follows it. A `.pge` is
written for each file that passes `pge2.check`, with
`pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")` and `pislquant=10`;
a file stopped earlier has none, and its row says where it stopped.

Written by `python -m pgecourse.examples <folder>`; the pge2 chain
column is what that run printed. The timing cases also give the
timing in the file and as pge2 plays it, with the segment dead and
ringdown times of `pgecourse.timing`.

## 01_raster_time

Rule: Every time in the file is a multiple of the GE raster: 4 us gradients and blocks, 2 us RF and ADC.

Notebook: `exercises/01_raster_time.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | pypulseq's default rasters: the sinc pulse is sampled every 1 us. | 3 segment(s), 5 base blocks; refused by pge2.check: Error in parent block 1: RF sample spacings not on RF_UPDATE_TIME (2e-06 s) boundary |
| After | `after.seq` | GE rasters in pp.Opts. | 3 segment(s), 5 base blocks; check and validate passed, .pge written |

## 02_events_in_loop

Rule: Events are made once, before the loop, and scaled in it.

Notebook: `exercises/02_events_in_loop.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | Each line makes its own shortest phase-encoding trapezoid; the segment is defined by its first instance, so every other line is played with line 0's ramps, rescaled: wrong k-space lines, no error at download or scan. | 3 segment(s), 7 base blocks; check passed, .pge written; pge2.validate FAILED: pge2.validate(): Checking scan loop: gy waveform mismatch (segment at row 186: max diff 0.258 G/cm at t = 7.456 ms) |
| After | `after.seq` | One phase-encoding trapezoid for the largest area, scaled with pp.scale_grad. | 3 segment(s), 5 base blocks; check and validate passed, .pge written |

## 03a_trid_dummy

Rule: Every instance of a segment has the same blocks and the same kinds of events.

Notebook: `exercises/03a_trid_gre.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | Dummy TRs (no ADC) share the imaging TRID: the segment, defined by a dummy TR, has no ADC for the imaging TRs to switch on. | refused by pulseg.fromSeq: (virtual segment 1) Expected ADC event not found in base block 3 |
| After | `after.seq` | One TRID per kind of TR: dummy, receive gain, acquire. | 3 segment(s), 5 base blocks; check and validate passed, .pge written |

## 03a_trid_whole_scan

Rule: Segments are short, about one TR: a segment is loaded whole into the sequencer's waveform memory.

Notebook: `exercises/03a_trid_gre.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | One TRID on the first block: the whole scan is one segment of 790 blocks, played once. The checks pass; whether it loads depends on the scanner's memory and on the scan's length. | 1 segment(s), 5 base blocks; check and validate passed, .pge written |
| After | `after.seq` | One TRID per kind of TR. | 3 segment(s), 5 base blocks; check and validate passed, .pge written |

## 03b_trid_mprage

Rule: The same blocks in every instance; a delay that ends a shot has a TRID of its own.

Notebook: `exercises/03b_trid_mprage.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | Preparation and readout TR labelled, recovery delay not: it joins the last readout TR, which then has one block more than the others. | refused by pulseg.fromSeq: segment instances of TRID 2 have different numbers of blocks: 4 in the first instance (block 4), 5 in the instance starting at block 256. Every instance of a segment must have the same blocks; give the extra blocks their own TRID. |
| After | `after.seq` | Three TRIDs: inversion and TI, readout TR, recovery delay. | 3 segment(s), 6 base blocks; check and validate passed, .pge written |

## 03c_trid_multislice

Rule: The same blocks in every instance; a fill delay has a TRID of its own.

Notebook: `exercises/03c_trid_multislice.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | A TRID on every slice, none on the fill delay: it joins the last slice's instance, which then has one block more than the others. | refused by pulseg.fromSeq: segment instances of TRID 1 have different numbers of blocks: 4 in the first instance (block 1), 5 in the instance starting at block 29. Every instance of a segment must have the same blocks; give the extra blocks their own TRID. |
| After | `after.seq` | One segment per slice and one pure-delay segment for the fill. | 2 segment(s), 4 base blocks; check and validate passed, .pge written |

## 04_fse_timing

Rule: Each segment instance ends with a gap the file does not contain; keep an echo train in one segment.

Notebook: `exercises/04_fse_timing.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | One TRID per echo: a gap after every echo spacing, so the echo spacing played is not twice the 90-180 time and the CPMG condition is broken. | 3 segment(s), 5 base blocks; check and validate passed, .pge written (file: 90-180 3.040 ms, echo spacing 7.512 ms; played: 90-180 3.157 ms, echo spacing 7.629 ms) |
| After | `after.seq` | The echo train in one segment, the z gradient joined across block boundaries. | 2 segment(s), 7 base blocks; check and validate passed, .pge written (file: 90-180 3.004 ms, echo spacing 7.264 ms; played: 90-180 3.004 ms, echo spacing 7.264 ms) |

## 05_epi_timing

Rule: Each segment instance ends with a gap the file does not contain; keep an EPI train in one segment.

Notebook: `exercises/05_epi_timing.ipynb`

| | File | What it does | pge2 chain |
|---|---|---|---|
| Before | `before.seq` | One TRID per readout line: a gap after every line, adding up over the train. | 4 segment(s), 6 base blocks; check and validate passed, .pge written (file: echo spacing 1048 us; played: echo spacing 1165 us) |
| After | `after.seq` | The train in one segment, the blips in the readout ramps. | 2 segment(s), 7 base blocks; check and validate passed, .pge written (file: echo spacing 968 us; played: echo spacing 968 us) |
