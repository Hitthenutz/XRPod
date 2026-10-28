#!/bin/sh
# Host test for the atomizer driver: builds src/atomizer.cpp against a fake
# Arduino API three ways and runs each. Run from subsystems/iaq/firmware/scent-node:
#     sh test/host/run.sh            # uses c++ (g++/clang++)
#     CXX="zig c++" sh test/host/run.sh
set -e
CXX=${CXX:-c++}
OUT=${TMPDIR:-/tmp}/atomizer_test
PINS="-DATOMIZER_PIN_0=25 -DATOMIZER_PIN_1=26"

run() {
  name=$1; shift
  # shellcheck disable=SC2086
  $CXX -std=c++17 -Wall -Wextra -Werror -Itest/host -Iinclude -Isrc "$@" \
    src/atomizer.cpp test/host/atomizer_test.cpp -o "$OUT"
  printf '%-22s' "$name"
  "$OUT"
}

run "mist + button press" $PINS -DATOMIZER_TYPE=MIST_MODULE -DATOMIZER_NEEDS_PRESS=1 \
  -DPRESS_PIN_0=32 -DPRESS_PIN_1=33
run "mist, no press" $PINS -DATOMIZER_TYPE=MIST_MODULE
run "AN6 motor" $PINS -DATOMIZER_TYPE=AN6_MOTOR
run "unwired (pins -1)"
