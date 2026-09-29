"use strict";
(() => {
  const $=id=>document.getElementById(id);
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const time=ts=>ts?new Date(ts).toLocaleString():"Not yet";
  const number=(v,d=2)=>Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:d}):"—";
  const percent=v=>Number.isFinite(v)?(v>0?"+":"")+number(v)+"%":"—";
  const labels={building:"Building interest",breakout:"Breakout observed",extended:"Already extended",quiet:"Quiet",unavailable:"Data unavailable"};
  let token=StockSession.getToken(), state=null, busy=false;
  function notice(message){$("notice").textContent=message;$("notice").hidden=!message;}
  async function api(action,body,blob=false){
    const options={headers:{}};if(token)options.headers.Authorization="Bearer "+token;
    if(body!==undefined){options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    try{return await StockSession.request("/api/crypto-watch/"+action,options,blob?"blob":"json");}
    catch(e){if(e.status===401){$("accessPanel").hidden=false;$("content").hidden=true;}throw e;}
  }
  function controls(){
    $("start").disabled=busy||!state||state.running||state.requires_token;
    $("stop").disabled=busy||!state?.enabled;$("export").disabled=busy||!state;
  }
  function render(){
    const bad=state.signals.filter(s=>s.stale||s.stage==="unavailable").length;
    $("watchState").textContent=state.running?(bad?"Watching · "+bad+" feeds pending or unavailable":"Watching"):
      state.enabled?"Watch needs attention":"Watch stopped";
    $("freshness").textContent="Last completed scan: "+time(state.last_scan_finished_ts)+" · Five-minute cadence";
    $("workerError").textContent=state.requires_token?"Configure APP_ACCESS_TOKEN on the server before starting.":state.worker_error||"";
    $("workerError").hidden=!$("workerError").textContent;controls();
    const cards=$("signals");cards.replaceChildren();
    for(const s of state.signals){
      const card=node("article",undefined,"watch-card"),heading=node("div",undefined,"watch-heading");
      heading.append(node("h3",s.symbol),node("span",s.stale&&s.observed_ts?"Stale observation":labels[s.stage],"watch-stage "+(s.stale?"stale":s.stage)));
      card.append(heading);
      const m=s.metrics,dl=node("dl");
      for(const [label,value] of [["Last closed price",Number.isFinite(m.price)?"$"+number(m.price,m.price<1?5:2):"—"],["Volume / baseline",Number.isFinite(m.relative_volume)?number(m.relative_volume)+"×":"—"],["15-minute change",percent(m.change_15m_pct)],["24-hour change",percent(m.change_24h_pct)],["Strength vs BTC",Number.isFinite(m.relative_btc_15m_pp)?number(m.relative_btc_15m_pp)+" pp":s.symbol==="BTC-USD"?"Benchmark":"—"]]){
        const item=node("div");item.append(node("dt",label),node("dd",value));dl.append(item);
      }
      card.append(dl);const reasons=node("ul");for(const reason of s.reasons)reasons.append(node("li",reason));card.append(reasons);
      card.append(node("p","Candle closed: "+time(s.candle_end_ts)+" · Observed: "+time(s.observed_ts),"muted"));
      if(s.initial_observation)card.append(node("p","Initial snapshot — does not establish early detection.","muted"));
      const a=node("a","Investigate with AI →");a.href="/agent?watch="+encodeURIComponent(s.symbol);card.append(a);cards.append(card);
    }
    const alerts=$("alerts");alerts.replaceChildren();
    if(!state.alerts.length)alerts.append(node("p","No qualifying observations recorded yet. Unavailable data is never counted as a quiet market.","muted"));
    for(const s of state.alerts){
      const article=node("article",undefined,"watch-observation");article.append(node("strong",s.symbol+" · "+labels[s.stage]),
        node("p","Observed: "+time(s.observed_ts)+" · Candle closed: "+time(s.candle_end_ts),"muted"),
        node("p",s.initial_observation?"Initial snapshot; this app may have started watching after the move began.":"Recorded while the watch was running."),node("p",s.reasons.join(" · ")));
      alerts.append(article);
    }
    const news=$("news");news.replaceChildren();
    $("newsStatus").textContent=state.news.source+" · Last retrieved: "+time(state.news.last_success_ts)+(state.news.error?" · Feed error: "+state.news.error:"");
    if(!state.news.items.length)news.append(node("p","No saved headlines. This does not establish that there is no relevant news.","muted"));
    for(const item of state.news.items){
      const article=node("article",undefined,"watch-news");let title=node("span",item.title);
      try{const u=new URL(item.url);if(["https:","http:"].includes(u.protocol)&&!u.username&&!u.password){title=node("a",item.title);title.href=u.href;title.target="_blank";title.rel="noopener noreferrer";}}catch(_){}
      article.append(title,node("p","Published: "+time(item.published_ts)+" · First observed revision: "+time(item.observed_ts)+" · "+item.assets.join(", "),"muted"));news.append(article);
    }
  }
  async function refresh(){try{state=await api("status");$("accessPanel").hidden=true;$("content").hidden=false;notice("");render();}catch(e){notice(e.message);}}
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();StockSession.setToken(token);await refresh();});
  for(const action of ["start","stop"]){$(action).addEventListener("click",async()=>{busy=true;controls();try{state=await api(action,{});notice("");render();}catch(e){notice(e.message);}finally{busy=false;controls();}});}
  $("export").addEventListener("click",async()=>{busy=true;controls();try{const blob=await api("export",undefined,true),url=URL.createObjectURL(blob),a=node("a");a.href=url;a.download="crypto-watch-observations.json";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notice(e.message);}finally{busy=false;controls();}});
  StockSession.poll(refresh,()=>!!state?.running,()=>!busy);
})();
