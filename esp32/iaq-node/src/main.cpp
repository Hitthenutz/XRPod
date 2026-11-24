// XRPod IAQ node (ESP32 WROOM-32): the BME688 on its own board.
//
//   BME688 --I2C--> this node --xrpod/iaq/reading--> Pi (pi/scent.py) --> HUD
//                             <--xrpod/scent/state--  scent node (which scent is on)
//
// Every 3 s it reads temperature, humidity, pressure and gas resistance,
// prints the reading over USB (115200 baud) and, once on the Pi's Wi-Fi,
// sends it to the Pi. It only reports: it has no outputs, so there's nothing
// to turn off if the Pi goes away.
//
// Without include/secrets.h it runs offline and only prints, which is enough
// to check the wiring. At start-up it lists every I2C device it can see, so a
// wiring mistake shows straight away.
//
// Logic that doesn't need the hardware lives in lib/iaq_core (unit-tested
// on a PC with `pio test -e native`).

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>

#include <IaqMessages.h>
#include <ScentDetector.h>

#include "IaqSensor.h"
#include "config.h"

// The Wi-Fi and MQTT login: this node's own include/secrets.h, or else the
// scent node's (same Pi, same login), so a laptop that already flashes the
// scent node needs nothing extra.
#if __has_include("secrets.h")
#include "secrets.h"
#define HAVE_SECRETS 1
#elif __has_include("../../scent-node/include/secrets.h")
#include "../../scent-node/include/secrets.h"
#define HAVE_SECRETS 1
#else
#include "secrets.example.h"
#define HAVE_SECRETS 0
#endif

#ifndef MQTT_USER
#define MQTT_USER nullptr
#endif
#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD nullptr
#endif

namespace {

IaqSensor iaq;
xrpod::ScentDetector detector;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

char clientId[32];
char activeScent[24] = "none";  // from the scent node; "none" until it says otherwise
char jsonBuf[320];
uint32_t lastWifiTryMs = 0;
uint32_t lastMqttTryMs = 0;
bool wasConnected = false;

// Lists every device answering on the I2C bus, e.g. "0x77", so you can see
// straight away whether the BME688 is wired up (and at which address).
void scanI2c() {
  Serial.printf("[i2c] scanning SDA=GPIO%u SCL=GPIO%u ...\n", cfg::kI2cSda, cfg::kI2cScl);
  uint8_t found = 0;
  for (uint8_t a = 1; a < 127; ++a) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("[i2c]   device at 0x%02X%s\n", a, (a == 0x76 || a == 0x77) ? "  <- BME688?" : "");
      ++found;
    }
  }
  if (found == 0) {
    Serial.println("[i2c]   nothing found. Check: 3V3 and GND connected, SDA on GPIO21, SCL on GPIO22,");
    Serial.println("[i2c]   and that the sensor's pins really touch (solder or press them in firmly).");
  }
}

void onMessage(char *topic, byte *payload, unsigned int len) {
  if (strcmp(topic, cfg::kTopicScentState) != 0) return;
  char scent[sizeof(activeScent)];
  if (xrpod::parseActiveScent(reinterpret_cast<const char *>(payload), len, scent, sizeof(scent))) {
    if (strcmp(scent, activeScent) != 0) Serial.printf("[iaq] scent node says: %s\n", scent);
    strncpy(activeScent, scent, sizeof(activeScent) - 1);
    activeScent[sizeof(activeScent) - 1] = '\0';
  }
}

// Wi-Fi and MQTT, never blocking for long: retries on a timer.
void keepConnected(uint32_t now) {
  if (!HAVE_SECRETS) return;
  if (WiFi.status() != WL_CONNECTED) {
    if (lastWifiTryMs == 0 || now - lastWifiTryMs >= cfg::kWifiRetryMs) {
      lastWifiTryMs = now;
      Serial.printf("[net] joining Wi-Fi '%s' ...\n", WIFI_SSID);
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;
  }
  if (mqtt.connected()) return;
  if (lastMqttTryMs != 0 && now - lastMqttTryMs < cfg::kMqttRetryMs) return;
  lastMqttTryMs = now;
  Serial.printf("[net] Wi-Fi ok (%s), MQTT %s:%d ... ", WiFi.localIP().toString().c_str(), MQTT_HOST,
                (int)MQTT_PORT);
  if (mqtt.connect(clientId, MQTT_USER, MQTT_PASSWORD, cfg::kTopicNode, 1, true, "offline")) {
    Serial.println("connected");
    mqtt.publish(cfg::kTopicNode, "online", true);
    mqtt.subscribe(cfg::kTopicScentState);
  } else {
    Serial.printf("failed (rc=%d; 5 = wrong MQTT login)\n", mqtt.state());
  }
}

}  // namespace

void setup() {
  pinMode(cfg::kStatusLed, OUTPUT);
  Serial.begin(115200);
  delay(300);
  Serial.println("\nXRPod IAQ node (BME688) booting");

  Wire.begin(cfg::kI2cSda, cfg::kI2cScl);
  scanI2c();
  if (iaq.begin(cfg::kBmeAddresses, sizeof(cfg::kBmeAddresses), cfg::kSensorPeriodMs, cfg::kGasHeaterC,
                cfg::kGasHeaterMs)) {
    Serial.printf("[iaq] BME688 found at 0x%02X - a reading every %lu s\n", iaq.address(),
                  (unsigned long)(cfg::kSensorPeriodMs / 1000));
  } else {
    Serial.println("[iaq] BME688 not found - check the wiring; trying again every 10 s");
  }

  if (HAVE_SECRETS) {
    snprintf(clientId, sizeof(clientId), "%s%06lx", cfg::kClientIdPrefix,
             (unsigned long)(ESP.getEfuseMac() & 0xFFFFFF));
    WiFi.mode(WIFI_STA);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(onMessage);
    mqtt.setBufferSize(512);  // readings and scent states are bigger than the 256-byte default
  } else {
    Serial.println("[net] no include/secrets.h - offline: readings are only printed here");
  }
}

void loop() {
  uint32_t now = millis();
  keepConnected(now);
  if (mqtt.connected()) mqtt.loop();

  bool connected = mqtt.connected();
  if (wasConnected && !connected) {
    Serial.println("[net] lost the Pi; reconnecting");
    // Can't trust which scent is on until the scent node says so again.
    strncpy(activeScent, "none", sizeof(activeScent));
  }
  wasConnected = connected;

  xrpod::IaqReading reading;
  if (iaq.poll(now, reading)) {
    detector.update(reading.gasOhms, strcmp(activeScent, "none") != 0);
    if (xrpod::buildReadingJson(reading, detector, activeScent, jsonBuf, sizeof(jsonBuf)) > 0) {
      Serial.println(jsonBuf);
      if (connected) mqtt.publish(cfg::kTopicReading, jsonBuf);
    }
  }

  // Status LED: solid = sending to the Pi, slow blink = offline,
  // fast blink = no sensor.
  bool on = !iaq.present()  ? (now / 150) % 2
            : connected     ? true
                            : (now / 1000) % 2;
  digitalWrite(cfg::kStatusLed, on ? HIGH : LOW);
}
