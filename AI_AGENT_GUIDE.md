# CLI Monitoring Tools — AI Agent Guide

You are interacting with a set of CLI monitoring tools. Each tool is a Python script that queries an external service API and prints human-readable output to stdout. Your job is to run the appropriate command based on the user's request and relay the output.

## General rules

- All scripts are in subdirectories of this repository. Always `cd` into the tool directory before running.
- All scripts support `--env FILE` to specify a custom .env file. Use this when the user references a specific server (e.g. "check backups on pbs-02" → `--env .env.pbs-02`).
- Without `--env`, the default `.env` in the tool directory is used.
- Output is plain text. Present it to the user as-is or summarize if they asked a general question.
- If a command fails with "Error:", report the error message to the user.
- Never modify .env files or credentials. If credentials are missing, tell the user to configure .env.

## Quick reference: user intent → command

### Sentry (sentry_api_tools/)

| User asks | Command |
|-----------|---------|
| list sentry projects | `python viewer.py projects` |
| show sentry issues for project X | `python viewer.py issues --current --project X` |
| sentry issues for last 12h / shift | `python viewer.py issues --duty-shift --project X` |
| sentry issues for last 24h / day | `python viewer.py issues --duty-day --project X` |
| details on sentry issue N | `python viewer.py issue N` |
| stacktrace for sentry issue N | `python viewer.py issue N --stacktrace` |
| recent events for sentry issue N | `python viewer.py issue N --events 25` |
| resolve sentry issue N | `python manager.py resolve N` |
| ignore/snooze sentry issue N | `python manager.py ignore N --duration 480` |
| assign sentry issue N to user/team | `python manager.py assign N --to user@example.com` |

Note: `--project` is required for `issues` command. Ask the user which project if not specified, or run `projects` first to list them.

### Zabbix (zabbix_api_tools/)

| User asks | Command |
|-----------|---------|
| current/active zabbix problems | `python problems_viewer.py --current` |
| zabbix problems for last 12h / shift | `python problems_viewer.py --duty-shift` |
| zabbix problems for last 24h / day | `python problems_viewer.py --duty-day` |
| zabbix problems for last week | `python problems_viewer.py --duty-week` |
| zabbix problems for last month | `python problems_viewer.py --duty-month` |
| problems grouped by host | add `--hosts` to any of the above |
| problems grouped by problem name | add `--problems` to any of the above |
| full action history on problems | add `--history` to any of the above |
| load/resource growth trends | `python trends_viewer.py --mode week --count 4` |
| trends by month, top 5 | `python trends_viewer.py --mode month --count 3 --top 5` |
| acknowledge zabbix problem | `python trouble_manager.py --problem ack --event-id ID` |
| close zabbix problem | `python trouble_manager.py --problem close --event-id ID` |
| suppress zabbix problem on host | `python trouble_manager.py --problem suppress --host HOSTNAME` |
| create maintenance window | `python trouble_manager.py --maintenance create --name "NAME" --host H1 H2 --duration MINUTES` |
| list maintenance windows | `python trouble_manager.py --maintenance list` |
| delete maintenance window | `python trouble_manager.py --maintenance delete --maintenance-id ID` |

### Uptime Kuma (uptimekuma_tools/)

| User asks | Command |
|-----------|---------|
| what's down / current problems | `python viewer.py --problems` |
| monitors with downtime in last 12h | `python viewer.py --problems --duty-shift` |
| monitors with downtime in last 24h | `python viewer.py --problems --duty-day` |
| history for specific monitor (by ID) | `python viewer.py --history --id N --duty-shift` |
| history for monitor (by name) | `python viewer.py --history --name "NAME" --duty-day` |

### Proxmox Backup Server (pbs_api_tools/)

| User asks | Command |
|-----------|---------|
| list datastores / storage usage | `python viewer.py --datastores` |
| show all backups | `python viewer.py --backups` |
| backups for specific datastore | `python viewer.py --backups --datastore NAME` |
| stale backups (older than 12h) | `python viewer.py --backups --duty-shift` |
| stale backups (older than 24h) | `python viewer.py --backups --duty-day` |
| backup tasks for last 12h | `python viewer.py --tasks --duty-shift` |
| backup tasks for last 24h | `python viewer.py --tasks --duty-day` |
| failed tasks only | `python viewer.py --tasks --duty-day --not-ok` |
| server status (CPU, RAM, uptime) | `python viewer.py --server` |

### Domain Tools (domain_tools/)

| User asks | Command |
|-----------|---------|
| check domain expiry (general) | `python expiry_checker.py domains.txt` |
| check with custom warning threshold | `python expiry_checker.py domains.txt --warn 60` |
| check GoDaddy domains | `python godaddy_checker.py godaddy_domains.txt` |
| check specific domains via GoDaddy | `python godaddy_checker.py example.com example.org` |

Note: `expiry_checker.py` does not require API keys. `godaddy_checker.py` requires GoDaddy API credentials in `.env`.

## Multi-server usage

When the user mentions a specific server name, use `--env .env.SERVERNAME`:

```bash
python viewer.py --env .env.pbs-01 --backups
python viewer.py --env .env.pbs-02 --server
python problems_viewer.py --env .env.zabbix-prod --current
```

If the user says "check all servers", run the command for each .env file and combine results.

## Interpreting "duty" terminology

- **duty-shift** = last 12 hours (half-day operator shift)
- **duty-day** = last 24 hours (full-day operator shift)
- **duty-week** = last 7 days (Zabbix only)
- **duty-month** = last 30 days (Zabbix only)

When the user says "what happened on my shift" or "shift report", use `--duty-shift`.
When the user says "daily report" or "what happened today", use `--duty-day`.

## Combining commands

Multiple flags can be combined in a single run where supported:

```bash
# PBS: datastores + server status in one call
python viewer.py --datastores --server

# Zabbix: current problems + last 12h history
python problems_viewer.py --current --duty-shift --history
```

## Error handling

- "Error: ... must be set in .env or environment" → credentials not configured, tell the user
- "Error: Cannot connect to ..." → service is unreachable, check URL or network
- "Error: HTTP 401/403" → invalid token or insufficient permissions
- "Error: ... timed out" → service is slow or unresponsive, try again

## Output format

All tools produce plain-text output with consistent formatting:
- `======` lines separate major sections
- `------` lines separate subsections
- Each item is indented with `  ` (2 spaces) and fields are labeled (e.g. `Last    :`, `Status  :`)
- Counts appear in section headers: `Backups — local (9)`

When summarizing for the user, focus on: counts, statuses (OK/FAILED/DOWN), timestamps, and anything that looks abnormal (old backups, failed tasks, DOWN monitors).
