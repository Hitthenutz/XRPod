#include "BenchCommand.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

namespace xrpod {

namespace {

constexpr uint8_t kMaxTokens = 4;
constexpr size_t kMaxLine = 64;

bool equalsIgnoreCase(const char *a, const char *b) {
  if (a == nullptr || b == nullptr) return false;
  while (*a && *b) {
    if (tolower(static_cast<unsigned char>(*a)) != tolower(static_cast<unsigned char>(*b))) {
      return false;
    }
    ++a;
    ++b;
  }
  return *a == *b;
}

int8_t findSlot(const char *name, const ScentSlot *slots, uint8_t numSlots) {
  for (uint8_t i = 0; i < numSlots; ++i) {
    if (equalsIgnoreCase(slots[i].name, name)) return static_cast<int8_t>(i);
  }
  return kNoScent;
}

// Whole-token integer in [lo, hi]; false on junk like "60x" or "".
bool parseInt(const char *s, long lo, long hi, long &out) {
  if (s == nullptr || *s == '\0') return false;
  char *end = nullptr;
  long v = strtol(s, &end, 10);
  if (end == s || *end != '\0' || v < lo || v > hi) return false;
  out = v;
  return true;
}

BenchCommand make(BenchAction a) {
  BenchCommand c = {a, kNoScent, 0, 0, false};
  return c;
}

}  // namespace

BenchCommand parseBenchLine(const char *line, const ScentSlot *slots, uint8_t numSlots,
                            uint8_t diffusersPerSlot) {
  if (line == nullptr) return make(BenchAction::None);

  char buf[kMaxLine + 1];
  strncpy(buf, line, kMaxLine);
  buf[kMaxLine] = '\0';

  // Split on whitespace in place (no strtok: it keeps hidden global state).
  char *tok[kMaxTokens] = {};
  uint8_t n = 0;
  char *p = buf;
  while (*p != '\0') {
    while (isspace(static_cast<unsigned char>(*p))) *p++ = '\0';
    if (*p == '\0') break;
    if (n == kMaxTokens) return make(BenchAction::BadArgs);  // too many words
    tok[n++] = p;
    while (*p != '\0' && !isspace(static_cast<unsigned char>(*p))) ++p;
  }
  if (n == 0) return make(BenchAction::None);

  const char *cmd = tok[0];
  if (equalsIgnoreCase(cmd, "help") || equalsIgnoreCase(cmd, "?")) return make(BenchAction::Help);
  if (equalsIgnoreCase(cmd, "status")) return make(BenchAction::Status);
  if (equalsIgnoreCase(cmd, "off") || equalsIgnoreCase(cmd, "stop")) return make(BenchAction::Off);
  if (equalsIgnoreCase(cmd, "sensor")) return make(BenchAction::Sensor);
  if (equalsIgnoreCase(cmd, "net")) return make(BenchAction::Net);
  if (equalsIgnoreCase(cmd, "scan")) return make(BenchAction::Scan);

  if (equalsIgnoreCase(cmd, "log")) {
    if (n != 2) return make(BenchAction::BadArgs);
    BenchCommand c = make(BenchAction::Log);
    if (equalsIgnoreCase(tok[1], "on")) c.flag = true;
    else if (equalsIgnoreCase(tok[1], "off")) c.flag = false;
    else return make(BenchAction::BadArgs);
    return c;
  }

  if (equalsIgnoreCase(cmd, "scent")) {
    long pct = 0;
    if (n != 3 || !parseInt(tok[2], 0, 100, pct)) return make(BenchAction::BadArgs);
    if (equalsIgnoreCase(tok[1], "none") || pct == 0) return make(BenchAction::Off);
    int8_t slot = findSlot(tok[1], slots, numSlots);
    if (slot == kNoScent) return make(BenchAction::BadArgs);
    BenchCommand c = make(BenchAction::Scent);
    c.slot = slot;
    c.pct = static_cast<uint8_t>(pct);
    return c;
  }

  if (equalsIgnoreCase(cmd, "pin")) {
    long d = 0;
    if (n != 3 || !parseInt(tok[2], 1, diffusersPerSlot, d)) return make(BenchAction::BadArgs);
    int8_t slot = findSlot(tok[1], slots, numSlots);
    if (slot == kNoScent) return make(BenchAction::BadArgs);
    BenchCommand c = make(BenchAction::Pin);
    c.slot = slot;
    c.diffuser = static_cast<uint8_t>(d - 1);
    return c;
  }

  return make(BenchAction::Unknown);
}

}  // namespace xrpod
