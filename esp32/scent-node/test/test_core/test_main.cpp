// Unit tests for lib/scent_core. Run on a PC: pio test -e native
#include <string.h>
#include <unity.h>

#include <CommandParser.h>
#include <Messages.h>
#include <ScentController.h>
#include <ScentDetector.h>

using namespace xrpod;

static const ScentSlot kSlots[3] = {
    {"lavender", {25, 26}},
    {"pine", {27, 13}},
    {"citrus", {32, 33}},
};

// Records pin levels and the worst case of how many scents were on at once.
class FakePort : public OutputPort {
 public:
  bool level[64] = {};
  int writes = 0;
  int maxScentsOn = 0;
  void write(uint8_t pin, bool on) override {
    level[pin] = on;
    ++writes;
    int scentsOn = 0;
    for (const ScentSlot &s : kSlots) {
      if (level[s.pins[0]] || level[s.pins[1]]) ++scentsOn;
    }
    if (scentsOn > maxScentsOn) maxScentsOn = scentsOn;
  }
  bool anyOn() const {
    for (const ScentSlot &s : kSlots)
      if (level[s.pins[0]] || level[s.pins[1]]) return true;
    return false;
  }
};

static const ScentControllerConfig kCfg = {kSlots, 3, 2, 10000, 15000};

static ParseResult parse(const char *json, ScentCommand &out) {
  return parseScentCommand(json, strlen(json), kSlots, 3, out);
}

void setUp() {}
void tearDown() {}

// ---- clampPct ---------------------------------------------------------------
void test_clamp_pct() {
  TEST_ASSERT_EQUAL_UINT8(0, clampPct(NAN));
  TEST_ASSERT_EQUAL_UINT8(0, clampPct(INFINITY));
  TEST_ASSERT_EQUAL_UINT8(0, clampPct(-INFINITY));
  TEST_ASSERT_EQUAL_UINT8(0, clampPct(-5));
  TEST_ASSERT_EQUAL_UINT8(42, clampPct(42.9));
  TEST_ASSERT_EQUAL_UINT8(100, clampPct(150));
}

// ---- duty math --------------------------------------------------------------
void test_diffuser_split() {
  TEST_ASSERT_EQUAL_UINT8(60, diffuserDutyPct(30, 0, 2));
  TEST_ASSERT_EQUAL_UINT8(0, diffuserDutyPct(30, 1, 2));
  TEST_ASSERT_EQUAL_UINT8(100, diffuserDutyPct(50, 0, 2));
  TEST_ASSERT_EQUAL_UINT8(0, diffuserDutyPct(50, 1, 2));
  TEST_ASSERT_EQUAL_UINT8(100, diffuserDutyPct(75, 0, 2));
  TEST_ASSERT_EQUAL_UINT8(50, diffuserDutyPct(75, 1, 2));
  TEST_ASSERT_EQUAL_UINT8(100, diffuserDutyPct(100, 1, 2));
  TEST_ASSERT_EQUAL_UINT8(0, diffuserDutyPct(80, 2, 2));  // out of range index
  TEST_ASSERT_EQUAL_UINT8(0, diffuserDutyPct(80, 0, 0));
}

void test_duty_window() {
  TEST_ASSERT_TRUE(dutyOnAt(60, 0, 10000));
  TEST_ASSERT_TRUE(dutyOnAt(60, 5999, 10000));
  TEST_ASSERT_FALSE(dutyOnAt(60, 6000, 10000));
  TEST_ASSERT_TRUE(dutyOnAt(60, 10000, 10000));  // next window
  TEST_ASSERT_FALSE(dutyOnAt(0, 0, 10000));
  TEST_ASSERT_TRUE(dutyOnAt(100, 9999, 10000));
  TEST_ASSERT_FALSE(dutyOnAt(50, 0, 0));
}

// ---- command parsing ------------------------------------------------------------
void test_parse_valid() {
  ScentCommand c = kScentOff;
  TEST_ASSERT_EQUAL(ParseResult::Ok,
                    parse("{\"selected_scent\":\"pine\",\"scent_intensity_pct\":60}", c));
  TEST_ASSERT_EQUAL_INT8(1, c.slot);
  TEST_ASSERT_EQUAL_UINT8(60, c.intensityPct);
}

void test_parse_clamps_and_truncates() {
  ScentCommand c = kScentOff;
  parse("{\"selected_scent\":\"citrus\",\"scent_intensity_pct\":250}", c);
  TEST_ASSERT_EQUAL_UINT8(100, c.intensityPct);
  parse("{\"selected_scent\":\"citrus\",\"scent_intensity_pct\":33.7}", c);
  TEST_ASSERT_EQUAL_UINT8(33, c.intensityPct);
}

void test_parse_off_cases() {
  const char *offs[] = {
      "{\"selected_scent\":\"none\",\"scent_intensity_pct\":60}",
      "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":0}",
      "{\"selected_scent\":\"pine\"}",
      "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":true}",
      "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":\"60\"}",
      "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":null}",
      "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":-10}",
      "{\"selected_scent\":42,\"scent_intensity_pct\":60}",
      "{}",
  };
  for (const char *j : offs) {
    ScentCommand c = {1, 99};
    TEST_ASSERT_EQUAL_MESSAGE(ParseResult::Ok, parse(j, c), j);
    TEST_ASSERT_EQUAL_INT8_MESSAGE(kNoScent, c.slot, j);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, c.intensityPct, j);
  }
}

void test_parse_unknown_scent_is_off() {
  ScentCommand c = {1, 99};
  TEST_ASSERT_EQUAL(ParseResult::UnknownScent,
                    parse("{\"selected_scent\":\"ocean\",\"scent_intensity_pct\":60}", c));
  TEST_ASSERT_EQUAL_INT8(kNoScent, c.slot);
}

void test_parse_rejects_garbage() {
  ScentCommand c = {1, 99};
  TEST_ASSERT_EQUAL(ParseResult::BadJson, parse("{not json", c));
  TEST_ASSERT_EQUAL(ParseResult::BadJson, parse("", c));
  TEST_ASSERT_EQUAL(ParseResult::NotObject, parse("[1,2]", c));
  TEST_ASSERT_EQUAL(ParseResult::NotObject, parse("\"pine\"", c));
  TEST_ASSERT_EQUAL_INT8(1, c.slot);  // untouched
  TEST_ASSERT_EQUAL(ParseResult::BadJson, parseScentCommand(nullptr, 5, kSlots, 3, c));
}

void test_parse_respects_length() {
  // Payload not NUL-terminated (as from MQTT): only the first len bytes count.
  const char buf[] = "{\"selected_scent\":\"pine\",\"scent_intensity_pct\":60}GARBAGE";
  ScentCommand c = kScentOff;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseScentCommand(buf, strlen(buf) - 7, kSlots, 3, c));
  TEST_ASSERT_EQUAL_INT8(1, c.slot);
}

// ---- controller ---------------------------------------------------------------
void test_begin_drives_all_off() {
  FakePort port;
  for (bool &l : port.level) l = true;
  ScentController sc(port, kCfg);
  TEST_ASSERT_TRUE(sc.begin());
  TEST_ASSERT_FALSE(port.anyOn());
  TEST_ASSERT_EQUAL_STRING("none", sc.activeName());
}

void test_bad_config_locks_off() {
  FakePort port;
  ScentControllerConfig bad = kCfg;
  bad.diffusersPerSlot = 9;
  ScentController sc(port, bad);
  TEST_ASSERT_FALSE(sc.begin());
  sc.apply({0, 100}, 0);
  TEST_ASSERT_FALSE(port.anyOn());
  TEST_ASSERT_EQUAL_STRING("bad_config", reasonName(sc.reason()));
}

void test_apply_and_duty_cycle() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  sc.apply({0, 30}, 1000);  // A at 60 %, B off
  TEST_ASSERT_TRUE(port.level[25]);
  TEST_ASSERT_FALSE(port.level[26]);
  sc.apply({0, 30}, 7000);  // 6 s in: past A's on-time (command refreshes timeout)
  TEST_ASSERT_FALSE(port.level[25]);
  sc.tick(11000);  // 10 s in: next window
  TEST_ASSERT_TRUE(port.level[25]);
}

void test_only_one_scent_ever_on() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  uint32_t t = 0;
  for (int i = 0; i < 30; ++i, t += 700) {
    sc.apply({static_cast<int8_t>(i % 3), static_cast<uint8_t>(40 + i * 2)}, t);
    sc.tick(t + 350);
  }
  TEST_ASSERT_EQUAL_INT(1, port.maxScentsOn);
}

void test_switching_turns_previous_off() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  sc.apply({0, 100}, 0);
  TEST_ASSERT_TRUE(port.level[25] && port.level[26]);
  sc.apply({2, 100}, 100);
  TEST_ASSERT_FALSE(port.level[25] || port.level[26]);
  TEST_ASSERT_TRUE(port.level[32] && port.level[33]);
  TEST_ASSERT_EQUAL_STRING("citrus", sc.activeName());
}

void test_command_timeout_turns_off() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  sc.apply({1, 100}, 0);
  sc.tick(15000);
  TEST_ASSERT_TRUE(port.anyOn());
  sc.tick(15001);
  TEST_ASSERT_FALSE(port.anyOn());
  TEST_ASSERT_EQUAL_STRING("cmd_timeout", reasonName(sc.reason()));
}

void test_timeout_survives_millis_wrap() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  uint32_t start = 0xFFFFF000u;
  sc.apply({1, 100}, start);
  sc.tick(start + 10000);  // wraps past 0
  TEST_ASSERT_TRUE(port.anyOn());
  sc.tick(start + 20000);
  TEST_ASSERT_FALSE(port.anyOn());
}

void test_off_and_change_count() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  uint32_t c0 = sc.changeCount();
  sc.apply({0, 50}, 0);
  uint32_t c1 = sc.changeCount();
  TEST_ASSERT_TRUE(c1 != c0);
  sc.apply({0, 50}, 100);  // same command again: no change
  TEST_ASSERT_EQUAL_UINT32(c1, sc.changeCount());
  sc.off(Reason::MqttLost);
  TEST_ASSERT_FALSE(port.anyOn());
  TEST_ASSERT_TRUE(sc.changeCount() != c1);
  TEST_ASSERT_EQUAL_STRING("mqtt_lost", reasonName(sc.reason()));
}

void test_no_redundant_writes() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  sc.apply({0, 100}, 0);
  int w = port.writes;
  for (uint32_t t = 1; t < 100; ++t) sc.tick(t);
  TEST_ASSERT_EQUAL_INT(w, port.writes);
}

// ---- detector ---------------------------------------------------------------
void test_detector_warmup_and_detect() {
  ScentDetector d({5, 0.2f, 0.25f, 2});
  for (int i = 0; i < 4; ++i) d.update(100000, false);
  TEST_ASSERT_FALSE(d.ready());
  d.update(100000, false);
  TEST_ASSERT_TRUE(d.ready());
  TEST_ASSERT_FLOAT_WITHIN(1, 100000, d.baselineOhms());

  d.update(60000, true);  // 40 % drop, first sample
  TEST_ASSERT_FALSE(d.detected());
  d.update(60000, true);  // confirmed
  TEST_ASSERT_TRUE(d.detected());
  TEST_ASSERT_FLOAT_WITHIN(1, 100000, d.baselineOhms());  // not learned while active
}

void test_detector_ignores_lingering_scent_and_bad_reads() {
  ScentDetector d({3, 0.5f, 0.25f, 1});
  for (int i = 0; i < 3; ++i) d.update(100000, false);
  d.update(50000, false);  // scent off but air still scented: keep baseline
  TEST_ASSERT_FLOAT_WITHIN(1, 100000, d.baselineOhms());
  TEST_ASSERT_TRUE(d.detected());
  d.update(NAN, false);
  d.update(-1, false);
  d.update(0, false);
  TEST_ASSERT_FLOAT_WITHIN(1, 100000, d.baselineOhms());
  d.update(98000, false);  // clean again
  TEST_ASSERT_FALSE(d.detected());
}

// ---- messages ---------------------------------------------------------------
void test_state_json() {
  FakePort port;
  ScentController sc(port, kCfg);
  sc.begin();
  sc.apply({0, 75}, 0);
  char buf[256];
  size_t n = buildStateJson(sc, 12, buf, sizeof(buf));
  TEST_ASSERT_TRUE(n > 0);
  TEST_ASSERT_EQUAL_STRING(
      "{\"selected_scent\":\"lavender\",\"scent_intensity_pct\":75,"
      "\"diffusers\":[true,true],\"reason\":\"command\",\"uptime_s\":12}",
      buf);
}

void test_reading_json_and_overflow() {
  ScentDetector d;
  IaqReading r = {22.44f, 41.26f, 1012.31f, 85230.0f};
  char buf[256];
  TEST_ASSERT_TRUE(buildReadingJson(r, d, "none", buf, sizeof(buf)) > 0);
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"temp_c\":22.4"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"gas_kohm\":85.2"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"scent_detected\":false"));
  char tiny[16];
  TEST_ASSERT_EQUAL_UINT(0, buildReadingJson(r, d, "none", tiny, sizeof(tiny)));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_clamp_pct);
  RUN_TEST(test_diffuser_split);
  RUN_TEST(test_duty_window);
  RUN_TEST(test_parse_valid);
  RUN_TEST(test_parse_clamps_and_truncates);
  RUN_TEST(test_parse_off_cases);
  RUN_TEST(test_parse_unknown_scent_is_off);
  RUN_TEST(test_parse_rejects_garbage);
  RUN_TEST(test_parse_respects_length);
  RUN_TEST(test_begin_drives_all_off);
  RUN_TEST(test_bad_config_locks_off);
  RUN_TEST(test_apply_and_duty_cycle);
  RUN_TEST(test_only_one_scent_ever_on);
  RUN_TEST(test_switching_turns_previous_off);
  RUN_TEST(test_command_timeout_turns_off);
  RUN_TEST(test_timeout_survives_millis_wrap);
  RUN_TEST(test_off_and_change_count);
  RUN_TEST(test_no_redundant_writes);
  RUN_TEST(test_detector_warmup_and_detect);
  RUN_TEST(test_detector_ignores_lingering_scent_and_bad_reads);
  RUN_TEST(test_state_json);
  RUN_TEST(test_reading_json_and_overflow);
  return UNITY_END();
}
