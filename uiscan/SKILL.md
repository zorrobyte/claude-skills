---
name: uiscan
description: Screenshot every screen of the ExposurePal iOS app and return labelled contact sheets. Use whenever the task needs to SEE the app — visual review, UI critique, "what does this screen look like", checking a layout change, auditing flows or empty states, or before/after comparison of a UI edit. Do not screenshot the simulator by hand; run this instead.
---

# uiscan — see the whole app in a few images

`uiscan` builds the app, installs it on a simulator it owns, walks every flow, and
tiles the screenshots into a handful of labelled contact sheets.

**Read the contact sheets, not the individual screenshots.** A 40-screen sweep is
4 sheet images. Reading 40 PNGs one at a time costs roughly ten times as much and
tells you the same thing. Only open an individual screenshot when a tile shows
something you cannot resolve at tile size.

## Run it

```sh
python3 Scripts/uiscan/uiscan.py                      # full sweep, fresh simulator
python3 Scripts/uiscan/uiscan.py --only test08Support # one flow
python3 Scripts/uiscan/uiscan.py --no-build --keep-state   # re-shoot fast
python3 Scripts/uiscan/uiscan.py --list               # available routes
```

It prints the sheet paths at the end:

```
uiscan: 46 screens captured, 5 contact sheet(s)
  …/sheets/sheet-01.png
  …/screenshots            <- individual PNGs, if you need one
```

Then `Read` each `sheet-*.png`.

Useful flags: `--out DIR` (default: a temp dir), `--location lat,lon` (default San
Francisco — mission generation needs real MapKit results nearby), `--cols/--rows`
(tiles per sheet, default 5×2).

A full sweep takes several minutes. Run it in the background and do other work
while it goes.

## What it does not touch

`uiscan` creates and owns a simulator called **UIScan** and erases only that one.
It never resets the developer's own simulators or their app data.

## Routes

One route per flow, in `Scripts/uiscan/CaptureUITests/ScreenWalk.swift`. Order is
significant: `test01Onboarding` needs a device with no user yet, and
`test02EmptyStates` needs one that has not been seeded, so both run before the
seeding routes. Everything after them launches with `-uiscan-onboarded
-uiscan-seed`, which is handled by `UITestBootstrap` (DEBUG-only) in the app.

## Adding or fixing a route

Routes are best-effort by design: `tap()` returns `false` instead of failing, so a
renamed button costs one blank tile rather than the rest of the sheet. Keep it
that way — a route that throws produces a half-empty sheet and hides everything
downstream of the break.

Prefer accessibility identifiers over labels. If a screen has none, add one to the
app; that is a better fix than a normalised coordinate.

After changing the app's UI, re-run and check the sheets: a tile showing the wrong
screen means a selector drifted.
