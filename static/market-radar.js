"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const node = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const time = ts => ts ? new Date(ts).toLocaleString() : "Not yet";
  const pct = v => Number.isFinite(v) ? (v>0?"+":"")+v.toFixed(2)+"%" : "—";
  const money = v => Number.isFinite(v) ? "$"+v.toLocaleString(undefined,{maximumFractionDigits:v<1?5:2}) : "—";
  const labels = {large_move:"Large move already observed",momentum_change:"Momentum changed",quiet:"No price threshold met",unavailable:"Data unavailable",market_closed:"Regular session closed"};
  let token=StockSession.getToken(),state=null,busy=false,initialized=false,epoch=0;
  function notice(message=""){ $("notice").textContent=message;$("notice").hidden=!message; }
  function link(title,url){const a=node("a",title);try{const u=new URL(url);if(u.protocol!=="https:"||u.username||u.password)throw Error();a.href=u.href;a.target="_blank";a.rel="noopener noreferrer";}catch(_){return node("span",title);}return a;}
  function tag(text,warning=false){return node("span",text,"radar-tag"+(warning?" warning":""));}
  function selected(item){const s=$("assetFilter").value;return !s||item.symbol===s||item.assets?.includes(s)||item.assets?.includes("*");}
  function controls(){
    $("start").disabled=busy||!state||state.running||state.requires_token;
    $("stop").disabled=busy||!state?.enabled;
    $("export").disabled=busy||!state;
    $("cryptoStart").disabled=busy||!state?.crypto_watch||state.crypto_watch.running||state.requires_token;
    for(const form of [$("catalystForm"),$("trackingForm")]) for(const button of form.querySelectorAll("button"))button.disabled=busy||state?.requires_token;
  }
  async function api(action,body,blob=false){
    const options={headers:{}};if(token)options.headers.Authorization="Bearer "+token;
    if(body!==undefined){options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    const path=action==="crypto/start"?"/api/crypto-watch/start":"/api/market-radar/"+action;
    try{return await StockSession.request(path,options,blob?"blob":"json");}
    catch(e){if(e.status===401){$("accessPanel").hidden=false;$("content").hidden=true;}throw e;}
  }
  function populate(){
    for(const item of state.watchlist){
      for(const id of ["assetFilter","trackingSymbol","eventSymbol"]){const option=node("option",item.symbol+" · "+item.name);option.value=item.symbol;$(id).append(option);}
    }
    $("trackingSymbol").value="HBAR-USD";loadTracking();initialized=true;
  }
  function loadTracking(){
    const item=state.watchlist.find(w=>w.symbol===$("trackingSymbol").value);if(!item)return;
    $("trackingMode").value=item.mode;$("trackingNote").value=item.note;
    $("trackingSaved").textContent=item.updated_ts?"Saved: "+time(item.updated_ts):"No personal notes saved yet.";
  }
  function editEvent(item){
    $("eventId").value=item?.id||"";$("eventVersion").value=item?.version||0;
    $("eventSymbol").value=item?.symbol||$("assetFilter").value||"HBAR-USD";
    $("eventTitle").value=item?.title||"";$("eventDate").value=item?.date||"";$("eventTime").value=item?.time_utc||"";
    $("eventStatus").value=item?.status||"scheduled";$("eventSource").value=item?.source_url||"";$("eventNote").value=item?.note||"";
    $("calendarEditor").open=true;$("eventTitle").focus();
  }
  function render(){
    if(!initialized)populate();
    $("radarState").textContent=state.running?"Radar running":state.enabled?"Radar needs attention":"Radar stopped";
    $("freshness").textContent="Last completed scan: "+time(state.last_scan_finished_ts);
    $("workerError").textContent=state.requires_token?"Set APP_ACCESS_TOKEN on the server to enable controls.":state.worker_error||"";
    $("workerError").hidden=!$("workerError").textContent;
    $("assetCount").textContent=state.watch_count;$("sourceCount").textContent=state.source_issues;
    $("dueCount").textContent=state.calendar.filter(c=>c.upcoming).length;
    $("coverageNote").textContent=state.source_issues?state.source_issues+" feeds need attention. Open source health below; missing data is not a quiet market.":"Feeds fetched recently. Coverage remains partial; verify the primary announcement.";
    $("investigate").href="/agent?radar="+encodeURIComponent($("assetFilter").value||"HBAR-USD");
    const sold=$("soldAssets");sold.replaceChildren();for(const w of state.watchlist.filter(w=>w.mode==="recently_sold"))sold.append(tag(w.symbol+" · still watched"));
    const calendar=$("calendar");calendar.replaceChildren();
    const events=state.calendar.filter(selected);
    if(!events.length)calendar.append(node("p","No sourced event recorded for this selection. This does not mean no events are scheduled.","muted"));
    for(const item of events.slice(0,10)){
      const card=node("article",undefined,"radar-item"),tags=node("div",undefined,"radar-tags");
      tags.append(tag(item.symbol),tag(item.status),tag(item.date+(item.time_utc?" · "+item.time_utc+" UTC":" · time unspecified")));
      if(item.upcoming)tags.append(tag("Approaching",true));if(item.past_due)tags.append(tag("Date passed · verify outcome",true));
      if(item.needs_source_check)tags.append(tag("Source needs review",true));
      card.append(tags,node("h3",item.title),node("p",item.note),link("Review source ↗",item.source_url),
        node("p",item.origin+" · Recorded: "+time(item.recorded_ts)+" · Revision "+item.version,"radar-meta"));
      const button=node("button","Edit / reschedule","small");button.type="button";button.addEventListener("click",()=>editEvent(item));card.append(button);calendar.append(card);
    }
    const news=$("news");news.replaceChildren();const matching=state.news.filter(selected);
    const headlines=matching.filter(n=>$("showReprints").checked||(!n.possible_reprint&&!n.timestamp_only_update));
    $("newsHidden").textContent=(matching.length-headlines.length)?(matching.length-headlines.length)+" possible repeats hidden. They remain in the export.":"";
    if(!headlines.length)news.append(node("p","No saved matching headlines. Check source health and use AI research to look for missing evidence.","muted"));
    for(const item of headlines.slice(0,20)){
      const card=node("article",undefined,"radar-item"),tags=node("div",undefined,"radar-tags");
      tags.append(tag(item.assets.join(", ")),tag(item.origin+" · "+item.category));
      for(const [key,label] of [["initial_snapshot","Initial snapshot"],["after_coverage_gap","Found after a coverage gap"],["late_discovery","Late discovery"],["revised","Updated item"],["timestamp_only_update","Feed text unchanged · timestamp update"],["possible_reprint","Possible reprint · not independent confirmation"]])if(item[key])tags.append(tag(label,true));
      const title=node("h3");title.append(link(item.title,item.url));
      card.append(tags,title,node("p","Published: "+time(item.published_ts)+" · Publisher update: "+time(item.updated_ts)+" · App first saw this revision: "+time(item.observed_ts),"radar-meta"));news.append(card);
    }
    const conn=state.stock_connection;$("stockFeed").textContent=(conn.feed||"iex").toUpperCase()+" · "+conn.coverage;
    $("stockConnection").textContent=!conn.configured?"Stock observations need Alpaca market-data keys in Render: ALPACA_API_KEY and ALPACA_SECRET_KEY. News and the calendar work without them.":conn.error||"Last observation batch: "+time(conn.last_success_ts)+". Prices refresh on scans, not every tick.";
    const prices=$("stockPrices");prices.replaceChildren();
    for(const p of state.stock_prices.filter(selected)){
      const card=node("article",undefined,"price-card");card.append(node("strong",p.symbol),node("p",money(p.price)+" · "+pct(p.change_pct),"price-number"),
        node("p",p.connection_error?"Connection failed; last saved data only":p.stale&&p.stage!=="market_closed"?"Stale / unavailable observation":labels[p.stage]),node("p",p.reason),node("p","Quote: "+time(p.quote_ts)+" · Observed: "+time(p.observed_ts),"muted"));prices.append(card);
    }
    const crypto=state.crypto_watch;
    $("cryptoState").textContent=crypto?(crypto.running?"Crypto watch running":"Crypto watch stopped or needs attention")+" · Last completed scan: "+time(crypto.last_scan_finished_ts):"Crypto watch not available";
    const alerts=$("alerts");alerts.replaceChildren();const journal=state.alerts.filter(a=>selected(a.item));
    if(!journal.length)alerts.append(node("p","No journal entries yet. Old headlines on the first news scan are not new alerts.","muted"));
    for(const a of journal.slice(0,12)){
      const p=a.item,card=node("article",undefined,"radar-item");
      card.append(tag(a.kind),node("h3",p.title||p.symbol+" · "+labels[p.stage]),node("p","App observed: "+time(a.observed_ts),"radar-meta"));
      if(a.superseded)card.append(tag("Historical calendar revision · no longer current",true));
      if(p.initial_observation)card.append(tag("Initial price snapshot · not early detection",true));
      if(p.after_coverage_gap)card.append(tag("Found after a coverage gap",true));
      if(a.kind==="calendar")card.append(node("p",p.date+" · "+(p.time_utc?p.time_utc+" UTC":"Time unspecified")+" · "+p.status));
      if(a.kind==="price")card.append(node("p",p.reason));
      if(p.url||p.source_url)card.append(link("Source ↗",p.url||p.source_url));alerts.append(card);
    }
    const sources=$("sources");sources.replaceChildren();
    for(const s of state.sources){
      const card=node("article",undefined,"radar-item");card.append(node("strong",s.name),node("p",s.error||(s.stale?"No recent successful fetch":"Fetched recently; partial coverage"),s.error||s.stale?"radar-warning":"muted"),
        node("p","Attempt: "+time(s.attempt_ts)+" · Success: "+time(s.success_ts)+" · Matched: "+(s.matched_items??"—")+" · Rejected entries: "+(s.rejected_items??"—"),"radar-meta"),link("Feed source ↗",s.url));sources.append(card);
    }
    controls();
  }
  async function refresh(){const ticket=++epoch;try{const value=await api("status");if(ticket!==epoch)return;state=value;$("accessPanel").hidden=true;$("content").hidden=false;render();}catch(e){if(ticket===epoch)notice(e.message);}}
  async function change(action,body,success){busy=true;++epoch;controls();try{const value=await api(action,body);state=action==="crypto/start"?await api("status"):value;notice(success||"");render();return true;}catch(e){notice(e.message);return false;}finally{busy=false;controls();}}
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();StockSession.setToken(token);notice();await refresh();});
  $("assetFilter").addEventListener("change",render);$("trackingSymbol").addEventListener("change",loadTracking);
  $("showReprints").addEventListener("change",render);
  $("start").addEventListener("click",()=>change("start",{}));$("stop").addEventListener("click",()=>change("stop",{}));
  $("cryptoStart").addEventListener("click",()=>change("crypto/start",{}));
  $("addCatalyst").addEventListener("click",()=>editEvent(null));$("cancelEdit").addEventListener("click",()=>$("calendarEditor").open=false);
  $("trackingForm").addEventListener("submit",async e=>{e.preventDefault();if(await change("tracking",{symbol:$("trackingSymbol").value,mode:$("trackingMode").value,note:$("trackingNote").value},"Watch notes saved. This asset remains covered."))loadTracking();});
  $("catalystForm").addEventListener("submit",async e=>{e.preventDefault();const body={id:$("eventId").value,version:Number($("eventVersion").value),symbol:$("eventSymbol").value,title:$("eventTitle").value,date:$("eventDate").value,time_utc:$("eventTime").value,status:$("eventStatus").value,source_url:$("eventSource").value,note:$("eventNote").value};if(await change("catalyst",body,"Catalyst saved with its source and revision history."))$("calendarEditor").open=false;});
  $("export").addEventListener("click",async()=>{busy=true;controls();try{const blob=await api("export",undefined,true),url=URL.createObjectURL(blob),a=node("a");a.href=url;a.download="market-radar-journal.json";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notice(e.message);}finally{busy=false;controls();}});
  StockSession.poll(refresh,()=>!!state?.running,()=>!busy);
})();
