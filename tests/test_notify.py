"""The paper-trading digest is the content of the Slack P&L alert. It must read
the existing performance/recommendation data and produce a concise summary that
works both in the terminal and as a Slack message."""
from tools.notify import build_digest


def _perf():
    return {
        "overall_brier": 0.2108,
        "hit_rate": 0.4735,
        "total_pnl": -61.47,
        "simulated_pnl": -2.0,
        "total_resolved": 359,
        "bias_by_category": {
            "NBA": {"weighted_bias": -0.0278, "count": 132},
            "NCAA Basketball": {"weighted_bias": 0.0057, "count": 127},
        },
    }


def test_digest_includes_headline_metrics():
    out = build_digest(_perf(), [{"status": "active"}, {"status": "resolved"}])
    assert "AugurBot" in out
    assert "0.211" in out or "0.2108" in out          # brier
    assert "47" in out                                 # hit rate %
    assert "-$61.47" in out                            # real P&L to date
    assert "1 active" in out                           # active paper recs


def test_digest_flags_paper_mode():
    out = build_digest(_perf(), [])
    # Must make clear no real money is being bet during data-gathering.
    assert "paper" in out.lower()
    assert "no real" in out.lower()
