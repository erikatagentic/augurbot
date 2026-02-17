# Check Kalshi Balance

Quick check of Kalshi account balance, open positions, and resting orders.

## Steps

1. Run:
   ```
   backend/.venv/bin/python3 tools/balance.py
   ```

2. Display the output to the user. It shows:
   - Cash balance
   - Portfolio value (open positions)
   - Total account value
   - List of open positions (ticker, side, quantity)
   - List of resting (unfilled) orders
