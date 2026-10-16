#!/usr/bin/env python3
"""Measure the pointer gain on the iOS Home Screen from the hover highlight (phone unlocked, mirroring running).
Moves along the first icon row/column and bisects where the highlight jumps to the next icon; the jump sits halfway
between two icon centres, which gives points per mouse count. Writes calib.json."""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from bridge import Bridge
from remote import Remote
from screenshot import grab
from pointer import diff_box, save_calib, PX_PER_PT

COLS = [110, 276, 443, 609]                     # icon centres, screenshot px (iPhone 13 Pro home screen)
ROWS = [545, 726, 905, 1085]                 # first home page: widgets on top, then 4 rows of icons
tmp = pathlib.Path(tempfile.mkdtemp())

def shot(name): return str(grab(str(tmp / name), bridge=BR))

def hover_at(b, cx, cy, base):  # cx, cy in mouse counts
    b.cmd("home"); time.sleep(0.4)
    b.cmd(f"move {cx} {cy}")
    time.sleep(1.0)
    return diff_box(base, shot("h.png"))

def bisect(b, base, axis, lo, hi, want_hi_index, cross):
    """Smallest count at which the highlight sits in the cell with index want_hi_index along `axis`."""
    centres = COLS if axis == "x" else ROWS
    for _ in range(6):
        mid = (lo + hi) // 2
        box = hover_at(b, mid if axis == "x" else cross, cross if axis == "x" else mid, base)
        if axis == "x": pos = None if not box else (box[0] + box[2]) / 2
        else: pos = None if not box else (box[1] + box[3]) / 2
        idx = None if pos is None else min(range(len(centres)), key=lambda i: abs(centres[i] - pos))
        if idx is not None and idx >= want_hi_index: hi = mid
        else: lo = mid
    return hi

import os
b = BR = Remote() if os.path.exists(os.environ.get("BRIDGE_SOCK", "/tmp/iphone-bridge.sock")) else Bridge()
b.cmd("homescreen"); time.sleep(2); b.cmd("home"); time.sleep(2)
base = shot("base.png")
res = {}
# keep the cross axis inside the first row/column so the highlight is unambiguous
b.cmd("home")
for axis, centres in (("y", ROWS), ("x", COLS)):      # y first: the x sweep needs gy to stay inside the first icon row
    est = []
    gy = res.get("gy", 1.0)
    cross = 60 if axis == "y" else round(ROWS[0] / PX_PER_PT / gy)   # y sweep: column 1 centre (~60 pt); x sweep: row 1 centre
    for i in (1, 2):                              # boundary between cell i-1 and i
        mid_pt = (centres[i - 1] + centres[i]) / 2 / PX_PER_PT
        guess = int(mid_pt)
        n = bisect(b, base, axis, max(guess // 3, 5), guess * 3, i, cross)
        est.append(mid_pt / n); print(axis, "boundary", i, "at", n, "counts ->", round(mid_pt / n, 3), "pt/count")
    res["g" + axis] = round(sum(est) / len(est), 3)
print(res); save_calib(res)
