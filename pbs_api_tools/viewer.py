#!/usr/bin/env python3

import argparse
import sys
from datetime import datetime

from client import pbs_api, make_session


def format_bytes(size):
    if size is None:
        return "N/A"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PiB"


def format_duration(seconds):
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def format_ts(epoch):
    if not epoch:
        return "—"
    return datetime.fromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M:%S")


def cmd_datastore_list(session):
    datastores = pbs_api(session, "/admin/datastore")
    usage_list = pbs_api(session, "/status/datastore-usage")

    usage_map = {}
    for u in usage_list:
        name = u.get("store")
        if name:
            usage_map[name] = u

    print(f"\n{'='*70}")
    print(f" Datastores ({len(datastores)})")
    print('='*70)

    if not datastores:
        print("  No datastores found.")
        return

    for ds in datastores:
        name = ds.get("store") or ds.get("name", "—")
        comment = ds.get("comment", "")
        u = usage_map.get(name, {})
        total = u.get("total")
        used = u.get("used")
        avail = u.get("avail")

        if total and total > 0:
            pct = used / total * 100 if used else 0
            pct_str = f"{pct:.1f}%"
        else:
            pct_str = "N/A"

        print(f"\n  {name}")
        if comment:
            print(f"    Comment : {comment}")
        print(f"    Used    : {format_bytes(used)} / {format_bytes(total)}  ({pct_str})")
        print(f"    Free    : {format_bytes(avail)}")

    print()


def get_datastore_names(session):
    datastores = pbs_api(session, "/admin/datastore")
    return [ds.get("store") or ds.get("name") for ds in datastores if ds.get("store") or ds.get("name")]


def get_latest_snapshots(session, store):
    snapshots = pbs_api(session, f"/admin/datastore/{store}/snapshots")
    latest = {}
    for snap in snapshots:
        key = (snap.get("backup-type", ""), snap.get("backup-id", ""))
        backup_time = snap.get("backup-time", 0)
        if key not in latest or backup_time > latest[key].get("backup-time", 0):
            latest[key] = snap
    return latest


def cmd_backups(session, datastore_names, older_than_hours=None):
    now = datetime.now().timestamp()

    if older_than_hours:
        threshold = now - older_than_hours * 3600
        label = f"last backup older than {older_than_hours}h"
    else:
        threshold = None
        label = None

    for store in datastore_names:
        groups = pbs_api(session, f"/admin/datastore/{store}/groups")
        latest = get_latest_snapshots(session, store)

        if threshold is not None:
            groups = [
                g for g in groups
                if not g.get("last-backup") or g["last-backup"] < threshold
            ]

        title = f"Backups — {store}"
        if label:
            title += f" — {label}"
        title += f" ({len(groups)})"

        print(f"\n{'='*70}")
        print(f" {title}")
        print('='*70)

        if not groups:
            if label:
                print("  All backups are up to date.")
            else:
                print("  No backup groups found.")
            continue

        for g in sorted(groups, key=lambda x: x.get("last-backup", 0)):
            backup_type = g.get("backup-type", "?")
            backup_id = g.get("backup-id", "?")
            count = g.get("backup-count", 0)
            last_backup = g.get("last-backup")
            owner = g.get("owner", "—")

            snap = latest.get((backup_type, str(backup_id)), {})
            comment = snap.get("comment", "")
            size = snap.get("size")
            verification = snap.get("verification", {})
            verify_state = verification.get("state") if verification else None

            if last_backup:
                age = now - last_backup
                age_str = format_duration(age)
                ts_str = format_ts(last_backup)
            else:
                age_str = "never"
                ts_str = "—"

            if verify_state == "ok":
                verify_str = "OK"
            elif verify_state == "failed":
                verify_str = "FAILED"
            else:
                verify_str = "not verified"

            print(f"  [{backup_type}] {backup_id}")
            if comment:
                print(f"    Comment : {comment}")
            print(f"    Last    : {ts_str}  ({age_str} ago)")
            print(f"    Size    : {format_bytes(size)}")
            print(f"    Verify  : {verify_str}")
            print(f"    Snaps   : {count}")
            print(f"    Owner   : {owner}")

    print()


def cmd_tasks(session, hours, not_ok=False):
    now = datetime.now().timestamp()
    since = int(now - hours * 3600)

    tasks = pbs_api(session, "/nodes/localhost/tasks", params={"since": since})

    # filter out noise
    skip_types = {"termproxy", "aptupdate", "logrotate"}
    tasks = [t for t in tasks if t.get("worker_type") not in skip_types]

    if not_ok:
        tasks = [t for t in tasks if t.get("status") != "OK"]

    label = f"{hours} hours"
    if not_ok:
        label += " — NOT OK only"

    print(f"\n{'='*70}")
    print(f" Tasks — last {label} ({len(tasks)})")
    print('='*70)

    if not tasks:
        print(f"  No tasks in the last {label}.")
        print()
        return

    for t in sorted(tasks, key=lambda x: x.get("starttime", 0)):
        worker_type = t.get("worker_type", "?")
        worker_id = t.get("worker_id") or ""
        status = t.get("status", "?")
        user = t.get("user", "—")
        starttime = t.get("starttime", 0)
        endtime = t.get("endtime", 0)

        ts_str = format_ts(starttime)

        if endtime and starttime:
            duration = format_duration(endtime - starttime)
        else:
            duration = "running"

        if status == "OK":
            status_str = "OK"
        elif status:
            status_str = f"FAILED: {status}"
        else:
            status_str = "running"

        id_str = f" {worker_id}" if worker_id else ""

        print(f"  [{ts_str}] [{worker_type}]{id_str}")
        print(f"    Status  : {status_str}")
        print(f"    Duration: {duration}")
        print(f"    User    : {user}")

    print()


def cmd_server(session):
    status = pbs_api(session, "/nodes/localhost/status")
    version_info = pbs_api(session, "/version")

    cpu = status.get("cpu", 0)
    cpuinfo = status.get("cpuinfo", {})
    mem = status.get("memory", {})
    swap = status.get("swap", {})
    root = status.get("root", {})
    uptime = status.get("uptime", 0)
    loadavg = status.get("loadavg", [])
    kver = status.get("kversion", "—")
    pbs_ver = version_info.get("version", "—")
    release = version_info.get("release", "")

    cpu_model = cpuinfo.get("model", "—")
    cpu_cores = cpuinfo.get("cpus", "—")

    mem_total = mem.get("total", 0)
    mem_used = mem.get("used", 0)
    mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0

    swap_total = swap.get("total", 0)
    swap_used = swap.get("used", 0)

    root_total = root.get("total", 0)
    root_used = root.get("used", 0)
    root_avail = root.get("avail", 0)
    root_pct = (root_used / root_total * 100) if root_total > 0 else 0

    la_str = ", ".join(f"{v:.2f}" for v in loadavg) if loadavg else "—"

    print(f"\n{'='*70}")
    print(f" PBS Server")
    print('='*70)
    print(f"  Version  : {pbs_ver}-{release}" if release else f"  Version  : {pbs_ver}")
    print(f"  Kernel   : {kver}")
    print(f"  Uptime   : {format_duration(uptime)}")
    print(f"  CPU      : {cpu_model} ({cpu_cores} cores)")
    print(f"  CPU usage: {cpu * 100:.1f}%")
    print(f"  Load avg : {la_str}")
    print(f"  Memory   : {format_bytes(mem_used)} / {format_bytes(mem_total)}  ({mem_pct:.1f}%)")
    print(f"  Swap     : {format_bytes(swap_used)} / {format_bytes(swap_total)}")
    print(f"  Root FS  : {format_bytes(root_used)} / {format_bytes(root_total)}  ({root_pct:.1f}%)")
    print(f"  Root free: {format_bytes(root_avail)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Proxmox Backup Server viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --datastores                            List all datastores with usage
  %(prog)s --backups                               Backups across all datastores
  %(prog)s --backups --datastore local             Backups for a specific datastore
  %(prog)s --backups --duty-shift                  Backups older than 12 hours
  %(prog)s --backups --duty-day                    Backups older than 24 hours
  %(prog)s --backups --duty-shift --datastore local  Stale backups for specific datastore
  %(prog)s --tasks --duty-shift                    Tasks for last 12 hours
  %(prog)s --tasks --duty-day                      Tasks for last 24 hours
  %(prog)s --tasks --duty-day --not-ok             Failed tasks for last 24 hours
  %(prog)s --server                                Server status (CPU, RAM, uptime)

Environment variables:
  export PBS_URL="https://pbs.example.com:8007"
  export PBS_TOKEN_ID="user@realm!tokenname"
  export PBS_TOKEN_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        """
    )

    parser.add_argument("--datastores", action="store_true",
                        help="List all datastores with usage")
    parser.add_argument("--backups", action="store_true",
                        help="List backup groups")
    parser.add_argument("--datastore", metavar="NAME",
                        help="Datastore name (for --backups; default: all)")
    parser.add_argument("--tasks", action="store_true",
                        help="Show task history (requires --duty-shift or --duty-day)")
    parser.add_argument("--duty-shift", action="store_true",
                        help="12 hours period (for --backups: older than 12h; for --tasks: last 12h)")
    parser.add_argument("--duty-day", action="store_true",
                        help="24 hours period (for --backups: older than 24h; for --tasks: last 24h)")
    parser.add_argument("--not-ok", action="store_true",
                        help="Show only failed tasks (for --tasks)")
    parser.add_argument("--server", action="store_true",
                        help="Show server status")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.datastores and not args.backups and not args.tasks and not args.server:
        parser.print_help()
        sys.exit(0)

    if args.datastore and not args.backups:
        print("Error: --datastore is only used with --backups.")
        sys.exit(1)

    if (args.duty_shift or args.duty_day) and not args.backups and not args.tasks:
        print("Error: --duty-shift and --duty-day require --backups or --tasks.")
        sys.exit(1)

    if args.duty_shift and args.duty_day:
        print("Error: --duty-shift and --duty-day are mutually exclusive.")
        sys.exit(1)

    if args.tasks and not args.duty_shift and not args.duty_day:
        print("Error: --tasks requires --duty-shift or --duty-day.")
        sys.exit(1)

    if args.not_ok and not args.tasks:
        print("Error: --not-ok is only used with --tasks.")
        sys.exit(1)

    session = make_session()

    try:
        if args.datastores:
            cmd_datastore_list(session)

        if args.backups:
            if args.datastore:
                stores = [args.datastore]
            else:
                stores = get_datastore_names(session)

            if args.duty_shift:
                older_than = 12
            elif args.duty_day:
                older_than = 24
            else:
                older_than = None

            cmd_backups(session, stores, older_than)

        if args.tasks:
            hours = 12 if args.duty_shift else 24
            cmd_tasks(session, hours, args.not_ok)

        if args.server:
            cmd_server(session)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
