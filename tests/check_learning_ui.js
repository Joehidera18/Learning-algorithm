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
  "\n  globalThis.testUI={renderLearning,renderJournal,download,practicePlan,showLearningDetails,renderEvents,renderForward};\n})();");
vm.createContext(context);vm.runInContext(code,context);
context.testUI.renderEvents({running:true,versions:2,sources:[{name:'<script>bad</script>',url:'https://example.org',healthy:false,error:'Unavailable <img src=x>'}],
  recent:[{title:'<img src=x onerror=bad()>',url:'javascript:bad()',published_ts:1789862572845,category:'regulation',source:'sec'}],
  upcoming:[{title:'Scheduled release',url:'https://example.org/release',event_ts:1789862572845,precision:'day',category:'macro',source:'bls'}]});
assert.match(element('eventsCoverage').textContent,/0 of 1/);
assert.match(element('eventsRecent').innerHTML,/&lt;img/);
assert.doesNotMatch(element('eventsRecent').innerHTML,/javascript:|<img/);
assert.match(element('eventsUpcoming').innerHTML,/date only/);
assert.match(element('eventsSources').innerHTML,/&lt;script/);
assert.match(element('eventsSources').innerHTML,/Unavailable or stale/);
context.testUI.renderEvents({sources:[],projects:[{title:'<script>release</script>',url:'javascript:bad()',
  source:'avalanche_releases',origin:'project_publication',published_ts:1789862572845,observed_ts:1789862572846}],
  category_coverage:{world:0,project:null}});
assert.match(element('eventsProjects').innerHTML,/&lt;script/);
assert.doesNotMatch(element('eventsProjects').innerHTML,/javascript:|<script/);
assert.match(element('eventsCategories').textContent,/world: 0/);
assert.match(element('eventsCategories').textContent,/project: no configured source/);
context.testUI.renderJournal([{product_id:'BTC-USD',status:'CLOSED',event_review:{
  signal:{coverage:1,recent:[{title:'<img src=x>',url:'https://example.org/news',source:'<script>',origin:'reporting'}]},
  entry:{coverage:.5,upcoming:[{title:'Known meeting',status:'scheduled',precision:'day',event_ts:1789862572845}]},
  after_entry:{versions_observed:1,truncated:true,items:[{title:'Later update',url:'javascript:bad()'}]},
  scope:'<img src=x>'}}]);
assert.match(element('journalTable').innerHTML,/News known at this trade/);
assert.match(element('journalTable').innerHTML,/Observed after entry/);
assert.match(element('journalTable').innerHTML,/Known meeting/);
assert.match(element('journalTable').innerHTML,/date only/);
assert.match(element('journalTable').innerHTML,/&lt;img/);
assert.doesNotMatch(element('journalTable').innerHTML,/javascript:|<img|<script/);
const original=process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2],"utf8")) :
  {results:[],historical_examples:0,phase:"completed",message:"Fixture"};
context.testUI.renderLearning(original);
context.testUI.renderForward({registered_studies:2,studies:[{id:'fixture',status:'active',last_error:'Unavailable <img src=x>',
  protocol:{symbol:'BTC-USD<script>',interval:'15m'},result:{accounts:{updating:{closed:{closed_trades:1,net_pnl:-2},
    open_mark_pnl:-1,model_updates:1,metrics:{ending_balance:497,max_drawdown_pct:.6}},frozen:{closed:{closed_trades:0,net_pnl:0},
    open_mark_pnl:-1,model_updates:0,metrics:{ending_balance:499,max_drawdown_pct:.2}}},equity_pnl_difference:-2}}]});
assert.match(element('forwardResults').innerHTML,/&lt;script/);
assert.doesNotMatch(element('forwardResults').innerHTML,/<script>|<img/);
assert.match(element('forwardResults').innerHTML,/\$497.00/);
assert.match(element('forwardResults').innerHTML,/Open net mark/);
assert.equal(element('forwardStart').disabled,true);
assert.equal(element('forwardStop').disabled,false);
context.testUI.renderForward({registered_studies:0,studies:[]});
assert.equal(element('forwardExport').disabled,true);
assert.match(element('forwardResults').innerHTML,/No forward study/);
const savedIntervals=original.practice_intervals || original.default_practice_intervals || ["15m","1h","6h"];
for (const iv of ["5m","15m","1h","6h"]) {
  assert.equal(element("practiceInterval"+iv).checked,savedIntervals.includes(iv));
  element("practiceInterval"+iv).checked=iv !== "5m";
}
element("autoFee").value="0.4";
element("autoFee").reportValidity=()=>true;
element("practiceSymbols").value="BTC, eth, BTC-USD";
element("practiceHistory").value="2920";
const plan=JSON.parse(JSON.stringify(context.testUI.practicePlan()));
assert.deepEqual(plan,{fee_rate:.004,symbols:["BTC-USD","ETH-USD"],intervals:["15m","1h","6h"],history_days:2920});
for (const iv of ["5m","15m","1h","6h"]) element("practiceInterval"+iv).checked=false;
assert.throws(()=>context.testUI.practicePlan(),/at least one timeframe/);
element("practiceInterval6h").checked=true;
assert.deepEqual(JSON.parse(JSON.stringify(context.testUI.practicePlan().intervals)),["6h"]);
if (original.results.length) {
  assert.match(element("learningResults").innerHTML,/BTC-USD/);
  assert.equal(element("learningTestTrades").textContent,String(original.results.reduce((n,r)=>n+(r.holdout?.trades||0),0)));
}
const current={...original,current_policy_version:"fixture",current_report_version:8,historical_examples:130625,
  results:[{symbol:'BTC-USD<img src=x onerror="bad()">',interval:"15m",policy_version:"fixture",learning_report_version:8,
    validated:false,holdout:{net_pnl:-.62,trades:16},holdout_stressed:{net_pnl:-21.84},data_quality:{rows:3000},
    history_request:{requested_days:2920,effective_days:1825,observed_candles:105063,coverage_pct:60,
      first_candle_ts:1695166200000,last_candle_close_ts:1789774200000},
    market_data:{provider:"Fixture",gap_repair:{recovered_direct:2,recovered_from_smaller_candles:3,missing_after:4},
      daily_context:{status:"daily_download_unavailable"}},
    daily_data:{source:"complete_intraday_aggregation",holdout_ready_candles:500,holdout_candles:1000},
    bitcoin_data:{source:"independent_daily_candles",holdout_ready_candles:900,holdout_candles:1000,rule:'<img src=x onerror="bad()">'},
    learning_evidence:{eligible_examples:135,cost_blocked_examples:8821,rule:'<img src=x onerror="bad()">',
      by_family:{trend_pullback_simple:{eligible_examples:135,cost_blocked_examples:8821,eligible_ready_candidates:1,candidates:4}}},
    failure_predictions:{targets:{little_follow_through:{samples:40,scored:10,brier_score:.24,prior_frequency_brier:.25}},scope:'<img src=x onerror="bad()">'},
    experiment_registry:{trial_id:'<img src=x onerror="bad()">',variants:['primary','higher_cost'],scope:'<img src=x onerror="bad()">'},
    learning_inputs:{dimensions:27},
    failure_learning:{by_family:{trend_pullback_simple:{causes:{stopped_out:7,fee_erased_gain:8,stalled_trade:9,other_loss:10}}}},
    outcome_memory_comparison:{net_pnl_difference:0,stress_net_pnl_difference:-1.23},
    prediction_audit:{selected:{samples:3,mean_predicted_net_r:.4,mean_actual_net_r:-.5,optimism_bias_r:.9,
      rmse_r:1.2,zero_forecast_rmse_r:1.0,calibration:{paired_samples:3,adjusted_forecasts:2,
        raw:{rmse_r:1.345},corrected:{rmse_r:1.2}}},shadow:{samples:40,mean_predicted_net_r:-.2,mean_actual_net_r:-.3}},
    development_prediction_audit:{samples:100,mean_predicted_net_r:-.1,mean_actual_net_r:-.2,
      by_practice_lane_and_forecast_band:{'eligible/0_to_0.5R':{samples:5,mean_predicted_net_r:.234,
        mean_actual_net_r:-.345,rmse_r:.789,zero_forecast_rmse_r:.678}},
      by_practice_lane:{eligible:{samples:25,mean_predicted_net_r:.1,mean_actual_net_r:-.1,rmse_r:.123},
        cost_blocked:{samples:75,mean_predicted_net_r:-.4,mean_actual_net_r:-.5,rmse_r:.456}}},
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
      end_ts:1789452000000,metrics:{trades:0,net_pnl:0,feedback:{resolved_examples:20,
        by_entry_period:{carried_in:{resolved_examples:8}}}},stressed:{net_pnl:0},practice_continuity:{},
      account_feedback_control:{metrics:{net_pnl:-2},stressed:{net_pnl:-3}}}}}]};
context.testUI.renderLearning(current);
const html=element("learningResults").innerHTML;
for (const text of ["Reused-history test","$9.01","$9.63","-$0.62","120","Confirmation on later prices",
  "Missing candle recovery","50.0%","Separate daily history could not be downloaded",
  "What happened in the failed trade examples?","Effect of the new outcome memory","-$1.23",
  "Entry context studied:","Large losses retain their full size",
  "Entry predictions and later outcomes","0.400R","-0.500R","0.900R","Zero forecast RMSE",
  "Learning from forecast mistakes","Earlier training practice","Original forecast error","1.345R","Trial adjustments",
  "Two-sided trial corrections do not control trading",
  "Relevant learning evidence","Affordable practice examples: 135","Bitcoin and market conditions",
  "Learning specific failure patterns","0.2400","0.2500","Experiment record","2 declared variants recorded",
  "Learning from trades that pass the cost rules","Passes cost rules","Fails cost rules","0.123R","0.456R",
  "Positive forecasts for affordable setups","0.234R","-0.345R","0.789R","0.678R",
  "Conditional selection experiment","-$3.75","Needs later data",
  "Loss and break-even study","Near break-even","Practice continued after losses","After exit:",
  "Fixed exit experiment","awaiting enough later candles","missing candles","Fees erased a gross gain",
  "Whole-account break-even experiment","$2.25","-$4.50","This experiment cannot control trading",
  "Selected-trade feedback on later prices","-$2.00","-$3.00","Download candles &amp; report",
  "History coverage:","2920 days requested; 1825 day limit","105063 candles, 60.0%","· 15m"])
  assert.ok(html.includes(text),text);
assert.ok(html.includes('20 practice outcomes became available in this window; 8 came from examples opened earlier.'));
assert.ok(!html.includes("<img"));assert.ok(html.includes("&lt;img"));
assert.equal(element("learningExamples").textContent,"130625");
context.testUI.renderLearning({...current,completed_studies:2,total_studies:6,total_markets:2,
  results:[current.results[0],{...current.results[0],symbol:"ETH-USD",interval:"6h",research_only:true,validated:true}]});
assert.match(element("learningResults").innerHTML,/ETH-USD · 6h/);
assert.match(element("learningResults").innerHTML,/<span class="badge ">Research only<\/span>/);
assert.match(element("learningProgress").textContent,/2 of 6 studies processed across 2 coins/);
context.testUI.renderJournal([{product_id:"BTC-USD",family:"fixture",status:"CLOSED",pnl:-.05,result_r:-.05,
  exit_reason:"TIME",entry_forecast:{estimated_net_r:.75},trade_review:current.results[0].trade_reviews.selected.cases[0].review}]);
assert.ok(element("journalTable").innerHTML.includes("At-close review"));
assert.ok(element("journalTable").innerHTML.includes("Entry estimate 0.750R; realized -0.050R"));
assert.ok(!element("journalTable").innerHTML.includes("<img"));
(async function () {
  const report={...current.results[0],symbol:"BTC-USD",fingerprint:"saved15m"};
  const summary={symbol:report.symbol,interval:report.interval,fingerprint:report.fingerprint,
    holdout:report.holdout,report_summary:true,details_available:true};
  context.testUI.renderLearning({...current,results:[summary]});
  assert.match(element("learningResults").innerHTML,/Open detailed learning review/);
  assert.ok(!element("learningResults").innerHTML.includes("Loss and break-even study"));
  context.fetch=async function (url) {
    assert.match(url,/\/api\/learning\/report\?symbol=BTC-USD&interval=15m&fingerprint=saved15m/);
    return {ok:true,json:async()=>report};
  };
  await context.testUI.showLearningDetails("BTC-USD","15m","saved15m");
  assert.match(element("learningResults").innerHTML,/Hide detailed review/);
  assert.match(element("learningResults").innerHTML,/Loss and break-even study/);
  await context.testUI.showLearningDetails("BTC-USD","15m","saved15m");
  assert.ok(!element("learningResults").innerHTML.includes("Loss and break-even study"));
  let resolveOld;
  context.fetch=()=>new Promise(resolve=>{resolveOld=resolve;});
  const pending=context.testUI.showLearningDetails("BTC-USD","15m","saved15m");
  context.testUI.renderLearning({...current,results:[{...summary,fingerprint:"new15m"}]});
  resolveOld({ok:true,json:async()=>report});
  await pending;
  assert.ok(!element("learningResults").innerHTML.includes("Loss and break-even study"));
  context.fetch=async()=>{throw new Error("fixture offline");};
  await assert.rejects(context.testUI.showLearningDetails("BTC-USD","15m","new15m"),/fixture offline/);
  assert.ok(!element("learningResults").innerHTML.includes("Loading review"));
  context.fetch=async()=>({ok:true,blob:async()=>({})});
  await context.testUI.download("/api/learning/data?symbol=BTC-USD&interval=15m","test.zip");
  assert.equal(element("download-anchor").clicked,true);
  assert.equal(element("download-anchor").attached,false);
  assert.ok(timers.some(t=>t.delay>=60000));
  console.log("Dashboard checks passed: summaries, on-demand detail, stale-response rejection, reports, costs, escaping and download handoff.");
})().catch(error=>{console.error(error);process.exitCode=1;});
