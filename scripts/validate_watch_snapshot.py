#!/usr/bin/env python3
"""Read-only, fail-closed validation of a public GitHub market snapshot.

This is WATCH research evidence only. No trading, Coinbase account or order state.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
from pathlib import Path

ASSETS = ('BTC', 'ETH', 'SOL', 'BNB')
MAX_AGE_S = 180
FUTURE_TOLERANCE_S = 5
ALLOWED_PROVIDERS = ('Coinbase Exchange', 'Binance.US', 'Kraken', 'Binance')


def timestamp(value):
    if not isinstance(value, str): return None
    try:
        obj=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return obj.timestamp() if obj.tzinfo else None
    except (ValueError, AttributeError, OverflowError):
        return None


def closed_bars(bars, span_s, now_s):
    if not isinstance(bars, list) or not bars: return False
    prior_close=None
    for b in bars:
        if not isinstance(b, dict): return False
        start=timestamp(b.get('open_time'))
        close=timestamp(b.get('close_time'))
        if (start is None or close is None or start % span_s != 0 or
            abs(close - start - span_s)>0.001 or close > now_s or
            (prior_close is not None and abs(start-prior_close)>0.001)):
            return False
        if any(type(b.get(k)) not in (int,float) or not math.isfinite(b[k]) or b[k]<=0 for k in ('open','high','low','close')):
            return False
        if type(b.get('volume')) not in (int,float) or not math.isfinite(b['volume']) or b['volume']<0:
            return False
        if not (b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']):
            return False
        prior_close=close
    return True


def expected_pair(provider, asset):
    if provider=='Coinbase Exchange': return f'{asset}-USD'
    if provider=='Binance.US': return f'{asset}USD'
    if provider=='Binance': return f'{asset}USDT'
    if provider=='Kraken': return 'XBTUSD' if asset=='BTC' else f'{asset}USD'
    return None


def lineage_verified(doc, asset, row):
    attempts=doc.get('provider_attempt_summary',doc.get('provider_attempts'))
    if not isinstance(attempts, list): return False
    provider=row.get('provider')
    for src in attempts:
        if not isinstance(src,dict): continue
        if any(src.get(k)!=v for k,v in (
            ('asset',asset),('provider',provider),('pair',row.get('pair')),
            ('quote_as_of',row.get('quote_as_of')))):
            continue
        if src.get('status')!='VERIFIED' or src.get('quote_fresh') is not True or src.get('one_h_closed') is not True or src.get('four_h_closed') is not True:
            continue
        endpoints=src.get('endpoints')
        if not isinstance(endpoints,dict): continue
        needed=('quote','one_h') if provider=='Coinbase Exchange' else ('quote','one_h','four_h')
        if all(isinstance(endpoints.get(k),dict) and endpoints[k].get('fetch_status')=='VERIFIED' and endpoints[k].get('http_status')==200 for k in needed):
            return True
    return False


def validate(doc, now_s, min_generated_s=None, expected_commit=None, expected_run_id=None):
    defects=[]
    if not isinstance(doc,dict) or doc.get('schema')!='CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1':return {'status':'BLOCKED','defects':['SCHEMA_INVALID']}
    gen=timestamp(doc.get('generated_at'))
    if gen is None or not 0<=now_s-gen<=MAX_AGE_S: defects.append('SNAPSHOT_STALE_OR_FUTURE')
    if min_generated_s is not None and (gen is None or gen < min_generated_s): defects.append('SNAPSHOT_PREDATES_REFRESH_REQUEST')
    commit=doc.get('github_commit'); run_id=str(doc.get('github_run_id') or '')
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-fA-F]{40}',commit): defects.append('GITHUB_COMMIT_MISSING_OR_INVALID')
    if not run_id.isdecimal() or int(run_id)==0: defects.append('GITHUB_RUN_ID_MISSING_OR_INVALID')
    if expected_commit is not None and commit!=expected_commit: defects.append('GITHUB_COMMIT_MISMATCH')
    if expected_run_id is not None and run_id!=str(expected_run_id): defects.append('GITHUB_RUN_ID_MISMATCH')
    coverage=doc.get('asset_coverage')
    if not isinstance(coverage,dict): coverage={}
    for a in ASSETS:
        row=coverage.get(a)
        if not isinstance(row,dict): defects.append(a+':MISSING');continue
        price=row.get('price'); quote=timestamp(row.get('quote_as_of'))
        if type(price) not in (int,float) or not math.isfinite(price) or price<=0 or quote is None or not 0<=now_s-quote<=MAX_AGE_S: defects.append(a+':QUOTE_UNVERIFIED')
        if row.get('instrument')!='SPOT' or row.get('timestamp_basis') not in ('EXCHANGE_TICKER_TRADE_TIME','ORIGINAL_SPOT_TRADE_TIME'):
            defects.append(a+':NOT_SPOT_TRADE_TIME')
        provider=row.get('provider')
        if provider not in ALLOWED_PROVIDERS or row.get('pair')!=expected_pair(provider,a): defects.append(a+':VENUE_PAIR_UNVERIFIED')
        if (provider=='Coinbase Exchange' and row.get('timestamp_basis')!='EXCHANGE_TICKER_TRADE_TIME') or (provider in ALLOWED_PROVIDERS and provider!='Coinbase Exchange' and row.get('timestamp_basis')!='ORIGINAL_SPOT_TRADE_TIME'):
            defects.append(a+':ORIGINAL_TRADE_TIMESTAMP_BASIS_INVALID')
        for suffix,span,max_age in (('1H',3600,7200),('4H',14400,28800)):
            bars=row.get(('one_h' if span==3600 else 'four_h')+'_bars')
            latest=timestamp(bars[-1].get('close_time')) if isinstance(bars,list) and bars and isinstance(bars[-1],dict) else None
            if (row.get(('one_h' if span==3600 else 'four_h')+'_closed') is not True or
                not closed_bars(bars,span,now_s) or latest is None or not 0<=now_s-latest<=max_age):
                defects.append(a+':'+suffix+'_UNVERIFIED')
        if not lineage_verified(doc,a,row): defects.append(a+':PROVIDER_LINEAGE_UNVERIFIED')
    return {'status':'PASS' if not defects else 'BLOCKED','defects':defects,'generated_at':doc.get('generated_at'),'github_run_id':doc.get('github_run_id')}


def main():
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--min-generated',default=None)
    p.add_argument('--expected-commit',default=None);p.add_argument('--expected-run-id',default=None)
    args=p.parse_args()
    doc=json.loads(Path(args.path).read_text(encoding='utf-8'))
    result=validate(doc,dt.datetime.now(dt.timezone.utc).timestamp(),timestamp(args.min_generated) if args.min_generated else None,
                    args.expected_commit or os.environ.get('GITHUB_SHA'),args.expected_run_id or os.environ.get('GITHUB_RUN_ID'))
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())