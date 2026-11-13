#!/usr/bin/env python3
"""Read-only, fail-closed validation of a public GitHub market snapshot.

This is WATCH research evidence only. No trading, Coinbase account or order state.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

ASSETS = ('BTC', 'ETH', 'SOL', 'BNB')
MAX_AGE_S = 180
FUTURE_TOLERANCE_S = 5


def timestamp(value):
    if not isinstance(value, str): return None
    try:
        obj=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return obj.timestamp() if obj.tzinfo else None
    except (ValueError, AttributeError, OverflowError):
        return None


def closed_bars(bars, span_s, now_s):
    if not isinstance(bars, list) or not bars: return False
    prior=-math.inf
    for b in bars:
        if not isinstance(b, dict): return False
        start=timestamp(b.get('open_time'))
        close=timestamp(b.get('close_time'))
        if start is None or close is None or int(start) % span_s != 0 or abs(close - start - span_s)>0.001 or close > now_s+FUTURE_TOLERANCE_S or start <= prior:
            return False
        if any(not isinstance(b.get(k),(int,float)) or not math.isfinite(b[k]) or b[k]<=0 for k in ('open','high','low','close')):
            return False
        if not (b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']):
            return False
        prior=start
    return True


def validate(doc, now_s, min_generated_s=None):
    defects=[]
    if not isinstance(doc,dict) or doc.get('schema')!='CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1':return {'status':'BLOCKED','defects':['SCHEMA_INVALID']}
    gen=timestamp(doc.get('generated_at'))
    if gen is None or not 0<=now_s-gen<=MAX_AGE_S: defects.append('SNAPSHOT_STALE_OR_FUTURE')
    if min_generated_s is not None and (gen is None or gen < min_generated_s): defects.append('SNAPSHOT_PREDATES_REFRESH_REQUEST')
    coverage=doc.get('asset_coverage')
    if not isinstance(coverage,dict): coverage={}
    for a in ASSETS:
        row=coverage.get(a)
        if not isinstance(row,dict): defects.append(a+':MISSING');continue
        price=row.get('price'); quote=timestamp(row.get('quote_as_of'))
        if not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0 or quote is None or not 0<=now_s-quote<=MAX_AGE_S: defects.append(a+':QUOTE_UNVERIFIED')
        if row.get('instrument')!='SPOT' or row.get('timestamp_basis') not in ('EXCHANGE_TICKER_TRADE_TIME','ORIGINAL_SPOT_TRADE_TIME'):
            defects.append(a+':NOT_SPOT_TRADE_TIME')
        if not row.get('one_h_closed') or not closed_bars(row.get('one_h_bars'),3600,now_s): defects.append(a+':1H_UNVERIFIED')
        if not row.get('four_h_closed') or not closed_bars(row.get('four_h_bars'),14400,now_s): defects.append(a+':4H_UNVERIFIED')
        if row.get('provider') in (None,'CoinGecko'): defects.append(a+':SOURCE_NOT_EXCHANGE_SPOT')
    return {'status':'PASS' if not defects else 'BLOCKED','defects':defects,'generated_at':doc.get('generated_at'),'github_run_id':doc.get('github_run_id')}


def main():
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--min-generated',default=None);args=p.parse_args()
    doc=json.loads(Path(args.path).read_text(encoding='utf-8'))
    result=validate(doc,dt.datetime.now(dt.timezone.utc).timestamp(),timestamp(args.min_generated) if args.min_generated else None)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())