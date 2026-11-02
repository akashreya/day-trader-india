---
name: trader-news
description: >-
  News Monitor for NSE and BSE stocks. Tracks the headlines and the exchange
  filings on every stock you watch and flags what moves it: Yahoo Finance's
  Indian headline feed per symbol, each company's NSE corporate announcements
  (results, board meetings, dividends, bonus and splits, order wins, pledges,
  rating changes, resignations, regulatory actions), BSE announcements for a
  .BO symbol, and how far each stock is from yesterday's close. Shows only
  what is new since the last check, newest first, in India time, tags each
  item and marks the filings that move stocks with "!". Use when the user says
  "any news on RELIANCE", "why is this moving", "what's the news on my
  watchlist", "morning briefing", "pre-market news", "monitor the news", "did
  anything break", "check the announcements", "any board meeting", or after
  /trader-scanner finds setups.
argument-hint: "[symbols]"
---

# trader-news

A chart can look perfect and still be about to gap on results, a pledge
invocation or a regulator's order. In India the exchange filings carry those
first: every listed company must disclose material events to NSE and BSE
under SEBI's listing rules. Before a setup becomes a trade, this skill reads
the filings and the headlines for every stock on the watchlist and tells you
only what is new. It also prints how far each stock has moved today, so a
filing and a move sit side by side.

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                              # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS --hours 12
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers 500325.BO          # BSE filings by scrip code
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-filings --json          # headlines only
```

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-scanner) |
| `trader/plan.json` | the trade you are planning (trader-exit) |
| `trader/portfolio.json` | what you hold (trader-broker records fills there) |
| Yahoo Finance headline RSS | `feeds.finance.yahoo.com/rss/2.0/headline?s=RELIANCE.NS&region=IN&lang=en-IN` |
| NSE corporate announcements | `www.nseindia.com/api/corporate-announcements?index=equities&symbol=RELIANCE`, inside a session from NSE's home page |
| BSE corporate announcements | for a `.BO` symbol, by scrip code: `500325.BO`, or `"bse_codes": {"RELIANCE.BO": "500325"}` in `trader/config.json` |
| Yahoo Finance chart endpoint | the last price against yesterday's close (unofficial, can lag) |
| `trader/state/news.json` | what has been shown (kept 30 days) |

NSE and BSE block scripted clients (in the live test on 2 Nov 2026 NSE's
API timed out and BSE's answered 403, every time). When they do, the tool
says so in a note, gives up on that site for the rest of the run, and the
headlines still run. The filings are then **unchecked**, and that matters:
results or a board meeting today is the biggest gap risk there is.

So when the notes say a filings site could not be reached:

1. If a browser tool is available (Claude in Chrome, or the built-in
   browser), open the stock's announcements page in it and read the latest
   filings yourself:
   `https://www.nseindia.com/get-quotes/equity?symbol=SYMBOL` (the Corporate
   Announcements section), or for a BSE stock
   `https://www.bseindia.com/stock-share-price/x/y/SCRIPCODE/corp-announcements/`.
   Reading a page in the user's browser is fine; do not script around the
   block (no fake browser headers, no proxies).
2. If no browser tool is available, tell the user in one line that the
   filings are unchecked and name the stocks, before any trade on them.

## The rules

- **Filings beat headlines.** A filing is what the company told the exchange.
  If a headline and a filing disagree, the filing wins. Open the PDF before
  telling the user what it says, and link it.
- **Headlines are leads, not facts.** Never summarise a story you could not
  read: say so.
- **Say what it touches.** Every item lists the symbols it touches and its
  tags: earnings, analyst, legal, deal, capital, people, risk, halt,
  regulatory, macro. Filings marked `!` are the kinds that move Indian stocks
  on the day: results and board-meeting outcomes, pledges, mergers and open
  offers, resignations of the MD, CEO or CFO, rating changes, buybacks,
  bonuses, splits and fund raising, defaults, NCLT, searches and penalties,
  and order wins.
- **MOVING** marks a stock 3 % or more from yesterday's close (`--move-pct`).
  A move with no filing is worth saying out loud too, and so is a stock
  near its circuit limit.
- **No predictions.** Report what was filed or published and how far the
  price is from yesterday's close. Never say what the stock will do next.

## Steps

1. Run the check: `python3 "${CLAUDE_SKILL_DIR}/news.py"`. Exit code 1 means
   nothing new. `--all` shows items already seen, `--json` gives everything
   machine readable, `--dry-run` leaves the state alone.
2. Read the items that matter first: every `!` filing, anything tagged
   earnings, halt, legal, regulatory or risk, and every MOVING symbol.
3. Write a short brief, per symbol: what happened, the source and link, the
   move, and one line on why it matters to the setup (for example "the board
   meets on results today after the close: an overnight gap can jump past any
   stop, so the trade is in and out today").
4. If a filing changes the picture, say so before `/trader-entry` and
   `/trader-exit`: results inside the trade, a pledge, a surveillance (ASM/GSM)
   move. Never act on a headline alone.

During the session: `/loop 15m /trader-news`, or a scheduled task each
morning before the open.

## Example: the test fixtures

The offline tests use a real Yahoo headline feed (TSLA, Oct 19 2026) and
hand-made NSE and BSE answers in the exchanges' JSON shapes. With the clock
at 7:30 PM IST on Oct 19:

```
RELIANCE   366.48 +3.31% vs yesterday's close 354.72 at 10:37 IST  MOVING

! 2026-10-19 18:30 IST  RELIANCE    NSE filing    Reliance Industries Limited: Outcome of Board Meeting
      tags: earnings, results  https://nsearchives.nseindia.com/corporate/SAMPLE_RELIANCE_19102026.pdf
  2026-10-19 09:10 IST  RELIANCE    NSE filing    Reliance Industries Limited: Updates
```

When a symbol has no news, say so rather than padding the brief.

## What it never does

- Never invents or embellishes a story, a filing, a quote or a number.
- Never trades on news, and never tells the user to buy or sell because of a
  headline or a filing.
- Never hammers a server: one request per feed per symbol, with a pause between calls.

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
