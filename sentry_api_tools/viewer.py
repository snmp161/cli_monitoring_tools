#!/usr/bin/env python3

import argparse
import sys
from datetime import datetime, timedelta, timezone

import client
from client import SentryClient


def fmt_date(iso_str):
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_str


def fmt_assignee(assignee):
    if not assignee:
        return "—"
    name = assignee.get("name", "")
    email = assignee.get("email", "")
    return f"{name} ({email})" if email else name or "—"


def separator(char="-", width=70):
    print(char * width)


def print_issue_block(issue):
    first_seen = issue.get("firstSeen", "")
    status = issue.get("status", "unresolved")
    level = issue.get("level", "?")

    status_str = " [RESOLVED]" if status == "resolved" else ""

    print(f"[{fmt_date(issue.get('lastSeen'))}] [{level}]{status_str}")
    print(f"  ID        : {issue.get('id', '—')}")
    print(f"  Count     : {issue.get('count', 0)}")
    print(f"  Users     : {issue.get('userCount', 0)}")
    print(f"  First seen: {fmt_date(first_seen)}")
    print(f"  Assignee  : {fmt_assignee(issue.get('assignedTo'))}")
    print(f"  Problem   : {issue.get('title', '—')}")
    print()


def cmd_projects(client, _args):
    orgs = client.get("/organizations/")
    if not orgs:
        print("No organizations found.")
        return

    for org in orgs:
        org_slug = org["slug"]
        print(f"\n{'='*70}")
        print(f" Organization: {org['name']} (slug: {org_slug})")
        print('='*70)

        projects = client.get(f"/organizations/{org_slug}/projects/")
        if not projects:
            print("  No projects.")
            continue

        for p in projects:
            platform = p.get("platform") or "unknown"
            print(f"  {p['slug']:<30} platform: {platform:<15} id: {p['id']}")
    print()


def resolve_project_id(client, org_slug, project):
    if project.isdecimal():
        return project
    projects = client.get(f"/organizations/{org_slug}/projects/")
    for p in projects:
        if p["slug"] == project or p["name"] == project:
            return p["id"]
    raise RuntimeError(
        f"Project '{project}' not found in organization '{org_slug}'. "
        f"Use 'projects' command to list available projects."
    )


def cmd_issues(client, args):
    orgs = client.get("/organizations/")
    if not orgs:
        print("No organizations found.")
        return

    now = datetime.now(timezone.utc)
    base_query = args.query or "is:unresolved"

    if args.duty_shift:
        since = now - timedelta(hours=12)
        query = f"{base_query} lastSeen:>{since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        title_suffix = "last 12 hours"
    elif args.duty_day:
        since = now - timedelta(hours=24)
        query = f"{base_query} lastSeen:>{since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        title_suffix = "last 24 hours"
    else:
        query = base_query
        title_suffix = None

    for org in orgs:
        org_slug = org["slug"]
        params = {"query": query}
        if args.current:
            params["limit"] = args.limit
        if args.project:
            params["project"] = resolve_project_id(client, org_slug, args.project)

        issues = client.get(f"/organizations/{org_slug}/issues/", params=params)

        print(f"\n{'='*70}")
        if title_suffix:
            print(f" Issues [{args.project}]  {title_suffix}")
        else:
            print(f" Issues [{args.project}]  query: \"{query}\"  limit: {args.limit}")
        print('='*70)
        print()

        if not issues:
            print("  No issues found.")
            continue

        for issue in issues:
            print_issue_block(issue)


def cmd_issue(client, args):
    issue = client.get(f"/issues/{args.id}/")
    latest_event = client.get(f"/issues/{args.id}/events/latest/")

    print(f"\n{'='*70}")
    print(f" Issue #{args.id}")
    print('='*70)
    full_title = issue.get("title") or "—"
    print(f"  Title     : {full_title}")
    print(f"  Type      : {issue.get('type', '—')}")
    print(f"  Level     : {issue.get('level', '—')}")
    print(f"  Status    : {issue.get('status', '—')}")
    print(f"  Platform  : {issue.get('platform', '—')}")
    print(f"  Project   : {issue.get('project', {}).get('slug', '—')}")
    print(f"  Event ID  : {latest_event.get('id', '—')}")
    print(f"  Permalink : {issue.get('permalink', '—')}")
    separator()
    print(f"  First seen: {fmt_date(issue.get('firstSeen'))}")
    print(f"  Last seen : {fmt_date(issue.get('lastSeen'))}")
    print(f"  Events    : {issue.get('count', 0)}  Users: {issue.get('userCount', 0)}")

    print(f"  Assignee  : {fmt_assignee(issue.get('assignedTo'))}")

    tags = client.get(f"/issues/{args.id}/tags/")
    if tags:
        separator()
        print("  Tags:")
        for tag in tags:
            top = tag.get("topValues", [{}])[0]
            print(f"    {tag['key']:<20} = {top.get('value', '—')} ({top.get('count', 0)} hits)")

    full_message = None
    for entry in latest_event.get("entries", []):
        if entry.get("type") == "exception":
            for exc in entry.get("data", {}).get("values", []):
                val = exc.get("value", "")
                if val:
                    exc_type = exc.get("type", "")
                    full_message = f"{exc_type}: {val}" if exc_type else val
                    break
        if full_message:
            break
    if not full_message:
        full_message = latest_event.get("message") or full_title

    separator()
    print(f"  Message   : {full_message}")

    if args.events and not args.stacktrace:
        separator()
        print("  Latest events:")
        events = client.get(f"/issues/{args.id}/events/", params={"limit": args.events})
        for ev in events:
            ev_date = fmt_date(ev.get("dateCreated"))
            ev_id = ev.get("id", "")
            ev_msg = ev.get("message") or ev.get("title") or ""
            print(f"    [{ev_date}] id:{ev_id}  {ev_msg}")

    if args.stacktrace:
        separator()
        print("  Stacktrace (latest event):")
        for entry in latest_event.get("entries", []):
            if entry.get("type") == "exception":
                for exc in entry.get("data", {}).get("values", []):
                    print(f"\n  {exc.get('type')}: {exc.get('value')}")
                    frames = exc.get("stacktrace", {}).get("frames", [])
                    for frame in frames[-5:]:
                        filename = frame.get("filename") or frame.get("module") or "?"
                        lineno = frame.get("lineNo", "?")
                        func = frame.get("function") or "?"
                        print(f"    File \"{filename}\", line {lineno}, in {func}")
                        for ctx in frame.get("context", []):
                            if ctx[0] == lineno:
                                print(f"      > {ctx[1].strip()}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Sentry API viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s projects
  %(prog)s issues --current --project myproject
  %(prog)s issues --current --project myproject --limit 50 --query "is:unresolved level:error"
  %(prog)s issues --duty-shift --project myproject
  %(prog)s issues --duty-day --project myproject
  %(prog)s issue 123456789
  %(prog)s issue 123456789 --events 25
  %(prog)s issue 123456789 --stacktrace

Environment variables:
  export SENTRY_URL="https://sentry.example.com/"
  export SENTRY_TOKEN="your_token_here"
        """
    )

    parser.add_argument("--env", metavar="FILE", help="Path to .env file (default: .env)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("projects", help="List all projects")

    p_issues = sub.add_parser("issues", help="List unresolved issues")
    mode = p_issues.add_mutually_exclusive_group(required=True)
    mode.add_argument("--current", action="store_true", help="Show all issues")
    mode.add_argument("--duty-shift", action="store_true",
                      help="Issues last seen in last 12 hours")
    mode.add_argument("--duty-day", action="store_true",
                      help="Issues last seen in last 24 hours")

    p_issues.add_argument("--project", "-p", help="Project slug or ID")
    p_issues.add_argument("--query", "-q", help="Filter query (default: is:unresolved)")
    p_issues.add_argument("--limit", "-l", type=int, default=25,
                          help="Max results for --current (default: 25); ignored for --duty-shift/--duty-day")

    p_issue = sub.add_parser("issue", help="Issue details")
    p_issue.add_argument("id", help="Issue ID")
    p_issue.add_argument("--events", "-e", type=int, metavar="N",
                         help="Show N latest events (hidden by default)")
    p_issue.add_argument("--stacktrace", "-s", action="store_true", help="Show stacktrace")


    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.command == "issues" and not args.project:
        print("Error: --project is required.")
        sys.exit(1)

    client.init(args.env)
    sentry = SentryClient(client.SENTRY_URL, client.SENTRY_TOKEN)
    commands = {
        "projects": cmd_projects,
        "issues": cmd_issues,
        "issue": cmd_issue,
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
