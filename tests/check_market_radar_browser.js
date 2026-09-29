/* End-to-end HTTP/UI checks with generated evidence and no external provider calls. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON||'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,RADAR_UI_FIXTURES:'1',AGENT_UI_FIXTURES:'1',OPENAI_API_KEY:'',
    ALPACA_API_KEY:'',ALPACA_SECRET_KEY:'',APCA_API_KEY_ID:'',APCA_API_SECRET_KEY:'',MASSIVE_API_KEY:''},stdio:['ignore','pipe','pipe']});
let browser,checks=0;const errors=[];
const check=async(name,fn)=>{await fn();checks++;console.log('PASS '+name);};
(async()=>{
  const base=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Server timeout '+errors.join(''))),20000);server.stdout.on('data',c=>{out+=c;const m=out.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});server.stderr.on('data',c=>errors.push(String(c)));server.on('error',reject);});
  const options={headless:true};
  if(process.env.STOCK_UI_BUNDLED_CHROMIUM==='1'){const module=require('@sparticuz/chromium'),bundled=module.default||module;options.executablePath=await bundled.executablePath();options.args=bundled.args.filter(a=>!['--disable-web-security','--allow-running-insecure-content','--disable-site-isolation-trials'].includes(a));}
  browser=await chromium.launch(options);
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const api=async path=>{const response=await context.request.get(base+path,{headers:{Authorization:'Bearer stock-ui-test-token'}});assert.equal(response.status(),200);return response.json();};
  await page.goto(base+'/market-radar');
  await check('Authentication and initial watch state',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor();
    assert.equal((await api('/api/market-radar/status')).enabled,false);
    assert.equal(await page.locator('#assetFilter option').count(),34);
    assert.equal(await page.locator('nav a[aria-current=page]').innerText(),'Market Radar');
    assert.equal(await page.locator('#trackingMode').inputValue(),'recently_sold');
  });
  await check('Start collects a baseline and exposes source failure without false news alerts',async()=>{
    await page.locator('#start').click();
    for(let i=0;i<30;i++){if((await api('/api/market-radar/status')).last_scan_finished_ts)break;await page.waitForTimeout(100);}
    await page.reload();await page.locator('#content').waitFor();
    assert.match(await page.locator('#radarState').innerText(),/running/);
    assert.match(await page.locator('#news').innerText(),/Initial snapshot/);
    assert.match(await page.locator('#news').innerText(),/Late discovery/);
    assert.match(await page.locator('#news').innerText(),/App first saw this revision/);
    const value=await api('/api/market-radar/status');assert(value.sources.some(s=>s.error));assert(!value.alerts.some(a=>a.kind==='news'));
    await page.locator('#sourcePanel summary').click();
    assert.match(await page.locator('#sources').innerText(),/timed out/);
    assert.equal(await page.locator('#news img').count(),0);
    assert.match(await page.locator('#stockConnection').innerText(),/need Alpaca/);
  });
  await check('Repeated headlines are hidden by default and remain available for review',async()=>{
    const distinct=await page.locator('#news .radar-item').count();
    assert.match(await page.locator('#newsHidden').innerText(),/hidden/);
    await page.locator('#showReprints').check();
    assert((await page.locator('#news .radar-item').count())>distinct);
    assert.match(await page.locator('#news').innerText(),/Possible reprint/);
    await page.locator('#showReprints').uncheck();
    assert.equal(await page.locator('#news .radar-item').count(),distinct);
  });
  await check('Recently sold assets and thesis notes persist across reload',async()=>{
    await page.locator('#trackingSymbol').selectOption('NTLA');await page.locator('#trackingMode').selectOption('recently_sold');
    await page.locator('#trackingNote').fill('Generated note: verify safety and dilution <img src=x>');await page.locator('#trackingForm button').click();
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('notes saved'));
    await page.reload();await page.locator('#content').waitFor();await page.locator('#trackingSymbol').selectOption('NTLA');
    assert.equal(await page.locator('#trackingMode').inputValue(),'recently_sold');
    assert.match(await page.locator('#trackingNote').inputValue(),/verify safety/);
    assert.match(await page.locator('#soldAssets').innerText(),/NTLA.*still watched/);
    assert.equal((await api('/api/market-radar/status')).watch_count,33);
  });
  await check('Calendar saves date precision, source, cancellation and revision history',async()=>{
    await page.locator('#addCatalyst').click();await page.locator('#eventSymbol').selectOption('NTLA');
    await page.locator('#eventTitle').fill('Generated upcoming decision fixture');
    await page.locator('#eventDate').fill(new Date(Date.now()+86400000).toISOString().slice(0,10));
    await page.locator('#eventStatus').selectOption('target');await page.locator('#eventSource').fill('https://example.org/fixture');
    await page.locator('#eventNote').fill('A target is not an approval.');await page.locator('#catalystForm button[type=submit]').click();
    await page.waitForFunction(()=>!document.getElementById('calendarEditor').open);
    const card=page.locator('#calendar .radar-item').filter({hasText:'Generated upcoming decision fixture'});
    assert.match(await card.innerText(),/time unspecified/);assert.match(await card.innerText(),/Source needs review/);
    await card.getByRole('button').click();await page.locator('#eventStatus').selectOption('cancelled');await page.locator('#catalystForm button[type=submit]').click();
    await page.waitForFunction(()=>!document.getElementById('calendarEditor').open);
    assert.match(await card.innerText(),/cancelled/);
    const value=await api('/api/market-radar/status');assert.equal(value.changes.length,2);assert.equal(value.changes[0].before.status,'target');
  });
  await check('Filters and AI handoff select the right asset without submitting research',async()=>{
    await page.locator('#assetFilter').selectOption('NTLA');
    const before=(await api('/api/agent/status')).daily_used;
    await page.locator('#investigate').click();await page.locator('#content').waitFor();
    assert.match(await page.locator('#message').inputValue(),/get_market_radar for NTLA/);
    assert.equal(await page.locator('#allowBacktests').isChecked(),false);
    assert.equal(await page.locator('#deepResearch').isChecked(),true);
    assert.equal((await api('/api/agent/status')).daily_used,before);
  });
  await check('Dashboard navigation, export and stop preserve evidence',async()=>{
    await page.goto(base+'/');await page.locator('#content').waitFor();assert.match(await page.locator('#radarSummary').innerText(),/33 stocks/);
    await page.getByRole('link',{name:'Open Market Radar →'}).click();await page.locator('#content').waitFor();
    await page.locator('#stop').click();await page.waitForFunction(()=>document.getElementById('radarState').textContent==='Radar stopped');
    const event=page.waitForEvent('download');await page.locator('#export').click();const download=await event;
    const value=JSON.parse(await fs.readFile(await download.path(),'utf8'));
    assert.equal(value.enabled,false);assert.equal(value.execution_enabled,false);assert(value.news.length);assert.equal(value.changes.length,2);
  });
  await check('Desktop and phone layout have no horizontal overflow',async()=>{
    await page.screenshot({path:'/tmp/market-radar-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await page.screenshot({path:'/tmp/market-radar-mobile.png',fullPage:true});
  });
  assert.deepEqual(errors,[]);console.log(checks+' market radar browser checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
