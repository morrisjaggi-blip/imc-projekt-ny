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
        
        # 1. KRASCHSÄKRING
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return result, 0, ""

        # 2. INSTÄLLNINGAR
        FAIR_VALUE = 10000
        LIMIT = 80
        current_pos = state.position.get(PRODUCT, 0)
        
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid_price = (best_bid + best_ask) / 2

        # --- 3. MARKET TAKING (SNIPING) ---
        # Vi börjar med att rensa boken på gratis pengar
        for ask, vol in sorted(order_depth.sell_orders.items()):
            if ask < FAIR_VALUE and current_pos < LIMIT:
                buy_qty = min(-vol, LIMIT - current_pos)
                orders.append(Order(PRODUCT, int(ask), buy_qty))
                current_pos += buy_qty

        for bid, vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > FAIR_VALUE and current_pos > -LIMIT:
                sell_qty = max(-vol, -LIMIT - current_pos)
                orders.append(Order(PRODUCT, int(bid), sell_qty))
                current_pos += sell_qty # sell_qty är negativt

        # --- 4. MARKET MAKING MED 3-LEVEL LADDERING ---
        # Deviation: Hur mycket 'fel' är priset just nu?
        deviation = mid_price - FAIR_VALUE
        
        # Offset: Här är hemligheten. Vi reagerar hårt på positionen (/4) 
        # för att inte fastna på 80 vid spikar.
        offset = (deviation * 0.7) + (current_pos / 4)

        # Grundpriser för våra stegar
        base_bid = int(min(best_bid + 1 - offset, FAIR_VALUE - 1))
        base_ask = int(max(best_ask - 1 - offset, FAIR_VALUE + 1))

        # Säkerhet: Lägg inte ordrar i kors
        if base_bid >= base_ask:
            base_bid, base_ask = int(mid_price - 1), int(mid_price + 1)

        # Funktion för att lägga 3-stegs-stegar
        def place_ladder(side, start_price, total_vol):
            if total_vol == 0: return
            # Fördelning: 50% / 30% / 20%
            v1 = int(total_vol * 0.5)
            v2 = int(total_vol * 0.3)
            v3 = total_vol - v1 - v2
            
            step = -1 if side == "BUY" else 1
            if abs(v1) > 0: orders.append(Order(PRODUCT, start_price, v1))
            if abs(v2) > 0: orders.append(Order(PRODUCT, start_price + step, v2))
            if abs(v3) > 0: orders.append(Order(PRODUCT, start_price + 2*step, v3))

        # Lägg köp-stege
        buy_space = LIMIT - current_pos
        if buy_space > 0:
            place_ladder("BUY", base_bid, buy_space)

        # Lägg sälj-stege
        sell_space = -LIMIT - current_pos
        if sell_space < 0:
            place_ladder("SELL", base_ask, sell_space)

        result[PRODUCT] = orders
        return result, 0, ""
