#!/usr/bin/env bash
# DEPRECATED: sync.py now reads each target's password from your OS keychain itself
# (service "time-assistant:<target name>", see docs/configuration.md), so this wrapper
# is no longer needed. It still works for one more release and then goes away.
#
# Usage:  python3 sync.py validate|check-config|discover|plan|apply [--week FILE]
set -euo pipefail
cd "$(dirname "$0")"
echo "tk.sh is deprecated and will be removed; run: python3 sync.py $*" >&2
exec python3 sync.py "$@"
