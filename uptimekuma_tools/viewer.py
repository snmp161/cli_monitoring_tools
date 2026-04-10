#!/usr/bin/env python3

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from uptime_kuma_api import UptimeKumaApi, MonitorStatus

load_dotenv()

UPTIMEKUMA_URL = os.environ.get("UPTIMEKUMA_URL", "http://localhost:3001")
UPTIMEKUMA_USERNAME = os.environ.get("UPTIMEKUMA_USERNAME", "")
UPTIMEKUMA_PASSWORD = os.environ.get("UPTIMEKUMA_PASSWORD", "")

STATUS_MAP = {
    MonitorStatus.DOWN: "DOWN",
    MonitorStatus.UP: "UP",
    MonitorStatus.PENDING: "PENDING",
    MonitorStatus.MAINTENANCE: "MAINTENANCE",
}


def connect_api():
    api = UptimeKumaApi(UPTIMEKUMA_URL, timeout=15)
    if UPTIMEKUMA_USERNAME and UPTIMEKUMA_PASSWORD:
        api.login(UPTIMEKUMA_USERNAME, UPTIMEKUMA_PASSWORD)
    else:
        raise RuntimeError(
            "No credentials. Set UPTIMEKUMA_USERNAME + UPTIMEKUMA_PASSWORD in .env"
        )
    return api


def format_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    elif m:
        return f"{m}m {s}s"
    return f"{s}s"


def parse_beat_time(time_str):
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


def monitor_type_str(monitor):
    t = monitor.get("type", "")
    if hasattr(t, "value"):
        return str(t.value).upper()
    return str(t).upper()


def monitor_target(monitor):
    url = monitor.get("url", "")
    if url:
        return url
    hostname = monitor.get("hostname", "")
    port = monitor.get("port")
    if hostname and port:
        return f"{hostname}:{port}"
    if hostname:
        return hostname
    return "—"


def print_monitor_problem(monitor, beats, now):
    mon_type = monitor_type_str(monitor)

    down_beats = [b for b in beats if b.get("status") == MonitorStatus.DOWN]
    up_beats = [b for b in beats if b.get("status") == MonitorStatus.UP]
    total = len(beats)
    uptime_pct = (len(up_beats) / total * 100) if total else 0
    downtime_sec = sum(b.get("duration", 0) for b in down_beats)

    pings = [b["ping"] for b in beats if b.get("ping") is not None and b["ping"] > 0]
    avg_ping = sum(pings) / len(pings) if pings else 0

    last_beat = max(beats, key=lambda b: b.get("time", "")) if beats else None
    last_status = STATUS_MAP.get(last_beat.get("status"), "—") if last_beat else "—"
    last_msg = last_beat.get("msg", "—") if last_beat else "—"

    # find when the first DOWN started in this beat set
    important_downs = sorted(
        [b for b in beats if b.get("important") and b.get("status") == MonitorStatus.DOWN],
        key=lambda b: b.get("time", "")
    )
    if important_downs:
        down_since = parse_beat_time(important_downs[0]["time"])
        problem_msg = important_downs[0].get("msg", "—")
    else:
        down_since = parse_beat_time(down_beats[0]["time"]) if down_beats else None
        problem_msg = down_beats[0].get("msg", "—") if down_beats else "—"

    ts = down_since.strftime("%Y-%m-%d %H:%M:%S") if down_since else "—"
    resolved = " [RESOLVED]" if last_status == "UP" else ""

    print(f"[{ts}] [{mon_type}]{resolved}")
    print(f"  ID          : {monitor['id']}")
    print(f"  Name        : {monitor.get('name', '—')}")
    print(f"  Problem     : {problem_msg}")
    print(f"  Downtime    : {format_duration(downtime_sec)}")
    print(f"  Uptime      : {uptime_pct:.1f}%")
    print(f"  Avg ping    : {avg_ping:.0f}ms")
    print(f"  Last status : {last_status}")
    print(f"  Last message: {last_msg}")
    print()


def show_problems(api, hours=None):
    monitors = api.get_monitors()
    active_monitors = [m for m in monitors if m.get("active")]
    now = datetime.now()

    if hours is None:
        down_monitors = [
            m for m in active_monitors
            if m.get("status") in (MonitorStatus.DOWN, MonitorStatus.PENDING)
        ]
        title = "DOWN monitors"
        print(f"\n{'='*70}")
        print(f" {title} ({len(down_monitors)})")
        print('='*70)

        if not down_monitors:
            print(f" All good — {len(active_monitors)} monitors are UP, no problems detected.")
            return

        for m in down_monitors:
            try:
                beats = api.get_monitor_beats(m["id"], 72)
            except Exception as e:
                print(f"  Warning: cannot get beats for monitor {m['id']}: {e}")
                beats = []
            print_monitor_problem(m, beats, now)
    else:
        label = f"{hours} hours"
        title = f"Monitors with DOWN beats — last {label}"

        problem_monitors = []
        for m in active_monitors:
            try:
                beats = api.get_monitor_beats(m["id"], hours)
            except Exception as e:
                print(f"  Warning: cannot get beats for monitor {m['id']}: {e}")
                continue
            down_beats = [b for b in beats if b.get("status") == MonitorStatus.DOWN]
            if down_beats:
                problem_monitors.append((m, beats))

        print(f"\n{'='*70}")
        print(f" {title} ({len(problem_monitors)})")
        print('='*70)

        if not problem_monitors:
            print(f" All good — no DOWN beats across {len(active_monitors)} monitors in the last {label}.")
            return

        for m, beats in problem_monitors:
            print_monitor_problem(m, beats, now)


def resolve_monitor(api, args):
    monitors = api.get_monitors()

    if args.id is not None:
        for m in monitors:
            if m["id"] == args.id:
                return m
        raise RuntimeError(f"Monitor with id {args.id} not found.")

    query = args.name.lower()
    matches = [m for m in monitors if query in m.get("name", "").lower()]

    if not matches:
        raise RuntimeError(f"No monitors matching '{args.name}'.")

    if len(matches) == 1:
        return matches[0]

    print(f"Multiple monitors match '{args.name}':")
    for m in matches:
        print(f"  id:{m['id']}  {m.get('name', '—')}")
    print()
    raise RuntimeError("Ambiguous name. Use --id to specify exact monitor.")


def show_history(api, monitor, hours):
    beats = api.get_monitor_beats(monitor["id"], hours)
    label = "12 hours" if hours == 12 else "24 hours"

    print(f"\n{'='*70}")
    print(f" Monitor: {monitor.get('name', '—')} (id:{monitor['id']}) — last {label}")
    print('='*70)
    print(f"  Type      : {monitor_type_str(monitor)}")
    print(f"  Target    : {monitor_target(monitor)}")
    print(f"  Interval  : {monitor.get('interval', '—')}s")

    # Summary
    total = len(beats)
    down_beats = [b for b in beats if b.get("status") == MonitorStatus.DOWN]
    up_beats = [b for b in beats if b.get("status") == MonitorStatus.UP]
    down_count = len(down_beats)
    up_count = len(up_beats)
    uptime_pct = (up_count / total * 100) if total else 0
    downtime_sec = sum(b.get("duration", 0) for b in down_beats)

    pings = [b["ping"] for b in beats if b.get("ping") is not None and b["ping"] > 0]
    avg_ping = sum(pings) / len(pings) if pings else 0
    min_ping = min(pings) if pings else 0
    max_ping = max(pings) if pings else 0

    print(f"\n{'-'*70}")
    print(f"  Summary")
    print(f"{'-'*70}")
    print(f"  Total beats : {total}")
    print(f"  UP          : {up_count} ({uptime_pct:.1f}%)")
    print(f"  DOWN        : {down_count} ({100 - uptime_pct:.1f}%)")
    print(f"  Downtime    : {format_duration(downtime_sec)}")
    print(f"  Avg ping    : {avg_ping:.0f}ms")
    print(f"  Min ping    : {min_ping}ms")
    print(f"  Max ping    : {max_ping}ms")

    # Status changes
    changes = sorted(
        [b for b in beats if b.get("important")],
        key=lambda b: b.get("time", "")
    )

    print(f"\n{'-'*70}")
    print(f"  Status changes ({len(changes)})")
    print(f"{'-'*70}")

    if not changes:
        print("  (no status changes in this period)")
    else:
        for beat in changes:
            ts = beat.get("time", "—")
            dt = parse_beat_time(ts)
            if dt:
                ts = dt.strftime("%Y-%m-%d %H:%M:%S")
            status = STATUS_MAP.get(beat.get("status"), "?")
            msg = beat.get("msg", "")
            ping = beat.get("ping")
            line = f"  [{ts}] {status:<5}"
            if msg:
                line += f'  "{msg}"'
            if ping and ping > 0:
                line += f"  ping: {ping}ms"
            print(line)

    print()


def main():
    parser = argparse.ArgumentParser(
        description="UptimeKuma monitor viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --problems                         Current DOWN monitors
  %(prog)s --problems --duty-shift            Monitors with DOWN in last 12h
  %(prog)s --problems --duty-day              Monitors with DOWN in last 24h
  %(prog)s --history --id 5 --duty-shift      History for monitor #5, last 12h
  %(prog)s --history --name "API" --duty-day  History by name, last 24h

Environment variables:
  UPTIMEKUMA_URL=http://uptimekuma.example.com:3001
  UPTIMEKUMA_USERNAME=admin
  UPTIMEKUMA_PASSWORD=your_password_here
        """
    )
    parser.add_argument("--problems", action="store_true",
                        help="Show DOWN monitors")
    parser.add_argument("--history", action="store_true",
                        help="Show heartbeat history for a monitor")

    duty = parser.add_mutually_exclusive_group()
    duty.add_argument("--duty-shift", action="store_true",
                      help="Period: last 12 hours")
    duty.add_argument("--duty-day", action="store_true",
                      help="Period: last 24 hours")

    target = parser.add_mutually_exclusive_group()
    target.add_argument("--id", type=int, default=None,
                        help="Monitor ID (for --history)")
    target.add_argument("--name", type=str, default=None,
                        help="Monitor name, partial match (for --history)")

    args = parser.parse_args()

    if not args.problems and not args.history:
        parser.print_help()
        sys.exit(0)

    if args.history and args.id is None and args.name is None:
        print("Error: --history requires --id or --name.")
        sys.exit(1)

    if args.history and not args.duty_shift and not args.duty_day:
        print("Error: --history requires --duty-shift or --duty-day.")
        sys.exit(1)

    if (args.id is not None or args.name is not None) and not args.history:
        print("Error: --id and --name are only used with --history.")
        sys.exit(1)

    api = None
    try:
        api = connect_api()

        if args.problems:
            if args.duty_shift:
                show_problems(api, hours=12)
            elif args.duty_day:
                show_problems(api, hours=24)
            else:
                show_problems(api)

        if args.history:
            monitor = resolve_monitor(api, args)
            hours = 12 if args.duty_shift else 24
            show_history(api, monitor, hours)

    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if api:
            api.disconnect()


if __name__ == "__main__":
    main()
