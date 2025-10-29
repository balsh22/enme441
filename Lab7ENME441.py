import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer

GPIO.setmode(GPIO.BCM)

led_pins = [17, 27, 22]
for pin in led_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

pwms = [GPIO.PWM(pin, 1000) for pin in led_pins]
for pwm in pwms:
    pwm.start(0)

# Track brightness levels
led_brightness = [0, 0, 0]

def parsePOSTdata(data):
    data_dict = {}
    idx = data.find('\r\n\r\n') + 4
    data = data[idx:]
    data_pairs = data.split('&')
    for pair in data_pairs:
        key_val = pair.split('=')
        if len(key_val) == 2:
            data_dict[key_val[0]] = key_val[1]
    return data_dict

class LEDHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(self.html_page().encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode("utf-8")

        # Use custom parser instead of urllib.parse
        data = parsePOSTdata(post_data)

        # Get LED and brightness
        led = int(data.get("led", "1")) - 1
        brightness = int(data.get("brightness", "0"))
        led_brightness[led] = brightness

        pwms[led].ChangeDutyCycle(brightness)

        # Refresh page
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

    def html_page(self):
        html = f"""
        <html>
        <form method="POST" action="/">
        <label>Brightness level:</label><br>
        <input type="range" name="brightness" min="0" max="100" value="0"><br>
        <br>
        Select LED:<br>
        <input type="radio" name="led" value="1" checked> LED 1 ({led_brightness[0]}%)<br>
        <input type="radio" name="led" value="2"> LED 2 ({led_brightness[1]}%)<br>
        <input type="radio" name="led" value="3"> LED 3 ({led_brightness[2]}%)<br>
        <br>
        <input type="submit" value="Change Brightness">
        </form>
        </html>
        """
        return html

# Run the server
try:
    print("Starting web server on http://0.0.0.0:8080 ...")
    with HTTPServer(('', 8080), LEDHandler) as server:
        server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    for pwm in pwms:
        pwm.stop()
    GPIO.cleanup()
    print("Server stopped, GPIO cleaned up.")