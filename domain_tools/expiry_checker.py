#!/usr/bin/env python3

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import whoisdomain as whois
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
RDAP_BOOTSTRAP_CACHE = Path(__file__).parent / ".rdap_bootstrap.json"
RDAP_BOOTSTRAP_TTL = 24 * 3600  # seconds

DEFAULT_WARN_DAYS = 30
DEFAULT_DELAY = 1.0  # seconds between requests


def make_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


# ─── RDAP bootstrap ───────────────────────────────────────────────────────────

def load_rdap_bootstrap(session):
    if RDAP_BOOTSTRAP_CACHE.exists():
        age = datetime.now().timestamp() - RDAP_BOOTSTRAP_CACHE.stat().st_mtime
        if age < RDAP_BOOTSTRAP_TTL:
            try:
                return json.loads(RDAP_BOOTSTRAP_CACHE.read_text())
            except (ValueError, OSError):
                pass  # corrupted or unreadable cache, re-download

    resp = session.get(RDAP_BOOTSTRAP_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    RDAP_BOOTSTRAP_CACHE.write_text(json.dumps(data))
    return data


def get_rdap_server(bootstrap, domain):
    tld = domain.rsplit(".", 1)[-1].lower()
    for tlds, servers in bootstrap["services"]:
        if tld in [t.lower() for t in tlds]:
            return servers[0].rstrip("/")
    return None


# ─── Queries ──────────────────────────────────────────────────────────────────

def query_rdap(session, server, domain):
    url = f"{server}/domain/{domain}"
    resp = session.get(url, timeout=10, headers={"Accept": "application/rdap+json"})
    resp.raise_for_status()
    for event in resp.json().get("events", []):
        if event.get("eventAction") == "expiration":
            raw = event["eventDate"]
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return None


def query_whois(domain):
    d = whois.query(domain)
    if d is None:
        return None
    exp = d.expiration_date
    if isinstance(exp, list):
        exp = exp[0]
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp


def check_domain(session, bootstrap, domain):
    result = {"domain": domain, "expiration_date": None, "source": None, "error": None}

    server = get_rdap_server(bootstrap, domain)
    if server:
        try:
            exp = query_rdap(session, server, domain)
            if exp:
                result["expiration_date"] = exp
                result["source"] = "rdap"
                return result
        except (requests.RequestException, KeyError, ValueError):
            pass  # fall through to WHOIS

    try:
        exp = query_whois(domain)
        if exp:
            result["expiration_date"] = exp
            result["source"] = "whois"
        else:
            result["error"] = "no expiration date returned"
    except (requests.RequestException, KeyError, ValueError) as e:
        result["error"] = str(e)

    return result


# ─── Output ───────────────────────────────────────────────────────────────────

def days_left(exp):
    now = datetime.now(timezone.utc)
    return (exp - now).days


def print_results(results, warn_days):
    now = datetime.now(timezone.utc)

    ok = [r for r in results if r["expiration_date"] and days_left(r["expiration_date"]) > warn_days]
    warn = [r for r in results if r["expiration_date"] and days_left(r["expiration_date"]) <= warn_days]
    errors = [r for r in results if r["error"]]

    warn.sort(key=lambda r: r["expiration_date"])
    ok.sort(key=lambda r: r["expiration_date"])

    col = max((len(r["domain"]) for r in results), default=10)
    col = max(col, 10)

    def print_row(r, marker=""):
        exp = r["expiration_date"]
        d = days_left(exp)
        src = r["source"]
        print(f"  {r['domain']:<{col}}  {exp.strftime('%Y-%m-%d')}  {d:>4}d  [{src}] {marker}")

    if warn:
        print(f"\n{'='*70}")
        print(f" EXPIRING SOON — within {warn_days} days ({len(warn)})")
        print('='*70)
        for r in warn:
            marker = "<<< EXPIRED" if days_left(r["expiration_date"]) < 0 else "<!>"
            print_row(r, marker)

    if ok:
        print(f"\n{'='*70}")
        print(f" OK ({len(ok)})")
        print('='*70)
        for r in ok:
            print_row(r)

    if errors:
        print(f"\n{'='*70}")
        print(f" ERRORS ({len(errors)})")
        print('='*70)
        for r in errors:
            print(f"  {r['domain']:<{col}}  {r['error']}")

    print(f"\n  Checked: {len(results)}  |  OK: {len(ok)}  |  Warn: {len(warn)}  |  Errors: {len(errors)}")
    print(f"  As of: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def load_domains(path):
    lines = Path(path).read_text().splitlines()
    domains = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            domains.append(line.lower())
    return domains


def main():
    parser = argparse.ArgumentParser(
        description="Domain expiry checker (RDAP + WHOIS fallback)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s domains.txt
  %(prog)s domains.txt --warn 60
  %(prog)s domains.txt --delay 2 --warn 14

domains.txt format (one domain per line, # for comments):
  example.com
  example.ru
  # this line is ignored
  mysite.org

Environment: no env vars required.
        """
    )
    parser.add_argument("file", help="File with domain list (one per line)")
    parser.add_argument("--warn", type=int, default=DEFAULT_WARN_DAYS, metavar="DAYS",
                        help=f"Warn if expiring within N days (default: {DEFAULT_WARN_DAYS})")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, metavar="SEC",
                        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    try:
        domains = load_domains(args.file)
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    if not domains:
        print("Error: no domains found in file.")
        sys.exit(1)

    session = make_session()

    try:
        print(f"Loading RDAP bootstrap...")
        try:
            bootstrap = load_rdap_bootstrap(session)
        except requests.RequestException as e:
            print(f"Warning: could not load RDAP bootstrap ({e}), RDAP disabled.")
            bootstrap = {"services": []}

        print(f"Checking {len(domains)} domain(s)...\n")

        results = []
        for i, domain in enumerate(domains, 1):
            print(f"  [{i:>3}/{len(domains)}] {domain}...", end=" ", flush=True)
            r = check_domain(session, bootstrap, domain)
            if r["expiration_date"]:
                d = days_left(r["expiration_date"])
                print(f"{r['expiration_date'].strftime('%Y-%m-%d')}  ({d}d)  [{r['source']}]")
            else:
                print(f"ERROR: {r['error']}")
            results.append(r)
            if i < len(domains):
                time.sleep(args.delay)

        print_results(results, args.warn)
    finally:
        session.close()


if __name__ == "__main__":
    main()
