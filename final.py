from datamodel import Order, TradingState, OrderDepth
from typing import List, Dict
import json
import math


class Trader:
    VELVET = "VELVETFRUIT_EXTRACT"
    HYDRO = "HYDROGEL_PACK"
    LIMIT = 200

    VEV_CONFIGS = {
        "VEV_5200": {"strike": 5200, "delta": 0.58, "half_spread": 1.2, "take_edge": 0.5, "size": 20, "z_coeff": 0.8},
        "VEV_5300": {"strike": 5300, "delta": 0.40, "half_spread": 0.8, "take_edge": 0.3, "size": 25, "z_coeff": 0.8},
        "VEV_5400": {"strike": 5400, "delta": 0.25, "half_spread": 0.5, "take_edge": 0.2, "size": 25, "z_coeff": 0.8},
        "VEV_5500": {"strike": 5500, "delta": 0.12, "half_spread": 0.4, "take_edge": 0.2, "size": 20, "z_coeff": 0.5},
    }

    ALL_DELTAS = {
        "VEV_4000": 1.0, "VEV_4500": 0.95, "VEV_5000": 0.85, "VEV_5100": 0.75,
        "VEV_5200": 0.58, "VEV_5300": 0.40, "VEV_5400": 0.25, "VEV_5500": 0.12,
        "VEV_6000": 0.02, "VEV_6500": 0.01,
    }

    def bid(self):
        return 1301

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        for p in state.order_depths:
            result[p] = []

        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except Exception:
                data = {}

        velvet_mid = self._get_mid(state, self.VELVET)

        self._trade_velvetfruit(state, data, result)
        self._trade_hydrogel(state, data, result)
        self._trade_vev_options(state, data, result, velvet_mid)
        self._delta_hedge(state, data, result, velvet_mid)

        return result, 0, json.dumps(data)

    # === VELVETFRUIT_EXTRACT ===

    def _trade_velvetfruit(self, state, data, result):
        product = self.VELVET
        if product not in state.order_depths:
            return
        depth = state.order_depths[product]
        if not depth.buy_orders or not depth.sell_orders:
            return

        orders: List[Order] = []
        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

        bid_vol = depth.buy_orders[best_bid]
        ask_vol = -depth.sell_orders[best_ask]
        microprice = (best_ask * bid_vol + best_bid * ask_vol) / (bid_vol + ask_vol)

        old_ema = data.get("vev_ema", mid)
        ema = 0.05 * mid + 0.95 * old_ema
        data["vev_ema"] = ema
        data["vev_prev_mid"] = data.get("vev_cur_mid", mid)
        data["vev_cur_mid"] = mid

        position = state.position.get(product, 0)
        fair = microprice + 0.3 - 0.03 * position

        buy_cap = self.LIMIT - position
        sell_cap = self.LIMIT + position

        for ask_price in sorted(depth.sell_orders.keys()):
            if ask_price <= fair - 0.5 and buy_cap > 0:
                vol = min(-depth.sell_orders[ask_price], buy_cap)
                if vol > 0:
                    orders.append(Order(product, ask_price, vol))
                    buy_cap -= vol
            else:
                break

        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_price >= fair + 0.8 and sell_cap > 0:
                vol = min(depth.buy_orders[bid_price], sell_cap)
                if vol > 0:
                    orders.append(Order(product, bid_price, -vol))
                    sell_cap -= vol
            else:
                break

        if spread >= 4:
            bid_p = min(best_bid + 1, int(math.floor(fair - 1.0)))
            ask_p = max(best_ask - 1, int(math.ceil(fair + 1.5)))
            if bid_p >= ask_p:
                bid_p = int(math.floor(mid - 1))
                ask_p = int(math.ceil(mid + 1))

            buy_size = 40
            sell_size = 40
            if position > 120:
                buy_size = 20
                sell_size = 60
            if position > 170:
                buy_size = 0
            if position < -100:
                sell_size = 20
                buy_size = 60
            if position < -170:
                sell_size = 0

            if buy_cap > 0 and buy_size > 0:
                qty = min(buy_size, buy_cap)
                orders.append(Order(product, bid_p, qty))
            if sell_cap > 0 and sell_size > 0:
                qty = min(sell_size, sell_cap)
                orders.append(Order(product, ask_p, -qty))

        result[product] = orders

    # === HYDROGEL_PACK ===

    def _trade_hydrogel(self, state, data, result):
        product = self.HYDRO
        if product not in state.order_depths:
            return
        depth = state.order_depths[product]
        if not depth.buy_orders or not depth.sell_orders:
            return

        orders: List[Order] = []
        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2

        history = data.get("hydro_hist", [])
        history.append(mid)
        if len(history) > 40:
            history = history[-40:]
        data["hydro_hist"] = history

        position = state.position.get(product, 0)

        if len(history) >= 10:
            rolling_mean = sum(history) / len(history)
            variance = sum((x - rolling_mean) ** 2 for x in history) / len(history)
            rolling_std = max(math.sqrt(variance), 3.0)
        else:
            rolling_mean = mid
            rolling_std = 10.0

        z = (mid - rolling_mean) / rolling_std
        fair = mid - 2.5 * z - 0.06 * position

        buy_cap = self.LIMIT - position
        sell_cap = self.LIMIT + position

        take_edge = 1.5 if abs(z) > 2.0 else 3.0

        for ask_price in sorted(depth.sell_orders.keys()):
            if ask_price < fair - take_edge and buy_cap > 0:
                vol = min(-depth.sell_orders[ask_price], buy_cap)
                if vol > 0:
                    orders.append(Order(product, ask_price, vol))
                    buy_cap -= vol
            else:
                break

        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_price > fair + take_edge and sell_cap > 0:
                vol = min(depth.buy_orders[bid_price], sell_cap)
                if vol > 0:
                    orders.append(Order(product, bid_price, -vol))
                    sell_cap -= vol
            else:
                break

        half_spread = 6
        if abs(z) > 1.5:
            skew = -2 if z > 0 else 2
        else:
            skew = 0

        bid_p = int(round(fair - half_spread + skew))
        ask_p = int(round(fair + half_spread + skew))

        bid_p = min(bid_p, best_bid + 1)
        ask_p = max(ask_p, best_ask - 1)

        if bid_p >= ask_p:
            bid_p = int(math.floor(mid - 1))
            ask_p = int(math.ceil(mid + 1))

        buy_size = 50
        sell_size = 50
        if position > 100:
            buy_size = 25
            sell_size = 75
        if position > 160:
            buy_size = 0
        if position < -100:
            sell_size = 25
            buy_size = 75
        if position < -160:
            sell_size = 0

        if buy_cap > 0 and buy_size > 0:
            qty = min(buy_size, buy_cap)
            orders.append(Order(product, bid_p, qty))
        if sell_cap > 0 and sell_size > 0:
            qty = min(sell_size, sell_cap)
            orders.append(Order(product, ask_p, -qty))

        result[product] = orders

    # === VEV OPTIONS ===

    def _trade_vev_options(self, state, data, result, velvet_mid):
        if velvet_mid is None:
            return

        opt_hist = data.get("opt_hist", {})
        prev_velvet = data.get("vev_prev_mid", velvet_mid)
        velvet_move = velvet_mid - prev_velvet

        for symbol, cfg in self.VEV_CONFIGS.items():
            if symbol not in state.order_depths:
                continue
            depth = state.order_depths[symbol]
            if not depth.buy_orders or not depth.sell_orders:
                continue

            orders: List[Order] = []
            best_bid = max(depth.buy_orders.keys())
            best_ask = min(depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2

            hist = opt_hist.get(symbol, [])
            hist.append(mid)
            if len(hist) > 30:
                hist = hist[-30:]
            opt_hist[symbol] = hist

            position = state.position.get(symbol, 0)

            if len(hist) >= 5:
                rolling_mean = sum(hist) / len(hist)
                variance = sum((x - rolling_mean) ** 2 for x in hist) / len(hist)
                rolling_std = max(math.sqrt(variance), 0.5)
                z = (mid - rolling_mean) / rolling_std
            else:
                z = 0

            fair = mid - cfg["z_coeff"] * z + cfg["delta"] * velvet_move - 0.02 * position

            buy_cap = self.LIMIT - position
            sell_cap = self.LIMIT + position
            take_edge = cfg["take_edge"]
            size = cfg["size"]

            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price < fair - take_edge and buy_cap > 0:
                    vol = min(-depth.sell_orders[ask_price], buy_cap, size)
                    if vol > 0:
                        orders.append(Order(symbol, ask_price, vol))
                        buy_cap -= vol
                else:
                    break

            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_price > fair + take_edge and sell_cap > 0:
                    vol = min(depth.buy_orders[bid_price], sell_cap, size)
                    if vol > 0:
                        orders.append(Order(symbol, bid_price, -vol))
                        sell_cap -= vol
                else:
                    break

            hs = cfg["half_spread"]
            bid_p = int(math.floor(fair - hs))
            ask_p = int(math.ceil(fair + hs))

            bid_p = min(bid_p, best_bid + 1)
            ask_p = max(ask_p, best_ask - 1)

            if bid_p >= ask_p:
                bid_p = int(math.floor(mid - 1))
                ask_p = int(math.ceil(mid + 1))

            if bid_p < 1:
                bid_p = 1

            if buy_cap > 0 and size > 0:
                qty = min(size, buy_cap)
                orders.append(Order(symbol, bid_p, qty))
            if sell_cap > 0 and size > 0:
                qty = min(size, sell_cap)
                orders.append(Order(symbol, ask_p, -qty))

            result[symbol] = orders

        data["opt_hist"] = opt_hist

    # === DELTA HEDGING ===

    def _delta_hedge(self, state, data, result, velvet_mid):
        if velvet_mid is None:
            return
        product = self.VELVET
        if product not in state.order_depths:
            return

        velvet_pos = state.position.get(product, 0)
        net_delta = velvet_pos

        for symbol, delta in self.ALL_DELTAS.items():
            opt_pos = state.position.get(symbol, 0)
            net_delta += opt_pos * delta

        if abs(net_delta) <= 30:
            return

        depth = state.order_depths[product]
        if not depth.buy_orders or not depth.sell_orders:
            return

        buy_cap = self.LIMIT - velvet_pos
        sell_cap = self.LIMIT + velvet_pos

        if net_delta > 30 and sell_cap > 0:
            best_bid = max(depth.buy_orders.keys())
            qty = min(int(net_delta - 15), sell_cap, 40)
            if qty > 0:
                result[product].append(Order(product, best_bid, -qty))

        elif net_delta < -30 and buy_cap > 0:
            best_ask = min(depth.sell_orders.keys())
            qty = min(int(-net_delta - 15), buy_cap, 40)
            if qty > 0:
                result[product].append(Order(product, best_ask, qty))

    # === HELPERS ===

    def _get_mid(self, state, product):
        if product not in state.order_depths:
            return None
        depth = state.order_depths[product]
        if not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2
