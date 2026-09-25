"""
Synthetic inputs for the backtest scripts
=========================================
Writes a made-up ghost score file and made-up daily prices so that
ghost_backtest_v2.py and ghost_concentration_compare_3.py can run end to end
without the licensed Revelio Labs data and without downloading prices.

Nothing here is market data. Tickers are SYN001, SYN002, ... plus a made-up
benchmark SYNMKT, and every company name ends in "(synthetic)". The numbers a
backtest prints on these files say nothing about ghost postings: they only show
that the pipeline runs.

Two scenarios:
  random   (default) scores and returns are independent — no signal by construction.
  planted  a firm's return in the quarter after quarter q is driven by its score
           for quarter q+1, a score that is only published after that quarter has
           ended. A backtest that respects the publication lag cannot earn it; one
           that reads scores before they are available earns a lot. scripts/check.py
           uses this to test that the backtester has no lookahead.

Files written to --out (default data/synthetic):
  ghost_scores_fq.parquet  the notebook's output schema (rcid, company, ticker, quarter,
                           num_postings, actual_inflows_next_q, predicted_inflows,
                           firm_median_pred, ghost_score, is_ghost)
  prices.parquet           long format: date, ticker, close, volume
  manifest.json            scenario, seed, date range, and the backtest window to use

USAGE
    python scripts/make_synthetic.py
    python scripts/make_synthetic.py --scenario planted --out /tmp/planted
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

QUARTERS = [f"{y}-Q{q}" for y in range(2020, 2024) for q in range(1, 5)][2:13]   # 2020-Q3 … 2023-Q1
PRICE_START, PRICE_END = "2020-06-01", "2023-06-30"
BACKTEST_START, BACKTEST_END = "2021-01-01", "2022-12-31"
BENCHMARK = "SYNMKT"


def quarter_end(q: str) -> pd.Timestamp:
    year, qn = int(q[:4]), int(q[-1])
    return pd.Timestamp(year=year, month=qn * 3, day=1) + pd.offsets.MonthEnd(0)


def ghost_scores(rng: np.random.Generator, firms: int) -> pd.DataFrame:
    """One row per firm-quarter, computed the way the notebook computes ghost_scores_fq (cells 26 and 29)."""
    rows = []
    for i in range(1, firms + 1):
        size = rng.lognormal(mean=3.0, sigma=0.8)                  # firm-level hiring scale
        for q in QUARTERS:
            postings = int(max(3, rng.poisson(size)))
            predicted = float(max(0.0, rng.normal(0.35 * postings, 0.15 * postings)))
            rows.append({
                "rcid": 900000 + i,
                "company": f"Synthetic Firm {i:03d} (synthetic)",
                "ticker": f"SYN{i:03d}",
                "quarter": q,
                "num_postings": postings,
                "actual_inflows_next_q": float(max(0.0, predicted + rng.normal(0, 2))),
                "predicted_inflows": predicted,
            })
    df = pd.DataFrame(rows)
    # firm-quarter score relative to the firm's median prediction (notebook cell 29), clipped to [0, 1]
    df["firm_median_pred"] = df.groupby("rcid")["predicted_inflows"].transform("median")
    df["ghost_score"] = (1.0 - df["predicted_inflows"] / df["firm_median_pred"].clip(lower=0.01)).clip(0.0, 1.0)
    # company-level flag: predicted fill rate at or below the 21st percentile (notebook cell 29)
    firm = df.groupby("rcid").agg(pred=("predicted_inflows", "sum"), posts=("num_postings", "sum"))
    fill = firm["pred"] / firm["posts"]
    df["is_ghost"] = df["rcid"].map(fill <= np.percentile(fill, 21.0))
    return df


def plant_scores(rng: np.random.Generator, df: pd.DataFrame) -> pd.DataFrame:
    """Planted scenario: independent uniform scores per firm-quarter, so a quarter's score says nothing about
    the scores of the quarters before it; the returns are then tied to these scores in prices()."""
    df = df.copy()
    df["ghost_score"] = rng.uniform(0.0, 1.0, len(df))
    return df


def prices(rng: np.random.Generator, scores: pd.DataFrame, scenario: str) -> pd.DataFrame:
    days = pd.bdate_range(PRICE_START, PRICE_END)
    tickers = sorted(scores["ticker"].unique())
    n = len(days)
    market = rng.normal(0.0004, 0.009, n)
    rets = {BENCHMARK: market}
    by_q = scores.pivot(index="ticker", columns="quarter", values="ghost_score") if scenario == "planted" else None
    q_ends = [quarter_end(q) for q in QUARTERS]
    for t in tickers:
        r = 0.9 * market + rng.normal(0.0, 0.015, n)
        if by_q is not None:
            # in the window (end of quarter q, end of quarter q+1] the return follows the score for quarter q+1,
            # which is published lag_days after the end of q+1: only a backtest that looks ahead can use it
            for k in range(len(QUARTERS) - 1):
                window = (days > q_ends[k]) & (days <= q_ends[k + 1])
                r[window] += 0.004 * (by_q.loc[t, QUARTERS[k + 1]] - 0.5) * 2.0
        rets[t] = r
    frames = []
    for t, r in rets.items():
        start = rng.uniform(20, 150) if t != BENCHMARK else 300.0
        close = start * np.cumprod(1.0 + r)
        volume = rng.integers(200_000, 2_000_000, n) if t != BENCHMARK else np.full(n, 50_000_000)
        frames.append(pd.DataFrame({"date": days, "ticker": t, "close": close, "volume": volume}))
    return pd.concat(frames, ignore_index=True)


def main(out: str = "data/synthetic", firms: int = 200, scenario: str = "random", seed: int = 486) -> Path:
    if scenario not in ("random", "planted"):
        raise SystemExit(f"unknown scenario {scenario!r}: use random or planted")
    rng = np.random.default_rng(seed)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    scores = ghost_scores(rng, firms)
    if scenario == "planted":
        scores = plant_scores(rng, scores)
    px = prices(rng, scores, scenario)
    scores.to_parquet(out_dir / "ghost_scores_fq.parquet", index=False)
    px.to_parquet(out_dir / "prices.parquet", index=False)
    manifest = {
        "synthetic": True,
        "scenario": scenario,
        "seed": seed,
        "firms": firms,
        "quarters": [QUARTERS[0], QUARTERS[-1]],
        "prices": [PRICE_START, PRICE_END],
        "backtest": [BACKTEST_START, BACKTEST_END],
        "benchmark": BENCHMARK,
        "note": "made-up data: tickers SYN###, benchmark SYNMKT; results say nothing about real firms",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"synthetic data ({scenario}, seed {seed}): {len(scores):,} firm-quarter scores for {firms} firms, "
          f"{px['date'].nunique():,} trading days of prices → {out_dir}/")
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write synthetic inputs for the backtest scripts",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--out", default="data/synthetic", help="output folder")
    parser.add_argument("--firms", type=int, default=200)
    parser.add_argument("--scenario", default="random", choices=["random", "planted"])
    parser.add_argument("--seed", type=int, default=486)
    args = parser.parse_args()
    main(out=args.out, firms=args.firms, scenario=args.scenario, seed=args.seed)
