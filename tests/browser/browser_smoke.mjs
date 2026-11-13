/** Real-browser checks against temporary fixture installations. No production URL is accepted. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const options = process.argv.slice(2);
const argument = (key, fallback) => options.includes(key) ? options[options.indexOf(key) + 1] : fallback;
if (options.includes('--help')) {
  console.log('node tests/browser/browser_smoke.mjs [--python .venv/bin/python] [--ui frontend/dist] [--output output/playwright]');
  process.exit(0);
}
const python = path.resolve(root, argument('--python', process.env.FINANCE_BROWSER_PYTHON ?? '.venv/bin/python'));
const ui = path.resolve(root, argument('--ui', 'frontend/dist'));
const output = path.resolve(root, argument('--output', 'output/playwright'));
await mkdir(output, { recursive: true });
const results = { fixtureOnly: true, startedAt: new Date().toISOString(), checks: [], screenshots: [], errors: [], expectedFailures: [] };
const processes = [];
let browser;
function record(message) { results.checks.push(message); console.log('PASS ' + message); }

async function poll(check, label, timeout = 20000) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    try { const value = await check(); if (value) return value; }
    catch (error) { last = error; }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out: ${label}${last ? ` (${last.message})` : ''}`);
}

async function server(mode) {
  const process = spawn(python, [path.join(here, 'seeded_server.py'), '--mode', mode, '--ui', ui], {
    cwd: root, env: { ...globalThis.process.env, PYTHONPATH: `${path.join(root, 'src')}:${path.join(root, 'tests')}` },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  processes.push(process);
  let stdout = '', stderr = '';
  process.stdout.on('data', data => { stdout += data; });
  process.stderr.on('data', data => { stderr += data; });
  const url = await poll(() => {
    if (process.exitCode !== null) throw new Error(`Fixture server exited: ${stderr}`);
    const line = stdout.split('\n').find(line => line.startsWith('{'));
    return line && JSON.parse(line).url;
  }, `${mode} server announcement`);
  await poll(async () => (await fetch(`${url}/api/health`)).ok, `${mode} server health`);
  const metadata = await (await fetch(`${url}/__browser-fixture`)).json();
  assert.equal(metadata.test_only, true, 'Refuse any server without fixture-only metadata');
  assert.equal(metadata.mode, mode);
  return url;
}

async function executable() {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  if (existsSync(chromium.executablePath())) return chromium.executablePath();
  if (existsSync('/usr/bin/chromium')) return '/usr/bin/chromium';
  const cache = path.join(homedir(), '.cache/ms-playwright');
  const installed = await readdir(cache).catch(() => []);
  for (const directory of installed.filter(name => /^chromium-\d+$/.test(name)).sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]))) {
    for (const sub of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const candidate = path.join(cache, directory, sub);
      if (existsSync(candidate)) return candidate;
    }
  }
  throw new Error('Install Chromium with: npm --prefix tests/browser exec playwright install chromium');
}

async function context(base, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, colorScheme: 'light', acceptDownloads: true });
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith(base + '/') || url.startsWith('data:') || url.startsWith('blob:')) return route.continue();
    results.errors.push(`Unexpected external browser request: ${url}`);
    return route.abort('blockedbyclient');
  });
  context.on('page', page => {
    page.setDefaultTimeout(12000);
    page.__canonicalReads = new Map();
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname;
      if (request.method() === 'GET' && /^\/api\/analysis\/[A-Z]\d\d$/.test(pathname) && !new URL(request.url()).search) {
        page.__canonicalReads.set(pathname, (page.__canonicalReads.get(pathname) ?? 0) + 1);
      }
    });
    page.on('pageerror', error => results.errors.push(`Page exception: ${error.message}`));
    page.on('console', message => {
      if (message.type() === 'error') {
        const text = message.text();
        // Explicit injected status failures are checked separately below.
        const status = /status of (\d+)/.exec(text)?.[1];
        if ((status && page.__expectedStatuses?.includes(Number(status))) || (page.__expectedConnection && /ERR_CONNECTION_REFUSED/.test(text))) results.expectedFailures.push(text);
        else results.errors.push(`Browser console: ${text}`);
      }
    });
  });
  return context;
}

async function screenshot(page, name, locator) {
  const filename = path.join(output, `${name}.png`);
  if (locator) await locator.screenshot({ path: filename });
  else await page.screenshot({ path: filename, fullPage: false });
  results.screenshots.push(filename);
}

async function shown(locator) { await locator.waitFor({ state: 'visible' }); return locator; }
async function enabled(locator) {
  await poll(async () => await locator.isVisible() && await locator.isEnabled(), 'enabled ' + await locator.textContent());
  return locator;
}
const section = (page, id) => page.locator('section.decision-section').filter({ has: page.locator(`#q-${id}`) });
const workspace = page => page.getByRole('region', { name: 'Saved figures', exact: true });
async function navigate(page, name) {
  const link = page.getByRole('link', { name, exact: true }).first();
  if (!await link.isVisible()) await page.getByRole('button', { name: /Menu/ }).click();
  await page.getByRole('link', { name, exact: true }).first().click();
}

async function openSaved(page, name) {
  await navigate(page, 'Saved figures');
  await workspace(page).getByRole('button', { name: `Open ${name}`, exact: true }).click();
  const found = workspace(page).getByRole('region', { name: 'Configure C01', exact: true }).filter({ visible: true });
  await shown(found.getByLabel('Figure name', { exact: true }));
  return found;
}
async function json(page, url) { const response = await page.request.get(url); assert.equal(response.status(), 200, await response.text()); return response.json(); }
async function savedRows(page, base) { return (await json(page, `${base}/api/saved-views`)).items; }

try {
  const [empty, seeded] = await Promise.all([server('empty'), server('seeded')]);
  results.browserExecutable = await executable();
  browser = await chromium.launch({ executablePath: results.browserExecutable, headless: true });
  results.browserVersion = browser.version();

  const emptyContext = await context(empty);
  const emptyPage = await emptyContext.newPage();
  await emptyPage.goto(empty);
  await shown(emptyPage.getByRole('heading', { name: 'Dashboard', exact: true }));
  await navigate(emptyPage, 'Saved figures');
  await shown(emptyPage.getByText('No saved figures yet.', { exact: true }));
  await navigate(emptyPage, 'Dashboard');
  await shown(emptyPage.getByText('C01 is not computed: research state is incomplete.'));
  await emptyPage.goto(`${empty}/#q-C01`);
  await shown(section(emptyPage, 'C01').getByText(/Not computed: research state is incomplete/));
  await navigate(emptyPage, 'Find a question');
  await emptyPage.getByRole('searchbox', { name: 'Find a question', exact: true }).fill('hedging');
  await shown(emptyPage.locator('#workbench a[href="#q-P07"]'));
  await screenshot(emptyPage, 'empty-install-desktop');
  record('Empty installation: overview, catalogue/workbench, withheld data and no saved figures');
  await emptyContext.close();

  const desktop = await context(seeded);
  await desktop.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = await desktop.newPage();
  await page.goto(seeded);
  await shown(page.getByRole('heading', { name: 'Dashboard', exact: true }));
  await page.waitForFunction(() => [...document.querySelectorAll('.dashboard-topic')].slice(0, 2).every(topic => { const state = topic.querySelector('.research-state'); return state && !state.textContent.includes('Reading evidence'); }));
  const initialReads = Object.fromEntries(page.__canonicalReads);
  assert.ok(Object.keys(initialReads).length >= 2 && Object.keys(initialReads).length < 8, 'Only visible/nearby dashboard leads are read initially');
  assert.ok(Object.values(initialReads).every(count => count === 1), 'Each overview analysis is read once on initial load');
  const catalogue = await json(page, `${seeded}/api/analysis`);
  const ownerBeforeNavigation = await json(page, `${seeded}/api/owner-inputs`);
  const savedBeforeNavigation = await savedRows(page, seeded);
  // Fresh URLs exercise delayed headings and every preserved public anchor.
  for (const row of catalogue) {
    await page.goto(`${seeded}/#q-${row.analysis_id}`);
    await page.reload();
    await shown(page.locator(`#q-${row.analysis_id}`));
    assert.equal(await page.locator('.decision-section h3[id^="q-"]').count(), 1);
  }
  assert.deepEqual(await json(page, `${seeded}/api/owner-inputs`), ownerBeforeNavigation);
  assert.deepEqual(await savedRows(page, seeded), savedBeforeNavigation);
  for (const hash of ['#theme-monetary_policy', '#supplementary-wisesheets', '#chart-gdp_growth_global']) {
    await page.goto(`${seeded}/${hash}`);
    await shown(page.locator(hash));
    assert.equal(await page.getByText('Source explorer', { exact: true }).evaluate(element => element.closest('details').open), true);
    if (hash.startsWith('#chart-')) assert.equal(await page.locator(hash).getByRole('button', { name: /^Close/ }).getAttribute('aria-expanded'), 'true');
  }
  await page.goBack(); await shown(page.locator('#supplementary-wisesheets'));
  await page.goForward(); await shown(page.locator('#chart-gdp_growth_global'));
  await page.goto(`${seeded}/#q-C01`);
  await shown(page.locator('#q-C01'));
  await page.goto(`${seeded}/#q-P07`);
  await shown(page.locator('#q-P07'));
  await page.goBack(); await shown(page.locator('#q-C01'));
  await page.goForward(); await shown(page.locator('#q-P07'));
  await page.goto(`${seeded}/#overview`);
  await shown(page.getByRole('heading', { name: 'Dashboard', exact: true }));
  await page.waitForFunction(() => [...document.querySelectorAll('.dashboard-topic')].slice(0, 2).every(topic => { const state = topic.querySelector('.research-state'); return state && !state.textContent.includes('Reading evidence'); }));
  await screenshot(page, 'seeded-overview-light');
  const overviewSize = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, page: document.documentElement.scrollHeight }));
  results.overviewSize = overviewSize;
  // The owner explicitly chose a full scrollable dashboard, not the former six-card short overview.
  assert.ok(overviewSize.page < 12000, 'Eight-topic dashboard must remain bounded without mounting 37 full analyses');
  const started = performance.now();
  const canonicalBefore = await json(page, `${seeded}/api/analysis/C01`);
  results.performance = { c01FixtureApiMilliseconds: Math.round((performance.now() - started) * 100) / 100,
    initialCanonicalReads: initialReads,
    note: 'Deterministic fixture timings; not a populated production-corpus performance baseline.' };
  const independentBefore = await json(page, `${seeded}/api/analysis/P07`);
  assert.ok(canonicalBefore.values.clock.length > 1);
  assert.equal((await json(page, `${seeded}/api/analysis/C03`)).values, null);
  record('All 37 question links, back/forward and full eight-topic dashboard; navigation preserves owner inputs and saved figures');
  await page.goto(`${seeded}/#q-C01`);
  await shown(section(page, 'C01').getByRole('button', { name: 'Configure', exact: true }));
  await section(page, 'C01').getByRole('button', { name: 'Configure', exact: true }).click();
  const draft = section(page, 'C01').getByRole('region', { name: 'Configure C01' });
  await shown(draft.getByLabel('Figure name', { exact: true }));
  const cap = await json(page, `${seeded}/api/analysis/C01/views/capabilities`);
  const native = cap.figures.find(figure => figure.roles.some(role => role.id === 'cli:DE'));
  assert.ok(native, 'C01 exposes a Germany native input figure');
  await draft.getByRole('combobox', { name: 'Figure', exact: true }).selectOption(native.id);
  const countries = draft.getByRole('group', { name: 'Countries and regions', exact: true });
  await countries.getByRole('checkbox', { name: 'Germany', exact: true }).check();
  for (const checkbox of await countries.getByRole('checkbox').all()) {
    const label = await checkbox.evaluate(input => input.parentElement.textContent.trim());
    if (label !== 'Germany') await checkbox.uncheck();
  }
  await draft.getByLabel('Start period', { exact: true }).fill('2024-01');
  await draft.getByLabel('End period', { exact: true }).fill('2025-02');
  await draft.getByRole('combobox', { name: 'Transformation', exact: true }).selectOption('index_100');
  await draft.getByRole('combobox', { name: 'Encoding', exact: true }).selectOption('table');
  await draft.getByLabel('Figure name', { exact: true }).fill('Browser Germany');
  await (await enabled(draft.getByRole('button', { name: 'Save figure', exact: true }))).click();
  await shown(draft.getByText('Saved Browser Germany.', { exact: true }));
  const records = await savedRows(page, seeded);
  const original = records.find(row => row.name === 'Browser Germany');
  assert.deepEqual(original.spec.geographies, ['DE']);
  assert.equal(original.spec.transform, 'index_100');
  const exportLink = draft.getByRole('link', { name: 'Export this view', exact: true });
  const href = await exportLink.getAttribute('href');
  const figureResponse = await json(page, `${seeded}${href.replace('/export?', '?')}`);
  assert.deepEqual([...new Set(figureResponse.figure.series.map(series => series.geography))], ['DE']);
  assert.equal(figureResponse.figure.series[0].data[0][1], 100);
  assert.ok(!figureResponse.figure.series[0].data.some(([period, value]) => period.startsWith('2024-03') && value !== null), 'Missing fixture month has no fabricated value');
  await shown(draft.getByRole('cell', { name: 'Missing', exact: true }));
  const downloadPromise = page.waitForEvent('download');
  await exportLink.click();
  const download = await downloadPromise;
  const exportPath = path.join(output, 'c01-exact-view.txt');
  await download.saveAs(exportPath);
  const exported = JSON.parse((await readFile(exportPath, 'utf8')).split('--- data (JSON) ---\n')[1]);
  assert.deepEqual(exported.figure, figureResponse.figure);
  assert.deepEqual(exported.view, figureResponse.view);
  assert.deepEqual((await json(page, `${seeded}/api/analysis/C01`)).values, canonicalBefore.values);
  assert.deepEqual((await json(page, `${seeded}/api/analysis/P07`)).values, independentBefore.values);
  await screenshot(page, 'configured-exact-view-desktop', draft);
  await draft.getByText('Method', { exact: true }).click();
  await draft.getByText(/^Sources \(/).click();
  await shown(draft.getByText(/OECD composite leading indicator, Germany/, { exact: false }).first());
  page.__expectedStatuses = [422];
  await draft.getByLabel('End period', { exact: true }).fill('2020-01');
  await shown(draft.getByRole('alert'));
  assert.equal(await draft.getByRole('link', { name: 'Export this view', exact: true }).count(), 0, 'Invalid draft must not retain an old export');
  assert.equal(await draft.getByRole('button', { name: 'Save changes', exact: true }).isEnabled(), false);
  await draft.getByLabel('End period', { exact: true }).fill('2025-02');
  await enabled(draft.getByRole('button', { name: 'Save changes', exact: true }));
  record('Selected analysis renders; exact Germany view, sparse table, method/sources and matching export, independent C01/P07');

  // Preserve the original while editing a separately identified copy.
  let saved = await openSaved(page, 'Browser Germany');
  await (await enabled(saved.getByRole('button', { name: 'Duplicate figure', exact: true }))).click();
  await shown(workspace(page).getByRole('button', { name: 'Open Browser Germany copy', exact: true }));
  saved = await openSaved(page, 'Browser Germany copy');
  await saved.getByRole('button', { name: 'Reset figure', exact: true }).click();
  await saved.getByLabel('Figure name', { exact: true }).fill('Browser reset copy');
  await (await enabled(saved.getByRole('button', { name: 'Save changes', exact: true }))).click();
  await shown(saved.getByText('Saved Browser reset copy.', { exact: true }));
  let latest = await savedRows(page, seeded);
  assert.deepEqual(latest.find(row => row.id === original.id), original);
  assert.equal(latest.find(row => row.name === 'Browser reset copy').spec.transform, native.defaults.transform);
  await navigate(page, 'Find a question');
  await page.getByRole('searchbox', { name: 'Find a question', exact: true }).fill('hedging');
  await page.locator('#workbench').getByRole('combobox', { name: 'Region', exact: true }).selectOption('US');
  assert.deepEqual(await savedRows(page, seeded), latest);
  await navigate(page, 'Saved figures');
  await page.reload();
  await shown(workspace(page).getByRole('button', { name: 'Open Browser Germany', exact: true }));
  await shown(workspace(page).getByRole('button', { name: 'Open Browser reset copy', exact: true }));
  record('Save/duplicate/rename/reset persist across reload; workbench filters preserve both independent records');

  // Both tabs open revision 1 before either saves. The stale write must fail.
  const second = await desktop.newPage();
  await second.goto(`${seeded}/#saved-figures`);
  const left = await openSaved(page, 'Browser Germany');
  const right = await openSaved(second, 'Browser Germany');
  await left.getByLabel('Figure name', { exact: true }).fill('Browser tab A');
  await (await enabled(left.getByRole('button', { name: 'Save changes', exact: true }))).click();
  await shown(left.getByText('Saved Browser tab A.', { exact: true }));
  second.__expectedStatuses = [409];
  await right.getByLabel('Figure name', { exact: true }).fill('Browser stale tab B');
  const conflict = second.waitForResponse(response => response.request().method() === 'PUT' && response.url().includes('/api/saved-views/'));
  await (await enabled(right.getByRole('button', { name: 'Save changes', exact: true }))).click();
  assert.equal((await conflict).status(), 409);
  await shown(right.getByRole('alert'));
  assert.equal((await savedRows(page, seeded)).find(row => row.id === original.id).name, 'Browser tab A');
  await right.getByRole('button', { name: 'Reload saved figure', exact: true }).click();
  await poll(async () => await right.getByLabel('Figure name', { exact: true }).inputValue() === 'Browser tab A', 'conflict reload');
  await screenshot(second, 'saved-conflict-recovery', right);
  record('Two real browser tabs: stale update receives409 and reload recovers without overwriting winner');

  await workspace(page).getByRole('button', { name: 'Compare figures', exact: true }).click();
  await workspace(page).getByRole('checkbox', { name: 'Compare Browser tab A', exact: true }).check();
  await workspace(page).getByRole('checkbox', { name: 'Compare Browser reset copy', exact: true }).check();
  await workspace(page).getByRole('checkbox', { name: 'Link chart zoom and crosshair', exact: true }).check();
  assert.equal(await workspace(page).getByRole('region', { name: 'Configure C01' }).filter({ visible: true }).count(), 2);
  await screenshot(page, 'compare-independent-figures', workspace(page));
  await page.getByRole('button', { name: 'Use dark appearance', exact: true }).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
  await screenshot(page, 'saved-compare-dark');
  await page.goto(`${seeded}/#overview`);
  await page.waitForFunction(() => [...document.querySelectorAll('.dashboard-topic')].slice(0, 2).every(topic => { const state = topic.querySelector('.research-state'); return state && !state.textContent.includes('Reading evidence'); }));
  await screenshot(page, 'seeded-overview-dark');
  record('Independent compare editors and explicit link control; dark appearance');

  await page.goto(`${seeded}/#q-P07`);
  await section(page, 'P07').getByRole('button', { name: 'Configure', exact: true }).click();
  const ratesEditor = section(page, 'P07').getByRole('region', { name: 'Configure P07' });
  const rateCap = await json(page, `${seeded}/api/analysis/P07/views/capabilities`);
  const rateFigure = rateCap.figures.find(figure => figure.roles.some(role => role.id === 'eur_short_rate'));
  await ratesEditor.getByRole('combobox', { name: 'Figure', exact: true }).selectOption(rateFigure.id);
  await ratesEditor.getByRole('combobox', { name: 'Encoding', exact: true }).selectOption('table');
  for (const value of ['0', '-1', '20']) await shown(ratesEditor.getByRole('cell', { name: value, exact: true }).first());
  await ratesEditor.getByRole('combobox', { name: 'Encoding', exact: true }).selectOption('line');
  await shown(ratesEditor.getByRole('link', { name: 'Export this view', exact: true }));
  await screenshot(page, 'signed-zero-outlier-rate-chart', ratesEditor);
  record('Native rate figure retains positive, negative, zero and large fixture observations in table and line view');

  page.__expectedStatuses = [503];
  const beforeSaveFailure = await savedRows(page, seeded);
  const refuseSave = route => route.request().method() === 'POST'
    ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Saved figures could not be stored; check the data directory permissions.' }) })
    : route.continue();
  await page.route('**/api/saved-views', refuseSave);
  await ratesEditor.getByLabel('Figure name', { exact: true }).fill('Browser signed rates');
  await (await enabled(ratesEditor.getByRole('button', { name: 'Save figure', exact: true }))).click();
  await shown(ratesEditor.getByRole('alert'));
  assert.deepEqual(await savedRows(page, seeded), beforeSaveFailure);
  await page.unroute('**/api/saved-views', refuseSave);
  await (await enabled(ratesEditor.getByRole('button', { name: 'Save figure', exact: true }))).click();
  await shown(ratesEditor.getByText('Saved Browser signed rates.', { exact: true }));
  record('Save failure leaves durable records intact and the same draft saves after storage recovers');

  await ratesEditor.getByRole('combobox', { name: 'Figure', exact: true }).selectOption('result:table');
  assert.equal(await ratesEditor.getByLabel('Start period', { exact: true }).isEnabled(), false);
  assert.equal(await ratesEditor.getByLabel('End period', { exact: true }).isEnabled(), false);
  await shown(ratesEditor.getByText(/Date filters are unavailable for this structured result/));
  await shown(ratesEditor.getByRole('link', { name: 'Export this view', exact: true }));
  await screenshot(page, 'structured-result-with-method', ratesEditor);
  record('Complete structured analytical result is accessible and its unsupported date filters are disabled/explained');

  await page.goto(`${seeded}/#portfolio`);
  const owner = page.getByRole('region', { name: 'Model portfolio scenarios', exact: true });
  await owner.getByLabel('Equities (%)', { exact: true }).fill('60');
  await owner.getByLabel('Bonds (%)', { exact: true }).fill('40');
  await owner.getByLabel('Gold (%)', { exact: true }).fill('0');
  await owner.getByLabel('Starting value (€)', { exact: true }).fill('123000');
  await owner.getByRole('button', { name: 'Save model scenario', exact: true }).click();
  await shown(owner.getByText('Saved. The model analyses now use this scenario.', { exact: true }));
  const ownerData = await json(page, `${seeded}/api/owner-inputs`);
  assert.equal(ownerData.start_value_eur, 123000);
  assert.equal(ownerData.is_example, false);
  assert.equal((await savedRows(page, seeded)).find(row => row.id === original.id).name, 'Browser tab A');
  await screenshot(page, 'owner-portfolio-saved', owner);
  record('Portfolio form saves a non-example60/40 allocation and preserves independent saved figures');

  // Actual instrument positions are independent of the broad model scenario.
  const holdings = page.getByRole('region', { name: 'ETF holdings', exact: true });
  await holdings.getByText('ETF holdings', { exact: true }).click();
  await holdings.getByText('Import a table', { exact: true }).click();
  await holdings.getByLabel('Holdings table', { exact: true }).fill('account\tname\tticker\tquantity\tprice_eur\tvalue_eur\tasset_class\nFixture A\tExample World ETF\tDEMO\t2\t50\t100\tequity\nFixture B\tExample Bond ETF\tBOND\t1\t25\t25\tbonds');
  await holdings.getByRole('button', { name: 'Add imported rows', exact: true }).click();
  await shown(holdings.getByLabel('Position 1 name', { exact: true }));
  await owner.getByLabel('Starting value (€)', { exact: true }).fill('141000');
  await navigate(page, 'Dashboard');
  await page.goBack();
  await holdings.getByText('ETF holdings', { exact: true }).click();
  await shown(holdings.getByLabel('Position 1 name', { exact: true }));
  assert.equal(await holdings.getByLabel('Position 1 name', { exact: true }).inputValue(), 'Example World ETF');
  assert.equal(await owner.getByLabel('Starting value (€)', { exact: true }).inputValue(), '141000');
  await owner.getByLabel('Starting value (€)', { exact: true }).fill('123000');
  assert.equal(await holdings.getByLabel('Position 1 identity', { exact: true }).inputValue(), 'unresolved');
  let releaseRequest;
  let submittedRequest;
  const requestSeen = new Promise(resolve => { releaseRequest = resolve; });
  const holdSave = route => {
    if (route.request().method() === 'PUT') { submittedRequest = route; releaseRequest(); return; }
    return route.continue();
  };
  await page.route('**/api/portfolio-holdings', holdSave);
  await holdings.getByRole('button', { name: 'Save holdings', exact: true }).click();
  await requestSeen;
  await holdings.getByLabel('Position 1 name', { exact: true }).fill('Newer unsaved browser edit');
  await submittedRequest.continue();
  await shown(holdings.getByText(/Newer edits remain unsaved/));
  assert.equal(await holdings.getByLabel('Position 1 name', { exact: true }).inputValue(), 'Newer unsaved browser edit');
  await page.unroute('**/api/portfolio-holdings', holdSave);
  await holdings.getByLabel('Position 1 name', { exact: true }).fill('Example World ETF');
  const holdingsData = await json(page, `${seeded}/api/portfolio-holdings`);
  assert.equal(holdingsData.positions.length, 2);
  assert.equal(holdingsData.as_of, null);
  assert.equal(holdingsData.monthly_contribution_eur, null);
  assert.equal(holdingsData.summary.total_value_eur, null, 'Separate accounts have no invented combined total');
  assert.deepEqual(await json(page, `${seeded}/api/owner-inputs`), ownerData, 'Holdings import must not change the model scenario');
  await screenshot(page, 'holdings-separate-accounts', holdings);

  const holdingsTab = await desktop.newPage();
  await holdingsTab.goto(`${seeded}/#portfolio`);
  const otherHoldings = holdingsTab.getByRole('region', { name: 'ETF holdings', exact: true });
  await otherHoldings.getByText('ETF holdings', { exact: true }).click();
  await shown(otherHoldings.getByLabel('Position 1 name', { exact: true }));
  await holdings.getByRole('checkbox', { name: 'Combine these accounts into one portfolio', exact: true }).check();
  await holdings.getByRole('button', { name: 'Save holdings', exact: true }).click();
  await poll(async () => (await json(page, `${seeded}/api/portfolio-holdings`)).summary.total_value_eur === 125, 'server aggregate after explicit combination');
  holdingsTab.__expectedStatuses = [409];
  await otherHoldings.getByLabel('Position 1 name', { exact: true }).fill('Conflicting fixture draft');
  await otherHoldings.getByRole('button', { name: 'Save holdings', exact: true }).click();
  await shown(otherHoldings.getByRole('alert'));
  assert.equal(await otherHoldings.getByLabel('Position 1 name', { exact: true }).inputValue(), 'Conflicting fixture draft');
  await otherHoldings.getByRole('button', { name: 'Reload holdings', exact: true }).click();
  await poll(async () => await otherHoldings.getByLabel('Position 1 name', { exact: true }).inputValue() === 'Example World ETF', 'holdings conflict reload');
  await holdingsTab.close();
  assert.deepEqual(await json(page, `${seeded}/api/owner-inputs`), ownerData);
  record('Actual holdings: table import, unknown dates/flows, separate accounts, explicit combination, revision conflict and model-store independence');
  await desktop.tracing.stop({ path: path.join(output, 'desktop-trace.zip') });
  await desktop.close();

  // Keyboard-only opening and narrow-screen legibility have distinct artifacts.
  const mobileContext = await context(seeded, { width: 390, height: 844 });
  const mobile = await mobileContext.newPage();
  await mobile.goto(seeded);
  await shown(mobile.getByRole('heading', { name: 'Dashboard', exact: true }));
  await mobile.getByText('Reading research findings…', { exact: true }).waitFor({ state: 'hidden' });
  await screenshot(mobile, 'mobile-overview-light');
  // The mobile toolbar deliberately hides Data & sync; it remains reachable through the one navigation menu.
  await mobile.getByRole('button', { name: 'Menu', exact: true }).click();
  const mobileSource = mobile.getByRole('link', { name: 'Source data', exact: true });
  const utilityBounds = await mobileSource.boundingBox();
  assert.ok(utilityBounds && utilityBounds.x >= 0 && utilityBounds.x + utilityBounds.width <= 390,
    'Source data and sync remain reachable from the mobile navigation without horizontal scrolling');
  await mobileSource.click();
  await shown(mobile.locator('#source-coverage > summary'));
  await mobile.goto(seeded);
  await mobile.keyboard.press('Tab');
  assert.equal(await mobile.getByRole('link', { name: 'Skip to content', exact: true }).evaluate(element => element === document.activeElement), true);
  await mobile.keyboard.press('Enter');
  assert.equal(await mobile.getByRole('main').evaluate(element => element === document.activeElement), true);
  for (const row of catalogue) {
    await mobile.goto(`${seeded}/#q-${row.analysis_id}`);
    await shown(mobile.locator(`#q-${row.analysis_id}`));
    assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Question ${row.analysis_id} fits390px`);
  }
  await mobile.goto(`${seeded}/#q-C01`);
  await shown(section(mobile, 'C01').getByRole('button', { name: 'Configure', exact: true }));
  const configure = section(mobile, 'C01').getByRole('button', { name: 'Configure', exact: true });
  let reached = false;
  for (let tabs = 0; tabs < 200; tabs += 1) {
    await mobile.keyboard.press('Tab');
    if (await configure.evaluate(element => element === document.activeElement)) { reached = true; break; }
  }
  assert.equal(reached, true, 'The figure Configure action is reachable using only Tab');
  await mobile.keyboard.press('Enter');
  const mobileEditor = section(mobile, 'C01').getByRole('region', { name: 'Configure C01' });
  await shown(mobileEditor.getByLabel('Figure name', { exact: true }));
  await mobile.keyboard.press('Tab');
  assert.equal(await mobileEditor.getByLabel('Figure name', { exact: true }).evaluate(element => element === document.activeElement), true);
  const focus = await mobileEditor.getByLabel('Figure name', { exact: true }).evaluate(element => {
    const style = getComputedStyle(element); return { outline: style.outlineStyle, width: style.outlineWidth, shadow: style.boxShadow };
  });
  assert.ok((focus.outline !== 'none' && focus.width !== '0px') || focus.shadow !== 'none', 'Keyboard focus has a visible indicator');
  await mobileEditor.evaluate(element => window.scrollTo({ left: 0, top: element.getBoundingClientRect().top + window.scrollY - 90, behavior: 'instant' }));
  await mobile.waitForTimeout(200);
  await mobileEditor.evaluate(element => window.scrollTo({ left: 0, top: element.getBoundingClientRect().top + window.scrollY - 90, behavior: 'instant' }));
  await screenshot(mobile, 'mobile-configure-keyboard-light');
  const overflow = await mobile.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth }));
  results.mobileOverflow = overflow;
  await mobile.getByRole('button', { name: 'Use dark appearance', exact: true }).click();
  await poll(async () => await mobile.locator('html').getAttribute('data-theme') === 'dark', 'mobile dark appearance');
  await mobileEditor.evaluate(element => window.scrollTo({ left: 0, top: element.getBoundingClientRect().top + window.scrollY - 90, behavior: 'instant' }));
  await mobile.waitForTimeout(200);
  await mobileEditor.evaluate(element => window.scrollTo({ left: 0, top: element.getBoundingClientRect().top + window.scrollY - 90, behavior: 'instant' }));
  await screenshot(mobile, 'mobile-dark');
  await mobile.goto(`${seeded}/#overview`);
  await screenshot(mobile, 'mobile-overview-dark');
  record('390px light/dark, keyboard editor activation/tab order and visible focus');
  await mobileContext.close();
  const tabletContext = await context(seeded, { width: 1024, height: 768 });
  const tablet = await tabletContext.newPage();
  await tablet.goto(`${seeded}/#q-C01`);
  await shown(tablet.locator('#q-C01'));
  assert.ok(await tablet.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await screenshot(tablet, 'tablet-selected-analysis');
  await tabletContext.close();

  // Controlled boundary failures: loading retries, permanent failure, lost connection.
  for (const failure of ['loading', 'evaluation', 'connection']) {
    const faultContext = await context(seeded);
    const fault = await faultContext.newPage();
    fault.__expectedStatuses = [503];
    fault.__expectedConnection = failure === 'connection';
    let count = 0;
    await fault.route('**/api/analysis/C01', route => {
      count += 1;
      if (failure === 'loading' && count > 1) return route.continue();
      if (failure === 'connection') return route.abort('connectionrefused');
      return route.fulfill({ status: 503, contentType: 'application/json',
        headers: failure === 'loading' ? { 'Retry-After': '1' } : {},
        body: JSON.stringify({ detail: failure === 'loading' ? 'Phase 2 acceptance evaluation in progress' : 'Phase 2 acceptance evaluation unavailable' }) });
    });
    await fault.goto(seeded);
    if (failure === 'loading') {
      await shown(fault.getByText(/being reassessed; this page retries automatically/).first());
      await shown(fault.locator('#dashboard-growth .dashboard-summary').first());
      assert.ok(count >= 2);
    } else {
      await shown(fault.getByText(/Some research findings could not be read/).first());
      const atFailure = count;
      await fault.waitForTimeout(1200);
      assert.equal(count, atFailure, 'Permanent failure must not spin a reload/retry loop');
    }
    await screenshot(fault, `failure-${failure}`);
    record(`Controlled ${failure} failure: visible explanation${failure === 'loading' ? ' and automatic recovery' : ', no retry loop'}`);
    await faultContext.close();
  }
  assert.ok(results.mobileOverflow.document <= results.mobileOverflow.width + 1,
    `Page overflows narrow viewport: ${JSON.stringify(results.mobileOverflow)}`);
  record('No whole-page horizontal overflow at390px');
  assert.deepEqual(results.errors, [], 'Unexpected browser errors');
  results.passed = true;
  console.log(JSON.stringify({ passed: true, checks: results.checks, output }, null, 2));
} catch (error) {
  results.passed = false;
  results.failure = error.stack ?? String(error);
  console.error(results.failure);
  process.exitCode = 1;
  if (browser) {
    let index = 0;
    for (const currentContext of browser.contexts()) for (const currentPage of currentContext.pages()) {
      await screenshot(currentPage, `failure-page-${index++}`).catch(() => {});
      await writeFile(path.join(output, `failure-page-${index}-aria.yml`), await currentPage.locator('body').ariaSnapshot()).catch(() => {});
    }
  }
} finally {
  if (browser) await browser.close();
  for (const process of processes) {
    if (process.exitCode === null) {
      process.kill('SIGTERM');
      await Promise.race([once(process, 'exit'), new Promise(resolve => setTimeout(resolve, 5000))]);
      if (process.exitCode === null) process.kill('SIGKILL');
    }
  }
  results.finishedAt = new Date().toISOString();
  await writeFile(path.join(output, 'browser-smoke-report.json'), JSON.stringify(results, null, 2) + '\n');
}
