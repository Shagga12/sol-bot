const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
function setup(){
 const nodes={};function node(){return {children:[],attrs:{},textContent:'',value:'21600',setAttribute(k,v){this.attrs[k]=v},append(n){this.children.push(n)},replaceChildren(){this.children=[]},getBoundingClientRect(){return {left:0,width:900}}};}
 const el=id=>nodes[id]??=(node());const source=fs.readFileSync('dashboard/dashboard.js','utf8');
 const helpers=source.slice(source.indexOf('  let chartMarket=null'),source.indexOf("  el('chart-window').addEventListener"));
 const context=vm.createContext({document:{createElementNS:()=>node()},el,text:(id,t)=>{el(id).textContent=t},money:v=>Number(v).toFixed(2),Date,Number,Math});vm.runInContext(helpers,context);return {context,el};
}
test('real journal renders markers, target levels and cumulative P&L without demo data',()=>{
 const {context,el}=setup();vm.runInContext(`chartMarket={fetched_at:Date.now()/1000,points:[{ts:Date.now()/1000-600,price:'65000'},{ts:Date.now()/1000,price:'65010'}]};chartStatus={control_connected:true,environment:'mainnet',state:'RUNNING',execution:{realized_pnl_usdt:'.8'},chart:{fills:[{ts:Date.now()/1000-300,price:'65005',side:'Buy',qty:'.0002',pnl:'.8'}],levels:[{label:'Stop loss',price:'64500'}],total_fills:1}};renderLiveCharts()`,context);
 assert.match(el('chart-realized').textContent,/0.80/);assert.ok(el('price-chart').children.some(n=>n.textContent==='▲'));assert.ok(el('pnl-chart').children.some(n=>n.attrs.d));assert.ok(el('price-chart').children.some(n=>String(n.textContent).includes('Stop loss')));
});
test('testnet journal and stale prices cannot appear as real money charts',()=>{
 const {context,el}=setup();vm.runInContext(`chartMarket={fetched_at:0,points:[{ts:1,price:'999'}]};chartStatus={control_connected:true,environment:'testnet',execution:{realized_pnl_usdt:'999'},chart:{fills:[],levels:[],total_fills:0}};renderLiveCharts()`,context);
 assert.equal(el('chart-last-price').textContent,'—');assert.match(el('chart-execution-note').textContent,/excluded/);assert.match(el('pnl-chart').children[0].textContent,/No verified/);
});
