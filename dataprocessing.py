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
CSV_NAME_RE = re.compile(r"^(prices|trades)_round_(-?\d+)_day_(-?\d+)\.csv$", re.IGNORECASE)


def load_prosperity_csv(path: str | Path) -> pd.DataFrame:
    path = _resolve_input_path(path)
    _, round_number, day_number = parse_csv_filename(path)
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

    out = df.copy()
    out["round"] = round_number
    out["day"] = day_number
    return out.sort_values(["round", "day", "timestamp", "product"]).reset_index(drop=True)


def parse_csv_filename(path: str | Path) -> tuple[str, int, int]:
    match = CSV_NAME_RE.match(Path(path).name)
    if not match:
        raise ValueError(
            f"{path}: expected filename like prices_round_3_day_0.csv "
            "or trades_round_3_day_0.csv"
        )
    kind, round_number, day_number = match.groups()
    return kind.lower(), int(round_number), int(day_number)


def parse_day_from_filename(path: str | Path) -> int:
    return parse_csv_filename(path)[2]


def load_trades_csv(path: str | Path) -> pd.DataFrame:
    path = _resolve_input_path(path)
    _, round_number, day_number = parse_csv_filename(path)
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
    out["round"] = round_number
    out["day"] = day_number
    return out.sort_values(["round", "day", "timestamp", "product"]).reset_index(drop=True)


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

    # Rolling diagnostics must be computed within each product/round/day stream.
    out = out.sort_values(["product", "round", "day", "timestamp"]).reset_index(drop=True)
    g = out.groupby(["product", "round", "day"], group_keys=False)

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


def plot_pmf_on_axis(ax, values: pd.Series, xlabel: str, title: str) -> bool:
    clean = values.dropna()
    if clean.empty:
        ax.set_visible(False)
        return False

    pmf = clean.value_counts(normalize=True).sort_index()
    ax.bar(pmf.index.astype(str), pmf.values, width=0.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Probability")
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=45)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
    return True


def make_panel_axes(n_panels: int):
    n_cols = min(2, n_panels)
    n_rows = int(np.ceil(n_panels / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(10 * n_cols, 5 * n_rows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[n_panels:]:
        ax.set_visible(False)
    return fig, axes


def combined_time_axis(subset: pd.DataFrame, days: list[int]) -> pd.Series:
    combined = pd.Series(index=subset.index, dtype=float)
    offset = 0
    for day in days:
        day_mask = subset["day"] == day
        day_time = (subset.loc[day_mask, "timestamp"] // 100).sort_values()
        if day_time.empty:
            continue

        shifted = day_time - day_time.iloc[0] + offset
        combined.loc[shifted.index] = shifted
        step = shifted.diff().dropna().min()
        if pd.isna(step) or step <= 0:
            step = 1
        offset = shifted.iloc[-1] + step
    return combined


def plot_product_price_time_panel(
    df: pd.DataFrame,
    product: str,
    round_number: int,
    days: list[int],
    output_dir: Path,
) -> None:
    subset = df[
        (df["product"] == product)
        & (df["round"] == round_number)
        & (df["day"].isin(days))
    ].copy()
    if subset.empty:
        return

    panels = [("Combined", subset.sort_values(["day", "timestamp"]))]
    for day in days:
        day_subset = subset[subset["day"] == day].sort_values("timestamp")
        if not day_subset.empty:
            panels.append((f"Day {day}", day_subset))

    fig, axes = make_panel_axes(len(panels))
    for ax, (title, panel_subset) in zip(axes, panels):
        if title == "Combined":
            t = combined_time_axis(panel_subset, days)
            xlabel = "Combined time step"
        else:
            t = panel_subset["timestamp"] // 100
            xlabel = "Time step"

        ax.plot(t, panel_subset["mid_price_clean"], label="Mid price")
        ax.plot(t, panel_subset["best_bid"], linestyle="--", label="Best bid")
        ax.plot(t, panel_subset["best_ask"], linestyle="--", label="Best ask")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Price")
        ax.set_title(title)
        ax.legend()

    fig.suptitle(f"{product} | Price-time")
    fig.tight_layout()
    fig.savefig(output_dir / f"{sanitize(product)}_price_time.png", dpi=180)
    plt.close(fig)


def plot_product_spread_pmf_panel(
    df: pd.DataFrame,
    product: str,
    round_number: int,
    days: list[int],
    output_dir: Path,
) -> None:
    subset = df[
        (df["product"] == product)
        & (df["round"] == round_number)
        & (df["day"].isin(days))
    ].copy()
    if subset.empty:
        return

    panels = [("Combined", subset)]
    for day in days:
        day_subset = subset[subset["day"] == day]
        if not day_subset.empty:
            panels.append((f"Day {day}", day_subset))

    fig, axes = make_panel_axes(len(panels))
    for ax, (title, panel_subset) in zip(axes, panels):
        plot_pmf_on_axis(ax, panel_subset["spread"], "Spread", title)

    fig.suptitle(f"{product} | Spread PMF")
    fig.tight_layout()
    fig.savefig(output_dir / f"{sanitize(product)}_spread_pmf.png", dpi=180)
    plt.close(fig)


def plot_product_price_pmf_panel(
    trades_df: pd.DataFrame,
    product: str,
    round_number: int,
    days: list[int],
    output_dir: Path,
) -> None:

    trades_subset = trades_df[
        (trades_df["product"] == product)
        & (trades_df["round"] == round_number)
        & (trades_df["day"].isin(days))
    ].copy()
    if trades_subset.empty:
        return

    panels = [("Combined", trades_subset)]
    for day in days:
        day_subset = trades_subset[trades_subset["day"] == day]
        if not day_subset.empty:
            panels.append((f"Day {day}", day_subset))

    fig, axes = make_panel_axes(len(panels))
    for ax, (title, panel_subset) in zip(axes, panels):
        plot_pmf_on_axis(ax, panel_subset["price"], "Trade price", title)

    fig.suptitle(f"{product} | Price PMF")
    fig.tight_layout()
    fig.savefig(output_dir / f"{sanitize(product)}_price_pmf.png", dpi=180)
    plt.close(fig)


def summarize_product_day(df: pd.DataFrame) -> pd.DataFrame:
    summary = df.groupby(["round", "day", "product"], as_index=False).agg(
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
    return summary.sort_values(["round", "product", "day"]).reset_index(drop=True)


def get_round_output_dir(output_parent: Path, round_number: int) -> Path:
    round_dir = output_parent / f"Plots_round_{round_number}"
    round_dir.mkdir(parents=True, exist_ok=True)
    return round_dir


def get_diagram_output_dirs(round_dir: Path) -> tuple[Path, Path, Path]:
    price_time_dir = round_dir / "Price-time diagrams"
    price_pmf_dir = round_dir / "Price PMFs"
    spread_pmf_dir = round_dir / "Spread PMFs"
    price_time_dir.mkdir(parents=True, exist_ok=True)
    price_pmf_dir.mkdir(parents=True, exist_ok=True)
    spread_pmf_dir.mkdir(parents=True, exist_ok=True)
    return price_time_dir, price_pmf_dir, spread_pmf_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Prosperity order book visualizer")
    parser.add_argument("csv_files", nargs="+", help="One or more Prosperity CSV files")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Parent directory where Plots_round_[round] folders are written",
    )
    args = parser.parse_args()

    output_parent = Path(args.output_dir)
    output_parent.mkdir(parents=True, exist_ok=True)

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
        else pd.DataFrame(columns=["timestamp", "product", "price", "quantity", "round", "day"])
    )

    feat = add_features(raw)

    for round_number in sorted(feat["round"].dropna().unique()):
        round_dir = get_round_output_dir(output_parent, int(round_number))
        price_time_dir, price_pmf_dir, spread_pmf_dir = get_diagram_output_dirs(round_dir)
        round_days = sorted(feat.loc[feat["round"] == round_number, "day"].dropna().unique())
        round_days = [int(day) for day in round_days]
        for product in sorted(feat.loc[feat["round"] == round_number, "product"].dropna().unique()):
            plot_product_price_time_panel(
                feat,
                product,
                int(round_number),
                round_days,
                price_time_dir,
            )
            plot_product_spread_pmf_panel(
                feat,
                product,
                int(round_number),
                round_days,
                spread_pmf_dir,
            )
        for product in sorted(trades.loc[trades["round"] == round_number, "product"].dropna().unique()):
            plot_product_price_pmf_panel(
                trades,
                product,
                int(round_number),
                round_days,
                price_pmf_dir,
            )

    summary = summarize_product_day(feat)
    for round_number in sorted(summary["round"].dropna().unique()):
        round_summary = summary[summary["round"] == round_number]
        round_dir = get_round_output_dir(output_parent, int(round_number))
        round_summary.to_csv(round_dir / "summary_by_day_product.csv", index=False)

    print(f"Done. Output written to: {output_parent.resolve()}")


if __name__ == "__main__":
    main()
