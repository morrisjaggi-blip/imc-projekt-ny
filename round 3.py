from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json
import math


class Trader:
    PRODUCT = "HYDROGEL_PACK"
    LIMIT = 200

    def bid(self):
        return 15

    def load_data(self, traderData: str) -> Dict:
        if traderData:
            try:
                return json.loads(traderData)
            except Exception:
                pass
        return {"mid_history": []}

    def save_data(self, data: Dict) -> str:
        return json.dumps(data)

    def run(self, state: TradingState):
        result = {}
        data = self.load_data(state.traderData)

        product = self.PRODUCT
        orders: List[Order] = []

        if product not in state.order_depths:
            return result, 0, self.save_data(data)

        order_depth: OrderDepth = state.order_depths[product]
        position = state.position.get(product, 0)

        if not order_depth.buy_orders or not order_depth.sell_orders:
            result[product] = orders
            return result, 0, self.save_data(data)

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        best_bid_volume = order_depth.buy_orders[best_bid]
        best_ask_volume = order_depth.sell_orders[best_ask]

        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

        history = data.get("mid_history", [])
        history.append(mid)

        if len(history) > 120:
            history = history[-120:]

        data["mid_history"] = history

        if len(history) >= 20:
            rolling_mean = sum(history[-60:]) / len(history[-60:])
            variance = sum((x - rolling_mean) ** 2 for x in history[-60:]) / len(history[-60:])
            rolling_std = math.sqrt(variance) if variance > 1e-9 else 1
        else:
            rolling_mean = mid
            rolling_std = 1

        z = (mid - rolling_mean) / rolling_std

        # Mean-reversion fair value:
        # If price is above rolling mean, fair value shifts lower.
        # If price is below rolling mean, fair value shifts higher.
        fair_value = mid - 1.8 * z

        # Inventory skew:
        # Long inventory -> lower fair value to encourage selling.
        # Short inventory -> higher fair value to encourage buying.
        inventory_skew = -0.045 * position
        fair_value += inventory_skew

        buy_capacity = self.LIMIT - position
        sell_capacity = self.LIMIT + position

        # 1. Aggressive taking when market is clearly favorable
        edge = 2.0

        for ask_price in sorted(order_depth.sell_orders.keys()):
            ask_volume = -order_depth.sell_orders[ask_price]

            if ask_price < fair_value - edge and buy_capacity > 0:
                qty = min(ask_volume, buy_capacity)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    buy_capacity -= qty
            else:
                break

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            bid_volume = order_depth.buy_orders[bid_price]

            if bid_price > fair_value + edge and sell_capacity > 0:
                qty = min(bid_volume, sell_capacity)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    sell_capacity -= qty
            else:
                break

        # 2. Passive market making
        base_half_spread = 8

        # Widen quotes when spread is compressed or volatility is high
        if spread < 14:
            quote_half_spread = 10
        elif abs(z) > 1.5:
            quote_half_spread = 9
        else:
            quote_half_spread = base_half_spread

        reservation_price = fair_value

        bid_price = int(round(reservation_price - quote_half_spread))
        ask_price = int(round(reservation_price + quote_half_spread))

        # Avoid crossing the book unintentionally
        bid_price = min(bid_price, best_bid + 1)
        ask_price = max(ask_price, best_ask - 1)

        # Keep prices logically separated
        if bid_price >= ask_price:
            bid_price = int(math.floor(mid - 1))
            ask_price = int(math.ceil(mid + 1))

        # Inventory-aware sizing
        max_passive_size = 35

        buy_size = min(max_passive_size, buy_capacity)
        sell_size = min(max_passive_size, sell_capacity)

        # Reduce buying when already long; reduce selling when already short
        if position > 80:
            buy_size = min(buy_size, 10)
        if position < -80:
            sell_size = min(sell_size, 10)

        # Strongly skew at extremes
        if position > 150:
            buy_size = 0
        if position < -150:
            sell_size = 0

        if buy_size > 0:
            orders.append(Order(product, bid_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, ask_price, -sell_size))

        result[product] = orders

        conversions = 0
        traderData = self.save_data(data)

        return result, conversions, traderData
