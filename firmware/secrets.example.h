// Copy to secrets.h (git-ignored). Used by `hardware/flash.sh --apsta`: the board keeps its hotspot for the
// iPhone and also joins this network, where it serves the TCP bridge (port 7300) and OTA.
#define WIFI_SSID "your-wifi"
#define WIFI_PASS "your-password"
#define BRIDGE_TOKEN "long-random-token"  // first line a TCP client must send: "auth <token>"; also the OTA password
