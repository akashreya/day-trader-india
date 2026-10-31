---
name: trader-broker
description: >-
  Order Executor for Zerodha Kite. Sends approved NSE/BSE intraday orders to
  your Kite account, paper by default, never without your yes. Shows each
  order as a plain ticket (entry, the stop-loss as an SL-M sell placed once
  the entry fills, the target as an alert, and the max loss at the stop) plus
  the exact arguments for the Kite MCP server's place_order tool, records your
  yes word for word, then Claude's own Allow once / Deny card asks again.
  Builds the sell ticket that closes a day trade by your flat-by time, records
  fills, and logs each trade's max loss so trader-risk can hold the daily
  limit. Covers running Zerodha's kite-mcp-server with your own Kite Connect
  keys (never in chat) and setting its order tools to "Needs approval". Use
  when the user says "place the order", "buy it", "execute", "send it to
  Kite", "close my position", "flatten", "get me out", "connect Zerodha",
  "set up Kite", or after /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Executor is the only skill in this pack that can lead to a real
order, so it is the strictest. An order reaches the market only after three
separate gates, every time, for every order:

1. **trader-risk passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user clicked Allow once** on Claude's own permission card, which
   appears because Kite's order tools are set to "Needs approval".

Two yeses from the user, one PASS from the rules. No yes, no order. And on a
paper config (the default) nothing goes to Kite at all: Kite has no paper
account, so "placed" is a paper placement the user records at the price now.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id ID --filled-qty 80 --filled-price 364.20
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 34 --price 1441.10
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 34
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets, checks that a reply
is a real yes for that order, builds the flatten ticket, and keeps the log in
`trader/state/broker.json`. `--now "2026-10-19 10:15"` pins the clock (IST).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/config.json` | `"paper"` (default true) and `"broker"` (`"kite"` for real orders) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `fill` and by `result --filled-qty` |
| `trader/plan.json` | the flat-by time for `flatten` |

## How an order maps onto Kite

Kite has no bracket order for equity intraday, so a planned trade becomes:

- **The entry**: `place_order` with `variety` regular, `exchange` NSE (BSE for
  a `.BO` symbol), `tradingsymbol` (RELIANCE, M&M), `transaction_type` BUY,
  `quantity`, `product` MIS, `order_type` MARKET or LIMIT (`price`), `validity` DAY.
- **The stop-loss**, placed only after the entry fills: a SELL, MIS,
  `order_type` SL-M with `trigger_price` at the stop. It rests at Kite.
- **The target is not a resting order.** Two resting sells (a stop-loss and a
  target) could both fill and leave the user short. trader-alerts rings at
  the target; then cancel the stop-loss and sell, as in "out by flat-by" below.

Kite wants the trading symbol (RELIANCE), not a BSE scrip code; the ticket
says so when an order carries a code.

## Setup: Zerodha's Kite MCP server, run by the user

Zerodha publishes github.com/zerodha/kite-mcp-server (MIT). Its hosted
endpoint (mcp.kite.trade) is read-only: it leaves out the order tools on
purpose. To place orders the user runs the server themselves with their own
Kite Connect app:

1. On developers.kite.trade the user creates a Kite Connect app and gets its
   API key and secret. Retail algo orders through an API sit under SEBI's
   framework for retail algorithmic trading (2025) and Zerodha's own rules for
   it: the user reads those first. This skill helps place orders the user
   approves one by one; it is not an automated strategy.
2. The user downloads or builds the server (a single program) from that repo.
3. In Claude Desktop: Settings > Developer > Edit Config, and add the block in
   `claude_desktop_config.example.json` here, with the path to the program and
   the user's key and secret typed into that file:

```json
{
  "mcpServers": {
    "kite": {
      "command": "C:\\Users\\YOU\\kite-mcp-server\\kite-mcp-server.exe",
      "env": {"APP_MODE": "stdio",
              "KITE_API_KEY": "typed into this file, never into the chat",
              "KITE_API_SECRET": "typed into this file, never into the chat"}
    }
  }
}
```

   **Keys never go in the chat.** Never ask for them, never read this file
   back into the conversation, and if the user pastes one anyway, tell them to
   delete that message and make new keys on developers.kite.trade.
4. Restart Claude Desktop, and log in through the server's `login` tool (it
   gives a Kite login link; the user logs in on Zerodha's own page). The
   session lasts the trading day.
5. **Set the tool permissions.** Customize > Connectors, open kite:
   - `place_order`, `modify_order`, `cancel_order`, `convert_position`, and the
     GTT tools: **Needs approval**. Never Always allow.
   - mutual fund order and SIP tools: **Blocked** unless the user says otherwise.
   - read-only tools (`get_profile`, `get_margins`, `get_positions`,
     `get_holdings`, `get_orders`, `get_trades`, `get_ltp`, `get_quotes`,
     `search_instruments`): Always allow is fine.
6. Check it: ask Claude for the Kite profile and margins (read only).
7. Only then, and only if the user asks for it, they set `"paper": false` and
   `"broker": "kite"` in `trader/config.json` themselves.

In Claude Code instead of Claude Desktop, keep the order tools on ask in
`.claude/settings.json`: `"permissions": {"ask": ["mcp__kite__place_order",
"mcp__kite__cancel_order", "mcp__kite__modify_order"]}`, never in `allow`.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT
   READY or BLOCKED goes back to `/trader-risk`.
2. Show ONE ticket and ask: "Place this order? Reply yes or no." One order
   per question. Never offer "yes to all".
3. Run `ticket.py approve --index N --reply "<the user's reply, word for word>"`.
   If it prints "Not recorded", the reply was not an explicit yes for this
   order (for example "sure", "haan", "yes to all", or a yes that names a
   different stock or amount). Ask again. Never turn a reply into a yes yourself.
4. Paper: record the paper placement with `result --status placed
   --filled-qty Q --filled-price P` at the price now. Live: only after
   "Recorded your yes", call `place_order` with exactly the entry JSON the
   ticket printed. Claude's card appears: Allow once or Deny.
5. Record what happened: `ticket.py result --index N --status placed
   --broker-id <Kite order id> --filled-qty Q --filled-price P` (from
   `get_orders` once it is COMPLETE), or `--status denied`, or `--status
   failed` with `--note`. A failed order is not retried without a new check
   and a new yes. The log keeps the entry's max loss for trader-risk.
6. Live: when the entry is COMPLETE, call `place_order` with the stop-loss
   JSON the ticket printed. It gets its own Allow once card.

## Steps: while it is open, and out by flat-by

- trader-alerts watches the stop, the target and the flat-by time
  (`alerts.py add --from-plan`). The SL-M sell at Kite does the stopping.
- When the stop-loss fills, record it: `ticket.py fill --symbol RELIANCE
  --side sell --qty 34 --price 1441.10`.
- At the target, or by `flat_by` (15:00 IST), close what is still open:
  1. Ask Kite what is held: `get_positions` (read only).
  2. `ticket.py flatten --symbol RELIANCE --qty 34` writes a market sell.
  3. `/trader-risk`. A sell that only closes what the user holds is never
     blocked by the daily limits or the entry window.
  4. `ticket.py show`, then the user's yes for that one order, as above.
  5. **Cancel the resting stop-loss first** (`get_orders`, status TRIGGER
     PENDING, then `cancel_order`, Needs approval), or both sells can fill.
     Then `place_order` with the ticket, then `result`.
  The broker squares off MIS positions itself near the close (3:00 to 3:25 PM
  depending on the broker and the stock) and charges for it.

## Example: the test fixture, on a live config

```
ORDER 1 of 1, LIVE KITE ACCOUNT, REAL MONEY, NSE
  BUY 80 TSLA, market, good for today
  stop-loss 358.32
  target 370.04 (an alert, not a resting order)
  max loss about Rs 468.80 if the stop fills at 358.32 (it can fill worse in a fast market)
  READY: trader-risk PASS, waiting for your yes
  Claude will call the Kite MCP place_order tool with exactly:
    {"variety": "regular", "exchange": "NSE", "tradingsymbol": "TSLA", "transaction_type": "BUY",
     "quantity": 80, "product": "MIS", "order_type": "MARKET", "validity": "DAY"}
  Then, once the entry has filled, the stop-loss as its own order:
    {..., "transaction_type": "SELL", "quantity": 80, "product": "MIS", "order_type": "SL-M",
     "trigger_price": 358.32, "validity": "DAY"}
```

On the default paper config the same ticket says "PAPER (nothing goes to
Kite)" and Claude calls nothing.

## What it never does

- Never places an order without all three gates, and never two orders on one yes.
- Never places orders from a scheduled or background task: nobody is there to say yes.
- Never asks for, reads, stores or repeats API keys, passwords, PINs or TOTP codes.
- Never switches `"paper"` to false or `"broker"` to kite. The user does that themselves.
- Never places F&O, CNC (delivery), GTT, mutual fund or short orders on its own.

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
