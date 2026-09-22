"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const money = value => finite(value) ? new Intl.NumberFormat(undefined, {style:"currency", currency:"USD"}).format(value) : "—";
  const number = value => finite(value) ? value.toLocaleString(undefined, {maximumFractionDigits:2}) : "—";
  const when = value => value ? new Date(value).toLocaleString(undefined, {timeZone:"America/New_York", timeZoneName:"short"}) : "Not yet observed";
  let token = StockSession.getToken(), state, loading = false, initialized = false, selectedAccount = "", chartTimer;

  function notice(message = "", error = false) {
    $("notice").textContent = message;
    $("notice").hidden = !message;
    $("notice").className = "notice" + (error ? " error" : "");
  }
  async function api(path, body, blob = false) {
    const options = {credentials:"same-origin", headers:{}};
    if (token) options.headers.Authorization = "Bearer " + token;
    if (body !== undefined) {
      options.method = "POST"; options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      if (response.status === 401) { $("accessPanel").hidden = false; $("content").hidden = true; }
      let message = "Request failed (" + response.status + ")";
      try { message = (await response.json()).error || message; } catch (_) {}
      throw Error(message);
    }
    return blob ? response.blob() : response.json();
  }
  function renderChart() {
    const stock = state.universe.find(s => s.ticker === $("marketSymbol").value);
    if (!stock) return;
    $("selectedTitle").textContent = "Study " + stock.ticker;
    $("learnLink").href = "/stock-practice?symbol=" + encodeURIComponent(stock.ticker);
    $("strategyLink").href = "/strategy-lab?symbol=" + encodeURIComponent(stock.ticker);
    $("researchLink").hidden = !stock.research;
    $("researchLink").href = "/stocks#" + encodeURIComponent(stock.ticker);
    $("externalChart").href = "https://www.tradingview.com/symbols/" + stock.market_symbol.replace(":", "-") + "/";
    const period = $("chartPeriod").value;
    const range = ["1", "5", "15", "30"].includes(period) ? "1d" : period === "60" ? "1m" : period === "240" ? "3m" : "12m";
    const url = new URL("https://www.tradingview-widget.com/embed-widget/symbol-overview/");
    url.searchParams.set("locale", "en");
    url.hash = encodeURIComponent(JSON.stringify({
      width:"100%", height:"100%", colorTheme:"dark", isTransparent:false,
      backgroundColor:"#101a24", symbols:[[stock.ticker, stock.market_symbol + "|" + period]],
      chartOnly:false, showVolume:true, hideMarketStatus:false, hideDateRanges:false,
      chartType:"candlesticks", changeMode:"price-and-percent", dateRanges:[range + "|" + period],
      scalePosition:"right", "page-uri":location.origin + location.pathname,
      utm_source:location.hostname, utm_medium:"widget", utm_campaign:"symbol-overview"
    }));
    const frame = document.createElement("iframe");
    frame.src = url.href;
    frame.title = stock.name + ": stock price, percentage change and chart";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation");
    frame.setAttribute("allow", "fullscreen");
    $("chartStatus").textContent = "Loading market display…";
    clearTimeout(chartTimer);
    frame.addEventListener("load", () => {
      if ($("marketChart").firstElementChild !== frame) return;
      clearTimeout(chartTimer);
      $("chartStatus").textContent = "Check quote time and availability inside the display.";
    });
    frame.addEventListener("error", () => {
      if ($("marketChart").firstElementChild !== frame) return;
      clearTimeout(chartTimer);
      $("chartStatus").textContent = "Market display unavailable. Reload it or use the TradingView link.";
    });
    $("marketChart").replaceChildren(frame);
    chartTimer = setTimeout(() => {
      if ($("marketChart").firstElementChild === frame) $("chartStatus").textContent = "The chart is taking longer to load. Reload it or open the TradingView link.";
    }, 20000);
  }
  function renderAccount() {
    const accounts = state.forward;
    const account = accounts.find(a => a.id === selectedAccount) || accounts.find(a => a.status === "running") || accounts[0];
    $("paperEmpty").hidden = !!account;
    $("paperContent").hidden = !account;
    if (!account) return;
    selectedAccount = account.id;
    $("accountPicker").innerHTML = accounts.map(a => '<option value="' + esc(a.id) + '">' + esc(a.symbol + " · " + a.interval + " · " + a.status + " · " + when(a.created_ts)) + '</option>').join("");
    $("accountPicker").value = selectedAccount;
    const report = account.account, metrics = report && report.metrics;
    // Missing or incomplete results never become zero or a successful account.
    const complete = metrics && metrics.complete === true;
    const facts = [
      [money(complete ? metrics.ending_balance : null), "Marked paper equity", "Includes any open position mark"],
      [money(complete ? metrics.net_pnl : null), "Net paper P/L", "After modeled trading costs"],
      [number(report ? report.closed_trades : null), "Closed paper trades", "Actual simulated account exits"],
      [number(report ? report.model_updates : null), "Learning updates", "Resolved setups; may overlap"]
    ];
    $("accountFacts").innerHTML = facts.map(([v, title, note]) => '<div class="metric"><span>' + esc(title) + '</span><strong>' + esc(v) + '</strong><small>' + esc(note) + '</small></div>').join("");
    $("accountMessage").textContent = account.status.toUpperCase() + " · " + account.message;
    const position = metrics && metrics.open_position;
    $("position").textContent = !metrics ? "Waiting for the first account evaluation." : !complete ? "Account evaluation is incomplete; the current position and total return are unverified." : position ? "Open paper position: " + number(position.qty) + " shares of " + account.symbol + " · entry " + money(position.entry) + " · stop " + money(position.stop) : "No open paper position.";
    $("accountTime").textContent = "Registered " + when(account.created_ts) + " · Last evaluation " + when(account.updated_ts) + " · Candle close " + when(metrics && metrics.as_of_ts) + ". Values are last observed marks, not streaming balances.";
    $("stopAccount").hidden = account.status !== "running";
  }
  function renderJobs() {
    $("recentRuns").innerHTML = state.jobs.length ? state.jobs.map(j => '<article class="job-row"><div><a href="/stock-practice">' + esc(j.manifest.symbol + " · " + j.manifest.interval + " · " + j.manifest.mode) + '</a><span class="badge">' + esc(j.status) + '</span></div><p>' + esc(j.progress.message) + '</p></article>').join("") : '<p class="desk-empty">No stock learning runs yet. Choose a stock above to begin.</p>';
    const lab = state.strategy_lab;
    $("recentStrategies").innerHTML = lab.error ? '<p class="desk-empty">' + esc(lab.error) + '</p>' : lab.jobs.length ? lab.jobs.map(j => '<article class="job-row"><div><a href="/strategy-lab">' + esc(j.request.symbol + " · " + j.request.strategy.replace(/_/g, " ")) + '</a><span class="badge">' + esc(j.status) + '</span></div><p>' + esc(j.message) + '</p></article>').join("") : '<p class="desk-empty">No strategy tests yet. Compare an opening-range breakout or a price-structure strategy on recorded stock candles.</p>';
  }
  function render() {
    const market = state.market;
    $("marketClock").textContent = market.open ? "Regular session open" : "Regular session closed";
    $("sessionDot").classList.toggle("open", market.open);
    $("sessionDetail").textContent = market.open ? "Closes " + when(market.close_ts) : "Next open " + when(market.next_open_ts);
    $("researchCount").textContent = state.universe.filter(s => s.research).length;
    $("runCount").textContent = state.practice.total_jobs;
    $("queueCount").textContent = state.practice.pending_jobs + " queued or in progress";
    $("forwardCount").textContent = state.forward.filter(f => f.status === "running").length;
    $("providers").innerHTML = Object.entries(state.catalog.providers).map(([name, p]) => '<div class="provider-row"><strong>' + esc(name[0].toUpperCase() + name.slice(1)) + '</strong><span>' + (name === "yahoo" ? "Public historical feed" : p.available ? "Key configured" : "Needs server keys") + '</span></div>').join("");
    $("researchDate").textContent = "Research edition: " + state.research_as_of + ". Company notes and catalyst dates are dated research.";
    if (!initialized) {
      $("marketSymbol").innerHTML = state.universe.map(s => '<option value="' + esc(s.ticker) + '">' + esc(s.ticker + " · " + s.name) + '</option>').join("");
      const requested = new URLSearchParams(location.search).get("symbol");
      if (state.universe.some(s => s.ticker === requested)) $("marketSymbol").value = requested;
      initialized = true; renderChart();
    }
    renderAccount(); renderJobs();
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const next = await api("/api/stocks/overview");
      if (next.error) throw Error(next.error);
      state = next;
      $("accessPanel").hidden = true; $("content").hidden = false;
      render();
      $("connection").textContent = "Workspace updated " + when(state.updated_ts);
      $("connection").className = "";
      notice();
    } catch (error) {
      $("connection").textContent = "Connection interrupted · displayed results may be out of date";
      $("connection").className = "stale";
      notice(error.message, true);
    } finally { loading = false; }
  }
  $("accessForm").addEventListener("submit", async event => {
    event.preventDefault(); token = $("accessToken").value.trim(); StockSession.setToken(token); await refresh();
  });
  $("refresh").addEventListener("click", refresh);
  $("marketSymbol").addEventListener("change", renderChart);
  $("chartPeriod").addEventListener("change", renderChart);
  $("reloadChart").addEventListener("click", () => { if (state) renderChart(); });
  $("accountPicker").addEventListener("change", () => { selectedAccount = $("accountPicker").value; renderAccount(); });
  $("stopAccount").addEventListener("click", async () => {
    $("stopAccount").disabled = true;
    try { await api("/api/stocks/practice/forward/stop", {id:selectedAccount}); await refresh(); }
    catch (error) { notice(error.message, true); }
    finally { $("stopAccount").disabled = false; }
  });
  $("exportJournal").addEventListener("click", async () => {
    try {
      const blob = await api("/api/stocks/practice/forward/export", undefined, true);
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = "stock-forward-journal.json";
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { notice(error.message, true); }
  });
  window.addEventListener("offline", () => {
    $("connection").textContent = "Offline · displayed results and market prices may be out of date";
    $("connection").className = "stale";
  });
  window.addEventListener("online", refresh);
  refresh(); setInterval(() => { if (!document.hidden) refresh(); }, 15000);
})();
