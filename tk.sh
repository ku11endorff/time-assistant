#!/usr/bin/env bash
# Runs sync.py with the TimeKeeper credentials taken from your OS keychain, so the
# password never sits in a file, in shell history or in front of an AI agent.
#
# One-time setup, macOS (prompts for the password):
#   security add-generic-password -s time-assistant -a 'YOUR-TIMEKEEPER-USERNAME' -U -w
# One-time setup, Linux (needs libsecret-tools):
#   secret-tool store --label=time-assistant service time-assistant account 'YOUR-TIMEKEEPER-USERNAME'
# Anything else (Windows, CI): set TK_USER and TK_PASSWORD yourself and run
#   python3 sync.py ... directly, or run this script and type the password when asked.
#
# The username (not a secret) comes from $TK_USER, else from the file .tk_user,
# else it is asked once and saved to .tk_user.
#
# Usage:  ./tk.sh validate|discover|plan|apply [--week FILE]
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${TK_USER:-}" ] && [ -s .tk_user ]; then
  TK_USER="$(tr -d '[:space:]' < .tk_user)"
fi
if [ -z "${TK_USER:-}" ]; then
  read -r -p "TimeKeeper username (saved in .tk_user, it is not a secret): " TK_USER
  printf '%s\n' "$TK_USER" > .tk_user
fi

if [ -z "${TK_PASSWORD:-}" ]; then
  if command -v security >/dev/null 2>&1; then
    TK_PASSWORD="$(security find-generic-password -s time-assistant -a "$TK_USER" -w)"
  elif command -v secret-tool >/dev/null 2>&1; then
    TK_PASSWORD="$(secret-tool lookup service time-assistant account "$TK_USER")"
  else
    read -r -s -p "TimeKeeper password for $TK_USER (not stored): " TK_PASSWORD
    echo
  fi
fi

export TK_USER TK_PASSWORD
exec python3 sync.py "$@"
