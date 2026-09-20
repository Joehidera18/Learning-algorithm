/* Dated stock research. This page never starts a trading or learning runner. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const savedKey = 'cryptoStockFavorites.v1';
  const state = {data: null, saved: new Set(), view: 'all', detail: null, loadId: 0, persistent: true};
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

  let token = '';
  try { token = sessionStorage.getItem('cryptoAccessToken') || ''; } catch (_) { /* Token can still be used for this visit. */ }
  function notice(message = '') {
    $('stockNotice').textContent = message;
    $('stockNotice').hidden = !message;
  }
  async function request(path) {
    const response = await fetch(path, {credentials: 'same-origin', headers: token ? {Authorization: `Bearer ${token}`} : {}});
    if (response.status === 401) {
      $('stockAccessPanel').hidden = false;
      throw new Error('Enter a valid app access token to load this research.');
    }
    if (!response.ok) throw new Error(`Research request failed (${response.status}). Please try again.`);
    return response;
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
      <div class="detail-actions">${saveButton(stock)}${externalLink(stock.quote_url, 'Open latest quote')}</div>
      <p class="detail-dates">Research: ${dateLabel(state.data.research_as_of)} · Market snapshot: ${dateLabel(state.data.market_data_as_of)} · No live quote</p>
      <p>${escape(stock.summary)}</p>
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
      const response = await request('/api/stocks/research');
      const data = await response.json();
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
      const response = await request(path);
      const url = URL.createObjectURL(await response.blob());
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
    try { sessionStorage.setItem('cryptoAccessToken', token); } catch (_) { /* Session-only in memory fallback. */ }
    $('stockAccessToken').value = '';
    loadResearch();
  });
  $('stockSearch').addEventListener('input', () => state.data && renderStocks());
  ['stockSector', 'stockExposure', 'stockSort'].forEach(id => $(id).addEventListener('change', () => state.data && renderStocks()));
  ['clearStockFilters', 'emptyClearFilters'].forEach(id => $(id).addEventListener('click', clearFilters));
  $('reloadResearch').addEventListener('click', loadResearch);
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
    const save = event.target.closest('[data-save-stock]');
    const view = event.target.closest('[data-stock-view]');
    if (open) { event.preventDefault(); openDetail(open.dataset.openStock); }
    else if (save) toggleSaved(save.dataset.saveStock, Boolean(save.closest('dialog')));
    else if (view) { state.view = view.dataset.stockView; renderStocks(); }
  });
  loadResearch();
})();
