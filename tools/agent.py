#!/usr/bin/env python3
"""Agent loop: screenshot -> vision model (Ollama) -> one action -> bridge -> repeat.

  agent.py "Oeffne die Einstellungen und zeige die iOS-Version" [--model qwen2.5vl:7b] [--ollama URL] [--max-steps 15]

Safety: stops at `touch /tmp/iphone-agent.stop`, after --max-steps, on a repeated no-op loop, and whenever the model asks
for the user or wants to do something that looks like paying, deleting, sending, or entering credentials (unless
--allow-risky). Runs are stored in ~/iphone-agent-runs/ (screenshots may contain private data: never commit them)."""
import argparse, base64, io, json, os, pathlib, re, sys, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from PIL import Image, ImageDraw
import numpy as np
from bridge import Bridge
from remote import Remote
from typing_de import type_de
from screenshot import grab
from pointer import Pointer, PX_PER_PT

STOP = pathlib.Path("/tmp/iphone-agent.stop")
RISKY = re.compile(r"bezahl|kaufen|kauf |zahlung|bestell|loesch|lösch|delete|senden|absenden|passwort|password|pin\b|"
                   r"anmelden|login|ueberweis|überweis|transfer|apple pay|face id", re.I)
RISKY_NOCRED = re.compile(r"bezahl|kaufen|kauf |zahlung|bestell|loesch|lösch|delete|senden|absenden|ueberweis|überweis|transfer|apple pay", re.I)
SECRET_ENV = "IPHONE_AGENT_SECRET"                        # real secret; the model only ever sees the placeholder {{PW}}
SIZE = (504, 1092)                                        # multiples of 28: the model's native patch grid

SYSTEM = """Du bedienst ein iPhone (iOS) wie ein Mensch. Du siehst einen Screenshot (Breite {w}, Hoehe {h} Pixel) und
bekommst ein Ziel. Antworte mit EINEM JSON-Objekt und sonst nichts:
{{"thought": "kurze Begruendung", "action": "tap|swipe|scroll|type|home|wait|done|ask_user|fail",
  "x": int, "y": int,              # tap: Mitte des Ziel-Elements in Bildpixeln
  "x2": int, "y2": int,            # swipe: Endpunkt, Start ist x,y
  "dy": int,                       # scroll: positiv = Inhalt nach oben schieben (nach unten lesen)
  "text": "...",                   # type: nur ASCII
  "reason": "..."}}                # done/fail/ask_user: Ergebnis bzw. Frage
Regeln:
- Genau eine Aktion pro Antwort. Koordinaten sind Pixel in DIESEM Bild, Ursprung oben links.
- tap trifft nur Symbole, Schaltflaechen und Listeneintraege. Kein Tippen auf leere Flaechen.
- Zum Wechseln der App: action home (Home-Bildschirm), dann das App-Symbol antippen.
- Wenn das Ziel erreicht ist: action done und beschreibe in reason, was du siehst.
- Bei Passwort, Zahlung, Kauf, Loeschen, Senden von Nachrichten oder wenn unklar: action ask_user.
- Das Passwort tippst du immer als Text {{PW}} ein (wird lokal ersetzt). Nenne oder rate nie einen echten Wert.
- Wiederhole nie dieselbe wirkungslose Aktion; probiere etwas anderes oder gib fail."""

def encode(png_path):
    im = Image.open(png_path).convert("RGB"); W, H = im.size
    buf = io.BytesIO(); im.resize(SIZE, Image.LANCZOS).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode(), W, H

def ask_model(url, model, goal, history, png_path):
    b64, W, H = encode(png_path)
    hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(history[-8:])) or "(noch keine)"
    msgs = [{"role": "system", "content": SYSTEM.format(w=SIZE[0], h=SIZE[1])},
            {"role": "user", "content": f"Ziel: {goal}\nBisherige Aktionen:\n{hist}\nWas ist der naechste Schritt?",
             "images": [b64]}]
    body = json.dumps({"model": model, "messages": msgs, "stream": False, "format": "json", "keep_alive": "10m",
                       "options": {"temperature": 0, "num_ctx": 8192}}).encode()
    req = urllib.request.Request(url + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r: out = json.load(r)["message"]["content"]
    return json.loads(out), W / SIZE[0], H / SIZE[1]

def changed(a, b):
    A = np.asarray(Image.open(a).convert("L"), dtype=int); B = np.asarray(Image.open(b).convert("L"), dtype=int)
    d = abs(A - B) > 30; d[:110, :] = False
    return float(d.mean())

def mark(png, x, y, out):
    im = Image.open(png).convert("RGB"); d = ImageDraw.Draw(im)
    d.ellipse([x - 28, y - 28, x + 28, y + 28], outline=(255, 40, 40), width=6); im.save(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("goal"); ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://10.10.0.210:11434"))
    ap.add_argument("--max-steps", type=int, default=15); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-risky", action="store_true"); ap.add_argument("--allow-secret", action="store_true", help="erlaubt Zugangsdaten-Eingabe ({{PW}}), alles andere Riskante stoppt weiter"); ap.add_argument("--settle", type=float, default=2.0)
    a = ap.parse_args()
    run = pathlib.Path.home() / "iphone-agent-runs" / time.strftime("%Y%m%d-%H%M%S"); run.mkdir(parents=True)
    log = (run / "run.jsonl").open("a"); STOP.unlink(missing_ok=True)
    bridge = Remote() if os.path.exists(os.environ.get("BRIDGE_SOCK", "/tmp/iphone-bridge.sock")) else Bridge(); shoot = lambda p: grab(str(p), bridge=bridge); ptr = Pointer(bridge, shoot, run)
    history, last, repeats = [], None, 0
    print(f"run dir: {run}")
    for step in range(1, a.max_steps + 1):
        if STOP.exists(): print("stop file found, abort"); break
        cur = run / f"s{step:02d}.png"; shoot(cur)
        t0 = time.time()
        act, sx, sy = ask_model(a.ollama, a.model, a.goal, history, cur)
        kind = str(act.get("action", "")).lower(); thought = act.get("thought", "")
        print(f"[{step}] {kind} {({k: act[k] for k in ('x','y','x2','y2','dy','text') if k in act})}  ({time.time()-t0:.0f}s) {thought}")
        log.write(json.dumps({"step": step, "act": act}, ensure_ascii=False) + "\n"); log.flush()
        if kind in ("done", "fail", "ask_user"):
            print(f"==> {kind}: {act.get('reason', '')}"); break
        risky = RISKY_NOCRED if a.allow_secret else RISKY
        if not a.allow_risky and risky.search(f"{thought} {act.get('text','')} {act.get('reason','')}"):
            print("==> stop: Aktion wirkt riskant (Zahlung/Loeschen/Senden/Zugangsdaten). Mit --allow-risky erzwingen."); break
        sig = json.dumps({k: act.get(k) for k in ("action", "x", "y", "text", "dy")}, sort_keys=True)
        repeats = repeats + 1 if sig == last else 0; last = sig
        if repeats >= 2: print("==> stop: gleiche Aktion mehrfach ohne Wirkung"); break
        desc = kind
        if a.dry_run: history.append(f"{kind} (dry-run)"); continue
        try:
            if kind == "tap":
                x, y = int(act["x"] * sx), int(act["y"] * sy); mark(cur, x, y, run / f"s{step:02d}_target.png")
                ok, box = ptr.goto_px(x, y); ptr.click(); desc = f"tap ({x},{y}) hover={'ja' if ok else 'nein'}"
            elif kind == "swipe":
                x, y, x2, y2 = (int(act[k] * s) for k, s in (("x", sx), ("y", sy), ("x2", sx), ("y2", sy)))
                ptr.drag(x, y, x2, y2); desc = f"swipe ({x},{y})->({x2},{y2})"
            elif kind == "scroll":
                dy = int(act.get("dy", 5)); bridge.cmd(f"scroll {max(-20, min(20, dy))} 0"); desc = f"scroll {dy}"
            elif kind == "type":
                txt = str(act.get("text", "")); real = txt.replace("{{PW}}", os.environ.get(SECRET_ENV, "")) if a.allow_secret else txt
                type_de(bridge, re.sub(r"[^\x20-\x7e]", "", real)); desc = "type " + txt
            elif kind == "home":
                bridge.cmd("homescreen")
            elif kind == "wait":
                pass
            else:
                desc = f"unbekannte Aktion {kind}"
        except Exception as e:
            desc = f"{kind} fehlgeschlagen: {e}"
        time.sleep(a.settle); after = run / f"s{step:02d}_after.png"; shoot(after)
        delta = changed(cur, after)
        history.append(f"{desc} -> Bild {'veraendert' if delta > 0.01 else 'UNVERAENDERT'}")
        print("     ", history[-1])
    else:
        print("==> max steps reached")
    print(f"Verlauf: {run}")

if __name__ == "__main__":
    main()
