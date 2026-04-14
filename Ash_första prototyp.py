from datamodel import Order

class Trader:

    def run(self, state):
        result = {}

        product = "ASH_COATED_OSMIUM"
        orders = []

        if product not in state.order_depths:
            return {}, 0, ""

        position = state.position.get(product, 0)

        POSITION_LIMIT = 20
        ORDER_SIZE = 5

        # Basnivåer (fair value ~10000, bokspread ~16 → vi quotar tätare)
        BUY_PRICE = 9993
        SELL_PRICE = 10007

        # Lägg alltid orders (market making)
        if position < POSITION_LIMIT:
            orders.append(Order(product, BUY_PRICE, ORDER_SIZE))

        if position > -POSITION_LIMIT:
            orders.append(Order(product, SELL_PRICE, -ORDER_SIZE))

        result[product] = orders

        return result, 0, ""
