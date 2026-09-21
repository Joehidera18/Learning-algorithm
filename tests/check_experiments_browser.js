/* Local integration fixtures only. Does not fetch candles or call an AI API. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const server=spawn(process.env.STOCK_UI_PYTHON || 'python3',['-m','tests.serve_stock_ui'],{
  cwd:path.resolve(__dirname,'..'),env:{...process.env,EXPERIMENT_UI_FIXTURES:'1',COINBASE_ALLOW_LIVE:'0',COINBASE_KEY_FILE:'',OPENAI_API_KEY:'',OPENAI_EXPERIMENT_MODEL:''},stdio:['ignore','pipe','pipe']});
let browser;const errors=[];let checks=0;
const check=async(name,run)=>{await run();checks++;console.log('PASS '+name);};
(async()=>{
  const base=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Test server timeout')),15000);let output='';
    server.stdout.on('data',c=>{output+=c;const m=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.stderr.on('data',c=>errors.push(String(c)));server.on('error',reject);
    server.on('exit',code=>{if(!output)reject(Error('Server exited '+code+errors.join('')));});
  });
  const options={headless:true};
  if(process.env.STOCK_UI_BUNDLED_CHROMIUM==='1'){
    const imported=require('@sparticuz/chromium'), bundled=imported.default || imported;
    options.executablePath=await bundled.executablePath();
    options.args=bundled.args.filter(a=>!['--disable-web-security','--allow-running-insecure-content','--disable-site-isolation-trials'].includes(a));
  }
  browser=await chromium.launch(options);
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/experiments');
  await check('Token protection and all experiment choices load',async()=>{
    await page.locator('#accessPanel').waitFor({state:'visible'});
    await page.locator('#accessToken').fill('stock-ui-test-token');
    await page.locator('#accessForm button').click();
    await page.locator('#runButton').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.getElementById('runButton').disabled);
    assert.equal(await page.locator('#recipeChoices input').count(),3);
    assert.equal(await page.locator('#interval option').count(),7);
    assert.equal(await page.locator('#symbol option').count(),15);
  });
  await check('Completed records expose net results, uncertainty and entry rejection reasons',async()=>{
    await page.locator('details[data-job] summary').first().click();
    assert.match(await page.locator('#jobs').innerText(),/insufficient evidence/);
    assert.match(await page.locator('#jobs').innerText(),/\$0.00/);
    await page.getByText('Why entries were rejected',{exact:true}).first().click();
    assert.match(await page.locator('#jobs').innerText(),/no channel breakout/);
  });
  await check('Queue, duplicate reuse, cancellation and resuming use the real API',async()=>{
    await page.locator('#days').fill('90');
    await page.locator('#runButton').click();
    await page.waitForFunction(()=>document.getElementById('jobCount').textContent==='2');
    await page.locator('#runButton').click();
    await page.waitForFunction(()=>!document.getElementById('runButton').disabled);
    assert.equal(await page.locator('#jobCount').textContent(),'2');
    await page.locator('button[data-action="cancel"]').click();
    await page.locator('button[data-action="retry"]').waitFor();
    await page.locator('button[data-action="retry"]').click();
    await page.locator('button[data-action="cancel"]').waitFor();
  });
  await check('Planner is honestly labelled and timeframes set appropriate history bounds',async()=>{
    assert.equal(await page.locator('#aiPlan').isDisabled(),true);
    assert.match(await page.locator('#plannerMode').innerText(),/BUILT-IN/);
    await page.locator('#interval').selectOption('4h');
    assert.equal(await page.locator('#days').inputValue(),'730');
    assert.equal(await page.locator('#days').getAttribute('min'),'517');
    await page.locator('#suggestions button').nth(1).click();
    assert.equal(await page.locator('input[name="recipe"]:checked').inputValue(),'exit_rules');
  });
  await check('Export contains the registered manifest and all comparison accounts',async()=>{
    const job=page.locator('.job').filter({has:page.locator('details[data-job]')});
    const downloaded=page.waitForEvent('download');await job.locator('button[data-action="export"]').click();
    const download=await downloaded,content=JSON.parse(await fs.readFile(await download.path(),'utf8'));
    assert.equal(content.manifest.provider,'Coinbase Exchange');
    assert.equal(content.result.variants.length,2);
    assert.equal(content.result.eligible_for_trading,false);
  });
  await check('Coverage distinguishes missing candles and source; hostile text stays inert',async()=>{
    assert.equal(await page.locator('#coverageRows tr').count(),15);
    assert.match(await page.locator('#coverageNote').innerText(),/not the Coinbase/);
    await page.route('**/api/experiments/planner',async route=>route.fulfill({json:{built_in:{mode:'built_in',note:'<img src=x onerror=alert(1)>',evidence:{closed_trades:0},suggestions:[{recipe:'exit_rules',rationale:'<script>window.bad=1</script>'}]},ai_available:false,ai_note:'Fixture'}}));
    await page.reload();await page.waitForFunction(()=>document.getElementById('plannerNote').textContent.includes('<img'));
    assert.equal(await page.locator('#plannerNote img').count(),0);assert.equal(await page.evaluate(()=>window.bad),undefined);
  });
  const artifacts=process.env.EXPERIMENT_UI_ARTIFACTS || '/tmp/experiment-ui';await fs.mkdir(artifacts,{recursive:true});
  await page.unroute('**/api/experiments/planner');await page.reload();await page.locator('#coverageRows tr').first().waitFor();
  await page.screenshot({path:path.join(artifacts,'experiments-desktop.png'),fullPage:true});
  await check('Mobile layout fits the viewport and preserves usable controls',async()=>{
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    assert.equal(await page.locator('#runButton').isVisible(),true);
    await page.screenshot({path:path.join(artifacts,'experiments-mobile.png'),fullPage:true});
  });
  assert.deepEqual(errors,[]);console.log(checks+' experiment browser checks passed. Screenshots: '+artifacts);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});
