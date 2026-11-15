"""Tenant-safe preparation logic. No wallet keys or exchange order methods."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN

RATE=Decimal('0.10')
class Locked(Exception):pass
class Invalid(Exception):pass

def decimal(value):
    if not isinstance(value,str) or len(value)>80:raise Invalid('Use a decimal string')
    try:n=Decimal(value)
    except InvalidOperation:raise Invalid('Invalid decimal') from None
    if not n.is_finite():raise Invalid('Invalid decimal')
    return n

@dataclass(frozen=True)
class Release:
    approval_reference:str=''
    onboarding_enabled:bool=False
    funding_enabled:bool=False
    trading_enabled:bool=False
    custody_provider:str=''
    execution_release:str=''
    def permits(self,action):
        approved=bool(self.approval_reference.strip())
        onboarding=approved and self.onboarding_enabled is True
        funding=onboarding and self.funding_enabled is True and bool(self.custody_provider.strip())
        trading=funding and self.trading_enabled is True and bool(self.execution_release.strip())
        return {'onboarding':onboarding,'funding':funding,'trading':trading}.get(action,False)
    def public(self):
        return {'approval_recorded':bool(self.approval_reference.strip()),
                'onboarding_enabled':self.permits('onboarding'),
                # Actual provider and order adapters are deliberately not installed.
                'funding_enabled':False,'trading_enabled':False,
                'commission_rate':'0.10','custody_configured':bool(self.custody_provider.strip()),
                'stage':'PREPARATION','message':'Trader funding and real orders are not available in this preparation build.'}

@dataclass
class CommissionBook:
    """10% at a cumulative realized-profit high-water mark, before commission.
    Input results must already include exchange fees. Accrual is not collection.
    Exact accruals accumulate; only a collection total is rounded down to cents.
    """
    net:Decimal=Decimal(0)
    high_water:Decimal=Decimal(0)
    accrued:Decimal=Decimal(0)
    collected:Decimal=Decimal(0)
    events:dict=field(default_factory=dict)
    def settle(self,event_id,net_pnl):
        pnl=decimal(net_pnl)
        if abs(pnl)>=Decimal('1e20') or pnl!=pnl.quantize(Decimal('.00000001')):raise Invalid('Settlement exceeds supported precision')
        if not isinstance(event_id,str) or not 1<=len(event_id)<=128:raise Invalid('Invalid settlement identifier')
        if event_id in self.events:
            if self.events[event_id]!=pnl:raise Invalid('Settlement identifier reused with different result')
            return Decimal(0)
        next_net=self.net+pnl
        if abs(next_net)>=Decimal('1e20'):raise Invalid('Cumulative settlement exceeds supported range')
        additional=max(Decimal(0),next_net-self.high_water)
        fee=additional*RATE
        self.net=next_net;self.high_water=max(self.high_water,next_net,Decimal(0))
        self.accrued+=fee;self.events[event_id]=pnl
        return fee
    def due(self):
        return max(Decimal(0),self.accrued-self.collected).quantize(Decimal('.01'),rounding=ROUND_DOWN)
    def collect(self,*_):raise Locked('Commission collection requires approval and an implemented payment provider')

class UnconfiguredCustody:
    def deposit_address(self,*_):raise Locked('No custody provider is connected; no deposit address has been issued')
    def withdraw(self,*_):raise Locked('Withdrawals are unavailable in preparation')

class UnconfiguredExecution:
    def submit(self,*_):raise Locked('Real order submission is unavailable in preparation')

def order_review(profile,body):
    if not isinstance(body,dict) or set(body)!={'side','symbol','amount_usdt'}:raise Invalid('Provide side, symbol and amount_usdt only')
    if body['side'] not in ('Buy','Sell') or body['symbol'] not in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):raise Invalid('Unsupported spot order')
    amount=decimal(body['amount_usdt'])
    if amount<=0:raise Invalid('Amount must be positive')
    ceiling=decimal(profile.get('order_limit_usdt','0'))
    if ceiling<=0 or amount>ceiling:raise Invalid('Amount exceeds the saved trader order limit')
    return {'side':body['side'],'symbol':body['symbol'],'amount_usdt':str(amount),
            'account_status':profile['status'],'can_submit':False,'orders_submitted':0,
            'note':'Review only. This is not an executable quote. A custody account, verified funds, current exchange rules and explicit activation are required.'}
