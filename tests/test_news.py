import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

news = load("trader-news", "news")

NDIR = os.path.join(FIX, "trader-news")
UTC = datetime.timezone.utc
# yahoo-TSLA.xml is a real Yahoo headline feed (Oct 19 2026). The NSE and BSE files are
# hand-made samples in the exchanges' JSON shapes ("Test fixture, not a real filing").
NOW = "2026-10-19T14:00:00Z"          # 19:30 IST, after the board meeting outcome


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = news.main(argv)
    return code, out.getvalue(), err.getvalue()


def read(name):
    with open(os.path.join(NDIR, name), "rb") as fh:
        return fh.read()


class Symbols(unittest.TestCase):
    def test_yahoo_symbols(self):
        self.assertEqual(news.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(news.yahoo_symbol("M&M"), "M%26M.NS")
        self.assertEqual(news.yahoo_symbol("TCS.BO"), "TCS.BO")
        self.assertEqual(news.nse_symbol("RELIANCE.NS"), "RELIANCE")
        self.assertIn("s=RELIANCE.NS&region=IN", news.YAHOO % news.yahoo_symbol("RELIANCE"))


class Parsing(unittest.TestCase):
    def test_the_real_yahoo_feed(self):
        items = news.parse_rss(read("yahoo-TSLA.xml"), "TSLA")
        self.assertEqual(len(items), 18)
        first = items[0]
        self.assertEqual(first["time"], datetime.datetime(2026, 10, 19, 14, 32, 17, tzinfo=UTC))
        self.assertEqual(news.to_ist(first["time"]), datetime.datetime(2026, 10, 19, 20, 2, 17))

    def test_nse_announcements(self):
        items = news.parse_nse_ann(read("nse-ann-RELIANCE.json"), "RELIANCE")
        self.assertEqual(len(items), 3)
        board = items[0]
        self.assertEqual(board["title"], "Reliance Industries Limited: Outcome of Board Meeting")
        self.assertEqual(board["time"], datetime.datetime(2026, 10, 19, 13, 0, 12, tzinfo=UTC))   # 18:30:12 IST
        self.assertTrue(board["important"])
        self.assertIn("results", board["categories"])
        self.assertFalse(items[1]["important"])                                  # a routine update
        self.assertIn("pledge", items[2]["categories"])
        self.assertEqual(news.parse_nse_ann(json.dumps({"data": json.loads(read("nse-ann-RELIANCE.json"))}),
                                            "RELIANCE")[0]["id"], "nse:900000001")
        with self.assertRaises(news.NewsError):
            news.parse_nse_ann(b"<html>Access Denied</html>", "RELIANCE")

    def test_bse_announcements(self):
        items = news.parse_bse_ann(read("bse-ann-500325.json"), "500325.BO")
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["time"], datetime.datetime(2026, 10, 19, 5, 35, tzinfo=UTC))           # 11:05 IST
        self.assertEqual(it["link"], "https://www.bseindia.com/xml-data/corpfiling/AttachLive/sample-0001.pdf")
        self.assertIn("orders", it["categories"])
        self.assertTrue(it["important"])

    def test_the_move(self):
        m = news.parse_chart(read("chart-TSLA.json"), "TSLA")
        self.assertEqual((m["price"], m["prev_close"], m["pct"]), (366.48, 354.72, 3.31))


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "news.json")
        self.cfg = os.path.join(self.d, "config.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_news(self, *extra):
        return run(["--offline", NDIR, "--state", self.state, "--config", self.cfg, "--now", NOW,
                    "--portfolio", os.path.join(self.d, "none"), "--watchlist", os.path.join(self.d, "none"),
                    "--plan", os.path.join(self.d, "none")] + list(extra))

    def test_nse_filings_and_the_move(self):
        code, text, _ = self.run_news("--tickers", "RELIANCE")
        self.assertEqual(code, 0)
        self.assertIn("RELIANCE   366.48 +3.31% vs yesterday's close 354.72", text)
        self.assertIn("MOVING", text)
        self.assertIn("! 2026-10-19 18:30 IST  RELIANCE    NSE filing    Reliance Industries Limited: Outcome of "
                      "Board Meeting", text)
        self.assertIn("  2026-10-19 09:10 IST  RELIANCE    NSE filing", text)
        self.assertNotIn("creation of pledge", text)          # Oct 10: outside the 48-hour window
        self.assertIn("headlines for RELIANCE: offline: no file", text)
        self.assertIn("Not financial advice", text)
        code, text, _ = self.run_news("--tickers", "RELIANCE")
        self.assertEqual(code, 1)                               # seen: shown once
        self.assertIn("Nothing new.", text)
        code, text, _ = self.run_news("--tickers", "RELIANCE", "--all", "--hours", "240")
        self.assertIn("creation of pledge", text)

    def test_bse_by_code_or_by_the_config(self):
        code, text, _ = self.run_news("--tickers", "500325.BO", "--no-moves")
        self.assertEqual(code, 0)
        self.assertIn("BSE filing    Reliance Industries Ltd: Reliance Industries Ltd - 500325 - Announcement", text)
        code, text, _ = self.run_news("--tickers", "RELIANCE.BO", "--no-moves", "--dry-run")
        self.assertIn("no scrip code", text)
        with open(self.cfg, "w") as fh:
            json.dump({"bse_codes": {"RELIANCE.BO": "500325"}}, fh)
        code, text, _ = self.run_news("--tickers", "RELIANCE.BO", "--no-moves", "--all")
        self.assertIn("BSE filing", text)

    def test_headlines_only_and_json(self):
        code, text, _ = self.run_news("--tickers", "TSLA", "--no-filings", "--hours", "24", "--json")
        doc = json.loads(text)
        now = datetime.datetime(2026, 10, 19, 14, tzinfo=UTC)   # the last 24 hours, nothing after the pinned clock
        want = [i for i in news.parse_rss(read("yahoo-TSLA.xml"), "TSLA")
                if now - datetime.timedelta(hours=24) <= i["time"] <= now + datetime.timedelta(minutes=10)]
        self.assertEqual(len(doc["items"]), len(want))
        self.assertEqual(len(want), 16)
        self.assertTrue(all(i["source"] == "Yahoo Finance" for i in doc["items"]))
        self.assertEqual(doc["moves"][0]["moving"], True)

    def test_no_symbols(self):
        code, _, err = self.run_news()
        self.assertEqual(code, 2)
        self.assertIn("no symbols", err)


if __name__ == "__main__":
    unittest.main()
