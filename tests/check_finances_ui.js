// Exercise the real renderers, account switching and request-failure behavior.
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,".."),elements=new Map(),listeners=new Map(),storage=new Map(),events=[],requests=[];
function element(id) {
  if (!elements.has(id)) elements.set(id,{value:"",textContent:"",innerHTML:"",dataset:{},handlers:{},
    addEventListener(name,fn){this.handlers[name]=fn;}});
  return elements.get(id);
}
let response,fail=false;
const context={console,Intl,Date,Number,Set,Map,encodeURIComponent,
  CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
  window:{addEventListener(name,fn){listeners.set(name,fn);},dispatchEvent(event){events.push(event);listeners.get(event.type)?.(event);}},
  sessionStorage:{getItem(key){return storage.get(key)||"";},setItem(key,value){storage.set(key,value);}},
  document:{getElementById:element,querySelectorAll(){return [];}},
  setTimeout(){},clearTimeout(){},
  fetch:async(url,options)=>{requests.push({url,options});if(fail)throw Error("Connection lost");return {ok:true,json:async()=>response};}};
vm.createContext(context);
const source=fs.readFileSync(path.join(root,"static/app.js"),"utf8").replace("\n  poll();\n})();",
  "\n  globalThis.financeTest={updateFinances,renderFinances};\n})();");
vm.runInContext(source,context);
const update=context.financeTest.updateFinances;
function choose(source) {element("financeSource").value=source;element("financeSource").handlers.change.call(element("financeSource"));}
const totals={status:"available",closed_trades:3,winning_trades:1,losing_trades:1,break_even_trades:1,
  money_won:5,money_lost:3,net_pnl:2,win_rate:100/3,window_end_exits:1};
assert.equal(element("financeSource").value,"history");
const history={total_markets:4,results:[{symbol:"AVAX-USD",interval:"15m",historical_examples:99999,trade_finances:totals},
  {symbol:'BAD<img src=x>',trade_finances:{status:"unavailable"}}]};
update("history",history);
assert.equal(element("financeTrades").textContent,"3");
assert.equal(element("financeWon").textContent,"$5.00");
assert.equal(element("financeLost").textContent,"-$3.00");
assert.equal(element("financeNet").textContent,"$2.00");
assert.equal(element("financeBreakEven").textContent,"1");
assert.match(element("financeNote").textContent,/Partial totals/);
assert.match(element("financeNote").textContent,/2 of 4/);
assert.match(element("financeNote").textContent,/1 simulated exit/);
assert.ok(!element("financeMarket").innerHTML.includes("<img"));
element("financeMarket").value="AVAX-USD:15m";
element("financeMarket").handlers.change();
update("history",history);
assert.equal(element("financeMarket").value,"AVAX-USD:15m");
assert.ok(!element("financeNote").textContent.includes("Partial totals"));
choose("paper");
assert.equal(storage.get("cryptoFinanceSource"),"paper");
assert.equal(element("financeTrades").textContent,"—");
update("paper",{trade_finances:{...totals,closed_trades:127,money_won:12.5,money_lost:31.25,net_pnl:-18.75}});
assert.equal(element("financeTrades").textContent,"127");
assert.equal(element("financeNet").textContent,"-$18.75");
assert.equal(element("financeNet").className,"negative");
assert.equal(element("financeMarketLabel").hidden,true);
update("history",{results:[]});
assert.equal(element("financeNet").textContent,"-$18.75");
update("paper",null,true);
assert.equal(element("financeNet").textContent,"-$18.75");
assert.match(element("financeUpdated").textContent,/Update failed/);
update("paper",{trade_finances:{...totals,closed_trades:0,winning_trades:0,losing_trades:0,break_even_trades:0,money_won:0,money_lost:0,net_pnl:0,win_rate:null}});
assert.equal(element("financeTrades").textContent,"0");
assert.equal(element("financeRate").textContent,"—");
assert.ok(!element("financeUpdated").textContent.includes("failed"));
choose("coinbase");
update("coinbase",{mode:"locked"});
assert.equal(element("financeNet").textContent,"—");
assert.match(element("financeNote").textContent,/locked/);
vm.runInContext(fs.readFileSync(path.join(root,"static/coinbase.js"),"utf8").replace("\n  poll();\n})();",
  "\n  globalThis.coinbaseTest={refresh,render};\n})();"),context);
response={mode:"idle",running:false,trades:[],snapshot:null,trade_finances:totals};
(async()=>{
  await context.coinbaseTest.refresh();
  assert.equal(element("financeNet").textContent,"$2.00");
  assert.match(element("financeNote").textContent,/Real money/);
  const delivered=events.length;
  context.coinbaseTest.render(response);
  assert.equal(events.length,delivered,"Redrawing old controls must not mark old finances fresh");
  fail=true;
  await context.coinbaseTest.refresh();
  assert.equal(element("financeNet").textContent,"$2.00");
  assert.match(element("financeUpdated").textContent,/Update failed/);
  assert.ok(requests.every(r=>r.url==="/api/coinbase/status" && !r.options.method));
  choose("history");
  update("history",{results:[{symbol:"MISSING-USD",trade_finances:{status:"unavailable"}}]});
  assert.equal(element("financeNet").textContent,"—");
  assert.match(element("financeNote").textContent,/unavailable/);
  console.log("Finance dashboard checks passed: separate accounts, complete totals, historical selection, empty/locked states, stale updates, escaping and read-only Coinbase refresh.");
})().catch(error=>{console.error(error);process.exitCode=1;});
