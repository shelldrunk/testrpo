#!/usr/bin/env python3
"""Create a compact, public, traceable research-only snapshot for Crypto Watch.

The original full provider attempts remain in the short-lived GitHub Actions artifact.
"""
import argparse
import json
from pathlib import Path


def compact(data):
    assets={}
    for symbol,row in (data.get('asset_coverage') or {}).items():
        if row is None:
            assets[symbol]=None
            continue
        r=dict(row)
        r['one_h_bars']=(row.get('one_h_bars') or [])[-12:]
        r['four_h_bars']=(row.get('four_h_bars') or [])[-8:]
        assets[symbol]=r
    attempts=[]
    for row in data.get('provider_attempts') or []:
        attempts.append({'provider':row.get('provider'),'asset':row.get('asset'),'pair':row.get('pair'),
                         'status':row.get('status'),'quote_as_of':row.get('quote_as_of'),
                         'quote_fresh':row.get('quote_fresh'),'one_h_closed':row.get('one_h_closed'),
                         'four_h_closed':row.get('four_h_closed'),
                         'endpoints':{k:{y:x.get(y) for y in ('url','fetch_status','http_status','error')} 
                                      for k,x in (row.get('endpoints') or {}).items()}})
    keys=('schema','generated_at','github_run_id','github_commit','quotes_max_age_seconds',
          'test_a_valid_spot_all_four','test_c_complete_candles_all_four','watch_conclusion',
          'execution_gate','trade_authorization','paper_fills')
    output={k:data.get(k) for k in keys}
    output['asset_coverage']=assets
    output['provider_attempt_summary']=attempts
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');args=p.parse_args()
    data=json.loads(Path(args.source).read_text(encoding='utf-8'))
    output=compact(data)
    Path(args.target).parent.mkdir(parents=True,exist_ok=True)
    Path(args.target).write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')


if __name__=='__main__':main()