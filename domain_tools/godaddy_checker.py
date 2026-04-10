#!/usr/bin/env python3
"""
GoDaddy domain expiry + parking checker.

━━━ Getting an API key ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Log in to your GoDaddy account at https://developer.godaddy.com/keys
   (same credentials you use to manage your domains).

2. Click "Create New API Key".

3. Fill in the form:
     Name        — any label, e.g. "domain-monitor"
     Environment — select "Production"
                   (OTE is a sandbox; your real domains are not visible there)

4. Click "Next". The page will show two values — copy them immediately,
   the secret is displayed only once:
     API Key    → GODADDY_API_KEY
     API Secret → GODADDY_API_SECRET

5. Create a .env file next to the script (see .env.example):

     GODADDY_API_KEY=your_key
     GODADDY_API_SECRET=your_secret

   The script loads it automatically. You can also override via shell:

     export GODADDY_API_KEY="your_key"
     export GODADDY_API_SECRET="your_secret"

Note: a key grants access only to the GoDaddy account it was created under.
If domains are spread across multiple accounts, you need a separate key for each.

━━━ What is checked per domain ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - expires        : real expiration date
  - renewAuto      : auto-renewal flag
  - status         : PARKED / PARKED_AND_HELD / PARKED_EXPIRED / …
  - nameServers    : ns\\d+.domaincontrol.com → secondary parking signal
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv(Path(__file__).parent / ".env")

GODADDY_API_BASE = "https://api.godaddy.com"

PARKED_STATUSES = {
    "PARKED",
    "PARKED_AND_HELD",
    "PARKED_EXPIRED",
    "PARKED_VERIFICATION_ICANN",
    "PENDING_PARKING_DETERMINATION",
    "PENDING_PARK_INVALID_WHOIS",
    "PENDING_REMOVAL_PARKED",
}

PARKING_NS_RE = re.compile(r"^ns\d+\.domaincontrol\.com$", re.IGNORECASE)

DEFAULT_WARN_DAYS = 30
DEFAULT_DELAY = 0.5


# ─── GoDaddy API ──────────────────────────────────────────────────────────────

def make_session(api_key: str, api_secret: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"sso-key {api_key}:{api_secret}"})
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def query_domain(session: requests.Session, domain: str) -> dict:
    """
    Returns a result dict:
      domain, expiration_date, renew_auto, status, nameservers,
      parked_by_status, parked_by_ns, error
    """
    result = {
        "domain": domain,
        "expiration_date": None,
        "renew_auto": None,
        "status": None,
        "nameservers": [],
        "parked_by_status": False,
        "parked_by_ns": False,
        "error": None,
    }

    url = f"{GODADDY_API_BASE}/v1/domains/{domain}"
    try:
        resp = session.get(url, params={"includes": "nameServers"}, timeout=15)
        if resp.status_code == 404:
            result["error"] = "not found in account"
            return result
        if resp.status_code == 403:
            result["error"] = "access denied (check API key)"
            return result
        resp.raise_for_status()
    except requests.RequestException as e:
        result["error"] = str(e)
        return result

    data = resp.json()

    # Expiration date
    raw_exp = data.get("expires")
    if raw_exp:
        try:
            result["expiration_date"] = datetime.fromisoformat(
                raw_exp.replace("Z", "+00:00")
            )
        except ValueError:
            result["error"] = f"cannot parse expires: {raw_exp!r}"
            return result
    else:
        result["error"] = "no 'expires' field in response"
        return result

    # Auto-renewal flag
    result["renew_auto"] = data.get("renewAuto")

    # Status
    status = data.get("status", "")
    result["status"] = status
    result["parked_by_status"] = status.upper() in PARKED_STATUSES

    # Nameservers
    ns_list = data.get("nameServers") or []
    result["nameservers"] = ns_list
    result["parked_by_ns"] = all(PARKING_NS_RE.match(ns) for ns in ns_list) if ns_list else False

    return result


# ─── Output ───────────────────────────────────────────────────────────────────

def days_left(exp: datetime) -> int:
    return (exp - datetime.now(timezone.utc)).days


def is_parked(r: dict) -> bool:
    return r["parked_by_status"] or r["parked_by_ns"]


def parking_tag(r: dict) -> str:
    parts = []
    if r["parked_by_status"]:
        parts.append(f"status={r['status']}")
    if r["parked_by_ns"]:
        ns_str = ", ".join(r["nameservers"])
        parts.append(f"ns={ns_str}")
    return "  [PARKED: " + "; ".join(parts) + "]" if parts else ""


def print_results(results: list, warn_days: int) -> None:
    now = datetime.now(timezone.utc)

    errors = [r for r in results if r["error"]]
    valid = [r for r in results if not r["error"]]

    parked = [r for r in valid if is_parked(r)]
    not_parked = [r for r in valid if not is_parked(r)]

    expiring = [r for r in not_parked if days_left(r["expiration_date"]) <= warn_days]
    ok = [r for r in not_parked if days_left(r["expiration_date"]) > warn_days]

    for lst in (parked, expiring, ok):
        lst.sort(key=lambda r: r["expiration_date"])

    col = max((len(r["domain"]) for r in results), default=10)
    col = max(col, 10)

    def row(r: dict, marker: str = "") -> str:
        exp = r["expiration_date"]
        d = days_left(exp)
        auto = "auto" if r["renew_auto"] else "manual"
        return f"  {r['domain']:<{col}}  {exp.strftime('%Y-%m-%d')}  {d:>4}d  [{auto}]{marker}"

    if parked:
        print(f"\n{'='*70}")
        print(f" PARKED BY GODADDY ({len(parked)})")
        print("="*70)
        for r in parked:
            print(row(r, parking_tag(r)))

    if expiring:
        print(f"\n{'='*70}")
        print(f" EXPIRING SOON — within {warn_days} days ({len(expiring)})")
        print("="*70)
        for r in expiring:
            marker = "  <<< EXPIRED" if days_left(r["expiration_date"]) < 0 else "  <!>"
            print(row(r, marker))

    if ok:
        print(f"\n{'='*70}")
        print(f" OK ({len(ok)})")
        print("="*70)
        for r in ok:
            print(row(r))

    if errors:
        print(f"\n{'='*70}")
        print(f" ERRORS ({len(errors)})")
        print("="*70)
        for r in errors:
            print(f"  {r['domain']:<{col}}  {r['error']}")

    total = len(results)
    print(
        f"\n  Checked: {total}  |  OK: {len(ok)}  |  Expiring: {len(expiring)}  |"
        f"  Parked: {len(parked)}  |  Errors: {len(errors)}"
    )
    print(f"  As of: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def load_domains(path: str) -> list[str]:
    lines = Path(path).read_text().splitlines()
    return [
        line.strip().lower()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GoDaddy domain expiry + parking checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Credentials (required):
  Create a .env file next to the script (see .env.example):
    GODADDY_API_KEY=your_key
    GODADDY_API_SECRET=your_secret
  Get keys at: https://developer.godaddy.com/keys

Examples:
  %(prog)s godaddy_domains.txt
  %(prog)s godaddy_domains.txt --warn 60
  %(prog)s proxy-man.com esimman.com

Columns:
  domain  expires      days-left  [auto|manual]
  auto   = renewAuto is true  (GoDaddy will renew automatically)
  manual = renewAuto is false

Parking detection:
  PARKED BY GODADDY = status in {PARKED, PARKED_AND_HELD, PARKED_EXPIRED, …}
                      OR all nameservers match ns\\d+.domaincontrol.com
        """
    )
    parser.add_argument(
        "domains", nargs="+",
        help="Domain names or path to a file with one domain per line"
    )
    parser.add_argument(
        "--warn", type=int, default=DEFAULT_WARN_DAYS, metavar="DAYS",
        help=f"Warn if expiring within N days (default: {DEFAULT_WARN_DAYS})"
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY, metavar="SEC",
        help=f"Delay between API requests in seconds (default: {DEFAULT_DELAY})"
    )

    args = parser.parse_args()

    api_key = os.environ.get("GODADDY_API_KEY", "").strip()
    api_secret = os.environ.get("GODADDY_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print("Error: GODADDY_API_KEY and GODADDY_API_SECRET must be set in .env or environment.")
        sys.exit(1)

    # Resolve domains: if single arg is a file path — load from file
    if len(args.domains) == 1 and Path(args.domains[0]).is_file():
        try:
            domains = load_domains(args.domains[0])
        except OSError as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    else:
        domains = [d.lower() for d in args.domains]

    if not domains:
        print("Error: no domains to check.")
        sys.exit(1)

    session = make_session(api_key, api_secret)

    try:
        print(f"Checking {len(domains)} domain(s) via GoDaddy API...\n")

        results = []
        for i, domain in enumerate(domains, 1):
            print(f"  [{i:>3}/{len(domains)}] {domain}...", end=" ", flush=True)
            r = query_domain(session, domain)
            if r["error"]:
                print(f"ERROR: {r['error']}")
            else:
                d = days_left(r["expiration_date"])
                auto_tag = "auto" if r["renew_auto"] else "manual"
                parked_tag = "  [PARKED]" if is_parked(r) else ""
                print(f"{r['expiration_date'].strftime('%Y-%m-%d')}  ({d}d)  [{auto_tag}]{parked_tag}")
            results.append(r)
            if i < len(domains):
                time.sleep(args.delay)

        print_results(results, args.warn)
    finally:
        session.close()


if __name__ == "__main__":
    main()
