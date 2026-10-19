"""Run a local synthetic integration command without putting credentials in argv/logs.

Requires an existing private.env from provision-trial-secrets.py. Only loopback
published ports of the isolated compose.trial.yaml stack are used.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import quote


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-env", type=Path, required=True)
    parser.add_argument("--database", help="Optional isolated backend_live database name")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    values = dict(line.split("=", 1) for line in args.private_env.read_text().splitlines() if line)
    database = args.database or values["POSTGRES_DB"]
    if "backend_live" not in database or any(char in database for char in "/?@:"):
        raise ValueError("only isolated backend_live fixture databases are permitted")
    env = os.environ.copy()
    env.update(values)
    env["POSTGRES_DB"] = database
    database_url = "postgresql+asyncpg://" + quote(values["POSTGRES_USER"], safe="") + ":" + quote(
        values["POSTGRES_PASSWORD"], safe=""
    ) + "@127.0.0.1:" + env.get("TRIAL_POSTGRES_PORT", "55432") + "/" + database
    env.update({
        "DATABASE_URL": database_url, "BACKEND_LIVE_DATABASE_URL": database_url,
        "BACKEND_LIVE_REDIS_URL": "redis://:" + quote(values["REDIS_PASSWORD"], safe="") +
        "@127.0.0.1:" + env.get("TRIAL_REDIS_PORT", "56379") + "/0",
        "REDIS_HOST": "127.0.0.1", "REDIS_PORT": env.get("TRIAL_REDIS_PORT", "56379"),
        "NEO4J_URI": "bolt://127.0.0.1:" + env.get("TRIAL_NEO4J_PORT", "57687"),
        "NEO4J_USER": "neo4j", "ENVIRONMENT": "test", "QA_LIVE_INFRA": "1",
        "BACKEND_LIVE_API_WORKERS": "2",
    })
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("a command is required")
    raise SystemExit(subprocess.call(command, env=env))


if __name__ == "__main__":
    main()
