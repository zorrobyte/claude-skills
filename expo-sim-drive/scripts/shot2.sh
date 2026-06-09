#!/bin/zsh
# usage: shot2.sh <name> <state.json|--keep|--wipe> <deeplink|""> <swipes>
# Like shot.sh but swipes up <swipes> times before the screenshot.
set -e
UDID=ECB3D35F-42FD-4D1A-A0F7-8AC9ACC21472
APP=com.lastcan.app
IDB="/usr/bin/python3 /Users/rossfisher/Library/Python/3.9/bin/idb"
NAME=$1
STATE=$2
LINK=$3
SWIPES=${4:-1}

xcrun simctl terminate $UDID $APP 2>/dev/null || true
sleep 1
if [ "$STATE" = "--wipe" ]; then
  /usr/bin/python3 /tmp/lastcan-tools/inject.py --wipe
elif [ -n "$STATE" ] && [ "$STATE" != "--keep" ]; then
  /usr/bin/python3 /tmp/lastcan-tools/inject.py "$STATE"
fi
xcrun simctl launch $UDID $APP > /dev/null
sleep 5
if [ -n "$LINK" ]; then
  xcrun simctl openurl $UDID "$LINK" &
  sleep 3.5
  if ${=IDB} ui describe-all --udid $UDID 2>/dev/null | grep -q "Open in"; then
    ${=IDB} ui tap --udid $UDID 280 475
  fi
  sleep 2.5
fi
for i in $(seq 1 $SWIPES); do
  ${=IDB} ui swipe --udid $UDID --duration 0.4 201 700 201 220
  sleep 1.5
done
mkdir -p /tmp/lastcan-shots
xcrun simctl io $UDID screenshot /tmp/lastcan-shots/$NAME.png > /dev/null 2>&1
echo "shot: $NAME"
