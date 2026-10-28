#!/usr/bin/env python3
"""Bench test: spin one ARCTIC P12 PWM fan from PCA9685 channel 0.
Run on the Pi: python3 fan_bench_test.py  (needs I2C enabled)"""

import fcntl
import os
import time

I2C_BUS = "/dev/i2c-1"
ADDRESS = 0x40      # PCA9685 default; check with: i2cdetect -y 1
CHANNEL = 0
PWM_HZ = 1000       # PCA9685 tops out around 1.5 kHz
STEPS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
SECONDS_PER_STEP = 5

I2C_SLAVE = 0x0703
MODE1, PRESCALE, LED0_ON_L = 0x00, 0xFE, 0x06


class PCA9685:
    def __init__(self, bus=I2C_BUS, address=ADDRESS):
        self.fd = os.open(bus, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def write(self, reg, value):
        os.write(self.fd, bytes([reg, value & 0xFF]))

    def set_frequency(self, hz):
        prescale = round(25_000_000 / (4096 * hz)) - 1
        self.write(MODE1, 0x10)          # sleep
        self.write(PRESCALE, prescale)
        self.write(MODE1, 0x00)          # wake
        time.sleep(0.005)
        self.write(MODE1, 0x80)          # restart PWM

    def set_duty(self, channel, pct):
        pct = max(0, min(100, pct))
        reg = LED0_ON_L + 4 * channel
        if pct == 0:
            self.write(reg + 3, 0x10)    # full off
            return
        if pct == 100:
            self.write(reg + 3, 0x00)
            self.write(reg + 1, 0x10)    # full on
            return
        off = int(4095 * pct / 100)
        self.write(reg + 0, 0)
        self.write(reg + 1, 0)
        self.write(reg + 2, off & 0xFF)
        self.write(reg + 3, off >> 8)

    def close(self):
        os.close(self.fd)


def main():
    pca = PCA9685()
    try:
        pca.set_frequency(PWM_HZ)
        for pct in STEPS:
            print(f"duty {pct:3d}%  (listen for whine, note how fast it spins)")
            pca.set_duty(CHANNEL, pct)
            time.sleep(SECONDS_PER_STEP)
    finally:
        pca.set_duty(CHANNEL, 0)
        pca.close()
        print("done, channel off")


if __name__ == "__main__":
    main()