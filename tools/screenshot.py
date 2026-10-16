#!/usr/bin/env python3
"""Grab the iPhone screen: asks the board for the current GOP (`snap`), decodes it with ffmpeg, writes a PNG.
Usage: screenshot.py out.png [-H host]"""
import os, struct, subprocess, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from bridge import Bridge

START, END, IDR, CONFIG, BENCH, SNAP = 1, 2, 4, 8, 16, 32

def annexb_from_chunks(chunks):
    out, cur = bytearray(), None
    for c in chunks:
        flags, payload = c[2], c[3:]
        if flags & BENCH: continue
        if flags & START:
            cur = bytearray(); payload = payload[4:]  # u32 board timestamp
        if cur is None: continue
        cur += payload
        if flags & END: out += cur; cur = None
    return bytes(out)

def grab(out_png, host=os.environ.get("BRIDGE_HOST", "192.168.178.44")):
    b = Bridge(host)
    reply = b.cmd("snap", "5")
    if not reply.startswith("ok"): raise RuntimeError(reply)
    end = time.time() + 1.0
    while time.time() < end: b.pump(0.2)
    h264 = annexb_from_chunks(b.video)
    p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "h264", "-i", "-", "-vsync", "0", "-update", "1", out_png],
                       input=h264, capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.decode())
    return out_png

if __name__ == "__main__":
    a = sys.argv[1:]; host = os.environ.get("BRIDGE_HOST", "192.168.178.44")
    if "-H" in a: i = a.index("-H"); host = a[i + 1]; del a[i:i + 2]
    print(grab(a[0] if a else "screen.png", host))
