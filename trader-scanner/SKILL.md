---
name: trader-scanner
description: >-
  Chart Scanner for NSE and BSE stocks. Scans thousands of charts for setups:
  opening-range breakouts, flags, oversold bounces. Builds the list of NSE
  stocks you can trade intraday (the EQ series) from Zerodha's public
  instrument list (or NSE's EQUITY_L.csv),
  runs a pre-market scan of daily closes (20-day closing-high breakout, bull
  flag, reclaimed the 20-day average, oversold, oversold bounce) and an
  intraday opening-range breakout scan on 5-minute bars, then writes
  trader/watchlist.json for trader-entry. Free Yahoo data (SYMBOL.NS),
  bar by bar. Use when the user says "scan the market", "find me setups",
  "what is breaking out", "opening range breakouts", "scan for bull flags",
  "oversold stocks", "pre-market scan", "build my watchlist", "what should I
  look at today", or at the start of a trading day.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads thousands of
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. Most people who day trade lose money;
the scanner does not change that. It only saves you from flipping through
2,000 charts by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # NSE -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe --exchange both       # NSE plus BSE-only stocks (SYMBOL.BO)
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS,INFY  # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                            # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:00                 # cut the clock at 10:00 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

Flags: `--min-price 5` and `--min-volume` (daily 1,000,000, orb 0),
`--or-minutes 15`, `--max-confirm 200` (orb stage 2),
`--now "2026-10-19 10:00"` (IST time) to pin the clock, `--offline PATH`
to read saved Yahoo files, `--no-write`, `--show N`, `--json`. Exit code 0
when the scan found something, 1 when it found nothing or could not run (the
reason is one plain line).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-entry reads `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 14:30) |

## The universe

`universe` downloads Zerodha's public instrument list,
`api.kite.trade/instruments/NSE` (and `/BSE` for `--exchange bse` or `both`):
refreshed every morning, no login, meant for scripts, and it works where the
exchanges' own sites block scripts (both did in the live test on 2 Nov 2026).
It keeps the EQ series: a symbol with a two-letter series suffix (`-BE`,
`-BZ` trade-for-trade, `-SM` / `-ST` SME, `-SG` gold bonds, `-N0`.. bonds) is
out, and so are ETFs and iNAVs. About 2,350 NSE stocks. Zerodha's list has no
BSE groups, so with `--exchange bse` or `both` a trade-for-trade BSE stock
(groups T, XT, Z) can slip in: your broker refuses an intraday order on one,
and the volume floor drops most of them. `both` adds BSE stocks whose symbol
and name are not already on NSE (about 10,000, mostly thin).

`--source exchange` uses the exchanges' own lists instead (below), with BSE's
groups and ISIN matching. `--offline` reads either kind of file: `kite-NSE.csv`
/ `kite-BSE.csv`, or `EQUITY_L.csv` / `Equity.csv`.

**NSE's own list.** `universe --source exchange` downloads NSE's list of listed equities,
`nsearchives.nseindia.com/content/equities/EQUITY_L.csv`, and keeps a row when
its series is `EQ`: the rolling segment, the one you can trade intraday. Out:
`BE` and `BZ` (trade-for-trade, delivery only, no intraday), SME boards, and
anything that is not a plain NSE symbol (letters, digits, `&` and `-`, like
`M&M` and `BAJAJ-AUTO`). That leaves about 2,000 stocks. Symbols are kept the
NSE way (`RELIANCE`); the tools add `.NS` for Yahoo. A BSE code with `.BO`
(`500325.BO`) also works anywhere a symbol does.

NSE's site blocks some scripted clients. If the download fails, open the
URL in a browser, save the file, and run `scan.py universe --offline EQUITY_L.csv`.

**BSE.** `scan.py universe --exchange bse` reads BSE's list of scrips and keeps
groups A, B and X, the rolling segment you can trade intraday. T, XT, Z, ZP,
P and TS are trade-for-trade (delivery only, no intraday), and M, MT and MS
are the SME board: all out. Symbols are written as `SYMBOL.BO`, and every
tool reads them from Yahoo's BSE charts. `--exchange both` keeps the NSE list
and adds the companies listed only on BSE (matched by ISIN), so each company
appears once. BSE blocks some scripted clients too: on bseindia.com open
Markets > List of Scrips, pick Equity and Active, download the CSV and pass
`--offline Equity.csv`. Most liquid stocks trade on both exchanges, with far
more intraday volume on NSE; BSE-only stocks are mostly thin, and the price
and volume floors drop many of them.

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so about
2,000 symbols take about 100 requests, a minute or so with the polite pause
(0.3 s). Liquidity comes from the spark meta: last price at
least `--min-price` (Rs 50, a penny-stock floor) and last session's volume
at least `--min-volume` (500,000 shares). Run it
before the open or after the close: during the session the volume is the
day's so far, and today's daily bar is left out until 3:30 P.M.

The setups are computed from daily closes only (spark has no highs or lows),
so a closing-high breakout is not quite an intraday-high one:

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

Hits are listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

The opening range is the first `--or-minutes` (15) of the session: the 9:15,
9:20 and 9:25 five-minute bars. A hit is the first completed 5-minute bar
to CLOSE above the range high, at that bar's close time.

1. Stage 1, every symbol: spark closes of today's 5-minute bars, 20 a
   request. A chart goes on only if a completed bar after the range closed at
   or above the highest close of the range. That is a necessary condition
   (the range high is at least every range close), so no breakout is lost.
2. Stage 2, each candidate: the v8 chart with real highs and lows, one
   request each. Range high = the highest high of the range bars, range low =
   the lowest low. On a strong morning most charts are candidates, so stage 2
   checks at most `--max-confirm` (200) of them, the most traded first (price
   times volume so far), and prints PARTIAL with the count it skipped.
   `--max-confirm 0` checks them all.

For a fast answer, scan the daily watchlist or a list of names you trade
(`--watchlist`, `--symbols`). The whole universe means about 100 spark
requests and then up to 200 v8 charts: a few minutes.

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there; a missing bar means a halt or a thin stock. Null closes are dropped,
a bar off the 5-minute grid (the live tick, like 10:43:07) is dropped, and a
bar counts only once it is complete (start + 5 minutes). Before 9:35 AM, on a
weekend or holiday, after the close, or after `no_entries_after` (an expired
setup) it prints one plain line and writes nothing. F&O stocks stop
continuous trading at 3:15 for the closing auction (since 3 Aug 2026), so
their last bars of the day are not like the others.

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag. Bars are
  5-minute bars, bar by bar, never tick by tick. query2 first, query1 on a 429
  or 5xx, one retry after a 5-second wait on a 429.
- Partial results are said as partial: "Fetched 1,950 of 2,040 charts (90
  failed or had no data)". Never round a partial scan up to "the whole market".
- NSE equity holidays for 2026 are built in (NSE circular, Dec 2025). Add the
  2027 list to each tool's `NSE_HOLIDAYS` when NSE publishes it. Muhurat and
  special weekend sessions are not in the calendar.

## Steps

1. Once a week or so: `scan.py universe`.
2. Before the open: `scan.py daily`. Tell the user the counts (fetched,
   liquid, scanned, hits) and the top few by setup.
3. After 9:35 AM IST (10:00 is the classic): `scan.py orb`. Tell the user how
   many usable charts broke their range and when, and that a later hit is
   closer to the price now.
4. The user picks one chart. Hand it on: `/trader-news SYMBOL` (the filings
   and headlines moving it), then `/trader-entry SYMBOL` (the entry bar by
   bar). Never pick for them.

## Example: the test fixture

The offline tests use real Yahoo 5-minute charts of 234 US stocks from Monday
Oct 19 2026, retimed onto NSE hours (9:30 New York became 9:15 IST), so the
scan can be checked bar for bar without a network:

```
python3 scan.py orb --offline wall5m-2026-10-19.json.gz --now "2026-10-19 10:00" --min-price 0
Fetched 233 of 234 charts (1 failed or had no data); 231 usable; 95 candidates, 95 confirmed with real highs and lows.
42 of 231 charts closed above their opening-range high by 10:00 AM:
  ...
  10:00 AM  TSLA    Rs 364.18  range 354.47 to 362.18  +0.55% over
```

TSLA's range is the 9:15 to 9:25 bars, high 362.18, low 354.47; the 9:55 bar
closed at 364.18, 0.55 % over the high, at 10:00 A.M. On real NSE data the
same command without `--offline` reads Yahoo's `.NS` charts.

## Rules

- Say what was scanned: how many symbols, how many charts came back, how many
  were usable, and the time of the data.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper by default (`"paper": true`): nothing goes to a broker. Real orders need `"paper": false` and
  `"broker": "kite"` in the user's own config, set by the user, and a Kite MCP server the user runs
  with their own Kite Connect keys (in its config file, never in the chat).
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because Kite's order tools are set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- NSE and BSE cash equity, intraday (MIS), longs only. No F&O, no short selling, no leverage beyond what
  the user's broker gives MIS on its own terms, and none of that is sized here.
- Indian intraday costs (brokerage, STT, exchange charges, SEBI fee, stamp duty, GST) are counted in
  the sizing. The contract note is the truth; the config's rates are an estimate.
- Be flat before the broker's MIS auto square-off (it charges a fee and sells at whatever price).
- Day trading loses most people money: SEBI's own study found about 7 in 10 individual intraday
  traders in the cash segment lost money. Small size, a stop on every trade, flat every day.
- Yahoo's data is free, unofficial and can lag. Check anything that matters against the broker.
