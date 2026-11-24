// Run wasm octave-cli under Node with a host folder tree copied into MEMFS.
const fs = require('fs'), path = require('path');
const ENV_DIR = process.argv[2];              // conda env with octave
const mounts = JSON.parse(process.argv[3]);   // {"/virtual/path": "/host/path", ...}
const args = process.argv.slice(4);
function copyTree(FS, host, virt) {
  const st = fs.statSync(host);
  if (st.isDirectory()) {
    try { FS.mkdirTree(virt); } catch (e) {}
    for (const n of fs.readdirSync(host)) copyTree(FS, path.join(host, n), virt + '/' + n);
  } else FS.writeFile(virt, fs.readFileSync(host));
}
const t0 = Date.now();
globalThis.Module = {
  arguments: args,
  print: s => console.log(s), printErr: s => console.error(s),
  preRun: [() => {
    const FS = globalThis.FS;
    for (const [v, h] of Object.entries(mounts)) copyTree(FS, h, v); console.error('[preRun: copied', Object.keys(mounts).join(','), ']');
    globalThis.ENV.OCTAVE_HOME = '/';
    globalThis.ENV.HOME = '/home/user';
    try { FS.mkdirTree('/home/user'); } catch (e) {}
  }],
  onExit: c => { console.error(`[exit ${c} after ${(Date.now()-t0)/1000}s]`); },
};
const loader = path.join(ENV_DIR, 'bin', 'octave-cli-10.3.0');
globalThis.require = require; globalThis.__filename = loader; globalThis.__dirname = path.dirname(loader);
require('vm').runInThisContext(fs.readFileSync(loader, 'utf8'), { filename: loader });
