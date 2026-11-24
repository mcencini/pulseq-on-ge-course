// Run code cells in the JupyterLite REPL and print the outputs.
const { chromium } = require('playwright');
const cells = (process.env.CELLS ? JSON.parse(require('fs').readFileSync(process.env.CELLS,'utf8')) : [
  "%pip install pypulseq",
  "import time, gre2d, pge_browser\nt=time.time(); ge = await pge_browser.GE.start(); seq = gre2d.gre2d(); print(f'START {time.time()-t:.1f} s')",
  "t=time.time(); r = await ge.from_seq(seq); print(r); print(f'FROMSEQ {time.time()-t:.1f} s')",
  "t=time.time(); p = await ge.check(); print(p); print(f'CHECK {time.time()-t:.1f} s')",
  "t=time.time(); ok = await ge.validate(); print('VALIDATE', ok, f'{time.time()-t:.1f} s')",
]);
(async () => {
  const b = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
  const p = await b.newPage();
  p.on('pageerror', e => console.log('[pageerror] ' + e));
  p.on('console', m => { const t = m.text(); if (!/^\[\w+\] (Loading|Loaded)/.test(t)) console.log('[console] ' + t.slice(0, 300)); });
  p.on('worker', w => { console.log('[worker] ' + w.url().slice(-80)); w.on('console', m => console.log('[worker console] ' + m.text().slice(0, 300))); });
  const url = process.argv[2] + '/repl/index.html?kernel=python&' + cells.map(c => 'code=' + encodeURIComponent(c)).join('&');
  const t = Date.now();
  await p.goto(url);
  try {
    await p.waitForFunction(() => [...document.querySelectorAll('.jp-OutputArea-output')].some(e => /VALIDATE |Traceback|Error:/.test(e.innerText)), null, { timeout: +(process.env.WAIT || 900000) });
    await p.waitForTimeout(1000);
  } catch (e) { console.log('[timeout]'); }
  const outs = await p.$$eval('.jp-OutputArea-output', els => els.map(e => e.innerText));
  console.log(outs.join('\n----\n').slice(0, 4000));
  console.log(`[page total ${(Date.now() - t) / 1000} s]`);
  await b.close();
})();
