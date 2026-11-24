// Unit tests for lib/iaq_core. Run on a PC: pio test -e native
#include <string.h>
#include <unity.h>

#include <IaqMessages.h>
#include <ScentDetector.h>

using namespace xrpod;

void setUp() {}
void tearDown() {}

// ---- detector ---------------------------------------------------------------

void test_detector_warmup_and_detect() {
  ScentDetector d({5, 0.2f, 0.25f, 2});
  for (int i = 0; i < 5; ++i) d.update(100000.0f, false);
  TEST_ASSERT_TRUE(d.ready());
  TEST_ASSERT_FALSE(d.detected());
  d.update(60000.0f, true);  // 40 % drop, once: not yet
  TEST_ASSERT_FALSE(d.detected());
  d.update(60000.0f, true);  // twice in a row: detected
  TEST_ASSERT_TRUE(d.detected());
  d.update(100000.0f, false);
  TEST_ASSERT_FALSE(d.detected());
}

void test_detector_ignores_lingering_scent_and_bad_reads() {
  ScentDetector d({3, 0.5f, 0.25f, 1});
  for (int i = 0; i < 3; ++i) d.update(100000.0f, false);
  float baseline = d.baselineOhms();
  d.update(50000.0f, false);  // scent still in the air after it stopped
  TEST_ASSERT_EQUAL_FLOAT(baseline, d.baselineOhms());
  d.update(0.0f, false);
  d.update(-5.0f, false);
  d.update(NAN, false);
  TEST_ASSERT_EQUAL_FLOAT(baseline, d.baselineOhms());
}

void test_detector_not_ready_never_detects() {
  ScentDetector d({10, 0.2f, 0.25f, 1});
  d.update(100000.0f, false);
  d.update(10000.0f, true);
  TEST_ASSERT_FALSE(d.ready());
  TEST_ASSERT_FALSE(d.detected());
}

// ---- messages ---------------------------------------------------------------

void test_reading_json_has_the_pi_fields() {
  ScentDetector d;
  IaqReading r = {22.46f, 41.24f, 1013.25f, 85300.0f};
  char buf[320];
  size_t n = buildReadingJson(r, d, "lavender", buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN(0, n);
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"temp_c\":22.5"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"humidity_pct\":41.2"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"pressure_hpa\":1013.3"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"gas_kohm\":85.3"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"baseline_ready\":false"));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"scent_active\":\"lavender\""));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"scent_detected\":false"));
}

void test_reading_json_defaults_and_overflow() {
  ScentDetector d;
  IaqReading r = {NAN, 40.0f, 1000.0f, 1000.0f};
  char buf[320];
  TEST_ASSERT_GREATER_THAN(0, buildReadingJson(r, d, nullptr, buf, sizeof(buf)));
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"temp_c\":0"));  // junk becomes 0, never NaN in JSON
  TEST_ASSERT_NOT_NULL(strstr(buf, "\"scent_active\":\"none\""));
  char tiny[16];
  TEST_ASSERT_EQUAL(0, buildReadingJson(r, d, "pine", tiny, sizeof(tiny)));
}

void test_parse_active_scent() {
  char out[24] = "none";
  const char *state = "{\"selected_scent\":\"citrus\",\"scent_intensity_pct\":60,\"diffusers\":[true,false]}";
  TEST_ASSERT_TRUE(parseActiveScent(state, strlen(state), out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("citrus", out);
  const char *off = "{\"selected_scent\":\"none\"}";
  TEST_ASSERT_TRUE(parseActiveScent(off, strlen(off), out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("none", out);
}

void test_parse_active_scent_rejects_garbage() {
  char out[8] = "none";
  const char *bad[] = {"", "nope", "{}", "{\"selected_scent\":5}", "{\"selected_scent\":\"\"}",
                       "{\"selected_scent\":\"far-too-long-name\"}"};
  for (const char *b : bad) {
    TEST_ASSERT_FALSE(parseActiveScent(b, strlen(b), out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("none", out);
  }
  TEST_ASSERT_FALSE(parseActiveScent(nullptr, 0, out, sizeof(out)));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_detector_warmup_and_detect);
  RUN_TEST(test_detector_ignores_lingering_scent_and_bad_reads);
  RUN_TEST(test_detector_not_ready_never_detects);
  RUN_TEST(test_reading_json_has_the_pi_fields);
  RUN_TEST(test_reading_json_defaults_and_overflow);
  RUN_TEST(test_parse_active_scent);
  RUN_TEST(test_parse_active_scent_rejects_garbage);
  return UNITY_END();
}
