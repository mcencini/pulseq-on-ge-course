"""pulseg and pge2 for pypulseq sequences, in the browser.

Same calls as the course helper (pgecourse.GE), but Octave runs as WebAssembly
in a Web Worker instead of a local process. Every method is a coroutine:

    ge = await GE.start()
    await ge.from_seq(seq)
    await ge.check()
    await ge.validate()
"""

import re
import tempfile

import js
from pyodide.ffi import to_js

PRELUDE = """
addpath('/tb/pge2'); addpath('/tb/pulseg/third_party'); addpath('/tb/pulseg');
addpath('/tb/pulseq'); addpath('/tb/overlay');
for f = {'DataHash','rmse','MException','throw'}
  if ~exist(f{1}), addpath(['/tb/shims/' f{1}]); end
end
warning('off', 'all');
"""

DEFAULT_SCANNER = dict(psd_rf_wait=100e-6, psd_grd_wait=100e-6, b1_max=0.25, g_max=5.0, slew_max=20.0, coil="xrm")

_PROGRESS = re.compile(r"\d+(\.\d+)?%\s*\[[ .*]*\]")


class PGE2Error(RuntimeError):
    """Raised when pulseg or pge2 rejects a sequence."""


class GE:
    def __init__(self, bridge, scanner=None):
        self._oc = bridge
        self.scanner = {**DEFAULT_SCANNER, **(scanner or {})}

    @classmethod
    async def start(cls, base="octave/", scanner=None):
        return cls(await js.OctaveBridge.load(base), scanner)

    async def _run(self, body, files=None):
        script = PRELUDE + "try\n" + body + "\ncatch err\n fprintf('PGE2ERROR %s\\n', err.message);\nend\n"
        js_files = to_js(files or {}, dict_converter=js.Object.fromEntries)
        r = await self._oc.run(script, js_files)
        out = _PROGRESS.sub("", str(r.stdout).replace("\b", ""))
        self.last_stdout, self.last_stderr = out, str(r.stderr)
        err = [l.replace("__PGE_ERROR__", "PGE2ERROR") for l in out.splitlines() if l.startswith(("PGE2ERROR ", "__PGE_ERROR__ "))]
        if err:
            raise PGE2Error(err[0][len("PGE2ERROR "):])
        return out, float(r.seconds)

    async def from_seq(self, seq):
        with tempfile.NamedTemporaryFile(suffix=".seq") as f:
            seq.write(f.name)
            data = open(f.name, "rb").read()
        out, t = await self._run(
            "psq = pulseg.fromSeq('/work/course.seq');\n"
            "save('-binary', '/work/psq.mat', 'psq');\n"
            "fprintf('NSEG %d NBASE %d\\n', psq.nSegments, psq.nParentBlocks);\n"
            "for i = 1:psq.nSegments, fprintf('SEG %d %s\\n', psq.segments(i).TRID, mat2str(psq.segments(i).blockIDs)); end",
            {"/work/course.seq": to_js(data)},
        )
        self.last_seconds = t
        return "\n".join(l for l in out.splitlines() if l.startswith(("NSEG", "SEG")))

    async def check(self, pns_weights=(1, 1, 1)):
        s = self.scanner
        out, t = await self._run(
            "load('/work/psq.mat');\n"
            f"sys_ge = pge2.opts({s['psd_rf_wait']}, {s['psd_grd_wait']}, {s['b1_max']}, {s['g_max']}, {s['slew_max']}, '{s['coil']}');\n"
            f"params = pge2.check(psq, sys_ge, 'PNSwt', [{' '.join(map(str, pns_weights))}]);\n"
            "save('-binary', '/work/params.mat', 'params', 'sys_ge');\n"
            "fprintf('PARAMS %.17g %.17g %.17g\\n', params.b1max, params.gmax, params.smax);"
        )
        self.last_seconds = t
        if "PARAMS" not in out:
            raise PGE2Error("no result; stdout:\n" + out[-2000:] + "\nstderr:\n" + self.last_stderr[-2000:])
        b1, g, sl = next(l for l in out.splitlines() if l.startswith("PARAMS")).split()[1:]
        return {"b1max": float(b1), "gmax": float(g), "smax": float(sl)}

    async def validate(self):
        out, t = await self._run(
            "load('/work/psq.mat'); load('/work/params.mat');\n"
            "seq_ref = mr.Sequence(); seq_ref.read('/work/course.seq');\n"
            "ok = pge2.validate(psq, sys_ge, seq_ref, [], 'row', [], 'plot', false);\n"
            "fprintf('OK %d\\n', ok);"
        )
        self.last_seconds = t
        return next(l for l in out.splitlines() if l.startswith("OK")).split()[1] == "1"
