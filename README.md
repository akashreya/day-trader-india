# Day Trader India

9 Claude skills for intraday trading on NSE and BSE: scan the market, track the filings, time every entry and exit, replay every outcome, size every trade with Indian charges, and send it to Zerodha Kite only on your yes.

An India port of Jake Schincariol's
[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT).
Same method, rebuilt for the National Stock Exchange: India time (IST, no
daylight saving), NSE hours (9:15 to 3:30) and the 2026 NSE holiday list,
NSE symbols (`RELIANCE`, `M&M`, `BAJAJ-AUTO`) and BSE ones (`RELIANCE.BO`),
NSE's and BSE's lists of stocks, rupees, intraday (MIS) charges in every size and risk number, and
the closing auction F&O stocks have had since 3 August 2026.

Free, MIT, no signup, no API key. The tools are plain Python that read free
public data: Yahoo Finance charts and headlines (`SYMBOL.NS`, `SYMBOL.BO`),
NSE's and BSE's lists of stocks and their corporate announcements.

**Paper by default, and never without your yes.** Only `/trader-broker` can
lead to an order, on Zerodha Kite, and only when your config says live, the
risk check passed that exact order, you typed yes for it, and Claude's own
Allow once card asks you again.

## Install

Paste this into Claude:

```
https://github.com/akashreya/day-trader-india

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add akashreya/day-trader-india
/plugin install day-trader-india@day-trader-india
```

Claude Code namespaces plugin skills, so installed as a plugin they show up
as `/day-trader-india:trader-scanner` and so on. Copy the folders instead if
you want plain `/trader-scanner`:

```bash
git clone https://github.com/akashreya/day-trader-india.git
cp -r day-trader-india/trader-* ~/.claude/skills/
```

The tools need Python 3.8 or newer. Nothing to pip install.

## The nine

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans about 2,000 NSE charts (or BSE, or both) for setups: opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | News Monitor | Tracks NSE/BSE announcements (results, pledges, orders, resignations) and Yahoo headlines on every stock you watch. |
| `/trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Exit Planner | Sets your stop and your target before you enter, and your flat-by time. |
| `/trader-timemachine` | Time Machine | Replays the rest of the session 10,000 times from the stock's own bars, plus every past time the setup fired. |
| `/trader-budget` | Budget Manager | Sizes every position to your budget and your max loss per trade, charges included. |
| `/trader-risk` | Risk Manager | Checks every trade against your limits and stops anything over them. |
| `/trader-broker` | Order Executor | Sends approved orders to Zerodha Kite (paper by default), never without your yes. |
| `/trader-alerts` | Price Alerts | Rings on your stop, your target, the opening bell and 3:00 PM to be flat. |

Not ported (US-only in the original): the SEC earnings analyst and the
Congress trades tracker. See "Coming later" below.

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 3:00 PM                                          (while it is open)
news                                                                           (on a schedule)
```

1. **`/trader-scanner`** after 9:35 AM: which NSE charts closed above their
   15-minute opening range (9:15 to 9:30).
2. **`/trader-news`**: the stock's NSE/BSE filings and headlines. Results
   after the close, a pledge or a regulator's order changes the trade.
3. **`/trader-entry`** watches one of them bar by bar and calls the first
   5-minute close above the range high.
4. **`/trader-exit`** sets the stop (the range midpoint by default) and the
   target (2R by default) before anything is bought, and the flat-by time
   (3:00 PM: before your broker's MIS auto square-off).
5. **`/trader-timemachine`** replays the rest of the day 10,000 times from
   the stock's last 60 days of 5-minute bars, up to 3:15 PM, and re-runs the
   same rule on every one of those days. It tells you if it is a coin flip.
6. **`/trader-budget`** sizes it: with Rs 1,00,000 and a Rs 500 max loss, a
   5.86 risk a share is 85 shares before charges and 80 after the Rs 30.60 of
   brokerage, STT, exchange charges, stamp duty and GST at the stop. It also
   shows that a 1R target is about 0.88R once charges come off.
7. **`/trader-risk`** checks it against your limits: max loss (charges
   included), daily loss, trades a day, reward:risk, the entry window, size
   and cash. PASS or BLOCK, with the reason.
8. **`/trader-broker`** shows you the ticket in plain words. On the default
   paper config nothing is sent. On a live Kite config you type yes for that
   exact order, Claude calls Kite's `place_order` (MIS), and Claude's own
   "Allow once / Deny" card asks you one more time. Once the entry fills, the
   stop-loss goes in as its own SL-M sell, with its own card.
9. **`/trader-alerts`** rings on the stop, the target and at 3:00 PM to be
   flat. Kite has no intraday bracket, so the target is an alert: when it
   rings, cancel the stop-loss and sell.

## The tools

All standard-library Python. The data tools read public endpoints and are
polite about it.

```bash
python3 trader-scanner/scan.py universe                                # NSE EQUITY_L.csv -> trader/universe.txt
python3 trader-scanner/scan.py universe --exchange both                # plus BSE-only stocks, as SYMBOL.BO
python3 trader-scanner/scan.py daily                                   # before the open: daily setups
python3 trader-scanner/scan.py orb --at 10:00                          # opening-range breakouts so far
python3 trader-entry/entry.py check RELIANCE --setup orb               # waiting / triggered / expired
python3 trader-entry/entry.py watch RELIANCE --every 30                # bar by bar until it triggers
python3 trader-exit/exit.py plan --stop or-mid --target 1R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + the history
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, flat by 3:00
python3 trader-alerts/alerts.py check                                  # rings what hit, once
python3 trader-news/news.py --tickers RELIANCE TCS                     # filings, headlines, the move
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline. Yahoo's NSE data cannot be bundled, so the fixtures
are real US 5-minute bars (TSLA and 233 others, October 2026) retimed onto
NSE hours: a bar at 9:30 New York became a bar at 9:15 IST. The prices are
real; the symbols are only test data. The stock lists and the NSE/BSE
announcements are small hand-made samples in the exchanges' own formats,
marked "Test fixture, not a real filing".

**First live run.** Check the data on your own machine before you rely on it:

```bash
python3 trader-entry/entry.py check RELIANCE
python3 trader-timemachine/timemachine.py run --symbol RELIANCE --date <today> \
    --entry <price> --stop <stop> --target <target> --entry-time "10:00 AM"
```

## BSE

Add `.BO` to any symbol (`RELIANCE.BO`, or the scrip code `500325.BO`) and
every skill works on BSE: same hours, same holidays, same closing auction for
F&O stocks. The charges use BSE's transaction fee (0.00375% against NSE's
0.00297%) and the order says `"exchange": "BSE"` (Kite places it on BSE). The scanner builds a
BSE list with `--exchange bse` (groups A, B and X; trade-for-trade and SME
groups are out) or `--exchange both` (the NSE list plus companies only on
BSE). Most liquid stocks trade on both, with far more intraday volume on NSE,
so for the same company NSE is usually the better book.

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation and it cannot see the future.
SEBI's own study found that about 7 in 10 individual intraday traders in the
equity cash segment lost money. You can lose money. Decide for yourself, and
talk to a SEBI-registered adviser if you need advice.

**No order goes through until you say yes.** Only `/trader-broker` can lead
to an order, and only after `/trader-risk` passes that exact order and you
type yes for it in the chat. `"paper": true` is the default, and Kite has no
paper account, so on paper nothing is sent at all. Going live is your own
edit: `"paper": false` and `"broker": "kite"` in `trader/config.json`.

**Kite.** Zerodha's hosted Kite MCP server is read-only (it leaves out the
order tools), so placing orders means running Zerodha's open-source
kite-mcp-server yourself with your own Kite Connect app. Keys go in its
config file, never in the chat. Set `place_order`, `modify_order` and
`cancel_order` to "Needs approval" (Customize, Connectors, tool
permissions), never "Always allow". Retail algo trading through a broker's
API falls under SEBI's 2025 framework for retail algorithmic trading; read
Zerodha's rules first. This pack helps you place orders you approve one by
one; it is not an automated strategy.

**Charges are an estimate.** Brokerage (0.03% up to Rs 20 an order), STT
0.025% on the sell, NSE 0.00297% (BSE 0.00375%), SEBI 0.0001%, stamp duty 0.003% on the
buy, GST 18%. Set your broker's rates under `"charges"` in
`trader/config.json`. Your contract note is the truth.

**Square-off.** Brokers close MIS positions themselves from about 3:00 to
3:25 PM (it varies by broker and by stock) and charge a fee for it. Since
3 August 2026, F&O stocks stop continuous trading at 3:15 PM and close in an
auction; other stocks trade to 3:30. Hence flat by 3:00 by default.

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last 60 days of 5-minute bars. The future can do things those 60
days never did: results, a circuit limit, a headline.

**A stop is a plan, not a guarantee.** A gap or a circuit can fill a stop
well past its price, or not at all. The max loss shown is the loss at the
stop price.

**The data is free and unofficial.** Yahoo Finance's chart endpoint is not
an official API: it can lag, change or rate-limit you, and its NSE bars are
delayed. NSE's and BSE's sites block some scripted downloads; save the list
in a browser and pass `--offline` if they do.

**Holidays.** The 2026 NSE holiday list is built in. NSE publishes the 2027
list in December: add it to `NSE_HOLIDAYS` in each tool. Muhurat and other
special sessions are not in the calendar.

**Taxes.** Intraday gains are speculative business income in India. Nothing
here is tax advice.

## Coming later

- **Insider and bulk deals**, the Indian stand-in for the original's Congress
  trades tracker: promoter and director trades disclosed under SEBI's insider
  trading rules, and NSE/BSE bulk and block deals, alerting on the stocks you
  watch.
- **Earnings analyst**: quarter-by-quarter results from the exchange filings,
  once there is a clean free source to read them from.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-risk/        SKILL.md, check.py
trader-broker/      SKILL.md, ticket.py, claude_desktop_config.example.json
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
tests/              unittest suite + offline fixtures
```

MIT. Original pack by [Jake Schincariol](https://github.com/Jakeschincariol/day-trader-skill);
India port by [akashreya](https://github.com/akashreya).
