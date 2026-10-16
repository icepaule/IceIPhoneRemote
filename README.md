# IceIPhoneRemote

Ein iPhone **sehen und bedienen** mit einem ESP32-S3 für wenige Euro: Der Rechner holt Screenshots vom iPhone-Bildschirm und schickt Maus- und Tastaturbefehle. Basis ist das Projekt [onehumanbeing/esp32-iphone-agent](https://github.com/onehumanbeing/esp32-iphone-agent). Dessen BLE-Strecke zur iOS-App ist hier durch eine **TCP-Bridge** ersetzt, damit ein beliebiger Rechner (oder ein KI-Agent) das iPhone steuern kann, ohne App auf dem Telefon.

> Getestet mit: iPhone 13 Pro (Lightning), iOS 27.0.1, ESP32-S3 N16R8 (8 MB PSRAM, 16 MB Flash), Arduino-ESP32 3.3.6.

## Was das System kann

| Fähigkeit | Wie | Beleg |
|---|---|---|
| Bildschirm ansehen | iPhone spiegelt per AirPlay auf den ESP32, der legt H.264 im PSRAM ab, der Rechner holt es per TCP und dekodiert mit ffmpeg | [Status](#beleg-1-videostrom) |
| iPhone bedienen | ESP32 ist per USB eine Maus und Tastatur, AssistiveTouch macht daraus Tippen und Wischen | [Home-Taste](#beleg-3-hid-erreicht-das-iphone), [Hover](#beleg-4-zeiger-und-hover) |
| Remote nutzbar | TCP-Bridge im Heimnetz, Token-Authentifizierung, OTA-Updates | [Protokoll](#tcp-protokoll) |

Nicht fertig (siehe [Offene Punkte](#status-und-offene-punkte)): ein vollautomatischer Agenten-Loop mit Vision-Modell und eine genaue Zeigerkalibrierung.

## Architektur und Datenfluss

![Datenfluss](docs/img/dataflow.png)

Quelle: [`docs/diagrams/dataflow.mmd`](docs/diagrams/dataflow.mmd). Die Bilder sind mit `mmdc` aus den `.mmd`-Dateien erzeugt.

Das iPhone ist an zwei Stellen mit dem ESP32 verbunden: **WLAN** (der ESP32 spannt einen Hotspot für die AirPlay-Spiegelung auf) und **USB** (der ESP32 ist Maus/Tastatur). Der Rechner spricht nur mit dem ESP32, und zwar über das Heimnetz.

![Ablauf](docs/img/sequence.png)

## Hardware

![Verkabelung](docs/img/hardware.png)

- **ESP32-S3 mit nativem USB und PSRAM** (z. B. N16R8). Ein klassischer ESP32, ESP32-C3 oder ESP8266 geht nicht: kein natives USB bzw. kein PSRAM.
- **iPhone**: iOS 18 oder neuer (getestet mit iOS 27.0.1).
- **Lightning-iPhones** (iPhone 13 und älter): ein **Lightning-auf-USB-3-Kamera-Adapter** mit Ladeanschluss plus Netzteil. Der Adapter macht das iPhone zum USB-Host. Ein einfaches Kabel mit Lightning-Stecker direkt am Board funktioniert **nicht**. USB-C-iPhones (15 und neuer) brauchen nur ein USB-C-Kabel.
- Ein normales USB-A-auf-USB-C-Kabel vom Adapter zum **nativen** USB-Port des ESP32-S3. Bei Boards mit zwei USB-C-Ports ist das der Port, an dem der Rechner das Gerät `303a:1001` (`ESP32S3_DEV`) sieht, nicht der UART-Port.
- Ein Rechner mit Linux, `arduino-cli`, `ffmpeg`, Python 3, optional `mmdc` für die Diagramme.

## Nachbau

### 1. Upstream-Projekt holen

```bash
git clone https://github.com/onehumanbeing/esp32-iphone-agent.git
cd esp32-iphone-agent
git checkout 8effa8c0cc798c3f504e4117b208d5756d9f3b9a   # Basis dieses Patches
```

### 2. Patch einspielen

```bash
git apply /pfad/zu/IceIPhoneRemote/firmware/apsta-tcp-bridge.patch
```

Der Patch ([`firmware/apsta-tcp-bridge.patch`](firmware/apsta-tcp-bridge.patch)) macht Folgendes:

- Neue Datei `hardware/hid_bridge/tcp_link.cpp` ersetzt die BLE-Schicht (`ble_link.cpp` wandert nach `legacy/`). Sie bietet dieselbe API (`ble_link.h`), so bleiben HID- und AirPlay-Code unverändert.
- `netcfg.cpp` bekommt den Modus **APSTA**: Hotspot für das iPhone und gleichzeitig Client im Heimnetz.
- `hid_bridge.ino`: OTA (`ArduinoOTA`) und der Befehl `netinfo`.
- `video_link.cpp`: Chunks bis 1400 Byte statt 512, weil TCP größere Frames verträgt.
- `flash.sh`: Flash-Größe 16 MB und die neue Option `--apsta`.

### 3. Toolchain

```bash
arduino-cli core install esp32:esp32@3.3.6
sudo apt install ffmpeg
```

NimBLE wird nicht mehr gebraucht.

### 4. Zugangsdaten anlegen (nie ins Repo!)

```bash
cp firmware/secrets.example.h hardware/hid_bridge/secrets.h
```

`secrets.h` enthält die WLAN-Daten des Heimnetzes und das Bridge-Token:

```c
#define WIFI_SSID "dein-wlan"
#define WIFI_PASS "dein-passwort"
#define BRIDGE_TOKEN "langes-zufaelliges-token"   // auch OTA-Passwort
```

Ein Token erzeugst du z. B. mit `python3 -c "import secrets;print(secrets.token_urlsafe(24))"`. Die Datei ist in der Upstream-`.gitignore` ausgeschlossen. **Das Token gehört nirgendwo hin außer in diese Datei.**

### 5. Bauen und flashen

Das Board hängt dazu **am Rechner** (nicht am iPhone).

```bash
cd hardware
./flash.sh --apsta --debug --build-only     # kompilieren
FQBN="esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc,FlashSize=16M,PSRAM=opi,PartitionScheme=default_8MB"
stty -F /dev/ttyACM0 1200 ; sleep 3          # Board in den ROM-Bootloader
arduino-cli upload -b "$FQBN" -p /dev/ttyACM0 --input-dir build hid_bridge
esptool --port /dev/ttyACM0 --after hard-reset chip-id
```

Warum nicht einfach `flash.sh` bis zum Ende? Mit angestecktem iPhone und teils auch am Rechner bricht das Skript nach dem 1200-Baud-Reset still ab, weil der Port nicht wie erwartet neu auftaucht. Der direkte `arduino-cli upload` plus ein anschließender Hard-Reset ist zuverlässig.

Den Chip prüfst du vorher mit `esptool --port /dev/ttyACM0 flash-id`: erwartet ESP32-S3, 8 MB PSRAM, 16 MB Flash.

### 6. Board am iPhone anschließen

1. **Rechner-Kabel abziehen.** Sonst ist der Rechner der USB-Host, und die HID-Befehle landen dort ([Beleg](#beleg-3-hid-erreicht-das-iphone)).
2. iPhone → Kamera-Adapter → USB-Kabel → nativer Port des Boards. Netzteil am Ladeanschluss des Adapters.
3. iPhone entsperrt lassen. Falls iOS „Zubehör erlauben?" fragt, bestätigen.

### 7. iPhone einrichten

1. **AssistiveTouch** aktivieren: Einstellungen → Bedienungshilfen → Tippen → AssistiveTouch. Unter „Zeigergeräte" sollte das Board erscheinen.
2. Das Board spannt einen Hotspot `ESP32Agent-XXXX` auf. Das Passwort holst du vom Rechner:
   ```bash
   export BRIDGE_SECRETS=hardware/hid_bridge/secrets.h BRIDGE_HOST=<board-ip>
   python3 tools/bridge.py netinfo
   ```
   Das iPhone tritt diesem WLAN bei (es hat dann kein WLAN-Internet, Mobilfunk bleibt aktiv).
3. **Spiegelung starten.** In iOS 27 liegt sie nicht als eigene Kachel im Kontrollzentrum, sondern: Kontrollzentrum → Medienkachel (oben rechts) → AirPlay-Symbol → **ESP32 Agent**.

### 8. Rechnerseitig nutzen

Die IP des Boards steht im Router oder im seriellen Log (`wifi: got ip ...`).

```bash
export BRIDGE_HOST=<board-ip>
export BRIDGE_SECRETS=hardware/hid_bridge/secrets.h
python3 tools/bridge.py ping
python3 tools/bridge.py homescreen
python3 tools/bridge.py home            # Zeiger in die linke obere Ecke
python3 tools/bridge.py "move 200 100"
python3 tools/bridge.py click
python3 tools/bridge.py "type hallo"
python3 tools/screenshot.py screen.png
```

## TCP-Protokoll

Port **7300**, ein Client gleichzeitig, ein neuer ersetzt den alten.

- Rechner → Board: Textzeilen `<id> <befehl>\n`. Die **erste** Zeile muss `auth <token>` sein, sonst wird die Verbindung nach 5 Sekunden getrennt.
- Board → Rechner: Frames `[Typ u8][Länge u16 LE][Nutzdaten]`. Typ `R` Antwort (`<id> ok` oder `<id> err ...`), `S` Status-JSON (1× pro Sekunde), `V` Video-Chunk.
- Video-Chunk: `[seq u16][flags u8][payload]`, Flags START/END/IDR/CONFIG/SNAP. Ein START-Chunk beginnt mit einem 4-Byte-Zeitstempel, danach Annex-B-H.264.
- Befehle: `ping`, `home`, `move DX DY`, `press`, `release`, `click`, `scroll V H`, `type TEXT`, `key kombi`, `homescreen`, `snap`, `stream on|off`, `netinfo`, `res W H`, `fps N`.

`screenshot.py` fordert per `snap` den aktuellen GOP an, setzt die Chunks zu Annex-B zusammen und lässt ffmpeg das letzte Bild als PNG schreiben.

## Belege, dass es funktioniert

Sensible Inhalte (App-Raster, Namen) sind unkenntlich gemacht. Von den Screenshots ist nur das jeweils relevante Symbol scharf.

### Beleg 1: Videostrom
![Status](docs/img/proof-status-streaming.png)

### Beleg 2: AirPlay-Handshake
Der Empfänger auf dem ESP32 akzeptiert das iPhone und richtet den Mirror-Stream ein.

![Handshake](docs/img/proof-airplay-handshake.png)

### Beleg 3: HID erreicht das iPhone
Zuerst hing das Board am Rechner. Der Kernel führte es als Maus, und `homescreen` ging an den Rechner. Nach dem Umstecken auf den Kamera-Adapter sieht der Rechner nichts mehr, und das iPhone springt auf den Home-Bildschirm.

![HID-Host](docs/img/proof-hid-host.png)

![Home-Taste](docs/img/proof-home-key.png)

### Beleg 4: Zeiger und Hover
Nach `home` und `move` rastet der Zeiger auf einem Symbol ein und hebt es hervor. Das zeigt, dass Mausbewegungen ankommen.

![Hover MikroTik](docs/img/proof-hover-mikrotik.png)
![Hover SmartLife](docs/img/proof-hover-smartlife.png)

## Fallstricke (alle selbst erlebt)

| Symptom | Ursache | Lösung |
|---|---|---|
| Bridge antwortet nur bei jeder zweiten Verbindung | AirPlay (RTSP) belegt Port 7000, später 7100 für den Mirror-Stream | Bridge auf **7300**. AirPlay nutzt 7000, 7010–7012, 7100 |
| Spiegelung `connected`, aber kein Video | gleiche Portkollision auf 7100 | siehe oben |
| Board verbindet sich nicht mit dem WLAN, `reason 15` | Hotspot auf fest Kanal 6, Heim-WLAN auf anderem Kanal | zuerst Client verbinden, dann Hotspot auf denselben Kanal (`WiFi.channel()`) |
| `reason 2` / `15` auch im reinen Client-Modus | manche WPA2-only-WLANs mit ESP32-S3 | ein anderes WLAN (WPA3-Transition) nutzen |
| `homescreen` tut nichts, `usb: ok` | der Rechner ist USB-Host | Rechner-Kabel abziehen, `grep -c 'ESP32S3_DEV Mouse' /proc/bus/input/devices` muss 0 sein |
| `usb: off` am iPhone | Lightning-Kabel direkt am Board | Kamera-Adapter verwenden |
| `flash.sh` endet ohne Ausgabe | Port taucht nach dem 1200-Baud-Reset nicht auf | `arduino-cli upload` direkt, dann `esptool ... --after hard-reset` |
| Board ohne Netz nach dem Flashen | blieb im ROM-Bootloader | `esptool --port ... --after hard-reset chip-id` |
| OTA bricht mit Timeout ab | WLAN ist durch die laufende Spiegelung ausgelastet | per USB flashen |
| Kachel „Bildschirmsynchronisierung" fehlt | iOS 27 | Medienkachel → AirPlay-Symbol |

## Sicherheit

- Die Bridge steuert ein Telefon: Token lang und zufällig wählen, nie ins Repo, nie in Flows oder Doku.
- Das Board hängt im Heimnetz. Wer das Token hat, kann tippen und Screenshots ziehen. Nutze ein abgeschottetes WLAN.
- Der AirPlay-Empfänger ist im Heimnetz per mDNS sichtbar. Jedes Gerät dort könnte spiegeln. Das sollte auf den Hotspot beschränkt werden (siehe offene Punkte).
- Screenshots enthalten alles, was auf dem iPhone sichtbar ist (Nachrichten, Banking, Adressen). Vor jeder Aktion prüfen, was offen ist.

## Status und offene Punkte

Fertig und getestet: Video (ca. 3 bis 6 Bilder/s, 480×1040), Home-Taste, Zeiger-Bewegung, Hover, TCP-Bridge mit Token, OTA.

Offen:

- **Genauigkeit des Zeigers**: iOS zeichnet den Zeiger nicht in die Spiegelung, nur das Hervorheben. Der Zeiger rastet außerdem auf Symbole ein. Eine saubere Zuordnung „Bildpunkt → Mausschritte" fehlt noch. Vorgesehen ist ein Regelkreis: bewegen, Screenshot, prüfen, was hervorgehoben ist, dann klicken.
- **Agenten-Loop**: Screenshot → Vision-Modell (z. B. `qwen2.5vl:7b` auf Ollama) → Aktion als JSON → Bridge. Noch nicht umgesetzt.
- **AirPlay nur auf dem Hotspot** anbieten statt auch im Heimnetz.
- Die Spiegelung endet, wenn sich das iPhone sperrt. Dann antwortet die Bridge mit `err phone usb asleep`.

## Lizenz

Die Skripte in `tools/` und die Doku stehen unter MIT. Der Patch ändert das Upstream-Projekt (MIT). Dessen AirPlay-Teil `hardware/hid_bridge/src/airplay/` ist von UxPlay portiert und steht unter **GPL-3.0**, deshalb steht die Firmware als Ganzes unter GPL-3.0, sobald sie gebaut wird. Der Patch enthält diesen Code nicht, er wird beim Nachbau aus dem Upstream-Repo geholt.
