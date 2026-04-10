#!/usr/bin/env python3

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

ZABBIX_URL = os.environ.get("ZABBIX_URL", "https://zabbix.example.com/api_jsonrpc.php")
ZABBIX_TOKEN = os.environ.get("ZABBIX_TOKEN", "your_api_token_here")

ACK_ACTION_MAP = {
    1: "close",
    2: "ack",
    4: "message",
    8: "severity change",
    16: "unack",
    32: "suppress",
    64: "unsuppress",
    128: "cause change",
}

SEVERITY_MAP = {
    "0": "Not classified",
    "1": "Information",
    "2": "Warning",
    "3": "Average",
    "4": "High",
    "5": "Disaster",
}


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


def format_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    elif m:
        return f"{m}m {s}s"
    return f"{s}s"


def decode_ack_action(action):
    action = int(action)
    parts = [label for bit, label in ACK_ACTION_MAP.items() if action & bit]
    return ", ".join(parts) if parts else "unknown"


def format_acknowledges(acknowledges):
    if not acknowledges:
        return None, None
    sorted_acks = sorted(acknowledges, key=lambda x: int(x["clock"]))
    last = sorted_acks[-1]
    ts = datetime.fromtimestamp(int(last["clock"])).strftime("%Y-%m-%d %H:%M:%S")
    action = decode_ack_action(last["action"])
    user = last.get("user", {})
    username = (
        f"{user.get('name', '')} {user.get('surname', '')}".strip()
        or last.get("userid", "N/A")
    )
    message = last.get("message", "").strip()
    history = []
    for a in sorted_acks:
        a_ts = datetime.fromtimestamp(int(a["clock"])).strftime("%Y-%m-%d %H:%M:%S")
        a_action = decode_ack_action(a["action"])
        a_user = a.get("user", {})
        a_uname = (
            f"{a_user.get('name', '')} {a_user.get('surname', '')}".strip()
            or a.get("userid", "N/A")
        )
        a_msg = a.get("message", "").strip()
        entry = f"[{a_ts}] [{a_action}] {a_uname}"
        if a_msg:
            entry += f': "{a_msg}"'
        history.append(entry)
    last_ack = f"[{ts}] [{action}] {username}"
    if message:
        last_ack += f': "{message}"'
    return last_ack, history


def format_suppression(suppression_data):
    if not suppression_data:
        return None
    parts = []
    for s in suppression_data:
        maintenance_id = s.get("maintenance_id", "N/A")
        suppress_until = s.get("suppress_until", 0)
        if int(suppress_until) > 0:
            until = datetime.fromtimestamp(int(suppress_until)).strftime("%Y-%m-%d %H:%M:%S")
            parts.append(f"maintenance #{maintenance_id} until {until}")
        else:
            parts.append(f"maintenance #{maintenance_id}")
    return ", ".join(parts)


def print_problem_block(p, now, indent="", show_history=False):
    ts = datetime.fromtimestamp(int(p["clock"])).strftime("%Y-%m-%d %H:%M:%S")
    sev = SEVERITY_MAP.get(p["severity"], "Unknown")
    resolved = ""
    if p["r_eventid"] != "0" and p.get("r_clock", "0") != "0":
        duration = format_duration(int(p["r_clock"]) - int(p["clock"]))
        resolved = " [RESOLVED]"
    else:
        duration = format_duration(now - int(p["clock"]))

    hosts = ", ".join(h["host"] for h in p.get("hosts", []))
    suppressed = format_suppression(p.get("suppression_data", []))
    last_ack, history = format_acknowledges(p.get("acknowledges", []))

    print(f"{indent}[{ts}] [{sev}]{resolved}")
    print(f"{indent}  ID        : {p['eventid']}")
    print(f"{indent}  Host      : {hosts or 'N/A'}")
    print(f"{indent}  Problem   : {p['name']}")
    print(f"{indent}  Duration  : {duration}")

    if suppressed:
        print(f"{indent}  Suppressed: YES — {suppressed}")

    if last_ack:
        print(f"{indent}  Last ack  : {last_ack}")

    if show_history and history:
        print(f"{indent}  History   :")
        for entry in history:
            print(f"{indent}    {entry}")

    print()


def print_problems_flat(problems, title, now, show_history=False):
    print(f"\n{'='*70}")
    print(f" {title} ({len(problems)})")
    print('='*70)
    if not problems:
        print(" (no data)")
        return
    for p in problems:
        print_problem_block(p, now, indent="", show_history=show_history)


def print_problems_by_host(problems, title, now, show_history=False):
    print(f"\n{'='*70}")
    print(f" {title} — by host ({len(problems)})")
    print('='*70)
    if not problems:
        print(" (no data)")
        return
    by_host = defaultdict(list)
    for p in problems:
        hosts = [h["host"] for h in p.get("hosts", [])] or ["N/A"]
        for host in hosts:
            by_host[host].append(p)
    for host in sorted(by_host):
        print(f"\n  [ {host} ] — {len(by_host[host])} problem(s)")
        print(f"  {'-'*60}")
        for p in by_host[host]:
            print_problem_block(p, now, indent="  ", show_history=show_history)


def print_problems_by_problem(problems, title, now, show_history=False):
    print(f"\n{'='*70}")
    print(f" {title} — by problem ({len(problems)})")
    print('='*70)
    if not problems:
        print(" (no data)")
        return
    by_name = defaultdict(list)
    for p in problems:
        by_name[p["name"]].append(p)
    for name in sorted(by_name):
        print(f"\n  [ {name} ] — {len(by_name[name])} occurrence(s)")
        print(f"  {'-'*60}")
        for p in by_name[name]:
            print_problem_block(p, now, indent="  ", show_history=show_history)


def print_problems(problems, title, now, by_host=False, by_problem=False, show_history=False):
    if by_host:
        print_problems_by_host(problems, title, now, show_history)
    elif by_problem:
        print_problems_by_problem(problems, title, now, show_history)
    else:
        print_problems_flat(problems, title, now, show_history)


def get_current(session):
    current_problems = zabbix_api(session, "problem.get", {
        "output": "extend",
        "selectAcknowledges": "extend",
        "selectSuppressionData": "extend",
        "recent": False,
        "sortfield": ["eventid"],
        "sortorder": "DESC"
    })
    if not current_problems:
        return []
    eventids = [p["eventid"] for p in current_problems]
    events = zabbix_api(session, "event.get", {
        "output": "extend",
        "selectHosts": ["host", "name"],
        "selectAcknowledges": "extend",
        "eventids": eventids,
        "sortfield": ["eventid"],
        "sortorder": "DESC"
    })
    supp_map = {p["eventid"]: p.get("suppression_data", []) for p in current_problems}
    for e in events:
        e["suppression_data"] = supp_map.get(e["eventid"], [])
    return events


def get_historical(session, hours):
    now_dt = datetime.now()
    now = int(now_dt.timestamp())
    since = int((now_dt - timedelta(hours=hours)).timestamp())
    events = zabbix_api(session, "event.get", {
        "output": "extend",
        "selectHosts": ["host", "name"],
        "selectAcknowledges": "extend",
        "source": 0,
        "object": 0,
        "value": 1,
        "time_from": since,
        "time_till": now,
        "sortfield": ["eventid"],
        "sortorder": "DESC"
    })
    # event.get не возвращает r_clock — получаем его отдельным запросом
    # по r_eventid (ID события восстановления) для разрешённых проблем
    r_eventids = [
        e["r_eventid"] for e in events
        if e.get("r_eventid", "0") not in ("0", "", None, 0)
    ]
    if r_eventids:
        recovery_events = zabbix_api(session, "event.get", {
            "output": ["eventid", "clock"],
            "eventids": r_eventids
        })
        r_clock_map = {e["eventid"]: e["clock"] for e in recovery_events}
        for e in events:
            r_eid = e.get("r_eventid", "0")
            if r_eid not in ("0", "", None, 0) and r_eid in r_clock_map:
                e["r_clock"] = r_clock_map[r_eid]
    return events


def main():
    parser = argparse.ArgumentParser(
        description="Zabbix problems viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --current                         Active problems
  %(prog)s --duty-shift                      Problems for last 12 hours
  %(prog)s --duty-day                        Problems for last 24 hours
  %(prog)s --duty-week                       Problems for last 7 days
  %(prog)s --duty-month                      Problems for last 30 days
  %(prog)s --duty-shift --hosts              Last 12h grouped by host
  %(prog)s --duty-day --problems             Last 24h grouped by problem
  %(prog)s --current --duty-shift --history  With full action history

Environment variables:
  export ZABBIX_URL="https://zabbix.example.com/api_jsonrpc.php"
  export ZABBIX_TOKEN="your_token_here"
        """
    )
    parser.add_argument("--current", action="store_true", help="Show active problems")
    parser.add_argument("--duty-shift", action="store_true", help="Show problems for last 12 hours")
    parser.add_argument("--duty-day", action="store_true", help="Show problems for last 24 hours")
    parser.add_argument("--duty-week", action="store_true", help="Show problems for last 7 days")
    parser.add_argument("--duty-month", action="store_true", help="Show problems for last 30 days")
    parser.add_argument("--hosts", action="store_true", help="Group output by host")
    parser.add_argument("--problems", action="store_true", help="Group output by problem name")
    parser.add_argument("--history", action="store_true", help="Show full action history per problem")

    args = parser.parse_args()

    duty_flags = [args.duty_shift, args.duty_day, args.duty_week, args.duty_month]

    if not (args.current or any(duty_flags)):
        parser.print_help()
        sys.exit(0)

    if sum(duty_flags) > 1:
        print("Error: --duty-shift, --duty-day, --duty-week and --duty-month are mutually exclusive.")
        sys.exit(1)

    if args.hosts and args.problems:
        print("Error: --hosts and --problems are mutually exclusive.")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ZABBIX_TOKEN}"
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))

    try:
        now = int(datetime.now().timestamp())

        if args.current:
            problems = get_current(session)
            print_problems(problems, "Current problems", now, args.hosts, args.problems, args.history)

        if args.duty_shift:
            problems = get_historical(session, hours=12)
            print_problems(problems, "Problems — last 12 hours", now, args.hosts, args.problems, args.history)

        if args.duty_day:
            problems = get_historical(session, hours=24)
            print_problems(problems, "Problems — last 24 hours", now, args.hosts, args.problems, args.history)

        if args.duty_week:
            problems = get_historical(session, hours=24*7)
            print_problems(problems, "Problems — last 7 days", now, args.hosts, args.problems, args.history)

        if args.duty_month:
            problems = get_historical(session, hours=24*30)
            print_problems(problems, "Problems — last 30 days", now, args.hosts, args.problems, args.history)
    finally:
        session.close()


if __name__ == "__main__":
    main()
