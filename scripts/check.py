"""
check.py — run the pipeline on synthetic data and test what the backtester promises
==================================================================================
Everything runs in a temporary folder with the scripts next to this file; nothing is
downloaded and no licensed data is read.

    python scripts/check.py            the checks below; exit 0 only if all pass
    python scripts/check.py --break    breaks the data and the code on purpose and
                                       requires the checks to go red; exit 0 only if
                                       every break is caught

Checks
  1. make_synthetic.py writes the score file, the prices and a manifest that says
     "synthetic"; every ticker is SYN### and every company is marked (synthetic).
  2. ghost_backtest_v2.py --synthetic runs: NAV for every strategy and the benchmark,
     one metrics row per NAV column, and the chart.
  3. ghost_concentration_compare_3.py --synthetic runs at 5%, 10% and 25%.
  4. A score file without the ghost_score column is refused with a message that
     names the missing column (exit code not 0).
  5. No lookahead. In the "planted" synthetic data a firm's return in the quarter
     after quarter q follows its score for quarter q+1, which is published 45 days
     after q+1 ends. Run with the 45-day lag, high-ghost and low-ghost longs must
     end within 25 percentage points of each other; run with a lag of -100 days
     (reading scores before they exist) the gap must exceed 200 points. The second
     run is the control that proves the test can see a leak.

Breaks (--break)
  A. the synthetic score file loses its ghost_score column  → check 2 must fail
  B. the backtester's time gate reads scores 150 days early → check 5 must fail
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ENV = dict(os.environ, MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1")
STRATEGIES = ["Short High Ghost", "Long High Ghost", "Long Low Ghost", "Long / Short", "Ghost Momentum",
              "Threshold (is_ghost)", "Ghost Barbell (Long Both)", "Universe (Equal Weight)", "Buy & Hold (SYNMKT)"]
TIME_GATE = 'eligible = df[df["available_date"] <= rdate]'


def run(scripts: Path, work: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(scripts / args[0]), *args[1:]],
                          cwd=work, env=ENV, capture_output=True, text=True, timeout=900)


def tail(r: subprocess.CompletedProcess, n: int = 3) -> str:
    lines = (r.stdout + r.stderr).strip().splitlines()
    return " | ".join(lines[-n:])


def total_return(metrics_csv: Path, strategy: str) -> float:
    m = pd.read_csv(metrics_csv, index_col=0)
    return float(str(m.loc[strategy, "Total Return"]).replace("%", "").replace("+", ""))


def check_generate(scripts: Path, work: Path) -> tuple[bool, str]:
    r = run(scripts, work, "make_synthetic.py", "--out", str(work / "random"))
    if r.returncode != 0:
        return False, f"exit {r.returncode}: {tail(r)}"
    scores = pd.read_parquet(work / "random" / "ghost_scores_fq.parquet")
    prices = pd.read_parquet(work / "random" / "prices.parquet")
    manifest = (work / "random" / "manifest.json").read_text(encoding="utf-8")
    ok = (scores["ticker"].str.fullmatch(r"SYN\d{3}").all() and scores["company"].str.endswith("(synthetic)").all()
          and set(prices["ticker"]) - set(scores["ticker"]) == {"SYNMKT"} and '"synthetic": true' in manifest
          and {"ticker", "quarter", "ghost_score", "is_ghost", "company"} <= set(scores.columns))
    return ok, (f"{len(scores):,} score rows · {scores['ticker'].nunique()} tickers · {prices['date'].nunique()} price days · "
                f"columns {sorted(scores.columns)}")


def check_backtest(scripts: Path, work: Path, data: Path) -> tuple[bool, str]:
    out = work / "backtest"
    r = run(scripts, work, "ghost_backtest_v2.py", "--synthetic", "--data_dir", str(data), "--output_dir", str(out))
    if r.returncode != 0:
        return False, f"exit {r.returncode}: {tail(r)}"
    nav = pd.read_csv(out / "backtest_nav.csv", index_col=0)
    metrics = pd.read_csv(out / "backtest_metrics.csv", index_col=0)
    chart = out / "backtest_results.png"
    ok = (len(nav) >= 400 and list(nav.columns) == STRATEGIES and list(metrics.index) == list(nav.columns)
          and chart.exists() and chart.stat().st_size > 10_000)
    return ok, f"{len(nav)} NAV days · columns {list(nav.columns)} · metrics rows {len(metrics)} · chart {chart.stat().st_size if chart.exists() else 0} bytes"


def check_sweep(scripts: Path, work: Path, data: Path) -> tuple[bool, str]:
    out = work / "sweep"
    r = run(scripts, work, "ghost_concentration_compare_3.py", "--synthetic", "--data_dir", str(data),
            "--concentrations", "0.05", "0.10", "0.25", "--output_dir", str(out))
    if r.returncode != 0:
        return False, f"exit {r.returncode}: {tail(r)}"
    files = [out / f"nav_conc_{c}.csv" for c in ("5%", "10%", "25%")] + [out / "concentration_comparison.png"]
    missing = [f.name for f in files if not f.exists()]
    return not missing, "all four outputs written" if not missing else f"missing {missing}"


def check_refuses_missing_column(scripts: Path, work: Path) -> tuple[bool, str]:
    bad = work / "no-score-column"
    bad.mkdir(exist_ok=True)
    shutil.copy(work / "random" / "prices.parquet", bad / "prices.parquet")
    shutil.copy(work / "random" / "manifest.json", bad / "manifest.json")
    pd.read_parquet(work / "random" / "ghost_scores_fq.parquet").drop(columns=["ghost_score"], errors="ignore").to_parquet(
        bad / "ghost_scores_fq.parquet", index=False)
    r = run(scripts, work, "ghost_backtest_v2.py", "--synthetic", "--data_dir", str(bad), "--output_dir", str(work / "refused"))
    text = r.stdout + r.stderr
    ok = r.returncode != 0 and "missing required columns" in text and "ghost_score" in text
    return ok, f"exit {r.returncode}: {tail(r, 2)}"


def check_no_lookahead(scripts: Path, work: Path) -> tuple[bool, str]:
    planted = work / "planted"
    r = run(scripts, work, "make_synthetic.py", "--scenario", "planted", "--out", str(planted))
    if r.returncode != 0:
        return False, f"make_synthetic exit {r.returncode}: {tail(r)}"
    gaps = {}
    for lag in ("45", "-100"):
        out = work / f"lag{lag}"
        r = run(scripts, work, "ghost_backtest_v2.py", "--synthetic", "--data_dir", str(planted), f"--lag_days={lag}",
                "--output_dir", str(out))
        if r.returncode != 0:
            return False, f"lag {lag}: exit {r.returncode}: {tail(r)}"
        gaps[lag] = total_return(out / "backtest_metrics.csv", "Long High Ghost") - total_return(out / "backtest_metrics.csv", "Long Low Ghost")
    ok = abs(gaps["45"]) < 25 and gaps["-100"] > 200
    return ok, (f"high-ghost minus low-ghost total return: {gaps['45']:+.1f} pp with the 45-day lag (must be within ±25), "
                f"{gaps['-100']:+.1f} pp when reading scores 100 days early (control, must exceed +200)")


def run_checks(scripts: Path, work: Path, data_hook=None) -> list[tuple[str, bool, str]]:
    results = [("1 synthetic data is written and marked synthetic", *check_generate(scripts, work))]
    data = work / "random"
    if data_hook:
        data_hook(data)
    results.append(("2 backtest runs on synthetic data", *check_backtest(scripts, work, data)))
    results.append(("3 concentration sweep runs on synthetic data", *check_sweep(scripts, work, data)))
    results.append(("4 a score file without ghost_score is refused by name", *check_refuses_missing_column(scripts, work)))
    results.append(("5 no lookahead: the publication lag keeps the planted future scores out", *check_no_lookahead(scripts, work)))
    return results


def report(results) -> bool:
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name} — {detail}")
    return all(ok for _, ok, _ in results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--break", dest="break_", action="store_true", help="break the data and the code; the checks must go red")
    args = parser.parse_args()

    if not args.break_:
        with tempfile.TemporaryDirectory() as tmp:
            ok = report(run_checks(HERE, Path(tmp)))
        print("RESULT: ALL PASS" if ok else "RESULT: FAILED")
        return 0 if ok else 1

    caught = []
    # A: the score file loses a column the backtester needs; check 2 must go red
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        def drop_column(data: Path):
            f = data / "ghost_scores_fq.parquet"
            pd.read_parquet(f).drop(columns=["ghost_score"]).to_parquet(f, index=False)

        results = run_checks(HERE, work, data_hook=drop_column)
        red = {name for name, ok, _ in results if not ok}
        # red is not enough: the check has to fail *because of the missing column*, or any unrelated breakage
        # (a pandas release that renames an offset, say) would read as "the break was caught"
        detail2 = next((d for name, ok, d in results if name.startswith("2 ") and not ok), "")
        right_reason = "ghost_score" in detail2
        print(f"break A (ghost_score column removed from the synthetic scores): red checks {sorted(red) or 'none'}"
              f" · check 2 names the missing column: {right_reason} · {detail2[:160]}")
        caught.append(any(name.startswith("2 ") for name in red) and right_reason)
    # B: the time gate reads scores 150 days before they are published; check 5 must go red
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        scripts = work / "scripts"
        shutil.copytree(HERE, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        source = (scripts / "ghost_backtest_v2.py").read_text(encoding="utf-8")
        if source.count(TIME_GATE) != 1:
            print(f"break B could not be applied: the time gate line {TIME_GATE!r} is not in ghost_backtest_v2.py exactly once")
            caught.append(False)
        else:
            (scripts / "ghost_backtest_v2.py").write_text(
                source.replace(TIME_GATE, 'eligible = df[df["available_date"] <= rdate + pd.Timedelta(days=150)]'), encoding="utf-8")
            name, ok, detail = ("5 no lookahead", *check_no_lookahead(scripts, work))
            # the failure must be the measured leak (both runs finished and the 45-day gap left the band), not a crash
            measured = detail.startswith("high-ghost minus low-ghost total return")
            print(f"break B (time gate reads scores 150 days early): check 5 "
                  f"{'PASS — NOT CAUGHT' if ok else 'FAIL as it must'} · failed on the measurement, not a crash: {measured} — {detail}")
            caught.append(not ok and measured)
    n = sum(caught)
    print(f"BREAK PASS {n}/{len(caught)} breaks caught" if all(caught) else f"BREAK FAIL {n}/{len(caught)} breaks caught")
    return 0 if all(caught) else 1


if __name__ == "__main__":
    sys.exit(main())
