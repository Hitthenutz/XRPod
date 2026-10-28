// XRPod atomizers: at most one on at a time, every run time-limited.
//
// Duty is time-proportioned over PULSE_PERIOD_MS (30 % = on for 3 s of every
// 10 s). Only power() and serviceButton() in atomizer.cpp know which
// ATOMIZER_TYPE is fitted; nothing else changes between the two.
#pragma once

#include <stdint.h>

constexpr int ATOMIZER_COUNT = 2;

// Call first thing in setup(): every output off.
void atomizerBegin();

// Run atomizer `index` at `dutyPct` (1-100) for `onS` seconds (capped at
// MAX_ON_S). Turns any other atomizer off first. index -1 or duty 0 means
// all off. Returns false, changing nothing, for an invalid request or an
// atomizer whose pin isn't set yet.
bool atomizerStart(int index, int dutyPct, uint32_t onS, uint32_t nowMs);

void atomizerOff();

// Call every loop(): runs the duty cycle, the button press and the timeout.
void atomizerService(uint32_t nowMs);

int atomizerActive();  // -1 when off
int atomizerDuty();    // 0 when off
bool atomizerPowered(int index);
