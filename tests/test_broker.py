import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS_PATH = os.path.join(FIX, "trader-risk", "orders-tsla.json")
PLAN_PATH = os.path.join(FIX, "trader-budget", "plan-tsla.json")
NOW = "2026-10-19 10:00"
TODAY = "2026-10-19"
ITC_BUY = {"symbol": "ITC", "side": "buy", "notional": "1250", "type": "market", "time_in_force": "day"}
BATCH = ["ITC", "HDFCBANK", "INFY", "RELIANCE", "TCS"]
ENTRY_CALL = {"variety": "regular", "exchange": "NSE", "tradingsymbol": "TSLA", "transaction_type": "BUY",
              "quantity": 80, "product": "MIS", "order_type": "MARKET", "validity": "DAY"}
STOP_CALL = {"variety": "regular", "exchange": "NSE", "tradingsymbol": "TSLA", "transaction_type": "SELL",
             "quantity": 80, "product": "MIS", "order_type": "SL-M", "trigger_price": 358.32, "validity": "DAY"}
TSLA_PLAIN = ("BUY 80 TSLA, market, good for today / stop-loss 358.32 / target 370.04 (an alert, not a resting "
              "order) / max loss about Rs 468.80 if the stop fills at 358.32 (it can fill worse in a fast market)")


def tsla(**over):
    with open(ORDERS_PATH) as fh:
        o = json.load(fh)["orders"][0]
    o.update(over)
    return o


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExplicitYes(unittest.TestCase):
    def yes(self, reply, order=ITC_BUY, batch=BATCH):
        return ticket.parse_yes(reply, order, batch)[0]

    def test_plain_yes_counts(self):
        for r in ("yes", "Yes.", "YES", "y", "yes place it", "Yes, buy it", "yes ITC", "yes Rs 1,250 of ITC",
                  "yes 1250"):
            self.assertTrue(self.yes(r), r)

    def test_anything_else_does_not(self):
        for r in ("", "sure", "ok", "okay", "go", "do it", "yeah", "yep", "haan", "absolutely", "send it",
                  "yes to all", "yes, all of them", "yes to the rest", "yes both",
                  "yes HDFCBANK", "yes 1000", "yes but make it 1000", "yes?", "no", "not yes",
                  "yes, wait", "yes if it is under 340"):
            self.assertFalse(self.yes(r), r)

    def test_amount_must_match_this_order(self):
        sell = {"symbol": "M&M", "side": "sell", "qty": "3", "type": "market", "time_in_force": "day"}
        self.assertTrue(self.yes("yes sell 3 M&M", sell, ["M&M", "TCS"]))
        self.assertFalse(self.yes("yes sell 4", sell))
        self.assertFalse(self.yes("yes TCS", sell, ["M&M", "TCS"]))

    def test_a_bracket_yes(self):
        o = tsla()
        for r in ("yes", "yes 80 TSLA", "yes 358.32", "yes max loss 468.80", "yes target 370.04"):
            self.assertTrue(self.yes(r, o, ["TSLA"]), r)
        for r in ("yes 81", "yes 100 TSLA", "yes but stop at 357", "yes, stop 358.32", "yes ITC", "sure"):
            self.assertFalse(self.yes(r, o, ["TSLA", "ITC"]), r)


class TicketShape(unittest.TestCase):
    def test_the_kite_calls(self):
        self.assertEqual(ticket.tool_input(tsla()), [ENTRY_CALL, STOP_CALL])
        lim = ticket.tool_input({"symbol": "M&M", "side": "buy", "qty": 3, "type": "limit", "limit_price": 3050.5,
                                 "time_in_force": "day"})
        self.assertEqual(lim, [{"variety": "regular", "exchange": "NSE", "tradingsymbol": "M&M",
                                "transaction_type": "BUY", "quantity": 3, "product": "MIS", "order_type": "LIMIT",
                                "validity": "DAY", "price": 3050.5}])
        bse = ticket.tool_input(tsla(symbol="RELIANCE.BO", exchange="BSE"))
        self.assertEqual((bse[0]["exchange"], bse[0]["tradingsymbol"], bse[1]["exchange"]), ("BSE", "RELIANCE", "BSE"))
        sell = ticket.tool_input({"symbol": "TSLA", "side": "sell", "qty": "80", "type": "market"})
        self.assertEqual(len(sell), 1)                       # a sell has no stop-loss leg
        self.assertEqual(sell[0]["transaction_type"], "SELL")

    def test_the_fingerprint_matches_the_risk_check(self):
        o = tsla()
        self.assertEqual(ticket.fingerprint(o), check.fingerprint(o))
        self.assertEqual(ticket.fingerprint(dict(o, why="x", plan={})), ticket.fingerprint(o))
        self.assertNotEqual(ticket.fingerprint(dict(o, exchange="BSE")), ticket.fingerprint(o))
        self.assertEqual(ticket.ORDER_FIELDS, check.ORDER_FIELDS)

    def test_plain_english(self):
        self.assertEqual(ticket.plain(ITC_BUY), "BUY Rs 1,250 of ITC, market order, good for today")
        self.assertEqual(ticket.plain({"symbol": "ITC", "side": "sell", "qty": "1", "type": "limit",
                                       "limit_price": "450", "time_in_force": "day"}),
                         "SELL 1 share of ITC, limit order at Rs 450, good for today")
        self.assertEqual(ticket.plain(tsla()), TSLA_PLAIN)
        lim = tsla(type="limit", limit_price="364.00")
        self.assertEqual(ticket.plain(lim).split(" / ")[0], "BUY 80 TSLA, limit 364.00, good for today")
        self.assertEqual(ticket.max_loss(lim), (454.4, 358.32))
        no_plan = {k: v for k, v in tsla().items() if k != "plan"}
        self.assertEqual(ticket.max_loss(no_plan), (None, 358.32))


class DesktopConfig(unittest.TestCase):
    def test_example_is_a_self_hosted_kite_server_with_placeholder_keys(self):
        with open(os.path.join(ROOT, "trader-broker", "claude_desktop_config.example.json")) as fh:
            server = json.load(fh)["mcpServers"]["kite"]
        self.assertEqual(server["env"]["APP_MODE"], "stdio")
        for k in ("KITE_API_KEY", "KITE_API_SECRET"):
            self.assertIn("NEVER_IN_CHAT", server["env"][k])


class Flow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        shutil.copy(ORDERS_PATH, self.orders)
        self.cfg = os.path.join(self.d, "config.json")
        shutil.copy(CFG_PATH, self.cfg)
        self.risk = os.path.join(self.d, "state", "risk.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.pf = os.path.join(self.d, "portfolio.json")
        self.none = os.path.join(self.d, "none")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra, **kw):
        return list(extra) + ["--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                              "--state", self.state, "--now", kw.get("now", NOW)]

    def run_risk(self, now=NOW):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", self.orders, "--config", self.cfg, "--portfolio", self.pf,
                               "--prices", self.none, "--state", self.state, "--now", now, "--out", self.risk])

    def go_live(self):
        with open(self.cfg) as fh:
            c = json.load(fh)
        c.update(paper=False, broker="kite")
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)

    def state_doc(self):
        with open(self.state) as fh:
            return json.load(fh)

    def test_nothing_is_ready_before_the_risk_check(self):
        code, text, _ = run(self.args("show"))
        self.assertEqual(code, 1)
        self.assertIn("NOT READY", text)
        self.assertNotIn("Reply \"yes\"", text)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("not ready", err)

    def test_paper_is_the_default_and_sends_nothing(self):
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, PAPER (nothing goes to Kite), NSE", text)
        self.assertIn("this would be place_order with (paper: not sent)", text)
        self.assertNotIn("Allow once", text)
        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn("PAPER: nothing goes to Kite", text)
        self.assertNotIn("call the Kite MCP place_order", text)
        self.assertEqual(self.state_doc()["orders"][0]["broker"], "paper")

    def test_the_full_two_yes_flow_on_a_live_kite_account(self):
        self.go_live()
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, LIVE KITE ACCOUNT, REAL MONEY, NSE", text)
        for part in TSLA_PLAIN.split(" / "):
            self.assertIn("  " + part + "\n", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn('"order_type": "SL-M"', text)
        self.assertIn('"trigger_price": 358.32', text)
        self.assertIn("not a resting order", text)
        self.assertNotIn('"plan"', text)
        self.assertNotIn('"why"', text)
        self.assertIn("Allow once", text)

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "sure"))
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", text)
        self.assertFalse(os.path.exists(self.state))

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn("call the Kite MCP place_order tool", text)
        first = text[text.index("{"):text.index("}") + 1]
        self.assertEqual(json.loads(first), ENTRY_CALL)
        self.assertIn('"order_type": "SL-M"', text[text.index("}") + 1:])
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("APPROVED", err)

        code, text, _ = run(self.args("result", "--index", "1", "--status", "placed", "--broker-id",
                                      "251019000123456", "--filled-qty", "80", "--filled-price", "364.20",
                                      "--portfolio", self.pf, now="2026-10-19 10:01"))
        self.assertEqual(code, 0)
        st = self.state_doc()
        self.assertEqual([r["status"] for r in st["orders"]], ["approved", "placed", "filled"])
        appr, plc = st["orders"][0], st["orders"][1]
        self.assertEqual((appr["reply"], appr["kind"], appr["max_loss"], appr["date"], appr["broker"]),
                         ("yes", "entry", 468.8, TODAY, "kite"))
        self.assertEqual(appr["at"], "2026-10-19T10:00:00+05:30")
        self.assertEqual((plc["broker_order_id"], plc["max_loss"], plc["kind"]), ("251019000123456", 468.8, "entry"))
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 70864.0)
        self.assertEqual(pf["positions"][0]["shares"], 80)

        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: placed", text)
        code, text, _ = run(["log", "--state", self.state, "--now", NOW])
        self.assertIn("1 placed today", text)
        self.assertIn("max loss Rs 468.80", text)

        # trader-risk now counts it: a second TSLA buy today is a duplicate, and Rs 468.80 is used
        res = check.check([tsla()], {"budget": 100000}, state=st, now=check.parse_now("2026-10-19 10:15"))
        self.assertIn("already placed today", " ".join(res["results"][0]["reasons"]))
        self.assertEqual((res["today"]["entries_placed"], res["today"]["loss_at_risk"]), (1, 468.8))

    def test_flatten_by_the_close(self):
        self.run_risk()
        run(self.args("approve", "--index", "1", "--reply", "yes"))
        run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "abc",
                      "--filled-qty", "80", "--filled-price", "364.20", "--portfolio", self.pf))
        late = "2026-10-19 15:00"
        code, text, _ = run(["flatten", "--symbol", "TSLA", "--orders", self.orders, "--portfolio", self.pf,
                             "--plan", PLAN_PATH, "--config", self.cfg, "--now", late])
        self.assertEqual(code, 0)
        self.assertIn("SELL 80 shares of TSLA, market order, good for today (flat by 15:00 IST)", text)
        self.assertIn("replaced 1 earlier proposal", text)
        self.assertIn("cancel it FIRST", text)
        with open(self.orders) as fh:
            doc = json.load(fh)
        self.assertEqual(ticket.tool_input(doc["orders"][0]),
                         [{"variety": "regular", "exchange": "NSE", "tradingsymbol": "TSLA", "transaction_type": "SELL",
                           "quantity": 80, "product": "MIS", "order_type": "MARKET", "validity": "DAY"}])
        self.assertEqual(self.run_risk(now=late), 0)       # after the 14:30 entry cutoff: an exit still passes
        with open(self.risk) as fh:
            self.assertEqual(json.load(fh)["results"][0]["kind"], "exit")
        code, text, _ = run(self.args("show", now=late))
        self.assertEqual(code, 0)
        self.assertIn("READY", text)
        self.assertEqual(run(self.args("approve", "--index", "1", "--reply", "yes sell 80 TSLA", now=late))[0], 0)
        code, _, _ = run(self.args("result", "--index", "1", "--status", "placed", "--filled-qty", "80",
                                   "--filled-price", "366.10", "--portfolio", self.pf, now="2026-10-19 15:01"))
        self.assertEqual(code, 0)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual((pf["cash"], pf["positions"]), (100152.0, []))
        self.assertEqual(check.day_trades(self.state_doc(), TODAY), (1, ["2026-10-19 TSLA"]))
        code, _, err = run(["flatten", "--symbol", "TSLA", "--orders", self.orders, "--portfolio", self.pf,
                            "--now", late])
        self.assertEqual(code, 1)
        self.assertIn("nothing to flatten", err)

    def test_flatten_with_the_broker_qty(self):
        code, text, _ = run(["flatten", "--symbol", "tsla", "--qty", "80", "--orders", self.orders,
                             "--portfolio", self.none, "--plan", self.none, "--config", self.cfg, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertNotIn("Check it against", text)
        code, text, _ = run(["flatten", "--symbol", "TCS.BO", "--qty", "5", "--orders", self.orders,
                             "--portfolio", self.none, "--plan", self.none, "--config", self.cfg, "--now", NOW])
        with open(self.orders) as fh:
            self.assertEqual(json.load(fh)["orders"][0]["exchange"], "BSE")
        self.assertEqual(run(["flatten", "--symbol", "TSLA", "--qty", "0", "--orders", self.orders])[0], 1)

    def test_an_edited_order_is_not_ready(self):
        self.run_risk()
        with open(self.orders) as fh:
            doc = json.load(fh)
        doc["orders"][0]["qty"] = "9"
        with open(self.orders, "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("was not in the last risk check", text)

    def test_yesterdays_check_does_not_count(self):
        self.run_risk(now="2026-10-16 10:00")
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("not today", text)

    def test_blocked_orders_are_never_ready(self):
        self.assertEqual(self.run_risk(now="2026-10-19 09:25"), 1)
        code, text, _ = run(self.args("show", "--index", "1", now="2026-10-19 09:25"))
        self.assertIn("BLOCKED by trader-risk: window: no new entries before 09:30", text)
        code, _, _ = run(self.args("approve", "--index", "1", "--reply", "yes", now="2026-10-19 09:25"))
        self.assertEqual(code, 1)

    def test_result_needs_an_approval_and_decline_is_logged(self):
        self.run_risk()
        code, _, err = run(self.args("result", "--index", "1", "--status", "placed"))
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)
        code, text, _ = run(self.args("decline", "--index", "1", "--reply", "no thanks"))
        self.assertEqual(code, 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: declined", text)

    def test_paper_false_without_kite_is_still_paper(self):
        with open(self.cfg) as fh:
            c = json.load(fh)
        c["paper"] = False                                  # broker stays "paper": nothing is sent
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)
        self.run_risk()
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("PAPER (nothing goes to Kite)", text)

    def test_fill_sell_relieves_the_oldest_lot(self):
        pf = {"cash": 0, "positions": [{"ticker": "ITC", "shares": 3, "lots": [
            {"id": "ITC-1", "date": "2025-01-02", "shares": 2, "cost": 120.0},
            {"id": "ITC-2", "date": "2026-01-02", "shares": 1, "cost": 70.0}]}]}
        with open(self.pf, "w") as fh:
            json.dump(pf, fh)
        code, text, _ = run(["fill", "--symbol", "ITC", "--side", "sell", "--qty", "2.5", "--price", "90",
                             "--date", TODAY, "--portfolio", self.pf, "--config", self.cfg, "--state", self.state])
        self.assertEqual(code, 0)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 225.0)
        lots = pf["positions"][0]["lots"]
        self.assertEqual([l["id"] for l in lots], ["ITC-2"])
        self.assertEqual(lots[0]["shares"], 0.5)
        self.assertEqual(lots[0]["cost"], 35.0)
        self.assertEqual(self.state_doc()["orders"][-1]["status"], "filled")
        code, _, err = run(["fill", "--symbol", "ITC", "--side", "sell", "--qty", "5", "--price", "90",
                            "--portfolio", self.pf, "--config", self.cfg, "--state", self.state])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
