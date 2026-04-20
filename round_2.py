
from datamodel import Order, TradingState, OrderDepth
from typing import List, Dict
import jsonpickle


class Trader:
    POSITION_LIMIT = 80

    def bid(self):
        # Required only in Round 2, ignored otherwise
        return 1300

    def _load_state(self, trader_data: str) -> Dict:
        if trader_data:
            try:
                data = jsonpickle.decode(trader_data)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_state(self, data: Dict) -> str:
        return jsonpickle.encode(data)

    def _clip(self, x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        result: Dict[str, List[Order]] = {}
        conversions = 0
        stored = self._load_state(state.traderData)

        # -----------------------------
        # ASH_COATED_OSMIUM
        # -----------------------------
        OSMIUM = "ASH_COATED_OSMIUM"
        if OSMIUM in state.order_depths:
            orders: List[Order] = []

            # Fair value parameters
            ALPHA = 0.12   # EMA update rate for anchor
            BETA = 0.25    # Mean-reversion strength
            ETA = 0.05     # Inventory term in fair value

            # Sizing parameters
            BASE_SIZE = 12
            K = 1.5        # Edge sensitivity
            C = 0.12       # Inventory sensitivity

            order_depth: OrderDepth = state.order_depths[OSMIUM]

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[OSMIUM] = orders
            else:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2

                position = state.position.get(OSMIUM, 0)

                previous_anchor = stored.get(OSMIUM, mid_price)
                anchor = (1 - ALPHA) * previous_anchor + ALPHA * mid_price

                fair_value = anchor - BETA * (mid_price - anchor) - ETA * position

                print(f"OSMIUM: {OSMIUM}")
                print(f"Best bid: {best_bid}, Best ask: {best_ask}, Mid: {mid_price}")
                print(f"Anchor: {anchor}, Fair value: {fair_value}, Position: {position}")

                # Remaining legal capacity for this iteration
                buy_capacity = self.POSITION_LIMIT - position
                sell_capacity = self.POSITION_LIMIT + position

                # 1. Market taking
                for ask, amount in sorted(order_depth.sell_orders.items()):
                    available_to_buy = -amount
                    if ask < fair_value and buy_capacity > 0:
                        qty = min(available_to_buy, buy_capacity)
                        if qty > 0:
                            print("BUY", str(qty) + "x", ask)
                            orders.append(Order(OSMIUM, int(ask), int(qty)))
                            buy_capacity -= qty

                for bid_price, amount in sorted(order_depth.buy_orders.items(), reverse=True):
                    available_to_sell = amount
                    if bid_price > fair_value and sell_capacity > 0:
                        qty = min(available_to_sell, sell_capacity)
                        if qty > 0:
                            print("SELL", str(qty) + "x", bid_price)
                            orders.append(Order(OSMIUM, int(bid_price), int(-qty)))
                            sell_capacity -= qty

                # 2. Market making with pennying
                d = mid_price - fair_value
                bid_size_float = BASE_SIZE - K * d - C * position
                ask_size_float = BASE_SIZE + K * d + C * position

                desired_bid_size = max(0, int(round(bid_size_float)))
                desired_ask_size = max(0, int(round(ask_size_float)))

                bid_size = min(desired_bid_size, buy_capacity)
                ask_size = min(desired_ask_size, sell_capacity)

                our_bid = None
                our_ask = None

                improved_bid = best_bid + 1
                improved_ask = best_ask - 1

                if improved_bid < fair_value:
                    our_bid = improved_bid

                if improved_ask > fair_value:
                    our_ask = improved_ask

                # If spread is too narrow to penny on both sides, avoid crossing
                if our_bid is not None and our_ask is not None and our_bid >= our_ask:
                    our_bid = None
                    our_ask = None

                if our_bid is not None and bid_size > 0:
                    print("MAKE BUY", str(bid_size) + "x", our_bid)
                    orders.append(Order(OSMIUM, int(our_bid), int(bid_size)))

                if our_ask is not None and ask_size > 0:
                    print("MAKE SELL", str(ask_size) + "x", our_ask)
                    orders.append(Order(OSMIUM, int(our_ask), int(-ask_size)))

                stored[OSMIUM] = anchor
                result[OSMIUM] = orders

        # -----------------------------
        # INTARIAN_PEPPER_ROOT
        # -----------------------------
        PEPPER = "INTARIAN_PEPPER_ROOT"
        if PEPPER in state.order_depths:
            orders: List[Order] = []
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

            if size > 0 and position < PEPPER_LIMIT and len(depth.sell_orders) > 0:
                best_ask = min(depth.sell_orders.keys())
                ask_vol = -depth.sell_orders[best_ask]
                qty = min(PEPPER_LIMIT - position, ask_vol, size)
                if qty > 0:
                    orders.append(Order(PEPPER, int(best_ask), int(qty)))

            result[PEPPER] = orders

        traderData = self._save_state(stored)
        return result, conversions, traderData
