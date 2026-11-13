import unittest
from scripts.compact_watch_feed import compact

class TestCompactFeed(unittest.TestCase):
    def test_strips_redundant_source_rows_but_keeps_provenance(self):
        d={'schema':'CRYPTO_PUBLIC_SPOT_MARKET_PROBE_V1','generated_at':'2026-11-13T00:49:59Z','asset_coverage':{'BTC':{'provider':'Coinbase Exchange','one_h_bars':list(range(24)),'four_h_bars':list(range(12))}},'provider_attempts':[{'provider':'Coinbase Exchange','asset':'BTC','pair':'BTC-USD','status':'VERIFIED','quote_as_of':'2026-11-13T00:49:58Z','endpoints':{'quote':{'url':'https://api.exchange.coinbase.com','fetch_status':'VERIFIED','http_status':200,'error':None}},'one_h_bars':list(range(24))}],'trade_authorization':'NONE'}
        c=compact(d)
        self.assertNotIn('provider_attempts',c)
        self.assertEqual(len(c['asset_coverage']['BTC']['one_h_bars']),12)
        self.assertEqual(len(c['asset_coverage']['BTC']['four_h_bars']),8)
        self.assertEqual(c['provider_attempt_summary'][0]['pair'],'BTC-USD')
        self.assertEqual(c['trade_authorization'],'NONE')
    def test_missing_asset_remains_missing(self):
        self.assertIsNone(compact({'asset_coverage':{'SOL':None}})['asset_coverage']['SOL'])
    def test_no_private_account_fields(self):
        c=compact({'asset_coverage':{},'provider_attempts':[],'balance':150,'orders':[1],'fills':[1]})
        self.assertNotIn('balance',c);self.assertNotIn('orders',c);self.assertNotIn('fills',c)
if __name__=='__main__': unittest.main()