"""Ledger reconciliation and privacy checks for the read-only finance display."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lab.coinbase_live import CoinbaseTrader
from lab.continuous import ContinuousLearner
from lab.finances import closed_trade_totals, historical_trade_totals
from lab.paper_store import db_connect, load_state, recent_trades, save_state
from lab.service import Service

ROOT = Path(__file__).resolve().parents[1]


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/"account.sqlite3"
        self.agent = ContinuousLearner(self.db, Path(self.tmp.name)/"data")
        self.broker = SimpleNamespace(configured=False, allow_live=False)
        self.trader = CoinbaseTrader(self.db, self.agent, self.broker)

    def tearDown(self):
        self.tmp.cleanup()

    def paper_rows(self, outcomes, status="CLOSED"):
        con = db_connect(self.db)
        with con:
            for index, pnl in enumerate(outcomes):
                con.execute("""INSERT INTO paper_trades(opened_at,closed_at,product_id,family,direction,
                    entry,stop,target,qty,risk_usd,status,pnl,result_r,balance_after,context_json,decision_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (index,index+1,"BTC-USD","fixture","LONG",100,99,102,1,1,status,pnl,pnl,500+pnl,"{}","{}"))
        con.close()

    def coinbase_rows(self, outcomes, status="CLOSED", prefix="closed"):
        con = db_connect(self.db)
        with con:
            for index, pnl in enumerate(outcomes):
                ident=prefix+str(index)
                trade={"id":ident,"status":status,"pnl":str(pnl),"created_at":index,"product_id":"BTC-USD"}
                con.execute("INSERT INTO coinbase_trades VALUES(?,?,?,?,?)",(ident,ident,index,status,json.dumps(trade)))
        con.close()

    def test_net_results_keep_small_losses_and_exact_break_even_distinct(self):
        result=closed_trade_totals([10,-4,0,-.000001])
        self.assertEqual((result["winning_trades"],result["losing_trades"],result["break_even_trades"]),(1,2,1))
        self.assertEqual(result["money_won"],10)
        self.assertEqual(result["money_lost"],4.000001)
        self.assertEqual(result["net_pnl"],5.999999)
        self.assertEqual(result["win_rate"],25)
        for value in (None,float("nan"),float("inf"),True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                closed_trade_totals([value])

    def test_paper_totals_use_entire_journal_and_survive_restart(self):
        self.paper_rows([12.5]+[-.25]*125+[0])
        self.paper_rows([999],status="OPEN")
        result=self.agent.analytics()["trade_finances"]
        self.assertEqual(len(recent_trades(self.db)),100)
        self.assertEqual(result["closed_trades"],127)
        self.assertEqual(result["money_won"],12.5)
        self.assertEqual(result["money_lost"],31.25)
        self.assertEqual(result["net_pnl"],-18.75)
        self.assertEqual(result["break_even_trades"],1)
        recovered=ContinuousLearner(self.db,self.agent.data_dir)
        self.assertEqual(recovered.analytics()["trade_finances"],result)
        self.assertEqual(self.trader.status()["trade_finances"]["closed_trades"],0)

    def test_coinbase_totals_include_old_settled_trades_and_exclude_other_orders(self):
        self.coinbase_rows([8]+[-.2]*30+[0])
        self.coinbase_rows([999],status="REJECTED",prefix="rejected")
        self.coinbase_rows([777],status="EXIT_PENDING",prefix="pending")
        state=self.trader.status()
        result=state["trade_finances"]
        self.assertEqual(len(state["trades"]),25)
        self.assertEqual(result["closed_trades"],32)
        self.assertEqual((result["winning_trades"],result["losing_trades"],result["break_even_trades"]),(1,30,1))
        self.assertEqual((result["money_won"],result["money_lost"],result["net_pnl"]),(8,6,2))
        self.assertEqual(Decimal(state["realized_pnl"]),self.trader._realized())
        recovered=CoinbaseTrader(self.db,self.agent,self.broker)
        self.assertEqual(recovered.status()["trade_finances"],result)
        self.assertEqual(self.agent.analytics()["trade_finances"]["closed_trades"],0)

    def test_empty_journals_have_zero_totals_and_no_invented_win_rate(self):
        for result in (self.agent.analytics()["trade_finances"],self.trader.status()["trade_finances"]):
            self.assertEqual(result["closed_trades"],0)
            self.assertEqual(result["net_pnl"],0)
            self.assertIsNone(result["win_rate"])

    def report(self):
        return {"symbol":"AVAX-USD","interval":"15m","fingerprint":"fixture",
            "holdout":{"trades":3,"net_pnl":3.,"complete":True},
            "holdout_trades":[{"pnl":5.,"reason":"TIME"},{"pnl":-2.,"reason":"STOP"},{"pnl":0.,"reason":"END"}],
            "model":{"sentinel":"preserve exact original export"},"historical_examples":20000}

    def test_history_reconciles_selected_test_and_identifies_window_end_exits(self):
        result=historical_trade_totals(self.report())
        self.assertEqual(result["closed_trades"],3)
        self.assertEqual(result["net_pnl"],3)
        self.assertEqual(result["window_end_exits"],1)
        self.assertEqual((result["winning_trades"],result["losing_trades"],result["break_even_trades"]),(1,1,1))

    def test_missing_sampled_incomplete_and_inconsistent_history_stays_unknown(self):
        variants=[]
        missing=self.report();missing.pop("holdout_trades");variants.append(missing)
        sampled=self.report();sampled["holdout_trades"].pop();variants.append(sampled)
        incomplete=self.report();incomplete["holdout"]["complete"]=False;variants.append(incomplete)
        wrong=self.report();wrong["holdout"]["net_pnl"]=4;variants.append(wrong)
        invalid=self.report();invalid["holdout_trades"][0]["pnl"]=None;variants.append(invalid)
        for report in variants:
            with self.subTest(report=report):
                result=historical_trade_totals(report)
                self.assertEqual(result["status"],"unavailable")
                self.assertNotIn("money_won",result)

    def test_existing_saved_history_appears_without_retraining_and_exports_unchanged(self):
        service=Service(ROOT,self.db,self.agent.data_dir)
        report=self.report()
        save_state(self.db,"learning_result_fixture",report)
        compact={k:v for k,v in report.items() if k not in ("model","holdout_trades")}
        service.autolearn.state["results"]=[compact]
        with patch("lab.autolearn.load_state",wraps=load_state) as read:
            first=service.autolearn.status()
            second=service.autolearn.status()
        reads=[c for c in read.call_args_list if c.args[1]=="learning_result_fixture"]
        self.assertEqual(len(reads),1)
        self.assertEqual(first["results"][0]["trade_finances"]["money_won"],5)
        self.assertEqual(first["results"],second["results"])
        self.assertNotIn("trade_finances",service.autolearn.state["results"][0])
        self.assertEqual(service.autolearn.export()["results"][0],report)
        newer=copy.deepcopy(report);newer["fingerprint"]="newer";newer["holdout_trades"][0]["pnl"]=7;newer["holdout"]["net_pnl"]=5
        save_state(self.db,"learning_result_newer",newer)
        service.autolearn.state["results"]=[{k:v for k,v in newer.items() if k not in ("model","holdout_trades")}]
        self.assertEqual(service.autolearn.status()["results"][0]["trade_finances"]["money_won"],7)
        self.assertNotIn("fixture",service.autolearn._finance_cache)

    def test_coinbase_finances_keep_existing_authentication_boundary(self):
        self.coinbase_rows([123.45])
        service=Service(ROOT,self.db,self.agent.data_dir)
        code,body,_=service.handle("GET","/api/coinbase/status")
        self.assertEqual(code,200)
        self.assertEqual(body["mode"],"locked")
        self.assertNotIn("trade_finances",body)
        service.token="finance-test-token-123456"
        self.assertEqual(service.handle("GET","/api/coinbase/status")[0],401)
        code,body,_=service.handle("GET","/api/coinbase/status",headers={"authorization":"Bearer "+service.token})
        self.assertEqual(code,200)
        self.assertEqual(body["trade_finances"]["money_won"],123.45)


if __name__=="__main__":
    unittest.main()
