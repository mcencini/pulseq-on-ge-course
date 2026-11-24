// Open a notebook of the built site in JupyterLite (headless Chromium), run all
// cells, print the outputs. Every request that is not to the site is blocked,
// to check that the site is self-contained.
// Usage: node lite/tests/run_notebook.js http://localhost:8768 00_gre2d_reference.ipynb
const { chromium } = require('playwright');
(async () => {
  const [site, nb] = process.argv.slice(2);
  const origin = new URL(site).origin;
  const b = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
  const ctx = await b.newContext();
  const blocked = new Set();
  await ctx.route('**/*', (route) => {
    const u = route.request().url();
    if (u.startsWith(origin) || u.startsWith('blob:') || u.startsWith('data:')) return route.continue();
    blocked.add(new URL(u).host);
    return route.abort();
  });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => console.log('[pageerror] ' + String(e).slice(0, 300)));
  const t0 = Date.now();
  await p.goto(`${site}/notebooks/index.html?path=${nb}`);
  await p.waitForSelector('.jp-Notebook .jp-Cell', { timeout: 120000 });
  await p.waitForFunction(() => /Idle/.test(document.body.innerText), null, { timeout: 180000 }).catch(() => {});
  await p.waitForTimeout(2000);
  const dlg = await p.$('.jp-Dialog');
  if (dlg) { console.log('[dialog] ' + (await dlg.innerText()).slice(0, 200)); await p.keyboard.press('Enter'); await p.waitForTimeout(1000); }
  await p.click('text=Run', { timeout: 30000 });
  await p.click('text=Run All Cells', { timeout: 30000 });
  // done when no cell has been running or queued ([*]) for 15 s
  let quiet = 0;
  const limit = Date.now() + +(process.env.WAIT || 1500000);
  while (Date.now() < limit) {
    await p.waitForTimeout(3000);
    const busy = await p.$$eval('.jp-CodeCell .jp-InputPrompt', (els) => els.some((e) => e.innerText.includes('*')));
    quiet = busy ? 0 : quiet + 3;
    if (quiet >= 15) break;
  }
  const cells = await p.$$eval('.jp-CodeCell', (els) => els.map((e) => ({
    prompt: e.querySelector('.jp-InputPrompt')?.innerText || '',
    out: [...e.querySelectorAll('.jp-OutputArea-output')].map((o) => o.innerText).join('\n'),
    error: !!e.querySelector('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stderr"], .jp-RenderedText[data-mime-type="application/vnd.jupyter.error"]'),
  })));
  for (const c of cells) console.log(`${c.prompt} ${c.error ? '[ERROR] ' : ''}${c.out.slice(0, 600)}`);
  console.log(`[${nb}: ${cells.length} code cells, ${(Date.now() - t0) / 1000} s; blocked hosts: ${[...blocked].join(', ') || 'none'}]`);
  await b.close();
})();
