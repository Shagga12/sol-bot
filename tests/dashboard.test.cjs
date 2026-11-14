const test=require('node:test');
const assert=require('node:assert/strict');
const {numeric,money,reportAge,filterTrades,csvCell,tradesCSV}=require('../dashboard/dashboard.js');
test('unknown balances are never displayed as zero',()=>{
  for(const value of [null,undefined,'',true,'NaN','Infinity']) assert.equal(numeric(value),null);
  assert.equal(money(null),'—');assert.equal(money('0'),'0.00');
});
test('negative and positive P&L preserve sign',()=>{
  assert.equal(money('-1.614',true),'−1.61');assert.equal(money('4',true),'+4.00');
});
test('freshness uses scan time so replaying old data is stale',()=>{
  assert.equal(reportAge({received_at:990,report:{valuation_timestamp:100}},1000),900);
  assert.equal(reportAge({report:null},1000),null);
  assert.equal(reportAge({received_at:2000,report:{}},1000),Infinity);
});
test('pair and closed trade filters intersect',()=>{
  const rows=[{symbol:'BTCUSDT',action:'DEMO_BUY'},{symbol:'BTCUSDT',action:'DEMO_SELL'},{symbol:'ETHUSDT',action:'DEMO_SELL'}];
  assert.deepEqual(filterTrades(rows,'BTCUSDT','DEMO_SELL'),[rows[1]]);
  assert.equal(filterTrades(rows,'all','all').length,3);
});
test('CSV quotes text and neutralizes spreadsheet formulas',()=>{
  assert.equal(csvCell('=HYPERLINK("bad")'),'"\'=HYPERLINK(""bad"")"');
  assert.equal(csvCell('a,b'),'"a,b"');
  const csv=tradesCSV([{ts:0,symbol:'BTCUSDT',action:'DEMO_BUY',reason:'signal',price:'1',pnl:'0'}]);
  assert.ok(csv.includes('1970-01-01T00:00:00.000Z'));assert.ok(csv.endsWith(',""'));
});
