// XRPod scent / IAQ node: compile-time settings.
//
// Anything tagged ---------MISSING: ...--------- is a placeholder until the
// hardware is on the bench; each one has a row in subsystems/iaq/docs/DESIGN.md.
// Pins left at -1 are never driven, so an unfinished build can't switch
// anything on.
//
// Every value is wrapped in #ifndef so the host test (test/host) can
// override it with -D flags.
#pragma once

#include <stdint.h>

// ---------NODE---------
#ifndef NODE_ID
#define NODE_ID "scent1"  // MQTT topics are xrpod/scent/<NODE_ID>/...
#endif

// ---------ATOMIZER TYPE---------
// MIST_MODULE: Starry 5 V USB ultrasonic mist module (water + a few drops of
//   oil). A logic MOSFET switches its 5 V; some modules also need their
//   button "pressed" (optocoupler across the switch) after power-up.
// AN6_MOTOR: Airversa AN6 waterless diffuser (pure oil), battery
//   disconnected. A logic MOSFET + flyback diode drives its air pump motor
//   directly; LEDC PWM on the gate brings the 5 V supply down to an average
//   of about MOTOR_VOLTS.
#define MIST_MODULE 1
#define AN6_MOTOR 2
#ifndef ATOMIZER_TYPE
#define ATOMIZER_TYPE MIST_MODULE  // ---------MISSING: FINAL ATOMIZER CHOICE---------
#endif
#if ATOMIZER_TYPE != MIST_MODULE && ATOMIZER_TYPE != AN6_MOTOR
#error "ATOMIZER_TYPE must be MIST_MODULE or AN6_MOTOR"
#endif

// ---------ATOMIZER PINS---------
// ---------MISSING: ATOMIZER MOSFET GATE PINS---------
#ifndef ATOMIZER_PIN_0
#define ATOMIZER_PIN_0 -1
#endif
#ifndef ATOMIZER_PIN_1
#define ATOMIZER_PIN_1 -1
#endif

// ---------MIST MODULE BUTTON PRESS---------
// ---------MISSING: DOES THE MIST MODULE NEED A BUTTON PRESS (bench test)---------
#ifndef ATOMIZER_NEEDS_PRESS
#define ATOMIZER_NEEDS_PRESS 0
#endif
// ---------MISSING: OPTOCOUPLER PINS (mist module only)---------
#ifndef PRESS_PIN_0
#define PRESS_PIN_0 -1
#endif
#ifndef PRESS_PIN_1
#define PRESS_PIN_1 -1
#endif
#ifndef POWER_SETTLE_MS
#define POWER_SETTLE_MS 300  // wait after power-up before pressing
#endif
#ifndef PRESS_MS
#define PRESS_MS 150  // how long the "button" is held
#endif

// ---------AN6 MOTOR DRIVE---------
#ifndef SUPPLY_VOLTS
#define SUPPLY_VOLTS 5.0
#endif
#ifndef MOTOR_VOLTS
#define MOTOR_VOLTS 3.7  // ---------MISSING: AN6 MOTOR VOLTAGE (measure on bench)---------
#endif
#ifndef MOTOR_PWM_HZ
#define MOTOR_PWM_HZ 20000  // above hearing range
#endif
#ifndef MOTOR_PWM_BITS
#define MOTOR_PWM_BITS 10
#endif
static_assert(MOTOR_VOLTS > 0 && MOTOR_VOLTS <= SUPPLY_VOLTS,
              "MOTOR_VOLTS must be between 0 and SUPPLY_VOLTS");

// ---------FAIL-SAFE LIMITS---------
#ifndef MAX_ON_S
#define MAX_ON_S 30  // longest any single command can run an atomizer
#endif
#ifndef PULSE_PERIOD_MS
#define PULSE_PERIOD_MS 10000  // duty % = share of each period the atomizer is on
#endif

// ---------BME688 SENSORS---------
// Scan sensor: AI-Studio scent classes. IAQ sensor: Bosch IAQ index, eCO2,
// bVOC, temperature, humidity, pressure. Mount the IAQ sensor away from the
// atomizers or every puff reads as bad air.
// ---------MISSING: BME688 I2C ADDRESSES (SDO wiring)---------
#ifndef SCAN_SENSOR_ADDR
#define SCAN_SENSOR_ADDR 0x76  // SDO to GND
#endif
#ifndef IAQ_SENSOR_ADDR
#define IAQ_SENSOR_ADDR 0x77  // SDO to VDDIO
#endif
// ---------MISSING: I2C PINS (board defaults until wired)---------
#ifndef I2C_SDA_PIN
#define I2C_SDA_PIN 21
#endif
#ifndef I2C_SCL_PIN
#define I2C_SCL_PIN 22
#endif
// ---------MISSING: IAQ SENSOR TEMPERATURE OFFSET (self-heating, measure in pod)---------
#ifndef TEMP_OFFSET_C
#define TEMP_OFFSET_C 0.0f
#endif

// ---------MQTT---------
#ifndef TELEMETRY_MS
#define TELEMETRY_MS 3000
#endif
#ifndef RECONNECT_MS
#define RECONNECT_MS 5000
#endif
