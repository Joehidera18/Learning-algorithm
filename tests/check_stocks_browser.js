/* Run with Node + Playwright installed, and python3 available. No network feeds. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const server = spawn(process.env.STOCK_UI_PYTHON || 'python3', ['-m', 'tests.serve_stock_ui'], {
  cwd: root, env: {...process.env, COINBASE_ALLOW_LIVE: '0', COINBASE_KEY_FILE: ''}, stdio: ['ignore', 'pipe', 'pipe']
});
let browser;
let checks = 0;
const problems = [];
const count = async (page, expected) => {
  await page.waitForFunction(n => document.querySelectorAll('#stockGrid .stock-card').length === n, expected);
  assert.equal(await page.locator('#stockGrid .stock-card').count(), expected);
};
const hasText = async (locator, expected) => assert.match(await locator.textContent(), expected);
const check = async (name, run) => { await run(); checks += 1; console.log(`PASS ${name}`); };

(async () => {
  const base = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Local test server did not start')), 15000);
    let output = '';
    server.stdout.on('data', chunk => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    server.stderr.on('data', chunk => problems.push(String(chunk)));
    server.on('error', reject);
    server.on('exit', code => { clearTimeout(timer); if (!output) reject(new Error(`Local server exited ${code}: ${problems.join('')}`)); });
  });
  const artifacts = process.env.STOCK_UI_ARTIFACTS || path.join(os.tmpdir(), 'stock-research-ui');
  await fs.mkdir(artifacts, {recursive: true});
  const launchOptions = {headless: true};
  if (process.env.STOCK_UI_BUNDLED_CHROMIUM === '1') {
    const packageModule = require('@sparticuz/chromium');
    const bundled = packageModule.default || packageModule;
    launchOptions.executablePath = await bundled.executablePath();
    launchOptions.args = bundled.args.filter(arg => !['--disable-web-security', '--allow-running-insecure-content', '--disable-site-isolation-trials'].includes(arg));
  }
  browser = await chromium.launch(launchOptions);
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
  const stubMarkets = async target => target.route('https://www.tradingview-widget.com/embed-widget/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><html><body style="background:#101a24;color:#b8c8d1;font:14px Arial;padding:20px">Market provider fixture · no real quotes</body></html>'
  }));
  await stubMarkets(context);
  const page = await context.newPage();
  page.on('pageerror', error => problems.push(error.message));
  const requests = [];
  page.on('request', request => requests.push({url: request.url(), method: request.method()}));
  await page.goto(`${base}/stocks`);

  await check('Existing app token protects research and connects through the page', async () => {
    await page.locator('#stockAccessPanel').waitFor({state: 'visible'});
    await page.locator('#stockAccessToken').fill('wrong');
    await page.locator('#stockAccessForm button').click();
    await page.waitForFunction(() => !document.getElementById('reloadResearch').disabled);
    assert.equal(await page.locator('#stockContent').isVisible(), false);
    await page.locator('#stockAccessToken').fill('stock-ui-test-token');
    await page.locator('#stockAccessForm button').click();
    await count(page, 20);
    assert.equal(await page.locator('#stockAccessPanel').isVisible(), false);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('cryptoAccessToken')), 'stock-ui-test-token');
    assert.equal(await page.evaluate(() => localStorage.getItem('cryptoAccessToken')), null);
  });
  await check('All profiles, focus companies, original candidates and valuation context render', async () => {
    assert.equal(await page.locator('#focusStocks a').count(), 5);
    assert.equal(await page.locator('#earlierStocks > div').count(), 5);
    assert.equal(await page.locator('#valuationRows tr').count(), 8);
    assert.equal(await page.locator('#catalystList .catalyst-row').count(), 6);
    await hasText(page.locator('#researchFreshness'), /Sep 20, 2026/);
    await hasText(page.locator('#valuationDate'), /Sep 18, 2026/);
    await page.screenshot({path: path.join(artifacts, 'stocks-desktop.png')});
  });
  await check('The market board contains all 20 mapped stocks and shows data-delay context', async () => {
    const source = new URL(await page.locator('#marketBoard iframe').getAttribute('src'));
    assert.equal(source.origin, 'https://www.tradingview-widget.com');
    const settings = JSON.parse(decodeURIComponent(source.hash.slice(1)));
    const symbols = settings.tabs[0].symbols.map(s => s.s);
    assert.equal(symbols.length, 20);
    assert.equal(new Set(symbols).size, 20);
    assert.ok(symbols.includes('NASDAQ:VRTX') && symbols.includes('NYSE:IONQ'));
    assert.equal(await page.locator('#marketSymbol option').count(), 20);
    await hasText(page.locator('#marketDataNote'), /delayed/);
    assert.ok(!source.href.includes('stock-ui-test-token'));
    assert.equal(await page.locator('#markets script[src]').count(), 0);
    assert.equal(settings.hideAbsoluteChange, true);
    await page.locator('[data-market-view="full"]').click();
    const full = new URL(await page.locator('#marketBoard iframe').getAttribute('src'));
    assert.ok(full.pathname.includes('market-quotes'));
    assert.equal(JSON.parse(decodeURIComponent(full.hash.slice(1))).symbolsGroups[0].symbols.length, 20);
    await page.locator('[data-market-view="summary"]').click();
  });
  await check('Charts switch stocks, preserve dollar and percentage settings, and link back to research', async () => {
    await page.locator('#marketSymbol').selectOption('IONQ');
    let source = new URL(await page.locator('#marketChart iframe').getAttribute('src'));
    let settings = JSON.parse(decodeURIComponent(source.hash.slice(1)));
    assert.equal(settings.symbols[0][1], 'NYSE:IONQ|1D');
    assert.equal(settings.changeMode, 'price-and-percent');
    assert.equal(settings.showVolume, true);
    assert.equal(settings.hideMarketStatus, false);
    await page.locator('#marketResearchLink').click();
    await hasText(page.locator('#detailTitle'), /IONQ/);
    await page.locator('[data-chart-stock="IONQ"]').click();
    await page.locator('#stockDetail').waitFor({state: 'hidden'});
    assert.equal(await page.locator('#marketSymbol').inputValue(), 'IONQ');
    await page.locator('#marketChart iframe').evaluate(frame => frame.dataset.preserved = 'true');
    await page.locator('#reloadResearch').click();
    await page.waitForFunction(() => !document.getElementById('reloadResearch').disabled);
    assert.equal(await page.locator('#marketChart iframe').getAttribute('data-preserved'), 'true');
    await page.locator('#reloadMarkets').click();
    assert.equal(await page.locator('#marketChart iframe').getAttribute('data-preserved'), null);
    assert.equal(await page.locator('#marketSymbol').inputValue(), 'IONQ');
  });
  await check('Offline state warns about stale quotes without replacing them with dated research values', async () => {
    await context.setOffline(true);
    await page.waitForFunction(() => document.getElementById('marketConnectionStatus').textContent.includes('offline'));
    assert.equal(await page.locator('#markets iframe').count(), 2);
    assert.equal(await page.locator('#markets').getByText('$249.39', {exact: true}).count(), 0);
    await context.setOffline(false);
    await page.waitForFunction(() => document.getElementById('marketConnectionStatus').textContent.includes('Updates supplied'));
  });
  await check('Search, theme, profile and focus filters combine and reset', async () => {
    await page.locator('#stockSector').selectOption('Biotech'); await count(page, 7);
    await page.locator('#stockExposure').selectOption('speculative'); await count(page, 3);
    await page.locator('#stockSearch').fill('beam'); await count(page, 1);
    await page.locator('#stockSearch').fill('HBAR'); await count(page, 0);
    assert.equal(await page.locator('#stockEmpty').isVisible(), true);
    await page.locator('#emptyClearFilters').click(); await count(page, 20);
    await page.locator('[data-stock-view="focus"]').click(); await count(page, 5);
    await page.locator('#stockSort').selectOption('ticker');
    assert.equal(await page.locator('.stock-card').first().getAttribute('data-ticker'), 'ALNY');
    await page.locator('#clearStockFilters').click(); await count(page, 20);
  });
  await check('Saved watchlist survives reload and handles removing the last item', async () => {
    await page.locator('#stockGrid [data-save-stock="BEAM"]').click();
    await page.locator('[data-stock-view="saved"]').click(); await count(page, 1);
    await page.reload(); await count(page, 20);
    await hasText(page.locator('#savedCount'), /1/);
    await page.locator('[data-stock-view="saved"]').click(); await count(page, 1);
    await page.locator('#stockGrid [data-save-stock="BEAM"]').click(); await count(page, 0);
    assert.equal(await page.locator('#stockSearch').evaluate(el => document.activeElement === el), true);
    await page.locator('#emptyClearFilters').click();
  });
  await check('Company details show the full thesis and support links and keyboard close', async () => {
    await page.locator('#focusStocks [data-open-stock="BEAM"]').click();
    assert.equal(await page.locator('#stockDetail').isVisible(), true);
    await hasText(page.locator('#stockDetailBody'), /Speculative/);
    assert.ok(await page.locator('#stockDetailBody .detail-block').count() >= 4);
    assert.ok(await page.locator('#stockDetailBody a[rel="noopener noreferrer"]').count() > 1);
    assert.equal(new URL(page.url()).hash, '#BEAM');
    await page.screenshot({path: path.join(artifacts, 'stocks-detail.png')});
    await page.keyboard.press('Escape');
    await page.locator('#stockDetail').waitFor({state: 'hidden'});
    await page.goto(`${base}/stocks#VRTX`);
    await page.locator('#stockDetail').waitFor({state: 'visible'});
    await hasText(page.locator('#detailTitle'), /VRTX/);
    await page.locator('#closeStockDetail').click();
  });
  await check('Report and machine-readable catalog downloads contain the research', async () => {
    for (const [id, extension] of [['downloadReport', '.md'], ['downloadWatchlist', '.json']]) {
      const pending = page.waitForEvent('download');
      await page.locator(`#${id}`).click();
      const download = await pending;
      assert.ok(download.suggestedFilename().endsWith(extension));
      const file = path.join(artifacts, download.suggestedFilename());
      await download.saveAs(file);
      const content = await fs.readFile(file, 'utf8');
      assert.ok(content.includes('VRTX') && content.includes('TWST'));
      if (extension === '.json') assert.equal(JSON.parse(content).stocks.length, 20);
    }
  });
  await check('Failed reload preserves the loaded research and shows the failure', async () => {
    await page.route('**/api/stocks/research', route => route.fulfill({status: 503, body: '{}', contentType: 'application/json'}));
    await page.locator('#reloadResearch').click();
    await page.waitForFunction(() => !document.getElementById('stockNotice').hidden);
    await hasText(page.locator('#stockNotice'), /previously loaded/);
    await count(page, 20);
    await page.unroute('**/api/stocks/research');
  });
  await check('Review-due and past catalyst dates remain visibly unverified', async () => {
    const data = await (await context.request.get(`${base}/api/stocks/research`, {headers: {Authorization: 'Bearer stock-ui-test-token'}})).json();
    data.review.status = 'review_due';
    data.stocks[0].catalyst.calendar_status = 'review_needed';
    await page.route('**/api/stocks/research', route => route.fulfill({json: data}));
    await page.locator('#reloadResearch').click();
    await page.waitForFunction(() => document.getElementById('researchFreshness').textContent.includes('Review due'));
    await hasText(page.locator('#catalystList'), /Date passed · review outcome/);
    await page.unroute('**/api/stocks/research');
  });
  await check('Research text and source URLs cannot inject executable markup', async () => {
    const data = await (await context.request.get(`${base}/api/stocks/research`, {headers: {Authorization: 'Bearer stock-ui-test-token'}})).json();
    data.stocks[0].summary = '<img src=x onerror="window.injected=true">';
    data.stocks[0].sources.push({title: 'Unsafe source', url: 'javascript:window.injected=true'});
    await page.route('**/api/stocks/research', route => route.fulfill({json: data}));
    await page.locator('#reloadResearch').click();
    await page.waitForFunction(() => document.getElementById('stockGrid').textContent.includes('<img'));
    await page.locator('#focusStocks [data-open-stock="VRTX"]').click();
    assert.equal(await page.locator('#stockDetail img, #stockGrid img, a[href^="javascript:"]').count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
    await page.locator('#closeStockDetail').click();
    await page.unroute('**/api/stocks/research');
  });
  await check('Mobile page and detail fit the viewport; favorites work when storage is blocked', async () => {
    const mobile = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, deviceScaleFactor: 1, hasTouch: true});
    await stubMarkets(mobile);
    await mobile.addInitScript(() => {
      if (location.protocol === 'http:') sessionStorage.setItem('cryptoAccessToken', 'stock-ui-test-token');
      Object.defineProperty(window, 'localStorage', {get() { throw new Error('Storage disabled'); }});
    });
    const phone = await mobile.newPage();
    phone.on('pageerror', error => problems.push(error.message));
    await phone.goto(`${base}/stocks`); await count(phone, 20);
    assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.equal(await phone.locator('#markets iframe').count(), 2);
    const marketBox = await phone.locator('#marketBoard iframe').boundingBox();
    assert.ok(marketBox.width <= 390 && marketBox.x >= 0);
    await hasText(phone.locator('#savedScope'), /browser storage is unavailable/);
    await phone.screenshot({path: path.join(artifacts, 'stocks-mobile.png')});
    await phone.locator('#stockGrid [data-save-stock="BEAM"]').click();
    await phone.locator('[data-stock-view="saved"]').click(); await count(phone, 1);
    await phone.locator('#stockGrid [data-open-stock="BEAM"]').click();
    const box = await phone.locator('#stockDetail').boundingBox();
    assert.ok(box.width <= 390 && box.x >= 0);
    await phone.screenshot({path: path.join(artifacts, 'stocks-mobile-detail.png')});
    // Leave both contexts open until browser.close() for single-process builds.
  });
  await check('Stock browsing makes no state-changing API calls and crypto navigation still works', async () => {
    assert.ok(requests.every(request => request.method === 'GET'));
    assert.ok(requests.filter(request => request.url.includes('/api/')).every(request => request.url.includes('/api/stocks/')));
    await page.locator('.market-nav a[href="/"]').click();
    await page.waitForURL(base + '/');
    assert.equal(await page.locator('.market-nav a[href="/stocks"]').count(), 1);
    await hasText(page.locator('body'), /Trade finances/);
  });
  assert.deepEqual(problems, []);
  console.log(`${checks} browser checks passed. Screenshots: ${artifacts}`);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  server.kill('SIGINT');
});
