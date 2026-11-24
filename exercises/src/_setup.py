# %% [markdown]
# On Colab, run the next cell once per session: it installs the course
# packages and GNU Octave (about 2 minutes). On your own computer, follow the
# README instead and skip it.

# %% tags=["install"]
%pip install -q "pgecourse[octave] @ git+https://github.com/GEHC-External/pulseq-ge-course"
!python -m pgecourse.colab

# %%
import numpy as np
import pypulseq as pp

import pge2py as pge2
from pge2py import pulseg

# scanner description: psd_rf_wait, psd_grd_wait (s), b1_max (G),
# g_max (G/cm), slew_max (G/cm/ms), gradient coil (notebook 00)
sys_ge = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")
