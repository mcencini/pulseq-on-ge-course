"""Run the pulseg and pge2 MATLAB toolboxes on a pypulseq sequence, through Octave.

The course checks every sequence with the same tools used before a scan:
``pulseg.fromSeq`` builds the segment representation, ``pge2.check`` checks it
against the GE hardware rules, and ``pge2.validate`` compares it with the
original ``.seq`` file. Those toolboxes are MATLAB code; here they run in GNU
Octave, driven from Python through oct2py.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Toolbox sources, pinned to the commits the course material was tested with.
TOOLBOXES = {
    "pulseq": ("https://github.com/pulseq/pulseq", "11e459d9b6b426aa6ea57a01153fb9afea332f6f"),
    "pulseg": ("https://github.com/HarmonizedMRI/pulseg", "ca2a278a4160f859f1009812dcda86b783a3f3a1"),
    "pge2": ("https://github.com/HarmonizedMRI/pge2", "9fa76e60e65a92325e51a0c98f0302e3a805d960"),
}

#: Default scanner description passed to ``pge2.opts``, taken from the pge2
#: 2DGRE demo: psd_rf_wait and psd_grd_wait in s, b1_max in G, g_max in G/cm,
#: slew_max in G/cm/ms, and the gradient coil name.
DEFAULT_SCANNER = {
    "psd_rf_wait": 100e-6,
    "psd_grd_wait": 100e-6,
    "b1_max": 0.25,
    "g_max": 5.0,
    "slew_max": 20.0,
    "coil": "xrm",
}

# Octave stand-ins for MATLAB functions the toolboxes call; each is put on the
# path only when the running Octave lacks the function.
_SHIMS = {
    "DataHash.m": """function h = DataHash(x, varargin)
% MD5 of the text serialisation of x (stand-in for the Java-based DataHash).
f = [tempname() '.txt'];
save('-text', f, 'x');
s = fileread(f); delete(f);
s = regexprep(s, '# Created by Octave[^\\n]*\\n', '');
h = hash('md5', s);
end
""",
    "rmse.m": """function e = rmse(a, b, varargin)
% Root-mean-square error (stand-in for the Statistics Toolbox function).
e = sqrt(mean(abs(a - b).^2, varargin{:}));
end
""",
    "MException.m": """function ME = MException(id, msg, varargin)
% Error description (stand-in where Octave has no MException constructor).
ME = struct('identifier', id, 'message', sprintf(msg, varargin{:}));
end
""",
    "throw.m": """function throw(ME)
% Raise the error described by ME (pairs with the MException stand-in).
error(ME.identifier, '%s', ME.message);
end
""",
}

_INPUTPARSER_OLD = "          this.Parameter(end+1)=this.Optional{i};"
_INPUTPARSER_NEW = """          o=this.Optional{i};
          if isfield(this.Parameter,'name') || isempty(fieldnames(this.Parameter))
            this.Parameter(end+1)=o;
          else
            this.Parameter.(o.name)=struct('def',o.def,'val',o.val);
          end"""

_PROGRESS = re.compile(r"\d+(\.\d+)?%\s*\[[ .*]*\]")


class PGE2Error(RuntimeError):
    """Raised when pulseg or pge2 rejects a sequence."""


@dataclass
class Segment:
    """One virtual segment found by ``pulseg.fromSeq``."""

    trid: int
    block_ids: list[int]
    n_instances: int

    @property
    def layout(self) -> str:
        """Blocks of the segment as letters: one letter per base block,
        ``d`` for a fixed pure delay and ``v`` for a variable pure delay."""
        out = []
        for b in self.block_ids:
            if b == 0:
                out.append("d")
            elif b == -1:
                out.append("v")
            else:
                out.append(_letter(b))
        return "".join(out)


@dataclass
class SegmentReport:
    """What ``pulseg.fromSeq`` made of a sequence."""

    segments: list[Segment]
    n_base_blocks: int
    n_blocks: int
    messages: list[str] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        """Warnings printed by ``pulseg.fromSeq``."""
        return [m for m in self.messages if m.lower().startswith("warning")]

    def __str__(self) -> str:
        lines = [
            f"{self.n_blocks} blocks -> {len(self.segments)} virtual segment(s), "
            f"{self.n_base_blocks} base block(s)",
            "",
            f"  {'TRID':>6}  {'instances':>9}  {'blocks':>6}  layout",
        ]
        for s in self.segments:
            layout = s.layout if len(s.layout) <= 60 else s.layout[:57] + "..."
            lines.append(f"  {s.trid:>6}  {s.n_instances:>9}  {len(s.block_ids):>6}  {layout}")
        if self.warnings:
            lines += ["", f"pulseg.fromSeq printed {len(self.warnings)} warning(s); the first one:"]
            lines.append("  " + self.warnings[0].replace("\n", "\n  "))
        return "\n".join(lines)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))


def _letter(i: int) -> str:
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _fetch(url: str, commit: str, dest: Path) -> None:
    if (dest / ".git").exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], dest)
    _run(["git", "fetch", "-q", "--depth", "1", url, commit], dest)
    _run(["git", "checkout", "-q", "FETCH_HEAD"], dest)


def prepare_toolboxes(cache: str | os.PathLike | None = None) -> list[Path]:
    """Download the pinned toolboxes and the Octave stand-ins.

    Parameters
    ----------
    cache : path, optional
        Where the toolboxes are kept. Defaults to ``$PGECOURSE_CACHE``, or
        ``~/.cache/pgecourse``.

    Returns
    -------
    list of Path
        Folders to put on the Octave path, in order.
    """
    root = Path(cache or os.environ.get("PGECOURSE_CACHE", Path.home() / ".cache" / "pgecourse"))
    for name, (url, commit) in TOOLBOXES.items():
        _fetch(url, commit, root / name)

    compat = root / "pulseq/matlab/+mr/+aux/@InputParserCompat/InputParserCompat.m"
    text = compat.read_bytes().decode()
    eol = "\r\n" if "\r\n" in text else "\n"
    if _INPUTPARSER_OLD in text:
        compat.write_bytes(text.replace(_INPUTPARSER_OLD, _INPUTPARSER_NEW.replace("\n", eol)).encode())

    overlay = root / "octave-overlay"
    overlay.mkdir(exist_ok=True)
    for private in (root / "pulseg/matlab/+pulseg/private", root / "pge2/matlab/+pge2/private"):
        for f in private.glob("*.m"):
            shutil.copy(f, overlay / f.name)
    vararg = (root / "pulseg/matlab/third_party/vararg_pair.m").read_text()
    (overlay / "vararg_pair.m").write_text(re.sub(r"(?m)^import ", "% import ", vararg))
    for name, body in _SHIMS.items():
        shim_dir = root / "octave-shims" / Path(name).stem
        shim_dir.mkdir(parents=True, exist_ok=True)
        (shim_dir / name).write_text(body)

    return [
        overlay,
        root / "pulseq/matlab",
        root / "pulseg/matlab",
        root / "pulseg/matlab/third_party",
        root / "pge2/matlab",
    ]


class GE:
    """pulseg and pge2, running in Octave, for one sequence at a time.

    Parameters
    ----------
    scanner : dict, optional
        Keyword arguments of ``pge2.opts``; see ``DEFAULT_SCANNER``.
    cache : path, optional
        Where the toolboxes are kept; see ``prepare_toolboxes``.
    """

    def __init__(self, scanner: dict | None = None, cache=None):
        if shutil.which("octave-cli") and "OCTAVE_EXECUTABLE" not in os.environ:
            os.environ["OCTAVE_EXECUTABLE"] = shutil.which("octave-cli")
        from oct2py import Oct2Py

        self.scanner = {**DEFAULT_SCANNER, **(scanner or {})}
        self._oc = Oct2Py()
        paths = prepare_toolboxes(cache)
        for p in reversed(paths):
            self._oc.addpath(str(p))
        shims = paths[0].parent / "octave-shims"
        for name in _SHIMS:
            fn = Path(name).stem
            if not self._get(f"exist('{fn}')"):
                self._oc.addpath(str(shims / fn))
        self._eval(
            "warning('off', 'Octave:possible-matlab-short-circuit-operator');"
            "warning('off', 'Octave:language-extension');"
        )
        self._tmp = Path(tempfile.mkdtemp(prefix="pgecourse-"))
        self._seq_file: Path | None = None

    def _eval(self, code: str) -> list[str]:
        out: list[str] = []
        try:
            self._oc.eval(code, stream_handler=out.append)
        except Exception as e:  # oct2py raises Oct2PyError
            msg = str(e).split("error: ", 1)[-1].split("error: called from")[0].strip()
            raise PGE2Error(msg) from None
        clean = []
        for line in out:
            line = _PROGRESS.sub("", line.replace("\b", "")).strip()
            if re.fullmatch(r"[\w.]+\(\): [^:]*:( ok)?", line):
                continue
            if line and not line.startswith(("Reading ", "done")):
                clean.append(line)
        return _merge_warnings(clean)

    def _get(self, expr: str):
        self._oc.eval(f"pgecourse_value__ = {expr};")
        return self._oc.pull("pgecourse_value__")

    def from_seq(self, seq) -> SegmentReport:
        """Convert a sequence to the pulseg representation.

        Parameters
        ----------
        seq : pypulseq.Sequence
            The sequence, as it would be written to a ``.seq`` file.

        Returns
        -------
        SegmentReport
            The virtual segments, their block layout and any warnings.

        Raises
        ------
        PGE2Error
            If ``pulseg.fromSeq`` stops with an error.
        """
        trids = _trid_instances(seq)
        if not trids:
            raise PGE2Error("no TRID label in the sequence: pulseg needs one on the first block of every segment")
        self._seq_file = self._tmp / "course.seq"
        seq.write(str(self._seq_file))
        messages = self._eval(f"psq = pulseg.fromSeq('{self._seq_file}');")
        n_seg = int(self._get(f"psq.nSegments"))
        segs = []
        for i in range(1, n_seg + 1):
            trid = int(self._get(f"psq.segments({i}).TRID"))
            ids = self._get(f"psq.segments({i}).blockIDs")
            ids = [int(x) for x in (ids.ravel() if hasattr(ids, "ravel") else [ids])]
            segs.append(Segment(trid=trid, block_ids=ids, n_instances=trids.get(trid, 0)))
        return SegmentReport(
            segments=segs,
            n_base_blocks=int(self._get(f"psq.nParentBlocks")),
            n_blocks=int(self._get(f"psq.nMax")),
            messages=messages,
        )

    def check(self, pns_weights=(1, 1, 1)) -> dict:
        """Check the converted sequence against the GE hardware rules.

        Runs ``pge2.check`` on the sequence last passed to ``from_seq``.

        Parameters
        ----------
        pns_weights : tuple of float
            Directional PNS weights, see ``pge2.pns``.

        Returns
        -------
        dict
            Peak B1 (G), peak gradient (G/cm) and peak slew (G/cm/ms) over
            the scan.

        Raises
        ------
        PGE2Error
            If a block or segment instance breaks a hardware rule.
        """
        s = self.scanner
        self._eval(
            f"sys_ge = pge2.opts({s['psd_rf_wait']}, {s['psd_grd_wait']}, {s['b1_max']}, "
            f"{s['g_max']}, {s['slew_max']}, '{s['coil']}');"
            f"params = pge2.check(psq, sys_ge, 'PNSwt', [{' '.join(map(str, pns_weights))}]);"
        )
        return {k: float(self._get(f"params.{k}")) for k in ("b1max", "gmax", "smax")}

    def validate(self) -> bool:
        """Compare the pulseg representation with the original ``.seq`` file.

        Runs ``pge2.validate`` over every segment instance.

        Returns
        -------
        bool
            True if every segment instance matches the ``.seq`` file.

        Raises
        ------
        PGE2Error
            If ``pge2.validate`` stops with an error.
        """
        self.last_messages = self._eval(
            f"seq_ref = mr.Sequence(); seq_ref.read('{self._seq_file}');"
            "ok = pge2.validate(psq, sys_ge, seq_ref, [], 'row', [], 'plot', false);"
        )
        return bool(self._get(f"ok"))

    def instance_waveforms(self, row: int) -> dict:
        """Gradients of one segment instance, as pge2 plays them and as the .seq file has them.

        Call ``check`` first.

        Parameters
        ----------
        row : int
            Block number (1-based, as in the ``.seq`` file) where the segment
            instance starts.

        Returns
        -------
        dict
            ``"played"`` and ``"seq"``, each mapping ``"gx"``, ``"gy"``, ``"gz"``
            to ``(t, g)``: time in s from the start of the instance and
            gradient in mT/m. ``"block_edges"`` holds the block boundaries in s.
        """
        self._eval(
            f"pgc_i = psq.loop({row}, 1); pgc_n2 = {row} - 1 + psq.segments(pgc_i).nBlocksInSegment;"
            f"pgc_S = getsegmentinstance(psq, pgc_i, sys_ge, psq.loop({row}:pgc_n2, :), 'rotate', false, 'interpolate', true);"
            f"if ~exist('seq_ref', 'var'), seq_ref = mr.Sequence(); seq_ref.read('{self._seq_file}'); end;"
            f"pgc_w = seq_ref.waveforms_and_times(true, [{row} pgc_n2]);"
        )
        dead = float(self._get("sys_ge.segment_dead_time"))
        out = {"played": {}, "seq": {}}
        for k, ax in enumerate(("gx", "gy", "gz"), start=1):
            t = np.asarray(self._get(f"pgc_S.{ax}.t")).ravel() - dead
            g = np.asarray(self._get(f"pgc_S.{ax}.signal")).ravel() * 10
            out["played"][ax] = (t, g)
            w = np.atleast_2d(np.asarray(self._get(f"pgc_w{{{k}}}")))
            if w.size:
                out["seq"][ax] = (w[0], w[1] / self._get("sys_ge.gamma") / 10)
            else:
                out["seq"][ax] = (np.zeros(0), np.zeros(0))
        out["block_edges"] = np.asarray(self._get("pgc_S.tic")).ravel() - dead
        return out

    def serialize(self, path: str | os.PathLike, pislquant: int = 10) -> Path:
        """Write the checked sequence to a ``.pge`` file for the scanner.

        Parameters
        ----------
        path : path
            Output file.
        pislquant : int
            Number of ADC events Auto Prescan uses to set the receive gain.

        Returns
        -------
        Path
            The file written.
        """
        path = Path(path).resolve()
        self._eval(
            f"pge2.serialize(psq, '{path}', 'pislquant', {pislquant}, 'params', params, 'checkHash', false);"
        )
        return path


def _trid_instances(seq) -> dict[int, int]:
    counts: dict[int, int] = {}
    for n in seq.block_events:
        labels = seq.get_block(n).label
        if not labels:
            continue
        for lab in labels.values():
            if lab.label == "TRID":
                counts[int(lab.value)] = counts.get(int(lab.value), 0) + 1
    return counts


def _merge_warnings(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for line in lines:
        if line.startswith("warning: called from") or line.startswith(("fromSeq at", "run")):
            continue
        if merged and merged[-1].lower().startswith("warning") and not line.lower().startswith(
            ("warning", "error")
        ):
            if line.startswith(("pulseg", "pge2")) or " at line " in line:
                continue
            merged[-1] += "\n" + line
        else:
            merged.append(line)
    return merged
