import os

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

ZABBIX_URL = os.environ.get("ZABBIX_URL", "https://zabbix.example.com/api_jsonrpc.php")
ZABBIX_TOKEN = os.environ.get("ZABBIX_TOKEN", "your_api_token_here")


def make_session():
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZABBIX_TOKEN}"
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def zabbix_api(session, method, params):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    try:
        response = session.post(ZABBIX_URL, json=payload, timeout=15)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot connect to Zabbix at {ZABBIX_URL}")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Zabbix request timed out: {method}")
    except requests.exceptions.HTTPError:
        raise RuntimeError(f"Zabbix HTTP {response.status_code}: {response.text[:200]}")
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"API error: {result['error']}")
    return result["result"]
