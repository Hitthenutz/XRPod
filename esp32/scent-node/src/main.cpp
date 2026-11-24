// XRPod scent carrier rev A — GPIO bench test over USB serial AND Wi-Fi/MQTT
//
// Same commands either way. Over MQTT:
//   send to   xrpod/test/cmd     (e.g. "k1", "p25", "p25 2")
//   replies   xrpod/test/reply
//   status    xrpod/test/status  ("online" / "offline", retained)
//
//   ?          help
//   k1 / k0    master kill Q1 (GPIO16) ON / OFF  -> powers the USB splitter
//   p25        one button press (150 ms) on GPIO25
//   p25 3      three presses on GPIO25
//   h25        hold GPIO25 HIGH (auto-releases after 5 s) — for meter checks
//   l25        release GPIO25
//   c25        set A1 to CONTINUOUS (sends however many presses it takes)
//   i25        set A1 to INTERMITTENT
//   o25        set A1 to OFF
//   x          everything OFF
//   s          status table
//   net        Wi-Fi / MQTT status and why it isn't connecting
//   scan       list the 2.4 GHz Wi-Fi networks the ESP32 can see
//
// The modules can't report their mode, so the ESP32 tracks it by counting presses
// (off -> continuous -> intermittent -> off). k0 resets every module to OFF.
// If the table ever disagrees with what you see, send k0 then k1 to resync.
//
// Fail-safe: everything OFF at boot and whenever MQTT drops.
//
// HUD control (protocol in docs/subsystems.md, Pi side in pi/scent.py):
//   xrpod/scent/cmd    <- Pi  {"selected_scent":"lavender","scent_intensity_pct":60}
//   xrpod/scent/state  -> Pi  what is running (retained, every 5 s)
//   xrpod/scent/node   -> Pi  "online"/"offline" (retained, last will)
//   xrpod/scent/error  -> Pi  {"error":"unknown_scent"} etc.
//   Scents: lavender = A1/A2, pine = A3/A4, citrus = A5/A6.
//   Simple on/off, continuous mode only: a scent = that scent's first diffuser in
//   CONTINUOUS; "none" = off. Intensity is ignored (even 0%).
//   Presses only on a change: ON = 1 press (idle -> continuous), OFF = 2 presses
//   (continuous -> intermittent -> off). The Pi's 5 s resends press nothing.
//   The kill switch is not used for HUD control (Q1 doesn't fully cut module power on rev A).
//   Start with the module idle (red). Don't mix serial button commands with HUD control.
//   If the Pi goes quiet for 15 s, everything turns off.
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <PubSubClient.h>
#include <stdarg.h>
#include <ArduinoJson.h>
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD

#ifndef MQTT_USER
#define MQTT_USER nullptr
#endif
#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD nullptr
#endif

const char* TOPIC_CMD    = "xrpod/test/cmd";
const char* TOPIC_REPLY  = "xrpod/test/reply";
const char* TOPIC_STATUS = "xrpod/test/status";
const char* TOPIC_SCENT_CMD   = "xrpod/scent/cmd";
const char* TOPIC_SCENT_STATE = "xrpod/scent/state";
const char* TOPIC_SCENT_NODE  = "xrpod/scent/node";
const char* TOPIC_SCENT_ERROR = "xrpod/scent/error";
const unsigned long HUD_TIMEOUT_MS = 15000;  // Pi resends every 5 s
const unsigned long STATE_EVERY_MS = 5000;
const char* SCENT_NAMES[] = {"lavender", "pine", "citrus"};  // pairs of modules: 0/1, 2/3, 4/5

const int BTN_PINS[]    = {25, 26, 27, 4, 32, 33};
const char* BTN_NAMES[] = {"A1 Lavender1", "A2 Lavender2", "A3 Pine1",
                           "A4 Pine2", "A5 Citrus1", "A6 Citrus2"};
const int N = 6;
const int KILL_PIN = 16;
const int LED_PIN  = 2;
const int PRESS_MS = 150;     // button hold time per press
const int GAP_MS   = 400;     // gap between repeated presses
const unsigned long HOLD_MAX_MS = 5000;
const unsigned long NET_RETRY_MS = 3000;

enum Mode { M_OFF = 0, M_CONT = 1, M_INT = 2 };
const char* MODE_NAMES[] = {"off", "CONTINUOUS", "INTERMITTENT"};
Mode mode[6] = {M_OFF, M_OFF, M_OFF, M_OFF, M_OFF, M_OFF};

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

String line;
volatile uint8_t lastWifiReason = 0;  // set by the Wi-Fi event handler

// Why the last Wi-Fi attempt failed, in plain words.
const char* wifiReasonText(uint8_t r) {
  switch (r) {
    case 0: return "no attempt yet";
    case WIFI_REASON_NO_AP_FOUND:
      return "can't see that network: name is wrong, it's on 5 GHz (ESP32 is 2.4 GHz only), or the hotspot is off";
    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
      return "network found but the password was rejected";
    case WIFI_REASON_ASSOC_FAIL:
    case WIFI_REASON_ASSOC_EXPIRE:
      return "network found but it refused the connection (full, or a MAC filter)";
    case WIFI_REASON_BEACON_TIMEOUT:
      return "lost the network (out of range or the hotspot went down)";
    case 2:   return "auth expired (password or security type mismatch)";
    case 210: return "network found but its security type isn't one the ESP32 accepts";
    case 211: return "network found but its security is below the allowed minimum";
    case 212: return "network found but the signal is too weak";
  }
  return "other Wi-Fi error";
}
int heldPin = -1;
unsigned long heldAt = 0;

// What the HUD last asked for
String hudScent = "none";
int hudPct = 0;
bool hudDriving = false;          // true while the HUD has a scent running
int hudPair = -1;                 // which scent pair is on (0 lavender, 1 pine, 2 citrus)
unsigned long hudLastCmd = 0;
String lastReason = "boot";

// Print to serial and, if connected, publish to xrpod/test/reply.
void reply(const char* fmt, ...) {
  char buf[400];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  Serial.println(buf);
  if (mqtt.connected()) mqtt.publish(TOPIC_REPLY, buf);
}

int idxOf(int pin) {
  for (int i = 0; i < N; i++) if (BTN_PINS[i] == pin) return i;
  return -1;
}

void allOff() {
  for (int i = 0; i < N; i++) digitalWrite(BTN_PINS[i], LOW);
  digitalWrite(KILL_PIN, LOW);
  heldPin = -1;
  for (int i = 0; i < N; i++) mode[i] = M_OFF;
  hudDriving = false;
}

bool powered() { return digitalRead(KILL_PIN); }

void status() {
  char buf[400];
  int n = snprintf(buf, sizeof(buf), "---- POWER (Q1): %s ----", powered() ? "ON" : "OFF");
  for (int i = 0; i < N && n < (int)sizeof(buf); i++) {
    const char* m = powered() ? MODE_NAMES[mode[i]] : "no power";
    n += snprintf(buf + n, sizeof(buf) - n, "\n  %-13s GPIO%-2d  %s%s", BTN_NAMES[i], BTN_PINS[i],
                  (powered() && mode[i] != M_OFF) ? ">> " : "   ", m);
  }
  reply("%s", buf);
}

void help() {
  reply("k1/k0 = power on/off | p25 [n] = press n times | c25/i25/o25 = continuous/intermittent/off | h25/l25 = hold/release | x = all off | s = status | net = connection info | scan = Wi-Fi networks");
}

void press(int i, int times) {
  for (int t = 0; t < times; t++) {
    digitalWrite(BTN_PINS[i], HIGH);
    delay(PRESS_MS);
    digitalWrite(BTN_PINS[i], LOW);
    if (powered()) mode[i] = (Mode)((mode[i] + 1) % 3);
    if (t < times - 1) delay(GAP_MS);
  }
}

void netInfo() {
  bool up = WiFi.status() == WL_CONNECTED;
  Serial.printf("wifi   : '%s' %s\n", WIFI_SSID, up ? "connected" : "NOT connected");
  if (up) {
    Serial.printf("         ESP32 IP %s, Pi/router %s, signal %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.gatewayIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.printf("         last problem: %s (reason %u)\n", wifiReasonText(lastWifiReason), lastWifiReason);
  }
  Serial.printf("broker : %s:%d -> %s (rc=%d)\n", MQTT_HOST, (int)MQTT_PORT,
                mqtt.connected() ? "connected" : "not connected", mqtt.state());
}

void scanWifi() {
  bool up = WiFi.status() == WL_CONNECTED;
  Serial.println("scanning 2.4 GHz Wi-Fi (about 3 s)...");
  if (!up) WiFi.disconnect();  // stop retrying so the scan can run
  int n = WiFi.scanNetworks();
  bool found = false;
  for (int i = 0; i < n; i++) {
    bool match = WiFi.SSID(i) == WIFI_SSID;
    found |= match;
    Serial.printf("  %s %-32s ch %2d  %4d dBm  auth %d\n", match ? ">>" : "  ", WiFi.SSID(i).c_str(),
                  WiFi.channel(i), WiFi.RSSI(i), (int)WiFi.encryptionType(i));
  }
  if (n <= 0) Serial.println("  no networks found");
  WiFi.scanDelete();
  if (found) {
    reply("scan: '%s' is visible - if it still won't join, check the password", WIFI_SSID);
  } else {
    reply("scan: '%s' NOT visible - check the exact name, set the hotspot to 2.4 GHz, or turn it on", WIFI_SSID);
  }
  // Plain join: locking to the Pi's BSSID/channel made every attempt fail with "auth expired"
  if (!up) WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// Press module i until it is in `target` mode (needs power on).
void setMode(int i, Mode target) {
  int n = (target - mode[i] + 3) % 3;
  if (n) press(i, n);
}

void publishScentState() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  int pair = hudPair;
  bool on = hudDriving && pair >= 0;
  doc["selected_scent"] = on ? hudScent.c_str() : "none";
  doc["scent_intensity_pct"] = on ? hudPct : 0;
  JsonArray d = doc["diffusers"].to<JsonArray>();
  d.add(on);
  d.add(false);
  doc["reason"] = lastReason.c_str();
  doc["uptime_s"] = millis() / 1000;
  char buf[200];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(TOPIC_SCENT_STATE, (const uint8_t*)buf, n, true);
}

void scentError(const char* code) {
  char buf[64];
  snprintf(buf, sizeof(buf), "{\"error\":\"%s\"}", code);
  if (mqtt.connected()) mqtt.publish(TOPIC_SCENT_ERROR, buf);
  Serial.printf("[hud] error: %s\n", code);
}

// HUD off: press the running diffuser continuous -> intermittent -> off (2 presses).
void scentOff(const char* reason) {
  if (hudDriving && hudPair >= 0) {
    press(hudPair * 2, 2);
    mode[hudPair * 2] = M_OFF;
  }
  hudDriving = false;
  hudPair = -1;
  lastReason = reason;
}

// Apply a HUD command. Safe to call every 5 s with the same values: presses only on a change.
void applyScent(const String& scent, int pct) {
  pct = constrain(pct, 0, 100);
  int pair = -1;
  for (int s = 0; s < 3; s++) if (scent == SCENT_NAMES[s]) pair = s;
  if (scent != "none" && pair < 0) scentError("unknown_scent");
  hudScent = scent; hudPct = pct;

  bool want = pair >= 0;  // intensity ignored: scent name alone decides on/off
  if (!want) {
    if (hudDriving) { scentOff("hud"); Serial.println("[hud] scent OFF (2 presses)"); }
    publishScentState();
    return;
  }
  if (hudDriving && hudPair == pair) { publishScentState(); return; }  // already on: nothing to do
  if (hudDriving) scentOff("hud");  // switching scents: turn the old one off first

  if (!powered()) digitalWrite(KILL_PIN, HIGH);  // keep the splitter powered
  press(pair * 2, 1);                            // idle -> continuous
  mode[pair * 2] = M_CONT;
  hudDriving = true;
  hudPair = pair;
  lastReason = "hud";
  Serial.printf("[hud] %s ON - continuous (1 press)\n", scent.c_str());
  publishScentState();
}

void onScentCmd(const char* payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) { scentError("bad_json"); return; }
  const char* sc = doc["selected_scent"] | "none";
  int pct = doc["scent_intensity_pct"] | 0;
  hudLastCmd = millis();
  applyScent(String(sc), pct);
}

void handle(String c) {
  c.trim();
  c.toLowerCase();
  if (!c.length()) return;

  if (c == "?" || c == "help") { help(); return; }
  if (c == "s") { status(); return; }
  if (c == "net") { netInfo(); return; }
  if (c == "scan") { scanWifi(); return; }
  if (c == "x") { allOff(); reply("ALL OFF"); status(); return; }
  if (c == "k1") {
    if (!powered()) for (int i = 0; i < N; i++) mode[i] = M_OFF;  // modules boot idle
    digitalWrite(KILL_PIN, HIGH); reply("POWER ON -> modules idle (red)"); status(); return;
  }
  if (c == "k0") {
    digitalWrite(KILL_PIN, LOW);
    for (int i = 0; i < N; i++) mode[i] = M_OFF;
    reply("POWER OFF -> all modules reset"); status(); return;
  }

  char cmd = c[0];
  if (cmd == 'p' || cmd == 'h' || cmd == 'l' || cmd == 'c' || cmd == 'i' || cmd == 'o') {
    int sp = c.indexOf(' ');
    int pin = c.substring(1, sp < 0 ? c.length() : sp).toInt();
    int i = idxOf(pin);
    if (i < 0) { reply("Not a button pin (25 26 27 4 32 33)"); return; }

    if (cmd == 'p') {
      int n = sp < 0 ? 1 : constrain(c.substring(sp + 1).toInt(), 1, 5);
      if (!powered()) reply("warning: power is OFF, module won't react (send k1)");
      press(i, n);
      reply("%s: %d press(es) -> %s", BTN_NAMES[i], n, MODE_NAMES[mode[i]]);
      status();
    } else if (cmd == 'c' || cmd == 'i' || cmd == 'o') {
      if (!powered()) { reply("power is OFF, send k1 first"); return; }
      Mode target = cmd == 'c' ? M_CONT : cmd == 'i' ? M_INT : M_OFF;
      int n = (target - mode[i] + 3) % 3;
      if (n) press(i, n);
      reply("%s -> %s (%d press%s)", BTN_NAMES[i], MODE_NAMES[mode[i]], n, n == 1 ? "" : "es");
      status();
    } else if (cmd == 'h') {
      if (heldPin >= 0) digitalWrite(heldPin, LOW);
      digitalWrite(pin, HIGH);
      heldPin = pin;
      heldAt = millis();
      reply("%s HELD (auto-release in 5 s)", BTN_NAMES[i]);
    } else {
      digitalWrite(pin, LOW);
      if (heldPin == pin) heldPin = -1;
      reply("%s released", BTN_NAMES[i]);
    }
    return;
  }
  reply("Unknown command '%s', send ?", c.c_str());
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  if (strcmp(topic, TOPIC_SCENT_CMD) == 0) { onScentCmd((const char*)payload, len); return; }
  String c;
  c.reserve(len);
  for (unsigned int i = 0; i < len; i++) c += (char)payload[i];
  Serial.printf("[mqtt] cmd: %s\n", c.c_str());
  handle(c);
}

void netLoop(unsigned long now) {
  static unsigned long lastTry = 0;
  static bool wasConnected = false;
  static bool wifiReported = false;

  bool wifiUp = WiFi.status() == WL_CONNECTED;
  if (wifiUp && !wifiReported) {
    Serial.printf("[net] Wi-Fi up, ESP32 IP %s\n", WiFi.localIP().toString().c_str());
  }
  wifiReported = wifiUp;

  bool up = mqtt.connected();
  if (wasConnected && !up) {
    if (hudDriving) scentOff("mqtt_lost");  // press it off (Q1 doesn't fully cut power)
    allOff();  // fail-safe: nobody can turn us off, so turn off now
    Serial.println("[net] MQTT lost - ALL OFF");
  }
  wasConnected = up;

  if (up) { mqtt.loop(); return; }
  if (now - lastTry < NET_RETRY_MS) return;
  lastTry = now;

  if (!wifiUp) {
    static int wifiWaits = 0;
    if (wifiWaits++ % 10 == 0)
      Serial.printf("[net] waiting for Wi-Fi '%s': %s (reason %u). Type 'scan' to see networks.\n",
                    WIFI_SSID, wifiReasonText(lastWifiReason), lastWifiReason);
    return;
  }

  char id[32];
  snprintf(id, sizeof(id), "xrpod-test-%06llX",
           (unsigned long long)(ESP.getEfuseMac() & 0xFFFFFF));
  static int fails = 0;
  if (mqtt.connect(id, MQTT_USER, MQTT_PASSWORD, TOPIC_SCENT_NODE, 1, true, "offline")) {
    fails = 0;
    mqtt.subscribe(TOPIC_CMD, 1);
    mqtt.subscribe(TOPIC_SCENT_CMD, 1);
    mqtt.publish(TOPIC_SCENT_NODE, "online", true);
    mqtt.publish(TOPIC_STATUS, "online", true);
    publishScentState();
    Serial.printf("[net] MQTT connected to %s:%d\n", MQTT_HOST, (int)MQTT_PORT);
    reply("XRPod GPIO test online - all OFF. Send ? for help");
  } else {
    // print the first failure, then only every ~60 s so it doesn't flood the terminal
    if (fails++ % 20 == 0)
      Serial.printf("[net] no MQTT broker at %s (rc=%d) - serial still works, retrying quietly\n",
                    MQTT_HOST, mqtt.state());
  }
}

void setup() {
  pinMode(KILL_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  for (int i = 0; i < N; i++) pinMode(BTN_PINS[i], OUTPUT);
  allOff();  // fail-safe: everything off at boot

  Serial.begin(115200);
  delay(500);
  Serial.println("\nXRPod scent carrier GPIO test (serial + MQTT) - all OFF");
  help();

  WiFi.onEvent([](WiFiEvent_t, WiFiEventInfo_t info) {
    lastWifiReason = info.wifi_sta_disconnected.reason;
  }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  WiFi.mode(WIFI_STA);
  // The Pi 5 hotspot (Broadcom chip) never answers the ESP32's 802.11n join ("auth expired",
  // reason 2), even at -50 dBm. Joining as 802.11b/g works. Must come after WiFi.mode().
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G);
  WiFi.setMinSecurity(WIFI_AUTH_WPA_PSK);  // also accept WPA/WPA2 mixed hotspots
  WiFi.setAutoReconnect(true);
  scanWifi();  // boot-time scan: shows whether the Pi's hotspot is visible, then starts connecting
  WiFi.setSleep(false);                  // modem power-save off: Pi hotspot drops sleepy clients during auth
  WiFi.setTxPower(WIFI_POWER_19_5dBm);   // full power; 8.5 dBm gave "auth expired" (reason 2)
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(15);
  mqtt.setBufferSize(512);  // status table is ~290 bytes; default 256 drops it silently
}

void loop() {
  unsigned long now = millis();
  netLoop(now);

  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handle(line); line = ""; }
    else line += ch;
  }

  // HUD fail-safe: the Pi resends every 5 s; silence for 15 s means it's gone
  // millis() fresh: `now` was taken before netLoop() ran the command callback,
  // so now - hudLastCmd would wrap around and trip the timeout instantly
  if (hudDriving && millis() - hudLastCmd > HUD_TIMEOUT_MS) {
    scentOff("timeout");
    Serial.println("[hud] no command from the Pi for 15 s - ALL OFF");
    publishScentState();
  }
  static unsigned long lastState = 0;
  if (now - lastState > STATE_EVERY_MS) { lastState = now; publishScentState(); }

  if (heldPin >= 0 && now - heldAt > HOLD_MAX_MS) {
    digitalWrite(heldPin, LOW);
    reply("GPIO%d auto-released", heldPin);
    heldPin = -1;
  }

  // LED: solid = MQTT connected, blink = offline
  digitalWrite(LED_PIN, mqtt.connected() ? HIGH : ((now / 500) % 2));
}