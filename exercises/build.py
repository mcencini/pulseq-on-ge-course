"""Build the exercise notebooks from the percent-format sources in src/.

Usage: python exercises/build.py
"""

from pathlib import Path

import jupytext

#: Where the notebooks are published; used for the "Open in Colab" badges and
#: for the package install line of the Colab setup cell.
COURSE_REPO = "GEHC-External/pulseq-ge-course"
COURSE_BRANCH = "main"

BADGE = (
    "[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]"
    "(https://colab.research.google.com/github/{repo}/blob/{branch}/exercises/{name}.ipynb)"
)

HERE = Path(__file__).parent
SRC = HERE / "src"
SETUP = (SRC / "_setup.py").read_text().replace(
    "{PACKAGE_URL}", f"git+https://github.com/{COURSE_REPO}@{COURSE_BRANCH}"
)

for src in sorted(SRC.glob("[0-9]*.py")):
    text = src.read_text().replace("# %%\n#INCLUDE _setup.py\n", SETUP)
    nb = jupytext.reads(text, fmt="py:percent")
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["colab"] = {"provenance": []}
    nb.metadata.pop("jupytext", None)
    badge = BADGE.format(repo=COURSE_REPO, branch=COURSE_BRANCH, name=src.stem)
    nb.cells[0].source = badge + "\n\n" + nb.cells[0].source
    for i, cell in enumerate(nb.cells):
        cell.id = f"cell-{i:02d}"
    jupytext.write(nb, HERE / f"{src.stem}.ipynb", fmt="ipynb")
    print("wrote", src.stem + ".ipynb")
