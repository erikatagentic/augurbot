# Check Results & Track Performance

Check which markets have resolved, update performance tracking, calculate calibration stats, and generate feedback to improve future predictions.

## Steps

1. **Check resolutions.** Run:
   ```
   backend/.venv/bin/python3 tools/results.py
   ```
   This checks all active recommendations and open bets against the Kalshi API, updates `data/performance.json` with results, and generates `data/calibration_feedback.txt`.

2. **Display the output** to the user. It shows:
   - Newly resolved markets with W/L outcomes and P&L
   - Overall performance stats (Brier score, hit rate, P&L)
   - Bias analysis by category

3. **Interpret the results** for the user:
   - If Brier score > 0.15: "Our predictions need improvement. Focus on [worst category]."
   - If Brier score 0.10-0.15: "Decent calibration. Room to improve in [categories with bias]."
   - If Brier score < 0.10: "Excellent calibration, on par with superforecasters."
   - If hit rate > 60%: "Positive edge detected. Keep betting."
   - If hit rate < 50%: "Losing edge. Review methodology and biases."
   - Comment on P&L trend and any category-specific biases

4. **If calibration feedback was updated**, mention that the next `/project:scan` will automatically incorporate these corrections.

5. **To see stats without checking resolutions** (offline mode), run:
   ```
   backend/.venv/bin/python3 tools/results.py --stats
   ```
