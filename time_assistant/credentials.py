"""Secrets for targets (passwords, tokens). They never live in config.json.

Looked up per target and field, in this order:
  1. environment variable TA_<TARGET>_<FIELD>, e.g. TA_CLIENT_PASSWORD
  2. macOS keychain       service "time-assistant:<target>", account "<field>"
  3. Linux secret service  (secret-tool) with the same service and account
  4. a hidden prompt, when running in a terminal

So the secret is read on your own machine and never shown to an AI agent.

Cloud sessions: with TIME_ASSISTANT_AUTH=proxy no secret is looked up at all. The login is
added to requests by the cloud environment's network secret, outside the session, so
neither the agent nor this script ever holds it (docs/cloud-sessions.md).
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys

SERVICE = "time-assistant"


def proxy_mode() -> bool:
    """True in a cloud session whose network secret supplies the target login."""
    return os.environ.get("TIME_ASSISTANT_AUTH", "").strip().lower() == "proxy"


def service(target_name: str) -> str:
    return f"{SERVICE}:{target_name}"


def env_name(target_name: str, field: str) -> str:
    return "TA_" + re.sub(r"[^A-Z0-9]", "_", f"{target_name}_{field}".upper())


def setup_hint(target_name: str, field: str) -> str:
    s = service(target_name)
    return (f"Store the {field} for target '{target_name}' once (it is asked for, not typed in the command):\n"
            f"  macOS:   security add-generic-password -s {s} -a {field} -U -w\n"
            f"  Linux:   secret-tool store --label={s} service {s} account {field}\n"
            f"  Other:   set the environment variable {env_name(target_name, field)}")


def _run(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.rstrip("\n") if r.returncode == 0 and r.stdout.strip() else None


def lookup(target_name: str, field: str, interactive: bool | None = None) -> str:
    value = os.environ.get(env_name(target_name, field))
    if value:
        return value
    s = service(target_name)
    if shutil.which("security"):
        value = _run(["security", "find-generic-password", "-s", s, "-a", field, "-w"])
    elif shutil.which("secret-tool"):
        value = _run(["secret-tool", "lookup", "service", s, "account", field])
    if value:
        return value
    if interactive is None:
        interactive = sys.stdin.isatty()
    if interactive:
        value = getpass.getpass(f"{field} for target '{target_name}' (not stored): ")
        if value:
            return value
    raise SystemExit(f"No {field} found for target '{target_name}'.\n{setup_hint(target_name, field)}")


def get_secrets(target_name: str, fields) -> dict:
    if proxy_mode():
        return {}
    return {f: lookup(target_name, f) for f in fields}
