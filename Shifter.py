import RPi.GPIO as GPIO
import time

class Shifter:
  def __init__(self, dataPin, clockPin, latchPin):
    self.dataPin = dataPin
    self.clockPin = clockPin
    self.latchPin = latchPin

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(self.dataPin, GPIO.OUT)
    GPIO.setup(self.clockPin, GPIO.OUT, initial=0) # start latch and clock low
    GPIO.setup(self.latchPin, GPIO.OUT, initial=0)

  def __ping(self, p):
    GPIO.output(p, 1)
    time.sleep(0)
    GPIO.output(p, 0)

  def shiftByte(self, b):
    for i in range(8):
      GPIO.output(self.serialPin, b & (1 << i))
      self.__ping(self.clockPin) # add bit to register
    self.__ping(self.latchPin) # send register to output

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
      elif self.x < 0:
        self.x = 0
      elif self.x > 7:
        self.x = 7

  def stop(self):
    self._running = False
    self.__shifter.shiftByte(0)
