// XRPod scent mixer — ESP32 firmware (Arduino IDE / arduino-cli, ESP32 core
// 2.x or 3.x). The Raspberry Pi agent (pi-agent/agent.py) talks to it over
// serial and is the only thing that tells it what to do.
//
// Protocol: 115200 8N1, ASCII, one command per line ('\n'; '\r' ignored).
//   MIX lavender=0 pine=40 citrus=0 ocean=0 rain=0   set every diffuser (0-100 %)
//   OFF                                              all diffusers off
//   PING                                             liveness check
// Replies: "OK" or "ERR <reason>". Anything else it prints starts with "#"
// and is ignored by the Pi.
//
// Fail-safe:
//   * Every output starts OFF at boot.
//   * A MIX is validated in full before anything changes; one bad token
//     rejects the whole command and keeps the previous mix.
//   * Scents left out of a MIX are set to 0.
//   * If no valid command arrives for WATCHDOG_MS, every diffuser turns off.
//     The Pi re-sends the mix every few seconds, so this only fires when the
//     Pi agent dies, hangs or the cable is unplugged.
//   * Total output is capped at MAX_TOTAL_PCT so a mix can't overload the
//     supply.

#include <Arduino.h>

// --- Fill in for your board -------------------------------------------------
// Same names and order as SCENTS in src/lib/podSettings.js (minus "none").
const char *const SCENT_NAMES[] = {"lavender", "pine", "citrus", "ocean", "rain"};
// TODO(hardware): the GPIO that drives each diffuser's MOSFET / driver.
// Avoid strapping pins (0, 2, 5, 12, 15) and input-only pins (34-39).
const int SCENT_PINS[] = {16, 17, 18, 19, 21};

const uint32_t BAUD = 115200;
const uint32_t WATCHDOG_MS = 10000;
// PWM settings. If your atomizer modules only work fully on or off, set
// PWM_FREQ_HZ low (e.g. 2) so "intensity" becomes an on/off duty cycle.
const uint32_t PWM_FREQ_HZ = 1000;
const uint8_t PWM_BITS = 10;
const int MAX_TOTAL_PCT = 200;
// ---------------------------------------------------------------------------

const size_t SCENT_COUNT = sizeof(SCENT_NAMES) / sizeof(SCENT_NAMES[0]);
static_assert(SCENT_COUNT == sizeof(SCENT_PINS) / sizeof(SCENT_PINS[0]),
              "SCENT_NAMES and SCENT_PINS must be the same length");

const size_t LINE_MAX = 128;
char line[LINE_MAX];
size_t lineLen = 0;
bool lineOverflow = false;

int levels[SCENT_COUNT] = {0};
uint32_t lastCommandMs = 0;
bool watchdogTripped = false;

void writeDuty(size_t i, int pct) {
  uint32_t duty = (uint32_t)pct * ((1u << PWM_BITS) - 1) / 100;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(SCENT_PINS[i], duty);
#else
  ledcWrite(i, duty);  // core 2.x: channel i is attached to SCENT_PINS[i]
#endif
}

void applyLevels(const int *next) {  // next has SCENT_COUNT entries
  for (size_t i = 0; i < SCENT_COUNT; i++) {
    levels[i] = next[i];
    writeDuty(i, next[i]);
  }
}

void allOff() {
  int zeros[SCENT_COUNT] = {0};
  applyLevels(zeros);
}

// Parses a whole integer 0-100. Rejects "", "50x", "-1", "101".
bool parsePct(const char *s, int &out) {
  if (*s == '\0') return false;
  int value = 0;
  for (const char *p = s; *p; p++) {
    if (*p < '0' || *p > '9') return false;
    value = value * 10 + (*p - '0');
    if (value > 100) return false;
  }
  out = value;
  return true;
}

int scentIndex(const char *name) {
  for (size_t i = 0; i < SCENT_COUNT; i++) {
    if (strcmp(name, SCENT_NAMES[i]) == 0) return (int)i;
  }
  return -1;
}

// Validates every "name=pct" token first, then applies them all at once.
bool handleMix(char *args, String &error) {
  int next[SCENT_COUNT] = {0};
  bool seen[SCENT_COUNT] = {false};
  int total = 0;

  for (char *tok = strtok(args, " "); tok; tok = strtok(nullptr, " ")) {
    char *eq = strchr(tok, '=');
    if (!eq) {
      error = String("bad token '") + tok + "'";
      return false;
    }
    *eq = '\0';
    int i = scentIndex(tok);
    if (i < 0) {
      error = String("unknown scent '") + tok + "'";
      return false;
    }
    if (seen[i]) {
      error = String("duplicate scent '") + tok + "'";
      return false;
    }
    int pct;
    if (!parsePct(eq + 1, pct)) {
      error = String("bad level for ") + tok + " (0-100)";
      return false;
    }
    seen[i] = true;
    next[i] = pct;
    total += pct;
  }
  if (total > MAX_TOTAL_PCT) {
    error = String("total ") + total + "% exceeds " + MAX_TOTAL_PCT + "%";
    return false;
  }
  applyLevels(next);
  return true;
}

void handleLine(char *cmd) {
  String error;
  bool ok;

  if (strncmp(cmd, "MIX", 3) == 0 && (cmd[3] == ' ' || cmd[3] == '\0')) {
    ok = handleMix(cmd + 3, error);
  } else if (strcmp(cmd, "OFF") == 0) {
    allOff();
    ok = true;
  } else if (strcmp(cmd, "PING") == 0) {
    ok = true;
  } else {
    error = "unknown command";
    ok = false;
  }

  if (ok) {
    lastCommandMs = millis();
    if (watchdogTripped) {
      watchdogTripped = false;
      Serial.println("# link restored");
    }
    Serial.println("OK");
  } else {
    Serial.print("ERR ");
    Serial.println(error);
  }
}

void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (lineOverflow) {
        Serial.println("ERR line too long");
      } else if (lineLen > 0) {
        line[lineLen] = '\0';
        handleLine(line);
      }
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < LINE_MAX - 1) {
      line[lineLen++] = c;
    } else {
      lineOverflow = true;  // drop the rest of this line
    }
  }
}

void setup() {
  // Outputs low before anything else, so a reboot never leaves one on.
  for (size_t i = 0; i < SCENT_COUNT; i++) {
    pinMode(SCENT_PINS[i], OUTPUT);
    digitalWrite(SCENT_PINS[i], LOW);
  }

  Serial.begin(BAUD);

  for (size_t i = 0; i < SCENT_COUNT; i++) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    bool attached = ledcAttach(SCENT_PINS[i], PWM_FREQ_HZ, PWM_BITS);
#else
    bool attached = ledcSetup(i, PWM_FREQ_HZ, PWM_BITS) != 0;
    if (attached) ledcAttachPin(SCENT_PINS[i], i);
#endif
    if (!attached) {
      Serial.printf("# PWM setup failed on GPIO %d\n", SCENT_PINS[i]);
    }
  }
  allOff();

  lastCommandMs = millis();
  watchdogTripped = true;  // nothing runs until the Pi sends a command
  Serial.println("# xrpod scent mixer ready");
}

void loop() {
  readSerial();

  // Unsigned subtraction stays correct when millis() wraps (~49 days).
  if (!watchdogTripped && millis() - lastCommandMs > WATCHDOG_MS) {
    allOff();
    watchdogTripped = true;
    Serial.println("# watchdog: no command from Pi, all diffusers off");
  }

  delay(2);
}
