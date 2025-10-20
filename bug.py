import RPi.GPIO as GPIO
import time
from Shifter import Bug  # assumes Bug class is saved in bug_class.py

# Switch pins
s1, s2, s3 = 17, 27, 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(s1, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(s2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(s3, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

bug = Bug()  # default timestep=0.1, x=3, isWrapOn=False
last_s2_state = GPIO.input(s2)
running = False

try:
    while True:
        s1_state = GPIO.input(s1)
        s2_state = GPIO.input(s2)
        s3_state = GPIO.input(s3)

        # --- Start/Stop (s1) ---
        if s1_state and not running:
            running = True
            print("Bug started")
        elif not s1_state and running:
            bug.stop()
            running = False
            print("Bug stopped")

        # --- Wrap toggle (s2) ---
        if s2_state != last_s2_state and s2_state == GPIO.HIGH:
            bug.isWrapOn = not bug.isWrapOn
            print(f"Wrap mode {'ON' if bug.isWrapOn else 'OFF'}")
        last_s2_state = s2_state

        # --- Speed control (s3) ---
        if s3_state:
            bug.timestep = 0.1 / 3.0  # speed ×3
        else:
            bug.timestep = 0.1  # normal speed

        # --- Update LED if running ---
        if running:
            bug._Bug__shifter.shiftByte(1 << bug.x)
            time.sleep(bug.timestep)
            # Move LED one step randomly
            import random
            bug.x += random.choice([-1, 1])
            if bug.isWrapOn:
                bug.x %= 8
            else:
                bug.x = max(0, min(7, bug.x))
        else:
            time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
    print("\nProgram terminated cleanly.")
