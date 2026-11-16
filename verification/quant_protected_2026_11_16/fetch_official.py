import urllib.request,json,concurrent.futures,time,pathlib,hashlib,datetime
import argparse
a=argparse.ArgumentParser();a.add_argument('--year',type=int,required=True);args=a.parse_args()
START=int(datetime.datetime(args.year,1,1,tzinfo=datetime.timezone.utc).timestamp()); END=int(datetime.datetime(args.year+1,1,1,tzinfo=datetime.timezone.utc).timestamp()); STEP=900
windows=[(s,min(s+899*STEP,END-STEP)) for s in range(START,END,900*STEP)]
def get(pair):
 s,e=pair;u=f'https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=900&limit=1000&start={s}&end={e}'
 for n in range(3):
  try:
   with urllib.request.urlopen(u,timeout=25) as r:d=json.load(r)
   return d['data']['ohlc']
  except Exception:
   if n==2:raise
   time.sleep(1)
rows={};duplicates=0
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for page in pool.map(get,windows):
  for row in page:
   t=int(row['timestamp'])
   if not START<=t<END:continue
   if t in rows:
    duplicates+=1
    assert rows[t]==row,'conflicting duplicate'
   rows[t]=row
expected=set(range(START,END,STEP));missing=sorted(expected-set(rows))
out={'source':'Bitstamp official OHLC v2 BTC/USD','start':START,'end_exclusive':END,'step':STEP,'missing':missing,'duplicates':duplicates,'rows':[rows[t] for t in sorted(rows)]}
p=pathlib.Path(f'/tmp/quant-official-btcusd-{args.year}.json');p.write_text(json.dumps(out,sort_keys=True))
print(json.dumps({'candles':len(rows),'expected':len(expected),'missing_count':len(missing),'missing_first':missing[:10],'duplicates':duplicates,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}),flush=True)
