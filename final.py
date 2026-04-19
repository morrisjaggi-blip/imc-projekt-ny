from datamodel import Order, TradingState, OrderDepth
from typing import List


class Trader:
    def bid(self):
        return 1301

    def run(self, state: TradingState):
        result = {}

        # === ASH_COATED_OSMIUM: MM + sniping ===
        OSMIUM = "ASH_COATED_OSMIUM"
        if OSMIUM in state.order_depths:
            depth: OrderDepth = state.order_depths[OSMIUM]
            orders: List[Order] = []

            if depth.buy_orders and depth.sell_orders:
                FAIR_VALUE = 10000
                LIMIT = 80
                current_pos = state.position.get(OSMIUM, 0)

                best_bid = max(depth.buy_orders.keys())
                best_ask = min(depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2

                # Market taking — ta allt under/över fair
                for ask, vol in sorted(depth.sell_orders.items()):
                    if ask < FAIR_VALUE and current_pos < LIMIT:
                        buy_qty = min(-vol, LIMIT - current_pos)
                        orders.append(Order(OSMIUM, ask, buy_qty))
                        current_pos += buy_qty

                for bid, vol in sorted(depth.buy_orders.items(), reverse=True):
                    if bid > FAIR_VALUE and current_pos > -LIMIT:
                        sell_qty = max(-vol, -LIMIT - current_pos)
                        orders.append(Order(OSMIUM, bid, sell_qty))
                        current_pos += sell_qty

                # Dynamisk bias + skew
                deviation = mid_price - FAIR_VALUE
                total_offset = (deviation * 0.7) + (current_pos / 6)

                our_bid = int(min(best_bid + 1 - total_offset, FAIR_VALUE - 1))
                our_ask = int(max(best_ask - 1 - total_offset, FAIR_VALUE + 1))
                if our_bid >= our_ask:
                    our_bid = int(mid_price - 1)
                    our_ask = int(mid_price + 1)

                # 3-level ladder (50/30/20)
                def add_ladder(side, price, volume):
                    if volume == 0:
                        return
                    v1 = int(volume * 0.5)
                    v2 = int(volume * 0.3)
                    v3 = volume - v1 - v2
                    step = -1 if side == "BUY" else 1
                    if v1 != 0:
                        orders.append(Order(OSMIUM, price, v1))
                    if v2 != 0:
                        orders.append(Order(OSMIUM, price + step, v2))
                    if v3 != 0:
                        orders.append(Order(OSMIUM, price + 2 * step, v3))

                if current_pos < LIMIT:
                    add_ladder("BUY", our_bid, LIMIT - current_pos)
                if current_pos > -LIMIT:
                    add_ladder("SELL", our_ask, -LIMIT - current_pos)

                result[OSMIUM] = orders

        # === INTARIAN_PEPPER_ROOT: buy-and-hold med ordbok-signal ===
        PEPPER = "INTARIAN_PEPPER_ROOT"
        if PEPPER in state.order_depths:
            orders = []
            depth = state.order_depths[PEPPER]
            position = state.position.get(PEPPER, 0)

            PEPPER_LIMIT = 80
            BASE_SIZE = 5
            FAST_SIZE = 15

            bid_levels = len(depth.buy_orders)
            ask_levels = len(depth.sell_orders)

            if ask_levels >= 3:
                size = FAST_SIZE
            elif bid_levels >= 3:
                size = 0
            else:
                size = BASE_SIZE

            if size > 0 and position < PEPPER_LIMIT and depth.sell_orders:
                best_ask = min(depth.sell_orders.keys())
                ask_vol = -depth.sell_orders[best_ask]
                qty = min(PEPPER_LIMIT - position, ask_vol, size)
                if qty > 0:
                    orders.append(Order(PEPPER, best_ask, qty))

            result[PEPPER] = orders

        return result, 0, ""
