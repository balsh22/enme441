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

# --- robust parser + URL-decode (no urllib.parse) ---
def _url_decode(s: str) -> str:
    # Replace '+' with space, then percent-decode (handles UTF-8 bytes)
    s = s.replace('+', ' ')
    b = bytearray()
    i = 0
    length = len(s)
    while i < length:
        ch = s[i]
        if ch == '%' and i + 2 < length:
            hex_part = s[i+1:i+3]
            try:
                b.append(int(hex_part, 16))
                i += 3
                continue
            except ValueError:
                # If invalid % sequence, treat '%' as literal
                b.append(ord('%'))
                i += 1
                continue
        else:
            b.append(ord(ch))
            i += 1
    try:
        return b.decode('utf-8', errors='replace')
    except Exception:
        return b.decode('latin-1', errors='replace')

def parsePOSTdata(data: str) -> dict:
    """
    Accepts either:
      - full HTTP request text (headers + \r\n\r\n + body), or
      - just the request body ("a=1&b=2")
    Returns a dict of decoded keys -> decoded values.
    """
    data_dict = {}
    if not data:
        return data_dict

    # If headers are present, extract body after the blank line
    idx = data.find('\r\n\r\n')
    if idx != -1:
        body = data[idx+4:]
    else:
        body = data

    if not body:
        return data_dict

    pairs = body.split('&')
    for pair in pairs:
        if '=' in pair:
            key, val = pair.split('=', 1)
            key_dec = _url_decode(key)
            val_dec = _url_decode(val)
            data_dict[key_dec] = val_dec
    return data_dict
# --------------------------------------------------------

class LEDHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(self.html_page().encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode("utf-8")

        # parse the incoming data (works for body-only or full request text)
        data = parsePOSTdata(post_data)

        # Safely parse led and brightness
        try:
            led = int(data.get("led", "1")) - 1
            if led < 0 or led >= len(led_brightness):
                led = 0
        except ValueError:
            led = 0

        try:
            brightness = int(data.get("brightness", "0"))
            if brightness < 0:
                brightness = 0
            elif brightness > 100:
                brightness = 100
        except ValueError:
            brightness = 0

        # Update internal state and PWM
        led_brightness[led] = brightness
        pwms[led].ChangeDutyCycle(brightness)

        # Redirect back to the main page so the displayed percentages update
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

    def html_page(self):
        # Keep slider default and radio default as you requested,
        # but display current percentages from led_brightness.
        html = f"""
        <html>
        <head>
          <meta charset="utf-8">
          <title>LED Control</title>
        </head>
        <body>
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
        </body>
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
