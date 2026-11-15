const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('mainnet fills populate activity and stale reports clear holdings and trades',()=>{
 const source=fs.readFileSync('dashboard/dashboard.js','utf8');const nodes={},tables={};const el=id=>nodes[id]??={textContent:'',disabled:false};
 const context=vm.createContext({el,text:(id,v)=>el(id).textContent=v,amount:(id,v)=>el(id).textContent=v??'—',badge:()=>{},empty:(id)=>tables[id]=[],makeTable:(id,cols,rows)=>tables[id]=rows,filterTrades:(r)=>r,tradeTime:()=>'',pairName:x=>x,money:String,Number,String});
 vm.runInContext('let currentTrades=[];'+source.slice(source.indexOf('  const tradeColumns='),source.indexOf('  async function requestJSON')),context);
 vm.runInContext(`renderExecution({control_connected:true,environment:'mainnet',state:'RUNNING',limits:{symbol:'BTCUSDT',capital_usdt:'56'},execution:{owned_qty:'.0002',cost_usdt:'15',realized_pnl_usdt:'0',active_protections:1},chart:{fills:[{ts:1,side:'Buy',price:'65000',qty:'.0002',pnl:'0'}]}})`,context);
 assert.equal(tables['trade-history'][0].action,'Buy');assert.equal(el('live-quantity').textContent,'.0002 BTC');assert.equal(tables.positions[0].active_protections,1);
 vm.runInContext('renderExecution(null)',context);assert.equal(tables.positions.length,0);assert.equal(tables['trade-history'].length,0);assert.equal(el('live-cost').textContent,'—');assert.equal(el('export').disabled,true);
});
test('client refers only to IDs present in the real-only page',()=>{
 const source=fs.readFileSync('dashboard/dashboard.js','utf8'),html=fs.readFileSync('dashboard/index.html','utf8');
 for(const match of source.matchAll(/(?:el|text|amount|badge|empty|makeTable)\('([^']+)'/g))assert.ok(html.includes(`id="${match[1]}"`),`Missing element ${match[1]}`);
 assert.ok(!/demo/i.test(html));assert.ok(!source.includes("requestJSON('/api/status'"));
});
