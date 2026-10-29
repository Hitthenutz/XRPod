// XRPod scent / IAQ node (ESP32 WROOM-32)
//
// Pi (MQTT broker) --xrpod/scent/cmd--> this node --> 3 scents x 2 diffusers
//                  <--xrpod/scent/state, xrpod/iaq/reading-- BME688
//
// Logic lives in lib/scent_core (unit-tested on a PC); this file only wires
// hardware and network to it.

#include <Arduino.h>
#include <Wire.h>

#include <CommandParser.h>
#include <Messages.h>
#include <ScentController.h>
#include <ScentDetector.h>

#include "config.h"
#include "hw/GpioOutputPort.h"
#include "hw/IaqSensor.h"
#include "net/MqttLink.h"

#if __has_include("secrets.h")
#include "secrets.h"
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

GpioOutputPort outputs(cfg::kOutputsActiveLow);
xrpod::ScentController scent(outputs, {cfg::kScents, cfg::kNumScents, cfg::kDiffusersPerScent,
                                       cfg::kDutyWindowMs, cfg::kCommandTimeoutMs});
xrpod::ScentDetector detector;
IaqSensor iaq;
MqttLink mqttLink;

// MQTT callbacks run inside mqttLink.loop(); just stash the latest command.
bool commandPending = false;
xrpod::ScentCommand pendingCommand = xrpod::kScentOff;
xrpod::ParseResult lastParseError = xrpod::ParseResult::Ok;
bool parseErrorPending = false;

char jsonBuf[384];

void onMessage(const char *topic, const uint8_t *payload, unsigned int len) {
  if (strcmp(topic, cfg::kTopicCmd) != 0) return;
  xrpod::ScentCommand cmd;
  xrpod::ParseResult r = xrpod::parseScentCommand(reinterpret_cast<const char *>(payload), len,
                                                  cfg::kScents, cfg::kNumScents, cmd);
  if (r == xrpod::ParseResult::Ok || r == xrpod::ParseResult::UnknownScent) {
    pendingCommand = cmd;
    commandPending = true;
  }
  if (r != xrpod::ParseResult::Ok) {
    lastParseError = r;
    parseErrorPending = true;
  }
}

void publishState(uint32_t nowMs) {
  if (xrpod::buildStateJson(scent, nowMs / 1000, jsonBuf, sizeof(jsonBuf)) > 0) {
    mqttLink.publish(cfg::kTopicState, jsonBuf, true);
  }
}

void publishError(const char *what) {
  snprintf(jsonBuf, sizeof(jsonBuf), "{\"error\":\"%s\"}", what);
  mqttLink.publish(cfg::kTopicError, jsonBuf);
  Serial.printf("[scent] error: %s\n", what);
}

}  // namespace

void setup() {
  // Outputs off before anything else.
  for (uint8_t s = 0; s < cfg::kNumScents; ++s) {
    for (uint8_t d = 0; d < cfg::kDiffusersPerScent; ++d) outputs.initOff(cfg::kScents[s].pins[d]);
  }
  pinMode(cfg::kStatusLed, OUTPUT);

  Serial.begin(115200);
  delay(200);
  Serial.println("\nXRPod scent node booting");

  if (!scent.begin()) Serial.println("[scent] BAD CONFIG - outputs locked off");

  Wire.begin(cfg::kI2cSda, cfg::kI2cScl);
  if (!iaq.begin(cfg::kBmeAddress, cfg::kSensorPeriodMs, cfg::kGasHeaterC, cfg::kGasHeaterMs)) {
    Serial.println("[iaq] BME688 not found - check wiring/address, will retry");
  }

  if (HAVE_SECRETS) {
    MqttLink::Settings s = {WIFI_SSID,    WIFI_PASSWORD,      MQTT_HOST,
                            MQTT_PORT,    MQTT_USER,          MQTT_PASSWORD,
                            cfg::kClientIdPrefix, cfg::kTopicCmd, cfg::kTopicNode,
                            cfg::kWifiRetryMs,    cfg::kMqttRetryMs};
    mqttLink.begin(s, onMessage);
  } else {
    Serial.println("No secrets.h - offline mode (outputs stay off)");
  }
}

void loop() {
  static uint32_t lastStatePubMs = 0;
  static uint32_t lastChange = 0;
  static bool wasConnected = false;
  uint32_t now = millis();

  mqttLink.loop(now);
  bool connected = mqttLink.connected();

  // Fail safe: no broker means no one can turn us off, so turn off now.
  if (wasConnected && !connected) {
    scent.off(xrpod::Reason::MqttLost);
    Serial.println("[scent] MQTT lost - all diffusers off");
  }
  wasConnected = connected;

  if (commandPending) {
    commandPending = false;
    scent.apply(pendingCommand, now);
  }
  if (parseErrorPending) {
    parseErrorPending = false;
    publishError(xrpod::parseResultName(lastParseError));
  }
  scent.tick(now);

  xrpod::IaqReading reading;
  if (iaq.poll(now, reading)) {
    detector.update(reading.gasOhms, scent.activeSlot() != xrpod::kNoScent);
    if (xrpod::buildReadingJson(reading, detector, scent.activeName(), jsonBuf,
                                sizeof(jsonBuf)) > 0) {
      mqttLink.publish(cfg::kTopicReading, jsonBuf);
      Serial.println(jsonBuf);
    }
  }

  bool justConnected = mqttLink.takeJustConnected();
  if (justConnected || scent.changeCount() != lastChange ||
      now - lastStatePubMs >= cfg::kStatePublishMs) {
    lastChange = scent.changeCount();
    lastStatePubMs = now;
    publishState(now);
  }

  // Status LED: solid = connected, slow blink = offline.
  digitalWrite(cfg::kStatusLed, connected ? HIGH : ((now / 1000) % 2 ? HIGH : LOW));
}
