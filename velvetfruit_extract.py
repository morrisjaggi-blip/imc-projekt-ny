from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math


class Trader:
    PRODUCT = "VELVETFRUIT_EXTRACT"
    POSITION_LIMIT = 200

    BASE_SIZE = 24
    MIN_SIZE = 5

    TAKE_EDGE = 1.2
    MAKE_EDGE = 1.5

    INV_SKEW = 0.04
    EMA_ALPHA = 0.08

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except:
                data = {}

        product = self.PRODUCT

        for p in state.order_depths:
            result[p] = []

        if product not in state.order_depths:
            return result, 0, json.dumps(data)

        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []

        if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
            result[product] = orders
            return result, 0, json.dumps(data)

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        bid_vol = order_depth.buy_orders[best_bid]
        ask_vol = -order_depth.sell_orders[best_ask]

        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

        # Microprice: fair value shifted toward the side with stronger volume
        microprice = (best_ask * bid_vol + best_bid * ask_vol) / (bid_vol + ask_vol)

        old_ema = data.get("ema", mid)
        ema = self.EMA_ALPHA * mid + (1 - self.EMA_ALPHA) * old_ema
        data["ema"] = ema

        position = state.position.get(product, 0)

        # Small mean-reversion adjustment
        fair = microprice - 0.05 * (mid - ema)

        # Inventory adjustment
        fair -= position * self.INV_SKEW

        buy_capacity = self.POSITION_LIMIT - position
        sell_capacity = self.POSITION_LIMIT + position

        size = int(self.BASE_SIZE * (1 - abs(position) / self.POSITION_LIMIT))
        size = max(self.MIN_SIZE, size)

        # Selective aggressive buying
        if buy_capacity > 0 and best_ask <= fair - self.TAKE_EDGE:
            qty = min(ask_vol, buy_capacity, size)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
                buy_capacity -= qty

        # Selective aggressive selling
        if sell_capacity > 0 and best_bid >= fair + self.TAKE_EDGE:
            qty = min(bid_vol, sell_capacity, size)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))
                sell_capacity -= qty

        # Passive market making
        quote_size = max(self.MIN_SIZE, size)

        if spread >= 4:
            bid_price = min(best_bid + 1, best_ask - 1, math.floor(fair - self.MAKE_EDGE))
            ask_price = max(best_ask - 1, best_bid + 1, math.ceil(fair + self.MAKE_EDGE))

            # Stop buying if too long
            if position < 150 and buy_capacity > 0 and bid_price < best_ask:
                qty = min(quote_size, buy_capacity)
                orders.append(Order(product, bid_price, qty))

            # Stop selling if too short
            if position > -150 and sell_capacity > 0 and ask_price > best_bid:
                qty = min(quote_size, sell_capacity)
                orders.append(Order(product, ask_price, -qty))

        result[product] = orders

        conversions = 0
        traderData = json.dumps(data)

        return result, conversions, traderData
