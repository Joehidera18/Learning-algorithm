/* Local fixture tests: no stock feeds, brokerage calls, or real account files. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON || 'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,STRATEGY_LAB_UI_FIXTURES:'1',COINBASE_ALLOW_LIVE:'0',COINBASE_KEY_FILE:'',
    ALPACA_API_KEY:'',ALPACA_SECRET_KEY:'',APCA_API_KEY_ID:'',APCA_API_SECRET_KEY:'',MASSIVE_API_KEY:'',OPENAI_API_KEY:''},
  stdio:['ignore','pipe','pipe']});
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
  const page=await browser.newPage({viewport:{width:1200,height:1000}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/backtests');
  await check('Lab requires the access token and loads all registered strategies',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#strategy option').count(),5);
    assert.equal(await page.locator('#jobs .equity-job').count(),3);
    assert.equal(await page.locator('#provider option[value="massive"]').evaluate(e=>e.disabled),true);
  });
  await check('Incomplete and legacy reports do not display a passing result',async()=>{
    const text=await page.locator('#jobs').innerText();
    assert.match(text,/Candles went missing/);assert.match(text,/rerun with the corrected backtester/);
    assert.match(text,/Incomplete comparison/);
    assert.match(text,/Did not pass the historical screen|Too few resolved trades/);
    assert.doesNotMatch(text,/\$99\.00|Passed the historical screen/);
  });
  await check('ORB excludes decision bars too large to form its opening range',async()=>{
    assert.equal(await page.locator('#decision option').filter({hasText:/^1h$/}).evaluate(e=>e.disabled),true);
    await page.locator('#strategy').selectOption('trend_pullback_simple');
    await page.locator('#decision').selectOption('1h');
    await page.locator('#mode').selectOption('swing');
    await page.locator('#strategy').selectOption('orb_15m');
    assert.equal(await page.locator('#mode').inputValue(),'day');
    assert.equal(await page.locator('#news option[value="yes"]').evaluate(e=>e.disabled),true);
    assert.equal(await page.locator('#decision').inputValue(),'5m');
  });
  await check('Authorized submission reaches the persisted queue',async()=>{
    const request=page.waitForRequest(r=>r.url().endsWith('/api/strategy-lab/start') && r.method()==='POST');
    await page.locator('#balance').fill('1500');
    await page.locator('#fractional').selectOption('no');
    await page.locator('#runButton').click();const sent=await request;
    assert.equal(sent.headers().authorization,'Bearer stock-ui-test-token');
    assert.equal(sent.postDataJSON().strategy,'orb_15m');
    assert.equal(sent.postDataJSON().starting_balance,1500);
    assert.equal(sent.postDataJSON().fractional_shares,false);
    assert.equal(sent.postDataJSON().context,'');
    assert.equal(sent.postDataJSON().settings.risk_per_trade,.005);
    await page.waitForFunction(()=>document.querySelectorAll('#jobs .equity-job').length===4);
  });
  await check('Completed reports show later metrics and load their journal only on demand',async()=>{
    const job=page.locator('#jobs .equity-job').filter({hasText:'Trend pullback'}).first();
    assert.equal(await job.locator('.backtest-metrics strong').count(),4);
    assert.equal(await job.locator('[data-journal] tbody tr').count(),0);
    // Re-render the job list while a slow journal request is still in flight.
    let release;
    const gate=new Promise(resolve=>{release=resolve;});
    await page.route('**/api/strategy-lab/report?id=*',async route=>{await gate;await route.continue();});
    const response=page.waitForResponse(r=>r.url().includes('/api/strategy-lab/report?id='));
    await job.locator('[data-action="journal"]').click();
    await page.route('**/api/strategy-lab/status',async route=>{
      const response=await route.fetch(),value=await response.json();
      value.jobs[0].message='Journal still loading during refresh';await route.fulfill({json:value});
    });
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.getElementById('jobs').textContent.includes('Journal still loading during refresh'));
    release();
    const report=await (await response).json();
    await page.unroute('**/api/strategy-lab/status');
    await page.unroute('**/api/strategy-lab/report?id=*');
    assert.ok(report.trade_journal.later.length>0);
    await job.locator('[data-journal] tbody tr').first().waitFor();
    assert.equal(await job.locator('[data-journal] tbody tr').count(),Math.min(100,report.trade_journal.later.length));
    await job.locator('[data-journal-window]').selectOption('development');
    assert.equal(await job.locator('[data-journal] tbody tr').count(),Math.min(100,report.trade_journal.development.length));
    const event=page.waitForEvent('download');await job.locator('[data-action="export"]').click();
    const file=await event,data=JSON.parse(await fs.readFile(await file.path(),'utf8'));
    assert.equal(data.report_version,3);
    assert.deepEqual(data.trade_journal,report.trade_journal);
    await page.locator('#refresh').click();
    assert.equal(await job.locator('[data-journal-window]').inputValue(),'development');
  });
  await check('Queued backtests can be cancelled without removing completed reports',async()=>{
    await page.locator('[data-action="cancel"]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-action="cancel"]'));
    assert.equal(await page.locator('#jobs .equity-job').count(),4);
    assert.match(await page.locator('#jobs').innerText(),/Cancelled by user/);
  });
  await check('A stalled request times out and the next request succeeds',async()=>{
    await page.route('**/api/health?slow-fixture=1',()=>{});
    const message=await page.evaluate(async()=>{
      try {await StockSession.request('/api/health?slow-fixture=1',{},'json',50);return 'unexpected success';}
      catch(error) {return error.message;}
    });
    assert.match(message,/timed out/);
    await page.unroute('**/api/health?slow-fixture=1');
    assert.equal(await page.evaluate(async()=>(await StockSession.request('/api/health')).ok),true);
  });
  await check('Hostile saved messages are rendered as inert text',async()=>{
    await page.route('**/api/strategy-lab/status',async route=>{
      const response=await route.fetch(),value=await response.json();
      value.jobs[0].message='<img src=x onerror=alert(1)> & "test"';await route.fulfill({json:value});
    });
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.getElementById('jobs').textContent.includes('<img'));
    assert.equal(await page.locator('#jobs img').count(),0);
    await page.unroute('**/api/strategy-lab/status');
  });
  await check('Unavailable lab produces a readable error',async()=>{
    await page.route('**/api/strategy-lab/status',route=>route.fulfill({json:{error:'Fixture lab unavailable'}}));
    await page.locator('#refresh').click();
    await page.waitForFunction(()=>document.getElementById('notice').textContent==='Fixture lab unavailable');
    await page.unroute('**/api/strategy-lab/status');
    await page.locator('#refresh').click();
  });
  await check('Phone layout fits without horizontal overflow',async()=>{
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await fs.mkdir('/tmp/stock-backtests-ui',{recursive:true});
    await page.screenshot({path:'/tmp/stock-backtests-ui/mobile.png',fullPage:true});
    await page.setViewportSize({width:1200,height:1000});
    await page.screenshot({path:'/tmp/stock-backtests-ui/desktop.png',fullPage:true});
  });
  assert.equal(errors.length,0,errors.join('\n'));console.log(checks+' strategy lab browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
