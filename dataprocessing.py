from __future__ import annotations

from pathlib import Path
import argparse
import csv
import re
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt


PRICE_COLS_BID = ["bid_price_1", "bid_price_2", "bid_price_3"]
PRICE_COLS_ASK = ["ask_price_1", "ask_price_2", "ask_price_3"]
VOL_COLS_BID = ["bid_volume_1", "bid_volume_2", "bid_volume_3"]
VOL_COLS_ASK = ["ask_volume_1", "ask_volume_2", "ask_volume_3"]


def load_prosperity_csv(path: str | Path) -> pd.DataFrame:
    path = _resolve_input_path(path)
    header = _locate_header(path)
    sep = _detect_separator(header)
    skiprows = _count_preamble_lines(path, header)

    try:
        df = pd.read_csv(path, sep=sep, skiprows=skiprows)
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"{path}: could not parse file as a delimited table. "
            f"Detected separator {sep!r} and header {header!r}. "
            "Check whether this is the expected Prosperity prices export."
        ) from exc

    required = {
        "day", "timestamp", "product",
        "bid_price_1", "bid_volume_1",
        "bid_price_2", "bid_volume_2",
        "ask_price_1", "ask_volume_1",
        "ask_price_2", "ask_volume_2",
        "mid_price",
    }
    missing = required - set(df.columns)
    if missing:
        if {"symbol", "buyer", "seller", "currency", "price", "quantity"}.issubset(df.columns):
            raise ValueError(
                f"{path}: this looks like a trades file, but the script expects order-book price files "
                "with columns like day, timestamp, product, bid_price_1, ask_price_1, and mid_price."
            )
        raise ValueError(f"{path}: missing required columns: {sorted(missing)}")

    return df.sort_values(["day", "timestamp", "product"]).reset_index(drop=True)


def parse_day_from_filename(path: str | Path) -> int:
    match = re.search(r"day_(-?\d+)", Path(path).name)
    if not match:
        raise ValueError(f"{path}: could not infer day from filename")
    return int(match.group(1))


def load_trades_csv(path: str | Path) -> pd.DataFrame:
    path = _resolve_input_path(path)
    header = _locate_header(path)
    sep = _detect_separator(header)
    skiprows = _count_preamble_lines(path, header)

    try:
        df = pd.read_csv(path, sep=sep, skiprows=skiprows)
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"{path}: could not parse file as a delimited table. "
            f"Detected separator {sep!r} and header {header!r}. "
            "Check whether this is the expected Prosperity trades export."
        ) from exc

    required = {"timestamp", "symbol", "price", "quantity"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns: {sorted(missing)}")

    out = df.rename(columns={"symbol": "product"}).copy()
    out["day"] = parse_day_from_filename(path)
    return out.sort_values(["day", "timestamp", "product"]).reset_index(drop=True)


def _resolve_input_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"Could not find input file {candidate!s}. "
        "Pass a valid relative or absolute path."
    )


def _locate_header(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for line in fh:
            candidate = line.strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if "timestamp" in lowered and (
                "product" in lowered or "symbol" in lowered or "bid_price_1" in lowered
            ):
                return candidate
    raise ValueError(f"{path}: could not find a recognizable header row")


def _detect_separator(header: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(header, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        for sep in (";", ",", "\t", "|"):
            if sep in header:
                return sep
    raise ValueError(f"Could not detect delimiter from header: {header!r}")


def _count_preamble_lines(path: Path, header: str) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for idx, line in enumerate(fh):
            if line.strip() == header:
                return idx
    return 0


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["best_bid"] = out[PRICE_COLS_BID].max(axis=1, skipna=True)
    out["best_ask"] = out[PRICE_COLS_ASK].min(axis=1, skipna=True)

    recomputed_mid = (out["best_bid"] + out["best_ask"]) / 2
    out["mid_price_clean"] = out["mid_price"].where(out["mid_price"].notna(), recomputed_mid)

    out["spread"] = out["best_ask"] - out["best_bid"]

    out["total_bid_volume"] = out[VOL_COLS_BID].fillna(0).sum(axis=1)
    out["total_ask_volume"] = out[VOL_COLS_ASK].fillna(0).sum(axis=1)

    top_denom = out["bid_volume_1"] + out["ask_volume_1"]
    full_denom = out["total_bid_volume"] + out["total_ask_volume"]

    out["imbalance_top"] = np.where(
        top_denom > 0,
        (out["bid_volume_1"] - out["ask_volume_1"]) / top_denom,
        np.nan,
    )

    out["imbalance_full"] = np.where(
        full_denom > 0,
        (out["total_bid_volume"] - out["total_ask_volume"]) / full_denom,
        np.nan,
    )

    # Rolling diagnostics must be computed within each product/day stream.
    out = out.sort_values(["product", "day", "timestamp"]).reset_index(drop=True)
    g = out.groupby(["product", "day"], group_keys=False)

    out["mid_rolling_50"] = g["mid_price_clean"].transform(
        lambda s: s.rolling(50, min_periods=1).mean()
    )
    out["spread_rolling_50"] = g["spread"].transform(
        lambda s: s.rolling(50, min_periods=1).mean()
    )

    return out


def sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(name))


def plot_empirical_pmf(
    values: pd.Series,
    xlabel: str,
    title: str,
    output_path: Path,
) -> None:
    clean = values.dropna()
    if clean.empty:
        return

    pmf = clean.value_counts(normalize=True).sort_index()

    plt.figure(figsize=(10, 5))
    plt.bar(pmf.index.astype(str), pmf.values, width=0.8)
    plt.xlabel(xlabel)
    plt.ylabel("Probability")
    plt.title(title)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def plot_product_day(
    df: pd.DataFrame,
    trades_df: pd.DataFrame,
    product: str,
    day: int,
    output_dir: Path,
) -> None:
    subset = df[(df["product"] == product) & (df["day"] == day)].copy()
    if subset.empty:
        return

    subset = subset.sort_values("timestamp")
    t = subset["timestamp"] // 100
    trades_subset = trades_df[
        (trades_df["product"] == product) & (trades_df["day"] == day)
    ].copy()

    # Price-time
    plt.figure(figsize=(20, 6))
    plt.plot(t, subset["mid_price_clean"], label="Mid price")
    plt.plot(t, subset["best_bid"], linestyle="--", label="Best bid")
    plt.plot(t, subset["best_ask"], linestyle="--", label="Best ask")
    #plt.plot(t, subset["mid_rolling_50"], linestyle=":", label="Mid (rolling 50)")
    plt.xlabel("Time step")
    plt.ylabel("Price")
    plt.title(f"{product} | Day {day} | Price-time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"{sanitize(product)}_day_{day}_price_time.png", dpi=180)
    plt.close()

    # Spread-time
    plt.figure(figsize=(12, 5))
    plt.plot(t, subset["spread"], label="Spread")
    plt.plot(t, subset["spread_rolling_50"], linestyle=":", label="Spread (rolling 50)")
    plt.xlabel("Time step")
    plt.ylabel("Spread")
    plt.title(f"{product} | Day {day} | Spread-time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"{sanitize(product)}_day_{day}_spread_time.png", dpi=180)
    plt.close()

    plot_empirical_pmf(
        subset["spread"],
        xlabel="Spread",
        title=f"{product} | Day {day} | Spread PMF",
        output_path=output_dir / f"{sanitize(product)}_day_{day}_spread_pmf.png",
    )

    # Volume-time
    plt.figure(figsize=(12, 5))
    plt.plot(t, subset["total_bid_volume"], label="Total visible bid volume")
    plt.plot(t, subset["total_ask_volume"], label="Total visible ask volume")
    plt.xlabel("Time step")
    plt.ylabel("Volume")
    plt.title(f"{product} | Day {day} | Visible volume-time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"{sanitize(product)}_day_{day}_volume_time.png", dpi=180)
    plt.close()

    # Imbalance-time
    plt.figure(figsize=(12, 5))
    plt.plot(t, subset["imbalance_top"], label="Top-of-book imbalance")
    plt.plot(t, subset["imbalance_full"], label="Full visible-book imbalance")
    plt.xlabel("Time step")
    plt.ylabel("Imbalance")
    plt.title(f"{product} | Day {day} | Order-book imbalance")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / f"{sanitize(product)}_day_{day}_imbalance_time.png", dpi=180)
    plt.close()

    if not trades_subset.empty:
        plot_empirical_pmf(
            trades_subset["price"],
            xlabel="Trade price",
            title=f"{product} | Day {day} | Price PMF",
            output_path=output_dir / f"{sanitize(product)}_day_{day}_price_pmf.png",
        )


def summarize_product_day(df: pd.DataFrame) -> pd.DataFrame:
    summary = df.groupby(["day", "product"], as_index=False).agg(
        n_rows=("timestamp", "size"),
        t_min=("timestamp", "min"),
        t_max=("timestamp", "max"),
        mid_mean=("mid_price_clean", "mean"),
        mid_std=("mid_price_clean", "std"),
        spread_mean=("spread", "mean"),
        spread_std=("spread", "std"),
        spread_min=("spread", "min"),
        spread_max=("spread", "max"),
        bid_vol_mean=("total_bid_volume", "mean"),
        ask_vol_mean=("total_ask_volume", "mean"),
        imbalance_full_mean=("imbalance_full", "mean"),
        imbalance_full_std=("imbalance_full", "std"),
    )
    return summary.sort_values(["product", "day"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prosperity order book visualizer")
    parser.add_argument("csv_files", nargs="+", help="One or more Prosperity CSV files")
    parser.add_argument(
        "--output-dir",
        default="prosperity_plots",
        help="Directory where plots and summary CSV are written",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    price_frames = []
    trade_frames = []
    skipped = []
    for path in args.csv_files:
        try:
            price_frames.append(load_prosperity_csv(path))
        except ValueError as exc:
            message = str(exc)
            if "looks like a trades file" in message:
                trade_frames.append(load_trades_csv(path))
                continue
            if "could not parse file as a delimited table" in message:
                skipped.append(message)
                continue
            raise

    if skipped:
        for message in skipped:
            print(f"Skipping file: {message}")

    if not price_frames:
        raise ValueError(
            "No usable price files were provided. Pass one or more Prosperity prices CSV files."
        )

    raw = pd.concat(price_frames, ignore_index=True)
    trades = (
        pd.concat(trade_frames, ignore_index=True)
        if trade_frames
        else pd.DataFrame(columns=["timestamp", "product", "price", "quantity", "day"])
    )

    feat = add_features(raw)

    for product in sorted(feat["product"].dropna().unique()):
        for day in sorted(feat["day"].dropna().unique()):
            plot_product_day(feat, trades, product, day, output_dir)

    summary = summarize_product_day(feat)
    summary.to_csv(output_dir / "summary_by_day_product.csv", index=False)

    print(f"Done. Output written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
