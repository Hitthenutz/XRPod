#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

// Fill these in before uploading, and never commit them.
const char* WIFI_NAME = "PUT_WIFI_NAME_HERE";
const char* WIFI_PASSWORD = "PUT_WIFI_PASSWORD_HERE";

const int FAN_PIN = 4;
const int TACH_PIN = 5;

WebServer server(80);
volatile unsigned long tachPulses = 0;
volatile unsigned long fellAtUs = 0;
volatile unsigned long countedAtUs = 0;
int fanPct = 0;
int fanRpm = 0;
unsigned long lastRpmTime = 0;
unsigned long lastContactMs = 0;
// Fail-safe (docs/subsystems.md): if the Pi stops talking to us, fans off.
// The Pi checks in every ~2 s, so 30 s of silence means it's gone.
const unsigned long CONTACT_TIMEOUT_MS = 30000;

void IRAM_ATTR onTach() {
  unsigned long now = micros();
  if (digitalRead(TACH_PIN) == LOW) {
    fellAtUs = now;
  } else if (now - fellAtUs > 1000 && now - countedAtUs > 10000) {
    tachPulses++;
    countedAtUs = now;
  }
}

void setFan(int pct) {
  fanPct = constrain(pct, 0, 100);
  ledcWrite(FAN_PIN, fanPct * 255 / 100);
}

void sendStatus() {
  lastContactMs = millis();
  String json = "{\"fan_pct\":" + String(fanPct) + ",\"fan_rpm\":" + String(fanRpm) + "}";
  server.send(200, "application/json", json);
}

void handleFan() {
  if (server.hasArg("pct")) setFan(server.arg("pct").toInt());
  sendStatus();
}

void setup() {
  Serial.begin(115200);
  ledcAttach(FAN_PIN, 25000, 8);
  setFan(0);
  pinMode(TACH_PIN, INPUT_PULLUP);
  attachInterrupt(TACH_PIN, onTach, CHANGE);

  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println();
  Serial.print("Connected! IP address: ");
  Serial.println(WiFi.localIP());

  MDNS.begin("xrpod-fan");
  server.on("/fan", handleFan);
  server.on("/status", sendStatus);
  server.begin();
}

void loop() {
  server.handleClient();
  if (fanPct > 0 && millis() - lastContactMs > CONTACT_TIMEOUT_MS) {
    Serial.println("No contact for 30 s: fans off");
    setFan(0);
  }
  if (millis() - lastRpmTime >= 1000) {
    noInterrupts();
    unsigned long pulses = tachPulses;
    tachPulses = 0;
    interrupts();
    fanRpm = pulses * 30;
    lastRpmTime = millis();
  }
}
