#!/usr/bin/env python3
"""Daemon: owns the one TCP connection to the board, decodes the mirrored H.264 stream continuously (PyAV, run with .venv/bin/python) and keeps the
latest frame, so a screenshot is instant instead of re-decoding a GOP (minutes on a static screen).

  bridged.py &            # needs BRIDGE_HOST / BRIDGE_SECRETS like bridge.py
  remote.py cmd "move 10 0" | remote.py shot out.png

Unix socket /tmp/iphone-bridge.sock, line protocol: `CMD <board command>` -> reply text, `SHOT <png path>` -> ok|err,
`INFO` -> frame age and size."""
import os, socket, struct, sys, threading, time, pathlib
import av
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from PIL import Image
from bridge import token

SOCK = os.environ.get("BRIDGE_SOCK", "/tmp/iphone-bridge.sock")
START, END, IDR, CONFIG, BENCH = 1, 2, 4, 8, 16

class Daemon:
    def __init__(self, host, port=7300):
        self.host, self.port = host, port
        self.frame, self.frame_at, self.status = None, 0.0, ""
        self.lock = threading.Lock(); self.tx = threading.Lock()
        self.pending = {}; self.next_id = 1
        self.dec = av.CodecContext.create("h264", "r"); self.dec.thread_type = "NONE"   # one packet in, frame out: no latency
    def decode(self, au):
        try:
            for fr in self.dec.decode(av.Packet(au)):
                arr = fr.to_ndarray(format="rgb24")
                with self.lock: self.frame, self.frame_at = arr, time.time()
        except av.error.FFmpegError as e:
            print("decode:", e, flush=True)                  # lost chunks: wait for the next keyframe
    def connect(self):
        self.s = socket.create_connection((self.host, self.port), timeout=10); self.s.settimeout(None)
        self.s.sendall(f"auth {token()}\n".encode())
    def reader(self):
        buf, cur = b"", None
        while True:
            d = self.s.recv(65536)
            if not d: print("board closed the connection", flush=True); os._exit(2)
            buf += d
            while len(buf) >= 3:
                t, n = chr(buf[0]), struct.unpack("<H", buf[1:3])[0]
                if len(buf) < 3 + n: break
                p, buf = buf[3:3 + n], buf[3 + n:]
                if t == "R":
                    rid, _, rest = p.decode().partition(" ")
                    ev = self.pending.get(rid)
                    if ev: ev[1] = rest; ev[0].set()
                elif t == "S":
                    self.status = p.decode(errors="replace")
                elif t == "V":
                    flags, payload = p[2], p[3:]
                    if flags & BENCH: continue
                    if flags & START: cur = bytearray(); payload = payload[4:]
                    if cur is None: continue
                    cur += payload
                    if flags & END:
                        self.decode(bytes(cur)); cur = None
    def cmd(self, line, timeout=15):
        with self.tx:
            rid = str(self.next_id); self.next_id += 1
            ev = [threading.Event(), ""]; self.pending[rid] = ev
            self.s.sendall(f"{rid} {line}\n".encode())
        ok = ev[0].wait(timeout); self.pending.pop(rid, None)
        return ev[1] if ok else "err timeout"
    def shot(self, path):
        with self.lock: f, at = self.frame, self.frame_at
        if f is None: return "err no frame yet"
        Image.fromarray(f).save(path); return f"ok age={time.time()-at:.1f}s"
    def serve(self):
        try: os.unlink(SOCK)
        except FileNotFoundError: pass
        srv = socket.socket(socket.AF_UNIX); srv.bind(SOCK); os.chmod(SOCK, 0o600); srv.listen(4)
        while True:
            c, _ = srv.accept(); threading.Thread(target=self.handle, args=(c,), daemon=True).start()
    def handle(self, c):
        f = c.makefile("rw")
        for line in f:
            op, _, arg = line.rstrip("\n").partition(" ")
            if op == "CMD": r = self.cmd(arg)
            elif op == "SHOT": r = self.shot(arg)
            elif op == "INFO": r = (f"frame_age={time.time()-self.frame_at:.1f}s" if self.frame is not None else "no frame") + " " + self.status
            else: r = "err unknown"
            f.write(r.replace("\n", " ") + "\n"); f.flush()

if __name__ == "__main__":
    d = Daemon(os.environ.get("BRIDGE_HOST", "192.168.178.44"))
    d.connect()
    threading.Thread(target=d.reader, daemon=True).start()
    print("auth:", d.cmd("ping"), flush=True)
    print("stream:", d.cmd("stream on"), flush=True)
    d.serve()
