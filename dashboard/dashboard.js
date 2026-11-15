'use strict';
const PAIRS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
function numeric(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function money(value, signed = false) {
  const n = numeric(value);
  if (n === null) return '—';
  const absolute = Math.abs(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (n < 0 ? '−' : signed && n > 0 ? '+' : '') + absolute;
}
function pairName(symbol) { return PAIRS.includes(symbol) ? symbol.slice(0, -4) + ' / USDT' : String(symbol || 'Unknown'); }
function reasonName(reason) {
  const names = {no_buy_signal: 'Waiting for a buy signal', trend_not_confirmed: 'Trend not confirmed',
    warming_up_price_history: 'Collecting price history', stop_loss_cooldown: 'Cooling down after an exit',
    daily_loss_limit: 'Daily entry loss limit reached', spread_too_wide: 'Spread is too wide',
    position_already_open: 'Position is open', moving_average_signal: 'Moving average signal',
    take_profit: 'Profit target reached', stop_loss: 'Stop-loss condition', no_available_balance: 'No available demo cash'};
  return names[reason] || String(reason || 'Awaiting worker data').replaceAll('_', ' ');
}
function reportAge(data, now = Date.now() / 1000) {
  if (!data || !data.report) return null;
  const received = numeric(data.received_at);
  const scanned = numeric(data.report.valuation_timestamp);
  if (received === null || received > now + 60 || (scanned !== null && scanned > now + 60)) return Infinity;
  return Math.max(0, now - Math.min(received, scanned ?? received));
}
function filterTrades(trades, pair, action) {
  return trades.filter(t => (pair === 'all' || t.symbol === pair) && (action === 'all' || t.action === action));
}
function csvCell(value) {
  let text = String(value ?? '');
  if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
function tradesCSV(trades) {
  const columns = ['time_utc', 'symbol', 'action', 'reason', 'price', 'pnl_usdt'];
  const rows = trades.map(t => [numeric(t.ts) === null ? '' : new Date(Number(t.ts)*1000).toISOString(),
    t.symbol, t.action, t.reason, t.price, t.action === 'DEMO_SELL' ? t.pnl : '']);
  return [columns, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
}
function setupAccountNote(config, result, now = Date.now() / 1000) {
  if (!config) return 'Validate your settings to compare them with the account check.';
  if (config.environment !== 'mainnet') return 'Testnet selected. The Bybit account tab checks mainnet only; it cannot verify this testnet account.';
  if (!result?.verified || !Number.isFinite(result.checked_at) || now - result.checked_at > 300 || result.checked_at > now + 60) return 'Mainnet account check missing or older than five minutes. Check your Bybit account again.';
  if (result.symbol !== config.symbol) return 'Account check is for a different pair. Recheck the selected pair.';
  if (!result.dedicated_spot_key) return 'A dedicated SpotTrade-only API key has not been verified. A read-only key cannot place orders.';
  return 'Recent mainnet account check reports a dedicated spot-trading key. Execution and exit validation are still required.';
}
if (typeof module !== 'undefined') module.exports = {numeric, money, pairName, reasonName, reportAge, filterTrades, csvCell, tradesCSV};
if (typeof module !== 'undefined') module.exports.setupAccountNote = setupAccountNote;

if (typeof document !== 'undefined') {
  const el = id => document.getElementById(id);
  let reportData = null, currentTrades = [], isLoading = false, connectionBusy = false;
  let liveConfig = null, accountCheck = null, draftRevision = 0;
  const draftKey = 'capital-connect-owner-setup-v1';
  const viewNames = {overview: ['Your trading desk.', 'A clear view of your bot, your activity and your next step.', 'Overview'],
    activity: ['Every trade, in view.', 'Review your demo activity and see how the results add up.', 'Activity'],
    account: ['Your Bybit account.', 'Verify your connection and funds without placing an order.', 'Bybit account'],
    setup: ['Your path to trading.', 'A straightforward view of what is ready and what comes next.', 'Trading setup']};
  function text(id, value) { el(id).textContent = value; }
  function feedback(message) { text('feedback', message); el('feedback').hidden = !message; }
  function showView() {
    let view = location.hash.slice(1);
    if (view === 'main') return;
    if (!Object.hasOwn(viewNames, view)) view = 'overview';
    document.querySelectorAll('.view').forEach(node => node.hidden = node.id !== 'view-' + view);
    document.querySelectorAll('[data-view]').forEach(node => {
      const active = node.dataset.view === view;
      node.classList.toggle('active', active);
      if (active) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current');
    });
    text('page-title', viewNames[view][0]); text('page-subtitle', viewNames[view][1]); text('view-name', viewNames[view][2]);
    document.title = 'Capital Connect · ' + viewNames[view][2];
    window.scrollTo(0, 0);
  }
  function amount(id, value, signed = false) {
    const node = el(id), n = numeric(value);
    node.replaceChildren(document.createTextNode(money(value, signed)));
    if (n !== null) { const unit = document.createElement('span'); unit.className = 'unit'; unit.textContent = 'USDT'; node.append(unit); }
    node.classList.toggle('positive', signed && n !== null && n > 0);
    node.classList.toggle('negative', signed && n !== null && n < 0);
  }
  function badge(id, label, kind = '') { const node = el(id); node.textContent = label; node.className = 'quiet-badge ' + kind; }
  function empty(container, title, description) {
    const node = document.createElement('div'); node.className = 'empty';
    const icon = document.createElement('span'); icon.className = 'empty-icon'; icon.textContent = '◫'; icon.setAttribute('aria-hidden', 'true');
    const heading = document.createElement('strong'); heading.textContent = title;
    const p = document.createElement('span'); p.textContent = description;
    node.append(icon, heading, p); el(container).replaceChildren(node);
  }
  function makeTable(container, columns, rows, emptyTitle, emptyDescription) {
    if (!rows.length) return empty(container, emptyTitle, emptyDescription);
    const wrap = document.createElement('div'); wrap.className = 'table-wrap';
    const table = document.createElement('table'), head = document.createElement('thead'), body = document.createElement('tbody'), hr = document.createElement('tr');
    for (const col of columns) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = col.label; hr.append(th); }
    head.append(hr);
    for (const row of rows) {
      const tr = document.createElement('tr');
      for (const col of columns) {
        const td = document.createElement('td'); td.dataset.label = col.label;
        const value = col.render(row);
        if (value instanceof Node) td.append(value); else td.textContent = value;
        if (col.className) td.className = col.className;
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(head, body); wrap.append(table); el(container).replaceChildren(wrap);
  }
  function tradeTime(row) {
    const node = document.createElement('span'), value = numeric(row.ts);
    if (value === null) { node.textContent = 'Unknown'; return node; }
    const date = new Date(value * 1000); if (isNaN(date)) { node.textContent = 'Unknown'; return node; }
    node.textContent = date.toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
    const time = document.createElement('time'); time.dateTime = date.toISOString(); time.textContent = date.toLocaleTimeString(undefined, {hour: 'numeric', minute: '2-digit'});
    node.append(time); return node;
  }
  const tradeColumns = [{label: 'Pair', render: t => pairName(t.symbol)}, {label: 'Activity', render: t => {
    const span = document.createElement('span'); span.className = 'trade-kind' + (t.action === 'DEMO_SELL' ? ' sell' : '');
    span.textContent = t.action === 'DEMO_BUY' ? 'DEMO BUY' : t.action === 'DEMO_SELL' ? 'DEMO SELL' : String(t.action); return span;
  }}, {label: 'Price · USDT', render: t => money(t.price)}, {label: 'Realized P&L', render: t => {
    const span = document.createElement('span'); span.textContent = t.action === 'DEMO_SELL' ? money(t.pnl, true) : '—';
    const n = numeric(t.pnl); if (t.action === 'DEMO_SELL' && n !== null) span.className = n < 0 ? 'negative' : n > 0 ? 'positive' : ''; return span;
  }}, {label: 'Reason', render: t => reasonName(t.reason), className: 'reason'}, {label: 'Time · local', render: tradeTime}];
  function filtered() { return filterTrades(currentTrades, el('pair-filter').value, el('action-filter').value); }
  function renderTrades() {
    makeTable('trade-history', tradeColumns, filtered(), reportData?.report ? 'No trades match this view' : 'Waiting for trade data',
      reportData?.report ? 'Try a different pair or activity filter.' : 'The dashboard will fill in after the worker reports.');
    el('export').disabled = filtered().length === 0;
  }
  function renderMarkets(report) {
    const latest = Array.isArray(report?.last_decisions) ? report.last_decisions : [];
    const nodes = PAIRS.map(symbol => {
      const coin = symbol.slice(0, -4), decision = latest.find(x => x.symbol === symbol);
      const card = document.createElement('article'); card.className = 'market-card';
      const top = document.createElement('div'); top.className = 'market-top';
      const mark = document.createElement('span'); mark.className = 'coin-mark ' + coin; mark.textContent = {BTC: '₿', ETH: 'Ξ', SOL: '◎', BNB: '◇'}[coin];
      const name = document.createElement('div'), strong = document.createElement('strong'), small = document.createElement('small');
      strong.textContent = coin + ' / USDT'; small.textContent = 'Monitored spot pair'; name.append(strong, small); top.append(mark, name);
      const price = document.createElement('strong'); price.className = 'market-price'; price.textContent = numeric(decision?.price) === null ? '—' : '$' + money(decision.price);
      const state = document.createElement('div'); state.className = 'decision';
      const dot = document.createElement('span'); dot.className = 'status-dot waiting';
      const label = document.createElement('span'); label.textContent = reasonName(decision?.reason); state.append(dot, label);
      card.append(top, price, state); return card;
    });
    el('market-cards').replaceChildren(...nodes);
  }
  function updateFreshness() {
    const age = reportAge(reportData);
    if (age === null) {
      text('worker-status', 'Waiting for worker report'); text('last-report', 'Next scheduled scan will populate the dashboard');
      el('worker-dot').className = 'status-dot waiting'; badge('ready-worker', 'Waiting'); return;
    }
    const stale = age > 1200, minutes = Math.floor(age / 60);
    text('worker-status', stale ? 'Worker report is stale' : 'Demo worker reporting');
    text('last-report', Number.isFinite(age) ? (minutes < 1 ? 'Last scan less than a minute ago' : 'Last scan ' + minutes + ' min ago') : 'Worker timestamp needs checking');
    el('worker-dot').className = 'status-dot ' + (stale ? 'stale' : '');
    badge('ready-worker', stale ? 'Stale' : 'Reporting', stale ? 'amber' : 'green');
    text('ready-worker-note', stale ? 'Displayed results are old. Check the worker before relying on them.' : 'A current demo report has reached this dashboard.');
    text('footer-mode', stale ? 'Demo data · stale report' : 'Demo data only');
  }
  function renderReport(data) {
    if (data.report && (data.report.mode !== 'DEMO' || data.report.live_order_execution !== false ||
        !Array.isArray(data.report.positions) || !Array.isArray(data.report.recent_trades))) throw Error('Worker report format is invalid. Previous data may be stale.');
    reportData = data;
    const report = data.report;
    renderMarkets(report); updateFreshness();
    const fields = {'equity': 'estimated_liquidation_equity_usdt', 'total-pnl': 'total_pnl_after_exit_fee_usdt', 'cash': 'cash_usdt',
      'commission': 'commission_estimate_usdt', 'realized': 'realized_pnl_usdt', 'unrealized': 'unrealized_pnl_after_exit_fee_usdt'};
    for (const [id, field] of Object.entries(fields)) amount(id, report?.[field], ['total-pnl', 'realized', 'unrealized'].includes(id));
    if (!report) {
      currentTrades = []; text('position-count', '—');
      ['setting-interval','setting-strategy','setting-profit','setting-stop'].forEach(id => text(id,'Awaiting worker report'));
      empty('positions', 'Waiting for the worker', 'No balances or positions have been invented. The next scheduled report will populate this view.');
      empty('recent-trades', 'No report received yet', 'The demo worker reports every 15 minutes.'); renderTrades(); return;
    }
    currentTrades = report.recent_trades.filter(t => ['DEMO_BUY', 'DEMO_SELL'].includes(t.action));
    text('position-count', String(report.positions.length));
    makeTable('positions', [{label:'Pair',render:p=>pairName(p.symbol)}, {label:'Entry · USDT',render:p=>money(p.entry)},
      {label:'Quantity',render:p=>numeric(p.qty) === null ? '—' : String(p.qty)}, {label:'Cost · USDT',render:p=>money(p.cost)}],
      report.positions, 'No open demo positions', 'The bot is waiting for a qualifying signal.');
    makeTable('recent-trades', tradeColumns, currentTrades.slice(0, 5), 'No demo trades yet', 'Trades will appear after the worker records a simulated buy or sell.');
    renderTrades();
    const interval = numeric(report.interval_seconds);
    text('setting-interval', interval === null ? 'Not reported' : (interval / 60) + ' minutes');
    text('setting-strategy', report.strategy_version || 'Not reported');
    const percent = value => numeric(value) === null ? 'Not reported' : (Number(value)*100).toLocaleString(undefined, {maximumFractionDigits:3}) + '%';
    text('setting-profit', percent(report.take_profit_net_return_target)); text('setting-stop', percent(report.stop_loss_price_move));
  }
  async function requestJSON(url, options = {}, timeout = 40000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
      if (response.status === 401) throw Error('Your sign-in has expired. Reload and sign in again.');
      let data; try { data = await response.json(); } catch { throw Error('The server returned an unreadable response. Try refreshing.'); }
      if (!response.ok) throw Error(data.error || 'Unable to complete this request. Try again shortly.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw Error('The request timed out. Please try again.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function draftValues() { return Object.fromEntries(new FormData(el('live-setup-form'))); }
  function updateLiveAccount() {
    text('live-account-note', setupAccountNote(liveConfig, accountCheck));
    text('live-funding-note', 'Configuration download does not deploy or activate the bot.');
    if (!liveConfig || liveConfig.environment !== 'mainnet' || accountCheck?.symbol !== liveConfig.symbol || !accountCheck?.verified || Date.now()/1000-accountCheck.checked_at>300) return;
    const free = numeric(accountCheck.available_spot_usdt), minimum = numeric(accountCheck.minimum_order_usdt);
    if (free === null || minimum === null) { text('live-funding-note','Available non-borrowed funds or pair minimum are unverified.'); return; }
    const ceiling = Math.min(Number(liveConfig.order_usdt), Number(liveConfig.capital_usdt), free);
    text('live-funding-note', 'Current mainnet funds: ' + money(free) + ' USDT. Entry ceiling before fees and rounding: ' + money(ceiling) + ' USDT; pair minimum: ' + money(minimum) + ' USDT. ' + (ceiling <= minimum ? 'Sizing may fail after fees and rounding.' : 'A worker-side size check is still required.'));
  }
  function invalidateDraft() {
    draftRevision++; liveConfig = null; el('download-live').disabled = true;
    text('live-draft-status','Settings changed. Validate again before downloading. The running bot has not changed.');
    updateLiveAccount();
  }
  async function loadLiveStatus() {
    try {
      const status = await requestJSON('/api/live/status');
      // Only an authenticated, fresh worker report can unlock Start.
      text('live-state', status.control_connected ? `${status.environment}: ${status.state}` : (status.connection_monitor_connected ? 'Connection check online — orders off' : 'Worker not reporting'));
      el('activate-live').disabled = !status.can_activate;
      el('stop-live').disabled = !status.control_connected;
      const blockers = Array.isArray(status.blockers) ? status.blockers : ['Execution readiness could not be established.'];
      el('live-blockers').replaceChildren(...blockers.map(value => { const li=document.createElement('li'); li.textContent=String(value); return li; }));
    } catch (error) {
      el('activate-live').disabled=true; el('stop-live').disabled=true;
      text('live-state','Backend check failed');
      const li=document.createElement('li'); li.textContent=error.message; el('live-blockers').replaceChildren(li);
    }
  }
  async function sendControl(action) {
    el('activate-live').disabled=true; el('stop-live').disabled=true;
    try {
      await requestJSON(`/api/live/${action}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      text('live-control-result', `${action === 'start' ? 'Start' : 'Stop'} requested. Awaiting worker acknowledgement.`);
    } catch(error) { text('live-control-result', error.message); }
    await loadLiveStatus();
  }
  el('activate-live').addEventListener('click', () => sendControl('start'));
  el('stop-live').addEventListener('click', () => sendControl('stop'));
  setInterval(() => { if (!document.hidden) loadLiveStatus(); }, 10000);
  el('live-setup-form').addEventListener('input', invalidateDraft);
  el('live-setup-form').addEventListener('change', invalidateDraft);
  el('live-setup-form').addEventListener('submit', async event => {
    event.preventDefault();
    const values=draftValues(), revision=draftRevision;
    el('validate-live').disabled=true; liveConfig=null; el('download-live').disabled=true;
    text('live-draft-status','Validating limits…');
    try {
      const result=await requestJSON('/api/live/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
      if (revision !== draftRevision) return;
      if (!result.valid || !result.config || result.settings_applied_to_bot !== false) throw Error('Setup response could not be verified.');
      liveConfig=result.config; el('download-live').disabled=false;
      try { localStorage.setItem(draftKey,JSON.stringify(values)); text('live-draft-status','Draft validated and saved in this browser only. No settings applied to the bot; no orders submitted.'); }
      catch { text('live-draft-status','Draft validated for download. Browser storage is unavailable; no settings applied to the bot.'); }
      updateLiveAccount();
    } catch (error) { if (revision===draftRevision) text('live-draft-status',error.message); }
    finally { el('validate-live').disabled=false; }
  });
  el('clear-live').addEventListener('click',() => {
    el('live-setup-form').reset(); invalidateDraft();
    try { localStorage.removeItem(draftKey); } catch {}
    text('live-draft-status','Draft cleared. No settings applied to the bot.');
  });
  el('download-live').addEventListener('click',() => {
    if (!liveConfig) return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(liveConfig,null,2)+'\n'],{type:'application/json'}));
    const a=document.createElement('a'); a.href=url; a.download='capital-connect-'+liveConfig.environment+'-config.json';
    document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  try {
    const saved=JSON.parse(localStorage.getItem(draftKey));
    if (saved && typeof saved==='object') {
      const form=el('live-setup-form');
      for (const [key,value] of Object.entries(saved)) if (form.elements.namedItem(key) && typeof value==='string') form.elements.namedItem(key).value=value;
      text('live-draft-status','Saved browser draft restored. Validate it again before downloading. It has not been applied to the bot.');
    }
  } catch {}
  async function load() {
    if (isLoading) return;
    isLoading = true; el('refresh').disabled = true;
    try { renderReport(await requestJSON('/api/status', {}, 30000)); feedback(''); }
    catch (error) { feedback(error.message + (reportData?.report ? ' Showing the last received data.' : '')); badge('ready-worker', 'Check failed', 'amber'); text('worker-status', 'Report refresh failed'); el('worker-dot').className = 'status-dot stale'; }
    finally { isLoading = false; el('refresh').disabled = false; }
  }
  function clearAccount() {
    accountCheck=null; updateLiveAccount();
    ['wallet-balance','locked-balance','available-balance','minimum-order'].forEach(id => amount(id, null));
    text('key-access','—'); text('account-status','Not verified'); text('checked-at','Complete a check to see your account information.');
    badge('ready-account','Not checked'); badge('ready-funds','Not checked'); text('ready-funds-note','Check non-borrowed funds and the current pair minimum.');
  }
  el('bybit-form').addEventListener('submit', async event => {
    event.preventDefault(); if (connectionBusy) return;
    connectionBusy = true; el('bybit-check').disabled = true; clearAccount();
    el('bybit-result').className = 'connection-result'; text('bybit-result','Checking account access and spot funds…');
    const form = event.target;
    let body = JSON.stringify({apiKey:form.elements.apiKey.value.trim(),apiSecret:form.elements.apiSecret.value.trim(),symbol:form.elements.symbol.value});
    form.elements.apiKey.value = ''; form.elements.apiSecret.value = '';
    try {
      const result = await requestJSON('/api/bybit/check',{method:'POST',headers:{'Content-Type':'application/json'},body},55000);
      if (!result.verified) throw Error(result.error || 'Connection was not verified.');
      accountCheck=result; updateLiveAccount();
      text('account-status','Connection verified'); text('checked-at','Checked ' + new Date(result.checked_at*1000).toLocaleString());
      amount('wallet-balance',result.wallet_usdt); amount('locked-balance',result.locked_usdt); amount('available-balance',result.available_spot_usdt); amount('minimum-order',result.minimum_order_usdt);
      text('key-access',result.key_access || 'Unknown'); badge('ready-account','Verified','green');
      const available = numeric(result.available_spot_usdt), minimum = numeric(result.minimum_order_usdt);
      const fundsKnown = available !== null && minimum !== null;
      badge('ready-funds', fundsKnown ? (available >= minimum ? 'Funds reported' : 'Below minimum') : 'Unverified', fundsKnown && available >= minimum ? 'green' : 'amber');
      text('ready-funds-note',fundsKnown ? pairName(result.symbol) + ': ' + money(available) + ' USDT available; minimum order value ' + money(minimum) + ' USDT. Fees, sizing and order validation still apply.' : (result.funding_note || 'Available funds or instrument rules could not be verified.'));
      el('bybit-result').className = 'connection-result success';
      text('bybit-result','Account connection verified. Credentials were not saved. ' + (result.funding_note || '') + ' Real orders remain disabled.');
    } catch (error) {
      el('bybit-result').className = 'connection-result error'; text('bybit-result',error.message + ' Credentials were cleared. No orders were submitted.');
      text('account-status','Connection not verified'); badge('ready-account','Check failed','amber');
    } finally { body = ''; connectionBusy = false; el('bybit-check').disabled = false; }
  });
  el('refresh').addEventListener('click',load);
  el('pair-filter').addEventListener('change',renderTrades); el('action-filter').addEventListener('change',renderTrades);
  el('export').addEventListener('click',() => {
    const rows = filtered(); if (!rows.length) return;
    const url = URL.createObjectURL(new Blob(['\ufeff' + tradesCSV(rows)],{type:'text/csv;charset=utf-8'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'capital-connect-demo-activity.csv';
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  window.addEventListener('hashchange',showView);
  showView(); renderReport({report:null}); load(); loadLiveStatus();
  setInterval(() => { updateFreshness(); updateLiveAccount(); if (el('auto-update').checked) load(); },60000);
}

