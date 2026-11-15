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
    take_profit: 'Profit target reached', stop_loss: 'Stop-loss condition', no_available_balance: 'No available funds'};
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
  const columns = ['time_utc', 'symbol', 'action', 'reason', 'price', 'cumulative_realized_pnl_usdt'];
  const rows = trades.map(t => [numeric(t.ts) === null ? '' : new Date(Number(t.ts)*1000).toISOString(),
    t.symbol, t.action, t.reason, t.price, t.action === 'Sell' ? t.pnl : '']);
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
  let currentTrades = [], isLoading = false, connectionBusy = false;
  let liveConfig = null, accountCheck = null, draftRevision = 0;
  const draftKey = 'capital-connect-owner-setup-v1';
  const viewNames = {overview: ['Your trading desk.', 'A clear view of your bot, your activity and your next step.', 'Overview'],
    activity: ['Every trade, in view.', 'Review reconciled real-money orders and cumulative realized results.', 'Activity'],
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
  const tradeColumns=[{label:'Pair',render:t=>pairName(t.symbol)},{label:'Activity',render:t=>t.action},{label:'Average fill · USDT',render:t=>money(t.price)},{label:'BTC quantity',render:t=>t.qty},{label:'Cumulative realized P&L · USDT',render:t=>money(t.pnl,true)},{label:'Reconciled · local',render:tradeTime}];
  function filtered(){return filterTrades(currentTrades,el('pair-filter').value,el('action-filter').value);}
  function renderTrades(){
    makeTable('trade-history',tradeColumns,filtered(),'No real-money trades to show','Filled orders appear after reconciliation. Check execution status if the worker is not reporting.');
    makeTable('recent-trades',tradeColumns,currentTrades.slice(0,5),'No real-money trades to show','No simulated balances or trades are displayed.');
    el('export').disabled=filtered().length===0;
  }
  function renderExecution(status){
    const real=!!(status?.control_connected&&status.environment==='mainnet');
    const execution=real?status.execution:null,limits=real?status.limits:null;
    currentTrades=real&&status.chart?status.chart.fills.map(f=>({...f,symbol:limits?.symbol||'BTCUSDT',action:f.side})).reverse():[];
    amount('live-allocation',limits?.capital_usdt);amount('live-realized',execution?.realized_pnl_usdt,true);amount('live-cost',execution?.cost_usdt);
    text('live-quantity',execution?execution.owned_qty+' BTC':'—');
    text('worker-status',real?'Real-money worker: '+status.state:'Execution status unavailable');
    text('last-report',real?'Current execution report received':'Waiting for an authenticated mainnet report');
    el('worker-dot').className='status-dot '+(real?'':'stale');
    badge('ready-worker',real?'Reporting':'Unverified',real?'green':'amber');
    text('ready-worker-note',real?'The mainnet execution worker is reporting.':'No fresh mainnet execution report.');
    text('footer-mode','Real-money execution');
    if(!execution)empty('positions','Position data unavailable','The mainnet worker must report before holdings can be shown.');
    else if(Number(execution.owned_qty)===0)empty('positions','No bot-held BTC','No open BTC holding is recorded in the execution journal.');
    else makeTable('positions',[{label:'Pair',render:()=>limits?.symbol||'BTCUSDT'},{label:'BTC quantity',render:r=>r.owned_qty},{label:'Cost · USDT',render:r=>money(r.cost_usdt)},{label:'Protective orders recorded',render:r=>String(r.active_protections)}],[execution],'','');
    renderTrades();
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
  let chartMarket=null, chartStatus=null;
  const svgNS='http://www.w3.org/2000/svg';
  function svgNode(parent,tag,attrs={},label=null) {
    const node=document.createElementNS(svgNS,tag);
    for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value));
    if(label!==null)node.textContent=label;
    parent.append(node);return node;
  }
  function drawChart(id,points,{height=300,levels=[],fills=[],step=false,empty='Waiting for data'}={}) {
    const root=el(id);root.replaceChildren();
    if(!points.length){svgNode(root,'text',{x:450,y:height/2,fill:'#a6bac4','text-anchor':'middle','font-size':16},empty);return;}
    const all=[...points.map(p=>p.value),...levels.map(p=>Number(p.price)),...fills.filter(f=>f.ts>=points[0].ts&&f.ts<=points.at(-1).ts).map(f=>Number(f.price))];
    let lo=Math.min(...all),hi=Math.max(...all);const pad=Math.max((hi-lo)*.14,Math.abs(hi)*.00005,.01);lo-=pad;hi+=pad;
    const start=points[0].ts,end=Math.max(points.at(-1).ts,start+1);
    const x=t=>20+(t-start)/(end-start)*775,y=v=>20+(hi-v)/(hi-lo)*(height-55);
    for(let i=0;i<4;i++){const value=lo+(hi-lo)*i/3,cy=y(value);svgNode(root,'line',{x1:20,x2:795,y1:cy,y2:cy,stroke:'#263c47'});svgNode(root,'text',{x:810,y:cy+4,fill:'#9fb3bd','font-size':12},money(value));}
    for(const level of levels){const cy=y(Number(level.price));svgNode(root,'line',{x1:20,x2:795,y1:cy,y2:cy,stroke:level.label==='Stop loss'?'#fa9292':'#d9bd75','stroke-dasharray':'6 5'});svgNode(root,'text',{x:24,y:cy-5,fill:'#d9bd75','font-size':12},`${level.label} ${money(level.price)}`);}
    let d=`M ${x(points[0].ts)} ${y(points[0].value)}`;
    for(const p of points.slice(1))d+=step?` H ${x(p.ts)} V ${y(p.value)}`:` L ${x(p.ts)} ${y(p.value)}`;
    svgNode(root,'path',{d,fill:'none',stroke:'#a4e5ce','stroke-width':2.5});
    for(const fill of fills){if(fill.ts<start||fill.ts>end)continue;const cx=x(fill.ts),cy=y(Number(fill.price));const marker=svgNode(root,'text',{x:cx,y:cy+5,fill:fill.side==='Buy'?'#a4e5ce':'#ff9292','font-size':21,'text-anchor':'middle'},fill.side==='Buy'?'▲':'▼');svgNode(marker,'title',{},`${fill.side} ${fill.qty} BTC @ ${fill.price}`);}
    for(const [t,anchor] of [[start,'start'],[end,'end']])svgNode(root,'text',{x:x(t),y:height-9,fill:'#9fb3bd','font-size':12,'text-anchor':anchor},new Date(t*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}));
    root.onpointermove=event=>{const ratio=(event.clientX-root.getBoundingClientRect().left)/root.getBoundingClientRect().width;const ts=start+(ratio*900-20)/775*(end-start);let nearest=points.reduce((a,b)=>Math.abs(a.ts-ts)<Math.abs(b.ts-ts)?a:b);text('chart-hover',`${new Date(nearest.ts*1000).toLocaleString()} · ${id==='price-chart'?'BTC / USDT':'Realized P&L'}: ${money(nearest.value)} USDT`);};
  }
  function renderLiveCharts(){
    const status=chartStatus,real=!!(status?.control_connected&&status.environment==='mainnet'),chart=real?status.chart:null;
    const market=chartMarket;const fresh=market&&Date.now()/1000-market.fetched_at<90;
    const points=fresh?market.points.filter(p=>p.ts>=Date.now()/1000-Number(el('chart-window').value)).map(p=>({ts:p.ts,value:Number(p.price)})):[];
    text('chart-last-price',points.length?money(points.at(-1).value)+' USDT':'—');
    drawChart('price-chart',points,{levels:chart?.levels||[],fills:chart?.fills||[],empty:'Live market prices unavailable'});
    const execution=real?status.execution:null;
    text('chart-realized',`Realized P&L: ${execution?money(execution.realized_pnl_usdt,true)+' USDT':'—'}`);
    const fills=chart?.fills||[];const now=Date.now()/1000;
    const pnl=fills.length?fills.map(f=>({ts:f.ts,value:Number(f.pnl)})):[];
    if(pnl.length)pnl.push({ts:now,value:pnl.at(-1).value});
    else if(chart&&execution&&Number(execution.realized_pnl_usdt)===0)pnl.push({ts:now-3600,value:0},{ts:now,value:0});
    drawChart('pnl-chart',pnl,{height:190,step:true,empty:'No verified real-money P&L history available'});
    text('chart-execution-note',!real?'Real-money journal unavailable or worker report stale. Only verified mainnet orders are shown.':!chart?'Waiting for chart telemetry from the worker.':`Real-money journal: ${chart.total_fills} reconciled order(s). ${chart.total_fills>100?'Showing the latest 100 with lifetime cumulative P&L.':fills.length?'Only reconciled mainnet orders included.':'No filled orders yet; realized P&L is zero.'} Protective levels appear when a bracket is recorded.`);
    text('chart-freshness',fresh?`Bybit spot · updated ${new Date(market.fetched_at*1000).toLocaleTimeString()} · ${real?'mainnet '+status.state:'execution status unverified'}`:'Price feed unavailable or stale; retrying every 30 seconds.');
  }
  async function loadChartMarket(){try{chartMarket=await requestJSON('/api/market/chart');}catch{chartMarket=null;}renderLiveCharts();}
  el('chart-window').addEventListener('change',renderLiveCharts);
  setInterval(()=>{if(!document.hidden)loadChartMarket();},30000);
  loadChartMarket();
  let latestControlStatus=null;
  el('confirm-real-start').addEventListener('change', () => {
    el('activate-live').disabled=!(latestControlStatus?.can_activate && (latestControlStatus.environment !== 'mainnet' || el('confirm-real-start').checked));
  });
  async function loadLiveStatus() {
    try {
      const status = await requestJSON('/api/live/status');
      // Only an authenticated, fresh worker report can unlock Start.
      text('live-state', status.control_connected ? `${status.environment}: ${status.state}` : (status.connection_monitor_connected ? 'Connection check online — orders off' : 'Worker not reporting'));
      if (latestControlStatus?.config_digest !== status.config_digest) el('confirm-real-start').checked=false;
      latestControlStatus=status;
      chartStatus=status; renderLiveCharts(); renderExecution(status);
      badge('ready-activation', !status.control_connected ? 'Not connected' : status.state, status.orders_running ? 'green' : 'amber');
      text('execution-mode-badge', !status.control_connected ? 'STATUS UNKNOWN' : (status.real_trading_active ? 'REAL TRADING ACTIVE' : (status.orders_running ? 'TESTNET ACTIVE' : 'EXECUTION OFF')));
      text('execution-overview-status', `Execution: ${status.environment || 'unreported'} · ${status.state}. Overview and Activity show only the real-money execution journal. Figures are not your exchange wallet balance.`);
      const execution=status.execution;
      text('execution-journal-summary', execution ? `Bot-owned quantity: ${execution.owned_qty} · Cost: ${money(execution.cost_usdt)} USDT · Realized execution P&L: ${money(execution.realized_pnl_usdt, true)} USDT · Pending entries: ${execution.pending_entries} · Active protective orders: ${execution.active_protections}.` : 'No execution journal reported yet. This is not your exchange wallet balance.');
      el('activate-live').disabled = !(status.can_activate && (status.environment !== 'mainnet' || el('confirm-real-start').checked));
      const limits=status.limits;
      text('saved-execution-limits', limits ? `Saved worker: ${limits.symbol} · ${limits.capital_usdt} USDT allocation · ${limits.order_usdt} USDT order ceiling · ${limits.daily_loss_usdt} USDT daily realized-loss ceiling · ${Number(limits.stop_loss_fraction)*100}% estimated stop trigger · ${Number(limits.take_profit_fraction)*100}% estimated profit trigger.` : 'Saved execution limits have not been reported.');
      el('stop-live').disabled = !status.control_connected;
      const blockers = Array.isArray(status.blockers) ? status.blockers : ['Execution readiness could not be established.'];
      el('live-blockers').replaceChildren(...blockers.map(value => { const li=document.createElement('li'); li.textContent=String(value); return li; }));
    } catch (error) {
      latestControlStatus=null;
      chartStatus=null; renderLiveCharts(); renderExecution(null);
      el('activate-live').disabled=true; el('stop-live').disabled=true;
      text('execution-mode-badge','STATUS UNKNOWN');
      text('live-state','Backend check failed');
      const li=document.createElement('li'); li.textContent=error.message; el('live-blockers').replaceChildren(li);
    }
  }
  async function sendControl(action) {
    el('activate-live').disabled=true; el('stop-live').disabled=true;
    try {
      await requestJSON(`/api/live/${action}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(action==='start' ? {config_digest:latestControlStatus?.config_digest, acknowledge_real_money:el('confirm-real-start').checked} : {})});
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
      for (const [key,value] of Object.entries(saved)) if (key!=='environment' && form.elements.namedItem(key) && typeof value==='string') form.elements.namedItem(key).value=value;
      text('live-draft-status','Saved browser draft restored. Validate it again before downloading. It has not been applied to the bot.');
    }
  } catch {}
  async function load(){
    if(isLoading)return;isLoading=true;el('refresh').disabled=true;
    try{await Promise.all([loadLiveStatus(),loadChartMarket()]);feedback('');}
    finally{isLoading=false;el('refresh').disabled=false;}
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
      text('bybit-result','Account connection verified. Credentials were not saved. ' + (result.funding_note || '') + ' This diagnostic does not change the worker state.');
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
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'capital-connect-real-activity.csv';
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  });
  window.addEventListener('hashchange',showView);
  showView(); renderExecution(null); load();
  setInterval(updateLiveAccount,60000);
}

