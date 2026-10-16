#!/usr/bin/env python3
"""Grab the iPhone screen: asks the board for the current GOP (`snap`), decodes it with ffmpeg, writes a PNG.
Usage: screenshot.py out.png [-H host]"""
import os, struct, subprocess, sys, time, pathlib
from PIL import Image
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

def grab(out_png, host=os.environ.get("BRIDGE_HOST", "192.168.178.44"), bridge=None):
    """Screenshot via `snap`. Pass an open Bridge to reuse its connection (the board serves one client at a time)."""
    if bridge is not None and hasattr(bridge, "shot"): return bridge.shot(out_png)   # bridged.py: latest frame, instant
    b = bridge or Bridge(host)
    b.video.clear()
    reply = b.cmd("snap", "5")
    if not reply.startswith("ok"): raise RuntimeError(reply)
    end = time.time() + 1.0
    while time.time() < end: b.pump(0.2)
    h264 = annexb_from_chunks(b.video)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", "-f", "h264", "-i", "pipe:0"], input=h264, capture_output=True)
    try: w, h = map(int, probe.stdout.decode().strip().split(",")[:2])
    except Exception: raise RuntimeError("cannot read video size: " + probe.stderr.decode()[:200])
    # decode to raw frames in a pipe and keep only the last one: writing every GOP frame as PNG took minutes
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "h264", "-i", "-", "-vsync", "0", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "pipe:1"], input=h264, capture_output=True)
    n = len(p.stdout) // (w * h * 3)
    if n == 0: raise RuntimeError("no frame decoded: " + p.stderr.decode()[:200])
    Image.frombytes("RGB", (w, h), p.stdout[(n - 1) * w * h * 3:n * w * h * 3]).save(out_png)
    return out_png

if __name__ == "__main__":
    a = sys.argv[1:]; host = os.environ.get("BRIDGE_HOST", "192.168.178.44")
    if "-H" in a: i = a.index("-H"); host = a[i + 1]; del a[i:i + 2]
    print(grab(a[0] if a else "screen.png", host))
