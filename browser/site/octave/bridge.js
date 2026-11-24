// Octave bridge: load once, then run scripts in fresh workers.
//   const oc = await OctaveBridge.load('octave/');
//   const r = await oc.run(script, {'/work/x.seq': bytes}, ['/work']);
// Files under /work persist between runs (kept here and written back each time).
(function (global) {
  class OctaveBridge {
    static async load(base) {
      const t0 = performance.now();
      const get = (f) => fetch(base + f).then((r) => { if (!r.ok) throw new Error(f + ': ' + r.status); return r; });
      const [wasmModule, share, shareIdx, tb, tbIdx] = await Promise.all([
        WebAssembly.compileStreaming(get('octave-cli.wasm')),
        get('share.pack').then((r) => r.arrayBuffer()),
        get('share.json').then((r) => r.json()),
        get('toolboxes.pack').then((r) => r.arrayBuffer()),
        get('toolboxes.json').then((r) => r.json()),
      ]);
      const b = new OctaveBridge();
      b.base = new URL(base, global.location.href).href;
      b.wasmModule = wasmModule;
      b.packs = [{ index: shareIdx, data: share }, { index: tbIdx, data: tb }];
      b.work = {};
      b.loadSeconds = (performance.now() - t0) / 1000;
      return b;
    }

    run(script, files = {}, collect = ['/work']) {
      const t0 = performance.now();
      const all = Object.assign({}, this.work, files);
      return new Promise((resolve) => {
        const w = new Worker(this.base + 'octave-worker.js');
        w.onmessage = (ev) => {
          w.terminate();
          const r = ev.data;
          for (const [p, d] of Object.entries(r.files)) if (p.startsWith('/work/')) this.work[p] = d;
          r.seconds = (performance.now() - t0) / 1000;
          resolve(r);
        };
        w.postMessage({ wasmModule: this.wasmModule, packs: this.packs, files: all, script: "try\n" + script + "\ncatch err__\n  disp(['__PGE_ERROR__ ' err__.message]);\nend\nfflush(stdout); disp('__PGE_DONE__');\n", collect, base: this.base });
      });
    }
  }
  global.OctaveBridge = OctaveBridge;
})(self);
