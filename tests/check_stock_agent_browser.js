/* Browser integration with a real local app and simulated AI; no paid requests. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON||'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,AGENT_UI_FIXTURES:'1',OPENAI_API_KEY:'',
    ALPACA_API_KEY:'',ALPACA_SECRET_KEY:'',APCA_API_KEY_ID:'',APCA_API_SECRET_KEY:'',MASSIVE_API_KEY:''},stdio:['ignore','pipe','pipe']});
let browser,checks=0;const errors=[];
const check=async(name,fn)=>{await fn();checks++;console.log('PASS '+name);};
(async()=>{
  const base=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Server timeout '+errors.join(''))),20000);server.stdout.on('data',c=>{out+=c;const m=out.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});server.stderr.on('data',c=>errors.push(String(c)));server.on('error',reject);});
  const options={headless:true};
  if(process.env.STOCK_UI_BUNDLED_CHROMIUM==='1'){const module=require('@sparticuz/chromium'),bundled=module.default||module;options.executablePath=await bundled.executablePath();options.args=bundled.args.filter(a=>!['--disable-web-security','--allow-running-insecure-content','--disable-site-isolation-trials'].includes(a));}
  browser=await chromium.launch(options);
  const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  await context.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const api=async action=>{const response=await context.request.get(base+action,{headers:{Authorization:'Bearer stock-ui-test-token'}});assert.equal(response.status(),200);return response.json();};
  async function send(message,{deep=false,tests=false}={}){await page.locator('#message').fill(message);await page.locator('#deepResearch').setChecked(deep);await page.locator('#allowBacktests').setChecked(tests);await page.locator('#send').click();await page.waitForFunction(()=>document.querySelector('.agent-answer')?.textContent.includes('Generated browser fixture'));}
  await page.goto(base+'/agent');
  await check('Agent authenticates with the existing app token',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#setupPanel').isVisible(),false);
    assert.equal(await page.locator('#send').isEnabled(),true);
    assert.equal(await page.locator('nav a[aria-current=page]').innerText(),'AI Research Agent');
  });
  await check('Research presets set scope without submitting paid work',async()=>{
    await page.locator('[data-preset=crypto]').click();
    assert.match(await page.locator('#message').inputValue(),/unlock/);
    assert.equal(await page.locator('#deepResearch').isChecked(),true);
    assert.equal(await page.locator('#allowBacktests').isChecked(),false);
    assert.equal((await api('/api/agent/status')).daily_used,0);
  });
  await check('Chat renders inline sources and treats provider HTML as text',async()=>{
    await send('proposal fixture');
    assert.equal(await page.locator('.agent-answer img').count(),0);
    assert.equal(await page.locator('.agent-answer a').getAttribute('href'),'https://example.org/fixture');
    assert.equal(await page.locator('a[href^="javascript:"]').count(),0);
    assert.match(await page.locator('.agent-answer').innerText(),/<img src=x/);
    assert.equal((await api('/api/strategy-lab/status')).jobs.length,0);
    assert.equal(await page.locator('a:has-text("Review QQQ backtest")').count(),1);
  });
  await check('Research reports export with source attribution',async()=>{
    const event=page.waitForEvent('download');await page.getByRole('button',{name:'Export report'}).click();const download=await event;
    const text=await fs.readFile(await download.path(),'utf8');assert.match(text,/https:\/\/example.org\/fixture/);assert.match(text,/proposal fixture/);
  });
  await check('Proposal opens the real backtest form with reviewed settings and no automatic job',async()=>{
    await page.getByRole('link',{name:'Review QQQ backtest'}).click();
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Agent proposal loaded'));
    assert.equal(await page.locator('#symbol').inputValue(),'QQQ');assert.equal(await page.locator('#days').inputValue(),'40');
    assert.equal(await page.locator('#fee').inputValue(),'0.01');assert.equal(await page.locator('#balance').inputValue(),'500');
    assert.equal((await api('/api/strategy-lab/status')).jobs.length,0);
    await page.locator('#runButton').click();await page.waitForFunction(()=>document.getElementById('jobs').textContent.includes('QQQ'));
    const jobs=(await api('/api/strategy-lab/status')).jobs;assert.equal(jobs.length,1);assert.equal(jobs[0].request.symbol,'QQQ');
  });
  await check('Saved conversations survive navigation and reload',async()=>{
    await page.goto(base+'/agent');await page.locator('.agent-answer').waitFor();await page.reload();await page.locator('.agent-answer').waitFor();
    assert.equal(await page.locator('.agent-message').count(),1);assert.equal((await api('/api/agent/status')).daily_used,1);
  });
  await check('A saved-test link resolves a job outside the recent status window',async()=>{
    const job=(await api('/api/strategy-lab/status')).jobs[0];
    await page.route('**/api/strategy-lab/status',async route=>{const response=await route.fetch(),value=await response.json();await route.fulfill({json:{...value,jobs:[]}});});
    await page.goto(base+'/backtests?job='+encodeURIComponent(job.id));
    await page.waitForFunction(()=>document.getElementById('jobs').textContent.includes('QQQ'));
    assert.equal(await page.locator('#jobs .equity-job').count(),1);
    await page.unroute('**/api/strategy-lab/status');await page.goto(base+'/agent');await page.locator('.agent-answer').waitFor();
  });
  await check('Permitted stock testing saves actual evidence in the strategy notebook',async()=>{
    await page.locator('#newChat').click();await send('strategy fixture',{deep:true,tests:true});
    await page.locator('#refreshNotebook').click();await page.waitForFunction(()=>document.getElementById('notebook').textContent.includes('insufficient trades'));
    assert.match(await page.locator('#notebook').innerText(),/four trades cannot establish an edge/);
    assert.equal(await page.getByRole('link',{name:'View test: SPY · orb_15m'}).count(),1);
    assert.equal((await api('/api/strategy-lab/status')).jobs.length,2);
  });
  await check('Cancelling a research run prevents a late answer from becoming success',async()=>{
    await page.locator('#newChat').click();await page.locator('#message').fill('slow fixture');await page.locator('#send').click();
    await page.locator('#progressPanel').waitFor({state:'visible'});await page.locator('#stop').click();
    await page.waitForFunction(()=>document.getElementById('conversation').textContent.includes('cancelled'));
    await page.waitForTimeout(2300);await page.reload();await page.locator('.agent-error').waitFor();
    assert.equal(await page.locator('.agent-answer').count(),0);assert.match(await page.locator('.agent-error').innerText(),/in-flight/);
  });
  await check('An ambiguous lost response retries the same request without a second run',async()=>{
    await page.locator('#newChat').click();let lost=false;
    await page.route('**/api/agent/start',async route=>{if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();});
    const before=(await api('/api/agent/status')).daily_used;
    await page.locator('#message').fill('retry fixture');await page.locator('#send').click();
    await page.locator('#retrySubmission').waitFor({state:'visible'});await page.locator('#retrySubmission').click();
    await page.locator('.agent-answer').waitFor();assert.equal((await api('/api/agent/status')).daily_used,before+1);
    await page.unroute('**/api/agent/start');
  });
  await check('Missing server credentials show setup without a fake research answer',async()=>{
    await page.route('**/api/agent/status',async route=>{const response=await route.fetch(),value=await response.json();await route.fulfill({json:{...value,configured:false,missing:['OPENAI_API_KEY']}});});
    await page.route('**/api/agent/thread**',async route=>{await new Promise(resolve=>setTimeout(resolve,300));await route.continue();});
    await page.reload();await page.locator('#setupPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#send').isDisabled(),true);assert.match(await page.locator('#setupMessage').innerText(),/OPENAI_API_KEY/);
    await page.locator('#conversation .agent-message').first().waitFor();
    await page.unroute('**/api/agent/thread**');
    await page.unroute('**/api/agent/status');await page.reload();await page.locator('#content').waitFor();
  });
  await check('Desktop and phone layouts remain within the viewport',async()=>{
    await page.screenshot({path:'/tmp/stock-agent-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true);
    await page.screenshot({path:'/tmp/stock-agent-mobile.png',fullPage:true});
    assert.equal(await page.locator('#message').isVisible(),true);
  });
  await check('Deleting a lesson or conversation preserves backtests and usage counts',async()=>{
    page.on('dialog',dialog=>dialog.accept());const before=(await api('/api/agent/status')).daily_used;
    await page.locator('#refreshNotebook').click();await page.getByRole('button',{name:'Remove lesson'}).click();
    await page.waitForFunction(()=>document.getElementById('notebook').textContent.includes('No lessons saved'));
    await page.locator('#deleteChat').click();await page.locator('#starters').waitFor({state:'visible'});
    assert.equal((await api('/api/agent/status')).daily_used,before);assert.equal((await api('/api/strategy-lab/status')).jobs.length,2);
  });
  assert.deepEqual(errors,[]);console.log(checks+' agent browser checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
