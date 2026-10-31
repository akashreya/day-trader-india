---
name: trader-risk
description: >-
  Risk Manager for NSE intraday. Checks every trade against your limits and
  stops anything over them. For a day trade: a stop is
  required, the loss at the stop plus the Indian intraday charges must fit
  your max loss per trade (measured from the higher of the plan's entry and
  a fresh price), reward:risk must
  meet your minimum, the day's total risk must fit your daily loss limit, no
  more than your trades per day, and no new entries outside your entry
  window or when the market is closed. It also keeps the basics: blocked
  tickers, order size, position cap, cash buffer, margin, short sales,
  options and crypto, malformed or bad bracket orders, duplicates and a daily
  order limit. Getting out is never blocked by a day limit. Prints PASS or
  BLOCK with the reason and records the verdicts with a fingerprint of each
  exact order. Use when the user says "check my order", "is this
  safe", "risk check", "does this break my rules", "can I take this trade",
  "how much have I risked today", or after /trader-budget, always.
argument-hint: "[path to orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposal and the user. Every order
written by trader-budget passes through it. A BLOCK is final for that order:
it is not shown to the user as a trade to take. This port is paper only, so
a PASS goes nowhere on its own either. Most people who day trade lose money. These limits
keep each loss and each day's losses small. They do not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                           # trader/ files; writes trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write                # look without recording
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-10-19 10:00"  # pin the clock (IST time)
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget) |
| `trader/config.json` | the limits (trader-budget ships `config.example.json`) |
| `trader/portfolio.json` | cash and holdings; if missing, a fresh account funded with the budget |
| `trader/prices.json` | `{"prices": {"SYMBOL": price}}`: a fresh price raises the entry it measures risk from |
| `trader/state/broker.json` | optional log of what you placed today (your paper trades): duplicates, trades per day, daily loss |
| `trader/state/risk.json` | the verdicts it writes, with a fingerprint of each exact order |

## Entries and exits

An **entry** opens or adds to a position: a buy, or a sell that would go
short. An **exit** only reduces what you already hold. Getting out must
always be possible, so an exit is checked for format, asset and short sales
only. Every other rule (day limits, entry window, loss, reward:risk, blocked
list, size, duplicates) turns into a warning for an exit, never a BLOCK.

## The checks

Orders are checked in file order, as if each passed order had filled, so a
batch that is fine order by order but breaks a limit together is caught.

| check | blocks when |
| --- | --- |
| format | no symbol, side not buy or sell, both or neither of qty and notional, a notional order that is not market + day, a limit order with no limit price; a bracket that is not whole shares, not `day` or `gtc`, or misses its stop-loss or take-profit |
| asset | an option symbol while `allow_options` is false; crypto or anything that is not an NSE symbol (RELIANCE, M&M, BAJAJ-AUTO; .NS or .BO allowed) |
| short | a sell of more than you hold (`allow_short` false) |
| blocked | (entries) the ticker is on the `blocked` list |
| size | (entries) under `min_order_inr` or over `max_order_inr` |
| position | (entries) the stock would be over `max_position_pct` of the account |
| cash | (entries) the buy would leave less than the cash buffer, or need margin |
| stop | (entries) no stop while `require_stop` is true (a bracket `stop_loss_stop_price`, or the order's plan stop); a stop on the wrong side of the entry |
| loss | (entries) qty x (entry minus stop), plus the intraday charges, over `max_loss_per_trade_inr` |
| reward:risk | (entries) (target minus entry) / (entry minus stop) under `min_reward_risk` |
| daily loss | (entries) the max losses at the stops of today's entries, plus this one, over `max_daily_loss_inr` |
| trades | (entries) `max_trades_per_day` entries already placed today |
| window | (entries) before `no_entries_before` or after `no_entries_after`, or the market is closed |
| duplicate | (entries) the same symbol and side twice in one batch, or already placed today |
| daily limit | (entries) `max_orders_per_day` orders already placed today |

How the numbers work:

- **The entry it measures from**: the limit price for a limit order. For a
  market order, the HIGHER of the plan's entry and a fresh price from
  `trader/prices.json` (under 15 minutes old). A plan written at 10:00 cannot
  understate the risk at 10:40 after the price ran up. An older price is not
  used, and it says so.
- **Charges**: brokerage (0.03% up to Rs 20 an order), STT 0.025% on the
  sell, NSE 0.00297% (BSE 0.00375% for a `.BO` symbol), SEBI 0.0001%, stamp duty 0.003% on the buy and 18% GST,
  the same rates as trader-budget (`"charges"` in the config; `false` turns
  them off). Your contract note is the truth.
- **Daily loss** counts the full max loss of every entry placed today, win or
  lose, as logged in `trader/state/broker.json`. Three full-size trades use
  up a Rs 1,500 day.
- **The window** is India time (IST, UTC+5:30, no daylight saving), worked
  out in the tool, never from the computer's clock zone. Weekends and NSE
  holidays (the 2026 list is built in; add 2027 when NSE publishes it) are
  closed. Set both `no_entries_*` to null to switch the window off.
- There is no pattern-day-trader rule in India. `pdt_guard` stays off.

Warnings do not block, but say them to the user: a LIVE account, a number
sent as a number instead of a string, a stop that lives only in the plan and
not at the broker, a price too old to use.

## Steps

1. If the price may have moved since the plan, put a fresh one in
   `trader/prices.json` first (`{"prices": {"RELIANCE": 1450.2}}`).
2. Run `check.py`. Exit code 0 means every order passed, 1 means at least one
   was blocked.
3. Tell the user the result in plain words, order by order: the max loss at
   the stop, reward:risk, and how much of today's limits it uses. For a
   BLOCK, give the reason and the fix (fewer shares, a closer stop from
   trader-exit, wait for the window, or skip the trade). Never change a
   limit yourself.
4. If the order changes in any way, run the check again. Each verdict is
   recorded with a fingerprint of the exact order, so an edited order has not
   passed until it passes again, and a verdict from yesterday does not count today.

## Example: the test fixture

The bracket trader-budget sized from the fixture plan (TSLA bars retimed onto
NSE hours) at 10:00 AM on Monday 2026-10-19, on a fresh Rs 1,00,000 paper
account with the example config:

```
PASS  #1 buy TSLA 80 shares, entry
          entry 364.18 (the plan's entry), stop 358.32, target 370.04: risk 5.86 a share
          max loss Rs 499.40 incl. Rs 30.60 charges (limit Rs 500), reward:risk 1.00 (min 1)
          today before this: 0 of 3 trades, Rs 0 of Rs 1,500 daily loss

1 passed, 0 blocked at 2026-10-19 10:00 IST. Cash after the passed orders: Rs 70,865.60 (paper account).
```

Six more shares and it is blocked:

```
BLOCK #1 buy TSLA 86 shares, entry
          entry 364.18 (the plan's entry), stop 358.32, target 370.04: risk 5.86 a share
          max loss Rs 536.85 incl. Rs 32.89 charges (limit Rs 500), reward:risk 1.00 (min 1)
          today before this: 0 of 3 trades, Rs 0 of Rs 1,500 daily loss
        - loss: 86 shares x 5.86 risk a share = Rs 503.96 at the stop + Rs 32.89 charges = Rs 536.85, over your Rs 500 max loss per trade
```

The same 80 shares checked at 10:40 with a 10:37 quote of 366.48 in
`trader/prices.json` are blocked twice: 80 x 8.16 = Rs 652.80 at the stop,
and reward:risk 0.44. At 9:25 they are blocked by the window (no new entries
before 9:30). A 3:00 PM sell that closes the position passes, even though it
is after the 2:30 entry cutoff: it is an exit.

## Rules

- A PASS only means the order is allowed to be shown to the user. It is not a yes.
- Every number comes from the config, the order, the portfolio, the prices or the broker log.
- Free Yahoo prices are unofficial and can lag; the broker's price is the one that fills, and a
  stop can fill worse than its price in a fast market.

## What it never does

It never places an order, never edits an order to make it pass, never
loosens a limit, never blocks a sell that only gets the user out, and never
treats a PASS as the user's yes.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper only. This India port has no broker step: nothing in it can place, change or cancel an
  order. Any real order is one the user types into their own broker and says yes to themselves.
- NSE cash equity, intraday (MIS), longs only. No F&O, no short selling, no leverage beyond what
  the user's broker gives MIS on its own terms, and none of that is sized here.
- Indian intraday costs (brokerage, STT, exchange charges, SEBI fee, stamp duty, GST) are counted in
  the sizing. The contract note is the truth; the config's rates are an estimate.
- Be flat before the broker's MIS auto square-off (it charges a fee and sells at whatever price).
- Day trading loses most people money: SEBI's own study found about 7 in 10 individual intraday
  traders in the cash segment lost money. Small size, a stop on every trade, flat every day.
- Yahoo's data is free, unofficial and can lag. Check anything that matters against the broker.
