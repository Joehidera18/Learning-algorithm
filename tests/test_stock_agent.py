"""Research agent integration tests. Provider responses and market jobs are fixtures."""
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import uuid

import requests

from lab.paper_store import db_connect
from lab.stock_agent import AgentError, StockAgent, extract_answer, TOOLS, RUN_TOOL
from lab.stock_service import StockService
from lab.strategy_lab import REPORT_VERSION

BASE = Path(__file__).resolve().parents[1]
TEST_REQUEST = {"symbol":"SPY", "strategy":"orb_15m", "decision":"5m", "days":30,
                "provider":"yahoo", "mode":"day", "starting_balance":500, "fractional_shares":True}


def reply(text="Fixture research. No investment recommendation.", annotations=None):
    return {"status":"completed", "output":[{"type":"message", "role":"assistant", "content":[
        {"type":"output_text", "text":text, "annotations":annotations or []}]}],
        "usage":{"input_tokens":100,"output_tokens":50}}


def tool(name, args):
    return {"status":"completed", "output":[{"type":"function_call", "name":name,
        "call_id":uuid.uuid4().hex, "arguments":json.dumps(args)}], "usage":{"input_tokens":100,"output_tokens":50}}


class StockAgentTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {"OPENAI_API_KEY":"fixture-server-key", "OPENAI_MODEL":"fixture-model",
            "AGENT_DAILY_RUN_LIMIT":"25", "ALPACA_API_KEY":"", "ALPACA_SECRET_KEY":"",
            "APCA_API_KEY_ID":"", "APCA_API_SECRET_KEY":"", "MASSIVE_API_KEY":""})
        self.env.start()
        self.temp=tempfile.TemporaryDirectory()
        self.service=StockService(BASE,Path(self.temp.name)/"unused.sqlite3",Path(self.temp.name)/"data","test-token",resume=False)
        self.service.strategy_lab.resume=Mock()
        self.service.equities.resume=Mock()
        self.agent=self.service.research_agent
        self.agent.transport=Mock(return_value=reply())
        self.network=patch("requests.post",side_effect=AssertionError("Unexpected external request"))
        self.network_mock=self.network.start()
        self.releases=[]

    def tearDown(self):
        for release in self.releases:
            release.set()
        if self.agent.worker:
            self.agent.worker.join(3)
        self.service.shutdown()
        self.network.stop()
        self.env.stop()
        self.temp.cleanup()

    def body(self, **kwargs):
        return {"message":"Research this test", "request_id":uuid.uuid4().hex, **kwargs}

    def ask(self, body=None):
        value=self.agent.start(body or self.body())
        self.agent.worker.join(4)
        self.assertFalse(self.agent.worker.is_alive(), "Fixture agent did not finish")
        return self.agent.get_run(value["id"])

    def blocked(self):
        entered,release=threading.Event(),threading.Event()
        self.releases.append(release)
        def transport(payload):
            entered.set()
            release.wait(4)
            return reply()
        self.agent.transport=Mock(side_effect=transport)
        body=self.body(allow_backtests=True)
        run=self.agent.start(body)
        self.assertTrue(entered.wait(2))
        return body,run,release

    def http(self, action, method="GET", body=None, authorized=True, query=None):
        headers={"content-type":"application/json"}
        if authorized:
            headers["authorization"]="Bearer test-token"
        return self.service.handle(method,"/api/agent/"+action,query,body,headers)

    def complete_job(self, **changes):
        job=self.service.strategy_lab.start(TEST_REQUEST)
        result={"report_version":REPORT_VERSION,"eligible_for_bot":True,
            "later":{"complete":True,"trades":25,"net_pnl":12,"mean_r":.2},
            "later_higher_cost":{"complete":True,"trades":25,"net_pnl":8,"mean_r":.1}, **changes}
        self.service.strategy_lab._patch(job["id"],status="complete",message="Fixture only",result=result)
        return job["id"]

    def test_authentication_guards_history_paid_work_and_notebook(self):
        run=self.ask()
        for method,action,body in [("GET","status",None),("GET","run",None),("GET","thread",None),
                ("GET","export",None),("GET","notebook",None),("GET","proposal",None),
                ("POST","start",self.body()),("POST","cancel",{"id":run["id"]}),
                ("POST","delete",{"id":run["thread_id"]}),("POST","notebook/delete",{"id":"job"})]:
            with self.subTest(action=action):
                self.assertEqual(self.http(action,method,body,False)[0],401)
        self.assertEqual(self.agent.status()["daily_used"],1)

    def test_missing_key_disables_only_agent_and_missing_token_hides_history(self):
        run=self.ask()
        self.agent.api_key=""
        self.assertEqual(self.http("start","POST",self.body())[0],503)
        self.assertEqual(self.http("status")[1]["missing"],["OPENAI_API_KEY"])
        self.assertEqual(self.service.handle("GET","/agent")[0],200)
        self.assertEqual(self.service.handle("GET","/api/health")[0],200)
        self.service.token=""
        self.assertEqual(self.http("status")[1]["threads"],[])
        self.assertEqual(self.http("run",query={"id":run["id"]})[0],503)

    def test_validates_inputs_before_billing_or_creating_conversation(self):
        cases=[{"message":" "},{"message":"a"*6001},{"message":[]},{"web_search":"yes"},
               {"deep_research":1},{"allow_backtests":"false"},{"request_id":"../secret"},
               {"thread_id":"missing"},{"model":"arbitrary"},{"thread_id":uuid.uuid4().hex}]
        for values in cases:
            with self.subTest(values=list(values)),self.assertRaises(AgentError):
                self.agent.start(self.body(**values))
        self.assertEqual(self.agent.status()["daily_used"],0)
        self.assertEqual(self.agent.status()["threads"],[])
        self.agent.transport.assert_not_called()

    def test_response_tool_round_trip_replays_reasoning_and_excludes_secrets(self):
        first=tool("get_workspace",{})
        first["output"].insert(0,{"type":"reasoning","id":"reasoning-id","summary":[],"encrypted_content":"opaque"})
        payloads=[]
        def transport(payload):
            payloads.append(copy.deepcopy(payload))
            return first if len(payloads)==1 else reply()
        self.agent.transport=transport
        run=self.ask()
        self.assertEqual(run["status"],"complete")
        self.assertEqual(payloads[1]["input"][1:3],first["output"])
        output=payloads[1]["input"][-1]
        self.assertEqual(output["type"],"function_call_output")
        evidence=json.loads(output["output"])
        self.assertFalse(evidence["live_orders_allowed"])
        self.assertEqual(evidence["asset_class"],"equity")
        self.assertFalse(payloads[1]["store"])
        self.assertIn("reasoning.encrypted_content",payloads[1]["include"])
        self.assertNotIn("fixture-server-key",json.dumps(payloads)+json.dumps(run))
        self.assertEqual(run["answer"]["usage"],{"input_tokens":200,"output_tokens":100})
        self.assertEqual(run["answer"]["tools"][0]["tool"],"get_workspace")

    def test_web_disabled_does_not_offer_search_or_claim_web_used(self):
        run=self.ask(self.body(web_search=False))
        tools=self.agent.transport.call_args.args[0]["tools"]
        self.assertFalse(any(t["type"]=="web_search" for t in tools))
        self.assertFalse(run["answer"]["web_searched"])
        self.assertFalse(any(t.get("name")=="run_stock_backtest" for t in tools))

    def test_citations_remain_inline_and_unsafe_links_are_discarded(self):
        text="🧬 Dated finding SOURCE. <img src=x onerror=alert(1)>"
        at=text.index("SOURCE")
        value=reply(text,[{"type":"url_citation","url":"https://example.org/release","title":"Source",
                          "start_index":at,"end_index":at+6},
                         {"type":"url_citation","url":"javascript:alert(1)","start_index":0,"end_index":1},
                         {"type":"url_citation","url":"https://user:pass@example.org","start_index":0,"end_index":1}])
        value["output"].insert(0,{"type":"web_search_call","status":"completed"})
        self.agent.transport=Mock(return_value=value)
        run=self.ask()
        self.assertTrue(run["answer"]["web_searched"])
        self.assertEqual(len(run["answer"]["sources"]),1)
        self.assertIn("🧬 Dated finding [1].",run["answer"]["text"])
        self.assertEqual(run["answer"]["parts"][1]["url"],"https://example.org/release")

    def test_prepared_backtest_is_validated_without_queue_or_download(self):
        self.agent.transport=Mock(side_effect=[tool("prepare_backtest",TEST_REQUEST),reply()])
        run=self.ask()
        proposal=run["answer"]["proposals"][0]
        self.assertEqual(self.service.strategy_lab.status()["jobs"],[])
        normalized=self.agent.proposal(run["id"],proposal["id"])["request"]
        self.assertEqual(normalized["symbol"],"SPY")
        self.assertIn("fee_rate",normalized["settings"])
        self.assertNotIn("cutoff_ts",normalized)
        self.network_mock.assert_not_called()

    def test_provider_availability_is_rechecked_when_opening_proposal(self):
        self.agent.transport=Mock(side_effect=[tool("prepare_backtest",TEST_REQUEST),reply()])
        run=self.ask()
        with patch.object(self.service.strategy_lab,"validate_request",side_effect=ValueError("Provider unavailable")):
            with self.assertRaisesRegex(ValueError,"Provider unavailable"):
                self.agent.proposal(run["id"],run["answer"]["proposals"][0]["id"])

    def test_arbitrary_actions_malformed_args_and_crypto_tests_are_rejected(self):
        for name,args in [("place_order",{}),("execute_code",{"code":"bad"}),("get_workspace",{"extra":1}),
                ("prepare_backtest",dict(TEST_REQUEST,days=True)),( "prepare_backtest",dict(TEST_REQUEST,symbol="BTC-USD")),
                ("prepare_backtest",dict(TEST_REQUEST,provider="http://localhost")),
                ("prepare_backtest",dict(TEST_REQUEST,strategy="../arbitrary")),
                ("prepare_backtest",dict(TEST_REQUEST,starting_balance=float("nan")))]:
            with self.subTest(name=name,args=args),self.assertRaises((AgentError,ValueError)):
                self.agent._tool(name,args,[])
        self.assertEqual(self.service.strategy_lab.status()["jobs"],[])

    def test_model_cannot_queue_without_run_permission(self):
        self.agent.transport=Mock(side_effect=[tool("run_stock_backtest",TEST_REQUEST),reply()])
        run=self.ask()
        self.assertFalse(run["answer"]["tools"][0]["ok"])
        self.assertEqual(run["answer"]["queued_backtests"],[])
        self.assertEqual(self.service.strategy_lab.status()["jobs"],[])

    def test_allowed_backtests_are_deduplicated_capped_and_saved(self):
        body,run,release=self.blocked()
        queued=[]
        def queue(args):
            return self.agent._tool("run_stock_backtest",args,[],run=run,started=time.monotonic(),queued=queued)
        first=queue(TEST_REQUEST)
        self.assertEqual(queue(TEST_REQUEST),first)
        queue(dict(TEST_REQUEST,symbol="QQQ"))
        self.assertEqual(queue(TEST_REQUEST),first)
        with self.assertRaisesRegex(AgentError,"two-backtest"):
            queue(dict(TEST_REQUEST,symbol="IWM"))
        self.assertEqual(len(self.service.strategy_lab.status()["jobs"]),2)
        self.assertEqual(len(self.agent.get_run(run["id"])["answer"]["queued_backtests"]),2)
        self.agent.cancel(run["id"])
        release.set()

    def test_cancellation_survives_late_answer_and_blocks_new_test(self):
        _,run,release=self.blocked()
        self.agent.cancel(run["id"])
        with self.assertRaisesRegex(AgentError,"stopped"):
            self.agent._tool("run_stock_backtest",TEST_REQUEST,[],run=run,started=time.monotonic(),queued=[])
        release.set();self.agent.worker.join(3)
        self.assertEqual(self.agent.get_run(run["id"])["status"],"cancelled")
        self.assertIsNone(self.agent.get_run(run["id"])["answer"])
        self.assertEqual(self.service.strategy_lab.status()["jobs"],[])

    def test_request_id_retry_and_daily_quota_survive_conversation_deletion(self):
        self.agent.daily_limit=1
        body=self.body();run=self.ask(body)
        self.assertEqual(self.agent.start(body)["id"],run["id"])
        with self.assertRaisesRegex(AgentError,"different message"):
            self.agent.start(dict(body,message="Changed prompt"))
        self.assertEqual(self.agent.transport.call_count,1)
        self.agent.delete_thread(run["thread_id"])
        with self.assertRaisesRegex(AgentError,"Daily"):
            self.agent.start(self.body())
        self.assertEqual(self.agent.status()["daily_used"],1)

    def test_parallel_process_cannot_recover_or_start_over_active_work(self):
        _,run,release=self.blocked()
        other=StockAgent(self.service,transport=Mock(return_value=reply()))
        try:
            self.assertEqual(other.get_run(run["id"])["status"],"running")
            with self.assertRaisesRegex(AgentError,"Another agent"):
                other.start(self.body())
            with self.assertRaisesRegex(AgentError,"active request"):
                other.delete_thread(run["thread_id"])
        finally:
            other.shutdown();release.set()

    def test_restart_marks_interruption_without_provider_retry(self):
        run=self.ask()
        with closing(db_connect(self.agent.db_path)) as con,con:
            con.execute("UPDATE agent_runs SET status='running' WHERE id=?",(run["id"],))
        transport=Mock()
        other=StockAgent(self.service,transport=transport)
        try:
            self.assertEqual(other.get_run(run["id"])["status"],"error")
            self.assertIn("restarted",other.get_run(run["id"])["error"])
            transport.assert_not_called()
        finally:
            other.shutdown()

    def test_prior_conversation_is_server_loaded_and_bounded(self):
        first=self.ask(self.body(message="Private first prompt"))
        second=self.ask(self.body(message="Follow up",thread_id=first["thread_id"]))
        messages=self.agent.transport.call_args.args[0]["input"]
        self.assertEqual([m["role"] for m in messages],["user","assistant","user"])
        self.assertIn("Private first prompt",json.dumps(messages))
        third=self.ask(self.body(message="Separate conversation"))
        self.assertNotIn("Private first prompt",json.dumps(self.agent.transport.call_args.args[0]["input"]))
        self.assertNotEqual(third["thread_id"],second["thread_id"])

    def test_notebook_classifies_evidence_without_trusting_model_claims(self):
        cases=[({},"passed_historical_checks"),
            ({"later":{"complete":False,"trades":30,"net_pnl":None}},"incomplete"),
            ({"later":{"complete":True,"trades":2,"net_pnl":5}},"insufficient_trades"),
            ({"later":{"complete":True,"trades":30,"net_pnl":-5,"mean_r":.1}},"did_not_pass"),
            ({"report_version":0},"obsolete_report")]
        for changes,expected in cases:
            ident=self.complete_job(**changes)
            review=self.agent.record_review({"id":ident,"lesson":"Model claim of success is just a note","next_hypothesis":"Another hypothesis"})
            self.assertEqual(review["assessment"],expected)
            self.assertFalse(review["live_trading_approved"])
            self.assertEqual(review["evidence"]["later"].get("net_pnl"),changes.get("later",{}).get("net_pnl",12))
        self.assertEqual(len(self.agent.notebook()["reviews"]),5)
        self.agent.delete_review(ident)
        self.assertEqual(len(self.agent.notebook()["reviews"]),4)
        self.assertEqual(self.service.strategy_lab.get(ident)["status"],"complete")

    def test_unfinished_test_cannot_be_saved_as_tested_evidence(self):
        ident=self.service.strategy_lab.start(TEST_REQUEST)["id"]
        with self.assertRaisesRegex(AgentError,"completed backtest"):
            self.agent.record_review({"id":ident,"lesson":"A success","next_hypothesis":"Next"})
        self.assertFalse(self.agent.notebook()["reviews"])

    def test_incomplete_provider_response_is_not_saved_as_success(self):
        self.agent.transport=Mock(return_value={"status":"incomplete","output":[]})
        run=self.ask()
        self.assertEqual(run["status"],"error")
        self.assertIsNone(run["answer"])
        self.assertEqual(self.agent.transport.call_count,1)

    def test_tool_loop_has_hard_limit_and_final_answer_turn(self):
        self.agent.transport=Mock(side_effect=lambda p:tool("get_backtest_options",{}))
        run=self.ask()
        self.assertEqual(run["status"],"error")
        self.assertEqual(self.agent.transport.call_count,5)
        self.assertEqual(self.agent.transport.call_args.args[0]["tool_choice"],"none")

    def test_unknown_tool_is_rejected_in_protocol_and_does_not_crash(self):
        self.agent.transport=Mock(side_effect=[tool("get_secrets",{}),reply()])
        run=self.ask()
        self.assertEqual(run["status"],"complete")
        self.assertEqual(run["answer"]["tools"][0]["tool"],"unsupported")
        self.assertFalse(run["answer"]["tools"][0]["ok"])

    def test_transport_uses_fixed_endpoint_server_auth_no_redirect_no_retry(self):
        response=Mock(status_code=200,content=b"{}")
        response.json.return_value=reply()
        with patch("requests.post",return_value=response) as post:
            self.agent._request_openai({"model":"fixture-model"})
        args,kwargs=post.call_args
        self.assertEqual(args[0],"https://api.openai.com/v1/responses")
        self.assertEqual(kwargs["headers"]["Authorization"],"Bearer fixture-server-key")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"],(5,120))
        self.assertEqual(post.call_count,1)

    def test_provider_failures_redact_raw_response_and_credentials(self):
        for code in (401,403,429,500,302):
            response=Mock(status_code=code,content=b"private provider response fixture-server-key")
            with self.subTest(code=code),patch("requests.post",return_value=response),self.assertRaises(AgentError) as error:
                self.agent._request_openai({})
            self.assertNotIn("fixture-server-key",str(error.exception))
        with patch("requests.post",side_effect=requests.Timeout("private-url")),self.assertRaises(AgentError) as error:
            self.agent._request_openai({})
        self.assertNotIn("private-url",str(error.exception))

    def test_export_is_authenticated_and_retains_source_urls(self):
        self.agent.transport=Mock(return_value=reply("Source [1]",[{"type":"url_citation","url":"https://example.org/release","title":"Release","start_index":7,"end_index":10}]))
        run=self.ask()
        status,body,headers=self.http("export",query={"id":run["id"]})
        self.assertEqual(status,200)
        self.assertIn(b"https://example.org/release",body)
        self.assertIn("attachment",headers["Content-Disposition"])


if __name__=="__main__":
    unittest.main()
