from datamodel import Order, TradingState, OrderDepth
from typing import Dict, List
import json


class Trader:
    LIMIT = 10

    # Mean reversion (single EMA)
    EMA_TRADERS = {
        "PEBBLES_XL":           {"alpha": 0.010, "edge": 28.0, "max_take": 2},
        "ROBOT_DISHES":         {"alpha": 0.010, "edge": 10.0, "max_take": 3},
        "TRANSLATOR_ASTRO_BLACK": {"alpha": 0.002, "edge": 28.0, "max_take": 2},
        "ROBOT_LAUNDRY":        {"alpha": 0.005, "edge": 28.0, "max_take": 1},
        "PEBBLES_L":            {"alpha": 0.005, "edge": 28.0, "max_take": 1},
        "PEBBLES_S":            {"alpha": 0.002, "edge": 28.0, "max_take": 3},
        "ROBOT_VACUUMING":      {"alpha": 0.002, "edge": 28.0, "max_take": 1},
    }

    # Dual-EMA momentum (fast vs slow crossover)
    MOMENTUM_TRADERS = {
        "PEBBLES_XS":           {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "PEBBLES_M":            {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "SLEEP_POD_COTTON":     {"af": 0.05, "as": 0.040, "edge": 12.0, "max_take": 3},
        "MICROCHIP_SQUARE":     {"af": 0.05, "as": 0.040, "edge": 16.0, "max_take": 1},
        "ROBOT_MOPPING":        {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 3},
        "PANEL_2X4":            {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "MICROCHIP_RECTANGLE":  {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 2},
        "OXYGEN_SHAKE_MORNING_BREATH": {"af": 0.03, "as": 0.020, "edge": 16.0, "max_take": 3},
        "GALAXY_SOUNDS_SOLAR_WINDS": {"af": 0.05, "as": 0.040, "edge": 8.0, "max_take": 3},
        "PANEL_1X4":            {"af": 0.03, "as": 0.005, "edge": 12.0, "max_take": 3},
        "TRANSLATOR_ECLIPSE_CHARCOAL": {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 3},
        "MICROCHIP_TRIANGLE":   {"af": 0.03, "as": 0.020, "edge": 8.0, "max_take": 3},
        "GALAXY_SOUNDS_DARK_MATTER": {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "TRANSLATOR_SPACE_GRAY": {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "TRANSLATOR_GRAPHITE_MIST": {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 1},
        "GALAXY_SOUNDS_SOLAR_FLAMES": {"af": 0.05, "as": 0.040, "edge": 12.0, "max_take": 3},
        "SLEEP_POD_NYLON":      {"af": 0.03, "as": 0.040, "edge": 8.0, "max_take": 3},
        "SNACKPACK_RASPBERRY":  {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 3},
        "UV_VISOR_MAGENTA":     {"af": 0.03, "as": 0.040, "edge": 8.0, "max_take": 2},
        "MICROCHIP_CIRCLE":     {"af": 0.05, "as": 0.040, "edge": 12.0, "max_take": 2},
        "OXYGEN_SHAKE_CHOCOLATE": {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "UV_VISOR_AMBER":       {"af": 0.05, "as": 0.040, "edge": 8.0, "max_take": 1},
        "SLEEP_POD_POLYESTER":  {"af": 0.03, "as": 0.040, "edge": 8.0, "max_take": 3},
        "OXYGEN_SHAKE_GARLIC":  {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 3},
        "PANEL_4X4":            {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 3},
        "GALAXY_SOUNDS_BLACK_HOLES": {"af": 0.03, "as": 0.005, "edge": 16.0, "max_take": 3},
        "PANEL_2X2":            {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 2},
        "SNACKPACK_VANILLA":    {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 2},
        "MICROCHIP_OVAL":       {"af": 0.03, "as": 0.020, "edge": 12.0, "max_take": 3},
        "UV_VISOR_RED":         {"af": 0.03, "as": 0.020, "edge": 12.0, "max_take": 1},
        "ROBOT_IRONING":        {"af": 0.05, "as": 0.020, "edge": 8.0, "max_take": 1},
        "SNACKPACK_CHOCOLATE":  {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 3},
    }

    # Bid-ask imbalance (volume pressure)
    IMBALANCE_TRADERS = {
        "UV_VISOR_ORANGE":              {"thr": 0.1, "max_take": 2},
        "SLEEP_POD_SUEDE":              {"thr": 0.4, "max_take": 1},
        "OXYGEN_SHAKE_MINT":            {"thr": 0.5, "max_take": 2},
        "PANEL_1X2":                    {"thr": 0.4, "max_take": 3},
        "TRANSLATOR_VOID_BLUE":         {"thr": 0.3, "max_take": 2},
        "GALAXY_SOUNDS_PLANETARY_RINGS": {"thr": 0.5, "max_take": 1},
        "OXYGEN_SHAKE_EVENING_BREATH":  {"thr": 0.1, "max_take": 3},
        "SLEEP_POD_LAMB_WOOL":          {"thr": 0.2, "max_take": 3},
        "SNACKPACK_STRAWBERRY":         {"thr": 0.1, "max_take": 3},
        "SNACKPACK_PISTACHIO":          {"thr": 0.1, "max_take": 3},
    }

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        try:
            data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            data = {}
        ema = data.get("ema", {})
        ema_fast = data.get("ema_fast", {})
        ema_slow = data.get("ema_slow", {})

        for sym, cfg in self.EMA_TRADERS.items():
            depth = state.order_depths.get(sym)
            mid = self._mid(depth)
            if mid is None:
                continue
            ema[sym] = cfg["alpha"] * mid + (1 - cfg["alpha"]) * ema.get(sym, mid)

        for sym, cfg in self.MOMENTUM_TRADERS.items():
            depth = state.order_depths.get(sym)
            mid = self._mid(depth)
            if mid is None:
                continue
            ema_fast[sym] = cfg["af"] * mid + (1 - cfg["af"]) * ema_fast.get(sym, mid)
            ema_slow[sym] = cfg["as"] * mid + (1 - cfg["as"]) * ema_slow.get(sym, mid)

        for sym, cfg in self.EMA_TRADERS.items():
            self._ema_take(state, result, sym, ema, cfg)

        for sym, cfg in self.MOMENTUM_TRADERS.items():
            self._momentum_take(state, result, sym, ema_fast, ema_slow, cfg)

        for sym, cfg in self.IMBALANCE_TRADERS.items():
            self._imbalance_take(state, result, sym, cfg)

        data["ema"] = ema
        data["ema_fast"] = ema_fast
        data["ema_slow"] = ema_slow
        return result, 0, json.dumps(data)

    def _mid(self, depth: OrderDepth):
        if not depth or not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2

    def _ema_take(self, state, result, sym, ema, cfg):
        depth = state.order_depths.get(sym)
        if not depth or not depth.buy_orders or not depth.sell_orders:
            return
        fair = ema.get(sym)
        if fair is None:
            return
        pos = state.position.get(sym, 0)
        edge = cfg["edge"]
        max_take = cfg["max_take"]
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        orders: List[Order] = []

        for ask_price in sorted(depth.sell_orders.keys()):
            if ask_price <= fair - edge and buy_cap > 0:
                vol = min(-depth.sell_orders[ask_price], buy_cap, max_take)
                if vol > 0:
                    orders.append(Order(sym, ask_price, vol))
                    buy_cap -= vol
            else:
                break

        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_price >= fair + edge and sell_cap > 0:
                vol = min(depth.buy_orders[bid_price], sell_cap, max_take)
                if vol > 0:
                    orders.append(Order(sym, bid_price, -vol))
                    sell_cap -= vol
            else:
                break

        if orders:
            result[sym] = orders

    def _momentum_take(self, state, result, sym, ema_fast, ema_slow, cfg):
        depth = state.order_depths.get(sym)
        if not depth or not depth.buy_orders or not depth.sell_orders:
            return
        ef = ema_fast.get(sym)
        es = ema_slow.get(sym)
        if ef is None or es is None:
            return
        edge = cfg["edge"]
        max_take = cfg["max_take"]
        pos = state.position.get(sym, 0)
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        orders: List[Order] = []

        if ef > es + edge and buy_cap > 0:
            for ask_price in sorted(depth.sell_orders.keys()):
                if buy_cap <= 0:
                    break
                vol = min(-depth.sell_orders[ask_price], buy_cap, max_take)
                if vol > 0:
                    orders.append(Order(sym, ask_price, vol))
                    buy_cap -= vol
                    break
        elif ef < es - edge and sell_cap > 0:
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if sell_cap <= 0:
                    break
                vol = min(depth.buy_orders[bid_price], sell_cap, max_take)
                if vol > 0:
                    orders.append(Order(sym, bid_price, -vol))
                    sell_cap -= vol
                    break

        if orders:
            result[sym] = orders

    def _imbalance_take(self, state, result, sym, cfg):
        depth = state.order_depths.get(sym)
        if not depth or not depth.buy_orders or not depth.sell_orders:
            return
        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        bv = depth.buy_orders[best_bid]
        av = -depth.sell_orders[best_ask]
        total = bv + av
        if total < 1:
            return
        imb = (bv - av) / total
        thr = cfg["thr"]
        max_take = cfg["max_take"]
        pos = state.position.get(sym, 0)
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        orders: List[Order] = []

        if imb > thr and buy_cap > 0:
            vol = min(av, buy_cap, max_take)
            if vol > 0:
                orders.append(Order(sym, best_ask, vol))
        elif imb < -thr and sell_cap > 0:
            vol = min(bv, sell_cap, max_take)
            if vol > 0:
                orders.append(Order(sym, best_bid, -vol))

        if orders:
            result[sym] = orders
