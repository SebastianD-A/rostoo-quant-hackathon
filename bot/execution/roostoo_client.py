import hashlib
import hmac
import time
import requests
from bot.config.logger import setup_logger

logger = setup_logger("RoostooClient")

class RoostooClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://mock-api.roostoo.com"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url

    def _get_timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _generate_signature_payload(self, payload: dict):
        payload["timestamp"] = self._get_timestamp()

        sorted_keys = sorted(payload.keys())
        total_params = "&".join(f"{key}={payload[key]}" for key in sorted_keys)

        #sha256 signature
        signature = hmac.new(self.secret_key.encode("utf-8"), total_params.encode("utf-8"), hashlib.sha256).hexdigest()

        headers = {
            "RST-API-KEY": self.api_key,
            "MSG-SIGNATURE": signature
        }
        
        return headers, payload, total_params
    
    def _safe_json_response(self, response: requests.Response) -> dict:
        try:
            return response.json()
        except Exception:
            logger.error(f"Failed to parse JSON response. HTTP Status Code: {response.status_code}")
            logger.error(f"Raw Response Body: {response.text[:200]}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code} - Non-JSON response received",
                "raw_body": response.text[:200]
            }

    #public endpoints
    def check_server_time(self) -> dict:
        time_url = f"{self.base_url}/v3/serverTime"

        response = requests.get(time_url)

        return response.json()

    def get_exchange_info(self) -> dict:
        ex_url = f"{self.base_url}/v3/exchangeInfo"

        response = requests.get(ex_url)
        return response.json()

    def get_ticker(self, pair: str = None) -> dict:
        ticker_url = f"{self.base_url}/v3/ticker"
        parameters = {"timestamp": self._get_timestamp()}

        if pair:
            parameters["pair"] = pair

        response = requests.get(ticker_url, params=parameters)
        return response.json()

    #signed endpoints
    def get_balance(self) -> dict:
        url = f"{self.base_url}/v3/balance"

        headers, payload, _ = self._generate_signature_payload({})

        response = requests.get(url, headers=headers, params=payload)
        return response.json()

    def get_pending_count(self) -> dict:
        url = f"{self.base_url}/v3/pending_count"

        headers, payload, _ = self._generate_signature_payload({})

        response = requests.get(url, headers=headers, params=payload)
        return response.json()

    #standard spot order
    def place_order(self, pair: str,side: str, quantity: float, price: float = None, order_type: str = "LIMIT") -> dict:
        url = f"{self.base_url}/v3/place_order"

        payload = {
            "pair": pair,
            "side": side.upper(),
            "quantity": str(quantity),
            "type": order_type.upper()
        }

        if price is not None:
            payload["price"] = str(price)

        headers, _, total_params = self._generate_signature_payload(payload)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        logger.info(f"Placing {side} order for {quantity} {pair}")
        res = requests.post(url, headers=headers, data=total_params).json()
        logger.info(f"Order response: {res}")

        return res

    def query_order(self, order_id: str = None, pair: str = None, pending_only: bool = None) -> dict:
        url = f"{self.base_url}/v3/query_order"
        payload = {}

        if order_id:
            payload["order_id"] = str(order_id)
        elif pair:
            payload["pair"] = pair

        if pending_only is not None:
            payload["pending_only"] = "TRUE" if pending_only else "FALSE"

        headers, _, total_params = self._generate_signature_payload(payload)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        return requests.post(url, headers=headers, data=total_params).json()

    def cancel_order(self, order_id: str = None, pair: str = None) -> dict:
        url = f"{self.base_url}/v3/cancel_order"
        payload = {}

        if order_id:
            payload["order_id"] = str(order_id)
        elif pair:
            payload["pair"] = pair

        headers, _, total_params = self._generate_signature_payload(payload)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        logger.info(f"Canceling order (order_id={order_id}, pair={pair})")
        response = requests.post(url, headers=headers, data=total_params)
        res = self._safe_json_response(response)
        
        logger.info(f"Cancel order response: {res}")

        return requests.post(url, headers=headers, data=total_params).json()

    #shorting options
    def open_short(self, pair: str, quantity: float, leverage: int = 1) -> dict:
        url = f"{self.base_url}/v3/position/short/open"
        payload = {
            "pair": pair,
            "quantity": str(quantity),
            "leverage": str(leverage)
        }

        headers, _, total_params = self._generate_signature_payload(payload)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        logger.info(f"Opening SHORT position on {pair} for {quantity}")
        response = requests.post(url, headers=headers, data=total_params)
        res = self._safe_json_response(response)
        logger.info(f"Open Short Response: {res}")

        return res

    def close_short(self, pair: str, quantity: float = None) -> dict:
        url = f"{self.base_url}/v3/position/short/close"
        payload = {"pair": pair}

        if quantity is not None:
            payload["quantity"] = str(quantity)

        headers, _, total_params = self._generate_signature_payload(payload)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        logger.info(f"Closing SHORT position on {pair}")
        response = requests.post(url, headers=headers, data=total_params)
        res = self._safe_json_response(response)
        logger.info(f"Close Short Response: {res}")

        return res

    def get_short_positions(self, pair: str = None, **kwargs) -> dict:
        balance_res = self.get_balance()
        if not balance_res.get("Success"):
            return balance_res

        spot_wallet = balance_res.get("SpotWallet", {})
        usd_info = spot_wallet.get("USD", {})

        result = {
            "success": True,
            "short_collateral": usd_info.get("ShortCollateral", 0),
            "spot_wallet": spot_wallet
        }

        if pair:
            result["pair"] = pair

        return result