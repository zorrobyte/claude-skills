#!/usr/bin/env python3
"""Inject a LastCan app state into the simulator's AsyncStorage manifest.

Usage: inject.py <state.json>   (or --wipe to clear all storage)
The app must be terminated first; the caller handles relaunching.
"""
import json
import os
import shutil
import subprocess
import sys

container = subprocess.check_output(
    ["xcrun", "simctl", "get_app_container",
     "ECB3D35F-42FD-4D1A-A0F7-8AC9ACC21472", "com.lastcan.app", "data"],
    text=True,
).strip()
MANIFEST = os.path.join(
    container, "Library/Application Support/com.lastcan.app/RCTAsyncLocalStorage_V1/manifest.json"
)

storage_dir = os.path.dirname(MANIFEST)

if sys.argv[1] == "--wipe":
    shutil.rmtree(storage_dir, ignore_errors=True)
    os.makedirs(storage_dir, exist_ok=True)
    sys.exit(0)

with open(sys.argv[1]) as f:
    state = json.load(f)  # validate it parses

manifest = {}
if os.path.exists(MANIFEST):
    try:
        with open(MANIFEST) as f:
            manifest = json.load(f)
    except Exception:
        manifest = {}

manifest["lastcan:v2"] = json.dumps(state)
with open(MANIFEST, "w") as f:
    json.dump(manifest, f)
print("injected", sys.argv[1])
