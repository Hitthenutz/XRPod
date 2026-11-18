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
//
// The modules can't report their mode, so the ESP32 tracks it by counting presses
// (off -> continuous -> intermittent -> off). k0 resets every module to OFF.
// If the table ever disagrees with what you see, send k0 then k1 to resync.
//
// Fail-safe: everything OFF at boot and whenever MQTT drops.
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <stdarg.h>
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
int heldPin = -1;
unsigned long heldAt = 0;

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
  reply("k1/k0 = power on/off | p25 [n] = press n times | c25/i25/o25 = continuous/intermittent/off | h25/l25 = hold/release | x = all off | s = status");
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

void handle(String c) {
  c.trim();
  c.toLowerCase();
  if (!c.length()) return;

  if (c == "?" || c == "help") { help(); return; }
  if (c == "s") { status(); return; }
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
    allOff();  // fail-safe: nobody can turn us off, so turn off now
    Serial.println("[net] MQTT lost - ALL OFF");
  }
  wasConnected = up;

  if (up) { mqtt.loop(); return; }
  if (now - lastTry < NET_RETRY_MS) return;
  lastTry = now;

  if (!wifiUp) {
    static int wifiWaits = 0;
    if (wifiWaits++ % 20 == 0) Serial.printf("[net] waiting for Wi-Fi '%s'...\n", WIFI_SSID);
    return;
  }

  char id[32];
  snprintf(id, sizeof(id), "xrpod-test-%06llX",
           (unsigned long long)(ESP.getEfuseMac() & 0xFFFFFF));
  static int fails = 0;
  if (mqtt.connect(id, MQTT_USER, MQTT_PASSWORD, TOPIC_STATUS, 1, true, "offline")) {
    fails = 0;
    mqtt.subscribe(TOPIC_CMD, 1);
    mqtt.publish(TOPIC_STATUS, "online", true);
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

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(15);
}

void loop() {
  unsigned long now = millis();
  netLoop(now);

  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handle(line); line = ""; }
    else line += ch;
  }

  if (heldPin >= 0 && now - heldAt > HOLD_MAX_MS) {
    digitalWrite(heldPin, LOW);
    reply("GPIO%d auto-released", heldPin);
    heldPin = -1;
  }

  // LED: solid = MQTT connected, blink = offline
  digitalWrite(LED_PIN, mqtt.connected() ? HIGH : ((now / 500) % 2));
}