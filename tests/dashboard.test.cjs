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
  const rows=[{symbol:'BTCUSDT',action:'Buy'},{symbol:'BTCUSDT',action:'Sell'},{symbol:'ETHUSDT',action:'Sell'}];
  assert.deepEqual(filterTrades(rows,'BTCUSDT','Sell'),[rows[1]]);
  assert.equal(filterTrades(rows,'all','all').length,3);
});
test('CSV quotes text and neutralizes spreadsheet formulas',()=>{
  assert.equal(csvCell('=HYPERLINK("bad")'),'"\'=HYPERLINK(""bad"")"');
  assert.equal(csvCell('a,b'),'"a,b"');
  const csv=tradesCSV([{ts:0,symbol:'BTCUSDT',action:'Buy',reason:'signal',price:'1',pnl:'0'}]);
  assert.ok(csv.includes('1970-01-01T00:00:00.000Z'));assert.ok(csv.endsWith(',""'));
});


const {setupAccountNote} = require('../dashboard/dashboard.js');
test('mainnet checks cannot verify testnet or a mismatched pair', () => {
  const result={verified:true,checked_at:1000,symbol:'ETHUSDT',dedicated_spot_key:true};
  assert.match(setupAccountNote({environment:'testnet',symbol:'ETHUSDT'},result,1001),/mainnet only/);
  assert.match(setupAccountNote({environment:'mainnet',symbol:'BTCUSDT'},result,1001),/different pair/);
});
test('stale and read-only keys cannot claim trading readiness', () => {
  const config={environment:'mainnet',symbol:'BTCUSDT'};
  const result={verified:true,checked_at:1000,symbol:'BTCUSDT',dedicated_spot_key:false};
  assert.match(setupAccountNote(config,result,1001),/read-only key/);
  assert.match(setupAccountNote(config,result,1400),/older than five minutes/);
  assert.match(setupAccountNote(config,{...result,dedicated_spot_key:true},1001),/validation are still required/);
});
