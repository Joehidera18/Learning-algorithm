"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const node = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  let token=StockSession.getToken(), status, threadId=null, runs=[], submitting=false, refreshing=false, pending=null, lastRender="", loadedThreadKey="";
  const readSession=key=>{try{return sessionStorage.getItem(key);}catch(_){return null;}};
  const saveSession=(key,value)=>{try{if(value===null)sessionStorage.removeItem(key);else sessionStorage.setItem(key,value);}catch(_){}};
  threadId=readSession("stockAgentThread");
  try {pending=JSON.parse(readSession("stockAgentPending") || "null");} catch(_) {}
  const watchRequest=new URLSearchParams(location.search).get("watch");
  const watchSymbols=new Set(["HBAR-USD","BTC-USD","ETH-USD","SOL-USD","XRP-USD","XLM-USD","LINK-USD","ADA-USD","DOGE-USD","AVAX-USD","LTC-USD","BCH-USD"]);
  const fromWatch=watchSymbols.has(watchRequest)&&!pending;
  const presets={
    stocks:"Research 5 emerging public companies in quantum computing, gene editing, medicine or AI with a plausible catalyst in the next 12 months. Prefer smaller businesses. Compare primary sources, cash runway, dilution, competition and valuation. Separate confirmed milestones from management targets. Explain the strongest bear case for each and what evidence would change your view. Do not promise returns.",
    crypto:"Research 5 cryptoassets with a credible growth thesis over the next year. Read current sources and look for contrary evidence. Compare adoption, token value capture, circulating and fully diluted valuation, unlock schedules, liquidity, security and concentration. Distinguish an interesting network from an attractive investment. Give dated catalysts and failure conditions, not guaranteed winners.",
    evidence:"Read our workspace and strategy notebook. Find recent completed backtests and learning results. Explain what held up on later data at higher costs, what failed, and where missing candles or small samples prevent conclusions. Suggest the most useful next test.",
    strategy:"Read our workspace, strategy notebook and supported backtest options. Choose two supported stock strategy tests that would answer a useful question. Run them if allowed, inspect their later-period and higher-cost results when complete, and save a grounded lesson with a next hypothesis. If tests are still running, give their IDs and explain what remains unknown."
  };
  function notice(message,error=false){$("notice").textContent=message;$("notice").hidden=!message;$("notice").className="notice"+(error?" error":"");}
  async function api(action,body,blob=false){
    const options={headers:{}};
    if(token) options.headers.Authorization="Bearer "+token;
    if(body!==undefined){options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
    try{return await StockSession.request("/api/agent/"+action,options,blob?"blob":"json");}
    catch(error){if(error.status===401){$("accessPanel").hidden=false;$("content").hidden=true;}throw error;}
  }
  function setThread(id){threadId=id;saveSession("stockAgentThread",id);lastRender="";loadedThreadKey="";}
  function savePending(value){pending=value;saveSession("stockAgentPending",value?JSON.stringify(value):null);$("retrySubmission").hidden=!value;}
  function link(text,url){const a=node("a",text);try{const u=new URL(url,location.origin);if(!["https:","http:"].includes(u.protocol)||u.username||u.password)return node("span",text);a.href=u.href;if(u.origin!==location.origin){a.target="_blank";a.rel="noopener noreferrer";}}catch(_){return node("span",text);}return a;}
  function syncControls(){
    const busy=!!status?.active || submitting;
    $("send").disabled=!status?.configured || busy || !!pending;
    $("send").textContent=submitting?"Starting…":busy?"Research in progress":"Start research";
    $("retrySubmission").hidden=!pending;$("retrySubmission").disabled=submitting;
    $("progressPanel").hidden=!status?.active;
    $("progress").textContent=status?.active?.progress || "";
    $("modelLabel").textContent=status?status.model+" · "+status.daily_used+" / "+status.daily_limit+" requests today":"";
    $("deleteChat").hidden=!threadId;$("deleteChat").disabled=submitting || !!pending || status?.active?.thread_id===threadId;
    $("newChat").disabled=submitting || !!pending;
  }
  function renderThreads(){
    $("threads").replaceChildren();
    for(const t of status.threads){const b=node("button",t.title);b.type="button";b.setAttribute("aria-current",String(t.id===threadId));b.disabled=submitting||!!pending;b.addEventListener("click",async()=>{setThread(t.id);await refresh();});$("threads").append(b);}
    if(!status.threads.length)$("threads").append(node("p","Your research conversations will appear here.","agent-empty"));
    $("usage").textContent=status.daily_used+" of "+status.daily_limit+" requests used today. Resets at 00:00 UTC.";
  }
  function render(){
    syncControls();
    const signature=JSON.stringify(runs);if(signature===lastRender)return;lastRender=signature;
    const panel=$("conversation"),nearBottom=panel.scrollHeight-panel.scrollTop-panel.clientHeight<120;
    panel.replaceChildren();$("starters").hidden=!!runs.length;
    for(const run of runs){
      const article=node("article",undefined,"agent-message");
      article.append(node("div",new Date(run.created*1000).toLocaleString()+" · "+run.status+(run.deep_research?" · deep research":""),"agent-message-meta"),node("div",run.prompt,"agent-prompt"));
      const answer=run.answer;
      if(answer?.text){const paragraph=node("div",undefined,"agent-answer");for(const p of answer.parts||[{text:answer.text}])paragraph.append(p.url?link(p.text,p.url):document.createTextNode(p.text));article.append(paragraph);}
      if(run.error)article.append(node("p",run.error,"agent-error"));
      if(run.status==="running")article.append(node("p",run.progress,"muted"));
      if(answer?.sources?.length){const details=node("details",undefined,"agent-sources"),list=node("ul");details.append(node("summary",answer.sources.length+" sources"));for(const s of answer.sources){const item=node("li");item.append(link(s.title,s.url));list.append(item);}details.append(list);article.append(details);}
      const actions=node("div",undefined,"agent-actions");
      for(const p of answer?.proposals||[])actions.append(link("Review "+p.request.symbol+" backtest","/backtests?agent_run="+encodeURIComponent(run.id)+"&agent_proposal="+encodeURIComponent(p.id)));
      for(const j of answer?.queued_backtests||[])actions.append(link("View test: "+j.request.symbol+" · "+j.request.strategy,"/backtests?job="+encodeURIComponent(j.id)));
      if(run.status!=="running"){const exportButton=node("button","Export report","small");exportButton.type="button";exportButton.addEventListener("click",async()=>{exportButton.disabled=true;try{const blob=await api("export?id="+encodeURIComponent(run.id),undefined,true),url=URL.createObjectURL(blob),a=node("a");a.href=url;a.download="stock-lab-research-"+run.id+".md";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notice(e.message,true);}finally{exportButton.disabled=false;}});actions.append(exportButton);}
      article.append(actions);
      if(answer?.tools?.length){const details=node("details",undefined,"agent-activity"),list=node("ul");details.append(node("summary","Workspace activity · "+answer.tools.length+" tool calls"));for(const t of answer.tools)list.append(node("li",t.label+(t.ok?"":" · rejected")));details.append(list);article.append(details);}
      if(run.status==="complete" && answer)article.append(node("p",(answer.web_searched?"Web sources retrieved":"No web search performed")+" · "+(answer.usage?.output_tokens??0).toLocaleString()+" output tokens (including reasoning)","agent-activity"));
      panel.append(article);
    }
    if(nearBottom)panel.scrollTop=panel.scrollHeight;
  }
  async function notebook(){
    try{const data=await api("notebook"),panel=$("notebook");panel.replaceChildren();
      if(!data.reviews.length)panel.append(node("p","No lessons saved yet. Ask the agent to review a completed backtest and record what it learned.","agent-empty"));
      for(const review of data.reviews){const article=node("article");article.append(node("span",review.assessment.replaceAll("_"," "),"badge"),node("h3",review.request.symbol+" · "+review.request.strategy),node("p",review.lesson),node("p","Next hypothesis: "+review.next_hypothesis));const detail=node("details");detail.append(node("summary","Historical evidence · "+new Date(review.recorded_at*1000).toLocaleDateString()),node("pre",JSON.stringify(review.evidence,null,2)));article.append(detail,link("Open saved backtest","/backtests?job="+encodeURIComponent(review.job_id)));const remove=node("button","Remove lesson","small");remove.type="button";remove.addEventListener("click",async()=>{if(!confirm("Remove this strategy lesson? The underlying backtest stays saved."))return;try{await api("notebook/delete",{id:review.job_id});await notebook();}catch(e){notice(e.message,true);}});article.append(document.createTextNode(" "),remove);panel.append(article);}
    }catch(e){notice(e.message,true);}
  }
  async function refresh(){
    if(refreshing)return;refreshing=true;
    try{
      status=await api("status");syncControls();$("accessPanel").hidden=true;$("content").hidden=false;
      $("setupPanel").hidden=status.configured;$("setupMessage").textContent="Missing server configuration: "+status.missing.join(", ")+".";
      if(!threadId && status.active && !fromWatch)setThread(status.active.thread_id);
      if(threadId && !status.threads.some(t=>t.id===threadId) && status.active?.thread_id!==threadId){setThread(null);runs=[];}
      if(threadId){
        const meta=status.threads.find(t=>t.id===threadId),active=status.active?.thread_id===threadId?status.active:null;
        const key=JSON.stringify([threadId,meta?.run_count,meta?.last_seq,active?.id]);
        if(key!==loadedThreadKey){const saved=await api("thread?id="+encodeURIComponent(threadId));runs=saved.runs;loadedThreadKey=key;}
        else if(active){const current=await api("run?id="+encodeURIComponent(active.id));const index=runs.findIndex(r=>r.id===current.id);if(index>=0)runs[index]=current;else runs.push(current);}
      }else runs=[];
      renderThreads();render();
    }catch(e){notice(e.message,true);}finally{refreshing=false;}
  }
  async function submit(body){
    submitting=true;syncControls();notice("");
    try{
      const run=await api("start",body);savePending(null);setThread(run.thread_id);$("message").value="";
      status.active=run.status==="running"?{id:run.id,thread_id:run.thread_id,progress:run.progress}:null;
      await refresh();
    }catch(e){
      // An HTTP rejection is definitive. A lost response is ambiguous: preserve
      // the same request ID so retrying cannot create a second paid run.
      if(e.status)savePending(null);
      notice(e.message+(e.status?"":" Use ‘Check / retry the same request’ to recover without creating a duplicate."),true);
    }finally{submitting=false;syncControls();}
  }
  $("accessForm").addEventListener("submit",async e=>{e.preventDefault();token=$("accessToken").value.trim();StockSession.setToken(token);await refresh();if(status&&!status.missing.includes("APP_ACCESS_TOKEN"))await notebook();});
  $("agentForm").addEventListener("submit",async e=>{e.preventDefault();if(submitting||pending||status?.active||!status?.configured)return;const message=$("message").value.trim();if(!message)return;const body={message,request_id:crypto.randomUUID(),web_search:$("webSearch").checked,deep_research:$("deepResearch").checked,allow_backtests:$("allowBacktests").checked};if(threadId)body.thread_id=threadId;savePending(body);await submit(body);});
  $("retrySubmission").addEventListener("click",()=>{if(pending&&!submitting)submit(pending);});
  $("newChat").addEventListener("click",()=>{setThread(null);runs=[];renderThreads();render();$("message").focus();});
  $("stop").addEventListener("click",async()=>{if(!status?.active)return;$("stop").disabled=true;try{await api("cancel",{id:status.active.id});notice("Research stopped. Already queued stock tests can be stopped on Backtest stocks.");await refresh();}catch(e){notice(e.message,true);}finally{$("stop").disabled=false;}});
  $("deleteChat").addEventListener("click",async()=>{if(!threadId||!confirm("Delete this conversation and its reports? Saved strategy lessons and backtests stay available."))return;try{await api("delete",{id:threadId});setThread(null);runs=[];await refresh();}catch(e){notice(e.message,true);}});
  $("refreshNotebook").addEventListener("click",notebook);
  $("starters").addEventListener("click",e=>{const b=e.target.closest("[data-preset]");if(!b)return;$("message").value=presets[b.dataset.preset];$("deepResearch").checked=["stocks","crypto","strategy"].includes(b.dataset.preset);$("webSearch").checked=["stocks","crypto"].includes(b.dataset.preset);$("allowBacktests").checked=b.dataset.preset==="strategy";$("message").focus();});
  if(fromWatch){setThread(null);$("message").value="Read our workspace crypto watch for "+watchRequest+". Check whether observations are fresh, initial, or already extended. Research current primary news, catalysts, liquidity, token value capture and contrary evidence. Distinguish publication time from when this app actually saw information. Explain what could invalidate the signal; do not claim an early prediction or a proven edge.";$("webSearch").checked=true;$("deepResearch").checked=true;$("allowBacktests").checked=false;}
  StockSession.poll(async()=>{const wasActive=!!status?.active,first=!status;await refresh();if(status&&!status.missing.includes("APP_ACCESS_TOKEN")&&(first||wasActive&&!status.active))await notebook();},()=>!!status?.active,()=>true);
})();
