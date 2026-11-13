#!/usr/bin/env python3
"""Human readable zh-TW proof output. NOT a LIVE production/watch action."""
import json,sys
from pathlib import Path
path=Path(sys.argv[1] if len(sys.argv)>1 else 'market_probe.json')
d=json.loads(path.read_text(encoding='utf-8'))
assets=d['asset_coverage']
all_four=d['test_a_valid_spot_all_four']=='PASS'
all_candles=d['test_c_complete_candles_all_four']=='PASS'
print('① 市場發生什麼事？')
if not all_four:
    print('本輪未取得四個資產皆具原始交易時間的有效現貨報價；不能判定目前市場方向或宣稱沒有觸發。')
else:
    for a in ('BTC','ETH','SOL','BNB'):
        r=assets[a]; print(f"{a}：{r['provider']} 現貨 {r['price']}，成交時間 {r['quote_as_of']}。")
print('\n② 有沒有值得注意的機會？')
if not all_candles:
    print('1H／4H 收盤證據不完整；無法證實新支撐、突破或有效進場。既有來源研究區僅保留為待核查背景。')
else:
    print('已取得四資產現貨與已收盤 K 線，僅構成結構分析的資料基礎；需另行研究支撐、阻力和失效條件，不能僅憑本測試宣布交易機會。')
print('\n③ 我現在需要做什麼？')
if not all_four or not all_candles:
    print('ACTION_NOW=WAIT（資料不足）。NEXT_ACTION=修復或切換行情取得環境；本輪不建立新 WATCH 或交易候選。')
else:
    print('ACTION_NOW=REVIEW（僅市場研究）。NEXT_ACTION=由 Crypto LIVE 依正式 MASTER 驗證訊號、風控與 Broker；不代表下單。')
print('\n診斷：WATCH_GATE='+d['watch_conclusion']+'；EXECUTION_GATE=NOT_EVALUATED；MASTER_SYNC=NOT_CHECKED_BY_THIS_PROBE；TRADE_AUTHORIZATION=NONE；CROSS_RUN_DEDUP=NOT_TESTED。')