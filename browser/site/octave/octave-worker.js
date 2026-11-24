// One Octave run per worker. The page sends:
//   {wasmModule: WebAssembly.Module, packs: [{index, data}], files: {path: Uint8Array},
//    script: string, collect: [dir]}
// The worker writes the packs and the files into MEMFS, runs `octave-cli --eval script`,
// and posts back {stdout, stderr, files} with every file under the `collect` dirs.
// This Octave build crashes while shutting down; output written before is kept.

self.onmessage = (ev) => {
  const { wasmModule, packs, files, script, collect, base } = ev.data;
  const stdout = [], stderr = [];
  let done = false;

  function finish(error) {
    if (done) return;
    done = true;
    const out = {};
    const walk = (dir) => {
      let names = [];
      try { names = self.FS.readdir(dir); } catch (e) { return; }
      for (const n of names) {
        if (n === '.' || n === '..') continue;
        const p = dir + '/' + n, st = self.FS.stat(p);
        if (self.FS.isDir(st.mode)) walk(p); else out[p] = self.FS.readFile(p);
      }
    };
    try { for (const d of collect) walk(d); } catch (e) {}
    self.postMessage({ stdout: stdout.join('\n'), stderr: stderr.join('\n'), files: out, error });
  }

  self.Module = {
    arguments: ['--no-gui', '--norc', '--no-history', '--eval', script],
    // The script ends with a marker line. On it, report and park this worker:
    // returning to Octave would run its shutdown, which crashes the tab.
    print: (s) => {
      if (s === '__PGE_DONE__') {
        finish(null);
        try { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0); } catch (e) {}
        for (;;) {}  // until the page terminates this worker
      }
      stdout.push(s); 
    },
    printErr: (s) => { stderr.push(s); },
    instantiateWasm: (imports, ok) => {
      WebAssembly.instantiate(wasmModule, imports).then((inst) => ok(inst, wasmModule));
      return {};
    },
    preRun: [() => {
      const FS = self.FS;
      const mk = (p) => { try { FS.mkdirTree(p); } catch (e) {} };
      for (const { index, data } of packs) {
        const bytes = new Uint8Array(data);
        for (const [path, [off, len]] of Object.entries(index)) {
          mk(path.slice(0, path.lastIndexOf('/')));
          FS.writeFile(path, bytes.subarray(off, off + len));
        }
      }
      for (const [path, data] of Object.entries(files)) {
        mk(path.slice(0, path.lastIndexOf('/')));
        FS.writeFile(path, data);
      }
      mk('/home/user'); mk('/work');
      self.ENV.OCTAVE_HOME = '/';
      self.ENV.HOME = '/home/user';
    }],
    onExit: () => finish(null),
    onAbort: (what) => finish(null),
  };
  self.onerror = () => { finish(null); return true; };
  // The wasm instantiates asynchronously, so main runs after importScripts returns;
  // the run ends in onExit, onAbort or (shutdown crash) self.onerror.
  self.addEventListener('unhandledrejection', () => finish(null));
  try {
    importScripts(base + 'octave-cli.js');
  } catch (e) {
    finish(String(e));
  }
};
