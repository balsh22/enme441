import RPi.GPIO as GPIO
import time
import random
import threading
from Shifter import Bug

s1, s2, s3 = 17, 27, 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(s1, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(s2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(s3, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

bug = Bug()
last_s2_state = GPIO.input(s2)
running = 0
bug_thread = None

def run_bug():
    bug.start()

try:
    while True:
        s1_state = GPIO.input(s1)
        s2_state = GPIO.input(s2)
        s3_state = GPIO.input(s3)

        if s1_state == 1 and running == 0:
            running = 1
            bug_thread = threading.Thread(target = run_bug, daemon = True)
            bug_thread.start()
        elif s1_state == 0 and running == 1:
            bug.stop()
            running = 0

        if s2_state != last_s2_state:
            bug.isWrapOn = not bug.isWrapOn
            print(f"Wrap mode {bug.isWrapOn}")
        last_s2_state = s2_state

        if s3_state:
            bug.timestep = 0.1 / 3.0
        else:
            bug.timestep = 0.1
        
        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
