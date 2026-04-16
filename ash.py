from datamodel import Order, TradingState, OrderDepth
from typing import List

class Trader:
    def run(self, state: TradingState):
        result = {}
        PRODUCT = "ASH_COATED_OSMIUM"
        
        if PRODUCT not in state.order_depths:
            return result, 0, ""

        order_depth: OrderDepth = state.order_depths[PRODUCT]
        orders: List[Order] = []
        
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return result, 0, ""

        # --- PARAMETRAR ---
        FAIR_VALUE = 10000
        LIMIT = 80
        current_pos = state.position.get(PRODUCT, 0)
        
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid_price = (best_bid + best_ask) / 2

        # --- 1. AGGRESSIV SNIPING (Market Taking) ---
        # Vi tar ALLT som ligger under/över 10k för omedelbar vinst
        for ask, vol in sorted(order_depth.sell_orders.items()):
            if ask < FAIR_VALUE and current_pos < LIMIT:
                buy_qty = min(-vol, LIMIT - current_pos)
                orders.append(Order(PRODUCT, ask, buy_qty))
                current_pos += buy_qty

        for bid, vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > FAIR_VALUE and current_pos > -LIMIT:
                sell_qty = max(-vol, -LIMIT - current_pos)
                orders.append(Order(PRODUCT, bid, sell_qty))
                current_pos += sell_qty

        # --- 2. DYNAMISK BIAS & SKEW ---
        deviation = mid_price - FAIR_VALUE
        
        # Vi ökar 'gain' på positionen (current_pos / 6) för att inte fastna på 80
        # total_offset styr var vi lägger våra passiva ordrar
        total_offset = (deviation * 0.7) + (current_pos / 6)

        our_bid = int(min(best_bid + 1 - total_offset, FAIR_VALUE - 1))
        our_ask = int(max(best_ask - 1 - total_offset, FAIR_VALUE + 1))

        if our_bid >= our_ask:
            our_bid = int(mid_price - 1)
            our_ask = int(mid_price + 1)

        # --- 3. 3-LEVEL LADDERING (Maximera Fill Rate) ---
        def add_ladder(side, price, volume):
            if volume == 0: return
            # Vi delar upp volymen: 50% på bästa pris, 30% på nivå 2, 20% på nivå 3
            v1 = int(volume * 0.5)
            v2 = int(volume * 0.3)
            v3 = volume - v1 - v2
            
            step = -1 if side == "BUY" else 1
            if v1 != 0: orders.append(Order(PRODUCT, price, v1))
            if v2 != 0: orders.append(Order(PRODUCT, price + step, v2))
            if v3 != 0: orders.append(Order(PRODUCT, price + (2 * step), v3))

        # Lägg köp-stege
        if current_pos < LIMIT:
            add_ladder("BUY", our_bid, LIMIT - current_pos)

        # Lägg sälj-stege
        if current_pos > -LIMIT:
            add_ladder("SELL", our_ask, -LIMIT - current_pos)

        result[PRODUCT] = orders
        return result, 0, ""
