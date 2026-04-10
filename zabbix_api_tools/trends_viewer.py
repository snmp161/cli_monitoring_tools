#!/usr/bin/env python3

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import client
from client import zabbix_api, make_session

METRICS = {
    "cpu": {
        "label": "CPU utilization",
        "search": "CPU utilization",
        "unit": "%",
    },
    "memory": {
        "label": "Memory utilization",
        "search": "Memory utilization",
        "unit": "%",
    },
    "la5": {
        "label": "Load average (5m)",
        "search": "Load average (5m avg)",
        "unit": "",
    },
    "la10": {
        "label": "Load average (10m)",
        "search": "Load average (10m avg)",
        "unit": "",
    },
    "la15": {
        "label": "Load average (15m)",
        "search": "Load average (15m avg)",
        "unit": "",
    },
}


def get_periods(mode, count):
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    periods = []
    for i in range(count, -1, -1):
        if mode == "week":
            end = now - timedelta(weeks=i)
            start = end - timedelta(weeks=1)
        else:
            month = now.month - i
            year = now.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            start = now.replace(year=year, month=month, day=1)
            if month == 12:
                end = now.replace(year=year + 1, month=1, day=1)
            else:
                end = now.replace(year=year, month=month + 1, day=1)
        periods.append((int(start.timestamp()), int(end.timestamp())))
    return periods


def get_all_hosts(session):
    return zabbix_api(session, "host.get", {
        "output": ["hostid", "host", "name"],
        "filter": {"status": 0},
        "sortfield": "host",
    })


def get_items_for_metric(session, hostids, search_name):
    return zabbix_api(session, "item.get", {
        "output": ["itemid", "hostid", "name"],
        "hostids": hostids,
        "search": {"name": search_name},
        "searchWildcardsEnabled": True,
        "filter": {"value_type": [0, 3]},
    })


def get_trend_avg(session, itemids, time_from, time_till):
    if not itemids:
        return {}
    trends = zabbix_api(session, "trend.get", {
        "output": ["itemid", "value_avg", "clock"],
        "itemids": itemids,
        "time_from": time_from,
        "time_till": time_till,
    })
    sums = defaultdict(float)
    counts = defaultdict(int)
    for t in trends:
        sums[t["itemid"]] += float(t["value_avg"])
        counts[t["itemid"]] += 1
    return {iid: sums[iid] / counts[iid] for iid in sums}


def collect_metric(session, hosts, metric_key, periods):
    meta = METRICS[metric_key]
    hostids = [h["hostid"] for h in hosts]
    hostmap = {h["hostid"]: h["host"] for h in hosts}

    items = get_items_for_metric(session, hostids, meta["search"])
    if not items:
        return {}

    host_items = defaultdict(list)
    for item in items:
        host_items[item["hostid"]].append(item["itemid"])

    results = {}
    for hostid, itemids in host_items.items():
        hostname = hostmap.get(hostid, hostid)
        period_avgs = []
        for time_from, time_till in periods:
            avgs = get_trend_avg(session, itemids, time_from, time_till)
            if avgs:
                if meta.get("multi"):
                    val = max(avgs.values())
                else:
                    val = list(avgs.values())[0]
            else:
                val = None
            period_avgs.append(val)
        results[hostname] = period_avgs

    return results


def calc_growth(values):
    growth = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        curr = values[i]
        if prev is not None and curr is not None and prev > 0:
            growth.append((curr - prev) / prev * 100)
        else:
            growth.append(None)
    return growth


def format_val(val, unit):
    if val is None:
        return "N/A"
    return f"{val:.2f}{unit}"


def format_growth(val):
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def print_top_separate(all_results, periods, mode, top_n):
    period_labels = []
    for time_from, time_till in periods:
        if mode == "week":
            label = datetime.fromtimestamp(time_from).strftime("W%W %Y")
        else:
            label = datetime.fromtimestamp(time_from).strftime("%b %Y")
        period_labels.append(label)

    for metric_key, meta in METRICS.items():
        data = all_results.get(metric_key, {})
        if not data:
            print(f"\n[{meta['label']}] — no data")
            continue

        ranked = []
        for hostname, values in data.items():
            growth = calc_growth(values)
            last_growth = next((g for g in reversed(growth) if g is not None), None)
            last_val = next((v for v in reversed(values) if v is not None), None)
            ranked.append((hostname, values, growth, last_growth, last_val))

        ranked.sort(key=lambda x: x[3] if x[3] is not None else float("-inf"), reverse=True)
        ranked = ranked[:top_n]

        col_host = max(len(r[0]) for r in ranked) if ranked else 10
        col_host = max(col_host, 10)
        col_period = 14

        print(f"\n{'='*70}")
        print(f" Top-{top_n}: {meta['label']}")
        print('='*70)

        header = f"{'Host':<{col_host}}"
        for label in period_labels:
            header += f"  {label:>{col_period}}"
        header += f"  {'Growth':>{col_period}}"
        print(header)
        print('-' * len(header))

        for hostname, values, growth, last_growth, last_val in ranked:
            row = f"{hostname:<{col_host}}"
            for val in values:
                row += f"  {format_val(val, meta['unit']):>{col_period}}"
            row += f"  {format_growth(last_growth):>{col_period}}"
            print(row)


def print_top_summary(all_results, periods, mode, top_n):
    period_labels = []
    for time_from, time_till in periods:
        if mode == "week":
            label = datetime.fromtimestamp(time_from).strftime("W%W %Y")
        else:
            label = datetime.fromtimestamp(time_from).strftime("%b %Y")
        period_labels.append(label)

    host_scores = defaultdict(list)
    for metric_key, data in all_results.items():
        for hostname, values in data.items():
            growth = calc_growth(values)
            last_growth = next((g for g in reversed(growth) if g is not None), None)
            if last_growth is not None:
                host_scores[hostname].append(last_growth)

    if not host_scores:
        print("\nNo data available.")
        return

    ranked = sorted(host_scores.items(),
                    key=lambda x: sum(x[1]) / len(x[1]),
                    reverse=True)[:top_n]
    ranked_hosts = [r[0] for r in ranked]

    col_host = max(len(h) for h in ranked_hosts) if ranked_hosts else 10
    col_host = max(col_host, 10)
    col_metric = 12

    print(f"\n{'='*70}")
    print(f" Top-{top_n} summary (sorted by avg growth across all metrics)")
    print('='*70)

    metrics_list = list(METRICS.keys())
    header = f"{'Host':<{col_host}}"
    for mk in metrics_list:
        header += f"  {METRICS[mk]['label'][:col_metric]:>{col_metric}}"
    print(header)
    print('-' * len(header))

    for hostname in ranked_hosts:
        row = f"{hostname:<{col_host}}"
        for mk in metrics_list:
            data = all_results.get(mk, {})
            values = data.get(hostname)
            if values:
                growth = calc_growth(values)
                last_growth = next((g for g in reversed(growth) if g is not None), None)
                row += f"  {format_growth(last_growth):>{col_metric}}"
            else:
                row += f"  {'N/A':>{col_metric}}"
        print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Zabbix load growth analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode week --count 4
  %(prog)s --mode month --count 3 --top 5
  %(prog)s --mode week --count 8 --output summary
  %(prog)s --mode month --count 6 --top 20 --output separate

Environment variables:
  export ZABBIX_URL="https://zabbix.example.com/api_jsonrpc.php"
  export ZABBIX_TOKEN="your_token_here"
        """
    )
    parser.add_argument("--env", metavar="FILE", help="Path to .env file (default: .env)")
    parser.add_argument("--mode", choices=["week", "month"], default="week",
                        help="Comparison period: week or month (default: week)")
    parser.add_argument("--count", type=int, default=4,
                        help="Number of periods to analyze (default: 4)")
    parser.add_argument("--top", type=int, default=10,
                        help="Number of top hosts to display (default: 10)")
    parser.add_argument("--output", choices=["separate", "summary"], default="separate",
                        help="Output format: separate tables per metric or summary (default: separate)")
    parser.add_argument("--group", nargs="+", metavar="GROUP",
                        help="Limit analysis to specific host groups")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.count < 2:
        print("Error: --count must be at least 2.")
        sys.exit(1)

    client.init(args.env)
    session = make_session()

    try:
        hosts = get_all_hosts(session)

        if args.group:
            groups = zabbix_api(session, "hostgroup.get", {
                "output": ["groupid", "name"],
                "filter": {"name": args.group}
            })
            if not groups:
                print(f"Error: no groups found: {', '.join(args.group)}")
                sys.exit(1)
            groupids = [g["groupid"] for g in groups]
            group_hosts = zabbix_api(session, "host.get", {
                "output": ["hostid"],
                "groupids": groupids,
                "filter": {"status": 0}
            })
            allowed = {h["hostid"] for h in group_hosts}
            hosts = [h for h in hosts if h["hostid"] in allowed]

        if not hosts:
            print("No hosts found.")
            sys.exit(1)

        print(f"Analyzing {len(hosts)} host(s), {args.count} {args.mode}(s)...")

        periods = get_periods(args.mode, args.count)

        all_results = {}
        for metric_key in METRICS:
            print(f"  Collecting {METRICS[metric_key]['label']}...")
            all_results[metric_key] = collect_metric(session, hosts, metric_key, periods)

        if args.output == "separate":
            print_top_separate(all_results, periods, args.mode, args.top)
        else:
            print_top_summary(all_results, periods, args.mode, args.top)
    finally:
        session.close()


if __name__ == "__main__":
    main()
