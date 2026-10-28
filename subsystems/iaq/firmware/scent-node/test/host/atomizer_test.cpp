// Host test for src/atomizer.cpp. Built three ways by run.sh: the mist
// module with a button press, the AN6 motor, and an unwired board (pins
// left at -1). See subsystems/iaq/README.md.
#include <stdio.h>

#include "Arduino.h"
#include "atomizer.h"
#include "config.h"

static int failures = 0;
#define CHECK(cond)                                              \
  do {                                                           \
    if (!(cond)) {                                               \
      printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);     \
      failures++;                                                \
    }                                                            \
  } while (0)

static const int GATES[ATOMIZER_COUNT] = {ATOMIZER_PIN_0, ATOMIZER_PIN_1};

// ---------WHAT THE HARDWARE SEES---------
static bool hwOn(int i) {
  if (GATES[i] < 0) return false;
#if ATOMIZER_TYPE == AN6_MOTOR
  return fake::channelPin[i] == GATES[i] && fake::channelDuty[i] > 0;
#else
  return fake::level[GATES[i]] == HIGH;
#endif
}

static int hwOnCount() {
  int n = 0;
  for (int i = 0; i < ATOMIZER_COUNT; i++) n += hwOn(i);
  return n;
}

static void fresh() {
  fake::reset();
  atomizerBegin();
}

// ---------TESTS FOR EVERY TYPE---------
#if ATOMIZER_PIN_0 >= 0 && ATOMIZER_PIN_1 >= 0

static void testBootsOff() {
  fresh();
  CHECK(hwOnCount() == 0);
  CHECK(atomizerActive() == -1);
}

static void testOneAtATime() {
  fresh();
  CHECK(atomizerStart(0, 100, 10, 0));
  CHECK(hwOn(0) && !hwOn(1));
  CHECK(atomizerStart(1, 100, 10, 100));
  CHECK(!hwOn(0) && hwOn(1));
  CHECK(atomizerActive() == 1);
  for (uint32_t t = 100; t < 12000; t += 50) {
    atomizerService(t);
    CHECK(hwOnCount() <= 1);
  }
}

static void testOffCommands() {
  fresh();
  atomizerStart(0, 100, 10, 0);
  CHECK(atomizerStart(-1, 0, 0, 10));
  CHECK(hwOnCount() == 0);
  atomizerStart(1, 100, 10, 20);
  CHECK(atomizerStart(1, 0, 10, 30));  // duty 0 = off
  CHECK(hwOnCount() == 0 && atomizerActive() == -1);
}

static void testRejectsBadRequests() {
  fresh();
  atomizerStart(0, 50, 10, 0);
  CHECK(!atomizerStart(2, 50, 10, 1));
  CHECK(!atomizerStart(-2, 50, 10, 1));
  CHECK(!atomizerStart(1, 101, 10, 1));
  CHECK(!atomizerStart(1, -5, 10, 1));
  CHECK(!atomizerStart(1, 50, 0, 1));
  CHECK(atomizerActive() == 0 && atomizerDuty() == 50);  // unchanged
}

static void testTimesOutAndCapsAtMaxOn() {
  fresh();
  atomizerStart(0, 100, 5, 0);
  atomizerService(4999);
  CHECK(hwOn(0));
  atomizerService(5000);
  CHECK(hwOnCount() == 0 && atomizerActive() == -1);

  atomizerStart(0, 100, 100000, 0);  // asks for far longer than allowed
  atomizerService(MAX_ON_S * 1000u - 1);
  CHECK(hwOn(0));
  atomizerService(MAX_ON_S * 1000u);
  CHECK(hwOnCount() == 0);
}

static void testDutyCycle() {
  fresh();
  atomizerStart(0, 30, 30, 0);  // on 3 s of every 10 s
  const uint32_t onMs = PULSE_PERIOD_MS * 30 / 100;
  atomizerService(onMs - 1);
  CHECK(hwOn(0));
  atomizerService(onMs);
  CHECK(!hwOn(0));
  atomizerService(PULSE_PERIOD_MS - 1);
  CHECK(!hwOn(0));
  atomizerService(PULSE_PERIOD_MS);
  CHECK(hwOn(0));
}

static void testRefreshKeepsPhase() {
  fresh();
  atomizerStart(0, 30, 10, 0);
  atomizerService(5000);
  CHECK(!hwOn(0));
  CHECK(atomizerStart(0, 30, 10, 5000));  // hub re-sends the same command
  CHECK(!hwOn(0));                       // still in the off part
  atomizerService(14000);                // extended past the first 10 s
  CHECK(atomizerActive() == 0);
}

static void testMillisWrap() {
  fresh();
  const uint32_t nearWrap = 0xFFFFFFFFu - 1000;
  atomizerStart(0, 100, 5, nearWrap);
  atomizerService(nearWrap + 4000);  // wraps past 0
  CHECK(hwOn(0));
  atomizerService(nearWrap + 5000);
  CHECK(hwOnCount() == 0);
}

#endif

// ---------TYPE-SPECIFIC TESTS---------
#if ATOMIZER_TYPE == AN6_MOTOR && ATOMIZER_PIN_0 >= 0

static void testMotorAverageVoltage() {
  fresh();
  CHECK(fake::channelHz[0] == MOTOR_PWM_HZ);
  CHECK(fake::channelPin[0] == ATOMIZER_PIN_0);
  atomizerStart(0, 100, 10, 0);
  const double maxDuty = (1u << MOTOR_PWM_BITS) - 1;
  const double volts = fake::channelDuty[0] / maxDuty * SUPPLY_VOLTS;
  CHECK(volts > MOTOR_VOLTS - 0.01 && volts < MOTOR_VOLTS + 0.01);
}

static void testMotorNeverPresses() {
  fresh();
  atomizerStart(0, 100, 10, 0);
  for (uint32_t t = 0; t < 2000; t += 10) atomizerService(t);
  for (int pin = 0; pin < fake::PINS; pin++) CHECK(fake::writes[pin] == 0);
}

#endif

#if ATOMIZER_TYPE == MIST_MODULE && ATOMIZER_NEEDS_PRESS && ATOMIZER_PIN_0 >= 0

static void testMistPressesAfterPowerUp() {
  fresh();
  atomizerStart(0, 100, 10, 0);
  CHECK(hwOn(0));
  atomizerService(POWER_SETTLE_MS - 1);
  CHECK(fake::level[PRESS_PIN_0] == LOW);
  atomizerService(POWER_SETTLE_MS);
  CHECK(fake::level[PRESS_PIN_0] == HIGH);
  atomizerService(POWER_SETTLE_MS + PRESS_MS);
  CHECK(fake::level[PRESS_PIN_0] == LOW);
  CHECK(fake::level[PRESS_PIN_1] == LOW);
}

static void testMistPressesEachPulse() {
  fresh();
  atomizerStart(0, 50, 30, 0);
  for (uint32_t t = 0; t <= PULSE_PERIOD_MS + POWER_SETTLE_MS; t += 10) atomizerService(t);
  CHECK(fake::level[PRESS_PIN_0] == HIGH);  // second power-up gets pressed too
}

static void testMistLowDutyStillPresses() {
  fresh();
  atomizerStart(0, 1, 30, 0);  // 1 % = 100 ms, shorter than settle + press
  for (uint32_t t = 0; t <= POWER_SETTLE_MS; t += 10) atomizerService(t);
  CHECK(hwOn(0) && fake::level[PRESS_PIN_0] == HIGH);
  for (uint32_t t = POWER_SETTLE_MS; t <= POWER_SETTLE_MS + PRESS_MS; t += 10) atomizerService(t);
  CHECK(fake::level[PRESS_PIN_0] == LOW);  // press completed, then released
  atomizerService(POWER_SETTLE_MS + PRESS_MS + 10);
  CHECK(!hwOn(0));  // and the pulse ends right after
}

static void testMistOffReleasesButton() {
  fresh();
  atomizerStart(0, 100, 10, 0);
  atomizerService(POWER_SETTLE_MS);
  CHECK(fake::level[PRESS_PIN_0] == HIGH);
  atomizerOff();
  CHECK(fake::level[PRESS_PIN_0] == LOW && hwOnCount() == 0);
}

#endif

#if ATOMIZER_PIN_0 < 0 && ATOMIZER_PIN_1 < 0

static void testUnwiredBoardDrivesNothing() {
  fresh();
  CHECK(!atomizerStart(0, 100, 10, 0));
  CHECK(!atomizerStart(1, 100, 10, 0));
  CHECK(hwOnCount() == 0);
  for (int pin = 0; pin < fake::PINS; pin++) CHECK(fake::writes[pin] == 0);
  for (int c = 0; c < fake::CHANNELS; c++) CHECK(fake::channelPin[c] == -1);
}

#endif

int main() {
#if ATOMIZER_PIN_0 >= 0 && ATOMIZER_PIN_1 >= 0
  testBootsOff();
  testOneAtATime();
  testOffCommands();
  testRejectsBadRequests();
  testTimesOutAndCapsAtMaxOn();
  testDutyCycle();
  testRefreshKeepsPhase();
  testMillisWrap();
#endif
#if ATOMIZER_TYPE == AN6_MOTOR && ATOMIZER_PIN_0 >= 0
  testMotorAverageVoltage();
  testMotorNeverPresses();
#endif
#if ATOMIZER_TYPE == MIST_MODULE && ATOMIZER_NEEDS_PRESS && ATOMIZER_PIN_0 >= 0
  testMistPressesAfterPowerUp();
  testMistPressesEachPulse();
  testMistLowDutyStillPresses();
  testMistOffReleasesButton();
#endif
#if ATOMIZER_PIN_0 < 0 && ATOMIZER_PIN_1 < 0
  testUnwiredBoardDrivesNothing();
#endif
  printf("%s\n", failures ? "FAILED" : "OK");
  return failures ? 1 : 0;
}
