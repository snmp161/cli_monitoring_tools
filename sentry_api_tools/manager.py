#!/usr/bin/env python3

import argparse
import sys

import client
from client import SentryClient


def fmt_assignee(assignee):
    if not assignee:
        return "—"
    name = assignee.get("name", "")
    email = assignee.get("email", "")
    return f"{name} ({email})" if email else name or "—"


def cmd_resolve(client, args):
    status_details = {}
    if args.in_next_release:
        status_details["inNextRelease"] = True
    elif args.in_release:
        status_details["inRelease"] = args.in_release

    issue = client.put(f"/issues/{args.id}/", {"status": "resolved", "statusDetails": status_details})

    print(f"\n{'='*70}")
    print(f" Issue #{args.id}")
    print('='*70)
    print(f"  Title  : {issue.get('title', '—')}")
    status_line = issue.get("status", "—")
    if args.in_next_release:
        status_line += "  (in next release)"
    elif args.in_release:
        status_line += f"  (in release: {args.in_release})"
    print(f"  Status : {status_line}")
    print()


def cmd_ignore(client, args):
    status_details = {}
    if args.duration:
        status_details["ignoreDuration"] = args.duration
    if args.count:
        status_details["ignoreCount"] = args.count
        if args.count_window:
            status_details["ignoreWindow"] = args.count_window
    if args.user_count:
        status_details["ignoreUserCount"] = args.user_count
        if args.user_window:
            status_details["ignoreUserWindow"] = args.user_window

    data = {"status": "ignored"}
    if status_details:
        data["statusDetails"] = status_details

    issue = client.put(f"/issues/{args.id}/", data)

    print(f"\n{'='*70}")
    print(f" Issue #{args.id}")
    print('='*70)
    print(f"  Title  : {issue.get('title', '—')}")
    print(f"  Status : {issue.get('status', '—')}")
    if args.duration:
        print(f"  Snooze : {args.duration} min")
    if args.count:
        count_str = f"occurrences > {args.count}"
        if args.count_window:
            count_str += f" per {args.count_window} min"
        print(f"  Snooze : {count_str}")
    if args.user_count:
        user_str = f"users > {args.user_count}"
        if args.user_window:
            user_str += f" per {args.user_window} min"
        print(f"  Snooze : {user_str}")
    print()


def cmd_assign(client, args):
    issue = client.put(f"/issues/{args.id}/", {"assignedTo": args.to})

    print(f"\n{'='*70}")
    print(f" Issue #{args.id}")
    print('='*70)
    print(f"  Title    : {issue.get('title', '—')}")
    print(f"  Assignee : {fmt_assignee(issue.get('assignedTo'))}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Sentry API manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s resolve 123456789
  %(prog)s resolve 123456789 --in-next-release
  %(prog)s resolve 123456789 --in-release 2.4.1

  %(prog)s ignore 123456789
  %(prog)s ignore 123456789 --duration 480
  %(prog)s ignore 123456789 --count 100 --count-window 60
  %(prog)s ignore 123456789 --user-count 50 --user-window 120
  %(prog)s ignore 123456789 --duration 1440 --count 500 --count-window 60

  %(prog)s assign 123456789 --to john@example.com
  %(prog)s assign 123456789 --to username
  %(prog)s assign 123456789 --to team:backend

Environment variables:
  export SENTRY_URL="https://sentry.example.com/"
  export SENTRY_TOKEN="your_token_here"
        """
    )

    parser.add_argument("--env", metavar="FILE", help="Path to .env file (default: .env)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve an issue")
    p_resolve.add_argument("id", help="Issue ID")
    release_mode = p_resolve.add_mutually_exclusive_group()
    release_mode.add_argument("--in-next-release", action="store_true",
                              help="Mark as resolved in the next release")
    release_mode.add_argument("--in-release", metavar="VERSION",
                              help="Mark as resolved in a specific release version")

    p_ignore = sub.add_parser("ignore", help="Ignore (snooze) an issue")
    p_ignore.add_argument("id", help="Issue ID")
    p_ignore.add_argument("--duration", type=int, metavar="MIN",
                          help="Snooze for N minutes")
    p_ignore.add_argument("--count", type=int, metavar="N",
                          help="Re-surface after N occurrences")
    p_ignore.add_argument("--count-window", type=int, metavar="MIN",
                          help="Time window in minutes for --count (optional)")
    p_ignore.add_argument("--user-count", type=int, metavar="N",
                          help="Re-surface after N unique users affected")
    p_ignore.add_argument("--user-window", type=int, metavar="MIN",
                          help="Time window in minutes for --user-count (optional)")

    p_assign = sub.add_parser("assign", help="Assign an issue to a user or team")
    p_assign.add_argument("id", help="Issue ID")
    p_assign.add_argument("--to", "-t", required=True, metavar="USER",
                          help="Username, email, or team:slug")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.command == "ignore":
        if args.count_window and not args.count:
            print("Error: --count-window requires --count.")
            sys.exit(1)
        if args.user_window and not args.user_count:
            print("Error: --user-window requires --user-count.")
            sys.exit(1)

    client.init(args.env)
    sentry = SentryClient(client.SENTRY_URL, client.SENTRY_TOKEN)
    commands = {
        "resolve": cmd_resolve,
        "ignore": cmd_ignore,
        "assign": cmd_assign,
    }
    try:
        commands[args.command](sentry, args)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        sentry.session.close()


if __name__ == "__main__":
    main()
