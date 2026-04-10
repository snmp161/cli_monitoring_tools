#!/usr/bin/env python3

import argparse
import os
import sys
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

ZABBIX_URL = os.environ.get("ZABBIX_URL", "https://zabbix.example.com/api_jsonrpc.php")
ZABBIX_TOKEN = os.environ.get("ZABBIX_TOKEN", "your_api_token_here")

SEVERITY_MAP = {
    "not_classified": 0,
    "information": 1,
    "warning": 2,
    "average": 3,
    "high": 4,
    "disaster": 5,
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


def resolve_host_ids(session, hostnames):
    if not hostnames:
        return []
    result = zabbix_api(session, "host.get", {
        "output": ["hostid", "host"],
        "filter": {"host": hostnames}
    })
    found = {h["host"]: h["hostid"] for h in result}
    for name in hostnames:
        if name not in found:
            print(f"Warning: host '{name}' not found, skipping.")
    return list(found.values())


def resolve_group_ids(session, groupnames):
    if not groupnames:
        return []
    result = zabbix_api(session, "hostgroup.get", {
        "output": ["groupid", "name"],
        "filter": {"name": groupnames}
    })
    found = {g["name"]: g["groupid"] for g in result}
    for name in groupnames:
        if name not in found:
            print(f"Warning: group '{name}' not found, skipping.")
    return list(found.values())


def resolve_event_ids(session, args):
    eventids = []
    if args.event_id:
        eventids = args.event_id
    elif args.problem_name or args.host or args.group:
        params = {
            "output": ["eventid", "name"],
            "source": 0,
            "object": 0,
            "value": 1,
            "recent": True,
            "sortfield": ["eventid"],
            "sortorder": "DESC"
        }
        if args.problem_name:
            params["search"] = {"name": args.problem_name}
            params["searchWildcardsEnabled"] = True
        if args.host:
            hostids = resolve_host_ids(session, args.host)
            if hostids:
                params["hostids"] = hostids
        if args.group:
            groupids = resolve_group_ids(session, args.group)
            if groupids:
                params["groupids"] = groupids
        problems = zabbix_api(session, "problem.get", params)
        if not problems:
            print("No matching problems found.")
            sys.exit(1)
        print(f"Matched {len(problems)} problem(s):")
        for p in problems:
            print(f"  [{p['eventid']}] {p['name']}")
        eventids = [p["eventid"] for p in problems]
    else:
        print("Error: specify --event-id, --problem-name, --host or --group.")
        sys.exit(1)
    return eventids


def cmd_problem(session, args):
    if not any([args.ack, args.close, args.suppress, args.unsuppress,
                args.message, args.severity]):
        print("Error: specify at least one action: --ack, --close, --suppress, "
              "--unsuppress, --message, --severity.")
        sys.exit(1)

    if args.severity and args.severity.lower() not in SEVERITY_MAP:
        print(f"Error: unknown severity '{args.severity}'. "
              f"Valid: {', '.join(SEVERITY_MAP)}")
        sys.exit(1)

    eventids = resolve_event_ids(session, args)

    action = 0
    if args.ack:
        action |= 2
    if args.close:
        action |= 1
    if args.suppress:
        action |= 32
    if args.unsuppress:
        action |= 64
    if args.message:
        action |= 4
    if args.severity:
        action |= 8

    params = {
        "eventids": eventids,
        "action": action,
    }
    if args.message:
        params["message"] = args.message
    if args.severity:
        params["severity"] = SEVERITY_MAP[args.severity.lower()]

    zabbix_api(session, "event.acknowledge", params)

    actions_done = []
    if args.close:
        actions_done.append("closed")
    if args.ack:
        actions_done.append("acknowledged")
    if args.suppress:
        actions_done.append("suppressed")
    if args.unsuppress:
        actions_done.append("unsuppressed")
    if args.message:
        actions_done.append("message set")
    if args.severity:
        actions_done.append(f"severity changed to {args.severity}")

    print(f"Done [{', '.join(actions_done)}] for {len(eventids)} problem(s).")


def cmd_maintenance_create(session, args):
    if not args.name:
        print("Error: --name is required.")
        sys.exit(1)
    if not args.duration:
        print("Error: --duration is required.")
        sys.exit(1)
    if not (args.host or args.group):
        print("Error: --host or --group is required.")
        sys.exit(1)

    if args.start:
        try:
            start_dt = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
        except ValueError:
            print("Error: --start format must be 'YYYY-MM-DD HH:MM'")
            sys.exit(1)
    else:
        start_dt = datetime.now().replace(second=0, microsecond=0)

    end_dt = start_dt + timedelta(minutes=args.duration)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    hostids = resolve_host_ids(session, args.host or [])
    groupids = resolve_group_ids(session, args.group or [])

    if not hostids and not groupids:
        print("Error: no valid hosts or groups found.")
        sys.exit(1)

    params = {
        "name": args.name,
        "active_since": start_ts,
        "active_till": end_ts,
        "maintenance_type": 1 if args.no_data else 0,
        "timeperiods": [{
            "timeperiod_type": 0,
            "start_date": start_ts,
            "period": args.duration * 60,
        }]
    }
    if hostids:
        params["hostids"] = hostids
    if groupids:
        params["groupids"] = groupids

    result = zabbix_api(session, "maintenance.create", params)
    maint_id = result["maintenanceids"][0]
    mode = "no data collection" if args.no_data else "with data collection"
    print(f"Maintenance #{maint_id} '{args.name}' created.")
    print(f"  Start   : {start_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"  End     : {end_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Duration: {args.duration} min")
    print(f"  Mode    : {mode}")
    if hostids:
        print(f"  Hosts   : {', '.join(args.host)}")
    if groupids:
        print(f"  Groups  : {', '.join(args.group)}")


def cmd_maintenance_delete(session, args):
    if not args.maintenance_id:
        print("Error: --maintenance-id is required for delete.")
        sys.exit(1)
    zabbix_api(session, "maintenance.delete", args.maintenance_id)
    print(f"Maintenance(s) deleted: {', '.join(args.maintenance_id)}")


def cmd_maintenance_list(session, args):
    params = {
        "output": ["maintenanceid", "name", "active_since", "active_till", "maintenance_type"],
        "selectHosts": ["host"],
        "selectGroups": ["name"],
        "sortfield": "name",
        "sortorder": "ASC"
    }
    if args.host:
        hostids = resolve_host_ids(session, args.host)
        if hostids:
            params["hostids"] = hostids
    if args.group:
        groupids = resolve_group_ids(session, args.group)
        if groupids:
            params["groupids"] = groupids

    result = zabbix_api(session, "maintenance.get", params)
    if not result:
        print("No maintenance windows found.")
        return

    now = int(datetime.now().timestamp())
    print(f"\n{'='*70}")
    print(f" Maintenance windows ({len(result)})")
    print('='*70)
    for m in result:
        since = datetime.fromtimestamp(int(m["active_since"])).strftime("%Y-%m-%d %H:%M")
        till = datetime.fromtimestamp(int(m["active_till"])).strftime("%Y-%m-%d %H:%M")
        mode = "no data" if m["maintenance_type"] == "1" else "with data"
        active = " [ACTIVE]" if int(m["active_since"]) <= now <= int(m["active_till"]) else ""
        hosts = ", ".join(h["host"] for h in m.get("hosts", []))
        groups = ", ".join(g["name"] for g in m.get("groups", []))
        print(f"[#{m['maintenanceid']}] {m['name']}{active}")
        print(f"  Period: {since} — {till}  ({mode})")
        if hosts:
            print(f"  Hosts : {hosts}")
        if groups:
            print(f"  Groups: {groups}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Zabbix maintenance and problem manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  Maintenance:
    %(prog)s --maintenance create --name "Deploy" --host web01 web02 --duration 60
    %(prog)s --maintenance create --name "Nightly" --group "Linux servers" --start "2025-03-01 02:00" --duration 120 --no-data
    %(prog)s --maintenance delete --maintenance-id 12 15
    %(prog)s --maintenance list
    %(prog)s --maintenance list --host web01

  Problems:
    %(prog)s --problem ack --event-id 1234
    %(prog)s --problem ack --event-id 1234 1235 --message "Working on it"
    %(prog)s --problem close --event-id 1234
    %(prog)s --problem suppress --host web01
    %(prog)s --problem unsuppress --problem-name "CPU*"
    %(prog)s --problem ack suppress --event-id 1234 --message "Suppressed during deploy"
    %(prog)s --problem severity --event-id 1234 --severity high

Environment variables:
  export ZABBIX_URL="https://zabbix.example.com/api_jsonrpc.php"
  export ZABBIX_TOKEN="your_token_here"
        """
    )

    parser.add_argument("--maintenance", nargs="+",
                        metavar="ACTION",
                        help="Maintenance action: create, delete, list")
    parser.add_argument("--problem", nargs="+",
                        metavar="ACTION",
                        help="Problem action(s): ack, close, suppress, unsuppress, severity, message")

    targets = parser.add_argument_group("Targets")
    targets.add_argument("--event-id", nargs="+", metavar="ID", help="Event ID(s)")
    targets.add_argument("--problem-name", metavar="NAME", help="Problem name (wildcards supported)")
    targets.add_argument("--host", nargs="+", metavar="HOST", help="Host name(s)")
    targets.add_argument("--group", nargs="+", metavar="GROUP", help="Host group name(s)")

    maint = parser.add_argument_group("Maintenance options")
    maint.add_argument("--name", metavar="NAME", help="Maintenance window name")
    maint.add_argument("--start", metavar="DATETIME",
                       help="Start time 'YYYY-MM-DD HH:MM' (default: now)")
    maint.add_argument("--duration", type=int, metavar="MINUTES", help="Duration in minutes")
    maint.add_argument("--no-data", action="store_true", help="Disable data collection during maintenance")
    maint.add_argument("--maintenance-id", nargs="+", metavar="ID", help="Maintenance ID(s) for delete")

    prob = parser.add_argument_group("Problem options")
    prob.add_argument("--message", metavar="TEXT", help="Message text for ack/message action")
    prob.add_argument("--severity", metavar="LEVEL",
                      help=f"New severity: {', '.join(SEVERITY_MAP)}")

    args = parser.parse_args()

    if not args.maintenance and not args.problem:
        parser.print_help()
        sys.exit(0)

    args.ack = args.problem and "ack" in args.problem
    args.close = args.problem and "close" in args.problem
    args.suppress = args.problem and "suppress" in args.problem
    args.unsuppress = args.problem and "unsuppress" in args.problem

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
        if args.maintenance:
            action = args.maintenance[0].lower()
            if action == "create":
                cmd_maintenance_create(session, args)
            elif action == "delete":
                cmd_maintenance_delete(session, args)
            elif action == "list":
                cmd_maintenance_list(session, args)
            else:
                print(f"Error: unknown maintenance action '{action}'. Use: create, delete, list.")
                sys.exit(1)

        if args.problem:
            valid_actions = {"ack", "close", "suppress", "unsuppress", "severity", "message"}
            unknown = set(args.problem) - valid_actions
            if unknown:
                print(f"Error: unknown problem action(s): {', '.join(unknown)}. "
                      f"Valid: {', '.join(sorted(valid_actions))}")
                sys.exit(1)
            cmd_problem(session, args)
    finally:
        session.close()


if __name__ == "__main__":
    main()
