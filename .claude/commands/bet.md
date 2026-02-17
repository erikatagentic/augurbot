# Place Top Bets

Automatically place the top 5 recommended bets from the most recent scan, using no more than 5% of available Kalshi balance per bet.

## Steps

1. **Read recommendations.** Read `data/recommendations.json` and find the most recent scan's recommendations (filter by most recent `scan_time`, status = "active", EV >= 3%).

2. If no active recommendations exist, tell the user to run `/project:scan` first.

3. **Check balance.** Run:
   ```
   backend/.venv/bin/python3 tools/balance.py
   ```
   Note the cash balance.

4. **Calculate bet sizes.** For each of the top 5 bets by EV:
   - Max per bet = 5% of cash balance
   - For YES bets: contracts = floor(max_per_bet / (yes_price / 100))
   - For NO bets: contracts = floor(max_per_bet / ((100 - yes_price) / 100))
   - Minimum 1 contract per bet

5. **Show confirmation table** before placing any bets:
   | # | Market | Direction | Contracts | Price | Cost | Potential Profit |

   Show total cost across all 5 bets.

6. **Place each bet** using:
   ```
   backend/.venv/bin/python3 tools/bet.py TICKER SIDE COUNT PRICE
   ```
   Where PRICE is the YES price in cents (from latest_scan.json, field `price_yes` x 100).

7. **Save placed bets.** Append each placed bet to `data/bets.json`:
   ```json
   {
     "placed_at": "ISO timestamp",
     "ticker": "KXMARKET-TICKER",
     "question": "Market question",
     "direction": "yes or no",
     "contracts": 10,
     "yes_price": 51,
     "cost": 4.90,
     "order_id": "from bet.py output",
     "order_status": "resting or executed",
     "status": "open",
     "pnl": null,
     "closed_at": null
   }
   ```

8. **Show summary** with total risk, potential max return, and remaining balance.
