/* Dated stock research. This page never starts a trading or learning runner. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const savedKey = 'cryptoStockFavorites.v1';
  const state = {data: null, saved: new Set(), view: 'all', detail: null, loadId: 0, persistent: true};
  const market = {key: '', selected: null, boardView: 'summary', timers: new Map()};
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const dateLabel = value => {
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'});
  };
  const externalLink = (url, label) => {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return escape(label);
      return `<a href="${escape(parsed.href)}" target="_blank" rel="noopener noreferrer">${escape(label)} ↗</a>`;
    } catch (_) { return escape(label); }
  };
  const sources = items => `<ul class="source-list">${items.map(s => `<li>${externalLink(s.url, s.title)}</li>`).join('')}</ul>`;
  const stockLink = ticker => `<a href="#${escape(ticker)}" data-open-stock="${escape(ticker)}">${escape(ticker)}</a>`;
  const getStock = ticker => state.data?.stocks.find(s => s.ticker === ticker);
  const statusLabel = catalyst => ({scheduled: 'Scheduled decision', target: 'Company target', monitor: 'Monitoring', review_needed: 'Date passed · review outcome', date_today: 'Scheduled today · outcome unverified', window_open: 'Target window · outcome unverified'}[catalyst.calendar_status] || 'Outcome unverified');
  const saveButton = stock => `<button class="save-stock" data-save-stock="${escape(stock.ticker)}" aria-pressed="${state.saved.has(stock.ticker)}" aria-label="${state.saved.has(stock.ticker) ? 'Unsave' : 'Save'} ${escape(stock.ticker)}">${state.saved.has(stock.ticker) ? 'Saved ✓' : '+ Save'}</button>`;
  const profileTags = stock => `<span class="stock-tags"><span class="stock-tag">${escape(stock.sector)}</span><span class="stock-tag ${escape(stock.exposure)}">${escape(state.data.exposures[stock.exposure])}</span></span>`;

  // These are the cross-origin frames created by TradingView's official embed
  // loaders. Keep provider code out of the app origin and its access-token storage.
  function mountMarketFrame(hostId, widget, settings, title) {
    const host = $(hostId);
    const status = $(`${hostId}Status`);
    clearTimeout(market.timers.get(hostId));
    const url = new URL(`https://www.tradingview-widget.com/embed-widget/${widget}/`);
    url.searchParams.set('locale', 'en');
    url.hash = encodeURIComponent(JSON.stringify({
      width: '100%', height: '100%', colorTheme: 'dark', isTransparent: false, backgroundColor: '#101a24',
      ...settings, 'page-uri': location.origin + location.pathname,
      utm_source: location.hostname, utm_medium: 'widget', utm_campaign: widget
    }));
    const frame = document.createElement('iframe');
    frame.loading = 'lazy';
    frame.src = url.href;
    frame.title = title;
    frame.referrerPolicy = 'strict-origin-when-cross-origin';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation');
    frame.setAttribute('allow', 'fullscreen');
    frame.setAttribute('allowtransparency', 'true');
    frame.setAttribute('scrolling', 'no');
    status.textContent = 'Loading TradingView display…';
    status.hidden = false;
    // Frame load is not proof of a fresh quote. The provider owns the quote-time,
    // closed-market, delayed-feed, and unavailable-symbol indicators inside it.
    frame.addEventListener('load', () => {
      if (host.firstElementChild !== frame) return;
      clearTimeout(market.timers.get(hostId));
      status.textContent = 'Check quote time and availability inside the display.';
    });
    frame.addEventListener('error', () => {
      if (host.firstElementChild !== frame) return;
      clearTimeout(market.timers.get(hostId));
      status.textContent = 'Market display could not load. Retry or open the TradingView link.';
    });
    host.replaceChildren(frame);
    market.timers.set(hostId, setTimeout(() => {
      if (host.firstElementChild === frame) status.textContent = 'This market display is taking longer to load. Retry or open the TradingView link.';
    }, 20000));
  }
  function marketStocks() {
    return state.data.stocks.filter(s => /^(NASDAQ|NYSE):[A-Z0-9.]+$/.test(s.market_symbol || ''));
  }
  function renderMarketChart(ticker) {
    const stock = marketStocks().find(s => s.ticker === ticker);
    if (!stock) return;
    market.selected = ticker;
    $('marketSymbol').value = ticker;
    $('marketResearchLink').dataset.openStock = ticker;
    $('marketResearchLink').href = `#${ticker}`;
    $('marketExternalLink').href = `https://www.tradingview.com/symbols/${stock.market_symbol.replace(':', '-')}/`;
    $('marketExternalLink').textContent = `${ticker} chart by TradingView ↗`;
    mountMarketFrame('marketChart', 'symbol-overview', {
      symbols: [[stock.ticker, `${stock.market_symbol}|1D`]],
      chartOnly: false, showVolume: true, hideDateRanges: false,
      hideMarketStatus: false, hideSymbolLogo: false, chartType: 'area',
      changeMode: 'price-and-percent', dateRanges: ['1d|1', '1m|30', '3m|60', '12m|1D', '60m|1W', 'all|1M'],
      scalePosition: 'right', scaleMode: 'Normal', fontFamily: 'Arial, sans-serif',
      lineColor: '#50cfb8', topColor: 'rgba(80,207,184,0.25)', bottomColor: 'rgba(80,207,184,0)',
      noTimeScale: false, valuesTracking: '1'
    }, `${stock.name}: price, dollar and percentage change, volume and chart`);
  }
  function renderMarketBoard() {
    const stocks = marketStocks();
    const chartUrl = `${location.origin}/stocks?tvwidgetsymbol={symbolname}#marketChartArea`;
    const full = market.boardView === 'full';
    $('marketTableHint').hidden = !full;
    document.querySelectorAll('[data-market-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.marketView === market.boardView)));
    mountMarketFrame('marketBoard', full ? 'market-quotes' : 'market-overview', full ? {
      symbolsGroups: [{name: 'Research watchlist', symbols: stocks.map(s => ({name: s.market_symbol, displayName: `${s.ticker} · ${s.name}`}))}],
      showSymbolLogo: true, largeChartUrl: chartUrl
    } : {
      tabs: [{title: 'Research watchlist', symbols: stocks.map(s => ({s: s.market_symbol, d: s.name}))}],
      showChart: false, showSymbolLogo: true, showFloatingTooltip: true,
      hideAbsoluteChange: true, onlyDescription: false, dateRange: '1D', largeChartUrl: chartUrl
    }, full ? '20-stock detailed market board: prices, dollar changes and percentage changes' : '20-stock market board: prices and percentage changes');
  }
  function renderMarkets(force = false) {
    const stocks = marketStocks();
    const key = stocks.map(s => s.market_symbol).join(',');
    if (!stocks.length || (!force && market.key === key)) return;
    market.key = key;
    $('marketSymbol').innerHTML = stocks.map(s => `<option value="${escape(s.ticker)}">${escape(s.ticker)} · ${escape(s.name)}</option>`).join('');
    const requested = new URLSearchParams(location.search).get('tvwidgetsymbol');
    const selected = stocks.find(s => s.ticker === market.selected) || stocks.find(s => s.market_symbol === requested) || stocks[0];
    renderMarketBoard();
    renderMarketChart(selected.ticker);
    connectionStatus();
  }
  function viewMarket(ticker) {
    if (!marketStocks().some(s => s.ticker === ticker)) return;
    if ($('stockDetail').open) $('stockDetail').close();
    renderMarketChart(ticker);
    const url = new URL(location.href);
    url.searchParams.set('tvwidgetsymbol', getStock(ticker).market_symbol);
    url.hash = 'marketChartArea';
    history.replaceState(null, '', url.pathname + url.search + url.hash);
    $('marketChartArea').scrollIntoView({behavior: 'auto', block: 'start'});
    $('marketSymbol').focus({preventScroll: true});
  }
  function connectionStatus() {
    $('marketConnectionStatus').textContent = navigator.onLine
      ? 'Updates supplied by TradingView · Stock data may be delayed.'
      : 'You are offline. Displayed quotes may be out of date; reconnect and reload the displays.';
  }

  let token = '';
  try { token = StockSession.getToken(); } catch (_) { /* Token can still be used for this visit. */ }
  function notice(message = '') {
    $('stockNotice').textContent = message;
    $('stockNotice').hidden = !message;
  }
  async function request(path, type="json") {
    try { return await StockSession.request(path, {headers: token ? {Authorization: `Bearer ${token}`} : {}}, type, type==="blob"?60000:20000); }
    catch(error) {
      if(error.status===401) $('stockAccessPanel').hidden=false;
      throw error;
    }
  }
  function readSaved() {
    try {
      const values = JSON.parse(localStorage.getItem(savedKey) || '[]');
      state.saved = new Set(Array.isArray(values) ? values.filter(t => typeof t === 'string' && getStock(t)) : []);
    } catch (_) { state.persistent = false; }
  }
  function renderSavedScope() {
    $('savedCount').textContent = state.saved.size;
    $('savedScope').textContent = `${state.persistent ? 'Saved stocks are kept in this browser.' : 'Saved stocks are kept for this visit; browser storage is unavailable.'} Research priority is an editorial ranking, not a profit probability.`;
  }
  function renderStocks() {
    const query = $('stockSearch').value.trim().toLowerCase();
    const sector = $('stockSector').value;
    const exposure = $('stockExposure').value;
    const sort = $('stockSort').value;
    const stocks = state.data.stocks.filter(s => {
      return (state.view !== 'focus' || s.focus) && (state.view !== 'saved' || state.saved.has(s.ticker)) &&
        (sector === 'all' || s.tags.includes(sector)) && (exposure === 'all' || s.exposure === exposure) &&
        (!query || `${s.ticker} ${s.name} ${s.summary} ${s.tags.join(' ')}`.toLowerCase().includes(query));
    }).sort((a, b) => sort === 'ticker' ? a.ticker.localeCompare(b.ticker) : sort === 'sector' ? a.sector.localeCompare(b.sector) || a.priority - b.priority : a.priority - b.priority);
    $('stockCount').textContent = `${stocks.length} of ${state.data.stocks.length} companies`;
    $('stockEmpty').hidden = stocks.length > 0;
    document.querySelectorAll('[data-stock-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.stockView === state.view)));
    renderSavedScope();
    $('stockGrid').innerHTML = stocks.map(s => `<article class="stock-card${s.focus ? ' is-focus' : ''}" data-ticker="${escape(s.ticker)}">
      <div class="stock-card-head"><span class="priority-label">Research priority ${String(s.priority).padStart(2, '0')}</span>${saveButton(s)}</div>
      <button class="stock-open" data-open-stock="${escape(s.ticker)}" aria-label="Read ${escape(s.ticker)} company research">
        <span class="ticker-line"><strong>${escape(s.ticker)}</strong>${s.focus ? '<span class="stock-focus-tag">Growth priority</span>' : ''}</span>
        <span class="stock-company">${escape(s.name)}</span>${profileTags(s)}<span class="stock-summary">${escape(s.summary)}</span>
        <span class="card-catalyst">Next checkpoint · ${escape(s.catalyst.window)}<b>${escape(s.catalyst.title)}</b></span>
        <span class="stock-read">Read investment case <span aria-hidden="true">↗</span></span>
      </button></article>`).join('');
  }
  function renderDetail(stock) {
    const valuation = state.data.valuation_checks.find(v => v.ticker === stock.ticker);
    $('stockDetailBody').innerHTML = `<div class="detail-heading"><p class="eyebrow">RESEARCH PRIORITY ${stock.priority} · ${escape(stock.horizon)}</p><h2 id="detailTitle">${escape(stock.ticker)}</h2><p>${escape(stock.name)}</p>${profileTags(stock)}</div>
      <div class="detail-actions">${saveButton(stock)}<button class="small" data-chart-stock="${escape(stock.ticker)}">View price &amp; chart</button>${externalLink(stock.quote_url, 'Open quote source')}</div>
      <p class="detail-dates">Research: ${dateLabel(state.data.research_as_of)} · Valuation snapshot: ${dateLabel(state.data.market_data_as_of)} · Updating quotes are in Markets &amp; charts</p>
      <p>${escape(stock.summary)}</p><p><a href="/stock-practice?symbol=${encodeURIComponent(stock.ticker)}">Train this stock ↗</a> · <a href="/backtests?symbol=${encodeURIComponent(stock.ticker)}">Test a strategy ↗</a></p>
      <div class="detail-catalyst"><span class="badge catalyst-status ${escape(stock.catalyst.calendar_status)}">${escape(statusLabel(stock.catalyst))}</span><h3>${escape(stock.catalyst.title)}</h3><p>${escape(stock.catalyst.window)}. ${escape(stock.catalyst.interpretation)}</p></div>
      ${stock.blocks.map(block => `<section class="detail-block"><h3>${escape(block.title)}</h3>${block.paragraphs.map(p => `<p>${escape(p)}</p>`).join('')}</section>`).join('')}
      ${valuation ? `<section class="detail-valuation"><h3>Dated valuation check</h3><strong>${escape(valuation.result)}</strong><p>${escape(valuation.numerator)} compared with ${escape(valuation.denominator)}.</p><p>${escape(valuation.note)} Market snapshot: ${dateLabel(valuation.price_as_of)}.</p>${sources([{title: 'Market snapshot source', url: valuation.market_source}, {title: 'Results / guidance source', url: valuation.guidance_source}])}</section>` : ''}
      <section class="detail-block"><h3>Research sources</h3>${sources(stock.sources)}</section>`;
  }
  function openDetail(ticker, updateHash = true) {
    const stock = getStock(ticker);
    if (!stock) return;
    state.detail = ticker;
    renderDetail(stock);
    const dialog = $('stockDetail');
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
    if (updateHash && location.hash !== `#${ticker}`) history.pushState(null, '', `#${encodeURIComponent(ticker)}`);
  }
  function syncHash() {
    const ticker = location.hash.slice(1).toUpperCase();
    if (getStock(ticker)) openDetail(ticker, false);
    else if ($('stockDetail').open) $('stockDetail').close();
  }
  function clearFilters() {
    $('stockSearch').value = '';
    $('stockSector').value = 'all';
    $('stockExposure').value = 'all';
    $('stockSort').value = 'priority';
    state.view = 'all';
    renderStocks();
  }
  function toggleSaved(ticker, fromDialog) {
    if (!getStock(ticker)) return;
    if (state.saved.has(ticker)) state.saved.delete(ticker); else state.saved.add(ticker);
    try { localStorage.setItem(savedKey, JSON.stringify([...state.saved])); } catch (_) { state.persistent = false; }
    renderStocks();
    if (state.detail) renderDetail(getStock(state.detail));
    const container = fromDialog ? $('stockDetail') : $('stockGrid');
    const nextFocus = [...container.querySelectorAll('[data-save-stock]')].find(b => b.dataset.saveStock === ticker);
    (nextFocus || $('stockSearch')).focus();
  }
  function renderResearch() {
    const data = state.data;
    const freshness = $('researchFreshness');
    const reviewNote = data.review.status === 'review_due' ? ' · Review due — check sources for newer developments' : data.review.status === 'future_date' ? ' · Research date is ahead of the server date — check the edition' : ' · Dated research';
    freshness.textContent = `Research as of ${dateLabel(data.research_as_of)}${reviewNote}`;
    freshness.classList.toggle('review-due', data.review.status !== 'dated');
    $('stockSector').innerHTML = '<option value="all">All themes</option>' + data.sectors.map(sector => `<option value="${escape(sector)}">${escape(sector)}</option>`).join('');
    $('focusNote').textContent = data.focus_note;
    $('focusStocks').innerHTML = data.focus_tickers.map(ticker => {
      const s = getStock(ticker);
      return `<a class="focus-stock" href="#${escape(ticker)}" data-open-stock="${escape(ticker)}"><span><strong>${escape(ticker)}</strong><small>${s.exposure === 'speculative' ? 'Speculative breakthrough' : escape(s.sector)}</small></span><span aria-hidden="true">↗</span></a>`;
    }).join('');
    $('catalystList').innerHTML = data.stocks.filter(s => s.catalyst.end_date).sort((a, b) => a.catalyst.end_date.localeCompare(b.catalyst.end_date)).map(s => `<article class="catalyst-row"><span class="catalyst-date">${escape(s.catalyst.window)}</span><div><h3>${stockLink(s.ticker)} · ${escape(s.catalyst.title)}</h3><p>${escape(s.catalyst.interpretation)}</p></div><span class="badge catalyst-status ${escape(s.catalyst.calendar_status)}">${escape(statusLabel(s.catalyst))}</span></article>`).join('');
    $('themeGrid').innerHTML = data.themes.map(theme => `<article class="theme-card panel"><h3>${escape(theme.title)}</h3><p class="muted">${escape(theme.body)}</p><div class="theme-tickers">${theme.tickers.map(stockLink).join('')}</div>${sources(theme.sources)}</article>`).join('');
    $('biotechExplainer').textContent = data.biotech_explainer;
    $('quantumExplainer').textContent = data.quantum_explainer;
    $('horizonGrid').innerHTML = data.decision_framework.map(item => `<article class="horizon-card"><h3>${escape(item.horizon)}</h3><p>${escape(item.text)}</p></article>`).join('');
    $('valuationDate').textContent = `SNAPSHOT · ${dateLabel(data.market_data_as_of)}`;
    $('valuationNote').textContent = data.valuation_note;
    $('valuationRows').innerHTML = data.valuation_checks.map(v => `<tr><td>${stockLink(v.ticker)}</td><td>${escape(v.result)}</td><td>${escape(v.numerator)}<br>${externalLink(v.market_source, 'Market source')}</td><td>${escape(v.denominator)}<br>${externalLink(v.guidance_source, 'Results / guidance')}</td><td>${escape(v.note)}</td></tr>`).join('');
    $('researchMethodology').textContent = data.methodology;
    $('earlierNote').textContent = data.earlier_candidates_note;
    $('earlierStocks').innerHTML = data.earlier_candidates.map(stock => `<div><strong>${externalLink(stock.quote_url, stock.ticker)}</strong><span>${escape(stock.name)}</span><small>Needs updated research</small></div>`).join('');
    $('stockContent').hidden = false;
    renderMarkets();
    $('downloadReport').disabled = false;
    $('downloadWatchlist').disabled = false;
    renderStocks();
    syncHash();
  }
  async function loadResearch() {
    const loadId = ++state.loadId;
    $('reloadResearch').disabled = true;
    notice();
    try {
      const data = await request('/api/stocks/research');
      if (loadId !== state.loadId) return;
      if (!Array.isArray(data.stocks) || !data.stocks.length || !data.review || !Array.isArray(data.focus_tickers)) throw new Error('The research edition is incomplete. Please try again.');
      const sector = $('stockSector').value;
      const firstLoad = !state.data;
      state.data = data;
      if (firstLoad) readSaved();
      $('stockAccessPanel').hidden = true;
      renderResearch();
      if (data.sectors.includes(sector)) { $('stockSector').value = sector; renderStocks(); }
    } catch (error) {
      if (loadId !== state.loadId) return;
      notice(`${error.message}${state.data ? ` Showing the previously loaded ${dateLabel(state.data.research_as_of)} edition.` : ''}`);
      if (!state.data) $('researchFreshness').textContent = 'Research has not loaded yet.';
    } finally {
      if (loadId === state.loadId) $('reloadResearch').disabled = false;
    }
  }
  async function download(path, filename, button) {
    button.disabled = true;
    notice();
    try {
      const data = await request(path, 'blob');
      const url = URL.createObjectURL(data);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = filename;
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { notice(error.message); }
    finally { button.disabled = false; }
  }

  $('stockAccessForm').addEventListener('submit', event => {
    event.preventDefault();
    token = $('stockAccessToken').value.trim();
    try { StockSession.setToken(token); } catch (_) { /* Session-only in memory fallback. */ }
    $('stockAccessToken').value = '';
    loadResearch();
  });
  $('stockSearch').addEventListener('input', () => state.data && renderStocks());
  ['stockSector', 'stockExposure', 'stockSort'].forEach(id => $(id).addEventListener('change', () => state.data && renderStocks()));
  ['clearStockFilters', 'emptyClearFilters'].forEach(id => $(id).addEventListener('click', clearFilters));
  $('reloadResearch').addEventListener('click', loadResearch);
  $('reloadMarkets').addEventListener('click', () => state.data && renderMarkets(true));
  $('marketSymbol').addEventListener('change', () => viewMarket($('marketSymbol').value));
  window.addEventListener('offline', connectionStatus);
  window.addEventListener('online', connectionStatus);
  $('downloadReport').addEventListener('click', () => download('/api/stocks/research/report', `stock-research-${state.data.research_as_of}.md`, $('downloadReport')));
  $('downloadWatchlist').addEventListener('click', () => download('/api/stocks/research/export', 'stock-research-watchlist.json', $('downloadWatchlist')));
  $('closeStockDetail').addEventListener('click', () => $('stockDetail').close());
  $('stockDetail').addEventListener('close', () => {
    state.detail = null;
    if (getStock(location.hash.slice(1).toUpperCase())) history.replaceState(null, '', location.pathname + location.search);
  });
  window.addEventListener('hashchange', syncHash);
  document.addEventListener('click', event => {
    const open = event.target.closest('[data-open-stock]');
    const chart = event.target.closest('[data-chart-stock]');
    const save = event.target.closest('[data-save-stock]');
    const view = event.target.closest('[data-stock-view]');
    const marketView = event.target.closest('[data-market-view]');
    if (chart) { event.preventDefault(); viewMarket(chart.dataset.chartStock); }
    else if (open) { event.preventDefault(); openDetail(open.dataset.openStock); }
    else if (save) toggleSaved(save.dataset.saveStock, Boolean(save.closest('dialog')));
    else if (marketView && ['summary', 'full'].includes(marketView.dataset.marketView)) { market.boardView = marketView.dataset.marketView; renderMarketBoard(); }
    else if (view) { state.view = view.dataset.stockView; renderStocks(); }
  });
  loadResearch();
})();
