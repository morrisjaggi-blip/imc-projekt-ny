from datamodel import Order, TradingState, OrderDepth
from typing import Dict, List
import json


class Trader:
    LIMIT = 10

    SNACK_CHOC = "SNACKPACK_CHOCOLATE"
    SNACK_VAN = "SNACKPACK_VANILLA"
    SNACK_PAIR_MEAN = 19940.7
    SNACK_PAIR_STD = 76.2

    EMA_TRADERS = {
        "PEBBLES_XL":             {"alpha": 0.010, "edge": 28.0, "max_take": 2},
        "ROBOT_DISHES":           {"alpha": 0.010, "edge": 10.0, "max_take": 3},
        "PEBBLES_XS":             {"alpha": 0.002, "edge": 22.0, "max_take": 3},
        "TRANSLATOR_ASTRO_BLACK": {"alpha": 0.002, "edge": 28.0, "max_take": 2},
        "ROBOT_LAUNDRY":          {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "PEBBLES_S":              {"alpha": 0.002, "edge": 28.0, "max_take": 3},
        "MICROCHIP_RECTANGLE":    {"alpha": 0.005, "edge": 22.0, "max_take": 2},
        "PEBBLES_L":              {"alpha": 0.005, "edge": 28.0, "max_take": 1},
        "PEBBLES_M":              {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "GALAXY_SOUNDS_DARK_MATTER": {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "MICROCHIP_TRIANGLE":     {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "SLEEP_POD_NYLON":        {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "TRANSLATOR_VOID_BLUE":   {"alpha": 0.002, "edge": 28.0, "max_take": 3},
        "SNACKPACK_RASPBERRY":    {"alpha": 0.002, "edge": 28.0, "max_take": 3},
        "SNACKPACK_PISTACHIO":    {"alpha": 0.002, "edge": 28.0, "max_take": 1},
        "MICROCHIP_CIRCLE":       {"alpha": 0.010, "edge": 28.0, "max_take": 1},
        "TRANSLATOR_ECLIPSE_CHARCOAL": {"alpha": 0.002, "edge": 28.0, "max_take": 2},
        "OXYGEN_SHAKE_CHOCOLATE": {"alpha": 0.005, "edge": 28.0, "max_take": 2},
        "TRANSLATOR_GRAPHITE_MIST": {"alpha": 0.010, "edge": 28.0, "max_take": 2},
        "OXYGEN_SHAKE_EVENING_BREATH": {"alpha": 0.002, "edge": 10.0, "max_take": 3},
    }

    MOMENTUM_TRADERS = {
        "PANEL_1X4":                {"af": 0.05, "as": 0.005, "edge": 5.0,  "max_take": 3},
        "SLEEP_POD_COTTON":         {"af": 0.05, "as": 0.010, "edge": 8.0,  "max_take": 1},
        "SLEEP_POD_SUEDE":          {"af": 0.05, "as": 0.005, "edge": 12.0, "max_take": 3},
        "OXYGEN_SHAKE_MINT":        {"af": 0.20, "as": 0.005, "edge": 8.0,  "max_take": 3},
        "MICROCHIP_OVAL":           {"af": 0.05, "as": 0.010, "edge": 12.0, "max_take": 1},
        "ROBOT_MOPPING":            {"af": 0.20, "as": 0.005, "edge": 3.0,  "max_take": 3},
        "OXYGEN_SHAKE_MORNING_BREATH": {"af": 0.10, "as": 0.005, "edge": 5.0, "max_take": 2},
        "ROBOT_IRONING":            {"af": 0.05, "as": 0.020, "edge": 8.0,  "max_take": 1},
        "GALAXY_SOUNDS_SOLAR_FLAMES": {"af": 0.05, "as": 0.010, "edge": 8.0, "max_take": 1},
        "GALAXY_SOUNDS_SOLAR_WINDS": {"af": 0.05, "as": 0.005, "edge": 5.0, "max_take": 3},
        "PANEL_1X2":                {"af": 0.05, "as": 0.005, "edge": 12.0, "max_take": 1},
        "PANEL_4X4":                {"af": 0.05, "as": 0.010, "edge": 12.0, "max_take": 1},
        "UV_VISOR_RED":             {"af": 0.05, "as": 0.005, "edge": 8.0,  "max_take": 3},
        "MICROCHIP_SQUARE":         {"af": 0.05, "as": 0.005, "edge": 12.0, "max_take": 1},
        "ROBOT_VACUUMING":          {"af": 0.10, "as": 0.020, "edge": 8.0,  "max_take": 3},
        "PANEL_2X4":                {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "TRANSLATOR_SPACE_GRAY":    {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 1},
        "OXYGEN_SHAKE_GARLIC":      {"af": 0.08, "as": 0.040, "edge": 16.0, "max_take": 3},
        "UV_VISOR_MAGENTA":         {"af": 0.03, "as": 0.040, "edge": 8.0,  "max_take": 2},
        "GALAXY_SOUNDS_PLANETARY_RINGS": {"af": 0.05, "as": 0.040, "edge": 16.0, "max_take": 3},
        "UV_VISOR_AMBER":           {"af": 0.05, "as": 0.040, "edge": 8.0,  "max_take": 1},
        "GALAXY_SOUNDS_BLACK_HOLES": {"af": 0.03, "as": 0.005, "edge": 16.0, "max_take": 3},
        "PANEL_2X2":                {"af": 0.03, "as": 0.040, "edge": 16.0, "max_take": 2},
        "SLEEP_POD_LAMB_WOOL":      {"af": 0.20, "as": 0.040, "edge": 8.0,  "max_take": 1},
        "SNACKPACK_STRAWBERRY":     {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 2},
        "UV_VISOR_ORANGE":          {"af": 0.03, "as": 0.040, "edge": 12.0, "max_take": 1},
    }

    EMA_TRADERS_EXTRA = {
        "SLEEP_POD_POLYESTER":      {"alpha": 0.001, "edge": 40.0, "max_take": 1},
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

        for sym in self.EMA_TRADERS:
            depth = state.order_depths.get(sym)
            mid = self._mid(depth)
            if mid is None:
                continue
            alpha = self.EMA_TRADERS[sym]["alpha"]
            ema[sym] = alpha * mid + (1 - alpha) * ema.get(sym, mid)

        for sym in self.EMA_TRADERS_EXTRA:
            depth = state.order_depths.get(sym)
            mid = self._mid(depth)
            if mid is None:
                continue
            alpha = self.EMA_TRADERS_EXTRA[sym]["alpha"]
            ema[sym] = alpha * mid + (1 - alpha) * ema.get(sym, mid)

        for sym, cfg in self.MOMENTUM_TRADERS.items():
            depth = state.order_depths.get(sym)
            mid = self._mid(depth)
            if mid is None:
                continue
            ema_fast[sym] = cfg["af"] * mid + (1 - cfg["af"]) * ema_fast.get(sym, mid)
            ema_slow[sym] = cfg["as"] * mid + (1 - cfg["as"]) * ema_slow.get(sym, mid)

        for sym, cfg in self.EMA_TRADERS.items():
            self._ema_take(state, result, sym, ema, cfg)

        for sym, cfg in self.EMA_TRADERS_EXTRA.items():
            self._ema_take(state, result, sym, ema, cfg)

        for sym, cfg in self.MOMENTUM_TRADERS.items():
            self._momentum_take(state, result, sym, ema_fast, ema_slow, cfg)

        self._snack_choc_van(state, result)

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
        mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        fair = ema.get(sym, mid)
        pos = state.position.get(sym, 0)
        fair_skewed = fair
        edge = cfg["edge"]
        max_take = cfg["max_take"]

        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        orders: List[Order] = []

        for ask_price in sorted(depth.sell_orders.keys()):
            if ask_price <= fair_skewed - edge and buy_cap > 0:
                vol = min(-depth.sell_orders[ask_price], buy_cap, max_take)
                if vol > 0:
                    orders.append(Order(sym, ask_price, vol))
                    buy_cap -= vol
            else:
                break

        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_price >= fair_skewed + edge and sell_cap > 0:
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

    def _snack_choc_van(self, state, result):
        d_c = state.order_depths.get(self.SNACK_CHOC)
        d_v = state.order_depths.get(self.SNACK_VAN)
        if not d_c or not d_v:
            return
        if not (d_c.buy_orders and d_c.sell_orders and d_v.buy_orders and d_v.sell_orders):
            return

        mc = (max(d_c.buy_orders) + min(d_c.sell_orders)) / 2
        mv = (max(d_v.buy_orders) + min(d_v.sell_orders)) / 2
        z = ((mc + mv) - self.SNACK_PAIR_MEAN) / self.SNACK_PAIR_STD

        pos_c = state.position.get(self.SNACK_CHOC, 0)
        pos_v = state.position.get(self.SNACK_VAN, 0)
        o_c, o_v = [], []

        bb_c = max(d_c.buy_orders); ba_c = min(d_c.sell_orders)
        bb_v = max(d_v.buy_orders); ba_v = min(d_v.sell_orders)
        bbv_c = d_c.buy_orders[bb_c]; bav_c = -d_c.sell_orders[ba_c]
        bbv_v = d_v.buy_orders[bb_v]; bav_v = -d_v.sell_orders[ba_v]

        if z > 2.0:
            sc = self.LIMIT + pos_c; sv = self.LIMIT + pos_v
            if sc > 0:
                o_c.append(Order(self.SNACK_CHOC, bb_c, -min(sc, 5, bbv_c)))
            if sv > 0:
                o_v.append(Order(self.SNACK_VAN, bb_v, -min(sv, 5, bbv_v)))
        elif z < -2.0:
            bc = self.LIMIT - pos_c; bv = self.LIMIT - pos_v
            if bc > 0:
                o_c.append(Order(self.SNACK_CHOC, ba_c, min(bc, 5, bav_c)))
            if bv > 0:
                o_v.append(Order(self.SNACK_VAN, ba_v, min(bv, 5, bav_v)))
        elif abs(z) < 0.3:
            if pos_c > 0:
                o_c.append(Order(self.SNACK_CHOC, bb_c, -min(pos_c, 5, bbv_c)))
            elif pos_c < 0:
                o_c.append(Order(self.SNACK_CHOC, ba_c, min(-pos_c, 5, bav_c)))
            if pos_v > 0:
                o_v.append(Order(self.SNACK_VAN, bb_v, -min(pos_v, 5, bbv_v)))
            elif pos_v < 0:
                o_v.append(Order(self.SNACK_VAN, ba_v, min(-pos_v, 5, bav_v)))

        if o_c:
            result[self.SNACK_CHOC] = o_c
        if o_v:
            result[self.SNACK_VAN] = o_v
