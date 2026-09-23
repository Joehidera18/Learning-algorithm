"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = x => String(x ?? "—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const money = x => finite(x) ? new Intl.NumberFormat(undefined,{style:"currency",currency:"USD"}).format(x) : "—";
  const number = (x,d=2) => finite(x) ? x.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
  const pct = x => finite(x) ? number(x)+"%" : "—";
  const when = x => x ? new Date(x).toLocaleString(undefined,{timeZone:"America/New_York",timeZoneName:"short"}) : "Not recorded";
  let token = StockSession.getToken(), state, initialized=false, refreshing=false, lastJobs="";
  const reports=new Map(), reportRequests=new Map(), openJournals=new Map();
  function notice(message,error=false) {$("notice").textContent=message;$("notice").hidden=!message;$("notice").className="notice"+(error?" error":"");}
  async function api(action,body,blob=false) {
    const options={headers:{}};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined) {options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    try {return await StockSession.request("/api/strategy-lab/"+action,options,blob?"blob":"json",blob || action.startsWith("report")?60000:20000);}
    catch(error) {
      if(error.status===401) {$("accessPanel").hidden=false;$("content").hidden=true;}
      throw error;
    }
  }
  function setup() {
    if(!state) return;
    const cat=state.catalog;
    if(!initialized) {
      $("strategy").innerHTML=(cat.strategies||[]).map(s=>'<option value="'+esc(s)+'">'+esc(cat.strategy_details[s].title)+'</option>').join("");
      $("strategy").value="orb_15m";
      $("tickerList").innerHTML=cat.equity.symbols.map(s=>'<option value="'+esc(s)+'"></option>').join("");
      const requested=new URLSearchParams(location.search).get("symbol");
      if(requested && /^[A-Z]{1,5}([.\-][A-Z])?$/.test(requested)) $("symbol").value=requested;
      const providers=cat.equity.providers;
      $("provider").innerHTML=Object.keys(providers).map(name=>'<option value="'+esc(name)+'"'+(providers[name].available?'':' disabled')+'>'+esc(name)+(providers[name].available?'':' · key missing')+'</option>').join("");
      $("endDate").max=new Date().toISOString().slice(0,10);
      initialized=true;
    }
    const spec=cat.strategy_details[$("strategy").value];
    $("strategyTitle").textContent=spec.title;
    $("strategyDescription").textContent=spec.description;
    const allowed=cat.strategy_intervals[$("strategy").value];
    for(const option of $("decision").options) option.disabled=!allowed.includes(option.value);
    if(!allowed.includes($("decision").value)) $("decision").value=allowed.includes("5m")?"5m":allowed[0];
    for(const option of $("mode").options) option.disabled=!spec.modes.includes(option.value);
    if(!spec.modes.includes($("mode").value)) $("mode").value=spec.modes[0];
    const newsAllowed=spec.news_filter && cat.equity.providers.massive.available;
    $("news").querySelector('[value="yes"]').disabled=!newsAllowed;
    if(!newsAllowed) $("news").value="no";
    const provider=cat.equity.providers[$("provider").value],decision=$("decision").value;
    const limit=provider.max_days[decision];
    $("days").max=limit;
    if(Number($("days").value)>limit) $("days").value=limit;
    $("hint").textContent=provider.note+" Maximum request for "+decision+": "+limit+" calendar days. The report shows the candles actually received.";
    $("runButton").disabled=!provider.available;
  }
  function action(kind,id,label) {return '<button class="small" data-action="'+kind+'" data-id="'+esc(id)+'">'+esc(label)+'</button>';}
  function journal(id,windowName="later") {
    const report=reports.get(id);
    if(!report) return '<p class="backtest-loader">'+(openJournals.has(id)?'Loading trade journal…':'Open the trade journal to load it.')+'</p>';
    const windows={later:"Later period",development:"Development period",later_higher_cost:"Later · 1.5× costs"};
    const trades=report.trade_journal?.[windowName] || [],visible=trades.slice(-100);
    let html='<label>Journal window<select data-journal-window="'+esc(id)+'">'+Object.entries(windows).map(([key,label])=>'<option value="'+key+'"'+(key===windowName?' selected':'')+'>'+label+'</option>').join("")+'</select></label>';
    html+='<p class="backtest-window">'+number(trades.length,0)+' simulated exits'+(trades.length>100?' · Showing the most recent 100; export includes every trade.':'.')+' Prices and times below are simulated fills. “Boundary mark” is a test-end valuation.</p>';
    if(!visible.length) return html+'<p>No simulated exits in this window. Inspect the signal checks below for rejected entries.</p>';
    return html+'<div class="result-table"><table><thead><tr><th>Entry (New York)</th><th>Exit (New York)</th><th>Shares at entry</th><th>Entry → exit</th><th>Net P/L</th><th>Fees</th><th>Exit reason</th></tr></thead><tbody>'+visible.map(t=>'<tr><td>'+esc(when(t.entry_ts))+'</td><td>'+esc(when(t.exit_time_ts || t.exit_ts))+'</td><td>'+number(t.actual_entry_shares ?? t.qty_initial,4)+'</td><td>'+money(t.entry)+' → '+money(t.exit)+'</td><td>'+money(t.pnl)+'</td><td>'+money(t.fees_paid)+'</td><td>'+esc(t.reason==='END'?'Boundary mark':t.reason)+'</td></tr>').join("")+'</tbody></table></div><p class="backtest-window">The exit price is the final exit. P/L includes any partial exits and their costs; the full report records total realized P/L and fees.</p>';
  }
  function result(job) {
    const r=job.result;
    if(!r) return "";
    const current=r.report_version===state.catalog.report_version && !r.requires_rerun;
    const later=r.later || {},stress=r.later_higher_cost || {};
    const verified=current && later.complete===true && stress.complete===true;
    let outcome;
    if(!current) outcome="Earlier report: rerun with the corrected backtester to verify this result.";
    else if(!verified) outcome="Incomplete comparison · "+(later.incomplete_reason || stress.incomplete_reason || "Account performance cannot be verified.");
    else if(later.trades<20 || stress.trades<20) outcome="Too few resolved trades to establish an edge. At least 20 are required in each later test.";
    else if(r.eligible_for_bot) outcome="Passed the historical screen · eligible for further paper research. Future profit is unproven.";
    else outcome="Did not pass the historical screen. Later P/L and mean R must both stay positive at standard and higher costs.";
    let html='<div class="backtest-result"><p class="backtest-outcome'+(verified && r.eligible_for_bot?' review':'')+'">'+esc(outcome)+'</p>';
    html+='<div class="backtest-metrics">'+[[money(verified?later.net_pnl:null),"Later net P/L"],[pct(verified?later.return_pct:null),"Later return"],[pct(verified?later.max_drawdown_pct:null),"Maximum drawdown"],[number(current?later.trades:null,0),"Resolved later trades"]].map(([value,label])=>'<div><strong>'+esc(value)+'</strong><span>'+esc(label)+'</span></div>').join("")+'</div>';
    if(current) {
      html+='<p class="backtest-window">Later window: '+esc(when(later.start_ts))+' → '+esc(when(later.end_ts))+' · Each comparison starts at '+money(r.starting_balance)+'.</p><div class="result-table"><table><thead><tr><th>Test window</th><th>Net P/L</th><th>Return</th><th>Drawdown</th><th>Win rate</th><th>Resolved trades</th><th>Mean R</th><th>Fees</th></tr></thead><tbody>';
      for(const [label,m] of [["Development",r.development],["Later",later],["Later · 1.5× costs",stress]]) {
        const q=m?.complete?m:{};
        html+='<tr><td>'+label+(m?.complete?'':' · incomplete')+'</td><td>'+money(q.net_pnl)+'</td><td>'+pct(q.return_pct)+'</td><td>'+pct(q.max_drawdown_pct)+'</td><td>'+pct(q.win_rate)+'</td><td>'+number(m?.trades,0)+'</td><td>'+number(q.mean_r)+'</td><td>'+money(q.fees_paid)+'</td></tr>';
      }
      html+='</tbody></table></div>';
      const coverage=r.requested_coverage || {},observed=r.coverage || {};
      html+='<p class="backtest-source">Requested session coverage: '+pct(coverage.coverage_pct)+' · '+number(coverage.missing_candles,0)+' scheduled candles missing · '+number(coverage.observed_candles ?? observed.rows,0)+' observed candles. Missing boundary coverage is shown separately from gaps within the observed data.</p>';
      html+='<p class="backtest-source">Data: '+esc(job.request.provider)+' · '+esc(r.market_data?.adjustment || "Adjustment metadata not recorded")+'. '+number(later.window_end_exits,0)+' later exits were boundary marks.</p>';
      html+='<div class="backtest-actions">'+action("journal",job.id,openJournals.has(job.id)?"Hide trade journal":"View trade journal")+action("export",job.id,"Export full backtest")+'</div><section data-journal="'+esc(job.id)+'"'+(openJournals.has(job.id)?'':' hidden')+'>'+journal(job.id,openJournals.get(job.id))+'</section>';
      html+='<details data-diagnostics="'+esc(job.id)+'"><summary>Signal checks, costs and data coverage</summary><pre class="backtest-diagnostics">'+esc(JSON.stringify({costs:r.costs,market_data:r.market_data,requested_coverage:r.requested_coverage,observed_coverage:r.coverage,later:later.signal_funnel,higher_cost:stress.signal_funnel},null,2))+'</pre></details>';
    } else html+='<div class="backtest-actions">'+action("summary",job.id,"Export saved summary")+'</div>';
    return html+'</div>';
  }
  function render() {
    $("queueStatus").textContent=state.pending_jobs?state.pending_jobs+" backtest(s) queued or running. Research jobs share one worker slot; progress updates appear below.":"Saved historical tests · No live orders.";
    const signature=JSON.stringify(state.jobs);
    if(signature===lastJobs) return;
    lastJobs=signature;
    const opened=new Set([...document.querySelectorAll("details[data-diagnostics][open]")].map(e=>e.dataset.diagnostics));
    $("jobs").innerHTML=state.jobs.length?state.jobs.map(job=>{
      const req=job.request,title=state.catalog.strategy_details[req.strategy]?.title || req.strategy;
      let html='<article class="equity-job"><div class="job-summary"><div class="job-title"><h3>'+esc(req.symbol)+' · '+esc(title)+'</h3><span class="badge">'+esc(job.status)+'</span></div><p>'+esc(job.message)+'</p><p class="muted">'+esc(req.decision)+' candles · '+esc(req.days)+' calendar days · '+esc(req.mode || "day")+' trading · '+esc(req.provider)+(req.news?' · news filter':'')+' · '+esc(req.end_date?'before '+req.end_date+' UTC':'cutoff '+when(req.cutoff_ts))+'</p>';
      if(["queued","running"].includes(job.status)) html+=action("cancel",job.id,"Cancel backtest");
      return html+'</div>'+result(job)+'</article>';
    }).join(""):'<div class="equity-empty"><strong>Your first backtest starts here.</strong>Try SPY and the 15-minute opening-range breakout on 5-minute candles. Results may be negative or inconclusive.</div>';
    for(const details of document.querySelectorAll("details[data-diagnostics]")) details.open=opened.has(details.dataset.diagnostics);
  }
  async function refresh(showError=true) {
    if(refreshing) return;
    refreshing=true;
    try {
      const next=await api("status");
      if(next.error) throw Error(next.error);
      state=next;$("accessPanel").hidden=true;$("content").hidden=false;
      setup();render();
      if($("notice").classList.contains("error")) notice("");
    } catch(error) {if(showError) notice(error.message,true);} finally {refreshing=false;}
  }
  async function loadReport(id) {
    if(reports.has(id)) return reports.get(id);
    if(!reportRequests.has(id)) reportRequests.set(id,api("report?id="+encodeURIComponent(id))
      .then(report=>{reports.set(id,report);return report;}).finally(()=>reportRequests.delete(id)));
    return reportRequests.get(id);
  }
  $("accessForm").addEventListener("submit",async event=>{event.preventDefault();token=$("accessToken").value.trim();StockSession.setToken(token);await refresh();});
  for(const id of ["provider","decision","strategy"]) $(id).addEventListener("change",setup);
  $("symbol").addEventListener("input",()=>{$("symbol").value=$("symbol").value.toUpperCase();});
  $("refresh").addEventListener("click",()=>refresh());
  $("jobs").addEventListener("change",event=>{
    const id=event.target.dataset.journalWindow;
    if(id) {openJournals.set(id,event.target.value);event.target.closest("[data-journal]").innerHTML=journal(id,event.target.value);}
  });
  $("jobs").addEventListener("click",async event=>{
    const button=event.target.closest("button[data-action]");if(!button) return;
    button.disabled=true;
    const id=button.dataset.id,kind=button.dataset.action;
    try {
      if(kind==="cancel") {await api("cancel",{id});await refresh();}
      else if(kind==="journal") {
        const panel=button.closest(".backtest-result").querySelector("[data-journal]");
        if(openJournals.has(id)) {openJournals.delete(id);panel.hidden=true;button.textContent="View trade journal";}
        else {
          openJournals.set(id,"later");panel.hidden=false;panel.textContent="Loading trade journal…";button.textContent="Hide trade journal";
          try {
            await loadReport(id);
            const current=[...document.querySelectorAll("[data-journal]")].find(el=>el.dataset.journal===id);
            if(current && openJournals.has(id)) current.innerHTML=journal(id,openJournals.get(id));
          } catch(error) {
            openJournals.delete(id);
            const current=[...document.querySelectorAll("[data-journal]")].find(el=>el.dataset.journal===id);
            if(current) {current.hidden=false;current.textContent=error.message;}
            const retry=[...document.querySelectorAll('[data-action="journal"]')].find(el=>el.dataset.id===id);
            if(retry) retry.textContent="Retry trade journal";
            throw error;
          }
        }
      } else if(kind==="export" || kind==="summary") {
        const blob=await api((kind==="export"?"report/export":"export")+"?id="+encodeURIComponent(id),undefined,true);
        const url=URL.createObjectURL(blob),link=document.createElement("a");
        link.href=url;link.download="stock-backtest-"+id+".json";document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }
    } catch(error) {notice(error.message,true);} finally {button.disabled=false;}
  });
  $("labForm").addEventListener("submit",async event=>{
    event.preventDefault();$("runButton").disabled=true;
    try {
      await api("start",{strategy:$("strategy").value,symbol:$("symbol").value.trim().toUpperCase(),decision:$("decision").value,context:$("context").value,days:Number($("days").value),provider:$("provider").value,news:$("news").value==="yes",starting_balance:Number($("balance").value),mode:$("mode").value,fractional_shares:$("fractional").value==="yes",end_date:$("endDate").value || null,settings:{fee_rate:Number($("fee").value)/100,slippage_rate:Number($("slip").value)/100,half_spread:Number($("spread").value)/100,risk_per_trade:Number($("risk").value)/100,max_notional_fraction:Number($("allocation").value)/100,daily_loss_limit:Number($("lossLimit").value)/100}});
      notice("Stock backtest queued. You can leave this page; the server keeps working.");await refresh();
    } catch(error) {notice(error.message,true);} finally {setup();}
  });
  StockSession.poll(()=>refresh(),()=>!!state?.pending_jobs,()=>$("accessPanel").hidden);
})();
