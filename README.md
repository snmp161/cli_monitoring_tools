# CLI Monitoring Tools

> [Русская версия](README.ru.md)

A collection of CLI utilities for working with monitoring systems and domain management. All utilities are written in Python 3 and interact with their respective services via API.

## Structure

```
├── sentry_api_tools/      # Sentry integration
├── zabbix_api_tools/      # Zabbix integration
├── uptimekuma_tools/      # Uptime Kuma integration
├── pbs_api_tools/         # Proxmox Backup Server integration
└── domain_tools/          # Domain expiry checking
```

## Sentry API Tools

View and manage Sentry issues via API.

### viewer.py

Browse projects and issues.

```bash
python viewer.py projects                                    # list all projects
python viewer.py issues --current --project myproject        # current issues
python viewer.py issues --duty-shift --project myproject     # issues from last 12 hours
python viewer.py issues --duty-day --project myproject       # issues from last 24 hours
python viewer.py issue 123456789                             # issue details
python viewer.py issue 123456789 --stacktrace                # with stacktrace
python viewer.py issue 123456789 --events 25                 # with latest events
```

### manager.py

Manage issues: resolve, ignore (snooze), assign.

```bash
python manager.py resolve 123456789                          # resolve issue
python manager.py resolve 123456789 --in-next-release        # resolve in next release
python manager.py ignore 123456789 --duration 480            # ignore for 480 minutes
python manager.py ignore 123456789 --count 100               # ignore until 100 occurrences
python manager.py assign 123456789 --to john@example.com     # assign to user
python manager.py assign 123456789 --to team:backend         # assign to team
```

**Environment variables:**
```
SENTRY_URL=https://sentry.example.com/
SENTRY_TOKEN=your_token_here
```

## Zabbix API Tools

Work with problems, trends and maintenance windows in Zabbix.

### problems_viewer.py

View current and historical problems.

```bash
python problems_viewer.py --current                          # active problems
python problems_viewer.py --duty-shift                       # last 12 hours
python problems_viewer.py --duty-day                         # last 24 hours
python problems_viewer.py --duty-week                        # last 7 days
python problems_viewer.py --duty-month                       # last 30 days
python problems_viewer.py --duty-shift --hosts               # group by host
python problems_viewer.py --duty-day --problems              # group by problem
python problems_viewer.py --current --history                # with full action history
```

### trends_viewer.py

Analyze load growth (CPU, memory, load average) across hosts over multiple periods. Shows top-N hosts with the highest metric growth.

```bash
python trends_viewer.py --mode week --count 4                # weekly comparison, 4 weeks
python trends_viewer.py --mode month --count 3 --top 5       # monthly, top 5 hosts
python trends_viewer.py --mode week --count 8 --output summary  # summary table
python trends_viewer.py --mode month --count 6 --group "Linux servers"  # by host group
```

### trouble_manager.py

Manage problems and maintenance windows.

```bash
# Problems
python trouble_manager.py --problem ack --event-id 1234               # acknowledge
python trouble_manager.py --problem close --event-id 1234             # close problem
python trouble_manager.py --problem suppress --host web01             # suppress by host
python trouble_manager.py --problem severity --event-id 1234 --severity high  # change severity

# Maintenance
python trouble_manager.py --maintenance create --name "Deploy" --host web01 web02 --duration 60
python trouble_manager.py --maintenance list
python trouble_manager.py --maintenance delete --maintenance-id 12
```

**Environment variables:**
```
ZABBIX_URL=https://zabbix.example.com/api_jsonrpc.php
ZABBIX_TOKEN=your_token_here
```

## Uptime Kuma Tools

### viewer.py

View monitor status and heartbeat history in Uptime Kuma.

```bash
python viewer.py --problems                                  # current DOWN monitors
python viewer.py --problems --duty-shift                     # monitors with DOWN in last 12h
python viewer.py --problems --duty-day                       # monitors with DOWN in last 24h
python viewer.py --history --id 5 --duty-shift               # history for monitor #5
python viewer.py --history --name "API" --duty-day           # history by monitor name
```

**Environment variables:**
```
UPTIMEKUMA_URL=http://uptimekuma.example.com:3001
UPTIMEKUMA_USERNAME=admin
UPTIMEKUMA_PASSWORD=your_password_here
```

## PBS API Tools

### viewer.py

View Proxmox Backup Server status, datastores and backup groups.

```bash
python viewer.py --datastore list                        # list all datastores
python viewer.py --datastore info --name storage1        # datastore details with backup groups
python viewer.py --server                                # server status (CPU, RAM, uptime)
```

**Environment variables:**
```
PBS_URL=https://pbs.example.com:8007
PBS_TOKEN_ID=user@realm!tokenname
PBS_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Domain Tools

Domain expiry checking.

### expiry_checker.py

Universal checker via RDAP (with WHOIS fallback). No API keys required.

```bash
python expiry_checker.py domains.txt                         # check domain list
python expiry_checker.py domains.txt --warn 60               # warn if expiring within 60 days
python expiry_checker.py domains.txt --delay 2               # delay between requests
```

### godaddy_checker.py

Check domains via GoDaddy API. Additionally detects parking status and auto-renewal.

```bash
python godaddy_checker.py godaddy_domains.txt                # check from file
python godaddy_checker.py godaddy_domains.txt --warn 60      # warning threshold
python godaddy_checker.py example.com example.org            # check specific domains
```

**Environment variables:**
```
GODADDY_API_KEY=your_key
GODADDY_API_SECRET=your_secret
```

## Installation

Each tool has its own `requirements.txt`. Install dependencies:

```bash
pip install -r sentry_api_tools/requirements.txt
pip install -r zabbix_api_tools/requirements.txt
pip install -r uptimekuma_tools/requirements.txt
pip install -r pbs_api_tools/requirements.txt
pip install -r domain_tools/requirements.txt
```

Each directory contains an `.env.example` template. Copy it to `.env` and fill in your values:

```bash
cp sentry_api_tools/.env.example sentry_api_tools/.env
cp zabbix_api_tools/.env.example zabbix_api_tools/.env
cp uptimekuma_tools/.env.example uptimekuma_tools/.env
cp pbs_api_tools/.env.example pbs_api_tools/.env
cp domain_tools/.env.example domain_tools/.env
```

`.env` files are listed in `.gitignore` and will not be overwritten on `git pull`.

## License

Apache License 2.0
