# CLAUDE.md

## Project overview

CLI monitoring tools — a collection of Python 3 scripts for querying monitoring systems via their APIs. Each tool suite lives in its own directory with a shared `client.py` module and one or more viewer/manager scripts.

## Repository structure

```
sentry_api_tools/    — Sentry (viewer.py, manager.py, client.py)
zabbix_api_tools/    — Zabbix (problems_viewer.py, trends_viewer.py, trouble_manager.py, client.py)
uptimekuma_tools/    — Uptime Kuma (viewer.py, no client.py — uses uptime-kuma-api library)
pbs_api_tools/       — Proxmox Backup Server (viewer.py, client.py)
domain_tools/        — Domain expiry (expiry_checker.py, godaddy_checker.py, no client.py)
```

## Code conventions

- No type annotations (removed intentionally for consistency)
- No docstrings on functions (except godaddy_checker module docstring for API key instructions)
- All scripts have `#!/usr/bin/env python3` shebang
- client.py modules have `if __name__ == "__main__"` guard against direct execution
- Exit with `sys.exit(1)`, not `raise SystemExit(1)`
- Output uses `print()`, not `logging` module
- Separator width is 70 chars: `'='*70` for sections, `'-'*70` for subsections
- f-strings everywhere, no `.format()` or `%`

## Architecture pattern

### Scripts with client.py (sentry, zabbix, pbs)

```
client.py:  init(env_file=None), make_session() or class, api call function
viewer.py:  import client; client.init(args.env); session = make_session()
```

- `client.init()` loads .env and validates credentials
- Credentials are module-level globals set by `init()`
- Session created after arg parsing, closed in `finally` block

### Scripts without client.py (uptimekuma, godaddy)

- `init(env_file)` or `load_dotenv(args.env)` called in `main()` after arg parsing
- Credentials read from `os.environ` after loading

## HTTP client pattern

All HTTP clients use:
- `requests.Session()` with retry: `Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])`
- Timeout: 15 seconds (domain tools: 10 seconds)
- Exception handling: `ConnectionError`, `Timeout`, `HTTPError`, `ValueError` (for JSON)
- Session closed in `finally` block

PBS client additionally: `session.verify = False` and `urllib3.disable_warnings(InsecureRequestWarning)`

## Adding a new tool

1. Create directory `newtool_api_tools/`
2. Create `client.py` with `init(env_file)`, `make_session()`, API call function
3. Create `viewer.py` with argparse, `--env` parameter, `client.init(args.env)` before session
4. Create `.env.example` with empty values
5. Create `requirements.txt` with pinned versions
6. Update both `README.md` and `README.ru.md` (structure, tool section, installation, env setup)
7. Update `AI_AGENT_GUIDE.md` with intent-to-command mapping

## Testing changes

No test suite exists. Verify by:
1. `python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"` — syntax check
2. `python3 script.py --help` — verify argparse (requires env vars set or use `--env`)
3. Run against real API to verify output format

## Files not to touch

- `.env` files — contain user credentials, gitignored
- `domains.txt`, `godaddy_domains.txt` — user domain lists, gitignored
- `LICENSE` — Apache 2.0, do not modify

## Do not add

- Docker/containerization — explicitly not wanted
- Logging module — print() is intentional for CLI tools
- Type annotations — removed for consistency, will be added project-wide with mypy if ever
- Tests/CI — not currently in scope
