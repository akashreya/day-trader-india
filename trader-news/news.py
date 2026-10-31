#!/usr/bin/env python3
"""News monitor for trader-news (NSE and BSE). Standard library only.

Watches headlines and exchange announcements for the stocks you watch or hold
and prints only what is new since the last check, newest first, with how far
each stock has moved today and a flag on anything that touches your stocks.

    python3 news.py                                  # watchlist + plan + portfolio symbols
    python3 news.py --tickers RELIANCE TCS INFY
    python3 news.py --tickers RELIANCE --all --hours 72  # everything in 3 days, seen or not
    python3 news.py --no-filings                     # headlines only
    python3 news.py --no-moves                       # skip the price line per symbol

Your symbols, when --tickers is not given: every hit in trader/watchlist.json
(trader-scanner), the symbol in trader/plan.json (trader-exit) and the
positions in trader/portfolio.json. NSE symbols as NSE writes them (RELIANCE,
M&M); BSE ones with .BO (RELIANCE.BO).

Sources, one request each per symbol:
  - Yahoo Finance headline RSS (Indian edition):
    https://feeds.finance.yahoo.com/rss/2.0/headline?s=RELIANCE.NS&region=IN&lang=en-IN
  - NSE corporate announcements (results, board meetings, dividends, orders,
    pledges, rating changes, resignations), what NSE's Corporate Filings page shows:
    https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE
    NSE wants a browser session: the tool first opens www.nseindia.com for its
    cookies. NSE blocks some scripted clients; then the tool says so and the
    headlines still run (or save the JSON from a browser and use --offline).
  - BSE corporate announcements, for a .BO symbol, by BSE scrip code: give the
    code as the symbol (500325.BO) or map it in trader/config.json
    ("bse_codes": {"RELIANCE.BO": "500325"}).
  - The move: Yahoo Finance's chart endpoint (unofficial, can lag), the last
    price against yesterday's close.

Times print in India time (IST). State: trader/state/news.json remembers what
you have seen (30 days), so an item shows once. Offline: --offline DIR reads
yahoo-<SYMBOL>.xml, chart-<SYMBOL>.json, nse-ann-<SYMBOL>.json and
bse-ann-<CODE>.json from DIR. The tests use it.

Headlines are leads, not facts: open the filing before acting, and treat
nothing here as advice.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import http.cookiejar
import urllib.parse
import xml.etree.ElementTree as XML

YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN"
CHART = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
NSE_HOME = "https://www.nseindia.com/"
NSE_ANN = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=%s"
BSE_ANN = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1"
           "&strPrevDate=%s&strScrip=%s&strSearch=P&strToDate=%s&strType=C&subcategory=-1")
BSE_ATTACH = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/%s"
BROWSER_UA = "Mozilla/5.0 (compatible; day-trader-india/1.0; +https://github.com/akashreya/day-trader-india)"
KEEP_DAYS = 30
MOVE_PCT = 3.0  # a stock this far from yesterday's close is flagged as moving

# An exchange announcement is flagged "!" when its subject says one of these: the
# filings that move Indian stocks on the day.
IMPORTANT = [
    ("results", r"financial result|\bresults?\b|outcome of board meeting"),
    ("pledge", r"\bpledge|encumbrance"),
    ("deal", r"acquisition|amalgamation|merger|scheme of arrangement|demerger|takeover|open offer"),
    ("people", r"resignation|cessation|appointment of (?:managing director|ceo|cfo)|change in (?:ceo|cfo|md)"),
    ("rating", r"credit rating"),
    ("capital", r"buy ?back|bonus|split|sub-division|rights issue|preferential|qip|fund raising"),
    ("risk", r"default|insolvency|ibc|nclt|fraud|forensic|search and seizure|raid|penalty|show cause"),
    ("orders", r"award of order|bagging|receipt of order|contract|letter of intent"),
]
KEYWORDS = [
    ("earnings", r"\bearnings\b|\bresults?\b|\bQ[1-4]\b|\bprofit\b|\bguidance\b|\bEBITDA\b"),
    ("analyst", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|target price|price target|\bbuy rating\b|\bsell rating\b"),
    ("legal", r"\blawsuit\b|\bprobe\b|\binvestigation\b|\bSEBI order\b|\bNCLT\b|\bcourt\b|\bpenalty\b"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bstake\b|\btakeover\b|\bdeal\b"),
    ("capital", r"\bdividend\b|\bbuy ?back\b|\bbonus\b|\bsplit\b|\bQIP\b|\brights issue\b|\bOFS\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bMD\b|\bresign|\bsteps down\b|\bappoint"),
    ("risk", r"\bpledge|\bdefault\b|\binsolvency\b|\bfraud\b|\braid\b|\bdowngrade to\b"),
    ("halt", r"\bsuspen(?:d|sion)\b|\bcircuit\b|\bASM\b|\bGSM\b"),
    ("regulatory", r"\bSEBI\b|\bRBI\b|\bUSFDA\b|\bCDSCO\b|\bapproval\b|\blicen[cs]e\b"),
    ("macro", r"\bRBI policy\b|\brepo rate\b|\bGDP\b|\binflation\b|\bCPI\b|\bFII\b|\bFPI\b|\bbudget\b|\btariffs?\b"),
]


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

IST_DELTA = _dt.timedelta(hours=5, minutes=30)   # India Standard Time, no daylight saving
IST_TZ = _dt.timezone(IST_DELTA)


def to_ist(utc):
    """Aware or naive UTC -> naive IST wall-clock time."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc)
    return utc.replace(tzinfo=None) + IST_DELTA


# ---------------------------------------------------------------- inputs

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{ticker: name or None}: the scanner's hits, the planned trade and your holdings."""
    out = {}
    wl = load_json(watchlist) or {}
    for h in wl.get("hits", []):
        sym = h.get("symbol") or h.get("ticker")
        if sym:
            out[nse_symbol(sym)] = h.get("name")
    pl = load_json(plan) or {}
    if pl.get("symbol"):
        out.setdefault(nse_symbol(pl["symbol"]), pl.get("name"))
    pf = load_json(portfolio) or {}
    for p in pf.get("positions", []):
        sym = p.get("ticker") or p.get("symbol")
        if sym:
            out[nse_symbol(sym)] = p.get("name") or out.get(nse_symbol(sym))
    return out


def bse_codes(config="trader/config.json"):
    cfg = load_json(config) or {}
    return {nse_symbol(k): str(v) for k, v in (cfg.get("bse_codes") or {}).items()}


# ---------------------------------------------------------------- fetching

class Fetcher(object):
    def __init__(self, offline=None, pause=0.15):
        self.offline = offline
        self.pause = pause
        self._last = 0.0
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._nse_ready = False

    def _open(self, url, headers):
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        req = urllib.request.Request(url, headers=headers)
        try:
            with self._opener.open(req, timeout=30) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("HTTP %s for %s" % (exc.code, url.split("?")[0]))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach %s: %s" % (url.split("/")[2], exc.reason))

    def get(self, url, name, site=None):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        headers = {"User-Agent": BROWSER_UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
        if site == "nse":
            if not self._nse_ready:          # NSE's API answers only inside a session from its home page
                self._open(NSE_HOME, dict(headers, Accept="text/html"))
                self._nse_ready = True
            headers["Referer"] = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
            headers["Accept"] = "application/json"
        elif site == "bse":
            headers["Referer"] = "https://www.bseindia.com/"
            headers["Origin"] = "https://www.bseindia.com"
            headers["Accept"] = "application/json"
        return self._open(url, headers)


def nse_symbol(sym):
    """'reliance', 'RELIANCE.NS' -> 'RELIANCE'; a BSE symbol keeps its suffix: 'RELIANCE.BO'."""
    s = str(sym or "").strip().upper()
    return s[:-3] if s.endswith(".NS") else s


def yahoo_symbol(sym):
    """RELIANCE -> RELIANCE.NS; .BO stays on BSE. URL-quoted (M&M -> M%26M.NS)."""
    s = nse_symbol(sym)
    return urllib.parse.quote(s if s.endswith(".BO") else s + ".NS", safe=".")


# ---------------------------------------------------------------- parsing

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_time(value):
    """RFC 822 (RSS) or ISO 8601 (Atom) -> aware UTC datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def parse_rss(data, ticker):
    """Yahoo headline RSS -> items."""
    try:
        root = XML.fromstring(data)
    except XML.ParseError as exc:
        raise NewsError("RSS for %s is not valid XML: %s" % (ticker, exc))
    out = []
    for it in root.iter("item"):
        title = _text(it, "title")
        link = _text(it, "link")
        guid = _text(it, "guid") or link
        out.append({"id": "rss:" + guid, "source": "Yahoo Finance", "kind": "headline",
                    "ticker": ticker, "title": title, "summary": _text(it, "description"),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def _ist_time(text, fmts):
    """An exchange's IST time text -> aware UTC datetime, or None."""
    text = (text or "").strip()
    for f in fmts:
        try:
            return _dt.datetime.strptime(text, f).replace(tzinfo=IST_TZ).astimezone(_dt.timezone.utc)
        except ValueError:
            continue
    return None


def _important(subject):
    hits = [label for label, rx in IMPORTANT if re.search(rx, subject or "", re.I)]
    return hits


def parse_nse_ann(data, ticker):
    """NSE corporate-announcements JSON (a list, or {"data": [...]}) -> items."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except ValueError:
        raise NewsError("NSE answered something that is not JSON for %s (it may have blocked the request)" % ticker)
    rows = doc.get("data", []) if isinstance(doc, dict) else doc
    out = []
    for r in rows or []:
        subject = str(r.get("desc") or "").strip()
        text = " ".join(str(r.get("attchmntText") or "").split())
        when = (_ist_time(r.get("sort_date"), ["%Y-%m-%d %H:%M:%S"])
                or _ist_time(r.get("an_dt"), ["%d-%b-%Y %H:%M:%S"]))
        sym = str(r.get("symbol") or ticker).upper()
        rid = str(r.get("seq_id") or hashlib.sha1(("%s|%s|%s" % (sym, subject, r.get("an_dt"))).encode()).hexdigest())
        hits = _important(subject + " " + text[:200])
        out.append({"id": "nse:" + rid, "source": "NSE filing", "kind": "filing", "form": subject,
                    "ticker": ticker, "title": "%s: %s" % (r.get("sm_name") or sym, subject or "announcement"),
                    "summary": text[:400], "important": bool(hits), "categories": hits,
                    "link": str(r.get("attchmntFile") or ""), "time": when})
    return out


def parse_bse_ann(data, ticker):
    """BSE AnnSubCategoryGetData JSON ({"Table": [...]}) -> items."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except ValueError:
        raise NewsError("BSE answered something that is not JSON for %s (it may have blocked the request)" % ticker)
    rows = doc.get("Table", []) if isinstance(doc, dict) else doc
    out = []
    for r in rows or []:
        subject = " ".join(str(r.get("NEWSSUB") or r.get("HEADLINE") or "").split())
        cat = str(r.get("CATEGORYNAME") or "").strip()
        when = _ist_time(str(r.get("NEWS_DT") or r.get("DissemDT") or "")[:19], ["%Y-%m-%dT%H:%M:%S"])
        att = str(r.get("ATTACHMENTNAME") or "").strip()
        hits = _important("%s %s" % (cat, subject))
        out.append({"id": "bse:%s" % (r.get("NEWSID") or hashlib.sha1(subject.encode()).hexdigest()),
                    "source": "BSE filing", "kind": "filing", "form": cat, "ticker": ticker,
                    "title": "%s: %s" % (r.get("SLONGNAME") or ticker, subject or cat or "announcement"),
                    "summary": " ".join(str(r.get("HEADLINE") or "").split())[:400], "important": bool(hits),
                    "categories": hits, "link": (BSE_ATTACH % att) if att else "", "time": when})
    return out


def parse_chart(data, ticker):
    """Yahoo chart JSON -> {"ticker", "price", "prev_close", "pct", "time"} or raise."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        meta = doc["chart"]["result"][0]["meta"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise NewsError("chart for %s is not usable" % ticker)
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        raise NewsError("chart for %s has no price" % ticker)
    when = meta.get("regularMarketTime")
    return {"ticker": ticker, "price": round(float(price), 2), "prev_close": round(float(prev), 2),
            "pct": round((float(price) / float(prev) - 1) * 100, 2),
            "time": _dt.datetime.fromtimestamp(when, _dt.timezone.utc) if when else None}


def collect_moves(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        name = "chart-%s.json" % t
        try:
            try:
                data = fetcher.get(CHART % ("query2", yahoo_symbol(t)), name)
            except NewsError as exc:
                if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
                    raise
                data = fetcher.get(CHART % ("query1", yahoo_symbol(t)), name)
            out.append(parse_chart(data, t))
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("price for %s: %s" % (t, exc))
    return out


def mention_patterns(watch):
    pats = {}
    for t, name in watch.items():
        base = t[:-3] if t.endswith(".BO") else t
        alts = [r"\(%s\)" % re.escape(base), r"\b(?:NSE|BSE)\s*:\s*%s\b" % re.escape(base)]
        if name and len(name) >= 4:
            alts.append(r"\b%s\b" % re.escape(name).replace(r"\ ", r"[\s-]"))
        pats[t] = re.compile("|".join(alts))
    return pats


def tag(items, watch):
    """Which of your tickers each item touches, and why it matters."""
    pats = mention_patterns(watch)
    for it in items:
        hay = "%s %s" % (it["title"], it.get("summary") or "")
        touches = {it["ticker"]} if it["ticker"] in watch else set()
        for t, rx in pats.items():
            if rx.search(hay):
                touches.add(t)
        it["touches"] = sorted(touches)
        it["tags"] = [label for label, rx in KEYWORDS if re.search(rx, hay, re.I)]
        for c in it.get("categories", []):
            if c not in it["tags"]:
                it["tags"].append(c)
    return items


def dedupe(items):
    """One item per story: same id, or same link, or same title the same day."""
    seen, out = {}, []
    for it in items:
        keys = [it["id"], it["link"],
                "%s|%s" % (re.sub(r"\W+", " ", it["title"].lower()).strip(),
                           it["time"].date() if it["time"] else "")]
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit is not None:
            for t in it.get("touches", []):
                if t not in hit["touches"]:
                    hit["touches"].append(t)
            hit["touches"].sort()
            continue
        for k in keys:
            if k:
                seen[k] = it
        out.append(it)
    return out


def fingerprint(it):
    return hashlib.sha1(it["id"].encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- the check

def collect(fetcher, watch, state, filings=True, codes=None, now=None, errors=None):
    errors = [] if errors is None else errors
    codes = codes or {}
    now = now or _dt.datetime.now(_dt.timezone.utc)
    items = []
    for t in sorted(watch):
        try:
            items += parse_rss(fetcher.get(YAHOO % yahoo_symbol(t), "yahoo-%s.xml" % t), t)
        except NewsError as exc:
            errors.append("headlines for %s: %s" % (t, exc))
    if not filings:
        return items
    for t in sorted(watch):
        if t.endswith(".BO"):
            code = codes.get(t) or (t[:-3] if t[:-3].isdigit() else None)
            if not code:
                errors.append("BSE filings for %s: no scrip code (use %s or add \"bse_codes\" in "
                              "trader/config.json)" % (t, "500325.BO"))
                continue
            day = to_ist(now)
            url = BSE_ANN % ((day - _dt.timedelta(days=7)).strftime("%Y%m%d"), code, day.strftime("%Y%m%d"))
            try:
                items += parse_bse_ann(fetcher.get(url, "bse-ann-%s.json" % code, site="bse"), t)
            except NewsError as exc:
                errors.append("BSE filings for %s: %s" % (t, exc))
        else:
            try:
                data = fetcher.get(NSE_ANN % urllib.parse.quote(t), "nse-ann-%s.json" % t, site="nse")
                items += parse_nse_ann(data, t)
            except NewsError as exc:
                errors.append("NSE filings for %s: %s" % (t, exc))
    return items


def select(items, state, now, hours=48, show_all=False):
    """Items within the window; only unseen ones unless show_all."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)  # a pinned --now: nothing from after it
    out = []
    for it in items:
        if it["time"] is not None and (it["time"] < cutoff or it["time"] > ahead):
            continue
        fp = fingerprint(it)
        it["new"] = fp not in seen
        if it["new"] or show_all:
            out.append(it)
    out.sort(key=lambda i: (i["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for it in items:
        seen.setdefault(fingerprint(it), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    state["last_check"] = stamp


def render_moves(moves, move_pct=MOVE_PCT):
    out = []
    for m in moves:
        flag = "MOVING" if abs(m["pct"]) >= move_pct else ""
        when = (" at %s IST" % to_ist(m["time"]).strftime("%H:%M")) if m.get("time") else ""
        out.append("%-10s %s %+.2f%% vs yesterday's close %s%s  %s" % (
            m["ticker"], "{:,.2f}".format(m["price"]), m["pct"], "{:,.2f}".format(m["prev_close"]),
            when, flag))
    return out


def render(items, errors, now, moves=None, move_pct=MOVE_PCT):
    out = render_moves(moves or [], move_pct)
    if out:
        out.append("")
    if not items:
        out.append("Nothing new.")
    for it in items:
        when = to_ist(it["time"]).strftime("%Y-%m-%d %H:%M IST") if it["time"] else "time unknown"
        mark = "!" if it.get("important") else " "
        who = ",".join(it["touches"]) or it["ticker"]
        out.append("%s %s  %-11s %-13s %s" % (mark, when, who, it["source"], it["title"]))
        extra = []
        if it["tags"]:
            extra.append("tags: " + ", ".join(it["tags"]))
        extra.append(it["link"])
        out.append("      " + "  ".join(extra))
    for e in errors:
        out.append("note: %s" % e)
    out.append("Checked %s. Headlines are leads, not facts; open the story before acting. "
               "Not financial advice." % to_ist(now).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(out) + "\n"


def _json_ready(items):
    out = []
    for it in items:
        d = dict(it)
        d["time"] = it["time"].isoformat() if it["time"] else None
        out.append(d)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*", help="default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore items older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--no-filings", action="store_true", help="headlines only (no NSE/BSE announcements)")
    ap.add_argument("--no-moves", action="store_true", help="skip the price line per ticker")
    ap.add_argument("--move-pct", type=float, default=MOVE_PCT, help="flag a move this big (percent)")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--now", help="ISO time, for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.tickers:
        watch = {nse_symbol(t): None for t in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({t: known[t] for t in watch if known.get(t)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
    if not watch:
        print("news: no symbols. Pass --tickers, or run /trader-scanner first (it writes "
              "trader/watchlist.json).", file=sys.stderr)
        return 2
    now = parse_time(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    state = load_json(args.state) or {}
    errors = []
    fetcher = Fetcher(offline=args.offline)
    items = collect(fetcher, watch, state, filings=not args.no_filings, codes=bse_codes(args.config),
                    now=now, errors=errors)
    items = dedupe(tag(items, watch))
    shown = select(items, state, now, hours=args.hours, show_all=args.all)
    moves = [] if args.no_moves else collect_moves(fetcher, watch, errors)
    if args.json:
        mv = [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                   moving=abs(m["pct"]) >= args.move_pct) for m in moves]
        print(json.dumps({"checked": now.isoformat(), "moves": mv, "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now, moves, args.move_pct))
    if not args.dry_run:
        remember(items, state, now)
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(i["new"] for i in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
