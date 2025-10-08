import RPi.GPIO as GPIO
import math
GPIO.setmode(GPIO.BCM)

p = 25    # GPIO pin number
f = 0.2     # frequency (Hz)
basef = 500
phi = math.pi/11

GPIO.setup(p, GPIO.OUT)
pwm = GPIO.PWM(p, basef)        # create PWM object

try:
  start_time = time.time()
  while True:
    t = time.time() - start_time
    brightness = math.sin(2 * math.pi * f * t - phi) ** 2
    pwm.start(brightness * 100)

except KeyboardInterrupt:   # stop gracefully on ctrl-C
  print('\nExiting')

pwm.stop()
GPIO.cleanup()