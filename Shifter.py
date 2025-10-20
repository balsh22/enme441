import RPi.GPIO as GPIO
import time

class Shifter:
  def __init__(self, serialPin, clockPin, latchPin):
    self.serialPin = serialPin
    self.clockPin = clockPin
    self.latchPin = latchPin

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(self.serialPin, GPIO.OUT)
    GPIO.setup(self.clockPin, GPIO.OUT, initial=0)
    GPIO.setup(self.latchPin, GPIO.OUT, initial=0)

  def __ping(self, pin):
    GPIO.output(pin, 1)
    time.sleep(0)
    GPIO.output(pin, 0)

  def shiftByte(self, value):
    for i in range(8):
      GPIO.output(self.serialPin, value & (1 << i))
      self.__ping(self.clockPin)
    self.__ping(self.latchPin)

class Bug:
  def __init__(self, timestep=0.1, x=3, isWrapOn=False):
    self.timestep = timestep
    self.x = x
    self.isWrapOn = isWrapOn
    self.__shifter = Shifter(23, 25, 24)
    self._running = False

  def start(self):
    self._running = True
    while self._running:
      self.__shifter.shiftByte(1 << self.x)
      time.sleep(self.timestep)
      step = random.choice([-1, 1])
      self.x += step
      if self.isWrapOn:
        self.x %= 8
      else:
        self.x = max(0, min(7, self.x))

  def stop(self):
    self._running = False
    self.__shifter.shiftByte(0)
