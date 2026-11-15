'use strict';
const el=id=>document.getElementById(id);
let me=null;
function message(value){el('message').textContent=value;}
async function api(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Request unavailable');return data;
 }finally{clearTimeout(timer);}
}
function table(id,columns,rows){
 const target=el(id);target.replaceChildren();
 if(!rows?.length){const p=document.createElement('p');p.textContent='No records available for this account.';target.append(p);return;}
 const wrap=document.createElement('div');wrap.className='table-wrap';const t=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr'),body=document.createElement('tbody');
 for(const [label] of columns){const th=document.createElement('th');th.scope='col';th.textContent=label;tr.append(th);}head.append(tr);
 for(const row of rows){const r=document.createElement('tr');for(const [,key]of columns){const td=document.createElement('td');td.textContent=row[key]===null||row[key]===undefined?'—':String(row[key]);r.append(td);}body.append(r);}t.append(head,body);wrap.append(t);target.append(wrap);
}
function tab(){
 const wanted=location.hash.slice(1)||'account',allowed=['account','trade','funding','commission',...(me?.is_owner?['admin']:[])];const name=allowed.includes(wanted)?wanted:'account';
 for(const node of document.querySelectorAll('.tab'))node.hidden=node.id!==name;
 for(const node of document.querySelectorAll('[data-tab]')){if(node.dataset.tab===name)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');}
 if(name==='admin')loadAdmin().catch(e=>message(e.message));
}
async function refresh(){
 me=await api('/api/me');el('login-panel').hidden=true;el('workspace').hidden=false;el('logout').hidden=false;el('admin-link').hidden=!me.is_owner;
 el('account-title').textContent=me.profile?.display_name||'Account preparation';el('profile-status').textContent=me.profile?.status||'Not onboarded';
 el('account-status').textContent=me.profile?'This profile is separate from the owner’s personal Bybit bot. Funding and order submission remain locked.':'Your sign-in is verified, but no real-money trader account has been onboarded.';
 el('order-limit').textContent=me.profile?me.profile.order_limit_usdt+' USDT':'—';
 for(const id of ['orders','wallet-entries','commission-records','admin-profiles','admin-audit'])el(id).replaceChildren();
 const data=await api('/api/account');el('ledger-state').textContent=data.wallet_entries.length?'Entries recorded':'No funded ledger';
 table('orders',[['Side','side'],['Pair','symbol'],['Quantity','quantity'],['Average fill','average_price'],['Net realized P&L','net_realized_pnl'],['Status','status']],data.orders);
 table('wallet-entries',[['Asset','asset'],['Amount','amount'],['Type','kind'],['Recorded','created_at']],data.wallet_entries);
 table('commission-records',[['Settlement','settlement_id'],['Net realized result','net_realized_pnl'],['10% commission accrued','commission_amount'],['Recorded','created_at']],data.commissions);tab();
}
async function loadAdmin(){
 const data=await api('/api/admin');
 table('admin-profiles',[['Trader','display_name'],['User ID','user_id'],['Vetting status','status'],['Order limit · USDT','order_limit_usdt']],data.profiles);
 table('admin-audit',[['Actor','actor'],['Action','action'],['Trader','target'],['Time','created_at']],data.audit);
 el('profile-choice').replaceChildren(...data.profiles.map(p=>{const o=document.createElement('option');o.value=p.user_id;o.textContent=p.display_name+' · '+p.user_id;return o;}));
 el('profile-form').querySelector('button').disabled=!data.profiles.length;
}
el('login-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.target,button=form.querySelector('button');button.disabled=true;message('Verifying sign-in…');let payload={email:form.elements.email.value.trim(),password:form.elements.password.value};form.elements.password.value='';try{await api('/api/login',payload);payload=null;await refresh();message('Signed in to private preparation. Funding and real orders remain locked.');}catch(e){message(e.message);}finally{payload=null;button.disabled=false;}});
el('register').addEventListener('click',async()=>{try{await api('/api/register',{});}catch(e){message(e.message);}});
el('order-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.target;try{const review=await api('/api/order-review',Object.fromEntries(new FormData(form)));const p=document.createElement('p');p.textContent=`${review.side} ${review.symbol} · requested value ${review.amount_usdt} USDT. ${review.note}`;el('order-review').replaceChildren(p);message('Request reviewed. No order submitted.');}catch(e){message(e.message);}});
for(const [id,path] of [['deposit-check','/api/deposit-address'],['withdraw-check','/api/withdraw']])el(id).addEventListener('click',async()=>{try{await api(path,{});}catch(e){message(e.message);}});
el('profile-form').addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/admin/profile',Object.fromEntries(new FormData(event.target)));message('Account vetting updated. Funding and real trading remain locked.');await loadAdmin();}catch(e){message(e.message);}});
el('logout').addEventListener('click',async()=>{try{await api('/api/logout',{});}catch(e){message('Sign-out could not be confirmed. '+e.message);return;}me=null;el('workspace').hidden=true;el('login-panel').hidden=false;el('logout').hidden=true;el('admin-link').hidden=true;message('Signed out.');for(const id of ['orders','wallet-entries','commission-records','admin-profiles','admin-audit','profile-choice','order-review'])el(id).replaceChildren();});
window.addEventListener('hashchange',tab);
refresh().catch(()=>message('Sign in to inspect the private preparation area. Customer registration, funding and order submission are closed.'));
