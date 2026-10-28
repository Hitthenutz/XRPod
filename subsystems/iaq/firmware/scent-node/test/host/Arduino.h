// Fake Arduino-ESP32 (core 2.x) API for the host atomizer test. Records pin
// levels and LEDC duty so the test can see what the hardware would do.
#pragma once

#include <stdint.h>

#define ESP_ARDUINO_VERSION_MAJOR 2
#define LOW 0
#define HIGH 1
#define OUTPUT 1

namespace fake {
constexpr int PINS = 40;
constexpr int CHANNELS = 16;
inline int level[PINS];
inline int mode[PINS];
inline int writes[PINS];  // digitalWrite calls per pin
inline int channelPin[CHANNELS];
inline uint32_t channelHz[CHANNELS];
inline uint32_t channelDuty[CHANNELS];

inline void reset() {
  for (int i = 0; i < PINS; i++) level[i] = mode[i] = writes[i] = 0;
  for (int c = 0; c < CHANNELS; c++) {
    channelPin[c] = -1;
    channelHz[c] = channelDuty[c] = 0;
  }
}
}  // namespace fake

inline void pinMode(int pin, int m) { fake::mode[pin] = m; }
inline void digitalWrite(int pin, int v) {
  fake::level[pin] = v;
  fake::writes[pin]++;
}
inline void ledcSetup(int ch, uint32_t hz, int) { fake::channelHz[ch] = hz; }
inline void ledcAttachPin(int pin, int ch) { fake::channelPin[ch] = pin; }
inline void ledcWrite(int ch, uint32_t duty) { fake::channelDuty[ch] = duty; }
