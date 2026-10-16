#!/usr/bin/env python3
"""Host client for the TCP bridge (tcp_link.cpp). Usage: bridge.py [-H host] <command...>
Host from $BRIDGE_HOST, token from $BRIDGE_TOKEN or the secrets.h at $BRIDGE_SECRETS (default firmware/secrets.h). Commands are the board's: ping, move DX DY, click, type TEXT, netinfo, ..."""
import os, re, socket, struct, sys, time, pathlib

def token():
    if os.environ.get("BRIDGE_TOKEN"): return os.environ["BRIDGE_TOKEN"]
    f = pathlib.Path(os.environ.get("BRIDGE_SECRETS", pathlib.Path(__file__).resolve().parents[1] / "firmware" / "secrets.h"))
    return re.search(r'BRIDGE_TOKEN\s+"([^"]*)"', f.read_text()).group(1)

class Bridge:
    def __init__(self, host=os.environ.get("BRIDGE_HOST", "192.168.178.44"), port=7300):
        for attempt in range(4):  # the board answers the next connection only after it noticed the last one closing
            self.s = socket.create_connection((host, port), timeout=8)
            self.buf = b""; self.video = []; self.status = None
            self.s.sendall(f"auth {token()}\n".encode())
            try:
                assert self.recv_reply("0", 3)[0] == "ok", "auth failed"
                return
            except TimeoutError:
                self.s.close()
        raise TimeoutError("bridge did not answer auth")
    def pump(self, timeout):
        self.s.settimeout(timeout)
        try: d = self.s.recv(65536)
        except socket.timeout: return None
        if not d: raise ConnectionError("closed")
        self.buf += d
        out = []
        while len(self.buf) >= 3:
            t, n = self.buf[0], struct.unpack("<H", self.buf[1:3])[0]
            if len(self.buf) < 3 + n: break
            out.append((chr(t), self.buf[3:3 + n])); self.buf = self.buf[3 + n:]
        for t, p in out:
            if t == "S": self.status = p.decode()
            elif t == "V": self.video.append(p)
        return out
    def recv_reply(self, rid, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            for t, p in self.pump(0.5) or []:
                if t == "R" and p.decode().split(" ", 1)[0] == rid: return p.decode().split(" ", 1)[1].split(" ", 1) + [""]
        raise TimeoutError(rid)
    def cmd(self, line, rid="1"):
        self.s.sendall(f"{rid} {line}\n".encode()); r = self.recv_reply(rid); return " ".join(r).strip()

if __name__ == "__main__":
    a = sys.argv[1:]; host = os.environ.get("BRIDGE_HOST", "192.168.178.44")
    if a[:1] == ["-H"]: host, a = a[1], a[2:]
    print(Bridge(host).cmd(" ".join(a)))
