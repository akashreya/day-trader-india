---
name: trader-budget
description: >-
  Budget Manager for NSE intraday. Sizes every position to your budget and
  your max loss per trade in rupees, charges included. Reads the trade plan
  from trader-exit (entry, stop, target), finds the whole shares that fit
  inside four limits (max loss per trade after brokerage, STT, exchange
  charges, stamp duty and GST; position cap; max order; cash after your
  buffer), says which limit decided it, shows the loss at the stop and the
  gain at the target after charges, and writes ONE paper bracket order
  (entry, stop-loss, take-profit, NSE or BSE, MIS) to trader/orders.json. A stop too
  far away for your max loss, or a target that does not even pay the
  charges, is a plain refusal. Nothing is placed. Use when the user says
  "how many shares", "size this trade", "how much should I buy", "I have
  Rs 1 lakh", "I only want to risk Rs 500 a trade", "what are the charges",
  "set my rules", or after /trader-exit writes a plan.
argument-hint: "[budget in rupees]"
---

# trader-budget

The Budget Manager turns a plan ("buy at 364.18, stop 358.32") into an exact
paper order ("buy 80 shares"), inside rules the user sets once. The stop
decides the size: the further away the stop, the fewer shares. Then the
Indian intraday charges come off: the max loss is what the trade can cost,
the move to the stop PLUS the charges. It writes a proposal only;
trader-risk checks it. Day trading loses most people money. Sizing to a max
loss keeps each loss small; it does not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                        # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write        # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 364.00 --json  # a limit order at 364.00
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights RELIANCE=40,TCS=60 --config split.json   # weights mode
```

`--now "2026-10-19 10:00"` pins the clock (India time, IST). A plan for
another day is refused: make a new one with trader-exit.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the rules (start from `config.example.json` in this folder) |
| `trader/plan.json` | the trade: entry, stop, target, setup, flat-by time (trader-exit writes it) |
| `trader/prices.json` | optional `{"prices": {"SYMBOL": price}}`: a fresh price above the plan's entry means a bigger risk |
| `trader/portfolio.json` | optional: its cash caps the size |
| `trader/orders.json` | the one proposed bracket order it writes with `--write` |

## Step 1: set the rules once

If `trader/config.json` does not exist, copy `config.example.json` into
`trader/config.json` and ask the user for each value in plain words:

- **budget**: how many rupees this is for. Only money they can afford to lose (example 1,00,000).
- **cash_buffer_pct**: how much always stays in cash (default 10).
- **max_loss_per_trade_inr**: the most one trade may cost at the stop, charges included (500).
- **max_position_pct**, **max_order_inr**, **min_order_inr**: the biggest position (75% of the
  budget), the biggest order (Rs 80,000) and the smallest order (Rs 100).
- The day limits trader-risk enforces: **max_daily_loss_inr** (1,500), **max_trades_per_day** (3),
  **min_reward_risk** (1.0), **require_stop** (true), **no_entries_before** / **no_entries_after**
  ("09:30" / "14:30") and **flat_by** ("15:00"), all IST.
- **charges**: the broker's rates. The defaults are the usual discount-broker intraday rates:
  brokerage 0.03% capped at Rs 20 an order, STT 0.025% on the sell, NSE transaction 0.00297%
  (BSE 0.00375% for a `.BO` symbol),
  SEBI 0.0001%, stamp duty 0.003% on the buy, GST 18% on brokerage + exchange + SEBI.
- **blocked**: symbols they never want to trade.
- Keep **paper** true until they have watched it work for a while. Real orders need
  `"paper": false` and `"broker": "kite"` (see `/trader-broker`).

## Step 2: size the trade

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
```

Whole shares only. The size is the smallest of four limits:

| limit | shares |
| --- | --- |
| max loss | `max_loss_per_trade_inr` / risk a share, then trimmed until loss at the stop + charges fits |
| position cap | budget x `max_position_pct` / entry |
| max order | `max_order_inr` / entry |
| cash | (budget minus the cash buffer) / entry, never more than the cash in `trader/portfolio.json` |

The entry it sizes at: the limit price with `--limit`. For a market order, the
plan's entry, or the price in `trader/prices.json` if it is fresh (under 15
minutes old) and higher. A price that ran up since the plan means a bigger
loss at the same stop, so fewer shares. A lower price never shrinks the risk.

It refuses, and writes no order, when: the size is zero shares, the order is
under the minimum, reward:risk is under `min_reward_risk`, the target does not
pay the charges, the stop is not below the entry, the target is not above it
(the move already happened), the plan is for another day, the symbol is
blocked, or the plan is a short. Say the reason to the user in one line.

## Step 3: show the user

Show the four limits, which one decided the size, the shares, the rupees, the
charges, and the loss at the stop and the gain at the target AFTER charges.
Say plainly that a stop is an order, not a promise: in a fast market it can
fill below the stop. Then hand over to `/trader-risk`.

## Example

The test fixture's plan (real 5-minute bars, retimed onto NSE hours): entry
364.18 at 10:00 AM, stop 358.32 (the opening-range midpoint), target 370.04
(1R). Risk 5.86 a share. The example config: Rs 1,00,000 budget, 10% cash
buffer, Rs 500 max loss.

| limit | the math | shares |
| --- | --- | --- |
| max loss | Rs 500 / 5.86 = 85, less charges | **80 (decides it)** |
| position cap | 75% of Rs 1,00,000 = Rs 75,000 / 364.18 | 205 |
| max order | Rs 80,000 / 364.18 | 219 |
| cash | Rs 1,00,000 minus Rs 10,000 = Rs 90,000 / 364.18 | 247 |

80 shares = Rs 29,134.40. Loss at the stop: 80 x 5.86 = Rs 468.80, plus
Rs 30.60 of charges = Rs 499.40. At the target: Rs 468.80 minus Rs 31.20 =
Rs 437.60. A 1R plan is 0.88R after charges: say that out loud. It writes:

```json
{"symbol": "TSLA", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "80", "type": "market",
 "time_in_force": "day", "order_class": "bracket", "take_profit_limit_price": "370.04",
 "stop_loss_stop_price": "358.32",
 "why": "opening-range breakout on TSLA: 80 shares, bound by your Rs 500 max loss per trade (80 x 5.86 = Rs 468.80 at the stop)",
 "plan": {"entry": 364.18, "stop": 358.32, "target": 370.04, "risk_per_share": 5.86, "max_loss": 468.8,
          "charges_at_stop": 30.6, "net_loss_at_stop": 499.4, "net_gain_at_target": 437.6,
          "setup": "orb", "entry_time": "10:00 AM", "flat_by": "15:00"}}
```

With a fresh quote of 366.48 the same plan sizes to 58 shares at 8.16 a
share, and reward:risk falls to 0.44: refused, because the move it was
waiting for has mostly happened. A 60-rupee stock with a 10-paise stop and a
5-paise target is refused too: 1,250 shares make Rs 62.50 before charges and
lose Rs 11.15 after Rs 73.65 of them.

## Weights mode (kept from v1)

`--weights RELIANCE=22.04,TCS=10.86` or `--targets FILE` (`targets.example.json`
here) splits a budget across a list by weight: the cash buffer comes off the
top, weights are renormalised to 100, any stock over `max_position_pct` is
pinned at the cap and its excess shared out, slices under the minimum order
are dropped, and amounts round to whole rupees so nothing is left idle by
accident. NSE has no fractional shares, so set `"fractional": false` and pass
prices (`--prices trader/prices.json`). These are plain buys with no stop:
trader-risk blocks them while `require_stop` is true. Use a separate config
(`--config`) for a long-term split.

## Rules

- Proposals only. This skill never calls a broker tool.
- Never size money the user has not said is for this. Ask for the budget and the max loss.
- Every number comes from the config, the plan or the prices. Nothing is guessed.
- No projections: never say what a trade will make. A target is a plan, not a forecast.
- Free Yahoo prices are unofficial and can lag. The broker's price is the one that fills.

## What it never does

It never places, approves or schedules an order, never raises a limit on its
own, never shrinks a stop to fit more shares, and never sizes F&O, margin or
short positions.

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
