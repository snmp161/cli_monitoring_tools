#!/usr/bin/env python3

if __name__ == "__main__":
    print("This module is not meant to be run directly. Use viewer.py.")
    raise SystemExit(1)

import os
import sys

import urllib3
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PBS_URL = ""
PBS_TOKEN_ID = ""
PBS_TOKEN_SECRET = ""


def init(env_file=None):
    global PBS_URL, PBS_TOKEN_ID, PBS_TOKEN_SECRET
    load_dotenv(env_file)
    PBS_URL = os.environ.get("PBS_URL", "")
    PBS_TOKEN_ID = os.environ.get("PBS_TOKEN_ID", "")
    PBS_TOKEN_SECRET = os.environ.get("PBS_TOKEN_SECRET", "")
    if not PBS_URL or not PBS_TOKEN_ID or not PBS_TOKEN_SECRET:
        print("Error: PBS_URL, PBS_TOKEN_ID and PBS_TOKEN_SECRET must be set in .env or environment.")
        sys.exit(1)


def make_session():
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"PBSAPIToken={PBS_TOKEN_ID}:{PBS_TOKEN_SECRET}"
    })
    session.verify = False
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def pbs_api(session, path, params=None):
    url = f"{PBS_URL.rstrip('/')}/api2/json{path}"
    try:
        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Cannot connect to PBS at {PBS_URL}")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"PBS request timed out: {path}")
    except requests.exceptions.HTTPError:
        raise RuntimeError(f"PBS HTTP {response.status_code}: {response.text[:200]}")
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"Invalid JSON response from PBS: {path}")
    return result.get("data", result)
