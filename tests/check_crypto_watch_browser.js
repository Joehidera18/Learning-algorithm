/* Real local HTTP service and generated market/news fixtures; no provider calls. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON||'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,CRYPTO_WATCH_UI_FIXTURES:'1',AGENT_UI_FIXTURES:'1',OPENAI_API_KEY:'',
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
  const api=async action=>{const response=await context.request.get(base+action,{headers:{Authorization:'Bearer stock-ui-test-token'}});assert.equal(response.status(),200);return response.json();};
  await page.goto(base+'/crypto-watch');
  await check('Authentication precedes controls and watch starts disabled',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal((await api('/api/crypto-watch/status')).enabled,false);
    assert.equal(await page.locator('.watch-card').count(),12);
    assert.equal(await page.locator('nav a[aria-current=page]').innerText(),'Crypto watch');
  });
  await check('Starting the server watch records distinct breakout, building and extended observations',async()=>{
    await page.locator('#start').click();
    for(let i=0;i<30;i++){if((await api('/api/crypto-watch/status')).last_scan_finished_ts)break;await page.waitForTimeout(100);}
    await page.reload();await page.locator('#content').waitFor();
    assert.match(await page.locator('.watch-card').filter({has:page.getByRole('heading',{name:'HBAR-USD',exact:true})}).innerText(),/Breakout observed/);
    assert.match(await page.locator('.watch-card').filter({has:page.getByRole('heading',{name:'ETH-USD',exact:true})}).innerText(),/Already extended/);
    assert.match(await page.locator('.watch-card').filter({has:page.getByRole('heading',{name:'SOL-USD',exact:true})}).innerText(),/Building interest/);
    assert.equal(await page.locator('#alerts .watch-observation').count(),3);
    assert.match(await page.locator('#alerts').innerText(),/Initial snapshot/);
  });
  await check('Provider failures remain visible and news distinguishes publication from discovery',async()=>{
    assert.match(await page.locator('.watch-card').filter({has:page.getByRole('heading',{name:'LTC-USD',exact:true})}).innerText(),/Data unavailable/);
    assert.match(await page.locator('#news').innerText(),/Published:.*First observed revision:/);
    assert.match(await page.locator('#watchState').innerText(),/1 feeds pending or unavailable/);
  });
  await check('Export contains saved timing and evidence without order capability',async()=>{
    const event=page.waitForEvent('download');await page.locator('#export').click();const download=await event;
    const value=JSON.parse(await fs.readFile(await download.path(),'utf8'));
    assert.equal(value.execution_enabled,false);assert.equal(value.alerts.length,3);
    assert(value.alerts.every(a=>a.observed_ts>=a.candle_end_ts&&a.initial_observation));
  });
  await check('Desktop and phone layout fit the viewport',async()=>{
    await page.screenshot({path:'/tmp/crypto-watch-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await page.screenshot({path:'/tmp/crypto-watch-mobile.png',fullPage:true});
  });
  await check('AI handoff uses workspace evidence and never auto-submits paid research',async()=>{
    const before=(await api('/api/agent/status')).daily_used;
    await page.locator('.watch-card').filter({has:page.getByRole('heading',{name:'HBAR-USD',exact:true})}).getByRole('link').click();
    await page.locator('#content').waitFor();
    assert.match(await page.locator('#message').inputValue(),/HBAR-USD/);
    assert.match(await page.locator('#message').inputValue(),/actual|actually/);
    assert.equal(await page.locator('#allowBacktests').isChecked(),false);
    assert.equal(await page.locator('#deepResearch').isChecked(),true);
    assert.equal((await api('/api/agent/status')).daily_used,before);
  });
  await check('Stopped watch preserves observations and remains accessible from the dashboard',async()=>{
    await page.goto(base+'/');await page.getByRole('link',{name:'Crypto watch',exact:true}).click();
    await page.locator('#content').waitFor();await page.locator('#stop').click();
    await page.waitForFunction(()=>document.getElementById('watchState').textContent==='Watch stopped');
    assert.equal((await api('/api/crypto-watch/status')).enabled,false);
    assert.equal(await page.locator('#alerts .watch-observation').count(),3);
  });
  assert.deepEqual(errors,[]);console.log(checks+' crypto watch browser checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
