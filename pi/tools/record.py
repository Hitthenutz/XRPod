#!/usr/bin/env python3
"""
Record the scan sensor's data to CSV, for BME AI-Studio training and for
calibrating the verify settings at the top of pi/scent.py.

One row per completed heater scan (xrpod/scent/+/detect, ~every 18 s).
The temperature, humidity and pressure columns are the scan sensor's own
readings, i.e. what AI-Studio sees; the IAQ sensor's telemetry isn't the
sensor being trained, so it isn't recorded.

    python3 pi/tools/record.py --label clean_air --minutes 30 --out data/clean_air.csv
    python3 pi/tools/record.py --label lavender --out data/lavender.csv

Broker settings come from the same environment variables as the agent
(MQTT_HOST, default 127.0.0.1, MQTT_PORT, MQTT_USER, MQTT_PASS), so the
password never ends up in your shell history. Appends to --out; Ctrl+C stops.
Needs python3-paho-mqtt.
"""

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scent  # noqa: E402

# ---------CSV FORMAT---------
GAS_COLUMNS = [f"gas_ohm_{i}" for i in range(10)]
PROB_COLUMNS = [f"prob_{i}" for i in range(len(scent.CLASS_NAMES))]
COLUMNS = ["timestamp", "node", "label", "atomizer", "duty", "t_c", "rh", "p_hpa",
           *GAS_COLUMNS, *PROB_COLUMNS]


def row(topic, detect, label, when):
    """One CSV row from a parsed detect message. Heater profiles shorter than
    10 steps leave the extra gas columns empty."""
    node = topic.split("/")[2]
    gas = detect["gas_ohm"] + [""] * (10 - len(detect["gas_ohm"]))
    return [when.isoformat(timespec="seconds"), node, label, detect["atomizer"], detect["duty"],
            detect["t_c"], detect["rh"], detect["p_hpa"], *gas, *detect["probs"]]


# ---------RECORDING---------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--label", required=True, help="what's in the air, e.g. clean_air or lavender")
    parser.add_argument("--out", required=True, help="CSV file to append to")
    parser.add_argument("--minutes", type=float, help="stop after this long (default: until Ctrl+C)")
    args = parser.parse_args(argv)

    new_file = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    with open(args.out, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(COLUMNS)
        lock, count = threading.Lock(), [0]

        def on_message(topic, payload):
            detect = scent.parse_detect(scent.decode(payload))
            if detect is None:
                print(f"skipped a bad message on {topic}", file=sys.stderr)
                return
            with lock:
                writer.writerow(row(topic, detect, args.label, datetime.now(timezone.utc)))
                f.flush()
                count[0] += 1
                print(f"\r{count[0]} rows ({args.label})", end="", flush=True)

        link = scent.MqttLink(os.environ.get("MQTT_HOST", "127.0.0.1"),
                              int(os.environ.get("MQTT_PORT", "1883")),
                              os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS"),
                              topics=["xrpod/scent/+/detect"])
        link.start(on_message)
        try:
            end = None if args.minutes is None else time.monotonic() + args.minutes * 60
            while end is None or time.monotonic() < end:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            link.close()
    print(f"\nwrote {count[0]} rows to {args.out}")


if __name__ == "__main__":
    main()
