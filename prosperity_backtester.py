import argparse
import csv
import importlib.util
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Tuple

from datamodel import Listing, Observation, Order, OrderDepth, Trade, TradingState


DEFAULT_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    "VEV_4000": 300,
    "VEV_4500": 300,
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
    "VEV_6000": 300,
    "VEV_6500": 300,
}

PRICE_FILE_RE = re.compile(r"^prices_round_(?P<round>\d+)_day_(?P<day>-?\d+)\.csv$")
ROUND_DIR_RE = re.compile(r"^ROUND_(?P<round>\d+)$")
DEFAULT_TRADER_CANDIDATES = ("trader.py", "round_5.py", "round_4.py")
QUICK_TIMESTAMP_TO = 10_000


@dataclass
class BookSnapshot:
    product: str
    mid: float
    bids: List[Tuple[int, int]]
    asks: List[Tuple[int, int]]

    def to_order_depth(self) -> OrderDepth:
        depth = OrderDepth()
        for price, volume in self.bids:
            depth.buy_orders[price] = volume
        for price, volume in self.asks:
            depth.sell_orders[price] = -volume
        return depth

    @property
    def best_bid(self) -> Optional[int]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[int]:
        return self.asks[0][0] if self.asks else None


@dataclass
class Fill:
    timestamp: int
    product: str
    price: int
    quantity: int
    reason: str


@dataclass
class PassiveEvent:
    price: int
    quantity: int
    side: str


def load_trader(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Trader file not found: {path}")
    sys.path.insert(0, str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace(" ", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import trader from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Trader()


def parse_int(value: str) -> Optional[int]:
    if value == "":
        return None
    return int(float(value))


def discover_data_dirs(base_dir: Path) -> List[Path]:
    candidates: List[Tuple[int, Path]] = []
    for path in base_dir.iterdir():
        if not path.is_dir():
            continue
        match = ROUND_DIR_RE.match(path.name.upper())
        if match is None:
            continue
        if any(path.glob("prices_round_*_day_*.csv")):
            candidates.append((int(match.group("round")), path))

    return [path for _, path in sorted(candidates)]


def default_data_dir() -> Path:
    data_dirs = discover_data_dirs(Path.cwd())
    if data_dirs:
        return data_dirs[-1]
    return Path("ROUND_5")


def default_trader_path() -> Path:
    for candidate in DEFAULT_TRADER_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    return Path(DEFAULT_TRADER_CANDIDATES[0])


def discover_price_days(data_dir: Path) -> Dict[int, List[int]]:
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    if not data_dir.is_dir():
        raise NotADirectoryError(f"Data path is not a directory: {data_dir}")

    days_by_round: DefaultDict[int, List[int]] = defaultdict(list)
    for path in data_dir.glob("prices_round_*_day_*.csv"):
        match = PRICE_FILE_RE.match(path.name)
        if match is None:
            continue
        days_by_round[int(match.group("round"))].append(int(match.group("day")))

    return {
        round_number: sorted(set(days))
        for round_number, days in days_by_round.items()
    }


def resolve_data_selection(
    data_dir: Path,
    round_number: Optional[int],
    days: Optional[Iterable[int]],
) -> Tuple[int, List[int]]:
    available = discover_price_days(data_dir)
    if not available:
        raise FileNotFoundError(f"No prices_round_*_day_*.csv files found in {data_dir}")

    if round_number is None:
        if len(available) == 1:
            round_number = next(iter(available))
        else:
            dirname_match = re.search(r"ROUND_(\d+)", data_dir.name.upper())
            inferred_round = int(dirname_match.group(1)) if dirname_match else None
            if inferred_round in available:
                round_number = inferred_round
            else:
                choices = ", ".join(str(value) for value in sorted(available))
                raise ValueError(f"Multiple rounds found in {data_dir}; pass --round. Available: {choices}")

    if round_number not in available:
        choices = ", ".join(str(value) for value in sorted(available))
        raise FileNotFoundError(f"No Round {round_number} price files found in {data_dir}. Available rounds: {choices}")

    selected_days = sorted(set(days)) if days is not None else available[round_number]
    missing_days = [day for day in selected_days if day not in available[round_number]]
    if missing_days:
        available_days = ", ".join(str(value) for value in available[round_number])
        missing = ", ".join(str(value) for value in missing_days)
        raise FileNotFoundError(
            f"Missing Round {round_number} price file(s) for day(s): {missing}. "
            f"Available days: {available_days}"
        )

    return round_number, selected_days


def load_prices(
    path: Path,
    products: Optional[set] = None,
    timestamp_from: Optional[int] = None,
    timestamp_to: Optional[int] = None,
) -> Dict[Tuple[int, int], Dict[str, BookSnapshot]]:
    snapshots: Dict[Tuple[int, int], Dict[str, BookSnapshot]] = defaultdict(dict)

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            timestamp = int(row["timestamp"])
            if timestamp_from is not None and timestamp < timestamp_from:
                continue
            if timestamp_to is not None and timestamp > timestamp_to:
                continue

            product = row["product"]
            if products is not None and product not in products:
                continue

            bids: List[Tuple[int, int]] = []
            asks: List[Tuple[int, int]] = []
            for level in (1, 2, 3):
                bid_price = parse_int(row.get(f"bid_price_{level}", ""))
                bid_volume = parse_int(row.get(f"bid_volume_{level}", ""))
                ask_price = parse_int(row.get(f"ask_price_{level}", ""))
                ask_volume = parse_int(row.get(f"ask_volume_{level}", ""))
                if bid_price is not None and bid_volume is not None:
                    bids.append((bid_price, abs(bid_volume)))
                if ask_price is not None and ask_volume is not None:
                    asks.append((ask_price, abs(ask_volume)))

            bids.sort(reverse=True)
            asks.sort()
            key = (int(row["day"]), timestamp)
            snapshots[key][product] = BookSnapshot(product, float(row["mid_price"]), bids, asks)

    return dict(snapshots)


def load_trades(
    path: Path,
    products: Optional[set] = None,
    timestamp_from: Optional[int] = None,
    timestamp_to: Optional[int] = None,
) -> Dict[Tuple[int, int, str], List[Trade]]:
    trades: Dict[Tuple[int, int, str], List[Trade]] = defaultdict(list)
    if not path.exists():
        return {}

    day = int(path.stem.split("_day_")[-1])
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            timestamp = int(row["timestamp"])
            if timestamp_from is not None and timestamp < timestamp_from:
                continue
            if timestamp_to is not None and timestamp > timestamp_to:
                continue

            product = row["symbol"]
            if products is not None and product not in products:
                continue
            trade = Trade(
                product,
                int(float(row["price"])),
                int(row["quantity"]),
                row.get("buyer") or None,
                row.get("seller") or None,
                timestamp,
            )
            trades[(day, trade.timestamp, product)].append(trade)

    return dict(trades)


def infer_taker_side(trade: Trade, snapshot: BookSnapshot) -> str:
    price = int(trade.price)
    if snapshot.best_ask is not None and price >= snapshot.best_ask:
        return "buyer"
    if snapshot.best_bid is not None and price <= snapshot.best_bid:
        return "seller"
    if price >= snapshot.mid:
        return "buyer"
    return "seller"


def passive_events_for_product(
    trades: List[Trade],
    snapshot: BookSnapshot,
) -> List[PassiveEvent]:
    events: List[PassiveEvent] = []
    for trade in trades:
        events.append(
            PassiveEvent(
                int(trade.price),
                int(trade.quantity),
                infer_taker_side(trade, snapshot),
            )
        )
    return events


def limit_for_product(limits: Dict[str, int], product: str) -> int:
    return limits.get(product, 10**9)


def execute_fill(
    fills: List[Fill],
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    timestamp: int,
    product: str,
    price: int,
    quantity: int,
    reason: str,
) -> None:
    if quantity == 0:
        return
    fills.append(Fill(timestamp, product, price, quantity, reason))
    position[product] += quantity
    cash[product] -= price * quantity


def marketable_fill_buy(
    timestamp: int,
    product: str,
    order_price: int,
    remaining: int,
    asks: List[List[int]],
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    fills: List[Fill],
) -> int:
    for ask in asks:
        if remaining <= 0 or order_price < ask[0]:
            break
        fill_quantity = min(remaining, ask[1])
        if fill_quantity > 0:
            execute_fill(fills, cash, position, timestamp, product, ask[0], fill_quantity, "cross_ask")
            remaining -= fill_quantity
            ask[1] -= fill_quantity
    return remaining


def marketable_fill_sell(
    timestamp: int,
    product: str,
    order_price: int,
    remaining: int,
    bids: List[List[int]],
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    fills: List[Fill],
) -> int:
    for bid in bids:
        if remaining <= 0 or order_price > bid[0]:
            break
        fill_quantity = min(remaining, bid[1])
        if fill_quantity > 0:
            execute_fill(fills, cash, position, timestamp, product, bid[0], -fill_quantity, "cross_bid")
            remaining -= fill_quantity
            bid[1] -= fill_quantity
    return remaining


def passive_fill_quantity(event_quantity: int, ratio: float) -> int:
    if event_quantity <= 0:
        return 0
    if ratio >= 1.0:
        return event_quantity
    return max(1, int(math.floor(event_quantity * ratio)))


def passive_fill_buy(
    timestamp: int,
    product: str,
    order_price: int,
    remaining: int,
    snapshot: BookSnapshot,
    events: List[PassiveEvent],
    passive_ratio: float,
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    fills: List[Fill],
) -> int:
    for event in events:
        if remaining <= 0:
            break
        if event.side != "seller" or event.quantity <= 0 or order_price < event.price:
            continue
        ratio = 1.0 if snapshot.best_bid is not None and order_price > snapshot.best_bid else passive_ratio
        fill_quantity = min(remaining, passive_fill_quantity(event.quantity, ratio))
        if fill_quantity > 0:
            execute_fill(fills, cash, position, timestamp, product, order_price, fill_quantity, "passive_bid")
            remaining -= fill_quantity
            event.quantity -= fill_quantity
    return remaining


def passive_fill_sell(
    timestamp: int,
    product: str,
    order_price: int,
    remaining: int,
    snapshot: BookSnapshot,
    events: List[PassiveEvent],
    passive_ratio: float,
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    fills: List[Fill],
) -> int:
    for event in events:
        if remaining <= 0:
            break
        if event.side != "buyer" or event.quantity <= 0 or order_price > event.price:
            continue
        ratio = 1.0 if snapshot.best_ask is not None and order_price < snapshot.best_ask else passive_ratio
        fill_quantity = min(remaining, passive_fill_quantity(event.quantity, ratio))
        if fill_quantity > 0:
            execute_fill(fills, cash, position, timestamp, product, order_price, -fill_quantity, "passive_ask")
            remaining -= fill_quantity
            event.quantity -= fill_quantity
    return remaining


def fill_orders(
    timestamp: int,
    orders_by_product: Dict[str, List[Order]],
    snapshots: Dict[str, BookSnapshot],
    trades_by_product: Dict[str, List[Trade]],
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    limits: Dict[str, int],
    fill_mode: str,
    passive_ratio: float,
) -> List[Fill]:
    fills: List[Fill] = []
    passive_events = {
        product: passive_events_for_product(trades_by_product.get(product, []), snapshot)
        for product, snapshot in snapshots.items()
    }

    for product, orders in orders_by_product.items():
        if product not in snapshots:
            continue
        snapshot = snapshots[product]
        bids = [[price, volume] for price, volume in snapshot.bids]
        asks = [[price, volume] for price, volume in snapshot.asks]

        for order in orders:
            quantity = int(order.quantity)
            order_price = int(order.price)
            if quantity == 0:
                continue

            limit = limit_for_product(limits, product)
            if quantity > 0:
                remaining = min(quantity, max(0, limit - position[product]))
                remaining = marketable_fill_buy(
                    timestamp,
                    product,
                    order_price,
                    remaining,
                    asks,
                    cash,
                    position,
                    fills,
                )
                if fill_mode == "taker-flow" and remaining > 0:
                    passive_fill_buy(
                        timestamp,
                        product,
                        order_price,
                        remaining,
                        snapshot,
                        passive_events.get(product, []),
                        passive_ratio,
                        cash,
                        position,
                        fills,
                    )
            else:
                remaining = min(-quantity, max(0, limit + position[product]))
                remaining = marketable_fill_sell(
                    timestamp,
                    product,
                    order_price,
                    remaining,
                    bids,
                    cash,
                    position,
                    fills,
                )
                if fill_mode == "taker-flow" and remaining > 0:
                    passive_fill_sell(
                        timestamp,
                        product,
                        order_price,
                        remaining,
                        snapshot,
                        passive_events.get(product, []),
                        passive_ratio,
                        cash,
                        position,
                        fills,
                    )

    return fills


def equity_by_product(
    cash: DefaultDict[str, float],
    position: DefaultDict[str, int],
    mids: Dict[str, float],
) -> Dict[str, float]:
    products = set(cash) | set(position) | set(mids)
    return {product: cash[product] + position[product] * mids.get(product, 0.0) for product in products}


def normalize_trader_output(output, previous_trader_data: str) -> Tuple[Dict[str, List[Order]], str]:
    if isinstance(output, tuple):
        if len(output) == 3:
            result, _, trader_data = output
        elif len(output) == 2:
            result, trader_data = output
        elif len(output) == 1:
            result = output[0]
            trader_data = previous_trader_data
        else:
            raise ValueError(f"Trader.run returned an unsupported tuple of length {len(output)}")
    else:
        result = output
        trader_data = previous_trader_data

    if result is None:
        result = {}
    if trader_data is None:
        trader_data = ""

    return result, str(trader_data)


def run_single_day(
    trader,
    data_dir: Path,
    round_number: int,
    day: int,
    limits: Dict[str, int],
    fill_mode: str,
    passive_ratio: float,
    products: Optional[set],
    timestamp_from: Optional[int] = None,
    timestamp_to: Optional[int] = None,
) -> Dict:
    price_path = data_dir / f"prices_round_{round_number}_day_{day}.csv"
    trades_path = data_dir / f"trades_round_{round_number}_day_{day}.csv"
    snapshots_by_tick = load_prices(price_path, products, timestamp_from, timestamp_to)
    if not snapshots_by_tick:
        product_note = f" matching products {sorted(products)}" if products else ""
        raise ValueError(f"No price snapshots loaded from {price_path}{product_note}")
    trades = load_trades(trades_path, products, timestamp_from, timestamp_to)

    cash: DefaultDict[str, float] = defaultdict(float)
    position: DefaultDict[str, int] = defaultdict(int)
    max_abs_position: DefaultDict[str, int] = defaultdict(int)
    fill_volume: DefaultDict[str, int] = defaultdict(int)
    fill_count: DefaultDict[str, int] = defaultdict(int)

    trader_data = ""
    own_trades: Dict[str, List[Trade]] = defaultdict(list)
    equity_curve: List[Tuple[int, float]] = []
    last_mids: Dict[str, float] = {}

    for _, timestamp in sorted(snapshots_by_tick):
        if timestamp_from is not None and timestamp < timestamp_from:
            continue
        if timestamp_to is not None and timestamp > timestamp_to:
            continue
        snapshots = snapshots_by_tick[(day, timestamp)]
        last_mids.update({product: snapshot.mid for product, snapshot in snapshots.items()})
        order_depths = {product: snapshot.to_order_depth() for product, snapshot in snapshots.items()}
        market_trades = {
            product: trades.get((day, timestamp, product), [])
            for product in snapshots
        }
        listings = {
            product: Listing(product, product, "XIRECS")
            for product in snapshots
        }

        state = TradingState(
            trader_data,
            timestamp,
            listings,
            order_depths,
            dict(own_trades),
            market_trades,
            dict(position),
            Observation({}, {}),
        )

        result, trader_data = normalize_trader_output(trader.run(state), trader_data)

        fills = fill_orders(
            timestamp,
            result,
            snapshots,
            market_trades,
            cash,
            position,
            limits,
            fill_mode,
            passive_ratio,
        )

        own_trades = defaultdict(list)
        for fill in fills:
            fill_volume[fill.product] += abs(fill.quantity)
            fill_count[fill.product] += 1
            if fill.quantity > 0:
                trade = Trade(fill.product, fill.price, fill.quantity, "SUBMISSION", "", timestamp)
            else:
                trade = Trade(fill.product, fill.price, -fill.quantity, "", "SUBMISSION", timestamp)
            own_trades[fill.product].append(trade)

        for product, value in position.items():
            max_abs_position[product] = max(max_abs_position[product], abs(value))

        product_equity = equity_by_product(cash, position, last_mids)
        equity_curve.append((timestamp, sum(product_equity.values())))

    product_pnl = equity_by_product(cash, position, last_mids)
    return {
        "day": day,
        "total_pnl": sum(product_pnl.values()),
        "product_pnl": product_pnl,
        "position": dict(position),
        "cash": dict(cash),
        "last_mids": dict(last_mids),
        "fill_volume": dict(fill_volume),
        "fill_count": dict(fill_count),
        "max_abs_position": dict(max_abs_position),
        "equity_curve": equity_curve,
    }


def resolve_limits(trader) -> Dict[str, int]:
    limits = dict(DEFAULT_LIMITS)
    trader_limits = getattr(trader, "POSITION_LIMITS", None)
    if isinstance(trader_limits, dict):
        limits.update({str(product): int(limit) for product, limit in trader_limits.items()})
    return limits


def print_day_summary(summary: Dict) -> None:
    print(f"\nDay {summary['day']} total PnL: {summary['total_pnl']:.2f}")
    print(f"{'product':22s} {'pnl':>11s} {'pos':>6s} {'maxpos':>7s} {'vol':>7s} {'fills':>6s}")
    for product in sorted(summary["product_pnl"]):
        pnl = summary["product_pnl"][product]
        pos = summary["position"].get(product, 0)
        maxpos = summary["max_abs_position"].get(product, 0)
        vol = summary["fill_volume"].get(product, 0)
        fills = summary["fill_count"].get(product, 0)
        if abs(pnl) > 1e-9 or pos or vol:
            print(f"{product:22s} {pnl:11.2f} {pos:6d} {maxpos:7d} {vol:7d} {fills:6d}")

    if summary["equity_curve"]:
        best = max(summary["equity_curve"], key=lambda item: item[1])
        worst = min(summary["equity_curve"], key=lambda item: item[1])
        print(f"Best equity: {best[1]:.2f} at t={best[0]}; worst equity: {worst[1]:.2f} at t={worst[0]}")


def parse_day_values(values: Optional[List[str]]) -> Optional[List[int]]:
    if values is None:
        return None

    days: List[int] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                days.append(int(part))

    return days


def resolve_cli_paths(args: argparse.Namespace) -> Tuple[Path, Path]:
    positional_trader = args.trader_file
    positional_data_dir = args.data_directory

    if positional_trader and positional_data_dir is None:
        candidate = Path(positional_trader)
        if candidate.is_dir():
            positional_data_dir = positional_trader
            positional_trader = None
        elif ROUND_DIR_RE.match(candidate.name.upper()):
            positional_data_dir = positional_trader
            positional_trader = None

    trader_path = Path(args.trader or positional_trader) if (args.trader or positional_trader) else default_trader_path()
    data_dir = Path(args.data_dir or positional_data_dir) if (args.data_dir or positional_data_dir) else default_data_dir()
    return trader_path, data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local Prosperity CSV backtester.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 prosperity_backtester.py\n"
            "  python3 prosperity_backtester.py trader.py\n"
            "  python3 prosperity_backtester.py trader.py ROUND_5\n"
            "  python3 prosperity_backtester.py ROUND_5 --quick\n"
            "  python3 prosperity_backtester.py trader.py ROUND_5 --day 2\n"
            "  python3 prosperity_backtester.py trader.py ROUND_5 --days 2,3,4\n"
        ),
    )
    parser.add_argument(
        "trader_file",
        nargs="?",
        help="Trader Python file. Defaults to the first existing file among trader.py, round_5.py, round_4.py.",
    )
    parser.add_argument(
        "data_directory",
        nargs="?",
        help="CSV data directory. Defaults to the latest ROUND_* directory with price files.",
    )
    parser.add_argument("--trader", default=None, help="Trader file to import. Same as the first positional argument.")
    parser.add_argument("--data-dir", default=None, help="Directory containing price/trade CSV files. Same as the second positional argument.")
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        dest="round_number",
        help="Round number in CSV filenames. Defaults to the round discovered in --data-dir.",
    )
    parser.add_argument(
        "--days",
        "--day",
        "-d",
        nargs="+",
        default=None,
        help="Historical days to run. Defaults to all days discovered for the selected round.",
    )
    parser.add_argument(
        "--fill-mode",
        choices=["cross", "taker-flow"],
        default="taker-flow",
        help="cross only fills marketable orders; taker-flow also approximates passive fills from the trade tape.",
    )
    parser.add_argument(
        "--passive-ratio",
        type=float,
        default=0.25,
        help="Queue share when joining an existing best bid/ask in taker-flow mode.",
    )
    parser.add_argument("-p", "--products", nargs="*", default=None, help="Optional product subset.")
    parser.add_argument("--timestamp-from", "--from", type=int, default=None, help="Optional first timestamp to include.")
    parser.add_argument("--timestamp-to", "--to", type=int, default=None, help="Optional last timestamp to include.")
    parser.add_argument(
        "-q",
        "--quick",
        action="store_true",
        help=f"Run a short smoke test ending at timestamp {QUICK_TIMESTAMP_TO}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trader_path, data_dir = resolve_cli_paths(args)
    products = set(args.products) if args.products else None
    timestamp_to = args.timestamp_to
    if args.quick and timestamp_to is None:
        timestamp_to = QUICK_TIMESTAMP_TO

    round_number, days = resolve_data_selection(data_dir, args.round_number, parse_day_values(args.days))

    aggregate: DefaultDict[str, float] = defaultdict(float)
    total = 0.0

    print(f"Running {trader_path} on {data_dir} (round {round_number}, days {days})")

    for day in days:
        trader = load_trader(trader_path)
        limits = resolve_limits(trader)
        summary = run_single_day(
            trader,
            data_dir,
            round_number,
            day,
            limits,
            args.fill_mode,
            args.passive_ratio,
            products,
            args.timestamp_from,
            timestamp_to,
        )
        print_day_summary(summary)
        total += summary["total_pnl"]
        for product, pnl in summary["product_pnl"].items():
            aggregate[product] += pnl

    print(f"\nAggregate PnL across {len(days)} day(s): {total:.2f}")
    print(f"{'product':22s} {'pnl':>11s}")
    for product in sorted(aggregate):
        if abs(aggregate[product]) > 1e-9:
            print(f"{product:22s} {aggregate[product]:11.2f}")


if __name__ == "__main__":
    main()
