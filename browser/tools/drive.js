const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--disable-dev-shm-usage', '--enable-logging=stderr', '--v=0'], dumpio: !!process.env.DUMPIO });
  const p = await b.newPage();
  p.on('console', m => process.stdout.write('[console] ' + m.text() + '\n'));
  p.on('worker', w => { process.stdout.write('[worker created]\n'); });
  p.on('pageerror', e => process.stdout.write('[pageerror] ' + e + '\n'));
  const t = Date.now();
  await p.goto(process.argv[2]);
  await p.waitForFunction(() => /DONE|FAILED/.test(document.getElementById('log').textContent), null, { timeout: 600000 });
  console.log(`[page total ${(Date.now() - t) / 1000} s]`);
  await b.close();
})();
