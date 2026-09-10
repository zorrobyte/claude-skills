#!/usr/bin/env python3
"""uiscan — walk the app on a throwaway simulator and hand back contact sheets.

One command does the whole loop: build, install onto an isolated simulator,
grant permissions, drive the UI through named routes, export every screenshot,
and tile them into a handful of labelled contact sheets.

The contact sheets are the point. Reviewing 40 screenshots one file at a time is
the expensive part of a visual pass; 40 tiles across 4 sheets is four looks.

    python3 Scripts/uiscan/uiscan.py                  # full sweep, fresh install
    python3 Scripts/uiscan/uiscan.py --only testSupportTools
    python3 Scripts/uiscan/uiscan.py --keep-state --no-build   # re-shoot, fast
    python3 Scripts/uiscan/uiscan.py --list           # what routes exist

Nothing here touches the developer's own simulators: uiscan creates and owns a
device called "UIScan" and erases only that one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEVICE_NAME = "UIScan"
TEST_TARGET = "UIScanTests"
TEST_CLASS = "ScreenWalk"

# Per-project settings. Override with flags, or drop a uiscan.json next to the
# skill or at the repo root: {"scheme": "...", "bundle_id": "...", "root": "..."}
DEFAULTS = {"scheme": "ExposurePal", "bundle_id": "com.zorrobyte.ExposurePal", "root": None}


def config() -> dict:
    merged = dict(DEFAULTS)
    for candidate in (HERE / "uiscan.json", Path.cwd() / "uiscan.json"):
        if candidate.exists():
            merged.update(json.loads(candidate.read_text()))
    return merged


CFG = config()
ROOT = Path(CFG["root"]).resolve() if CFG.get("root") else Path.cwd()
BUNDLE_ID = CFG["bundle_id"]
SCHEME = CFG["scheme"]

# Simulator location: San Francisco. Mission generation needs a fix with real
# MapKit results around it, so a plausible city centre matters.
DEFAULT_LOCATION = "37.7749,-122.4194"

# Services the walk needs granted up front; a permission alert mid-route
# swallows taps and produces a sheet full of identical screenshots.
PRIVACY_SERVICES = ["location-always", "photos", "photos-add", "camera"]


def run(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"uiscan: {msg}", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------
# Simulator


def simctl_json(*args) -> dict:
    out = run(["xcrun", "simctl", "list", "-j", *args]).stdout
    return json.loads(out)


def newest_runtime() -> str:
    runtimes = [
        r for r in simctl_json("runtimes")["runtimes"]
        if r.get("isAvailable") and r["identifier"].startswith("com.apple.CoreSimulator.SimRuntime.iOS")
    ]
    if not runtimes:
        die("no iOS simulator runtimes are installed")
    runtimes.sort(key=lambda r: [int(p) for p in r["version"].split(".")])
    return runtimes[-1]["identifier"]


def find_device(name: str) -> str | None:
    for devices in simctl_json("devices")["devices"].values():
        for d in devices:
            if d["name"] == name and d.get("isAvailable"):
                return d["udid"]
    return None


def device_type_for(runtime: str) -> str:
    """Newest iPhone Pro the runtime supports, so screenshots match current hardware."""
    pairs = simctl_json("devicetypes")["devicetypes"]
    pro = [d for d in pairs if re.match(r"^iPhone \d+ Pro$", d["name"])]
    if not pro:
        pro = [d for d in pairs if d["name"].startswith("iPhone")]
    if not pro:
        die("no iPhone device types available")
    pro.sort(key=lambda d: int(re.search(r"\d+", d["name"]).group()))
    return pro[-1]["identifier"]


def ensure_device(fresh: bool) -> str:
    udid = find_device(DEVICE_NAME)
    if udid and fresh:
        run(["xcrun", "simctl", "shutdown", udid])
        run(["xcrun", "simctl", "erase", udid])
    if not udid:
        runtime = newest_runtime()
        result = run(["xcrun", "simctl", "create", DEVICE_NAME, device_type_for(runtime), runtime])
        if result.returncode != 0:
            die(f"could not create the {DEVICE_NAME} simulator: {result.stderr.strip()}")
        udid = result.stdout.strip()
    run(["xcrun", "simctl", "boot", udid])
    run(["xcrun", "simctl", "bootstatus", udid, "-b"])
    return udid


def prepare_device(udid: str, location: str):
    for service in PRIVACY_SERVICES:
        run(["xcrun", "simctl", "privacy", udid, "grant", service, BUNDLE_ID])
    run(["xcrun", "simctl", "location", udid, "set", location])
    # A fixed clock keeps sheets comparable between runs.
    run(["xcrun", "simctl", "status_bar", udid, "override",
         "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100",
         "--cellularMode", "active", "--cellularBars", "4", "--dataNetwork", "wifi",
         "--wifiMode", "active", "--wifiBars", "3"])


# --------------------------------------------------------------------------
# Build & install


def build_and_install(udid: str) -> Path:
    derived = ROOT / "build/DerivedData"
    cmd = ["xcodebuild", "-scheme", SCHEME, "-destination", f"platform=iOS Simulator,id={udid}",
           "-derivedDataPath", str(derived), "build"]
    print("uiscan: building…", flush=True)
    result = run(cmd, cwd=ROOT)
    if result.returncode != 0:
        tail = "\n".join(
            line for line in result.stdout.splitlines() if "error:" in line
        ) or result.stdout[-2000:]
        die(f"build failed:\n{tail}")
    app = next(derived.glob("Build/Products/Debug-iphonesimulator/*.app"), None)
    if app is None:
        die("build succeeded but no .app was produced")
    run(["xcrun", "simctl", "install", udid, str(app)])
    return app


# --------------------------------------------------------------------------
# Routes


def route_names() -> list[str]:
    source = (HERE / "CaptureUITests" / f"{TEST_CLASS}.swift").read_text()
    return re.findall(r"func (test\w+)\(", source)


# --------------------------------------------------------------------------
# Walk


def walk(udid: str, only: list[str], out: Path) -> int:
    work = Path(tempfile.mkdtemp(prefix="uiscan-"))
    shutil.copy2(HERE / "project.yml", work / "project.yml")
    shutil.copytree(HERE / "CaptureUITests", work / "CaptureUITests")
    generated = run(["xcodegen", "generate"], cwd=work)
    if generated.returncode != 0:
        die(f"xcodegen failed: {generated.stderr.strip()}")

    result_bundle = out / "walk.xcresult"
    cmd = ["xcodebuild", "test", "-project", str(work / "UIScan.xcodeproj"),
           "-scheme", TEST_TARGET, "-destination", f"platform=iOS Simulator,id={udid}",
           "-parallel-testing-enabled", "NO", "-collect-test-diagnostics", "never",
           "-resultBundlePath", str(result_bundle)]
    for name in (only or route_names()):
        cmd += [f"-only-testing:{TEST_TARGET}/{TEST_CLASS}/{name}"]

    log = out / "xcodebuild.log"
    print(f"uiscan: walking {len(only or route_names())} routes… ({log})", flush=True)
    with log.open("w") as handle:
        status = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT).returncode
    return status


def export_shots(out: Path) -> list[Path]:
    """Pull PNG attachments out of the result bundle, named as the route named them."""
    result_bundle = out / "walk.xcresult"
    if not result_bundle.exists():
        return []
    attachments = out / "attachments"
    if run(["xcrun", "xcresulttool", "export", "attachments",
            "--path", str(result_bundle), "--output-path", str(attachments)]).returncode != 0:
        return []

    manifest = json.loads((attachments / "manifest.json").read_text())
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for test in manifest:
        for item in test.get("attachments", []):
            name = item.get("suggestedHumanReadableName", "")
            source = attachments / item["exportedFileName"]
            # Routes name their captures "12-explore-discover"; anything else is
            # XCTest's own failure diagnostics, which we do not want on a sheet.
            if source.suffix.lower() != ".png" or not re.match(r"\d+[a-z]?-", name):
                continue
            stem = re.sub(r"_\d+_[0-9A-Fa-f-]+\.png$", "", name)
            stem = re.sub(r"[^a-zA-Z0-9_-]", "-", stem)
            destination = shots / f"{stem}.png"
            n = 2
            while destination.exists():
                destination = shots / f"{stem}-{n}.png"
                n += 1
            shutil.copy2(source, destination)
            written.append(destination)
    return sorted(written)


def contact_sheets(shots: list[Path], out: Path, cols: int, rows: int) -> list[str]:
    if not shots:
        return []
    sheets = out / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    result = run(["swift", str(HERE / "contactsheet.swift"), "--out", str(sheets),
                  "--cols", str(cols), "--rows", str(rows), *[str(p) for p in shots]])
    if result.returncode != 0:
        die(f"contact sheet failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


# --------------------------------------------------------------------------


def main() -> int:
    global SCHEME, BUNDLE_ID
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", default=[], help="route to run (repeatable)")
    parser.add_argument("--list", action="store_true", help="list available routes and exit")
    parser.add_argument("--out", type=Path, help="output directory (default: a temp dir)")
    parser.add_argument("--no-build", action="store_true", help="reuse the installed app")
    parser.add_argument("--keep-state", action="store_true", help="do not erase the simulator first")
    parser.add_argument("--location", default=DEFAULT_LOCATION, help="lat,lon for the simulated fix")
    parser.add_argument("--scheme", help="Xcode scheme (default from uiscan.json)")
    parser.add_argument("--bundle-id", help="app bundle identifier (default from uiscan.json)")
    parser.add_argument("--cols", type=int, default=5)
    parser.add_argument("--rows", type=int, default=2)
    args = parser.parse_args()

    if args.scheme:
        SCHEME = args.scheme
    if args.bundle_id:
        BUNDLE_ID = args.bundle_id

    if args.list:
        for name in route_names():
            print(name)
        return 0

    for tool in ("xcodegen", "xcodebuild", "xcrun", "swift"):
        if not shutil.which(tool):
            die(f"required tool not found: {tool}")

    out = args.out or Path(tempfile.mkdtemp(prefix="uiscan-run-"))
    out.mkdir(parents=True, exist_ok=True)

    udid = ensure_device(fresh=not args.keep_state)
    if not args.no_build:
        build_and_install(udid)
    prepare_device(udid, args.location)

    status = walk(udid, args.only, out)
    shots = export_shots(out)
    sheets = contact_sheets(shots, out, args.cols, args.rows)

    print()
    print(f"uiscan: {len(shots)} screens captured, {len(sheets)} contact sheet(s)")
    for sheet in sheets:
        print(f"  {sheet}")
    print(f"  screenshots: {out / 'screenshots'}")
    if status != 0:
        print(f"  NOTE: some routes failed — see {out / 'xcodebuild.log'}", file=sys.stderr)
    return 0 if shots else status


if __name__ == "__main__":
    raise SystemExit(main())
