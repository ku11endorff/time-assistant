#!/bin/bash
# macOS double-click launcher: dry run for every enabled target, ask for confirmation,
# then write the newest week-*.json in this folder and verify the result.
# (On Linux/Windows run the same steps by hand: python3 sync.py plan --week FILE, then apply.)
cd "$(dirname "$0")" || exit 1

pause() { echo; read -r -p "Press Enter to close this window..." _; }

latest="$(ls -t week-*.json 2>/dev/null | head -1)"
if [ -z "$latest" ]; then
  echo "No week-*.json file found in $(pwd)."
  echo "Ask your AI agent to export the week first (docs/agent-playbook.md), then run this again."
  pause; exit 1
fi

echo "Week file: $latest"
echo "-------------------------------------------"
plan_out="$(python3 sync.py plan --week "$latest" 2>&1)"
plan_status=$?
echo "$plan_out"
echo "-------------------------------------------"

if [ $plan_status -ne 0 ] || echo "$plan_out" | grep -q '^  ERROR'; then
  echo "The dry run reported errors - nothing was written. Fix them first."
  pause; exit 1
fi
if echo "$plan_out" | grep -q '^dry run - nothing written: 0 create, 0 update, 0 delete, 0 receipts'; then
  echo "Nothing to write - every target is already up to date for this week."
  pause; exit 0
fi

read -r -p "Write this to the targets above? Type y to confirm, anything else cancels: " answer
if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
  echo "Cancelled - nothing was written."
  pause; exit 0
fi

if python3 sync.py apply --week "$latest"; then
  echo
  echo "Verifying (everything should now show as unchanged):"
  python3 sync.py plan --week "$latest"
else
  echo
  echo "Writing did not fully succeed - see the message above. Re-running the same week is safe."
fi
pause
