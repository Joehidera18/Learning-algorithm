/* Browser checks use generated fixtures and never contact a stock feed or broker. */
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON || 'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,EQUITY_UI_FIXTURES:'1',COINBASE_ALLOW_LIVE:'0',COINBASE_KEY_FILE:'',OPENAI_API_KEY:''},stdio:['ignore','pipe','pipe']});
let browser,checks=0;const errors=[];
const check=async(name,run)=>{await run();checks++;console.log('PASS '+name);};
(async()=>{
  const base=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Test server timeout '+errors.join(''))),20000);
    server.stdout.on('data',c=>{output+=c;const m=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.stderr.on('data',c=>errors.push(String(c)));server.on('error',reject);
  });
  const options={headless:true};
  if(process.env.STOCK_UI_BUNDLED_CHROMIUM==='1'){
    const imported=require('@sparticuz/chromium'),bundled=imported.default || imported;
    options.executablePath=await bundled.executablePath();
    options.args=bundled.args.filter(a=>!['--disable-web-security','--allow-running-insecure-content','--disable-site-isolation-trials'].includes(a));
  }
  browser=await chromium.launch(options);
  const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/stock-practice');
  await check('Protected stock practice loads eight timeframes and 26 presets',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#interval option').count(),8);
    assert.equal(await page.locator('#tickerList option').count(),26);
    assert.match(await page.locator('#marketClock').innerText(),/REGULAR SESSION/);
  });
  await check('Six actual fixture comparisons and their evidence limits are visible',async()=>{
    await page.locator('details[data-job] summary').first().click();
    await page.waitForFunction(()=>document.querySelectorAll('.result-table tbody tr').length===6);
    assert.match(await page.locator('#jobs').innerText(),/resolved learning examples/);
    assert.match(await page.locator('#jobs').innerText(),/insufficient evidence/);
    assert.match(await page.locator('#jobs').innerText(),/buy & hold/);
  });
  await check('Source limits, daily mode and unavailable credentials change the controls',async()=>{
    await page.locator('#interval').selectOption('1m');assert.equal(await page.locator('#days').getAttribute('max'),'29');
    await page.locator('#interval').selectOption('1d');assert.equal(await page.locator('#mode').inputValue(),'swing');
    assert.equal(await page.locator('#mode option[value="day"]').evaluate(e=>e.disabled),true);
    assert.equal(await page.locator('#provider option[value="alpaca"]').evaluate(e=>e.disabled),true);
    await page.locator('#provider').selectOption('yahoo');await page.locator('#interval').selectOption('1h');
  });
  await check('Queue and cancellation use the stock-only API',async()=>{
    await page.locator('#symbol').fill('NVDA');await page.locator('#runButton').click();
    await page.waitForFunction(()=>document.getElementById('jobCount').textContent==='2 RUNS');
    await page.locator('button[data-action="cancel"]').click();
    await page.locator('button[data-action="retry"]').waitFor();
    await page.locator('button[data-action="retry"]').click();await page.locator('button[data-action="cancel"]').waitFor();
  });
  await check('Full results and source candles download with saved provenance',async()=>{
    const event=page.waitForEvent('download');await page.locator('button[data-action="export"]').click();
    const file=await event,data=JSON.parse(await fs.readFile(await file.path(),'utf8'));
    assert.equal(data.result.asset_class,'equity');assert.equal(data.result.validated,false);assert.ok(data.result.model);
    const second=page.waitForEvent('download');await page.locator('button[data-action="candles"]').click();
    const source=JSON.parse(await fs.readFile(await (await second).path(),'utf8'));
    assert.ok(source.rows.length>500);assert.equal(source.market_data.provider,'test_fixture');
  });
  await check('Forward practice registers after the run and can be stopped',async()=>{
    await page.locator('button[data-action="forward/start"]').click();
    await page.locator('button[data-action="forward/stop"]').waitFor();
    assert.match(await page.locator('#forwardAccounts').innerText(),/Waiting for a signal candle/);
    await page.locator('button[data-action="forward/stop"]').click();
    await page.waitForFunction(()=>document.getElementById('forwardAccounts').textContent.includes('Stopped.'));
  });
  await check('Desktop and phone layouts fit the screen and preserve readable results',async()=>{
    const out='/tmp/equity-ui';await fs.mkdir(out,{recursive:true});
    await page.screenshot({path:out+'/stock-practice-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:out+'/stock-practice-mobile.png',fullPage:true});
  });
  await check('Provider failures and hostile text are rendered as inert text',async()=>{
    await page.route('**/api/stocks/practice/status',async route=>{
      const response=await route.fetch(),v=await response.json();v.jobs[0].progress.message='<img src=x onerror=alert(1)>';await route.fulfill({json:v});
    });
    await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('jobs').textContent.includes('<img'));
    assert.equal(await page.locator('#jobs img').count(),0);
  });
  assert.equal(errors.length,0,errors.join('\n'));console.log(checks+' equity browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
