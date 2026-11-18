// End to end test of the desktop app screen. Needs: node, playwright, python with tally_connect importable.
// Usage:  NODE_PATH=$(npm root -g) node tests/e2e_ui.js [screenshot_dir]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const root = path.resolve(__dirname, '..');
const shots = process.argv[2] || '/tmp';
const PORT = 8700 + Math.floor(Math.random() * 200);
let srvRef = null;
const results = [];
function check(name, cond, extra) { results.push({ name, ok: !!cond, extra }); if (!cond) console.log('FAIL', name, extra || ''); }

(async () => {
  const srv = spawn(process.env.PYTHON || 'python3', ['-m', 'tally_connect.cli', 'app', '--demo', '--no-browser', '--port', String(PORT)],
    { env: { ...process.env, ...(process.env.E2E_INSTALLED ? {} : { PYTHONPATH: path.join(root, 'src') }), TALLY_CONNECT_HOME: require('fs').mkdtempSync('/tmp/tc-e2e-') }, stdio: 'pipe' });
  srvRef = srv;
  await new Promise(r => setTimeout(r, 2500));
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1360, height: 960 } })).newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  const url = `http://127.0.0.1:${PORT}/`;
  const shot = n => p.screenshot({ path: path.join(shots, n + '.png') });

  await p.goto(url);
  await p.waitForSelector('#pConn.ok', { timeout: 8000 });
  check('connected pill shows company', /Demo Traders/.test(await p.textContent('#pConn')));
  check('demo badge shown', /DEMO/.test(await p.textContent('#pMode')));
  await shot('app-1-import');

  // ----- read the sample -----
  await p.click('[data-act="sample"]');
  await p.waitForSelector('tr.rw', { timeout: 8000 });
  check('nine rows', (await p.locator('tr.rw').count()) === 9);
  const chips = await p.textContent('#planBox');
  check('counts 5 ready 2 held', /5 ready/.test(chips) && /2 held/.test(chips));
  check('series complete banner', /Series complete/.test(chips));
  await shot('app-2-review');

  // ----- invalid: held party cannot be approved, create ledger needs complete details -----
  await p.click('tr.rw[data-i="3"]');
  check('held party shows a question', /no ledger for ANKUR SRIVASTAV/i.test(await p.textContent('.detail')));
  check('no approve button for a missing party', (await p.locator('[data-act="approve"]').count()) === 0);
  await p.click('[data-act="newledger"]');
  await p.click('[data-act="ledgercheck"]');
  await p.waitForSelector('#lf-go');
  check('incomplete ledger is flagged and blocked', await p.locator('#lf-go').isDisabled() && /Still needed/.test(await p.textContent('.detail')));
  await shot('app-3-ledger-incomplete');
  await p.fill('#lf-state', 'Chandigarh'); await p.fill('#lf-pin', '160022'); await p.fill('#lf-addr', 'Shop 12\nSector 22');
  await p.click('[data-act="ledgercheck"]');
  await p.waitForSelector('#lf-ok:not([disabled])');
  await p.click('[data-act="ledgercreate"]');
  await p.waitForTimeout(300);
  check('needs the approval tick first', /Tick the box/.test(await p.textContent('#toast')));
  await p.check('#lf-ok'); await p.click('[data-act="ledgercreate"]');
  await p.waitForFunction(() => document.querySelector('tr.rw[data-i="3"] .pill.ok'), null, { timeout: 8000 });
  check('row 2204 is ready after the ledger is created', true);

  // ----- held item: map to an existing item -----
  await p.click('tr.rw[data-i="4"]');
  check('item hold shown', /No stock item matches/.test(await p.textContent('.detail')));
  await p.fill('input[data-key]', 'pb331'); await p.click('[data-act="search"]');
  await p.waitForSelector('[data-act="mapitem"]');
  await p.click('[data-act="mapitem"]');
  await p.waitForFunction(() => document.querySelector('tr.rw[data-i="4"] .pill.ok'), null, { timeout: 8000 });
  check('row 2205 is ready after mapping', true);

  // ----- error and duplicate rows explain themselves -----
  await p.click('tr.rw[data-i="6"]');
  check('error row explains tax inclusive amounts', /may already include tax/.test(await p.textContent('.detail')));
  await p.click('tr.rw[data-i="5"]');
  check('duplicate row explains', /already in Tally/.test(await p.textContent('.detail')));
  await p.click('tr.rw[data-i="5"]');

  // ----- skip one on purpose, then post -----
  await p.click('.chip:has-text("Ready")');
  const readyBefore = await p.locator('tr.rw').count();
  check('7 ready before posting', readyBefore === 7, readyBefore);
  await p.click('.chip:has-text("All")');
  await shot('app-4-ready-to-post');
  await p.click('#postBtn');
  check('post button needs the approval tick', await p.locator('#cfYes').isDisabled());
  await p.check('#cf'); await p.click('#cfYes');
  await p.waitForFunction(() => /All done|Stopped/.test(document.querySelector('#postBox').textContent), null, { timeout: 30000 });
  const post = await p.textContent('#postBox');
  check('all done', /All done/.test(post) && /7 entries posted/.test(post), post);
  check('seven posted pills', (await p.locator('tr.rw .pill:has-text("Posted")').count()) === 7);
  await shot('app-5-posted');
  await p.click('tr.rw[data-i="0"]');
  check('balance proof is shown', /Posted and verified/.test(await p.textContent('.detail')) && /party balance moved by/.test(await p.textContent('.detail')));
  await shot('app-6-proof');

  // ----- read the same file again: everything posted is now a duplicate -----
  await p.click('[data-tab="import"]');
  await p.click('[data-act="sample"]');
  await p.waitForSelector('tr.rw', { timeout: 8000 });
  const again = await p.textContent('#planBox');
  check('re-reading shows 8 duplicates, nothing ready', /0 ready/.test(again) && /8 skipped or duplicate/.test(again), again.slice(0, 200));
  await shot('app-7-duplicates');

  // ----- csv report downloads -----
  const [dl] = await Promise.all([p.waitForEvent('download'), p.click('[data-act="report"]')]);
  check('report downloads as csv', /\.csv$/.test(dl.suggestedFilename()));

  // ----- setup, history, help -----
  await p.click('[data-tab="setup"]');
  await p.waitForSelector('#gstin');
  check('setup shows the company details', (await p.inputValue('#gstin')) === '04AAAAA0000A1Z5');
  await p.click('[data-sact="scan"]');
  await p.waitForSelector('[data-led="cgst_out"]');
  await p.waitForTimeout(400);
  check('scan lists the ledger names', (await p.inputValue('[data-led="utgst_out"]')) === 'UTGST OUTPUT');
  await shot('app-8-setup');
  await p.check('#ro', { force: true }).catch(() => {});
  await p.evaluate(() => { const c = document.querySelector('#ro'); c.checked = true; });
  await p.click('[data-sact="save"]');
  await p.waitForFunction(() => document.querySelector('#pWrite').textContent.includes('Read only'), null, { timeout: 5000 });
  check('read only mode is shown in the header', true);
  await p.click('[data-tab="import"]');
  await p.click('[data-act="sample"]');
  await p.waitForSelector('tr.rw');
  check('post button disabled in read only', await p.locator('#postBtn').isDisabled());
  await p.click('[data-tab="setup"]'); await p.waitForSelector('#ro');
  await p.evaluate(() => { document.querySelector('#ro').checked = false; });
  await p.click('[data-sact="save"]');
  await p.waitForFunction(() => !document.querySelector('#pWrite').textContent.includes('Read only'), null, { timeout: 5000 });

  await p.click('[data-tab="history"]');
  await p.waitForSelector('table');
  check('history lists the 7 sales', (await p.locator('tbody tr').count()) >= 7);
  await shot('app-9-history');
  await p.click('[data-tab="help"]');
  await p.click('[data-hact="diag"]');
  await p.waitForSelector('#diag:not([hidden])');
  check('diagnostics text has no secrets and has the version', /Tally Connect 0\.2\.0/.test(await p.textContent('#diag')) && !/token/i.test(await p.textContent('#diag')));
  await shot('app-10-help');

  // ----- phone width and dark mode do not break the layout -----
  await p.setViewportSize({ width: 390, height: 800 });
  await p.click('[data-tab="import"]');
  check('no sideways scroll on a phone', !(await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2)));
  await p.emulateMedia({ colorScheme: 'dark' });
  await shot('app-11-dark-mobile');

  check('no browser errors', errs.length === 0, errs.join(' | '));
  await b.close(); srv.kill();
  const bad = results.filter(r => !r.ok);
  console.log(JSON.stringify({ total: results.length, passed: results.length - bad.length, failed: bad.map(x => x.name + ' ' + (x.extra || '')) }, null, 1));
  process.exit(bad.length ? 1 : 0);
})().catch(e => { console.error('E2E CRASH', e); if (srvRef) srvRef.kill(); process.exit(2); });
