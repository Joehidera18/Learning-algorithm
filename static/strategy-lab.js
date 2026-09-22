"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = x => String(x == null ? "—" : x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const money = x => finite(x) ? new Intl.NumberFormat(undefined,{style:"currency",currency:"USD"}).format(x) : "—";
  const number = (x,d=2) => finite(x) ? x.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
  let token = StockSession.getToken(), state, refreshing = false;
  function notice(message,error=false) {$("notice").textContent=message;$("notice").hidden=false;$("notice").className="notice"+(error?" error":"");}
  async function api(action,body) {
    const options={credentials:"same-origin",headers:{}};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined) {options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    const response=await fetch("/api/strategy-lab/"+action,options);
    if(!response.ok) {
      if(response.status===401) {$("accessPanel").hidden=false;$("content").hidden=true;}
      let message="Request failed ("+response.status+")";
      try {message=(await response.json()).error || message;} catch(_) {}
      throw Error(message);
    }
    return response.json();
  }
  function setup() {
    const cat=state.catalog;
    if(!$("strategy").options.length) {
      $("strategy").innerHTML=(cat.strategies||[]).map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join("");
      $("strategy").value="orb_15m";
      const requested=new URLSearchParams(location.search).get("symbol");
      if(requested && /^[A-Z]{1,5}([.\-][A-Z])?$/.test(requested)) $("symbol").value=requested;
      const providers=cat.equity.providers;
      $("provider").innerHTML=Object.keys(providers).map(name=>'<option value="'+esc(name)+'"'+(providers[name].available?'':' disabled')+'>'+esc(name)+(providers[name].available?'':' · key missing')+'</option>').join("");
    }
    const allowed=cat.strategy_intervals[$("strategy").value];
    for(const option of $("decision").options) option.disabled=!allowed.includes(option.value);
    if(!allowed.includes($("decision").value)) $("decision").value=allowed.includes("5m")?"5m":allowed[0];
    const provider=$("provider").value, decision=$("decision").value;
    const limit=cat.equity.providers[provider].max_days[decision];
    $("days").max=limit;
    if(Number($("days").value)>limit) $("days").value=limit;
    $("hint").textContent=cat.equity.providers[provider].note+" Cap for "+decision+": "+limit+" days.";
    $("runButton").disabled=!cat.equity.providers[provider].available;
  }
  function render() {
    $("queueStatus").textContent=state.running?"A lab job is running.":"Idle.";
    $("jobs").innerHTML=state.jobs.length?state.jobs.map(job=>{
      const r=job.result, later=r&&r.later;
      let html='<article class="equity-job"><div class="job-summary"><div class="job-title"><h3>'+esc(job.request.strategy)+' · '+esc(job.request.symbol)+'</h3><span class="badge">'+esc(job.status)+'</span></div><p>'+esc(job.message)+'</p><p class="muted">'+esc(job.request.decision)+' · '+esc(job.request.provider)+(job.request.news?' · news filter':'')+'</p>';
      if(later) {
        const verified=r.report_version===2 && later.complete===true && r.later_higher_cost && r.later_higher_cost.complete===true;
        html+='<p>Later trades '+esc(later.trades)+' · net '+money(verified?later.net_pnl:null)+' · mean R '+number(verified?later.mean_r:null)+' · eligible '+esc(verified?r.eligible_for_bot:false)+'</p>';
        if(!verified) html+='<p class="muted">'+esc(r.report_version===2?(later.incomplete_reason || 'Incomplete comparison. Eligibility is unavailable.'):'Earlier report: rerun with the corrected backtester to verify this result.')+'</p>';
      }
      if(["queued","running"].includes(job.status)) html+='<button class="small" data-cancel="'+esc(job.id)+'">Cancel backtest</button>';
      return html+'</div></article>';
    }).join(""):'<div class="equity-empty"><strong>No lab runs yet.</strong>Start with SPY and orb_15m on 5-minute bars.</div>';
  }
  async function refresh(showError=true) {
    if(refreshing) return;
    refreshing=true;
    try {
      const next=await api("status");
      if(next.error) throw Error(next.error);
      state=next;
      $("accessPanel").hidden=true;$("content").hidden=false;
      setup();render();
    } catch(e) {if(showError) notice(e.message,true);} finally {refreshing=false;}
  }
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();StockSession.setToken(token);await refresh();});
  $("provider").addEventListener("change",setup);$("decision").addEventListener("change",setup);$("strategy").addEventListener("change",setup);
  $("refresh").addEventListener("click",()=>refresh());
  $("jobs").addEventListener("click",async e=>{
    const button=e.target.closest("button[data-cancel]");if(!button) return;
    button.disabled=true;
    try {await api("cancel",{id:button.dataset.cancel});await refresh();}
    catch(error) {notice(error.message,true);}
    finally {button.disabled=false;}
  });
  $("labForm").addEventListener("submit",async e=>{
    e.preventDefault();$("runButton").disabled=true;
    try {
      await api("start",{strategy:$("strategy").value,symbol:$("symbol").value.trim().toUpperCase(),decision:$("decision").value,context:$("context").value,days:Number($("days").value),provider:$("provider").value,news:$("news").value==="yes"});
      notice("Strategy lab queued.");await refresh();
    } catch(err) {notice(err.message,true);} finally {setup();}
  });
  refresh();setInterval(()=>{if(!document.hidden) refresh(false);},8000);
})();
