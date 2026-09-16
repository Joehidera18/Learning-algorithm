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
  "\n  globalThis.testUI={renderLearning,renderJournal,download};\n})();");
vm.createContext(context);vm.runInContext(code,context);
const original=process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2],"utf8")) :
  {results:[],historical_examples:0,phase:"completed",message:"Fixture"};
context.testUI.renderLearning(original);
if (original.results.length) {
  assert.match(element("learningResults").innerHTML,/BTC-USD/);
  assert.equal(element("learningTestTrades").textContent,String(original.results.reduce((n,r)=>n+(r.holdout?.trades||0),0)));
}
const current={...original,current_policy_version:"fixture",current_report_version:8,historical_examples:130625,
  results:[{symbol:'BTC-USD<img src=x onerror="bad()">',interval:"15m",policy_version:"fixture",learning_report_version:8,
    validated:false,holdout:{net_pnl:-.62,trades:16},holdout_stressed:{net_pnl:-21.84},data_quality:{rows:3000},
    market_data:{provider:"Fixture",gap_repair:{recovered_direct:2,recovered_from_smaller_candles:3,missing_after:4},
      daily_context:{status:"daily_download_unavailable"}},
    daily_data:{source:"complete_intraday_aggregation",holdout_ready_candles:500,holdout_candles:1000},
    learning_inputs:{dimensions:27},
    failure_learning:{by_family:{trend_pullback_simple:{causes:{stopped_out:7,fee_erased_gain:8,stalled_trade:9,other_loss:10}}}},
    outcome_memory_comparison:{net_pnl_difference:0,stress_net_pnl_difference:-1.23},
    prediction_audit:{selected:{samples:3,mean_predicted_net_r:.4,mean_actual_net_r:-.5,optimism_bias_r:.9,
      rmse_r:1.2,zero_forecast_rmse_r:1.0,calibration:{paired_samples:3,adjusted_forecasts:2,
        raw:{rmse_r:1.345},corrected:{rmse_r:1.2}}},shadow:{samples:40,mean_predicted_net_r:-.2,mean_actual_net_r:-.3}},
    development_prediction_audit:{samples:100,mean_predicted_net_r:-.1,mean_actual_net_r:-.2},
    forecast_calibration:{rule:'<img src=x onerror="bad()">'},
    selection_policy_comparison:{rule:'<img src=x onerror="bad()">',holdout:{net_pnl:-3.75,trades:1},
      holdout_stressed:{net_pnl:0},net_pnl_difference:-3.13,rejection_reasons:['Needs later data']},
    exit_policy_comparison:{historical_examples:90,holdout:{net_pnl:2.25,trades:7},
      holdout_stressed:{net_pnl:-4.5,trades:4},net_pnl_difference:2.87,stress_net_pnl_difference:17.34,
      eligible_for_trading:false,rejection_reasons:['<img src=x onerror="bad()">']},
    trade_reviews:{break_even_band_r:.1,development:{examples:50,outcomes:{near_break_even:7},cases:[]},
      selected:{outcomes:{near_break_even:1},cases:[{strategy_family:"support_rsi_reclaim_simple",entry_ts:1789000000000,pnl:-.05,
        review:{outcome:"near_break_even",net_r:-.05,fee_r:.2,best_net_r:.6,giveback_r:.65,holding_hours:2,
          findings:["fees_erased_gain","gave_back_gains",'<img src=x onerror="bad()">']},entry_context:{regime:"CHOP",rsi:50,daily:{ready:true,trend_up:true}},
        post_exit:{observations:[{hours:1,status:"complete",end_move_pct:1,favorable_move_pct:2,adverse_move_pct:-1},
          {hours:4,status:"pending"},{hours:24,status:"missing_candles"}]},
        break_even_stop:{status:"complete",net_r:0,difference_r:.05}}]}},
    training_diagnostics:{totals:{loss_pause_overrides:12},candidates:[]},
    holdout_shadow_feedback:{resolved_examples:120},performance_attribution:{scope:"Modeled costs",
      by_family:{daily_trend_momentum_simple:{trades:16,gross_pnl:9.01,fees_paid:9.63,net_pnl:-.62}}},
    evaluation:{reuses_reviewed_history:true,reviewed_through_ts:1789448400000,confirmation:{start_ts:1789448400000,
      end_ts:1789452000000,metrics:{trades:0,net_pnl:0},stressed:{net_pnl:0},
      account_feedback_control:{metrics:{net_pnl:-2},stressed:{net_pnl:-3}}}}}]};
context.testUI.renderLearning(current);
const html=element("learningResults").innerHTML;
for (const text of ["Reused-history test","$9.01","$9.63","-$0.62","120","Confirmation on later prices",
  "Missing candle recovery","50.0%","Separate daily history could not be downloaded",
  "What happened in the failed trade examples?","Effect of the new outcome memory","-$1.23",
  "Entry context studied:","Large losses retain their full size",
  "Entry predictions and later outcomes","0.400R","-0.500R","0.900R","Zero forecast RMSE",
  "Learning from forecast mistakes","Earlier training practice","Original forecast error","1.345R","Trial adjustments",
  "They are disabled for trading",
  "Conditional selection experiment","-$3.75","Needs later data",
  "Loss and break-even study","Near break-even","Practice continued after losses","After exit:",
  "Fixed exit experiment","awaiting enough later candles","missing candles","Fees erased a gross gain",
  "Whole-account break-even experiment","$2.25","-$4.50","This experiment cannot control trading",
  "Selected-trade feedback on later prices","-$2.00","-$3.00","Download candles &amp; report"])
  assert.ok(html.includes(text),text);
assert.ok(!html.includes("<img"));assert.ok(html.includes("&lt;img"));
assert.equal(element("learningExamples").textContent,"130625");
context.testUI.renderJournal([{product_id:"BTC-USD",family:"fixture",status:"CLOSED",pnl:-.05,result_r:-.05,
  exit_reason:"TIME",entry_forecast:{estimated_net_r:.75},trade_review:current.results[0].trade_reviews.selected.cases[0].review}]);
assert.ok(element("journalTable").innerHTML.includes("At-close review"));
assert.ok(element("journalTable").innerHTML.includes("Entry estimate 0.750R; realized -0.050R"));
assert.ok(!element("journalTable").innerHTML.includes("<img"));
context.testUI.download("/api/learning/data?symbol=BTC-USD&interval=15m","test.zip").then(()=>{
  assert.equal(element("download-anchor").clicked,true);
  assert.equal(element("download-anchor").attached,false);
  assert.ok(timers.some(t=>t.delay>=60000));
  console.log("Dashboard checks passed: supplied report, new counts, cost attribution, confirmation, escaping and download handoff.");
}).catch(error=>{console.error(error);process.exitCode=1;});
