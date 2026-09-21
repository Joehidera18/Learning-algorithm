"use strict";
(function () {
  const $ = id => document.getElementById(id);
  const esc = value => String(value == null ? "—" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const finite = v => typeof v === "number" && Number.isFinite(v);
  const number = (v, d=2) => finite(v) ? v.toLocaleString("en-US",{maximumFractionDigits:d,minimumFractionDigits:d}) : "—";
  const money = v => finite(v) ? new Intl.NumberFormat("en-US",{style:"currency",currency:"USD"}).format(v) : "—";
  const label = v => String(v || "").replace(/_/g," ");
  const date = ts => ts ? new Date(ts).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"}) : "—";
  let token = sessionStorage.getItem("cryptoAccessToken") || "", state = null, inventory = null, initialized = false, refreshing = false;
  let timer = null;
  function notice(message,error=false) { $("notice").textContent=message;$("notice").className="notice"+(error?" error":"");$("notice").hidden=false; }
  async function api(path,body,blob=false) {
    const options={headers:{},credentials:"same-origin"};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined) {options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    const response=await fetch(path,options);
    if(!response.ok) {
      if(response.status===401) $("accessPanel").hidden=false;
      let message="Request failed ("+response.status+")";
      try {message=(await response.json()).error || message;} catch (_) {}
      throw new Error(message);
    }
    return blob ? response.blob() : response.json();
  }
  function daysLimits(reset=false) {
    if(!state) return;
    const iv=$("interval").value, limits=state.catalog.history_limits[iv];
    $("days").min=limits.min_days;$("days").max=limits.max_days;
    if(reset) $("days").value=({"1m":14,"4m":60,"5m":90,"15m":90,"30m":180,"1h":365,"4h":730})[iv];
    $("daysHint").textContent=limits.min_days+"–"+limits.max_days+" days · bounded to 50,000 candles";
  }
  function setup() {
    if(initialized || !state) return;
    $("symbol").innerHTML=state.catalog.symbols.map(s=>'<option>'+esc(s)+'</option>').join("");
    $("interval").innerHTML=state.catalog.intervals.map(s=>'<option>'+esc(s)+'</option>').join("");
    $("interval").value="15m";
    $("recipeChoices").innerHTML='<legend>Choose the experiments to run</legend>'+state.catalog.recipes.map((r,i)=>
      '<label class="recipe-choice"><input type="checkbox" name="recipe" value="'+esc(r.id)+'" '+(i===0?'checked':'')+'><strong>'+esc(r.title)+'</strong><p>'+esc(r.hypothesis)+'</p></label>').join("");
    daysLimits();initialized=true;$("runButton").disabled=false;
  }
  function accountTable(report,window="later") {
    return '<div class="table-wrap" tabindex="0" role="region" aria-label="'+esc(window)+' account comparison"><table><thead><tr><th>Account</th><th>Net after costs</th><th>50% higher costs</th><th>Closed trades</th><th>End marks</th><th>Drawdown</th><th>Profit factor</th><th>Model updates</th></tr></thead><tbody>'+report.variants.map(v=>{
      const w=v.windows[window];if(!w) return "";
      const a=w.standard,m=a.metrics,s=w.higher_cost.metrics;
      return '<tr><td>'+esc(label(v.id))+'</td><td class="'+(m.net_pnl<0?'negative':m.net_pnl>0?'positive':'')+'">'+money(m.net_pnl)+'</td><td>'+money(s.net_pnl)+'</td><td>'+a.closed_trades+'</td><td>'+a.window_end_exits+'</td><td>'+number(m.max_drawdown_pct)+'%</td><td>'+number(m.profit_factor)+'</td><td>'+a.model_updates+'</td></tr>';
    }).join("")+'</tbody></table></div>';
  }
  function comparisons(report) {
    return (report.comparisons || []).map(c=>'<div class="comparison '+(c.status==='no_improvement' || c.status==='lower_loss_only'?'negative':'')+'"><strong>'+esc(label(c.challenger))+' · '+esc(label(c.status))+'</strong><p>'+esc(c.reason)+'</p><p>Difference vs '+esc(label(c.control))+': '+money(c.net_difference)+' · higher costs: '+money(c.stress_net_difference)+'</p></div>').join("");
  }
  function reportHtml(r) {
    const p=r.market_data || {};
    const rejected=r.variants.map(v=>{const f=v.windows.later.standard.metrics.signal_funnel || {},counts=f.rejections || {};
      return '<p class="scope"><strong>'+esc(label(v.id))+':</strong> '+number(f.entries_opened,0)+' entries / '+number(f.entry_attempts,0)+' attempts. '+Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([k,n])=>esc(label(k))+': '+number(n,0)).join(' · ')+'</p>';}).join('');
    return '<p class="scope">Later evaluation: '+date(r.later_start_ts)+' – '+date(r.end_ts)+'. '+esc(p.provider || 'Recorded OHLCV')+' · '+esc(r.symbol)+' · '+esc(r.interval)+'. Each row is a separate $500 account.</p>'+accountTable(r)+comparisons(r)+
      '<p class="scope">Closed trades exclude end-of-window marks. Net P&amp;L includes those marks and execution costs. Incomplete accounts show no return. Profit factor is unavailable when there are no losing trades.</p>'+
      '<p class="scope">'+number(r.coverage && r.coverage.downloaded_candles,0)+' observed candles · '+number(r.data_quality && r.data_quality.gaps,0)+' internal gaps. Historical development only; not independent forward evidence.</p>'+
      '<details><summary>Why entries were rejected</summary>'+rejected+'<p class="scope">Cost rejections mean the proposed move did not meet the configured fee and reward requirements. Use your verified exchange fee tier in Settings; these tests do not assume a cheaper tier.</p></details>'+
      (r.variants.some(v=>v.windows.earlier)?'<details><summary>Earlier development accounts</summary>'+accountTable(r,"earlier")+'</details>':'')+
      '<details><summary>Protocol and evidence limits</summary><p class="scope">'+(r.limitations || []).map(esc).join('<br>')+'</p><p class="identity">Data: '+esc(r.data_sha256)+'<br>Code: '+esc(r.source_sha256)+'<br>Experiment: '+esc(r.fingerprint)+'</p></details>';
  }
  function render() {
    setup();$("jobCount").textContent=state.total_jobs;$("pendingCount").textContent=state.pending_jobs;
    $("workerState").textContent=state.blocked_by_other_research?"Waiting for other research to finish":state.active_id?"Working on a saved comparison":state.pending_jobs?"Queued for the worker":"Ready for a new question";
    const opened=new Set(Array.from($("jobs").querySelectorAll("details[data-job][open]")).map(x=>x.dataset.job));
    $("jobs").innerHTML=state.jobs.length?state.jobs.map(j=>{
      const m=j.manifest,r=j.result,active=["queued","downloading","features","training","testing"].includes(j.status);
      const title=(state.catalog.recipes.find(x=>x.id===m.recipe) || {}).title || label(m.recipe);
      return '<article class="panel job"><div class="job-head"><div><h3>'+esc(title)+'</h3><p>'+esc(m.symbol)+' · '+esc(m.interval)+' · '+m.days+' days · cutoff '+date(m.cutoff_ts)+'</p></div><span class="badge job-status">'+esc(label(j.status))+'</span></div><p class="job-progress">'+esc(j.progress.message)+'</p>'+
        '<p class="scope">Fee '+number(m.settings.fee_rate*100,3)+'% per side · modeled slippage '+number(m.settings.slippage_rate*100,3)+'% + 0.05% half spread per side · risk '+number(m.settings.risk_per_trade*100,2)+'%</p>'+
        (r?'<details data-job="'+j.id+'" '+(opened.has(j.id)?'open':'')+'><summary>View measured results</summary>'+reportHtml(r)+'</details>':'')+
        '<div class="job-controls">'+(active?'<button data-action="cancel" data-id="'+j.id+'">Cancel</button>':'')+(['error','cancelled'].includes(j.status)?'<button data-action="retry" data-id="'+j.id+'">Resume same experiment</button>':'')+'<button data-action="export" data-id="'+j.id+'">Download record</button></div></article>';
    }).join(""):'<div class="panel"><div class="empty-experiments"><h3>Your first comparison starts here.</h3><p class="muted">Choose a market and a question above. Every outcome stays in the record, including no trades, missing data, and losing results.</p></div></div>';
  }
  function renderPlan(plan) {
    $("plannerMode").textContent=plan.mode==='openai'?"AI HYPOTHESES":"BUILT-IN SUGGESTIONS";
    $("plannerNote").textContent=plan.note+' Journal evidence: '+plan.evidence.closed_trades+' closed paper trades.';
    $("suggestions").innerHTML=plan.suggestions.map(p=>'<article class="suggestion"><h3>'+esc((state.catalog.recipes.find(r=>r.id===p.recipe)||{}).title || label(p.recipe))+'</h3><p>'+esc(p.rationale)+'</p><button data-select="'+esc(p.recipe)+'">Select this experiment</button></article>').join("");
  }
  async function planner() {
    const p=await api('/api/experiments/planner');renderPlan(p.last_ai_plan || p.built_in);
    $("aiPlan").disabled=!p.ai_available;$("aiNote").textContent=p.ai_note;
  }
  async function refresh() {
    if(refreshing) return;
    refreshing=true;
    try {state=await api('/api/experiments/status');render();}
    catch(e){notice(e.message,true);}
    finally {refreshing=false;clearTimeout(timer);timer=setTimeout(refresh,10000);}
  }
  function coverage() {
    if(!inventory) return;
    $("coverageNote").textContent=inventory.scope+' · '+inventory.as_of+'.';
    const iv=$("coverageInterval").value;
    $("coverageRows").innerHTML=inventory.coins.map(c=>{const t=c.timeframes.find(t=>t.interval===iv);return '<tr><td>'+esc(c.pair)+'</td><td>'+number(t.rows,0)+'</td><td>'+number(t.coverage_pct,3)+'%</td><td class="'+(t.missing_candles?'negative':'')+'">'+number(t.missing_candles,0)+'</td><td>'+number(t.zero_volume_rows,0)+'</td></tr>';}).join("");
  }
  async function loadExtras() {
    const work = [planner(),api('/api/continuous/settings').then(s=>{$("costs").textContent='Current settings: fee '+number(s.fee_rate*100,3)+'% per side; modeled slippage '+number(s.slippage_rate*100,3)+'% plus a 0.05% half spread per side; risk '+number(s.risk_per_trade*100)+'% per trade. Each queued job saves these settings.';}),
      api('/api/experiments/coverage').then(v=>{inventory=v;coverage();}),
      api('/api/experiments/release-results').then(v=>{if(v.reports && v.reports.length){$("releaseSection").hidden=false;$("releaseNote").textContent=v.note;$("releaseResults").innerHTML=v.reports.map(r=>'<details class="release-result"><summary>'+esc(r.symbol)+' · '+esc(r.interval)+' · '+esc(r.title)+'</summary>'+reportHtml(r)+'</details>').join('');}})];
    const results=await Promise.allSettled(work);results.forEach(r=>{if(r.status==='rejected')notice(r.reason.message,true);});
  }
  $("interval").addEventListener('change',()=>daysLimits(true));
  $("coverageInterval").addEventListener('change',coverage);
  $("refresh").addEventListener('click',refresh);
  $("experimentForm").addEventListener('submit',async e=>{
    e.preventDefault();const recipes=Array.from(document.querySelectorAll('input[name="recipe"]:checked')).map(x=>x.value);
    if(!recipes.length){notice('Choose at least one experiment.',true);return;}
    $("runButton").disabled=true;
    try {const result=await api('/api/experiments/start',{symbol:$("symbol").value,interval:$("interval").value,days:Number($("days").value),recipes});notice(result.message);await refresh();}
    catch(e){notice(e.message,true);}finally{$("runButton").disabled=false;}
  });
  $("suggestions").addEventListener('click',e=>{const b=e.target.closest('button[data-select]');if(!b)return;document.querySelectorAll('input[name="recipe"]').forEach(x=>{x.checked=x.value===b.dataset.select;});$("experimentForm").scrollIntoView({behavior:'smooth',block:'start'});});
  $("jobs").addEventListener('click',async e=>{
    const b=e.target.closest('button[data-action]');if(!b)return;b.disabled=true;
    try {if(b.dataset.action==='export') {const blob=await api('/api/experiments/export?id='+encodeURIComponent(b.dataset.id),undefined,true),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='experiment-'+b.dataset.id.slice(0,12)+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
      else {await api('/api/experiments/'+b.dataset.action,{id:b.dataset.id});await refresh();}}
    catch(e){notice(e.message,true);}finally{b.disabled=false;}
  });
  $("aiPlan").addEventListener('click',async()=>{$("aiPlan").disabled=true;try{const p=await api('/api/experiments/planner',{mode:'openai'});renderPlan(p);notice('Research hypotheses saved. Select a comparison to test them.');}catch(e){notice(e.message,true);}finally{$("aiPlan").disabled=false;}});
  $("accessForm").addEventListener('submit',async e=>{e.preventDefault();token=$("accessToken").value.trim();sessionStorage.setItem('cryptoAccessToken',token);$("accessPanel").hidden=true;await refresh();if(state)await loadExtras();});
  (async()=>{await refresh();if(state)await loadExtras();})();
})();
