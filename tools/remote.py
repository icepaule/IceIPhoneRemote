#!/usr/bin/env python3
"""Client for bridged.py. Usage: remote.py cmd <board command...> | remote.py shot out.png | remote.py info
As a module: Remote().cmd(line), Remote().shot(path); drop-in for Bridge/grab in agent.py, pointer.py, calibrate.py."""
import os, socket, sys

class Remote:
    def __init__(self, sock=os.environ.get("BRIDGE_SOCK", "/tmp/iphone-bridge.sock")):
        self.s = socket.socket(socket.AF_UNIX); self.s.connect(sock); self.f = self.s.makefile("rw"); self.video = []
    def _ask(self, line):
        self.f.write(line + "\n"); self.f.flush(); return self.f.readline().rstrip("\n")
    def cmd(self, line, rid=None): return self._ask("CMD " + line)
    def shot(self, path):
        r = self._ask(f"SHOT {path}")
        if not r.startswith("ok"): raise RuntimeError(r)
        return path

if __name__ == "__main__":
    r, a = Remote(), sys.argv[1:]
    print(r._ask("INFO") if a[:1] == ["info"] else r.shot(a[1]) if a[:1] == ["shot"] else r.cmd(" ".join(a[1:])))
