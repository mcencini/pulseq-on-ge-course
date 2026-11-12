from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOKS = sorted((Path(__file__).parents[1] / "exercises").glob("[0-9]*.ipynb"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_notebook_runs_top_to_bottom(path, tmp_path):
    nb = nbformat.read(path, as_version=4)
    nb.cells = [c for c in nb.cells if "colab-only" not in c.metadata.get("tags", [])]
    NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(tmp_path)}}).execute()


def test_notebooks_are_built_from_their_sources():
    import subprocess
    import sys

    root = Path(__file__).parents[1]
    before = {p: p.read_text() for p in NOTEBOOKS}
    subprocess.run([sys.executable, str(root / "exercises" / "build.py")], check=True, capture_output=True)
    for p, text in before.items():
        assert p.read_text() == text, f"{p.name} differs from exercises/src; run exercises/build.py"
