"""Build the course site: JupyterLite with every exercise notebook, runnable in the browser.

Everything the notebooks need is served by the site itself (no CDN, no PyPI at
run time): Pyodide (core plus the packages the kernel and the notebooks load),
and the wheels of pgecourse, pge2py (which bundles GNU Octave compiled to
WebAssembly and the pulseg and pge2 toolboxes), pypulseq and comm.

Usage:
    pip install -r lite/requirements.txt
    python lite/build_site.py [--pge2py WHEEL] [--out lite/_output]

Without --pge2py, the pge2py wheel is downloaded from PyPI.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

#: Must match the Pyodide that jupyterlite-pyodide-kernel (lite/requirements.txt) uses.
PYODIDE_VERSION = "314.0.6"
PYODIDE_CORE = f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}/pyodide-core-{PYODIDE_VERSION}.tar.bz2"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"

#: Pyodide packages to serve: those the kernel loads at start-up, and those the
#: notebooks import. Their dependencies are added from pyodide-lock.json.
PYODIDE_SEEDS = [
    "micropip", "packaging", "ipython", "jedi", "pygments",
    "numpy", "scipy", "matplotlib", "coverage",
]

#: Wheels served from the site's own package index (installed with %pip).
WHEELS = ["pypulseq==1.5.0.post1", "comm"]


def run(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pulseq-on-ge-course-site-build"})
    return urllib.request.urlopen(req).read()


def add_pyodide(out: Path) -> None:
    """Pyodide core and the needed packages, in out/pyodide."""
    dest = out / "pyodide"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(fetch(PYODIDE_CORE)), mode="r:bz2") as tar:
        for m in tar.getmembers():
            if m.isfile():
                name = m.name.split("/", 1)[1]
                (dest / name).parent.mkdir(parents=True, exist_ok=True)
                (dest / name).write_bytes(tar.extractfile(m).read())
    lock = json.loads((dest / "pyodide-lock.json").read_text())
    norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()  # noqa: E731
    pkgs = {norm(k): v for k, v in lock["packages"].items()}
    need, todo = set(), [norm(s) for s in PYODIDE_SEEDS]
    while todo:
        name = todo.pop()
        if name in need:
            continue
        if name not in pkgs:
            sys.exit(f"{name} is not a Pyodide {PYODIDE_VERSION} package")
        need.add(name)
        todo += [norm(d) for d in pkgs[name].get("depends", [])]
    total = 0
    for name in sorted(need):
        info = pkgs[name]
        data = fetch(PYODIDE_CDN + info["file_name"])
        if hashlib.sha256(data).hexdigest() != info["sha256"]:
            sys.exit(f"sha256 mismatch for {info['file_name']}")
        (dest / info["file_name"]).write_bytes(data)
        total += len(data)
    print(f"pyodide {PYODIDE_VERSION}: core + {len(need)} packages ({total / 1e6:.0f} MB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pge2py", type=Path, help="pge2py wheel (default: download from PyPI)")
    ap.add_argument("--out", type=Path, default=HERE / "_output")
    args = ap.parse_args()

    work = HERE / "_build"
    shutil.rmtree(work, ignore_errors=True)
    (work / "files").mkdir(parents=True)
    (work / "pypi").mkdir()

    # The notebooks name the "python3" kernel (Colab, desktop); in JupyterLite
    # the Pyodide kernel is "python".
    for nb in sorted((ROOT / "exercises").glob("[0-9]*.ipynb")):
        data = json.loads(nb.read_text())
        data["metadata"]["kernelspec"] = {"name": "python", "display_name": "Python (Pyodide)", "language": "python"}
        (work / "files" / nb.name).write_text(json.dumps(data, indent=1, ensure_ascii=False))

    pypi = work / "pypi"
    run(sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(pypi), str(ROOT))
    if args.pge2py:
        shutil.copy(args.pge2py, pypi)
    else:
        run(sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", str(pypi), "pge2py")
    run(sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", str(pypi), *WHEELS)

    shutil.copy(HERE / "jupyter-lite.json", work / "jupyter-lite.json")
    shutil.rmtree(args.out, ignore_errors=True)
    run(sys.executable, "-m", "jupyter", "lite", "build", "--output-dir", str(args.out.resolve()), cwd=work)
    add_pyodide(args.out)
    (args.out / ".nojekyll").write_text("")
    size = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"site in {args.out} ({size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
