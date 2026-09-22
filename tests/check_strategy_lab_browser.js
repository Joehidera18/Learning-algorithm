/* Local fixture tests: no stock feeds, brokerage calls, or real account files. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path');
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
  await page.goto(base+'/strategy-lab');
  await check('Lab requires the access token and loads all registered strategies',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#content').isVisible(),false);
    await page.locator('#accessToken').fill('stock-ui-test-token');await page.locator('#accessForm button').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert.equal(await page.locator('#strategy option').count(),5);
    assert.equal(await page.locator('#jobs .equity-job').count(),2);
    assert.equal(await page.locator('#provider option[value="massive"]').evaluate(e=>e.disabled),true);
  });
  await check('Incomplete and legacy reports do not display a passing result',async()=>{
    const text=await page.locator('#jobs').innerText();
    assert.match(text,/Candles went missing/);assert.match(text,/rerun with the corrected backtester/);
    assert.equal((text.match(/eligible false/g)||[]).length,2);
    assert.doesNotMatch(text,/\$99\.00|eligible true/);
  });
  await check('ORB excludes decision bars too large to form its opening range',async()=>{
    assert.equal(await page.locator('#decision option').filter({hasText:/^1h$/}).evaluate(e=>e.disabled),true);
    await page.locator('#strategy').selectOption('trend_pullback_simple');
    await page.locator('#decision').selectOption('1h');
    await page.locator('#strategy').selectOption('orb_15m');
    assert.equal(await page.locator('#decision').inputValue(),'5m');
  });
  await check('Authorized submission reaches the persisted queue',async()=>{
    const request=page.waitForRequest(r=>r.url().endsWith('/api/strategy-lab/start') && r.method()==='POST');
    await page.locator('#runButton').click();const sent=await request;
    assert.equal(sent.headers().authorization,'Bearer stock-ui-test-token');
    assert.equal(sent.postDataJSON().strategy,'orb_15m');
    await page.waitForFunction(()=>document.querySelectorAll('#jobs .equity-job').length===3);
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
  });
  assert.equal(errors.length,0,errors.join('\n'));console.log(checks+' strategy lab browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
