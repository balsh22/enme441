import RPi.GPIO as GPIO
import math
import time
import threading
GPIO.setmode(GPIO.BCM)
pos_neg = 1

pins = [14, 15, 18, 23, 24, 25, 8, 7, 12, 16]
p = 25    # GPIO pin number
f = 0.2     # frequency (Hz)
basef = 500
phi = math.pi/11

in1 = 26
GPIO.setup(in1, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def callbackFunction(direction):
  global pos_neg
  pos_neg *= -1

GPIO.add_event_detect(in1, GPIO.RISING, callback=callbackFunction, bouncetime=100)

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
      brightness = math.sin(2 * math.pi * f * t - (phi * n * pos_neg)) ** 2
      pin.start(brightness * 100)

except KeyboardInterrupt:   # stop gracefully on ctrl-C
  print('\nExiting')

finally:
  for pin in pins2:
    pwm.stop()
  GPIO.cleanup()