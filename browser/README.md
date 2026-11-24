# Browser prototype: pulseg and pge2 from Python, with nothing installed

pypulseq runs in [Pyodide](https://pyodide.org) (Python compiled to WebAssembly).
The official pulseg and pge2 MATLAB toolboxes run in GNU Octave 10.3 compiled to
WebAssembly (the `octave` package of [emscripten-forge](https://emscripten-forge.org)),
in a Web Worker. `pge_browser.GE` offers the same calls as `pgecourse.GE`, as
coroutines:

```python
ge = await GE.start()
await ge.from_seq(seq)
await ge.check()
await ge.validate()
```

Status, on the reference gre2d in headless Chromium:

- plain page: fromSeq 4.5 s, check 5.9 s, validate 6.5 s;
- JupyterLite (Pyodide 314 kernel): fromSeq 5.3 s, check 7.6 s, validate 6.7 s,
  Octave workers started from the kernel's worker;
- results identical to desktop Octave;
- `pyodide.ffi.run_sync` works (JSPI), so the calls can be made without `await`.

Not tested in Firefox or Safari.

## How it works

- `site/octave/bridge.js` compiles `octave-cli.wasm` once and fetches two packs:
  Octave's script library (`share.pack`) and the pinned toolboxes
  (`toolboxes.pack`), each a concatenation of files with a JSON index.
- Every call starts a fresh worker (`octave-worker.js`) that writes the packs and
  the files under `/work` into its in-memory filesystem and runs
  `octave-cli --eval <script>`. Files under `/work` (the `.seq`, the saved `psq`)
  are carried over to the next call.
- This Octave build crashes when it shuts down, and in Chromium that takes the
  tab down. So the bridge wraps every script in try/catch and ends it with a
  marker line; on that line the worker reports and is terminated before Octave
  reaches its shutdown.

## Build

```bash
pip install py-rattler
python tools/fetch_octave_wasm.py octave "$PWD/oct-env"
python -c "import pgecourse; pgecourse.GE()"   # fetches and patches the toolboxes into ~/.cache/pgecourse
python tools/pack.py "$PWD/oct-env" ~/.cache/pgecourse "$PWD/site"
cp oct-env/bin/octave-cli-10.3.0 site/octave/octave-cli.js
cp oct-env/bin/octave-cli.wasm site/octave/
pip download --no-deps pypulseq==1.5.0.post1 -d site
cp ../pgecourse/sequences/gre2d.py site/
```

## Test

```bash
(cd site && python -m http.server 8765) &
node tools/drive.js http://localhost:8765/index.html
```

`tools/run_node.js` and `tools/test_chain.m` run the same chain under Node,
without a browser.

## JupyterLite

```bash
pip install jupyterlite-core jupyterlite-pyodide-kernel jupyter-server
mkdir -p lite/files lite/pypi
cp site/pge_browser.py ../pgecourse/sequences/gre2d.py lite/files/
pip download --no-deps pypulseq==1.5.0.post1 comm -d lite/pypi   # wheels served by the site itself
(cd lite && jupyter lite build --output-dir dist)
cp -r site/octave lite/dist/octave
(cd lite/dist && python -m http.server 8766) &
node tools/drive_lite.js http://localhost:8766            # runs the chain in the JupyterLite console
CELLS=tools/cells_sync.json node tools/drive_lite.js http://localhost:8766   # same, without await
```

`comm` is needed by the kernel and is not in the Pyodide distribution; bundling
it (and pypulseq) means the site does not need PyPI at run time.
