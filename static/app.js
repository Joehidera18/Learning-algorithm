"use strict";
(function () {
  const $ = function (id) { return document.getElementById(id); };
  let token = sessionStorage.getItem("cryptoAccessToken") || "";
  let state = null, learningState = null, settingsLoaded = false, busy = false, noticeTimer = null;
  let practiceSelectionLoaded = false;
  const percentFields = new Set(["fee_rate","slippage_rate","risk_per_trade","max_total_risk","daily_loss_limit","max_notional_fraction","max_spread"]);
  const escape = function (value) { return String(value == null ? "—" : value).replace(/[&<>"']/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); };
  const finite = function (v) { return typeof v === "number" && Number.isFinite(v); };
  const money = function (v) { return finite(v) ? new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(v) : "—"; };
  const num = function (v, d) { return finite(v) ? v.toFixed(d == null ? 2 : d) : "—"; };
  const pct = function (v) { return finite(v) ? num(v) + "%" : "—"; };
  const price = function (v) { return finite(v) ? "$" + v.toLocaleString("en-US",{maximumFractionDigits:v < 1 ? 6 : 2}) : "—"; };
  const tone = function (v) { return finite(v) && v !== 0 ? (v > 0 ? "positive" : "negative") : ""; };
  const family = function (v) { return String(v || "").replace(/_simple$/,"").replace(/_/g," "); };
  const date = function (v, ms) { return v ? new Date(ms ? v : v * 1000).toLocaleString() : "—"; };
  const emptyRow = function (cols, text) { return '<tr><td class="empty" colspan="' + cols + '">' + escape(text) + "</td></tr>"; };
  function notice(message, error) {
    clearTimeout(noticeTimer);
    $("notice").textContent = message; $("notice").className = "notice" + (error ? " error" : ""); $("notice").hidden = false;
    if (!error) noticeTimer = setTimeout(function () { $("notice").hidden = true; }, 6500);
  }
  async function api(path, body, asBlob) {
    const options = {headers:{},credentials:"same-origin"};
    if (token) options.headers.Authorization = "Bearer " + token;
    if (body !== undefined) { options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(body); }
    const response = await fetch(path, options);
    if (!response.ok) {
      if (response.status === 401) $("accessPanel").hidden = false;
      let msg = "Request failed (" + response.status + ")";
      try { msg = (await response.json()).error || msg; } catch (_) {}
      throw new Error(msg);
    }
    return asBlob ? response.blob() : response.json();
  }
  async function download(path, filename) {
    const blob = await api(path, undefined, true), url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }
  function bind(id, action) {
    $(id).addEventListener("click", async function () {
      const button = $(id); button.disabled = true;
      try { await action(); } catch (e) { notice(e.message, true); }
      finally {
        button.disabled = (id==="startBtn" || id==="practiceBtn") && learningState ?
          !!learningState.enabled || learningState.phase==="stopping" : false;
      }
    });
  }
  function renderState(s) {
    state = s;
    const p = s.portfolio, r = s.runtime, day = s.risk_day || {};
    $("equity").textContent = money(p.equity);
    $("equityNote").textContent = p.equity_stale ? "Stale quote: marked equity may be outdated" : "Starting balance · " + money(p.starting_balance);
    $("return").textContent = pct(p.return_pct); $("return").className = tone(p.return_pct);
    $("realized").textContent = "Realized P&L · " + money(p.realized_pnl);
    $("openRisk").textContent = money(p.open_risk_usd); $("exposure").textContent = "Position value · " + money(p.gross_exposure_usd);
    $("profiles").textContent = Object.keys(s.active_profiles || {}).length;
    $("runtimeBadge").textContent = r.running ? (s.settings.entries_paused ? "Entries paused" : "Paper trader running") : (r.stream_status === "stopping" ? "Stopping" : "Stopped");
    $("runtimeBadge").className = "badge" + (r.running ? " positive" : "");
    $("startBtn").disabled = r.running; $("stopBtn").disabled = !r.running && r.stream_status !== "stopping";
    $("pauseBtn").textContent = s.settings.entries_paused ? "Resume entries" : "Pause entries";
    $("streamState").textContent = r.last_error ? "Data error: " + r.last_error : (r.stream_message || "Paper trader is stopped.");
    $("bootstrapState").textContent = r.running && !r.bootstrapped ? "Loading market history: " + r.bootstrap_done + " / " + r.bootstrap_total + " markets" : (r.last_tick_age_seconds != null ? "Latest quote received " + num(r.last_tick_age_seconds,0) + " seconds ago" : "");
    $("dayPnl").textContent = money(day.pnl); $("dayPnl").className = tone(day.pnl);
    $("dayNote").textContent = day.date ? day.date + " · Change in marked equity since today's baseline" : "Start the paper trader to begin tracking today.";
    $("goalFill").style.width = Math.max(0, Math.min(100, (day.pnl || 0) / 15 * 100)) + "%";
    $("entryState").textContent = day.halted ? "Daily loss threshold reached. New entries are blocked until the next UTC day." : (s.settings.entries_paused ? "New entries paused. Existing positions remain monitored while running." : (s.settings.validated_only ? "Only strategies with a current passing historical profile can enter." : "Experiment mode: unvalidated paper trades use one quarter of configured risk."));
    $("positions").innerHTML = s.positions.length ? s.positions.map(function (p) {
      return "<tr><td><b>" + escape(p.product_id) + "</b><small>" + escape(family(p.family)) + "</small></td><td>" + price(p.entry) + "</td><td>" + price(p.stop) + "<small>" + price(p.target) + "</small></td><td>" + money(p.risk_usd) + '</td><td class="' + tone(p.unrealized_pnl) + '">' + money(p.unrealized_pnl) + (p.price_stale ? "<small>Stale quote</small>" : "") + '</td><td><button class="small" data-close="' + escape(p.product_id) + '">Close</button></td></tr>';
    }).join("") : emptyRow(6,"No open paper positions.");
    $("marketsTable").innerHTML = s.coins.length ? s.coins.map(function (c) {
      const blocks = rejectionSummary(c.rejections);
      return "<tr><td><b>" + escape(c.product_id) + "</b></td><td>" + price(c.price) + '</td><td class="' + (c.price_stale ? "negative" : "") + '">' + (c.quote_age_seconds == null ? "No quote" : num(c.quote_age_seconds,0) + "s") + "</td><td>" + ["5m","15m","1h","4h"].map(function (iv) { return c.bar_counts[iv] || 0; }).join(" / ") + "</td><td>" + escape(c.regime) + "<small>" + escape(c.structure) + "</small></td><td>" + escape(c.last_decision || c.readiness) +
        (blocks ? '<details><summary>Candidate checks</summary><small>'+blocks+'</small></details>' : '') + "</td></tr>";
    }).join("") : emptyRow(6,"Start the paper trader to load markets.");
    if (!settingsLoaded) {
      $("autoFee").value = Number((s.settings.fee_rate*100).toFixed(6));
      const form = $("settingsForm");
      Object.keys(s.settings).forEach(function (k) {
        const input = form.elements.namedItem(k);
        if (!input) return;
        if (input.type === "checkbox") input.checked = s.settings[k];
        else input.value = percentFields.has(k) ? Number((s.settings[k] * 100).toFixed(6)) : s.settings[k];
      });
      settingsLoaded = true;
    }
    $("researchCosts").textContent = "Current assumptions: " + s.settings.decision_interval + " candles · " + pct(s.settings.fee_rate * 100) + " fee per side · " + pct(s.settings.slippage_rate * 100) + " slippage per fill + 0.05% assumed half-spread. Stress test multiplies costs by 1.5.";
  }
  function drawCurve(points) {
    if (points.length < 2) { $("balanceChart").innerHTML = '<p class="empty">Your balance history will appear after a paper trade closes.</p>'; return; }
    const balances = points.map(function (p) { return p.balance; }), lo = Math.min.apply(null,balances), hi = Math.max.apply(null,balances);
    const spread = Math.max(hi - lo, 2), bottom = lo - spread * .1, top = hi + spread * .1;
    const coords = points.map(function (p,i) { return (55 + i / (points.length - 1) * 535).toFixed(2) + "," + (175 - (p.balance - bottom) / (top - bottom) * 155).toFixed(2); }).join(" ");
    $("balanceChart").innerHTML = '<svg viewBox="0 0 620 205" role="img" aria-label="Realized paper balance after each closed trade"><line x1="55" y1="175" x2="590" y2="175" stroke="#263342"/><line x1="55" y1="20" x2="590" y2="20" stroke="#263342"/><text x="0" y="27">' + escape(money(top)) + '</text><text x="0" y="180">' + escape(money(bottom)) + '</text><polyline fill="none" stroke="#56d6bc" stroke-width="2.5" points="' + coords + '"/><text x="55" y="201">Start</text><text x="535" y="201">Latest</text></svg>';
  }
  function renderAnalytics(a) {
    $("tradeCount").textContent = a.closed_trades + " closed trades";
    $("winRate").textContent = pct(a.win_rate); $("profitFactor").textContent = num(a.profit_factor); $("profitFactor").title = a.profit_factor_note || "";
    $("expectancy").textContent = num(a.expectancy_r); $("drawdown").textContent = pct(a.max_closed_drawdown_pct);
    drawCurve(a.equity_curve);
    $("strategyResults").innerHTML = a.strategies.length ? '<div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Trades</th><th>Net P&L</th><th>Mean net R</th></tr></thead><tbody>' + a.strategies.map(function (x) {
      return "<tr><td>" + escape(family(x.family)) + "</td><td>" + x.trades + '</td><td class="' + tone(x.net_pnl) + '">' + money(x.net_pnl) + "</td><td>" + num(x.expectancy_r) + "</td></tr>";
    }).join("") + "</tbody></table></div>" : '<p class="empty">No closed trades to summarize.</p>';
  }
  function renderJournal(rows) {
    $("journalTable").innerHTML = rows.length ? rows.map(function (t) {
      const review=t.trade_review;
      const detail=review && review.outcome ? '<details><summary>At-close review</summary><p>'+escape(review.outcome.replace(/_/g," "))+
        '; fees '+num(review.fee_r,3)+'R; best observed net mark '+num(review.best_net_r,3)+'R; giveback '+num(review.giveback_r,3)+
        'R.</p><p>'+escape((review.findings || []).join(" · ").replace(/_/g," "))+'</p><p class="footnote">Observed quotes may not capture every price between updates.</p></details>' : '';
      return "<tr><td><b>" + escape(t.product_id) + "</b><small>" + escape(date(t.opened_at)) + "</small></td><td>" + escape(family(t.family)) + "</td><td>" + escape(t.status) + '</td><td class="' + tone(t.pnl) + '">' + money(t.pnl) + "</td><td>" + num(t.result_r) + "</td><td>" + escape(t.exit_reason) +detail+ "</td></tr>";
    }).join("") : emptyRow(6,"No paper trades recorded.");
  }
  function rejectionSummary(counts) {
    const labels = {
      trading_cost_too_high:"Trading costs too high",
      net_reward_too_small:"Reward after costs too small",
      entry_gap_too_large:"Entry price moved too far",
      daily_history_not_ready:"Needs 21 complete, consecutive daily candles",
      daily_downtrend:"Daily trend is falling",
      no_daily_momentum:"Daily trend and weekly momentum do not agree",
      no_prior_compression:"No preceding volatility contraction",
      no_expansion_breakout:"No confirmed volatility breakout",
      no_support_reclaim:"Support was not reclaimed",
      no_rsi_recovery:"RSI has not recovered above 40",
      missing_market_candles:"Missing market candles",
      daily_loss_limit:"Daily loss halt",
      insufficient_learning_samples:"Too few completed training examples",
      nonpositive_recent_return:"Recent learned returns are not positive",
      recent_context_losses:"Similar recent setups lost money after costs",
      low_estimated_return:"Estimated return below the entry threshold",
      prediction_error_too_large:"Prediction error leaves too little estimated return",
      no_positive_learned_setup:"No candidate passed the learning checks",
      no_current_learning_model:"No current qualifying model"
    };
    return Object.entries(counts || {}).filter(function (entry) { return entry[1]>0; })
      .sort(function (a,b) { return b[1]-a[1]; }).slice(0,3).map(function (entry) {
        return escape(labels[entry[0]] || entry[0].replace(/_/g," "))+": "+num(entry[1],0);
      }).join(" · ");
  }
  function renderLearningDiagnostics(r) {
    const diagnostics=r.training_diagnostics;
    if (!diagnostics) return "";
    const totals=diagnostics.totals || {};
    const training=rejectionSummary(totals.rejections);
    const entryBlocks=rejectionSummary(totals.entry_rejections);
    const explored=rejectionSummary(totals.training_cost_overrides);
    const held=(r.holdout || {}).signal_funnel || {};
    const execution=rejectionSummary(held.rejections);
    const learned=rejectionSummary(held.learning_candidate_rejections);
    const families=Object.create(null);
    (diagnostics.candidates || []).forEach(function (candidate) {
      const key=(candidate.params || {}).family || "unknown";
      families[key]=(families[key] || 0)+(candidate.resolved_examples || 0);
    });
    const familyTable='<details><summary>Training examples by strategy</summary><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Completed examples</th></tr></thead><tbody>'+Object.entries(families).map(function (entry) {
      return '<tr><td>'+escape(family(entry[0]))+'</td><td>'+num(entry[1],0)+'</td></tr>';
    }).join('')+'</tbody></table></div><p class="footnote">Training examples can overlap. More examples do not mean higher profit.</p></details>';
    return '<p class="footnote"><b>Training:</b> '+num(r.historical_examples,0)+
      ' completed examples from '+num(totals.qualified_setups,0)+' signal matches and '+
      num(totals.entries_opened,0)+' simulated entries across '+num(r.candidate_count,0)+
      ' variants. Variants can overlap on the same candles.</p>'+
      (typeof totals.exploratory_entries === "number" ? '<p class="footnote"><b>Learning from costly setups:</b> '+
        num(totals.exploratory_entries,0)+' hypothetical entries studied despite the cost screen, with all fees and slippage charged. '+
        'These examples do not approve a strategy for trading.'+(explored ? ' '+explored+'.' : '')+'</p>' : '')+
      (totals.gap_censored_examples ? '<p class="footnote"><b>Unknown outcomes:</b> '+num(totals.gap_censored_examples,0)+
        ' training entries crossed missing prices and were excluded from learning. No exit was invented.</p>' : '')+
      (typeof totals.loss_pause_overrides === "number" ? '<p class="footnote"><b>Practice continued after losses:</b> '+
        num(totals.loss_pause_overrides,0)+' longer loss-streak pauses skipped by independent training simulations. Routine entry spacing and full costs still apply.</p>' : '')+
      (entryBlocks ? '<p class="footnote"><b>Training entry blocks after a signal matched:</b> '+entryBlocks+'</p>' : '')+
      (training ? '<p class="footnote"><b>Most common training blocks:</b> '+training+'</p>' : '')+
      (execution ? '<p class="footnote"><b>Final-test entry blocks:</b> '+execution+'</p>' : '')+
      (learned ? '<p class="footnote"><b>Final-test candidate blocks:</b> '+learned+'</p>' : '')+familyTable;
  }
  function renderLearningComparison(r) {
    const comparison=r.upgrade_comparison, coverage=r.data_selection, regimes=r.regime_examples;
    let html="";
    if (r.market_data) html+='<p class="footnote"><b>Price data:</b> '+escape(r.market_data.provider)+
      ' recorded market candles. Trades are simulated.</p>';
    const repair=(r.market_data || {}).gap_repair, daily=r.daily_data;
    if (repair) html+='<p class="footnote"><b>Missing candle recovery:</b> '+num(repair.recovered_direct,0)+
      ' recovered directly and '+num(repair.recovered_from_smaller_candles,0)+' rebuilt from complete smaller candles on the latest check. '+
      num(repair.missing_after,0)+' missing intervals remain. Prices are never interpolated.</p>';
    if (daily) html+='<p class="footnote"><b>Daily market context:</b> '+
      (daily.source==="independent_daily_candles" ? 'Separate daily candles' : 'Complete days from the intraday candles')+
      '; available on '+num(daily.holdout_candles ? 100*daily.holdout_ready_candles/daily.holdout_candles : 0,1)+
      '% of final-test candles. Only days already closed can inform a decision.</p>';
    if ((r.market_data || {}).daily_context?.status==="daily_download_unavailable")
      html+='<p class="footnote">Separate daily history could not be downloaded. This run used only complete days available in the intraday data.</p>';
    if (r.replay) html+='<p class="footnote"><b>Past-market practice:</b> '+escape(date(r.replay.training_start_ts,true))+
      ' to '+escape(date(r.replay.training_end_ts,true))+'. Final later test: '+escape(date(r.replay.test_start_ts,true))+
      ' to '+escape(date(r.replay.test_end_ts,true))+'. Decisions cannot see later prices.</p>';
    if (regimes) html+='<p class="footnote"><b>Completed examples by market condition:</b> Rising '+
      num(regimes.BULL,0)+' · Falling '+num(regimes.BEAR,0)+' · Sideways '+num(regimes.CHOP,0)+'. Includes overlapping variants.</p>';
    if (coverage && coverage.excluded_candles) html+='<p class="footnote">Used '+num(coverage.used_hours,0)+
      ' hours of continuous history. Excluded '+num(coverage.excluded_candles,0)+' earlier candles because of gaps.</p>';
    if (coverage && coverage.segment_count) html+='<p class="footnote"><b>Recorded history retained:</b> '+num(coverage.used_hours,0)+
      ' hours across '+num(coverage.segment_count,0)+' continuous sections. '+num(coverage.missing_intervals,0)+
      ' missing intervals were not filled in. Indicators restart in each section; '+num(coverage.warmup_candles,0)+
      ' observed candles are used for warmup before entries can be considered.</p>';
    if (comparison) html+='<p class="footnote"><b>Change versus pooled learning:</b> '+money(comparison.net_pnl_difference)+
      ' in the final test; '+money(comparison.stress_net_pnl_difference)+' at higher costs. Negative means this upgrade did worse. This comparison does not choose the model.</p>';
    if (r.strategy_expansion_comparison) {
      const expansion=r.strategy_expansion_comparison;
      html+='<p class="footnote"><b>Effect of adding the three new strategies:</b> '+money(expansion.net_pnl_difference)+
        ' in the final test; '+money(expansion.stress_net_pnl_difference)+' at higher costs. Compared with the original 16 candidates using the same features, model seed and risk. Negative means the additions made this test worse. This comparison does not choose the model.</p>';
    }
    if (r.benchmarks) html+='<p class="footnote">Same-period buy-and-hold net result on $500: '+money(r.benchmarks.buy_hold_net_pnl)+
      '. Holding cash: $0. Exposure differs from the trading policy.</p>';
    if (r.next_review_at) html+='<p class="footnote">Next scheduled historical review: '+escape(date(r.next_review_at))+'.</p>';
    return html;
  }
  function renderCostLearning(r) {
    let html="";
    if (r.failure_learning) html+='<details><summary>What happened in the failed trade examples?</summary><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Stopped out</th><th>Near break-even</th><th>Fees erased a gain</th><th>Time exit loss</th><th>Other losses</th></tr></thead><tbody>'+
      Object.entries(r.failure_learning.by_family || {}).map(function (entry) {
        const a=entry[1].causes || {};
        return '<tr><td>'+escape(family(entry[0]))+'</td><td>'+num(a.stopped_out || 0,0)+
          '</td><td>'+num(a.near_break_even || 0,0)+'</td><td>'+num(a.fee_erased_gain || 0,0)+'</td><td>'+num(a.stalled_trade || 0,0)+
          '</td><td>'+num(a.other_loss || 0,0)+'</td></tr>';
      }).join('')+'</tbody></table></div><p class="footnote">The learner uses recent net outcomes from similar market conditions to adjust entries. These are overlapping historical examples. Exit labels describe what happened; they do not prove why a trade failed.</p></details>';
    if (r.outcome_memory_comparison) html+='<p class="footnote"><b>Effect of the new outcome memory:</b> '+
      money(r.outcome_memory_comparison.net_pnl_difference)+' in the final test; '+
      money(r.outcome_memory_comparison.stress_net_pnl_difference)+
      ' at higher costs, compared with the same learner with this adjustment disabled. Negative means it did worse.</p>';
    const feedback=r.holdout_shadow_feedback;
    if (feedback) html+='<p class="footnote"><b>Continued historical practice:</b> '+num(feedback.resolved_examples,0)+
      ' additional hypothetical outcomes learned during the later test, including opportunities the account skipped. '+
      'Each outcome becomes available only after its exit candle closes. These are overlapping training examples, not account trades.</p>';
    const attribution=r.performance_attribution;
    if (attribution) html+='<details><summary>Which strategies earned or lost money?</summary><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Account trades</th><th>Before fees</th><th>Fees</th><th>Net result</th></tr></thead><tbody>'+
      Object.entries(attribution.by_family || {}).map(function (entry) {
        const a=entry[1];
        return '<tr><td>'+escape(family(entry[0]))+'</td><td>'+num(a.trades,0)+'</td><td>'+money(a.gross_pnl)+
          '</td><td>'+money(a.fees_paid)+'</td><td class="'+tone(a.net_pnl)+'">'+money(a.net_pnl)+'</td></tr>';
      }).join('')+'</tbody></table></div><p class="footnote">'+escape(attribution.scope)+'</p></details>';
    const control=r.account_feedback_comparison;
    if (control) html+='<p class="footnote"><b>Learning only from selected account trades:</b> '+money((control.baseline || {}).net_pnl)+
      ' after costs; '+money((control.baseline_stressed || {}).net_pnl)+' at higher costs. '+
      'This tests the feedback used between scheduled historical reviews. It must also be profitable before qualification.</p>';
    const evaluation=r.evaluation;
    if (evaluation && evaluation.reuses_reviewed_history) {
      html+='<p class="callout"><b>Research on previously reviewed history.</b> A report ending '+escape(date(evaluation.reviewed_through_ts,true))+
        ' informed this learner. An improved replay of that history does not count as independent confirmation.</p>';
      const fresh=evaluation.confirmation;
      if (fresh) html+='<p class="footnote"><b>Confirmation on later prices:</b> '+escape(date(fresh.start_ts,true))+
        ' to '+escape(date(fresh.end_ts,true))+'. '+num(fresh.metrics.trades,0)+' selected trades; '+money(fresh.metrics.net_pnl)+
        ' after costs, '+money(fresh.stressed.net_pnl)+' at higher costs. A small or incomplete test cannot qualify.</p>';
      else html+='<p class="footnote">No later price window is available in this download yet. Historical practice is complete; new confirmation data is still needed.</p>';
      if (fresh && fresh.account_feedback_control) html+='<p class="footnote"><b>Selected-trade feedback on later prices:</b> '+
        money(fresh.account_feedback_control.metrics.net_pnl)+' after costs; '+money(fresh.account_feedback_control.stressed.net_pnl)+
        ' at higher costs. Both must also pass.</p>';
    }
    return html;
  }
  function renderTradeReviews(r) {
    const study=r.trade_reviews;
    if (!study) return "";
    const development=study.development || {}, selected=study.selected || {};
    const labels={near_break_even:"Near break-even",full_risk_loss:"Loss of at least 1R",loss:"Smaller loss",profit:"Profit"};
    const findings={fees_erased_gain:"Fees erased a gross gain",gave_back_gains:"An observed gain was given back",
      little_follow_through:"Little favorable movement before exit",loss_exceeded_plan:"Loss exceeded the planned stop risk",
      entry_bar_stop:"Stopped during the entry candle",time_exit:"Reached the holding-time limit",
      high_fee_burden:"Fees used at least 0.25R",against_daily_trend:"Entry opposed the completed daily trend",
      profitable_exit:"Finished positive after costs"};
    function cases(items,title) {
      items=items || [];
      if (!items.length) return "";
      return '<details><summary>'+escape(title)+' ('+num(items.length,0)+')</summary>'+
        (items.length>12 ? '<p class="footnote">Showing the first 12 priority cases. The download contains the full recorded sample.</p>' : '')+
        items.slice(0,12).map(function (c) {
          const review=c.review || {}, context=c.entry_context || {}, daily=context.daily || {};
          const after=((c.post_exit || {}).observations || []).map(function (o) {
            return num(o.hours,0)+'h: '+(o.status==="complete" ? num(o.end_move_pct,2)+'% ending move; '+
              num(o.favorable_move_pct,2)+'% favorable / '+num(o.adverse_move_pct,2)+'% adverse extreme' :
              escape(o.status==="pending" ? "awaiting enough later candles" : o.status==="missing_candles" ? "missing candles" : o.status));
          }).join(' · ');
          const alternative=c.break_even_stop || {};
          return '<details><summary>'+escape(family(c.strategy_family))+' · '+escape(labels[review.outcome] || review.outcome || "Trade")+
            ' · '+escape(date(c.entry_ts,true))+' · '+money(c.pnl)+'</summary>'+
            '<p>Net '+num(review.net_r,3)+'R; fees '+num(review.fee_r,3)+'R. Best observed net mark '+num(review.best_net_r,3)+
            'R; giveback '+num(review.giveback_r,3)+'R. Held '+num(review.holding_hours,2)+' hours.</p>'+
            '<p><b>What happened:</b> '+(review.findings || []).map(function (key) {return escape(findings[key] || key);}).join(' · ')+
            '</p><p><b>At entry:</b> '+escape(context.regime || "unknown")+'; RSI '+num(context.rsi,1)+'; volume z '+num(context.volume_z,2)+
            '; daily trend '+escape(!daily.ready ? "unavailable" : daily.trend_up ? "up" : daily.trend_down ? "down" : "mixed")+'.</p>'+
            '<p><b>After exit:</b> '+after+'. These observed moves are relative to the exit price, in the trade direction; they are not account profits.</p>'+
            (alternative.status==="complete" ? '<p><b>Fixed exit experiment:</b> '+num(alternative.net_r,3)+'R ('+
              num(alternative.difference_r,3)+'R difference) using a fee-covered break-even stop only after a previous candle closed at +1 net R. '+
              'This is a hypothetical result; it does not change the learned reward or select a trading rule.</p>' : '')+'</details>';
        }).join('')+'</details>';
    }
    return '<details><summary>Loss and break-even study</summary><p>Near break-even means within '+num(study.break_even_band_r,2)+
      'R of zero after costs. These outcomes receive extra review attention and keep their actual net return.</p>'+
      '<div class="table-wrap"><table><thead><tr><th>Outcome</th><th>Development examples</th><th>Selected test trades</th></tr></thead><tbody>'+
      Object.entries(labels).map(function (entry) {return '<tr><td>'+escape(entry[1])+'</td><td>'+num((development.outcomes || {})[entry[0]] || 0,0)+
        '</td><td>'+num((selected.outcomes || {})[entry[0]] || 0,0)+'</td></tr>';}).join('')+'</tbody></table></div>'+
      '<p class="footnote">Development examples overlap. Detailed cases are a priority sample; the counts above cover all reviewed outcomes. '+
      'Observations suggest questions to test and do not prove why a trade lost. Later candles never enter its original decision.</p>'+
      cases(selected.cases,"Selected account trade reviews")+cases(development.cases,"Priority practice reviews")+'</details>';
  }
  function renderLearning(s) {
    learningState=s;
    if (!practiceSelectionLoaded) {
      const saved=s.practice_symbols || s.default_practice_symbols;
      if (Array.isArray(saved) && saved.length) $("practiceSymbols").value=saved.map(function (symbol) { return symbol.replace(/-USD$/, ""); }).join(", ");
      practiceSelectionLoaded=true;
    }
    $("practiceSymbols").disabled=!!s.enabled || s.phase==="stopping";
    const phases={stopped:"Ready",starting:"Loading markets",downloading:"Collecting history",
      learning:"Learning",testing:"Testing",watching:"Watching & learning",waiting:"Waiting for evidence",
      error:"Needs attention",stopping:"Stopping",completed:"Practice complete"};
    $("learningPhase").textContent=phases[s.phase] || s.phase;
    $("learningMessage").textContent=s.message;
    $("learningHours").textContent=Math.round(s.market_data_hours || 0).toLocaleString();
    $("learningExamples").textContent=num(s.historical_examples || 0,0);
    $("learningTestTrades").textContent=num((s.results || []).reduce(function (sum,r) { return sum+((r.holdout || {}).trades || 0); },0),0);
    $("learningTrades").textContent=String(s.forward_learning_trades || 0);
    $("learningMarkets").textContent=String((s.active_markets || []).length);
    $("startBtn").disabled=!!s.enabled || s.phase==="stopping";
    $("practiceBtn").disabled=!!s.enabled || s.phase==="stopping";
    $("startBtn").textContent=(s.results || []).length ? "Resume learning & paper trading" : "Start learning & paper trading";
    $("stopBtn").disabled=!s.enabled && !s.paper_running && s.phase!=="stopping";
    $("learningResults").innerHTML=(s.results || []).length ? s.results.map(function (r) {
      const h=r.holdout || {}, stressed=r.holdout_stressed || {}, d=r.daily_goal || {};
      const stale=(s.current_policy_version && r.policy_version!==s.current_policy_version) ||
        (s.current_report_version && r.learning_report_version!==s.current_report_version);
      const incomplete=h.complete===false || stressed.complete===false;
      return '<div class="learning-result"><b>'+escape(r.symbol)+'</b><span class="badge '+(r.validated && !stale ? "positive" : "negative")+'">'+
        (stale ? "Updated learner · practice again" : (r.validated ? "Passed historical checks" : "Not qualified"))+'</span><p>'+
        (r.error ? escape(r.error) : incomplete ? 'Final test incomplete: missing candles interrupted an open position. A full-period result is unavailable.' :
          ((r.evaluation || {}).reuses_reviewed_history ? 'Reused-history test: ' : 'Final test: ')+money(h.net_pnl)+' after costs across '+num(h.trades,0)+
          ' trades. At higher costs: '+money(stressed.net_pnl)+'. Average realized per day: '+money(d.mean_net_per_day)+'.')+
        '</p><p class="footnote">'+escape((r.rejection_reasons || []).join(" "))+'</p>'+
        renderCostLearning(r)+renderTradeReviews(r)+renderLearningDiagnostics(r)+renderLearningComparison(r)+
        (r.data_quality ? '<button class="small" data-learning-data="'+escape(r.symbol)+'" data-interval="'+escape(r.interval)+'">Download candles &amp; report</button>' : '')+'</div>';
    }).join("")+'<p class="footnote">Each market test starts with $500. These results are not a combined account return or a profit forecast.</p>' :
      '<p class="empty">No completed learning run yet.</p>';
  }
  function renderCandidateSelection(selection) {
    if (!selection || !Array.isArray(selection.candidates)) return "";
    const labels = {failed_training:"Failed training", not_shortlisted:"Outside top five",
      rejected_validation:"Failed validation", survived_validation:"Passed; lower rank", selected:"Selected for holdout"};
    const rows = selection.candidates.map(function (c) {
      const p=c.params || {};
      return '<tr><td>'+escape(family(p.family))+'<small>Candidate '+escape(c.candidate_id)+
        ' · Stop '+num(p.stop_atr)+' ATR · Target '+num(p.rr2)+'× · Volume z ≥ '+num(p.volume_z_min)+
        '</small></td><td>'+money(c.training && c.training.net_pnl)+'</td><td>'+money(c.validation && c.validation.net_pnl)+
        '</td><td>'+money(c.validation_stressed && c.validation_stressed.net_pnl)+'</td><td>'+escape(labels[c.selection_status] || c.selection_status)+'</td></tr>';
    }).join("");
    return '<details><summary>Inspect all '+selection.candidates.length+' candidates</summary><p class="footnote">'+escape(selection.scope)+
      ' Ranking uses net R with a sample-size penalty, subject to trade-count and drawdown screens.</p><div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Training net P&amp;L</th><th>Validation net P&amp;L</th><th>Validation at 1.5× costs</th><th>Selection outcome</th></tr></thead><tbody>'+rows+'</tbody></table></div></details>';
  }
  function renderResearch(r) {
    $("researchMessage").textContent = r.message || r.status;
    const running = ["running","training","downloading"].includes(r.status);
    $("researchRun").disabled = running; $("researchCancel").disabled = !running;
    $("researchProgress").value = r.status === "complete" ? 1 : ((r.completed || 0) / (r.total || 1));
    if (!r.results || !r.results.length) {
      $("researchResults").innerHTML = '<p class="empty">' + (running ? "Research in progress. Completed market reports will appear here." : "No completed results. A valid outcome is that every strategy is rejected.") + "</p>"; return;
    }
    $("researchResults").innerHTML = r.results.map(function (x) {
      const h = x.holdout || {}, stress = x.holdout_stressed || {}, d = x.daily_goal || {}, ci = x.holdout_expectancy_interval || {};
      const stale = !!r.active_engine_version && x.engine_version !== r.active_engine_version;
      const c=x.upgrade_comparison;
      const comparison=c ? '<div class="callout">V9 filters versus the same rule without them: net P&amp;L difference <b>'+money(c.net_pnl_difference)+'</b>, at stressed costs <b>'+money(c.stress_net_pnl_difference)+'</b>; trade difference '+num(c.trade_count_difference)+'.<p class="footnote">'+escape(c.scope)+'</p></div>' : "";
      const candidates=renderCandidateSelection(x.candidate_selection);
      return '<article class="panel"><div class="panel-title"><h2>' + escape(x.symbol) + ' <span class="muted">' + escape(x.interval) + '</span></h2><span class="badge ' + (x.validated && !stale ? "positive" : "negative") + '">' + (stale ? "OLDER ENGINE · RERUN RESEARCH" : (x.validated ? "PASSES HISTORICAL GATE" : "NOT QUALIFIED")) + '</span></div><p class="muted">' + escape(x.selected_params ? family(x.selected_params.family) : "No strategy survived selection") + '</p><div class="result-metrics"><div>Holdout net return<strong class="' + tone(h.return_pct) + '">' + pct(h.return_pct) + '</strong></div><div>Holdout trades<strong>' + (h.trades == null ? "0" : h.trades) + '</strong></div><div>At 1.5× costs<strong>' + pct(stress.return_pct) + '</strong></div><div>Mean realized / day<strong>' + money(d.mean_net_per_day) + '</strong></div></div><p class="muted">Days reaching $10: ' + (d.days_at_least_10 || 0) + " / " + (d.calendar_days || 0) + " · Days reaching $15: " + (d.days_at_least_15 || 0) + " · Losing days: " + (d.losing_days || 0) + '</p><p class="footnote">Cash benchmark: 0% · Buy and hold after costs: ' + pct(x.buy_hold_return_pct) + " · Positive walk-forward windows: " + x.profitable_folds + "/3 · Historical mean R interval: " + num(ci.lower_r) + " to " + num(ci.upper_r) + '</p><ul class="result-reasons">' + x.rejection_reasons.map(function (reason) { return "<li>" + escape(reason) + "</li>"; }).join("") + '</ul>' + candidates + comparison + '<p class="footnote">' + escape(x.scope) + " " + escape(x.warning) + "</p></article>";
    }).join("");
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const responses = await Promise.allSettled([
        api("/api/continuous/status"), api("/api/continuous/analytics"),
        api("/api/continuous/trades?limit=100"), api("/api/continuous/activity?limit=20"), api("/api/research/status"), api("/api/learning/status")
      ]);
      const renderers = [renderState,renderAnalytics,renderJournal,function (rows) {
        $("activity").innerHTML = rows.length ? rows.map(function (a) { return '<div class="activity-row">' + escape(a.message) + "<small>" + escape(date(a.ts)) + "</small></div>"; }).join("") : '<p class="empty">No activity yet.</p>';
      },renderResearch,renderLearning];
      let firstError = null;
      responses.forEach(function (response,i) { if (response.status === "fulfilled") renderers[i](response.value); else if (!firstError) firstError = response.reason; });
      if (firstError) throw firstError;
    } catch (e) { notice(e.message, true); } finally { busy = false; }
  }
  window.addEventListener("coinbase-fee-applied",function () { settingsLoaded=false; notice("Coinbase fee applied. Rerun research with the updated fee."); refresh(); });
  document.querySelectorAll("[data-tab]").forEach(function (button) {
    button.addEventListener("click",function () {
      document.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("active", b === button); });
      document.querySelectorAll(".tab-panel").forEach(function (panel) { panel.hidden = panel.id !== button.dataset.tab; });
    });
  });
  bind("startBtn",async function () {
    const input=$("autoFee");
    if (!input.value.trim() || !input.reportValidity()) throw new Error("Enter your Coinbase fee per side.");
    await api("/api/learning/start",{fee_rate:Number(input.value)/100}); settingsLoaded=false; await refresh();
  });
  $("practiceSymbols").addEventListener("input",function () { practiceSelectionLoaded=true; });
  bind("practiceBtn",async function () {
    const input=$("autoFee");
    if (!input.value.trim() || !input.reportValidity()) throw new Error("Enter your Coinbase fee per side.");
    const symbols=Array.from(new Set($("practiceSymbols").value.toUpperCase().split(/[,\s]+/).filter(Boolean).map(function (symbol) {
      return symbol.endsWith("-USD") ? symbol : symbol+"-USD";
    })));
    if (!symbols.length || symbols.length>20) throw new Error("Choose one to twenty coins for historical practice.");
    if (symbols.some(function (symbol) { return !/^[A-Z0-9]{2,16}-USD$/.test(symbol); })) throw new Error("Enter Coinbase USD tickers such as HBAR, XRP, XLM.");
    await api("/api/learning/practice",{fee_rate:Number(input.value)/100,symbols:symbols}); settingsLoaded=false; await refresh();
  });
  bind("stopBtn",async function () { await api("/api/continuous/stop",{}); await refresh(); });
  bind("pauseBtn",async function () { await api("/api/continuous/pause",{paused:!(state && state.settings.entries_paused)}); await refresh(); });
  bind("refreshRankings",async function () {
    const rows = await api("/api/continuous/opportunities");
    $("rankings").innerHTML = rows.length ? rows.map(function (x) { return '<div class="rank-row"><div><b>' + escape(x.product_id) + "</b><small>" + escape(family(x.family)) + " · " + escape(x.regime) + " · " + escape(date(x.signal_ts,true)) + '</small></div><span class="score">' + num(x.score,1) + "</span></div>"; }).join("") : '<p class="empty">No qualifying setups in the current snapshot.</p>';
  });
  $("positions").addEventListener("click",async function (event) {
    const button = event.target.closest("[data-close]"); if (!button) return;
    button.disabled = true;
    try { const result = await api("/api/continuous/close",{product_id:button.dataset.close}); notice("Paper position closed. Net P&L: " + money(result.pnl)); await refresh(); }
    catch (e) { notice(e.message,true); } finally { button.disabled = false; }
  });
  $("researchForm").addEventListener("submit",async function (event) {
    event.preventDefault(); $("researchRun").disabled = true;
    try { await api("/api/research/start",{symbols:$("researchSymbols").value.split(/[,\s]+/).filter(Boolean),days:Number($("researchDays").value)}); await refresh(); }
    catch (e) { notice(e.message,true); $("researchRun").disabled = false; }
  });
  bind("researchCancel",async function () { await api("/api/research/cancel",{}); notice("Cancellation requested."); });
  bind("researchExport",function () { return download("/api/research/export","research-results.json"); });
  bind("learningExport",function () { return download("/api/learning/export","learning-results.json"); });
  $("learningResults").addEventListener("click",async function (event) {
    const button=event.target.closest("[data-learning-data]"); if (!button) return;
    const symbol=button.dataset.learningData, interval=button.dataset.interval;
    button.disabled=true;
    try { await download("/api/learning/data?symbol="+encodeURIComponent(symbol)+"&interval="+encodeURIComponent(interval),symbol+"_"+interval+"_learning-data.zip"); }
    catch (e) { notice(e.message,true); } finally { button.disabled=false; }
  });
  bind("tradeExport",function () { return download("/api/continuous/export","paper-trades.csv"); });
  bind("backupBtn",function () { return download("/api/continuous/backup","crypto-account-backup.sqlite3"); });
  bind("resetBtn",async function () {
    if (prompt("Type RESET to clear the paper account journal and return to $500. A database backup is created first.") !== "RESET") return;
    await api("/api/continuous/reset",{confirm:"RESET",keep_memory:$("keepMemory").checked}); notice("Paper account reset. A backup was saved before the reset."); await refresh();
  });
  $("settingsForm").addEventListener("submit",async function (event) {
    event.preventDefault();
    const patch = {}, button = event.submitter; if (button) button.disabled = true;
    Array.from(event.target.elements).forEach(function (input) {
      if (!input.name) return;
      patch[input.name] = input.type === "checkbox" ? input.checked : (input.name === "decision_interval" ? input.value : Number(input.value) / (percentFields.has(input.name) ? 100 : 1));
    });
    try { await api("/api/continuous/settings",patch); settingsLoaded = false; notice("Settings saved."); await refresh(); }
    catch (e) { notice(e.message,true); } finally { if (button) button.disabled = false; }
  });
  $("accessForm").addEventListener("submit",async function (event) {
    event.preventDefault(); token = $("accessToken").value; sessionStorage.setItem("cryptoAccessToken",token); $("accessPanel").hidden = true; $("notice").hidden = true; await refresh();
  });
  async function poll() { if (!document.hidden) await refresh(); setTimeout(poll,5000); }
  poll();
})();
