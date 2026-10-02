import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.config import settings
from bot.execution.roostoo_client import RoostooClient

def run_tests():
    print("1. Initializing Roostoo Client")
    client = RoostooClient(api_key=settings.ROOSTOO_API_KEY, secret_key=settings.ROOSTOO_SECRET_KEY, base_url=settings.ROOSTOO_BASE_URL)

    print("\n2. Testing Server Time and Exchange Info")
    server_time = client.check_server_time()
    print("Server Time Response:", server_time)

    exchange_info = client.get_exchange_info()
    print("Exchange Info Keys:", list(exchange_info.keys()))

    print("\n3. Testing Ticker Data")
    ticker = client.get_ticker("BTC/USD")
    print("BTC/USD Ticker:", ticker)

    print("\n4. Testing Account Balances")
    balance = client.get_balance()
    print("Account Balance:", balance)

    print("\n5. Testing Order Queries")
    pending_count = client.get_pending_count()
    print("Pending Orders Count:", pending_count)

    orders = client.query_order(pair="BTC/USD", pending_only=True)
    print("Pending Orders for BTC/USD:", orders)

    print("\n6. Testing Short Positions Info")
    shorts = client.get_short_positions(pair="BTC/USD")
    print("Short Positions:", shorts)

    print("\n7. Executing Live Test Order (Trade Logging Test)")
    ticker_data = ticker.get("Data", {}).get("BTC/USD", {})
    last_price = ticker_data.get("LastPrice", 80000)
    target_price = round(last_price * 0.90, 2)

    buy_order = client.place_order(
        pair="BTC/USD",
        side="BUY",
        quantity=0.001,
        price=target_price,
        order_type="LIMIT"
    )
    print("Place Order Response:", buy_order)

    order_detail = buy_order.get("OrderDetail", {})
    order_id = order_detail.get("OrderID") or buy_order.get("OrderId") or buy_order.get("order_id")

    if order_id:
        print(f"\n8. Canceling Test Order ID: {order_id}")
        cancel_res = client.cancel_order(order_id=order_id, pair="BTC/USD")
        print("Cancel Response:", cancel_res)
    else:
        print("\n8. Could not extract OrderID from response")   

if __name__ == "__main__":
    run_tests()