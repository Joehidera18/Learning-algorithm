"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = x => String(x == null ? "—" : x).replace(/[&<>"']/g,c=>({"&":"&","<":"<",">":">",'"':""","'":"&#39;"}[c]));
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const money = x => finite(x) ? new Intl.NumberFormat(undefined,{style:"currency",currency:"USD"}).format(x) : "—";
  const number = (x,d=2) => finite(x) ? x.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}) : "—";
  let token = sessionStorage.getItem("cryptoAccessToken") || "", state, refreshing = false;
  function notice(message,error=false) {$("notice").textContent=message;$("notice").hidden=false;$("notice").className="notice"+(error?" error":"");}
  async function api(action,body) {
    const options={credentials:"same-origin",headers:{}};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined) {options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    const response=await fetch("/api/strategy-lab/"+action,options);
    if(!response.ok) {
      if(response.status===401) $("accessPanel").hidden=false;
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
      const providers=cat.equity.providers;
      $("provider").innerHTML=Object.keys(providers).map(name=>'<option value="'+esc(name)+'"'+(providers[name].available?'':' disabled')+'>'+esc(name)+(providers[name].available?'':' · key missing')+'</option>').join("");
    }
    const provider=$("provider").value, decision=$("decision").value;
    const limit=cat.equity.providers[provider].max_days[decision];
    $("days").max=limit;
    $("hint").textContent=cat.equity.providers[provider].note+" Cap for "+decision+": "+limit+" days.";
    $("runButton").disabled=!cat.equity.providers[provider].available;
  }
  function render() {
    $("queueStatus").textContent=state.running?"A lab job is running.":"Idle.";
    $("jobs").innerHTML=state.jobs.length?state.jobs.map(job=>{
      const r=job.result, later=r&&r.later;
      let html='<article class="equity-job"><div class="job-summary"><div class="job-title"><h3>'+esc(job.request.strategy)+' · '+esc(job.request.symbol)+'</h3><span class="badge">'+esc(job.status)+'</span></div><p>'+esc(job.message)+'</p><p class="muted">'+esc(job.request.decision)+' · '+esc(job.request.provider)+(job.request.news?' · news filter':'')+'</p>';
      if(later) html+='<p>Later trades '+esc(later.trades)+' · net '+money(later.net_pnl)+' · mean R '+number(later.mean_r)+' · eligible '+esc(r.eligible_for_bot)+'</p>';
      return html+'</div></article>';
    }).join(""):'<div class="equity-empty"><strong>No lab runs yet.</strong>Start with SPY and orb_15m on 5-minute bars.</div>';
  }
  async function refresh(showError=true) {
    if(refreshing) return;
    refreshing=true;
    try {
      state=await api("status");
      $("accessPanel").hidden=true;$("content").hidden=false;
      setup();render();
    } catch(e) {if(showError) notice(e.message,true);} finally {refreshing=false;}
  }
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();sessionStorage.setItem("cryptoAccessToken",token);await refresh();});
  $("provider").addEventListener("change",setup);$("decision").addEventListener("change",setup);
  $("refresh").addEventListener("click",()=>refresh());
  $("labForm").addEventListener("submit",async e=>{
    e.preventDefault();$("runButton").disabled=true;
    try {
      await api("start",{strategy:$("strategy").value,symbol:$("symbol").value.trim().toUpperCase(),decision:$("decision").value,context:$("context").value,days:Number($("days").value),provider:$("provider").value,news:$("news").value==="yes"});
      notice("Strategy lab queued.");await refresh();
    } catch(err) {notice(err.message,true);} finally {setup();}
  });
  refresh();setInterval(()=>{if(!document.hidden) refresh(false);},8000);
})();
