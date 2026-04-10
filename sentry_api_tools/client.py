import os

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

SENTRY_URL = os.environ.get("SENTRY_URL", "https://sentry.example.com/")
SENTRY_TOKEN = os.environ.get("SENTRY_TOKEN", "your_api_token_here")


class SentryClient:
    def __init__(self, host, token):
        self.base_url = f"{host.rstrip('/')}/api/0"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        retry = Retry(total=3, backoff_factor=0.5,
                      status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def get(self, path, params=None):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to {url}")
        except requests.exceptions.HTTPError:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    def put(self, path, data):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.put(url, json=data, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to {url}")
        except requests.exceptions.HTTPError:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
