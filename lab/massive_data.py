"""Optional historical crypto data. Never merged into Coinbase execution data."""
import csv
import io
import json
import os
import re
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .evaluation import DATA_FIELDS, dataset_digest
from .forward_study import validated_candles, DAY

INTERVALS={"15m":(15,"minute",900000),"1h":(1,"hour",3600000),"1d":(1,"day",DAY)}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("Massive returned a redirect; authentication was not forwarded")


class MassiveHistory:
    def __init__(self, api_key=None, opener=None, clock=time.monotonic, wait=time.sleep):
        self.key=api_key if api_key is not None else os.getenv("MASSIVE_API_KEY","")
        self.opener=opener or build_opener(NoRedirect())
        self.clock,self.wait=clock,wait
        self.next_request=0.

    def _get(self,path,params):
        if not self.key or "\n" in self.key or "\r" in self.key:
            raise ValueError("Set MASSIVE_API_KEY privately in the environment before downloading")
        # Stay below Basic's five requests per minute, including chunk boundaries.
        delay=max(0.,self.next_request-self.clock())
        if delay:self.wait(delay)
        self.next_request=self.clock()+12.2
        request=Request("https://api.massive.com"+path+"?"+urlencode(params),
            headers={"Authorization":"Bearer "+self.key,"Accept":"application/json","User-Agent":"CryptO-Research/11.14"})
        try:
            with self.opener.open(request,timeout=15) as response:
                raw=response.read(16_000_001)
                if len(raw)>16_000_000:raise ValueError("Massive response exceeded the size limit")
                data=json.loads(raw)
        except HTTPError as exc:
            raise ValueError(f"Massive returned HTTP {exc.code}; check access, subscription and rate limits") from None
        except (URLError,TimeoutError,OSError):
            raise ValueError("Massive data connection failed; no prices were assumed") from None
        if not isinstance(data,dict) or data.get("status") not in ("OK","DELAYED"):
            raise ValueError("Massive did not return a successful data response")
        return data

    def download(self,symbol,interval,start,end,now=None):
        """Basic-compatible: finished UTC days and at most 730 requested days.

        Chunk below the API's 50,000 base-aggregate cap; require full responses.
        Empty intervals stay missing. Cross-exchange candles are research only.
        """
        if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9]{2,16}-USD",symbol) or interval not in INTERVALS:
            raise ValueError("Use a crypto USD pair with 15m, 1h or 1d candles")
        now=int(time.time()*1000) if now is None else now
        multiplier,timespan,step=INTERVALS[interval]
        if (type(start) is not int or type(end) is not int or start%step or end%step
                or not 0<end-start<=730*DAY or start < now//DAY*DAY-730*DAY
                or end>now//DAY*DAY):
            raise ValueError("Request at most 730 days within the past two years, ending before today's UTC session")
        ticker="X:"+symbol.replace("-","")
        rows,request_ids=[],[]
        approximate_volume=0
        cursor=start
        while cursor<end:
            cutoff=min(end,cursor+30*DAY)
            data=self._get(f"/v2/aggs/ticker/{quote(ticker,safe='')}/range/{multiplier}/{timespan}/{cursor}/{cutoff-1}",
                {"sort":"asc","limit":50000,"adjusted":"true"})
            if data.get("ticker")!=ticker or data.get("next_url"):
                raise ValueError("Massive returned a different market or an incomplete page")
            results=data.get("results",[])
            if not isinstance(results,list) or data.get("resultsCount",len(results))!=len(results):
                raise ValueError("Massive result count does not match its candles")
            chunk=[]
            try:
                for r in results:
                    if type(r["t"]) is not int or not cursor<=r["t"]<cutoff:
                        raise ValueError("Massive candle is outside its requested chunk")
                    for k in ("o","h","l","c","v"):
                        if isinstance(r[k],bool):raise ValueError("Boolean market value")
                    chunk.append({"ts":r["t"],"open":r["o"],"high":r["h"],"low":r["l"],"close":r["c"],
                        "volume":r["v"],"quote_volume":float(r["v"])*float(r.get("vw",r["c"])),"trades":r.get("n",0)})
                    approximate_volume+=int("vw" not in r)
            except (KeyError,TypeError,OverflowError):
                raise ValueError("Massive returned malformed candle fields") from None
            rows.extend(validated_candles(chunk,step,cutoff))
            request_ids.append(data.get("request_id"))
            cursor=cutoff
        if not rows:raise ValueError("Massive returned no candles for the requested market and dates")
        expected=(end-start)//step
        manifest={"provider":"Massive","symbol":symbol,"provider_ticker":ticker,"interval":interval,
            "requested_start_ts":start,"requested_end_ts":end,"retrieved_at":now,"rows":len(rows),
            "data_sha256":dataset_digest(rows),"coverage_pct":100*len(rows)/expected,
            "missing_intervals":expected-len(rows),"request_ids":request_ids,
            "recency_mode":"Historical completed UTC days; Basic-compatible requests, actual entitlement determined by provider",
            "quote_volume_basis":"volume times reported VWAP; when absent, volume times close is an estimate",
            "estimated_quote_volume_rows":approximate_volume,
            "trade_count_basis":"Provider n field; zero means unknown when n was absent",
            "execution_venue":"Aggregate crypto source; not a Coinbase fill history",
            "scope":"Separate research dataset. No gap filling, no automatic training or qualification. "
                    "Availability, market coverage and billing remain subject to the data provider's subscription."}
        output=io.BytesIO()
        content=io.StringIO(newline="")
        writer=csv.DictWriter(content,fieldnames=DATA_FIELDS);writer.writeheader();writer.writerows(rows)
        with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("candles.csv",content.getvalue())
            z.writestr("manifest.json",json.dumps(manifest,indent=2,allow_nan=False))
        return output.getvalue(),manifest
