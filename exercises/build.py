"""Build the exercise notebooks from the percent-format sources in src/.

Usage: python exercises/build.py
"""

from pathlib import Path

import jupytext

HERE = Path(__file__).parent
SRC = HERE / "src"
SETUP = (SRC / "_setup.py").read_text()

for src in sorted(SRC.glob("[0-9]*.py")):
    text = src.read_text().replace("# %%\n#INCLUDE _setup.py\n", SETUP)
    nb = jupytext.reads(text, fmt="py:percent")
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["colab"] = {"provenance": []}
    # jupytext builds this filter from a set, so its order changes between
    # runs; sort it so that rebuilding an unchanged source is a no-op.
    filt = nb.metadata.get("jupytext", {}).get("cell_metadata_filter")
    if filt:
        keys = filt.split(",")
        nb.metadata["jupytext"]["cell_metadata_filter"] = ",".join(
            sorted(k for k in keys if not k.startswith("-")) + [k for k in keys if k.startswith("-")]
        )
    for i, cell in enumerate(nb.cells):
        cell.id = f"cell-{i:02d}"
    jupytext.write(nb, HERE / f"{src.stem}.ipynb", fmt="ipynb")
    print("wrote", src.stem + ".ipynb")
