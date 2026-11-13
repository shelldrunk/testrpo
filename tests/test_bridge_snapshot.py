import copy, unittest, datetime as dt
from scripts.validate_watch_snapshot import validate

NOW=1794529600
COMMIT='a'*40
RUN_ID='123456789'

def iso(x): return dt.datetime.fromtimestamp(x,dt.timezone.utc).isoformat().replace('+00:00','Z')

def bar(start,duration):
    return {'open_time':iso(start),'close_time':iso(start+duration),'open':100.,'high':102.,'low':99.,'close':101.,'volume':2.}

def sample(now=NOW):
    h=int(now//3600*3600-3*3600)
    f=int(now//14400*14400-2*14400)
    assets={}; attempts=[]
    for a in ('BTC','ETH','SOL','BNB'):
        pair=a+'-USD'
        quote=iso(now-4)
        assets[a]={'provider':'Coinbase Exchange','pair':pair,'instrument':'SPOT','timestamp_basis':'EXCHANGE_TICKER_TRADE_TIME',
                   'price':100.,'quote_as_of':quote,'one_h_closed':True,'four_h_closed':True,
                   'one_h_bars':[bar(h+i*3600,3600) for i in range(3)],
                   'four_h_bars':[bar(f+i*14400,14400) for i in range(2)]}
        attempts.append({'asset':a,'provider':'Coinbase Exchange','pair':pair,'status':'VERIFIED','quote_as_of':quote,
                         'quote_fresh':True,'one_h_closed':True,'four_h_closed':True,
                         'endpoints':{key:{'fetch_status':'VERIFIED','http_status':200} for key in ('quote','one_h')}})
    return {'schema':'CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1','generated_at':iso(now-3),'github_commit':COMMIT,
            'github_run_id':RUN_ID,'asset_coverage':assets,'provider_attempt_summary':attempts}

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

    def test_missing_middle_1h_blocked(self):
        d=sample();d['asset_coverage']['BTC']['one_h_bars'].pop(1);self.assertIn('BTC:1H_UNVERIFIED',validate(d,NOW)['defects'])
    def test_missing_middle_4h_blocked(self):
        d=sample();f=int(NOW//14400*14400);d['asset_coverage']['ETH']['four_h_bars']=[bar(f-4*14400,14400),bar(f-2*14400,14400),bar(f-14400,14400)];self.assertIn('ETH:4H_UNVERIFIED',validate(d,NOW)['defects'])
    def test_duplicate_1h_blocked(self):
        d=sample();d['asset_coverage']['BTC']['one_h_bars'].insert(1,copy.deepcopy(d['asset_coverage']['BTC']['one_h_bars'][0]));self.assertIn('BTC:1H_UNVERIFIED',validate(d,NOW)['defects'])
    def test_off_boundary_4h_blocked(self):
        d=sample();b=d['asset_coverage']['ETH']['four_h_bars'][0];b['open_time']=iso(int(NOW//14400*14400-28800)+60);b['close_time']=iso(int(NOW//14400*14400-14400)+60);self.assertIn('ETH:4H_UNVERIFIED',validate(d,NOW)['defects'])
    def test_unknown_venue_blocked(self):
        d=sample();d['asset_coverage']['SOL']['provider']='Unlisted Exchange';self.assertIn('SOL:VENUE_PAIR_UNVERIFIED',validate(d,NOW)['defects'])
    def test_wrong_pair_blocked(self):
        d=sample();d['asset_coverage']['ETH']['pair']='BTC-USD';self.assertIn('ETH:VENUE_PAIR_UNVERIFIED',validate(d,NOW)['defects'])
    def test_missing_lineage_blocked(self):
        d=sample();del d['provider_attempt_summary'];self.assertIn('BNB:PROVIDER_LINEAGE_UNVERIFIED',validate(d,NOW)['defects'])
    def test_bad_lineage_endpoint_blocked(self):
        d=sample();d['provider_attempt_summary'][0]['endpoints']['quote']['fetch_status']='FAILED';self.assertIn('BTC:PROVIDER_LINEAGE_UNVERIFIED',validate(d,NOW)['defects'])
    def test_bad_lineage_timestamp_blocked(self):
        d=sample();d['provider_attempt_summary'][1]['quote_as_of']=iso(NOW-8);self.assertIn('ETH:PROVIDER_LINEAGE_UNVERIFIED',validate(d,NOW)['defects'])
    def test_missing_commit_blocked(self):
        d=sample();d['github_commit']=None;self.assertIn('GITHUB_COMMIT_MISSING_OR_INVALID',validate(d,NOW)['defects'])
    def test_commit_mismatch_blocked(self):
        self.assertIn('GITHUB_COMMIT_MISMATCH',validate(sample(),NOW,expected_commit='b'*40)['defects'])
    def test_run_id_mismatch_blocked(self):
        self.assertIn('GITHUB_RUN_ID_MISMATCH',validate(sample(),NOW,expected_run_id='987')['defects'])
    def test_run_id_valid_match(self):
        self.assertEqual(validate(sample(),NOW,expected_commit=COMMIT,expected_run_id=RUN_ID)['status'],'PASS')
    def test_volume_negative_blocked(self):
        d=sample();d['asset_coverage']['BTC']['one_h_bars'][0]['volume']=-1;self.assertIn('BTC:1H_UNVERIFIED',validate(d,NOW)['defects'])

if __name__=='__main__':unittest.main()