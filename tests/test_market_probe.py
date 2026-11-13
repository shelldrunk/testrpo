import sys,unittest,datetime as dt, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from market_probe import coinbase_parser,aggregate_four_h,binance_klines_parser,kraken_ohlc_parser,parse_quote,probe_one,iso

NOW=dt.datetime(2026,11,12,16,30,tzinfo=dt.timezone.utc).timestamp()
BASE=int(NOW//14400*14400)-14400

class TestMarketProof(unittest.TestCase):
    def make_coinbase_rows(self):
        return [[BASE+3600*i, 90,110,100,105,500] for i in range(4)]
    def test_candle_partial_excluded(self):
        rows=[[int(NOW//3600*3600),90,110,100,105,500]]
        self.assertEqual(coinbase_parser(rows,'one_h',NOW),[])
    def test_4h_requires_four_complete_contiguous(self):
        a=coinbase_parser(self.make_coinbase_rows(),'one_h',BASE+14400+3600)
        self.assertEqual(len(aggregate_four_h(a,BASE+14400+3600)),1)
        self.assertEqual(aggregate_four_h(a[:-1],BASE+14400+3600),[])
    def test_4h_boundary_alignment(self):
        shifted=[[BASE+3600*(i+1),90,110,100,105,500] for i in range(4)]
        a=coinbase_parser(shifted,'one_h',BASE+20000)
        self.assertEqual(aggregate_four_h(a,BASE+20000),[])
    def test_negative_price_rejected(self):
        self.assertIsNone(parse_quote('Coinbase Exchange',{'price':'-1','time':iso(NOW)})['price'])
    def test_coingecko_not_execution_source(self):
        self.assertNotIn('CoinGecko',('Coinbase Exchange','Binance.US','Kraken','Binance'))
    def test_timestamp_not_pubdate(self):
        self.assertIsNone(parse_quote('Coinbase Exchange',{'price':'100','last_updated':iso(NOW)})['traded_at_s'])
    def test_future_quote_rejected(self):
        rows=self.make_coinbase_rows()
        def fake(u):
            if 'ticker' in u: return {'price':'100','time':iso(NOW+100)},200,None
            return rows,200,None
        self.assertFalse(probe_one('Coinbase Exchange','BTC',NOW,fake)['quote_fresh'])
    def test_stale_quote_rejected(self):
        rows=self.make_coinbase_rows()
        def fake(u):
            if 'ticker' in u:return {'price':'100','time':iso(NOW-3600)},200,None
            return rows,200,None
        self.assertFalse(probe_one('Coinbase Exchange','BTC',NOW,fake)['quote_fresh'])
    def test_kraken_final_candle_is_forming(self):
        r=[[BASE,100,110,90,105,104,123,1],[BASE+3600,105,110,100,107,106,250,1]]
        p={'error':[],'result':{'XXBTZUSD':r,'last':42}}
        out=kraken_ohlc_parser(p,3600,BASE+7200)
        self.assertEqual(len(out),1)
    def test_binance_hour_alignment(self):
        rows=[[int(BASE*1000),'100','110','90','105','30',0],[(int(BASE)+1800)*1000,'100','110','90','105','30',0]]
        out=binance_klines_parser(rows,3600,BASE+7200)
        self.assertEqual(len(out),1)
    def test_missing_quote_never_verified(self):
        def failed(u):return None,None,'URLError:DNS'
        r=probe_one('Coinbase Exchange','BTC',NOW,failed)
        self.assertEqual(r['status'],'FAILED')
        self.assertFalse(r['one_h_closed'])
        self.assertFalse(r['four_h_closed'])
    def test_one_h_fresh_and_4h_fresh_can_verify(self):
        base=BASE
        rows=self.make_coinbase_rows()
        def fake(u):
            if 'ticker' in u: return {'price':'105','time':iso(NOW-30)},200,None
            return rows,200,None
        r=probe_one('Coinbase Exchange','ETH',NOW,fake)
        self.assertEqual(r['status'],'VERIFIED')
        self.assertEqual(r['instrument'],'SPOT')
        self.assertEqual(r['price'],105.0)
    def test_coingecko_aggregation_not_trade(self):
        def fake(u):return [{"current_price":101,"last_updated":iso(NOW-10)}],200,None
        r=probe_one("CoinGecko","BTC",NOW,fake)
        self.assertEqual(r["status"],"PARTIAL")
        self.assertEqual(r["reference_price"],101.0)
        self.assertFalse(r["quote_fresh"])
        self.assertIsNone(r["quote_as_of"])
    def test_broker_firewall_no_account_fields(self):
        def failed(u):return None,None,'DNS'
        r=probe_one('Coinbase Exchange','BTC',NOW,failed)
        self.assertNotIn('fill',r)
        self.assertNotIn('order',r)
        self.assertNotIn('balance',r)


    def test_live_provider_fetch_uses_end_of_fetch_timestamp(self):
        import unittest.mock as mock
        rows=self.make_coinbase_rows()
        def fake(u):
            if 'ticker' in u: return {'price':'105','time':iso(NOW+12)},200,None
            return rows,200,None
        with mock.patch('market_probe.utcnow',return_value=dt.datetime.fromtimestamp(NOW+20,dt.timezone.utc)):
            r=probe_one('Coinbase Exchange','ETH',None,fake)
        self.assertTrue(r['quote_fresh'])
        self.assertEqual(r['fetched_at'],iso(NOW+20))
    def test_live_fetch_still_rejects_future_timestamp(self):
        import unittest.mock as mock
        rows=self.make_coinbase_rows()
        def fake(u):
            if 'ticker' in u: return {'price':'105','time':iso(NOW+100)},200,None
            return rows,200,None
        with mock.patch('market_probe.utcnow',return_value=dt.datetime.fromtimestamp(NOW+20,dt.timezone.utc)):
            r=probe_one('Coinbase Exchange','ETH',None,fake)
        self.assertFalse(r['quote_fresh'])

if __name__=='__main__': unittest.main()