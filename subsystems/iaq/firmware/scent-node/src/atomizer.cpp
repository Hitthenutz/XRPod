#include "atomizer.h"

#include <Arduino.h>

#include "config.h"

// The pinned espressif32 platform ships Arduino core 2.x (channel-based LEDC).
#if ESP_ARDUINO_VERSION_MAJOR >= 3
#error "atomizer.cpp uses the Arduino-ESP32 2.x LEDC API (ledcSetup/ledcAttachPin)"
#endif

namespace {

// ---------STATE---------
const int GATE_PINS[ATOMIZER_COUNT] = {ATOMIZER_PIN_0, ATOMIZER_PIN_1};

int active = -1;
int duty = 0;
uint32_t startMs = 0;
uint32_t offAtMs = 0;
bool powered[ATOMIZER_COUNT] = {false, false};

// millis() wraps after ~49 days; compare by difference.
bool reached(uint32_t now, uint32_t t) { return (int32_t)(now - t) >= 0; }

// ---------HARDWARE (the only code that knows ATOMIZER_TYPE)---------
// power(), serviceButton() and minOnMs() per type.
#if ATOMIZER_TYPE == AN6_MOTOR

// LEDC channel i drives atomizer i's gate; full duty would put the whole
// 5 V supply across a ~3.7 V motor.
const uint32_t MOTOR_DUTY =
    (uint32_t)(MOTOR_VOLTS / SUPPLY_VOLTS * ((1u << MOTOR_PWM_BITS) - 1) + 0.5);

void setupPins() {
  for (int i = 0; i < ATOMIZER_COUNT; i++) {
    if (GATE_PINS[i] < 0) continue;
    ledcSetup(i, MOTOR_PWM_HZ, MOTOR_PWM_BITS);
    ledcAttachPin(GATE_PINS[i], i);
    ledcWrite(i, 0);
  }
}

void power(int i, bool on, uint32_t) {
  if (GATE_PINS[i] < 0) return;
  ledcWrite(i, on ? MOTOR_DUTY : 0);
  powered[i] = on;
}

void serviceButton(uint32_t) {}  // the motor has no button

uint32_t minOnMs() { return 0; }

#else  // MIST_MODULE

const int PRESS_PINS[ATOMIZER_COUNT] = {PRESS_PIN_0, PRESS_PIN_1};
bool pressPending = false;
bool pressing = false;
uint32_t pressAtMs = 0;
uint32_t releaseAtMs = 0;

void releaseButtons() {
  for (int i = 0; i < ATOMIZER_COUNT; i++) {
    if (PRESS_PINS[i] >= 0) digitalWrite(PRESS_PINS[i], LOW);
  }
  pressPending = pressing = false;
}

void setupPins() {
  for (int i = 0; i < ATOMIZER_COUNT; i++) {
    if (GATE_PINS[i] >= 0) {
      digitalWrite(GATE_PINS[i], LOW);
      pinMode(GATE_PINS[i], OUTPUT);
    }
    if (ATOMIZER_NEEDS_PRESS && PRESS_PINS[i] >= 0) {
      digitalWrite(PRESS_PINS[i], LOW);
      pinMode(PRESS_PINS[i], OUTPUT);
    }
  }
}

void power(int i, bool on, uint32_t now) {
  if (GATE_PINS[i] < 0) return;
  digitalWrite(GATE_PINS[i], on ? HIGH : LOW);
  powered[i] = on;
  releaseButtons();
  // The module powers up idle; "press" its button once it has settled.
  if (on && ATOMIZER_NEEDS_PRESS && PRESS_PINS[i] >= 0) {
    pressPending = true;
    pressAtMs = now + POWER_SETTLE_MS;
  }
}

// A pulse must last long enough for the press to finish, or low duties
// would never mist.
uint32_t minOnMs() { return ATOMIZER_NEEDS_PRESS ? POWER_SETTLE_MS + PRESS_MS : 0; }

void serviceButton(uint32_t now) {
  if (active < 0 || PRESS_PINS[active] < 0) return;
  if (pressPending && reached(now, pressAtMs)) {
    digitalWrite(PRESS_PINS[active], HIGH);
    pressPending = false;
    pressing = true;
    releaseAtMs = now + PRESS_MS;
  }
  if (pressing && reached(now, releaseAtMs)) {
    digitalWrite(PRESS_PINS[active], LOW);
    pressing = false;
  }
}

#endif

}  // namespace

// ---------PUBLIC API---------
void atomizerBegin() {
  setupPins();
  atomizerOff();
}

void atomizerOff() {
  for (int i = 0; i < ATOMIZER_COUNT; i++) power(i, false, 0);
  active = -1;
  duty = 0;
}

bool atomizerStart(int index, int dutyPct, uint32_t onS, uint32_t nowMs) {
  if (index == -1 || dutyPct == 0) {
    atomizerOff();
    return true;
  }
  if (index < 0 || index >= ATOMIZER_COUNT || GATE_PINS[index] < 0) return false;
  if (dutyPct < 0 || dutyPct > 100 || onS == 0) return false;
  if (onS > MAX_ON_S) onS = MAX_ON_S;

  // A repeat of the running command only extends it, so the hub's refresh
  // doesn't restart the duty cycle.
  if (index != active) {
    atomizerOff();  // break before make
    active = index;
    startMs = nowMs;
  }
  duty = dutyPct;
  offAtMs = nowMs + onS * 1000u;
  atomizerService(nowMs);
  return true;
}

void atomizerService(uint32_t nowMs) {
  if (active < 0) return;
  if (reached(nowMs, offAtMs)) {
    atomizerOff();
    return;
  }
  uint32_t phase = (nowMs - startMs) % PULSE_PERIOD_MS;
  uint32_t onMs = (uint32_t)duty * PULSE_PERIOD_MS / 100;
  if (onMs < minOnMs()) onMs = minOnMs();
  bool want = phase < onMs;
  if (want != powered[active]) power(active, want, nowMs);
  serviceButton(nowMs);
}

int atomizerActive() { return active; }
int atomizerDuty() { return duty; }
bool atomizerPowered(int index) {
  return index >= 0 && index < ATOMIZER_COUNT && powered[index];
}
