---
name: trader-alerts
description: >-
  Price Alerts for NSE and BSE. Rings when a price, a stop, a target or the
  clock hits. Turns the trade plan into three alerts in one go (the stop, the
  target and "flat by 15:00", before your broker's MIS square-off), plus
  above / below / stop / target levels, percent moves from the previous close,
  any time of day, and the NSE opening bell, each ringing once so you are not
  spammed. Knows NSE hours (9:15 to 3:30 IST) and the 2026 NSE holidays, works
  out India time itself, fetches free delayed quotes from Yahoo (SYMBOL.NS, or
  SYMBOL.BO for BSE) one symbol at a time, and writes trader/prices.json for
  sizing and the risk check. Use when the user says "alert me when", "tell me
  if RELIANCE hits", "watch my stop", "watch my trade", "remind me to close by
  3", "is the market open", "when does the market open", "get me a price", or
  right after /trader-exit writes a plan.
argument-hint: "[symbol] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when an alert rings, nothing
is sold by this skill. On Kite the stop-loss rests at the broker as an SL-M
sell; the target does not (Kite has no intraday bracket), so the target alert
is the signal to close the trade yourself.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat-by from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1441.10
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 1459.30
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:00 --label "flat by 15:00"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol INFY --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE TCS.BO --write  # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan symbols
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-10-19 15:00"` pins the clock (IST); `--offline DIR` reads saved
quote files instead of the network.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest quotes, merged in, for trader-budget and trader-risk |
| `trader/portfolio.json` | the symbols held, for `quote --holdings` |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the IST clock passed `at` ("15:00") on a trading day | once per trading day |
| `opening_bell` | the NSE is open | once per trading day |

A rule with `"date"` is watched on that date only; `--from-plan` rules carry
the plan's date, so yesterday's stop never rings today. NSE has no scheduled
early closes, so a time alert rings at the time it says.

## Quotes

- Yahoo's chart endpoint, `query2.finance.yahoo.com/v8/finance/chart/RELIANCE.NS`
  (`.BO` for BSE), an unofficial free JSON endpoint, one request per symbol,
  half a second apart. On a 429 it waits and tries once more; on a 429 or a
  5xx after that it tries `query1`.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts
  and for checking a size, not for timing an order. The broker's price is the
  one that fills. Each price in `trader/prices.json` keeps its quote time, and
  trader-risk only uses one under 15 minutes old.
- If Yahoo is down, read the price from Kite (`get_ltp`, read only) and write
  it into `trader/prices.json` as `{"as_of": "...Z", "prices": {"RELIANCE": 1450.2}}`.

## The NSE clock

Regular session 9:15 a.m. to 3:30 p.m. IST (India has no daylight saving),
closed on weekends and on the 2026 NSE equity holidays: Jan 15, Jan 26, Mar 3,
Mar 26, Mar 31, Apr 3, Apr 14, May 1, May 28, Jun 26, Sep 14, Oct 2, Oct 20,
Nov 10, Nov 24 and Dec 25. BSE keeps the same equity holidays. Muhurat and
special weekend sessions are not in the calendar. For 2027 the clock says the
holiday list is unknown until NSE's December circular is added.

## Steps

1. Right after trader-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by time.
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. Each run fetches only the symbols in today's
   rules and rings each alert once. A check reads the latest delayed quote;
   it is not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang in one line each. A stop alert means the SL-M sell
   has probably filled: check Kite's `get_positions` and record the fill with
   trader-broker. A target alert or "flat by 15:00" means close what is still
   open: cancel the resting stop-loss, then trader-broker `flatten`,
   trader-risk and the user's yes. Never act for them.

## Example: the test fixture

The fixture plan (real US bars retimed onto NSE hours, symbol TSLA) on Monday
2026-10-19: entry 364.18 at 10:00 AM, stop 358.32, target 370.04, flat by
15:00. `add --from-plan` writes `tsla-plan-stop`, `tsla-plan-target` and
`tsla-flat-by` for that day. A `check` at 10:38 reads the 10:37 quote, 366.48,
between the stop and the target: nothing rings. At 3:00 PM:

```
ALERT Flat by 15:00: close it before your broker's MIS square-off: it is 15:00 IST (set for 15:00),
the market closes at 15:30. If TSLA is still open, close it: trader-broker flatten --symbol TSLA
builds the sell ticket, then trader-risk and your yes.
```

It rings once. The next trading day the plan's three alerts are no longer
watched; with `add --opening-bell`, the bell rings at 9:15.

## Rules

- An alert is a fact about a price or the clock. Say it as a fact.
- Never present a quote as live. Free quotes are delayed and unofficial.
- Confirm every new rule back to the user: symbol, type, level, day.

## What it never does

It never places, cancels or changes an order, never claims a quote is
live, and never predicts where a price is going.

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
