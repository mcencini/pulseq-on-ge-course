# %% [markdown]
# **On Colab**, run the next cell once per session. It connects your Google
# Drive, finds the course folder there and installs the course package and
# GNU Octave (about 2 minutes). **On your own computer**, follow the README
# instead and skip it.

# %% tags=["colab-only"]
import glob
import subprocess
import sys

from google.colab import drive

drive.mount("/content/drive")
found = sorted(
    p
    for depth in range(4)
    for p in glob.glob("/content/drive/MyDrive/" + "*/" * depth + "pyproject.toml")
    if "name = \"pgecourse\"" in open(p).read()
)
if not found:
    raise FileNotFoundError("Course folder not found in your Google Drive: upload the repository folder to My Drive.")
course = found[0].rsplit("/", 1)[0]
print("Course folder:", course)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", course], check=True)
subprocess.run([sys.executable, "-m", "pgecourse.colab"], check=True)

# %%
import numpy as np
import pypulseq as pp

import pgecourse

ge = pgecourse.GE()  # downloads the Pulseq, pulseg and pge2 toolboxes on first use
