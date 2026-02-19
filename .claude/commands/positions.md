# Check Open Positions

Check current market prices on all open bets, show unrealized P&L, and flag line movement.

## Steps

1. **Check positions.** Run:
   ```
   backend/.venv/bin/python3 tools/positions.py
   ```

2. **Display the output** to the user. It shows:
   - All open bets with entry price vs current price
   - Line movement (% change since entry)
   - Unrealized P&L per position and total
   - Flags: "CASH OUT?" if line moved >10% in our favor, "CUT LOSS?" if >10% against

3. **If any positions are flagged**, explain the tradeoff:
   - **CASH OUT?**: The line moved heavily in our favor. We could sell now to lock in profit, but forgo the potential max payout if the bet resolves in our favor.
   - **CUT LOSS?**: The line moved against us. Consider whether fundamentals changed or if this is noise. Holding risks further loss, but selling now locks in the loss.
