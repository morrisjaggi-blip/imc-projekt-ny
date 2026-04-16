from datamodel import Order, TradingState, OrderDepth
from typing import List

class Trader:
    def run(self, state: TradingState, imbalance_weight, inventory_weight):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # 1. Market Analysis
            if not order_depth.buy_orders or not order_depth.sell_orders:
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2
            current_spread = best_ask - best_bid

            # Order book imbalance
            bid_volume = sum(order_depth.buy_orders.values())
            ask_volume = sum(order_depth.sell_orders.values())
            imbalance = (bid_volume - ask_volume) / max(bid_volume + ask_volume, 1)
            
            # 2. Inventory Management
            POSITION_LIMIT = 80
            current_position = state.position.get(product, 0)
            # Inventory pressure
            inventory_ratio = current_position / POSITION_LIMIT
            
            # 3. Fair Value Computation
            # Adjust FV based on imbalance and inventory;
            # imbalance_weight and inventory_weight fitted (BUT NOT OVERFITTED) to historical data,
            # e.g. using maximum likelihood
            fair_price = (mid_price 
                  + imbalance * mid_price * imbalance_weight
                  - inventory_ratio * mid_price * inventory_weight)

            # 4. Market Taking (Take what is given to us)
            # If there are asks below our fair price, we buy immediately;
            # if there are bids above our fair price, we sell immediately.
            for ask, amount in sorted(order_depth.sell_orders.items()):
                if (ask < fair_price) and current_position < POSITION_LIMIT:
                    buy_qty = min(-amount, POSITION_LIMIT - current_position)
                    orders.append(Order(product, ask, buy_qty))
                    current_position += buy_qty

            for bid, amount in sorted(order_depth.buy_orders.items(), reverse=True):
                if (bid > fair_price) and current_position > -POSITION_LIMIT:
                    sell_qty = max(-amount, -POSITION_LIMIT - current_position)
                    orders.append(Order(product, bid, sell_qty))
                    current_position += sell_qty

            # 4. Market Making with Pennying (position shading incorporated in FV computation)
            # We position ourselves 1 XIREC better than best_bid/best_ask,
            # given that our bid/ask is still below/above the computed FV (Pennying)
            # How aggresively we position ourselves based on our inventory is managed by the dynamic FV (Shading)

            # Compute our bid
            if best_bid + 1 < fair_price:
                our_bid = best_bid + 1

            # Compute our ask
            if best_ask - 1 > fair_price:
                our_ask = best_ask - 1

            # 5. Send orders (verify that we are not exceeding position limits)
            # Buy orders
            if current_position < POSITION_LIMIT:
                bid_size = POSITION_LIMIT - current_position
                orders.append(Order(product, int(our_bid), int(bid_size)))

            # Sell orders
            if current_position > -POSITION_LIMIT:
                ask_size = -POSITION_LIMIT - current_position
                orders.append(Order(product, int(our_ask), int(ask_size)))

            result[product] = orders

        return result, 0, ""
    


