import time
import random
from Shifter import Shifter

# instantiate
s = Shifter(serialPin=23, clockPin=25, latchPin=24)

x = 3  # start position
while True:
    s.shiftByte(1 << x)
    time.sleep(0.05)

    # random step: -1 or +1
    x += random.choice([-1, 1])
    if x < 0:
        x = 0
    elif x > 7:
        x = 7
