#!/usr/bin/env python3
"""Manual driver on top of bridged.py (for a human or an LLM that reads the screenshots itself).

  tap.py shot out.png            screenshot (latest decoded frame)
  tap.py tap X Y                 park pointer on screenshot pixel (X, Y), confirm by hover, click
  tap.py swipe X Y X2 Y2         drag
  tap.py scroll N                mouse wheel (+N = read further down)
  tap.py type TEXT               type text, mapped for the German hardware layout (rawtype: US codes as is)
  tap.py key enter|esc|tab|...   key combo
  tap.py home                    iOS home screen"""
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from remote import Remote
from pointer import Pointer
from typing_de import type_de

r = Remote(); a = sys.argv[1:]
work = pathlib.Path(tempfile.gettempdir()) / "iphone-tap"; work.mkdir(exist_ok=True)
ptr = Pointer(r, lambda p: r.shot(str(p)), work)
op = a[0]
if op == "shot": print(r.shot(a[1]))
elif op == "tap":
    ok, box = ptr.goto_px(int(a[1]), int(a[2]), corrections=1)
    print("hover:", "ja" if ok else "nein (kein Highlight, klicke trotzdem)", box); ptr.click()
elif op == "swipe": ptr.drag(*map(int, a[1:5])); print("ok")
elif op == "scroll": print(r.cmd(f"scroll {a[1]} 0"))
elif op == "type": type_de(r, " ".join(a[1:])); print("ok")
elif op == "rawtype": print(r.cmd("type " + " ".join(a[1:])))
elif op == "key": print(r.cmd("key " + a[1]))
elif op == "home": print(r.cmd("homescreen"))
else: sys.exit(__doc__)
