"""Generate bundled demo parquet fixtures for the grocery endpoints.

Produces app/fixtures/store_daily_metrics.parquet and
app/fixtures/anomaly_flags.parquet with realistic synthetic data
across 8 stores and approximately 6 months of daily observations.
The output is the API's fallback when STORE_METRICS_PATH and
ANOMALY_FLAGS_PATH are not configured to point at live ETL output.

Run after a deliberate change to demo data shape:

    venv/Scripts/python.exe scripts/generate_demo_fixtures.py

Output is committed to the repo. The script is rerun rarely.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


STORE_PROFILES = {
    1: ("suburban-family", 95000, 38.00, 0.105),
    2: ("suburban-family", 110000, 38.00, 0.105),
    3: ("suburban-family", 85000, 38.00, 0.105),
    4: ("urban-dense", 68000, 28.00, 0.115),
    5: ("urban-dense", 58000, 28.00, 0.115),
    6: ("urban-dense", 62000, 28.00, 0.115),
    7: ("value-market", 55000, 32.00, 0.120),
    8: ("value-market", 52000, 32.00, 0.120),
}

DOW_FACTOR = {
    0: 0.82,  # Mon
    1: 0.85,  # Tue
    2: 0.95,  # Wed
    3: 1.00,  # Thu
    4: 1.18,  # Fri
    5: 1.35,  # Sat
    6: 1.10,  # Sun
}

RULE_REVENUE = "revenue_band"
RULE_LABOR = "labor_pct_band"
RULE_TRANSACTIONS = "transactions_band"


def _severity_level(score: float) -> str:
    if score <= 1.0:
        return "info"
    if score <= 2.0:
        return "warning"
    return "critical"


def _build_metrics(end_date: date, days: int) -> pd.DataFrame:
    rows = []
    start = end_date - timedelta(days=days - 1)
    for i in range(days):
        day = start + timedelta(days=i)
        dow = day.weekday()
        for store_id, (profile, base_revenue, avg_ticket, labor_center) in STORE_PROFILES.items():
            noise = 1.0 + random.uniform(-0.05, 0.05)
            total_sales = round(base_revenue * DOW_FACTOR[dow] * noise, 2)
            tx_noise = 1.0 + random.uniform(-0.03, 0.03)
            transaction_count = max(1, int(round((total_sales / avg_ticket) * tx_noise)))
            avg_basket_size = round(total_sales / transaction_count, 4)
            labor_cost_pct = round(labor_center + random.uniform(-0.015, 0.015), 4)
            rows.append({
                "date": day,
                "store_id": store_id,
                "total_sales": total_sales,
                "transaction_count": transaction_count,
                "avg_basket_size": avg_basket_size,
                "labor_cost_pct": labor_cost_pct,
            })
    df = pd.DataFrame(rows)
    df = df.sort_values(["date", "store_id"]).reset_index(drop=True)
    return df


def _inject_anomalies(metrics: pd.DataFrame, target_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mutate ``metrics`` to inject ``target_count`` anomalies and return
    (mutated metrics, anomaly_flags). Mix: 60% revenue, 25% labor, 15% txn."""
    indices = random.sample(range(len(metrics)), target_count)
    flags = []

    for idx in indices:
        row = metrics.iloc[idx]
        store_id = int(row["store_id"])
        day = row["date"]
        profile, base_revenue, avg_ticket, labor_center = STORE_PROFILES[store_id]
        dow = day.weekday()
        expected_revenue = base_revenue * DOW_FACTOR[dow]

        roll = random.random()
        if roll < 0.60:
            # revenue band breach
            high_breach = random.random() < 0.5
            new_sales = round(base_revenue * (1.4 if high_breach else 0.6), 2)
            metrics.at[idx, "total_sales"] = new_sales
            new_basket = round(new_sales / max(1, row["transaction_count"]), 4)
            metrics.at[idx, "avg_basket_size"] = new_basket
            expected_low = round(expected_revenue * 0.85, 2)
            expected_high = round(expected_revenue * 1.15, 2)
            actual = new_sales
            if actual > expected_high:
                distance = round(actual - expected_high, 2)
                band_width = max(1.0, expected_high - expected_low)
                score = round(distance / band_width, 4)
            else:
                distance = round(expected_low - actual, 2)
                band_width = max(1.0, expected_high - expected_low)
                score = round(distance / band_width, 4)
            flags.append({
                "date": day,
                "store_id": store_id,
                "rule_id": RULE_REVENUE,
                "actual_value": float(actual),
                "expected_low": float(expected_low),
                "expected_high": float(expected_high),
                "distance_from_band": float(abs(distance)),
                "severity_score": float(abs(score)),
                "severity_level": _severity_level(abs(score)),
            })
        elif roll < 0.85:
            # labor pct band breach
            high_breach = random.random() < 0.5
            new_labor = round(labor_center + (0.06 if high_breach else -0.06), 4)
            metrics.at[idx, "labor_cost_pct"] = new_labor
            expected_low = round(labor_center - 0.02, 4)
            expected_high = round(labor_center + 0.02, 4)
            actual = new_labor
            if actual > expected_high:
                distance = round(actual - expected_high, 4)
                band_width = max(0.001, expected_high - expected_low)
                score = round(distance / band_width, 4)
            else:
                distance = round(expected_low - actual, 4)
                band_width = max(0.001, expected_high - expected_low)
                score = round(distance / band_width, 4)
            flags.append({
                "date": day,
                "store_id": store_id,
                "rule_id": RULE_LABOR,
                "actual_value": float(actual),
                "expected_low": float(expected_low),
                "expected_high": float(expected_high),
                "distance_from_band": float(abs(distance)),
                "severity_score": float(abs(score)),
                "severity_level": _severity_level(abs(score)),
            })
        else:
            # transactions band breach
            high_breach = random.random() < 0.5
            current_tx = int(row["transaction_count"])
            new_tx = max(1, current_tx * 2 if high_breach else current_tx // 2)
            metrics.at[idx, "transaction_count"] = new_tx
            new_basket = round(float(metrics.at[idx, "total_sales"]) / new_tx, 4)
            metrics.at[idx, "avg_basket_size"] = new_basket
            expected_tx = expected_revenue / avg_ticket
            expected_low = round(expected_tx * 0.85, 0)
            expected_high = round(expected_tx * 1.15, 0)
            actual = new_tx
            if actual > expected_high:
                distance = float(actual - expected_high)
                band_width = max(1.0, expected_high - expected_low)
                score = round(distance / band_width, 4)
            else:
                distance = float(expected_low - actual)
                band_width = max(1.0, expected_high - expected_low)
                score = round(distance / band_width, 4)
            flags.append({
                "date": day,
                "store_id": store_id,
                "rule_id": RULE_TRANSACTIONS,
                "actual_value": float(actual),
                "expected_low": float(expected_low),
                "expected_high": float(expected_high),
                "distance_from_band": float(abs(distance)),
                "severity_score": float(abs(score)),
                "severity_level": _severity_level(abs(score)),
            })

    flags_df = pd.DataFrame(flags)
    flags_df = flags_df.sort_values(["date", "store_id", "rule_id"]).reset_index(drop=True)
    return metrics, flags_df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("app/fixtures"),
        help="Directory to write parquet outputs (default: app/fixtures)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=183,
        help="Number of days of history to generate (default: 183, ~6 months)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Last date in the dataset, YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--anomalies",
        type=int,
        default=45,
        help="Approximate anomaly count to inject (default: 45, target 30–60)",
    )
    args = parser.parse_args()

    random.seed(42)
    np.random.seed(42)

    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").date()
        if args.end_date
        else date.today()
    )

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_df = _build_metrics(end_date, args.days)
    metrics_df, flags_df = _inject_anomalies(metrics_df, args.anomalies)

    metrics_path = output_dir / "store_daily_metrics.parquet"
    flags_path = output_dir / "anomaly_flags.parquet"
    metrics_df.to_parquet(metrics_path, engine="pyarrow", index=False)
    flags_df.to_parquet(flags_path, engine="pyarrow", index=False)

    print(f"Wrote {metrics_path} ({metrics_df.shape[0]} rows)")
    print(f"Wrote {flags_path} ({flags_df.shape[0]} rows)")


if __name__ == "__main__":
    main()
