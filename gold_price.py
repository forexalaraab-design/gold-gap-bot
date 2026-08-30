import time

import config
import requests


class GoldFetchError(Exception):
    pass


def fetch_gold_api():
    r = requests.get(config.GOLD_API_URL, timeout=15)
    r.raise_for_status()
    data = r.json()
    price = float(data.get("price"))
    if price <= 0:
        raise GoldFetchError("gold-api.com returned non-positive price")
    return price, data.get("updatedAt", "")


def fetch_yahoo():
    r = requests.get(
        config.YAHOO_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    payload = r.json()
    meta = payload["chart"]["result"][0]["meta"]
    price = float(meta.get("regularMarketPrice") or meta.get("chartPreviousClose"))
    if price <= 0:
        raise GoldFetchError("yahoo returned non-positive price")
    return price + YAHOO_OFFSET_USD, meta.get("regularMarketTime", "")


def get_global_gold_price():
    """Returns (price, source_label, source_ts). Primary = gold-api.com, fallback = Yahoo GCSE=F."""
    last_error = None
    try:
        price, ts = fetch_gold_api()
        return price, "gold-api", ts
    except Exception as exc:
        last_error = repr(exc)
    try:
        price, ts = fetch_yahoo()
        return price, "yahoo-GC=F", str(ts)
    except Exception as exc:
        last_error += " | yahoo: " + repr(exc)
    raise GoldFetchError("all global gold sources failed: " + str(last_error))