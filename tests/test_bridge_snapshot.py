import unittest,datetime as dt
from scripts.validate_watch_snapshot import validate

NOW=1794529600

def bar(start,duration):
    def iso(x):return dt.datetime.fromtimestamp(x,dt.timezone.utc).isoformat().replace('+00:00','Z')
    return {'open_time':iso(start),'close_time':iso(start+duration),'open':100.,'high':102.,'low':99.,'close':101.,'volume':2.}

def sample(now=NOW):
    iso=lambda t:dt.datetime.fromtimestamp(t,dt.timezone.utc).isoformat().replace('+00:00','Z')
    h=int(now//3600*3600-3600)
    f=int(now//14400*14400-14400)
    row={'provider':'Coinbase Exchange','pair':'BTC-USD','instrument':'SPOT','timestamp_basis':'EXCHANGE_TICKER_TRADE_TIME','price':100.,'quote_as_of':iso(now-4),'one_h_closed':True,'four_h_closed':True,'one_h_bars':[bar(h,3600)],'four_h_bars':[bar(f,14400)]}
    return {'schema':'CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1','generated_at':iso(now-3),'asset_coverage':{a:dict(row) for a in ('BTC','ETH','SOL','BNB')}}

class BridgeValidationTest(unittest.TestCase):
    def test_valid_fresh_complete_all_assets(self):self.assertEqual(validate(sample(),NOW)['status'],'PASS')
    def test_stale_generated_blocked(self):self.assertEqual(validate(sample(NOW-3600),NOW)['status'],'BLOCKED')
    def test_stale_quote_blocked(self):
        d=sample();d['asset_coverage']['BTC']['quote_as_of']=dt.datetime.fromtimestamp(NOW-400,dt.timezone.utc).isoformat();self.assertEqual(validate(d,NOW)['status'],'BLOCKED')
    def test_aggregated_quote_blocked(self):
        d=sample();d['asset_coverage']['ETH']['timestamp_basis']='AGGREGATOR_UPDATE_NOT_TRADE_TIME';self.assertEqual(validate(d,NOW)['status'],'BLOCKED')
    def test_missing_asset_blocked(self):
        d=sample();del d['asset_coverage']['BNB'];self.assertEqual(validate(d,NOW)['status'],'BLOCKED')
    def test_unclosed_4h_blocked(self):
        d=sample();d['asset_coverage']['SOL']['four_h_bars'][0]['close_time']=dt.datetime.fromtimestamp(NOW+3600,dt.timezone.utc).isoformat();self.assertEqual(validate(d,NOW)['status'],'BLOCKED')
    def test_snap_predates_trigger_blocked(self):self.assertEqual(validate(sample(),NOW,min_generated_s=NOW-2)['status'],'BLOCKED')
    def test_valid_no_private_broker_fields(self):
        d=sample();self.assertNotIn('orders',d);self.assertNotIn('balance',d);self.assertNotIn('fills',d)
    def test_invalid_ohlc_blocked(self):
        d=sample();d['asset_coverage']['SOL']['one_h_bars'][0]['high']=98.;self.assertEqual(validate(d,NOW)['status'],'BLOCKED')
    def test_future_quote_blocked(self):
        d=sample();d['asset_coverage']['BTC']['quote_as_of']=dt.datetime.fromtimestamp(NOW+10,dt.timezone.utc).isoformat();self.assertEqual(validate(d,NOW)['status'],'BLOCKED')

if __name__=='__main__':unittest.main()