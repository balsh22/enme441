import RPi.GPIO as GPIO
import math
import time
GPIO.setmode(GPIO.BCM)

pins = [14, 15, 18, 23, 24, 25, 8, 7, 12, 16]
p = 25    # GPIO pin number
f = 0.2     # frequency (Hz)
basef = 500
phi = math.pi/11

pins2 = []
for pin in pins:
  GPIO.setup(pin, GPIO.OUT)
  pwm = GPIO.PWM(pin, basef)        # create PWM object
  pins2.append(pwm)

try:
  start_time = time.time()
  while True:
    t = time.time() - start_time
    for n, pin in enumerate(pins2):
      brightness = math.sin(2 * math.pi * f * t - (phi * n)) ** 2
      pins2.start(brightness * 100)

except KeyboardInterrupt:   # stop gracefully on ctrl-C
  print('\nExiting')

finally:
  for pin in pins2:
    pwm.stop()
  GPIO.cleanup()