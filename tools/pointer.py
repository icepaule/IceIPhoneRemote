"""Pointer model: maps screenshot pixels to mouse counts.

The mirror stream does not draw the pointer, only what iOS highlights under it (hover). So we dead-reckon from the
top-left corner (`home`) with a calibrated gain (points per mouse count), then confirm with the hover highlight and
correct if the highlighted element does not contain the target."""
import json, os, pathlib, time
from PIL import Image
import numpy as np

CALIB = pathlib.Path(os.environ.get("POINTER_CALIB", pathlib.Path(__file__).with_name("calib.json")))
PX_PER_PT = 720 / 390          # screenshot pixels per iOS point (iPhone 13 Pro, 390 pt wide)

def load_calib():
    try: return json.loads(CALIB.read_text())
    except Exception: return {"gx": 1.0, "gy": 1.0}   # points per mouse count

def save_calib(c): CALIB.write_text(json.dumps(c, indent=1))

def diff_box(a_path, b_path, region=None, thr=22, min_px=400):
    """Bounding box (x0,y0,x1,y1) of what changed between two screenshots (status bar ignored), or None."""
    A = np.asarray(Image.open(a_path).convert("L"), dtype=int); B = np.asarray(Image.open(b_path).convert("L"), dtype=int)
    d = abs(A - B) > thr
    d[:110, :] = False
    if region:
        x0, y0, x1, y1 = region; m = np.zeros_like(d); m[max(y0, 0):y1, max(x0, 0):x1] = True; d &= m
    ys, xs = np.nonzero(d)
    if len(xs) < min_px: return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

class Pointer:
    def __init__(self, bridge, shoot, workdir, calib=None):
        self.b, self.shoot, self.dir, self.c = bridge, shoot, pathlib.Path(workdir), calib or load_calib()
        self.pos = None                                   # pointer position in points; None until `home`
    def home(self):
        self.b.cmd("home"); self.pos = [0.0, 0.0]
    def _move_pt(self, dx, dy):
        cx, cy = round(dx / self.c["gx"]), round(dy / self.c["gy"])
        if abs(cx) > 3000 or abs(cy) > 3000: raise ValueError("move too large")
        if cx or cy: self.b.cmd(f"move {cx} {cy}")
        self.pos[0] += cx * self.c["gx"]; self.pos[1] += cy * self.c["gy"]
    def goto_px(self, x, y, corrections=2):
        """Park the pointer on screenshot pixel (x, y). Returns (confirmed_by_hover, hover_box)."""
        self.home(); time.sleep(1.2)                       # pointer in the corner: nothing is hovered yet
        before = self.shoot(self.dir / "p_before.png")
        self._move_pt(x / PX_PER_PT, y / PX_PER_PT)
        box = None
        for attempt in range(corrections + 1):
            time.sleep(1.0)
            after = self.shoot(self.dir / "p_after.png")
            box = diff_box(before, after, region=(x - 260, y - 260, x + 260, y + 260))
            if box and box[0] - 25 <= x <= box[2] + 25 and box[1] - 25 <= y <= box[3] + 25:
                return True, box                           # the highlighted element contains the target
            if not box or attempt == corrections: break
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            self._move_pt((x - cx) / PX_PER_PT, (y - cy) / PX_PER_PT)
        return False, box
    def click(self): self.b.cmd("click")
    def drag(self, x0, y0, x1, y1):
        ok, _ = self.goto_px(x0, y0, corrections=0)
        self.b.cmd("press"); time.sleep(0.15)
        self._move_pt((x1 - x0) / PX_PER_PT, (y1 - y0) / PX_PER_PT); time.sleep(0.2)
        self.b.cmd("release")
