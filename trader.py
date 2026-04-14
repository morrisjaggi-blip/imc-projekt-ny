from datamodel import Order, TradingState, OrderDepth
from typing import List

class Trader:
    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # 1. Identifiera marknadsläget
            if not order_depth.buy_orders or not order_depth.sell_orders:
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2
            current_spread = best_ask - best_bid
            
            # 2. Inställningar för produkten
            POSITION_LIMIT = 80
            current_position = state.position.get(product, 0)
            
            # Vi sätter vårt "Fair Value" till mid_price för enkelhetens skull
            fair_price = mid_price 

            # 3. Market Taking (Hämta pengar som ligger på bordet)
            # Om någon säljer under vårt fair_price, köp direkt!
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

            # 4. Market Making med Pennying & Position Shading
            # Vi vill ligga 1 steg bättre än nuvarande best_bid/ask (Pennying)
            # Men vi justerar priset baserat på hur nära limiten vi är (Shading)

            # --- Beräkna vårt Köp-pris (Bid) ---
            our_bid = best_bid + 1
            # Om vi har för mycket i lager (t.ex. > 40), sänk vårt köppris 
            # för att minska risken att vi köper ännu mer.
            if current_position > 20:
                our_bid = best_bid - 1 # Bli mindre aggressiv
            if current_position > 60:
                our_bid = best_bid - 3 # Bli väldigt defensiv

            # --- Beräkna vårt Sälj-pris (Ask) ---
            our_ask = best_ask - 1
            # Om vi har en stor kort position (t.ex. < -40), höj vårt säljpris.
            if current_position < -20:
                our_ask = best_ask + 1
            if current_position < -60:
                our_ask = best_ask + 3

            # 5. Skicka ordrarna (kontrollera mot limit)
            # Lägg Köp-order
            if current_position < POSITION_LIMIT:
                bid_size = POSITION_LIMIT - current_position
                orders.append(Order(product, int(our_bid), int(bid_size)))

            # Lägg Sälj-order
            if current_position > -POSITION_LIMIT:
                ask_size = -POSITION_LIMIT - current_position
                orders.append(Order(product, int(our_ask), int(ask_size)))

            result[product] = orders

        return result, 0, ""

