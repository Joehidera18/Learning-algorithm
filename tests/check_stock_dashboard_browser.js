/* Integration fixtures: no live stock feed, brokerage or private account. */
'use strict';
const assert = require('node:assert/strict'), path = require('node:path'), fs = require('node:fs/promises');
const {spawn} = require('node:child_process'), {chromium} = require('playwright');
const server = spawn(process.env.STOCK_UI_PYTHON || 'python3', ['-m','tests.serve_stock_ui'], {
  cwd:path.resolve(__dirname,'..'), env:{...process.env, STOCK_DASHBOARD_UI_FIXTURES:'1',
    ALPACA_API_KEY:'', ALPACA_SECRET_KEY:'', APCA_API_KEY_ID:'', APCA_API_SECRET_KEY:'', MASSIVE_API_KEY:''},
  stdio:['ignore','pipe','pipe']
});
let browser, checks = 0; const errors = [];
const check = async (name, action) => { await action(); checks++; console.log('PASS '+name); };
(async () => {
  const base = await new Promise((resolve,reject) => {
    let output=''; const timer=setTimeout(()=>reject(Error('Fixture server timeout '+errors.join(''))),20000);
    server.stdout.on('data', c=>{output+=c; const match=output.match(/http:\/\/127\.0\.0\.1:\d+/); if(match){clearTimeout(timer);resolve(match[0]);}});
    server.stderr.on('data', c=>errors.push(String(c))); server.on('error',reject);
  });
  const options={headless:true};
  if(process.env.STOCK_UI_BUNDLED_CHROMIUM==='1') {
    const module=require('@sparticuz/chromium'), bundled=module.default || module;
    options.executablePath=await bundled.executablePath();
    options.args=bundled.args.filter(a=>!['--disable-web-security','--allow-running-insecure-content','--disable-site-isolation-trials'].includes(a));
  }
  browser=await chromium.launch(options);
  const context=await browser.newContext({viewport:{width:1440,height:1080},acceptDownloads:true});
  await context.route('**/*', route=>route.request().url().startsWith(base) ? route.continue() :
    route.fulfill({contentType:'text/html',body:'<html><body style="background:#101a24;color:#9dacbc;font:16px system-ui;padding:32px">External market display replaced by a test fixture. No market prices are fabricated.</body></html>'}));
  const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await check('Stock dashboard is protected and preserves the existing login',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.evaluate(()=>sessionStorage.setItem('cryptoAccessToken','stock-ui-test-token'));
    await page.reload(); await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#marketSymbol option').count(),26);
    assert.equal(await page.locator('#researchCount').innerText(),'20');
    assert.equal(await page.locator('#runCount').innerText(),'1');
    assert.doesNotMatch(await page.locator('nav.market-nav').innerText(),/Crypto|Experiments/);
  });
  await check('Chart selection changes stock, timeframe and stock workflow links',async()=>{
    await page.locator('#marketSymbol').selectOption('NVDA');
    await page.locator('#chartPeriod').selectOption('240');
    const source=await page.locator('#marketChart iframe').getAttribute('src');
    const url=new URL(source), settings=JSON.parse(decodeURIComponent(url.hash.slice(1)));
    assert.equal(url.hostname,'www.tradingview-widget.com');
    assert.equal(settings.symbols[0][1],'NASDAQ:NVDA|240');
    assert.ok(!source.includes('stock-ui-test-token'));
    assert.equal(await page.locator('#learnLink').getAttribute('href'),'/stock-practice?symbol=NVDA');
    assert.equal(await page.locator('#researchLink').getAttribute('href'),'/stocks#NVDA');
  });
  await check('Dashboard actions prefill both stock forms',async()=>{
    await page.locator('#learnLink').click();await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#symbol').inputValue(),'NVDA');
    await page.goto(base+'/strategy-lab?symbol=NVDA');await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#symbol').inputValue(),'NVDA');
    await page.goto(base+'/stock-practice');await page.locator('#content').waitFor({state:'visible'});
    await page.locator('button[data-action="forward/start"]').click();
    await page.locator('button[data-action="forward/stop"]').waitFor();
    await page.goto(base);await page.locator('#paperContent').waitFor({state:'visible'});
  });
  await check('Unobserved account equity stays unknown rather than becoming a fake balance',async()=>{
    assert.match(await page.locator('#accountMessage').innerText(),/Waiting for a signal candle/);
    assert.equal(await page.locator('#accountFacts strong').first().innerText(),'—');
    assert.doesNotMatch(await page.locator('#accountFacts').innerText(),/\$500/);
    assert.equal(await page.locator('#forwardCount').innerText(),'1');
  });
  await check('Account figures use the selected journal and suppress incomplete profit',async()=>{
    let complete=true;
    await page.route('**/api/stocks/overview',async route=>{
      const response=await route.fetch(),value=await response.json();
      value.forward[0].account={closed_trades:3,model_updates:17,metrics:{complete,ending_balance:512.34,net_pnl:12.34,as_of_ts:1790083800000,open_position:null}};
      value.forward[0].message='<img src=x onerror=alert(1)> journal fixture';
      await route.fulfill({json:value});
    });
    await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('accountFacts').textContent.includes('$512.34'));
    assert.match(await page.locator('#accountFacts').innerText(),/\$12.34/);
    assert.equal(await page.locator('#accountMessage img').count(),0);
    complete=false;await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.getElementById('position').textContent.includes('incomplete'));
    assert.doesNotMatch(await page.locator('#accountFacts').innerText(),/\$512|\$12/);
    await page.unroute('**/api/stocks/overview');
  });
  await check('Stop and journal export operate on saved stock accounts',async()=>{
    await page.locator('#stopAccount').click();
    await page.waitForFunction(()=>document.getElementById('accountMessage').textContent.startsWith('STOPPED'));
    assert.equal(await page.locator('#stopAccount').isVisible(),false);
    const event=page.waitForEvent('download');await page.locator('#exportJournal').click();
    const file=await event, data=JSON.parse(await fs.readFile(await file.path(),'utf8'));
    assert.equal(data.length,1);assert.equal(data[0].symbol,'SPY');assert.equal(data[0].status,'stopped');
  });
  await check('Dashboard fits desktop and phone viewports',async()=>{
    await fs.mkdir('/tmp/stock-dashboard-ui',{recursive:true});
    await page.screenshot({path:'/tmp/stock-dashboard-ui/desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:'/tmp/stock-dashboard-ui/mobile.png',fullPage:true});
    await page.setViewportSize({width:1440,height:1080});
  });
  await check('Offline and expired access cannot masquerade as current results',async()=>{
    await page.route('**/api/stocks/overview',route=>route.fulfill({status:503,json:{error:'Fixture data outage'}}));
    await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('connection').classList.contains('stale'));
    assert.match(await page.locator('#notice').innerText(),/Fixture data outage/);
    await page.unroute('**/api/stocks/overview');
    await page.route('**/api/stocks/overview',route=>route.fulfill({status:401,json:{error:'Token expired'}}));
    await page.locator('#refresh').click();await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.unroute('**/api/stocks/overview');
  });
  await check('Research remains connected to stock learning and existing saved favorites',async()=>{
    await page.evaluate(()=>localStorage.setItem('cryptoStockFavorites.v1',JSON.stringify(['NVDA'])));
    await page.goto(base+'/stocks#NVDA');await page.locator('#stockDetail').waitFor({state:'visible'});
    assert.equal(await page.locator('#stockGrid .stock-card').count(),20);
    assert.equal(await page.locator('#savedCount').innerText(),'1');
    assert.equal(await page.locator('#stockDetailBody a[href="/stock-practice?symbol=NVDA"]').count(),1);
  });
  assert.equal(errors.length,0,errors.join('\n'));
  console.log(checks+' stock dashboard browser checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
