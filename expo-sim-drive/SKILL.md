---
name: expo-sim-drive
description: Drive an Expo/React Native iOS app headlessly in the simulator - build, install, inject AsyncStorage state fixtures, deep-link to any screen, tap via idb, and screenshot every screen and state without a human or the Simulator UI. Use when asked to inspect, verify, screenshot, or QA RN/Expo app screens in the iOS simulator, including onboarding mid-steps, paywalls, pro/free tiers, dark mode, and large dynamic type.
---

# Headless Expo/RN iOS simulator driving

Written by an agent, for agents. Every command here was verified end-to-end on
2026-06-09 (Darwin 27, Xcode 27 beta, Expo SDK 56, RN with Hermes, iPhone 17 Pro
sim, iOS 26.2). The core insight: **you do not need the Simulator UI, Metro, or
a human finger. CoreSimulator renders headlessly; AsyncStorage is a plaintext
JSON manifest you can write; deep links + a conditional idb tap reach every
route; `simctl io screenshot` captures it all.**

## 0. Toolchain sanity (new/beta Xcode)

- `xcrun simctl` failing with "unable to find utility": `xcode-select -p` points
  at CommandLineTools → user must `sudo xcode-select -s /Applications/Xcode*.app/Contents/Developer
  && sudo xcodebuild -license accept`. Verify acceptance took: `defaults read
  /Library/Preferences/com.apple.dt.Xcode` must be non-empty; an empty result
  means the accept silently failed, ask the user to rerun.
- Newer Xcode betas removed `Simulator.app` (DeviceHub replaces it) and moved
  `SimulatorKit.framework` to `Xcode.app/Contents/SharedFrameworks/`. Nothing
  below needs the Simulator UI. `expo run:ios` DOES need it and dies with
  "Can't determine id of Simulator app" - don't use it; use raw `xcodebuild`
  (section 2).
- Boot headless: `xcrun simctl list devices available`, then
  `xcrun simctl boot <UDID>`. Screenshots work with no window.

## 1. Prebuild + pods (Expo managed apps, `ios/` gitignored)

```bash
npx expo prebuild -p ios   # or let a failed `expo run:ios` do it; prebuild+pods still complete
cd ios && pod install
```

Beta-toolchain compile fixes, ALL in gitignored paths (ios/, node_modules/), so
they are safe scratch patches - but tell the user they exist and that the real
fix is dependency updates or a stable Xcode:

- "deployment target ... 13.4 but range is 15.0+": append to Podfile
  post_install and re-run `pod install`:
  ```ruby
  installer.pods_project.targets.each do |t|
    t.build_configurations.each do |c|
      v = c.build_settings['IPHONEOS_DEPLOYMENT_TARGET']
      c.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.1' if v && v.to_f < 15.1
    end
  end
  ```
  Do NOT pass IPHONEOS_DEPLOYMENT_TARGET=15.1 globally on the xcodebuild CLI -
  it drags down pods that legitimately need 16+ (`@expo/ui`) and they break.
- RevenueCat pod "invalid redeclaration of synthesized memberwise
  init(stringRepresentation:)" (RevenueCat 5.74 vs new Swift): in
  `ios/Pods/RevenueCat/Sources/Paywalls/PaywallColor.swift`, MOVE the private
  "designated" `init(stringRepresentation:underlyingColor:)` from the private
  extension into the struct body (declaring any init in the body suppresses the
  colliding synthesis; leaving both copies = redeclaration error).
- expo-modules-jsi "C function pointer can only be formed from a reference to a
  'func'": in `node_modules/expo-modules-jsi/.../JavaScriptRuntime.swift`,
  replace the `cond ? nil : funcRef` argument with an explicit if/else that
  passes the func reference directly in each branch.

## 2. Build Release, not Debug, for inspection

```bash
cd ios && xcodebuild -workspace <App>.xcworkspace -scheme <App> \
  -configuration Release -destination "id=$UDID" -derivedDataPath build build
xcrun simctl install $UDID build/Build/Products/Release-iphonesimulator/<App>.app
```

Why Release: embedded JS bundle (no Metro), no LogBox warning toasts polluting
screenshots, release-realistic performance. Grep xcodebuild output for
`error:|BUILD SUCCEEDED|BUILD FAILED`; run it in background, it takes minutes.

**RevenueCat kill-switch**: a `test_...` API key in a Release build raises a
blocking native alert "Wrong API Key ... The app will close now" and exits.
Expo bakes `extra` config into the BUILT app at
`<App>.app/EXConstants.bundle/app.config` (plain JSON). Patch the build
product, not the repo: load that JSON, set `extra.revenueCatKey = ""` (empty →
well-built apps fall back to a mock subscription service; mock offerings render
the paywall, mock purchases succeed, injected `isPro` is respected because no
real entitlement refresh overwrites it), reinstall with `simctl install`.
Generally: ANY `extra.*` runtime config can be rewritten post-build this way.

## 3. State injection - the core trick

react-native-async-storage on iOS stores everything in
`<data-container>/Library/Application Support/<bundle-id>/RCTAsyncLocalStorage_V1/manifest.json`.
Values ≤ ~1KB live INLINE in the manifest as a JSON-encoded string; larger ones
live in a sibling file named `md5 -qs "<key>"` with `null` in the manifest.
Writing the value inline ALWAYS works regardless of size (read path checks the
manifest first).

```python
import json, os, subprocess
container = subprocess.check_output(["xcrun","simctl","get_app_container",UDID,BUNDLE_ID,"data"],text=True).strip()
manifest = os.path.join(container,"Library/Application Support",BUNDLE_ID,"RCTAsyncLocalStorage_V1/manifest.json")
m = json.load(open(manifest)) if os.path.exists(manifest) else {}
m[STORAGE_KEY] = json.dumps(fixture_dict)   # value is a JSON STRING, not an object
json.dump(m, open(manifest,"w"))
```

Critical details:
- **Terminate the app first** (`simctl terminate`), inject, then `simctl launch`.
  RN apps flush state on backgrounding and would overwrite your injection.
- **Re-resolve the container path after every `simctl install`** - reinstalls
  can move the data container UUID. Never hardcode it.
- Read the app's reducer/persistence source first to learn the exact persisted
  shape + schema version; write fixtures that match (wrong shape = silent
  fallback to defaults or a migration throw).
- Wipe = delete the `RCTAsyncLocalStorage_V1` dir.
- If the app persists a step index (e.g. onboarding `stepIndex`), every
  mid-flow screen is reachable by fixture + relaunch - no tapping through.
- Fixture matrix that covers most apps: fresh install; each onboarding step;
  day-one empty; lived-in free tier (streaks, logs, content); pro/subscribed;
  error/celebration variants. Generate them with one python script.

## 4. Navigation: deep links + conditional tap

`xcrun simctl openurl $UDID "<scheme>://<route>"` (expo-router: URL path ==
route path; route groups like `(tabs)` are invisible in the URL).

SpringBoard shows an "Open in <App>?" confirmation dialog - SOMETIMES. iOS
stops asking after several approvals, so a blind tap will eventually hit your
app's UI and mutate state (it pressed a segmented control for us). Tap
CONDITIONALLY:

```bash
IDB="/usr/bin/python3 $HOME/Library/Python/3.9/bin/idb"   # see idb fixes below
xcrun simctl openurl $UDID "$LINK" & sleep 3.5
if $IDB ui describe-all --udid $UDID 2>/dev/null | grep -q "Open in"; then
  $IDB ui tap --udid $UDID 280 475      # Open button, points, iPhone 17 Pro (402x874pt)
fi
sleep 2.5
```

The dialog can take >2s to appear; tapping too early dismisses a STALE dialog
and leaves the new one up (classic off-by-one where every screenshot shows the
previous link's destination + a dialog). The describe-all guard fixes both.

idb fixes on beta Xcode:
- `idb` client shebang points at `/Applications/Xcode.app/...` python → invoke
  as `/usr/bin/python3 ~/Library/Python/3.9/bin/idb`.
- companion needs SimulatorKit at the old path:
  `mkdir -p /Applications/Xcode*.app/Contents/Developer/Library/PrivateFrameworks &&
  ln -sf /Applications/Xcode*.app/Contents/SharedFrameworks/SimulatorKit.framework
  /Applications/Xcode*.app/Contents/Developer/Library/PrivateFrameworks/SimulatorKit.framework`
- `simctl spawn $UDID uiopen <url>` does NOT exist in new runtimes; don't chase it.
- Below-the-fold content: `$IDB ui swipe --udid $UDID --duration 0.4 201 700 201 220`,
  repeat per screen-height, screenshot after each.

Note: deep links may bypass JS-side auth/onboarding gates that live only in the
index route - if you land somewhere you "shouldn't", that is a real app bug
worth reporting, and also your way in.

## 5. Capture matrix

```bash
xcrun simctl io $UDID screenshot out.png        # headless OK
xcrun simctl ui $UDID appearance dark|light     # dark-mode pass (top contrast-bug source)
xcrun simctl ui $UDID content_size extra-extra-extra-large   # dynamic type pass
xcrun simctl ui $UDID content_size large        # reset
```

Loop: terminate → inject fixture → launch → (deep link + conditional tap) →
(swipes) → screenshot. ~8s per screen. Then actually READ every screenshot -
look for: dark-on-dark text in branded/gradient cards, truncated steppers and
chips, past dates rendered in future-tense copy, year-less dates, blocked
dialogs, state that contradicts the fixture (means some service overwrote your
injection - hunt the listener).

## 6. Script templates

Keep three small files (e.g. in /tmp): `inject.py` (section 3, plus `--wipe`),
`shot.sh <name> <fixture|--keep|--wipe> [deeplink] [settle]` (the loop above),
`make-states.py` (fixture generator). Working copies that produced 45+ clean
screenshots live in this skill's `scripts/` directory - adapt UDID, bundle id,
storage key, and fixture shape per app.
