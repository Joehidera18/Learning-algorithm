// Exercises the actual dashboard renderer; no browser rendering is claimed.
"use strict";
const assert=require("node:assert/strict"), fs=require("node:fs"), vm=require("node:vm"), path=require("node:path");
const root=path.resolve(__dirname,"..");
const elements=new Map(), timers=[];
function element(id) {
  if (!elements.has(id)) elements.set(id,{value:"",textContent:"",innerHTML:"",dataset:{},addEventListener(){},
    click(){assert.equal(this.attached,true);this.clicked=true;},remove(){this.attached=false;}});
  return elements.get(id);
}
const context={console,Intl,Date,Number,Set,Map,encodeURIComponent,
  window:{addEventListener(){}},
  sessionStorage:{getItem(){return "";},setItem(){}},
  document:{getElementById:element,querySelectorAll(){return [];},createElement(){return element("download-anchor");},
    body:{appendChild(a){a.attached=true;}}},
  setTimeout(fn,delay){timers.push({fn,delay});return timers.length;},clearTimeout(){},
  URL:{createObjectURL(){return "blob:test";},revokeObjectURL(){}},
  fetch:async()=>({ok:true,blob:async()=>({})})};
const code=fs.readFileSync(path.join(root,"static/app.js"),"utf8").replace("\n  poll();\n})();",
  "\n  globalThis.testUI={renderLearning,download};\n})();");
vm.createContext(context);vm.runInContext(code,context);
const original=process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2],"utf8")) :
  {results:[],historical_examples:0,phase:"completed",message:"Fixture"};
context.testUI.renderLearning(original);
if (original.results.length) {
  assert.match(element("learningResults").innerHTML,/BTC-USD/);
  assert.equal(element("learningTestTrades").textContent,String(original.results.reduce((n,r)=>n+(r.holdout?.trades||0),0)));
}
const current={...original,current_policy_version:"fixture",current_report_version:7,historical_examples:130625,
  results:[{symbol:'BTC-USD<img src=x onerror="bad()">',interval:"15m",policy_version:"fixture",learning_report_version:7,
    validated:false,holdout:{net_pnl:-.62,trades:16},holdout_stressed:{net_pnl:-21.84},data_quality:{rows:3000},
    holdout_shadow_feedback:{resolved_examples:120},performance_attribution:{scope:"Modeled costs",
      by_family:{daily_trend_momentum_simple:{trades:16,gross_pnl:9.01,fees_paid:9.63,net_pnl:-.62}}},
    evaluation:{reuses_reviewed_history:true,reviewed_through_ts:1789448400000,confirmation:{start_ts:1789448400000,
      end_ts:1789452000000,metrics:{trades:0,net_pnl:0},stressed:{net_pnl:0},
      account_feedback_control:{metrics:{net_pnl:-2},stressed:{net_pnl:-3}}}}}]};
context.testUI.renderLearning(current);
const html=element("learningResults").innerHTML;
for (const text of ["Reused-history test","$9.01","$9.63","-$0.62","120","Confirmation on later prices",
  "Selected-trade feedback on later prices","-$2.00","-$3.00","Download candles &amp; report"])
  assert.ok(html.includes(text),text);
assert.ok(!html.includes("<img"));assert.ok(html.includes("&lt;img"));
assert.equal(element("learningExamples").textContent,"130625");
context.testUI.download("/api/learning/data?symbol=BTC-USD&interval=15m","test.zip").then(()=>{
  assert.equal(element("download-anchor").clicked,true);
  assert.equal(element("download-anchor").attached,false);
  assert.ok(timers.some(t=>t.delay>=60000));
  console.log("Dashboard checks passed: supplied report, new counts, cost attribution, confirmation, escaping and download handoff.");
}).catch(error=>{console.error(error);process.exitCode=1;});
