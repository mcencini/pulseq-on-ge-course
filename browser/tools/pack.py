"""Pack folder trees into one binary blob plus a JSON index: {virtual_path: [offset, length]}."""
import json, os, sys
from pathlib import Path

def pack(mounts, out_bin, out_idx, skip=()):
    index, off = {}, 0
    with open(out_bin, "wb") as f:
        for virt, host in mounts.items():
            host = Path(host)
            for p in sorted(host.rglob("*")):
                if p.is_dir() or any(s in p.parts for s in skip):
                    continue
                data = p.read_bytes()
                index[virt + "/" + p.relative_to(host).as_posix()] = [off, len(data)]
                f.write(data); off += len(data)
    Path(out_idx).write_text(json.dumps(index))
    print(f"{out_bin}: {len(index)} files, {off/1e6:.1f} MB")

if __name__ == "__main__":
    env, cache, site = sys.argv[1:4]
    pack({"/share/octave": f"{env}/share/octave"}, f"{site}/octave/share.pack", f"{site}/octave/share.json",
         skip=("doc", "fonts", "imagelib"))
    pack({"/tb/pulseq/+mr": f"{cache}/pulseq/matlab/+mr", "/tb/pulseg": f"{cache}/pulseg/matlab",
          "/tb/pge2": f"{cache}/pge2/matlab", "/tb/overlay": f"{cache}/octave-overlay",
          "/tb/shims": f"{cache}/octave-shims"},
         f"{site}/octave/toolboxes.pack", f"{site}/octave/toolboxes.json", skip=(".git",))
