import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")

url = "https://api-fxpractice.oanda.com/v3/instruments/USD_JPY/candles"

headers = {"Authorization": f"Bearer {API_KEY}"}

params = {
    "granularity": "M1",
    "count": 5
}

r = requests.get(url, headers=headers, params=params)
print(r.status_code)
print(r.json())