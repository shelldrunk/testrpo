#!/usr/bin/env python3
"""Fail CI on incomplete actual market acceptance, despite successful execution."""
import json,sys
from pathlib import Path
p=Path(sys.argv[1] if len(sys.argv)>1 else 'market_probe.json')
try:d=json.loads(p.read_text())
except (FileNotFoundError,ValueError) as e: print('BLOCKED',e);sys.exit(2)
a=d.get('test_a_valid_spot_all_four')=='PASS'
c=d.get('test_c_complete_candles_all_four')=='PASS'
print('TEST-A', 'PASS' if a else 'BLOCKED','TEST-C','PASS' if c else 'BLOCKED')
print('REAL_MARKET_FEED_ACCEPTANCE','PASS' if a and c else 'BLOCKED')
sys.exit(0 if a and c else 2)