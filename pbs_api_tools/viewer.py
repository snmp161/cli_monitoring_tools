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

            if last_backup:
                age = now - last_backup
                age_str = format_duration(age)
                ts_str = format_ts(last_backup)
            else:
                age_str = "never"
                ts_str = "—"

            print(f"  [{backup_type}] {backup_id}")
            print(f"    Last    : {ts_str}  ({age_str} ago)")
            print(f"    Snaps   : {count}")
            print(f"    Owner   : {owner}")

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
    parser.add_argument("--duty-shift", action="store_true",
                        help="Show only backups older than 12 hours (for --backups)")
    parser.add_argument("--duty-day", action="store_true",
                        help="Show only backups older than 24 hours (for --backups)")
    parser.add_argument("--server", action="store_true",
                        help="Show server status")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.datastores and not args.backups and not args.server:
        parser.print_help()
        sys.exit(0)

    if args.datastore and not args.backups:
        print("Error: --datastore is only used with --backups.")
        sys.exit(1)

    if (args.duty_shift or args.duty_day) and not args.backups:
        print("Error: --duty-shift and --duty-day are only used with --backups.")
        sys.exit(1)

    if args.duty_shift and args.duty_day:
        print("Error: --duty-shift and --duty-day are mutually exclusive.")
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

        if args.server:
            cmd_server(session)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
