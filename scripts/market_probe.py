#!/usr/bin/env python3
"""Read-only, manual GitHub Actions market feed acceptance probe.

Never writes to exchanges, broker, Watch, or Production. No API keys.
The result is evidence; it does not declare a trading opportunity or authorization.
"""
import argparse
import datetime as dt
import json
import math
import os
import pathlib
import ssl
import urllib.error
import urllib.parse
import urllib.request

ASSETS = ("BTC", "ETH", "SOL", "BNB")
PROVIDERS = ("Coinbase Exchange", "Binance.US", "Kraken", "Binance", "CoinGecko")
QUOTE_MAX_AGE_S = 180
ONE_H_MAX_AGE_S = 7200
FOUR_H_MAX_AGE_S = 28800
UA = "crypto-watch-read-only-acceptance/0.1"


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def numeric(value):
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else None
    except (ValueError, TypeError):
        return None


def parse_utc(text):
    try:
        d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return d.timestamp() if d.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def fetch(url, timeout=8):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = response.status
            data = response.read(750000)
            return json.loads(data.decode("utf-8")), status, None
    except urllib.error.HTTPError as e:
        return None, e.code, f"HTTP_{e.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
        return None, None, type(e).__name__ + ":" + str(e)[:160]


def ohlc_bar(start_s, duration_s, op, hi, lo, cl, volume, now_s):
    vals = [numeric(q) for q in (op, hi, lo, cl)]
    if any(v is None for v in vals) or not (vals[2] <= vals[0] <= vals[1] and vals[2] <= vals[3] <= vals[1]):
        return None
    if start_s % duration_s or start_s + duration_s > now_s:
        return None
    return {"open_time": iso(start_s), "close_time": iso(start_s+duration_s), "close_timestamp": start_s+duration_s,
            "open": vals[0], "high": vals[1], "low": vals[2], "close": vals[3], "volume": numeric(volume) or 0.0}


def coinbase_parser(payload, label, now_s):
    if label == "quote":
        if not isinstance(payload, dict): return None
        return {"price": numeric(payload.get("price")), "traded_at_s": parse_utc(payload.get("time")), "timestamp_basis": "EXCHANGE_TICKER_TRADE_TIME"}
    if not isinstance(payload, list): return []
    out=[]
    for r in payload:
        if not isinstance(r,list) or len(r)<6: continue
        try: b=ohlc_bar(int(r[0]), 3600, r[3],r[2],r[1],r[4],r[5],now_s)
        except (TypeError,ValueError): continue
        if b: out.append(b)
    return sorted({x['open_time']:x for x in out}.values(),key=lambda x:x['close_timestamp'])


def aggregate_four_h(one_h, now_s):
    buckets = {}
    for b in one_h:
        t=b['close_timestamp']-3600
        base=t - t%14400
        buckets.setdefault(base,[]).append(b)
    out=[]
    for base, group in buckets.items():
        group.sort(key=lambda x:x['close_timestamp'])
        expected=[base+3600*(i+1) for i in range(4)]
        if len(group)!=4 or [x['close_timestamp'] for x in group]!=expected or base+14400>now_s: continue
        out.append(ohlc_bar(base,14400,group[0]['open'],max(x['high'] for x in group),min(x['low'] for x in group),group[-1]['close'],sum(x['volume'] for x in group),now_s))
    return sorted([x for x in out if x],key=lambda x:x['close_timestamp'])


def binance_klines_parser(payload, interval_s, now_s):
    out=[]
    if not isinstance(payload,list):return out
    for r in payload:
        if not isinstance(r,list) or len(r)<6:continue
        try: b=ohlc_bar(int(r[0])//1000,interval_s,r[1],r[2],r[3],r[4],r[5],now_s)
        except (TypeError,ValueError):continue
        if b:out.append(b)
    return sorted({x['open_time']:x for x in out}.values(),key=lambda x:x['close_timestamp'])


def kraken_ohlc_parser(payload,interval_s,now_s):
    if not isinstance(payload,dict) or payload.get('error') or not isinstance(payload.get('result'),dict):return []
    keys=[x for k,x in payload['result'].items() if k!='last' and isinstance(x,list)]
    if not keys:return []
    rows=keys[0]
    # Kraken's final row is current/incomplete regardless of apparent time boundaries.
    out=[]
    for r in rows[:-1]:
        if not isinstance(r,list) or len(r)<7:continue
        try:b=ohlc_bar(int(r[0]),interval_s,r[1],r[2],r[3],r[4],r[6],now_s)
        except (TypeError,ValueError):continue
        if b:out.append(b)
    return sorted({x['open_time']:x for x in out}.values(),key=lambda x:x['close_timestamp'])


def urls(provider,asset):
    if provider=='CoinGecko':
        coin={'BTC':'bitcoin','ETH':'ethereum','SOL':'solana','BNB':'binancecoin'}[asset]
        sym=asset+'-USD (aggregate reference only)'
        return sym,{'quote':f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin}'}
    if provider=='Coinbase Exchange':
        sym=f'{asset}-USD';base=f'https://api.exchange.coinbase.com/products/{sym}'
        return sym,{"quote":f'{base}/ticker',"one_h":f'{base}/candles?granularity=3600'}
    if provider in ('Binance.US','Binance'):
        base='https://api.binance.us/api/v3' if provider=='Binance.US' else 'https://api.binance.com/api/v3'
        sym=asset + ('USD' if provider=='Binance.US' else 'USDT')
        q=urllib.parse.quote(sym)
        return sym,{"quote":f'{base}/trades?symbol={q}&limit=1',"one_h":f'{base}/klines?symbol={q}&interval=1h&limit=20',"four_h":f'{base}/klines?symbol={q}&interval=4h&limit=6'}
    sym='XBTUSD' if asset=='BTC' else asset+'USD'
    base='https://api.kraken.com/0/public'
    return sym,{"quote":f'{base}/Trades?pair={sym}&count=1',"one_h":f'{base}/OHLC?pair={sym}&interval=60',"four_h":f'{base}/OHLC?pair={sym}&interval=240'}


def parse_quote(provider,payload):
    if provider=='CoinGecko':
        if not isinstance(payload,list) or not payload or not isinstance(payload[0],dict):return None
        return {'price':numeric(payload[0].get('current_price')),'traded_at_s':None,'provider_updated_at_s':parse_utc(payload[0].get('last_updated')),'timestamp_basis':'AGGREGATOR_UPDATE_NOT_TRADE_TIME'}
    if provider=='Coinbase Exchange':return coinbase_parser(payload,'quote',0)
    if provider in ('Binance.US','Binance'):
        if not isinstance(payload,list) or not payload:return None
        r=payload[-1]
        return {"price":numeric(r.get('price')),"traded_at_s":(int(r['time'])/1000 if r.get('time') is not None else None),"timestamp_basis":"ORIGINAL_SPOT_TRADE_TIME"} if isinstance(r,dict) else None
    if not isinstance(payload,dict) or payload.get('error') or not isinstance(payload.get('result'),dict):return None
    rows=next((v for k,v in payload['result'].items() if k!='last' and isinstance(v,list)),[])
    if not rows:return None
    r=rows[-1]
    try:return {"price":numeric(r[0]),"traded_at_s":float(r[2]),"timestamp_basis":"ORIGINAL_SPOT_TRADE_TIME"}
    except (TypeError,ValueError,IndexError):return None


def probe_one(provider,asset,now_s,request_fn=fetch):
    symbol,targets=urls(provider,asset)
    row={"provider":provider,"asset":asset,"pair":symbol,"instrument":"AGGREGATED_SPOT_REFERENCE" if provider=="CoinGecko" else "SPOT","endpoints":{},
         "fetched_at":None,"quote_as_of":None,"price":None,"quote_fresh":False,
         "one_h_closed":False,"four_h_closed":False,"one_h_latest":None,"four_h_latest":None,
         "one_h_bars":[],"four_h_bars":[],
         "status":"FAILED"}
    responses={}
    for key,url in targets.items():
        data,status,error=request_fn(url)
        row['endpoints'][key]={"url":url,"attempted":True,"http_status":status,"error":error,"fetch_status":"VERIFIED" if status==200 and data is not None else "FAILED"}
        responses[key]=data
    # In a live run, compare venue trade times with when this provider's fetch has FINISHED.
    # Fixed now_s remains supported for deterministic regression fixtures.
    now_s = utcnow().timestamp() if now_s is None else now_s
    row['fetched_at'] = iso(now_s)
    q=parse_quote(provider,responses['quote']) if responses['quote'] is not None else None
    if provider=='CoinGecko' and q and q.get('price'):
        row['reference_price']=q['price']
        row['provider_updated_at']=iso(q['provider_updated_at_s']) if q.get('provider_updated_at_s') else None
        row['timestamp_basis']='AGGREGATOR_UPDATE_NOT_TRADE_TIME'
    if q and q.get('price') and q.get('traded_at_s') is not None:
        t=q['traded_at_s'];row['quote_as_of']=iso(t);row['price']=q['price'];row['timestamp_basis']=q['timestamp_basis']
        row['quote_age_seconds']=round(now_s-t,2)
        row['quote_fresh']=0 <= now_s-t <= QUOTE_MAX_AGE_S
    if provider=='CoinGecko':
        c1=[];c4=[]
    elif provider=='Coinbase Exchange':
        c1=coinbase_parser(responses['one_h'],'one_h',now_s)
        c4=aggregate_four_h(c1,now_s)
    elif provider in ('Binance.US','Binance'):
        c1=binance_klines_parser(responses['one_h'],3600,now_s)
        c4=binance_klines_parser(responses['four_h'],14400,now_s)
    else:
        c1=kraken_ohlc_parser(responses['one_h'],3600,now_s)
        c4=kraken_ohlc_parser(responses['four_h'],14400,now_s)
    if c1:
        row['one_h_bars'] = [{k:v for k,v in bar.items() if k!='close_timestamp'} for bar in c1[-24:]]
        row['one_h_latest']={k:v for k,v in c1[-1].items() if k!='close_timestamp'}
        row['one_h_closed']=0<=now_s-c1[-1]['close_timestamp'] <= ONE_H_MAX_AGE_S
        row['one_h_recent_range']={"high":max(x['high'] for x in c1[-5:]),"low":min(x['low'] for x in c1[-5:])} if len(c1)>=5 else None
    if c4:
        row['four_h_bars'] = [{k:v for k,v in bar.items() if k!='close_timestamp'} for bar in c4[-12:]]
        row['four_h_latest']={k:v for k,v in c4[-1].items() if k!='close_timestamp'}
        row['four_h_closed']=0<=now_s-c4[-1]['close_timestamp'] <= FOUR_H_MAX_AGE_S
    row['status']='VERIFIED' if row['quote_fresh'] and row['one_h_closed'] and row['four_h_closed'] else 'PARTIAL' if row.get('price') or row.get('reference_price') or c1 or c4 else 'FAILED'
    return row


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='market_probe.json')
    p.add_argument('--providers',default=','.join(PROVIDERS))
    p.add_argument('--fast-fallback', action='store_true', help='Skip further providers for assets already verified by a spot exchange')
    args=p.parse_args()
    t=utcnow().timestamp()
    providers=[x.strip() for x in args.providers.split(',') if x.strip()]
    rows=[]
    verified_assets=set()
    for provider in providers:
        if provider not in PROVIDERS: raise SystemExit('Unknown provider: '+provider)
        for asset in ASSETS:
            if args.fast_fallback and asset in verified_assets: continue
            row=probe_one(provider,asset,None)
            rows.append(row)
            if row['status']=='VERIFIED': verified_assets.add(asset)
        if args.fast_fallback and verified_assets==set(ASSETS):break
    best={}
    for a in ASSETS:
        candidates=[r for r in rows if r['asset']==a]
        good=[r for r in candidates if r['status']=='VERIFIED']
        best[a]=(good[0] if good else next((r for r in candidates if r.get('quote_fresh')),None))
    all_fresh=all(best[a] and best[a]['quote_fresh'] for a in ASSETS)
    all_full=all(best[a] and best[a]['status']=='VERIFIED' for a in ASSETS)
    t=utcnow().timestamp()
    report={"schema":"CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1", "generated_at":iso(t),"quotes_max_age_seconds":QUOTE_MAX_AGE_S,
      "github_run_id":os.environ.get("GITHUB_RUN_ID"),"github_commit":os.environ.get("GITHUB_SHA"),
      "asset_coverage":{a: {"provider":best[a]['provider'],"pair":best[a]['pair'],"instrument":best[a]['instrument'],
                  "timestamp_basis":best[a].get('timestamp_basis'),
                  "price":best[a]['price'],"quote_as_of":best[a]['quote_as_of'],
                  "one_h_closed":best[a]['one_h_closed'],"four_h_closed":best[a]['four_h_closed'],
                  "one_h_latest":best[a].get('one_h_latest'),"four_h_latest":best[a].get('four_h_latest'),
                  "one_h_bars":best[a].get('one_h_bars',[]),"four_h_bars":best[a].get('four_h_bars',[]),
                  "one_h_recent_range":best[a].get('one_h_recent_range')} if best[a] else None for a in ASSETS},
      "test_a_valid_spot_all_four":"PASS" if all_fresh else "BLOCKED",
      "test_c_complete_candles_all_four":"PASS" if all_full else "BLOCKED",
      "watch_conclusion":"RESEARCH_EVIDENCE_AVAILABLE" if all_full else "PARTIAL_MARKET_COVERAGE" if any(best.values()) else "DATA_PIPELINE_DEFECT",
      "execution_gate":"NOT_EVALUATED_NO_PRIVATE_BROKER_EVIDENCE","trade_authorization":"NONE","paper_fills":"NONE","provider_attempts":rows}
    pathlib.Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='provider_attempts'},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())