# %% [markdown]
# Run the next cell once per session. On Colab it installs the course package
# and GNU Octave (about 2 minutes); on your own computer, follow the README
# instead and skip it.

# %% tags=["colab-only"]
# !pip -q install git+https://github.com/GEHC-External/pulseq-ge-course && python -m pgecourse.colab

# %%
import numpy as np
import pypulseq as pp

import pgecourse

ge = pgecourse.GE()  # downloads the Pulseq, pulseg and pge2 toolboxes on first use
