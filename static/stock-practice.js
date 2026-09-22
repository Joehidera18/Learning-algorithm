"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = x => String(x == null ? "—" : x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const number = (x,d=2) => finite(x) ? x.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
  const money = x => finite(x) ? new Intl.NumberFormat(undefined,{style:"currency",currency:"USD"}).format(x) : "—";
  const when = x => x ? new Date(x).toLocaleString() : "—";
  const name = x => String(x || "").replace(/_/g," ");
  const apiRoot = "/api/stocks/practice/";
  let token = sessionStorage.getItem("cryptoAccessToken") || "", state, initialized = false, refreshing = false;
  function notice(message,error=false) {$("notice").textContent=message;$("notice").hidden=false;$("notice").className="notice"+(error?" error":"");}
  async function api(action,body,blob=false) {
    const options={credentials:"same-origin",headers:{}};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined) {options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    const response=await fetch(apiRoot+action,options);
    if(!response.ok) {
      if(response.status===401) $("accessPanel").hidden=false;
      let message="Request failed ("+response.status+")";
      try {message=(await response.json()).error || message;} catch(_) {}
      throw Error(message);
    }
    return blob ? response.blob() : response.json();
  }
  function bounds(reset=false) {
    if(!state) return;
    const provider=$("provider").value,iv=$("interval").value;
    const config=state.catalog.providers[provider],limit=config.max_days[iv];
    $("days").max=limit;
    if(reset || Number($("days").value)>limit) $("days").value=Math.min(limit,iv==="1d"?1825:iv==="4h"?729:iv==="1h"?365:59);
    $("feedLabel").hidden=provider!=="alpaca";
    if(iv==="1d") $("mode").value="swing";
    $("mode").querySelector('option[value="day"]').disabled=iv==="1d";
    $("historyHint").textContent="Up to "+limit+" calendar days on this source. "+config.note+(iv==="4m"?" Minute data is downloaded in six-day batches, then complete four-minute bars are built.":"");
    $("runButton").disabled=!config.available;
  }
  function setup() {
    if(initialized) return;
    $("tickerList").innerHTML=state.catalog.symbols.map(s=>'<option value="'+esc(s)+'"></option>').join("");
    $("interval").innerHTML=state.catalog.intervals.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join("");
    $("interval").value=state.catalog.default_interval || "15m";
    const providers=state.catalog.providers;
    $("provider").innerHTML=Object.keys(providers).map(key=>'<option value="'+esc(key)+'"'+(providers[key].available?'':' disabled')+'>'+esc(key)+(providers[key].available?'':' · unavailable')+'</option>').join("");
    initialized=true;bounds();
  }
  function facts(items) {return '<div class="equity-facts">'+items.map(([v,label])=>'<div><strong>'+esc(v)+'</strong><span>'+esc(label)+'</span></div>').join("")+'</div>';}
  function button(action,id,text) {return '<button class="small" data-action="'+esc(action)+'" data-id="'+esc(id)+'">'+esc(text)+'</button>';}
  function renderJobs() {
    const opened=new Set([...document.querySelectorAll("details[data-job][open]")].map(e=>e.dataset.job));
    $("jobCount").textContent=state.total_jobs+" RUN"+(state.total_jobs===1?"":"S");
    $("queueStatus").textContent=state.blocked_by_other_research?"Waiting for the other research task to finish.":state.pending_jobs?state.pending_jobs+" run(s) queued or running.":"Saved stock results stay separate from crypto practice.";
    $("jobs").innerHTML=state.jobs.length?state.jobs.map(job=>{
      const m=job.manifest,r=job.result,done=job.status==="complete";
      let html='<article class="equity-job"><div class="job-summary"><div class="job-title"><h3>'+esc(m.symbol)+' <span class="muted">· '+esc(m.interval)+' · '+esc(m.mode)+'</span></h3><span class="badge">'+esc(name(job.status))+'</span></div><p>'+esc(job.progress.message)+'</p><p class="muted">'+esc(m.provider)+(m.provider==="alpaca"?' / '+esc(m.feed):'')+' · '+esc(m.days)+' calendar days · '+(m.fractional_shares?'fractional':'whole')+' shares</p><div class="equity-actions">';
      if(done) html+=button("forward/start",job.id,"Start forward practice")+button("export",job.id,"Export full results")+button("candles",job.id,"Download candles");
      else if(["error","cancelled"].includes(job.status)) html+=button("retry",job.id,"Retry saved run");
      else if(job.status!=="code_changed") html+=button("cancel",job.id,"Cancel");
      html+='</div></div>';
      if(r) {
        html+='<details class="job-body" data-job="'+esc(job.id)+'"'+(opened.has(job.id)?' open':'')+'><summary>View learning, coverage & strategy results</summary>';
        html+=facts([[number(r.seed.resolved_examples,0),"earlier resolved learning examples"],[number(r.coverage.observed_candles,0),"observed stock candles"],[number(r.coverage.coverage_pct,2)+"%","requested session coverage"],[money(r.buy_hold_price_return.net_pnl),"buy & hold · price-only net"]]);
        html+='<p class="muted">Later comparison: '+esc(when(r.later_start_ts))+' → '+esc(when(r.end_ts))+'. Every row is an independent $500 simulation.</p><div class="result-table"><table><thead><tr><th>Strategy</th><th>Net P/L</th><th>Return</th><th>Higher-cost P/L</th><th>Closed trades</th><th>Drawdown</th><th>Learning updates</th></tr></thead><tbody>';
        for(const v of r.variants) {
          const a=v.windows.later.standard,b=v.windows.later.higher_cost,q=a.metrics;
          html+='<tr><td>'+esc(name(v.id))+'</td><td class="'+(q.net_pnl>0?'up':q.net_pnl<0?'down':'')+'">'+money(q.net_pnl)+'</td><td>'+number(q.return_pct)+'%</td><td>'+money(b.metrics.net_pnl)+'</td><td>'+number(a.closed_trades,0)+'</td><td>'+number(q.max_drawdown_pct)+'%</td><td>'+number(a.model_updates,0)+'</td></tr>';
        }
        html+='</tbody></table></div>';
        for(const c of r.comparisons) html+='<div class="comparison"><strong>'+esc(name(c.challenger))+' vs '+esc(name(c.control))+' · '+esc(name(c.status))+'</strong><p>'+esc(c.reason)+'</p><p>Net difference '+money(c.net_difference)+' · higher-cost difference '+money(c.stress_net_difference)+'</p></div>';
        html+='<details><summary>Entry decisions, costs and data limits</summary><p>'+esc(r.market_data.adjustment)+'. '+number(r.coverage.missing_candles,0)+' scheduled candles missing. No synthetic candles.</p><pre>'+esc(JSON.stringify({costs:r.costs,source:r.market_data,training:r.training.map(t=>({family:t.family,examples:t.resolved_examples,rejections:t.signal_funnel.entry_rejections})),accounts:r.variants.map(v=>({strategy:v.id,rejections:v.windows.later.standard.metrics.signal_funnel.rejections,complete:v.windows.later.standard.metrics.complete})),limitations:r.limitations},null,2))+'</pre></details></details>';
      }
      return html+'</article>';
    }).join(""):'<div class="equity-empty"><strong>Your stock learner is ready to practice.</strong>Start with a stock or an ETF. The results will show whether the strategy traded, what it learned, and what it earned after assumed costs.</div>';
  }
  function renderForward() {
    $("forwardAccounts").innerHTML=state.forward.length?state.forward.map(f=>{
      const a=f.account,m=a&&a.metrics;
      let h='<article class="equity-job"><div class="job-summary"><div class="job-title"><h3>'+esc(f.symbol)+' · '+esc(f.interval)+' · '+esc(f.mode)+'</h3><span class="badge">'+esc(name(f.status))+'</span></div><p>'+esc(f.message)+'</p><p>Registered '+esc(when(f.created_ts))+' · latest candle close '+esc(when(m&&m.as_of_ts))+'</p>';
      if(m) h+=facts([[money(m.ending_balance),"marked account equity"],[money(m.net_pnl),"net P/L, including open mark"],[number(a.closed_trades,0),"closed paper trades"],[number(a.model_updates,0),"resolved setup learning updates"]])+'<p>'+(m.open_position?'Open paper position: '+esc(number(m.open_position.qty,6))+' shares · entry '+money(m.open_position.entry)+' · stop '+money(m.open_position.stop):'No open paper position.')+'</p>';
      if(f.status==="running") h+=button("forward/stop",f.id,"Stop forward practice");
      return h+'</div></article>';
    }).join(""):'<div class="equity-empty"><strong>No forward stock account yet.</strong>Complete historical stock practice, then choose “Start forward practice” on its result.</div>';
  }
  async function refresh(showError=true) {
    if(refreshing) return;
    refreshing=true;
    try {
      state=await api("status");setup();
      $("accessPanel").hidden=true;$("content").hidden=false;
      const m=state.market;
      $("marketClock").textContent=m.open?"REGULAR SESSION OPEN · closes "+when(m.close_ts):"REGULAR SESSION CLOSED · next open "+when(m.next_open_ts);
      renderJobs();renderForward();
    } catch(e) {if(showError) notice(e.message,true);} finally {refreshing=false;}
  }
  async function download(action,filename) {
    const blob=await api(action,undefined,true),url=URL.createObjectURL(blob),a=document.createElement("a");
    a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();sessionStorage.setItem("cryptoAccessToken",token);await refresh();});
  $("symbol").addEventListener("input",()=>{$("symbol").value=$("symbol").value.toUpperCase();});
  $("interval").addEventListener("change",()=>bounds(true));$("provider").addEventListener("change",()=>bounds(true));
  $("refresh").addEventListener("click",()=>refresh());
  $("practiceForm").addEventListener("submit",async e=>{
    e.preventDefault();$("runButton").disabled=true;
    try {
      const response=await api("start",{symbol:$("symbol").value.trim(),interval:$("interval").value,days:Number($("days").value),mode:$("mode").value,provider:$("provider").value,feed:$("feed").value,fractional_shares:$("fractional").value==="yes",settings:{fee_rate:Number($("fee").value)/100,slippage_rate:Number($("slip").value)/100,half_spread:Number($("spread").value)/100,risk_per_trade:Number($("risk").value)/100,max_notional_fraction:Number($("allocation").value)/100,daily_loss_limit:Number($("lossLimit").value)/100}});
      notice(response.created?"Stock practice queued. Its progress and results will appear below.":"This exact stock practice request already exists; its saved result is shown below.");await refresh();
    } catch(e) {notice(e.message,true);} finally {bounds();}
  });
  document.addEventListener("click",async e=>{
    const b=e.target.closest("button[data-action]");if(!b) return;b.disabled=true;
    try {
      const action=b.dataset.action,id=b.dataset.id;
      if(["export","candles"].includes(action)) await download(action+"?id="+encodeURIComponent(id),"stock-"+action+"-"+id.slice(0,8)+".json");
      else {await api(action,{id});notice(action==="forward/start"?"Forward paper practice registered. Waiting for new completed stock candles.":"Stock practice updated.");await refresh();}
    } catch(e) {notice(e.message,true);} finally {b.disabled=false;}
  });
  $("exportForward").addEventListener("click",()=>download("forward/export","stock-forward-journal.json").catch(e=>notice(e.message,true)));
  refresh();setInterval(()=>{if(!document.hidden) refresh(false);},12000);
})();
