#!/bin/zsh
# usage: shot.sh <name> [state.json|--wipe|--keep] [deeplink] [settle-seconds]
# Terminates the app, optionally injects state, relaunches, optionally deep-links,
# screenshots to /tmp/lastcan-shots/<name>.png
set -e
UDID=ECB3D35F-42FD-4D1A-A0F7-8AC9ACC21472
APP=com.lastcan.app
NAME=$1
STATE=$2
LINK=$3
SETTLE=${4:-5}

xcrun simctl terminate $UDID $APP 2>/dev/null || true
sleep 1
if [ -n "$STATE" ] && [ "$STATE" != "--keep" ]; then
  /usr/bin/python3 /tmp/lastcan-tools/inject.py "$STATE"
fi
xcrun simctl launch $UDID $APP > /dev/null
sleep $SETTLE
if [ -n "$LINK" ]; then
  xcrun simctl openurl $UDID "$LINK" &
  sleep 3.5
  # Confirm the system "Open in Last Can?" dialog only if it is actually shown
  # (iOS stops prompting after enough approvals; a blind tap would hit app UI).
  IDB="/usr/bin/python3 /Users/rossfisher/Library/Python/3.9/bin/idb"
  if ${=IDB} ui describe-all --udid $UDID 2>/dev/null | grep -q "Open in"; then
    ${=IDB} ui tap --udid $UDID 280 475
  fi
  sleep 2.5
fi
mkdir -p /tmp/lastcan-shots
xcrun simctl io $UDID screenshot /tmp/lastcan-shots/$NAME.png > /dev/null 2>&1
echo "shot: $NAME"
