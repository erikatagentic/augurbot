"""Score researched markets against the revealed book using the shared pipeline.

Input JSON: list of {ticker, ai_estimate, yes_ask, yes_bid, confidence}.
Output JSON (stdout): same rows annotated with recommend/direction/edge/ev/kelly.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.strategy import evaluate_market


def main() -> None:
    rows = json.loads(Path(sys.argv[1]).read_text())
    out = []
    for r in rows:
        d = evaluate_market(
            ai_estimate=r["ai_estimate"],
            yes_ask=r["yes_ask"], yes_bid=r["yes_bid"],
            confidence=r.get("confidence", "medium"),
        )
        out.append({**r, **d})
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
