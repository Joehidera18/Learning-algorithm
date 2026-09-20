"""Provider boundaries and error handling; fixtures are not downloaded markets."""
import io
import json
import unittest
import zipfile
from unittest.mock import patch
from lab.massive_data import MassiveHistory, NoRedirect
from lab.forward_study import DAY


def response(start):
    return {"status":"OK","ticker":"X:BTCUSD","request_id":"fixture","resultsCount":1,
        "results":[{"t":start,"o":100,"h":102,"l":99,"c":101,"v":10,"vw":100.5,"n":3}]}


class MassiveTests(unittest.TestCase):
    def test_chunking_keeps_missing_intervals_missing_and_writes_provenance(self):
        client=MassiveHistory('private-test-key');start=1700006400000;end=start+60*DAY
        calls=[]
        def get(path,params):
            calls.append((path,params));return response(start+(len(calls)-1)*30*DAY)
        with patch.object(client,'_get',side_effect=get):content,manifest=client.download('BTC-USD','1h',start,end,end+DAY)
        self.assertEqual(len(calls),2)
        self.assertEqual(manifest['rows'],2)
        self.assertEqual(manifest['missing_intervals'],60*24-2)
        self.assertEqual(manifest['execution_venue'],'Aggregate crypto source; not a Coinbase fill history')
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            self.assertEqual(set(z.namelist()),{'candles.csv','manifest.json'})
            self.assertNotIn('private-test-key',z.read('manifest.json').decode())
            self.assertIn('1005.0',z.read('candles.csv').decode())

    def test_free_compatible_window_and_pair_validation_before_request(self):
        client=MassiveHistory('fixture');now=1700006400000
        with patch.object(client,'_get') as get:
            for symbol,interval,start,end in [('BTC-USD','1h',now,now+DAY),('BTC-USD','1h',now-731*DAY,now),
                ('../../bad','1h',now-DAY,now),('BTC-USD','1m',now-DAY,now)]:
                with self.assertRaises(ValueError):client.download(symbol,interval,start,end,now)
            get.assert_not_called()

    def test_malformed_partial_duplicate_and_other_market_responses_fail(self):
        now=1700006400000;start=now-DAY;client=MassiveHistory('fixture')
        cases=[{**response(start),'ticker':'X:ETHUSD'}, {**response(start),'next_url':'https://other.example'},
            {**response(start),'resultsCount':2}, {**response(start),'results':[response(start)['results'][0]]*2,'resultsCount':2},
            {**response(start),'results':[{**response(start)['results'][0],'h':50}]}]
        for data in cases:
            with patch.object(client,'_get',return_value=data),self.assertRaises(ValueError):
                client.download('BTC-USD','1h',start,now,now)

    def test_key_is_header_only_requests_are_paced_and_redirects_are_rejected(self):
        class Opener:
            def __init__(self):self.requests=[]
            def open(self,request,timeout):
                self.requests.append(request);return io.BytesIO(json.dumps({'status':'OK'}).encode())
        opener=Opener();waits=[]
        client=MassiveHistory('private-test-key',opener=opener,clock=lambda:10,wait=waits.append)
        client._get('/v2/test',{});client._get('/v2/test',{})
        self.assertEqual(len(waits),1);self.assertAlmostEqual(waits[0],12.2)
        self.assertEqual(opener.requests[0].get_header('Authorization'),'Bearer private-test-key')
        self.assertNotIn('private-test-key',opener.requests[0].full_url)
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
        with self.assertRaises(ValueError):MassiveHistory('')._get('/v2/test',{})


if __name__=='__main__':unittest.main()
