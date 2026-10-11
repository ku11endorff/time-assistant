#!/bin/bash
# macOS double-click launcher: dry run, ask for confirmation, then post the newest
# week-*.json in this folder to TimeKeeper and verify the result.
# (On Linux/Windows run the same steps by hand: ./tk.sh plan --week FILE, then apply.)
cd "$(dirname "$0")" || exit 1

pause() { echo; read -r -p "Press Enter to close this window..." _; }

latest="$(ls -t week-*.json 2>/dev/null | head -1)"
if [ -z "$latest" ]; then
  echo "No week-*.json file found in $(pwd)."
  echo "Ask your AI agent to export the week first (docs/agent-playbook.md), then run this again."
  pause; exit 1
fi

# Ask for the username once here, so the password lookup below never waits on a hidden prompt.
if [ -z "${TK_USER:-}" ] && [ ! -s .tk_user ]; then
  read -r -p "TimeKeeper username: " u
  printf '%s\n' "$u" > .tk_user
fi

echo "Week file: $latest"
echo "-------------------------------------------"
plan_out="$(./tk.sh plan --week "$latest" 2>&1)"
plan_status=$?
echo "$plan_out"
echo "-------------------------------------------"

if [ $plan_status -ne 0 ]; then
  echo "The dry run failed - nothing was written to TimeKeeper."
  pause; exit 1
fi
if echo "$plan_out" | grep -q '^  ERROR'; then
  echo "The plan contains ERROR lines - nothing was written. Fix them first."
  pause; exit 1
fi
if echo "$plan_out" | grep -q ': 0 create, 0 update, 0 delete, 0 receipts'; then
  echo "Nothing to post - TimeKeeper is already up to date for this week."
  pause; exit 0
fi

read -r -p "Post this to TimeKeeper? Type y to confirm, anything else cancels: " answer
if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
  echo "Cancelled - nothing was written."
  pause; exit 0
fi

if ./tk.sh apply --week "$latest"; then
  echo
  echo "Verifying (everything should now show as unchanged):"
  ./tk.sh plan --week "$latest"
else
  echo
  echo "Posting failed - see the message above. Nothing more was done."
fi
pause
