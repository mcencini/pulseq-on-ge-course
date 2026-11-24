# %% [markdown]
# Run the next cell once per session. In the browser (JupyterLite) it installs
# the course packages from the course site, in a few seconds; on Colab it also
# installs GNU Octave (about 2 minutes). On your own computer, follow the README
# instead and skip it.

# %% tags=["install"]
import sys

if sys.platform == "emscripten":  # JupyterLite: everything runs in this browser tab
    %pip install pgecourse
else:  # Colab
    %pip install -q "pgecourse[octave] @ git+https://github.com/GEHC-External/pulseq-ge-course"
    !python -m pgecourse.colab

# %%
import numpy as np
import pypulseq as pp

import pge2py

ge = pge2py.GE()
